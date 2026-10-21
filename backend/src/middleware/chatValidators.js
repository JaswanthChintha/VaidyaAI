'use strict';

const { body } = require('express-validator');


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
