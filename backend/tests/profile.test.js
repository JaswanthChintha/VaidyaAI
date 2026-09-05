'use strict';

const { app, request, registerUser, createUserWithRole, login } = require('./helpers');
const config = require('../src/config/env');
const Profile = require('../src/models/Profile');
const { ROLES } = require('../src/utils/roles');

const PROFILE = `${config.apiPrefix}/profile/me`;

const PASSWORD = 'Str0ng!Passw0rd';

/** Register a fresh user and return their access token + id. */
async function makeUser(email) {
  const { res } = await registerUser({ email, name: 'Test User' });
  expect(res.status).toBe(201);
  return { token: res.body.data.accessToken, id: res.body.data.user.id, email };
}

/** Create a user with a privileged role and log in as them. */
async function makePrivilegedUser(role, email) {
  const user = await createUserWithRole(role, { email, password: PASSWORD });
  const res = await login(email, PASSWORD);
  expect(res.status).toBe(200);
  return { token: res.body.data.accessToken, id: user._id.toString(), email };
}

const auth = (token) => ({ Authorization: `Bearer ${token}` });

const send = (method, token, body) => {
  const req = request(app)[method](PROFILE);
  if (token) req.set(auth(token));
  return body === undefined ? req : req.send(body);
};

const FULL_PROFILE = {
  age: 41,
  gender: 'female',
  heightCm: 165,
  weightKg: 68,
  hypertension: true,
  heartDisease: false,
  heartDiseaseDetails: ['No cardiac events on record'],
  smokingHistory: 'former',
  allergies: ['Penicillin', 'Peanuts'],
  medicalConditions: ['Type 2 diabetes'],
  medications: ['Metformin 500mg'],
  previousHealthInformation: ['Gestational diabetes in 2014'],
};

describe('Module 2 - Patient Profile Management', () => {
  // ---------------------------------------------------------------- CRUD ----
  describe('CRUD on the caller\'s own profile', () => {
    let user;
    beforeEach(async () => {
      user = await makeUser('owner@example.com');
    });

    it('returns 404 when no profile exists yet', async () => {
      const res = await send('get', user.token);
      expect(res.status).toBe(404);
      expect(res.body.success).toBe(false);
      expect(res.body.error.code).toBe('NOT_FOUND');
    });

    it('creates a profile with POST and returns 201', async () => {
      const res = await send('post', user.token, FULL_PROFILE);

      expect(res.status).toBe(201);
      expect(res.body.success).toBe(true);
      expect(res.body.data.profile).toMatchObject({
        age: 41,
        gender: 'female',
        heightCm: 165,
        weightKg: 68,
        hypertension: true,
        heartDisease: false,
        smokingHistory: 'former',
      });
      expect(res.body.data.profile.user).toBe(user.id);
      expect(res.body.data.profile.allergies).toEqual(['Penicillin', 'Peanuts']);
    });

    it('reads the profile back with GET', async () => {
      await send('post', user.token, FULL_PROFILE);
      const res = await send('get', user.token);

      expect(res.status).toBe(200);
      expect(res.body.data.profile.medications).toEqual(['Metformin 500mg']);
      expect(res.body.data.profile.completeness.percent).toBe(100);
    });

    it('rejects a second POST with 409', async () => {
      await send('post', user.token, FULL_PROFILE);
      const res = await send('post', user.token, FULL_PROFILE);

      expect(res.status).toBe(409);
      expect(res.body.error.code).toBe('CONFLICT');
      expect(await Profile.countDocuments({ user: user.id })).toBe(1);
    });

    it('survives a concurrent duplicate-create race with exactly one profile', async () => {
      // The pre-check in the controller cannot win a race on its own: all five
      // requests can pass it before any of them writes. The unique index on
      // `user` is what actually holds, and the existing 11000 handler turns the
      // losers into a 409 rather than a 500. Make sure the index is built
      // before firing, otherwise this asserts nothing.
      await Profile.init();

      const responses = await Promise.all(
        Array.from({ length: 5 }, () => send('post', user.token, { age: 30 }))
      );

      const statuses = responses.map((r) => r.status).sort();
      expect(statuses).toEqual([201, 409, 409, 409, 409]);
      expect(await Profile.countDocuments({ user: user.id })).toBe(1);

      for (const res of responses.filter((r) => r.status === 409)) {
        expect(res.body.success).toBe(false);
        expect(res.body.error.code).toBe('CONFLICT');
      }
    });

    it('PUT creates when absent (201) and replaces when present (200)', async () => {
      const created = await send('put', user.token, { age: 30, heightCm: 170 });
      expect(created.status).toBe(201);

      const replaced = await send('put', user.token, { age: 31 });
      expect(replaced.status).toBe(200);
      expect(replaced.body.data.profile.age).toBe(31);
      // Replace semantics: omitted fields are cleared.
      expect(replaced.body.data.profile.heightCm).toBeUndefined();
      expect(await Profile.countDocuments({ user: user.id })).toBe(1);
    });

    it('PATCH partially updates and leaves other fields intact', async () => {
      await send('post', user.token, FULL_PROFILE);
      const res = await send('patch', user.token, { weightKg: 72 });

      expect(res.status).toBe(200);
      expect(res.body.data.profile.weightKg).toBe(72);
      expect(res.body.data.profile.age).toBe(41);
      expect(res.body.data.profile.allergies).toEqual(['Penicillin', 'Peanuts']);
    });

    it('PATCH returns 404 when there is no profile (it never creates)', async () => {
      const res = await send('patch', user.token, { age: 30 });
      expect(res.status).toBe(404);
      expect(await Profile.countDocuments({})).toBe(0);
    });

    it('DELETE removes the profile, then 404s', async () => {
      await send('post', user.token, FULL_PROFILE);

      const del = await send('delete', user.token);
      expect(del.status).toBe(200);
      expect(del.body.data.deleted).toBe(true);
      expect(await Profile.countDocuments({ user: user.id })).toBe(0);

      const again = await send('delete', user.token);
      expect(again.status).toBe(404);
    });

    it('records timestamps', async () => {
      const res = await send('post', user.token, { age: 30 });
      expect(res.body.data.profile.createdAt).toBeDefined();
      expect(res.body.data.profile.updatedAt).toBeDefined();
    });
  });

  // ------------------------------------------------------ authentication ----
  describe('authentication', () => {
    it.each(['get', 'post', 'put', 'patch', 'delete'])(
      '%s /profile/me without a token returns 401',
      async (method) => {
        const res = await send(method, null, {});
        expect(res.status).toBe(401);
        expect(res.body.success).toBe(false);
      }
    );

    it('rejects a garbage bearer token with 401', async () => {
      const res = await send('get', 'not-a-real-token');
      expect(res.status).toBe(401);
    });
  });

  // ----------------------------------------------------------- ownership ----
  describe('ownership - user A cannot touch user B\'s profile', () => {
    let alice;
    let bob;
    let aliceProfileId;

    beforeEach(async () => {
      alice = await makeUser('alice@example.com');
      bob = await makeUser('bob@example.com');
      const res = await send('post', alice.token, FULL_PROFILE);
      aliceProfileId = res.body.data.profile.id;
    });

    it('B reading gets 404, not A\'s data (no existence leak)', async () => {
      const res = await send('get', bob.token);
      expect(res.status).toBe(404);
      expect(JSON.stringify(res.body)).not.toContain('Penicillin');
      expect(JSON.stringify(res.body)).not.toContain(aliceProfileId);
    });

    it('B PATCHing gets 404 and A\'s profile is unchanged', async () => {
      const res = await send('patch', bob.token, { age: 99, allergies: ['tampered'] });
      expect(res.status).toBe(404);

      const aliceView = await send('get', alice.token);
      expect(aliceView.body.data.profile.age).toBe(41);
      expect(aliceView.body.data.profile.allergies).toEqual(['Penicillin', 'Peanuts']);
    });

    it('B DELETEing gets 404 and A\'s profile survives', async () => {
      const res = await send('delete', bob.token);
      expect(res.status).toBe(404);
      expect(await Profile.countDocuments({ user: alice.id })).toBe(1);
    });

    it('B PUTting creates B\'s OWN profile and never overwrites A\'s', async () => {
      const res = await send('put', bob.token, { age: 22 });
      expect(res.status).toBe(201);
      expect(res.body.data.profile.user).toBe(bob.id);
      expect(res.body.data.profile.id).not.toBe(aliceProfileId);

      const aliceView = await send('get', alice.token);
      expect(aliceView.body.data.profile.id).toBe(aliceProfileId);
      expect(aliceView.body.data.profile.age).toBe(41);
      expect(await Profile.countDocuments({})).toBe(2);
    });

    it('B cannot address A\'s profile by smuggling ids in the body', async () => {
      const res = await send('post', bob.token, {
        age: 22,
        user: alice.id,
        _id: aliceProfileId,
        id: aliceProfileId,
      });

      expect(res.status).toBe(201);
      expect(res.body.data.profile.user).toBe(bob.id);
      expect(res.body.data.profile.id).not.toBe(aliceProfileId);
    });

    it('B cannot reassign their profile to A with PATCH', async () => {
      await send('post', bob.token, { age: 22 });
      const res = await send('patch', bob.token, { user: alice.id, age: 23 });

      expect(res.status).toBe(200);
      expect(res.body.data.profile.user).toBe(bob.id);
      expect(await Profile.countDocuments({ user: alice.id })).toBe(1);
    });

    it('an ADMIN does not bypass ownership on profile data', async () => {
      const admin = await makePrivilegedUser(ROLES.ADMIN, 'admin@example.com');

      const read = await send('get', admin.token);
      expect(read.status).toBe(404);
      expect(JSON.stringify(read.body)).not.toContain('Penicillin');

      const patch = await send('patch', admin.token, { age: 1 });
      expect(patch.status).toBe(404);

      const del = await send('delete', admin.token);
      expect(del.status).toBe(404);

      // A's profile is untouched, and the admin's own PUT made a separate doc.
      const aliceView = await send('get', alice.token);
      expect(aliceView.body.data.profile.age).toBe(41);
    });

    it('a CLINICIAN does not bypass ownership on profile data', async () => {
      const clinician = await makePrivilegedUser(ROLES.CLINICIAN, 'doc@example.com');
      const res = await send('get', clinician.token);
      expect(res.status).toBe(404);
      expect(await Profile.countDocuments({ user: alice.id })).toBe(1);
    });
  });

  // ----------------------------------------------------------------- BMI ----
  describe('BMI is derived, never trusted', () => {
    let user;
    beforeEach(async () => {
      user = await makeUser('bmi@example.com');
    });

    it('computes BMI from heightCm and weightKg', async () => {
      const res = await send('post', user.token, { heightCm: 180, weightKg: 81 });
      expect(res.status).toBe(201);
      expect(res.body.data.profile.bmi).toBe(25); // 81 / 1.8^2
    });

    it('rounds to two decimal places', async () => {
      const res = await send('post', user.token, { heightCm: 165, weightKg: 68 });
      expect(res.body.data.profile.bmi).toBe(24.98);
    });

    it('ignores a client-supplied bmi entirely', async () => {
      const res = await send('post', user.token, {
        heightCm: 180,
        weightKg: 81,
        bmi: 12.3,
      });
      expect(res.body.data.profile.bmi).toBe(25);

      const stored = await Profile.findOne({ user: user.id });
      expect(stored.bmi).toBe(25);
    });

    it('ignores a client-supplied bmi when height/weight are absent', async () => {
      const res = await send('post', user.token, { age: 30, bmi: 12.3 });
      expect(res.status).toBe(201);
      expect(res.body.data.profile.bmi).toBeUndefined();
    });

    it('recomputes BMI on PATCH', async () => {
      await send('post', user.token, { heightCm: 180, weightKg: 81 });
      const res = await send('patch', user.token, { weightKg: 90 });
      expect(res.body.data.profile.bmi).toBe(27.78);
    });

    it('clears BMI when PUT drops the height', async () => {
      await send('post', user.token, { heightCm: 180, weightKg: 81 });
      const res = await send('put', user.token, { weightKg: 81 });
      expect(res.body.data.profile.bmi).toBeUndefined();
    });
  });

  // ---------------------------------------------------------- validation ----
  describe('physiological bounds', () => {
    let token;
    beforeEach(async () => {
      ({ token } = await makeUser('bounds@example.com'));
    });

    const accepts = async (body) => {
      const res = await send('post', token, body);
      expect(res.status).toBe(201);
      await Profile.deleteMany({});
    };
    const rejects = async (body) => {
      const res = await send('post', token, body);
      expect(res.status).toBe(422);
      expect(res.body.error.code).toBe('VALIDATION_ERROR');
      expect(await Profile.countDocuments({})).toBe(0);
    };

    it('accepts age at both boundaries', async () => {
      await accepts({ age: 0 });
      await accepts({ age: 120 });
    });

    it('rejects age outside the boundaries', async () => {
      await rejects({ age: -1 });
      await rejects({ age: 121 });
    });

    it('rejects a non-integer age', async () => {
      await rejects({ age: 30.5 });
    });

    it('accepts height at both boundaries', async () => {
      await accepts({ heightCm: 30 });
      await accepts({ heightCm: 275 });
    });

    it('rejects height outside the boundaries', async () => {
      await rejects({ heightCm: 29.9 });
      await rejects({ heightCm: 275.1 });
    });

    it('accepts weight at both boundaries', async () => {
      await accepts({ weightKg: 1 });
      await accepts({ weightKg: 650 });
    });

    it('rejects weight outside the boundaries', async () => {
      await rejects({ weightKg: 0.9 });
      await rejects({ weightKg: 651 });
    });

    it('rejects NaN-ish numeric strings for numbers (units cannot be smuggled)', async () => {
      await rejects({ weightKg: '70kg' });
      await rejects({ heightCm: '170' });
    });
  });

  describe('enums', () => {
    let token;
    beforeEach(async () => {
      ({ token } = await makeUser('enum@example.com'));
    });

    it.each(['male', 'female', 'other', 'prefer_not_to_say'])(
      'accepts gender %s',
      async (gender) => {
        const res = await send('post', token, { gender });
        expect(res.status).toBe(201);
        expect(res.body.data.profile.gender).toBe(gender);
      }
    );

    it('normalises gender casing and whitespace', async () => {
      const res = await send('post', token, { gender: '  FEMALE ' });
      expect(res.status).toBe(201);
      expect(res.body.data.profile.gender).toBe('female');
    });

    it('rejects an unknown gender', async () => {
      const res = await send('post', token, { gender: 'unicorn' });
      expect(res.status).toBe(422);
    });

    it.each(['never', 'former', 'current', 'ever', 'not_current', 'no_info'])(
      'accepts smokingHistory %s',
      async (smokingHistory) => {
        const res = await send('post', token, { smokingHistory });
        expect(res.status).toBe(201);
        expect(res.body.data.profile.smokingHistory).toBe(smokingHistory);
      }
    );

    it('rejects an unknown smokingHistory', async () => {
      const res = await send('post', token, { smokingHistory: 'sometimes' });
      expect(res.status).toBe(422);
    });
  });

  describe('type-confusion payloads are rejected on every field', () => {
    let token;
    beforeEach(async () => {
      ({ token } = await makeUser('types@example.com'));
    });

    const SCALAR_FIELDS = [
      'age',
      'gender',
      'heightCm',
      'weightKg',
      'hypertension',
      'heartDisease',
      'smokingHistory',
    ];
    const LIST_FIELDS = [
      'allergies',
      'medicalConditions',
      'medications',
      'previousHealthInformation',
      'heartDiseaseDetails',
    ];
    const HOSTILE = [
      ['an array', [1, 2]],
      ['an object', { a: 1 }],
      ['a $ne operator', { $ne: null }],
      ['a null', null],
    ];

    describe.each(SCALAR_FIELDS)('%s', (field) => {
      it.each(HOSTILE)('rejects %s', async (_label, value) => {
        const res = await send('post', token, { [field]: value });
        expect(res.status).toBe(422);
        expect(await Profile.countDocuments({})).toBe(0);
      });
    });

    describe.each(LIST_FIELDS)('%s', (field) => {
      it.each([
        ['a bare string', 'penicillin'],
        ['an object', { $ne: null }],
        ['a null', null],
        ['an array containing an object', [{ $ne: null }]],
        ['an array containing a number', [1]],
      ])('rejects %s', async (_label, value) => {
        const res = await send('post', token, { [field]: value });
        expect(res.status).toBe(422);
        expect(await Profile.countDocuments({})).toBe(0);
      });
    });

    it('rejects a boolean given as the string "true"', async () => {
      const res = await send('post', token, { hypertension: 'true' });
      expect(res.status).toBe(422);
    });

    it('rejects a boolean given as 1', async () => {
      const res = await send('post', token, { heartDisease: 1 });
      expect(res.status).toBe(422);
    });

    it('applies the same guards to PATCH', async () => {
      await send('post', token, { age: 30 });
      const res = await send('patch', token, { age: { $ne: null } });
      expect(res.status).toBe(422);
      const after = await send('get', token);
      expect(after.body.data.profile.age).toBe(30);
    });
  });

  describe('free-text caps and sanitisation', () => {
    let token;
    beforeEach(async () => {
      ({ token } = await makeUser('text@example.com'));
    });

    it('accepts exactly the maximum number of entries', async () => {
      const list = Array.from({ length: 30 }, (_, i) => `item-${i}`);
      const res = await send('post', token, { allergies: list });
      expect(res.status).toBe(201);
      expect(res.body.data.profile.allergies).toHaveLength(30);
    });

    it('rejects one entry over the count cap', async () => {
      const list = Array.from({ length: 31 }, (_, i) => `item-${i}`);
      const res = await send('post', token, { allergies: list });
      expect(res.status).toBe(422);
    });

    it('accepts an entry at the length cap and rejects one over it', async () => {
      const ok = await send('post', token, { medications: ['a'.repeat(200)] });
      expect(ok.status).toBe(201);
      await Profile.deleteMany({});

      const bad = await send('post', token, { medications: ['a'.repeat(201)] });
      expect(bad.status).toBe(422);
    });

    it('applies the tighter caps to previousHealthInformation', async () => {
      const okRes = await send('post', token, {
        previousHealthInformation: ['a'.repeat(500)],
      });
      expect(okRes.status).toBe(201);
      await Profile.deleteMany({});

      const tooLong = await send('post', token, {
        previousHealthInformation: ['a'.repeat(501)],
      });
      expect(tooLong.status).toBe(422);

      const tooMany = await send('post', token, {
        previousHealthInformation: Array.from({ length: 11 }, (_, i) => `n${i}`),
      });
      expect(tooMany.status).toBe(422);
    });

    it('strips control characters, collapses whitespace and drops blanks', async () => {
      const res = await send('post', token, {
        allergies: ['  Peanut  oil  ', '   ', 'Dust\tmite'],
      });
      expect(res.status).toBe(201);
      expect(res.body.data.profile.allergies).toEqual(['Peanut oil', 'Dust mite']);
    });

    it('accepts an empty array', async () => {
      const res = await send('post', token, { allergies: [] });
      expect(res.status).toBe(201);
      expect(res.body.data.profile.allergies).toEqual([]);
    });

    it('does not echo the submitted value back in the error message', async () => {
      const secret = 'x'.repeat(400);
      const res = await send('post', token, { allergies: [secret] });
      expect(res.status).toBe(422);
      expect(JSON.stringify(res.body)).not.toContain(secret);
    });
  });

  // -------------------------------------------------------- completeness ----
  describe('completeness', () => {
    it('reports which ML-relevant fields are missing', async () => {
      const { token } = await makeUser('complete@example.com');
      const res = await send('post', token, { age: 40, gender: 'male' });

      expect(res.status).toBe(201);
      const { completeness } = res.body.data.profile;
      expect(completeness.filled).toBe(2);
      expect(completeness.fields).toBe(7);
      expect(completeness.percent).toBe(29);
      expect(completeness.missing).toEqual(
        expect.arrayContaining(['heightCm', 'weightKg', 'hypertension', 'heartDisease', 'smokingHistory'])
      );
    });

    it('is 0% for an empty profile', async () => {
      const { token } = await makeUser('empty@example.com');
      const res = await send('post', token, {});
      expect(res.status).toBe(201);
      expect(res.body.data.profile.completeness.percent).toBe(0);
    });
  });
});
