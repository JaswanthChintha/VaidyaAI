'use strict';

const Profile = require('../models/Profile');
const ApiError = require('../utils/ApiError');
const asyncHandler = require('../utils/asyncHandler');
const { sendSuccess } = require('../utils/apiResponse');
const { WRITABLE_FIELDS } = require('../middleware/profileValidators');
const { ownerScopedFilter, assertCanAccess, OWNER_ONLY } = require('../utils/ownership');


const ownFilter = (req) => ownerScopedFilter(req.user, { ...OWNER_ONLY });

function pickWritable(body) {
  const payload = {};
  for (const field of WRITABLE_FIELDS) {
    if (Object.prototype.hasOwnProperty.call(body, field)) {
      payload[field] = body[field];
    }
  }
  return payload;
}

const profileNotFound = () =>
  ApiError.notFound('No profile found for this account. Create one first.');

const getMyProfile = asyncHandler(async (req, res) => {
  const profile = await Profile.findOne(ownFilter(req));
  if (!profile) throw profileNotFound();

  assertCanAccess(req.user, profile, { ...OWNER_ONLY });
  return sendSuccess(res, 200, { profile: profile.toPublicJSON() });
});

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

const replaceMyProfile = asyncHandler(async (req, res) => {
  const filter = ownFilter(req);
  const existing = await Profile.findOne(filter);
  const payload = pickWritable(req.body);

  if (!existing) {
    const created = await Profile.create({ ...payload, user: req.user._id });
    return sendSuccess(res, 201, { profile: created.toPublicJSON() });
  }

  assertCanAccess(req.user, existing, { ...OWNER_ONLY });

  for (const field of WRITABLE_FIELDS) {
    existing.set(field, Object.prototype.hasOwnProperty.call(payload, field)
      ? payload[field]
      : undefined);
  }

  await existing.save();
  return sendSuccess(res, 200, { profile: existing.toPublicJSON() });
});

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
