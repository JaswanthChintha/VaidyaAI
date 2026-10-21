'use strict';


const mongoose = require('mongoose');

const mockAxios = { post: jest.fn(), get: jest.fn() };
jest.mock('axios', () => ({
  create: () => ({
    post: (...args) => mockAxios.post(...args),
    get: (...args) => mockAxios.get(...args),
  }),
}));

require('./helpers');
const config = require('../src/config/env');
const Report = require('../src/models/Report');
const User = require('../src/models/User');
const { ROLES } = require('../src/utils/roles');
const historyService = require('../src/services/historyService');


let userSeq = 0;

async function makeUser(role = ROLES.PATIENT) {
  userSeq += 1;
  const user = await User.create({
    name: 'History User',
    email: `history.${userSeq}@example.com`,
    password: 'Str0ng!Passw0rd',
    role,
  });
  return { id: user._id.toString(), _id: user._id, role };
}

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

    it("EXCLUDES someone else's report as SOMEONE_ELSE (2026-10-03)", async () => {
      const own = await seedReport(user.id, { chronoDate: day(1) });
      const theirs = await seedReport(user.id, { chronoDate: day(2) });
      await Report.updateOne({ _id: theirs }, { $set: { 'subject.owner': 'other' } });

      const history = await historyService.assembleHistory({ user });
      expect(history.snapshots.map((s) => s.report_id)).toEqual([own]);

      const excluded = await historyService.describeExcluded({ user });
      expect(excluded.count).toBe(1);
      expect(excluded.reports[0]).toMatchObject({
        reportId: theirs,
        reasonCode: historyService.EXCLUSION_REASONS.SOMEONE_ELSE,
      });
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
      const id = await seedReport(user.id, { status: 'partial', chronoDate: day(1) });
      const history = await historyService.assembleHistory({ user });
      expect(history.snapshots.map((s) => s.report_id)).toEqual([id]);
      expect(history.included[0].status).toBe('partial');
    });

    it('EXCLUDES a `partial` report when validation itself was the failed stage', async () => {
      await seedReport(user.id, { status: 'partial', validated: false });
      const history = await historyService.assembleHistory({ user });
      expect(history.snapshots).toEqual([]);

      const excluded = await historyService.describeExcluded({ user });
      expect(excluded.reports[0].reasonCode).toBe(
        historyService.EXCLUSION_REASONS.NO_VALIDATED_FEATURES
      );
    });

    it('INCLUDES a `failed` report that still holds a real Module 6 verdict', async () => {
      const id = await seedReport(user.id, { status: 'failed', chronoDate: day(1) });
      const history = await historyService.assembleHistory({ user });
      expect(history.snapshots.map((s) => s.report_id)).toEqual([id]);
      expect(history.included[0].status).toBe('failed');
    });

    it('INCLUDES a report whose every reading was rejected', async () => {
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
      expect(history.snapshots[0].validated.rejected.hba1c.rejection_code).toBe(
        'IMPLAUSIBLE_VALUE'
      );
      expect(doc.status).toBe('processed');
    });

    it('`considered = included + excludedCount` holds across a mixed library', async () => {
      await seedReport(user.id, { chronoDate: day(1) });
      await seedReport(user.id, { status: 'partial', chronoDate: day(2) });
      await seedReport(user.id, { status: 'failed', chronoDate: day(3) });
      await seedReport(user.id, { analysed: false, validated: false });
      await seedReport(user.id, { validated: false });

      const history = await historyService.assembleHistory({ user });
      const excluded = await historyService.describeExcluded({ user });
      const summary = historyService.summariseHistory(history, excluded);

      expect(summary.included).toBe(3);
      expect(summary.excludedCount).toBe(2);
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
      const realCap = config.history.maxReports;
      config.history.maxReports = 3;
      try {
        for (let i = 1; i <= 5; i += 1) {
          await seedReport(user.id, { chronoDate: day(i) });
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
        expect(summary.droppedByCap).toBe(2);
        expect(summary.considered).toBe(
          summary.included + summary.excludedCount + summary.droppedByCap
        );
      } finally {
        config.history.maxReports = realCap;
      }
    });

    it('the three exclusion codes are the only ones, and they are ours', () => {
      expect(Object.values(historyService.EXCLUSION_REASONS)).toEqual([
        'NOT_ANALYSED',
        'NO_VALIDATED_FEATURES',
        'SOMEONE_ELSE',
      ]);
    });
  });

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
      expect(history.snapshots).toEqual([]);
      expect(history.truncated).toBe(false);
    });
  });

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
        ids.push(await seedReport(user.id, { chronoDate: day(n) }));
      }

      const history = await historyService.assembleHistory({ user });
      expect(history.snapshots.map((s) => s.report_id)).toEqual([ids[2], ids[3], ids[4]]);
      expect(history.includedCount).toBe(3);
      expect(history.truncated).toBe(true);
      expect(history.cap).toBe(3);
    });

    it('exactly `cap` eligible reports is NOT truncated', async () => {
      for (let n = 1; n <= 3; n += 1) {
        await seedReport(user.id, { chronoDate: day(n) });
      }
      const history = await historyService.assembleHistory({ user });
      expect(history.includedCount).toBe(3);
      expect(history.truncated).toBe(false);
    });

    it('`cap + 1` eligible reports IS truncated - the boundary, proven not guessed', async () => {
      for (let n = 1; n <= 4; n += 1) {
        await seedReport(user.id, { chronoDate: day(n) });
      }
      const history = await historyService.assembleHistory({ user });
      expect(history.includedCount).toBe(3);
      expect(history.truncated).toBe(true);
      expect(history.snapshots).toHaveLength(3);
    });

    it('many INELIGIBLE reports do not make a short history look truncated', async () => {
      await seedReport(user.id, { chronoDate: day(1) });
      for (let n = 0; n < 10; n += 1) {
        await seedReport(user.id, { analysed: false, validated: false });
      }
      const history = await historyService.assembleHistory({ user });
      expect(history.includedCount).toBe(1);
      expect(history.truncated).toBe(false);
      expect(history.totalReports).toBe(11);
    });
  });

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
      expect(history.snapshots).toEqual([]);
      expect(history.totalReports).toBe(0);
      expect((await historyService.describeExcluded({ user: staff })).count).toBe(0);
    });

    it('throws rather than building an unscoped filter for an identity-less caller', async () => {
      const patient = await makeUser();
      await seedReport(patient.id, { chronoDate: day(1) });

      await expect(historyService.assembleHistory({ user: {} })).rejects.toThrow();
      await expect(historyService.assembleHistory({ user: null })).rejects.toThrow();
      await expect(historyService.assembleHistory({ user: undefined })).rejects.toThrow();
      await expect(
        historyService.describeExcluded({ user: { role: ROLES.ADMIN } })
      ).rejects.toThrow();
    });
  });

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
      expect(named.statusCode).toBe(random.statusCode);
      expect(named.code).toBe(random.code);
      expect(named.message).toBe(random.message);
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

      expect(err.statusCode).toBe(422);
      expect(err.code).toBe('REPORT_NOT_IN_HISTORY');
      expect(err.message).not.toContain(unanalysed);
    });

    it('422s exactly one of the two ids, without querying `_id: undefined`', async () => {
      for (const args of [
        { baseline: aliceIds[0], comparison: undefined },
        { baseline: undefined, comparison: aliceIds[1] },
      ]) {
        const err = await historyService
          .resolveNamedPair({ user: alice, ...args, snapshotIds: await idsOf(alice) })
          .catch((e) => e);
        expect(err.statusCode).toBe(422);
        expect(err.code).toBe('VALIDATION_ERROR');
      }
    });
  });

  describe('loadPrintedParameters', () => {
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

      expect(printed.get(a).get('Lymphocytes').reference_high).toBe(45);
      expect(printed.get(b).get('LYMPHOCYTES').reference_high).toBe(40);
      expect(printed.get(a).has('LYMPHOCYTES')).toBe(false);
    });

    it('will not read another patient\'s report, even when handed its id', async () => {
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
        const printed = await historyService.loadPrintedParameters({ user, reportIds });
        expect(printed.size).toBe(0);
      }
    });

    it('omits a report that stored no extraction rather than inventing an entry', async () => {
      const user = await makeUser();
      const id = await seedReport(user.id, { chronoDate: day(1) });

      const printed = await historyService.loadPrintedParameters({ user, reportIds: [id] });
      expect(printed.get(id).size).toBe(0);
    });

    it('keeps the FIRST of two rows printing the same name, as the dashboard does', async () => {
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

      const without = historyService.summariseHistory(history, undefined);
      expect(without.excludedCount).toBeUndefined();
      expect(without.excludedCount).not.toBe(0);
      expect(without.excluded).toBeUndefined();
      expect(without.excluded).not.toEqual([]);
    });
  });


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
      await seedReport(user.id, {});
      const history = await historyService.assembleHistory({ user });
      const entry = history.included[0];

      expect(entry.reportDate).toBeNull();
      expect(entry.chronoDate).toBeInstanceOf(Date);
      expect(Number.isNaN(entry.chronoDate.getTime())).toBe(false);
    });

    it('does not change the ORDER, only what can be said about it', async () => {
      const older = await seedReport(user.id, { chronoDate: day(1) });
      const undated = await seedReport(user.id, {});
      const history = await historyService.assembleHistory({ user });

      expect(history.snapshots.map((s) => s.report_id)).toEqual([older, undated]);
      expect(history.included.map((e) => e.reportDate === null)).toEqual([false, true]);
    });
  });
});
