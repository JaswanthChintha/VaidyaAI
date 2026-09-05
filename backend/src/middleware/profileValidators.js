'use strict';

const { body } = require('express-validator');
const {
  GENDER_VALUES,
  SMOKING_HISTORY_VALUES,
  BOUNDS,
  TEXT_LIST,
  NOTES_LIST,
} = require('../models/Profile');

/**
 * SECURITY - the same rule Module 1's authValidators documents applies here,
 * and applies to NON-string fields too.
 *
 * A JSON body can carry arrays and objects. `hpp()` only touches query strings
 * and urlencoded bodies, and `express-mongo-sanitize` only strips `$`/`.` keys
 * (so `{"$ne": null}` arrives as `{"_ne": null}` - still an object). Without an
 * explicit type guard those values reach Mongo, where scalar-vs-array matching
 * silently changes the meaning of a query. Every chain below therefore starts
 * with a type guard and `.bail()` before any range check or sanitizer:
 *
 *   strings  -> .isString().bail()
 *   numbers  -> typeof === 'number' && Number.isFinite  (JSON numbers only;
 *               numeric STRINGS are rejected, so units can never be smuggled
 *               in as "70kg")
 *   booleans -> typeof === 'boolean'  (not "true"/1)
 *   arrays   -> .isArray().bail()
 *
 * Error messages are static and never echo the submitted value back.
 */

const TYPE_MESSAGES = {
  number: 'must be a number',
  boolean: 'must be true or false',
  string: 'must be a single text value',
  array: 'must be an array of text values',
};

/** Optional JSON number within [min, max]; integers only when `integer` is set. */
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

/** Optional strict JSON boolean. */
const booleanField = (field, label) =>
  body(field)
    .optional()
    .custom((value) => typeof value === 'boolean')
    .withMessage(`${label} ${TYPE_MESSAGES.boolean}`);

/** Optional string constrained to an enum. */
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

/** Strip control characters and collapse runs of whitespace. */
const cleanText = (value) =>
  String(value)
    .replace(/[\x00-\x1f\x7f]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

/**
 * Optional array of free-text entries with a count cap and a per-entry length
 * cap. Entries are sanitized (control characters removed, whitespace collapsed,
 * blanks dropped) AFTER the caps are enforced, so a caller cannot slip an
 * over-long entry past the cap by padding it with whitespace.
 */
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

/**
 * One shared chain list for POST / PUT / PATCH.
 *
 * Every field is optional at the validation layer: a profile may legitimately
 * be partially filled in (see the `completeness` virtual - later modules are
 * required to degrade gracefully rather than assume a full profile).
 *
 * `bmi` is intentionally absent: it is derived from height and weight by the
 * model. The controller allow-lists the fields below, so a client-supplied
 * `bmi` (or `user`, or `_id`) is silently ignored rather than persisted.
 *
 * `null` is not an accepted value for any field - it fails the type guard with
 * a 422. To clear fields, send a full `PUT /me` without them, or `DELETE /me`.
 */
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

/** Fields a client is allowed to write. Anything else in the body is ignored. */
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
