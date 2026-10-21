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

const EXTENSION_BY_MIME = Object.freeze(
  ALLOWED_TYPES.reduce((acc, type) => {
    acc[type.mimeType] = type.extension;
    return acc;
  }, {})
);

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
  NO_LAB_RESULTS: 'No test results were found in this file',
  STORAGE_UNAVAILABLE: 'The storage backend for this report is not available',
  STORAGE_READ_FAILED: 'The stored report file could not be read',
  PAYLOAD_TOO_LARGE: 'The stored report file is too large to analyse',
  UNSUPPORTED_MEDIA_TYPE: 'The stored report file format is not supported',
  NOT_FOUND: 'The stored file for this report is no longer available',
  ANALYSIS_SUPERSEDED: 'A newer analysis of this report replaced this one',
  ANALYSIS_PARTIAL: 'Some analysis stages did not complete; see analysis.stages',
  ANALYSIS_STAGE_FAILED: 'An analysis stage failed',
});

const EXPLANATION_OUTCOMES = Object.freeze({
  GENERATED: 'generated',
  WITHHELD_BY_SAFETY: 'withheld_by_safety',
  NOT_GROUNDED: 'not_grounded',
  MODEL_UNAVAILABLE: 'model_unavailable',
  UNKNOWN_SUBJECT: 'unknown_subject',
});
const EXPLANATION_OUTCOME_VALUES = Object.freeze(Object.values(EXPLANATION_OUTCOMES));

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

const EXPLANATION_NOTICE_FALLBACK =
  'A plain-language explanation could not be prepared for this finding. The structured findings were produced by the analysis itself and are unaffected. A qualified healthcare professional can go through them with you.';

const EXPLANATION_SET_NOTICE =
  'No plain-language explanation could be prepared for this report. The structured findings below were produced by the analysis itself and are unaffected. A qualified healthcare professional can go through them with you.';

const GENERIC_STATUS_MESSAGE = 'The analysis could not be completed';

function safeStatusMessage(err) {
  const code = err && typeof err.code === 'string' ? err.code : null;
  if (code && Object.prototype.hasOwnProperty.call(SAFE_STATUS_MESSAGES, code)) {
    return `${code}: ${SAFE_STATUS_MESSAGES[code]}`;
  }
  return GENERIC_STATUS_MESSAGE;
}


const PIPELINE_STAGES = Object.freeze([
  aiService.STAGES.EXTRACTION,
  aiService.STAGES.FEATURES,
  aiService.STAGES.VALIDATION,
  aiService.STAGES.RULES,
  aiService.STAGES.ML,
  aiService.STAGES.REPORT,
  aiService.STAGES.EXPLANATION,
  aiService.STAGES.GUIDANCE,
]);

const STAGE_SKIP_REASONS = Object.freeze({
  VALIDATION_UNAVAILABLE:
    'Validation did not produce a result, so this stage had no validated input',
  REPORT_UNAVAILABLE:
    'The clinical report was not produced, so this stage had no findings to work from',
});

function safeErrorCode(err) {
  const code = err && typeof err.code === 'string' ? err.code : null;
  if (code && Object.prototype.hasOwnProperty.call(SAFE_STATUS_MESSAGES, code)) return code;
  return 'ANALYSIS_STAGE_FAILED';
}

const stageOk = (durationMs) => ({ ok: true, durationMs });

const stageFailed = (err, durationMs) => ({
  ok: false,
  errorCode: safeErrorCode(err),
  durationMs,
});

const stageSkipped = (reasonCode) => ({ ok: false, skipped: true, reasonCode });

async function runStage(fn) {
  const startedAt = Date.now();
  try {
    const value = await fn();
    return { value, record: stageOk(Date.now() - startedAt) };
  } catch (err) {
    return { value: null, record: stageFailed(err, Date.now() - startedAt) };
  }
}


function buildProfilePayload(profile) {
  if (!profile || typeof profile !== 'object') return undefined;

  const payload = {};
  for (const field of CLINICAL_PROFILE_FIELDS) {
    const value = profile[field];
    if (value === undefined || value === null) continue;
    payload[field] = value;
  }

  return Object.keys(payload).length > 0 ? payload : undefined;
}

function subjectProfile(subject) {
  return {
    age: Number.isFinite(subject?.age) ? subject.age : undefined,
    gender: typeof subject?.sex === 'string' && subject.sex ? subject.sex : undefined,
  };
}

async function loadOwnProfile(user) {
  const filter = ownerScopedFilter(user, { ...OWNER_ONLY });
  return Profile.findOne(filter);
}


function tagWarning(warning, defaultStage) {
  if (warning === null || warning === undefined) return null;

  if (typeof warning === 'object' && !Array.isArray(warning)) {
    const carriesOrigin =
      typeof warning.stage === 'string' ||
      typeof warning.origin === 'string' ||
      typeof warning.source === 'string';
    return carriesOrigin ? { ...warning } : { ...warning, stage: defaultStage };
  }

  return { stage: defaultStage, message: String(warning) };
}

function warningKey(warning) {
  return JSON.stringify([
    warning.stage || warning.origin || warning.source || '',
    warning.code || '',
    warning.message || warning.detail || warning.text || '',
  ]);
}

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

  push(report && report.validation_warnings, aiService.STAGES.REPORT);
  push(report && report.fusion && report.fusion.all_warnings, aiService.STAGES.REPORT);

  push(rules && rules.all_warnings, aiService.STAGES.RULES);
  push(ml && ml.all_warnings, aiService.STAGES.ML);
  push(validation && validation.all_warnings, aiService.STAGES.VALIDATION);
  push(features && features.all_warnings, aiService.STAGES.FEATURES);

  push(rules && rules.upstream_warnings, aiService.STAGES.VALIDATION);
  push(rules && rules.warnings, aiService.STAGES.RULES);
  push(ml && ml.upstream_warnings, aiService.STAGES.VALIDATION);
  push(ml && ml.warnings, aiService.STAGES.ML);
  push(validation && validation.upstream_warnings, aiService.STAGES.FEATURES);
  push(validation && validation.warnings, aiService.STAGES.VALIDATION);
  push(features && features.upstream_warnings, aiService.STAGES.EXTRACTION);
  push(features && features.warnings, aiService.STAGES.FEATURES);
  push(extraction && extraction.warnings, aiService.STAGES.EXTRACTION);

  push(extra, aiService.STAGES.EXPLANATION);

  return merged;
}


const RISK_RANK = Object.freeze({ Low: 0, Medium: 1, High: 2 });

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

function flaggedConditions(...payloads) {
  const seen = new Set();
  for (const payload of payloads) {
    const list = summaryOf(payload).conditions_flagged;
    if (!Array.isArray(list)) continue;
    for (const condition of list) if (typeof condition === 'string') seen.add(condition);
  }
  return [...seen];
}

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


const OVERALL_STATUS_VALUES = Object.freeze([
  'Healthy',
  'Needs Monitoring',
  'Needs Medical Attention',
]);

const NOT_ASSESSED_LABEL = 'Not Assessed';

const HEALTHY_PARTIAL_LABEL = 'Healthy (partial assessment)';

const OVERALL_STATUS_LABEL_VALUES = Object.freeze([
  'Healthy',
  HEALTHY_PARTIAL_LABEL,
  'Needs Monitoring',
  'Needs Medical Attention',
  NOT_ASSESSED_LABEL,
]);

const LABELS_PERMITTED_BY_STATUS = Object.freeze({
  Healthy: Object.freeze(['Healthy', HEALTHY_PARTIAL_LABEL]),
  'Needs Monitoring': Object.freeze(['Needs Monitoring']),
  'Needs Medical Attention': Object.freeze(['Needs Medical Attention']),
  __null__: Object.freeze([NOT_ASSESSED_LABEL]),
});

const STATUS_LABEL_DISAGREEMENTS = Object.freeze({
  MISSING: 'STATUS_LABEL_MISSING',
  UNRECOGNISED: 'STATUS_LABEL_UNRECOGNISED',
  INCONSISTENT: 'STATUS_LABEL_INCONSISTENT_WITH_STATUS',
  COMPLETENESS: 'STATUS_LABEL_COMPLETENESS_MISMATCH',
});

function isUsableClinicalReport(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

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

const RISK_VALUES = Object.freeze(['Low', 'Medium', 'High']);

function countOf(value) {
  return Number.isInteger(value) && value >= 0 ? value : undefined;
}

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

  let status = OVERALL_STATUS_VALUES.includes(overall.status) ? overall.status : null;

  const serviceSaysComplete = overall.complete === true;

  const rawLabel = typeof overall.status_label === 'string' ? overall.status_label : undefined;
  const permitted = LABELS_PERMITTED_BY_STATUS[status === null ? '__null__' : status];

  let statusLabel;
  let statusLabelDisagreement;

  if (rawLabel === undefined) {
    statusLabel =
      status === null
        ? NOT_ASSESSED_LABEL
        : status === 'Healthy' && !serviceSaysComplete
          ? HEALTHY_PARTIAL_LABEL
          : status;
    statusLabelDisagreement = STATUS_LABEL_DISAGREEMENTS.MISSING;
  } else if (!OVERALL_STATUS_LABEL_VALUES.includes(rawLabel)) {
    status = null;
    statusLabel = NOT_ASSESSED_LABEL;
    statusLabelDisagreement = STATUS_LABEL_DISAGREEMENTS.UNRECOGNISED;
  } else if (!permitted.includes(rawLabel)) {
    status = null;
    statusLabel = NOT_ASSESSED_LABEL;
    statusLabelDisagreement = STATUS_LABEL_DISAGREEMENTS.INCONSISTENT;
  } else if (
    status === 'Healthy' &&
    rawLabel !== (serviceSaysComplete ? 'Healthy' : HEALTHY_PARTIAL_LABEL)
  ) {
    statusLabel = HEALTHY_PARTIAL_LABEL;
    statusLabelDisagreement = STATUS_LABEL_DISAGREEMENTS.COMPLETENESS;
  } else {
    statusLabel = rawLabel;
  }

  const overallStatesRisk =
    Object.prototype.hasOwnProperty.call(overall, 'risk') && overall.risk !== undefined;
  const statedRisk = overallStatesRisk ? overall.risk : report.overall_risk;
  const risk =
    status !== null && RISK_VALUES.includes(statedRisk) ? statedRisk : null;

  const complete = overall.complete === true && status !== null;
  const anyAssessed = overall.any_assessed === true && status !== null;

  const listSize = (value) => (Array.isArray(value) ? value.length : undefined);

  return {
    reportVersion: typeof report.report_version === 'string' ? report.report_version : undefined,
    overallStatus: status,
    overallStatusLabel: statusLabel,
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

function approvedText(value) {
  return typeof value === 'string' && value.trim().length > 0 ? value : null;
}

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
    generated_count: generated,
    withheld_count: items.length - generated,
    explanation_count: items.length,
    explanation_available: available,
    notice: available ? null : EXPLANATION_SET_NOTICE,
  };
}

function normaliseGuidance(guidance) {
  if (!guidance || typeof guidance !== 'object' || Array.isArray(guidance)) return null;
  return stripRefusedText(guidance);
}

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

function summariseGuidance(guidance) {
  if (!guidance || typeof guidance !== 'object') {
    return { guidanceItemCount: undefined, guidanceGenerated: undefined };
  }
  return {
    guidanceItemCount: Array.isArray(guidance.items) ? guidance.items.length : 0,
    guidanceGenerated: guidance.generated === true,
  };
}

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

function summariseUpstream(extraction, features) {
  const upstream = (features && features.upstream) || {};

  const pagesUnreadable = Array.isArray(upstream.pages_unreadable)
    ? upstream.pages_unreadable.filter((page) => Number.isFinite(page))
    : [];

  const confidence = [upstream.extraction_confidence, extraction && extraction.extraction_confidence]
    .find((value) => typeof value === 'number');

  return { pagesUnreadable, extractionConfidence: confidence };
}

function redactExtraction(extraction) {
  if (!extraction || typeof extraction !== 'object') return extraction;

  const { raw_text: rawText, pages, ...rest } = extraction;

  const redacted = { ...rest };
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

function hasLabResults(extraction) {
  const rows = Array.isArray(extraction && extraction.extracted_parameters)
    ? extraction.extracted_parameters
    : [];
  return rows.some(
    (row) =>
      row &&
      typeof row.test_name === 'string' &&
      row.test_name.trim() !== '' &&
      row.value_raw !== undefined &&
      row.value_raw !== null &&
      String(row.value_raw).trim() !== ''
  );
}

function assertProductiveFeatures(extraction, features) {
  const parameters = Array.isArray(extraction && extraction.extracted_parameters)
    ? extraction.extracted_parameters.length
    : 0;
  if (parameters === 0) return;

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
        'analysis.progressStep': 'reading',
        'analysis.progressAt': now,
      },
      $unset: { statusMessage: '', 'analysis.completedAt': '', 'analysis.durationMs': '' },
      $inc: { 'analysis.runCount': 1 },
    },
    { new: true }
  );
}

async function markStep(ownerFilter, step) {
  try {
    await Report.updateOne(ownerFilter, {
      $set: { 'analysis.progressStep': step, 'analysis.progressAt': new Date() },
    });
  } catch {
  }
}


async function openStorage(report) {
  let storage;
  try {
    storage = getStorage(report.storageDriver);
  } catch (err) {
    throw new ApiError(
      503,
      'STORAGE_UNAVAILABLE',
      'The storage backend for this report is not available'
    );
  }

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

async function runDownstreamStages({
  features,
  extraction = null,
  requestId,
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

  const guidanceAsk = guidanceInputs(clinicalReport);

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

function syntheticFilename(report) {
  const extension = EXTENSION_BY_MIME[report.mimeType] || '.bin';
  return `report-${report._id.toString()}${extension}`;
}

async function runAnalysis({ user, report, requestId }) {
  const startedAt = Date.now();
  const ownerFilter = ownerScopedFilter(user, {
    ...OWNER_ONLY,
    base: { _id: report._id, 'analysis.requestId': requestId },
  });

  try {
    const streamFactory = await openStorage(report);

    await aiService.waitUntilReady();

    const extraction = await aiService.extract({
      streamFactory,
      filename: syntheticFilename(report),
      mimeType: report.mimeType,
      requestId,
    });

    if (!hasLabResults(extraction)) {
      throw new ApiError(422, 'NO_LAB_RESULTS', SAFE_STATUS_MESSAGES.NO_LAB_RESULTS);
    }
    await markStep(ownerFilter, 'checking');

    const profile =
      report.subject?.owner === 'other'
        ? buildProfilePayload(subjectProfile(report.subject))
        : buildProfilePayload(await loadOwnProfile(user));

    const features = await aiService.engineerFeatures({ extraction, profile, requestId });

    assertProductiveFeatures(extraction, features);

    const downstream = await runDownstreamStages({
      features,
      extraction,
      requestId,
      onStep: (step) => markStep(ownerFilter, step),
    });
    const { validation, rules, ml, report: clinicalReport } = downstream;

    const explanation = normaliseExplanationSet(downstream.explanation);
    const guidance = normaliseGuidance(downstream.guidance);
    const parameterGlossary = downstream.parameterGlossary || null;

    const stages = {
      [aiService.STAGES.EXTRACTION]: stageOk(undefined),
      [aiService.STAGES.FEATURES]: stageOk(undefined),
      ...downstream.stages,
    };
    const stagesFailed = PIPELINE_STAGES.filter((stage) => !(stages[stage] || {}).ok);

    const reportCounts = summariseReport(clinicalReport);

    const warnings = collectWarnings(
      extraction,
      features,
      validation,
      rules,
      ml,
      clinicalReport,
      [...explanationWarnings(explanation), ...statusLabelWarnings(reportCounts)]
    );
    const upstream = summariseUpstream(extraction, features);
    const decisions = summariseDecisions(rules, ml);
    const validationCounts = summariseValidation(validation);
    const explanationCounts = summariseExplanation(explanation);
    const guidanceCounts = summariseGuidance(guidance);
    const completedAt = new Date();

    const $set = {
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

    const store = (path, value) => {
      if (value === undefined || value === null) $unset[path] = '';
      else $set[path] = value;
    };
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

    store('printedIdentity', readPrintedIdentity(extraction));

    if (stagesFailed.length === 0) {
      $unset.statusMessage = '';
    } else {
      $set.statusMessage = safeStatusMessage({ code: 'ANALYSIS_PARTIAL' });
    }

    $unset['analysis.progressStep'] = '';
    $unset['analysis.progressAt'] = '';

    const result = await Report.updateOne(ownerFilter, {
      $set,
      $unset,
      $inc: { 'analysis.version': 1 },
    });

    if (result.matchedCount === 0) {
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
    await Report.updateOne(ownerFilter, {
      $set: {
        status: REPORT_STATUS.FAILED,
        statusMessage: safeStatusMessage(err),
        'analysis.completedAt': new Date(),
        'analysis.durationMs': Date.now() - startedAt,
      },
      $unset: { 'analysis.progressStep': '', 'analysis.progressAt': '' },
    }).catch(() => {
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
