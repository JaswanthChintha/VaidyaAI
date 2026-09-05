'use strict';

/**
 * Consistent success envelope: { success: true, data: ... }
 * @param {import('express').Response} res
 * @param {number} statusCode
 * @param {*} data
 */
function sendSuccess(res, statusCode, data) {
  return res.status(statusCode).json({ success: true, data });
}

/**
 * Consistent error envelope: { success: false, error: { code, message, details? } }
 * @param {import('express').Response} res
 * @param {number} statusCode
 * @param {string} code
 * @param {string} message
 * @param {*} [details]
 */
function sendError(res, statusCode, code, message, details) {
  const error = { code, message };
  if (details !== undefined) error.details = details;
  return res.status(statusCode).json({ success: false, error });
}

module.exports = { sendSuccess, sendError };
