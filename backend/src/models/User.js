'use strict';

const mongoose = require('mongoose');
const bcrypt = require('bcryptjs');
const config = require('../config/env');
const { ROLE_VALUES, ROLES } = require('../utils/roles');

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[a-zA-Z]{2,}$/;

/**
 * Hashed refresh tokens. One subdocument per active session, so a user can be
 * signed in on several devices and each session can be revoked independently.
 * The raw token is never persisted - only its SHA-256 digest.
 */
const refreshTokenSchema = new mongoose.Schema(
  {
    tokenHash: { type: String, required: true },
    jti: { type: String, required: true },
    expiresAt: { type: Date, required: true },
    createdAt: { type: Date, default: Date.now },
  },
  { _id: false }
);

const userSchema = new mongoose.Schema(
  {
    name: {
      type: String,
      required: [true, 'Name is required'],
      trim: true,
      minlength: [2, 'Name must be at least 2 characters'],
      maxlength: [100, 'Name must be at most 100 characters'],
    },
    email: {
      type: String,
      required: [true, 'Email is required'],
      unique: true,
      lowercase: true,
      trim: true,
      match: [EMAIL_REGEX, 'Please provide a valid email address'],
    },
    password: {
      type: String,
      required: [true, 'Password is required'],
      minlength: [8, 'Password must be at least 8 characters'],
      select: false,
      // bcrypt silently ignores every byte past 72, so a longer password would
      // authenticate against any string sharing its first 72 bytes. Enforced
      // HERE, at the model, rather than only in the route validator, so it
      // holds for every entry path: seed scripts, admin provisioning, tests,
      // and any future change-password / reset flow. Same reasoning as the
      // session purge in the pre('save') hook below.
      //
      // Mongoose runs document validation before user-defined pre('save')
      // hooks, so `value` here is the plaintext, not the bcrypt hash.
      validate: {
        validator(value) {
          return Buffer.byteLength(String(value), 'utf8') <= config.maxPasswordBytes;
        },
        // Measured in BYTES, not characters: one emoji is 4 bytes.
        message: `Password must be at most ${config.maxPasswordBytes} bytes long`,
      },
    },
    role: {
      type: String,
      enum: {
        values: ROLE_VALUES,
        message: `Role must be one of: ${ROLE_VALUES.join(', ')}`,
      },
      default: ROLES.PATIENT,
    },
    isActive: {
      type: Boolean,
      default: true,
    },
    passwordChangedAt: {
      type: Date,
      select: false,
    },
    refreshTokens: {
      type: [refreshTokenSchema],
      default: [],
      select: false,
    },
  },
  {
    timestamps: true,
    toJSON: {
      transform(doc, ret) {
        delete ret.password;
        delete ret.refreshTokens;
        delete ret.passwordChangedAt;
        delete ret.__v;
        return ret;
      },
    },
  }
);

userSchema.pre('save', async function hashPassword(next) {
  if (!this.isModified('password')) return next();
  this.password = await bcrypt.hash(this.password, config.bcryptCostFactor);
  if (!this.isNew) {
    // Backdated by a second so tokens issued right after a change are not
    // wrongly considered "issued before the password change".
    this.passwordChangedAt = new Date(Date.now() - 1000);
    // A password change ends every existing session: purge the stored refresh
    // token digests so no pre-change refresh token can mint a new access token.
    // Driven from the model layer so it applies to any future code path that
    // changes a password, not just one endpoint.
    this.refreshTokens = [];
  }
  return next();
});

/**
 * Constant-time-ish password comparison (delegated to bcrypt).
 * @param {string} candidatePassword
 * @returns {Promise<boolean>}
 */
userSchema.methods.comparePassword = function comparePassword(candidatePassword) {
  if (!this.password) {
    throw new Error('Password field was not selected on this document');
  }
  return bcrypt.compare(candidatePassword, this.password);
};

/**
 * Was the password changed after the given JWT `iat` (seconds since epoch)?
 * @param {number} tokenIssuedAtSeconds
 * @returns {boolean}
 */
userSchema.methods.passwordChangedAfter = function passwordChangedAfter(
  tokenIssuedAtSeconds
) {
  if (!this.passwordChangedAt) return false;
  const changedAtSeconds = Math.floor(this.passwordChangedAt.getTime() / 1000);
  return changedAtSeconds > tokenIssuedAtSeconds;
};

/** Public-safe representation (used inside the API success envelope). */
userSchema.methods.toPublicJSON = function toPublicJSON() {
  return {
    id: this._id.toString(),
    name: this.name,
    email: this.email,
    role: this.role,
    isActive: this.isActive,
    createdAt: this.createdAt,
    updatedAt: this.updatedAt,
  };
};

module.exports = mongoose.model('User', userSchema);
module.exports.EMAIL_REGEX = EMAIL_REGEX;
