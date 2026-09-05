'use strict';

/**
 * OPT-IN live end-to-end test: backend -> real `ai-service` -> real Gemini.
 *
 * It exercises the WHOLE section-16 chain against a really-running service:
 * OCR extraction (4) -> feature engineering (5) -> validation (6) ->
 * clinical rules (8) || ML predictors (9/10) || the clinical report (17-20,
 * with Modules 15/16's fusion produced inside it), then retrieval of
 * everything that was stored - including `GET /reports/:id/report`, the
 * user-visible deliverable.
 *
 * SKIPPED BY DEFAULT. It is the only test in the suite that touches the
 * network, so it must never be able to run by accident - the offline suite's
 * value depends on that. Enable it deliberately:
 *
 *   RUN_LIVE_INTEGRATION=1 \
 *   AI_SERVICE_URL=http://127.0.0.1:8000 \
 *   AI_SERVICE_API_KEY=<the same key the ai-service is running with> \
 *   npx cross-env NODE_ENV=test npx jest tests/liveIntegration.test.js --runInBand --forceExit
 *
 * Optionally point LIVE_REPORT_PATH at a real lab-report PDF or image; without
 * one, a minimal generated PDF is used, which proves the wiring end to end even
 * though it contains no lab values.
 *
 * Note the timeout: a live extraction was measured at ~20 s and the
 * ai-service's worst case with shipped defaults is far longer, so this test
 * allows several minutes rather than the suite's usual 60 s.
 */

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

/** A minimal but structurally valid single-page PDF carrying a lab line. */
function minimalPdf() {
  const text = 'HbA1c 6.8 % (4.0 - 5.6) HIGH';
  const objects = [
    '1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n',
    '2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n',
    '3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]' +
      '/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>endobj\n',
    null, // content stream, built below
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
    // eslint-disable-next-line no-console
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

    // A profile with hypertension DELIBERATELY absent: the live run is the only
    // place the tri-state crosses a real language boundary.
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
    // eslint-disable-next-line no-console
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
        // Modules 17-20. `overallStatus: null` with the label `Not Assessed`
        // is a legitimate live outcome and is printed as-is.
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
    // The wiring bug this exists to catch: a 200 with nothing in it.
    expect(analysis.features.features).toBeDefined();

    // ------------------------------------------- the full section-16 chain ---
    // `partial` is a legitimate live outcome (e.g. no trained ML artifact on
    // this machine), so the status is asserted as one of the two, and the
    // per-stage record is what says which stages actually ran.
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
    // Stages 4 and 5 are load-bearing: a 200 is impossible without them.
    expect(analysis.stages.extraction.ok).toBe(true);
    expect(analysis.stages.feature_engineering.ok).toBe(true);

    if (analysis.stages.validation.ok) {
      // Module 6's real partition, against a real validation rule table.
      expect(analysis.validation).not.toBeNull();
      expect(analysis.validation.valid).toBeDefined();
      expect(analysis.validation.rejected).toBeDefined();
      expect(typeof analysis.validFeatureCount).toBe('number');
      // The tri-state is still a MISSING feature after validation, not a false.
      expect(analysis.validation.valid.hypertension).toBeUndefined();
      expect(analysis.validation.rejected.hypertension).toBeUndefined();
    }
    if (analysis.stages.rules.ok) {
      expect(analysis.ruleDecisions).not.toBeNull();
      expect(Array.isArray(analysis.ruleDecisions.decisions)).toBe(true);
      expect(analysis.ruleDecisionCount).toBe(analysis.ruleDecisions.decisions.length);
      // Every decision is stored whole - several decisions for one condition
      // from one source is INTENDED (one decision per rule), so nothing here
      // may assume uniqueness by condition.
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
    // ------------------------------------------- Modules 17-20, the report ---
    if (analysis.stages.report.ok) {
      const clinical = analysis.report;
      expect(clinical).not.toBeNull();
      // eslint-disable-next-line no-console
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

      // MODULE 18 HAS FOUR CASES AND ALL FOUR MUST BE RENDERABLE.
      expect([null, 'Healthy', 'Needs Monitoring', 'Needs Medical Attention']).toContain(
        analysis.overallStatus
      );
      expect(['Not Assessed', 'Healthy', 'Needs Monitoring', 'Needs Medical Attention']).toContain(
        analysis.overallStatusLabel
      );
      // The two can never disagree: a null status is `Not Assessed`, never one
      // of the spec's three words, and never rendered as `Healthy`.
      if (analysis.overallStatus === null) {
        expect(analysis.overallStatusLabel).toBe('Not Assessed');
        expect(analysis.anyAssessed).toBe(false);
        expect(analysis.assessmentComplete).toBe(false);
        expect(analysis.overallRisk).toBeNull();
      } else {
        expect(analysis.overallStatusLabel).toBe(analysis.overallStatus);
      }
      // `caveat` is non-null EXACTLY when `complete` is false.
      if (analysis.assessmentComplete === false) {
        expect(clinical.overall.caveat).not.toBeNull();
      }
      // Module 16's fusion is nested verbatim, so the rule or model behind any
      // line stays reachable from the report.
      expect(clinical.fusion).toBeDefined();
      expect(Array.isArray(clinical.fusion.fused)).toBe(true);

      // The deliverable is served on its own, owner-scoped, from its own route.
      const only = await request(app).get(`${REPORTS}/${reportId}/report`).set(auth(token));
      expect(only.status).toBe(200);
      expect(only.body.data.clinicalReport).toEqual(clinical);
      expect(only.body.data.overall.statusLabel).toBe(analysis.overallStatusLabel);
      expect(only.body.data.overall.status).toBe(analysis.overallStatus);
    }

    // Warnings from every stage that raised one, origins intact - now
    // including Module 16's fusion and Module 17's own.
    //
    // `explanation` BELONGS IN THIS LIST, and its absence was a defect in this
    // assertion rather than in the pipeline. Two different objects were being
    // conflated:
    //
    //   * the stored clinical report's `warnings_by_stage` genuinely CANNOT
    //     carry an explanation entry - Module 17 builds the report before
    //     Module 23 runs, so no explanation-era warning exists yet; and
    //   * `analysis.warnings`, asserted here, is the BACKEND's cross-stage
    //     list, assembled after all eight stages have run. `analysisService`
    //     appends Module 23's warnings to it deliberately and last.
    //
    // Applying the report-era stage vocabulary to the backend-era list made
    // this assertion fail whenever the explanation stage raised a warning -
    // observed live on 2026-09-04, when a rate-limited generation produced
    // "no plain-language explanation could be prepared for this report".
    // Earlier live runs passed only because the explanation stage had always
    // fully succeeded and so raised nothing.
    //
    // That warning is precisely the one a patient must not lose: without it a
    // report with no explanation is indistinguishable from one that needed
    // none. So the origin is added to the list; the check that every warning
    // carries a RECOGNISED origin is unchanged and still does its work.
    // `guidance` is deliberately NOT added - Module 26 pushes no warnings, and
    // an unreachable value in an allow-list only weakens it.
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

    // The tri-state survived the real language boundary.
    const missing = analysis.features.missing_features;
    if (Array.isArray(missing)) expect(missing).toContain('hypertension');
    expect(analysis.features.features.hypertension).toBeUndefined();

    // Retrieval returns the same stored analysis, decisions included.
    const fetched = await request(app).get(`${REPORTS}/${reportId}/analysis`).set(auth(token));
    expect(fetched.status).toBe(200);
    expect(fetched.body.data.analysis.version).toBe(1);
    expect(fetched.body.data.analysis.validation).toEqual(analysis.validation);
    expect(fetched.body.data.analysis.ruleDecisions).toEqual(analysis.ruleDecisions);
    expect(fetched.body.data.analysis.mlDecisions).toEqual(analysis.mlDecisions);
    expect(fetched.body.data.analysis.report).toEqual(analysis.report);
    expect(fetched.body.data.analysis.overallStatus).toBe(analysis.overallStatus);
    expect(fetched.body.data.analysis.overallStatusLabel).toBe(analysis.overallStatusLabel);
    // Raw report text is never persisted.
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
