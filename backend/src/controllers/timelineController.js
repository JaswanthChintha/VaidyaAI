'use strict';

const asyncHandler = require('../utils/asyncHandler');
const { sendSuccess } = require('../utils/apiResponse');
const aiService = require('../services/aiServiceClient');
const historyService = require('../services/historyService');
const labSeriesService = require('../services/labSeriesService');


const patientRefOf = (req) => String(req.user.id ?? req.user._id);

const historyRequestId = () => aiService.newRequestId();

const resolvePair = (req, snapshotIds) =>
  historyService.resolveNamedPair({
    user: req.user,
    baseline: req.query.baseline,
    comparison: req.query.comparison,
    snapshotIds,
  });

async function loadHistory(req) {
  const history = await historyService.assembleHistory({ user: req.user });
  const excluded = await historyService.describeExcluded({ user: req.user });
  return { history, excluded };
}


async function labAliases(history, printed) {
  const firstPass = labSeriesService.buildLabSeries(history.snapshots, printed);
  const askAbout = labSeriesService.unjoinedNames(firstPass);
  if (askAbout.length < 2) return new Map();

  try {
    const matched = await aiService.matchLabNames({
      names: askAbout,
      requestId: historyRequestId(),
    });
    return labSeriesService.aliasMap(matched && matched.groups);
  } catch (error) {
    console.warn(
      `[lab-name-match] outcome=unavailable asked=${askAbout.length} ` +
        `code=${(error && error.code) || 'UNKNOWN'}`
    );
    return new Map();
  }
}

async function labWithVerdicts(snapshots, printed, aliases) {
  const built = labSeriesService.buildLabSeries(
    snapshots,
    printed,
    aliases && aliases.size ? aliases : undefined
  );

  const classifiable = labSeriesService.classifiableSeries(built);
  if (!classifiable.length) return built;

  try {
    const verdicts = await aiService.classifyLabSeries({
      series: classifiable,
      requestId: historyRequestId(),
    });
    return labSeriesService.attachVerdicts(built, verdicts && verdicts.verdicts);
  } catch (error) {
    console.warn(
      `[lab-polarity] outcome=unavailable requested=${classifiable.length} ` +
        `code=${(error && error.code) || 'UNKNOWN'}`
    );
    return built;
  }
}

const getTrends = asyncHandler(async (req, res) => {
  if (!aiService.isConfigured()) throw aiService.notConfigured();

  const { history, excluded } = await loadHistory(req);

  const printed = await historyService.loadPrintedParameters({
    user: req.user,
    reportIds: history.snapshots.map((s) => s.report_id),
  });

  const aliases = await labAliases(history, printed);
  const labSeries = await labWithVerdicts(history.snapshots, printed, aliases);

  const trends = await aiService.analyseTrends({
    reports: history.snapshots,
    patientRef: patientRefOf(req),
    requestId: historyRequestId(),
  });

  return sendSuccess(res, 200, {
    history: historyService.summariseHistory(history, excluded),
    labSeries,
    trends,
  });
});


const getComparison = asyncHandler(async (req, res) => {
  if (!aiService.isConfigured()) throw aiService.notConfigured();

  const { history, excluded } = await loadHistory(req);
  const snapshotIds = new Set(history.snapshots.map((s) => s.report_id));
  const pair = await resolvePair(req, snapshotIds);

  const comparison = await aiService.compareReports({
    reports: history.snapshots,
    patientRef: patientRefOf(req),
    baselineRef: pair ? pair.baselineRef : undefined,
    comparisonRef: pair ? pair.comparisonRef : undefined,
    requestId: historyRequestId(),
  });

  const used = comparison && comparison.pair;
  const baselineId = used ? used.baseline_report_id : null;
  const comparisonId = used ? used.comparison_report_id : null;

  let labComparison = { rows: [], count: 0 };
  let identity = null;
  if (baselineId && comparisonId) {
    identity = await historyService.checkPairIdentity({
      user: req.user,
      baselineId,
      comparisonId,
    });
    const printed = await historyService.loadPrintedParameters({
      user: req.user,
      reportIds: [baselineId, comparisonId],
    });
    const aliases = await labAliases(history, printed);
    const pairSnapshots = history.snapshots.filter(
      (s) => s.report_id === baselineId || s.report_id === comparisonId
    );
    const built = await labWithVerdicts(pairSnapshots, printed, aliases);
    labComparison = labSeriesService.buildLabComparison(built, baselineId, comparisonId);
  }

  return sendSuccess(res, 200, {
    history: historyService.summariseHistory(history, excluded),
    labComparison,
    requestedPair: pair
      ? { baseline: pair.baselineRef, comparison: pair.comparisonRef }
      : null,
    comparison,
    identity,
  });
});


const getProgress = asyncHandler(async (req, res) => {
  if (!aiService.isConfigured()) throw aiService.notConfigured();

  const { history, excluded } = await loadHistory(req);
  const snapshotIds = new Set(history.snapshots.map((s) => s.report_id));
  const pair = await resolvePair(req, snapshotIds);

  const progress = await aiService.scoreProgress({
    reports: history.snapshots,
    patientRef: patientRefOf(req),
    baselineRef: pair ? pair.baselineRef : undefined,
    comparisonRef: pair ? pair.comparisonRef : undefined,
    requestId: historyRequestId(),
  });

  return sendSuccess(res, 200, {
    history: historyService.summariseHistory(history, excluded),
    requestedPair: pair
      ? { baseline: pair.baselineRef, comparison: pair.comparisonRef }
      : null,
    progress,
  });
});

module.exports = { getTrends, getComparison, getProgress };
