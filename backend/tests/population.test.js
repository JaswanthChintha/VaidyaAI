'use strict';


const mongoose = require('mongoose');

const mockAxios = { post: jest.fn(), get: jest.fn() };
jest.mock('axios', () => ({
  create: () => ({
    post: (...args) => mockAxios.post(...args),
    get: (...args) => mockAxios.get(...args),
  }),
}));

const { app, request, registerUser } = require('./helpers');
const config = require('../src/config/env');
const Report = require('../src/models/Report');
const Profile = require('../src/models/Profile');

const REPORTS = `${config.apiPrefix}/reports`;
const auth = (token) => ({ Authorization: `Bearer ${token}` });
const okResponse = (data) => ({ status: 200, data: { success: true, data } });

async function makeUser(email) {
  const { res } = await registerUser({ email, name: 'Test User' });
  expect(res.status).toBe(201);
  return { token: res.body.data.accessToken, id: res.body.data.user.id };
}

const used = (age, gender, source) => ({
  features: {
    age: { name: 'age', value: age, source },
    gender: { name: 'gender', value: gender, source },
  },
});

async function seed(userId, features) {
  const doc = await Report.create({
    user: userId,
    originalName: 'labs.pdf',
    storageKey: `${userId}/${new mongoose.Types.ObjectId().toString()}.pdf`,
    storageDriver: 'local',
    mimeType: 'application/pdf',
    sizeBytes: 1024,
    checksumSha256: 'a'.repeat(64),
    status: 'processed',
    analysis: { version: 1, runCount: 1 },
    featureValidation: { valid: { hemoglobin: { name: 'hemoglobin', value: 9.2, unit: 'g/dL' } } },
    ...(features ? { features } : {}),
  });
  return doc._id.toString();
}

const sentPayload = () => {
  expect(mockAxios.post).toHaveBeenCalledTimes(1);
  return mockAxios.post.mock.calls[0][1];
};

const getContext = (token, id) =>
  request(app).get(`${REPORTS}/${id}/population-context`).set(auth(token));

beforeEach(() => {
  mockAxios.post.mockReset();
  mockAxios.post.mockResolvedValue(okResponse({ features: {} }));
});

describe('the population cohort uses the sex and age the analysis used', () => {
  it('sends the age and sex printed on the report when the analysis used them', async () => {
    const alice = await makeUser('pop.report@example.com');
    await Profile.create({ user: alice.id, age: 20, gender: 'male' });
    const id = await seed(alice.id, used(63, 'male', 'report_details'));

    const res = await getContext(alice.token, id);
    expect(res.status).toBe(200);
    expect(sentPayload()).toMatchObject({ age: 63, gender: 'male' });
    expect(res.body.data.subject).toMatchObject({
      source: 'report', ageSource: 'report', genderSource: 'report',
      ageProvided: true, genderProvided: true,
    });
  });

  it('a printed sex wins over a different profile sex', async () => {
    const alice = await makeUser('pop.sex@example.com');
    await Profile.create({ user: alice.id, age: 20, gender: 'male' });
    const id = await seed(alice.id, used(34, 'female', 'report_details'));

    await getContext(alice.token, id);
    expect(sentPayload()).toMatchObject({ age: 34, gender: 'female' });
  });

  it('falls back to the profile when the analysis used the profile', async () => {
    const alice = await makeUser('pop.profile@example.com');
    await Profile.create({ user: alice.id, age: 20, gender: 'male' });
    const id = await seed(alice.id, used(20, 'male', 'patient_profile'));

    const res = await getContext(alice.token, id);
    expect(sentPayload()).toMatchObject({ age: 20, gender: 'male' });
    expect(res.body.data.subject).toMatchObject({ source: 'profile', ageSource: 'profile', genderSource: 'profile' });
  });

  it('falls back to the profile for an analysis that stored no features', async () => {
    const alice = await makeUser('pop.old@example.com');
    await Profile.create({ user: alice.id, age: 41, gender: 'female' });
    const id = await seed(alice.id, null);

    await getContext(alice.token, id);
    expect(sentPayload()).toMatchObject({ age: 41, gender: 'female' });
  });

  it('mixes per field: printed age, profile sex', async () => {
    const alice = await makeUser('pop.mixed@example.com');
    await Profile.create({ user: alice.id, age: 20, gender: 'female' });
    const id = await seed(alice.id, {
      features: {
        age: { name: 'age', value: 63, source: 'report_details' },
        gender: { name: 'gender', value: 'female', source: 'patient_profile' },
      },
    });

    const res = await getContext(alice.token, id);
    expect(sentPayload()).toMatchObject({ age: 63, gender: 'female' });
    expect(res.body.data.subject).toMatchObject({ source: 'mixed', ageSource: 'report', genderSource: 'profile' });
  });

  it('never invents a value: no report details and no profile sends neither', async () => {
    const alice = await makeUser('pop.none@example.com');
    const id = await seed(alice.id, null);

    const res = await getContext(alice.token, id);
    const payload = sentPayload();
    expect(payload).not.toHaveProperty('age');
    expect(payload).not.toHaveProperty('gender');
    expect(res.body.data.subject).toMatchObject({
      profileExists: false, ageProvided: false, genderProvided: false, ageSource: null, genderSource: null,
    });
  });

  it('ignores an age or sex supplied in the query string', async () => {
    const alice = await makeUser('pop.query@example.com');
    await Profile.create({ user: alice.id, age: 20, gender: 'male' });
    const id = await seed(alice.id, used(63, 'male', 'report_details'));

    await request(app)
      .get(`${REPORTS}/${id}/population-context?age=5&gender=female`)
      .set(auth(alice.token));
    expect(sentPayload()).toMatchObject({ age: 63, gender: 'male' });
  });
});

describe('notCompared -- the names of the tests that never reach Module 31', () => {
  it('lists each unmapped test name once, in order, and nothing else', async () => {
    const alice = await makeUser('pop.unmapped@example.com');
    await Profile.create({ user: alice.id, age: 20, gender: 'male' });
    const id = await seed(alice.id, {
      unmapped: [
        { test_name: 'ESR', value_raw: '45', unit: 'mm/hr' },
        { test_name: 'C-REACTIVE PROTEIN(CRP)', value_raw: '38.9', unit: 'mg/L' },
        { test_name: ' ESR ', value_raw: '45', unit: 'mm/hr' },
        { test_name: '', value_raw: '1' },
        { value_raw: '2' },
      ],
    });

    const res = await getContext(alice.token, id);
    expect(res.status).toBe(200);
    expect(res.body.data.notCompared).toEqual(['ESR', 'C-REACTIVE PROTEIN(CRP)']);
  });

  it('carries NAMES ONLY -- no value or unit leaves on this endpoint', async () => {
    const alice = await makeUser('pop.unmapped.names@example.com');
    const id = await seed(alice.id, {
      unmapped: [{ test_name: 'TSH', value_raw: '1.81', unit: 'uIU/mL' }],
    });

    const res = await getContext(alice.token, id);
    expect(res.body.data.notCompared).toEqual(['TSH']);
    expect(JSON.stringify(res.body.data.notCompared)).not.toMatch(/1\.81|uIU/);
  });

  it('is an empty list, not absent, when every test was compared', async () => {
    const alice = await makeUser('pop.unmapped.none@example.com');
    const id = await seed(alice.id, null);

    const res = await getContext(alice.token, id);
    expect(res.body.data.notCompared).toEqual([]);
  });
});
