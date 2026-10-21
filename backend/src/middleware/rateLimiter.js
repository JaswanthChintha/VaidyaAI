'use strict';

const { rateLimit, MemoryStore } = require('express-rate-limit');
const config = require('./../config/env');

const handler = (req, res) =>
  res.status(429).json({
    success: false,
    error: {
      code: 'RATE_LIMIT_EXCEEDED',
      message: 'Too many requests, please try again later',
    },
  });

const authStore = new MemoryStore();
const loginStore = new MemoryStore();
const uploadStore = new MemoryStore();
const analysisStore = new MemoryStore();
const historyStore = new MemoryStore();

const baseOptions = {
  standardHeaders: 'draft-7',
  legacyHeaders: false,
  handler,
  skip: () => !config.rateLimit.enabled,
};

const authLimiter = rateLimit({
  ...baseOptions,
  store: authStore,
  windowMs: config.rateLimit.windowMs,
  max: config.rateLimit.generalMax,
});

const loginLimiter = rateLimit({
  ...baseOptions,
  store: loginStore,
  windowMs: config.rateLimit.windowMs,
  max: config.rateLimit.loginMax,
  skipSuccessfulRequests: true,
});

const uploadLimiter = rateLimit({
  ...baseOptions,
  store: uploadStore,
  windowMs: config.upload.rateLimitWindowMs,
  max: config.upload.rateLimitMax,
});

const analysisLimiter = rateLimit({
  ...baseOptions,
  store: analysisStore,
  windowMs: config.aiService.rateLimitWindowMs,
  max: config.aiService.rateLimitMax,
});

const historyLimiter = rateLimit({
  ...baseOptions,
  store: historyStore,
  windowMs: config.history.rateLimitWindowMs,
  max: config.history.rateLimitMax,
});

const chatStore = new MemoryStore();
const chatLimiter = rateLimit({
  ...baseOptions,
  store: chatStore,
  windowMs: config.chat.rateLimitWindowMs,
  max: config.chat.rateLimitMax,
  keyGenerator: (req) => (req.user && req.user._id ? `user:${req.user._id}` : `ip:${req.ip}`),
});

async function resetRateLimiters() {
  await Promise.all([
    authStore.resetAll(),
    loginStore.resetAll(),
    uploadStore.resetAll(),
    analysisStore.resetAll(),
    historyStore.resetAll(),
    chatStore.resetAll(),
  ]);
}

module.exports = {
  authLimiter,
  loginLimiter,
  uploadLimiter,
  analysisLimiter,
  historyLimiter,
  chatLimiter,
  resetRateLimiters,
};
