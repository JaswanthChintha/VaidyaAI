'use strict';

function sendSuccess(res, statusCode, data) {
  return res.status(statusCode).json({ success: true, data });
}

function sendError(res, statusCode, code, message, details) {
  const error = { code, message };
  if (details !== undefined) error.details = details;
  return res.status(statusCode).json({ success: false, error });
}

module.exports = { sendSuccess, sendError };
