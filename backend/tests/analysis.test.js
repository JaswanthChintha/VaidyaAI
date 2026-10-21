'use strict';


const fs = require('fs');
const os = require('os');
const path = require('path');
const mongoose = require('mongoose');

const UPLOAD_ROOT = fs.mkdtempSync(path.join(os.tmpdir(), 'vaidyaai-analysis-test-'));
process.env.UPLOAD_ROOT = UPLOAD_ROOT;
process.env.UPLOAD_MAX_BYTES = String(64 * 1024);

const mockAxios = { post: jest.fn(), get: jest.fn() };
jest.mock('axios', () => ({
  create: () => ({
    post: (...args) => mockAxios.post(...args),
    get: (...args) => mockAxios.get(...args),
  }),
}));

const { app, request, registerUser, createUserWithRole, login } = require('./helpers');
const config = require('../src/config/env');
const Report = require('../src/models/Report');
const Profile = require('../src/models/Profile');
const { ROLES } = require('../src/utils/roles');
const aiServiceClient = require('../src/services/aiServiceClient');
const analysisService = require('../src/services/analysisService');

const REPORTS = `${config.apiPrefix}/reports`;
const PROFILE = `${config.apiPrefix}/profile/me`;
const PASSWORD = 'Str0ng!Passw0rd';
const EXTRACT_PATH = '/api/v1/ocr/extract';
const ENGINEER_PATH = '/api/v1/features/engineer';
const VALIDATE_PATH = '/api/v1/features/validate';
const RULES_PATH = '/api/v1/rules/evaluate';
const PREDICT_PATH = '/api/v1/ml/predict';
const REPORT_PATH = '/api/v1/report/generate';
const EXPLAIN_PATH = '/api/v1/explain/report';
const GUIDANCE_PATH = '/api/v1/explain/guidance';
const FUSE_PATH = '/api/v1/decisions/fuse';
const TERM_PATH = '/api/v1/explain/term';

const auth = (token) => ({ Authorization: `Bearer ${token}` });


const pdfBytes = (filler = 'lab report body') =>
  Buffer.concat([Buffer.from('%PDF-1.7\n'), Buffer.from(filler), Buffer.from('\n%%EOF\n')]);

const PHI_CANARY = 'PATIENT-ASHA-PATEL-HBA1C-6.8-CANARY';

const extractionFixture = () => ({
  source: 'pdf',
  raw_text: `Haemoglobin 14.2 g/dl ${PHI_CANARY}`,
  pages: [{ page_number: 1, raw_text: `HbA1c 6.8 % ${PHI_CANARY}` }],
  extracted_parameters: [
    {
      test_name: 'HbA1c',
      value_raw: '6.8',
      value_numeric: 6.8,
      unit: '%',
      reference_range_raw: '4.0 - 5.6',
      reference_low: 4.0,
      reference_high: 5.6,
      flag: 'high',
      page_number: 1,
      confidence: 0.94,
    },
  ],
  report_metadata: { lab_name: 'Test Diagnostics', report_date: '2026-03-14' },
  extraction_confidence: 0.99,
  warnings: ['page 1 was recovered by the PDF repairer'],
});

const REPAIR_WARNING = 'page 1 was recovered by the PDF repairer';
const UNIT_WARNING = 'unit for creatinine was not recognised; value left unconverted';

const featuresFixture = () => ({
  features: { hba1c: 6.8, blood_glucose: 112 },
  missing_features: ['hypertension'],
  unmapped: [],
  duplicates_resolved: [],
  warnings: [UNIT_WARNING],
  upstream_warnings: [
    { stage: 'extraction', module: 'module-4-ocr', message: REPAIR_WARNING },
  ],
  all_warnings: [
    { stage: 'extraction', module: 'module-4-ocr', message: REPAIR_WARNING },
    { stage: 'feature_engineering', module: 'module-5-features', message: UNIT_WARNING },
  ],
  upstream: {
    provided: true,
    source: 'pdf',
    report_metadata: { lab_name: 'Test Diagnostics' },
    extraction_confidence: 0.99,
    pages: [{ page_number: 1, raw_text_available: true }],
    pages_unreadable: [2],
    warning_count: 1,
  },
});

const validationFixture = (body) => {
  const engineered = (body && body.engineered) || {};
  const featureMap = engineered.features || {};
  const valid = {};
  for (const [name, value] of Object.entries(featureMap)) {
    valid[name] = {
      name,
      value,
      unit: null,
      canonical_unit: true,
      source: 'lab_report',
      provenance: { test_name: name },
      status: 'valid',
      questionable: false,
      clinically_extreme: false,
      flags: [],
    };
  }
  const upstreamWarnings = Array.isArray(engineered.all_warnings)
    ? engineered.all_warnings
    : [];
  return {
    valid,
    questionable: {},
    rejected: {},
    clinically_extreme: [],
    missing_features: engineered.missing_features || [],
    unmapped: engineered.unmapped || [],
    warnings: [],
    upstream_warnings: upstreamWarnings,
    all_warnings: upstreamWarnings,
    upstream: engineered.upstream || {},
    upstream_summary: engineered.summary || {},
    summary: {
      features_received: Object.keys(featureMap).length,
      valid_count: Object.keys(valid).length,
      questionable_count: 0,
      rejected_count: 0,
    },
  };
};

const forwarded = (body) =>
  (body && body.validated && Array.isArray(body.validated.all_warnings)
    ? body.validated.all_warnings
    : []);

const rulesFixture = (body) => ({
  decisions: [
    {
      condition: 'diabetes',
      status: 'Indicated',
      risk: 'High',
      confidence: 0.95,
      source: 'clinical_rule_engine',
      source_kind: 'clinical_rule',
      evidence: [
        { feature: 'hba1c', value: 6.8, unit: '%', threshold: 6.5, comparator: '>=' },
      ],
      recommendations: [
        { code: 'DISCUSS_WITH_CLINICIAN', text: 'Discuss these results with a clinician.' },
      ],
      metadata: {},
      created_at: '2026-08-29T00:00:00Z',
    },
  ],
  warnings: [],
  upstream_warnings: forwarded(body),
  all_warnings: forwarded(body),
  upstream: {},
  summary: {
    decision_count: 1,
    flagged_count: 1,
    indicated_count: 1,
    highest_risk: 'High',
    conditions_assessed: ['diabetes'],
    conditions_flagged: ['diabetes'],
    rules_evaluated: 12,
    rules_fired: 1,
  },
  metadata: { engine: 'rules' },
});

const mlFixture = (body) => ({
  decisions: [
    {
      condition: 'diabetes',
      status: 'Borderline',
      risk: 'Medium',
      confidence: 0.61,
      source: 'diabetes_rf_v1',
      source_kind: 'machine_learning',
      evidence: [{ feature: 'hba1c', value: 6.8, unit: '%' }],
      recommendations: [],
      metadata: { probability_positive: 0.61 },
      created_at: '2026-08-29T00:00:00Z',
    },
  ],
  warnings: [],
  upstream_warnings: forwarded(body),
  all_warnings: forwarded(body),
  upstream: {},
  summary: {
    decision_count: 1,
    flagged_count: 1,
    borderline_count: 1,
    highest_risk: 'Medium',
    predictors_registered: 1,
    predictors_run: 1,
    predictors_skipped: 0,
    conditions_assessed: ['diabetes'],
    conditions_flagged: ['diabetes'],
  },
  metadata: { engine: 'ml' },
});

const clinicalReportFixture = (body) => {
  const validated = (body && body.validated) || {};
  const warnings = Array.isArray(validated.all_warnings) ? validated.all_warnings : [];
  const laboratoryValues = Object.entries(validated.valid || {}).map(([name, record]) => ({
    feature: name,
    value: record.value,
    unit: record.unit,
    printed_test_name: name,
    status: 'valid',
    usable: true,
  }));

  return {
    report_version: '1.0.0',
    generated_at: '2026-08-30T00:00:00Z',
    patient: { contains_identity: false, age: null, gender: null },
    laboratory_values: laboratoryValues,
    conditions: [
      {
        condition: 'diabetes',
        status: 'Indicated',
        risk: 'High',
        evidence_features: ['hba1c'],
        contributions: [
          { source: 'clinical_rule_engine', status: 'Indicated', risk: 'High' },
          { source: 'diabetes_rf_v1', status: 'Borderline', risk: 'Medium' },
        ],
        render_contributions_separately: false,
      },
    ],
    overall: {
      status: 'Needs Medical Attention',
      status_label: 'Needs Medical Attention',
      risk: 'High',
      rule_applied: 'abnormal_with_high_risk',
      any_assessed: true,
      complete: true,
      caveat: null,
      assessed_condition_count: 1,
      unassessed_condition_count: 0,
      unassessed_conditions: [],
    },
    overall_risk: 'High',
    critical_conditions: ['diabetes'],
    abnormal_findings: ['diabetes'],
    normal_findings: [],
    unassessed_conditions: [],
    prioritized: [{ condition: 'diabetes', status: 'Indicated', risk: 'High', flagged: true }],
    explainability: { evidence_lines: [], rejected_features_joined: [] },
    recommendations: [
      { code: 'DISCUSS_WITH_CLINICIAN', text: 'Discuss these results with a clinician.' },
    ],
    document: {
      extraction_provided: true,
      extraction_confidence: 0.99,
      pages_unreadable: [2],
      partial_document: true,
      rejected_features: Object.keys(validated.rejected || {}),
      missing_features: validated.missing_features || [],
    },
    validation_warnings: warnings,
    warnings_by_stage: warnings.reduce((acc, w) => {
      acc[w.stage] = (acc[w.stage] || 0) + 1;
      return acc;
    }, {}),
    summary: {
      condition_count: 1,
      abnormal_count: 1,
      critical_count: 1,
      normal_count: 0,
      unassessed_count: 0,
      hybrid_count: 1,
      laboratory_value_count: laboratoryValues.length,
      recommendation_count: 1,
      warning_count: warnings.length,
      input_kind: 'validated',
    },
    metadata: { report_version: '1.0.0', input_received: 'validated' },
    fusion: {
      fused: [
        {
          condition: 'diabetes',
          status: 'Indicated',
          risk: 'High',
          confidence: 0.95,
          sources: ['Clinical Rule Engine', 'diabetes_rf_v1'],
          hybrid: true,
          basis_conflict: false,
        },
      ],
      collection: { collected: [], groups: [], sources: [] },
      warnings: [],
      upstream_warnings: warnings,
      all_warnings: warnings,
      summary: {
        overall_status: 'Needs Medical Attention',
        overall_risk: 'High',
        any_assessed: true,
        assessment_incomplete: false,
      },
      metadata: {},
    },
  };
};

const nothingAssessedReport = (body) => {
  const report = clinicalReportFixture(body);
  return {
    ...report,
    conditions: [],
    overall: {
      status: null,
      status_label: 'Not Assessed',
      risk: null,
      rule_applied: 'nothing_assessed',
      any_assessed: false,
      complete: false,
      caveat: 'No condition in this analysis could be assessed from the submitted document.',
      assessed_condition_count: 0,
      unassessed_condition_count: 2,
      unassessed_conditions: ['diabetes', 'kidney_disease'],
    },
    overall_risk: null,
    critical_conditions: [],
    abnormal_findings: [],
    normal_findings: [],
    unassessed_conditions: ['diabetes', 'kidney_disease'],
    prioritized: [],
    summary: {
      ...report.summary,
      condition_count: 0,
      abnormal_count: 0,
      critical_count: 0,
      normal_count: 0,
      unassessed_count: 2,
    },
    fusion: {
      ...report.fusion,
      fused: [],
      summary: {
        overall_status: null,
        overall_risk: null,
        any_assessed: false,
        assessment_incomplete: true,
      },
    },
  };
};


const EXPLANATION_TEXT =
  'HbA1c reflects the average amount of sugar carried in your blood over the ' +
  'past few months. Your result is above the range this laboratory prints as ' +
  'usual. This is information to discuss with a qualified healthcare professional.';

const REFUSED_CANARY =
  'REFUSED-UNSAFE-CANARY you definitely have diabetes, start metformin 500mg twice daily';
const REFUSED_SPAN_CANARY = 'REFUSED-SPAN-CANARY you definitely have diabetes';

const FALLBACK_NOTICE =
  'A plain-language explanation could not be prepared for this report. The ' +
  'structured findings above were produced by the analysis itself and are ' +
  'unaffected. A qualified healthcare professional can go through them with you.';

const NOT_GROUNDED_NOTICE =
  'No reviewed medical knowledge in this platform covers this finding closely ' +
  'enough to explain it, so no explanation was written.';
const MODEL_UNAVAILABLE_NOTICE =
  'The plain-language explanation service was not available, so no explanation was written.';

const safeFallback = (violationCodes = []) => ({
  version: '1.0.0',
  generated_explanation_available: false,
  notice: FALLBACK_NOTICE,
  use_structured_report: true,
  recommendation_codes: ['NOT_A_DIAGNOSIS', 'DISCUSS_WITH_CLINICIAN', 'INFORMATION_INCOMPLETE'],
  recommendations: [
    {
      code: 'NOT_A_DIAGNOSIS',
      text: 'This is not a diagnosis.',
      category: 'safety',
    },
    {
      code: 'DISCUSS_WITH_CLINICIAN',
      text: 'Discuss these results with a qualified healthcare professional.',
      category: 'safety',
    },
    {
      code: 'INFORMATION_INCOMPLETE',
      text: 'This assessment rests on incomplete information.',
      category: 'safety',
    },
  ],
  violation_codes: violationCodes,
});

const sourcesFixture = () => [
  {
    chunk_id: 'kb-hba1c-0001',
    doc_id: 'hba1c-overview',
    title: 'What HbA1c measures',
    topic: 'hba1c',
    basis: 'ADA Standards of Care',
    last_reviewed: '2026-01-01',
    score: 0.41,
    features: ['hba1c'],
    conditions: ['diabetes'],
  },
];

function explanationItem(feature, conditions, outcome = 'generated', { leak = false } = {}) {
  const base = {
    module: 23,
    version: '1.0.0',
    prompt_version: '1.0.0',
    subject: feature,
    feature,
    conditions,
    outcome,
    permitted_numbers: [6.8, 4.0, 5.6],
    findings: [`${feature} is above the printed reference range`],
  };

  if (outcome === 'generated') {
    return {
      ...base,
      explanation: EXPLANATION_TEXT,
      fallback: null,
      notice: null,
      grounding_available: true,
      sources: sourcesFixture(),
      safety: {
        validated: true,
        verdict: 'approved',
        version: '1.0.0',
        violation_codes: [],
        modification_count: 0,
        attempts: 1,
      },
    };
  }

  if (outcome === 'withheld_by_safety') {
    const codes = ['DIAGNOSIS_CLAIM', 'MEDICATION_ADVICE'];
    return {
      ...base,
      explanation: leak ? REFUSED_CANARY : null,
      fallback: safeFallback(codes),
      notice: null,
      grounding_available: true,
      sources: sourcesFixture(),
      safety: {
        validated: true,
        verdict: 'rejected',
        version: '1.0.0',
        violation_codes: codes,
        modification_count: 0,
        attempts: 2,
        ...(leak
          ? {
              offending_span: REFUSED_SPAN_CANARY,
              rejected_text: REFUSED_CANARY,
              modifications: [{ span: REFUSED_SPAN_CANARY, reason: 'DIAGNOSIS_CLAIM' }],
            }
          : {}),
      },
    };
  }

  const notices = {
    not_grounded: NOT_GROUNDED_NOTICE,
    model_unavailable: MODEL_UNAVAILABLE_NOTICE,
    unknown_subject: 'This parameter is not one this platform can explain.',
  };

  return {
    ...base,
    explanation: null,
    fallback: safeFallback([]),
    notice: notices[outcome] || 'No explanation was written.',
    grounding_available: outcome === 'model_unavailable',
    sources: outcome === 'model_unavailable' ? sourcesFixture() : [],
    safety: {
      validated: false,
      verdict: null,
      version: '1.0.0',
      violation_codes: [],
      modification_count: 0,
      attempts: 0,
    },
  };
}

function explanationFixture(body, { outcome = 'generated', leak = false } = {}) {
  const report = (body && body.report) || {};
  const byFeature = {};
  for (const condition of report.conditions || []) {
    for (const feature of condition.evidence_features || []) {
      (byFeature[feature] = byFeature[feature] || []).push(condition.condition);
    }
  }

  const explanations = (report.laboratory_values || [])
    .filter((row) => row.usable === true)
    .slice(0, body && Number.isInteger(body.max_explanations) ? body.max_explanations : 6)
    .map((row) => explanationItem(row.feature, byFeature[row.feature] || [], outcome, { leak }));

  const generated = explanations.filter((e) => e.outcome === 'generated').length;
  return {
    module: 23,
    version: '1.0.0',
    explanations,
    generated_count: generated,
    withheld_count: explanations.length - generated,
    skipped: [],
  };
}

function guidanceFixture(body) {
  const asked = body || {};
  return {
    module: 26,
    version: '1.0.0',
    generated: false,
    source: 'recommendation_catalog',
    conditions: asked.conditions || [],
    features: asked.features || [],
    items: [
      {
        code: 'BALANCED_DIET',
        text: 'A balanced diet with vegetables, whole grains and limited added sugar is generally recommended.',
        category: 'lifestyle',
        conditions: asked.conditions || [],
        features: [],
      },
      {
        code: 'REGULAR_ACTIVITY',
        text: 'Regular physical activity is generally recommended for most adults.',
        category: 'lifestyle',
        conditions: asked.conditions || [],
        features: [],
      },
    ],
    further_reading: [],
    text: 'A balanced diet ... Regular physical activity ...',
    fallback: null,
    unknown_conditions: [],
    unknown_features: [],
    unknown_codes: [],
    safety_verdict: 'approved',
  };
}

const okResponse = (data) => ({ status: 200, data: { success: true, data } });

function transportError({ status, code, message = 'transport failure' }) {
  const err = new Error(message);
  if (status !== undefined) {
    err.response = {
      status,
      data: { detail: `service failed while reading ${PHI_CANARY}` },
    };
  }
  if (code !== undefined) err.code = code;
  return err;
}

let outgoing = [];

function wireAiService({
  extract,
  engineer,
  validate,
  rules,
  predict,
  report,
  explain,
  guidance,
} = {}) {
  mockAxios.post.mockReset();
  mockAxios.post.mockImplementation(async (url, body, options) => {
    outgoing.push({ url, body, options });
    const stage = {
      [EXTRACT_PATH]: [extract, () => okResponse(extractionFixture())],
      [ENGINEER_PATH]: [engineer, () => okResponse(featuresFixture())],
      [VALIDATE_PATH]: [validate, (b) => okResponse(validationFixture(b))],
      [RULES_PATH]: [rules, (b) => okResponse(rulesFixture(b))],
      [PREDICT_PATH]: [predict, (b) => okResponse(mlFixture(b))],
      [REPORT_PATH]: [report, (b) => okResponse(clinicalReportFixture(b))],
      [EXPLAIN_PATH]: [explain, (b) => okResponse(explanationFixture(b))],
      [GUIDANCE_PATH]: [guidance, (b) => okResponse(guidanceFixture(b))],
    }[url];
    if (!stage) throw new Error(`unexpected ai-service path ${url}`);
    const [override, fallback] = stage;
    return typeof override === 'function' ? override(body, options) : fallback(body, options);
  });
}

const EXPLAIN_PHASE = [EXPLAIN_PATH, GUIDANCE_PATH];

function expectFullChain(calls) {
  expect(calls.slice(0, 3)).toEqual([EXTRACT_PATH, ENGINEER_PATH, VALIDATE_PATH]);
  expect(calls.slice(3, 6).sort()).toEqual([PREDICT_PATH, REPORT_PATH, RULES_PATH].sort());
  expect(calls.slice(6).sort()).toEqual([...EXPLAIN_PHASE].sort());
  expect(calls).toHaveLength(8);
}

const callsTo = (url) => outgoing.filter((call) => call.url === url);


async function makeUser(email) {
  const { res } = await registerUser({ email, name: 'Test User' });
  expect(res.status).toBe(201);
  return { token: res.body.data.accessToken, id: res.body.data.user.id, email };
}

async function makePrivilegedUser(role, email) {
  const user = await createUserWithRole(role, { email, password: PASSWORD });
  const res = await login(email, PASSWORD);
  expect(res.status).toBe(200);
  return { token: res.body.data.accessToken, id: user._id.toString(), email };
}

async function uploadReport(token, buffer = pdfBytes()) {
  const res = await request(app)
    .post(REPORTS)
    .set(auth(token))
    .attach('file', buffer, { filename: 'labs.pdf', contentType: 'application/pdf' });
  expect(res.status).toBe(201);
  return res.body.data.report;
}

const analyze = (token, id) => request(app).post(`${REPORTS}/${id}/analyze`).set(auth(token));
const getAnalysis = (token, id) =>
  request(app).get(`${REPORTS}/${id}/analysis`).set(auth(token));

const loadRaw = (id) =>
  Report.findById(id).select(
    '+extraction +features +featureValidation +ruleDecisions +mlDecisions +clinicalReport ' +
      '+patientExplanation +lifestyleGuidance +analysisWarnings'
  );

const getClinicalReport = (token, id) =>
  request(app).get(`${REPORTS}/${id}/report`).set(auth(token));

const getExplanation = (token, id) =>
  request(app).get(`${REPORTS}/${id}/explanation`).set(auth(token));


describe('unmappedTestNames - which skipped tests get described', () => {
  const { unmappedTestNames } = analysisService;

  const features = (names) => ({ unmapped: names.map((test_name) => ({ test_name })) });
  const extraction = (rows) => ({ extracted_parameters: rows });

  it('asks about a test the laboratory flagged and this platform skipped', () => {
    expect(
      unmappedTestNames(
        features(['Potassium']),
        extraction([{ test_name: 'Potassium', flag: 'high' }])
      )
    ).toEqual(['Potassium']);
  });

  it('ASKS ABOUT AN UNFLAGGED TEST TOO, which is the change', () => {
    expect(
      unmappedTestNames(
        features(['Urine Colour', 'Urine Clarity']),
        extraction([
          { test_name: 'Urine Colour', flag: null, value_raw: 'Pale Yellow' },
          { test_name: 'Urine Clarity', reference_low: 1, reference_high: 2 },
        ])
      )
    ).toEqual(['Urine Colour', 'Urine Clarity']);
  });

  it('sends a NAME and nothing else, whatever the row carries', () => {
    const out = unmappedTestNames(
      features(['Potassium']),
      extraction([
        {
          test_name: 'Potassium',
          flag: 'high',
          value_raw: '5.9',
          unit: 'mmol/l',
          reference_low: 3.5,
          reference_high: 5.1,
        },
      ])
    );
    expect(out).toEqual(['Potassium']);
    expect(typeof out[0]).toBe('string');
  });

  it('does not ask about a test this platform DID assess', () => {
    expect(
      unmappedTestNames(
        features(['Potassium']),
        extraction([
          { test_name: 'HbA1c', flag: 'high' },
          { test_name: 'Potassium', flag: 'high' },
        ])
      )
    ).toEqual(['Potassium']);
  });

  it('takes every unassessed test, whatever its marking says', () => {
    expect(
      unmappedTestNames(
        features(['A', 'B', 'C', 'D']),
        extraction([
          { test_name: 'A', flag: 'HIGH' },
          { test_name: 'B', flag: 'Low' },
          { test_name: 'C', flag: 'critical' },
          { test_name: 'D', flag: 'Normal' },
        ])
      )
    ).toEqual(['A', 'B', 'C', 'D']);
  });

  it('never repeats a name, even when the report prints it twice', () => {
    expect(
      unmappedTestNames(
        features(['Potassium']),
        extraction([
          { test_name: 'Potassium', flag: 'high', page_number: 1 },
          { test_name: 'Potassium', flag: 'high', page_number: 3 },
        ])
      )
    ).toEqual(['Potassium']);
  });

  it('returns an empty list rather than throwing on missing or malformed input', () => {
    for (const [f, e] of [
      [null, null],
      [undefined, undefined],
      [{}, {}],
      [{ unmapped: 'nope' }, { extracted_parameters: 'nope' }],
      [features(['A']), null],
      [{ unmapped: [null, 7, {}] }, extraction([null, 7, {}])],
    ]) {
      expect(unmappedTestNames(f, e)).toEqual([]);
    }
  });
});

describe('Modules 4+5 - analysis orchestration', () => {
  const originalRetries = config.aiService.retries;
  let consoleWarn;
  let consoleError;

  beforeEach(() => {
    outgoing = [];
    config.aiService.retries = 0;
    wireAiService();
    mockAxios.get.mockReset();
    mockAxios.get.mockResolvedValue({ status: 200, data: { success: true, data: { status: 'ok' } } });
    consoleWarn = jest.spyOn(console, 'warn').mockImplementation(() => {});
    consoleError = jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    config.aiService.retries = originalRetries;
    consoleWarn.mockRestore();
    consoleError.mockRestore();
    aiServiceClient.resetClient();
  });

  afterAll(() => {
    fs.rmSync(UPLOAD_ROOT, { recursive: true, force: true });
  });

  describe('progress steps for the Reports page', () => {
    const recording = (seen, name, id, respond) => async (body, options) => {
      const doc = await Report.findById(id);
      seen.push([name, doc.analysis.progressStep, doc.toPublicJSON().analysisProgress]);
      return respond(body, options);
    };

    it('records each step as it begins, in order, and clears it at the end', async () => {
      const user = await makeUser('progress.order@example.com');
      const report = await uploadReport(user.token);
      const seen = [];
      wireAiService({
        extract: recording(seen, 'extract', report.id, () => okResponse(extractionFixture())),
        engineer: recording(seen, 'engineer', report.id, () => okResponse(featuresFixture())),
        validate: recording(seen, 'validate', report.id, (b) => okResponse(validationFixture(b))),
        rules: recording(seen, 'rules', report.id, (b) => okResponse(rulesFixture(b))),
        predict: recording(seen, 'predict', report.id, (b) => okResponse(mlFixture(b))),
        report: recording(seen, 'report', report.id, (b) => okResponse(clinicalReportFixture(b))),
        explain: recording(seen, 'explain', report.id, (b) => okResponse(explanationFixture(b))),
        guidance: recording(seen, 'guidance', report.id, (b) => okResponse(guidanceFixture(b))),
      });

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);

      const stepAt = Object.fromEntries(seen.map(([name, step]) => [name, step]));
      expect(stepAt).toEqual({
        extract: 'reading',
        engineer: 'checking',
        validate: 'checking',
        rules: 'deciding',
        predict: 'deciding',
        report: 'deciding',
        explain: 'explaining',
        guidance: 'explaining',
      });
      const shown = Object.fromEntries(seen.map(([name, , progress]) => [name, progress]));
      expect(shown.extract).toMatchObject({ step: 'reading', stepNumber: 1, totalSteps: 4 });
      expect(shown.explain).toMatchObject({ step: 'explaining', stepNumber: 4, totalSteps: 4 });
      expect(new Date(shown.extract.startedAt).getTime()).not.toBeNaN();

      const done = await Report.findById(report.id);
      expect(done.analysis.progressStep).toBeUndefined();
      expect(done.analysis.progressAt).toBeUndefined();
      expect(done.toPublicJSON().analysisProgress).toBeUndefined();
      expect(res.body.data.report.analysisProgress).toBeUndefined();
    });

    it('clears the step when the run fails', async () => {
      const user = await makeUser('progress.fail@example.com');
      const report = await uploadReport(user.token);
      wireAiService({
        engineer: () => {
          throw transportError({ code: 'ECONNREFUSED' });
        },
      });

      await analyze(user.token, report.id);
      const failed = await Report.findById(report.id);
      expect(failed.status).toBe('failed');
      expect(failed.analysis.progressStep).toBeUndefined();
      expect(failed.toPublicJSON().analysisProgress).toBeUndefined();
    });

    it('never fails an analysis because a progress write did not land', async () => {
      const user = await makeUser('progress.writefail@example.com');
      const report = await uploadReport(user.token);
      const original = Report.updateOne.bind(Report);
      const spy = jest.spyOn(Report, 'updateOne').mockImplementation((filter, update, ...rest) => {
        const set = (update && update.$set) || {};
        if ('analysis.progressStep' in set && !('status' in set)) {
          return Promise.reject(new Error('write failed'));
        }
        return original(filter, update, ...rest);
      });
      try {
        const res = await analyze(user.token, report.id);
        expect(res.status).toBe(200);
        expect(spy.mock.calls.some(([, u]) => u && u.$set && u.$set['analysis.progressStep'])).toBe(true);
        expect((await Report.findById(report.id)).status).toBe('processed');
      } finally {
        spy.mockRestore();
      }
    });

    it('shows no step for a processing report that has none, and nothing once finished', () => {
      const base = { user: new mongoose.Types.ObjectId(), originalName: 'x.pdf' };
      const running = new Report({ ...base, status: 'processing', analysis: { startedAt: new Date() } });
      expect(running.toPublicJSON().analysisProgress).toMatchObject({
        step: null,
        stepNumber: null,
        totalSteps: 4,
      });
      const checking = new Report({ ...base, status: 'processing', analysis: { progressStep: 'checking' } });
      expect(checking.toPublicJSON().analysisProgress).toMatchObject({ step: 'checking', stepNumber: 2 });
      const stale = new Report({ ...base, status: 'failed', analysis: { progressStep: 'deciding' } });
      expect(stale.toPublicJSON().analysisProgress).toBeUndefined();
    });
  });

  describe('a sleeping ai-service is waited for, not failed on', () => {
    const saved = {};
    const badGateway = () => Object.assign(new Error('bad gateway'), { response: { status: 502, data: '' } });

    beforeEach(() => {
      saved.wait = config.aiService.wakeWaitMs;
      saved.interval = config.aiService.wakeIntervalMs;
      config.aiService.wakeWaitMs = 2000;
      config.aiService.wakeIntervalMs = 1;
    });
    afterEach(() => {
      config.aiService.wakeWaitMs = saved.wait;
      config.aiService.wakeIntervalMs = saved.interval;
    });

    it('asks /health until it answers, and only THEN sends the report', async () => {
      let probes = 0;
      mockAxios.get.mockImplementation(async () => {
        probes += 1;
        if (probes < 3) throw badGateway();
        return { status: 200, data: { success: true, data: { status: 'ok' } } };
      });
      const user = await makeUser('sleepy@example.com');
      const report = await uploadReport(user.token);

      const res = await analyze(user.token, report.id);

      expect(res.body.data.report.status).toBe('processed');
      expect(probes).toBe(3);
      const lastProbe = Math.max(...mockAxios.get.mock.invocationCallOrder);
      expect(lastProbe).toBeLessThan(mockAxios.post.mock.invocationCallOrder[0]);
    });

    it('gives up at the deadline WITHOUT throwing, so the real call reports the real error', async () => {
      const aiService = require('../src/services/aiServiceClient');
      mockAxios.get.mockRejectedValue(badGateway());
      const verdict = await aiService.waitUntilReady({ maxWaitMs: 30, intervalMs: 10 });
      expect(verdict.ready).toBe(false);
      expect(verdict.attempts).toBeGreaterThan(1);
    });

    it('is off by default: no /health probe at all', async () => {
      config.aiService.wakeWaitMs = 0;
      mockAxios.get.mockClear();
      const user = await makeUser('awake@example.com');
      const report = await uploadReport(user.token);
      const res = await analyze(user.token, report.id);
      expect(res.body.data.report.status).toBe('processed');
      expect(mockAxios.get).not.toHaveBeenCalled();
    });
  });

  describe('a file with no test results is not assessed at all', () => {
    it.each([
      ['no rows at all', []],
      ['only blank rows', [{ test_name: '  ', value_raw: '' }, { test_name: 'HbA1c', value_raw: null }]],
    ])('%s -> failed with NO_LAB_RESULTS, and no later stage is called', async (_label, rows) => {
      wireAiService({
        extract: () => okResponse({ ...extractionFixture(), extracted_parameters: rows }),
      });
      const user = await makeUser(`empty-${rows.length}@example.com`);
      const report = await uploadReport(user.token);

      const res = await analyze(user.token, report.id);

      expect(res.status).toBe(422);
      expect(res.body.error.code).toBe('NO_LAB_RESULTS');
      expect(outgoing.map((c) => c.url)).toEqual([EXTRACT_PATH]);

      const stored = await loadRaw(report.id);
      expect(stored.status).toBe('failed');
      expect(stored.statusMessage).toBe('NO_LAB_RESULTS: No test results were found in this file');
      expect(stored.clinicalReport).toBeUndefined();
    });

    it('one real result is enough to go on', async () => {
      wireAiService({
        extract: () =>
          okResponse({
            ...extractionFixture(),
            extracted_parameters: [extractionFixture().extracted_parameters[0]],
          }),
      });
      const user = await makeUser('one-result@example.com');
      const report = await uploadReport(user.token);
      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);
      expect(outgoing.length).toBeGreaterThan(1);
    });
  });

  describe('happy path', () => {
    it('runs extraction then feature engineering and persists both', async () => {
      const user = await makeUser('happy@example.com');
      const report = await uploadReport(user.token);
      expect(report.status).toBe('uploaded');

      const res = await analyze(user.token, report.id);

      expect(res.status).toBe(200);
      expect(res.body.success).toBe(true);
      expect(res.body.data.report.status).toBe('processed');
      expect(res.body.data.report.statusMessage).toBeUndefined();
      expect(res.body.data.analysis.version).toBe(1);
      expect(res.body.data.analysis.runCount).toBe(1);
      expect(res.body.data.analysis.extraction.extracted_parameters).toHaveLength(1);
      expect(res.body.data.analysis.features.features.hba1c).toBe(6.8);
      expect(res.body.data.analysis.extractionConfidence).toBe(0.99);

      expectFullChain(outgoing.map((c) => c.url));

      const stored = await loadRaw(report.id);
      expect(stored.status).toBe('processed');
      expect(stored.extraction.extraction_confidence).toBe(0.99);
      expect(stored.features.features.blood_glucose).toBe(112);
      expect(stored.analysis.version).toBe(1);
      expect(stored.analysis.completedAt).toBeInstanceOf(Date);
    });

    it('sends the service key and an opaque correlation id on both calls', async () => {
      const user = await makeUser('headers@example.com');
      const report = await uploadReport(user.token);
      await analyze(user.token, report.id);

      expect(outgoing).toHaveLength(8);
      for (const call of outgoing) {
        expect(call.options.headers['X-Service-Key']).toBe(config.aiService.apiKey);
        const requestId = call.options.headers['X-Request-Id'];
        expect(typeof requestId).toBe('string');
        expect(requestId).toBe(report.id);
        expect(requestId).not.toContain(PHI_CANARY);
      }
      expect(outgoing[0].options.headers['X-Request-Id']).toBe(
        outgoing[1].options.headers['X-Request-Id']
      );
    });

    it('only ever sends a correlation id the service will accept', () => {
      for (const dirty of [
        'asha patel.pdf',
        'report/../../etc',
        'a\nb',
        '<script>',
        'x'.repeat(200),
        '',
      ]) {
        const id = aiServiceClient.newRequestId(dirty);
        expect(id).toMatch(aiServiceClient.REQUEST_ID_PATTERN);
        expect(id).not.toBe(dirty);
      }
      const objectId = new mongoose.Types.ObjectId().toString();
      expect(aiServiceClient.newRequestId(objectId)).toBe(objectId);
    });

    it('UNWRAPS the extraction envelope before the features call', async () => {
      const user = await makeUser('unwrap@example.com');
      const report = await uploadReport(user.token);
      await analyze(user.token, report.id);

      const body = callsTo(ENGINEER_PATH)[0].body;
      expect(body.extraction).toBeDefined();
      expect(body.extraction.success).toBeUndefined();
      expect(body.extraction.data).toBeUndefined();
      expect(body.extraction.extracted_parameters[0].test_name).toBe('HbA1c');
    });

    it('sends the CANONICAL body shape, with no ambiguous alternatives', async () => {
      const user = await makeUser('canonical@example.com');
      const report = await uploadReport(user.token);
      await analyze(user.token, report.id);

      const body = callsTo(ENGINEER_PATH)[0].body;
      expect(Object.keys(body).sort()).toEqual(['extraction']);
      expect(body).not.toHaveProperty('data');
      expect(body).not.toHaveProperty('extracted_parameters');
      expect(callsTo(ENGINEER_PATH)[0].options.headers['Content-Type']).toBe(
        'application/json'
      );
    });

    it('treats a 200 that accounted for NO parameters as a failure', async () => {
      const user = await makeUser('emptyresult@example.com');
      const report = await uploadReport(user.token);
      wireAiService({
        engineer: () =>
          okResponse({ features: {}, unmapped: [], duplicates_resolved: [], warnings: [] }),
      });

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(502);
      expect(res.body.error.code).toBe('AI_SERVICE_EMPTY_RESULT');

      const stored = await loadRaw(report.id);
      expect(stored.status).toBe('failed');
      expect(stored.analysis.version).toBe(0);
    });

    it('a successful analysis always yields a non-empty feature set', async () => {
      const user = await makeUser('nonempty@example.com');
      const report = await uploadReport(user.token);
      const res = await analyze(user.token, report.id);

      expect(res.status).toBe(200);
      expect(Object.keys(res.body.data.analysis.features.features).length).toBeGreaterThan(0);
    });

    it('accepts an empty feature set when Module 5 accounted for the parameters', async () => {
      const user = await makeUser('allunmapped@example.com');
      const report = await uploadReport(user.token);
      wireAiService({
        engineer: () =>
          okResponse({ features: {}, unmapped: [{ test_name: 'HbA1c' }], warnings: [] }),
      });

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);
    });

    it('does NOT persist raw report text', async () => {
      const user = await makeUser('redact@example.com');
      const report = await uploadReport(user.token);
      await analyze(user.token, report.id);

      const form = callsTo(EXTRACT_PATH)[0].body;
      expect(form).toBeDefined();
      expect(callsTo(ENGINEER_PATH)[0].body.extraction.raw_text).toContain(PHI_CANARY);

      const stored = await loadRaw(report.id);
      expect(stored.extraction.raw_text).toBeUndefined();
      expect(stored.extraction.raw_text_available).toBe(true);
      expect(stored.extraction.pages[0].raw_text).toBeUndefined();
      expect(stored.extraction.pages[0].raw_text_available).toBe(true);
      expect(stored.extraction.pages[0].page_number).toBe(1);
      expect(stored.extraction.extracted_parameters[0].test_name).toBe('HbA1c');
      expect(stored.extraction.report_metadata.lab_name).toBe('Test Diagnostics');
      expect(stored.extraction.source).toBe('pdf');
      expect(stored.extraction.extraction_confidence).toBe(0.99);

      const persisted = JSON.stringify(stored.toObject());
      expect(persisted).not.toContain(PHI_CANARY);
    });

    it('sends a synthetic, PHI-free filename in the multipart part', async () => {
      const user = await makeUser('filename@example.com');
      const report = await request(app)
        .post(REPORTS)
        .set(auth(user.token))
        .attach('file', pdfBytes(), {
          filename: 'asha-patel-diabetes-results.pdf',
          contentType: 'application/pdf',
        });
      expect(report.status).toBe(201);
      const id = report.body.data.report.id;

      await analyze(user.token, id);

      const form = callsTo(EXTRACT_PATH)[0].body;
      expect(form).toBeInstanceOf(FormData);
      const part = form.get('file');
      expect(part.name).toBe(`report-${id}.pdf`);
      expect(part.name).not.toContain('asha-patel');
    });

    it('uses the multipart part name `file`', async () => {
      const user = await makeUser('partname@example.com');
      const report = await uploadReport(user.token);
      await analyze(user.token, report.id);

      const form = callsTo(EXTRACT_PATH)[0].body;
      expect([...form.keys()]).toEqual(['file']);
    });
  });

  describe("someone else's report -- the account profile is not sent", () => {
    const fullProfile = {
      age: 20,
      gender: 'male',
      heightCm: 178,
      weightKg: 80,
      hypertension: true,
      heartDisease: false,
      smokingHistory: 'current',
    };
    const markOther = (token, id, extra = {}) =>
      request(app)
        .patch(`${REPORTS}/${id}/subject`)
        .set(auth(token))
        .send({ subjectOwner: 'other', ...extra });

    it('sends ONLY the age and sex typed for the report', async () => {
      const user = await makeUser('other.typed@example.com');
      expect((await request(app).post(PROFILE).set(auth(user.token)).send(fullProfile)).status).toBe(201);
      const report = await uploadReport(user.token);
      expect((await markOther(user.token, report.id, { subjectAge: 34, subjectSex: 'female' })).status).toBe(200);

      await analyze(user.token, report.id);
      const profile = callsTo(ENGINEER_PATH)[0].body.profile;
      expect(profile).toEqual({ age: 34, gender: 'female' });
      const wire = JSON.stringify(callsTo(ENGINEER_PATH)[0].body);
      for (const field of ['heightCm', 'weightKg', 'bmi', 'hypertension', 'heartDisease', 'smokingHistory']) {
        expect(wire).not.toContain(field);
      }
    });

    it('sends NO profile at all when nothing was typed -- unknown stays unknown', async () => {
      const user = await makeUser('other.blank@example.com');
      expect((await request(app).post(PROFILE).set(auth(user.token)).send(fullProfile)).status).toBe(201);
      const report = await uploadReport(user.token);
      expect((await markOther(user.token, report.id)).status).toBe(200);

      await analyze(user.token, report.id);
      expect(callsTo(ENGINEER_PATH)[0].body.profile).toBeUndefined();
    });

    it("still sends the owner's profile for the owner's own report", async () => {
      const user = await makeUser('other.self@example.com');
      expect((await request(app).post(PROFILE).set(auth(user.token)).send(fullProfile)).status).toBe(201);
      const report = await uploadReport(user.token);

      await analyze(user.token, report.id);
      expect(callsTo(ENGINEER_PATH)[0].body.profile).toMatchObject({ age: 20, gender: 'male', smokingHistory: 'current' });
    });
  });

  describe('tri-state profile fields (hypertension / heartDisease)', () => {
    it('keeps an absent hypertension ABSENT from the wire payload', async () => {
      const user = await makeUser('tristate@example.com');
      const created = await request(app)
        .post(PROFILE)
        .set(auth(user.token))
        .send({
          age: 47,
          gender: 'female',
          heightCm: 165,
          weightKg: 68,
          heartDisease: false,
          smokingHistory: 'never',
        });
      expect(created.status).toBe(201);
      expect(created.body.data.profile.hypertension).toBeUndefined();

      const report = await uploadReport(user.token);
      await analyze(user.token, report.id);

      const profile = callsTo(ENGINEER_PATH)[0].body.profile;

      expect(Object.prototype.hasOwnProperty.call(profile, 'hypertension')).toBe(false);
      expect('hypertension' in profile).toBe(false);
      expect(JSON.stringify(callsTo(ENGINEER_PATH)[0].body)).not.toContain('hypertension');

      expect(Object.prototype.hasOwnProperty.call(profile, 'heartDisease')).toBe(true);
      expect(profile.heartDisease).toBe(false);
    });

    it('keeps it absent across EVERY stage of the chain, not just the first', async () => {
      const user = await makeUser('tristatechain@example.com');
      const created = await request(app)
        .post(PROFILE)
        .set(auth(user.token))
        .send({
          age: 47,
          gender: 'female',
          heightCm: 165,
          weightKg: 68,
          heartDisease: false,
          smokingHistory: 'never',
        });
      expect(created.status).toBe(201);

      const report = await uploadReport(user.token);
      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);
      expectFullChain(outgoing.map((c) => c.url));

      for (const call of outgoing) {
        if (call.url === EXTRACT_PATH) continue;
        const serialised = JSON.stringify(call.body);
        expect(serialised).not.toContain('"hypertension":false');
        expect(serialised).not.toContain('"hypertension": false');
        expect(serialised).not.toContain('"hypertension":null');
      }

      const profile = callsTo(ENGINEER_PATH)[0].body.profile;
      expect(Object.prototype.hasOwnProperty.call(profile, 'hypertension')).toBe(false);
      expect(JSON.stringify(profile)).not.toContain('hypertension');

      const engineered = callsTo(VALIDATE_PATH)[0].body.engineered;
      expect(engineered.features.hypertension).toBeUndefined();
      expect(engineered.missing_features).toContain('hypertension');
      for (const path of [RULES_PATH, PREDICT_PATH]) {
        const validated = callsTo(path)[0].body.validated;
        expect(validated.valid.hypertension).toBeUndefined();
        expect(validated.rejected.hypertension).toBeUndefined();
        expect(validated.missing_features).toContain('hypertension');
      }

      expect(callsTo(ENGINEER_PATH)[0].body.profile.heartDisease).toBe(false);

      const stored = await loadRaw(report.id);
      expect(stored.features.missing_features).toContain('hypertension');
      expect(stored.features.features.hypertension).toBeUndefined();
      expect(stored.featureValidation.valid.hypertension).toBeUndefined();
      expect(stored.featureValidation.rejected.hypertension).toBeUndefined();
      expect(stored.featureValidation.missing_features).toContain('hypertension');
    });

    it('sends an explicit true for both when both are set', async () => {
      const user = await makeUser('tristate2@example.com');
      await request(app)
        .post(PROFILE)
        .set(auth(user.token))
        .send({ age: 60, hypertension: true, heartDisease: true });

      const report = await uploadReport(user.token);
      await analyze(user.token, report.id);

      const profile = callsTo(ENGINEER_PATH)[0].body.profile;
      expect(profile.hypertension).toBe(true);
      expect(profile.heartDisease).toBe(true);
    });

    it('sends Module 2 camelCase field names untranslated', async () => {
      const user = await makeUser('camel@example.com');
      await request(app)
        .post(PROFILE)
        .set(auth(user.token))
        .send({ age: 50, gender: 'male', heightCm: 180, weightKg: 90, smokingHistory: 'former' });

      const report = await uploadReport(user.token);
      await analyze(user.token, report.id);

      const profile = callsTo(ENGINEER_PATH)[0].body.profile;
      expect(profile).toHaveProperty('smokingHistory', 'former');
      expect(profile).toHaveProperty('heightCm', 180);
      expect(profile).toHaveProperty('weightKg', 90);
      expect(profile).toHaveProperty('bmi');
      expect(profile).not.toHaveProperty('smoking_history');
      expect(profile).not.toHaveProperty('height_cm');
    });

    it('never sends free-text profile fields (least privilege)', async () => {
      const user = await makeUser('freetext@example.com');
      await request(app)
        .post(PROFILE)
        .set(auth(user.token))
        .send({ age: 40, allergies: ['peanuts'], medications: ['metformin'] });

      const report = await uploadReport(user.token);
      await analyze(user.token, report.id);

      const serialised = JSON.stringify(callsTo(ENGINEER_PATH)[0].body);
      expect(serialised).not.toContain('peanuts');
      expect(serialised).not.toContain('metformin');
    });

    it('unit: buildProfilePayload never invents a value', () => {
      expect(analysisService.buildProfilePayload(null)).toBeUndefined();
      expect(analysisService.buildProfilePayload({})).toBeUndefined();

      const built = analysisService.buildProfilePayload({
        age: 30,
        hypertension: undefined,
        heartDisease: null,
        smokingHistory: 'never',
      });
      expect(Object.keys(built).sort()).toEqual(['age', 'smokingHistory']);
      expect('hypertension' in built).toBe(false);
      expect('heartDisease' in built).toBe(false);

      const withFalse = analysisService.buildProfilePayload({ hypertension: false });
      expect(withFalse).toEqual({ hypertension: false });
    });
  });

  describe('no profile', () => {
    it('still analyses on lab data alone and omits `profile` entirely', async () => {
      const user = await makeUser('noprofile@example.com');
      const probe = await request(app).get(PROFILE).set(auth(user.token));
      expect(probe.status).toBe(404);

      const report = await uploadReport(user.token);
      const res = await analyze(user.token, report.id);

      expect(res.status).toBe(200);
      expect(res.body.data.report.status).toBe('processed');
      expect(res.body.data.analysis.profileUsed).toBe(false);

      const body = callsTo(ENGINEER_PATH)[0].body;
      expect(Object.prototype.hasOwnProperty.call(body, 'profile')).toBe(false);
      expect(body.extraction).toBeDefined();
    });
  });

  describe('ai-service failures are handled distinctly and never 500-with-stack', () => {
    const cases = [
      { name: '401 (bad service key)', failure: { status: 401 }, status: 502, code: 'AI_SERVICE_UNAUTHORIZED' },
      { name: '403', failure: { status: 403 }, status: 502, code: 'AI_SERVICE_UNAUTHORIZED' },
      { name: '422 (validation)', failure: { status: 422 }, status: 422, code: 'AI_SERVICE_REJECTED_INPUT' },
      { name: '500', failure: { status: 500 }, status: 502, code: 'AI_SERVICE_ERROR' },
      { name: '503', failure: { status: 503 }, status: 502, code: 'AI_SERVICE_ERROR' },
      { name: 'timeout', failure: { code: 'ECONNABORTED' }, status: 504, code: 'AI_SERVICE_TIMEOUT' },
      { name: 'connection refused', failure: { code: 'ECONNREFUSED' }, status: 503, code: 'AI_SERVICE_UNAVAILABLE' },
      { name: 'DNS failure', failure: { code: 'ENOTFOUND' }, status: 503, code: 'AI_SERVICE_UNAVAILABLE' },
      { name: 'connection reset', failure: { code: 'ECONNRESET' }, status: 503, code: 'AI_SERVICE_UNAVAILABLE' },
    ];

    it.each(cases)('extraction $name -> $status $code', async ({ failure, status, code }) => {
      const user = await makeUser(`err-${code}-${status}@example.com`);
      const report = await uploadReport(user.token);
      wireAiService({
        extract: () => {
          throw transportError(failure);
        },
      });

      const res = await analyze(user.token, report.id);

      expect(res.status).toBe(status);
      expect(res.body.success).toBe(false);
      expect(res.body.error.code).toBe(code);
      expect(res.body.error.stack).toBeUndefined();
      expect(JSON.stringify(res.body)).not.toMatch(/node_modules|\.js:\d+/);
      expect(JSON.stringify(res.body)).not.toContain(PHI_CANARY);

      const stored = await loadRaw(report.id);
      expect(stored.status).toBe('failed');
      expect(stored.statusMessage).toContain(code);
      expect(stored.statusMessage).not.toContain(PHI_CANARY);
      expect(stored.extraction).toBeUndefined();
      expect(stored.analysis.version).toBe(0);
    });

    it('a malformed envelope from extraction is a 502, not a 500', async () => {
      const user = await makeUser('malformed@example.com');
      const report = await uploadReport(user.token);
      wireAiService({ extract: () => ({ status: 200, data: { parameters: [] } }) });

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(502);
      expect(res.body.error.code).toBe('AI_SERVICE_MALFORMED_RESPONSE');
      expect(res.body.error.stack).toBeUndefined();
    });

    it.each([
      ['null body', null],
      ['a bare array', []],
      ['success:false', { success: false, data: {} }],
      ['data missing', { success: true }],
      ['data not an object', { success: true, data: 'ok' }],
    ])('rejects %s from the features stage', async (label, payload) => {
      const user = await makeUser(`envelope-${label.replace(/\W/g, '')}@example.com`);
      const report = await uploadReport(user.token);
      wireAiService({ engineer: () => ({ status: 200, data: payload }) });

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(502);
      expect(res.body.error.code).toBe('AI_SERVICE_MALFORMED_RESPONSE');
    });

    it('rejects a payload whose keys MongoDB cannot store, without a 500', async () => {
      const user = await makeUser('badkeys@example.com');
      const report = await uploadReport(user.token);
      wireAiService({
        extract: () => okResponse({ ...extractionFixture(), $where: 'sleep(1)' }),
      });

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(502);
      expect(res.body.error.code).toBe('AI_SERVICE_MALFORMED_RESPONSE');
      expect(res.body.error.stack).toBeUndefined();
    });

    it('a features-stage failure still marks the report failed', async () => {
      const user = await makeUser('featfail@example.com');
      const report = await uploadReport(user.token);
      wireAiService({
        engineer: () => {
          throw transportError({ status: 500 });
        },
      });

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(502);

      const stored = await loadRaw(report.id);
      expect(stored.status).toBe('failed');
      expect(stored.extraction).toBeUndefined();
    });

    it('answers 503 when the pipeline is not configured, without touching the report', async () => {
      const user = await makeUser('unconfigured@example.com');
      const report = await uploadReport(user.token);

      const savedUrl = config.aiService.url;
      config.aiService.url = '';
      try {
        const res = await analyze(user.token, report.id);
        expect(res.status).toBe(503);
        expect(res.body.error.code).toBe('AI_SERVICE_NOT_CONFIGURED');
      } finally {
        config.aiService.url = savedUrl;
      }

      const stored = await loadRaw(report.id);
      expect(stored.status).toBe('uploaded');
      expect(outgoing).toHaveLength(0);
    });

    it('reports a missing stored file as 404, not a 500', async () => {
      const user = await makeUser('nofile@example.com');
      const report = await uploadReport(user.token);
      const stored = await loadRaw(report.id);
      const { getStorage } = require('../src/storage');
      await getStorage(stored.storageDriver).remove(stored.storageKey);

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(404);
      expect(res.body.error.stack).toBeUndefined();
      expect(outgoing).toHaveLength(0);
    });
  });

  describe('retry policy', () => {
    it('retries a transient 500 but not a 401', async () => {
      config.aiService.retries = 1;

      const userA = await makeUser('retry500@example.com');
      const reportA = await uploadReport(userA.token);
      let attempts = 0;
      wireAiService({
        extract: () => {
          attempts += 1;
          if (attempts === 1) throw transportError({ status: 500 });
          return okResponse(extractionFixture());
        },
      });
      const resA = await analyze(userA.token, reportA.id);
      expect(resA.status).toBe(200);
      expect(attempts).toBe(2);

      outgoing = [];
      const userB = await makeUser('retry401@example.com');
      const reportB = await uploadReport(userB.token);
      wireAiService({
        extract: () => {
          throw transportError({ status: 401 });
        },
      });
      const resB = await analyze(userB.token, reportB.id);
      expect(resB.status).toBe(502);
      expect(callsTo(EXTRACT_PATH)).toHaveLength(1);
    });

    it('does not retry a 422', async () => {
      config.aiService.retries = 2;
      const user = await makeUser('retry422@example.com');
      const report = await uploadReport(user.token);
      wireAiService({
        extract: () => {
          throw transportError({ status: 422 });
        },
      });

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(422);
      expect(callsTo(EXTRACT_PATH)).toHaveLength(1);
    });

    it('gives a retried attempt a FRESH stream (a stream cannot be replayed)', async () => {
      config.aiService.retries = 1;
      const user = await makeUser('freshstream@example.com');
      const report = await uploadReport(user.token, pdfBytes('retry-payload'));

      const sizes = [];
      let attempts = 0;
      wireAiService({
        extract: async (form) => {
          attempts += 1;
          sizes.push(form.get('file').size);
          if (attempts === 1) throw transportError({ code: 'ECONNRESET' });
          return okResponse(extractionFixture());
        },
      });

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);
      expect(sizes).toHaveLength(2);
      expect(sizes[1]).toBe(sizes[0]);
      expect(sizes[1]).toBeGreaterThan(0);
    });
  });

  describe('warnings survive with their origin', () => {
    it('persists both stages\' warnings and preserves stated provenance', async () => {
      const user = await makeUser('warnings@example.com');
      const report = await uploadReport(user.token);

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);

      const warnings = res.body.data.analysis.warnings;
      const repaired = warnings.find((w) => /PDF repairer/.test(w.message));
      const unitWarning = warnings.find((w) => /creatinine/.test(w.message));
      expect(repaired).toBeDefined();
      expect(repaired.stage).toBe('extraction');
      expect(repaired.module).toBe('module-4-ocr');
      expect(unitWarning).toBeDefined();
      expect(unitWarning.stage).toBe('feature_engineering');

      expect(warnings.filter((w) => /PDF repairer/.test(w.message))).toHaveLength(1);
      expect(warnings).toHaveLength(2);
      expect(warnings[0].stage).toBe('extraction');

      const stored = await loadRaw(report.id);
      expect(stored.analysisWarnings).toHaveLength(2);
      expect(stored.analysis.warningCount).toBe(2);
      expect(stored.analysis.pagesUnreadable).toEqual([2]);
      expect(res.body.data.analysis.pagesUnreadable).toEqual([2]);
    });

    it('still surfaces Module 4 warnings if the service stops propagating them', async () => {
      const user = await makeUser('noprop@example.com');
      const report = await uploadReport(user.token);
      wireAiService({
        engineer: () =>
          okResponse({
            features: { hba1c: 6.8 },
            unmapped: [],
            warnings: [],
          }),
      });

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);
      const warnings = res.body.data.analysis.warnings;
      expect(warnings).toHaveLength(1);
      expect(warnings[0]).toEqual({ stage: 'extraction', message: REPAIR_WARNING });
    });

    it('prefers all_warnings over the backwards-compatible warnings[]', () => {
      const merged = analysisService.collectWarnings(
        { warnings: [] },
        {
          warnings: ['own'],
          upstream_warnings: [{ stage: 'extraction', module: 'm4', message: 'up' }],
          all_warnings: [
            { stage: 'extraction', module: 'm4', message: 'up' },
            { stage: 'feature_engineering', module: 'm5', message: 'own' },
          ],
        }
      );
      expect(merged).toHaveLength(2);
      expect(merged[0]).toEqual({ stage: 'extraction', module: 'm4', message: 'up' });
      expect(merged[1]).toEqual({
        stage: 'feature_engineering',
        module: 'm5',
        message: 'own',
      });
    });

    it('never overwrites an origin the service already stated', () => {
      const tagged = analysisService.tagWarning(
        { stage: 'extraction', code: 'PAGE_UNREADABLE', page: 2 },
        'features'
      );
      expect(tagged.stage).toBe('extraction');
      expect(tagged.code).toBe('PAGE_UNREADABLE');
      expect(tagged.page).toBe(2);

      expect(analysisService.tagWarning({ origin: 'ocr', message: 'x' }, 'features').origin).toBe(
        'ocr'
      );
      expect(analysisService.tagWarning('bare', 'features')).toEqual({
        stage: 'features',
        message: 'bare',
      });
    });

    it('keeps warnings that differ, and does not flatten extra fields', () => {
      const merged = analysisService.collectWarnings(
        { warnings: [{ code: 'REPAIRED', message: 'a', page: 1, severity: 'warn' }] },
        { warnings: [{ code: 'REPAIRED', message: 'b' }, 'c'] }
      );
      expect(merged).toHaveLength(3);
      const fromExtraction = merged.find((w) => w.stage === 'extraction');
      expect(fromExtraction).toMatchObject({
        stage: 'extraction',
        code: 'REPAIRED',
        message: 'a',
        page: 1,
        severity: 'warn',
      });
      expect(merged.filter((w) => w.code === 'REPAIRED')).toHaveLength(2);
      expect(merged).toContainEqual({ stage: 'feature_engineering', message: 'c' });
    });

    it('carries a warning from EVERY stage through with its origin intact', async () => {
      const user = await makeUser('allstagewarnings@example.com');
      const report = await uploadReport(user.token);

      const VALIDATION_WARNING = 'creatinine 42 mg/dl is outside the plausible range';
      const RULES_WARNING = 'the diabetes rule ran on a questionable hba1c';
      const ML_WARNING = 'the kidney predictor was skipped: required features missing';

      wireAiService({
        validate: (body) => {
          const data = validationFixture(body);
          data.warnings = [VALIDATION_WARNING];
          data.all_warnings = [
            ...data.all_warnings,
            { stage: 'validation', module: 6, message: VALIDATION_WARNING },
          ];
          return okResponse(data);
        },
        rules: (body) => {
          const data = rulesFixture(body);
          data.warnings = [RULES_WARNING];
          data.all_warnings = [
            ...data.all_warnings,
            { stage: 'rules', module: 8, message: RULES_WARNING },
          ];
          return okResponse(data);
        },
        predict: (body) => {
          const data = mlFixture(body);
          data.warnings = [ML_WARNING];
          data.all_warnings = [
            ...data.all_warnings,
            { stage: 'ml', module: 9, message: ML_WARNING },
          ];
          return okResponse(data);
        },
      });

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);

      const byStage = (stage) =>
        res.body.data.analysis.warnings.filter((w) => w.stage === stage);

      expect(byStage('extraction')[0].message).toBe(REPAIR_WARNING);
      expect(byStage('extraction')[0].module).toBe('module-4-ocr');
      expect(byStage('feature_engineering')[0].message).toBe(UNIT_WARNING);
      expect(byStage('validation')[0]).toEqual({
        stage: 'validation',
        module: 6,
        message: VALIDATION_WARNING,
      });
      expect(byStage('rules')[0].message).toBe(RULES_WARNING);
      expect(byStage('ml')[0].message).toBe(ML_WARNING);
      expect(res.body.data.analysis.warnings).toHaveLength(5);

      const stored = await loadRaw(report.id);
      expect(stored.analysisWarnings).toHaveLength(5);
      expect(stored.analysis.warningCount).toBe(5);
      const fetched = await getAnalysis(user.token, report.id);
      expect(fetched.body.data.analysis.warnings).toHaveLength(5);
      expect(fetched.body.data.analysis.warnings.map((w) => w.stage).sort()).toEqual([
        'extraction',
        'feature_engineering',
        'ml',
        'rules',
        'validation',
      ]);
    });

    it('carries FUSION and REPORT warnings through with their origins too', async () => {
      const user = await makeUser('reportwarnings@example.com');
      const report = await uploadReport(user.token);

      const FUSION_WARNING = 'the diabetes predictor could not assess this condition';
      const REPORT_WARNING = 'some conditions in this analysis could not be assessed';

      wireAiService({
        report: (body) => {
          const data = clinicalReportFixture(body);
          data.validation_warnings = [
            ...data.validation_warnings,
            { stage: 'fusion', module: 16, message: FUSION_WARNING },
            { stage: 'report', module: 17, message: REPORT_WARNING },
          ];
          return okResponse(data);
        },
      });

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);

      const warnings = res.body.data.analysis.warnings;
      const byStage = (stage) => warnings.filter((w) => w.stage === stage);

      expect(byStage('extraction')[0].message).toBe(REPAIR_WARNING);
      expect(byStage('extraction')[0].module).toBe('module-4-ocr');
      expect(byStage('feature_engineering')[0].message).toBe(UNIT_WARNING);
      expect(byStage('fusion')[0]).toEqual({
        stage: 'fusion',
        module: 16,
        message: FUSION_WARNING,
      });
      expect(byStage('report')[0]).toEqual({
        stage: 'report',
        module: 17,
        message: REPORT_WARNING,
      });
      expect(warnings).toHaveLength(4);
      expect(byStage('report')).toHaveLength(1);

      const stored = await loadRaw(report.id);
      expect(stored.analysis.warningCount).toBe(4);
      const fetched = await getAnalysis(user.token, report.id);
      expect(fetched.body.data.analysis.warnings.map((w) => w.stage).sort()).toEqual([
        'extraction',
        'feature_engineering',
        'fusion',
        'report',
      ]);
    });

    it('keeps every stage\'s warnings when the REPORT stage fails', async () => {
      const user = await makeUser('warnreportfail@example.com');
      const report = await uploadReport(user.token);
      wireAiService({
        report: () => {
          throw transportError({ status: 500 });
        },
      });

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);
      expect(res.body.data.analysis.warnings.map((w) => w.stage).sort()).toEqual([
        'extraction',
        'feature_engineering',
      ]);
    });

    it('keeps upstream warnings even when a downstream stage FAILS', async () => {
      const user = await makeUser('warnpartial@example.com');
      const report = await uploadReport(user.token);
      wireAiService({
        validate: () => {
          throw transportError({ status: 500 });
        },
      });

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);
      expect(res.body.data.analysis.warnings.map((w) => w.stage)).toEqual([
        'extraction',
        'feature_engineering',
      ]);
    });

    it('an empty warnings array is preserved as empty, not dropped', async () => {
      const user = await makeUser('nowarn@example.com');
      const report = await uploadReport(user.token);
      wireAiService({
        extract: () => okResponse({ ...extractionFixture(), warnings: [] }),
        engineer: () =>
          okResponse({
            ...featuresFixture(),
            warnings: [],
            upstream_warnings: [],
            all_warnings: [],
          }),
      });

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);
      expect(res.body.data.analysis.warnings).toEqual([]);
    });
  });

  describe('validation, clinical rules and ML predictors', () => {
    it('runs the whole section-16 chain and persists every stage', async () => {
      const user = await makeUser('fullchain@example.com');
      const report = await uploadReport(user.token);

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);
      expect(res.body.data.report.status).toBe('processed');
      expectFullChain(outgoing.map((c) => c.url));

      const { analysis } = res.body.data;
      for (const stage of [
        'extraction',
        'feature_engineering',
        'validation',
        'rules',
        'ml',
        'report',
      ]) {
        expect(analysis.stages[stage]).toMatchObject({ ok: true });
      }
      expect(analysis.stagesFailed).toEqual([]);

      expect(analysis.validation.valid.hba1c.value).toBe(6.8);
      expect(analysis.validFeatureCount).toBe(2);
      expect(analysis.rejectedFeatureCount).toBe(0);

      expect(analysis.ruleDecisions.decisions[0].condition).toBe('diabetes');
      expect(analysis.ruleDecisions.decisions[0].evidence[0].feature).toBe('hba1c');
      expect(analysis.ruleDecisions.decisions[0].recommendations[0].code).toBe(
        'DISCUSS_WITH_CLINICIAN'
      );
      expect(analysis.mlDecisions.decisions[0].source_kind).toBe('machine_learning');

      expect(analysis.ruleDecisionCount).toBe(1);
      expect(analysis.mlDecisionCount).toBe(1);
      expect(analysis.decisionCount).toBe(2);
      expect(analysis.highestRisk).toBe('High');
      expect(analysis.conditionsFlagged).toEqual(['diabetes']);

      const stored = await loadRaw(report.id);
      expect(stored.featureValidation.valid.hba1c.value).toBe(6.8);
      expect(stored.ruleDecisions.decisions).toHaveLength(1);
      expect(stored.mlDecisions.decisions).toHaveLength(1);
      expect(stored.analysis.decisionCount).toBe(2);
      expect(stored.analysis.highestRisk).toBe('High');
      expect(stored.analysis.stagesFailed).toEqual([]);
    });

    it('feeds each stage the WHOLE unwrapped output of the stage before it', async () => {
      const user = await makeUser('chainbodies@example.com');
      const report = await uploadReport(user.token);
      await analyze(user.token, report.id);

      const validateBody = callsTo(VALIDATE_PATH)[0].body;
      expect(Object.keys(validateBody)).toEqual(['engineered']);
      expect(validateBody.engineered.success).toBeUndefined();
      expect(validateBody.engineered.features.hba1c).toBe(6.8);
      expect(validateBody.engineered.all_warnings).toHaveLength(2);
      expect(validateBody.engineered.upstream.pages_unreadable).toEqual([2]);

      for (const path of [RULES_PATH, PREDICT_PATH]) {
        const body = callsTo(path)[0].body;
        expect(Object.keys(body)).toEqual(['validated']);
        expect(body.validated.valid.hba1c.status).toBe('valid');
        expect(body.validated.all_warnings).toHaveLength(2);
        expect(body).not.toHaveProperty('engineered');
      }
    });

    it('stores EVERY decision, including several for one condition from one source', async () => {
      const user = await makeUser('multidecision@example.com');
      const report = await uploadReport(user.token);

      wireAiService({
        rules: (body) => {
          const data = rulesFixture(body);
          data.decisions = [
            {
              ...data.decisions[0],
              status: 'Indicated',
              risk: 'High',
              metadata: { rule_id: 'HBA1C_DIABETIC_RANGE' },
              evidence: [{ feature: 'hba1c', value: 6.8, unit: '%', threshold: 6.5 }],
            },
            {
              ...data.decisions[0],
              status: 'Borderline',
              risk: 'Medium',
              metadata: { rule_id: 'FASTING_GLUCOSE_IMPAIRED' },
              evidence: [
                { feature: 'blood_glucose', value: 112, unit: 'mg/dl', threshold: 100 },
              ],
            },
          ];
          data.summary = { ...data.summary, decision_count: 2, highest_risk: 'High' };
          return okResponse(data);
        },
      });

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);

      const ruleDecisions = res.body.data.analysis.ruleDecisions.decisions;
      expect(ruleDecisions).toHaveLength(2);
      expect(ruleDecisions.map((d) => d.condition)).toEqual(['diabetes', 'diabetes']);
      expect(ruleDecisions.map((d) => d.source_kind)).toEqual([
        'clinical_rule',
        'clinical_rule',
      ]);
      expect(ruleDecisions.map((d) => d.metadata.rule_id)).toEqual([
        'HBA1C_DIABETIC_RANGE',
        'FASTING_GLUCOSE_IMPAIRED',
      ]);
      expect(ruleDecisions.map((d) => d.risk)).toEqual(['High', 'Medium']);
      expect(ruleDecisions[0].evidence[0].feature).toBe('hba1c');
      expect(ruleDecisions[1].evidence[0].feature).toBe('blood_glucose');

      expect(res.body.data.analysis.ruleDecisionCount).toBe(2);
      expect(res.body.data.analysis.decisionCount).toBe(3);
      expect(res.body.data.analysis.highestRisk).toBe('High');
      expect(res.body.data.analysis.conditionsFlagged).toEqual(['diabetes']);

      const stored = await loadRaw(report.id);
      expect(stored.ruleDecisions.decisions).toHaveLength(2);
      expect(stored.analysis.ruleDecisionCount).toBe(2);

      const fetched = await getAnalysis(user.token, report.id);
      const retrieved = fetched.body.data.analysis.ruleDecisions.decisions;
      expect(retrieved).toHaveLength(2);
      expect(retrieved).toEqual(ruleDecisions);
    });

    it('never calls the in-memory Module 7 repository', async () => {
      const user = await makeUser('norepo@example.com');
      const report = await uploadReport(user.token);
      await analyze(user.token, report.id);

      expect(outgoing.map((c) => c.url)).not.toContain('/api/v1/repository/load');
      expect(outgoing.some((c) => c.url.includes('/repository'))).toBe(false);
    });

    it('gives the fast stages their OWN timeout, never the extraction one', async () => {
      const user = await makeUser('timeouts@example.com');
      const report = await uploadReport(user.token);
      await analyze(user.token, report.id);

      const timeoutFor = (url) => callsTo(url)[0].options.timeout;
      expect(timeoutFor(EXTRACT_PATH)).toBe(config.aiService.timeoutMs);
      expect(timeoutFor(VALIDATE_PATH)).toBe(config.aiService.validateTimeoutMs);
      expect(timeoutFor(RULES_PATH)).toBe(config.aiService.rulesTimeoutMs);
      expect(timeoutFor(PREDICT_PATH)).toBe(config.aiService.mlTimeoutMs);
      expect(timeoutFor(REPORT_PATH)).toBe(config.aiService.reportTimeoutMs);

      for (const url of [VALIDATE_PATH, RULES_PATH, PREDICT_PATH, REPORT_PATH]) {
        expect(timeoutFor(url)).toBeLessThan(config.aiService.timeoutMs);
      }
    });

    it('runs rules and ML CONCURRENTLY, not one after the other', async () => {
      const user = await makeUser('concurrentstages@example.com');
      const report = await uploadReport(user.token);

      let releaseRules;
      const rulesGate = new Promise((resolve) => {
        releaseRules = resolve;
      });
      const events = [];
      wireAiService({
        rules: async (body) => {
          events.push('rules:start');
          await rulesGate;
          events.push('rules:end');
          return okResponse(rulesFixture(body));
        },
        predict: async (body) => {
          events.push('ml:start');
          releaseRules();
          events.push('ml:end');
          return okResponse(mlFixture(body));
        },
      });

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);
      expect(events.indexOf('ml:start')).toBeLessThan(events.indexOf('rules:end'));
    });
  });

  describe('clinical report (Modules 17-20)', () => {
    it('runs the chain THROUGH to a persisted clinical report', async () => {
      const user = await makeUser('report@example.com');
      const report = await uploadReport(user.token);

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);
      expect(res.body.data.report.status).toBe('processed');
      expectFullChain(outgoing.map((c) => c.url));

      const { analysis } = res.body.data;
      expect(analysis.stages.report).toMatchObject({ ok: true });
      expect(analysis.report.report_version).toBe('1.0.0');
      expect(analysis.report.conditions[0].condition).toBe('diabetes');
      expect(analysis.report.fusion.fused[0].hybrid).toBe(true);

      expect(analysis.overallStatus).toBe('Needs Medical Attention');
      expect(analysis.overallStatusLabel).toBe('Needs Medical Attention');
      expect(analysis.overallRisk).toBe('High');
      expect(analysis.assessmentComplete).toBe(true);
      expect(analysis.anyAssessed).toBe(true);
      expect(analysis.conditionCount).toBe(1);
      expect(analysis.criticalConditionCount).toBe(1);
      expect(analysis.unassessedConditionCount).toBe(0);
      expect(analysis.recommendationCount).toBe(1);
      expect(analysis.laboratoryValueCount).toBe(2);

      const stored = await loadRaw(report.id);
      expect(stored.clinicalReport.overall.rule_applied).toBe('abnormal_with_high_risk');
      expect(stored.analysis.overallStatus).toBe('Needs Medical Attention');
      expect(stored.analysis.stagesFailed).toEqual([]);
    });

    it('sends Module 6\'s WHOLE data object, `rejected` map included', async () => {
      const user = await makeUser('reportbody@example.com');
      const report = await uploadReport(user.token);
      wireAiService({
        validate: (body) => {
          const data = validationFixture(body);
          data.rejected = {
            creatinine: {
              name: 'creatinine',
              value: 884,
              unit: 'umol/l',
              status: 'rejected',
              reason_code: 'IMPLAUSIBLE_HIGH',
              reason: 'outside the plausible range for this analyte',
            },
          };
          return okResponse(data);
        },
      });
      await analyze(user.token, report.id);

      const body = callsTo(REPORT_PATH)[0].body;
      expect(Object.keys(body)).toEqual(['validated']);
      expect(body.validated.success).toBeUndefined();
      expect(body.validated.rejected.creatinine.reason_code).toBe('IMPLAUSIBLE_HIGH');
      expect(body.validated.valid.hba1c.status).toBe('valid');
      expect(body.validated.all_warnings).toHaveLength(2);
      expect(body).not.toHaveProperty('engineered');
      expect(callsTo(REPORT_PATH)[0].options.headers['Content-Type']).toBe('application/json');
    });

    it('never calls /decisions/fuse - the report carries that fusion already', async () => {
      const user = await makeUser('nofuse@example.com');
      const report = await uploadReport(user.token);
      await analyze(user.token, report.id);

      expect(outgoing.map((c) => c.url)).not.toContain(FUSE_PATH);
      expect(outgoing.some((c) => c.url.includes('/decisions'))).toBe(false);
      const stored = await loadRaw(report.id);
      expect(stored.clinicalReport.fusion.fused).toHaveLength(1);
    });

    it('runs the report CONCURRENTLY with rules and ML', async () => {
      const user = await makeUser('concurrentreport@example.com');
      const report = await uploadReport(user.token);

      let releaseRules;
      const rulesGate = new Promise((resolve) => {
        releaseRules = resolve;
      });
      const events = [];
      wireAiService({
        rules: async (body) => {
          events.push('rules:start');
          await rulesGate;
          return okResponse(rulesFixture(body));
        },
        report: async (body) => {
          events.push('report:start');
          releaseRules();
          return okResponse(clinicalReportFixture(body));
        },
      });

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);
      expect(events).toEqual(['rules:start', 'report:start']);
    });

    it('retrieves the stored report from GET /reports/:id/analysis', async () => {
      const user = await makeUser('reportget@example.com');
      const report = await uploadReport(user.token);
      await analyze(user.token, report.id);

      const res = await getAnalysis(user.token, report.id);
      expect(res.status).toBe(200);
      expect(res.body.data.analysis.report.overall.status).toBe('Needs Medical Attention');
      expect(res.body.data.analysis.report.fusion.fused[0].condition).toBe('diabetes');
      expect(res.body.data.analysis.overallStatusLabel).toBe('Needs Medical Attention');
    });

    it('serves the report on its own from GET /reports/:id/report', async () => {
      const user = await makeUser('reportroute@example.com');
      const report = await uploadReport(user.token);
      await analyze(user.token, report.id);

      const res = await getClinicalReport(user.token, report.id);
      expect(res.status).toBe(200);
      expect(res.body.success).toBe(true);
      expect(res.body.data.clinicalReport.report_version).toBe('1.0.0');
      expect(res.body.data.clinicalReport.laboratory_values).toHaveLength(2);
      expect(res.body.data.overall).toEqual({
        status: 'Needs Medical Attention',
        statusLabel: 'Needs Medical Attention',
        risk: 'High',
        complete: true,
        anyAssessed: true,
      });
      expect(res.body.data.report.id).toBe(report.id);
    });

    it('404s on GET /report before the report has ever been analysed', async () => {
      const user = await makeUser('reportnotyet@example.com');
      const report = await uploadReport(user.token);
      const res = await getClinicalReport(user.token, report.id);
      expect(res.status).toBe(404);
      expect(res.body.error.code).toBe('NOT_FOUND');
    });

    it('rejects a non-ObjectId id on GET /report before it reaches a query', async () => {
      const user = await makeUser('reportbadid@example.com');
      for (const id of ['not-an-id', '../../etc/passwd', '{"$ne":null}']) {
        const res = await getClinicalReport(user.token, encodeURIComponent(id));
        expect(res.status).toBe(422);
      }
    });

    it('never persists raw report text through the report stage', async () => {
      const user = await makeUser('reportnotext@example.com');
      const report = await uploadReport(user.token);
      await analyze(user.token, report.id);

      const stored = await loadRaw(report.id);
      expect(JSON.stringify(stored.clinicalReport)).not.toContain('raw_text');
      expect(JSON.stringify(stored.clinicalReport)).not.toContain(PHI_CANARY);

      const res = await getClinicalReport(user.token, report.id);
      expect(JSON.stringify(res.body)).not.toContain(PHI_CANARY);
    });
  });

  describe('Module 18 overall status - the fourth case survives to the API', () => {
    async function analyseWithReport(email, buildReport) {
      const user = await makeUser(email);
      const report = await uploadReport(user.token);
      wireAiService({ report: (body) => okResponse(buildReport(body)) });
      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);
      return { user, report, res };
    }

    it('NOTHING ASSESSED: status is null, label is "Not Assessed", complete false', async () => {
      const { user, report, res } = await analyseWithReport(
        'notassessed@example.com',
        nothingAssessedReport
      );

      const { analysis } = res.body.data;
      expect(analysis.overallStatus).toBeNull();
      expect(analysis.overallStatusLabel).toBe('Not Assessed');
      expect(analysis.overallRisk).toBeNull();
      expect(analysis.assessmentComplete).toBe(false);
      expect(analysis.anyAssessed).toBe(false);
      expect(analysis.unassessedConditionCount).toBe(2);

      expect(analysis.overallStatusLabel).not.toBe('Healthy');
      expect(JSON.stringify(analysis.overallStatus)).toBe('null');

      expect(analysis.report.overall.caveat).not.toBeNull();
      expect(analysis.report.overall.rule_applied).toBe('nothing_assessed');

      const fetched = await getAnalysis(user.token, report.id);
      expect(fetched.body.data.analysis.overallStatus).toBeNull();
      expect(fetched.body.data.analysis.overallStatusLabel).toBe('Not Assessed');
      expect(fetched.body.data.analysis.assessmentComplete).toBe(false);
      expect(fetched.body.data.analysis.report.overall.caveat).not.toBeNull();

      const only = await getClinicalReport(user.token, report.id);
      expect(only.status).toBe(200);
      expect(only.body.data.overall).toEqual({
        status: null,
        statusLabel: 'Not Assessed',
        risk: null,
        complete: false,
        anyAssessed: false,
      });

      const stored = await loadRaw(report.id);
      expect(stored.analysis.overallStatus).toBeNull();
      expect(stored.analysis.overallStatusLabel).toBe('Not Assessed');
      expect(stored.analysis.anyAssessed).toBe(false);
    });

    it('produces all FOUR distinct outcomes, never three', async () => {
      const cases = [
        [null, 'Not Assessed', null, false],
        ['Healthy', 'Healthy', 'Low', true],
        ['Needs Monitoring', 'Needs Monitoring', 'Medium', true],
        ['Needs Medical Attention', 'Needs Medical Attention', 'High', true],
      ];

      const observed = [];
      for (const [status, label, risk, assessed] of cases) {
        const { res } = await analyseWithReport(
          `overall-${String(status)}@example.com`.toLowerCase().replace(/\s+/g, '-'),
          (body) => {
            const base =
              status === null ? nothingAssessedReport(body) : clinicalReportFixture(body);
            return {
              ...base,
              overall: {
                ...base.overall,
                status,
                status_label: label,
                risk,
                any_assessed: assessed,
                complete: assessed,
              },
              overall_risk: risk,
            };
          }
        );
        const { analysis } = res.body.data;
        observed.push([analysis.overallStatus, analysis.overallStatusLabel, analysis.overallRisk]);
      }

      expect(observed).toEqual([
        [null, 'Not Assessed', null],
        ['Healthy', 'Healthy', 'Low'],
        ['Needs Monitoring', 'Needs Monitoring', 'Medium'],
        ['Needs Medical Attention', 'Needs Medical Attention', 'High'],
      ]);
      expect(new Set(observed.map((o) => o[1])).size).toBe(4);
    });

    it('a PARTIAL assessment never presents as complete', async () => {
      const { user, report, res } = await analyseWithReport(
        'partialassess@example.com',
        (body) => {
          const base = clinicalReportFixture(body);
          return {
            ...base,
            overall: {
              ...base.overall,
              status: 'Healthy',
              status_label: 'Healthy',
              risk: 'Low',
              rule_applied: 'no_abnormal_findings',
              any_assessed: true,
              complete: false,
              caveat: 'Some topics in this analysis could not be assessed.',
              unassessed_condition_count: 1,
              unassessed_conditions: ['kidney_disease'],
            },
            overall_risk: 'Low',
            unassessed_conditions: ['kidney_disease'],
            summary: { ...base.summary, unassessed_count: 1 },
          };
        }
      );

      const { analysis } = res.body.data;
      expect(analysis.overallStatus).toBe('Healthy');
      expect(analysis.assessmentComplete).toBe(false);
      expect(analysis.unassessedConditionCount).toBe(1);
      expect(analysis.report.overall.caveat).not.toBeNull();
      expect(analysis.report.unassessed_conditions).toEqual(['kidney_disease']);

      const only = await getClinicalReport(user.token, report.id);
      expect(only.body.data.overall.complete).toBe(false);
      expect(only.body.data.overall.status).toBe('Healthy');

      const stored = await loadRaw(report.id);
      expect(stored.analysis.assessmentComplete).toBe(false);
    });

    it('an UNRECOGNISED status degrades to "Not Assessed", never to "Healthy"', async () => {
      for (const bogus of ['Fine', '', 'healthy', 42, {}]) {
        const { res } = await analyseWithReport(
          `bogus-${String(typeof bogus)}-${String(bogus).slice(0, 4) || 'x'}@example.com`
            .toLowerCase()
            .replace(/[^a-z0-9@.-]/g, ''),
          (body) => {
            const base = clinicalReportFixture(body);
            return {
              ...base,
              overall: { ...base.overall, status: bogus, status_label: 'Healthy' },
            };
          }
        );
        expect(res.body.data.analysis.overallStatus).toBeNull();
        expect(res.body.data.analysis.overallStatusLabel).toBe('Not Assessed');
        expect(res.body.data.analysis.assessmentComplete).toBe(false);
        expect(res.body.data.analysis.anyAssessed).toBe(false);
      }
    });

    it('unit: summariseReport derives the label from the status, in one place', () => {
      const { summariseReport } = analysisService;

      expect(summariseReport(null).overallStatusLabel).toBeUndefined();
      expect(summariseReport(null).overallStatus).toBeUndefined();

      const lying = summariseReport({
        overall: { status: null, status_label: 'Healthy', any_assessed: true, complete: true },
      });
      expect(lying.overallStatus).toBeNull();
      expect(lying.overallStatusLabel).toBe('Not Assessed');
      expect(lying.anyAssessed).toBe(false);
      expect(lying.assessmentComplete).toBe(false);

      expect(summariseReport({ overall: { status: 'Healthy' } }).assessmentComplete).toBe(false);
      expect(summariseReport({ overall: { status: 'Healthy', risk: 'Severe' } }).overallRisk)
        .toBeNull();
      expect(analysisService.OVERALL_STATUS_VALUES).not.toContain(
        analysisService.NOT_ASSESSED_LABEL
      );
    });
  });

  describe('partial failure - a stage that fails never claims success', () => {
    it('validation fails: features are still stored, rules and ML are SKIPPED', async () => {
      const user = await makeUser('valfail@example.com');
      const report = await uploadReport(user.token);
      wireAiService({
        validate: () => {
          throw transportError({ status: 500 });
        },
      });

      const res = await analyze(user.token, report.id);

      expect(res.status).toBe(200);
      expect(res.body.data.report.status).toBe('partial');
      expect(res.body.data.analysis.stages.validation).toMatchObject({
        ok: false,
        errorCode: 'AI_SERVICE_ERROR',
      });
      expect(res.body.data.analysis.stages.rules).toEqual({
        ok: false,
        skipped: true,
        reasonCode: 'VALIDATION_UNAVAILABLE',
      });
      expect(res.body.data.analysis.stages.ml.skipped).toBe(true);
      expect(res.body.data.analysis.stages.report).toEqual({
        ok: false,
        skipped: true,
        reasonCode: 'VALIDATION_UNAVAILABLE',
      });
      expect(res.body.data.analysis.stages.explanation).toEqual({
        ok: false,
        skipped: true,
        reasonCode: 'REPORT_UNAVAILABLE',
      });
      expect(res.body.data.analysis.stages.guidance).toEqual({
        ok: false,
        skipped: true,
        reasonCode: 'REPORT_UNAVAILABLE',
      });
      expect(res.body.data.analysis.stagesFailed).toEqual([
        'validation',
        'rules',
        'ml',
        'report',
        'explanation',
        'guidance',
      ]);

      expect(callsTo(RULES_PATH)).toHaveLength(0);
      expect(callsTo(PREDICT_PATH)).toHaveLength(0);
      expect(callsTo(REPORT_PATH)).toHaveLength(0);
      expect(callsTo(EXPLAIN_PATH)).toHaveLength(0);
      expect(callsTo(GUIDANCE_PATH)).toHaveLength(0);

      const stored = await loadRaw(report.id);
      expect(stored.status).toBe('partial');
      expect(stored.analysis.version).toBe(1);
      expect(stored.extraction.extracted_parameters).toHaveLength(1);
      expect(stored.features.features.hba1c).toBe(6.8);
      expect(stored.featureValidation).toBeUndefined();
      expect(stored.ruleDecisions).toBeUndefined();
      expect(stored.mlDecisions).toBeUndefined();
      expect(stored.clinicalReport).toBeUndefined();
      expect(stored.analysis.decisionCount).toBeUndefined();
      expect(stored.analysis.highestRisk).toBeUndefined();
      expect(stored.analysis.validFeatureCount).toBeUndefined();
      expect(stored.analysis.overallStatus).toBeUndefined();
      expect(stored.analysis.overallStatusLabel).toBeUndefined();
    });

    it('rules fail: the ML result is NOT lost', async () => {
      const user = await makeUser('rulesfail@example.com');
      const report = await uploadReport(user.token);
      wireAiService({
        rules: () => {
          throw transportError({ code: 'ECONNABORTED' });
        },
      });

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);
      expect(res.body.data.report.status).toBe('partial');
      expect(res.body.data.analysis.stagesFailed).toEqual(['rules']);
      expect(res.body.data.analysis.stages.rules).toMatchObject({
        ok: false,
        errorCode: 'AI_SERVICE_TIMEOUT',
      });
      expect(res.body.data.analysis.stages.ml.ok).toBe(true);

      const stored = await loadRaw(report.id);
      expect(stored.featureValidation).toBeDefined();
      expect(stored.ruleDecisions).toBeUndefined();
      expect(stored.mlDecisions.decisions).toHaveLength(1);
      expect(stored.analysis.ruleDecisionCount).toBeUndefined();
      expect(stored.analysis.mlDecisionCount).toBe(1);
      expect(stored.analysis.decisionCount).toBe(1);
      expect(stored.analysis.highestRisk).toBe('Medium');
    });

    it('ML fails: the rule decisions are NOT lost', async () => {
      const user = await makeUser('mlfail@example.com');
      const report = await uploadReport(user.token);
      wireAiService({
        predict: () => {
          throw transportError({ status: 503 });
        },
      });

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);
      expect(res.body.data.analysis.stagesFailed).toEqual(['ml']);
      expect(res.body.data.analysis.ruleDecisions.decisions).toHaveLength(1);
      expect(res.body.data.analysis.mlDecisions).toBeNull();

      const stored = await loadRaw(report.id);
      expect(stored.ruleDecisions.decisions).toHaveLength(1);
      expect(stored.mlDecisions).toBeUndefined();
      expect(stored.analysis.highestRisk).toBe('High');
    });

    it('the report fails: the validation and both decision sources are NOT lost', async () => {
      const user = await makeUser('reportfail@example.com');
      const report = await uploadReport(user.token);
      wireAiService({
        report: () => {
          throw transportError({ status: 500 });
        },
      });

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);
      expect(res.body.data.report.status).toBe('partial');
      expect(res.body.data.analysis.stagesFailed).toEqual([
        'report',
        'explanation',
        'guidance',
      ]);
      expect(res.body.data.analysis.stages.explanation).toEqual({
        ok: false,
        skipped: true,
        reasonCode: 'REPORT_UNAVAILABLE',
      });
      expect(callsTo(EXPLAIN_PATH)).toHaveLength(0);
      expect(res.body.data.analysis.explanation).toBeNull();
      expect(res.body.data.analysis.explanationAvailable).toBeUndefined();
      expect(res.body.data.analysis.stages.report).toMatchObject({
        ok: false,
        errorCode: 'AI_SERVICE_ERROR',
      });
      expect(res.body.data.analysis.stages.rules.ok).toBe(true);
      expect(res.body.data.analysis.stages.ml.ok).toBe(true);
      expect(res.body.data.analysis.ruleDecisions.decisions).toHaveLength(1);
      expect(res.body.data.analysis.mlDecisions.decisions).toHaveLength(1);
      expect(res.body.data.analysis.report).toBeNull();
      expect(res.body.data.analysis.overallStatus).toBeUndefined();
      expect(res.body.data.analysis.overallStatusLabel).toBeUndefined();

      const stored = await loadRaw(report.id);
      expect(stored.clinicalReport).toBeUndefined();
      expect(stored.featureValidation).toBeDefined();
      expect(stored.ruleDecisions.decisions).toHaveLength(1);

      const only = await getClinicalReport(user.token, report.id);
      expect(only.status).toBe(404);
      expect(JSON.stringify(only.body)).not.toContain(PHI_CANARY);
    });

    it('rules fail: the clinical report is still produced', async () => {
      const user = await makeUser('rulesfailreport@example.com');
      const report = await uploadReport(user.token);
      wireAiService({
        rules: () => {
          throw transportError({ status: 503 });
        },
      });

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);
      expect(res.body.data.analysis.stagesFailed).toEqual(['rules']);
      expect(res.body.data.analysis.stages.report.ok).toBe(true);
      expect(res.body.data.analysis.report.report_version).toBe('1.0.0');
      expect(res.body.data.analysis.overallStatus).toBe('Needs Medical Attention');
    });

    it('a partial re-run REMOVES the previous run\'s stale clinical report', async () => {
      const user = await makeUser('stalereport@example.com');
      const report = await uploadReport(user.token);
      expect((await analyze(user.token, report.id)).body.data.report.status).toBe('processed');

      wireAiService({
        report: () => {
          throw transportError({ status: 500 });
        },
      });
      const second = await analyze(user.token, report.id);
      expect(second.body.data.analysis.version).toBe(2);

      const stored = await loadRaw(report.id);
      expect(stored.clinicalReport).toBeUndefined();
      expect(stored.analysis.overallStatus).toBeUndefined();
      expect(stored.analysis.overallStatusLabel).toBeUndefined();
      expect(stored.analysis.assessmentComplete).toBeUndefined();
    });

    it('a report-stage failure records a statusMessage carrying no PHI', async () => {
      const user = await makeUser('reportfailmsg@example.com');
      const report = await uploadReport(user.token);
      wireAiService({
        report: () => {
          throw transportError({ status: 500 });
        },
      });
      await analyze(user.token, report.id);

      const detail = await request(app).get(`${REPORTS}/${report.id}`).set(auth(user.token));
      expect(detail.body.data.report.statusMessage).toBe(
        `ANALYSIS_PARTIAL: ${analysisService.SAFE_STATUS_MESSAGES.ANALYSIS_PARTIAL}`
      );
      expect(detail.body.data.report.statusMessage).not.toContain(PHI_CANARY);
      expect(JSON.stringify(detail.body)).not.toContain(PHI_CANARY);
    });

    it('a malformed downstream envelope is a recorded stage failure, not a 500', async () => {
      const user = await makeUser('downstreammalformed@example.com');
      const report = await uploadReport(user.token);
      wireAiService({ predict: () => ({ status: 200, data: { decisions: [] } }) });

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);
      expect(res.body.error).toBeUndefined();
      expect(res.body.data.analysis.stages.ml).toMatchObject({
        ok: false,
        errorCode: 'AI_SERVICE_MALFORMED_RESPONSE',
      });
    });

    it('a partial run records a statusMessage from the safe table only', async () => {
      const user = await makeUser('partialmsg@example.com');
      const report = await uploadReport(user.token);
      wireAiService({
        rules: () => {
          throw transportError({ status: 500 });
        },
      });
      await analyze(user.token, report.id);

      const detail = await request(app).get(`${REPORTS}/${report.id}`).set(auth(user.token));
      expect(detail.body.data.report.statusMessage).toBe(
        `ANALYSIS_PARTIAL: ${analysisService.SAFE_STATUS_MESSAGES.ANALYSIS_PARTIAL}`
      );
      expect(detail.body.data.report.statusMessage).not.toContain(PHI_CANARY);
      expect(JSON.stringify(detail.body)).not.toContain(PHI_CANARY);
    });

    it('a stage record can only ever hold a machine code we defined', () => {
      const leaky = { code: `LEAK_${PHI_CANARY}`, message: PHI_CANARY };
      expect(analysisService.safeErrorCode(leaky)).toBe('ANALYSIS_STAGE_FAILED');
      expect(analysisService.safeErrorCode(new Error(PHI_CANARY))).toBe(
        'ANALYSIS_STAGE_FAILED'
      );
      expect(analysisService.safeErrorCode({ code: 'AI_SERVICE_TIMEOUT' })).toBe(
        'AI_SERVICE_TIMEOUT'
      );
      expect(analysisService.safeErrorCode(null)).toBe('ANALYSIS_STAGE_FAILED');
    });

    it('a partial re-run REMOVES the previous run\'s stale decisions', async () => {
      const user = await makeUser('stalestage@example.com');
      const report = await uploadReport(user.token);

      const first = await analyze(user.token, report.id);
      expect(first.body.data.report.status).toBe('processed');

      wireAiService({
        rules: () => {
          throw transportError({ status: 500 });
        },
      });
      const second = await analyze(user.token, report.id);
      expect(second.status).toBe(200);
      expect(second.body.data.analysis.version).toBe(2);

      const stored = await loadRaw(report.id);
      expect(stored.ruleDecisions).toBeUndefined();
      expect(stored.analysis.ruleDecisionCount).toBeUndefined();
      expect(stored.mlDecisions.decisions).toHaveLength(1);
    });

    it('a FATAL stage still loses nothing that was already stored', async () => {
      const user = await makeUser('fatalkeeps@example.com');
      const report = await uploadReport(user.token);
      expect((await analyze(user.token, report.id)).status).toBe(200);

      wireAiService({
        engineer: () => {
          throw transportError({ status: 500 });
        },
      });
      const second = await analyze(user.token, report.id);
      expect(second.status).toBe(502);

      const stored = await loadRaw(report.id);
      expect(stored.status).toBe('failed');
      expect(stored.analysis.version).toBe(1);
      expect(stored.ruleDecisions.decisions).toHaveLength(1);
      expect(stored.mlDecisions.decisions).toHaveLength(1);
    });

    it('unit: highestRisk fuses Low < Medium < High and never invents one', () => {
      const { highestRisk } = analysisService;
      expect(highestRisk('Low', 'High')).toBe('High');
      expect(highestRisk('Medium', 'Low')).toBe('Medium');
      expect(highestRisk(undefined, null)).toBeNull();
      expect(highestRisk('Catastrophic')).toBeNull();
      expect(highestRisk('Catastrophic', 'Low')).toBe('Low');
    });
  });

  describe('status lifecycle', () => {
    it('moves uploaded -> processing -> processed', async () => {
      const user = await makeUser('lifecycle@example.com');
      const report = await uploadReport(user.token);

      let observedDuringRun = null;
      wireAiService({
        extract: async () => {
          const mid = await Report.findById(report.id);
          observedDuringRun = mid.status;
          return okResponse(extractionFixture());
        },
      });

      const res = await analyze(user.token, report.id);
      expect(observedDuringRun).toBe('processing');
      expect(res.body.data.report.status).toBe('processed');
    });

    it('moves uploaded -> processing -> failed and records a safe statusMessage', async () => {
      const user = await makeUser('lifecyclefail@example.com');
      const report = await uploadReport(user.token);
      wireAiService({
        extract: () => {
          throw transportError({ code: 'ECONNREFUSED' });
        },
      });

      await analyze(user.token, report.id);

      const detail = await request(app).get(`${REPORTS}/${report.id}`).set(auth(user.token));
      expect(detail.status).toBe(200);
      expect(detail.body.data.report.status).toBe('failed');
      expect(detail.body.data.report.statusMessage).toBe(
        'AI_SERVICE_UNAVAILABLE: The analysis service was unreachable'
      );
    });

    it('statusMessage can only ever be a value from the safe table', () => {
      const leaky = new Error(`mongo rejected value ${PHI_CANARY}`);
      leaky.code = 'SOME_UNMAPPED_CODE';
      expect(analysisService.safeStatusMessage(leaky)).toBe(
        analysisService.GENERIC_STATUS_MESSAGE
      );
      expect(analysisService.safeStatusMessage(leaky)).not.toContain(PHI_CANARY);

      const mapped = { code: 'AI_SERVICE_TIMEOUT', message: PHI_CANARY };
      expect(analysisService.safeStatusMessage(mapped)).not.toContain(PHI_CANARY);
      expect(analysisService.safeStatusMessage(null)).toBe(
        analysisService.GENERIC_STATUS_MESSAGE
      );
    });

    it('lists a processed report under ?status=processed', async () => {
      const user = await makeUser('statusfilter@example.com');
      const report = await uploadReport(user.token);
      await analyze(user.token, report.id);

      const res = await request(app)
        .get(`${REPORTS}?status=processed`)
        .set(auth(user.token));
      expect(res.status).toBe(200);
      expect(res.body.data.reports.map((r) => r.id)).toEqual([report.id]);
    });
  });

  describe('concurrency guard', () => {
    it('two simultaneous analyses: one runs, the other gets 409', async () => {
      const user = await makeUser('concurrent@example.com');
      const report = await uploadReport(user.token);

      let release;
      const gate = new Promise((resolve) => {
        release = resolve;
      });
      let started = 0;
      wireAiService({
        extract: async () => {
          started += 1;
          await gate;
          return okResponse(extractionFixture());
        },
      });

      const first = analyze(user.token, report.id).then((res) => res);
      await new Promise((resolve) => setTimeout(resolve, 300));
      const second = await analyze(user.token, report.id);

      expect(second.status).toBe(409);
      expect(second.body.error.code).toBe('ANALYSIS_IN_PROGRESS');

      release();
      const firstRes = await first;
      expect(firstRes.status).toBe(200);

      expect(started).toBe(1);
      expect(callsTo(EXTRACT_PATH)).toHaveLength(1);

      const stored = await loadRaw(report.id);
      expect(stored.analysis.version).toBe(1);
      expect(stored.analysis.runCount).toBe(1);
    });

    it('the lock is a single atomic claim, so only one of many callers wins', async () => {
      const user = await makeUser('atomicclaim@example.com');
      const report = await uploadReport(user.token);
      const userDoc = { _id: user.id, id: user.id, role: ROLES.PATIENT };

      const claims = await Promise.all(
        [1, 2, 3, 4, 5].map((n) =>
          analysisService.claimForAnalysis({
            user: userDoc,
            reportId: report.id,
            requestId: `req-${n}`,
          })
        )
      );
      expect(claims.filter(Boolean)).toHaveLength(1);
    });

    it('takes over a lock stranded by a crashed run, once it is stale', async () => {
      const user = await makeUser('stalelock@example.com');
      const report = await uploadReport(user.token);
      const userDoc = { _id: user.id, id: user.id, role: ROLES.PATIENT };

      await Report.updateOne(
        { _id: report.id },
        {
          $set: {
            status: 'processing',
            'analysis.startedAt': new Date(Date.now() - config.aiService.lockTtlMs - 1000),
            'analysis.requestId': 'dead-run',
          },
        }
      );

      const claimed = await analysisService.claimForAnalysis({
        user: userDoc,
        reportId: report.id,
        requestId: 'new-run',
      });
      expect(claimed).not.toBeNull();
      expect(claimed.analysis.requestId).toBe('new-run');
    });

    it('a superseded run cannot overwrite the run that took its lock', async () => {
      const user = await makeUser('superseded@example.com');
      const report = await uploadReport(user.token);
      const userDoc = { _id: user.id, id: user.id, role: ROLES.PATIENT };

      const claimed = await analysisService.claimForAnalysis({
        user: userDoc,
        reportId: report.id,
        requestId: 'run-one',
      });
      await Report.updateOne({ _id: report.id }, { $set: { 'analysis.requestId': 'run-two' } });

      await expect(
        analysisService.runAnalysis({ user: userDoc, report: claimed, requestId: 'run-one' })
      ).rejects.toMatchObject({ statusCode: 409, code: 'ANALYSIS_SUPERSEDED' });

      const stored = await loadRaw(report.id);
      expect(stored.analysis.version).toBe(0);
      expect(stored.extraction).toBeUndefined();
    });
  });

  describe('re-run semantics (overwrite, non-destructive on failure)', () => {
    it('a successful re-run overwrites and bumps the version', async () => {
      const user = await makeUser('rerun@example.com');
      const report = await uploadReport(user.token);

      await analyze(user.token, report.id);
      wireAiService({
        extract: () => okResponse({ ...extractionFixture(), extraction_confidence: 0.5 }),
        engineer: () => okResponse({ ...featuresFixture(), features: { hba1c: 7.4 } }),
      });
      const second = await analyze(user.token, report.id);

      expect(second.status).toBe(200);
      expect(second.body.data.analysis.version).toBe(2);
      expect(second.body.data.analysis.runCount).toBe(2);
      expect(second.body.data.analysis.features.features.hba1c).toBe(7.4);

      const stored = await loadRaw(report.id);
      expect(stored.extraction.extraction_confidence).toBe(0.5);
      expect(stored.features.features.blood_glucose).toBeUndefined();
    });

    it('a FAILED re-run leaves the previous successful analysis intact', async () => {
      const user = await makeUser('rerunfail@example.com');
      const report = await uploadReport(user.token);

      const first = await analyze(user.token, report.id);
      expect(first.status).toBe(200);

      wireAiService({
        extract: () => {
          throw transportError({ code: 'ECONNABORTED' });
        },
      });
      const second = await analyze(user.token, report.id);
      expect(second.status).toBe(504);

      const stored = await loadRaw(report.id);
      expect(stored.status).toBe('failed');
      expect(stored.analysis.runCount).toBe(2);
      expect(stored.analysis.version).toBe(1);
      expect(stored.features.features.hba1c).toBe(6.8);

      const retrieved = await getAnalysis(user.token, report.id);
      expect(retrieved.status).toBe(200);
      expect(retrieved.body.data.analysis.version).toBe(1);
    });

    it('a failed report can be analysed again successfully', async () => {
      const user = await makeUser('recover@example.com');
      const report = await uploadReport(user.token);
      wireAiService({
        extract: () => {
          throw transportError({ status: 500 });
        },
      });
      expect((await analyze(user.token, report.id)).status).toBe(502);

      wireAiService();
      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);
      expect(res.body.data.report.status).toBe('processed');
      expect(res.body.data.report.statusMessage).toBeUndefined();
      expect(res.body.data.analysis.version).toBe(1);
    });
  });

  describe('the date the report prints (2026-09-24)', () => {
    const printing = (reportDate) => () =>
      okResponse({ ...extractionFixture(), report_metadata: { lab_name: 'X', report_date: reportDate } });

    async function uploadTyped(token, typed) {
      const res = await request(app)
        .post(REPORTS)
        .set(auth(token))
        .field('reportDate', typed)
        .attach('file', pdfBytes(), { filename: 'labs.pdf', contentType: 'application/pdf' });
      expect(res.status).toBe(201);
      return res.body.data.report;
    }

    it('orders by the printed date when none was typed', async () => {
      const user = await makeUser('printed.only@example.com');
      const report = await uploadReport(user.token);
      wireAiService({ extract: printing('05-Sep-2026 17:40') });

      const res = await analyze(user.token, report.id);
      expect(res.status).toBe(200);

      const stored = await Report.findById(report.id).lean();
      expect(stored.printedDateStatus).toBe('read');
      expect(stored.printedDate.toISOString()).toBe('2026-09-05T00:00:00.000Z');
      expect(stored.chronoDate.toISOString()).toBe('2026-09-05T00:00:00.000Z');
      expect(stored.reportDate).toBeUndefined();
    });

    it('keeps a typed date first, and keeps the printed one beside it', async () => {
      const user = await makeUser('printed.typed@example.com');
      const report = await uploadTyped(user.token, '2026-09-09');
      wireAiService({ extract: printing('05-Sep-2026 17:40') });
      await analyze(user.token, report.id);

      const stored = await Report.findById(report.id).lean();
      expect(stored.chronoDate.toISOString()).toBe('2026-09-09T00:00:00.000Z');
      expect(stored.printedDate.toISOString()).toBe('2026-09-05T00:00:00.000Z');

      const listed = await request(app).get(REPORTS).set(auth(user.token));
      const row = listed.body.data.reports.find((r) => r.id === report.id);
      expect(row.reportDate).toBe('2026-09-09T00:00:00.000Z');
      expect(row.printedDate).toBe('2026-09-05T00:00:00.000Z');
    });

    it('never guesses DD/MM against MM/DD, and falls back to the upload day', async () => {
      const user = await makeUser('printed.ambiguous@example.com');
      const report = await uploadReport(user.token);
      wireAiService({ extract: printing('05/09/2026') });
      await analyze(user.token, report.id);

      const stored = await Report.findById(report.id).lean();
      expect(stored.printedDateStatus).toBe('ambiguous');
      expect(stored.printedDate).toBeUndefined();
      expect(stored.chronoDate.getTime()).toBe(stored.uploadedAt.getTime());

      const listed = await request(app).get(REPORTS).set(auth(user.token));
      expect(listed.body.data.reports[0].printedDateRaw).toBe('05/09/2026');
    });

    it('records that the report prints no date, which is not "nobody looked"', async () => {
      const user = await makeUser('printed.absent@example.com');
      const report = await uploadReport(user.token);
      wireAiService({ extract: printing(null) });
      await analyze(user.token, report.id);

      const stored = await Report.findById(report.id).lean();
      expect(stored.printedDateStatus).toBe('absent');
      expect(stored.printedDate).toBeUndefined();
      expect(stored.printedDateRaw).toBeUndefined();
    });

    it('stores the printed sex and age, and leaves them unset for an old-style extraction', async () => {
      const user = await makeUser('printed.identity@example.com');
      const report = await uploadReport(user.token);
      wireAiService({
        extract: () =>
          okResponse({
            ...extractionFixture(),
            report_metadata: { lab_name: 'X', report_date: null, patient_sex: 'Female', patient_age: '34 Years' },
          }),
      });
      await analyze(user.token, report.id);
      let stored = await Report.findById(report.id).lean();
      expect(stored.printedIdentity).toEqual({ sex: 'female', sexStatus: 'read', ageYears: 34, ageStatus: 'read' });

      wireAiService();
      await analyze(user.token, report.id);
      stored = await Report.findById(report.id).lean();
      expect(stored.printedIdentity).toBeUndefined();
    });

    it('a re-run that no longer reads a date REMOVES the old one', async () => {
      const user = await makeUser('printed.rerun@example.com');
      const report = await uploadReport(user.token);
      wireAiService({ extract: printing('05-Sep-2026') });
      await analyze(user.token, report.id);
      wireAiService({ extract: printing('02 Dec, 2X') });
      await analyze(user.token, report.id);

      const stored = await Report.findById(report.id).lean();
      expect(stored.printedDateStatus).toBe('unreadable');
      expect(stored.printedDate).toBeUndefined();
      expect(stored.printedDateRaw).toBe('02 Dec, 2X');
      expect(stored.chronoDate.getTime()).toBe(stored.uploadedAt.getTime());
    });
  });

  describe('GET /reports/:id/analysis', () => {
    it('404s before the report has ever been analysed', async () => {
      const user = await makeUser('notyet@example.com');
      const report = await uploadReport(user.token);

      const res = await getAnalysis(user.token, report.id);
      expect(res.status).toBe(404);
      expect(res.body.error.code).toBe('NOT_FOUND');
    });

    it('returns the stored extraction, features and warnings', async () => {
      const user = await makeUser('retrieve@example.com');
      const report = await uploadReport(user.token);
      await analyze(user.token, report.id);

      const res = await getAnalysis(user.token, report.id);
      expect(res.status).toBe(200);
      expect(res.body.data.analysis.extraction.extracted_parameters[0].test_name).toBe('HbA1c');
      expect(res.body.data.analysis.features.features.hba1c).toBe(6.8);
      expect(res.body.data.analysis.warnings).toHaveLength(2);
      expect(res.body.data.report.id).toBe(report.id);
    });

    it('returns the validation verdict and both decision sources', async () => {
      const user = await makeUser('retrievedecisions@example.com');
      const report = await uploadReport(user.token);
      await analyze(user.token, report.id);

      const res = await getAnalysis(user.token, report.id);
      expect(res.status).toBe(200);
      const { analysis } = res.body.data;

      expect(analysis.validation.valid.hba1c.value).toBe(6.8);
      expect(analysis.validation.summary.valid_count).toBe(2);
      expect(analysis.ruleDecisions.decisions[0].condition).toBe('diabetes');
      expect(analysis.mlDecisions.decisions[0].condition).toBe('diabetes');
      expect(analysis.decisionCount).toBe(2);
      expect(analysis.highestRisk).toBe('High');
      expect(analysis.stages.ml.ok).toBe(true);
      expect(analysis.stagesFailed).toEqual([]);
    });

    it('returns a PARTIAL analysis rather than hiding it', async () => {
      const user = await makeUser('retrievepartial@example.com');
      const report = await uploadReport(user.token);
      wireAiService({
        predict: () => {
          throw transportError({ status: 500 });
        },
      });
      await analyze(user.token, report.id);

      const res = await getAnalysis(user.token, report.id);
      expect(res.status).toBe(200);
      expect(res.body.data.report.status).toBe('partial');
      expect(res.body.data.analysis.ruleDecisions.decisions).toHaveLength(1);
      expect(res.body.data.analysis.mlDecisions).toBeNull();
      expect(res.body.data.analysis.stages.ml.ok).toBe(false);
    });

    it('does NOT leak the analysis payload into the report list or detail', async () => {
      const user = await makeUser('noleak@example.com');
      const report = await uploadReport(user.token);
      await analyze(user.token, report.id);

      const list = await request(app).get(REPORTS).set(auth(user.token));
      expect(JSON.stringify(list.body)).not.toContain(PHI_CANARY);

      const detail = await request(app).get(`${REPORTS}/${report.id}`).set(auth(user.token));
      expect(JSON.stringify(detail.body)).not.toContain(PHI_CANARY);
      expect(detail.body.data.report.extraction).toBeUndefined();
      expect(detail.body.data.report.storageKey).toBeUndefined();
    });

    it('rejects a non-ObjectId id before it reaches a query', async () => {
      const user = await makeUser('badid@example.com');
      for (const id of ['not-an-id', '../../etc/passwd', '{"$ne":null}']) {
        const res = await getAnalysis(user.token, encodeURIComponent(id));
        expect(res.status).toBe(422);
      }
    });
  });

  describe('ownership - medical data has no staff exception', () => {
    let owner;
    let reportId;

    beforeEach(async () => {
      owner = await makeUser('owner@example.com');
      const report = await uploadReport(owner.token);
      reportId = report.id;
      await analyze(owner.token, reportId);
      outgoing = [];
    });

    const strangers = [
      ['another patient', () => makeUser('other@example.com')],
      ['an admin', () => makePrivilegedUser(ROLES.ADMIN, 'admin@example.com')],
      ['a clinician', () => makePrivilegedUser(ROLES.CLINICIAN, 'clinician@example.com')],
    ];

    it.each(strangers)('%s gets 404 on analyze, identical to a random id', async (_l, make) => {
      const stranger = await make();
      const randomId = new mongoose.Types.ObjectId().toString();

      const onOthers = await analyze(stranger.token, reportId);
      const onRandom = await analyze(stranger.token, randomId);

      expect(onOthers.status).toBe(404);
      expect(onOthers.body).toEqual(onRandom.body);
      expect(outgoing).toHaveLength(0);
    });

    it.each(strangers)('%s gets 404 on the analysis GET', async (_l, make) => {
      const stranger = await make();
      const randomId = new mongoose.Types.ObjectId().toString();

      const onOthers = await getAnalysis(stranger.token, reportId);
      const onRandom = await getAnalysis(stranger.token, randomId);

      expect(onOthers.status).toBe(404);
      expect(onOthers.body).toEqual(onRandom.body);
      expect(JSON.stringify(onOthers.body)).not.toContain(PHI_CANARY);
    });

    it.each(strangers)('%s gets 404 on the clinical report route', async (_l, make) => {
      const stranger = await make();
      const randomId = new mongoose.Types.ObjectId().toString();

      const onOthers = await getClinicalReport(stranger.token, reportId);
      const onRandom = await getClinicalReport(stranger.token, randomId);

      expect(onOthers.status).toBe(404);
      expect(onOthers.body).toEqual(onRandom.body);
      expect(JSON.stringify(onOthers.body)).not.toContain(PHI_CANARY);
      expect(JSON.stringify(onOthers.body)).not.toContain('Needs Medical Attention');
    });

    it('a stranger cannot move the owner\'s report out of `processed`', async () => {
      const stranger = await makeUser('stranger2@example.com');
      await analyze(stranger.token, reportId);

      const stored = await loadRaw(reportId);
      expect(stored.status).toBe('processed');
      expect(stored.analysis.runCount).toBe(1);
    });

    it.each(strangers)('%s gets 404 on the explanation route', async (_l, make) => {
      const stranger = await make();
      const randomId = new mongoose.Types.ObjectId().toString();

      const onOthers = await getExplanation(stranger.token, reportId);
      const onRandom = await getExplanation(stranger.token, randomId);

      expect(onOthers.status).toBe(404);
      expect(onOthers.body).toEqual(onRandom.body);
      expect(JSON.stringify(onOthers.body)).not.toContain(PHI_CANARY);
      expect(JSON.stringify(onOthers.body)).not.toContain(EXPLANATION_TEXT);
      expect(JSON.stringify(onOthers.body)).not.toContain('HbA1c reflects');
    });

    it('rejects an unauthenticated caller with 401 on all four routes', async () => {
      const analyzeRes = await request(app).post(`${REPORTS}/${reportId}/analyze`);
      const getRes = await request(app).get(`${REPORTS}/${reportId}/analysis`);
      const reportRes = await request(app).get(`${REPORTS}/${reportId}/report`);
      const explainRes = await request(app).get(`${REPORTS}/${reportId}/explanation`);
      expect(analyzeRes.status).toBe(401);
      expect(getRes.status).toBe(401);
      expect(reportRes.status).toBe(401);
      expect(explainRes.status).toBe(401);
      expect(JSON.stringify(reportRes.body)).not.toContain('Needs Medical Attention');
      expect(JSON.stringify(explainRes.body)).not.toContain(EXPLANATION_TEXT);
      expect(outgoing).toHaveLength(0);
    });

    it('deleting the report removes the stored analysis with it', async () => {
      const del = await request(app).delete(`${REPORTS}/${reportId}`).set(auth(owner.token));
      expect(del.status).toBe(200);
      expect(await Report.findById(reportId)).toBeNull();
    });
  });

  describe('health / readiness', () => {
    beforeEach(() => {
      require('../src/routes').resetAiHealthCache();
    });

    it('GET /health never blocks on the ai-service', async () => {
      mockAxios.get.mockImplementation(
        () => new Promise(() => {})
      );
      const res = await request(app).get(`${config.apiPrefix}/health`);
      expect(res.status).toBe(200);
      expect(res.body.data.aiService.configured).toBe(true);
    });

    it('GET /health/ai reports reachable', async () => {
      mockAxios.get.mockResolvedValue({ status: 200, data: { success: true, data: {} } });
      const res = await request(app).get(`${config.apiPrefix}/health/ai`);
      expect(res.status).toBe(200);
      expect(res.body.data.aiService).toMatchObject({ configured: true, reachable: true });
    });

    it('GET /health/ai reports 503 when the service is down', async () => {
      mockAxios.get.mockRejectedValue(transportError({ code: 'ECONNREFUSED' }));
      const res = await request(app).get(`${config.apiPrefix}/health/ai`);
      expect(res.status).toBe(503);
      expect(res.body.error.code).toBe('AI_SERVICE_UNAVAILABLE');
      expect(JSON.stringify(res.body)).not.toContain(PHI_CANARY);
    });

    it('GET /health/ai does not amplify: repeated calls share one probe', async () => {
      mockAxios.get.mockResolvedValue({ status: 200, data: { success: true, data: {} } });

      const results = await Promise.all(
        [1, 2, 3, 4, 5, 6, 7, 8].map(() => request(app).get(`${config.apiPrefix}/health/ai`))
      );
      for (const res of results) expect(res.status).toBe(200);

      expect(mockAxios.get).toHaveBeenCalledTimes(1);
    });

    it('GET /health/ai says so when the pipeline is not configured', async () => {
      const savedUrl = config.aiService.url;
      config.aiService.url = '';
      try {
        const res = await request(app).get(`${config.apiPrefix}/health/ai`);
        expect(res.status).toBe(200);
        expect(res.body.data.aiService.configured).toBe(false);
      } finally {
        config.aiService.url = savedUrl;
      }
    });
  });

  describe('PHI never reaches a log', () => {
    it('logs nothing containing report text on the failure path', async () => {
      const user = await makeUser('phi@example.com');
      const report = await uploadReport(user.token);
      wireAiService({
        extract: () => {
          throw transportError({ status: 500 });
        },
      });

      await analyze(user.token, report.id);

      const logged = [...consoleWarn.mock.calls, ...consoleError.mock.calls]
        .flat()
        .map((entry) => (typeof entry === 'string' ? entry : JSON.stringify(entry)))
        .join('\n');
      expect(logged).not.toContain(PHI_CANARY);
      expect(logged).not.toContain('unhandled-error');
    });
  });
});

describe('the glossary stage spends model calls, and is budgeted like it', () => {
  const aiServiceClient = require('../src/services/aiServiceClient');
  const originalRetries = config.aiService.retries;

  beforeEach(() => {
    mockAxios.post.mockReset();
    config.aiService.retries = 1;
    aiServiceClient.resetClient();
  });

  afterEach(() => {
    config.aiService.retries = originalRetries;
    aiServiceClient.resetClient();
  });

  it('does NOT use the budget meant for stages that call no model', () => {
    expect(config.aiService.glossaryTimeoutMs).not.toBe(config.aiService.guidanceTimeoutMs);
    expect(config.aiService.glossaryTimeoutMs).toBeGreaterThanOrEqual(24 * 4000);
  });

  it('sends the glossary call with its own timeout', async () => {
    mockAxios.post.mockResolvedValue({ status: 200, data: { success: true, data: { entries: [] } } });
    await aiServiceClient.describeParameters({ testNames: ['PCV'], requestId: 'r1' });

    const [, , options] = mockAxios.post.mock.calls[0];
    expect(options.timeout).toBe(config.aiService.glossaryTimeoutMs);
  });

  it('NEVER RETRIES A TIMEOUT, because the calls are already spent', async () => {
    const timeout = Object.assign(new Error('timeout of 30000ms exceeded'), {
      code: 'ECONNABORTED',
      isAxiosError: true,
    });
    mockAxios.post.mockRejectedValue(timeout);

    await expect(
      aiServiceClient.describeParameters({ testNames: ['PCV'], requestId: 'r2' })
    ).rejects.toBeDefined();

    expect(mockAxios.post).toHaveBeenCalledTimes(1);
  });

  it('still retries a stage that has NOT been given its own budget', async () => {
    const timeout = Object.assign(new Error('timeout'), {
      code: 'ECONNABORTED',
      isAxiosError: true,
    });
    mockAxios.post.mockRejectedValue(timeout);

    await expect(
      aiServiceClient.lifestyleGuidance({ conditions: ['Diabetes'], features: [], requestId: 'r3' })
    ).rejects.toBeDefined();

    expect(mockAxios.post.mock.calls.length).toBeGreaterThan(1);
  });
});

describe('Module 34 spends model calls too, and is budgeted like it', () => {
  const aiServiceClient = require('../src/services/aiServiceClient');
  const originalRetries = config.aiService.retries;

  beforeEach(() => {
    mockAxios.post.mockReset();
    config.aiService.retries = 1;
    aiServiceClient.resetClient();
  });

  afterEach(() => {
    config.aiService.retries = originalRetries;
    aiServiceClient.resetClient();
  });

  it('does NOT share the budget of stages that make a single call', () => {
    expect(config.aiService.findingContextTimeoutMs).not.toBe(
      config.aiService.explainTimeoutMs
    );
    expect(config.aiService.findingContextTimeoutMs).toBeGreaterThanOrEqual(16 * 4000);
  });

  it('sends the finding-context call with its own timeout', async () => {
    mockAxios.post.mockResolvedValue({
      status: 200,
      data: { success: true, data: { entries: [] } },
    });
    await aiServiceClient.describeFindings({
      findings: [{ test_name: 'ESR', direction: 'raised' }],
      requestId: 'fc1',
    });

    const [, , options] = mockAxios.post.mock.calls[0];
    expect(options.timeout).toBe(config.aiService.findingContextTimeoutMs);
  });

  it('NEVER RETRIES A TIMEOUT, because the calls are already spent', async () => {
    const timeout = Object.assign(new Error('timeout of 120000ms exceeded'), {
      code: 'ECONNABORTED',
      isAxiosError: true,
    });
    mockAxios.post.mockRejectedValue(timeout);

    await expect(
      aiServiceClient.describeFindings({
        findings: [{ test_name: 'ESR', direction: 'raised' }],
        requestId: 'fc2',
      })
    ).rejects.toBeDefined();

    expect(mockAxios.post).toHaveBeenCalledTimes(1);
  });
});
