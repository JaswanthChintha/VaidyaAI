'use strict';

const Report = require('../models/Report');
const ApiError = require('../utils/ApiError');
const asyncHandler = require('../utils/asyncHandler');
const { sendSuccess } = require('../utils/apiResponse');
const { ownerScopedFilter, assertCanAccess, OWNER_ONLY } = require('../utils/ownership');
const aiService = require('../services/aiServiceClient');
const dashboardService = require('../services/dashboardService');
const historyService = require('../services/historyService');
const config = require('../config/env');


const ownFilter = (req, base = {}) => ownerScopedFilter(req.user, { ...OWNER_ONLY, base });

const DOCTOR_SUMMARY_PROJECTION =
  '+clinicalReport +doctorNarrative +features +extraction';

const getDoctorSummary = asyncHandler(async (req, res) => {
  if (!aiService.isConfigured()) throw aiService.notConfigured();

  const report = await Report.findOne(ownFilter(req, { _id: req.params.id })).select(
    DOCTOR_SUMMARY_PROJECTION
  );
  assertCanAccess(req.user, report, { ...OWNER_ONLY });

  const version = (report.analysis && report.analysis.version) || 0;
  if (version === 0 || !report.clinicalReport) {
    throw ApiError.notFound(
      version === 0
        ? 'This report has not been analysed yet. Run POST /reports/:id/analyze first.'
        : 'No clinical report was produced for this analysis, so there is nothing to summarise. See GET /reports/:id/analysis for which stage did not complete.'
    );
  }

  const history = await historyService.assembleHistory({ user: req.user });
  const excluded = await historyService.describeExcluded({ user: req.user });
  const otherPerson = report.subject?.owner === 'other';
  const snapshots = otherPerson ? [] : history.snapshots;

  const snapshotIds = new Set(snapshots.map((s) => s.report_id));
  const pair = otherPerson
    ? null
    : await historyService.resolveNamedPair({
        user: req.user,
        baseline: req.query.baseline,
        comparison: req.query.comparison,
        snapshotIds,
      });

  const summary = await aiService.generateDoctorSummary({
    report: report.clinicalReport,
    reportRef: report._id.toString(),
    reportDate: report.chronoDate ? new Date(report.chronoDate).toISOString() : undefined,
    history: snapshots,
    patientRef: String(req.user.id ?? req.user._id),
    options: pair
      ? { baseline_ref: pair.baselineRef, comparison_ref: pair.comparisonRef }
      : undefined,
    requestId: aiService.newRequestId(report._id.toString()),
  });

  const narrative = await resolveNarrative(report, version, summary);

  return sendSuccess(res, 200, {
    report: report.toPublicJSON(),
    history: {
      ...historyService.summariseHistory(history, excluded),
      subjectInHistory: snapshotIds.has(report._id.toString()),
    },
    requestedPair: pair
      ? { baseline: pair.baselineRef, comparison: pair.comparisonRef }
      : null,
    doctorSummary: summary,
    unassessed: dashboardService.buildUnanalysedSection(
      report.features === undefined ? null : report.features,
      report.extraction === undefined ? null : report.extraction,
      null
    ),
    narrative,
  });
});

async function resolveNarrative(report, version, summary) {
  const cached = report.doctorNarrative;
  const fingerprint = await aiService.clinicianSummaryFingerprint();
  const sameCode = fingerprint === null || cached?.codeFingerprint === fingerprint;
  if (
    cached
    && cached.analysisVersion === version
    && sameCode
    && cached.outcome
    && cached.outcome !== 'model_unavailable'
  ) {
    return cached;
  }

  let written = null;
  try {
    written = await aiService.writeClinicianSummary({
      summary,
      requestId: aiService.newRequestId(report._id.toString()),
    });
  } catch (err) {
    if (!config.isTest) {
      console.warn(
        `[narrative] reportId=${report._id} outcome=unavailable ${err.message}`
      );
    }
    return null;
  }
  if (!written || typeof written !== 'object') return null;

  const stored = { ...written, analysisVersion: version, codeFingerprint: fingerprint };
  try {
    await Report.updateOne(
      { _id: report._id },
      { $set: { doctorNarrative: stored } }
    );
  } catch (err) {
    if (!config.isTest) {
      console.warn(`[narrative] reportId=${report._id} outcome=not_cached ${err.message}`);
    }
  }
  return stored;
}

module.exports = { getDoctorSummary };
