'use strict';

const crypto = require('crypto');

const Report = require('../models/Report');
const asyncHandler = require('../utils/asyncHandler');
const { sendSuccess } = require('../utils/apiResponse');
const { ownerScopedFilter, assertCanAccess, OWNER_ONLY } = require('../utils/ownership');
const aiService = require('../services/aiServiceClient');
const config = require('../config/env');

const MODEL_UNAVAILABLE = 'model_unavailable';
const IN_PROGRESS = 'in_progress';
const NOT_AN_ANSWER = new Set([MODEL_UNAVAILABLE, IN_PROGRESS]);


const PROSE_PROJECTION = '+summaryProse';

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

function fingerprint(sentences, names) {
  const payload = JSON.stringify({
    s: (sentences || []).map((x) => String(x).trim()),
    n: (names || []).map((x) => String(x).trim()),
  });
  return crypto.createHash('sha256').update(payload).digest('hex').slice(0, 32);
}

const getSummaryProse = asyncHandler(async (req, res) => {
  const filter = ownerScopedFilter(req.user, { ...OWNER_ONLY, base: { _id: req.params.id } });
  const report = await Report.findOne(filter).select(PROSE_PROJECTION);
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
      if (!config.isTest) {
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
        console.warn(`[summary-prose] reportId=${report._id} outcome=not_cached ${err.message}`);
      }
    }
    return { prose: stored };
  });
  return sendSuccess(res, 200, data);
});

const getFindingContext = asyncHandler(async (req, res) => {
  const filter = ownerScopedFilter(req.user, { ...OWNER_ONLY, base: { _id: req.params.id } });
  const report = await Report.findOne(filter).select('+findingContext');
  assertCanAccess(req.user, report, { ...OWNER_ONLY });

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

async function describeAndStore(report, findings, version, key) {
  let written = null;
  try {
    written = await aiService.describeFindings({
      findings,
      requestId: aiService.newRequestId(report._id.toString()),
    });
  } catch (err) {
    if (!config.isTest) {
      console.warn(`[finding-context] reportId=${report._id} outcome=unavailable ${err.message}`);
    }
    return { context: null };
  }

  if (!written || typeof written !== 'object') {
    return { context: null };
  }

  const stored = { ...written, analysisVersion: version, findingsHash: key };

  const entries = Array.isArray(written.entries) ? written.entries : [];
  if (!entries.some((entry) => entry && entry.available === true)) {
    return { context: stored };
  }
  if (entries.some((entry) => entry && NOT_AN_ANSWER.has(entry.refused_by))) {
    return { context: stored };
  }

  try {
    await Report.updateOne({ _id: report._id }, { $set: { findingContext: stored } });
  } catch (err) {
    if (!config.isTest) {
      console.warn(`[finding-context] reportId=${report._id} outcome=not_cached ${err.message}`);
    }
  }
  return { context: stored };
}

module.exports = { getSummaryProse, getFindingContext };
