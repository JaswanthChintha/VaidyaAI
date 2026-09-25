'use strict';

const crypto = require('crypto');

const Report = require('../models/Report');
const asyncHandler = require('../utils/asyncHandler');
const { sendSuccess } = require('../utils/apiResponse');
const { ownerScopedFilter, assertCanAccess, OWNER_ONLY } = require('../utils/ownership');
const aiService = require('../services/aiServiceClient');
const config = require('../config/env');

// The ai-service's names for a finding with no answer YET -- the model never
// answered (every attempt raised), or its description was still being written
// when the ai-service's deadline passed. Neither is a gate refusal, so a
// result carrying either is never cached. See `getFindingContext`.
const MODEL_UNAVAILABLE = 'model_unavailable';
const IN_PROGRESS = 'in_progress';
const NOT_AN_ANSWER = new Set([MODEL_UNAVAILABLE, IN_PROGRESS]);

/**
 * Module 33 - the patient's closing summary, rewritten for flow.
 *
 *   POST /reports/:id/summary-prose   { sentences: [...], names: [...] }
 *
 * ==========================================================================
 * WHY THE CALLER SENDS THE SENTENCES
 * ==========================================================================
 *
 * The summary is COMPOSED BY THE PAGE, from the cards it is actually
 * rendering - `Dashboard.jsx`'s `InShort` counts the grouped arrays rather
 * than the payload's own counters, because MEMORY.md section 6u records this
 * project printing `unmapped_count: 0` over a list of sixty-three. Recomposing
 * it here would be a second implementation of those rules that could disagree
 * with the first, and the screen would then be arguing with its own summary.
 *
 * So the page sends what it would otherwise render, and the ai-service rewrites
 * exactly that. Nothing in this path derives a finding.
 *
 * ==========================================================================
 * CACHED PER ANALYSIS AND PER COMPOSITION, NEVER PER PAGE VIEW
 * ==========================================================================
 *
 * The free tier is twenty calls a day per model. One call per page view is one
 * reader. The cache key is the analysis version AND a hash of the sentences:
 * the version alone is not enough, because the page can change what it composes
 * without the analysis changing at all, and serving yesterday's prose about
 * different sentences is the worst of both.
 *
 * A REFUSAL IS CACHED TOO, for the reason `doctorSummaryController` gives: a
 * safety rejection costs two model calls and retrying it every page view would
 * spend the day's quota on one reader. `model_unavailable` is the exception -
 * that is a configuration state, not an answer about this report.
 */

const PROSE_PROJECTION = '+summaryProse';

/**
 * ONE MODEL CALL FOR TWO IDENTICAL REQUESTS IN FLIGHT.
 *
 * Measured 2026-09-24: every page load sent both POSTs below TWICE, a few
 * milliseconds apart -- `<React.StrictMode>` mounts the dashboard twice in
 * development, and the first mount's `cancelled` flag only makes the page
 * ignore its answer, not un-send it. Both missed the cache (nothing is stored
 * until the first returns), so each finding was generated twice: Test 3's
 * HbA1c cost two calls for one sentence. Two tabs, or a revisit while a slow
 * call is running, do the same in production.
 *
 * The second request now waits on the first one's promise instead of calling
 * the ai-service. Keyed like the cache -- report, analysis version, content
 * hash -- so a different question is never answered with this one. Entries
 * live only while the call is running and are removed however it ends, so a
 * failure is never replayed to a later request. OWNERSHIP IS NOT SHARED: each
 * request passes its own `assertCanAccess` before it can reach this map, and
 * the report id is in the key.
 */
const inFlight = new Map();

function coalesce(key, run) {
  const running = inFlight.get(key);
  if (running) return running;
  const promise = (async () => {
    try {
      return await run();
    } finally {
      inFlight.delete(key);
    }
  })();
  inFlight.set(key, promise);
  return promise;
}

/** Stable across key order and whitespace, so the same page does not re-ask. */
function fingerprint(sentences, names) {
  const payload = JSON.stringify({
    s: (sentences || []).map((x) => String(x).trim()),
    n: (names || []).map((x) => String(x).trim()),
  });
  return crypto.createHash('sha256').update(payload).digest('hex').slice(0, 32);
}

const getSummaryProse = asyncHandler(async (req, res) => {
  // The SAME helper shape every other report controller uses: the USER, not
  // the request, and the id goes in `base`. Passing `req` builds no filter at
  // all -- `ownerScopedFilter` finds no identity on it and throws rather than
  // returning one that would match every document.
  const filter = ownerScopedFilter(req.user, { ...OWNER_ONLY, base: { _id: req.params.id } });
  const report = await Report.findOne(filter).select(PROSE_PROJECTION);
  // 404 BEFORE 403, the same order as every other report route: naming a
  // report that is not yours must not confirm that it exists.
  assertCanAccess(req.user, report, { ...OWNER_ONLY });

  const sentences = Array.isArray(req.body?.sentences) ? req.body.sentences : [];
  const names = Array.isArray(req.body?.names) ? req.body.names : [];
  const version = report.analysis?.version || report.analysisVersion || null;
  const key = fingerprint(sentences, names);

  const cached = report.summaryProse;
  if (
    cached
    && cached.sentencesHash === key
    && cached.analysisVersion === version
    && cached.outcome
    && cached.outcome !== 'model_unavailable'
  ) {
    return sendSuccess(res, 200, { prose: cached });
  }

  const data = await coalesce(`prose:${report._id}:${version}:${key}`, async () => {
    let written = null;
    try {
      written = await aiService.rewriteSummaryProse({
        sentences,
        names,
        requestId: aiService.newRequestId(report._id.toString()),
      });
    } catch (err) {
      // NEVER AN ERROR TO THE PAGE. This is a presentation improvement on a
      // summary that already renders; a failure here must cost nothing, so the
      // reason is logged for correlation and the caller is told there is no
      // prose. Same shape as `resolveNarrative`.
      if (!config.isTest) {
        // eslint-disable-next-line no-console
        console.warn(
          `[summary-prose] reportId=${report._id} outcome=unavailable ${err.message}`
        );
      }
      return { prose: null };
    }

    if (!written || typeof written !== 'object') {
      return { prose: null };
    }

    const stored = { ...written, analysisVersion: version, sentencesHash: key };
    try {
      await Report.updateOne({ _id: report._id }, { $set: { summaryProse: stored } });
    } catch (err) {
      if (!config.isTest) {
        // eslint-disable-next-line no-console
        console.warn(`[summary-prose] reportId=${report._id} outcome=not_cached ${err.message}`);
      }
    }
    return { prose: stored };
  });
  return sendSuccess(res, 200, data);
});

/**
 * Module 34 - general context for the tests already marked out of range.
 *
 *   POST /reports/:id/finding-context   { findings: [{test_name, direction}] }
 *
 * Same shape as `getSummaryProse` above and cached the same way, because it
 * has the same problem: one model call per finding, and a free tier of twenty
 * a day. The page derives the findings from the rows it is rendering, so the
 * key is the analysis version AND a hash of what was asked.
 *
 * THE BODY CARRIES NO VALUES AND CANNOT. The ai-service forbids extra fields;
 * this controller forwards only `test_name` and `direction`, rebuilt here
 * rather than passed through, so a client cannot widen the payload by sending
 * more.
 */
const getFindingContext = asyncHandler(async (req, res) => {
  const filter = ownerScopedFilter(req.user, { ...OWNER_ONLY, base: { _id: req.params.id } });
  const report = await Report.findOne(filter).select('+findingContext');
  assertCanAccess(req.user, report, { ...OWNER_ONLY });

  // REBUILT, NEVER FORWARDED. Two fields, both strings, nothing else -- so a
  // caller cannot reach the model with a value attached.
  const findings = (Array.isArray(req.body?.findings) ? req.body.findings : [])
    .map((item) => ({
      test_name: String(item?.test_name ?? item?.testName ?? '').trim(),
      direction: String(item?.direction ?? '').trim(),
    }))
    .filter((item) => item.test_name && item.direction);

  const version = report.analysis?.version || report.analysisVersion || null;
  const key = fingerprint(findings.map((f) => `${f.test_name}|${f.direction}`), []);

  const cached = report.findingContext;
  if (cached && cached.findingsHash === key && cached.analysisVersion === version) {
    return sendSuccess(res, 200, { context: cached });
  }

  if (!findings.length) return sendSuccess(res, 200, { context: null });

  const data = await coalesce(`context:${report._id}:${version}:${key}`, () =>
    describeAndStore(report, findings, version, key)
  );
  return sendSuccess(res, 200, data);
});

/** The ai-service call and the store behind `getFindingContext`, run once per
 *  identical request in flight. Returns the response `data`. */
async function describeAndStore(report, findings, version, key) {
  let written = null;
  try {
    written = await aiService.describeFindings({
      findings,
      requestId: aiService.newRequestId(report._id.toString()),
    });
  } catch (err) {
    if (!config.isTest) {
      // eslint-disable-next-line no-console
      console.warn(`[finding-context] reportId=${report._id} outcome=unavailable ${err.message}`);
    }
    return { context: null };
  }

  if (!written || typeof written !== 'object') {
    return { context: null };
  }

  const stored = { ...written, analysisVersion: version, findingsHash: key };

  // A TOTAL REFUSAL IS NOT CACHED, and the reason is a real outage rather
  // than a hypothetical one: when the Gemini quota is spent, every model in
  // the chain refuses and nothing comes back available. Storing that would
  // pin an empty result to this report and this set of findings FOREVER --
  // the quota resets tomorrow and nothing would ever ask again, because the
  // cache key has not changed. Same exception `summaryProse` makes for
  // `model_unavailable`: a transport or quota state is not an answer about
  // this report. A PARTIAL result is cached, because those refusals came from
  // the gates and asking again would produce the same ones.
  //
  // THE TEST IS "DID ANYTHING COME BACK AVAILABLE", NOT `generated_count`,
  // AND THE DIFFERENCE IS A CACHE HIT. The ai-service keys its own process
  // cache on the test name and direction -- the whole prompt -- so a report
  // whose findings were all described for an earlier report arrives fully
  // populated with `generated_count: 0` and `cached_count` equal to the lot.
  // Reading that as "the model answered nothing" would decline to store a
  // complete result, and this report would re-request on every page view
  // exactly when the answer was already free.
  //
  // ⚠ AND "A PARTIAL RESULT'S REFUSALS CAME FROM THE GATES" WAS NOT TRUE UNTIL
  // THE ai-SERVICE COULD SAY OTHERWISE. A Gemini outage on some findings was
  // reported as `refused_by: "safety"`, cached here beside the ones that did
  // come back, and pinned to the report until it was re-analysed -- measured
  // 2026-09-24 on `Test 3.pdf`: NEUTROPHILS, ESR and CRP, `ServerError` on
  // both attempts. The ai-service now names that `model_unavailable`, and a
  // result carrying one is not stored, for the total-outage reason above.
  // Asking again costs only the missing ones: the ai-service answers the rest
  // from its own process cache.
  const entries = Array.isArray(written.entries) ? written.entries : [];
  if (!entries.some((entry) => entry && entry.available === true)) {
    return { context: stored };
  }
  // `in_progress` (2026-09-24): the ai-service now answers within a deadline
  // and leaves slow descriptions running. Storing that answer would pin the
  // unfinished ones exactly as an outage was pinned; the next view gets them
  // from the ai-service's cache instead.
  if (entries.some((entry) => entry && NOT_AN_ANSWER.has(entry.refused_by))) {
    return { context: stored };
  }

  try {
    await Report.updateOne({ _id: report._id }, { $set: { findingContext: stored } });
  } catch (err) {
    if (!config.isTest) {
      // eslint-disable-next-line no-console
      console.warn(`[finding-context] reportId=${report._id} outcome=not_cached ${err.message}`);
    }
  }
  return { context: stored };
}

module.exports = { getSummaryProse, getFindingContext };
