'use strict';

const { body } = require('express-validator');
const config = require('../config/env');
const { ROLES } = require('../utils/roles');

const PASSWORD_RULE =
  'Password must be at least 8 characters and include an uppercase letter, a lowercase letter, a number and a special character';

const PASSWORD_BYTES_RULE = `Password is too long. Use at most ${config.maxPasswordBytes} characters (emoji and letters from some other alphabets count as more than one)`;

const stringField = (field, requiredMessage) =>
  body(field)
    .isString()
    .withMessage(requiredMessage)
    .bail();

const passwordChain = (field = 'password') =>
  stringField(field, 'Password must be a string')
    .isLength({ min: 8 })
    .withMessage(PASSWORD_RULE)
    .bail()
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

const currentPasswordChain = (field) =>
  stringField(field, 'Enter your current password')
    .notEmpty()
    .withMessage('Enter your current password')
    .bail()
    .custom((value) => Buffer.byteLength(value, 'utf8') <= config.maxPasswordBytes)
    .withMessage(PASSWORD_BYTES_RULE);

const changePasswordValidator = [
  currentPasswordChain('currentPassword'),
  passwordChain('newPassword'),
];

const deleteAccountValidator = [currentPasswordChain('password')];

module.exports = {
  registerValidator,
  loginValidator,
  refreshValidator,
  logoutValidator,
  changePasswordValidator,
  deleteAccountValidator,
  PASSWORD_RULE,
  PASSWORD_BYTES_RULE,
};
