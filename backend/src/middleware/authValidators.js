'use strict';

const { body } = require('express-validator');
const config = require('../config/env');
const { ROLES } = require('../utils/roles');

const PASSWORD_RULE =
  'Password must be at least 8 characters and include an uppercase letter, a lowercase letter, a number and a special character';

const PASSWORD_BYTES_RULE = `Password must be at most ${config.maxPasswordBytes} bytes long`;

/**
 * SECURITY: every chain below starts with `.isString().bail()`.
 *
 * A JSON body can carry arrays and objects, and neither hpp() (which only
 * touches query strings and urlencoded bodies) nor express-mongo-sanitize
 * (which strips `$`/`.` keys) turns those into strings. Without an explicit
 * type check a value such as `["a@example.com","b@example.com"]` reaches
 * Mongo, whose scalar-vs-array matching treats it as "any of these" - letting
 * one request spray a single password across many accounts. Type-check first,
 * and bail before any sanitizer (`.trim()`, `.normalizeEmail()`) that assumes
 * a string.
 */
const stringField = (field, requiredMessage) =>
  body(field)
    .isString()
    .withMessage(requiredMessage)
    .bail();

const passwordChain = (field = 'password') =>
  stringField(field, 'Password must be a string')
    .isLength({ min: 8, max: config.maxPasswordBytes })
    .withMessage(PASSWORD_RULE)
    .bail()
    // bcrypt silently ignores everything past 72 BYTES, so a 100-byte password
    // would authenticate against any string sharing its first 72 bytes.
    // Measure bytes, not characters: one emoji is 4 bytes.
    .custom((value) => Buffer.byteLength(value, 'utf8') <= config.maxPasswordBytes)
    .withMessage(PASSWORD_BYTES_RULE)
    .bail()
    .matches(/[a-z]/)
    .withMessage(PASSWORD_RULE)
    .bail()
    .matches(/[A-Z]/)
    .withMessage(PASSWORD_RULE)
    .bail()
    .matches(/\d/)
    .withMessage(PASSWORD_RULE)
    .bail()
    .matches(/[^A-Za-z0-9]/)
    .withMessage(PASSWORD_RULE);

const emailChain = () =>
  stringField('email', 'Email must be a single text value')
    .trim()
    .notEmpty()
    .withMessage('Email is required')
    .bail()
    .isLength({ max: 254 })
    .withMessage('Email is too long')
    .bail()
    .isEmail()
    .withMessage('Please provide a valid email address')
    .bail()
    .normalizeEmail({ gmail_remove_dots: false });

const registerValidator = [
  stringField('name', 'Name must be a single text value')
    .trim()
    .notEmpty()
    .withMessage('Name is required')
    .bail()
    .isLength({ min: 2, max: 100 })
    .withMessage('Name must be between 2 and 100 characters'),
  emailChain(),
  passwordChain('password'),
  // Self-service signup may only create patient accounts. Clinician/admin
  // accounts are provisioned by an administrator (see restrictTo usage).
  // The controller additionally hard-codes the role, so this is defence in depth.
  body('role')
    .optional()
    .isString()
    .withMessage('Self-registration is only permitted for the patient role')
    .bail()
    .isIn([ROLES.PATIENT])
    .withMessage('Self-registration is only permitted for the patient role'),
];

const loginValidator = [
  emailChain(),
  // No complexity rules on login (they belong at registration), but the byte
  // cap DOES apply to the submitted candidate. bcrypt truncates whatever it is
  // given at 72 bytes, so for an account whose password is exactly 72 bytes,
  // "<the password> + anything" would otherwise compare equal and authenticate.
  // Registration can no longer produce a password longer than 72 bytes, so
  // rejecting over-long candidates locks out nobody legitimate.
  stringField('password', 'Password is required')
    .notEmpty()
    .withMessage('Password is required')
    .bail()
    .custom((value) => Buffer.byteLength(value, 'utf8') <= config.maxPasswordBytes)
    .withMessage(PASSWORD_BYTES_RULE),
];

const refreshValidator = [
  stringField('refreshToken', 'refreshToken is required')
    .notEmpty()
    .withMessage('refreshToken is required'),
];

const logoutValidator = refreshValidator;

module.exports = {
  registerValidator,
  loginValidator,
  refreshValidator,
  logoutValidator,
  PASSWORD_RULE,
  PASSWORD_BYTES_RULE,
};
