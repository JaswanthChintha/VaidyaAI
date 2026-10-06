'use strict';

const Report = require('../models/Report');
const { REPORT_STATUS, deriveChronoDate } = require('../models/Report');
const { parsePrintedDate, printedDateText } = require('../utils/printedDate');
const { readPrintedIdentity } = require('../utils/printedIdentity');
const Profile = require('../models/Profile');
const ApiError = require('../utils/ApiError');
const config = require('../config/env');
const { getStorage } = require('../storage');
const { ALLOWED_TYPES } = require('../utils/fileSecurity');
const { ownerScopedFilter, OWNER_ONLY, toIdString } = require('../utils/ownership');
const aiService = require('./aiServiceClient');

/**
 * ORCHESTRATION: the layer that makes section 16's data flow real.
 *
 *   Upload (Module 3)
 *     -> OCR / Extraction            (Module 4)   POST /ocr/extract
 *     -> Feature Engineering         (Module 5)   POST /features/engineer
 *          + the caller's Module 2 profile
 *     -> Feature Validation          (Module 6)   POST /features/validate
 *     -> Clinical Rules (Module 8)  ||  ML Predictors (Modules 9/10)
 *          POST /rules/evaluate      ||  POST /ml/predict
 *          ||  Clinical Report       (Modules 17-20)  POST /report/generate
 *     -> Patient Explanation         (Module 23)  POST /explain/report
 *          ||  Lifestyle Guidance    (Module 26)  POST /explain/guidance
 *     -> persisted against the report
 *
 * WHY THE EXPLANATION IS A PIPELINE STAGE AND NOT AN ON-DEMAND CALL
 * ----------------------------------------------------------------
 *
 * There is a real argument for the other shape - the explanation needs a live
 * LLM round trip, it is the only stage after extraction that can be slow, and
 * it can legitimately produce nothing - so the decision is recorded here rather
 * than left implicit.
 *
 *   1. THE SPEC PUTS IT UPSTREAM OF THE DELIVERABLE. Section 16's flow is
 *      `... -> RAG || XAI -> LLM -> Safety Validation -> Final Health Report ->
 *      Dashboard | Timeline | Doctor Report`, and section 14's safety
 *      architecture ends `LLM Generation -> Medical Safety Validation -> User`.
 *      The explanation is not something bolted onto the report afterwards; it
 *      is part of what reaches the user. Making it a later, separate call would
 *      invert the spec's own ordering.
 *
 *   2. A SECOND GENERATION PATH IS A SECOND SOURCE OF TRUTH. An LLM is
 *      non-deterministic: two on-demand calls over the same findings produce
 *      two different explanations, and neither is the one the patient was
 *      shown. Generating once, inside the run, and storing the prose beside the
 *      safety verdict, the violation codes and the retrieval sources that
 *      produced it is what makes the patient-facing text AUDITABLE - which is
 *      the entire point of section 14. This project has already refused a
 *      second source of truth twice for weaker reasons (Module 7's repository,
 *      `/decisions/fuse`); it would be strange to accept one here, in the one
 *      place where the output is unreviewed prose.
 *
 *   3. "IT CAN FAIL" IS NOT AN ARGUMENT FOR SEPARATION - it is an argument for
 *      the stage class that already exists. Every refusal is an HTTP 200 with a
 *      structured fallback, so a withheld explanation is not a failure at all;
 *      and a genuine transport failure is handled exactly as the rules and ML
 *      stages' failures are - `partial`, with the report intact. Nothing about
 *      the failure modes needs a new endpoint.
 *
 *   4. AN ON-DEMAND ROUTE WOULD NEED ITS OWN LOCK, ITS OWN RATE LIMIT AND ITS
 *      OWN IDEMPOTENCY, all of which this file already implements once.
 *
 * THE COST, STATED PLAINLY: `analyze` gets slower, by one LLM round trip per
 * explained finding. That is why the stage has its OWN timeout (see
 * config/env.js) rather than the fast-stage or extraction budget, and why
 * `maxExplanations` is a config value. The real fix for a synchronous analyze
 * call is a background job queue, which is already recorded as known debt for
 * the extraction stage and applies here for the same reason.
 *
 * MODULE 25 (terminology) IS NOT A STAGE. It answers "what does <word> mean"
 * for a word a patient typed - a per-question lookup with no report input and
 * nothing to persist against a run. See aiServiceClient's header.
 *
 * All THREE of those run CONCURRENTLY. They take the same input (Module 6's
 * output) and none reads another's result, so running them in series would add
 * two round trips for nothing. Each is wrapped so it settles rather than
 * rejects: a failed rules call must never throw away a successful ML result or
 * a successful report, which is what a bare `Promise.all` would do.
 *
 * THE STAGE SEQUENCE, AND WHY `/decisions/fuse` IS NOT IN IT
 * ---------------------------------------------------------
 *
 * `POST /report/generate` runs the decision chain internally - Module 15's
 * collection, Module 16's fusion, then Modules 17-20 - and returns that exact
 * fusion object nested VERBATIM under `report.fusion`. Calling
 * `/decisions/fuse` as well would therefore:
 *
 *   - run the decision engine a second time for a result we are handed anyway;
 *   - produce TWO fusion objects that a non-deterministic predictor tie-break
 *     could make disagree, i.e. a second source of truth for the same facts -
 *     the exact reason Module 7's repository is not called either.
 *
 * So the fusion is READ OUT OF the report rather than fetched separately. One
 * call, one answer, and `analysis.stages.report` covers both modules.
 *
 * The rule and ML calls, by contrast, ARE kept even though `/report/generate`
 * re-derives them internally. That duplication is deliberate and bounded:
 *
 *   - This backend persists each stage's own output for auditability
 *     (`ruleDecisions`, `mlDecisions`), and the report's fused view cannot be
 *     un-fused back into them: Module 15 groups by (condition, source), so the
 *     per-RULE traceability that makes "which rule fired, on what evidence"
 *     answerable exists only in the standalone Module 8 response.
 *   - `/report/generate` contains an engine failure internally, as a
 *     `sources_failed` entry inside an HTTP 200. Without the standalone calls
 *     the backend could not say "the ML stage failed" at all - it would store a
 *     report that quietly rests on one source and call the run `processed`.
 *   - The cost is CPU on the Python side, not latency: the three calls run
 *     concurrently, and none of them touches Gemini. Nothing is re-extracted.
 *
 * If the ai-service ever grows a way to hand it pre-computed decisions over
 * HTTP, this is the seam to revisit.
 *
 * MODULE 7 (FEATURE REPOSITORY) IS DELIBERATELY NOT CALLED. The ai-service's
 * repository is IN-MEMORY and PROCESS-LOCAL - it does not survive a restart and
 * is not shared between workers, which its own module docstring says plainly.
 * MongoDB is this pipeline's durable store, so calling `/repository/load` would
 * put the same feature set in a second place with a different lifetime and no
 * owner scoping, i.e. a second source of truth that is guaranteed to disagree
 * with the first after any restart. Modules 8 and 9/10 take Module 6's output
 * directly, so the repository is not on the critical path at all. When it grows
 * a persistent backend, THAT is the moment to reconsider - not before.
 *
 * Everything crossing the process boundary goes through `aiServiceClient`.
 * This file owns the parts that are ours: the status lifecycle, the
 * concurrency lock, the profile payload, warning provenance, and the rule that
 * a failure never destroys a previous success.
 *
 * PARTIAL FAILURE - the rule this file enforces:
 *
 *   Stages 4 and 5 are LOAD-BEARING. If either fails, there is no result at
 *   all: nothing is persisted, `status` becomes `failed`, and any previous
 *   successful analysis survives untouched.
 *
 *   Stages 6, 8, 9/10, 17-20, 23 and 26 are NOT. If one of them fails, everything that
 *   succeeded is still persisted and returned, `status` becomes `partial`
 *   (never `processed` - a failed stage may not hide behind a success), and
 *   `analysis.stages` records which stage failed with which machine code.
 *   The failed stage's payload is UNSET rather than left alone, so a stale
 *   decision from a previous run can never sit beside this run's features and
 *   look current.
 *
 * PHI RULES:
 *   - `statusMessage` is produced by a TABLE LOOKUP on an error code
 *     (`safeStatusMessage`), never by formatting an error message. Module 3
 *     reserved that field on the condition that it never holds report text,
 *     and a lookup makes that structural rather than a promise.
 *   - Nothing here logs report text, extracted values, warnings, filenames or
 *     buffers. Only the correlation id and opaque ids.
 *   - The filename sent to the ai-service is SYNTHETIC, derived from the report
 *     id, not the user's original filename: a lab report is routinely named
 *     after the patient, and the service does not need it.
 */

/** Module 2 fields Module 5 consumes. Sent under Module 2's own camelCase names. */
const CLINICAL_PROFILE_FIELDS = Object.freeze([
  'age',
  'gender',
  'heightCm',
  'weightKg',
  'bmi',
  'hypertension',
  'heartDisease',
  'smokingHistory',
]);

/** mimeType -> the extension WE chose at upload. Never a client-supplied one. */
const EXTENSION_BY_MIME = Object.freeze(
  ALLOWED_TYPES.reduce((acc, type) => {
    acc[type.mimeType] = type.extension;
    return acc;
  }, {})
);

/**
 * The ONLY strings that may ever become a `statusMessage`.
 *
 * A failure message from the ai-service can quote report text, so interpolating
 * `err.message` here would put PHI into a field Module 3 explicitly reserved on
 * the condition that it never holds any. This table means an unrecognised error
 * degrades to a generic phrase rather than leaking - the failure mode is loss
 * of detail, which is the correct direction.
 */
const SAFE_STATUS_MESSAGES = Object.freeze({
  AI_SERVICE_NOT_CONFIGURED: 'The analysis service is not configured on this deployment',
  AI_SERVICE_UNAVAILABLE: 'The analysis service was unreachable',
  AI_SERVICE_TIMEOUT: 'The analysis service did not respond in time',
  AI_SERVICE_UNAUTHORIZED: 'The analysis service rejected this deployment\'s credentials',
  AI_SERVICE_REJECTED_INPUT: 'The analysis service could not process this report',
  AI_SERVICE_REJECTED_REQUEST: 'The analysis service rejected the request',
  AI_SERVICE_BUSY: 'The analysis service was busy',
  AI_SERVICE_ERROR: 'The analysis service failed to process this report',
  AI_SERVICE_MALFORMED_RESPONSE: 'The analysis service returned an unexpected response',
  AI_SERVICE_EMPTY_RESULT: 'The analysis service accounted for none of the extracted parameters',
  STORAGE_UNAVAILABLE: 'The storage backend for this report is not available',
  STORAGE_READ_FAILED: 'The stored report file could not be read',
  PAYLOAD_TOO_LARGE: 'The stored report file is too large to analyse',
  UNSUPPORTED_MEDIA_TYPE: 'The stored report file format is not supported',
  NOT_FOUND: 'The stored file for this report is no longer available',
  ANALYSIS_SUPERSEDED: 'A newer analysis of this report replaced this one',
  ANALYSIS_PARTIAL: 'Some analysis stages did not complete; see analysis.stages',
  ANALYSIS_STAGE_FAILED: 'An analysis stage failed',
});

/**
 * MODULE 23'S FIVE OUTCOMES, verbatim from `app/services/explanation.py`.
 *
 * Only `generated` means a patient-facing sentence exists. The other four are
 * HTTP 200 answers carrying a structured fallback, and every one of them is a
 * legitimate result that must reach the API unchanged - see
 * `normaliseExplanationSet` for the one thing this file adds to them.
 */
const EXPLANATION_OUTCOMES = Object.freeze({
  GENERATED: 'generated',
  WITHHELD_BY_SAFETY: 'withheld_by_safety',
  NOT_GROUNDED: 'not_grounded',
  MODEL_UNAVAILABLE: 'model_unavailable',
  UNKNOWN_SUBJECT: 'unknown_subject',
});
const EXPLANATION_OUTCOME_VALUES = Object.freeze(Object.values(EXPLANATION_OUTCOMES));

/**
 * THE ONLY STRINGS THIS BACKEND MAY EVER PUT IN A `notice`.
 *
 * The ai-service supplies its own reviewed wording for three of the four
 * non-generated outcomes, and `fallback.notice` covers the fourth
 * (`withheld_by_safety`, where `notice` is deliberately null because the
 * reviewed sentence lives on the fallback). This table is the LAST resort, for
 * a response that carries neither - a contract drift, or an outcome added on
 * the far side after this file was written.
 *
 * Same discipline as SAFE_STATUS_MESSAGES: a fixed table, never a formatted
 * string, so a notice can never come to hold a fragment of the refused text or
 * a value from the report. The wording deliberately mirrors the ai-service's
 * own: an explanation could not be produced, the structured findings are
 * unaffected, talk to a professional. It never apologises for a "failure",
 * because a withheld generation is the safety layer working.
 */
const EXPLANATION_NOTICES = Object.freeze({
  [EXPLANATION_OUTCOMES.WITHHELD_BY_SAFETY]:
    'A plain-language explanation was prepared for this finding but was not approved for release, so it is not shown. The structured findings are unaffected. A qualified healthcare professional can go through them with you.',
  [EXPLANATION_OUTCOMES.NOT_GROUNDED]:
    'No reviewed medical knowledge in this platform covers this finding closely enough to explain it, so no explanation was written. The structured findings are unaffected. A qualified healthcare professional can go through them with you.',
  [EXPLANATION_OUTCOMES.MODEL_UNAVAILABLE]:
    'The plain-language explanation service was not available, so no explanation was written. The structured findings were produced by the analysis itself and are unaffected. A qualified healthcare professional can go through them with you.',
  [EXPLANATION_OUTCOMES.UNKNOWN_SUBJECT]:
    'This finding is outside the set of parameters this platform can explain, so no explanation was written. The structured findings are unaffected. A qualified healthcare professional can go through them with you.',
});

/** For an outcome this build does not know, and for the set-level notice. */
const EXPLANATION_NOTICE_FALLBACK =
  'A plain-language explanation could not be prepared for this finding. The structured findings were produced by the analysis itself and are unaffected. A qualified healthcare professional can go through them with you.';

const EXPLANATION_SET_NOTICE =
  'No plain-language explanation could be prepared for this report. The structured findings below were produced by the analysis itself and are unaffected. A qualified healthcare professional can go through them with you.';

const GENERIC_STATUS_MESSAGE = 'The analysis could not be completed';

/**
 * @param {*} err
 * @returns {string} a message guaranteed to contain no report content.
 */
function safeStatusMessage(err) {
  const code = err && typeof err.code === 'string' ? err.code : null;
  if (code && Object.prototype.hasOwnProperty.call(SAFE_STATUS_MESSAGES, code)) {
    return `${code}: ${SAFE_STATUS_MESSAGES[code]}`;
  }
  return GENERIC_STATUS_MESSAGE;
}

// -------------------------------------------------------- stage outcomes ----

/** The six pipeline stages, in the order the data flows through them. */
const PIPELINE_STAGES = Object.freeze([
  aiService.STAGES.EXTRACTION, // Module 4
  aiService.STAGES.FEATURES, // Module 5
  aiService.STAGES.VALIDATION, // Module 6
  aiService.STAGES.RULES, // Module 8
  aiService.STAGES.ML, // Modules 9/10
  aiService.STAGES.REPORT, // Modules 17-20 (15/16 fused inside it)
  aiService.STAGES.EXPLANATION, // Module 23, gated by Module 24
  aiService.STAGES.GUIDANCE, // Module 26 (no model)
]);

/**
 * The ONLY reasons a stage may record for not having run.
 *
 * Same discipline as SAFE_STATUS_MESSAGES: a fixed table of our own machine
 * codes, so `analysis.stages` cannot become a place a service response body
 * leaks into.
 */
const STAGE_SKIP_REASONS = Object.freeze({
  VALIDATION_UNAVAILABLE:
    'Validation did not produce a result, so this stage had no validated input',
  REPORT_UNAVAILABLE:
    'The clinical report was not produced, so this stage had no findings to work from',
});

/**
 * An error's code, reduced to one this codebase defined.
 *
 * An error can carry any `code` at all - a driver error, an OS errno, or (the
 * case that matters) something built from a service response body. Only codes
 * present in the safe table are stored; anything else degrades to
 * `ANALYSIS_STAGE_FAILED`. Loss of detail is the correct failure direction.
 *
 * @param {*} err
 * @returns {string} a machine code that is provably not PHI.
 */
function safeErrorCode(err) {
  const code = err && typeof err.code === 'string' ? err.code : null;
  if (code && Object.prototype.hasOwnProperty.call(SAFE_STATUS_MESSAGES, code)) return code;
  return 'ANALYSIS_STAGE_FAILED';
}

/** A succeeded-stage record. */
const stageOk = (durationMs) => ({ ok: true, durationMs });

/** A failed-stage record: outcome plus a safe machine code, never a message. */
const stageFailed = (err, durationMs) => ({
  ok: false,
  errorCode: safeErrorCode(err),
  durationMs,
});

/** A stage that never ran because something it depended on did not produce input. */
const stageSkipped = (reasonCode) => ({ ok: false, skipped: true, reasonCode });

/**
 * Run one downstream stage, timing it, and never let it throw.
 *
 * @returns {Promise<{ value: object|null, record: object }>}
 */
async function runStage(fn) {
  const startedAt = Date.now();
  try {
    const value = await fn();
    return { value, record: stageOk(Date.now() - startedAt) };
  } catch (err) {
    return { value: null, record: stageFailed(err, Date.now() - startedAt) };
  }
}

// ------------------------------------------------------------- profile -----

/**
 * Build the profile payload for Module 5 from a Module 2 profile document.
 *
 * TRI-STATE, THE HIGHEST-RISK PATH IN THIS FILE.
 *
 * `hypertension` and `heartDisease` are tri-state in Module 2: `true`, `false`,
 * or ABSENT meaning unknown. Absent must stay absent all the way onto the wire.
 * Sending `false` for "we never asked" fabricates a negative clinical finding,
 * and Module 12's kidney predictor uses exactly that distinction to decide when
 * to skip - so collapsing it here would silently corrupt a prediction with no
 * error anywhere.
 *
 * The construction is therefore additive and has no defaults, no `||`, no `??`
 * and no destructuring with fallbacks: a key is written ONLY when the profile
 * actually carries a value. `false` is a value and is written; `undefined` and
 * `null` are not and are skipped, leaving the key genuinely missing from the
 * JSON body (`JSON.stringify` would drop an explicit `undefined` anyway, but
 * relying on that would leave `null` - which pydantic can read as a value -
 * one careless edit away).
 *
 * Field names are Module 2's camelCase, passed through untranslated: Module 5
 * accepts them directly via pydantic aliases (`smokingHistory`,
 * `heartDisease`). Renaming them here would be a second source of truth.
 *
 * @param {object|null} profile
 * @returns {object|undefined} undefined when there is nothing to send.
 */
function buildProfilePayload(profile) {
  if (!profile || typeof profile !== 'object') return undefined;

  const payload = {};
  for (const field of CLINICAL_PROFILE_FIELDS) {
    const value = profile[field];
    if (value === undefined || value === null) continue; // ABSENCE IS PRESERVED
    payload[field] = value;
  }

  return Object.keys(payload).length > 0 ? payload : undefined;
}

/**
 * The only person details sent for SOMEONE ELSE's report: the age and sex
 * typed for it on upload, or nothing. Never the account holder's profile.
 */
function subjectProfile(subject) {
  return {
    age: Number.isFinite(subject?.age) ? subject.age : undefined,
    gender: typeof subject?.sex === 'string' && subject.sex ? subject.sex : undefined,
  };
}

/**
 * The caller's own profile, or null.
 *
 * Module 2 answers 404 when a user has no profile, and the pipeline must still
 * run on lab data alone in that case - most first-time uploads have no profile
 * yet. This reads the model directly (same process, same ownership helper)
 * rather than calling our own HTTP API.
 */
async function loadOwnProfile(user) {
  const filter = ownerScopedFilter(user, { ...OWNER_ONLY });
  return Profile.findOne(filter);
}

// ------------------------------------------------------------ warnings -----

/**
 * Tag one warning with the stage it came from, WITHOUT flattening it.
 *
 * Module 4 emits warnings as strings; Module 5 propagates Module 4's warnings
 * into its own output with their origin preserved, so a warning arriving from
 * the features stage may already carry `stage`/`origin`/`source`. When it does,
 * that is the authoritative provenance and it is left exactly as it is - the
 * whole point of the propagation fix is that "the extraction stage repaired a
 * damaged page" must not become "the features stage said something".
 */
function tagWarning(warning, defaultStage) {
  if (warning === null || warning === undefined) return null;

  if (typeof warning === 'object' && !Array.isArray(warning)) {
    const carriesOrigin =
      typeof warning.stage === 'string' ||
      typeof warning.origin === 'string' ||
      typeof warning.source === 'string';
    // Spread preserves every field the service sent - code, page, severity,
    // anything added later - and adds `stage` only when nothing states it.
    return carriesOrigin ? { ...warning } : { ...warning, stage: defaultStage };
  }

  return { stage: defaultStage, message: String(warning) };
}

/** Stable identity for a warning, used only to drop exact repeats. */
function warningKey(warning) {
  return JSON.stringify([
    warning.stage || warning.origin || warning.source || '',
    warning.code || '',
    warning.message || warning.detail || warning.text || '',
  ]);
}

/**
 * Merge every warning source into one origin-tagged list.
 *
 * MODULE 5'S OUTPUT HAS FOUR RELEVANT KEYS, and picking the wrong one silently
 * loses data:
 *
 *   warnings[]           plain strings - MODULE 5'S OWN ONLY (kept for
 *                        backwards compatibility). Persisting only this is
 *                        exactly the bug that was just fixed on the Python
 *                        side: every Module 4 warning disappears.
 *   upstream_warnings[]  { stage, module, message } - Module 4's, verbatim.
 *   all_warnings[]       { stage, module, message } - BOTH, upstream first.
 *                        This is the authoritative list and is read first.
 *   upstream{}           provenance metadata (see summariseUpstream).
 *
 * `all_warnings` is consumed FIRST so that its richer entries (which carry
 * `module` as well as `stage`) win the de-duplication over anything this file
 * would have tagged itself. The remaining sources are then folded in as a
 * safety net: if the Python side ever regresses and stops propagating, Module
 * 4's own `warnings[]` still reaches the user from `extraction`. Losing a
 * warning is the failure this list exists to prevent, so every source is read
 * and only EXACT repeats (same origin, same code, same message) collapse.
 *
 * `stage` is `extraction` or `feature_engineering` on the Python side; nothing
 * here rewrites a stage that was stated.
 */
function collectWarnings(extraction, features, validation, rules, ml, report, extra) {
  const merged = [];
  const seen = new Set();

  const push = (list, defaultStage) => {
    if (!Array.isArray(list)) return;
    for (const raw of list) {
      const tagged = tagWarning(raw, defaultStage);
      if (!tagged) continue;
      const key = warningKey(tagged);
      if (seen.has(key)) continue;
      seen.add(key);
      merged.push(tagged);
    }
  };

  // EVERY stage is read, richest source first, and de-duplication is by
  // (origin, code, message) - so a warning that arrives five times because each
  // stage faithfully propagated it collapses to ONE entry with its ORIGINAL
  // origin, while a warning that only the last stage propagated still survives.
  //
  // Reading only the last stage's list would be the tempting simplification and
  // is exactly the defect this project has already shipped twice: Module 8 and
  // Module 10 forward their upstream, but a single regression anywhere in that
  // chain would silently erase every extraction warning, and a damaged,
  // partly-unreadable scan would become indistinguishable from a clean one.
  // MODULE 17'S LIST IS READ FIRST. `validation_warnings` is the report's own
  // contract for "every warning from every stage - extraction, feature
  // engineering, validation, rules, ml, fusion and report - with its origin
  // intact", so it is the richest source available and its entries win the
  // de-duplication. It is also the ONLY place Module 16's fusion warnings (an
  // abstaining predictor, a basis conflict) appear at all: nothing else in this
  // chain carries them, and they are exactly what tells a reader "the rules
  // flagged this, the model could not assess it".
  //
  // Every other source is still read below - the report list is preferred, not
  // trusted alone. This is the last hop, and dropping upstream warnings at the
  // last hop has been a real defect on this project twice.
  push(report && report.validation_warnings, aiService.STAGES.REPORT);
  push(report && report.fusion && report.fusion.all_warnings, aiService.STAGES.REPORT);

  push(rules && rules.all_warnings, aiService.STAGES.RULES);
  push(ml && ml.all_warnings, aiService.STAGES.ML);
  push(validation && validation.all_warnings, aiService.STAGES.VALIDATION);
  push(features && features.all_warnings, aiService.STAGES.FEATURES);

  // Each stage's OWN list, in case a downstream stage stopped propagating.
  push(rules && rules.upstream_warnings, aiService.STAGES.VALIDATION);
  push(rules && rules.warnings, aiService.STAGES.RULES);
  push(ml && ml.upstream_warnings, aiService.STAGES.VALIDATION);
  push(ml && ml.warnings, aiService.STAGES.ML);
  push(validation && validation.upstream_warnings, aiService.STAGES.FEATURES);
  push(validation && validation.warnings, aiService.STAGES.VALIDATION);
  push(features && features.upstream_warnings, aiService.STAGES.EXTRACTION);
  push(features && features.warnings, aiService.STAGES.FEATURES);
  // Last resort: Module 4's own list, straight off the extraction response.
  push(extraction && extraction.warnings, aiService.STAGES.EXTRACTION);

  // STAGES 23 AND 26, LAST AND ADDITIVE. They are appended rather than merged
  // ahead of anything, because they are the newest origins and must not be able
  // to win the de-duplication against an upstream entry that describes the same
  // words - `stage` is part of the key, so in practice they never collide, and
  // appending keeps that true by construction. `extra` is built by
  // `explanationWarnings`, whose messages come from a fixed table.
  push(extra, aiService.STAGES.EXPLANATION);

  return merged;
}

// ------------------------------------------------------------ decisions ----

/** Module 16's ordering: Low < Medium < High. `null` is NOT a risk level. */
const RISK_RANK = Object.freeze({ Low: 0, Medium: 1, High: 2 });

/**
 * The higher of two risk levels.
 *
 * An unrecognised value is treated as no value at all rather than being ranked
 * arbitrarily: "no decisions" must never silently become "low risk", and a
 * vocabulary drift must not fabricate a risk band this backend does not
 * understand.
 */
function highestRisk(...levels) {
  let best = null;
  for (const level of levels) {
    if (typeof level !== 'string') continue;
    if (!Object.prototype.hasOwnProperty.call(RISK_RANK, level)) continue;
    if (best === null || RISK_RANK[level] > RISK_RANK[best]) best = level;
  }
  return best;
}

const decisionsOf = (payload) =>
  Array.isArray(payload && payload.decisions) ? payload.decisions : null;

const summaryOf = (payload) =>
  payload && typeof payload.summary === 'object' && payload.summary ? payload.summary : {};

/** De-duplicated union of the `conditions_flagged` lists, strings only. */
function flaggedConditions(...payloads) {
  const seen = new Set();
  for (const payload of payloads) {
    const list = summaryOf(payload).conditions_flagged;
    if (!Array.isArray(list)) continue;
    for (const condition of list) if (typeof condition === 'string') seen.add(condition);
  }
  return [...seen];
}

/**
 * The always-loaded decision summary.
 *
 * Deliberately reports `undefined` rather than `0` for a stage that did not
 * run: "the rule engine produced no decisions" and "the rule engine did not
 * answer" are different facts, and collapsing them is the same class of error
 * as collapsing an absent tri-state into `false`.
 */
function summariseDecisions(rules, ml) {
  const ruleList = decisionsOf(rules);
  const mlList = decisionsOf(ml);
  const counted = [ruleList, mlList].filter(Array.isArray);

  return {
    ruleDecisionCount: ruleList ? ruleList.length : undefined,
    mlDecisionCount: mlList ? mlList.length : undefined,
    decisionCount: counted.length
      ? counted.reduce((total, list) => total + list.length, 0)
      : undefined,
    highestRisk:
      highestRisk(summaryOf(rules).highest_risk, summaryOf(ml).highest_risk) || undefined,
    conditionsFlagged: counted.length ? flaggedConditions(rules, ml) : undefined,
  };
}

/** Module 6's partition sizes, pulled up so a listing need not load the payload. */
function summariseValidation(validation) {
  if (!validation || typeof validation !== 'object') {
    return {
      validFeatureCount: undefined,
      questionableFeatureCount: undefined,
      rejectedFeatureCount: undefined,
    };
  }
  const size = (value) =>
    value && typeof value === 'object' && !Array.isArray(value)
      ? Object.keys(value).length
      : undefined;
  return {
    validFeatureCount: size(validation.valid),
    questionableFeatureCount: size(validation.questionable),
    rejectedFeatureCount: size(validation.rejected),
  };
}

// -------------------------------------------------- clinical report (17-20) --

/**
 * The THREE statuses spec Module 18 names. There is a fourth CASE, and it is
 * deliberately not a fourth value: `null`.
 */
const OVERALL_STATUS_VALUES = Object.freeze([
  'Healthy',
  'Needs Monitoring',
  'Needs Medical Attention',
]);

/**
 * The label for the case the spec does not name. A word that is NOT one of the
 * three, so a consumer that knows only the spec's vocabulary cannot read it as
 * one of them.
 */
const NOT_ASSESSED_LABEL = 'Not Assessed';

/**
 * THE FIFTH LABEL, and the reason this backend carries the service's label
 * instead of re-deriving one.
 *
 * `ai-service/app/schemas/report.py` declares FIVE values for `status_label`
 * (`OVERALL_STATUS_LABELS`) while `status` still holds only the spec's three or
 * `None`. The fifth exists because of integration audit D4: a report in which
 * exactly one clean value could be assessed used to be BYTE-IDENTICAL to a
 * report in which every topic was assessed and every one was clean - same
 * `status`, same `status_label`, same risk. `complete: false` and the caveat
 * were both present and correct, but the one string a card actually prints
 * showed no difference at all, so a label-only renderer told a patient with two
 * unassessed organ systems that they were "Healthy".
 *
 * This backend reintroduced exactly that defect one hop later by deriving the
 * label from `status` and never reading `overall.status_label`, which - by
 * construction - cannot produce a value the three-word vocabulary does not
 * contain. The producer is the source of truth for the wording; this file's job
 * is to VALIDATE it, not to invent it.
 */
const HEALTHY_PARTIAL_LABEL = 'Healthy (partial assessment)';

/**
 * The five labels `status_label` may hold, mirroring the producer's
 * `OVERALL_STATUS_LABELS`. Anything outside this list is a vocabulary we do not
 * understand and is refused, not rendered.
 */
const OVERALL_STATUS_LABEL_VALUES = Object.freeze([
  'Healthy',
  HEALTHY_PARTIAL_LABEL,
  'Needs Monitoring',
  'Needs Medical Attention',
  NOT_ASSESSED_LABEL,
]);

/**
 * Which labels may legitimately accompany which validated `status`.
 *
 * This is the pairing half of the check. A label from the right vocabulary can
 * still be the WRONG label for the status beside it - `status: null` with
 * `status_label: "Healthy"` is the single most dangerous pair this pipeline
 * could emit - so membership in the vocabulary is necessary and not sufficient.
 *
 * `Healthy` is the only status with two permitted labels: the bare word and its
 * partial-assessment qualification. Module 18 deliberately does NOT qualify
 * `Needs Monitoring` / `Needs Medical Attention`, on the grounds that a finding
 * that WAS made is not made less real by another topic going unassessed.
 */
const LABELS_PERMITTED_BY_STATUS = Object.freeze({
  Healthy: Object.freeze(['Healthy', HEALTHY_PARTIAL_LABEL]),
  'Needs Monitoring': Object.freeze(['Needs Monitoring']),
  'Needs Medical Attention': Object.freeze(['Needs Medical Attention']),
  // The key for `status === null`. Only ever the fourth-case label.
  __null__: Object.freeze([NOT_ASSESSED_LABEL]),
});

/**
 * Machine codes for the four ways the service's label and this backend's own
 * reading of the report can fail to agree. Fixed codes, never a formatted
 * string and never an echo of the offending value: these are persisted and
 * served, and §9's "never echo unsanitized input" applies to a peer service's
 * output for the same reason it applies to a client's.
 */
const STATUS_LABEL_DISAGREEMENTS = Object.freeze({
  /** No `status_label` at all. We fall back to deriving one - pessimistically. */
  MISSING: 'STATUS_LABEL_MISSING',
  /** A label from a vocabulary this backend does not know. */
  UNRECOGNISED: 'STATUS_LABEL_UNRECOGNISED',
  /** A known label that may not accompany this status (e.g. `null` + `Healthy`). */
  INCONSISTENT: 'STATUS_LABEL_INCONSISTENT_WITH_STATUS',
  /** `Healthy` vs `Healthy (partial assessment)` disagreeing with `complete`. */
  COMPLETENESS: 'STATUS_LABEL_COMPLETENESS_MISMATCH',
});

/**
 * IS THIS STORED VALUE A CLINICAL REPORT AT ALL?
 *
 * `Report.clinicalReport` is a `Mixed` field, so the schema stores whatever it
 * is handed. Nothing in the pipeline can put an array or a string there - the
 * ai-service's own response model forbids it and `summariseReport` below
 * already refuses both - so a value that fails this test means the DOCUMENT IS
 * CORRUPT, not that the caller asked for the wrong thing. It must still not
 * surface as a 500: a 500 says "the server is broken", tells the reader
 * nothing about their report, and on a non-production build carries a stack
 * trace with absolute paths in it. The truthful answer is the one an
 * unanalysed report already gets - there is no clinical report here.
 *
 * IT IS ONE EXPORTED PREDICATE BECAUSE THAT IS THE DEFECT THAT WAS FOUND. The
 * dashboard and doctor-summary controllers gated on a bare
 * `!report.clinicalReport`, which `[]` and `'oops'` both pass, while
 * `buildDashboard` required a plain object and threw. Two spellings of one
 * condition is how a gate and the thing it guards come to disagree.
 *
 * @param {*} value the stored `report.clinicalReport`.
 * @returns {boolean} true only for a plain object.
 */
function isUsableClinicalReport(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

/** Patient-safe wording for each code, from a fixed table. */
const STATUS_LABEL_DISAGREEMENT_MESSAGES = Object.freeze({
  [STATUS_LABEL_DISAGREEMENTS.MISSING]:
    'The analysis service did not state an overall status label for this report, so one was derived from the status it did state.',
  [STATUS_LABEL_DISAGREEMENTS.UNRECOGNISED]:
    'The analysis service returned an overall status label this system does not recognise, so the overall result is reported as not assessed.',
  [STATUS_LABEL_DISAGREEMENTS.INCONSISTENT]:
    'The analysis service returned an overall status label that does not match the overall status beside it, so the overall result is reported as not assessed.',
  [STATUS_LABEL_DISAGREEMENTS.COMPLETENESS]:
    'The analysis service reported a clean overall result whose label and completeness flag disagree, so it is shown as a partial assessment.',
});

/** Module 16's risk vocabulary. `null` is a legitimate value; `Low` is not a default. */
const RISK_VALUES = Object.freeze(['Low', 'Medium', 'High']);

/** Non-negative integer, or undefined. Never coerced, never defaulted to 0. */
function countOf(value) {
  return Number.isInteger(value) && value >= 0 ? value : undefined;
}

/**
 * The always-loaded summary of Modules 17-20's clinical report.
 *
 * THIS FUNCTION EXISTS TO PROTECT ONE PROPERTY: MODULE 18 HAS FOUR CASES AND
 * ALL FOUR MUST REACH THE API - AND THE CLEAN CASE HAS TWO LABELS, NOT ONE.
 *
 *   status null  + label 'Not Assessed'                    nothing assessed
 *   status 'Healthy' + label 'Healthy'                     everything assessed,
 *                                                          nothing abnormal
 *   status 'Healthy' + label 'Healthy (partial assessment)' nothing abnormal in
 *                                                          the part that could
 *                                                          be assessed
 *   status 'Needs Monitoring'                              abnormal, no High risk
 *   status 'Needs Medical Attention'                       abnormal + High risk
 *
 * `overallStatusLabel` IS CARRIED FROM THE SERVICE'S `overall.status_label`,
 * NOT RE-DERIVED FROM `overallStatus`.
 *
 * Re-deriving it was a real, shipped defect. `status` holds only the spec's
 * three words, so any label computed from it is structurally incapable of
 * expressing the fifth value the producer declares - and the fifth value exists
 * precisely because a partial clean result was otherwise indistinguishable from
 * a complete one. A report carrying only a normal HbA1c and a normal fasting
 * glucose, with heart and kidney unassessed, arrived here labelled
 * `Healthy (partial assessment)` and was rendered `Healthy`. That is the D4
 * defect Module 18 was amended to fix, reintroduced one hop later, and it is
 * why this function now reads the producer instead of guessing.
 *
 * WHAT REPLACES THE OLD "DERIVED IN ONE PLACE" GUARANTEE IS A CHECK, NOT TRUST.
 * The carried label is validated three ways before it is believed:
 *
 *   1. VOCABULARY. It must be one of `OVERALL_STATUS_LABEL_VALUES`, mirroring
 *      the producer's own five-valued `OVERALL_STATUS_LABELS`.
 *   2. PAIRING. It must be permitted for the validated `status`
 *      (`LABELS_PERMITTED_BY_STATUS`). `status: null` admits only
 *      `Not Assessed`, so a service claiming `status: null, status_label:
 *      "Healthy"` still cannot turn a null into a word.
 *   3. COMPLETENESS. Within the two Healthy labels, the label must agree with
 *      `overall.complete`. When it does not, the PESSIMISTIC reading wins and
 *      the partial label is shown: a clean bill that is only known to cover
 *      part of the report may not print as if it covered all of it.
 *
 * A failure of (1) or (2) means we do not understand the producer's answer, so
 * the whole overall verdict degrades exactly as an unrecognised `status` always
 * has: `overallStatus: null`, `overallStatusLabel: 'Not Assessed'`, both flags
 * false. This is the same "absence is not a value" rule the file already
 * applied to `status` - it now applies to the label the service actually
 * prints. It is deliberately NOT a downgrade to `Healthy`: an unknown must fail
 * towards "we cannot say", never towards a clean bill. It does mean a future
 * SIXTH label would hide a real abnormal finding behind "Not Assessed"; that is
 * accepted, because on this project `Not Assessed` is ranked ABOVE settled
 * normal findings by Module 19 and reads as an open question, whereas a
 * mis-rendered clean bill reads as a closed one.
 *
 * A failure of (1), (2) or (3), and an absent label, are each recorded in
 * `statusLabelDisagreement` as a fixed machine code and raised as a warning by
 * `statusLabelWarnings` - the check the header of this function used to claim
 * existed while `status_label` appeared nowhere in this file. Had it existed,
 * the defect above would have surfaced as a warning instead of shipping.
 *
 * Everything is validated against a fixed vocabulary and anything unrecognised
 * degrades TOWARDS "not assessed", never towards "healthy". A service that
 * started returning `status: "Fine"` must produce a report that says nothing
 * could be assessed, not one that says the patient is well.
 *
 * Returns `undefined` for every field when the report stage did not answer -
 * `undefined`, not `0` and not `null`, because "the report stage did not run"
 * and "the report ran and assessed nothing" are different facts and this
 * codebase has a standing rule against collapsing that distinction.
 *
 * @param {object|null} report the UNWRAPPED ClinicalReport, or null.
 */
function summariseReport(report) {
  const absent = {
    reportVersion: undefined,
    overallStatus: undefined,
    overallStatusLabel: undefined,
    statusLabelDisagreement: undefined,
    overallRisk: undefined,
    assessmentComplete: undefined,
    anyAssessed: undefined,
    conditionCount: undefined,
    criticalConditionCount: undefined,
    abnormalConditionCount: undefined,
    normalConditionCount: undefined,
    unassessedConditionCount: undefined,
    recommendationCount: undefined,
    laboratoryValueCount: undefined,
  };

  if (!report || typeof report !== 'object' || Array.isArray(report)) return absent;

  const overall =
    report.overall && typeof report.overall === 'object' && !Array.isArray(report.overall)
      ? report.overall
      : {};
  const summary =
    report.summary && typeof report.summary === 'object' && !Array.isArray(report.summary)
      ? report.summary
      : {};

  // THE FOURTH CASE. Only one of the three spec words survives; everything else
  // - null, undefined, a value from a future vocabulary - becomes `null`.
  let status = OVERALL_STATUS_VALUES.includes(overall.status) ? overall.status : null;

  // The producer's own completeness flag, read STRICTLY: a missing field means
  // "we do not know it was complete", and the safe reading of an unknown is the
  // pessimistic one. It is read here, before the label, because the label check
  // below is partly a check AGAINST it.
  const serviceSaysComplete = overall.complete === true;

  const rawLabel = typeof overall.status_label === 'string' ? overall.status_label : undefined;
  const permitted = LABELS_PERMITTED_BY_STATUS[status === null ? '__null__' : status];

  let statusLabel;
  let statusLabelDisagreement;

  if (rawLabel === undefined) {
    // NOTHING TO CARRY. Fall back to the old derivation - but pessimistically:
    // a `Healthy` status whose completeness was not affirmed prints as a
    // partial assessment, not as a clean bill. This is not a second source of
    // truth for the label; it is the floor that applies when the producer
    // stated no label at all, and it uses only the producer's own `complete`.
    statusLabel =
      status === null
        ? NOT_ASSESSED_LABEL
        : status === 'Healthy' && !serviceSaysComplete
          ? HEALTHY_PARTIAL_LABEL
          : status;
    statusLabelDisagreement = STATUS_LABEL_DISAGREEMENTS.MISSING;
  } else if (!OVERALL_STATUS_LABEL_VALUES.includes(rawLabel)) {
    // A vocabulary we do not understand. Degrade the whole verdict.
    status = null;
    statusLabel = NOT_ASSESSED_LABEL;
    statusLabelDisagreement = STATUS_LABEL_DISAGREEMENTS.UNRECOGNISED;
  } else if (!permitted.includes(rawLabel)) {
    // A known label that cannot accompany this status - `status: null` beside
    // `status_label: "Healthy"` is the case that matters. The label is never
    // believed over the status, and the pair is never rendered as either half.
    status = null;
    statusLabel = NOT_ASSESSED_LABEL;
    statusLabelDisagreement = STATUS_LABEL_DISAGREEMENTS.INCONSISTENT;
  } else if (
    status === 'Healthy' &&
    rawLabel !== (serviceSaysComplete ? 'Healthy' : HEALTHY_PARTIAL_LABEL)
  ) {
    // Both Healthy labels are permitted for a Healthy status, so only
    // `complete` can say which one is right. When the two contradict each
    // other, the pessimistic reading wins in BOTH directions: a bare `Healthy`
    // beside `complete: false` must not print as a complete clean bill, and a
    // partial label beside `complete: true` is left partial because the
    // producer's own wording is the more cautious of the two claims.
    statusLabel = HEALTHY_PARTIAL_LABEL;
    statusLabelDisagreement = STATUS_LABEL_DISAGREEMENTS.COMPLETENESS;
  } else {
    // Validated on all three counts: carried through verbatim.
    statusLabel = rawLabel;
  }

  // RISK. Three rules, in this order, and each one exists because the previous
  // shape of this code broke it.
  //
  // 1. THE PRODUCER'S OWN NULL IS AN ANSWER, NOT A GAP. `overall.risk: null`
  //    is Module 18 saying "there is no risk to state". The `key absent` case
  //    and the `key present and null` case are therefore distinguished with
  //    `hasOwnProperty`, not by testing the value: the previous
  //    `RISK_VALUES.includes(overall.risk)` test could not tell them apart, so
  //    an explicit null fell through to `report.overall_risk` and came back as
  //    `Low`. The top-level field is a FALLBACK for a report that stated no
  //    `overall` risk at all - never an override of one that stated null.
  //    (A key present with `undefined` is treated as absent. No JSON producer
  //    can send that, so it can only be a local construction that meant
  //    "unset"; `null` is the wire's way of saying "stated, and empty".)
  //
  // 2. AN UNRECOGNISED VALUE IS NULL, at whichever level it was read from. A
  //    vocabulary we do not understand is not evidence of low risk.
  //
  // 3. NOTHING ASSESSED CARRIES NO RISK. `status === null` is the fourth case
  //    - including the degradations decided above, where an unrecognised or
  //    impossible `status_label` pulled the whole verdict down to it. The risk
  //    goes with the verdict it qualifies; leaving it standing produced a card
  //    reading `Not Assessed` beside `Low`, which is the section 11 hazard
  //    ("absence must never become a value") in the one place a reader is most
  //    likely to take the reassuring half at face value. This is the same gate
  //    `complete` and `anyAssessed` below already apply, applied here too.
  const overallStatesRisk =
    Object.prototype.hasOwnProperty.call(overall, 'risk') && overall.risk !== undefined;
  const statedRisk = overallStatesRisk ? overall.risk : report.overall_risk;
  const risk =
    status !== null && RISK_VALUES.includes(statedRisk) ? statedRisk : null;

  // STRICT `=== true` ON BOTH FLAGS. A missing field means "we do not know it
  // was complete", which is not the same as complete, and the safe reading of
  // an unknown is the pessimistic one.
  const complete = overall.complete === true && status !== null;
  const anyAssessed = overall.any_assessed === true && status !== null;

  const listSize = (value) => (Array.isArray(value) ? value.length : undefined);

  return {
    reportVersion: typeof report.report_version === 'string' ? report.report_version : undefined,
    overallStatus: status,
    overallStatusLabel: statusLabel,
    // `undefined` when the service's label agreed with everything else about
    // this report - the normal case - so a reader can branch on its presence.
    statusLabelDisagreement,
    overallRisk: risk,
    assessmentComplete: complete,
    anyAssessed,
    conditionCount: countOf(summary.condition_count) ?? listSize(report.conditions),
    criticalConditionCount:
      countOf(summary.critical_count) ?? listSize(report.critical_conditions),
    abnormalConditionCount:
      countOf(summary.abnormal_count) ?? listSize(report.abnormal_findings),
    normalConditionCount: countOf(summary.normal_count) ?? listSize(report.normal_findings),
    unassessedConditionCount:
      countOf(summary.unassessed_count) ?? listSize(report.unassessed_conditions),
    recommendationCount:
      countOf(summary.recommendation_count) ?? listSize(report.recommendations),
    laboratoryValueCount:
      countOf(summary.laboratory_value_count) ?? listSize(report.laboratory_values),
  };
}

// ------------------------------------ patient explanation (23) / guidance (26) --

/**
 * KEYS THAT COULD CARRY REFUSED PROSE OR AN OFFENDING SPAN, stripped from
 * anything Module 23 or 26 returns, at every depth, before it is stored.
 *
 * THE AI-SERVICE ALREADY DOES NOT SEND THESE. `PatientExplanation.explanation`
 * is assigned in exactly one place, from `guarded_generation().approved_text`,
 * which is null unless Module 24 approved the text; the refused text is
 * discarded inside `guarded_generation` and `safe_fallback()` copies the
 * violation CODES across without reading the verdict's text or its span. This
 * list is therefore not a fix for a known leak - it is the structural guarantee
 * that the leak cannot appear later.
 *
 * That matters because the failure would be silent and permanent: a refused
 * sentence is by definition one the safety layer judged unsafe to show a
 * patient, and persisting it puts it in the database, in every backup, and one
 * careless renderer away from the screen it was withheld from. A `Mixed` field
 * stores whatever it is handed, so the check has to happen before the write.
 *
 * NOTE WHAT IS *NOT* HERE. Bare `text` is legitimate and load-bearing:
 * `fallback.recommendations[].text` and Module 26's `items[].text` are REVIEWED
 * CATALOGUE STRINGS, scanned at import on the Python side, and stripping them
 * would delete the very content a refusal falls back to. Only keys that name a
 * generation or a match are removed.
 */
const REFUSED_TEXT_KEYS = Object.freeze([
  'offending_span',
  'offending_spans',
  'span',
  'spans',
  'matched_text',
  'match',
  'matches',
  'excerpt',
  'snippet',
  'sample',
  'text_sample',
  'raw_text',
  'rejected_text',
  'refused_text',
  'candidate_text',
  'generated_text',
  'original_text',
  'unapproved_text',
  'draft',
  'prompt',
  'prompt_text',
  'modifications',
]);

const REFUSED_TEXT_KEY_SET = new Set(REFUSED_TEXT_KEYS);

/**
 * Deep copy with every `REFUSED_TEXT_KEYS` entry removed.
 *
 * REMOVES rather than blanks: a key present with an empty value invites a
 * renderer to show an empty quote box, and a key that is absent cannot be
 * rendered at all. Depth-capped for the same reason `assertStorableKeys` is.
 */
function stripRefusedText(value, depth = 0) {
  if (depth > 32) return null;
  if (Array.isArray(value)) return value.map((item) => stripRefusedText(item, depth + 1));
  if (!value || typeof value !== 'object') return value;

  const out = {};
  for (const [key, item] of Object.entries(value)) {
    if (REFUSED_TEXT_KEY_SET.has(key)) continue;
    out[key] = stripRefusedText(item, depth + 1);
  }
  return out;
}

/** A usable patient-facing sentence, or null. Never `''`, never whitespace. */
function approvedText(value) {
  return typeof value === 'string' && value.trim().length > 0 ? value : null;
}

/**
 * Normalise ONE explanation so a renderer can never mistake "nothing was
 * approved" for "nothing to say".
 *
 * THE PROBLEM THIS SOLVES. A UI that branches on the presence of a string sees
 * a withheld explanation and an absent one identically - both are "no text" -
 * and the natural rendering of "no text" is nothing at all. The patient is then
 * shown a report with a blank space where the platform's own safety layer
 * refused to speak, and no indication that anything was withheld. That is the
 * exact failure Module 23's five-outcome contract exists to prevent, and it can
 * be reintroduced by one careless `{explanation && <p>...</p>}`.
 *
 * So this adds two DERIVED fields and changes nothing else:
 *
 *   generated_explanation_available   the boolean a renderer must branch on.
 *                                     Derived here and NOWHERE ELSE, so it
 *                                     cannot drift from the text it describes.
 *                                     (`overallStatusLabel` used to be cited
 *                                     here as the same pattern. It is not one:
 *                                     it is now CARRIED from the producer and
 *                                     checked, because the producer's label
 *                                     vocabulary is strictly larger than the
 *                                     status vocabulary it was derived from.)
 *   notice                            guaranteed non-empty whenever that
 *                                     boolean is false, so there is always
 *                                     something to show. The service's own
 *                                     wording wins; `fallback.notice` is next
 *                                     (it is the reviewed sentence for the
 *                                     `withheld_by_safety` case, where `notice`
 *                                     is deliberately null); the fixed table is
 *                                     the last resort.
 *
 * `outcome` IS NEVER REWRITTEN. It is the service's verdict on its own
 * generation and it is persisted exactly as received, including a value this
 * build does not recognise. `explanation` is forced to `null` when there is no
 * approved text - never `''`, which is a string a renderer will happily print
 * as a blank paragraph.
 *
 * THE ONE CASE WHERE THE TWO DISAGREE: `outcome: "generated"` with no text.
 * That is a contract break on the far side. The outcome is still stored
 * faithfully, but `generated_explanation_available` is false and a notice is
 * filled in, so the disagreement degrades towards "we cannot show you an
 * explanation" and never towards a blank pretending to be one.
 */
function normaliseExplanation(item) {
  if (!item || typeof item !== 'object' || Array.isArray(item)) return item;

  const clean = stripRefusedText(item);
  const outcome = typeof clean.outcome === 'string' ? clean.outcome : null;
  const text =
    outcome === EXPLANATION_OUTCOMES.GENERATED ? approvedText(clean.explanation) : null;

  if (text !== null) {
    return { ...clean, explanation: text, generated_explanation_available: true, notice: null };
  }

  const fallbackNotice =
    clean.fallback && typeof clean.fallback === 'object'
      ? approvedText(clean.fallback.notice)
      : null;

  return {
    ...clean,
    explanation: null,
    generated_explanation_available: false,
    notice:
      approvedText(clean.notice) ||
      fallbackNotice ||
      EXPLANATION_NOTICES[outcome] ||
      EXPLANATION_NOTICE_FALLBACK,
  };
}

/**
 * Normalise the whole `ReportExplanationSet` before it is persisted.
 *
 * The set-level `explanation_available` and `notice` exist for the same reason
 * the per-item ones do, one level up: a report where EVERY finding was withheld
 * must not render as a report with an empty explanations section. The counts
 * are recomputed from the normalised items rather than trusted from the
 * service's own `generated_count`, so the number shown can never disagree with
 * the number of items that actually carry text.
 */
function normaliseExplanationSet(set) {
  if (!set || typeof set !== 'object' || Array.isArray(set)) return null;

  const clean = stripRefusedText(set);
  const items = Array.isArray(clean.explanations)
    ? clean.explanations.map(normaliseExplanation)
    : [];

  const generated = items.filter(
    (item) => item && item.generated_explanation_available === true
  ).length;
  const available = generated > 0;

  return {
    ...clean,
    explanations: items,
    // RECOMPUTED, not forwarded: these are what a UI counts on.
    generated_count: generated,
    withheld_count: items.length - generated,
    explanation_count: items.length,
    explanation_available: available,
    notice: available ? null : EXPLANATION_SET_NOTICE,
  };
}

/** Module 26's answer, put through the same strip. Catalogue text only. */
function normaliseGuidance(guidance) {
  if (!guidance || typeof guidance !== 'object' || Array.isArray(guidance)) return null;
  return stripRefusedText(guidance);
}

/**
 * The always-loaded explanation summary.
 *
 * `undefined` for every field when the stage did not answer - the same rule the
 * decision and report summaries follow, and for the same reason: "no
 * explanation was approved" and "the explanation stage never ran" are different
 * facts, and only the first of them is something to tell a patient.
 *
 * `explanationOutcomes` is a COUNT PER OUTCOME rather than a list, because the
 * question an operator asks is "how often is the safety layer refusing", which
 * a list of the same word repeated does not answer.
 */
function summariseExplanation(set) {
  if (!set || typeof set !== 'object') {
    return {
      explanationAvailable: undefined,
      explanationCount: undefined,
      explanationGeneratedCount: undefined,
      explanationWithheldCount: undefined,
      explanationOutcomes: undefined,
    };
  }

  const items = Array.isArray(set.explanations) ? set.explanations : [];
  const outcomes = {};
  for (const item of items) {
    const outcome =
      item && typeof item.outcome === 'string' && item.outcome ? item.outcome : 'unknown';
    outcomes[outcome] = (outcomes[outcome] || 0) + 1;
  }

  return {
    explanationAvailable: set.explanation_available === true,
    explanationCount: items.length,
    explanationGeneratedCount: countOf(set.generated_count) ?? 0,
    explanationWithheldCount: countOf(set.withheld_count) ?? 0,
    explanationOutcomes: outcomes,
  };
}

/**
 * The status-label check, expressed as a warning.
 *
 * THIS IS THE SAFETY NET FOR EXACTLY ONE CLASS OF DRIFT: the producer changing
 * what it says about the overall result while this backend keeps rendering the
 * old vocabulary. It fires whenever `summariseReport` could not take
 * `overall.status_label` at face value - a missing label, a label from a
 * vocabulary this file does not know, a label that may not accompany its
 * status, or a Healthy label contradicting `overall.complete`.
 *
 * It exists because this function's absence was itself a defect: the header of
 * `summariseReport` asserted that "the service's own `status_label` is checked
 * against ours and a disagreement is recorded as a warning-worthy fact", while
 * `status_label` appeared NOWHERE in this file. Nothing was checked and nothing
 * was recorded, so the label defect above shipped silently. A comment asserting
 * a guarantee is not a guarantee; this is the guarantee.
 *
 * The message comes from a FIXED TABLE and the code is one of four constants -
 * the offending value is never echoed into a persisted warning.
 *
 * @param {object} summary the result of `summariseReport`.
 */
function statusLabelWarnings(summary) {
  const code = summary && summary.statusLabelDisagreement;
  if (typeof code !== 'string') return [];

  return [
    {
      stage: aiService.STAGES.REPORT,
      module: 'module-18-overall-status',
      code,
      message:
        STATUS_LABEL_DISAGREEMENT_MESSAGES[code] ||
        'The overall status label reported by the analysis service could not be used as given.',
    },
  ];
}

/** Module 26's summary. `undefined` when the stage did not answer. */
function summariseGuidance(guidance) {
  if (!guidance || typeof guidance !== 'object') {
    return { guidanceItemCount: undefined, guidanceGenerated: undefined };
  }
  return {
    guidanceItemCount: Array.isArray(guidance.items) ? guidance.items.length : 0,
    // Module 26 asserts `generated: false` in its own payload so the absence of
    // a model call is checkable from the data rather than from a docstring.
    // Stored as-is; a `true` here would be a defect worth seeing, not hiding.
    guidanceGenerated: guidance.generated === true,
  };
}

/**
 * The explanation stage's OWN warnings.
 *
 * Module 23 emits no stage-tagged warning list of its own - its outcomes ARE
 * its warnings - so this is where they enter `all_warnings` with an origin, so
 * that "the safety layer withheld an explanation" appears in the same list, and
 * with the same shape, as "page 1 was recovered by the PDF repairer". A reader
 * of the warnings alone must be able to tell that something was withheld.
 *
 * MESSAGES COME FROM A TABLE AND ARE NEVER FORMATTED. No count, no feature
 * name, no subject is interpolated - the counts are in
 * `analysis.explanationOutcomes` and the per-finding detail is in the stored
 * payload. This is the same structural PHI guarantee `statusMessage` and
 * `analysis.stages` carry, applied to the one stage whose input is prose.
 */
function explanationWarnings(set) {
  if (!set || typeof set !== 'object') return [];

  const items = Array.isArray(set.explanations) ? set.explanations : [];
  const warnings = [];
  const seenOutcomes = new Set();

  for (const item of items) {
    if (!item || item.generated_explanation_available === true) continue;
    const outcome = typeof item.outcome === 'string' ? item.outcome : 'unknown';
    if (seenOutcomes.has(outcome)) continue;
    seenOutcomes.add(outcome);
    warnings.push({
      stage: aiService.STAGES.EXPLANATION,
      module: 'module-23-explanation',
      code: `EXPLANATION_${String(outcome).toUpperCase()}`,
      message: EXPLANATION_NOTICES[outcome] || EXPLANATION_NOTICE_FALLBACK,
    });
  }

  // The whole-report case, raised even when the per-finding warnings above
  // already say why: a consumer scanning for one code should not have to know
  // all five outcome names to discover that nothing at all was explained.
  if (items.length > 0 && set.explanation_available !== true) {
    warnings.push({
      stage: aiService.STAGES.EXPLANATION,
      module: 'module-23-explanation',
      code: 'EXPLANATION_UNAVAILABLE',
      message: EXPLANATION_SET_NOTICE,
    });
  }

  return warnings;
}

/**
 * What Module 26 is asked about, read out of Module 17's report.
 *
 * CANONICAL NAMES ONLY, and the service reports anything it does not recognise
 * under `unknown_conditions` / `unknown_features` rather than silently
 * answering about nothing - so a vocabulary drift is visible in the stored
 * payload instead of producing plausible guidance about the wrong thing.
 *
 * Only USABLE laboratory values are sent, matching Module 23's own rule: a
 * value the validator refused to trust must not pull lifestyle guidance towards
 * itself. Both lists are capped at the service's `max_length=16`, which is a
 * 422 if exceeded.
 */
/**
 * Every test on the report that this platform does not assess.
 *
 * Joins Module 5's `unmapped` list back to Module 4's extraction, which is
 * where the printed name survives -- feature engineering drops the parameter
 * and everything on it.
 *
 * NAMES ONLY, AND THAT IS THE CONTRACT DOWNSTREAM. What goes to the model is
 * a test NAME with no value, no interval and no flag attached (§6v), so the
 * description it produces is about the test and never about this reader.
 */
function unmappedTestNames(features, extraction) {
  const unmapped = Array.isArray(features?.unmapped) ? features.unmapped : [];
  if (!unmapped.length) return [];

  const skipped = new Set(
    unmapped
      .map((entry) => (entry && typeof entry.test_name === 'string' ? entry.test_name : null))
      .filter(Boolean)
  );
  if (!skipped.size) return [];

  const parameters = Array.isArray(extraction?.extracted_parameters)
    ? extraction.extracted_parameters
    : [];

  const names = [];
  for (const parameter of parameters) {
    const name = parameter && typeof parameter.test_name === 'string' ? parameter.test_name : null;
    if (!name || !skipped.has(name)) continue;
    // EVERY UNASSESSED TEST, on the reader's instruction. This used to take
    // only the ones the laboratory had marked abnormal -- the values a reader
    // stops on -- because describing all of them is what spends a free-tier
    // day. The reader asked why so many parameters had no description, which
    // is a fair question about a section titled "What these results mean":
    // a test listed with no explanation reads as one nobody could explain.
    //
    // The cost is bounded in two places, not here: the ai-service caps a
    // single request (`MAX_PER_REQUEST`) and caches every answer under the
    // normalised test NAME, so a common panel is described once and reused by
    // every later report.
    if (!names.includes(name)) names.push(name);
  }
  return names;
}

function guidanceInputs(report) {
  if (!report || typeof report !== 'object') return { conditions: [], features: [] };

  const conditions = [];
  for (const condition of Array.isArray(report.conditions) ? report.conditions : []) {
    const name = condition && condition.condition;
    if (typeof name === 'string' && name && !conditions.includes(name)) conditions.push(name);
  }

  const features = [];
  for (const row of Array.isArray(report.laboratory_values) ? report.laboratory_values : []) {
    if (!row || row.usable !== true) continue;
    const name = row.feature;
    if (typeof name === 'string' && name && !features.includes(name)) features.push(name);
  }

  return { conditions: conditions.slice(0, 16), features: features.slice(0, 16) };
}

/**
 * Provenance Module 5 forwards under `upstream` - which pages could not be
 * read, and how confident the extraction was.
 *
 * `pages_unreadable` is the difference between "this test is not on the report"
 * and "we could not read the page it was on", and Module 17 has to be able to
 * say which. It is pulled up into the always-loaded `analysis` metadata so a
 * consumer does not have to fetch the whole payload to find out.
 */
function summariseUpstream(extraction, features) {
  const upstream = (features && features.upstream) || {};

  const pagesUnreadable = Array.isArray(upstream.pages_unreadable)
    ? upstream.pages_unreadable.filter((page) => Number.isFinite(page))
    : [];

  const confidence = [upstream.extraction_confidence, extraction && extraction.extraction_confidence]
    .find((value) => typeof value === 'number');

  return { pagesUnreadable, extractionConfidence: confidence };
}

/**
 * Strip bulk report text from the extraction before it is stored.
 *
 * The ai-service deliberately does not carry `raw_text` forward per page - it
 * forwards `{ page_number, raw_text_available }` plus `pages_unreadable[]` -
 * because the full text of a lab report is the largest concentration of PHI in
 * the whole pipeline. The same principle applies to what we PERSIST: the
 * structured `extracted_parameters` are what every downstream module (6, 7, 10-12,
 * 17) actually consumes, and keeping a verbatim copy of the report text in a
 * second place multiplies the blast radius of any database exposure for no
 * consumer that exists.
 *
 * The FULL extraction is still sent to Module 5 - only the stored copy is
 * reduced - and the original file remains downloadable through Module 3, so
 * nothing is irrecoverable.
 */
function redactExtraction(extraction) {
  if (!extraction || typeof extraction !== 'object') return extraction;

  const { raw_text: rawText, pages, ...rest } = extraction;

  const redacted = { ...rest };
  // Record that text existed without keeping it.
  redacted.raw_text_available = typeof rawText === 'string' && rawText.length > 0;

  if (Array.isArray(pages)) {
    redacted.pages = pages.map((page) => {
      if (!page || typeof page !== 'object') return page;
      const { raw_text: pageText, ...pageRest } = page;
      return {
        ...pageRest,
        raw_text_available: typeof pageText === 'string' && pageText.length > 0,
      };
    });
  }

  return redacted;
}

/**
 * Reject a feature-engineering response that succeeded but produced nothing.
 *
 * THIS IS A REAL, OBSERVED SILENT FAILURE, not a hypothetical. Relaying Module
 * 4's `{ success, data }` envelope to `/features/engineer` instead of the
 * unwrapped `data` used to be accepted with HTTP 200 and `features: {}` - a
 * pipeline wired that way looks perfectly healthy on every dashboard and
 * produces nothing at all. The Python side now rejects the ambiguous form, but
 * "200 with an empty result" is precisely the shape a future contract drift
 * would take, so it is checked here too rather than trusted.
 *
 * The check is narrow on purpose. An extraction that found no lab parameters
 * legitimately yields no features, and a report whose parameters were all
 * rejected legitimately yields none either - but in that case Module 5 lists
 * them in `unmapped`/`duplicates_resolved`, proving it saw them. Only the
 * combination "the extraction had parameters AND Module 5 accounted for none of
 * them" is the wiring failure.
 */
function assertProductiveFeatures(extraction, features) {
  const parameters = Array.isArray(extraction && extraction.extracted_parameters)
    ? extraction.extracted_parameters.length
    : 0;
  if (parameters === 0) return; // nothing to account for

  const accountedFor =
    Object.keys((features && features.features) || {}).length +
    (Array.isArray(features && features.unmapped) ? features.unmapped.length : 0) +
    (Array.isArray(features && features.duplicates_resolved)
      ? features.duplicates_resolved.length
      : 0);

  if (accountedFor === 0) {
    throw new ApiError(
      502,
      'AI_SERVICE_EMPTY_RESULT',
      'The analysis service accounted for none of the extracted parameters'
    );
  }
}

// ---------------------------------------------------------------- lock -----

/**
 * Atomically move a report into `processing`, or refuse.
 *
 * CONCURRENCY. Two simultaneous `POST /reports/:id/analyze` calls must not both
 * run: they would each spend a multi-second LLM call and then interleave their
 * writes, and the loser's extraction could land on top of the winner's
 * features. The lock is a single conditional `findOneAndUpdate` - the claim and
 * the test are one atomic Mongo operation, so there is no window between them.
 * A second caller matches nothing and gets 409.
 *
 * STALE LOCKS. A process that dies mid-analysis would otherwise leave the
 * report in `processing` forever, permanently unanalysable. A claim is
 * therefore also allowed when the existing `processing` state is older than
 * `AI_SERVICE_LOCK_TTL_MS` (default 10 min, comfortably above the ~20 s a real
 * extraction takes), or when it carries no start time at all.
 *
 * The filter is owner-scoped, so this is additionally incapable of touching
 * another user's report.
 *
 * @returns {Promise<object|null>} the claimed report, or null if refused.
 */
async function claimForAnalysis({ user, reportId, requestId, now = new Date() }) {
  const staleBefore = new Date(now.getTime() - config.aiService.lockTtlMs);
  const filter = ownerScopedFilter(user, {
    ...OWNER_ONLY,
    base: {
      _id: reportId,
      $or: [
        { status: { $ne: REPORT_STATUS.PROCESSING } },
        { 'analysis.startedAt': { $lt: staleBefore } },
        { 'analysis.startedAt': { $exists: false } },
      ],
    },
  });

  return Report.findOneAndUpdate(
    filter,
    {
      $set: {
        status: REPORT_STATUS.PROCESSING,
        'analysis.requestId': requestId,
        'analysis.startedAt': now,
        // Step 1 begins the moment the lock is taken.
        'analysis.progressStep': 'reading',
        'analysis.progressAt': now,
      },
      $unset: { statusMessage: '', 'analysis.completedAt': '', 'analysis.durationMs': '' },
      $inc: { 'analysis.runCount': 1 },
    },
    { new: true }
  );
}

/**
 * Record which step a running analysis has reached (2026-10-04), for the
 * Reports page's progress bar.
 *
 * NEVER FAILS THE RUN. Progress is a courtesy to the reader; a write that
 * does not land leaves the bar on the previous step and nothing else. The
 * filter carries this run's `requestId`, so a run that lost its lock cannot
 * move a newer run's bar.
 */
async function markStep(ownerFilter, step) {
  try {
    await Report.updateOne(ownerFilter, {
      $set: { 'analysis.progressStep': step, 'analysis.progressAt': new Date() },
    });
  } catch {
    // Deliberately ignored -- see above.
  }
}

// ------------------------------------------------------------- pipeline -----

/**
 * Open a fresh read stream for the report's stored bytes.
 *
 * A FACTORY, not a stream: a retried attempt cannot replay a consumed stream.
 * The key is opaque and only the adapter that produced it may resolve it - no
 * path is ever constructed here.
 */
async function openStorage(report) {
  let storage;
  try {
    storage = getStorage(report.storageDriver);
  } catch (err) {
    // A row naming a driver this build does not register.
    throw new ApiError(
      503,
      'STORAGE_UNAVAILABLE',
      'The storage backend for this report is not available'
    );
  }

  // `stat` normally returns null for a missing file, but a tampered or
  // adapter-rejected key can make it throw. That throw would be an unmapped
  // error class reaching the stack-printing 500 branch - the D1 defect shape -
  // so it is converted here to the same clean 404 a missing file produces. A
  // key that cannot be resolved and a key that resolves to nothing are the same
  // fact from the caller's point of view, and neither discloses anything.
  let stats = null;
  try {
    stats = await storage.stat(report.storageKey);
  } catch (err) {
    stats = null;
  }
  if (!stats) {
    throw ApiError.notFound('The stored file for this report is no longer available');
  }

  return () => storage.createReadStream(report.storageKey);
}

/**
 * Stages 6, 8, 9/10, 17-20, 23 and 26.
 *
 * NEVER THROWS. Every failure is captured as a stage record, because none of
 * these stages is allowed to destroy a result the expensive stages already
 * produced. The caller decides what that means for `status`.
 *
 * A WITHHELD EXPLANATION IS NOT A FAILED STAGE. Modules 23 and 26 answer 200
 * for every outcome they have, refusals included, so the explanation stage is
 * `ok` whenever the call returned - and `analysis.explanationAvailable` plus
 * the stored outcomes say whether anything was actually approved. Marking the
 * stage failed because the safety layer did its job would turn a sound analysis
 * into a `partial` one and, worse, would train an operator to read a working
 * safety gate as an outage.
 *
 * SEQUENCING:
 *   validation runs first - Modules 8, 9/10 and 17-20 all consume its output.
 *   rules, ML and the clinical report then run CONCURRENTLY: none of them reads
 *   another's result. The report endpoint re-derives the decisions it needs
 *   in-process (see the file header for why that duplication is deliberate),
 *   so it genuinely does not depend on the two calls beside it and there is no
 *   reason to make it wait for them.
 *   Each is wrapped in `runStage`, which SETTLES instead of rejecting, so the
 *   surrounding `Promise.all` cannot short-circuit - one stage failing can
 *   never discard another's result, which a bare `Promise.all` over the three
 *   raw calls would do.
 *
 * WHEN VALIDATION FAILS, all three are SKIPPED rather than re-pointed at
 * Module 5's output. The ai-service would accept `engineered` and validate
 * in-process, which is tempting - but the decisions, and the report built on
 * them, would then rest on a validation this backend never saw and never
 * stored, so the stored evidence would not explain the stored conclusion. A
 * recorded skip is honest; a silently different input path is not.
 *
 * @returns {Promise<{validation: object|null, rules: object|null, ml: object|null,
 *                    report: object|null, stages: Record<string, object>}>}
 */
async function runDownstreamStages({
  features,
  extraction = null,
  requestId,
  // Told when a progress step begins ('deciding', 'explaining'). Optional.
  onStep = async () => {},
}) {
  const stages = {};

  const validationRun = await runStage(() =>
    aiService.validateFeatures({ engineered: features, requestId })
  );
  stages[aiService.STAGES.VALIDATION] = validationRun.record;
  const validation = validationRun.value;

  if (!validation) {
    const skipped = stageSkipped('VALIDATION_UNAVAILABLE');
    stages[aiService.STAGES.RULES] = skipped;
    stages[aiService.STAGES.ML] = skipped;
    stages[aiService.STAGES.REPORT] = skipped;
    // Modules 23 and 26 read the clinical report, which was never built.
    stages[aiService.STAGES.EXPLANATION] = stageSkipped('REPORT_UNAVAILABLE');
    stages[aiService.STAGES.GUIDANCE] = stageSkipped('REPORT_UNAVAILABLE');
    return {
      validation: null,
      rules: null,
      ml: null,
      report: null,
      explanation: null,
      guidance: null,
      stages,
    };
  }

  await onStep('deciding');
  const [rulesRun, mlRun, reportRun] = await Promise.all([
    runStage(() => aiService.evaluateRules({ validated: validation, requestId })),
    runStage(() => aiService.predict({ validated: validation, requestId })),
    runStage(() => aiService.generateReport({ validated: validation, requestId })),
  ]);
  stages[aiService.STAGES.RULES] = rulesRun.record;
  stages[aiService.STAGES.ML] = mlRun.record;
  stages[aiService.STAGES.REPORT] = reportRun.record;

  const clinicalReport = reportRun.value;

  // --- Modules 23 and 26 -----------------------------------------------------
  //
  // THESE TWO RUN AFTER THE REPORT, NOT BESIDE IT, because the report IS their
  // input: `explain_report` walks its `laboratory_values` for the values it may
  // explain and its `conditions` for what each one contributed to, and Module 26
  // is asked about the conditions and features that report actually names. There
  // is nothing to explain until it exists. This is the one place in the pipeline
  // where a serial hop is unavoidable rather than a missed optimisation.
  //
  // WITH each other they ARE concurrent: neither reads the other's result, one
  // is an LLM round trip and the other is a catalogue lookup, and running them
  // in series would add the cheap one's latency to the expensive one's for
  // nothing. Both settle rather than reject, so a withheld or failed explanation
  // can never discard the guidance beside it - and vice versa.
  if (!clinicalReport) {
    const skipped = stageSkipped('REPORT_UNAVAILABLE');
    stages[aiService.STAGES.EXPLANATION] = skipped;
    stages[aiService.STAGES.GUIDANCE] = skipped;
    return {
      validation,
      rules: rulesRun.value,
      ml: mlRun.value,
      report: null,
      explanation: null,
      guidance: null,
      stages,
    };
  }

  // NOTE the names: `features` is already this function's parameter (Module 5's
  // whole output object), and Module 26 wants a list of canonical feature NAMES
  // read out of the report. Two different things - kept textually distinct so a
  // future edit cannot pass one where the other belongs.
  const guidanceAsk = guidanceInputs(clinicalReport);

  // WHICH SKIPPED TESTS ARE WORTH A DESCRIPTION.
  //
  // A report can carry sixty parameters this platform does not assess, and
  // describing all of them would spend a free-tier day's quota on "Urine
  // Colour: Pale Yellow". The ones that matter are the ones THE LABORATORY
  // ITSELF marked outside its own range -- those are the values a reader will
  // stop on, and the ones a doctor will want raised. Everything else is still
  // listed on the dashboard, just without a description.
  const glossaryAsk = unmappedTestNames(features, extraction);

  await onStep('explaining');
  const [explanationRun, guidanceRun, glossaryRun] = await Promise.all([
    runStage(() => aiService.explainReport({ report: clinicalReport, requestId })),
    runStage(() =>
      aiService.lifestyleGuidance({
        conditions: guidanceAsk.conditions,
        features: guidanceAsk.features,
        requestId,
      })
    ),
    // Skipped entirely when there is nothing to describe, so a report whose
    // every parameter is understood costs no extra model call.
    glossaryAsk.length
      ? runStage(() =>
          aiService.describeParameters({ testNames: glossaryAsk, requestId })
        )
      : Promise.resolve({ value: null, record: null }),
  ]);
  stages[aiService.STAGES.EXPLANATION] = explanationRun.record;
  stages[aiService.STAGES.GUIDANCE] = guidanceRun.record;
  if (glossaryRun.record) stages[aiService.STAGES.GLOSSARY] = glossaryRun.record;

  return {
    validation,
    rules: rulesRun.value,
    ml: mlRun.value,
    report: clinicalReport,
    explanation: explanationRun.value,
    parameterGlossary: glossaryRun.value,
    guidance: guidanceRun.value,
    stages,
  };
}

/** PHI-free filename for the outgoing multipart part. */
function syntheticFilename(report) {
  const extension = EXTENSION_BY_MIME[report.mimeType] || '.bin';
  return `report-${report._id.toString()}${extension}`;
}

/**
 * Run extraction + feature engineering for one already-claimed report and
 * persist the outcome.
 *
 * RE-RUN SEMANTICS: OVERWRITE, NOT VERSIONED.
 *
 * A successful re-run replaces `extraction`, `features` and `analysisWarnings`
 * wholesale and increments `analysis.version`. There is exactly one current
 * analysis per report. History is deliberately NOT kept here: retaining every
 * run's full report text would multiply the most sensitive documents in the
 * database for no consumer that exists yet, and the versioned store is Module
 * 7's job (the Feature Repository), not an ad-hoc one invented in the interim.
 * `analysis.version` is the hook Module 7 will need.
 *
 * A FAILED re-run is non-destructive: the failure path writes only `status`,
 * `statusMessage` and the timing fields, so a report that was analysed
 * successfully yesterday still returns yesterday's analysis from
 * `GET /:id/analysis` after today's attempt fails. `status` reflects the LATEST
 * ATTEMPT; `analysis.version` and `analysis.completedAt` describe the stored
 * payload. Re-running is therefore always safe.
 *
 * Both terminal writes are conditioned on `analysis.requestId` still matching
 * this run, so a run whose stale lock was taken over by a newer one can never
 * overwrite the newer run's result or mark its success as failed.
 */
async function runAnalysis({ user, report, requestId }) {
  const startedAt = Date.now();
  const ownerFilter = ownerScopedFilter(user, {
    ...OWNER_ONLY,
    base: { _id: report._id, 'analysis.requestId': requestId },
  });

  try {
    const streamFactory = await openStorage(report);

    const extraction = await aiService.extract({
      streamFactory,
      filename: syntheticFilename(report),
      mimeType: report.mimeType,
      requestId,
    });
    await markStep(ownerFilter, 'checking');

    // NOTE the unwrap: `aiService.extract` already returns the `data` object,
    // and `engineerFeatures` sends it under `extraction`. Passing the wrapped
    // `{ success, data }` envelope here would break the pipeline silently.
    // WHOSE REPORT (2026-10-03). For someone else's report the ACCOUNT's
    // profile is not loaded at all -- not its age or sex, and not its BMI,
    // smoking, blood pressure or heart history, which describe the account
    // holder and would otherwise be applied to another person's blood. Only
    // what was typed for this report is sent, in the profile's own field
    // names; a value the report PRINTS still wins inside Module 5, exactly as
    // it does for the owner's reports.
    const profile =
      report.subject?.owner === 'other'
        ? buildProfilePayload(subjectProfile(report.subject))
        : buildProfilePayload(await loadOwnProfile(user));

    // The FULL extraction goes to Module 5 (it is the pinned contract); only
    // the copy we persist is reduced.
    const features = await aiService.engineerFeatures({ extraction, profile, requestId });

    // A 200 that accounted for nothing is a failure, not a success.
    assertProductiveFeatures(extraction, features);

    // Stages 6, 8 and 9/10. None of them can fail the run - see the header.
    const downstream = await runDownstreamStages({
      features,
      extraction,
      requestId,
      onStep: (step) => markStep(ownerFilter, step),
    });
    const { validation, rules, ml, report: clinicalReport } = downstream;

    // MODULE 23'S PAYLOAD IS NORMALISED BEFORE IT IS LOOKED AT AT ALL, so that
    // every later reader - the warning builder, the summary, the write - sees
    // the same object the patient will, with refused prose already impossible
    // and `generated_explanation_available` already derived. Doing it here, at
    // the single point the payload enters this file, is what makes "no refused
    // text is ever persisted" a property of the code path rather than of five
    // call sites remembering.
    const explanation = normaliseExplanationSet(downstream.explanation);
    const guidance = normaliseGuidance(downstream.guidance);
    // Descriptions of tests this platform does not assess. Optional by
    // design: `null` whenever nothing needed describing or the stage failed,
    // and `store()` unsets the field rather than persisting an empty shell.
    const parameterGlossary = downstream.parameterGlossary || null;

    const stages = {
      [aiService.STAGES.EXTRACTION]: stageOk(undefined),
      [aiService.STAGES.FEATURES]: stageOk(undefined),
      ...downstream.stages,
    };
    const stagesFailed = PIPELINE_STAGES.filter((stage) => !(stages[stage] || {}).ok);

    // COMPUTED BEFORE THE WARNINGS, not after, because the status-label check
    // it performs is itself warning-worthy: a disagreement between the
    // service's `status_label` and the rest of its own report has to reach
    // `analysisWarnings`, not just the derived summary, or nobody sees it.
    const reportCounts = summariseReport(clinicalReport);

    const warnings = collectWarnings(
      extraction,
      features,
      validation,
      rules,
      ml,
      clinicalReport,
      // Both lists carry their OWN `stage`, so `tagWarning` leaves the origin
      // alone: the label warning is stamped `report` (Module 18's stage), not
      // `explanation`, even though it travels in the same argument.
      [...explanationWarnings(explanation), ...statusLabelWarnings(reportCounts)]
    );
    const upstream = summariseUpstream(extraction, features);
    const decisions = summariseDecisions(rules, ml);
    const validationCounts = summariseValidation(validation);
    const explanationCounts = summariseExplanation(explanation);
    const guidanceCounts = summariseGuidance(guidance);
    const completedAt = new Date();

    const $set = {
      // NEVER `processed` while a stage is failed - see REPORT_STATUS.PARTIAL.
      status: stagesFailed.length === 0 ? REPORT_STATUS.PROCESSED : REPORT_STATUS.PARTIAL,
      extraction: redactExtraction(extraction),
      features,
      analysisWarnings: warnings,
      'analysis.completedAt': completedAt,
      'analysis.durationMs': Date.now() - startedAt,
      'analysis.profileUsed': Boolean(profile),
      'analysis.extractionConfidence': upstream.extractionConfidence,
      'analysis.pagesUnreadable': upstream.pagesUnreadable,
      'analysis.warningCount': warnings.length,
      'analysis.stages': stages,
      'analysis.stagesFailed': stagesFailed,
    };
    const $unset = {};

    // A stage that did not answer has its payload and its derived metadata
    // REMOVED, not left as it was. Leaving a previous run's rule decisions
    // beside this run's features would present stale clinical conclusions about
    // a report whose values may have changed - the failure is visible in
    // `analysis.stages`, but nobody reads that before reading the decisions.
    const store = (path, value) => {
      if (value === undefined || value === null) $unset[path] = '';
      else $set[path] = value;
    };
    /**
     * Same rule, but `null` IS A VALUE.
     *
     * `analysis.overallStatus` and `analysis.overallRisk` are Module 18's
     * fourth case: "we assessed nothing", written as an explicit `null`. Only
     * `undefined` - the report stage did not answer at all - unsets them.
     * Routing these through `store()` above would erase the fourth case into
     * "absent" and lose exactly the distinction this pass exists to preserve.
     */
    const storeNullable = (path, value) => {
      if (value === undefined) $unset[path] = '';
      else $set[path] = value;
    };

    store('featureValidation', validation);
    store('ruleDecisions', rules);
    store('mlDecisions', ml);
    store('clinicalReport', clinicalReport);
    store('patientExplanation', explanation);
    store('lifestyleGuidance', guidance);
    store('parameterGlossary', parameterGlossary);
    for (const [key, value] of Object.entries({
      ...decisions,
      ...validationCounts,
      ...explanationCounts,
      ...guidanceCounts,
    })) {
      store(`analysis.${key}`, value);
    }
    for (const [key, value] of Object.entries(reportCounts)) {
      storeNullable(`analysis.${key}`, value);
    }

    // THE DATE THE DOCUMENT PRINTS, read from THIS run's extraction. Extraction
    // returned it on every report and nothing read it, so two reports printing
    // 05-Sep-2026 sat on the timeline as 9 and 11 September -- the dates typed
    // at upload -- with nothing saying the document disagreed. See
    // `utils/printedDate` for what is refused rather than guessed.
    //
    // `chronoDate` IS RECOMPUTED HERE because `updateOne` skips the schema's
    // pre-validate hook, by the same function that hook uses.
    const printed = parsePrintedDate(printedDateText(extraction), {
      notAfter: report.uploadedAt,
    });
    $set.printedDateStatus = printed.status;
    store('printedDate', printed.date);
    store('printedDateRaw', printed.raw);
    $set.chronoDate = deriveChronoDate({
      reportDate: report.reportDate,
      printedDate: printed.date,
      uploadedAt: report.uploadedAt,
    });

    // THE SEX AND AGE THE DOCUMENT PRINTS, from this run's extraction. Unset
    // -- "nobody looked" -- when the extraction carries no such keys, which a
    // re-run against an older ai-service would; never an empty "checked".
    store('printedIdentity', readPrintedIdentity(extraction));

    if (stagesFailed.length === 0) {
      $unset.statusMessage = '';
    } else {
      // TABLE LOOKUP, never a formatted string: which stages failed is in
      // `analysis.stages`, which is built from machine codes only.
      $set.statusMessage = safeStatusMessage({ code: 'ANALYSIS_PARTIAL' });
    }

    // A finished run has no current step.
    $unset['analysis.progressStep'] = '';
    $unset['analysis.progressAt'] = '';

    const result = await Report.updateOne(ownerFilter, {
      $set,
      $unset,
      $inc: { 'analysis.version': 1 },
    });

    if (result.matchedCount === 0) {
      // Our lock was taken over by a newer run (only possible after the stale
      // TTL). The newer run owns the report; we discard our result rather than
      // clobber theirs.
      throw new ApiError(
        409,
        'ANALYSIS_SUPERSEDED',
        'A newer analysis of this report replaced this one'
      );
    }

    return {
      warnings,
      profileUsed: Boolean(profile),
      stages,
      stagesFailed,
      partial: stagesFailed.length > 0,
    };
  } catch (err) {
    // Failure path. It writes NOTHING to extraction/features/analysisWarnings
    // and does not touch analysis.version, so any previous successful analysis
    // survives intact.
    await Report.updateOne(ownerFilter, {
      $set: {
        status: REPORT_STATUS.FAILED,
        statusMessage: safeStatusMessage(err),
        'analysis.completedAt': new Date(),
        'analysis.durationMs': Date.now() - startedAt,
      },
      $unset: { 'analysis.progressStep': '', 'analysis.progressAt': '' },
    }).catch(() => {
      // A bookkeeping write must never mask the real failure.
    });
    throw err;
  }
}

module.exports = {
  CLINICAL_PROFILE_FIELDS,
  SAFE_STATUS_MESSAGES,
  GENERIC_STATUS_MESSAGE,
  PIPELINE_STAGES,
  STAGE_SKIP_REASONS,
  RISK_RANK,
  safeStatusMessage,
  safeErrorCode,
  highestRisk,
  summariseDecisions,
  summariseValidation,
  summariseReport,
  // The single spelling of "there is a clinical report stored here", shared by
  // every controller that gates a route on it. See its own comment.
  isUsableClinicalReport,
  OVERALL_STATUS_VALUES,
  OVERALL_STATUS_LABEL_VALUES,
  LABELS_PERMITTED_BY_STATUS,
  NOT_ASSESSED_LABEL,
  HEALTHY_PARTIAL_LABEL,
  STATUS_LABEL_DISAGREEMENTS,
  STATUS_LABEL_DISAGREEMENT_MESSAGES,
  statusLabelWarnings,
  EXPLANATION_OUTCOMES,
  EXPLANATION_OUTCOME_VALUES,
  EXPLANATION_NOTICES,
  EXPLANATION_NOTICE_FALLBACK,
  EXPLANATION_SET_NOTICE,
  REFUSED_TEXT_KEYS,
  stripRefusedText,
  normaliseExplanation,
  normaliseExplanationSet,
  normaliseGuidance,
  summariseExplanation,
  summariseGuidance,
  explanationWarnings,
  guidanceInputs,
  // Exported to be tested directly: it decides which test names are sent to
  // the glossary stage, and both of its failure modes are expensive -- too
  // wide burns a free-tier day's quota, too narrow silently drops the
  // laboratory's own abnormal markings from the description it deserves.
  unmappedTestNames,
  runDownstreamStages,
  buildProfilePayload,
  subjectProfile,
  loadOwnProfile,
  tagWarning,
  collectWarnings,
  summariseUpstream,
  redactExtraction,
  assertProductiveFeatures,
  claimForAnalysis,
  runAnalysis,
  syntheticFilename,
  toIdString,
};
