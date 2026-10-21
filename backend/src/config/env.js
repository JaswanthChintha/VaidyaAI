'use strict';

const path = require('path');
const dotenv = require('dotenv');

dotenv.config({ path: path.resolve(__dirname, '..', '..', '.env') });

const NODE_ENV = process.env.NODE_ENV || 'development';
const isTest = NODE_ENV === 'test';
const isProduction = NODE_ENV === 'production';

const REQUIRED_VARS = ['MONGODB_URI', 'JWT_SECRET', 'JWT_REFRESH_SECRET'];

const TEST_DEFAULTS = {
  MONGODB_URI: 'mongodb://127.0.0.1:27017/vaidyaai_test',
  JWT_SECRET: 'test-access-secret-do-not-use-in-production-0123456789',
  JWT_REFRESH_SECRET: 'test-refresh-secret-do-not-use-in-production-0123456789',
};

const MIN_SECRET_LENGTH = 32;

if (isTest) {
  for (const [key, value] of Object.entries(TEST_DEFAULTS)) {
    if (!process.env[key]) process.env[key] = value;
  }
}

const missing = REQUIRED_VARS.filter((key) => !process.env[key]);
if (missing.length > 0) {
  throw new Error(
    `Missing required environment variable(s): ${missing.join(', ')}. ` +
      'Copy .env.example to .env and fill in the values.'
  );
}

if (process.env.JWT_SECRET === process.env.JWT_REFRESH_SECRET) {
  throw new Error(
    'JWT_SECRET and JWT_REFRESH_SECRET must be different values. Sharing one ' +
      'secret would let a refresh token be presented as an access token.'
  );
}
for (const key of ['JWT_SECRET', 'JWT_REFRESH_SECRET']) {
  if (process.env[key].length < MIN_SECRET_LENGTH) {
    throw new Error(
      `${key} must be at least ${MIN_SECRET_LENGTH} characters. Generate one with: ` +
        'node -e "console.log(require(\'crypto\').randomBytes(48).toString(\'hex\'))"'
    );
  }
}

const toInt = (value, fallback) => {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const toBool = (value, fallback) => {
  if (value === undefined || value === '') return fallback;
  return ['1', 'true', 'yes', 'on'].includes(String(value).trim().toLowerCase());
};

function parseTrustProxy(raw) {
  if (raw === undefined || raw === null || String(raw).trim() === '') return false;
  const value = String(raw).trim();
  const lowered = value.toLowerCase();
  if (['false', '0', 'no', 'off'].includes(lowered)) return false;
  if (lowered === 'true') return true;
  if (/^\d+$/.test(value)) return Number.parseInt(value, 10);
  return value;
}

function parseDnsServers(raw) {
  if (raw === undefined || raw === null || String(raw).trim() === '') return [];
  const { isIP } = require('net');
  const servers = String(raw)
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  const bad = servers.filter((s) => isIP(s) === 0);
  if (bad.length) {
    throw new Error(
      `DNS_SERVERS must be IP addresses separated by commas (e.g. 8.8.8.8,1.1.1.1); ` +
        `not an IP address: ${bad.join(', ')}`
    );
  }
  return servers;
}

const STAGE_TIMEOUT_DEFAULT = toInt(process.env.AI_SERVICE_STAGE_TIMEOUT_MS, 30 * 1000);

const config = {
  env: NODE_ENV,
  isTest,
  isProduction,
  port: toInt(process.env.PORT, 5000),
  apiPrefix: process.env.API_PREFIX || '/api/v1',
  mongoUri: process.env.MONGODB_URI,
  chat: {
    rateLimitMax: toInt(process.env.CHAT_RATE_LIMIT_MAX, 20),
    rateLimitWindowMs: toInt(process.env.CHAT_RATE_LIMIT_WINDOW_MS, 60 * 60 * 1000),
  },

  dnsServers: parseDnsServers(process.env.DNS_SERVERS),

  trustProxy: parseTrustProxy(process.env.TRUST_PROXY),

  frontendDist: process.env.FRONTEND_DIST
    ? path.resolve(path.join(__dirname, '..', '..'), process.env.FRONTEND_DIST)
    : null,

  jwt: {
    accessSecret: process.env.JWT_SECRET,
    accessExpiresIn: process.env.JWT_EXPIRES_IN || '15m',
    refreshSecret: process.env.JWT_REFRESH_SECRET,
    refreshExpiresIn: process.env.JWT_REFRESH_EXPIRES_IN || '7d',
    issuer: process.env.JWT_ISSUER || 'vaidyaai',
    audience: process.env.JWT_AUDIENCE || 'vaidyaai-clients',
  },

  bcryptCostFactor: toInt(process.env.BCRYPT_COST_FACTOR, 12),

  cors: {
    origin: (process.env.CORS_ORIGIN || 'http://localhost:3000')
      .split(',')
      .map((o) => o.trim())
      .filter(Boolean),
  },

  rateLimit: {
    windowMs: toInt(process.env.RATE_LIMIT_WINDOW_MS, 15 * 60 * 1000),
    generalMax: toInt(process.env.RATE_LIMIT_MAX, 100),
    loginMax: toInt(process.env.LOGIN_RATE_LIMIT_MAX, 5),
    enabled: !isTest || toBool(process.env.ENABLE_RATE_LIMIT, false),
  },

  maxPasswordBytes: 72,

  upload: {
    driver: (process.env.STORAGE_DRIVER || 'local').trim().toLowerCase(),

    root: path.resolve(
      path.join(__dirname, '..', '..'),
      process.env.UPLOAD_ROOT || path.join('storage', 'uploads')
    ),

    maxBytes: toInt(process.env.UPLOAD_MAX_BYTES, 10 * 1024 * 1024),

    rateLimitMax: toInt(process.env.UPLOAD_RATE_LIMIT_MAX, 20),
    rateLimitWindowMs: toInt(process.env.UPLOAD_RATE_LIMIT_WINDOW_MS, 15 * 60 * 1000),
  },

  aiService: {
    url: (process.env.AI_SERVICE_URL || '').trim().replace(/\/+$/, ''),
    apiKey: process.env.AI_SERVICE_API_KEY || '',

    timeoutMs: toInt(process.env.AI_SERVICE_TIMEOUT_MS, 5 * 60 * 1000),

    healthTimeoutMs: toInt(process.env.AI_SERVICE_HEALTH_TIMEOUT_MS, 3000),

    stageTimeoutMs: STAGE_TIMEOUT_DEFAULT,
    validateTimeoutMs: toInt(process.env.AI_SERVICE_VALIDATE_TIMEOUT_MS, STAGE_TIMEOUT_DEFAULT),
    rulesTimeoutMs: toInt(process.env.AI_SERVICE_RULES_TIMEOUT_MS, STAGE_TIMEOUT_DEFAULT),
    mlTimeoutMs: toInt(process.env.AI_SERVICE_ML_TIMEOUT_MS, STAGE_TIMEOUT_DEFAULT),

    reportTimeoutMs: toInt(process.env.AI_SERVICE_REPORT_TIMEOUT_MS, STAGE_TIMEOUT_DEFAULT),

    explainTimeoutMs: toInt(process.env.AI_SERVICE_EXPLAIN_TIMEOUT_MS, 120 * 1000),

    guidanceTimeoutMs: toInt(process.env.AI_SERVICE_GUIDANCE_TIMEOUT_MS, STAGE_TIMEOUT_DEFAULT),

    glossaryTimeoutMs: toInt(process.env.AI_SERVICE_GLOSSARY_TIMEOUT_MS, 180 * 1000),

    findingContextTimeoutMs: toInt(
      process.env.AI_SERVICE_FINDING_CONTEXT_TIMEOUT_MS,
      180 * 1000
    ),

    labPolarityTimeoutMs: toInt(
      process.env.AI_SERVICE_LAB_POLARITY_TIMEOUT_MS,
      180 * 1000
    ),

    labNameMatchTimeoutMs: toInt(
      process.env.AI_SERVICE_LAB_NAME_MATCH_TIMEOUT_MS,
      60 * 1000
    ),

    timelineTimeoutMs: toInt(process.env.AI_SERVICE_TIMELINE_TIMEOUT_MS, STAGE_TIMEOUT_DEFAULT),
    comparisonTimeoutMs: toInt(
      process.env.AI_SERVICE_COMPARISON_TIMEOUT_MS,
      STAGE_TIMEOUT_DEFAULT
    ),
    progressTimeoutMs: toInt(process.env.AI_SERVICE_PROGRESS_TIMEOUT_MS, STAGE_TIMEOUT_DEFAULT),

    doctorSummaryTimeoutMs: toInt(
      process.env.AI_SERVICE_DOCTOR_SUMMARY_TIMEOUT_MS,
      STAGE_TIMEOUT_DEFAULT
    ),

    populationTimeoutMs: toInt(
      process.env.AI_SERVICE_POPULATION_TIMEOUT_MS,
      STAGE_TIMEOUT_DEFAULT
    ),

    maxExplanations: Math.min(24, Math.max(0, toInt(process.env.AI_SERVICE_MAX_EXPLANATIONS, 24))),

    retries: toInt(process.env.AI_SERVICE_RETRIES, 1),
    retryDelayMs: toInt(process.env.AI_SERVICE_RETRY_DELAY_MS, 500),

    wakeWaitMs: toInt(process.env.AI_SERVICE_WAKE_WAIT_MS, 0),
    chatTimeoutMs: toInt(process.env.AI_SERVICE_CHAT_TIMEOUT_MS, 150000),
    wakeIntervalMs: toInt(process.env.AI_SERVICE_WAKE_INTERVAL_MS, 5000),
    chatWakeWaitMs: Math.min(
      2 * 60 * 1000,
      toInt(process.env.AI_SERVICE_WAKE_WAIT_MS, 0)
    ),

    lockTtlMs: toInt(process.env.AI_SERVICE_LOCK_TTL_MS, 10 * 60 * 1000),

    rateLimitMax: toInt(process.env.ANALYSIS_RATE_LIMIT_MAX, 20),
    rateLimitWindowMs: toInt(process.env.ANALYSIS_RATE_LIMIT_WINDOW_MS, 15 * 60 * 1000),
  },

  history: {
    maxReports: Math.min(500, Math.max(2, toInt(process.env.HISTORY_MAX_REPORTS, 50))),

    rateLimitMax: toInt(process.env.HISTORY_RATE_LIMIT_MAX, 60),
    rateLimitWindowMs: toInt(process.env.HISTORY_RATE_LIMIT_WINDOW_MS, 15 * 60 * 1000),
  },
};

if (config.aiService.url && !config.aiService.apiKey) {
  throw new Error(
    'AI_SERVICE_URL is set but AI_SERVICE_API_KEY is empty. The ai-service ' +
      'requires the X-Service-Key header; refusing to start rather than send ' +
      'medical documents unauthenticated. Set AI_SERVICE_API_KEY, or unset ' +
      'AI_SERVICE_URL to disable the analysis pipeline.'
  );
}
if (config.aiService.url && config.aiService.apiKey.length < MIN_SECRET_LENGTH) {
  throw new Error(
    `AI_SERVICE_API_KEY must be at least ${MIN_SECRET_LENGTH} characters - the ` +
      'ai-service enforces the same minimum and refuses to start below it. ' +
      'Generate one with: node -e "console.log(require(\'crypto\').randomBytes(32).toString(\'hex\'))"'
  );
}
if (config.aiService.url && !/^https?:\/\/[^\s]+$/i.test(config.aiService.url)) {
  throw new Error(
    `AI_SERVICE_URL must be an absolute http(s) URL (got "${config.aiService.url}")`
  );
}

module.exports = config;
module.exports.parseTrustProxy = parseTrustProxy;
module.exports.parseDnsServers = parseDnsServers;
