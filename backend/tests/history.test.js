'use strict';

/**
 * `src/services/historyService.js` - the shared assembler behind Modules 28,
 * 29, 30 and 32.
 *
 * This is the one module in the longitudinal layer that decides WHICH of a
 * patient's reports exist as far as every timeline answer is concerned. Get it
 * wrong in the permissive direction and one patient's readings appear in
 * another's trend; get it wrong in the restrictive direction and a patient's
 * timeline silently shortens, which MEMORY.md section 6m names as the exact
 * failure the `considered` / `included` / `excludedCount` accounting exists to
 * prevent.
 *
 * It is tested directly rather than through a route because its contract is a
 * function contract - the routes that consume it are covered in
 * `tests/timeline.test.js`. axios is still mocked, because nothing in this
 * suite may reach a service even by accident.
 */

const mongoose = require('mongoose');

const mockAxios = { post: jest.fn(), get: jest.fn() };
jest.mock('axios', () => ({
  create: () => ({
    post: (...args) => mockAxios.post(...args),
    get: (...args) => mockAxios.get(...args),
  }),
}));

require('./helpers'); // boots src/app.js and therefore src/config/env.js
const config = require('../src/config/env');
const Report = require('../src/models/Report');
const User = require('../src/models/User');
const { ROLES } = require('../src/utils/roles');
const historyService = require('../src/services/historyService');

// --- fixtures ---------------------------------------------------------------

let userSeq = 0;

/** A real User row, so `user.id` is a genuine ObjectId the filters can match. */
async function makeUser(role = ROLES.PATIENT) {
  userSeq += 1;
  const user = await User.create({
    name: 'History User',
    email: `history.${userSeq}@example.com`,
    password: 'Str0ng!Passw0rd',
    role,
  });
  // The shape `protect` attaches to `req.user`.
  return { id: user._id.toString(), _id: user._id, role };
}

/** Module 6's `data` object, in the shape `TimelineReportInput.validated` takes. */
function validatedFeatureSet(features = { hba1c: 6.4 }) {
  const valid = {};
  for (const [name, value] of Object.entries(features)) {
    valid[name] = { name, value, unit: '%', status: 'valid', usable: true };
  }
  return {
    valid,
    questionable: {},
    rejected: {},
    missing_features: [],
    summary: { valid_count: Object.keys(valid).length },
  };
}

/**
 * One report row.
 *
 * `analysed` and `validated` are separated on purpose: the inclusion rule is a
 * conjunction of two independent facts, and a fixture that could not express
 * one without the other could not exercise either half of it.
 */
async function seedReport(
  userId,
  { analysed = true, validated = true, status = 'processed', chronoDate, features } = {}
) {
  const doc = await Report.create({
    user: userId,
    originalName: 'labs.pdf',
    storageKey: `${userId}/${new mongoose.Types.ObjectId().toString()}.pdf`,
    storageDriver: 'local',
    mimeType: 'application/pdf',
    sizeBytes: 1024,
    checksumSha256: 'b'.repeat(64),
    status,
    reportDate: chronoDate,
    analysis: { version: analysed ? 1 : 0, runCount: analysed ? 1 : 0 },
    featureValidation: validated ? validatedFeatureSet(features) : undefined,
  });
  return doc._id.toString();
}

const day = (n) => new Date(Date.UTC(2026, 0, n, 12, 0, 0));

describe('historyService - the shared timeline assembler', () => {
  // ========================================================= inclusion rule ==
  //
  // The documented rule is `analysis.version > 0` AND `featureValidation`
  // stored, with `status` DELIBERATELY not consulted. Each case below pins one
  // consequence of that, because each one is a decision somebody could
  // reasonably undo by "simplifying" the filter to a status check.
  describe('inclusion and exclusion', () => {
    let user;
    beforeEach(async () => {
      user = await makeUser();
    });

    it('includes a `processed` report with a validated feature set', async () => {
      const id = await seedReport(user.id, { chronoDate: day(1) });
      const history = await historyService.assembleHistory({ user });
      expect(history.snapshots.map((s) => s.report_id)).toEqual([id]);
      expect(history.includedCount).toBe(1);
    });

    it('EXCLUDES an unanalysed report as NOT_ANALYSED', async () => {
      await seedReport(user.id, { analysed: false, validated: false, status: 'uploaded' });
      const history = await historyService.assembleHistory({ user });
      expect(history.snapshots).toEqual([]);

      const excluded = await historyService.describeExcluded({ user });
      expect(excluded.count).toBe(1);
      expect(excluded.reports[0].reasonCode).toBe(
        historyService.EXCLUSION_REASONS.NOT_ANALYSED
      );
    });

    it('INCLUDES a `partial` report when validation succeeded', async () => {
      // A partial run is one where validation succeeded and the rules or the
      // predictors did not. Its readings are exactly as validated as a
      // `processed` report's, and dropping them would shorten the timeline over
      // a failure that has nothing to do with the readings.
      const id = await seedReport(user.id, { status: 'partial', chronoDate: day(1) });
      const history = await historyService.assembleHistory({ user });
      expect(history.snapshots.map((s) => s.report_id)).toEqual([id]);
      // And the status travels with it, so this is visible rather than assumed.
      expect(history.included[0].status).toBe('partial');
    });

    it('EXCLUDES a `partial` report when validation itself was the failed stage', async () => {
      await seedReport(user.id, { status: 'partial', validated: false });
      const history = await historyService.assembleHistory({ user });
      expect(history.snapshots).toEqual([]);

      const excluded = await historyService.describeExcluded({ user });
      // The SAME test excluded it - not a special case. Different reason code,
      // because the report did analyse; it just has no Module 6 verdict.
      expect(excluded.reports[0].reasonCode).toBe(
        historyService.EXCLUSION_REASONS.NO_VALIDATED_FEATURES
      );
    });

    it('INCLUDES a `failed` report that still holds a real Module 6 verdict', async () => {
      // The failure path writes only status bookkeeping; it never touches the
      // stored payloads or `analysis.version`. A report that analysed and then
      // failed a LATER re-run still carries a genuine reading of its own
      // document, and dropping it would remove that reading from the series
      // because of a subsequent unrelated failure.
      const id = await seedReport(user.id, { status: 'failed', chronoDate: day(1) });
      const history = await historyService.assembleHistory({ user });
      expect(history.snapshots.map((s) => s.report_id)).toEqual([id]);
      expect(history.included[0].status).toBe('failed');
    });

    it('INCLUDES a report whose every reading was rejected', async () => {
      // Module 28 renders it as a `TimelineGap` carrying the reason each
      // feature is unavailable, which beats it vanishing from the series. A gap
      // has no `value` field on either side of the wire, so it can never be
      // read back as a zero.
      const doc = await Report.create({
        user: user.id,
        originalName: 'labs.pdf',
        storageKey: `${user.id}/rejected.pdf`,
        storageDriver: 'local',
        mimeType: 'application/pdf',
        sizeBytes: 512,
        checksumSha256: 'c'.repeat(64),
        status: 'processed',
        analysis: { version: 1 },
        featureValidation: {
          valid: {},
          questionable: {},
          rejected: { hba1c: { name: 'hba1c', rejection_code: 'IMPLAUSIBLE_VALUE' } },
        },
      });
      const history = await historyService.assembleHistory({ user });
      expect(history.snapshots).toHaveLength(1);
      // Module 6's data object goes VERBATIM - `rejected` included, because it
      // is the map that lets a gap say WHY a reading is missing.
      expect(history.snapshots[0].validated.rejected.hba1c.rejection_code).toBe(
        'IMPLAUSIBLE_VALUE'
      );
      expect(doc.status).toBe('processed');
    });

    it('`considered = included + excludedCount` holds across a mixed library', async () => {
      await seedReport(user.id, { chronoDate: day(1) }); // included
      await seedReport(user.id, { status: 'partial', chronoDate: day(2) }); // included
      await seedReport(user.id, { status: 'failed', chronoDate: day(3) }); // included
      await seedReport(user.id, { analysed: false, validated: false }); // excluded
      await seedReport(user.id, { validated: false }); // excluded

      const history = await historyService.assembleHistory({ user });
      const excluded = await historyService.describeExcluded({ user });
      const summary = historyService.summariseHistory(history, excluded);

      expect(summary.included).toBe(3);
      expect(summary.excludedCount).toBe(2);
      // THE ACCOUNTING IDENTITY. Without it a timeline built from three of a
      // patient's five reports is indistinguishable from a patient with only
      // three reports.
      expect(summary.considered).toBe(
        summary.included + summary.excludedCount + summary.droppedByCap
      );
      expect(summary.droppedByCap).toBe(0);
      expect(summary.considered).toBe(5);
      expect(summary.excluded.map((r) => r.reasonCode).sort()).toEqual([
        'NOT_ANALYSED',
        'NO_VALIDATED_FEATURES',
      ]);
    });

    it('the accounting identity survives the cap engaging', async () => {
      /**
       * THE CASE THE TEST ABOVE CANNOT REACH, and an audit found it broken.
       *
       * That test seeds fewer eligible reports than the cap, so truncation
       * never engages and the identity holds trivially. With the cap engaged
       * the two-term version silently lost reports: 5 eligible + 2 unanalysed
       * against a cap of 3 reported `considered: 7, included: 3,
       * excludedCount: 2` and left TWO reports in neither bucket, with
       * `truncated: true` the only hint that anything was missing.
       *
       * `droppedByCap` is the third term that closes it. Keep this strict: a
       * history block that loses reports is indistinguishable from a patient
       * who never had them, which is the exact confusion the block exists to
       * prevent.
       */
      const realCap = config.history.maxReports;
      config.history.maxReports = 3;
      try {
        for (let i = 1; i <= 5; i += 1) {
          await seedReport(user.id, { chronoDate: day(i) }); // eligible
        }
        await seedReport(user.id, { analysed: false, validated: false });
        await seedReport(user.id, { validated: false });

        const history = await historyService.assembleHistory({ user });
        const excluded = await historyService.describeExcluded({ user });
        const summary = historyService.summariseHistory(history, excluded);

        expect(summary.truncated).toBe(true);
        expect(summary.considered).toBe(7);
        expect(summary.included).toBe(3);
        expect(summary.excludedCount).toBe(2);
        // The two eligible reports the cap dropped are named, not lost.
        expect(summary.droppedByCap).toBe(2);
        expect(summary.considered).toBe(
          summary.included + summary.excludedCount + summary.droppedByCap
        );
      } finally {
        config.history.maxReports = realCap;
      }
    });

    it('the two exclusion codes are the only ones, and they are ours', () => {
      // Fixed machine codes from this table and nowhere else - never built from
      // a service response and never from user input.
      expect(Object.values(historyService.EXCLUSION_REASONS)).toEqual([
        'NOT_ANALYSED',
        'NO_VALIDATED_FEATURES',
      ]);
    });
  });

  // ================================================================ ordering ==
  describe('ordering and the window', () => {
    let user;
    beforeEach(async () => {
      user = await makeUser();
    });

    it('returns snapshots OLDEST FIRST, by chronoDate', async () => {
      const middle = await seedReport(user.id, { chronoDate: day(2) });
      const oldest = await seedReport(user.id, { chronoDate: day(1) });
      const newest = await seedReport(user.id, { chronoDate: day(3) });

      const history = await historyService.assembleHistory({ user });
      expect(history.snapshots.map((s) => s.report_id)).toEqual([oldest, middle, newest]);
      expect(new Date(history.window.from)).toEqual(day(1));
      expect(new Date(history.window.to)).toEqual(day(3));
    });

    it('sends `chrono_date` as ISO-8601 with an explicit offset', async () => {
      await seedReport(user.id, { chronoDate: day(1) });
      const history = await historyService.assembleHistory({ user });
      // The far side reads a naive datetime as UTC, so the offset is the only
      // thing that stops the two sides disagreeing about a report's position.
      expect(history.snapshots[0].chrono_date).toBe('2026-01-01T12:00:00.000Z');
    });

    it('sends no `sequence` - the array index must not decide the ordering', async () => {
      await seedReport(user.id, { chronoDate: day(1) });
      await seedReport(user.id, { chronoDate: day(2) });
      const history = await historyService.assembleHistory({ user });
      for (const snapshot of history.snapshots) {
        expect(snapshot).not.toHaveProperty('sequence');
        expect(Object.keys(snapshot).sort()).toEqual(['chrono_date', 'report_id', 'validated']);
      }
    });

    it('`window` is null for a patient with no eligible reports', async () => {
      await seedReport(user.id, { analysed: false, validated: false });
      const history = await historyService.assembleHistory({ user });
      expect(history.window).toBeNull();
      // A refusal, not an error, and not an empty-but-successful trend.
      expect(history.snapshots).toEqual([]);
      expect(history.truncated).toBe(false);
    });
  });

  // ==================================================================== cap ===
  //
  // `truncated` must be PROVEN by fetching cap+1, not inferred. Inferring it
  // from `rows.length === cap` calls a patient with exactly `cap` reports
  // truncated; comparing against the total report count calls a patient with
  // many unanalysed reports truncated. Both are asserted below.
  describe('the HISTORY_MAX_REPORTS cap', () => {
    const realCap = config.history.maxReports;
    let user;

    beforeEach(async () => {
      user = await makeUser();
      config.history.maxReports = 3;
    });
    afterEach(() => {
      config.history.maxReports = realCap;
    });

    it('the shipped default is 50 and is clamped into the service\'s own range', () => {
      expect(realCap).toBe(50);
      expect(realCap).toBeGreaterThanOrEqual(2);
      expect(realCap).toBeLessThanOrEqual(500);
    });

    it('takes the MOST RECENT cap reports and returns them oldest-first', async () => {
      const ids = [];
      for (let n = 1; n <= 5; n += 1) {
        // eslint-disable-next-line no-await-in-loop
        ids.push(await seedReport(user.id, { chronoDate: day(n) }));
      }

      const history = await historyService.assembleHistory({ user });
      // Days 3, 4, 5 - the newest three. Dropping the oldest keeps the series a
      // trend is actually read off; dropping the newest would answer a question
      // about the patient's past while claiming to describe their present.
      expect(history.snapshots.map((s) => s.report_id)).toEqual([ids[2], ids[3], ids[4]]);
      expect(history.includedCount).toBe(3);
      expect(history.truncated).toBe(true);
      expect(history.cap).toBe(3);
    });

    it('exactly `cap` eligible reports is NOT truncated', async () => {
      for (let n = 1; n <= 3; n += 1) {
        // eslint-disable-next-line no-await-in-loop
        await seedReport(user.id, { chronoDate: day(n) });
      }
      const history = await historyService.assembleHistory({ user });
      expect(history.includedCount).toBe(3);
      // The failure mode of inferring truncation from `rows.length === cap`.
      expect(history.truncated).toBe(false);
    });

    it('`cap + 1` eligible reports IS truncated - the boundary, proven not guessed', async () => {
      for (let n = 1; n <= 4; n += 1) {
        // eslint-disable-next-line no-await-in-loop
        await seedReport(user.id, { chronoDate: day(n) });
      }
      const history = await historyService.assembleHistory({ user });
      expect(history.includedCount).toBe(3);
      expect(history.truncated).toBe(true);
      // The extra probe row is discarded, never sent.
      expect(history.snapshots).toHaveLength(3);
    });

    it('many INELIGIBLE reports do not make a short history look truncated', async () => {
      await seedReport(user.id, { chronoDate: day(1) });
      for (let n = 0; n < 10; n += 1) {
        // eslint-disable-next-line no-await-in-loop
        await seedReport(user.id, { analysed: false, validated: false });
      }
      const history = await historyService.assembleHistory({ user });
      expect(history.includedCount).toBe(1);
      // `truncated` means "the CAP dropped an eligible report", not "this
      // patient has reports that did not qualify". The second fact is
      // `excludedCount`'s job.
      expect(history.truncated).toBe(false);
      expect(history.totalReports).toBe(11);
    });
  });

  // ============================================================== ownership ===
  describe('ownership', () => {
    it('never returns another patient\'s report', async () => {
      const alice = await makeUser();
      const bob = await makeUser();
      const aliceReport = await seedReport(alice.id, { chronoDate: day(1) });
      await seedReport(bob.id, { chronoDate: day(2) });

      const bobHistory = await historyService.assembleHistory({ user: bob });
      expect(bobHistory.snapshots.map((s) => s.report_id)).not.toContain(aliceReport);
      expect(bobHistory.totalReports).toBe(1);

      const bobExcluded = await historyService.describeExcluded({ user: bob });
      expect(bobExcluded.count).toBe(0);
    });

    it.each([
      ['an admin', ROLES.ADMIN],
      ['a clinician', ROLES.CLINICIAN],
    ])('%s sees an EMPTY history, not the whole collection', async (_label, role) => {
      const patient = await makeUser();
      await seedReport(patient.id, { chronoDate: day(1) });
      await seedReport(patient.id, { chronoDate: day(2) });

      const staff = await makeUser(role);
      const history = await historyService.assembleHistory({ user: staff });
      // No `allowRoles` grant is passed anywhere in this module. A widened
      // filter here would leak a patient's entire library, not one report.
      expect(history.snapshots).toEqual([]);
      expect(history.totalReports).toBe(0);
      expect((await historyService.describeExcluded({ user: staff })).count).toBe(0);
    });

    it('throws rather than building an unscoped filter for an identity-less caller', async () => {
      const patient = await makeUser();
      await seedReport(patient.id, { chronoDate: day(1) });

      // `{}` as a filter would match every report in the collection. The
      // guarantee is that this is impossible to reach, not that no caller does
      // it today.
      await expect(historyService.assembleHistory({ user: {} })).rejects.toThrow();
      await expect(historyService.assembleHistory({ user: null })).rejects.toThrow();
      await expect(historyService.assembleHistory({ user: undefined })).rejects.toThrow();
      await expect(
        historyService.describeExcluded({ user: { role: ROLES.ADMIN } })
      ).rejects.toThrow();
    });
  });

  // ================================================== an explicitly named pair =
  //
  // "The id appears in a filter" is not the same guarantee as "the caller may
  // read this report". Being able to NAME a report is not permission to read
  // it, and here the difference is a whole patient's data.
  describe('resolveNamedPair', () => {
    let alice;
    let bob;
    let aliceIds;

    beforeEach(async () => {
      alice = await makeUser();
      bob = await makeUser();
      aliceIds = [
        await seedReport(alice.id, { chronoDate: day(1) }),
        await seedReport(alice.id, { chronoDate: day(2) }),
      ];
    });

    const idsOf = async (user) =>
      new Set((await historyService.assembleHistory({ user })).snapshots.map((s) => s.report_id));

    it('returns null when neither id is named', async () => {
      const pair = await historyService.resolveNamedPair({
        user: alice,
        baseline: undefined,
        comparison: undefined,
        snapshotIds: await idsOf(alice),
      });
      expect(pair).toBeNull();
    });

    it('resolves the owner\'s own analysed pair', async () => {
      const pair = await historyService.resolveNamedPair({
        user: alice,
        baseline: aliceIds[0],
        comparison: aliceIds[1],
        snapshotIds: await idsOf(alice),
      });
      expect(pair).toEqual({ baselineRef: aliceIds[0], comparisonRef: aliceIds[1] });
    });

    it('404s another patient\'s report id, exactly as a random id does', async () => {
      const bobId = await seedReport(bob.id, { chronoDate: day(3) });
      const bobSnapshots = await idsOf(bob);

      const named = await historyService
        .resolveNamedPair({
          user: bob,
          baseline: aliceIds[0],
          comparison: bobId,
          snapshotIds: bobSnapshots,
        })
        .catch((err) => err);

      const random = await historyService
        .resolveNamedPair({
          user: bob,
          baseline: '0123456789abcdef01234567',
          comparison: bobId,
          snapshotIds: bobSnapshots,
        })
        .catch((err) => err);

      expect(named.statusCode).toBe(404);
      // The two are indistinguishable: a non-owner cannot use this parameter to
      // probe whether a report exists.
      expect(named.statusCode).toBe(random.statusCode);
      expect(named.code).toBe(random.code);
      expect(named.message).toBe(random.message);
      // And the submitted id is never echoed back.
      expect(named.message).not.toContain(aliceIds[0]);
    });

    it.each([
      ['an admin', ROLES.ADMIN],
      ['a clinician', ROLES.CLINICIAN],
    ])('%s naming a patient\'s report gets the same 404', async (_label, role) => {
      const staff = await makeUser(role);
      const err = await historyService
        .resolveNamedPair({
          user: staff,
          baseline: aliceIds[0],
          comparison: aliceIds[1],
          snapshotIds: new Set(),
        })
        .catch((e) => e);
      expect(err.statusCode).toBe(404);
      expect(err.message).not.toContain(aliceIds[0]);
    });

    it('422 REPORT_NOT_IN_HISTORY for the owner\'s own UNANALYSED report', async () => {
      const unanalysed = await seedReport(alice.id, {
        analysed: false,
        validated: false,
        status: 'uploaded',
      });

      const err = await historyService
        .resolveNamedPair({
          user: alice,
          baseline: unanalysed,
          comparison: aliceIds[1],
          snapshotIds: await idsOf(alice),
        })
        .catch((e) => e);

      // NOT a 404. The report demonstrably exists and belongs to the caller;
      // answering 404 would tell an owner their own report does not exist.
      expect(err.statusCode).toBe(422);
      expect(err.code).toBe('REPORT_NOT_IN_HISTORY');
      expect(err.message).not.toContain(unanalysed);
    });

    it('422s exactly one of the two ids, without querying `_id: undefined`', async () => {
      // The validator enforces both-or-neither; this is the authorisation half,
      // which a validator cannot do. If only one arrived anyway, the loop would
      // query `_id: undefined`.
      for (const args of [
        { baseline: aliceIds[0], comparison: undefined },
        { baseline: undefined, comparison: aliceIds[1] },
      ]) {
        // eslint-disable-next-line no-await-in-loop
        const err = await historyService
          .resolveNamedPair({ user: alice, ...args, snapshotIds: await idsOf(alice) })
          .catch((e) => e);
        expect(err.statusCode).toBe(422);
        expect(err.code).toBe('VALIDATION_ERROR');
      }
    });
  });

  // =========================================================== PHI / payloads =
  // ================================================= the printed intervals ==
  //
  // `loadPrintedParameters` carries the laboratory's own reference interval
  // forward to the one page that needs it. It is a SEPARATE query on purpose,
  // so the three tests that matter are: it is scoped like everything else
  // here, it stays narrow, and its absence degrades to no scale rather than a
  // wrong one.
  describe('loadPrintedParameters', () => {
    /** A report carrying an extraction with printed ranges. */
    async function seedExtracted(userId, parameters, extra = {}) {
      const doc = await Report.create({
        user: userId,
        originalName: 'labs.pdf',
        storageKey: `${userId}/${new mongoose.Types.ObjectId().toString()}.pdf`,
        storageDriver: 'local',
        mimeType: 'application/pdf',
        sizeBytes: 1024,
        checksumSha256: 'c'.repeat(64),
        status: 'processed',
        analysis: { version: 1 },
        featureValidation: validatedFeatureSet(),
        extraction: { extracted_parameters: parameters, ...extra },
      });
      return doc._id.toString();
    }

    it('returns each report keyed by the name AS PRINTED on that report', async () => {
      const user = await makeUser();
      const a = await seedExtracted(user.id, [
        { test_name: 'Lymphocytes', value_raw: '15', reference_low: 22, reference_high: 45 },
      ]);
      const b = await seedExtracted(user.id, [
        { test_name: 'LYMPHOCYTES', value_raw: '14', reference_low: 20, reference_high: 40 },
      ]);

      const printed = await historyService.loadPrintedParameters({
        user,
        reportIds: [a, b],
      });

      // Two spellings, each found in its OWN report. That is what lets one
      // series carry both without this function deciding they are the same.
      expect(printed.get(a).get('Lymphocytes').reference_high).toBe(45);
      expect(printed.get(b).get('LYMPHOCYTES').reference_high).toBe(40);
      expect(printed.get(a).has('LYMPHOCYTES')).toBe(false);
    });

    it('will not read another patient\'s report, even when handed its id', async () => {
      // Being able to NAME a report is not permission to read it. These ids
      // normally come from the caller's own history, which is a reason to
      // keep this check rather than to drop it.
      const owner = await makeUser();
      const stranger = await makeUser();
      const theirs = await seedExtracted(owner.id, [
        { test_name: 'Zorblex', value_raw: '1', reference_low: 0, reference_high: 9 },
      ]);

      const printed = await historyService.loadPrintedParameters({
        user: stranger,
        reportIds: [theirs],
      });
      expect(printed.size).toBe(0);
    });

    it('grants a clinician no reach either, matching every other route here', async () => {
      const owner = await makeUser();
      const clinician = await makeUser(ROLES.CLINICIAN);
      const theirs = await seedExtracted(owner.id, [
        { test_name: 'Zorblex', value_raw: '1', reference_low: 0, reference_high: 9 },
      ]);

      const printed = await historyService.loadPrintedParameters({
        user: clinician,
        reportIds: [theirs],
      });
      expect(printed.size).toBe(0);
    });

    it('reads the four range fields and NOT the rest of the extraction', async () => {
      // The narrowness `HISTORY_PROJECTION` argues for, held one function
      // down. `extraction` is a large payload and this takes four fields out
      // of one array.
      const user = await makeUser();
      const id = await seedExtracted(
        user.id,
        [
          {
            test_name: 'Zorblex',
            value_raw: 'CANARY-VALUE',
            unit: 'CANARY-UNIT',
            flag: 'high',
            reference_low: 0,
            reference_high: 9,
            reference_range_raw: '0 - 9',
          },
        ],
        { raw_text: 'CANARY-RAW-TEXT', report_metadata: { note: 'CANARY-META' } }
      );

      const printed = await historyService.loadPrintedParameters({ user, reportIds: [id] });
      const serialised = JSON.stringify([...printed.get(id).values()]);

      for (const canary of ['CANARY-RAW-TEXT', 'CANARY-META', 'CANARY-VALUE', 'CANARY-UNIT']) {
        expect(serialised).not.toContain(canary);
      }
      expect(printed.get(id).get('Zorblex')).toEqual(
        expect.objectContaining({ reference_low: 0, reference_high: 9, reference_range_raw: '0 - 9' })
      );
    });

    it('answers with an empty map, never a throw, when there is nothing to load', async () => {
      const user = await makeUser();
      for (const reportIds of [undefined, null, [], [null, undefined]]) {
        // eslint-disable-next-line no-await-in-loop
        const printed = await historyService.loadPrintedParameters({ user, reportIds });
        expect(printed.size).toBe(0);
      }
    });

    it('omits a report that stored no extraction rather than inventing an entry', async () => {
      const user = await makeUser();
      const id = await seedReport(user.id, { chronoDate: day(1) });

      const printed = await historyService.loadPrintedParameters({ user, reportIds: [id] });
      // Present with nothing in it, not absent: the report WAS read and had
      // no parameters, which is a different fact from not being readable.
      expect(printed.get(id).size).toBe(0);
    });

    it('keeps the FIRST of two rows printing the same name, as the dashboard does', async () => {
      // Two screens disagreeing about one test's range would be worse than
      // either choice; this matches `buildUnanalysedSection`'s own join.
      const user = await makeUser();
      const id = await seedExtracted(user.id, [
        { test_name: 'Zorblex', value_raw: '1', reference_low: 0, reference_high: 9 },
        { test_name: 'Zorblex', value_raw: '2', reference_low: 1, reference_high: 8 },
      ]);

      const printed = await historyService.loadPrintedParameters({ user, reportIds: [id] });
      expect(printed.get(id).get('Zorblex').reference_low).toBe(0);
    });
  });

  describe('what it reads and what it does not', () => {
    it('reads no payload but `featureValidation`', async () => {
      const user = await makeUser();
      const doc = await Report.create({
        user: user.id,
        originalName: 'labs.pdf',
        storageKey: `${user.id}/x.pdf`,
        storageDriver: 'local',
        mimeType: 'application/pdf',
        sizeBytes: 512,
        checksumSha256: 'd'.repeat(64),
        status: 'processed',
        analysis: { version: 1 },
        featureValidation: validatedFeatureSet(),
        extraction: { raw_text: 'CANARY-EXTRACTION' },
        features: { note: 'CANARY-FEATURES' },
        clinicalReport: { note: 'CANARY-REPORT' },
        patientExplanation: { note: 'CANARY-EXPLANATION' },
        lifestyleGuidance: { note: 'CANARY-GUIDANCE' },
      });
      expect(doc._id).toBeDefined();

      const history = await historyService.assembleHistory({ user });
      const serialised = JSON.stringify(history);
      for (const canary of [
        'CANARY-EXTRACTION',
        'CANARY-FEATURES',
        'CANARY-REPORT',
        'CANARY-EXPLANATION',
        'CANARY-GUIDANCE',
      ]) {
        expect(serialised).not.toContain(canary);
      }
      expect(history.snapshots[0].validated.valid.hba1c.value).toBe(6.4);
    });

    it('describeExcluded reads no feature payload at all', async () => {
      const user = await makeUser();
      await Report.create({
        user: user.id,
        originalName: 'labs.pdf',
        storageKey: `${user.id}/y.pdf`,
        storageDriver: 'local',
        mimeType: 'application/pdf',
        sizeBytes: 512,
        checksumSha256: 'e'.repeat(64),
        status: 'uploaded',
        analysis: { version: 0 },
        extraction: { raw_text: 'CANARY-EXCLUDED-EXTRACTION' },
      });

      const excluded = await historyService.describeExcluded({ user });
      expect(excluded.count).toBe(1);
      expect(JSON.stringify(excluded)).not.toContain('CANARY-EXCLUDED-EXTRACTION');
      expect(excluded.reports[0]).toEqual(
        expect.objectContaining({ reasonCode: 'NOT_ANALYSED', status: 'uploaded' })
      );
    });

    it('summariseHistory reports absence as `undefined`, never as zero', () => {
      // Section 6n D6: a documented-but-absent `excluded[]` key means a caller
      // trusting it reads `undefined` and renders "nothing was excluded".
      // Both keys must exist when the caller supplied the second query...
      const history = {
        totalReports: 4,
        includedCount: 1,
        window: null,
        cap: 50,
        truncated: false,
        included: [],
      };
      const withExcluded = historyService.summariseHistory(history, {
        count: 3,
        reports: [{ reportId: 'x', reasonCode: 'NOT_ANALYSED' }],
      });
      expect(withExcluded.excludedCount).toBe(3);
      expect(withExcluded.excluded).toHaveLength(1);

      // ...and be honestly absent when it did not, rather than reading as
      // "nothing was excluded".
      const without = historyService.summariseHistory(history, undefined);
      expect(without.excludedCount).toBeUndefined();
      expect(without.excludedCount).not.toBe(0);
      expect(without.excluded).toBeUndefined();
      expect(without.excluded).not.toEqual([]);
    });
  });

  // ============================================= the date ON the report ==
  //
  // `chronoDate` is `reportDate ?? uploadedAt` and is NEVER absent, so a
  // consumer holding only that cannot tell a date somebody read off their
  // document from the clock at upload time. Both arrive as a Date.
  //
  // FOUND ON THE REAL PAGE, 2026-09-19: a report printed 13 September,
  // uploaded on the 19th with the optional field blank, was labelled
  // `9/19/2026 - Test 3.pdf` in the comparison picker. The upload clock was
  // being presented as the date on the document.

  describe('reportDate travels beside chronoDate', () => {
    let user;
    beforeEach(async () => {
      user = await makeUser();
    });

    it('carries the printed date when one was given', async () => {
      const printed = day(4);
      await seedReport(user.id, { chronoDate: printed });
      const history = await historyService.assembleHistory({ user });

      expect(history.included[0].reportDate).toEqual(printed);
      expect(history.included[0].chronoDate).toEqual(printed);
    });

    it('carries NULL when none was given, while chronoDate still sorts', async () => {
      // THE CASE THE PAGE GOT WRONG. `seedReport` maps its `chronoDate`
      // argument onto the schema's `reportDate`, so omitting it is exactly a
      // person leaving the optional field blank.
      await seedReport(user.id, {});
      const history = await historyService.assembleHistory({ user });
      const entry = history.included[0];

      expect(entry.reportDate).toBeNull();
      // The sort key is still a real date -- the upload time -- because
      // ordering must keep working. That is the whole reason the two fields
      // are different, and why printing one as the other was wrong.
      expect(entry.chronoDate).toBeInstanceOf(Date);
      expect(Number.isNaN(entry.chronoDate.getTime())).toBe(false);
    });

    it('does not change the ORDER, only what can be said about it', async () => {
      const older = await seedReport(user.id, { chronoDate: day(1) });
      const undated = await seedReport(user.id, {}); // sorts on upload time
      const history = await historyService.assembleHistory({ user });

      // Oldest first, and the undated one sorts by when it arrived -- today,
      // which is after January.
      expect(history.snapshots.map((s) => s.report_id)).toEqual([older, undated]);
      expect(history.included.map((e) => e.reportDate === null)).toEqual([false, true]);
    });
  });
});
