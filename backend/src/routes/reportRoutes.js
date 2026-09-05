'use strict';

const express = require('express');

const reportController = require('../controllers/reportController');
const analysisController = require('../controllers/analysisController');
const dashboardController = require('../controllers/dashboardController');
const doctorSummaryController = require('../controllers/doctorSummaryController');
const populationController = require('../controllers/populationController');
const validate = require('../middleware/validate');
const { protect } = require('../middleware/auth');
const { uploadLimiter, analysisLimiter, historyLimiter } = require('../middleware/rateLimiter');
const { singleReportUpload } = require('../middleware/upload');
const {
  uploadReportValidator,
  reportIdValidator,
  listReportsValidator,
} = require('../middleware/reportValidators');
const { comparisonPairValidator } = require('../middleware/timelineValidators');

const router = express.Router();

/**
 * Module 3 - /api/v1/reports
 *
 * Every route is authenticated and owner-scoped. Ids appear in these URLs, so
 * unlike Module 2 there IS something to tamper with - which is why the
 * controller loads every report through an owner-scoped filter and then
 * re-checks ownership. See reportController for the full model.
 */
router.use(protect);

router
  .route('/')
  // MIDDLEWARE ORDER IS DELIBERATE:
  //   protect (above)   - an anonymous caller is rejected before a single byte
  //                       of their file is buffered.
  //   uploadLimiter     - throttles the expensive path separately from auth.
  //   singleReportUpload- multer; enforces the byte cap and one-file rule, and
  //                       any failure becomes a 4xx via the error handler.
  //   validate          - runs AFTER multer because multipart text fields do
  //                       not exist on req.body until multer has parsed them.
  .post(
    uploadLimiter,
    singleReportUpload,
    validate(uploadReportValidator),
    reportController.uploadReport
  )
  .get(validate(listReportsValidator), reportController.listReports);

router
  .route('/:id')
  .get(validate(reportIdValidator), reportController.loadOwnReport, reportController.getReport)
  .delete(
    validate(reportIdValidator),
    reportController.loadOwnReport,
    reportController.deleteReport
  );

router.get(
  '/:id/download',
  validate(reportIdValidator),
  reportController.loadOwnReport,
  reportController.downloadReport
);

/**
 * Modules 4 + 5 orchestration. Same authentication and same owner scoping as
 * every route above - the controller builds each query with
 * `ownerScopedFilter(req.user, { ...OWNER_ONLY })` and re-checks with
 * `assertCanAccess`, so a non-owner (including an admin or a clinician) gets a
 * 404 indistinguishable from a random id.
 *
 * `analysisLimiter` is separate from `uploadLimiter` on purpose: an analysis
 * costs a multi-second LLM call in the Python service, so it needs its own,
 * much smaller budget than an upload.
 */
router.post(
  '/:id/analyze',
  analysisLimiter,
  validate(reportIdValidator),
  analysisController.analyzeReport
);

router.get('/:id/analysis', validate(reportIdValidator), analysisController.getAnalysis);

/**
 * Modules 17-20 - the clinical report on its own. Same authentication, same
 * validator, same owner scoping as `/analysis`; it is a narrower VIEW of the
 * same stored document, not a second access path with its own rules.
 */
router.get('/:id/report', validate(reportIdValidator), analysisController.getClinicalReport);

/**
 * Modules 23 + 26 - the patient-facing explanation and the pre-approved
 * educational guidance. Same authentication, same validator, same owner scoping
 * as `/report`; another VIEW of the same stored document, not a second access
 * path with its own rules.
 *
 * NOT rate-limited separately, and deliberately so: it reads what the analyze
 * run already generated and stored. No model is called here - the LLM round
 * trip happens once, inside `POST /:id/analyze`, which IS separately limited.
 */
router.get('/:id/explanation', validate(reportIdValidator), analysisController.getExplanation);

/**
 * Module 27 - the health dashboard's read model. Same authentication, same
 * validator, same owner scoping as `/report` and `/explanation`; a fourth VIEW
 * of the same stored document, not a second access path with its own rules.
 *
 * NOT rate-limited separately, for the same reason `/explanation` is not: it
 * reads what the analyze run already stored and calls no model and no service.
 */
router.get('/:id/dashboard', validate(reportIdValidator), dashboardController.getDashboard);

/**
 * Module 32 - the doctor-friendly clinical summary of THIS report.
 *
 * A fifth view of the same stored document, with the same authentication and
 * the same owner scoping. It differs from the four above in one way that
 * drives everything about this route: it also reads the patient's report
 * HISTORY, to fill its trend and historical-comparison sections. The clinical
 * content still comes from this report's stored `clinicalReport` alone.
 *
 * `historyLimiter`, unlike `/report`, `/explanation` and `/dashboard`, and for
 * the reason those three are unlimited: they read one document and call
 * nothing, while this one reads up to HISTORY_MAX_REPORTS documents and makes
 * an outbound ai-service call. It is the same limiter the `/timeline` routes
 * use, so a caller cannot dodge that budget by asking for the same fan-out
 * through a different URL.
 *
 * The validator chain is the report-id one PLUS the optional, both-or-neither
 * `?baseline=`/`?comparison=` pair, which is passed to Module 29 through
 * Module 32. Both named ids are re-checked for ownership in the controller -
 * naming a report is not permission to read it.
 */
router.get(
  '/:id/doctor-summary',
  historyLimiter,
  validate([...reportIdValidator, ...comparisonPairValidator]),
  doctorSummaryController.getDoctorSummary
);

/**
 * Module 31 - population context for this report's accepted readings.
 *
 * Same authentication, same owner scoping and the same 404-before-403 as every
 * other report route. The cohort is chosen from the AUTHENTICATED user's own
 * Module 2 profile - age and gender are never read from a query parameter,
 * because a caller who could name the cohort could score a value against an
 * arbitrary population and read the percentile as though it were theirs.
 *
 * `historyLimiter` rather than none: this makes an outbound ai-service call,
 * which is the line `/dashboard` (one document, no call) sits on the other
 * side of. It is not `analysisLimiter`, whose 20-per-window budget is sized for
 * LLM quota - Module 31 calls no model at all, and reading a percentile must
 * not consume an allowance the patient needs to analyse an upload.
 *
 * A REFUSAL IS A 200. A profile with no age, or a gender the published survey
 * has no stratum for, returns entries with `available: false`, a reason code
 * and reviewed copy - not an error. That is the answer Module 31 was built to
 * give, and the controller passes it through verbatim rather than restating it
 * in this backend's own words.
 */
router.get(
  '/:id/population-context',
  historyLimiter,
  validate(reportIdValidator),
  populationController.getPopulationContext
);

module.exports = router;
