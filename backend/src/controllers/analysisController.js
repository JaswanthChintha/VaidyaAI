'use strict';

const Report = require('../models/Report');
const { REPORT_STATUS } = require('../models/Report');
const ApiError = require('../utils/ApiError');
const asyncHandler = require('../utils/asyncHandler');
const { sendSuccess } = require('../utils/apiResponse');
const { ownerScopedFilter, assertCanAccess, OWNER_ONLY } = require('../utils/ownership');
const aiService = require('../services/aiServiceClient');
const analysisService = require('../services/analysisService');


const ownFilter = (req, base = {}) => ownerScopedFilter(req.user, { ...OWNER_ONLY, base });

const ANALYSIS_PROJECTION =
  '+extraction +features +featureValidation +ruleDecisions +mlDecisions +clinicalReport ' +
  '+patientExplanation +lifestyleGuidance +analysisWarnings';


const analyzeReport = asyncHandler(async (req, res) => {
  if (!aiService.isConfigured()) throw aiService.notConfigured();

  const report = await Report.findOne(ownFilter(req, { _id: req.params.id }));
  assertCanAccess(req.user, report, { ...OWNER_ONLY });

  const requestId = aiService.newRequestId(report._id.toString());

  const claimed = await analysisService.claimForAnalysis({
    user: req.user,
    reportId: report._id,
    requestId,
  });

  if (!claimed) {
    throw new ApiError(
      409,
      'ANALYSIS_IN_PROGRESS',
      'An analysis of this report is already running. Try again when it finishes.'
    );
  }

  await analysisService.runAnalysis({ user: req.user, report: claimed, requestId });

  const fresh = await Report.findOne(ownFilter(req, { _id: report._id })).select(
    ANALYSIS_PROJECTION
  );
  if (!fresh) throw ApiError.notFound('Report not found');

  return sendSuccess(res, 200, {
    report: fresh.toPublicJSON(),
    analysis: fresh.toAnalysisJSON(),
  });
});


const getAnalysis = asyncHandler(async (req, res) => {
  const report = await Report.findOne(ownFilter(req, { _id: req.params.id })).select(
    ANALYSIS_PROJECTION
  );
  assertCanAccess(req.user, report, { ...OWNER_ONLY });

  const version = (report.analysis && report.analysis.version) || 0;
  if (version === 0 || !report.extraction) {
    throw ApiError.notFound(
      report.status === REPORT_STATUS.FAILED
        ? 'This report has not been analysed successfully. See the report status for detail.'
        : 'This report has not been analysed yet. Run POST /reports/:id/analyze first.'
    );
  }

  return sendSuccess(res, 200, {
    report: report.toPublicJSON(),
    analysis: report.toAnalysisJSON(),
  });
});

const getClinicalReport = asyncHandler(async (req, res) => {
  const report = await Report.findOne(ownFilter(req, { _id: req.params.id })).select(
    ANALYSIS_PROJECTION
  );
  assertCanAccess(req.user, report, { ...OWNER_ONLY });

  const version = (report.analysis && report.analysis.version) || 0;
  if (version === 0 || !report.clinicalReport) {
    throw ApiError.notFound(
      version === 0
        ? 'This report has not been analysed yet. Run POST /reports/:id/analyze first.'
        : 'No clinical report was produced for this analysis. See GET /reports/:id/analysis for which stage did not complete.'
    );
  }

  const analysis = report.toAnalysisJSON();

  return sendSuccess(res, 200, {
    report: report.toPublicJSON(),
    overall: {
      status: analysis.overallStatus,
      statusLabel: analysis.overallStatusLabel,
      risk: analysis.overallRisk,
      complete: analysis.assessmentComplete,
      anyAssessed: analysis.anyAssessed,
    },
    clinicalReport: report.clinicalReport,
  });
});

const getExplanation = asyncHandler(async (req, res) => {
  const report = await Report.findOne(ownFilter(req, { _id: req.params.id })).select(
    ANALYSIS_PROJECTION
  );
  assertCanAccess(req.user, report, { ...OWNER_ONLY });

  const version = (report.analysis && report.analysis.version) || 0;
  if (version === 0 || !report.patientExplanation) {
    throw ApiError.notFound(
      version === 0
        ? 'This report has not been analysed yet. Run POST /reports/:id/analyze first.'
        : 'No patient explanation was produced for this analysis. See GET /reports/:id/analysis for which stage did not complete.'
    );
  }

  const analysis = report.toAnalysisJSON();

  return sendSuccess(res, 200, {
    report: report.toPublicJSON(),
    summary: {
      available: analysis.explanationAvailable,
      count: analysis.explanationCount,
      generatedCount: analysis.explanationGeneratedCount,
      withheldCount: analysis.explanationWithheldCount,
      outcomes: analysis.explanationOutcomes,
      guidanceItemCount: analysis.guidanceItemCount,
    },
    explanation: analysis.explanation,
    guidance: analysis.guidance,
  });
});

module.exports = { analyzeReport, getAnalysis, getClinicalReport, getExplanation };
