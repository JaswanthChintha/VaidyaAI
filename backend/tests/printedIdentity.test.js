'use strict';

/**
 * The sex and age a report PRINTS -- read, compared, never guessed.
 *
 * 2026-09-24: `01-all-normal.pdf` ("34 Years / Female") and
 * `03-renal-anaemia-deficiency.pdf` ("63 Years / Male") were compared as one
 * person's history, and both were analysed as the profile's "20, male". See
 * `src/utils/printedIdentity.js`.
 */

const mongoose = require('mongoose');

const Report = require('../src/models/Report');
const historyService = require('../src/services/historyService');
const {
  parseSex,
  parseAge,
  readPrintedIdentity,
  comparePair,
  compareWithProfile,
} = require('../src/utils/printedIdentity');

describe('parseSex', () => {
  it.each([
    ['Male', 'male'], ['M', 'male'], ['m.', 'male'], ['MALE', 'male'],
    ['Female', 'female'], ['F', 'female'], ['female ', 'female'],
  ])('%s -> %s', (raw, value) => {
    expect(parseSex(raw)).toEqual({ status: 'read', value });
  });

  it.each([['Other'], ['M/F'], ['7'], ['Transgender']])('%s is not read as either', (raw) => {
    expect(parseSex(raw)).toEqual({ status: 'unreadable', value: null });
  });

  it.each([[null], [undefined], [''], ['  ']])('%p is absent', (raw) => {
    expect(parseSex(raw).status).toBe('absent');
  });
});

describe('parseAge', () => {
  it.each([
    ['63 Years', 63], ['63 Yrs', 63], ['63Y', 63], ['63', 63],
    ['34Y 2M', 34.17], ['6 Months', 0.5], ['10 Days', 0.03], ['1 Year 6 Months', 1.5],
  ])('%s -> %s years', (raw, years) => {
    expect(parseAge(raw)).toEqual({ status: 'read', value: years });
  });

  it.each([['adult'], ['34.5.1'], ['200 Years'], ['DOB 01/01/1990']])('%s is unreadable', (raw) => {
    expect(parseAge(raw).status).toBe('unreadable');
  });

  it('absent when not printed', () => {
    expect(parseAge(null)).toEqual({ status: 'absent', value: null });
  });
});

describe('readPrintedIdentity', () => {
  it('is null -- nobody looked -- for an extraction that predates the fields', () => {
    expect(readPrintedIdentity({ report_metadata: { lab_name: 'X', report_date: 'y' } })).toBeNull();
    expect(readPrintedIdentity(null)).toBeNull();
  });

  it('records "not printed" when the keys are there and null', () => {
    expect(readPrintedIdentity({ report_metadata: { patient_sex: null, patient_age: null } })).toEqual({
      sexStatus: 'absent',
      ageStatus: 'absent',
    });
  });

  it('reads both, and keeps the raw text only when it could not be read', () => {
    expect(
      readPrintedIdentity({ report_metadata: { patient_sex: 'Female', patient_age: 'about thirty' } })
    ).toEqual({ sex: 'female', sexStatus: 'read', ageStatus: 'unreadable', ageRaw: 'about thirty' });
  });

  it('carries no undefined keys, which the driver could store as null', () => {
    const identity = readPrintedIdentity({ report_metadata: { patient_sex: null, patient_age: '63' } });
    expect(Object.values(identity)).not.toContain(undefined);
  });
});

describe('comparePair -- could these be one person?', () => {
  const day = (iso) => new Date(`${iso}T00:00:00Z`);
  const person = (sex, ageYears, date) => ({
    identity: { sex, sexStatus: 'read', ageYears, ageStatus: 'read' },
    date: day(date),
  });

  it('THE CASE ON SCREEN: 63 / male then 34 / female, two days apart', () => {
    const result = comparePair(person('male', 63, '2026-09-09'), person('female', 34, '2026-09-11'));
    expect(result.status).toBe('conflict');
    expect(result.conflicts.map((c) => c.field)).toEqual(['sex', 'age']);
  });

  it('one person, a year and a half older a year and a half later', () => {
    expect(comparePair(person('male', 40, '2024-01-01'), person('male', 41, '2025-07-01')).status).toBe(
      'consistent'
    );
  });

  it('whole-year printing is tolerated, a decade is not', () => {
    expect(comparePair(person('male', 40, '2025-01-01'), person('male', 42, '2025-06-01')).status).toBe(
      'consistent'
    );
    expect(comparePair(person('male', 40, '2025-01-01'), person('male', 50, '2025-06-01')).status).toBe(
      'conflict'
    );
  });

  it('is "incomplete", never "consistent", when one report prints no sex', () => {
    const noSex = { identity: { sexStatus: 'absent', ageYears: 40, ageStatus: 'read' }, date: day('2025-01-01') };
    expect(comparePair(noSex, person('male', 40, '2025-02-01')).status).toBe('incomplete');
  });

  it('is "not_checked" when either report predates the fields, and says which', () => {
    const result = comparePair({ identity: null, date: day('2025-01-01') }, person('male', 40, '2025-02-01'));
    expect(result).toEqual({ status: 'not_checked', conflicts: [], notChecked: ['baseline'] });
  });
});

describe('compareWithProfile', () => {
  const features = (age, gender, source = 'patient_profile') => ({
    features: {
      age: { value: age, source },
      gender: { value: gender, source },
    },
  });

  it('carries the printed age forward to when the analysis ran', () => {
    const result = compareWithProfile({
      identity: { sex: 'male', sexStatus: 'read', ageYears: 30, ageStatus: 'read' },
      features: features(35, 'male'),
      reportDate: new Date('2021-01-01T00:00:00Z'),
      analysedAt: new Date('2026-01-01T00:00:00Z'),
    });
    expect(result.status).toBe('consistent');
  });

  it('ignores a value that did not come from the profile', () => {
    const result = compareWithProfile({
      identity: { sex: 'female', sexStatus: 'read', ageYears: 34, ageStatus: 'read' },
      features: features(34, 'male', 'report'),
      reportDate: new Date(),
      analysedAt: new Date(),
    });
    expect(result.conflicts).toEqual([]);
    expect(result.status).toBe('incomplete');
  });

  it('does not compare sex against "other" or "prefer not to say"', () => {
    const result = compareWithProfile({
      identity: { sex: 'female', sexStatus: 'read', ageStatus: 'absent' },
      features: features(null, 'prefer_not_to_say'),
      reportDate: new Date(),
      analysedAt: new Date(),
    });
    expect(result.conflicts).toEqual([]);
  });
});

describe('historyService.checkPairIdentity -- owner-scoped', () => {
  async function seed(user, printedIdentity, reportDate) {
    const doc = await Report.create({
      user,
      originalName: 'labs.pdf',
      storageKey: `k/${new mongoose.Types.ObjectId()}.pdf`,
      storageDriver: 'local',
      mimeType: 'application/pdf',
      sizeBytes: 10,
      checksumSha256: 'c'.repeat(64),
      reportDate: new Date(reportDate),
      printedIdentity,
    });
    return String(doc._id);
  }
  const owner = () => {
    const id = new mongoose.Types.ObjectId();
    return { id: String(id), _id: id, role: 'patient' };
  };

  it('finds the conflict between the owner\'s two reports', async () => {
    const alice = owner();
    const a = await seed(alice._id, { sex: 'male', sexStatus: 'read', ageYears: 63, ageStatus: 'read' }, '2026-09-09');
    const b = await seed(alice._id, { sex: 'female', sexStatus: 'read', ageYears: 34, ageStatus: 'read' }, '2026-09-11');
    const result = await historyService.checkPairIdentity({ user: alice, baselineId: a, comparisonId: b });
    expect(result.status).toBe('conflict');
  });

  it('reads nothing of another patient\'s report -- it is "not checked", not compared', async () => {
    const alice = owner();
    const bob = owner();
    const a = await seed(alice._id, { sex: 'male', sexStatus: 'read', ageYears: 63, ageStatus: 'read' }, '2026-09-09');
    const b = await seed(bob._id, { sex: 'female', sexStatus: 'read', ageYears: 34, ageStatus: 'read' }, '2026-09-11');
    const result = await historyService.checkPairIdentity({ user: alice, baselineId: a, comparisonId: b });
    expect(result).toEqual({ status: 'not_checked', conflicts: [], notChecked: ['comparison'] });
  });
});
