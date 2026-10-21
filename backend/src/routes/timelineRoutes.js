'use strict';

const express = require('express');

const timelineController = require('../controllers/timelineController');
const validate = require('../middleware/validate');
const { protect } = require('../middleware/auth');
const { historyLimiter } = require('../middleware/rateLimiter');
const { comparisonPairValidator } = require('../middleware/timelineValidators');

const router = express.Router();

router.use(protect);

router.use(historyLimiter);

router.get('/trends', timelineController.getTrends);

router.get(
  '/comparison',
  validate(comparisonPairValidator),
  timelineController.getComparison
);

router.get('/progress', validate(comparisonPairValidator), timelineController.getProgress);

module.exports = router;
