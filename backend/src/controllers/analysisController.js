'use strict';

const Report = require('../models/Report');
const { REPORT_STATUS } = require('../models/Report');
const ApiError = require('../utils/ApiError');
const asyncHandler = require('../utils/asyncHandler');
const { sendSuccess } = require('../utils/apiResponse');
const { ownerScopedFilter, assertCanAccess, OWNER_ONLY } = require('../utils/ownership');
const aiService = require('../services/aiServiceClient');
const analysisService = require('../services/analysisService');

/**
 * The analysis endpoints - the backend half of section 16's data flow.
 *
 *   POST /reports/:id/analyze   run the whole chain: extraction (4) -> feature
 *                               engineering (5) -> validation (6) -> clinical
 *                               rules (8) || ML predictors (9/10) || the
 *                               clinical report (17-20, with 15/16 fused
 *                               inside it)
 *   GET  /reports/:id/analysis  fetch what the last successful run stored,
 *                               decisions AND the clinical report included
 *   GET  /reports/:id/report    the clinical report on its own - the
 *                               user-visible deliverable, without the
 *                               machine-facing payloads around it
 *   GET  /reports/:id/explanation
 *                               Modules 23 + 26 - the same findings in
 *                               plain language, safety-approved, plus the
 *                               pre-approved educational guidance
 *
 * OWNERSHIP is identical to every other report route and is not weakened here:
 * every query is built by `ownerScopedFilter(req.user, { ...OWNER_ONLY })`, so
 * another user's report id cannot match a document at all and a non-owner sees
 * exactly the 404 a random id produces. The loaded document is then re-checked
 * with `assertCanAccess`, which answers 404 before 403. Medical data has no
 * staff exception - an admin and a clinician get the same 404 as user B.
 *
 * LOGGING: nothing here logs report text, extracted values or filenames. The
 * correlation id and opaque ids only.
 */

/** Filter matching only the caller's own reports. Throws if unauthenticated. */
const ownFilter = (req, base = {}) => ownerScopedFilter(req.user, { ...OWNER_ONLY, base });

/**
 * Fields carrying the analysis payload. All `select: false` on the schema, so
 * they are loaded ONLY by the two analysis endpoints and never by a listing.
 * Modules 4, 5, 6, 8 and 9/10 respectively, plus the merged warning list.
 */
const ANALYSIS_PROJECTION =
  '+extraction +features +featureValidation +ruleDecisions +mlDecisions +clinicalReport ' +
  '+patientExplanation +lifestyleGuidance +analysisWarnings';

// --------------------------------------------------------------- analyze ----

/**
 * POST /reports/:id/analyze
 *
 * Lifecycle: `uploaded -> processing -> processed | partial | failed`, driven
 * here and nowhere else. The move into `processing` doubles as the concurrency
 * lock (see `analysisService.claimForAnalysis`).
 *
 * `partial` is a 200: extraction and feature engineering succeeded and their
 * results are stored, but at least one of validation / rules / ML did not
 * answer. The response body says so twice over - `report.status` is `partial`
 * and `analysis.stages` names the failed stage and its machine code - so
 * nothing about the response claims a stage succeeded when it did not. A
 * partial result is genuinely more useful than none: the validated features and
 * whichever decision source did answer are exactly what Module 17 needs.
 *
 * Idempotency / re-run: safe to call repeatedly. A success overwrites the
 * stored analysis and bumps `analysis.version`; a failure writes only status
 * bookkeeping, so a previous success survives. See analysisService for the full
 * rationale.
 */
const analyzeReport = asyncHandler(async (req, res) => {
  if (!aiService.isConfigured()) throw aiService.notConfigured();

  // Owner-scoped load FIRST, so a non-owner's 404 is produced before anything
  // else can distinguish their request from a request for a report that does
  // not exist (e.g. by taking the lock, or by answering 409).
  const report = await Report.findOne(ownFilter(req, { _id: req.params.id }));
  assertCanAccess(req.user, report, { ...OWNER_ONLY });

  // The correlation id is the report id: opaque, stable across retries of the
  // same report, and trivially greppable in both services' logs. It is NEVER
  // derived from anything in the report's contents.
  const requestId = aiService.newRequestId(report._id.toString());

  const claimed = await analysisService.claimForAnalysis({
    user: req.user,
    reportId: report._id,
    requestId,
  });

  if (!claimed) {
    // The conditional update matched nothing. The report demonstrably exists
    // and belongs to the caller (it was just loaded), so the only reason left
    // is that another analysis holds the lock.
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

// -------------------------------------------------------------- retrieve ----

/**
 * GET /reports/:id/analysis
 *
 * 404 when the report has never been analysed successfully - the same decision
 * Module 2 made for a profile that does not exist. "Not analysed" and "analysed
 * and empty" are different states and a synthesised empty body would hide the
 * difference. `status` and `statusMessage` remain available on
 * `GET /reports/:id` for a report whose analysis failed.
 */
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

/**
 * GET /reports/:id/report - Modules 17-20, on their own.
 *
 * A SIBLING OF `/analysis`, NOT A REPLACEMENT. `/analysis` returns everything
 * the pipeline stored, the report included; this returns only the deliverable a
 * person actually reads, so a renderer does not have to pull the extraction,
 * the feature map and both decision payloads to draw one page.
 *
 * OWNER SCOPING IS THE SAME CODE, not a copy of the same idea: the identical
 * `ownFilter` + `assertCanAccess` pair as every route above, so user B, an
 * admin and a clinician all get the 404 a random id produces.
 *
 * 404 when no report has been generated - the same decision `/analysis` makes
 * for an unanalysed report, and for the same reason: a synthesised empty body
 * would be indistinguishable from a report that genuinely found nothing, which
 * is the fourth-case failure this whole pass exists to prevent, one layer up.
 * A run whose report stage failed says so in `analysis.stages.report` on
 * `/analysis`, and the message here points there.
 */
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
    // The Module 18 summary travels WITH the report rather than being left for
    // the caller to recompute: `overallStatus` may be `null` (nothing could be
    // assessed) and `overallStatusLabel` is the four-valued companion a
    // renderer shows instead of inventing a default for the null.
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

/**
 * GET /reports/:id/explanation - Modules 23 and 26, on their own.
 *
 * THE PATIENT-FACING VIEW. `/report` serves the clinical report - accurate, and
 * written for a reader who already knows what HbA1c is. This serves the same
 * findings as the platform explained them, plus the pre-approved educational
 * guidance beside them, so a patient-facing screen does not have to pull the
 * extraction, the feature map and both decision payloads to draw one page.
 *
 * OWNER SCOPING IS THE SAME CODE as every route above - the identical
 * `ownFilter` + `assertCanAccess` pair, so user B, an admin and a clinician all
 * get the 404 a random id produces. Not a copy of the same idea: the same call.
 *
 * WHAT IS AND IS NOT A 404 HERE - THE DISTINCTION THIS ROUTE EXISTS TO KEEP:
 *
 *   404   the explanation stage did not ANSWER - never analysed, or the stage
 *         failed or was skipped. There is nothing stored, and inventing an
 *         empty body would be indistinguishable from a report that genuinely
 *         had nothing to explain.
 *   200   the stage answered. This includes the case where EVERY explanation
 *         was withheld: `explanation.explanation_available` is `false`, the
 *         reviewed notice says an explanation could not be prepared, and each
 *         finding carries its own outcome and notice. A withheld explanation is
 *         a RESULT, not an absence, and must never be served as a 404 - the
 *         patient is owed the statement that something was withheld.
 */
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
    // The summary travels WITH the payload rather than being left for the
    // caller to recompute. `available` is the ONE field a renderer should
    // branch on: `false` means show `explanation.notice` and the per-finding
    // notices, NOT an empty section.
    summary: {
      available: analysis.explanationAvailable,
      count: analysis.explanationCount,
      generatedCount: analysis.explanationGeneratedCount,
      withheldCount: analysis.explanationWithheldCount,
      outcomes: analysis.explanationOutcomes,
      guidanceItemCount: analysis.guidanceItemCount,
    },
    explanation: analysis.explanation,
    // Module 26. `null` when that stage did not answer - it is a separate,
    // model-free stage and it can succeed or fail independently of Module 23.
    guidance: analysis.guidance,
  });
});

module.exports = { analyzeReport, getAnalysis, getClinicalReport, getExplanation };
