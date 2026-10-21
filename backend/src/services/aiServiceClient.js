'use strict';

const crypto = require('crypto');
const axios = require('axios');

const config = require('../config/env');
const ApiError = require('../utils/ApiError');


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
  clinicianSummary: '/api/v1/explain/clinician-summary',
  clinicianFingerprint: '/api/v1/explain/clinician-summary/fingerprint',
  summaryProse: '/api/v1/explain/summary-prose',
  findingContext: '/api/v1/explain/finding-context',
  labPolarity: '/api/v1/explain/lab-polarity',
  labNameMatch: '/api/v1/explain/lab-name-match',
  timeline: '/api/v1/timeline/trends',
  comparison: '/api/v1/comparison/reports',
  progress: '/api/v1/progress/score',
  doctorSummary: '/api/v1/doctor-summary/generate',
  population: '/api/v1/population/context',
  chat: '/api/v1/chat',
  health: '/api/v1/health',
});

const HEADER_SERVICE_KEY = 'X-Service-Key';
const HEADER_REQUEST_ID = 'X-Request-Id';

const STAGES = Object.freeze({
  EXTRACTION: 'extraction',
  FEATURES: 'feature_engineering',
  VALIDATION: 'validation',
  RULES: 'rules',
  ML: 'ml',
  REPORT: 'report',
  EXPLANATION: 'explanation',
  GUIDANCE: 'guidance',
  GLOSSARY: 'glossary',
  LAB_POLARITY: 'lab_polarity',
  LAB_NAME_MATCH: 'lab_name_match',
  TIMELINE: 'timeline',
  COMPARISON: 'comparison',
  PROGRESS: 'progress',
  DOCTOR_SUMMARY: 'doctor_summary',
  POPULATION: 'population',
  CHAT: 'chat',
  HEALTH: 'health',
});


function isConfigured() {
  return Boolean(config.aiService.url && config.aiService.apiKey);
}

const REQUEST_ID_PATTERN = /^[A-Za-z0-9._:-]{1,128}$/;

function newRequestId(seed) {
  if (typeof seed === 'string' && REQUEST_ID_PATTERN.test(seed)) return seed;
  return crypto.randomUUID();
}

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

let cachedClient = null;
let cachedFor = null;

function http() {
  const base = config.aiService.url;
  if (cachedClient && cachedFor === base) return cachedClient;
  cachedClient = axios.create({
    baseURL: base,
    maxContentLength: 32 * 1024 * 1024,
    maxBodyLength: 64 * 1024 * 1024,
    validateStatus: (status) => status >= 200 && status < 300,
  });
  cachedFor = base;
  return cachedClient;
}

function resetClient() {
  cachedClient = null;
  cachedFor = null;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function logFailure(stage, requestId, detail) {
  if (config.isTest) return;
  console.warn(
    `[ai-service] stage=${stage} requestId=${requestId} outcome=failure ${detail}`
  );
}


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

function aiServiceErrorCode(response) {
  const code = response && response.data && response.data.error && response.data.error.code;
  return typeof code === 'string' ? code : null;
}

function mapAxiosError(err, stage) {
  const response = err && err.response;

  if (response) {
    const status = Number(response.status);
    const detail = `status=${status}`;

    if (status === 401 || status === 403) {
      return {
        retryable: false,
        detail,
        error: new ApiError(
          502,
          'AI_SERVICE_UNAUTHORIZED',
          'The analysis service rejected this deployment\'s credentials'
        ),
      };
    }

    if (status === 400 || status === 422) {
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

async function withRetry(stage, requestId, attempt, retries) {
  const maxExtra = Math.max(
    0,
    typeof retries === 'number' ? retries : config.aiService.retries
  );
  let lastError = null;

  for (let tryIndex = 0; tryIndex <= maxExtra; tryIndex += 1) {
    try {
      return await attempt();
    } catch (err) {
      if (err instanceof ApiError) throw err;

      const { error, retryable, detail } = mapAxiosError(err, stage);
      lastError = error;
      logFailure(stage, requestId, `${detail} attempt=${tryIndex + 1} retryable=${retryable}`);

      if (!retryable || tryIndex === maxExtra) throw error;
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


async function postJson({ path, stage, payload, requestId, timeoutMs, retries }) {
  if (!isConfigured()) throw notConfigured();

  return withRetry(stage, requestId, async () => {
    const res = await http().post(path, payload, {
      headers: { ...authHeaders(requestId), 'Content-Type': 'application/json' },
      timeout: timeoutMs,
    });
    return unwrapEnvelope(res.data, stage);
  }, retries);
}


async function engineerFeatures({ extraction, profile, requestId }) {
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


async function validateFeatures({ engineered, requestId }) {
  return postJson({
    path: PATHS.validate,
    stage: STAGES.VALIDATION,
    payload: { engineered },
    requestId,
    timeoutMs: config.aiService.validateTimeoutMs,
  });
}

async function evaluateRules({ validated, requestId }) {
  return postJson({
    path: PATHS.rules,
    stage: STAGES.RULES,
    payload: { validated },
    requestId,
    timeoutMs: config.aiService.rulesTimeoutMs,
  });
}

async function predict({ validated, requestId }) {
  return postJson({
    path: PATHS.predict,
    stage: STAGES.ML,
    payload: { validated },
    requestId,
    timeoutMs: config.aiService.mlTimeoutMs,
  });
}


async function generateReport({ validated, requestId }) {
  return postJson({
    path: PATHS.report,
    stage: STAGES.REPORT,
    payload: { validated },
    requestId,
    timeoutMs: config.aiService.reportTimeoutMs,
  });
}


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

async function describeParameters({ testNames, requestId }) {
  return postJson({
    path: PATHS.glossary,
    stage: STAGES.GLOSSARY,
    payload: {
      test_names: Array.isArray(testNames) ? testNames : [],
    },
    requestId,
    timeoutMs: config.aiService.glossaryTimeoutMs,
    retries: 0,
  });
}

async function classifyLabSeries({ series, requestId }) {
  return postJson({
    path: PATHS.labPolarity,
    stage: STAGES.LAB_POLARITY,
    payload: {
      series: Array.isArray(series) ? series : [],
    },
    requestId,
    timeoutMs: config.aiService.labPolarityTimeoutMs,
    retries: 0,
  });
}

async function matchLabNames({ names, requestId }) {
  return postJson({
    path: PATHS.labNameMatch,
    stage: STAGES.LAB_NAME_MATCH,
    payload: {
      names: Array.isArray(names) ? names : [],
    },
    requestId,
    timeoutMs: config.aiService.labNameMatchTimeoutMs,
    retries: 0,
  });
}


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


async function writeClinicianSummary({ summary, requestId }) {
  return postJson({
    path: PATHS.clinicianSummary,
    stage: STAGES.EXPLANATION,
    payload: { summary },
    requestId,
    timeoutMs: config.aiService.explainTimeoutMs,
  });
}

const FINGERPRINT_TTL_MS = 60 * 1000;
let fingerprintMemo = { value: null, at: 0 };

async function clinicianSummaryFingerprint() {
  if (!isConfigured()) return null;
  if (fingerprintMemo.value && Date.now() - fingerprintMemo.at < FINGERPRINT_TTL_MS) {
    return fingerprintMemo.value;
  }
  try {
    const res = await http().get(PATHS.clinicianFingerprint, {
      timeout: config.aiService.healthTimeoutMs,
      headers: authHeaders(newRequestId()),
    });
    const data = unwrapEnvelope(res.data, STAGES.EXPLANATION);
    const value = typeof data.fingerprint === 'string' && data.fingerprint ? data.fingerprint : null;
    if (value) fingerprintMemo = { value, at: Date.now() };
    return value;
  } catch (err) {
    return null;
  }
}

function resetFingerprintMemo() {
  fingerprintMemo = { value: null, at: 0 };
}

async function rewriteSummaryProse({ sentences, names, requestId }) {
  return postJson({
    path: PATHS.summaryProse,
    stage: STAGES.EXPLANATION,
    payload: { sentences, names: names || [] },
    requestId,
    timeoutMs: config.aiService.explainTimeoutMs,
  });
}

async function describeFindings({ findings, requestId }) {
  return postJson({
    path: PATHS.findingContext,
    stage: STAGES.EXPLANATION,
    payload: { findings },
    requestId,
    timeoutMs: config.aiService.findingContextTimeoutMs,
    retries: 0,
  });
}

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
      error: error.code,
      detail,
      latencyMs: Date.now() - startedAt,
      checkedAt,
    };
  }
}

async function chat({ question, report, requestId }) {
  const payload = { question };
  if (report) payload.report = report;
  return postJson({
    path: PATHS.chat,
    stage: STAGES.CHAT,
    payload,
    requestId,
    timeoutMs: config.aiService.chatTimeoutMs,
    retries: 0,
  });
}

async function waitUntilReady({
  maxWaitMs = config.aiService.wakeWaitMs,
  intervalMs = config.aiService.wakeIntervalMs,
} = {}) {
  const startedAt = Date.now();
  let attempts = 0;
  if (!isConfigured() || !(maxWaitMs > 0)) return { ready: false, attempts, waitedMs: 0 };
  for (;;) {
    attempts += 1;
    const verdict = await health();
    if (verdict.reachable) return { ready: true, attempts, waitedMs: Date.now() - startedAt };
    if (Date.now() - startedAt + intervalMs > maxWaitMs) {
      return { ready: false, attempts, waitedMs: Date.now() - startedAt };
    }
    await sleep(intervalMs);
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
  classifyLabSeries,
  matchLabNames,
  analyseTrends,
  compareReports,
  scoreProgress,
  generateDoctorSummary,
  writeClinicianSummary,
  clinicianSummaryFingerprint,
  resetFingerprintMemo,
  rewriteSummaryProse,
  describeFindings,
  populationContext,
  health,
  chat,
  waitUntilReady,
  resetClient,
  mapAxiosError,
  unwrapEnvelope,
  assertStorableKeys,
  readStreamToBuffer,
};
