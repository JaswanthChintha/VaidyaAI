'use strict';

const { body } = require('express-validator');
const {
  GENDER_VALUES,
  SMOKING_HISTORY_VALUES,
  BOUNDS,
  TEXT_LIST,
  NOTES_LIST,
} = require('../models/Profile');


const TYPE_MESSAGES = {
  number: 'must be a number',
  boolean: 'must be true or false',
  string: 'must be a single text value',
  array: 'must be an array of text values',
};

const numberField = (field, label, { min, max, integer = false } = {}) => {
  let chain = body(field)
    .optional()
    .custom((value) => typeof value === 'number' && Number.isFinite(value))
    .withMessage(`${label} ${TYPE_MESSAGES.number}`)
    .bail();

  if (integer) {
    chain = chain
      .custom((value) => Number.isInteger(value))
      .withMessage(`${label} must be a whole number`)
      .bail();
  }

  return chain
    .custom((value) => value >= min && value <= max)
    .withMessage(`${label} must be between ${min} and ${max}`);
};

const booleanField = (field, label) =>
  body(field)
    .optional()
    .custom((value) => typeof value === 'boolean')
    .withMessage(`${label} ${TYPE_MESSAGES.boolean}`);

const enumField = (field, label, values) =>
  body(field)
    .optional()
    .isString()
    .withMessage(`${label} ${TYPE_MESSAGES.string}`)
    .bail()
    .trim()
    .toLowerCase()
    .isIn(values)
    .withMessage(`${label} must be one of: ${values.join(', ')}`);

const cleanText = (value) =>
  String(value)
    .replace(/[\x00-\x1f\x7f]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

const textListField = (field, label, cap) =>
  body(field)
    .optional()
    .isArray()
    .withMessage(`${label} ${TYPE_MESSAGES.array}`)
    .bail()
    .custom((list) => list.length <= cap.maxItems)
    .withMessage(`${label} may contain at most ${cap.maxItems} entries`)
    .bail()
    .custom((list) => list.every((entry) => typeof entry === 'string'))
    .withMessage(`Each entry in ${label.toLowerCase()} ${TYPE_MESSAGES.string}`)
    .bail()
    .custom((list) => list.every((entry) => entry.length <= cap.maxItemLength))
    .withMessage(
      `Each entry in ${label.toLowerCase()} must be at most ${cap.maxItemLength} characters`
    )
    .customSanitizer((list) => list.map(cleanText).filter((entry) => entry.length > 0));

const profileValidator = [
  numberField('age', 'Age', { ...BOUNDS.age, integer: true }),
  enumField('gender', 'Gender', GENDER_VALUES),
  numberField('heightCm', 'Height (cm)', BOUNDS.heightCm),
  numberField('weightKg', 'Weight (kg)', BOUNDS.weightKg),
  booleanField('hypertension', 'Hypertension status'),
  booleanField('heartDisease', 'Heart disease status'),
  textListField('heartDiseaseDetails', 'Heart disease details', TEXT_LIST),
  enumField('smokingHistory', 'Smoking history', SMOKING_HISTORY_VALUES),
  textListField('allergies', 'Allergies', TEXT_LIST),
  textListField('medicalConditions', 'Medical conditions', TEXT_LIST),
  textListField('medications', 'Medications', TEXT_LIST),
  textListField('previousHealthInformation', 'Previous health information', NOTES_LIST),
];

const WRITABLE_FIELDS = Object.freeze([
  'age',
  'gender',
  'heightCm',
  'weightKg',
  'hypertension',
  'heartDisease',
  'heartDiseaseDetails',
  'smokingHistory',
  'allergies',
  'medicalConditions',
  'medications',
  'previousHealthInformation',
]);

module.exports = { profileValidator, WRITABLE_FIELDS, cleanText };
