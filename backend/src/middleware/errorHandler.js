'use strict';

const config = require('../config/env');
const ApiError = require('../utils/ApiError');
const { sendError } = require('../utils/apiResponse');

/** 404 handler for unmatched routes. */
function notFoundHandler(req, res, next) {
  next(ApiError.notFound(`Route ${req.method} ${req.originalUrl} not found`));
}

/**
 * Messages busboy raises for a corrupt multipart stream. Matching on the
 * message is unpleasant, but busboy gives us nothing else to key on: these are
 * bare `new Error(...)` instances. The authoritative fix is structural (see
 * `middleware/upload.js`, which tags every error multer surfaces); this list is
 * only the second line of defence.
 */
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

/** Does this error look like a multipart/busboy parse failure? */
function isMultipartParseError(err) {
  if (!err) return false;
  // Structural marker set by middleware/upload.js - always preferred.
  if (err.isMultipartParseError === true) return true;
  if (err.name === 'MulterError') return false; // handled by its own branch
  const message = String((err && err.message) || '').toLowerCase();
  if (!message) return false;
  return MULTIPART_PARSE_MESSAGES.some((needle) => message.includes(needle));
}

/** Translate known third-party/driver errors into ApiError instances. */
function normalizeError(err) {
  if (err instanceof ApiError) return err;

  // Duplicate key (unique index) - e.g. email already registered.
  if (err && err.code === 11000) {
    const field = Object.keys(err.keyValue || {})[0] || 'field';
    return ApiError.conflict(`An account with that ${field} already exists`);
  }

  // Mongoose schema validation.
  if (err && err.name === 'ValidationError') {
    const details = Object.values(err.errors || {}).map((e) => ({
      field: e.path,
      message: e.message,
    }));
    return ApiError.validation('Invalid request payload', details);
  }

  // Bad ObjectId / cast failure.
  if (err && err.name === 'CastError') {
    return ApiError.badRequest(`Invalid value for ${err.path}`);
  }

  // --- multer / multipart failures (Module 3 uploads) -----------------------
  // MulterError is a plain Error subclass with a `code`. Left unmapped it falls
  // through to the 500 branch, which prints a stack trace containing absolute
  // filesystem paths - exactly the defect Module 1 had with oversized JSON
  // bodies. An oversized upload must be a clean 413, never a 500 and never a
  // hung request. Messages here are static and never echo the field name or
  // filename the client supplied.
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

  // --- busboy / raw multipart parse failures (defect D1) --------------------
  // multer delegates parsing to busboy, and busboy signals a corrupt multipart
  // stream by throwing a PLAIN `Error` - `Malformed part header`,
  // `Unexpected end of form`, `Malformed part header` on a filename containing
  // a control character, and so on. No `code`, no `type`, no `expose`, so it
  // misses every branch above and lands in the generic 500 branch, which prints
  // a stack trace naming `node_modules/busboy/lib/types/multipart.js`.
  //
  // A malformed multipart body is a CLIENT error and must be a 400 in every
  // environment, not just a non-leaky 500 in production. The primary fix lives
  // upstream in `middleware/upload.js`, which converts anything multer/busboy
  // surfaces into an ApiError before it ever reaches here; this branch is the
  // belt-and-braces half, so any future route that parses multipart by another
  // route still gets a 4xx rather than a stack trace.
  if (isMultipartParseError(err)) {
    return ApiError.badRequest('The multipart form data could not be parsed');
  }

  // --- storage adapter resolution failure (defect D2) -----------------------
  // A report row naming a driver this build does not register. Only reachable
  // through a raw-driver write or a rolled-back deploy, but it must not be the
  // one error class left able to print a stack.
  if (err && err.name === 'UnknownStorageDriverError') {
    return new ApiError(
      503,
      'STORAGE_UNAVAILABLE',
      'The storage backend for this report is not available'
    );
  }

  // --- body-parser / raw-body failures -------------------------------------
  // These carry an `err.type` and an HTTP status but are plain Error subclasses,
  // so without explicit mapping they fall through to the generic 500 branch and
  // leak a stack trace containing absolute node_modules paths.
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

  // Generic safety net for any other http-errors-style client error (these set
  // `expose: true` for 4xx). Keeps unexpected framework errors out of the 500
  // branch, which is the only branch that prints a stack.
  const status = Number(err && (err.status || err.statusCode));
  if (Number.isInteger(status) && status >= 400 && status < 500 && err.expose === true) {
    return new ApiError(status, 'BAD_REQUEST', err.message || 'Bad request');
  }

  return null;
}

/**
 * Centralized error handler.
 * Only operational errors leak their message; everything else becomes a generic
 * 500. Stack traces are exposed in non-production environments only.
 */
// eslint-disable-next-line no-unused-vars
function errorHandler(err, req, res, next) {
  const normalized = normalizeError(err);

  if (normalized) {
    const body = { code: normalized.code, message: normalized.message };
    if (normalized.details !== undefined) body.details = normalized.details;
    // NO STACK HERE, at any status code. A stack is a debugging aid for an
    // UNEXPECTED failure, and reaching this branch means the error was
    // recognised and deliberately mapped - it is operational by definition,
    // including the 5xx mappings above such as an unresolvable storage driver.
    // Attaching a stack to a case we already understand only re-opens the
    // absolute-path disclosure this handler exists to contain. Genuinely
    // unexpected errors still get one below, in non-production only.
    return res
      .status(normalized.statusCode)
      .json({ success: false, error: body });
  }

  // Unexpected error: log server-side, return an opaque response.
  if (!config.isTest) {
    // eslint-disable-next-line no-console
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
