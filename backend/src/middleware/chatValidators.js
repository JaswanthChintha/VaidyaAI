'use strict';

const { body } = require('express-validator');

/**
 * The chatbot's input (2026-10-09).
 *
 * THE STANDING RULE: every chain starts with a type guard and `.bail()` before
 * any sanitizer, so no untyped value reaches a Mongo query -- `reportId` is
 * handed to `Report.findOne`. Messages are static and never echo the input.
 */

const OBJECT_ID = /^[a-fA-F0-9]{24}$/;
const MAX_QUESTION_CHARS = 300;

const chatValidator = [
  body('question')
    .isString()
    .withMessage('Type a question')
    .bail()
    .trim()
    .isLength({ min: 1, max: MAX_QUESTION_CHARS })
    .withMessage(`A question must be 1 to ${MAX_QUESTION_CHARS} characters`),
  body('reportId')
    .optional({ values: 'null' })
    .isString()
    .withMessage('reportId must be a report id')
    .bail()
    .matches(OBJECT_ID)
    .withMessage('reportId must be a valid report id'),
];

module.exports = { chatValidator, MAX_QUESTION_CHARS };
