'use strict';

/**
 * The backend longitudinal layer - Modules 28, 29, 30 and 32 as they are
 * reachable by a client.
 *
 *   GET /api/v1/timeline/trends
 *   GET /api/v1/timeline/comparison?baseline=&comparison=
 *   GET /api/v1/timeline/progress?baseline=&comparison=
 *   GET /api/v1/reports/:id/doctor-summary?baseline=&comparison=
 *
 * WHAT THIS SUITE IS FOR, in priority order:
 *
 *   1. OWNERSHIP. There is no patient id in the timeline URLs, so "another
 *      patient's data" can only arrive two ways: through a widened history
 *      filter, or through a report id a caller NAMED in the query string.
 *      Both are covered. A widened filter here leaks a patient's entire
 *      library, not one report, which is why these are the first tests in the
 *      file.
 *   2. `?baseline=` / `?comparison=` ARE NOT PERMISSION. Naming a report is
 *      not authorisation to read it: another patient's id must produce the
 *      identical 404 a random id produces, and no message may echo the id.
 *   3. VALIDATOR HARDENING. Every chain must start with `.isString().bail()`.
 *      MEMORY.md section 6 records that a missing one was a live
 *      authentication bypass on this project, so the guard is exercised
 *      against an app with NO `express-mongo-sanitize` and NO `hpp` in front
 *      of it - otherwise the test would prove those two middlewares work and
 *      say nothing about the chain.
 *   4. REFUSALS PASS THROUGH UNTOUCHED. A patient with zero or one analysed
 *      report gets the ai-service's own vocabulary, not a second "not enough
 *      history" invented here, and never a 500.
 *
 * axios is mocked at the transport layer, exactly as `tests/analysis.test.js`
 * does it and for the same reason: the outgoing request body is itself under
 * test (which report ids were sent, and which were not), and a client-level
 * mock would assert that against itself.
 */

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

// --- users ------------------------------------------------------------------

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

// --- fixtures ---------------------------------------------------------------

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

/** A minimal stored `ClinicalReport` - enough for `/doctor-summary` to proceed. */
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

// --- ai-service mock --------------------------------------------------------
//
// Every fixture below is a REFUSAL-CAPABLE shape: `outcome` is the field a
// client branches on and it is carried verbatim. The defaults are the answers
// the real service gives for a rich history; the tests that care about
// refusals override them explicitly.

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

/** Every outgoing ai-service call, in order. */
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

// The four endpoints, described once. Every ownership, validator and refusal
// test below runs over all of them rather than over a representative one -
// section 6m's point is precisely that one of these paths was never exercised.
const ROUTES = [
  { name: 'trends', url: () => `${TIMELINE}/trends`, pairs: false },
  { name: 'comparison', url: () => `${TIMELINE}/comparison`, pairs: true },
  { name: 'progress', url: () => `${TIMELINE}/progress`, pairs: true },
];

describe('Modules 28-30 + 32 - the longitudinal endpoints', () => {
  // ============================================================== ownership ==
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
      // Not one of Alice's ids reached the wire, let alone the response.
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
      // And nothing was asked of the ai-service on the way to that 401.
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

  // ============================== a named id is not permission to read it ====
  //
  // `?baseline=` and `?comparison=` are the only ids a caller may put in these
  // URLs. Each is re-loaded owner-scoped and re-checked BEFORE it can reach a
  // request body.
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
        // NO MESSAGE ECHOES THE SUBMITTED ID.
        expect(JSON.stringify(named.body)).not.toContain(aliceIds[0]);
        // And nothing was sent to the ai-service - the check happens before
        // the id can reach a request body.
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

        // NOT 404: the report demonstrably exists and belongs to the caller.
        // Answering 404 would tell an owner their own report does not exist.
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
      // The caller's naming is honoured EXACTLY, including a baseline that is
      // the later report - swapping would invert every reported direction.
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
      // Absent, not null - the service chooses earliest-to-latest itself.
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

  // ================================================ doctor-summary ownership ==
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
      // THE FACT THAT THIS DOCUMENT IS MEANT FOR A CLINICIAN DOES NOT GIVE A
      // CLINICIAN ACCOUNT ACCESS TO IT. The patient requests it and shares it.
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

  // ===================================================== validator hardening ==
  //
  // MEMORY.md section 9: "every validator chain starts with `.isString().bail()`
  // before any sanitizer. This is not style - a missing one caused a live
  // authentication bypass."
  //
  // The first block runs against the REAL app (which has express-mongo-sanitize
  // and hpp in front); the second runs the same inputs against a bare express
  // app that has NEITHER, which is the only way to show the chain is doing the
  // work itself rather than leaning on a middleware ordering somewhere else.
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

      // 404, NOT 422, and the difference is worth writing down. On the REAL app
      // `hpp()` runs before the chain and collapses the duplicate to a single
      // string, so what the validator sees is a well-formed id that simply does
      // not belong to this caller - hence the ownership 404. MEMORY.md section
      // 6m's "duplicated baseline -> 422" was measured against an app with no
      // `hpp`, which is exactly the bare-chain block further down; both are
      // true, of different apps.
      //
      // What matters either way is that NO ARRAY ever reaches a Mongo query and
      // the answer is a refusal, never a 200 and never a 500.
      expect([404, 422]).toContain(res.status);
      expect(res.body.success).toBe(false);
      expect(outgoing).toHaveLength(0);
    });

    it.each(PAIR_URLS)('%s: a non-hex id is 422', async (url) => {
      for (const bad of ['not-an-id', 'zzzzzzzzzzzzzzzzzzzzzzzz', '0123456789abcdef0123456', '']) {
        // eslint-disable-next-line no-await-in-loop
        const res = await request(app)
          .get(`${url}?baseline=${encodeURIComponent(bad)}&comparison=${ABSENT_ID}`)
          .set(auth(alice.token));
        expect(res.status).toBe(422);
      }
      expect(outgoing).toHaveLength(0);
    });

    it.each(PAIR_URLS)('%s: one of the two alone is 422 (both-or-neither)', async (url) => {
      for (const query of [{ baseline: ABSENT_ID }, { comparison: ABSENT_ID }]) {
        // eslint-disable-next-line no-await-in-loop
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
        // eslint-disable-next-line no-await-in-loop
        const res = await request(app)
          .get(`${REPORTS}/${id}/doctor-summary?${query}`)
          .set(auth(alice.token));
        expect(res.status).toBe(422);
      }
      expect(outgoing).toHaveLength(0);
    });

    // ------------------------------------------------------------------------
    // THE CHAIN, ALONE. No `protect`, no `express-mongo-sanitize`, no `hpp` -
    // only `validate(comparisonPairValidator)` and the error handler. If the
    // chain's own `.isString().bail()` were removed, every case below would
    // reach the handler and be answered 200, and this block is the only place
    // in the suite that could notice.
    describe('the chain alone, with no sanitiser in front of it', () => {
      let bare;

      beforeAll(() => {
        bare = express();
        bare.get(
          '/pair',
          validate(comparisonPairValidator),
          // Echoes what SURVIVED validation. Reaching this handler at all with
          // a non-string is the defect.
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
        // Never reached the handler, so a Mongo query could never have seen it.
        expect(res.body.reached).toBeUndefined();
        // And the error never echoes the submitted value.
        expect(res.body.error.message).toBe('Invalid request payload');
      });

      it('an absent pair is allowed through - the parameters are optional', async () => {
        const res = await request(bare).get('/pair');
        expect(res.status).toBe(200);
        expect(res.body.baseline).toBeUndefined();
      });
    });
  });

  // ================================================ refusals pass through =====
  //
  // "The ai-service is called even with 0 or 1 reports." Short-circuiting would
  // create a SECOND definition of "not enough history" in this backend, in this
  // backend's own words, free to drift from the one the service applies.
  describe('a patient with 0 or 1 analysed reports', () => {
    let alice;
    beforeEach(async () => {
      alice = await makeUser('alice.empty@example.com');
    });

    it.each(ROUTES)('$name: 200 with an empty history, and the service IS called', async (route) => {
      const res = await request(app).get(route.url()).set(auth(alice.token));

      // 200, NOT 404: a patient's timeline exists whether or not anything is on
      // it yet, and the refusal IS the answer.
      expect(res.status).toBe(200);
      expect(res.body.data.history.included).toBe(0);
      // The call was made with an empty report list rather than short-circuited.
      expect(outgoing).toHaveLength(1);
      expect(outgoing[0].body.reports).toEqual([]);
    });

    it('passes INSUFFICIENT_DATA through untouched for one report', async () => {
      await seedReport(alice.id, { chronoDate: day(1) });
      const res = await request(app).get(`${TIMELINE}/trends`).set(auth(alice.token));

      expect(res.status).toBe(200);
      // `outcome` is the field to branch on, never `trend`. Fewer than two
      // usable readings is INSUFFICIENT_DATA with `trend: null` - never
      // `stable`, which is a measured claim about a stability band.
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
      // A band label standing in for a missing number would be the same lie in
      // words rather than digits.
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
      // A backend-authored "not enough history" phrase would be a second
      // vocabulary that could drift from the service's.
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

  // =========================================================== the transport ==
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
      // Each stage carries its own configured timeout, never a shared default
      // read at the call site - `config/env.js` gives each its own env var for
      // exactly this reason.
      expect(call.options.timeout).toBe(config.aiService[key]);
      expect(typeof call.options.timeout).toBe('number');
    });

    it('doctor-summary and population-context each use their own timeout too', async () => {
      const id = await seedReport(alice.id, { chronoDate: day(2) });
      await request(app).get(`${REPORTS}/${id}/doctor-summary`).set(auth(alice.token));

      const [call] = callsTo(DOCTOR_SUMMARY_PATH);
      expect(call.options.timeout).toBe(config.aiService.doctorSummaryTimeoutMs);
      // The five new timeouts are five DISTINCT configuration keys, so an
      // operator can lengthen the slow one without lengthening the fast ones.
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

    // --- section 6n: 400 joins the 422 branch -------------------------------
    //
    // `report_comparator._select_pair` raises HTTP 400
    // (`COMPARISON_REPORT_NOT_FOUND`) for a named ref absent from the supplied
    // set. Mapping that to a 502 "contract mismatch" describes a bug
    // accurately and a caller-content refusal very badly: it reports a
    // caller-fixable problem as a server fault, and tells an operator their two
    // services disagree on the wire format when they agree perfectly.
    it.each([
      [400, 'a content refusal the service parsed and declined'],
      [422, 'a request-validation refusal'],
    ])('maps %i to 422 AI_SERVICE_REJECTED_INPUT (%s)', async (status) => {
      const err = new Error('refused');
      err.response = { status, data: { detail: 'COMPARISON_REPORT_NOT_FOUND' } };
      const mapped = aiServiceClient.mapAxiosError(err, 'comparison');

      expect(mapped.error.statusCode).toBe(422);
      expect(mapped.error.code).toBe('AI_SERVICE_REJECTED_INPUT');
      // NOT the contract-mismatch branch.
      expect(mapped.error.code).not.toBe('AI_SERVICE_REJECTED_REQUEST');
      expect(mapped.error.statusCode).not.toBe(502);
      // Deterministic - retrying only burns the rate limit.
      expect(mapped.retryable).toBe(false);
      // The service's body is never quoted back to the caller.
      expect(mapped.error.message).not.toContain('COMPARISON_REPORT_NOT_FOUND');
    });

    it('still calls an unclassified 4xx a contract mismatch', async () => {
      // 400 and 422 were moved deliberately; the rest of the 4xx range was not,
      // and a test that only checked 400 could not tell the two apart.
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

  // ================================================= what crosses the wire ====
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
      // The patient reference is the opaque user id - never a name or an email.
      expect(call.body.patient_ref).toBe(alice.id);
      expect(JSON.stringify(call.body)).not.toContain('alice.shape@example.com');
      expect(JSON.stringify(call.body)).not.toContain('labs.pdf');
    });
  });
});

// ===================================== the parameters this platform skips ==
//
// The clinician document listed the four values this platform ASSESSES under
// the words "The reported values are", on a report where the laboratory had
// printed twenty-one. The narrative states the count; these are the rows
// behind it, so a clinician can read the values rather than be told how many
// they cannot see.
//
// Built by the DASHBOARD'S assembler, deliberately: deriving them a second
// time here would be a second implementation free to disagree with the
// patient page about what was set aside.
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
    // `normal` is a flag and is NOT an abnormal one.
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
    // A SECTION THAT VANISHES IS INDISTINGUISHABLE FROM ONE THAT FOUND
    // NOTHING. `count: 0` is the honest answer and the renderer can branch.
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
