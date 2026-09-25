'use strict';

/**
 * Module 27 - the Health Dashboard read model.
 *
 *   GET /api/v1/reports/:id/dashboard  (dashboardController)
 *   src/services/dashboardService.js   (pure projection, no I/O)
 *
 * WHY THIS SUITE EXISTS. MEMORY.md section 6m recorded that Module 27's
 * ownership path was "copied from `analysisController` and has not been
 * exercised against user B / admin / clinician", and section 6n D3 recorded a
 * HIGH defect in which a report the analysis service labelled
 * `Healthy (partial assessment)` reached a patient's card as a flat `Healthy`
 * because the backend re-derived the label from the three-valued `status`
 * instead of carrying the producer's five-valued `status_label`. Both are
 * covered here, behaviourally, through the real Express stack.
 *
 * EVERYTHING IS OFFLINE. axios is mocked at the transport layer exactly as
 * `tests/analysis.test.js` does it, even though `/dashboard` calls no service
 * at all: if a future edit ever makes it call one, this suite must fail to
 * connect rather than reach a real ai-service.
 *
 * Reports are seeded directly through the model rather than through the
 * analyze pipeline. That is deliberate: the properties under test are about
 * what the dashboard does with a STORED payload, and driving eight mocked
 * stages to produce one would put the fixture three layers away from the
 * assertion it supports.
 */

const mongoose = require('mongoose');

// --- axios transport mock (see the header) ----------------------------------
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
const dashboardService = require('../src/services/dashboardService');
const analysisService = require('../src/services/analysisService');

const REPORTS = `${config.apiPrefix}/reports`;
const PASSWORD = 'Str0ng!Passw0rd';
const auth = (token) => ({ Authorization: `Bearer ${token}` });

/** A well-formed ObjectId that will never exist. The 404 baseline. */
const ABSENT_ID = '0123456789abcdef01234567';

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

/**
 * The minimum a report row needs to exist. Module 3's own required fields; the
 * file itself is never touched by any route under test here.
 */
function reportRow(userId, overrides = {}) {
  return {
    user: userId,
    originalName: 'labs.pdf',
    storageKey: `${userId}/${new mongoose.Types.ObjectId().toString()}.pdf`,
    storageDriver: 'local',
    mimeType: 'application/pdf',
    sizeBytes: 1024,
    checksumSha256: 'a'.repeat(64),
    status: 'processed',
    ...overrides,
  };
}

/**
 * A stored `ClinicalReport` in Modules 17-20's shape.
 *
 * The default is a FULLY assessed, healthy report - `status: 'Healthy'`,
 * `status_label: 'Healthy'`, `any_assessed: true`, `complete: true` - because
 * the cases that matter here are all departures from it, and building each one
 * from the same base is the only way a test can show that one field is what
 * changed the answer.
 */
function clinicalReport(overrides = {}) {
  const { overall, ...rest } = overrides;
  return {
    report_version: '1.0.0',
    generated_at: '2026-09-01T00:00:00Z',
    laboratory_values: [],
    conditions: [],
    prioritized: [],
    overall: {
      status: 'Healthy',
      status_label: 'Healthy',
      risk: 'Low',
      rule_applied: 'all_normal',
      policy: 'module-18-overall-status',
      any_assessed: true,
      complete: true,
      caveat: null,
      assessed_condition_count: 2,
      unassessed_condition_count: 0,
      unassessed_conditions: [],
      partially_assessed_conditions: [],
      abnormal_condition_count: 0,
      high_risk_condition_count: 0,
      sources_failed: [],
      ...(overall || {}),
    },
    overall_risk: 'Low',
    explainability: { conditions: [] },
    recommendations: [],
    document: {},
    validation_warnings: [],
    warnings_by_stage: {},
    summary: {
      condition_count: 2,
      abnormal_count: 0,
      critical_count: 0,
      normal_count: 2,
      unassessed_count: 0,
      laboratory_value_count: 0,
      recommendation_count: 0,
      warning_count: 0,
    },
    ...rest,
  };
}

/** Seed one analysed report owned by `userId` and return its id. */
async function seedAnalysed(userId, { report = clinicalReport(), ...extra } = {}) {
  const doc = await Report.create(
    reportRow(userId, {
      clinicalReport: report,
      analysis: { version: 1, runCount: 1 },
      ...extra,
    })
  );
  return doc._id.toString();
}

const getDashboard = (token, id) =>
  request(app).get(`${REPORTS}/${id}/dashboard`).set(auth(token));

beforeEach(() => {
  mockAxios.post.mockReset();
  mockAxios.get.mockReset();
  // Any call at all from this route would be a defect. Fail loudly rather than
  // returning a plausible body that would let a wrong test pass.
  mockAxios.post.mockImplementation(async (url) => {
    throw new Error(`/dashboard must call no service; it called ${url}`);
  });
});

describe('Module 27 - GET /reports/:id/dashboard', () => {
  // ============================================================= ownership ===
  //
  // MEMORY.md section 6m: "the ownership path is copied from
  // `analysisController` and has not been exercised against user B / admin /
  // clinician". This block is that exercise. The property is not merely "a
  // non-owner is refused" but "a non-owner cannot tell the report exists",
  // which is why every case is compared BYTE FOR BYTE against the 404 for an
  // id that certainly does not exist.
  describe('ownership - 404 before 403, indistinguishable from a random id', () => {
    let alice;
    let aliceReportId;

    beforeEach(async () => {
      alice = await makeUser('alice.dash@example.com');
      aliceReportId = await seedAnalysed(alice.id);
    });

    it('the owner can read it (so the 404s below are about identity, not state)', async () => {
      const res = await getDashboard(alice.token, aliceReportId);
      expect(res.status).toBe(200);
      expect(res.body.data.dashboard.module).toBe(27);
    });

    it.each([
      ['another patient', () => makeUser('bob.dash@example.com')],
      ['an admin', () => makePrivilegedUser(ROLES.ADMIN, 'admin.dash@example.com')],
      ['a clinician', () => makePrivilegedUser(ROLES.CLINICIAN, 'clin.dash@example.com')],
    ])('%s gets a 404 byte-identical to the 404 for an id that does not exist', async (
      _label,
      makeCaller
    ) => {
      const caller = await makeCaller();

      const real = await getDashboard(caller.token, aliceReportId);
      const absent = await getDashboard(caller.token, ABSENT_ID);

      expect(real.status).toBe(404);
      expect(real.status).toBe(absent.status);
      expect(real.body.error.code).toBe(absent.body.error.code);
      // The MESSAGE too. A different sentence for a real id is an existence
      // oracle just as surely as a 403 would be.
      expect(real.body.error.message).toBe(absent.body.error.message);
      expect(JSON.stringify(real.body)).toBe(JSON.stringify(absent.body));
    });

    it('no role grant widens the route: the report is untouched and unread', async () => {
      const admin = await makePrivilegedUser(ROLES.ADMIN, 'admin2.dash@example.com');
      const res = await getDashboard(admin.token, aliceReportId);
      expect(res.status).toBe(404);
      // Nothing about the report leaked into the body.
      expect(JSON.stringify(res.body)).not.toContain(aliceReportId);
      expect(await Report.countDocuments({ _id: aliceReportId })).toBe(1);
    });

    it('is 401 unauthenticated, and 401 does not depend on the id existing', async () => {
      const real = await request(app).get(`${REPORTS}/${aliceReportId}/dashboard`);
      const absent = await request(app).get(`${REPORTS}/${ABSENT_ID}/dashboard`);
      expect(real.status).toBe(401);
      expect(absent.status).toBe(401);
    });

    it('rejects a malformed id without reaching the database', async () => {
      for (const id of ['not-an-id', '{"$ne":null}', '../../etc/passwd']) {
        // eslint-disable-next-line no-await-in-loop
        const res = await getDashboard(alice.token, encodeURIComponent(id));
        expect([404, 422]).toContain(res.status);
        expect(res.body.success).toBe(false);
      }
    });
  });

  // ============================================== nothing to draw is a 404 ===
  describe('404 when there is nothing to draw', () => {
    let alice;

    beforeEach(async () => {
      alice = await makeUser('alice.nodraw@example.com');
    });

    it('404s an unanalysed report rather than synthesising an empty dashboard', async () => {
      const doc = await Report.create(reportRow(alice.id, { status: 'uploaded' }));
      const res = await getDashboard(alice.token, doc._id.toString());
      expect(res.status).toBe(404);
      // An empty 200 would be indistinguishable from a report that genuinely
      // found nothing - which a card renders as a clean bill of health.
      expect(res.body.success).toBe(false);
    });

    it('404s an analysed report whose report stage stored nothing', async () => {
      const doc = await Report.create(
        reportRow(alice.id, { status: 'partial', analysis: { version: 1 } })
      );
      const res = await getDashboard(alice.token, doc._id.toString());
      expect(res.status).toBe(404);
    });

    it('serves a `partial` report that DID produce a clinical report', async () => {
      const id = await seedAnalysed(alice.id, { status: 'partial' });
      const res = await getDashboard(alice.token, id);
      expect(res.status).toBe(200);
    });
  });

  // ========================================= section 6n D3 - the label bug ===
  //
  // THE MANDATORY REGRESSION. Module 18 emits FIVE `status_label` values. The
  // fifth, `Healthy (partial assessment)`, exists precisely because a partial
  // clean result was otherwise byte-identical to a full one. D3 was the
  // backend re-deriving the label from the three-valued `status`, which cannot
  // express the fifth value at all, so it printed `Healthy`.
  //
  // These tests are written against the ROUTE's own JSON, not against
  // `summariseReport`, because that is where the defect was observable: the
  // service said one thing and the dashboard printed another.
  describe('section 6n D3 - `status_label` is carried, never re-derived', () => {
    let alice;
    beforeEach(async () => {
      alice = await makeUser('alice.label@example.com');
    });

    const withOverall = (overall) => clinicalReport({ overall });

    it('`Healthy (partial assessment)` reaches the card as exactly that', async () => {
      const id = await seedAnalysed(alice.id, {
        report: withOverall({
          status: 'Healthy',
          status_label: 'Healthy (partial assessment)',
          any_assessed: true,
          // The producer's own completeness flag agrees with its label, so
          // there is no disagreement to record - the label is simply carried.
          complete: false,
          caveat: 'Two conditions could not be assessed from this document.',
          assessed_condition_count: 1,
          unassessed_condition_count: 2,
          unassessed_conditions: ['kidney_disease', 'heart_disease'],
        }),
      });

      const res = await getDashboard(alice.token, id);
      expect(res.status).toBe(200);

      const { overall } = res.body.data.dashboard;
      // THE ASSERTION D3 WAS ABOUT. Not `toContain`, not a prefix match: the
      // pre-fix code printed the literal string `Healthy`, which passes any
      // loose check.
      expect(overall.statusLabel).toBe('Healthy (partial assessment)');
      expect(overall.statusLabel).not.toBe('Healthy');
      // `complete: false` survived in the pre-fix code too - it was never the
      // failing half. Asserted so this test cannot be satisfied by it.
      expect(overall.complete).toBe(false);
      expect(overall.caveat).toBe(
        'Two conditions could not be assessed from this document.'
      );
      // The unassessed topics are still countable from the card.
      expect(overall.unassessedConditionCount).toBe(2);
      expect(overall.unassessedConditions).toEqual(['kidney_disease', 'heart_disease']);
    });

    it('a genuinely complete `Healthy` still prints `Healthy`', async () => {
      // The other half of the regression: the fix must not make everything
      // partial. A test that only checked the partial case would pass against
      // a backend that hard-coded the qualifier.
      const id = await seedAnalysed(alice.id);
      const res = await getDashboard(alice.token, id);
      expect(res.body.data.dashboard.overall.statusLabel).toBe('Healthy');
      expect(res.body.data.dashboard.overall.complete).toBe(true);
    });

    it.each([
      ['Needs Monitoring', 'Needs Monitoring', 'Medium'],
      ['Needs Medical Attention', 'Needs Medical Attention', 'High'],
    ])('carries `%s` unchanged', async (label, status, risk) => {
      const id = await seedAnalysed(alice.id, {
        report: withOverall({ status, status_label: label, risk, any_assessed: true }),
      });
      const res = await getDashboard(alice.token, id);
      expect(res.body.data.dashboard.overall.statusLabel).toBe(label);
      expect(res.body.data.dashboard.overall.status).toBe(status);
      expect(res.body.data.dashboard.overall.risk).toBe(risk);
    });

    it('an UNRECOGNISED label degrades to `Not Assessed`, never toward a clean bill', async () => {
      const id = await seedAnalysed(alice.id, {
        report: withOverall({
          status: 'Healthy',
          // A vocabulary this backend does not know. The dangerous failure mode
          // is treating it as "close enough to Healthy".
          status_label: 'Totally Fine',
          risk: 'Low',
          any_assessed: true,
          complete: true,
        }),
      });

      const res = await getDashboard(alice.token, id);
      expect(res.status).toBe(200);

      const { overall } = res.body.data.dashboard;
      expect(overall.statusLabel).toBe('Not Assessed');
      // The whole verdict degrades with it - a status of `Healthy` beside a
      // label nobody understands is not a healthy report.
      expect(overall.status).toBeNull();
      expect(overall.anyAssessed).toBe(false);
      expect(overall.complete).toBe(false);
      // And the unrecognised string itself is never echoed to the client.
      expect(JSON.stringify(res.body.data.dashboard.overall)).not.toContain('Totally Fine');
    });

    it('records STATUS_LABEL_UNRECOGNISED as the disagreement code', () => {
      // Asserted against `summariseReport` directly because that is the single
      // place the code is produced, and it is what the persisted
      // `analysis.statusLabelDisagreement` and the `report`-stage warning are
      // both built from. See the note in the report at the end of this suite
      // about where this code is and is not visible over HTTP.
      const summary = analysisService.summariseReport(
        clinicalReport({
          overall: { status: 'Healthy', status_label: 'Totally Fine', complete: true },
        })
      );
      expect(summary.statusLabelDisagreement).toBe('STATUS_LABEL_UNRECOGNISED');
      expect(summary.overallStatusLabel).toBe('Not Assessed');
      expect(summary.overallStatus).toBeNull();

      const warnings = analysisService.statusLabelWarnings(summary);
      expect(warnings).toHaveLength(1);
      expect(warnings[0].code).toBe('STATUS_LABEL_UNRECOGNISED');
      // A fixed table sentence - never the offending value.
      expect(warnings[0].message).not.toContain('Totally Fine');
    });

    it('`status: null` beside `status_label: "Healthy"` is refused, not believed', async () => {
      // The single most dangerous pair this pipeline could emit.
      const id = await seedAnalysed(alice.id, {
        report: withOverall({
          status: null,
          status_label: 'Healthy',
          risk: null,
          any_assessed: false,
          complete: false,
        }),
      });
      const res = await getDashboard(alice.token, id);
      const { overall } = res.body.data.dashboard;
      expect(overall.statusLabel).toBe('Not Assessed');
      expect(overall.status).toBeNull();
      expect(overall.anyAssessed).toBe(false);
      expect(overall.complete).toBe(false);
    });

    /**
     * ================== A DEFECT THIS SUITE FOUND. DO NOT DELETE. ==========
     *
     * `analysisService.summariseReport` gates `assessmentComplete` and
     * `anyAssessed` on `status !== null`, but NOT `overallRisk`. So when the
     * status degrades to `null` - because the label was unrecognised, or
     * because it could not accompany the status - the RISK LEVEL survives the
     * degradation and reaches the card unchanged.
     *
     * The result is a dashboard whose overall card reads
     * `statusLabel: "Not Assessed"` beside `risk: "Low"`, which is precisely
     * the section 11 hazard ("no decisions must never become Low") that the
     * comment above that very line in `analysisService.js` claims is prevented:
     *
     *     // Risk: null when nothing was assessed, and null when the service
     *     // sent something we do not recognise. "No decisions" must never
     *     // become "Low".
     *
     * `Low` is the reassuring half of the card, and it was the half that
     * survived.
     *
     * FIXED 2026-09-05, and these two tests now GUARD the fix. They were
     * written asserting the wrong behaviour on purpose, with the instruction
     * to invert both `toBe('Low')` assertions to `toBeNull()` once the source
     * was corrected - which is what happened, and the inversion is exactly
     * what made the fix visible here rather than silent.
     *
     * Keep both strict. The failure they guard is not a crash: it is a card
     * printing "Not Assessed" beside a reassuring "Low", which is `INSUFFICIENT
     * _DATA` carrying a risk - the hazard section 11 names first.
     */
    it('risk does NOT survive an unrecognised-label degradation', () => {
      const summary = analysisService.summariseReport(
        clinicalReport({
          overall: {
            status: 'Healthy',
            status_label: 'Totally Fine',
            risk: 'Low',
            any_assessed: true,
            complete: true,
          },
        })
      );
      expect(summary.overallStatus).toBeNull();
      expect(summary.overallStatusLabel).toBe('Not Assessed');
      expect(summary.anyAssessed).toBe(false);
      // Nothing was assessed, so there is no risk to state. A recognised
      // `risk` value on the payload does not survive the degradation.
      expect(summary.overallRisk).toBeNull();
    });

    it('an explicit `risk: null` is not overridden by the top-level `overall_risk`', () => {
      const summary = analysisService.summariseReport({
        overall: {
          status: null,
          status_label: 'Not Assessed',
          risk: null,
          any_assessed: false,
          complete: false,
        },
        // Module 17 also prints the risk at the top level, and the fallback to
        // it is legitimate when `overall.risk` is genuinely ABSENT. It is not
        // legitimate here: `overall.risk` is present and explicitly `null`,
        // which is the producer saying "there is no risk to state". An
        // explicit null is an answer, not a gap to be filled from elsewhere.
        overall_risk: 'Low',
      });
      expect(summary.overallStatus).toBeNull();
      expect(summary.anyAssessed).toBe(false);
      expect(summary.overallRisk).toBeNull();
    });

    it('a bare `Healthy` label contradicting `complete: false` prints as partial', async () => {
      const id = await seedAnalysed(alice.id, {
        report: withOverall({
          status: 'Healthy',
          status_label: 'Healthy',
          any_assessed: true,
          complete: false,
        }),
      });
      const res = await getDashboard(alice.token, id);
      // The pessimistic reading wins: the card must not show a complete clean
      // bill for an assessment the producer itself called incomplete.
      expect(res.body.data.dashboard.overall.statusLabel).toBe(
        'Healthy (partial assessment)'
      );
    });

    it('a MISSING label falls back pessimistically, not to the bare status', async () => {
      const id = await seedAnalysed(alice.id, {
        report: withOverall({
          status: 'Healthy',
          status_label: undefined,
          any_assessed: true,
          complete: false,
        }),
      });
      const res = await getDashboard(alice.token, id);
      expect(res.body.data.dashboard.overall.statusLabel).toBe(
        'Healthy (partial assessment)'
      );
    });
  });

  // ================================================== the absence hazard ====
  //
  // MEMORY.md section 11: "Absence must never become a value." A dashboard is
  // where that happens, because a card has to show SOMETHING.
  describe('absence never becomes a value', () => {
    let alice;
    beforeEach(async () => {
      alice = await makeUser('alice.absence@example.com');
    });

    it('`status: null` + `any_assessed: false` renders as Not Assessed, never Healthy', async () => {
      const id = await seedAnalysed(alice.id, {
        report: clinicalReport({
          conditions: [],
          prioritized: [],
          overall: {
            status: null,
            status_label: 'Not Assessed',
            risk: null,
            rule_applied: 'nothing_assessed',
            any_assessed: false,
            complete: false,
            caveat:
              'No condition in this analysis could be assessed from the submitted document.',
            assessed_condition_count: 0,
            unassessed_condition_count: 2,
            unassessed_conditions: ['diabetes', 'kidney_disease'],
            abnormal_condition_count: 0,
            high_risk_condition_count: 0,
          },
          overall_risk: null,
          summary: {
            condition_count: 0,
            abnormal_count: 0,
            critical_count: 0,
            normal_count: 0,
            unassessed_count: 2,
          },
        }),
      });

      const res = await getDashboard(alice.token, id);
      const { overall } = res.body.data.dashboard;

      expect(overall.status).toBeNull();
      expect(overall.statusLabel).toBe('Not Assessed');
      expect(overall.risk).toBeNull();
      expect(overall.anyAssessed).toBe(false);
      // "0 abnormal findings" reads exactly like a clean bill, so the fact that
      // NOTHING was assessed has to be on the card beside the zeroes.
      expect(overall.unassessedConditionCount).toBe(2);
      expect(overall.caveat).toMatch(/could be assessed/);
      // And the word must not appear anywhere in the overall card.
      expect(JSON.stringify(overall)).not.toContain('Healthy');
    });

    it('an unassessed CONDITION card carries no risk and is not "normal"', async () => {
      const id = await seedAnalysed(alice.id, {
        report: clinicalReport({
          conditions: [
            {
              condition: 'kidney_disease',
              status: null,
              risk: null,
              confidence: null,
              assessed: false,
              flagged: false,
              // Deliberately absent: `normal` and `critical`. The producer did
              // not say, and the card must not decide for it.
            },
          ],
          prioritized: [
            {
              condition: 'kidney_disease',
              rank: 1,
              priority: 'Not Assessed',
              tier: 2,
              status: null,
              risk: null,
              assessed: false,
            },
          ],
        }),
      });

      const res = await getDashboard(alice.token, id);
      const [card] = res.body.data.dashboard.conditions;

      expect(card.condition).toBe('kidney_disease');
      expect(card.status).toBeNull();
      expect(card.risk).toBeNull();
      expect(card.assessed).toBe(false);
      expect(card.priority).toBe('Not Assessed');
      // NOT `false`. The producer said nothing about these, and `false` is a
      // claim. `undefined` disappears from JSON, which is the honest render.
      expect(card).not.toHaveProperty('normal');
      expect(card).not.toHaveProperty('critical');
    });

    // `numberOrUndefined` / `booleanOrUndefined` are asserted at the service
    // level as well as through the route: over HTTP an `undefined` is simply
    // an absent key, and the only way to prove the module did not coerce is to
    // look at what it returned before serialisation.
    it('numberOrUndefined never turns a missing count into 0', () => {
      const built = dashboardService.buildOverallCard({
        overall: {
          status: 'Healthy',
          status_label: 'Healthy',
          complete: true,
          any_assessed: true,
        },
        summary: {},
      });

      for (const key of [
        'assessedConditionCount',
        'unassessedConditionCount',
        'abnormalConditionCount',
        'highRiskConditionCount',
      ]) {
        expect(built[key]).toBeUndefined();
        expect(built[key]).not.toBe(0);
      }
      for (const key of Object.keys(built.counts)) {
        expect(built.counts[key]).toBeUndefined();
      }
      // A non-finite number is absence too - NaN is not a count.
      expect(
        dashboardService.buildOverallCard({
          overall: {},
          summary: { abnormal_count: NaN, condition_count: Infinity },
        }).counts.abnormal
      ).toBeUndefined();
    });

    it('booleanOrUndefined never turns a missing flag into false', () => {
      const [card] = dashboardService.buildConditionCards({
        conditions: [{ condition: 'diabetes' }],
      });
      for (const key of [
        'assessed',
        'partiallyAssessed',
        'flagged',
        'critical',
        'normal',
        'hybrid',
        'basisConflict',
      ]) {
        expect(card[key]).toBeUndefined();
        expect(card[key]).not.toBe(false);
      }
    });

    it('an unrecognised laboratory partition is `null`, never `valid`', () => {
      expect(dashboardService.labState('valid')).toBe('valid');
      expect(dashboardService.labState('questionable')).toBe('questionable');
      expect(dashboardService.labState('rejected')).toBe('rejected');
      // A partition name from a future build must render as "we do not know how
      // reliable this is", never as one the analysis was entitled to rely on.
      expect(dashboardService.labState('provisional')).toBeNull();
      expect(dashboardService.labState(undefined)).toBeNull();
      expect(dashboardService.labState(null)).toBeNull();
      // And never accidentally the fourth state, which means something else.
      expect(dashboardService.labState('unavailable')).toBeNull();
    });

    it('a REJECTED value keeps its own card and is never downgraded to unavailable', async () => {
      const id = await seedAnalysed(alice.id, {
        report: clinicalReport({
          laboratory_values: [
            {
              feature: 'creatinine',
              display_name: 'Creatinine',
              value: 88.4,
              unit: 'mg/dl',
              status: 'rejected',
              usable: false,
              rejection_code: 'IMPLAUSIBLE_VALUE',
              rejection_reason: 'The value is outside any physiologically possible range.',
            },
          ],
          explainability: {
            conditions: [
              {
                condition: 'kidney_disease',
                evidence: [
                  {
                    feature: 'creatinine',
                    availability: 'found_but_not_trusted',
                    explanation: 'This value was read but could not be trusted.',
                  },
                ],
              },
            ],
          },
        }),
      });

      const res = await getDashboard(alice.token, id);
      const cards = res.body.data.dashboard.laboratory;

      // Exactly ONE card for creatinine - it was printed and read, so reporting
      // it as missing would be false.
      expect(cards.filter((c) => c.feature === 'creatinine')).toHaveLength(1);
      const [card] = cards;
      expect(card.state).toBe('rejected');
      expect(card.state).not.toBe('unavailable');
      expect(card.rejectionCode).toBe('IMPLAUSIBLE_VALUE');
      expect(card.usable).toBe(false);
    });

    it('a feature Module 20 recorded as absent gets an UNAVAILABLE card with a reason', async () => {
      const id = await seedAnalysed(alice.id, {
        report: clinicalReport({
          laboratory_values: [],
          explainability: {
            conditions: [
              {
                condition: 'diabetes',
                evidence: [
                  {
                    feature: 'hba1c',
                    display_name: 'HbA1c',
                    availability: 'not_present_in_report',
                    explanation: 'This test is not present on the submitted report.',
                  },
                ],
              },
            ],
          },
        }),
      });

      const res = await getDashboard(alice.token, id);
      const card = res.body.data.dashboard.laboratory.find((c) => c.feature === 'hba1c');

      expect(card.state).toBe('unavailable');
      // No value is invented for it, in either direction.
      expect(card.value).toBeNull();
      expect(card.unit).toBeNull();
      expect(card.availability).toBe('not_present_in_report');
      expect(card.availabilityExplanation).toBe(
        'This test is not present on the submitted report.'
      );
    });

    it('`document.missing_features` alone creates no card - there is no reason to show', async () => {
      const id = await seedAnalysed(alice.id, {
        report: clinicalReport({
          laboratory_values: [],
          document: { missing_features: ['vitamin_d'] },
          explainability: { conditions: [] },
        }),
      });

      const res = await getDashboard(alice.token, id);
      // The fact is still reported, under document quality where it belongs...
      expect(res.body.data.dashboard.document.missingFeatures).toEqual(['vitamin_d']);
      // ...but not as a laboratory card, which would have to state a reason
      // nobody wrote down.
      expect(res.body.data.dashboard.laboratory).toEqual([]);
    });

    it('"unreadable" is never downgraded to "not present" when lines disagree', () => {
      // Two citations of one feature. `unreadable_document` is the weaker, more
      // cautious claim and must survive; asserting "it was not there" would
      // state something the analysis does not know.
      const index = dashboardService.indexEvidenceLines({
        explainability: {
          conditions: [
            {
              condition: 'diabetes',
              evidence: [
                { feature: 'hba1c', availability: 'not_present_in_report' },
                { feature: 'hba1c', availability: 'unreadable_document' },
              ],
            },
          ],
        },
      });
      expect(index.get('hba1c').availability).toBe('unreadable_document');
    });
  });

  // ============================================ Module 23: the boolean =======
  describe('Module 23 branches on the boolean, not on the string', () => {
    let alice;
    beforeEach(async () => {
      alice = await makeUser('alice.m23@example.com');
    });

    const entry = (overrides) => ({
      subject: 'hba1c',
      feature: 'hba1c',
      conditions: ['diabetes'],
      sources: [],
      findings: [],
      ...overrides,
    });

    it('carries the results that were never explained, and why', async () => {
      // A REPORT WITH EIGHT RESULTS AND SIX EXPLANATIONS. Module 23 explains up
      // to `max_explanations` and records every value it passed over; that list
      // was produced, stored, and dropped at this layer, so the dashboard
      // showed six cards with nothing saying the other two were not attempted.
      // The entries array cannot carry this: an explanation that was never
      // requested has no entry to be absent in.
      const id = await seedAnalysed(alice.id, {
        patientExplanation: {
          explanation_available: true,
          generated_count: 1,
          withheld_count: 0,
          explanations: [
            entry({
              feature: 'hba1c',
              outcome: 'generated',
              generated_explanation_available: true,
              explanation: 'HbA1c reflects average blood sugar over recent months.',
              notice: null,
            }),
          ],
          skipped: [
            { feature: 'cholesterol', reason: 'explanation_limit_reached' },
            { feature: 'triglycerides', reason: 'explanation_limit_reached' },
          ],
        },
      });

      const res = await getDashboard(alice.token, id);
      const { notExplained } = res.body.data.dashboard.recommendations.explanations;

      expect(notExplained).toEqual([
        { feature: 'cholesterol', reason: 'explanation_limit_reached' },
        { feature: 'triglycerides', reason: 'explanation_limit_reached' },
      ]);
    });

    it('reports nothing skipped as an empty list, never as a missing key', async () => {
      const id = await seedAnalysed(alice.id, {
        patientExplanation: {
          explanation_available: true,
          generated_count: 1,
          withheld_count: 0,
          explanations: [
            entry({
              feature: 'hba1c',
              outcome: 'generated',
              generated_explanation_available: true,
              explanation: 'HbA1c reflects average blood sugar.',
              notice: null,
            }),
          ],
        },
      });

      const res = await getDashboard(alice.token, id);
      expect(
        res.body.data.dashboard.recommendations.explanations.notExplained
      ).toEqual([]);
    });

    it('a WITHHELD explanation and an ABSENT one render differently', async () => {
      const id = await seedAnalysed(alice.id, {
        patientExplanation: {
          explanation_available: true,
          generated_count: 1,
          withheld_count: 1,
          explanations: [
            entry({
              feature: 'hba1c',
              outcome: 'generated',
              generated_explanation_available: true,
              explanation: 'HbA1c reflects average blood sugar over recent months.',
              notice: null,
            }),
            entry({
              feature: 'creatinine',
              subject: 'creatinine',
              outcome: 'withheld_by_safety',
              // THE POINT. The boolean says no approved text exists; the string
              // is present anyway, as a regressed producer might send it.
              generated_explanation_available: false,
              explanation: 'CANARY-a-sentence-the-safety-layer-refused',
              notice: 'A plain-language explanation could not be prepared for this finding.',
            }),
          ],
        },
      });

      const res = await getDashboard(alice.token, id);
      const { entries } = res.body.data.dashboard.recommendations.explanations;

      const generated = entries.find((e) => e.feature === 'hba1c');
      expect(generated.available).toBe(true);
      expect(generated.explanation).toMatch(/average blood sugar/);
      expect(generated.notice).toBeNull();

      const withheld = entries.find((e) => e.feature === 'creatinine');
      expect(withheld.available).toBe(false);
      // The string is NOT rendered even though it is present in the payload.
      expect(withheld.explanation).toBeNull();
      // And there is always something to show instead - a blank space is what
      // a `{explanation && ...}` renderer would produce.
      expect(withheld.notice).toMatch(/could not be prepared/);
      expect(JSON.stringify(res.body)).not.toContain('CANARY-a-sentence');
    });

    it('a truthy-but-not-true availability flag is treated as unavailable', async () => {
      const id = await seedAnalysed(alice.id, {
        patientExplanation: {
          explanation_available: true,
          explanations: [
            entry({
              outcome: 'generated',
              // Not the boolean `true`. `=== true` is the only correct test.
              generated_explanation_available: 'yes',
              explanation: 'CANARY-truthy-string-availability',
              notice: 'No explanation was written.',
            }),
          ],
        },
      });

      const res = await getDashboard(alice.token, id);
      const [only] = res.body.data.dashboard.recommendations.explanations.entries;
      expect(only.available).toBe(false);
      expect(only.explanation).toBeNull();
      expect(JSON.stringify(res.body)).not.toContain('CANARY-truthy-string');
    });

    it('a stage that never answered is `null`, not `false`', async () => {
      // Module 23 absent entirely: the stage did not run. That is a different
      // fact from "it ran and approved nothing", and a renderer must be able to
      // tell them apart.
      const id = await seedAnalysed(alice.id);
      const res = await getDashboard(alice.token, id);
      const { explanations, guidance } = res.body.data.dashboard.recommendations;

      expect(explanations.available).toBeNull();
      expect(explanations.entries).toEqual([]);
      // Module 26 has only two states - it has no "withheld" outcome - so
      // `false` there means exactly "no guidance result is stored".
      expect(guidance.available).toBe(false);
      expect(guidance.items).toEqual([]);
    });

    it('a Module 23 stage that answered and approved nothing is `false`, with a notice', async () => {
      const id = await seedAnalysed(alice.id, {
        patientExplanation: {
          explanation_available: false,
          notice:
            'No plain-language explanation could be prepared for this report. The structured findings are unaffected.',
          generated_count: 0,
          withheld_count: 2,
          explanations: [],
        },
      });

      const res = await getDashboard(alice.token, id);
      const { explanations } = res.body.data.dashboard.recommendations;
      expect(explanations.available).toBe(false);
      expect(explanations.notice).toMatch(/could be prepared/);
      expect(explanations.withheldCount).toBe(2);
    });
  });

  // ====================================== descriptions of skipped tests ======
  //
  // The glossary describes tests this platform does NOT assess, generated from
  // the test NAME alone. The property that makes it safe is negative -- no
  // patient data goes into the prompt -- and cannot be asserted from here; it
  // lives in the ai-service's own suite. What CAN be asserted here, and is, is
  // that the read model keeps three cases apart:
  //
  //   never asked   -> no description fields at all
  //   described     -> descriptionAvailable: true  + description
  //   withheld      -> descriptionAvailable: false + descriptionNotice
  //
  // Only tests the laboratory flagged are ever asked about, so "never asked"
  // is the common case. Folding it into "withheld" would tell a reader there
  // is nothing to say about a test nobody enquired about -- this codebase's
  // standing failure mode, one field away.
  describe('parameter glossary merged into the unassessed section', () => {
    const features = {
      unmapped: [
        { test_name: 'Potassium', value_raw: '5.2', unit: 'mmol/L', reason: 'no_feature' },
        { test_name: 'LDL Cholesterol', value_raw: '160', unit: 'mg/dL', reason: 'no_feature' },
        { test_name: 'Urine Colour', value_raw: 'Pale Yellow', reason: 'no_feature' },
      ],
    };
    const extraction = {
      extracted_parameters: [
        { test_name: 'Potassium', flag: 'high', reference_low: 3.5, reference_high: 5.1 },
        { test_name: 'LDL Cholesterol', flag: 'high', reference_high: 100 },
        { test_name: 'Urine Colour', flag: null },
      ],
    };
    const glossary = {
      version: '1.0.0',
      entries: [
        {
          test_name: 'Potassium',
          description: 'A mineral your body uses for nerve and muscle function.',
          available: true,
          notice: null,
        },
        {
          test_name: 'LDL Cholesterol',
          description: null,
          available: false,
          notice: 'The description did not pass safety review.',
        },
      ],
    };

    const unanalysedFrom = (parameterGlossary) =>
      dashboardService.buildDashboard({
        clinicalReport: clinicalReport(),
        engineeredFeatures: features,
        extraction,
        parameterGlossary,
      }).unanalysed;

    const byName = (unanalysed, name) =>
      unanalysed.items.find((item) => item.testName === name);

    it('attaches a description to the test it belongs to, and to no other', () => {
      const unanalysed = unanalysedFrom(glossary);
      const potassium = byName(unanalysed, 'Potassium');
      expect(potassium.descriptionAvailable).toBe(true);
      expect(potassium.description).toBe(
        'A mineral your body uses for nerve and muscle function.'
      );
      // The laboratory's own facts are untouched by the merge.
      expect(potassium.labFlaggedAbnormal).toBe(true);
      expect(potassium.labReferenceHigh).toBe(5.1);
    });

    it('reports a WITHHELD description as withheld, never as an absent one', () => {
      const ldl = byName(unanalysedFrom(glossary), 'LDL Cholesterol');
      expect(ldl.descriptionAvailable).toBe(false);
      expect(ldl.descriptionNotice).toBe('The description did not pass safety review.');
      expect(ldl).not.toHaveProperty('description');
    });

    it('leaves a test nobody asked about with NO description fields at all', () => {
      const urine = byName(unanalysedFrom(glossary), 'Urine Colour');
      expect(urine).not.toHaveProperty('descriptionAvailable');
      expect(urine).not.toHaveProperty('description');
      expect(urine).not.toHaveProperty('descriptionNotice');
    });

    it('distinguishes "the stage never ran" from "it described nothing"', () => {
      expect(unanalysedFrom(null).descriptionsPresent).toBe(false);
      expect(unanalysedFrom({ version: '1.0.0', entries: [] }).descriptionsPresent).toBe(true);
      // And a report with nothing unmapped still answers the question.
      const empty = dashboardService.buildDashboard({
        clinicalReport: clinicalReport(),
        engineeredFeatures: { unmapped: [] },
        extraction,
        parameterGlossary: glossary,
      }).unanalysed;
      expect(empty.descriptionsPresent).toBe(true);
      expect(empty.describedCount).toBe(0);
    });

    it('counts what is on screen, not what the payload claims', () => {
      // A producer's own counters would say ninety-nine of each. These counts
      // come from the items, so an entry naming a test that is not on this
      // report cannot inflate them.
      const inflated = {
        ...glossary,
        generated_count: 99,
        withheld_count: 99,
        entries: [
          ...glossary.entries,
          { test_name: 'Not On This Report', description: 'x', available: true },
        ],
      };
      const unanalysed = unanalysedFrom(inflated);
      expect(unanalysed.describedCount).toBe(1);
      expect(unanalysed.withheldCount).toBe(1);
      expect(unanalysed.count).toBe(3);
      expect(unanalysed.items.map((item) => item.testName)).not.toContain('Not On This Report');
    });

    it('treats a non-string or blank description as no description', () => {
      for (const description of [42, '', '   ', null, { text: 'nope' }]) {
        const item = byName(
          unanalysedFrom({ entries: [{ test_name: 'Potassium', description, available: true }] }),
          'Potassium'
        );
        expect(item.descriptionAvailable).toBe(false);
        expect(item).not.toHaveProperty('description');
      }
    });

    it('withholds when `available` is not true, whatever text came with it', () => {
      // The producer's flag decides, not the truthiness of the string. An
      // entry carrying text it did not clear for release must not be shown.
      const item = byName(
        unanalysedFrom({
          entries: [
            {
              test_name: 'Potassium',
              description: 'Text that was not approved.',
              available: false,
            },
          ],
        }),
        'Potassium'
      );
      expect(item.descriptionAvailable).toBe(false);
      expect(item).not.toHaveProperty('description');
    });

    it('survives a malformed glossary without losing the section', () => {
      for (const bad of [
        { entries: 'nope' },
        { entries: [null, 7, { test_name: '' }] },
        'nope',
        [],
      ]) {
        const unanalysed = unanalysedFrom(bad);
        expect(unanalysed.count).toBe(3);
        expect(unanalysed.describedCount).toBe(0);
      }
    });

    it('reaches the HTTP response, which is what the projection is for', async () => {
      const alice = await makeUser('alice.glossary@example.com');
      const id = await seedAnalysed(alice.id, {
        features,
        extraction,
        parameterGlossary: glossary,
      });

      const res = await getDashboard(alice.token, id);
      expect(res.status).toBe(200);
      const unanalysed = res.body.data.dashboard.unanalysed;
      expect(unanalysed.descriptionsPresent).toBe(true);
      expect(unanalysed.items.find((item) => item.testName === 'Potassium').description).toMatch(
        /nerve and muscle/
      );
    });

    it('a report analysed before the stage existed says so, and still renders', async () => {
      const alice = await makeUser('alice.noglossary@example.com');
      const id = await seedAnalysed(alice.id, { features, extraction });

      const res = await getDashboard(alice.token, id);
      expect(res.status).toBe(200);
      const unanalysed = res.body.data.dashboard.unanalysed;
      expect(unanalysed.descriptionsPresent).toBe(false);
      expect(unanalysed.count).toBe(3);
      expect(unanalysed.items.every((item) => !('descriptionAvailable' in item))).toBe(true);
    });
  });

  // ================================================= projection discipline ===
  describe('the route reads only what it needs', () => {
    it('does not read the extraction, the features or either decision payload', async () => {
      const alice = await makeUser('alice.proj@example.com');
      const id = await seedAnalysed(alice.id, {
        extraction: { raw_text: 'CANARY-EXTRACTION-RAW-TEXT' },
        features: { features: { hba1c: 6.8 }, note: 'CANARY-FEATURES' },
        ruleDecisions: { note: 'CANARY-RULES' },
        mlDecisions: { note: 'CANARY-ML' },
        featureValidation: { note: 'CANARY-VALIDATION' },
      });

      const res = await getDashboard(alice.token, id);
      expect(res.status).toBe(200);
      const body = JSON.stringify(res.body);
      for (const canary of [
        'CANARY-EXTRACTION-RAW-TEXT',
        'CANARY-FEATURES',
        'CANARY-RULES',
        'CANARY-ML',
        'CANARY-VALIDATION',
      ]) {
        expect(body).not.toContain(canary);
      }
      // And the storage key never leaves the server.
      expect(body).not.toContain('storageKey');
    });

    it('buildDashboard refuses to synthesise a dashboard from nothing', () => {
      expect(() => dashboardService.buildDashboard({ clinicalReport: null })).toThrow(TypeError);
      expect(() => dashboardService.buildDashboard({ clinicalReport: [] })).toThrow(TypeError);
      expect(() => dashboardService.buildDashboard({})).toThrow(TypeError);
    });
  });

  describe('a value outside its printed interval, with no flag extracted', () => {
    /* THE DEFECT THIS PINS, AND IT REACHED A READER.
     *
     * `labFlaggedAbnormal` used to be the extracted `flag` alone. `Test 3.pdf`
     * was analysed twice: the first run extracted `flag: "high"` for CRP, the
     * second returned `flag: null` for CRP, SGPT and TSH while extracting the
     * same values and the same printed intervals. Extraction is a model call
     * and is not deterministic -- MEMORY.md 6ba records the same happening to
     * test NAMES.
     *
     * The consequence was not a missing flag. It was C-REACTIVE PROTEIN
     * 38.9 mg/L, against a printed interval of <= 5, shown to the patient as
     * "In range" -- because the dashboard reads "an interval was printed" as
     * "the laboratory compared it and it was fine" and never compared the two
     * numbers itself. A dropped flag turned a finding into a reassurance.
     */
    // ⚠ `value_numeric` AND `value_raw`, COPIED FROM A REAL STORED RECORD.
    // An earlier version of this fixture used `value:`, which does not exist
    // on an extracted parameter. The code under test read `source.value` too,
    // so both were wrong in the same direction and these tests PASSED while
    // the real page still showed CRP 38.9 mg/L as "In range". A fixture
    // written from an assumption cannot catch that assumption.
    const extractionWithoutFlags = {
      extracted_parameters: [
        // The real CRP row from `Test 3.pdf`, with the flag the re-extraction
        // lost. Note `reference_low: null` -- the report prints "< 5.0".
        {
          test_name: 'CRP',
          value_raw: '38.9',
          value_numeric: 38.9,
          flag: null,
          reference_low: null,
          reference_high: 5,
        },
        // Inside its interval, also unflagged: must NOT become abnormal.
        {
          test_name: 'TSH',
          value_raw: '1.81',
          value_numeric: 1.81,
          flag: null,
          reference_low: 0.27,
          reference_high: 5,
        },
        // Below its lower bound, unflagged.
        {
          test_name: 'Ferritin',
          value_raw: '4',
          value_numeric: 4,
          flag: null,
          reference_low: 30,
          reference_high: 400,
        },
        // Non-numeric, no interval: nothing to compare, nothing to claim.
        { test_name: 'Urine Colour', value_raw: 'Yellow', flag: null },
      ],
    };

    // `unmapped` is what puts a row in the unassessed section; `extraction`
    // supplies the printed value, interval and flag for it. Both are needed,
    // exactly as in the glossary fixture above.
    const unmappedRows = {
      unmapped: [
        { test_name: 'CRP', value_raw: '38.9', unit: 'mg/L', reason: 'no_feature' },
        { test_name: 'TSH', value_raw: '1.81', unit: 'uIU/mL', reason: 'no_feature' },
        { test_name: 'Ferritin', value_raw: '4', unit: 'ng/mL', reason: 'no_feature' },
        { test_name: 'Urine Colour', value_raw: 'Yellow', reason: 'no_feature' },
      ],
    };

    const built = () =>
      dashboardService.buildDashboard({
        clinicalReport: clinicalReport(),
        engineeredFeatures: unmappedRows,
        extraction: extractionWithoutFlags,
        parameterGlossary: null,
      }).unanalysed;

    const row = (name) => built().items.find((item) => item.testName === name);

    it('is abnormal when the value is ABOVE the printed high bound', () => {
      expect(row('CRP').labFlaggedAbnormal).toBe(true);
      // A direction the page can print, derived from the two numbers a reader
      // can see -- not invented, and not attributed to the laboratory.
      expect(row('CRP').labFlag).toBe('high');
    });

    it('is abnormal when the value is BELOW the printed low bound', () => {
      expect(row('Ferritin').labFlaggedAbnormal).toBe(true);
      expect(row('Ferritin').labFlag).toBe('low');
    });

    it('is NOT abnormal when the value sits inside the printed interval', () => {
      // The half that must not collapse: widening this into "no flag means
      // look again" would flag every normal result on the report.
      expect(row('TSH').labFlaggedAbnormal).toBe(false);
      expect(row('TSH').labFlag).toBeNull();
    });

    it('claims nothing when there is no interval to compare against', () => {
      expect(row('Urine Colour').labFlaggedAbnormal).toBe(false);
      expect(row('Urine Colour').labFlag).toBeNull();
    });

    it('counts the comparison, not the flags', () => {
      // `labFlaggedCount` feeds the dashboard's summary sentence. With the
      // flag alone it said 1 on a report with two results outside their
      // printed intervals.
      expect(built().labFlaggedCount).toBe(2);
    });
  });
});

// =========================================================================
// THE REPORT'S OWN SEX AND AGE AGAINST THE PROFILE THE ANALYSIS USED
// =========================================================================
//
// 2026-09-24: every analysis takes sex and age from the account profile. A
// report printing "34 Years / Female" on a "20, male" account was judged with
// male thresholds and nothing on the page said so.
describe('printed sex and age against the profile the analysis used', () => {
  const profileFeatures = (age, gender) => ({
    features: {
      age: { name: 'age', value: age, source: 'patient_profile' },
      gender: { name: 'gender', value: gender, source: 'patient_profile' },
    },
  });
  const analysedOn = (iso) => ({ version: 1, runCount: 1, completedAt: new Date(iso) });

  it('names a disagreement in sex and in age', async () => {
    const alice = await makeUser('identity.conflict@example.com');
    const id = await seedAnalysed(alice.id, {
      printedIdentity: { sex: 'female', sexStatus: 'read', ageYears: 34, ageStatus: 'read' },
      features: profileFeatures(20, 'male'),
      reportDate: new Date('2026-09-05T00:00:00Z'),
      analysis: analysedOn('2026-09-11T00:00:00Z'),
    });
    const res = await getDashboard(alice.token, id);
    expect(res.status).toBe(200);
    expect(res.body.data.identity.status).toBe('conflict');
    expect(res.body.data.identity.conflicts).toEqual([
      { field: 'sex', printed: 'female', used: 'male' },
      { field: 'age', printed: 34, used: 20 },
    ]);
  });

  it('says consistent only when both were read and both agree', async () => {
    const alice = await makeUser('identity.ok@example.com');
    const id = await seedAnalysed(alice.id, {
      printedIdentity: { sex: 'male', sexStatus: 'read', ageYears: 20, ageStatus: 'read' },
      features: profileFeatures(21, 'male'),
      reportDate: new Date('2025-09-05T00:00:00Z'),
      analysis: analysedOn('2026-09-11T00:00:00Z'),
    });
    const res = await getDashboard(alice.token, id);
    expect(res.body.data.identity.status).toBe('consistent');
  });

  it('is NOT "consistent" when the report does not print an age', async () => {
    const alice = await makeUser('identity.partial@example.com');
    const id = await seedAnalysed(alice.id, {
      printedIdentity: { sex: 'male', sexStatus: 'read', ageStatus: 'absent' },
      features: profileFeatures(20, 'male'),
      analysis: analysedOn('2026-09-11T00:00:00Z'),
    });
    const res = await getDashboard(alice.token, id);
    expect(res.body.data.identity.status).toBe('incomplete');
  });

  it('is "not_checked" for a report analysed before these fields existed', async () => {
    const alice = await makeUser('identity.old@example.com');
    const id = await seedAnalysed(alice.id, { features: profileFeatures(20, 'male') });
    const res = await getDashboard(alice.token, id);
    expect(res.body.data.identity.status).toBe('not_checked');
    expect(res.body.data.identity.conflicts).toEqual([]);
  });
});
