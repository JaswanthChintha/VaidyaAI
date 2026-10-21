'use strict';

const config = require('../config/env');
const ApiError = require('../utils/ApiError');
const { sendError } = require('../utils/apiResponse');

function notFoundHandler(req, res, next) {
  next(ApiError.notFound(`Route ${req.method} ${req.originalUrl} not found`));
}

const MULTIPART_PARSE_MESSAGES = [
  'malformed part header',
  'unexpected end of form',
  'unexpected end of multipart data',
  'malformed content type',
  'missing content-type boundary',
  'multipart: boundary not found',
  'unsupported content type',
  'invalid multipart',
];

function isMultipartParseError(err) {
  if (!err) return false;
  if (err.isMultipartParseError === true) return true;
  if (err.name === 'MulterError') return false;
  const message = String((err && err.message) || '').toLowerCase();
  if (!message) return false;
  return MULTIPART_PARSE_MESSAGES.some((needle) => message.includes(needle));
}

function normalizeError(err) {
  if (err instanceof ApiError) return err;

  if (err && err.code === 11000) {
    const field = Object.keys(err.keyValue || {})[0] || 'field';
    return ApiError.conflict(`An account with that ${field} already exists`);
  }

  if (err && err.name === 'ValidationError') {
    const details = Object.values(err.errors || {}).map((e) => ({
      field: e.path,
      message: e.message,
    }));
    return ApiError.validation('Invalid request payload', details);
  }

  if (err && err.name === 'CastError') {
    return ApiError.badRequest(`Invalid value for ${err.path}`);
  }

  if (err && err.name === 'MulterError') {
    switch (err.code) {
      case 'LIMIT_FILE_SIZE':
        return new ApiError(
          413,
          'PAYLOAD_TOO_LARGE',
          'The uploaded file exceeds the maximum allowed size'
        );
      case 'LIMIT_FILE_COUNT':
      case 'LIMIT_UNEXPECTED_FILE':
        return ApiError.badRequest(
          'Unexpected file upload. Send exactly one file in the `file` field.'
        );
      case 'LIMIT_PART_COUNT':
      case 'LIMIT_FIELD_COUNT':
      case 'LIMIT_FIELD_KEY':
      case 'LIMIT_FIELD_VALUE':
        return ApiError.badRequest('The upload contains too many or too large form fields');
      default:
        return ApiError.badRequest('The uploaded form data could not be processed');
    }
  }

  if (isMultipartParseError(err)) {
    return ApiError.badRequest('The multipart form data could not be parsed');
  }

  if (err && err.name === 'UnknownStorageDriverError') {
    return new ApiError(
      503,
      'STORAGE_UNAVAILABLE',
      'The storage backend for this report is not available'
    );
  }

  if (err && typeof err.type === 'string') {
    switch (err.type) {
      case 'entity.parse.failed':
        return ApiError.badRequest('Malformed JSON in request body');
      case 'entity.too.large':
      case 'parameters.too.many':
        return new ApiError(
          413,
          'PAYLOAD_TOO_LARGE',
          'Request body is too large'
        );
      case 'request.aborted':
        return ApiError.badRequest('Request aborted before it was fully received');
      case 'request.size.did.not.match.content.length':
        return ApiError.badRequest('Request body size did not match Content-Length');
      case 'encoding.unsupported':
      case 'charset.unsupported':
        return new ApiError(
          415,
          'UNSUPPORTED_MEDIA_TYPE',
          'Unsupported content encoding or charset'
        );
      case 'entity.verify.failed':
        return ApiError.forbidden('Request body verification failed');
      default:
        break;
    }
  }

  const status = Number(err && (err.status || err.statusCode));
  if (Number.isInteger(status) && status >= 400 && status < 500 && err.expose === true) {
    return new ApiError(status, 'BAD_REQUEST', err.message || 'Bad request');
  }

  return null;
}

function errorHandler(err, req, res, next) {
  const normalized = normalizeError(err);

  if (normalized) {
    const body = { code: normalized.code, message: normalized.message };
    if (normalized.details !== undefined) body.details = normalized.details;
    return res
      .status(normalized.statusCode)
      .json({ success: false, error: body });
  }

  if (!config.isTest) {
    console.error('[unhandled-error]', err);
  }

  if (config.isProduction) {
    return sendError(res, 500, 'INTERNAL_ERROR', 'Internal server error');
  }
  return res.status(500).json({
    success: false,
    error: {
      code: 'INTERNAL_ERROR',
      message: err && err.message ? err.message : 'Internal server error',
      stack: err && err.stack,
    },
  });
}

module.exports = { errorHandler, notFoundHandler, normalizeError, isMultipartParseError };
