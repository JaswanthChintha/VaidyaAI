'use strict';

const ApiError = require('./ApiError');

/**
 * Generic ownership utilities implementing the spec's principle of least privilege:
 * "users can access only their own medical information".
 *
 * These helpers are deliberately storage-agnostic. No patient-record collection
 * exists in Module 1, so nothing here assumes a particular model; later modules
 * (profiles, reports, analyses) reuse these helpers by pointing `ownerField` at
 * whichever attribute holds the owning user id.
 */

const DEFAULT_OPTIONS = Object.freeze({
  ownerField: 'user',
  // Roles that may bypass the ownership check (staff/administrative access).
  //
  // SECURITY: this DENIES BY DEFAULT - no role bypasses ownership unless a call
  // site explicitly grants one. It previously defaulted to `[ROLES.ADMIN]`,
  // which is an opt-OUT security default and therefore fails open: every future
  // module touching patient data (reports, feature repository, dashboards,
  // trends, comparisons) would silently inherit an administrator bypass on
  // medical records if its author simply forgot to opt out.
  //
  // That is the same failure shape this codebase has already hit twice - the
  // 72-byte password cap that held only at the validator, and `.isString()`
  // present on four validator chains but missing on the fifth (a live
  // authentication bypass). Both times the fix that held was the one at the
  // lowest layer, applied by default. Section 19 requires that "users can
  // access only their own medical information" under the principle of least
  // privilege, so the safe behaviour is the one you get for free.
  //
  // The capability is unchanged and still available where it is genuinely
  // warranted - pass it explicitly and deliberately:
  //   ownerScopedFilter(req.user, { allowRoles: [ROLES.ADMIN] })
  allowRoles: [],
});

/**
 * Options preset for medical data: nobody bypasses ownership, not even an
 * administrator.
 *
 * NOTE: as of the deny-by-default change above this is IDENTICAL to the default
 * and is therefore redundant. It is kept, exported, and still spread at the
 * profile call sites deliberately - the same belt-and-braces reasoning that
 * makes the controller re-check with `assertCanAccess` after an already
 * owner-scoped query. It states the intent at the call site, and it keeps
 * health-data access denying even if the default is ever loosened again.
 *
 *   assertCanAccess(req.user, profile, { ...OWNER_ONLY });
 *   ownerScopedFilter(req.user, { ...OWNER_ONLY });
 */
const OWNER_ONLY = Object.freeze({ allowRoles: Object.freeze([]) });

/** Normalise ObjectId | string | populated doc to a comparable id string. */
function toIdString(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === 'string') return value;
  if (typeof value === 'object') {
    // ObjectId first: a Mongoose ObjectId exposes an `_id` getter that returns
    // itself, so checking `_id` before `toHexString` would recurse forever.
    if (typeof value.toHexString === 'function') return value.toHexString();
    if (value._id !== undefined && value._id !== null && value._id !== value) {
      return toIdString(value._id);
    }
  }
  return String(value);
}

/** Read a possibly dotted path off an object. */
function getPath(source, path) {
  if (!source || typeof source !== 'object') return undefined;
  return String(path)
    .split('.')
    .reduce((acc, key) => (acc === null || acc === undefined ? undefined : acc[key]), source);
}

/**
 * Does `user` own `resource`?
 * @param {{id?: *, _id?: *, role?: string}} user
 * @param {object} resource
 * @param {{ownerField?: string, allowRoles?: string[]}} [options]
 * @returns {boolean}
 */
function isOwner(user, resource, options = {}) {
  const { ownerField } = { ...DEFAULT_OPTIONS, ...options };
  if (!user || !resource) return false;

  const userId = toIdString(user.id ?? user._id);
  if (!userId) return false;

  const ownerId = toIdString(getPath(resource, ownerField));
  if (!ownerId) return false;

  return ownerId === userId;
}

/**
 * Would `user` be permitted to touch `resource` — as its owner, or via a role
 * that `allowRoles` explicitly grants a bypass (nobody, by default)?
 * @returns {boolean}
 */
function canAccess(user, resource, options = {}) {
  const { allowRoles } = { ...DEFAULT_OPTIONS, ...options };
  if (!user) return false;
  if (Array.isArray(allowRoles) && user.role && allowRoles.includes(user.role)) return true;
  return isOwner(user, resource, options);
}

/**
 * Throwing variant of {@link canAccess}. Throws 404 when the resource is absent
 * (so a non-owner cannot probe for the existence of another user's record) and
 * 403 when it exists but belongs to somebody else.
 */
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

/**
 * Build a Mongo query filter scoped to the requesting user. Every caller is
 * limited to their own documents unless `allowRoles` explicitly grants their
 * role a bypass, in which case the filter is left unscoped.
 * @param {{id?: *, _id?: *, role?: string}} user
 * @param {{ownerField?: string, allowRoles?: string[], base?: object}} [options]
 * @returns {object}
 */
function ownerScopedFilter(user, options = {}) {
  const { ownerField, allowRoles, base = {} } = { ...DEFAULT_OPTIONS, ...options };

  // ORDER IS SECURITY-CRITICAL. The identity check runs FIRST, before any
  // `allowRoles` bypass is considered.
  //
  // Previously the bypass was evaluated first, so an identity-less caller that
  // merely carried a granted role - `ownerScopedFilter({ role: 'admin' },
  // { allowRoles: ['admin'] })` - received `{}`, an UNSCOPED filter matching
  // every document in the collection. That is precisely the outcome the throw
  // below was added to prevent, and it silently sidestepped it. No call site
  // reaches it today because every one of them passes `{ ...OWNER_ONLY }`, but
  // the first module that legitimately grants a staff bypass (a clinician
  // viewing a shared report, an admin audit tool) would inherit a
  // collection-wide read from a malformed identity object.
  //
  // With the order reversed, "no id" always denies, whatever the role claims.
  const ownerId = toIdString(user && (user.id ?? user._id));
  if (!ownerId) {
    // SECURITY: previously this returned `{ user: null }`, which is a VALID
    // Mongo filter that matches every document whose owner field is null or
    // absent - i.e. an unauthenticated or malformed caller got a query that
    // silently succeeded instead of one that denied. Fail loudly instead: a
    // scoped query with no identity to scope to is a programming error, and an
    // exception becomes a 500, never a data leak.
    throw new Error(
      'ownerScopedFilter requires an authenticated user with an id; ' +
        'refusing to build an unscoped filter'
    );
  }

  // Only now may an explicitly granted role widen the scope.
  if (Array.isArray(allowRoles) && user.role && allowRoles.includes(user.role)) {
    return { ...base };
  }

  return { ...base, [ownerField]: ownerId };
}

/**
 * Express middleware factory. `loadResource(req)` returns (or resolves to) the
 * resource being accessed; the middleware enforces ownership and stashes the
 * resource on `req.resource` for the downstream handler.
 *
 * @param {(req: import('express').Request) => any} loadResource
 * @param {{ownerField?: string, allowRoles?: string[], attachAs?: string}} [options]
 */
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
