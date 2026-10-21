'use strict';

const { body, param, query } = require('express-validator');
const { SORT_FIELDS, REPORT_STATUS_VALUES } = require('../models/Report');
const Profile = require('../models/Profile');


const PAGINATION = Object.freeze({
  defaultLimit: 20,
  maxLimit: 100,
  maxPage: 10000,
});

const MIN_REPORT_YEAR = 1900;

const FUTURE_SKEW_MS = 24 * 60 * 60 * 1000;

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

const SUBJECT_OWNERS = Object.freeze(['self', 'other']);

const subjectOwnerField = (required) => {
  const chain = body('subjectOwner');
  return (required ? chain : chain.optional())
    .isString()
    .withMessage('Whose report this is must be "self" or "other"')
    .bail()
    .trim()
    .isIn(SUBJECT_OWNERS)
    .withMessage('Whose report this is must be "self" or "other"');
};

const onlyForOther = (label) => (value, { req }) => {
  if (req.body.subjectOwner !== 'other') {
    throw new Error(`${label} can only be given for someone else's report`);
  }
  return true;
};

const subjectAgeField = body('subjectAge')
  .optional({ values: 'falsy' })
  .custom((value) => {
    const text = typeof value === 'number' ? String(value) : value;
    if (typeof text !== 'string' || !/^\d{1,3}$/.test(text.trim())) {
      throw new Error('Age must be a whole number of years');
    }
    const n = Number(text.trim());
    if (n < 0 || n > 120) throw new Error('Age must be between 0 and 120');
    return true;
  })
  .bail()
  .custom(onlyForOther('An age'))
  .customSanitizer((value) => Number(String(value).trim()));

const subjectSexField = body('subjectSex')
  .optional({ values: 'falsy' })
  .isString()
  .withMessage('Sex must be one of the listed options')
  .bail()
  .trim()
  .isIn(Profile.GENDER_VALUES)
  .withMessage('Sex must be one of the listed options')
  .bail()
  .custom(onlyForOther('A sex'));

const uploadReportValidator = [
  reportDateField,
  subjectOwnerField(false),
  subjectAgeField,
  subjectSexField,
];

const reportSubjectValidator = [subjectOwnerField(true), subjectAgeField, subjectSexField];

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
  reportSubjectValidator,
  SUBJECT_OWNERS,
  reportIdValidator,
  listReportsValidator,
  PAGINATION,
  MIN_REPORT_YEAR,
};
