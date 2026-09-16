'use strict';

const path = require('path');
const dotenv = require('dotenv');

// Load .env from the backend root (one level above src/config -> src -> backend)
dotenv.config({ path: path.resolve(__dirname, '..', '..', '.env') });

const NODE_ENV = process.env.NODE_ENV || 'development';
const isTest = NODE_ENV === 'test';
const isProduction = NODE_ENV === 'production';

/**
 * Variables that must be present outside of the test environment.
 * In tests, safe throwaway defaults are used so the suite can run without a .env file.
 */
const REQUIRED_VARS = ['MONGODB_URI', 'JWT_SECRET', 'JWT_REFRESH_SECRET'];

const TEST_DEFAULTS = {
  MONGODB_URI: 'mongodb://127.0.0.1:27017/vaidyaai_test',
  JWT_SECRET: 'test-access-secret-do-not-use-in-production-0123456789',
  JWT_REFRESH_SECRET: 'test-refresh-secret-do-not-use-in-production-0123456789',
};

/** Minimum acceptable length for a signing secret. */
const MIN_SECRET_LENGTH = 32;

if (isTest) {
  for (const [key, value] of Object.entries(TEST_DEFAULTS)) {
    if (!process.env[key]) process.env[key] = value;
  }
}

const missing = REQUIRED_VARS.filter((key) => !process.env[key]);
if (missing.length > 0) {
  // Fail fast: never fall back to a hard-coded secret outside tests.
  throw new Error(
    `Missing required environment variable(s): ${missing.join(', ')}. ` +
      'Copy .env.example to .env and fill in the values.'
  );
}

// --- Secret strength / distinctness (README claims this; enforce it) --------
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

/**
 * Parse the TRUST_PROXY setting for `app.set('trust proxy', ...)`.
 *
 * SECURITY: this controls whether Express derives `req.ip` from the
 * client-supplied `X-Forwarded-For` header, and `req.ip` is the rate limiter's
 * key. Trusting a proxy that is not actually in front of the app lets any
 * caller rotate that header and bypass rate limiting entirely. The default is
 * therefore `false` (trust nobody); set it to the real number of proxy hops
 * only when a load balancer genuinely fronts the service.
 *
 * Accepted values: unset/false/0 -> false; true -> true (NOT recommended);
 * an integer -> that many hops; anything else -> passed through verbatim so
 * Express' own syntax (`loopback`, a CIDR, a comma-separated IP list) works.
 *
 * @param {string|undefined} raw
 * @returns {boolean|number|string}
 */
function parseTrustProxy(raw) {
  if (raw === undefined || raw === null || String(raw).trim() === '') return false;
  const value = String(raw).trim();
  const lowered = value.toLowerCase();
  if (['false', '0', 'no', 'off'].includes(lowered)) return false;
  if (lowered === 'true') return true;
  if (/^\d+$/.test(value)) return Number.parseInt(value, 10);
  return value;
}

/**
 * Default timeout for every ai-service stage EXCEPT extraction and health.
 * See `aiService.stageTimeoutMs` below for why the extraction timeout must not
 * be reused for them.
 */
const STAGE_TIMEOUT_DEFAULT = toInt(process.env.AI_SERVICE_STAGE_TIMEOUT_MS, 30 * 1000);

const config = {
  env: NODE_ENV,
  isTest,
  isProduction,
  port: toInt(process.env.PORT, 5000),
  apiPrefix: process.env.API_PREFIX || '/api/v1',
  mongoUri: process.env.MONGODB_URI,

  // See parseTrustProxy above. Default: trust no proxy.
  trustProxy: parseTrustProxy(process.env.TRUST_PROXY),

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
    // Rate limiting is off by default under NODE_ENV=test so the integration
    // suite is not throttled; ENABLE_RATE_LIMIT=true turns it back on for the
    // dedicated rate-limiting tests.
    enabled: !isTest || toBool(process.env.ENABLE_RATE_LIMIT, false),
  },

  // Maximum password length in BYTES. bcrypt silently ignores input past 72
  // bytes, so anything longer must be rejected rather than truncated.
  maxPasswordBytes: 72,

  // --- Module 3: report upload / storage -----------------------------------
  upload: {
    // Which storage adapter backs report files. Only `local` exists today; the
    // adapter interface (src/storage/StorageAdapter.js) is the seam where a
    // cloud driver would be added later without touching the controller.
    driver: (process.env.STORAGE_DRIVER || 'local').trim().toLowerCase(),

    // Absolute directory that holds uploaded report files. It MUST NOT be
    // inside any directory served statically - nothing in this app serves
    // static files, and downloads go through an owner-scoped, authenticated
    // route that forces `Content-Disposition: attachment`.
    // A relative UPLOAD_ROOT is resolved against the backend directory, not
    // process.cwd(), so `npm start` from a different working directory cannot
    // silently scatter medical files into an unexpected place.
    root: path.resolve(
      path.join(__dirname, '..', '..'),
      process.env.UPLOAD_ROOT || path.join('storage', 'uploads')
    ),

    // Hard cap on a single uploaded file, in bytes. Enforced by multer's own
    // limit (which aborts the stream) and re-checked after buffering.
    maxBytes: toInt(process.env.UPLOAD_MAX_BYTES, 10 * 1024 * 1024),

    // Uploads are throttled separately from the auth limiter: writing files is
    // far more expensive than a login attempt.
    rateLimitMax: toInt(process.env.UPLOAD_RATE_LIMIT_MAX, 20),
    rateLimitWindowMs: toInt(process.env.UPLOAD_RATE_LIMIT_WINDOW_MS, 15 * 60 * 1000),
  },

  // --- ai-service (Modules 4 + 5, the Python/FastAPI service) --------------
  //
  // The backend orchestrates the pipeline; the Python service performs OCR
  // extraction and feature engineering. Both calls are authenticated with a
  // shared service key sent as `X-Service-Key`.
  //
  // FAIL-CLOSED, matching the Python side: a URL configured WITHOUT a key is a
  // startup error (see the check below), never "call it anonymously". Neither
  // configured at all is a supported state - Modules 1-3 work exactly as
  // before and the analysis endpoints answer 503.
  aiService: {
    url: (process.env.AI_SERVICE_URL || '').trim().replace(/\/+$/, ''),
    apiKey: process.env.AI_SERVICE_API_KEY || '',

    // TIMEOUT. A happy-path extraction was measured at ~20 s, but that is the
    // best case: the ai-service's WORST case with its shipped defaults is
    // ~61 minutes - (GEMINI_MAX_RETRIES x GEMINI_TIMEOUT_SECONDS + backoff) x
    // MAX_PAGE_COUNT = (3 x 120 + 3.75) x 10 = 3637.5 s, exposed there as
    // `Settings.worst_case_extraction_seconds`.
    //
    // A 61-minute client timeout is not a real option (it would pin an HTTP
    // connection and a Node handle for an hour), so the default is 5 minutes:
    // comfortably above any single-page or few-page report, and short enough
    // that a pathological document fails rather than hangs. It MUST exceed
    // whatever the deployed ai-service is actually configured for - the Python
    // README recommends GEMINI_TIMEOUT_SECONDS=45 / GEMINI_MAX_RETRIES=2
    // (~15 min worst case), so the two have to be tuned together. See the
    // README's known-limitations section.
    timeoutMs: toInt(process.env.AI_SERVICE_TIMEOUT_MS, 5 * 60 * 1000),

    // The health probe must never inherit the extraction timeout: /health is
    // meant to answer immediately or not at all.
    healthTimeoutMs: toInt(process.env.AI_SERVICE_HEALTH_TIMEOUT_MS, 3000),

    // THE DOWNSTREAM STAGES MUST NOT INHERIT THE EXTRACTION TIMEOUT.
    //
    // Extraction is the only slow stage - it makes one or more Gemini calls per
    // page, hence the 5-minute default above. Validation (Module 6), the
    // clinical rule engine (Module 8) and the ML predictors (Modules 9/10) are
    // pure computation over an already-extracted feature set and return in
    // milliseconds; the models are loaded once and cached. Giving them five
    // minutes would mean a wedged ai-service pinned three more Node handles for
    // five minutes each after the expensive stage had already succeeded.
    //
    // 30 s is ~3 orders of magnitude above the measured cost of any of them,
    // and each stage can still be tuned individually.
    stageTimeoutMs: STAGE_TIMEOUT_DEFAULT,
    validateTimeoutMs: toInt(process.env.AI_SERVICE_VALIDATE_TIMEOUT_MS, STAGE_TIMEOUT_DEFAULT),
    rulesTimeoutMs: toInt(process.env.AI_SERVICE_RULES_TIMEOUT_MS, STAGE_TIMEOUT_DEFAULT),
    mlTimeoutMs: toInt(process.env.AI_SERVICE_ML_TIMEOUT_MS, STAGE_TIMEOUT_DEFAULT),

    // Modules 17-20 (the clinical report). It is the heaviest of the fast
    // stages - it runs the decision chain in-process and then builds the whole
    // report - but it is still pure computation over an already-extracted
    // feature set, so it belongs with the fast stages and NOT on the extraction
    // budget. Separately tunable for the same reason the other three are.
    reportTimeoutMs: toInt(process.env.AI_SERVICE_REPORT_TIMEOUT_MS, STAGE_TIMEOUT_DEFAULT),

    // MODULE 23 (the patient-friendly explanation) IS NEITHER A FAST STAGE NOR
    // AN EXTRACTION, AND MUST NOT INHERIT EITHER BUDGET.
    //
    // It is the only stage after extraction that makes a live LLM round trip,
    // so the 30 s fast-stage default is too tight: `explain_report` explains up
    // to `maxExplanations` findings and each one is its own generation, a
    // safety-rejected generation is retried once with a different prompt, and
    // `gemini-3.6-flash` is a THINKING model - its reasoning tokens are drawn
    // from `max_output_tokens` before a single word of prose is emitted, which
    // is why the ai-service had to raise its cap to 4096. None of that is
    // instant.
    //
    // Equally it must not inherit the 5-minute extraction budget. Extraction is
    // long because it makes a Gemini call PER PAGE of an arbitrarily long scan;
    // this stage's work is bounded by `maxExplanations`, and it runs AFTER the
    // expensive stage has already succeeded - pinning a Node handle for five
    // more minutes at that point would risk the whole analyze request for a
    // stage whose absence is a legitimate, already-modelled outcome.
    //
    // 120 s: roughly 6 generations plus a retry at the measured live cost of a
    // thinking-model call, with headroom.
    explainTimeoutMs: toInt(process.env.AI_SERVICE_EXPLAIN_TIMEOUT_MS, 120 * 1000),

    // MODULE 26 (educational lifestyle guidance) CALLS NO MODEL AT ALL. Its
    // route declares no LLM dependency on the Python side - it resolves
    // reviewed catalogue text by code - so it belongs with the fast stages and
    // deliberately does NOT share the explanation budget above. A wedged
    // guidance call must not hold a handle for two minutes for work that is a
    // dictionary lookup.
    guidanceTimeoutMs: toInt(process.env.AI_SERVICE_GUIDANCE_TIMEOUT_MS, STAGE_TIMEOUT_DEFAULT),

    // MODULE 25's GLOSSARY MAKES ONE MODEL CALL PER TEST, and it used to
    // borrow `guidanceTimeoutMs` -- the budget above, whose whole argument is
    // that its stage "CALLS NO MODEL AT ALL". That was wrong from the start
    // and survived only because the glossary was capped at eight tests and
    // eight calls happened to fit inside thirty seconds.
    //
    // It broke the moment the cap rose to 24 to describe every test on a
    // report: the ai-service generated all seventeen descriptions for
    // Test 3.pdf in about twenty-five seconds, the backend gave up at thirty,
    // and every one of them was discarded. The log is unambiguous about who
    // did what -- ai-service `generated: 16, cached: 1`, backend
    // `outcome=failure code=ECONNABORTED`.
    //
    // Sized from that measurement, not guessed: ~1.2s per description at the
    // fast model, and several times that when the daily quota pushes the chain
    // onto a slower fallback. 24 x 4s + safety validation, rounded up.
    glossaryTimeoutMs: toInt(process.env.AI_SERVICE_GLOSSARY_TIMEOUT_MS, 180 * 1000),

    // MODULES 28, 29, 30 AND 32 (trends, comparison, progress score, doctor
    // summary) ARE MODEL-FREE AND OFFLINE ON THE PYTHON SIDE - they are pure
    // computation over feature snapshots the backend supplies, so they belong
    // with the fast stages and must NOT inherit the extraction budget or the
    // explanation budget.
    //
    // They are given their OWN names rather than reusing `stageTimeoutMs`
    // directly for the reason the file already states for validate/rules/ml:
    // each stage has to be tunable on its own. They differ from those three in
    // one respect that matters for tuning - their cost scales with the number
    // of reports in the request (up to `history.maxReports` snapshots, each a
    // whole Module 6 verdict), not with one report - so if any fast stage ever
    // needs a longer budget it will be one of these, and it must be raisable
    // without also loosening the single-report stages.
    timelineTimeoutMs: toInt(process.env.AI_SERVICE_TIMELINE_TIMEOUT_MS, STAGE_TIMEOUT_DEFAULT),
    comparisonTimeoutMs: toInt(
      process.env.AI_SERVICE_COMPARISON_TIMEOUT_MS,
      STAGE_TIMEOUT_DEFAULT
    ),
    progressTimeoutMs: toInt(process.env.AI_SERVICE_PROGRESS_TIMEOUT_MS, STAGE_TIMEOUT_DEFAULT),

    // Module 32 assembles a clinician document out of a clinical report PLUS
    // the trend and comparison sections, so it does the work of Modules 28 and
    // 29 in addition to its own. Still model-free, still bounded by the same
    // snapshot count - but it is the heaviest of the four, hence its own knob.
    doctorSummaryTimeoutMs: toInt(
      process.env.AI_SERVICE_DOCTOR_SUMMARY_TIMEOUT_MS,
      STAGE_TIMEOUT_DEFAULT
    ),

    // MODULE 31 (population context and percentiles) IS MODEL-FREE AND OFFLINE
    // TOO, and is the cheapest call in this list: the seven NHANES distribution
    // tables are loaded once at import on the Python side, and one request is a
    // bisect against at most fourteen of them. It belongs with the fast stages.
    //
    // It gets its OWN name rather than sharing `stageTimeoutMs` or borrowing one
    // of the four above, for the rule this file already states twice: a stage
    // that cannot be tuned on its own is a stage that gets tuned by accident
    // when a neighbour needs a longer budget. It differs from the four
    // longitudinal calls in that its cost is bounded by ONE report's validated
    // feature set rather than by `history.maxReports` snapshots, so if those
    // ever need raising, this must not be raised with them.
    populationTimeoutMs: toInt(
      process.env.AI_SERVICE_POPULATION_TIMEOUT_MS,
      STAGE_TIMEOUT_DEFAULT
    ),

    // How many findings Module 23 may explain in one run. EVERY ONE IS A MODEL
    // CALL, so this is a cost and latency control, not a display preference.
    // The ai-service caps the field at its own `DEFAULT_MAX_EXPLANATIONS` and
    // 422s anything higher, so it is clamped here rather than sent and
    // rejected at the far end.
    //
    // RAISED 6 -> 10 (2026-09-11). At 6 an ordinary eight-value report left two
    // results unexplained, chosen by row order. **THIS NUMBER MUST NOT EXCEED
    // THE ai-service's OWN `DEFAULT_MAX_EXPLANATIONS`** -- the two are separate
    // constants in separate languages and nothing links them, so raising this
    // one alone turns every analyse into a 422.
    maxExplanations: Math.min(10, Math.max(0, toInt(process.env.AI_SERVICE_MAX_EXPLANATIONS, 10))),

    // Extra attempts after the first, for TRANSIENT failures only (connection
    // refused/reset, timeout, 5xx). A 401 or a 422 is deterministic and is
    // never retried - see services/aiServiceClient.js.
    retries: toInt(process.env.AI_SERVICE_RETRIES, 1),
    retryDelayMs: toInt(process.env.AI_SERVICE_RETRY_DELAY_MS, 500),

    // How long a report may sit in `processing` before another analyze call is
    // allowed to take the lock over. Covers a crash mid-analysis; without it a
    // report would be stuck in `processing` forever.
    lockTtlMs: toInt(process.env.AI_SERVICE_LOCK_TTL_MS, 10 * 60 * 1000),

    // Analysis is the most expensive endpoint in the app (a multi-second LLM
    // call per request), so it gets its own budget rather than sharing the
    // upload limiter.
    rateLimitMax: toInt(process.env.ANALYSIS_RATE_LIMIT_MAX, 20),
    rateLimitWindowMs: toInt(process.env.ANALYSIS_RATE_LIMIT_WINDOW_MS, 15 * 60 * 1000),
  },

  // --- Modules 28-30 + 32: the patient's report history --------------------
  //
  // These endpoints differ from every other read in the app in one way: one
  // request touches MANY reports. That makes two numbers worth stating in
  // config rather than burying in a service.
  history: {
    // HOW MANY REPORTS ONE CALL MAY ASSEMBLE.
    //
    // Each included report contributes its whole Module 6 verdict
    // (`featureValidation`) - a `select: false` payload holding every valid,
    // questionable and rejected feature with its provenance. Fifty of them is
    // already a substantial body to pull out of Mongo, serialise, and send over
    // HTTP, and the clinical value of an older reading falls away long before
    // the fiftieth: a trend is read off the recent series.
    //
    // The window is the MOST RECENT `maxReports`, never the oldest - see
    // historyService. The ai-service's own hard cap is 500 (`max_length` on
    // `TimelineTrendsRequest.reports`), so this stays comfortably inside it and
    // a raised value here must stay inside it too.
    maxReports: Math.min(500, Math.max(2, toInt(process.env.HISTORY_MAX_REPORTS, 50))),

    // History endpoints get their own rate-limit budget - see
    // middleware/rateLimiter.js for why it is neither the analysis budget nor
    // no budget at all.
    rateLimitMax: toInt(process.env.HISTORY_RATE_LIMIT_MAX, 60),
    rateLimitWindowMs: toInt(process.env.HISTORY_RATE_LIMIT_WINDOW_MS, 15 * 60 * 1000),
  },
};

// A configured ai-service URL with no service key would mean sending medical
// documents to an unauthenticated endpoint. Refuse to start instead - the same
// fail-closed rule the Python service applies to the identical variable.
if (config.aiService.url && !config.aiService.apiKey) {
  throw new Error(
    'AI_SERVICE_URL is set but AI_SERVICE_API_KEY is empty. The ai-service ' +
      'requires the X-Service-Key header; refusing to start rather than send ' +
      'medical documents unauthenticated. Set AI_SERVICE_API_KEY, or unset ' +
      'AI_SERVICE_URL to disable the analysis pipeline.'
  );
}
// The ai-service refuses to start on a key shorter than 32 characters, and its
// 401 is byte-identical for a missing header, a wrong key, an empty key and a
// whitespace key - so a too-short key here would surface only as an
// indistinguishable 401 at the first analysis, long after deploy. Enforce the
// same minimum on this side, at startup, where the message can say what is
// wrong. Same reasoning as MIN_SECRET_LENGTH for the JWT secrets.
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
