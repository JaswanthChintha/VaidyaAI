'use strict';

const { query } = require('express-validator');

/**
 * Modules 28-30 validators.
 *
 * THE STANDING RULE, VERBATIM: every chain starts with a type guard and
 * `.bail()` before any sanitizer or comparison, so no untyped value can reach a
 * Mongo query. That is not style - a missing `.isString()` on one of five
 * chains was a live authentication bypass on this project.
 *
 * It matters specifically here because these two parameters are REPORT IDS
 * FROM THE QUERY STRING, and a query string can carry an array
 * (`?baseline=a&baseline=b`) or an object (`?baseline[$ne]=`). Either would
 * arrive as a non-string and, without the guard, would be handed straight to
 * `Report.findOne({ _id: ... })`. `express-mongo-sanitize` and `hpp()` run
 * ahead of this and would catch those particular shapes today; the guard is
 * here anyway, because a control that holds only because of a middleware
 * ordering somewhere else is the shape of defect this codebase keeps finding.
 *
 * Error messages are static and never echo the submitted value.
 */

/** The one id shape this application accepts anywhere: a 24-char ObjectId. */
const OBJECT_ID = /^[a-fA-F0-9]{24}$/;

const reportIdQueryParam = (name, label) =>
  query(name)
    .optional()
    .isString()
    .withMessage(`${label} must be a single report id`)
    .bail()
    .trim()
    .matches(OBJECT_ID)
    .withMessage(`${label} must be a valid report id`);

/**
 * `GET /timeline/comparison` and `GET /timeline/progress`.
 *
 * `baseline` and `comparison` are optional, but they are BOTH-OR-NEITHER. The
 * ai-service rejects exactly one of them with a 422 and this rejects it here,
 * for the same reason: "compare against report X" with no second report named
 * has no defined meaning, and choosing a partner on the caller's behalf would
 * silently answer a different question from the one asked.
 *
 * Naming an id here is NOT an authorisation to read it. The controller
 * re-loads each named id through the same owner-scoped filter every other
 * report route uses before it goes anywhere near the analysis request - see
 * timelineController. Passing validation means the value is a well-formed id
 * and nothing more.
 */
const comparisonPairValidator = [
  reportIdQueryParam('baseline', 'Baseline'),
  reportIdQueryParam('comparison', 'Comparison'),
  query('baseline').custom((value, { req }) => {
    const hasBaseline = req.query.baseline !== undefined;
    const hasComparison = req.query.comparison !== undefined;
    if (hasBaseline !== hasComparison) {
      throw new Error(
        'Name both baseline and comparison, or neither. One alone does not identify a pair.'
      );
    }
    return true;
  }),
];

module.exports = { comparisonPairValidator, OBJECT_ID };
