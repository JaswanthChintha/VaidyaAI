'use strict';

/**
 * Operational (expected) application error.
 * Anything thrown that is NOT an ApiError is treated as an unexpected failure
 * by the centralized error handler and is never echoed back to the client.
 */
class ApiError extends Error {
  /**
   * @param {number} statusCode HTTP status code
   * @param {string} code Stable machine-readable error code
   * @param {string} message Human-readable message (safe to expose)
   * @param {*} [details] Optional structured details (e.g. validation issues)
   */
  constructor(statusCode, code, message, details) {
    super(message);
    this.name = 'ApiError';
    this.statusCode = statusCode;
    this.code = code;
    this.details = details;
    this.isOperational = true;
    Error.captureStackTrace(this, this.constructor);
  }

  static badRequest(message = 'Bad request', details) {
    return new ApiError(400, 'BAD_REQUEST', message, details);
  }

  static validation(message = 'Validation failed', details) {
    return new ApiError(422, 'VALIDATION_ERROR', message, details);
  }

  static unauthorized(message = 'Authentication required', code = 'UNAUTHORIZED') {
    return new ApiError(401, code, message);
  }

  static forbidden(message = 'You do not have permission to perform this action', code = 'FORBIDDEN') {
    return new ApiError(403, code, message);
  }

  static notFound(message = 'Resource not found') {
    return new ApiError(404, 'NOT_FOUND', message);
  }

  static conflict(message = 'Resource already exists') {
    return new ApiError(409, 'CONFLICT', message);
  }

  static tooManyRequests(message = 'Too many requests, please try again later') {
    return new ApiError(429, 'RATE_LIMIT_EXCEEDED', message);
  }

  static internal(message = 'Internal server error') {
    return new ApiError(500, 'INTERNAL_ERROR', message);
  }
}

module.exports = ApiError;
