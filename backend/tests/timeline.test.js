'use strict';


const express = require('express');
const mongoose = require('mongoose');

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
const { ROLES } = require('../src/utils/roles');
const validate = require('../src/middleware/validate');
const { errorHandler } = require('../src/middleware/errorHandler');
const { comparisonPairValidator } = require('../src/middleware/timelineValidators');
const aiServiceClient = require('../src/services/aiServiceClient');

const TIMELINE = `${config.apiPrefix}/timeline`;
const REPORTS = `${config.apiPrefix}/reports`;
const PASSWORD = 'Str0ng!Passw0rd';
const auth = (token) => ({ Authorization: `Bearer ${token}` });
const ABSENT_ID = '0123456789abcdef01234567';

const TRENDS_PATH = '/api/v1/timeline/trends';
const COMPARISON_PATH = '/api/v1/comparison/reports';
const PROGRESS_PATH = '/api/v1/progress/score';
const DOCTOR_SUMMARY_PATH = '/api/v1/doctor-summary/generate';


async function makeUser(email) {
  const { res } = await registerUser({ email, name: 'Test User' });
  expect(res.status).toBe(201);
  return { token: res.body.data.accessToken, id: res.body.data.user.id };
}

async function makePrivilegedUser(role, email) {
  const user = await createUserWithRole(role, { email, password: PASSWORD });
  const res = await login(email, PASSWORD);
  expect(res.status).toBe(200);
  return { token: res.body.data.accessToken, id: user._id.toString() };
}


const day = (n) => new Date(Date.UTC(2026, 0, n, 12, 0, 0));

function validatedFeatureSet(hba1c) {
  return {
    valid: { hba1c: { name: 'hba1c', value: hba1c, unit: '%', status: 'valid', usable: true } },
    questionable: {},
    rejected: {},
    missing_features: [],
    summary: { valid_count: 1 },
  };
}

const clinicalReport = () => ({
  report_version: '1.0.0',
  overall: {
    status: 'Healthy',
    status_label: 'Healthy',
    risk: 'Low',
    any_assessed: true,
    complete: true,
  },
  laboratory_values: [],
  conditions: [],
  summary: {},
});

async function seedReport(
  userId,
  { analysed = true, validated = true, status = 'processed', chronoDate, hba1c = 6.4, report } = {}
) {
  const doc = await Report.create({
    user: userId,
    originalName: 'labs.pdf',
    storageKey: `${userId}/${new mongoose.Types.ObjectId().toString()}.pdf`,
    storageDriver: 'local',
    mimeType: 'application/pdf',
    sizeBytes: 1024,
    checksumSha256: 'f'.repeat(64),
    status,
    reportDate: chronoDate,
    analysis: { version: analysed ? 1 : 0 },
    featureValidation: validated ? validatedFeatureSet(hba1c) : undefined,
    clinicalReport: report === undefined ? clinicalReport() : report,
  });
  return doc._id.toString();
}


const okResponse = (data) => ({ status: 200, data: { success: true, data } });

const trendsFixture = (body) => ({
  module: 28,
  outcome: (body.reports || []).length >= 2 ? 'TREND_CLASSIFIED' : 'INSUFFICIENT_DATA',
  features: (body.reports || []).length >= 2
    ? [{ feature: 'hba1c', outcome: 'TREND_CLASSIFIED', trend: 'worsening' }]
    : [{ feature: 'hba1c', outcome: 'INSUFFICIENT_DATA', trend: null }],
  gaps: [],
  warnings: [],
});

const comparisonFixture = (body) => ({
  module: 29,
  pair: (body.reports || []).length >= 2 ? { selection: 'earliest_to_latest' } : null,
  parameters: [],
  warnings: [],
});

const progressFixture = (body) => ({
  module: 30,
  outcome: (body.reports || []).length >= 2 ? 'SCORE_COMPUTED' : 'NO_PAIR',
  score: (body.reports || []).length >= 2 ? 41.7 : null,
  band: (body.reports || []).length >= 2 ? 'Mixed' : null,
  higher_is_better: true,
  coverage: { contributing: 0, excluded: [] },
});

const doctorSummaryFixture = (body) => ({
  module: 32,
  sections: [],
  trends: { present: (body.history || []).length >= 2, reason: 'SECTION_SINGLE_REPORT' },
  comparison: { present: (body.history || []).length >= 2, reason: 'SECTION_SINGLE_REPORT' },
});

let outgoing = [];

function wireAiService(overrides = {}) {
  mockAxios.post.mockReset();
  mockAxios.post.mockImplementation(async (url, body, options) => {
    outgoing.push({ url, body, options });
    const route = {
      [TRENDS_PATH]: [overrides.trends, trendsFixture],
      [COMPARISON_PATH]: [overrides.comparison, comparisonFixture],
      [PROGRESS_PATH]: [overrides.progress, progressFixture],
      [DOCTOR_SUMMARY_PATH]: [overrides.doctorSummary, doctorSummaryFixture],
    }[url];
    if (!route) throw new Error(`unexpected ai-service path ${url}`);
    const [override, fallback] = route;
    return typeof override === 'function'
      ? override(body, options)
      : okResponse(fallback(body || {}));
  });
}

const callsTo = (url) => outgoing.filter((call) => call.url === url);

beforeEach(() => {
  outgoing = [];
  wireAiService();
  mockAxios.get.mockReset();
  mockAxios.get.mockResolvedValue(okResponse({ status: 'ok' }));
});

const ROUTES = [
  { name: 'trends', url: () => `${TIMELINE}/trends`, pairs: false },
  { name: 'comparison', url: () => `${TIMELINE}/comparison`, pairs: true },
  { name: 'progress', url: () => `${TIMELINE}/progress`, pairs: true },
];

describe('Modules 28-30 + 32 - the longitudinal endpoints', () => {
  describe('ownership - no route widens the history', () => {
    let alice;
    let bob;
    let aliceIds;

    beforeEach(async () => {
      alice = await makeUser('alice.tl@example.com');
      bob = await makeUser('bob.tl@example.com');
      aliceIds = [
        await seedReport(alice.id, { chronoDate: day(1), hba1c: 6.1 }),
        await seedReport(alice.id, { chronoDate: day(2), hba1c: 6.8 }),
      ];
    });

    it.each(ROUTES)('$name: another patient\'s reports never enter the history', async (route) => {
      const res = await request(app).get(route.url()).set(auth(bob.token));
      expect(res.status).toBe(200);

      expect(res.body.data.history.considered).toBe(0);
      expect(res.body.data.history.included).toBe(0);
      expect(res.body.data.history.reports).toEqual([]);
      const sent = JSON.stringify(outgoing.map((c) => c.body));
      for (const id of aliceIds) {
        expect(JSON.stringify(res.body)).not.toContain(id);
        expect(sent).not.toContain(id);
      }
    });

    it.each(ROUTES)('$name: an ADMIN sees an empty history, not the collection', async (route) => {
      const admin = await makePrivilegedUser(ROLES.ADMIN, `admin.${route.name}@example.com`);
      const res = await request(app).get(route.url()).set(auth(admin.token));
      expect(res.status).toBe(200);
      expect(res.body.data.history.included).toBe(0);
      expect(res.body.data.history.considered).toBe(0);
      expect(JSON.stringify(outgoing.map((c) => c.body))).not.toContain(aliceIds[0]);
    });

    it.each(ROUTES)('$name: a CLINICIAN sees an empty history too', async (route) => {
      const staff = await makePrivilegedUser(ROLES.CLINICIAN, `clin.${route.name}@example.com`);
      const res = await request(app).get(route.url()).set(auth(staff.token));
      expect(res.status).toBe(200);
      expect(res.body.data.history.included).toBe(0);
      expect(JSON.stringify(outgoing.map((c) => c.body))).not.toContain(aliceIds[0]);
    });

    it.each(ROUTES)('$name: is 401 unauthenticated', async (route) => {
      const res = await request(app).get(route.url());
      expect(res.status).toBe(401);
      expect(outgoing).toHaveLength(0);
    });

    it('the owner does see their own two reports (so the emptiness above is about identity)', async () => {
      const res = await request(app).get(`${TIMELINE}/trends`).set(auth(alice.token));
      expect(res.status).toBe(200);
      expect(res.body.data.history.included).toBe(2);
      expect(res.body.data.history.reports.map((r) => r.reportId).sort()).toEqual(
        [...aliceIds].sort()
      );
    });
  });

  describe('?baseline= / ?comparison= is not an authorisation', () => {
    let alice;
    let bob;
    let aliceIds;
    let bobIds;

    const PAIR_ROUTES = [
      { name: 'comparison', url: () => `${TIMELINE}/comparison` },
      { name: 'progress', url: () => `${TIMELINE}/progress` },
    ];

    beforeEach(async () => {
      alice = await makeUser('alice.pair@example.com');
      bob = await makeUser('bob.pair@example.com');
      aliceIds = [
        await seedReport(alice.id, { chronoDate: day(1), hba1c: 6.1 }),
        await seedReport(alice.id, { chronoDate: day(2), hba1c: 6.8 }),
      ];
      bobIds = [
        await seedReport(bob.id, { chronoDate: day(1), hba1c: 5.4 }),
        await seedReport(bob.id, { chronoDate: day(2), hba1c: 5.5 }),
      ];
    });

    it.each(PAIR_ROUTES)(
      '$name: another patient\'s id 404s, byte-identically to a random id',
      async (route) => {
        const named = await request(app)
          .get(route.url())
          .query({ baseline: aliceIds[0], comparison: bobIds[1] })
          .set(auth(bob.token));
        const random = await request(app)
          .get(route.url())
          .query({ baseline: ABSENT_ID, comparison: bobIds[1] })
          .set(auth(bob.token));

        expect(named.status).toBe(404);
        expect(named.status).toBe(random.status);
        expect(named.body.error.code).toBe(random.body.error.code);
        expect(named.body.error.message).toBe(random.body.error.message);
        expect(JSON.stringify(named.body)).toBe(JSON.stringify(random.body));
        expect(JSON.stringify(named.body)).not.toContain(aliceIds[0]);
        expect(outgoing).toHaveLength(0);
      }
    );

    it.each(PAIR_ROUTES)('$name: an admin naming a patient\'s pair gets the same 404', async (
      route
    ) => {
      const admin = await makePrivilegedUser(ROLES.ADMIN, `admin.pair.${route.name}@example.com`);
      const res = await request(app)
        .get(route.url())
        .query({ baseline: aliceIds[0], comparison: aliceIds[1] })
        .set(auth(admin.token));
      expect(res.status).toBe(404);
      expect(JSON.stringify(res.body)).not.toContain(aliceIds[0]);
      expect(outgoing).toHaveLength(0);
    });

    it.each(PAIR_ROUTES)('$name: a clinician naming a patient\'s pair gets the same 404', async (
      route
    ) => {
      const staff = await makePrivilegedUser(
        ROLES.CLINICIAN,
        `clin.pair.${route.name}@example.com`
      );
      const res = await request(app)
        .get(route.url())
        .query({ baseline: aliceIds[0], comparison: aliceIds[1] })
        .set(auth(staff.token));
      expect(res.status).toBe(404);
      expect(outgoing).toHaveLength(0);
    });

    it.each(PAIR_ROUTES)(
      '$name: the owner\'s own UNANALYSED report is 422 REPORT_NOT_IN_HISTORY',
      async (route) => {
        const unanalysed = await seedReport(alice.id, {
          analysed: false,
          validated: false,
          status: 'uploaded',
        });

        const res = await request(app)
          .get(route.url())
          .query({ baseline: unanalysed, comparison: aliceIds[1] })
          .set(auth(alice.token));

        expect(res.status).toBe(422);
        expect(res.body.error.code).toBe('REPORT_NOT_IN_HISTORY');
        expect(JSON.stringify(res.body)).not.toContain(unanalysed);
        expect(outgoing).toHaveLength(0);
      }
    );

    it.each(PAIR_ROUTES)('$name: the owner\'s own analysed pair is honoured verbatim', async (
      route
    ) => {
      const res = await request(app)
        .get(route.url())
        .query({ baseline: aliceIds[1], comparison: aliceIds[0] })
        .set(auth(alice.token));

      expect(res.status).toBe(200);
      expect(res.body.data.requestedPair).toEqual({
        baseline: aliceIds[1],
        comparison: aliceIds[0],
      });
      const [call] = outgoing;
      expect(call.body.baseline_ref).toBe(aliceIds[1]);
      expect(call.body.comparison_ref).toBe(aliceIds[0]);
    });

    it.each(PAIR_ROUTES)('$name: with no pair named, no refs are sent at all', async (route) => {
      const res = await request(app).get(route.url()).set(auth(alice.token));
      expect(res.status).toBe(200);
      expect(res.body.data.requestedPair).toBeNull();
      const [call] = outgoing;
      expect(call.body.baseline_ref).toBeUndefined();
      expect(call.body.comparison_ref).toBeUndefined();
    });

    it('doctor-summary applies the identical rules to its own pair', async () => {
      const own = aliceIds[1];

      const foreign = await request(app)
        .get(`${REPORTS}/${own}/doctor-summary`)
        .query({ baseline: bobIds[0], comparison: aliceIds[0] })
        .set(auth(alice.token));
      const random = await request(app)
        .get(`${REPORTS}/${own}/doctor-summary`)
        .query({ baseline: ABSENT_ID, comparison: aliceIds[0] })
        .set(auth(alice.token));

      expect(foreign.status).toBe(404);
      expect(JSON.stringify(foreign.body)).toBe(JSON.stringify(random.body));
      expect(JSON.stringify(foreign.body)).not.toContain(bobIds[0]);
      expect(outgoing).toHaveLength(0);
    });
  });

  describe('Module 32 - GET /reports/:id/doctor-summary ownership', () => {
    let alice;
    let aliceReportId;

    beforeEach(async () => {
      alice = await makeUser('alice.ds@example.com');
      aliceReportId = await seedReport(alice.id, { chronoDate: day(1) });
    });

    it('the owner can read it', async () => {
      const res = await request(app)
        .get(`${REPORTS}/${aliceReportId}/doctor-summary`)
        .set(auth(alice.token));
      expect(res.status).toBe(200);
      expect(res.body.data.doctorSummary.module).toBe(32);
    });

    it.each([
      ['another patient', () => makeUser('bob.ds@example.com')],
      ['an admin', () => makePrivilegedUser(ROLES.ADMIN, 'admin.ds@example.com')],
      ['a clinician', () => makePrivilegedUser(ROLES.CLINICIAN, 'clin.ds@example.com')],
    ])('%s gets a 404 byte-identical to the 404 for an absent id', async (_label, makeCaller) => {
      const caller = await makeCaller();
      const real = await request(app)
        .get(`${REPORTS}/${aliceReportId}/doctor-summary`)
        .set(auth(caller.token));
      const absent = await request(app)
        .get(`${REPORTS}/${ABSENT_ID}/doctor-summary`)
        .set(auth(caller.token));

      expect(real.status).toBe(404);
      expect(real.status).toBe(absent.status);
      expect(JSON.stringify(real.body)).toBe(JSON.stringify(absent.body));
      expect(outgoing).toHaveLength(0);
    });

    it('404s an unanalysed report rather than summarising nothing', async () => {
      const id = await seedReport(alice.id, {
        analysed: false,
        validated: false,
        status: 'uploaded',
        report: null,
      });
      const res = await request(app)
        .get(`${REPORTS}/${id}/doctor-summary`)
        .set(auth(alice.token));
      expect(res.status).toBe(404);
    });

    it('does not send the patient explanation - model prose cannot reach a clinician', async () => {
      await Report.updateOne(
        { _id: aliceReportId },
        { $set: { patientExplanation: { note: 'CANARY-PATIENT-PROSE' } } }
      );
      const res = await request(app)
        .get(`${REPORTS}/${aliceReportId}/doctor-summary`)
        .set(auth(alice.token));
      expect(res.status).toBe(200);
      expect(JSON.stringify(outgoing)).not.toContain('CANARY-PATIENT-PROSE');
      expect(JSON.stringify(res.body)).not.toContain('CANARY-PATIENT-PROSE');
    });
  });

  describe('validator hardening on ?baseline / ?comparison', () => {
    let alice;
    beforeEach(async () => {
      alice = await makeUser('alice.val@example.com');
      await seedReport(alice.id, { chronoDate: day(1) });
    });

    const PAIR_URLS = [`${TIMELINE}/comparison`, `${TIMELINE}/progress`];

    it.each(PAIR_URLS)('%s: an operator object `?baseline[$ne]=` is 422', async (url) => {
      const res = await request(app)
        .get(`${url}?baseline[$ne]=&comparison=${ABSENT_ID}`)
        .set(auth(alice.token));
      expect(res.status).toBe(422);
      expect(res.body.error.code).toBe('VALIDATION_ERROR');
      expect(outgoing).toHaveLength(0);
    });

    it.each(PAIR_URLS)('%s: a duplicated `?baseline=a&baseline=b` never reaches Mongo', async (
      url
    ) => {
      const res = await request(app)
        .get(`${url}?baseline=${ABSENT_ID}&baseline=${'1'.repeat(24)}&comparison=${ABSENT_ID}`)
        .set(auth(alice.token));

      expect([404, 422]).toContain(res.status);
      expect(res.body.success).toBe(false);
      expect(outgoing).toHaveLength(0);
    });

    it.each(PAIR_URLS)('%s: a non-hex id is 422', async (url) => {
      for (const bad of ['not-an-id', 'zzzzzzzzzzzzzzzzzzzzzzzz', '0123456789abcdef0123456', '']) {
        const res = await request(app)
          .get(`${url}?baseline=${encodeURIComponent(bad)}&comparison=${ABSENT_ID}`)
          .set(auth(alice.token));
        expect(res.status).toBe(422);
      }
      expect(outgoing).toHaveLength(0);
    });

    it.each(PAIR_URLS)('%s: one of the two alone is 422 (both-or-neither)', async (url) => {
      for (const query of [{ baseline: ABSENT_ID }, { comparison: ABSENT_ID }]) {
        const res = await request(app).get(url).query(query).set(auth(alice.token));
        expect(res.status).toBe(422);
        expect(res.body.error.code).toBe('VALIDATION_ERROR');
      }
      expect(outgoing).toHaveLength(0);
    });

    it('doctor-summary carries the same pair validator', async () => {
      const id = await seedReport(alice.id, { chronoDate: day(2) });
      for (const query of [
        `baseline[$ne]=&comparison=${ABSENT_ID}`,
        `baseline=${ABSENT_ID}`,
        `baseline=nope&comparison=${ABSENT_ID}`,
      ]) {
        const res = await request(app)
          .get(`${REPORTS}/${id}/doctor-summary?${query}`)
          .set(auth(alice.token));
        expect(res.status).toBe(422);
      }
      expect(outgoing).toHaveLength(0);
    });

    describe('the chain alone, with no sanitiser in front of it', () => {
      let bare;

      beforeAll(() => {
        bare = express();
        bare.get(
          '/pair',
          validate(comparisonPairValidator),
          (req, res) => res.status(200).json({ reached: true, baseline: req.query.baseline })
        );
        bare.use(errorHandler);
      });

      it('accepts a well-formed pair (so the refusals below mean something)', async () => {
        const res = await request(bare).get(
          `/pair?baseline=${ABSENT_ID}&comparison=${'1'.repeat(24)}`
        );
        expect(res.status).toBe(200);
        expect(res.body.reached).toBe(true);
      });

      it.each([
        ['an operator object', `baseline[$ne]=&comparison=${ABSENT_ID}`],
        ['a nested operator object', `baseline[$gt]=&comparison=${ABSENT_ID}`],
        ['a duplicated parameter', `baseline=${ABSENT_ID}&baseline=${'1'.repeat(24)}&comparison=${ABSENT_ID}`],
        ['an array literal', `baseline[]=${ABSENT_ID}&comparison=${ABSENT_ID}`],
        ['a non-hex id', `baseline=not-an-id&comparison=${ABSENT_ID}`],
        ['a 23-character id', `baseline=${'a'.repeat(23)}&comparison=${ABSENT_ID}`],
        ['a 25-character id', `baseline=${'a'.repeat(25)}&comparison=${ABSENT_ID}`],
        ['baseline alone', `baseline=${ABSENT_ID}`],
        ['comparison alone', `comparison=${ABSENT_ID}`],
      ])('rejects %s with 422 - the chain, not a sanitiser', async (_label, query) => {
        const res = await request(bare).get(`/pair?${query}`);
        expect(res.status).toBe(422);
        expect(res.body.error.code).toBe('VALIDATION_ERROR');
        expect(res.body.reached).toBeUndefined();
        expect(res.body.error.message).toBe('Invalid request payload');
      });

      it('an absent pair is allowed through - the parameters are optional', async () => {
        const res = await request(bare).get('/pair');
        expect(res.status).toBe(200);
        expect(res.body.baseline).toBeUndefined();
      });
    });
  });

  describe('a patient with 0 or 1 analysed reports', () => {
    let alice;
    beforeEach(async () => {
      alice = await makeUser('alice.empty@example.com');
    });

    it.each(ROUTES)('$name: 200 with an empty history, and the service IS called', async (route) => {
      const res = await request(app).get(route.url()).set(auth(alice.token));

      expect(res.status).toBe(200);
      expect(res.body.data.history.included).toBe(0);
      expect(outgoing).toHaveLength(1);
      expect(outgoing[0].body.reports).toEqual([]);
    });

    it('passes INSUFFICIENT_DATA through untouched for one report', async () => {
      await seedReport(alice.id, { chronoDate: day(1) });
      const res = await request(app).get(`${TIMELINE}/trends`).set(auth(alice.token));

      expect(res.status).toBe(200);
      expect(res.body.data.trends.outcome).toBe('INSUFFICIENT_DATA');
      expect(res.body.data.trends.features[0].outcome).toBe('INSUFFICIENT_DATA');
      expect(res.body.data.trends.features[0].trend).toBeNull();
      expect(JSON.stringify(res.body.data.trends)).not.toContain('stable');
    });

    it('passes NO_PAIR through with a null score - never 50, never 0', async () => {
      await seedReport(alice.id, { chronoDate: day(1) });
      const res = await request(app).get(`${TIMELINE}/progress`).set(auth(alice.token));

      expect(res.status).toBe(200);
      expect(res.body.data.progress.outcome).toBe('NO_PAIR');
      expect(res.body.data.progress.score).toBeNull();
      expect(res.body.data.progress.band).toBeNull();
      expect(res.body.data.progress.score).not.toBe(0);
      expect(res.body.data.progress.score).not.toBe(50);
    });

    it('passes a null comparison pair through rather than inventing one', async () => {
      const res = await request(app).get(`${TIMELINE}/comparison`).set(auth(alice.token));
      expect(res.status).toBe(200);
      expect(res.body.data.comparison.pair).toBeNull();
      expect(res.body.data.requestedPair).toBeNull();
    });

    it.each(ROUTES)('$name: an empty history is not a 500', async (route) => {
      const res = await request(app).get(route.url()).set(auth(alice.token));
      expect(res.status).toBeLessThan(300);
    });

    it('invents no vocabulary of its own: only the service\'s codes appear', async () => {
      await seedReport(alice.id, { chronoDate: day(1) });
      const res = await request(app).get(`${TIMELINE}/trends`).set(auth(alice.token));
      const body = JSON.stringify(res.body.data.trends);
      for (const invented of ['NOT_ENOUGH_HISTORY', 'TOO_FEW_REPORTS', 'NO_HISTORY']) {
        expect(body).not.toContain(invented);
      }
    });

    it('a short history is distinguishable from a patient with little history', async () => {
      await seedReport(alice.id, { chronoDate: day(1) });
      await seedReport(alice.id, { analysed: false, validated: false, status: 'uploaded' });
      await seedReport(alice.id, { validated: false, status: 'partial' });

      const res = await request(app).get(`${TIMELINE}/trends`).set(auth(alice.token));
      const { history } = res.body.data;

      expect(history.considered).toBe(3);
      expect(history.included).toBe(1);
      expect(history.excludedCount).toBe(2);
      expect(history.considered).toBe(history.included + history.excludedCount);
      expect(history.excluded.map((r) => r.reasonCode).sort()).toEqual([
        'NOT_ANALYSED',
        'NO_VALIDATED_FEATURES',
      ]);
    });
  });

  describe('aiServiceClient - the five new stages', () => {
    let alice;
    beforeEach(async () => {
      alice = await makeUser('alice.client@example.com');
      await seedReport(alice.id, { chronoDate: day(1) });
    });

    it.each([
      ['trends', () => `${TIMELINE}/trends`, TRENDS_PATH, 'timelineTimeoutMs'],
      ['comparison', () => `${TIMELINE}/comparison`, COMPARISON_PATH, 'comparisonTimeoutMs'],
      ['progress', () => `${TIMELINE}/progress`, PROGRESS_PATH, 'progressTimeoutMs'],
    ])('%s posts to %s with ITS OWN per-stage timeout', async (_name, url, path, key) => {
      const res = await request(app).get(url()).set(auth(alice.token));
      expect(res.status).toBe(200);

      const [call] = callsTo(path);
      expect(call).toBeDefined();
      expect(call.options.timeout).toBe(config.aiService[key]);
      expect(typeof call.options.timeout).toBe('number');
    });

    it('doctor-summary and population-context each use their own timeout too', async () => {
      const id = await seedReport(alice.id, { chronoDate: day(2) });
      await request(app).get(`${REPORTS}/${id}/doctor-summary`).set(auth(alice.token));

      const [call] = callsTo(DOCTOR_SUMMARY_PATH);
      expect(call.options.timeout).toBe(config.aiService.doctorSummaryTimeoutMs);
      const keys = [
        'timelineTimeoutMs',
        'comparisonTimeoutMs',
        'progressTimeoutMs',
        'doctorSummaryTimeoutMs',
        'populationTimeoutMs',
      ];
      for (const key of keys) {
        expect(typeof config.aiService[key]).toBe('number');
        expect(config.aiService[key]).toBeGreaterThan(0);
      }
      expect(new Set(keys).size).toBe(5);
    });

    it('sends the service key and a correlation id on every new stage', async () => {
      await request(app).get(`${TIMELINE}/trends`).set(auth(alice.token));
      const [call] = callsTo(TRENDS_PATH);
      expect(call.options.headers['X-Service-Key']).toBe(config.aiService.apiKey);
      expect(call.options.headers['X-Request-Id']).toMatch(/^[A-Za-z0-9._:-]{1,128}$/);
    });

    it.each([
      [400, 'a content refusal the service parsed and declined'],
      [422, 'a request-validation refusal'],
    ])('maps %i to 422 AI_SERVICE_REJECTED_INPUT (%s)', async (status) => {
      const err = new Error('refused');
      err.response = { status, data: { detail: 'COMPARISON_REPORT_NOT_FOUND' } };
      const mapped = aiServiceClient.mapAxiosError(err, 'comparison');

      expect(mapped.error.statusCode).toBe(422);
      expect(mapped.error.code).toBe('AI_SERVICE_REJECTED_INPUT');
      expect(mapped.error.code).not.toBe('AI_SERVICE_REJECTED_REQUEST');
      expect(mapped.error.statusCode).not.toBe(502);
      expect(mapped.retryable).toBe(false);
      expect(mapped.error.message).not.toContain('COMPARISON_REPORT_NOT_FOUND');
    });

    it('still calls an unclassified 4xx a contract mismatch', async () => {
      const err = new Error('weird');
      err.response = { status: 418, data: {} };
      const mapped = aiServiceClient.mapAxiosError(err, 'comparison');
      expect(mapped.error.statusCode).toBe(502);
      expect(mapped.error.code).toBe('AI_SERVICE_REJECTED_REQUEST');
    });

    it('a 400 from the comparison endpoint surfaces as 422 over HTTP', async () => {
      wireAiService({
        comparison: () => {
          const err = new Error('refused');
          err.response = { status: 400, data: { detail: 'COMPARISON_REPORT_NOT_FOUND' } };
          throw err;
        },
      });

      const res = await request(app).get(`${TIMELINE}/comparison`).set(auth(alice.token));
      expect(res.status).toBe(422);
      expect(res.body.error.code).toBe('AI_SERVICE_REJECTED_INPUT');
      expect(JSON.stringify(res.body)).not.toContain('COMPARISON_REPORT_NOT_FOUND');
    });

    it('a service timeout is a 504, distinct from the service being down', async () => {
      wireAiService({
        trends: () => {
          const err = new Error('timeout');
          err.code = 'ECONNABORTED';
          throw err;
        },
      });
      const res = await request(app).get(`${TIMELINE}/trends`).set(auth(alice.token));
      expect(res.status).toBe(504);
      expect(res.body.error.code).toBe('AI_SERVICE_TIMEOUT');
    });
  });

  describe('the snapshot shape crossing the boundary', () => {
    it('sends `TimelineReportInput` and nothing else per report', async () => {
      const alice = await makeUser('alice.shape@example.com');
      const first = await seedReport(alice.id, { chronoDate: day(1), hba1c: 6.1 });
      const second = await seedReport(alice.id, { chronoDate: day(2), hba1c: 6.8 });

      const res = await request(app).get(`${TIMELINE}/trends`).set(auth(alice.token));
      expect(res.status).toBe(200);

      const [call] = callsTo(TRENDS_PATH);
      expect(call.body.reports.map((r) => r.report_id)).toEqual([first, second]);
      for (const report of call.body.reports) {
        expect(Object.keys(report).sort()).toEqual(['chrono_date', 'report_id', 'validated']);
      }
      expect(call.body.patient_ref).toBe(alice.id);
      expect(JSON.stringify(call.body)).not.toContain('alice.shape@example.com');
      expect(JSON.stringify(call.body)).not.toContain('labs.pdf');
    });
  });
});

describe('Module 32 - the parameters the platform does not assess', () => {
  const UNMAPPED = [
    { test_name: 'CRP (C-REACTIVE PROTEIN)', value_raw: '12.1', unit: 'mg/L', reason: 'no_canonical_feature', page_number: 3 },
    { test_name: 'SGPT', value_raw: '101.9', unit: 'U/L', reason: 'no_canonical_feature', page_number: 3 },
    { test_name: 'ESR', value_raw: '35', unit: 'mm/hr', reason: 'no_canonical_feature', page_number: 1 },
  ];
  const EXTRACTED = [
    { test_name: 'CRP (C-REACTIVE PROTEIN)', flag: 'high', reference_low: 0, reference_high: 6 },
    { test_name: 'SGPT', flag: 'high', reference_low: 0, reference_high: 50 },
    { test_name: 'ESR', flag: 'normal', reference_low: 0, reference_high: 15 },
  ];

  let owner;
  let reportId;

  beforeEach(async () => {
    owner = await makeUser('doc.unassessed@example.com');
    reportId = await seedReport(owner.id);
    await Report.updateOne(
      { _id: reportId },
      { $set: { features: { unmapped: UNMAPPED }, extraction: { extracted_parameters: EXTRACTED } } }
    );
  });

  it('carries every skipped parameter with its value and unit', async () => {
    const res = await request(app)
      .get(`${REPORTS}/${reportId}/doctor-summary`)
      .set(auth(owner.token));

    expect(res.status).toBe(200);
    const items = res.body.data.unassessed.items;
    expect(res.body.data.unassessed.count).toBe(3);
    expect(items.map((i) => i.testName)).toEqual([
      'CRP (C-REACTIVE PROTEIN)',
      'SGPT',
      'ESR',
    ]);
    const crp = items[0];
    expect(crp.value).toBe('12.1');
    expect(crp.unit).toBe('mg/L');
  });

  it("carries the LABORATORY's own flag and printed interval, not this tool's", async () => {
    const res = await request(app)
      .get(`${REPORTS}/${reportId}/doctor-summary`)
      .set(auth(owner.token));

    const items = res.body.data.unassessed.items;
    expect(items[0].labFlag).toBe('high');
    expect(items[0].labFlaggedAbnormal).toBe(true);
    expect(items[0].labReferenceHigh).toBe(6);
    expect(items[2].labFlag).toBe('normal');
    expect(items[2].labFlaggedAbnormal).toBe(false);
    expect(res.body.data.unassessed.labFlaggedCount).toBe(2);
  });

  it('describes nothing, because that is not a question this reader has', async () => {
    const res = await request(app)
      .get(`${REPORTS}/${reportId}/doctor-summary`)
      .set(auth(owner.token));

    const items = res.body.data.unassessed.items;
    for (const item of items) {
      expect(item.description).toBeUndefined();
      expect(item.descriptionAvailable).toBeUndefined();
    }
  });

  it('is an empty section, never absent, when every parameter mapped', async () => {
    const other = await seedReport(owner.id);
    const res = await request(app)
      .get(`${REPORTS}/${other}/doctor-summary`)
      .set(auth(owner.token));

    expect(res.status).toBe(200);
    expect(res.body.data.unassessed).toBeDefined();
    expect(res.body.data.unassessed.count).toBe(0);
    expect(res.body.data.unassessed.items).toEqual([]);
  });
});

describe('Module 32 - the cached narrative follows the code fingerprint', () => {
  const CLINICIAN_PATH = '/api/v1/explain/clinician-summary';
  const FINGERPRINT_PATH = '/api/v1/explain/clinician-summary/fingerprint';
  let owner;
  let reportId;
  let fingerprint;
  let fingerprintCalls;

  const written = (text) => okResponse({ module: 32, version: '1.0.0', outcome: 'generated', text });
  const narrativeCalls = () => callsTo(CLINICIAN_PATH);
  const summaryOf = () =>
    request(app).get(`${REPORTS}/${reportId}/doctor-summary`).set(auth(owner.token));
  const cache = (over) =>
    Report.updateOne(
      { _id: reportId },
      { $set: { doctorNarrative: { outcome: 'generated', text: 'cached note', analysisVersion: 1, ...over } } }
    );

  beforeEach(async () => {
    aiServiceClient.resetFingerprintMemo();
    owner = await makeUser(`doc.fp.${Date.now()}.${Math.random()}@example.com`);
    reportId = await seedReport(owner.id);

    const shared = mockAxios.post.getMockImplementation();
    mockAxios.post.mockImplementation(async (url, body, options) => {
      if (url === CLINICIAN_PATH) {
        outgoing.push({ url, body, options });
        return written('fresh note');
      }
      return shared(url, body, options);
    });

    fingerprint = 'aaaaaaaaaaaaaaaa';
    fingerprintCalls = 0;
    mockAxios.get.mockImplementation(async (url) => {
      if (url === FINGERPRINT_PATH) {
        fingerprintCalls += 1;
        if (fingerprint instanceof Error) throw fingerprint;
        return okResponse({ fingerprint, narrative_version: '1.0.0' });
      }
      return okResponse({ status: 'ok' });
    });
  });

  afterEach(() => aiServiceClient.resetFingerprintMemo());

  it('reuses a cached note written by the same code -- no model call', async () => {
    await cache({ codeFingerprint: 'aaaaaaaaaaaaaaaa' });
    const res = await summaryOf();
    expect(res.status).toBe(200);
    expect(res.body.data.narrative.text).toBe('cached note');
    expect(narrativeCalls()).toHaveLength(0);
  });

  it('re-writes a cached note written by different code, and saves the new fingerprint', async () => {
    await cache({ codeFingerprint: 'bbbbbbbbbbbbbbbb' });
    const res = await summaryOf();
    expect(res.body.data.narrative.text).toBe('fresh note');
    expect(narrativeCalls()).toHaveLength(1);
    const stored = await Report.findById(reportId).select('+doctorNarrative').lean();
    expect(stored.doctorNarrative.codeFingerprint).toBe('aaaaaaaaaaaaaaaa');
  });

  it('re-writes, once, a note cached before fingerprints existed', async () => {
    await cache({});
    await summaryOf();
    await summaryOf();
    expect(narrativeCalls()).toHaveLength(1);
  });

  it('trusts the cache when the fingerprint cannot be read -- a hiccup costs no model call', async () => {
    await cache({ codeFingerprint: 'bbbbbbbbbbbbbbbb' });
    fingerprint = new Error('ECONNREFUSED');
    const res = await summaryOf();
    expect(res.body.data.narrative.text).toBe('cached note');
    expect(narrativeCalls()).toHaveLength(0);
  });

  it('still re-writes a note from an earlier analysis, whatever the fingerprint', async () => {
    await cache({ codeFingerprint: 'aaaaaaaaaaaaaaaa', analysisVersion: 0 });
    await summaryOf();
    expect(narrativeCalls()).toHaveLength(1);
  });

  it('asks for the fingerprint once a minute, not once a page view', async () => {
    await cache({ codeFingerprint: 'aaaaaaaaaaaaaaaa' });
    await summaryOf();
    await summaryOf();
    await summaryOf();
    expect(fingerprintCalls).toBe(1);
  });
});
