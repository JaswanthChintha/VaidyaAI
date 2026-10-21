'use strict';

const User = require('../models/User');
const Profile = require('../models/Profile');
const Report = require('../models/Report');
const { getStorage } = require('../storage');
const ApiError = require('../utils/ApiError');
const asyncHandler = require('../utils/asyncHandler');
const { sendSuccess } = require('../utils/apiResponse');
const { ROLES } = require('../utils/roles');
const {
  signAccessToken,
  signRefreshToken,
  verifyRefreshToken,
  hashToken,
} = require('../utils/jwt');

const MAX_SESSIONS = 5;

async function issueTokens(user) {
  const accessToken = signAccessToken({ id: user._id, role: user.role });
  const { token: refreshToken, jti } = signRefreshToken({ id: user._id });

  const decoded = verifyRefreshToken(refreshToken);
  const expiresAt = new Date(decoded.exp * 1000);

  const now = Date.now();
  const existing = (user.refreshTokens || []).filter(
    (t) => t.expiresAt && t.expiresAt.getTime() > now
  );
  existing.push({ tokenHash: hashToken(refreshToken), jti, expiresAt });

  user.refreshTokens = existing.slice(-MAX_SESSIONS);
  await user.save({ validateBeforeSave: false });

  return { accessToken, refreshToken };
}

const register = asyncHandler(async (req, res) => {
  const { name, email, password } = req.body;

  const existing = await User.findOne({ email });
  if (existing) {
    throw ApiError.conflict('An account with that email already exists');
  }

  const user = await User.create({
    name,
    email,
    password,
    role: ROLES.PATIENT,
  });

  const tokens = await issueTokens(user);

  return sendSuccess(res, 201, { user: user.toPublicJSON(), ...tokens });
});

const login = asyncHandler(async (req, res) => {
  const { email, password } = req.body;

  const user = await User.findOne({ email }).select('+password +refreshTokens');

  if (!user) {
    throw ApiError.unauthorized('Invalid email or password', 'INVALID_CREDENTIALS');
  }

  const matches = await user.comparePassword(password);
  if (!matches) {
    throw ApiError.unauthorized('Invalid email or password', 'INVALID_CREDENTIALS');
  }

  if (!user.isActive) {
    throw ApiError.unauthorized('This account has been deactivated', 'ACCOUNT_INACTIVE');
  }

  const tokens = await issueTokens(user);

  return sendSuccess(res, 200, { user: user.toPublicJSON(), ...tokens });
});

const refresh = asyncHandler(async (req, res) => {
  const { refreshToken } = req.body;

  const payload = verifyRefreshToken(refreshToken);

  const user = await User.findById(payload.sub).select('+refreshTokens +passwordChangedAt');
  if (!user || !user.isActive) {
    throw ApiError.unauthorized('Invalid refresh token', 'INVALID_REFRESH_TOKEN');
  }

  if (user.passwordChangedAfter(payload.iat)) {
    throw ApiError.unauthorized(
      'Password was changed recently. Please log in again.',
      'PASSWORD_CHANGED'
    );
  }

  const tokenHash = hashToken(refreshToken);
  const stored = (user.refreshTokens || []).find(
    (t) => t.tokenHash === tokenHash && t.jti === payload.jti
  );
  if (!stored) {
    throw ApiError.unauthorized(
      'Refresh token has been revoked',
      'REFRESH_TOKEN_REVOKED'
    );
  }
  if (stored.expiresAt.getTime() <= Date.now()) {
    throw ApiError.unauthorized('Refresh token has expired', 'TOKEN_EXPIRED');
  }

  user.refreshTokens = user.refreshTokens.filter((t) => t.tokenHash !== tokenHash);
  const tokens = await issueTokens(user);

  return sendSuccess(res, 200, { user: user.toPublicJSON(), ...tokens });
});

const logout = asyncHandler(async (req, res) => {
  const { refreshToken } = req.body;

  let payload;
  try {
    payload = verifyRefreshToken(refreshToken);
  } catch (err) {
    return sendSuccess(res, 200, { message: 'Logged out successfully' });
  }

  const user = await User.findById(payload.sub).select('+refreshTokens');
  if (user) {
    const tokenHash = hashToken(refreshToken);
    user.refreshTokens = (user.refreshTokens || []).filter(
      (t) => t.tokenHash !== tokenHash
    );
    await user.save({ validateBeforeSave: false });
  }

  return sendSuccess(res, 200, { message: 'Logged out successfully' });
});

const getMe = asyncHandler(async (req, res) =>
  sendSuccess(res, 200, { user: req.user.toPublicJSON() })
);

const listUsers = asyncHandler(async (req, res) => {
  const users = await User.find().sort({ createdAt: -1 }).limit(100);
  return sendSuccess(res, 200, {
    count: users.length,
    users: users.map((u) => u.toPublicJSON()),
  });
});

const changePassword = asyncHandler(async (req, res) => {
  const { currentPassword, newPassword } = req.body;

  const user = await User.findById(req.user._id).select('+password +refreshTokens');
  if (!user) throw ApiError.unauthorized('Not authenticated');

  if (!(await user.comparePassword(currentPassword))) {
    throw new ApiError(400, 'INVALID_CURRENT_PASSWORD', 'Your current password is not correct');
  }
  if (await user.comparePassword(newPassword)) {
    throw new ApiError(
      400,
      'PASSWORD_UNCHANGED',
      'Choose a new password that is different from your current one'
    );
  }

  user.password = newPassword;
  await user.save();

  const tokens = await issueTokens(user);
  return sendSuccess(res, 200, { user: user.toPublicJSON(), ...tokens });
});

const deleteAccount = asyncHandler(async (req, res) => {
  const user = await User.findById(req.user._id).select('+password');
  if (!user) throw ApiError.unauthorized('Not authenticated');

  if (!(await user.comparePassword(req.body.password))) {
    throw new ApiError(400, 'INVALID_CURRENT_PASSWORD', 'Your password is not correct');
  }

  const userId = user._id;
  const reports = await Report.find({ user: userId }).select('storageKey storageDriver').lean();

  const reportsResult = await Report.deleteMany({ user: userId });
  const profileResult = await Profile.deleteMany({ user: userId });
  await User.deleteOne({ _id: userId });

  let filesRemoved = 0;
  let filesFailed = 0;
  const drivers = new Set();
  for (const r of reports) {
    try {
      const storage = getStorage(r.storageDriver);
      drivers.add(r.storageDriver);
      if (await storage.remove(r.storageKey)) filesRemoved += 1;
    } catch (err) {
      filesFailed += 1;
    }
  }
  drivers.add(undefined);
  for (const driver of drivers) {
    try {
      await getStorage(driver).removeUserScope(userId.toString());
    } catch (err) {
    }
  }

  return sendSuccess(res, 200, {
    deleted: true,
    reportsDeleted: reportsResult.deletedCount,
    profileDeleted: profileResult.deletedCount > 0,
    filesRemoved,
    filesFailed,
  });
});

module.exports = {
  register,
  login,
  refresh,
  logout,
  getMe,
  listUsers,
  changePassword,
  deleteAccount,
  issueTokens,
};
