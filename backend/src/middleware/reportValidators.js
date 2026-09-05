'use strict';

const { body, param, query } = require('express-validator');
const { SORT_FIELDS, REPORT_STATUS_VALUES } = require('../models/Report');

/**
 * Module 3 validators.
 *
 * The same rule Modules 1 and 2 document applies verbatim: every chain starts
 * with a type guard and `.bail()` before any sanitizer or comparison, so no
 * untyped value can reach a Mongo query. This matters more here than elsewhere
 * because multipart fields are parsed by multer AFTER `express-mongo-sanitize`
 * and `hpp()` have already run - those two middlewares see an empty body on an
 * upload request and protect nothing. The guards below are the only thing
 * standing between a multipart field and the database.
 *
 * Error messages are static and never echo the submitted value.
 */

const PAGINATION = Object.freeze({
  defaultLimit: 20,
  maxLimit: 100,
  maxPage: 10000,
});

/** Earliest plausible date on a lab report. Rejects typos like year 0201. */
const MIN_REPORT_YEAR = 1900;

/** Tolerance for a client clock running ahead of the server. */
const FUTURE_SKEW_MS = 24 * 60 * 60 * 1000;

/**
 * `reportDate` - the date printed on the lab report (optional).
 * Multipart fields are always strings, so this is a string chain even though
 * the stored value is a Date.
 */
const reportDateField = body('reportDate')
  .optional()
  .isString()
  .withMessage('Report date must be a single text value')
  .bail()
  .trim()
  .notEmpty()
  .withMessage('Report date must not be empty')
  .bail()
  .isISO8601()
  .withMessage('Report date must be an ISO-8601 date (e.g. 2026-03-14)')
  .bail()
  .custom((value) => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return false;
    if (date.getUTCFullYear() < MIN_REPORT_YEAR) {
      throw new Error(`Report date must be no earlier than ${MIN_REPORT_YEAR}`);
    }
    if (date.getTime() > Date.now() + FUTURE_SKEW_MS) {
      throw new Error('Report date cannot be in the future');
    }
    return true;
  })
  .withMessage('Report date is not a valid date')
  .customSanitizer((value) => new Date(value));

const uploadReportValidator = [reportDateField];

/** `:id` must be a 24-char hex ObjectId before it is allowed near a query. */
const reportIdValidator = [
  param('id')
    .isString()
    .withMessage('Invalid report id')
    .bail()
    .trim()
    .matches(/^[a-fA-F0-9]{24}$/)
    .withMessage('Invalid report id'),
];

const listReportsValidator = [
  query('page')
    .optional()
    .isString()
    .withMessage('Page must be a single value')
    .bail()
    .isInt({ min: 1, max: PAGINATION.maxPage })
    .withMessage(`Page must be an integer between 1 and ${PAGINATION.maxPage}`)
    .bail()
    .toInt(),

  query('limit')
    .optional()
    .isString()
    .withMessage('Limit must be a single value')
    .bail()
    .isInt({ min: 1, max: PAGINATION.maxLimit })
    .withMessage(`Limit must be an integer between 1 and ${PAGINATION.maxLimit}`)
    .bail()
    .toInt(),

  // Allow-listed, never interpolated into a query from raw input.
  query('sort')
    .optional()
    .isString()
    .withMessage('Sort must be a single value')
    .bail()
    .trim()
    .isIn(SORT_FIELDS)
    .withMessage(`Sort must be one of: ${SORT_FIELDS.join(', ')}`),

  query('order')
    .optional()
    .isString()
    .withMessage('Order must be a single value')
    .bail()
    .trim()
    .toLowerCase()
    .isIn(['asc', 'desc'])
    .withMessage('Order must be asc or desc'),

  query('status')
    .optional()
    .isString()
    .withMessage('Status must be a single value')
    .bail()
    .trim()
    .toLowerCase()
    .isIn(REPORT_STATUS_VALUES)
    .withMessage(`Status must be one of: ${REPORT_STATUS_VALUES.join(', ')}`),
];

module.exports = {
  uploadReportValidator,
  reportIdValidator,
  listReportsValidator,
  PAGINATION,
  MIN_REPORT_YEAR,
};
