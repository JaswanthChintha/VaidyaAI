'use strict';

const crypto = require('crypto');
const axios = require('axios');

const config = require('../config/env');
const ApiError = require('../utils/ApiError');

/**
 * Client for `ai-service` - the Python/FastAPI service that owns Module 4 (OCR
 * and medical text extraction) and Module 5 (medical feature engineering).
 *
 * This file is the ONLY place in the backend that knows the Python service
 * exists. Everything above it deals in `ApiError`s from the existing
 * vocabulary; everything below it is HTTP.
 *
 * THE CONTRACT (pinned - do not invent alternatives):
 *
 *   Auth          `X-Service-Key: <AI_SERVICE_API_KEY>`. The service fails
 *                 closed, so this is always required.
 *   Correlation   `X-Request-Id`, echoed back by the service, logged on both
 *                 sides so one failure can be traced across two processes.
 *                 It is OPAQUE and NEVER PHI - a report id or a random uuid.
 *   Extraction    POST /api/v1/ocr/extract, multipart, file part named `file`.
 *                 -> { success: true, data: { source, raw_text, pages[],
 *                      extracted_parameters[], report_metadata,
 *                      extraction_confidence, warnings[] } }
 *   Features      POST /api/v1/features/engineer, JSON
 *                 { extraction: <the DATA OBJECT above, unwrapped>, profile? }
 *                 The `data` envelope MUST be unwrapped; sending the wrapped
 *                 form is a silent pipeline break.
 *   Profile       Module 5 accepts Module 2's camelCase JSON directly via
 *                 pydantic aliases. Field names are NOT translated here.
 *   Validation    POST /api/v1/features/validate, JSON
 *                 { engineered: <Module 5's DATA OBJECT, unwrapped> }   Module 6
 *   Rules         POST /api/v1/rules/evaluate, JSON
 *                 { validated: <Module 6's DATA OBJECT, unwrapped> }    Module 8
 *   ML            POST /api/v1/ml/predict, JSON
 *                 { validated: <Module 6's DATA OBJECT, unwrapped> }    Modules 9/10
 *   Report        POST /api/v1/report/generate, JSON
 *                 { validated: <Module 6's DATA OBJECT, unwrapped> }  Modules 17-20
 *                 -> the ClinicalReport, with Module 16's fusion (and through
 *                 it Module 15's collection) nested VERBATIM under `fusion`.
 *   Explanation   POST /api/v1/explain/report, JSON
 *                 { report: <Module 17's DATA OBJECT, unwrapped>,
 *                   max_explanations: <int, 0..6> }                  Module 23
 *                 -> a ReportExplanationSet. NOTE: a refusal is an HTTP 200
 *                 with `outcome` != "generated", NOT an error - see below.
 *   Guidance      POST /api/v1/explain/guidance, JSON
 *                 { conditions: [], features: [] }                   Module 26
 *                 Catalogue text only; this route reaches no model.
 *   Trends        POST /api/v1/timeline/trends, JSON
 *                 { patient_ref?, reports: TimelineReportInput[],
 *                   options? }                                     Module 28
 *   Comparison    POST /api/v1/comparison/reports, JSON
 *                 { ...as above, baseline_ref?, comparison_ref? }  Module 29
 *   Progress      POST /api/v1/progress/score, JSON
 *                 { ...exactly as Module 29 }                      Module 30
 *   Population    POST /api/v1/population/context, JSON
 *                 { patient_ref?, age?, gender?,
 *                   measurements: [{feature, value, unit}] }        Module 31
 *                 `age` and `gender` are the SUBJECT, not measurements, and
 *                 are read from the authenticated user's own Module 2 profile
 *                 - never from a query parameter and never from the report.
 *                 Omitting either is answered with a reason code; neither is
 *                 ever defaulted or coerced. NO `snapshot` is ever sent: the
 *                 service refuses a request carrying both sources, and
 *                 `snapshot` is also the only door through which age and
 *                 gender could arrive from somewhere other than the profile.
 *   Doctor summ.  POST /api/v1/doctor-summary/generate, JSON
 *                 { report: <Module 17's DATA OBJECT, unwrapped>,
 *                   report_ref?, report_date?,
 *                   history: TimelineReportInput[], options? }     Module 32
 *   History shape `TimelineReportInput` is ONE shape shared by all four:
 *                 { report_id, chrono_date, validated: <Module 6's DATA
 *                 OBJECT, unwrapped> }. Built once in historyService.
 *   Health        GET /api/v1/health, unauthenticated.
 *
 * MODULE 23 REFUSALS ARE NOT TRANSPORT FAILURES. `/explain/report` answers 200
 * for all five outcomes - `generated`, `withheld_by_safety`, `not_grounded`,
 * `model_unavailable` and `unknown_subject` - each carrying a `safe_fallback`
 * payload. Nothing in this file may map a refusal onto an ApiError: a report
 * whose explanation the safety layer withheld is a GOOD report, and treating it
 * as a failed call would mark a sound analysis `failed`.
 *
 * `/api/v1/explain/term` and `/api/v1/explain/terms` (Module 25) are
 * DELIBERATELY NOT CALLED from the pipeline. They answer "what does <word>
 * mean" for a word a patient typed - a per-question lookup with no report
 * input, no owner scoping to inherit and nothing to persist against a run.
 * Wiring them into `analyze` would mean inventing terms to look up. They are a
 * future patient-facing lookup route, not a stage.
 *
 * `/api/v1/decisions/fuse` (Modules 15+16) is DELIBERATELY NOT CALLED. The
 * report endpoint runs the same chain internally and returns that exact fusion
 * object under `report.fusion`, so a separate call would run the decision
 * engine twice and hand us TWO fusion objects that a non-deterministic
 * predictor tie-break could make disagree. One call, one answer.
 *
 * EVERY stage passes the WHOLE upstream data object, never a slice of it. Each
 * one carries `all_warnings`, `upstream` and the missing/unmapped lists forward,
 * and a consumer that forwards only `features` / `valid` silently destroys the
 * provenance the final report (Module 17) needs to tell a damaged scan from a
 * clean one.
 *
 * TIMEOUTS ARE PER STAGE. Extraction is the only slow one (Gemini calls per
 * page); validation, rules and ML return in milliseconds and get their own,
 * much shorter, separately configurable budgets. See config/env.js.
 *
 * PHI RULES observed throughout this file:
 *   - No response body, no request body, and no filename is ever logged.
 *   - No message returned to a caller is built from the service's response
 *     body: an ai-service error body can quote report text, so every message
 *     below is a static string. Only the HTTP status and the correlation id
 *     cross into a log line or an error message.
 */

const PATHS = Object.freeze({
  extract: '/api/v1/ocr/extract',
  engineer: '/api/v1/features/engineer',
  validate: '/api/v1/features/validate',
  rules: '/api/v1/rules/evaluate',
  predict: '/api/v1/ml/predict',
  report: '/api/v1/report/generate',
  explain: '/api/v1/explain/report',
  guidance: '/api/v1/explain/guidance',
  glossary: '/api/v1/explain/glossary',
  timeline: '/api/v1/timeline/trends',
  comparison: '/api/v1/comparison/reports',
  progress: '/api/v1/progress/score',
  doctorSummary: '/api/v1/doctor-summary/generate',
  population: '/api/v1/population/context',
  health: '/api/v1/health',
});

const HEADER_SERVICE_KEY = 'X-Service-Key';
const HEADER_REQUEST_ID = 'X-Request-Id';

/**
 * Stage names, used for correlation logging and for warning provenance.
 *
 * These MATCH the ai-service's own `stage` values (`extraction` /
 * `feature_engineering`) on purpose: a warning tagged here and a warning tagged
 * there must be the same string, or de-duplication silently fails and a
 * consumer sees the same warning twice under two different origins.
 */
const STAGES = Object.freeze({
  EXTRACTION: 'extraction',
  FEATURES: 'feature_engineering',
  VALIDATION: 'validation',
  RULES: 'rules',
  ML: 'ml',
  // `report` MATCHES the ai-service's own `stage: "report"` on its Module 17
  // warnings, for the same reason every other name here does: a warning tagged
  // on that side and a warning tagged here must be the same string or
  // de-duplication silently fails and one warning appears twice.
  REPORT: 'report',
  // Modules 23 and 26. These two names are OURS - the explain endpoints do not
  // emit stage-tagged warnings of their own, so unlike every name above there
  // is no far-side string to match. They are still fixed constants for the same
  // reason: `analysis.stages` is keyed by them and a drifting key is a silently
  // missing stage.
  EXPLANATION: 'explanation',
  GUIDANCE: 'guidance',
  GLOSSARY: 'glossary',
  // Modules 28, 29, 30 and 32. These four DO have a far-side string to match
  // and they match it exactly: `STAGE_TIMELINE` in app/schemas/timeline.py,
  // `STAGE_COMPARISON` in comparison.py, `STAGE_PROGRESS` in progress.py and
  // `STAGE_DOCTOR_SUMMARY` in doctor_summary.py. Same reason as every name
  // above - a warning tagged there and a warning tagged here have to be the
  // same string or de-duplication silently fails.
  TIMELINE: 'timeline',
  COMPARISON: 'comparison',
  PROGRESS: 'progress',
  DOCTOR_SUMMARY: 'doctor_summary',
  // Module 31. This name is OURS, like EXPLANATION and GUIDANCE above and
  // unlike the four before it: Module 31 tags no warnings with a stage of its
  // own (`PopulationContextData.warnings` is a flat list of sentences about the
  // request), so there is no far-side string to match. Fixed constant for the
  // same reason as every other name here - a drifting key is a silently missing
  // stage in a correlation log.
  POPULATION: 'population',
  HEALTH: 'health',
});

// --------------------------------------------------------------- plumbing ---

/** Is the pipeline configured at all? */
function isConfigured() {
  return Boolean(config.aiService.url && config.aiService.apiKey);
}

/**
 * The charset the ai-service accepts for `X-Request-Id`: `[A-Za-z0-9._:-]`,
 * 1-128 characters. Anything outside it is SILENTLY DISCARDED on that side, so
 * a rejected id costs the correlation without any error to notice - hence the
 * hard filter here rather than a hope.
 */
const REQUEST_ID_PATTERN = /^[A-Za-z0-9._:-]{1,128}$/;

/**
 * A fresh correlation id. Opaque by construction - a uuid, or a caller-supplied
 * value which in practice is a Mongo ObjectId. NEVER derived from user input, a
 * filename, or anything in the report: it is logged on both sides, so anything
 * user-controlled here would be a log-injection and PHI hazard at once.
 */
function newRequestId(seed) {
  if (typeof seed === 'string' && REQUEST_ID_PATTERN.test(seed)) return seed;
  return crypto.randomUUID();
}

/**
 * Startup diagnostic.
 *
 * The ai-service returns a BYTE-IDENTICAL 401 for a missing header, a wrong
 * key, an empty key and a whitespace key, so a 401 at runtime cannot tell an
 * operator which of those it is. The only way to distinguish "we are
 * misconfigured" from "the key is wrong" is to state our own configuration at
 * startup. The key itself is never printed - only whether one is present and
 * how long it is.
 */
function describeConfig() {
  return {
    configured: isConfigured(),
    url: config.aiService.url || null,
    apiKeyPresent: Boolean(config.aiService.apiKey),
    apiKeyLength: config.aiService.apiKey ? config.aiService.apiKey.length : 0,
    timeoutMs: config.aiService.timeoutMs,
    retries: config.aiService.retries,
  };
}

function notConfigured() {
  return new ApiError(
    503,
    'AI_SERVICE_NOT_CONFIGURED',
    'The analysis service is not configured on this deployment'
  );
}

/** Lazily-built axios instance. Rebuilt when the base URL changes (tests). */
let cachedClient = null;
let cachedFor = null;

function http() {
  const base = config.aiService.url;
  if (cachedClient && cachedFor === base) return cachedClient;
  cachedClient = axios.create({
    baseURL: base,
    // Defence in depth: never buffer an unbounded response from the service.
    maxContentLength: 32 * 1024 * 1024,
    maxBodyLength: 64 * 1024 * 1024,
    // Let axios throw on non-2xx so `err.response.status` drives the mapping.
    validateStatus: (status) => status >= 200 && status < 300,
  });
  cachedFor = base;
  return cachedClient;
}

/** Test hook: drop the cached axios instance. */
function resetClient() {
  cachedClient = null;
  cachedFor = null;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** Correlation logging. Status + stage + opaque id only - never a body. */
function logFailure(stage, requestId, detail) {
  if (config.isTest) return;
  // eslint-disable-next-line no-console
  console.warn(
    `[ai-service] stage=${stage} requestId=${requestId} outcome=failure ${detail}`
  );
}

// ---------------------------------------------------------- error mapping ---

/**
 * Translate a transport/HTTP failure into an `ApiError` plus a retryability
 * verdict.
 *
 * The distinctions matter operationally: "the service is down" (503),
 * "the service is slow" (504), "we are misconfigured against it" (502 on a
 * 401 - a client must never be told an auth detail), and "the document itself
 * was rejected" (422/415, which is genuinely the caller's problem) all have
 * different fixes.
 *
 * @returns {{ error: ApiError, retryable: boolean, detail: string }}
 */
/**
 * User-actionable refusals from the ai-service, keyed by ITS stable error code.
 *
 * WHY THIS EXISTS. A 400/422 from the ai-service is always the caller's
 * problem and is usually FIXABLE BY THE PATIENT - a report with too many
 * pages, a password-protected PDF, a scan with no readable page. Collapsing
 * every one of them into "could not process this report" tells the user
 * nothing they can act on, and sends them to a maintainer for something they
 * could have fixed themselves in ten seconds.
 *
 * These are OUR OWN strings, not the ai-service's response body. The body is
 * still never echoed: only the stable `code` is read, and it selects a message
 * written here. That keeps the existing guarantee (nothing from the service's
 * body, which could quote report content, reaches the patient) while still
 * naming the cause.
 *
 * An unknown code falls back to the generic message below, so a new code on
 * the Python side degrades to today's behaviour rather than breaking.
 */
const INTAKE_REFUSAL_MESSAGES = Object.freeze({
  TOO_MANY_PAGES:
    'This report has more pages than the analysis service accepts. Split it into smaller files and upload them separately.',
  FILE_TOO_LARGE:
    'This report is too large for the analysis service. Upload a smaller or lower-resolution file.',
  ENCRYPTED_PDF:
    'This PDF is password-protected. Remove the password and upload it again.',
  CORRUPT_FILE:
    'This file could not be opened. It may be damaged - try re-downloading or re-exporting it.',
  UNSUPPORTED_FILE_TYPE:
    'This file type is not supported. Upload a PDF, JPEG or PNG.',
  NO_RENDERABLE_PAGES:
    'No readable pages were found in this file. Check that it is not blank.',
  NO_FILE: 'No file reached the analysis service. Upload the report again.',
});

/**
 * The ai-service's stable error code from a refusal envelope
 * (`{ success: false, error: { code, message } }`), or null. Only the code is
 * read - never the message.
 */
function aiServiceErrorCode(response) {
  const code = response && response.data && response.data.error && response.data.error.code;
  return typeof code === 'string' ? code : null;
}

function mapAxiosError(err, stage) {
  const response = err && err.response;

  if (response) {
    const status = Number(response.status);
    const detail = `status=${status}`;

    // 401/403 - OUR credential is wrong. This is a server-side configuration
    // failure, not something the caller did, so it is never surfaced as a 401
    // (which would suggest the caller re-authenticate) and never explains what
    // was wrong with the key.
    if (status === 401 || status === 403) {
      return {
        retryable: false, // deterministic - retrying only burns the rate limit
        detail,
        error: new ApiError(
          502,
          'AI_SERVICE_UNAUTHORIZED',
          'The analysis service rejected this deployment\'s credentials'
        ),
      };
    }

    // 400 and 422 - the service looked at the payload and refused it.
    // Deterministic, and NOT a contract mismatch, so neither may fall through
    // to the 502 below.
    //
    // The two arrive by different routes and mean the same thing to a caller:
    // FastAPI's own request validation answers 422, while the service's
    // `BadRequestError` answers 400 for a payload that parsed but whose
    // CONTENT it will not accept - Module 29's `COMPARISON_REPORT_NOT_FOUND`
    // for a named report absent from the supplied set, for instance. Calling
    // that a 502 tells the operator their two services disagree on the wire
    // format, when in fact they agree perfectly and the request content was
    // refused; it also reports a caller-fixable problem as a server fault.
    if (status === 400 || status === 422) {
      // Name the cause when the service gave us a code we recognise. See
      // INTAKE_REFUSAL_MESSAGES above for why the body itself is still unread.
      const serviceCode = aiServiceErrorCode(response);
      const specific = serviceCode && INTAKE_REFUSAL_MESSAGES[serviceCode];
      return {
        retryable: false,
        detail: serviceCode ? `${detail} code=${serviceCode}` : detail,
        error: new ApiError(
          422,
          'AI_SERVICE_REJECTED_INPUT',
          specific || 'The analysis service could not process this report'
        ),
      };
    }

    if (status === 413) {
      return {
        retryable: false,
        detail,
        error: new ApiError(
          413,
          'PAYLOAD_TOO_LARGE',
          'This report is too large for the analysis service'
        ),
      };
    }

    if (status === 415) {
      return {
        retryable: false,
        detail,
        error: new ApiError(
          415,
          'UNSUPPORTED_MEDIA_TYPE',
          'The analysis service does not support this report format'
        ),
      };
    }

    // 429 - transient by definition; back off and try once more.
    if (status === 429) {
      return {
        retryable: true,
        detail,
        error: new ApiError(
          503,
          'AI_SERVICE_BUSY',
          'The analysis service is busy; please try again shortly'
        ),
      };
    }

    if (status >= 500) {
      return {
        retryable: true,
        detail,
        error: new ApiError(
          502,
          'AI_SERVICE_ERROR',
          'The analysis service failed to process this report'
        ),
      };
    }

    // Any other 4xx: a contract mismatch between the two services.
    return {
      retryable: false,
      detail,
      error: new ApiError(
        502,
        'AI_SERVICE_REJECTED_REQUEST',
        'The analysis service rejected the request'
      ),
    };
  }

  const code = String((err && err.code) || '').toUpperCase();
  const detail = `code=${code || 'UNKNOWN'}`;

  // Timeout. Distinct from "down": the service is reachable and may well be
  // mid-extraction, so the operator's fix is a longer AI_SERVICE_TIMEOUT_MS,
  // not a restart.
  if (['ECONNABORTED', 'ETIMEDOUT', 'ERR_CANCELED', 'ETIME'].includes(code)) {
    return {
      retryable: true,
      detail,
      error: new ApiError(
        504,
        'AI_SERVICE_TIMEOUT',
        'The analysis service did not respond in time'
      ),
    };
  }

  // Connection refused / DNS / reset - the service is not reachable.
  if (
    ['ECONNREFUSED', 'ENOTFOUND', 'EAI_AGAIN', 'ECONNRESET', 'EPIPE', 'EHOSTUNREACH',
      'ENETUNREACH', 'ERR_NETWORK'].includes(code)
  ) {
    return {
      retryable: true,
      detail,
      error: new ApiError(
        503,
        'AI_SERVICE_UNAVAILABLE',
        'The analysis service is currently unreachable'
      ),
    };
  }

  return {
    retryable: false,
    detail,
    error: new ApiError(
      502,
      'AI_SERVICE_ERROR',
      'The analysis service could not be reached'
    ),
  };
}

/**
 * Validate the `{ success: true, data: {...} }` envelope both endpoints use.
 * A body that does not match is a contract break, not a 500 with a stack.
 */
function unwrapEnvelope(body, stage) {
  const ok =
    body &&
    typeof body === 'object' &&
    !Array.isArray(body) &&
    body.success === true &&
    body.data &&
    typeof body.data === 'object' &&
    !Array.isArray(body.data);

  if (!ok) {
    throw new ApiError(
      502,
      'AI_SERVICE_MALFORMED_RESPONSE',
      `The analysis service returned an unexpected ${stage} response`
    );
  }
  assertStorableKeys(body.data, stage);
  return body.data;
}

/**
 * MongoDB cannot reliably store field names beginning with `$`, and a name
 * containing `.` is ambiguous with a path. The two payloads are persisted as
 * `Mixed`, so a service response carrying such a key would surface as a driver
 * error deep inside the success write - i.e. an unmapped error class reaching
 * the stack-printing 500 branch, which is the exact defect shape (D1) this pass
 * exists to close.
 *
 * The payload is REJECTED rather than rewritten. Silently renaming a key inside
 * a medical extraction would corrupt data to make a write succeed, which is the
 * wrong trade: better a clean, retryable 502 that names the contract as broken.
 */
function assertStorableKeys(value, stage, depth = 0) {
  if (depth > 32) {
    throw new ApiError(
      502,
      'AI_SERVICE_MALFORMED_RESPONSE',
      `The analysis service returned an unexpected ${stage} response`
    );
  }
  if (Array.isArray(value)) {
    for (const item of value) assertStorableKeys(item, stage, depth + 1);
    return;
  }
  if (!value || typeof value !== 'object') return;
  for (const key of Object.keys(value)) {
    if (key.startsWith('$') || key.includes('.')) {
      throw new ApiError(
        502,
        'AI_SERVICE_MALFORMED_RESPONSE',
        `The analysis service returned an unexpected ${stage} response`
      );
    }
    assertStorableKeys(value[key], stage, depth + 1);
  }
}

/**
 * Run `attempt` with the configured retry policy.
 *
 * ONLY transient failures are retried - connection refused/reset, timeout, 429,
 * 5xx. A 401 and a 422 are deterministic: retrying them cannot change the
 * outcome and would double the load on a service that has already said no. An
 * ApiError raised by our own envelope check is likewise never retried.
 */
async function withRetry(stage, requestId, attempt) {
  const maxExtra = Math.max(0, config.aiService.retries);
  let lastError = null;

  for (let tryIndex = 0; tryIndex <= maxExtra; tryIndex += 1) {
    try {
      // eslint-disable-next-line no-await-in-loop
      return await attempt();
    } catch (err) {
      if (err instanceof ApiError) throw err; // our own envelope/config errors

      const { error, retryable, detail } = mapAxiosError(err, stage);
      lastError = error;
      logFailure(stage, requestId, `${detail} attempt=${tryIndex + 1} retryable=${retryable}`);

      if (!retryable || tryIndex === maxExtra) throw error;
      // eslint-disable-next-line no-await-in-loop
      await sleep(config.aiService.retryDelayMs * (tryIndex + 1));
    }
  }

  throw lastError || ApiError.internal();
}

function authHeaders(requestId) {
  return {
    [HEADER_SERVICE_KEY]: config.aiService.apiKey,
    [HEADER_REQUEST_ID]: requestId,
  };
}

// ------------------------------------------------------------- extraction ---

/**
 * Drain a readable stream into a Buffer, aborting past `maxBytes`.
 *
 * The file has to become a multipart part, so it has to be materialised
 * somewhere. `UPLOAD_MAX_BYTES` already bounds this - Module 3 buffers the same
 * bytes on the way in - but the cap is re-asserted here so a file that grew on
 * disk (or a driver that lies) cannot exhaust memory on the way out.
 */
function readStreamToBuffer(stream, maxBytes) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let total = 0;
    stream.on('data', (chunk) => {
      total += chunk.length;
      if (total > maxBytes) {
        stream.destroy();
        reject(
          new ApiError(
            413,
            'PAYLOAD_TOO_LARGE',
            'The stored report file exceeds the size the analysis service accepts'
          )
        );
        return;
      }
      chunks.push(chunk);
    });
    stream.on('error', (err) =>
      reject(
        err instanceof ApiError
          ? err
          : new ApiError(500, 'STORAGE_READ_FAILED', 'The stored report file could not be read')
      )
    );
    stream.on('end', () => resolve(Buffer.concat(chunks, total)));
  });
}

/**
 * POST /api/v1/ocr/extract
 *
 * @param {object} args
 * @param {() => Promise<import('stream').Readable>|import('stream').Readable} args.streamFactory
 *        Produces a FRESH read stream. It is a factory rather than a stream
 *        because a stream cannot be replayed: a retried attempt needs its own.
 *        The caller builds it from `getStorage(driver).createReadStream(key)` -
 *        a path is never constructed from a key.
 * @param {string} args.filename Synthetic, PHI-free (see analysisService).
 * @param {string} args.mimeType Detected type recorded at upload.
 * @param {string} args.requestId Opaque correlation id.
 * @returns {Promise<object>} the UNWRAPPED `data` object.
 */
async function extract({ streamFactory, filename, mimeType, requestId }) {
  if (!isConfigured()) throw notConfigured();

  const maxBytes = config.upload.maxBytes;

  return withRetry(STAGES.EXTRACTION, requestId, async () => {
    const stream = await streamFactory();
    const buffer = await readStreamToBuffer(stream, maxBytes);

    const form = new FormData();
    form.append(
      'file',
      new Blob([buffer], { type: mimeType || 'application/octet-stream' }),
      filename
    );

    const res = await http().post(PATHS.extract, form, {
      headers: authHeaders(requestId),
      timeout: config.aiService.timeoutMs,
    });

    return unwrapEnvelope(res.data, STAGES.EXTRACTION);
  });
}

// ------------------------------------------------------- JSON stage caller ---

/**
 * One JSON stage call: configured check, auth + correlation headers, the
 * stage's OWN timeout, the shared retry policy, and envelope validation.
 *
 * Every JSON stage goes through here so a change to the contract (a header, the
 * envelope shape, the retry rules) cannot be applied to four call sites and
 * missed on the fifth.
 *
 * @param {object} args
 * @param {string} args.path      One of PATHS.
 * @param {string} args.stage     One of STAGES - used for logging and warnings.
 * @param {object} args.payload   The request body, built by the caller verbatim.
 * @param {string} args.requestId Opaque correlation id.
 * @param {number} args.timeoutMs THIS stage's timeout, never a shared default.
 * @returns {Promise<object>} the UNWRAPPED `data` object.
 */
async function postJson({ path, stage, payload, requestId, timeoutMs }) {
  if (!isConfigured()) throw notConfigured();

  return withRetry(stage, requestId, async () => {
    const res = await http().post(path, payload, {
      headers: { ...authHeaders(requestId), 'Content-Type': 'application/json' },
      timeout: timeoutMs,
    });
    return unwrapEnvelope(res.data, stage);
  });
}

// --------------------------------------------------------------- features ---

/**
 * POST /api/v1/features/engineer
 *
 * @param {object} args
 * @param {object} args.extraction The UNWRAPPED extraction `data` object.
 * @param {object} [args.profile] Module 2's camelCase profile, or omitted.
 * @param {string} args.requestId
 * @returns {Promise<object>} the UNWRAPPED `data` object.
 */
async function engineerFeatures({ extraction, profile, requestId }) {
  // TRI-STATE SAFETY. The body is assembled by ADDING `profile` only when a
  // profile object exists. `hypertension` / `heartDisease` are tri-state in
  // Module 2 - true, false, or ABSENT meaning unknown - and the absence has to
  // survive intact all the way to the wire. Nothing here defaults, coerces, or
  // fills a missing field; the payload is built in analysisService by explicit
  // key copying and is passed through verbatim.
  const payload = { extraction };
  if (profile && typeof profile === 'object') payload.profile = profile;

  return postJson({
    path: PATHS.engineer,
    stage: STAGES.FEATURES,
    payload,
    requestId,
    timeoutMs: config.aiService.timeoutMs,
  });
}

// ------------------------------------------- validation / rules / ML (6,8,9) ---

/**
 * POST /api/v1/features/validate - Module 6.
 *
 * The WHOLE Module 5 data object is sent under `engineered`, not just its
 * `features` map: Module 6 forwards `all_warnings`, `upstream`,
 * `missing_features` and `unmapped` into its own output, and slicing here would
 * lose every upstream warning at this boundary - the exact defect shape that
 * has already bitten this project twice.
 *
 * @returns {Promise<object>} the UNWRAPPED `data` object.
 */
async function validateFeatures({ engineered, requestId }) {
  return postJson({
    path: PATHS.validate,
    stage: STAGES.VALIDATION,
    payload: { engineered },
    requestId,
    timeoutMs: config.aiService.validateTimeoutMs,
  });
}

/**
 * POST /api/v1/rules/evaluate - Module 8 (deterministic clinical rules).
 *
 * Takes Module 6's WHOLE data object under `validated`. The service also
 * accepts `engineered` as a fallback, which this client deliberately never
 * uses: that path re-validates in-process, so the rules would silently run
 * against a validation this backend never saw or stored.
 */
async function evaluateRules({ validated, requestId }) {
  return postJson({
    path: PATHS.rules,
    stage: STAGES.RULES,
    payload: { validated },
    requestId,
    timeoutMs: config.aiService.rulesTimeoutMs,
  });
}

/**
 * POST /api/v1/ml/predict - Modules 9/10 (the ML predictor engine).
 *
 * Same input as the rule engine and INDEPENDENT of it - see analysisService,
 * which runs the two concurrently and keeps whichever succeeds.
 */
async function predict({ validated, requestId }) {
  return postJson({
    path: PATHS.predict,
    stage: STAGES.ML,
    payload: { validated },
    requestId,
    timeoutMs: config.aiService.mlTimeoutMs,
  });
}

// ------------------------------------------ clinical report (17-20) -------

/**
 * POST /api/v1/report/generate - Modules 17, 18, 19 and 20.
 *
 * THE USER-VISIBLE DELIVERABLE. Everything before this produces machine
 * decisions; this is the clinical report a person reads.
 *
 * Takes Module 6's WHOLE data object under `validated`, exactly as the rule and
 * ML stages do - `ClinicalReportRequest` subclasses `DecisionFusionRequest`
 * subclasses `RuleEvaluationRequest`, so the accepted shapes cannot drift
 * between the three.
 *
 * SENDING THE WHOLE OBJECT IS LOAD-BEARING HERE IN A WAY IT IS NOWHERE ELSE.
 * Module 20's rejected-feature join is built by lifting Module 6's `rejected`
 * map out of the RAW request body (the decision chain's request models
 * deliberately cannot parse it, which is what makes "a clinical rule can never
 * read a rejected value" structural). Slicing the payload down to `valid` would
 * not fail: it would return HTTP 200 with a report that says "this value was
 * not available in the submitted report" about a value that WAS in the report
 * and was refused - the exact wrong statement Module 20 exists to correct.
 *
 * @returns {Promise<object>} the UNWRAPPED ClinicalReport `data` object.
 */
async function generateReport({ validated, requestId }) {
  return postJson({
    path: PATHS.report,
    stage: STAGES.REPORT,
    payload: { validated },
    requestId,
    timeoutMs: config.aiService.reportTimeoutMs,
  });
}

// ----------------------------------- patient explanation (23) / guidance (26) --

/**
 * POST /api/v1/explain/report - Module 23, gated by Module 24.
 *
 * THE LAST HOP TO THE PATIENT. Everything before it, the clinical report
 * included, is written for a reader who already knows what HbA1c is. This is
 * the stage that turns those findings into language a patient can act on, and
 * spec section 14 puts it - and the safety validation behind it - between the
 * clinical analysis and the user.
 *
 * TAKES MODULE 17'S WHOLE REPORT OBJECT, not a slice of it. `explain_report`
 * walks `laboratory_values` for the values it may explain and `conditions` for
 * the findings each one contributed to, and it explains ONLY rows whose
 * `usable` flag is true - writing a friendly paragraph about a number the
 * validator refused to trust is the worst kind of fluency. Sending a reduced
 * payload would silently produce explanations with no conditions attached, or
 * explanations of values the system does not believe.
 *
 * `max_explanations` is sent explicitly rather than left to the far side's
 * default: every explanation is a model call, and the number of them one
 * analyze request may spend is a deployment decision that belongs in this
 * deployment's config. The service `ge=0, le=6`-validates it, so it is clamped
 * in config/env.js rather than sent and 422'd.
 *
 * A REFUSAL IS A SUCCESS AT THIS LAYER. Every non-generated outcome is an HTTP
 * 200 carrying a structured fallback, so it arrives here as a normal `data`
 * object and is returned unchanged. Nothing in this function inspects
 * `outcome`; interpreting it is analysisService's job.
 *
 * @returns {Promise<object>} the UNWRAPPED ReportExplanationSet `data` object.
 */
async function explainReport({ report, requestId, maxExplanations }) {
  const limit =
    Number.isInteger(maxExplanations) && maxExplanations >= 0
      ? maxExplanations
      : config.aiService.maxExplanations;

  return postJson({
    path: PATHS.explain,
    stage: STAGES.EXPLANATION,
    payload: { report, max_explanations: limit },
    requestId,
    timeoutMs: config.aiService.explainTimeoutMs,
  });
}

/**
 * POST /api/v1/explain/guidance - Module 26, educational lifestyle guidance.
 *
 * THIS ROUTE REACHES NO LANGUAGE MODEL. It resolves reviewed catalogue text by
 * recommendation code, and its request model has no text parameter at all, so
 * the absence of generation is visible in the signature rather than promised in
 * a comment. That is why it is a separate call from `explainReport` and gets
 * the fast-stage timeout: the spec asks for PRE-APPROVED educational guidance
 * rather than unrestricted AI-generated advice, and keeping the two calls apart
 * keeps that distinction observable in `analysis.stages`.
 *
 * `codes` is deliberately NEVER sent. The service computes the educational code
 * set itself from the conditions and features, and forwarding the report's own
 * recommendation codes would mean asking for whatever Modules 8/16/17 attached
 * to a decision - which includes band-specific, risk-tier sentences that are
 * not general guidance. Passing none means the answer can only ever be the
 * general educational set.
 *
 * @returns {Promise<object>} the UNWRAPPED LifestyleGuidance `data` object.
 */
async function lifestyleGuidance({ conditions, features, requestId }) {
  return postJson({
    path: PATHS.guidance,
    stage: STAGES.GUIDANCE,
    payload: {
      conditions: Array.isArray(conditions) ? conditions : [],
      features: Array.isArray(features) ? features : [],
    },
    requestId,
    timeoutMs: config.aiService.guidanceTimeoutMs,
  });
}

/**
 * Describe laboratory tests this platform does NOT assess.
 *
 * SENDS NAMES AND NOTHING ELSE. No value, no unit, no reference range, no
 * flag, no profile field. That is not an economy, it is the safety property:
 * the service can only be asked what a test measures, never what a patient's
 * number means, so nothing it returns can be an interpretation of this
 * patient. The endpoint's request model has nowhere to put a value either, so
 * a future caller cannot add one by accident.
 *
 * The reply is cached per test name inside the Python service, so repeated
 * analytes across reports cost nothing after the first.
 */
async function describeParameters({ testNames, requestId }) {
  return postJson({
    path: PATHS.glossary,
    stage: STAGES.GLOSSARY,
    payload: {
      test_names: Array.isArray(testNames) ? testNames : [],
    },
    requestId,
    timeoutMs: config.aiService.guidanceTimeoutMs,
  });
}

// ------------------------- history: trends / comparison / progress (28-30) ---

/**
 * THE FOUR CALLS BELOW ARE THE ONLY ONES IN THIS FILE THAT ARE ABOUT MANY
 * REPORTS RATHER THAN ONE.
 *
 * Every stage above answers "what does THIS document say". Modules 28, 29, 30
 * and 32 answer "what has changed across this patient's documents", so each of
 * them takes a LIST of report snapshots in one shared shape -
 * `TimelineReportInput` (app/schemas/timeline.py) - which `historyService`
 * builds once and every one of these calls reuses verbatim. There is
 * deliberately no second snapshot shape and no per-endpoint variant: a
 * second projection of the same reports is a second thing to get wrong.
 *
 * ORDER IS NOT SENT AND MUST NOT BE. All four sort the array themselves by
 * `chrono_date`, breaking ties on `sequence` when supplied and otherwise on
 * `report_id`. Both are properties of the DATA, so the answer cannot depend on
 * the order this client happened to serialise the array in.
 *
 * WHY THESE ARE NOT PIPELINE STAGES. Nothing here is called by
 * `analysisService.runAnalysis` and nothing here is persisted. They are read
 * models computed on demand from what the pipeline already stored, which is
 * why they can be safely recomputed and why a failure here can never leave a
 * report in a wrong state. They still go through `postJson` - same headers,
 * same retry policy, same envelope validation - because the transport contract
 * is the transport contract.
 *
 * A REFUSAL FROM ANY OF THEM IS AN HTTP 200, exactly as a Module 23 refusal
 * is. "Fewer than two usable readings" comes back as `outcome:
 * INSUFFICIENT_DATA` / `NO_PAIR`, not as an error, and nothing in this file
 * inspects `outcome` or maps it onto an ApiError. Interpreting - or rather,
 * deliberately NOT interpreting - those codes is the controller's job.
 */

/**
 * POST /api/v1/timeline/trends - Module 28.
 *
 * @param {object} args
 * @param {object[]} args.reports `TimelineReportInput` snapshots, any order.
 * @param {string} [args.patientRef] Opaque patient id. NEVER a name; it is
 *        echoed back by the service, so it carries the same rule as
 *        `X-Request-Id`.
 * @param {object} [args.options] `TimelineOptions`, passed through verbatim.
 * @param {string} args.requestId
 * @returns {Promise<object>} the UNWRAPPED `TimelineTrendsData` object.
 */
async function analyseTrends({ reports, patientRef, options, requestId }) {
  const payload = { reports: Array.isArray(reports) ? reports : [] };
  if (patientRef) payload.patient_ref = patientRef;
  if (options && typeof options === 'object') payload.options = options;

  return postJson({
    path: PATHS.timeline,
    stage: STAGES.TIMELINE,
    payload,
    requestId,
    timeoutMs: config.aiService.timelineTimeoutMs,
  });
}

/**
 * POST /api/v1/comparison/reports - Module 29.
 *
 * `baselineRef` and `comparisonRef` are added ONLY when both are present. The
 * service rejects exactly one of them with a 422, and it is a genuine caller
 * error rather than something to paper over: "compare against report X" with
 * no second report named has no defined meaning, and picking a partner for the
 * caller would silently answer a different question from the one asked.
 *
 * The pair is NOT reordered here even when the named baseline is the later
 * report. Module 29 honours the caller's naming exactly and flags the
 * reversal in its own warnings; swapping it would invert every reported
 * direction of change without telling anyone.
 *
 * @returns {Promise<object>} the UNWRAPPED `ReportComparisonData` object.
 */
async function compareReports({
  reports,
  patientRef,
  baselineRef,
  comparisonRef,
  options,
  requestId,
}) {
  const payload = { reports: Array.isArray(reports) ? reports : [] };
  if (patientRef) payload.patient_ref = patientRef;
  if (baselineRef && comparisonRef) {
    payload.baseline_ref = baselineRef;
    payload.comparison_ref = comparisonRef;
  }
  if (options && typeof options === 'object') payload.options = options;

  return postJson({
    path: PATHS.comparison,
    stage: STAGES.COMPARISON,
    payload,
    requestId,
    timeoutMs: config.aiService.comparisonTimeoutMs,
  });
}

/**
 * POST /api/v1/progress/score - Module 30.
 *
 * Same request shape as Module 29 because it IS Module 29's comparison,
 * scored: `analyse_progress` runs the comparator and places each parameter on
 * a declared scale. That is why the pair selection, the refs and the
 * questionable-reading option all mean exactly what they mean above, and why
 * this client does not offer a different way to name the pair.
 *
 * @returns {Promise<object>} the UNWRAPPED `HealthProgressData` object.
 */
async function scoreProgress({
  reports,
  patientRef,
  baselineRef,
  comparisonRef,
  options,
  requestId,
}) {
  const payload = { reports: Array.isArray(reports) ? reports : [] };
  if (patientRef) payload.patient_ref = patientRef;
  if (baselineRef && comparisonRef) {
    payload.baseline_ref = baselineRef;
    payload.comparison_ref = comparisonRef;
  }
  if (options && typeof options === 'object') payload.options = options;

  return postJson({
    path: PATHS.progress,
    stage: STAGES.PROGRESS,
    payload,
    requestId,
    timeoutMs: config.aiService.progressTimeoutMs,
  });
}

// ----------------------------------------- doctor-friendly summary (32) -----

/**
 * POST /api/v1/doctor-summary/generate - Module 32.
 *
 * THE CLINICIAN-FACING DOCUMENT. It takes Module 17's WHOLE `ClinicalReport`
 * verbatim under `report` - the stored `clinicalReport`, relayed unchanged -
 * plus, optionally, the same `TimelineReportInput` history the three calls
 * above take, which drives the trend and comparison SECTIONS and nothing else.
 * Module 32 never re-runs fusion or re-derives the overall status from the
 * history; the clinical content comes from `report` alone.
 *
 * THIS ROUTE REACHES NO LANGUAGE MODEL either. Every sentence it emits comes
 * from a fixed template table scanned by the Module 24 safety scanner at
 * import time, and `DoctorSummaryRequest` has no field that can carry
 * generated prose - Module 23's explanation lives on a different object and
 * cannot be posted here. That is why this is a cheap call despite being the
 * one a clinician reads.
 *
 * `report_ref` and `report_date` are opaque identity, not content: the report
 * id and its `chronoDate`, so every clinical line in the document can be
 * attributed to a source document. Absent means the attribution says so; they
 * are never inferred from anything.
 *
 * @returns {Promise<object>} the UNWRAPPED `DoctorSummaryData` object.
 */
async function generateDoctorSummary({
  report,
  reportRef,
  reportDate,
  history,
  patientRef,
  options,
  requestId,
}) {
  const payload = { report };
  if (patientRef) payload.patient_ref = patientRef;
  if (reportRef) payload.report_ref = reportRef;
  if (reportDate) payload.report_date = reportDate;
  if (Array.isArray(history)) payload.history = history;
  if (options && typeof options === 'object') payload.options = options;

  return postJson({
    path: PATHS.doctorSummary,
    stage: STAGES.DOCTOR_SUMMARY,
    payload,
    requestId,
    timeoutMs: config.aiService.doctorSummaryTimeoutMs,
  });
}

// --------------------------------------------- population context (31) ------

/**
 * POST /api/v1/population/context - Module 31.
 *
 * "Among people of the same sex and a similar age in a real, published health
 * survey, how common is a value like this one?" - a DESCRIPTIVE question about
 * a population, answered from shipped NHANES tables. It is not a reference
 * range, not an interpretation and not a risk: Module 8 owns "is this value in
 * range", Module 31 owns only "how common is this value".
 *
 * MODEL-FREE AND DETERMINISTIC on the far side. One request is a unit
 * conversion through the audited table plus a bisect against eleven published
 * cut-points, so it is the cheapest JSON call in this file.
 *
 * ==========================================================================
 * THE SUBJECT IS NOT A MEASUREMENT, AND IT COMES FROM THE PROFILE
 * ==========================================================================
 *
 * `age` and `gender` choose the cohort a value is scored against, so they are
 * the one thing in this payload a caller must never be able to set: scoring a
 * value against an arbitrary cohort is a different claim wearing the same
 * words. The controller reads both from the AUTHENTICATED user's own Module 2
 * profile and nowhere else, and neither is accepted from the request.
 *
 * EACH IS OMITTED WHEN ABSENT, NEVER DEFAULTED. A profile with no age yields
 * `AGE_NOT_PROVIDED` from the service; a profile whose gender is `other`,
 * `prefer_not_to_say`, or absent yields `SEX_COHORT_NOT_AVAILABLE`. Those
 * refusals ARE the product - Module 31 publishes no all-adults distribution to
 * fall back on, because haemoglobin and creatinine differ enough by sex that an
 * unmatched percentile would be a different statement in the same sentence.
 * Nothing here substitutes, rounds, or "helpfully" picks a nearer category.
 *
 * `snapshot` IS DELIBERATELY NEVER SENT. It is the request's second value
 * source (the service 422s a request carrying both), and it is also the only
 * other place the service will read an age or a gender from - so not sending
 * it is what makes "the subject comes from the profile" true by construction
 * rather than by convention.
 *
 * MEASUREMENTS ARE PASSED THROUGH UNFILTERED. The caller sends the report's
 * validated feature set as it stands; deciding which features Module 31 covers
 * is not this backend's job, and a filter here would be a second, drifting copy
 * of the service's own coverage table. An uncovered, non-numeric or
 * unit-less entry comes back as its own `available: false` reason code, which
 * is a better answer than the feature silently not appearing at all.
 *
 * A REFUSAL IS AN HTTP 200, exactly as it is for Modules 23 and 28-30. Nothing
 * in this function inspects `available` or `reason_code`.
 *
 * @param {object} args
 * @param {{feature: string, value: *, unit: ?string}[]} args.measurements
 * @param {number} [args.age] Whole years, from the profile. Omitted if unknown.
 * @param {string} [args.gender] Module 2's own vocabulary, VERBATIM - `male` |
 *        `female` | `other` | `prefer_not_to_say`. Never translated, never
 *        mapped onto a binary category.
 * @param {string} [args.patientRef] Opaque patient id; echoed back, never a name.
 * @param {object} [args.options] `PopulationOptions`, passed through verbatim.
 * @param {string} args.requestId
 * @returns {Promise<object>} the UNWRAPPED `PopulationContextData` object.
 */
async function populationContext({
  measurements,
  age,
  gender,
  patientRef,
  options,
  requestId,
}) {
  const payload = { measurements: Array.isArray(measurements) ? measurements : [] };
  if (patientRef) payload.patient_ref = patientRef;
  // ABSENCE MUST NOT BECOME A VALUE. The key is ADDED only when there is a
  // real one, so an unknown age is an absent field rather than a zero and an
  // unstated gender is an absent field rather than a guess. `age` is admitted
  // on `Number.isFinite` rather than on truthiness, because a truthiness test
  // would silently drop a genuine age of 0.
  if (Number.isFinite(age)) payload.age = age;
  if (typeof gender === 'string' && gender) payload.gender = gender;
  if (options && typeof options === 'object') payload.options = options;

  return postJson({
    path: PATHS.population,
    stage: STAGES.POPULATION,
    payload,
    requestId,
    timeoutMs: config.aiService.populationTimeoutMs,
  });
}

// ----------------------------------------------------------------- health ---

/**
 * GET /api/v1/health - unauthenticated, short timeout, never retried.
 *
 * Returns a verdict object rather than throwing: a health probe that throws
 * would make the backend's own liveness depend on another process being up.
 *
 * @returns {Promise<{configured: boolean, reachable: boolean, status?: number,
 *   error?: string, latencyMs?: number, checkedAt: string}>}
 */
async function health() {
  const checkedAt = new Date().toISOString();
  if (!isConfigured()) {
    return { configured: false, reachable: false, error: 'NOT_CONFIGURED', checkedAt };
  }

  const startedAt = Date.now();
  try {
    const res = await http().get(PATHS.health, {
      timeout: config.aiService.healthTimeoutMs,
      headers: { [HEADER_REQUEST_ID]: newRequestId() },
    });
    return {
      configured: true,
      reachable: true,
      status: res.status,
      latencyMs: Date.now() - startedAt,
      checkedAt,
    };
  } catch (err) {
    const { error, detail } = mapAxiosError(err, STAGES.HEALTH);
    return {
      configured: true,
      reachable: false,
      // The stable machine code only - never the service's response body.
      error: error.code,
      detail,
      latencyMs: Date.now() - startedAt,
      checkedAt,
    };
  }
}

module.exports = {
  PATHS,
  STAGES,
  HEADER_SERVICE_KEY,
  HEADER_REQUEST_ID,
  isConfigured,
  describeConfig,
  REQUEST_ID_PATTERN,
  newRequestId,
  notConfigured,
  extract,
  engineerFeatures,
  validateFeatures,
  evaluateRules,
  predict,
  generateReport,
  explainReport,
  lifestyleGuidance,
  describeParameters,
  analyseTrends,
  compareReports,
  scoreProgress,
  generateDoctorSummary,
  populationContext,
  health,
  resetClient,
  // exported for unit tests
  mapAxiosError,
  unwrapEnvelope,
  assertStorableKeys,
  readStreamToBuffer,
};
