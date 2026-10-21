'use strict';

const { query } = require('express-validator');


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
