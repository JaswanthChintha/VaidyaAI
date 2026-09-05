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

// Stores are held explicitly so the test suite can reset counters between
// cases without reaching into express-rate-limit internals.
const authStore = new MemoryStore();
const loginStore = new MemoryStore();
const uploadStore = new MemoryStore();
const analysisStore = new MemoryStore();
const historyStore = new MemoryStore();

const baseOptions = {
  standardHeaders: 'draft-7',
  legacyHeaders: false,
  handler,
  // NOTE: the limiter keys on `req.ip`, which honours X-Forwarded-For only when
  // `trust proxy` is enabled (see src/app.js and config.trustProxy).
  skip: () => !config.rateLimit.enabled,
};

/** Applied to every /auth route. */
const authLimiter = rateLimit({
  ...baseOptions,
  store: authStore,
  windowMs: config.rateLimit.windowMs,
  max: config.rateLimit.generalMax,
});

/** Stricter limiter for credential-checking endpoints (brute-force defence). */
const loginLimiter = rateLimit({
  ...baseOptions,
  store: loginStore,
  windowMs: config.rateLimit.windowMs,
  max: config.rateLimit.loginMax,
  skipSuccessfulRequests: true,
});

/**
 * Module 3: report uploads, throttled SEPARATELY from the auth limiters.
 *
 * An upload buffers up to UPLOAD_MAX_BYTES in memory, hashes it and writes it
 * to disk, so its cost is orders of magnitude above a login attempt and it
 * needs its own, much smaller budget. Sharing the auth limiter would also mean
 * a burst of uploads could lock a user out of logging in, and vice versa.
 *
 * Like the others this keys on `req.ip`, which honours X-Forwarded-For only
 * when `trust proxy` is enabled - see config.trustProxy.
 */
const uploadLimiter = rateLimit({
  ...baseOptions,
  store: uploadStore,
  windowMs: config.upload.rateLimitWindowMs,
  max: config.upload.rateLimitMax,
});

/**
 * Report analysis. The most expensive endpoint in the application by a wide
 * margin - one call drives a multi-second OCR/LLM extraction in the Python
 * service and burns third-party quota - so it gets its own budget rather than
 * sharing the upload limiter. Uploading and analysing are separate costs, and
 * neither should be able to exhaust the other.
 *
 * Keys on `req.ip` like the others, and inherits the same TRUST_PROXY caveat.
 */
const analysisLimiter = rateLimit({
  ...baseOptions,
  store: analysisStore,
  windowMs: config.aiService.rateLimitWindowMs,
  max: config.aiService.rateLimitMax,
});

/**
 * Modules 28-30 and 32: the history endpoints (trends, comparison, progress
 * score, doctor summary).
 *
 * THEY GET A LIMITER, AND THE REASONING IS WORTH KEEPING because the obvious
 * answer is that they should not. `/dashboard`, `/report` and `/explanation`
 * are deliberately unlimited: they read one stored document, call nothing and
 * compute nothing. The history endpoints differ on both counts.
 *
 *   FAN-OUT. One request reads up to `HISTORY_MAX_REPORTS` reports and pulls
 *   the whole Module 6 verdict off each - the largest read this application
 *   performs outside a file download, and up to fifty times the cost of the
 *   single-document reads that are correctly unlimited.
 *
 *   OUTBOUND AMPLIFICATION. Each one makes an ai-service call. Without a
 *   budget, an authenticated caller turns one cheap inbound request into one
 *   outbound request against the Python service indefinitely - the same
 *   amplifier `/health/ai` is cached to avoid, but authenticated and with a
 *   far larger payload.
 *
 * THEY DO NOT SHARE `analysisLimiter`, and that is the other half of the
 * decision. That budget (20 per window) is sized for a multi-second LLM call
 * that burns third-party quota; these routes reach no model at all on either
 * side, so charging them against it would let drawing a trend screen lock a
 * patient out of analysing a report they just uploaded - and vice versa. Their
 * own, larger budget keeps the two costs independent, which is the same reason
 * `uploadLimiter` and `analysisLimiter` are already separate.
 *
 * Keys on `req.ip` like the others, and inherits the same TRUST_PROXY caveat.
 */
const historyLimiter = rateLimit({
  ...baseOptions,
  store: historyStore,
  windowMs: config.history.rateLimitWindowMs,
  max: config.history.rateLimitMax,
});

/** Test helper: clear all counters. */
async function resetRateLimiters() {
  await Promise.all([
    authStore.resetAll(),
    loginStore.resetAll(),
    uploadStore.resetAll(),
    analysisStore.resetAll(),
    historyStore.resetAll(),
  ]);
}

module.exports = {
  authLimiter,
  loginLimiter,
  uploadLimiter,
  analysisLimiter,
  historyLimiter,
  resetRateLimiters,
};
