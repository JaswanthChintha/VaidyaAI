'use strict';

const express = require('express');

const reportController = require('../controllers/reportController');
const analysisController = require('../controllers/analysisController');
const dashboardController = require('../controllers/dashboardController');
const doctorSummaryController = require('../controllers/doctorSummaryController');
const populationController = require('../controllers/populationController');
const summaryProseController = require('../controllers/summaryProseController');
const validate = require('../middleware/validate');
const { protect } = require('../middleware/auth');
const { uploadLimiter, analysisLimiter, historyLimiter } = require('../middleware/rateLimiter');
const { singleReportUpload } = require('../middleware/upload');
const {
  uploadReportValidator,
  reportSubjectValidator,
  reportIdValidator,
  listReportsValidator,
} = require('../middleware/reportValidators');
const { comparisonPairValidator } = require('../middleware/timelineValidators');

const router = express.Router();

router.use(protect);

router
  .route('/')
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

router.patch(
  '/:id/subject',
  validate([...reportIdValidator, ...reportSubjectValidator]),
  reportController.loadOwnReport,
  reportController.setReportSubject
);

router.post(
  '/:id/analyze',
  analysisLimiter,
  validate(reportIdValidator),
  analysisController.analyzeReport
);

router.get('/:id/analysis', validate(reportIdValidator), analysisController.getAnalysis);

router.get('/:id/report', validate(reportIdValidator), analysisController.getClinicalReport);

router.get('/:id/explanation', validate(reportIdValidator), analysisController.getExplanation);

router.get('/:id/dashboard', validate(reportIdValidator), dashboardController.getDashboard);

router.post(
  '/:id/summary-prose',
  historyLimiter,
  validate(reportIdValidator),
  summaryProseController.getSummaryProse
);

router.post(
  '/:id/finding-context',
  historyLimiter,
  validate(reportIdValidator),
  summaryProseController.getFindingContext
);

router.get(
  '/:id/doctor-summary',
  historyLimiter,
  validate([...reportIdValidator, ...comparisonPairValidator]),
  doctorSummaryController.getDoctorSummary
);

router.get(
  '/:id/population-context',
  historyLimiter,
  validate(reportIdValidator),
  populationController.getPopulationContext
);

module.exports = router;
