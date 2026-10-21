'use strict';

const crypto = require('crypto');
const jwt = require('jsonwebtoken');
const config = require('../config/env');
const ApiError = require('./ApiError');

const TOKEN_TYPE = Object.freeze({ ACCESS: 'access', REFRESH: 'refresh' });

function signAccessToken(user) {
  return jwt.sign(
    { sub: String(user.id), role: user.role, type: TOKEN_TYPE.ACCESS },
    config.jwt.accessSecret,
    {
      expiresIn: config.jwt.accessExpiresIn,
      issuer: config.jwt.issuer,
      audience: config.jwt.audience,
    }
  );
}

function signRefreshToken(user) {
  const jti = crypto.randomUUID();
  const token = jwt.sign(
    { sub: String(user.id), type: TOKEN_TYPE.REFRESH, jti },
    config.jwt.refreshSecret,
    {
      expiresIn: config.jwt.refreshExpiresIn,
      issuer: config.jwt.issuer,
      audience: config.jwt.audience,
    }
  );
  return { token, jti };
}

function verifyToken(token, secret, expectedType) {
  let payload;
  try {
    payload = jwt.verify(token, secret, {
      issuer: config.jwt.issuer,
      audience: config.jwt.audience,
    });
  } catch (err) {
    if (err instanceof jwt.TokenExpiredError) {
      throw ApiError.unauthorized('Token has expired', 'TOKEN_EXPIRED');
    }
    throw ApiError.unauthorized('Invalid authentication token', 'INVALID_TOKEN');
  }

  if (payload.type !== expectedType) {
    throw ApiError.unauthorized('Invalid authentication token', 'INVALID_TOKEN');
  }
  return payload;
}

const verifyAccessToken = (token) =>
  verifyToken(token, config.jwt.accessSecret, TOKEN_TYPE.ACCESS);

const verifyRefreshToken = (token) =>
  verifyToken(token, config.jwt.refreshSecret, TOKEN_TYPE.REFRESH);

function hashToken(token) {
  return crypto.createHash('sha256').update(token).digest('hex');
}

function extractBearerToken(headerValue) {
  if (!headerValue || typeof headerValue !== 'string') return null;
  const parts = headerValue.trim().split(/\s+/);
  if (parts.length !== 2) return null;
  if (parts[0].toLowerCase() !== 'bearer') return null;
  if (!parts[1]) return null;
  return parts[1];
}

module.exports = {
  TOKEN_TYPE,
  signAccessToken,
  signRefreshToken,
  verifyAccessToken,
  verifyRefreshToken,
  hashToken,
  extractBearerToken,
};
