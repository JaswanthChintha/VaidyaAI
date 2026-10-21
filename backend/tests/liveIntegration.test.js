'use strict';


const fs = require('fs');
const os = require('os');
const path = require('path');

const UPLOAD_ROOT = fs.mkdtempSync(path.join(os.tmpdir(), 'vaidyaai-live-test-'));
process.env.UPLOAD_ROOT = UPLOAD_ROOT;
process.env.UPLOAD_MAX_BYTES = String(10 * 1024 * 1024);

const LIVE = process.env.RUN_LIVE_INTEGRATION === '1';

const { app, request, registerUser } = require('./helpers');
const config = require('../src/config/env');
const aiServiceClient = require('../src/services/aiServiceClient');

const REPORTS = `${config.apiPrefix}/reports`;
const PROFILE = `${config.apiPrefix}/profile/me`;
const auth = (token) => ({ Authorization: `Bearer ${token}` });

function minimalPdf() {
  const text = 'HbA1c 6.8 % (4.0 - 5.6) HIGH';
  const objects = [
    '1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n',
    '2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n',
    '3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]' +
      '/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>endobj\n',
    null,
    '5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n',
  ];
  const stream = `BT /F1 14 Tf 72 700 Td (${text}) Tj ET`;
  objects[3] = `4 0 obj<</Length ${stream.length}>>stream\n${stream}\nendstream endobj\n`;

  let body = '%PDF-1.4\n';
  const offsets = [];
  for (const obj of objects) {
    offsets.push(body.length);
    body += obj;
  }
  const xrefStart = body.length;
  body += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const offset of offsets) {
    body += `${String(offset).padStart(10, '0')} 00000 n \n`;
  }
  body +=
    `trailer<</Size ${objects.length + 1}/Root 1 0 R>>\n` +
    `startxref\n${xrefStart}\n%%EOF\n`;
  return Buffer.from(body, 'latin1');
}

function reportBytes() {
  if (process.env.LIVE_REPORT_PATH) return fs.readFileSync(process.env.LIVE_REPORT_PATH);
  return minimalPdf();
}

const describeLive = LIVE ? describe : describe.skip;

describeLive(
  'LIVE end-to-end: upload -> extraction -> features -> validation -> rules || ML || report',
  () => {
  jest.setTimeout(6 * 60 * 1000);

  afterAll(() => {
    fs.rmSync(UPLOAD_ROOT, { recursive: true, force: true });
  });

  it('the ai-service is reachable and its health endpoint is unauthenticated', async () => {
    expect(aiServiceClient.isConfigured()).toBe(true);
    const res = await request(app).get(`${config.apiPrefix}/health/ai`);
    console.log('[live] ai-service health:', JSON.stringify(res.body));
    expect(res.status).toBe(200);
    expect(res.body.data.aiService.reachable).toBe(true);
  });

  it('runs the whole pipeline and stores a real analysis', async () => {
    const { res: registered } = await registerUser({
      email: `live-${Date.now()}@example.com`,
      name: 'Live Test',
    });
    expect(registered.status).toBe(201);
    const token = registered.body.data.accessToken;

    const profile = await request(app)
      .post(PROFILE)
      .set(auth(token))
      .send({
        age: 47,
        gender: 'female',
        heightCm: 165,
        weightKg: 68,
        heartDisease: false,
        smokingHistory: 'never',
      });
    expect(profile.status).toBe(201);

    const upload = await request(app)
      .post(REPORTS)
      .set(auth(token))
      .attach('file', reportBytes(), {
        filename: 'live-report.pdf',
        contentType: 'application/pdf',
      });
    expect(upload.status).toBe(201);
    const reportId = upload.body.data.report.id;

    const analysed = await request(app).post(`${REPORTS}/${reportId}/analyze`).set(auth(token));
    const analysis = analysed.body.data && analysed.body.data.analysis;
    console.log(
      '[live] analyze ->',
      analysed.status,
      JSON.stringify(analysed.body.error || {
        status: analysed.body.data.report.status,
        version: analysis.version,
        confidence: analysis.extractionConfidence,
        stages: analysis.stages,
        stagesFailed: analysis.stagesFailed,
        warnings: analysis.warnings,
        features: Object.keys(analysis.features.features || {}),
        validFeatureCount: analysis.validFeatureCount,
        rejectedFeatureCount: analysis.rejectedFeatureCount,
        ruleDecisionCount: analysis.ruleDecisionCount,
        mlDecisionCount: analysis.mlDecisionCount,
        highestRisk: analysis.highestRisk,
        conditionsFlagged: analysis.conditionsFlagged,
        overallStatus: analysis.overallStatus,
        overallStatusLabel: analysis.overallStatusLabel,
        overallRisk: analysis.overallRisk,
        assessmentComplete: analysis.assessmentComplete,
        anyAssessed: analysis.anyAssessed,
        conditionCount: analysis.conditionCount,
        criticalConditionCount: analysis.criticalConditionCount,
        unassessedConditionCount: analysis.unassessedConditionCount,
        recommendationCount: analysis.recommendationCount,
        laboratoryValueCount: analysis.laboratoryValueCount,
      })
    );

    expect(analysed.status).toBe(200);
    expect(analysis.version).toBe(1);
    expect(analysis.extraction).toBeDefined();
    expect(analysis.features).toBeDefined();
    expect(analysis.features.features).toBeDefined();

    expect(['processed', 'partial']).toContain(analysed.body.data.report.status);
    for (const stage of [
      'extraction',
      'feature_engineering',
      'validation',
      'rules',
      'ml',
      'report',
    ]) {
      expect(analysis.stages[stage]).toBeDefined();
    }
    expect(analysis.stages.extraction.ok).toBe(true);
    expect(analysis.stages.feature_engineering.ok).toBe(true);

    if (analysis.stages.validation.ok) {
      expect(analysis.validation).not.toBeNull();
      expect(analysis.validation.valid).toBeDefined();
      expect(analysis.validation.rejected).toBeDefined();
      expect(typeof analysis.validFeatureCount).toBe('number');
      expect(analysis.validation.valid.hypertension).toBeUndefined();
      expect(analysis.validation.rejected.hypertension).toBeUndefined();
    }
    if (analysis.stages.rules.ok) {
      expect(analysis.ruleDecisions).not.toBeNull();
      expect(Array.isArray(analysis.ruleDecisions.decisions)).toBe(true);
      expect(analysis.ruleDecisionCount).toBe(analysis.ruleDecisions.decisions.length);
      for (const decision of analysis.ruleDecisions.decisions) {
        expect(typeof decision.condition).toBe('string');
        expect(decision.source_kind).toBe('clinical_rule');
      }
    }
    if (analysis.stages.ml.ok) {
      expect(analysis.mlDecisions).not.toBeNull();
      expect(Array.isArray(analysis.mlDecisions.decisions)).toBe(true);
      expect(analysis.mlDecisionCount).toBe(analysis.mlDecisions.decisions.length);
    }
    if (analysis.stages.report.ok) {
      const clinical = analysis.report;
      expect(clinical).not.toBeNull();
      console.log(
        '[live] clinical report ->',
        JSON.stringify({
          report_version: clinical.report_version,
          overall: clinical.overall,
          overall_risk: clinical.overall_risk,
          conditions: clinical.conditions.map((c) => ({
            condition: c.condition,
            status: c.status,
            risk: c.risk,
          })),
          critical_conditions: clinical.critical_conditions,
          abnormal_findings: clinical.abnormal_findings,
          normal_findings: clinical.normal_findings,
          unassessed_conditions: clinical.unassessed_conditions,
          prioritized: clinical.prioritized,
          laboratory_values: (clinical.laboratory_values || []).length,
          recommendations: (clinical.recommendations || []).map((r) => r.code),
          document: clinical.document,
          warnings_by_stage: clinical.warnings_by_stage,
          summary: clinical.summary,
          fusion_fused: (clinical.fusion.fused || []).map((f) => ({
            condition: f.condition,
            status: f.status,
            risk: f.risk,
            sources: f.sources,
            hybrid: f.hybrid,
          })),
        })
      );

      expect([null, 'Healthy', 'Needs Monitoring', 'Needs Medical Attention']).toContain(
        analysis.overallStatus
      );
      expect(['Not Assessed', 'Healthy', 'Needs Monitoring', 'Needs Medical Attention']).toContain(
        analysis.overallStatusLabel
      );
      if (analysis.overallStatus === null) {
        expect(analysis.overallStatusLabel).toBe('Not Assessed');
        expect(analysis.anyAssessed).toBe(false);
        expect(analysis.assessmentComplete).toBe(false);
        expect(analysis.overallRisk).toBeNull();
      } else {
        expect(analysis.overallStatusLabel).toBe(analysis.overallStatus);
      }
      if (analysis.assessmentComplete === false) {
        expect(clinical.overall.caveat).not.toBeNull();
      }
      expect(clinical.fusion).toBeDefined();
      expect(Array.isArray(clinical.fusion.fused)).toBe(true);

      const only = await request(app).get(`${REPORTS}/${reportId}/report`).set(auth(token));
      expect(only.status).toBe(200);
      expect(only.body.data.clinicalReport).toEqual(clinical);
      expect(only.body.data.overall.statusLabel).toBe(analysis.overallStatusLabel);
      expect(only.body.data.overall.status).toBe(analysis.overallStatus);
    }

    for (const warning of analysis.warnings) {
      expect([
        'extraction',
        'feature_engineering',
        'validation',
        'rules',
        'ml',
        'fusion',
        'report',
        'explanation',
      ]).toContain(warning.stage);
    }

    const missing = analysis.features.missing_features;
    if (Array.isArray(missing)) expect(missing).toContain('hypertension');
    expect(analysis.features.features.hypertension).toBeUndefined();

    const fetched = await request(app).get(`${REPORTS}/${reportId}/analysis`).set(auth(token));
    expect(fetched.status).toBe(200);
    expect(fetched.body.data.analysis.version).toBe(1);
    expect(fetched.body.data.analysis.validation).toEqual(analysis.validation);
    expect(fetched.body.data.analysis.ruleDecisions).toEqual(analysis.ruleDecisions);
    expect(fetched.body.data.analysis.mlDecisions).toEqual(analysis.mlDecisions);
    expect(fetched.body.data.analysis.report).toEqual(analysis.report);
    expect(fetched.body.data.analysis.overallStatus).toBe(analysis.overallStatus);
    expect(fetched.body.data.analysis.overallStatusLabel).toBe(analysis.overallStatusLabel);
    expect(fetched.body.data.analysis.extraction.raw_text).toBeUndefined();
    expect(JSON.stringify(fetched.body)).not.toContain('"raw_text"');
  });

  it('rejects a wrong service key with a mapped 502, not a 500', async () => {
    const savedKey = config.aiService.apiKey;
    config.aiService.apiKey = 'deliberately-wrong-key-0123456789abcdef';
    try {
      const { res: registered } = await registerUser({
        email: `live-badkey-${Date.now()}@example.com`,
        name: 'Live Test',
      });
      const token = registered.body.data.accessToken;
      const upload = await request(app)
        .post(REPORTS)
        .set(auth(token))
        .attach('file', reportBytes(), {
          filename: 'live-report.pdf',
          contentType: 'application/pdf',
        });
      const analysed = await request(app)
        .post(`${REPORTS}/${upload.body.data.report.id}/analyze`)
        .set(auth(token));

      expect(analysed.status).toBe(502);
      expect(analysed.body.error.code).toBe('AI_SERVICE_UNAUTHORIZED');
      expect(analysed.body.error.stack).toBeUndefined();
    } finally {
      config.aiService.apiKey = savedKey;
    }
  });
});
