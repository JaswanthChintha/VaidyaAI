'use strict';

const mongoose = require('mongoose');
const bcrypt = require('bcryptjs');
const config = require('../config/env');
const { ROLE_VALUES, ROLES } = require('../utils/roles');

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[a-zA-Z]{2,}$/;

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
      validate: {
        validator(value) {
          return Buffer.byteLength(String(value), 'utf8') <= config.maxPasswordBytes;
        },
        message: `Password is too long. Use at most ${config.maxPasswordBytes} characters (emoji and letters from some other alphabets count as more than one)`,
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
    this.passwordChangedAt = new Date(Date.now() - 1000);
    this.refreshTokens = [];
  }
  return next();
});

userSchema.methods.comparePassword = function comparePassword(candidatePassword) {
  if (!this.password) {
    throw new Error('Password field was not selected on this document');
  }
  return bcrypt.compare(candidatePassword, this.password);
};

userSchema.methods.passwordChangedAfter = function passwordChangedAfter(
  tokenIssuedAtSeconds
) {
  if (!this.passwordChangedAt) return false;
  const changedAtSeconds = Math.floor(this.passwordChangedAt.getTime() / 1000);
  return changedAtSeconds > tokenIssuedAtSeconds;
};

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
