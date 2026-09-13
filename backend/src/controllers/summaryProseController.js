'use strict';

const crypto = require('crypto');

const Report = require('../models/Report');
const asyncHandler = require('../utils/asyncHandler');
const { sendSuccess } = require('../utils/apiResponse');
const { ownerScopedFilter, assertCanAccess, OWNER_ONLY } = require('../utils/ownership');
const aiService = require('../services/aiServiceClient');
const config = require('../config/env');

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
    return sendSuccess(res, 200, { prose: null });
  }

  if (!written || typeof written !== 'object') {
    return sendSuccess(res, 200, { prose: null });
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
  return sendSuccess(res, 200, { prose: stored });
});

module.exports = { getSummaryProse };
