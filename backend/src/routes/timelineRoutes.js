'use strict';

const express = require('express');

const timelineController = require('../controllers/timelineController');
const validate = require('../middleware/validate');
const { protect } = require('../middleware/auth');
const { historyLimiter } = require('../middleware/rateLimiter');
const { comparisonPairValidator } = require('../middleware/timelineValidators');

const router = express.Router();

/**
 * Modules 28, 29 and 30 - /api/v1/timeline
 *
 * WHY THESE ARE NOT UNDER `/reports/:id/...` LIKE EVERY OTHER ANALYSIS VIEW.
 * `/reports/:id/report`, `/explanation` and `/dashboard` are all views OF ONE
 * REPORT and are addressed by that report's id. A trend is not: it is a
 * property of the PATIENT, computed across every report they have. Hanging it
 * off one report's id would have to pick an arbitrary report to be the URL,
 * and would make it look as though the answer were about that report.
 *
 * There is no patient id in these URLs, for the same reason Module 2's
 * `/profile/me` has none: the owner always comes from the verified JWT, so
 * there is nothing in the path to tamper with. The only ids a caller may name
 * are the optional `?baseline=`/`?comparison=` pair, and those are re-checked
 * for ownership before use - see historyService.resolveNamedPair.
 *
 * All three are GETs: they read stored analysis and compute a view of it.
 * Nothing here writes, nothing here calls a model, and re-running one changes
 * nothing.
 */
router.use(protect);

/**
 * `historyLimiter`, not `analysisLimiter` and not nothing.
 *
 * One call reads up to HISTORY_MAX_REPORTS reports with their Module 6
 * verdicts and makes an outbound ai-service request, so unlike `/dashboard`
 * and `/explanation` - which read one stored document and call nothing - these
 * are worth a budget. It is a separate, larger budget from the analysis one
 * because these routes reach no model on either side, and drawing a trend
 * screen must not be able to lock a patient out of analysing a report.
 * See middleware/rateLimiter.js for the full reasoning.
 */
router.use(historyLimiter);

/** Module 28 - per-feature trajectory across the patient's history. */
router.get('/trends', timelineController.getTrends);

/**
 * Module 29 - two reports side by side.
 *
 * `?baseline=<id>&comparison=<id>` are optional and BOTH-OR-NEITHER. With
 * neither, the earliest and latest reports are compared. The validator only
 * proves the ids are well-formed strings; the controller re-checks that the
 * caller owns each one.
 */
router.get(
  '/comparison',
  validate(comparisonPairValidator),
  timelineController.getComparison
);

/** Module 30 - the same pair as `/comparison`, scored. Same parameters. */
router.get('/progress', validate(comparisonPairValidator), timelineController.getProgress);

module.exports = router;
