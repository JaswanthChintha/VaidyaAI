'use strict';

const ApiError = require('./ApiError');


const DEFAULT_OPTIONS = Object.freeze({
  ownerField: 'user',
  allowRoles: [],
});

const OWNER_ONLY = Object.freeze({ allowRoles: Object.freeze([]) });

function toIdString(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === 'string') return value;
  if (typeof value === 'object') {
    if (typeof value.toHexString === 'function') return value.toHexString();
    if (value._id !== undefined && value._id !== null && value._id !== value) {
      return toIdString(value._id);
    }
  }
  return String(value);
}

function getPath(source, path) {
  if (!source || typeof source !== 'object') return undefined;
  return String(path)
    .split('.')
    .reduce((acc, key) => (acc === null || acc === undefined ? undefined : acc[key]), source);
}

function isOwner(user, resource, options = {}) {
  const { ownerField } = { ...DEFAULT_OPTIONS, ...options };
  if (!user || !resource) return false;

  const userId = toIdString(user.id ?? user._id);
  if (!userId) return false;

  const ownerId = toIdString(getPath(resource, ownerField));
  if (!ownerId) return false;

  return ownerId === userId;
}

function canAccess(user, resource, options = {}) {
  const { allowRoles } = { ...DEFAULT_OPTIONS, ...options };
  if (!user) return false;
  if (Array.isArray(allowRoles) && user.role && allowRoles.includes(user.role)) return true;
  return isOwner(user, resource, options);
}

function assertCanAccess(user, resource, options = {}) {
  if (!resource) {
    throw ApiError.notFound('Resource not found');
  }
  if (!canAccess(user, resource, options)) {
    throw ApiError.forbidden(
      'You do not have permission to access this resource',
      'OWNERSHIP_REQUIRED'
    );
  }
  return true;
}

function ownerScopedFilter(user, options = {}) {
  const { ownerField, allowRoles, base = {} } = { ...DEFAULT_OPTIONS, ...options };

  const ownerId = toIdString(user && (user.id ?? user._id));
  if (!ownerId) {
    throw new Error(
      'ownerScopedFilter requires an authenticated user with an id; ' +
        'refusing to build an unscoped filter'
    );
  }

  if (Array.isArray(allowRoles) && user.role && allowRoles.includes(user.role)) {
    return { ...base };
  }

  return { ...base, [ownerField]: ownerId };
}

function requireOwnership(loadResource, options = {}) {
  const { attachAs = 'resource' } = options;
  return async function ownershipMiddleware(req, res, next) {
    try {
      if (!req.user) {
        return next(ApiError.unauthorized('Authentication required'));
      }
      const resource = await loadResource(req);
      assertCanAccess(req.user, resource, options);
      req[attachAs] = resource;
      return next();
    } catch (err) {
      return next(err);
    }
  };
}

module.exports = {
  OWNER_ONLY,
  isOwner,
  canAccess,
  assertCanAccess,
  ownerScopedFilter,
  requireOwnership,
  toIdString,
};
