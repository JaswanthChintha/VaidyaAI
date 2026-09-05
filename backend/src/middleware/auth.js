'use strict';

const mongoose = require('mongoose');
const User = require('../models/User');
const ApiError = require('../utils/ApiError');
const asyncHandler = require('../utils/asyncHandler');
const { verifyAccessToken, extractBearerToken } = require('../utils/jwt');

/**
 * Authentication guard.
 * Reads `Authorization: Bearer <token>`, verifies the access token, loads the
 * user and attaches it to `req.user`.
 *
 * Every failure mode here - missing header, malformed header, expired token,
 * tampered token, deleted/deactivated user, token issued before a password
 * change - results in 401, never 500.
 */
const protect = asyncHandler(async (req, res, next) => {
  const token = extractBearerToken(req.headers.authorization);
  if (!token) {
    throw ApiError.unauthorized(
      'Authentication required. Provide a Bearer token.',
      'MISSING_TOKEN'
    );
  }

  const payload = verifyAccessToken(token); // throws ApiError(401) on any problem

  if (!mongoose.isValidObjectId(payload.sub)) {
    throw ApiError.unauthorized('Invalid authentication token', 'INVALID_TOKEN');
  }

  const user = await User.findById(payload.sub).select('+passwordChangedAt');
  if (!user) {
    throw ApiError.unauthorized(
      'The user belonging to this token no longer exists',
      'USER_NOT_FOUND'
    );
  }
  if (!user.isActive) {
    throw ApiError.unauthorized('This account has been deactivated', 'ACCOUNT_INACTIVE');
  }
  if (user.passwordChangedAfter(payload.iat)) {
    throw ApiError.unauthorized(
      'Password was changed recently. Please log in again.',
      'PASSWORD_CHANGED'
    );
  }

  req.user = user;
  req.tokenPayload = payload;
  return next();
});

/**
 * Authorization guard. Must run after `protect`.
 * @param {...string} roles roles allowed through
 */
function restrictTo(...roles) {
  const allowed = roles.flat();
  return function roleGuard(req, res, next) {
    if (!req.user) {
      return next(ApiError.unauthorized('Authentication required'));
    }
    if (!allowed.includes(req.user.role)) {
      return next(
        ApiError.forbidden(
          'You do not have permission to perform this action',
          'INSUFFICIENT_ROLE'
        )
      );
    }
    return next();
  };
}

module.exports = { protect, restrictTo };
