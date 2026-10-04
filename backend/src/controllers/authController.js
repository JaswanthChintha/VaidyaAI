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

/** Maximum number of concurrent refresh-token sessions kept per user. */
const MAX_SESSIONS = 5;

/**
 * Issue an access/refresh pair and persist the hashed refresh token on the user.
 * @param {import('mongoose').Document} user
 */
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

  // Keep only the most recent sessions.
  user.refreshTokens = existing.slice(-MAX_SESSIONS);
  await user.save({ validateBeforeSave: false });

  return { accessToken, refreshToken };
}

/**
 * POST /api/v1/auth/register
 * Creates a patient account and returns the user plus a fresh token pair.
 */
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
    // Privilege escalation guard: self-registration is always a patient.
    role: ROLES.PATIENT,
  });

  // refreshTokens is select:false, but the freshly created doc already has it.
  const tokens = await issueTokens(user);

  return sendSuccess(res, 201, { user: user.toPublicJSON(), ...tokens });
});

/**
 * POST /api/v1/auth/login
 */
const login = asyncHandler(async (req, res) => {
  const { email, password } = req.body;

  const user = await User.findOne({ email }).select('+password +refreshTokens');

  // Same generic message + same code path whether the email or the password is
  // wrong, so the endpoint cannot be used to enumerate registered accounts.
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

/**
 * POST /api/v1/auth/refresh
 * Verifies the refresh token, checks it against the stored hash, then rotates it.
 */
const refresh = asyncHandler(async (req, res) => {
  const { refreshToken } = req.body;

  const payload = verifyRefreshToken(refreshToken); // 401 on invalid/expired

  const user = await User.findById(payload.sub).select('+refreshTokens +passwordChangedAt');
  if (!user || !user.isActive) {
    throw ApiError.unauthorized('Invalid refresh token', 'INVALID_REFRESH_TOKEN');
  }

  // A refresh token minted before the password changed must not survive the
  // change. The stored digests are purged by the model's pre-save hook too;
  // this is the belt to that braces.
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
    // Either already rotated/revoked, or a forgery. Treat as unauthorized.
    throw ApiError.unauthorized(
      'Refresh token has been revoked',
      'REFRESH_TOKEN_REVOKED'
    );
  }
  if (stored.expiresAt.getTime() <= Date.now()) {
    throw ApiError.unauthorized('Refresh token has expired', 'TOKEN_EXPIRED');
  }

  // Rotation: the presented token is invalidated before a new one is issued.
  user.refreshTokens = user.refreshTokens.filter((t) => t.tokenHash !== tokenHash);
  const tokens = await issueTokens(user);

  return sendSuccess(res, 200, { user: user.toPublicJSON(), ...tokens });
});

/**
 * POST /api/v1/auth/logout
 * Revokes the supplied refresh token (this session only).
 */
const logout = asyncHandler(async (req, res) => {
  const { refreshToken } = req.body;

  let payload;
  try {
    payload = verifyRefreshToken(refreshToken);
  } catch (err) {
    // Logout is idempotent - an unusable token is already "logged out".
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

/**
 * GET /api/v1/auth/me  (protected)
 */
const getMe = asyncHandler(async (req, res) =>
  sendSuccess(res, 200, { user: req.user.toPublicJSON() })
);

/**
 * GET /api/v1/auth/admin/users  (protected + admin only)
 * Present so the authorization half of Module 1 is exercised by a real route.
 */
const listUsers = asyncHandler(async (req, res) => {
  const users = await User.find().sort({ createdAt: -1 }).limit(100);
  return sendSuccess(res, 200, {
    count: users.length,
    users: users.map((u) => u.toPublicJSON()),
  });
});

/**
 * POST /api/v1/auth/change-password  (protected)
 *
 * The current password is re-checked even though the caller holds a valid
 * access token: a session left open on a shared computer must not be enough
 * to take the account over.
 *
 * Saving a new password runs the model's pre-save hook, which stamps
 * `passwordChangedAt` and EMPTIES `refreshTokens` -- every other device is
 * signed out, and every access token issued before now stops working at
 * `protect`. This device then gets a fresh pair, so the person who just
 * changed it stays signed in.
 */
const changePassword = asyncHandler(async (req, res) => {
  const { currentPassword, newPassword } = req.body;

  const user = await User.findById(req.user._id).select('+password +refreshTokens');
  if (!user) throw ApiError.unauthorized('Not authenticated');

  if (!(await user.comparePassword(currentPassword))) {
    // 400, not 401: the client treats a 401 as an expired session and would
    // refresh and RESEND the request -- a second guess at the password.
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

/**
 * DELETE /api/v1/auth/me  (protected)
 *
 * PERMANENT. The account, its profile, every report row (and with it every
 * stored analysis) and every uploaded file are removed. Nothing is archived.
 *
 * Re-checks the password for the same reason as `changePassword`.
 *
 * ORDER: rows first, files second -- the same choice `deleteReport` makes and
 * for the same reason. If removing a file fails, what is left is a file no
 * record points at (invisible, reclaimable), never a record pointing at a
 * missing file. Everything is scoped to the caller's own id; there is no
 * parameter that could name anybody else.
 */
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

  // Files: each report's own file, then the whole user folder for every driver
  // in use, which also catches anything a row no longer points at.
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
  drivers.add(undefined); // the configured default driver
  for (const driver of drivers) {
    try {
      await getStorage(driver).removeUserScope(userId.toString());
    } catch (err) {
      // Best effort; the rows are already gone.
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
