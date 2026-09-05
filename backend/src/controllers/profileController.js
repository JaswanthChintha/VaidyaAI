'use strict';

const Profile = require('../models/Profile');
const ApiError = require('../utils/ApiError');
const asyncHandler = require('../utils/asyncHandler');
const { sendSuccess } = require('../utils/apiResponse');
const { WRITABLE_FIELDS } = require('../middleware/profileValidators');
const { ownerScopedFilter, assertCanAccess, OWNER_ONLY } = require('../utils/ownership');

/**
 * Module 2 - Patient Profile Management.
 *
 * OWNERSHIP MODEL (section 19: "users can access only their own medical
 * information"). Two independent layers, both using src/utils/ownership.js:
 *
 *  1. Every read and write is issued through `ownerScopedFilter(req.user,
 *     { ...OWNER_ONLY })`, so the Mongo query itself can only ever match the
 *     caller's own document. There is no route that accepts a profile id or a
 *     user id from the client, so there is nothing to tamper with.
 *  2. `assertCanAccess(req.user, profile, { ...OWNER_ONLY })` re-checks the
 *     loaded document before it is returned or mutated. Redundant by design:
 *     if a future refactor widens the filter, this still denies.
 *
 * `OWNER_ONLY` opts out of the helper's default administrator bypass. Health
 * data has no staff exception; an administrator reading another patient's
 * profile gets the same 404 any other non-owner gets.
 *
 * `assertCanAccess` answers 404 before 403, so a non-owner cannot use the
 * status code to learn whether another patient's record exists. Because the
 * query is owner-scoped, a non-owner never loads the document in the first
 * place and always sees the plain "no profile" 404 - indistinguishable from
 * the caller simply not having created one.
 */

/** Filter matching exactly the caller's own profile. Throws if unauthenticated. */
const ownFilter = (req) => ownerScopedFilter(req.user, { ...OWNER_ONLY });

/** Pick only the client-writable fields present in the body. */
function pickWritable(body) {
  const payload = {};
  for (const field of WRITABLE_FIELDS) {
    if (Object.prototype.hasOwnProperty.call(body, field)) {
      payload[field] = body[field];
    }
  }
  // NOTE: `bmi` is not in WRITABLE_FIELDS, so a client-supplied BMI is dropped
  // here. The model's pre('validate') hook then recomputes it from heightCm and
  // weightKg on every save, so even a direct model write cannot persist one.
  return payload;
}

const profileNotFound = () =>
  ApiError.notFound('No profile found for this account. Create one first.');

/**
 * GET /profile/me
 * 404 when the caller has no profile yet.
 *
 * Decision: 404, not an empty 200 object. "No profile" and "an empty profile"
 * are different states - the client needs to know whether to POST or PATCH, and
 * a synthesised empty body would report a misleading 0% completeness for a
 * record that does not exist.
 */
const getMyProfile = asyncHandler(async (req, res) => {
  const profile = await Profile.findOne(ownFilter(req));
  if (!profile) throw profileNotFound();

  assertCanAccess(req.user, profile, { ...OWNER_ONLY });
  return sendSuccess(res, 200, { profile: profile.toPublicJSON() });
});

/**
 * POST /profile/me
 * Strict create. 409 when a profile already exists (one profile per user, held
 * by a unique index on `user`).
 */
const createMyProfile = asyncHandler(async (req, res) => {
  const existing = await Profile.findOne(ownFilter(req)).select('_id').lean();
  if (existing) {
    throw ApiError.conflict('A profile already exists for this account. Use PUT or PATCH.');
  }

  const profile = await Profile.create({
    ...pickWritable(req.body),
    user: req.user._id,
  });

  return sendSuccess(res, 201, { profile: profile.toPublicJSON() });
});

/**
 * PUT /profile/me
 * Full replace, upserting when absent. 201 on create, 200 on replace.
 *
 * Decision: PUT has replace semantics - fields omitted from the body are
 * CLEARED. This is the only way to unset a field (null is rejected by the
 * validators as a type error), and it keeps PUT idempotent.
 */
const replaceMyProfile = asyncHandler(async (req, res) => {
  const filter = ownFilter(req);
  const existing = await Profile.findOne(filter);
  const payload = pickWritable(req.body);

  if (!existing) {
    const created = await Profile.create({ ...payload, user: req.user._id });
    return sendSuccess(res, 201, { profile: created.toPublicJSON() });
  }

  assertCanAccess(req.user, existing, { ...OWNER_ONLY });

  // Replace semantics: unset every writable field the body did not supply.
  for (const field of WRITABLE_FIELDS) {
    existing.set(field, Object.prototype.hasOwnProperty.call(payload, field)
      ? payload[field]
      : undefined);
  }

  await existing.save();
  return sendSuccess(res, 200, { profile: existing.toPublicJSON() });
});

/**
 * PATCH /profile/me
 * Partial update. 404 when no profile exists (PATCH never creates).
 */
const updateMyProfile = asyncHandler(async (req, res) => {
  const profile = await Profile.findOne(ownFilter(req));
  if (!profile) throw profileNotFound();

  assertCanAccess(req.user, profile, { ...OWNER_ONLY });

  const payload = pickWritable(req.body);
  for (const [field, value] of Object.entries(payload)) {
    profile.set(field, value);
  }

  await profile.save();
  return sendSuccess(res, 200, { profile: profile.toPublicJSON() });
});

/**
 * DELETE /profile/me
 * Deletes the caller's own profile. 404 when there is nothing to delete.
 */
const deleteMyProfile = asyncHandler(async (req, res) => {
  const profile = await Profile.findOne(ownFilter(req));
  if (!profile) throw profileNotFound();

  assertCanAccess(req.user, profile, { ...OWNER_ONLY });
  await Profile.deleteOne({ _id: profile._id, ...ownFilter(req) });

  return sendSuccess(res, 200, { deleted: true, id: profile._id.toString() });
});

module.exports = {
  getMyProfile,
  createMyProfile,
  replaceMyProfile,
  updateMyProfile,
  deleteMyProfile,
};
