'use strict';

const jwt = require('jsonwebtoken');
const {
  app,
  request,
  BASE,
  validUser,
  registerUser,
  createUserWithRole,
  login,
} = require('./helpers');
const User = require('../src/models/User');
const config = require('../src/config/env');

describe('Module 1 - Authentication', () => {
  describe('GET /api/v1/health', () => {
    it('reports service health', async () => {
      const res = await request(app).get(`${config.apiPrefix}/health`);
      expect(res.status).toBe(200);
      expect(res.body.success).toBe(true);
      expect(res.body.data.status).toBe('ok');
    });
  });

  describe('POST /auth/register', () => {
    it('registers a new user and returns tokens without the password', async () => {
      const { res } = await registerUser();

      expect(res.status).toBe(201);
      expect(res.body.success).toBe(true);
      expect(res.body.data.user).toMatchObject({
        name: validUser.name,
        email: validUser.email,
        role: 'patient',
      });
      expect(res.body.data.user.password).toBeUndefined();
      expect(typeof res.body.data.accessToken).toBe('string');
      expect(typeof res.body.data.refreshToken).toBe('string');
    });

    it('stores the password hashed, never in plaintext', async () => {
      await registerUser();
      const stored = await User.findOne({ email: validUser.email }).select('+password');
      expect(stored.password).not.toBe(validUser.password);
      expect(stored.password.startsWith('$2')).toBe(true);
      await expect(stored.comparePassword(validUser.password)).resolves.toBe(true);
      await expect(stored.comparePassword('wrong-password')).resolves.toBe(false);
    });

    it('rejects a duplicate email with 409', async () => {
      await registerUser();
      const { res } = await registerUser();

      expect(res.status).toBe(409);
      expect(res.body.success).toBe(false);
      expect(res.body.error.code).toBe('CONFLICT');
    });

    it('rejects a weak password with 422', async () => {
      const { res } = await registerUser({ password: 'weak' });

      expect(res.status).toBe(422);
      expect(res.body.error.code).toBe('VALIDATION_ERROR');
      expect(res.body.error.details.some((d) => d.field === 'password')).toBe(true);
    });

    it('rejects an invalid email with 422', async () => {
      const { res } = await registerUser({ email: 'not-an-email' });

      expect(res.status).toBe(422);
      expect(res.body.error.details.some((d) => d.field === 'email')).toBe(true);
    });

    it('rejects a missing name with 422', async () => {
      const res = await request(app)
        .post(`${BASE}/register`)
        .send({ email: validUser.email, password: validUser.password });

      expect(res.status).toBe(422);
      expect(res.body.error.details.some((d) => d.field === 'name')).toBe(true);
    });

    it('refuses privilege escalation via the role field', async () => {
      const res = await request(app)
        .post(`${BASE}/register`)
        .send({ ...validUser, role: 'admin' });

      expect(res.status).toBe(422);
      expect(res.body.error.details.some((d) => d.field === 'role')).toBe(true);
    });

    it('rejects a password longer than 72 bytes', async () => {
      const longPassword = `Str0ng!${'a'.repeat(96)}`;
      expect(longPassword).toHaveLength(103);

      const { res } = await registerUser({ password: longPassword });

      expect(res.status).toBe(422);
      expect(res.body.error.details.some((d) => d.field === 'password')).toBe(true);
    });

    it('tells an over-long password that it is too long, in plain words', async () => {
      const { res } = await registerUser({ password: `Str0ng!${'a'.repeat(96)}` });
      expect(res.status).toBe(422);
      const message = res.body.error.details.find((d) => d.field === 'password').message;
      expect(message).toMatch(/too long/i);
      expect(message).toMatch(/72 characters/);
      expect(message).not.toMatch(/byte/i);
    });

    it('a different string sharing the first 72 bytes cannot authenticate', async () => {
      const password = `Aa1!${'x'.repeat(56)}`;
      expect(Buffer.byteLength(password, 'utf8')).toBe(60);

      const reg = await registerUser({ password });
      expect(reg.res.status).toBe(201);

      const attack = `${password}DIFFERS!`;
      expect(Buffer.byteLength(attack, 'utf8')).toBeLessThanOrEqual(72);
      const res = await login(validUser.email, attack);
      expect(res.status).toBe(401);
      expect(res.body.error.code).toBe('INVALID_CREDENTIALS');

      const genuine = await login(validUser.email, password);
      expect(genuine.status).toBe(200);
    });

    it('rejects a 72-byte password plus a suffix at the boundary', async () => {
      const password = `Aa1!${'x'.repeat(68)}`;
      expect(Buffer.byteLength(password, 'utf8')).toBe(72);

      const reg = await registerUser({ password });
      expect(reg.res.status).toBe(201);

      const res = await login(validUser.email, `${password}JUNKJUNKJUNK`);
      expect(res.status).not.toBe(200);
      expect(res.body.success).toBe(false);

      const genuine = await login(validUser.email, password);
      expect(genuine.status).toBe(200);
    });

    it('enforces the 72-byte cap at the model, bypassing the validator entirely', async () => {
      const longPassword = `Str0ng!${'a'.repeat(93)}`;
      expect(Buffer.byteLength(longPassword, 'utf8')).toBe(100);

      await expect(
        User.create({ name: 'Seed User', email: 'seed@example.com', password: longPassword })
      ).rejects.toMatchObject({ name: 'ValidationError' });

      expect(await User.findOne({ email: 'seed@example.com' })).toBeNull();
    });

    it('enforces the model cap when an existing password is changed', async () => {
      await registerUser();
      const user = await User.findOne({ email: validUser.email }).select('+password');
      user.password = `Str0ng!${'a'.repeat(93)}`;

      await expect(user.save()).rejects.toMatchObject({ name: 'ValidationError' });

      const res = await login(validUser.email, validUser.password);
      expect(res.status).toBe(200);
    });

    it('surfaces a model-level cap violation as a clean 422 through a route', async () => {
      const { res } = await registerUser({ password: `Str0ng!${'a'.repeat(93)}` });

      expect(res.status).toBe(422);
      expect(res.body.error.code).toBe('VALIDATION_ERROR');
      expect(res.body.error.stack).toBeUndefined();
    });

    it('measures the 72-byte limit in bytes, not characters', async () => {
      const multibyte = `Aa1!${'\u{1F600}'.repeat(20)}bcde`;
      expect(multibyte.length).toBe(48);
      expect(Buffer.byteLength(multibyte, 'utf8')).toBe(88);

      const { res } = await registerUser({ password: multibyte });
      expect(res.status).toBe(422);
      expect(res.body.error.details.some((d) => d.field === 'password')).toBe(true);
    });

    it('accepts a password sitting exactly on the 72-byte limit', async () => {
      const exact = `Aa1!${'x'.repeat(68)}`;
      expect(Buffer.byteLength(exact, 'utf8')).toBe(72);

      const { res } = await registerUser({ password: exact });
      expect(res.status).toBe(201);
    });

    it('rejects non-string types on every register field', async () => {
      const bodies = [
        { ...validUser, name: ['Asha', 'Patel'] },
        { ...validUser, name: 42 },
        { ...validUser, email: ['a@example.com', 'b@example.com'] },
        { ...validUser, email: 42 },
        { ...validUser, password: [validUser.password] },
        { ...validUser, password: 12345678 },
        { ...validUser, role: ['patient'] },
      ];

      for (const payload of bodies) {
        const res = await request(app).post(`${BASE}/register`).send(payload);
        expect(res.status).toBe(422);
        expect(res.body.success).toBe(false);
      }
    });

    it('neutralises NoSQL operator injection in the body', async () => {
      const res = await request(app)
        .post(`${BASE}/register`)
        .send({ ...validUser, email: { $gt: '' } });

      expect(res.status).toBe(422);
    });
  });

  describe('POST /auth/login', () => {
    beforeEach(async () => {
      await registerUser();
    });

    it('logs in with correct credentials', async () => {
      const res = await login(validUser.email, validUser.password);

      expect(res.status).toBe(200);
      expect(res.body.success).toBe(true);
      expect(res.body.data.user.email).toBe(validUser.email);
      expect(typeof res.body.data.accessToken).toBe('string');
      expect(typeof res.body.data.refreshToken).toBe('string');
    });

    it('rejects a wrong password with 401', async () => {
      const res = await login(validUser.email, 'Wr0ng!Password');

      expect(res.status).toBe(401);
      expect(res.body.error.code).toBe('INVALID_CREDENTIALS');
    });

    it('rejects an unknown email with the same generic 401', async () => {
      const res = await login('nobody@example.com', validUser.password);

      expect(res.status).toBe(401);
      expect(res.body.error.code).toBe('INVALID_CREDENTIALS');
      expect(res.body.error.message).toBe('Invalid email or password');
    });

    it('rejects an operator-object login attempt with 422', async () => {
      const res = await request(app)
        .post(`${BASE}/login`)
        .send({ email: { $ne: null }, password: { $ne: null } });

      expect(res.status).toBe(422);
      expect(res.body.error.code).toBe('VALIDATION_ERROR');
      expect(res.body.error.details.some((d) => d.field === 'email')).toBe(true);
    });

    it('rejects an array email (credential-spray via type confusion)', async () => {
      const res = await request(app)
        .post(`${BASE}/login`)
        .send({
          email: ['nobody@example.com', validUser.email],
          password: validUser.password,
        });

      expect(res.status).toBe(422);
      expect(res.body.error.code).toBe('VALIDATION_ERROR');
      expect(res.body.error.details.some((d) => d.field === 'email')).toBe(true);
      expect(res.body.data).toBeUndefined();
    });

    it('rejects an array email in either position (order-independent)', async () => {
      const res = await request(app)
        .post(`${BASE}/login`)
        .send({
          email: [validUser.email, 'nobody@example.com'],
          password: validUser.password,
        });

      expect(res.status).toBe(422);
      expect(res.body.error.code).toBe('VALIDATION_ERROR');
    });

    it('rejects a single-element array email', async () => {
      const res = await request(app)
        .post(`${BASE}/login`)
        .send({ email: [validUser.email], password: validUser.password });

      expect(res.status).toBe(422);
    });

    it('rejects non-string types on every login field', async () => {
      const bodies = [
        { email: 42, password: validUser.password },
        { email: null, password: validUser.password },
        { email: true, password: validUser.password },
        { email: validUser.email, password: [validUser.password] },
        { email: validUser.email, password: { $ne: null } },
        { email: validUser.email, password: 12345678 },
      ];

      for (const payload of bodies) {
        const res = await request(app).post(`${BASE}/login`).send(payload);
        expect(res.status).toBe(422);
        expect(res.body.success).toBe(false);
      }
    });
  });

  describe('GET /auth/me (protect middleware)', () => {
    let accessToken;

    beforeEach(async () => {
      const { res } = await registerUser();
      accessToken = res.body.data.accessToken;
    });

    it('returns 401 without a token', async () => {
      const res = await request(app).get(`${BASE}/me`);

      expect(res.status).toBe(401);
      expect(res.body.error.code).toBe('MISSING_TOKEN');
    });

    it('returns 401 for a malformed Authorization header', async () => {
      const res = await request(app)
        .get(`${BASE}/me`)
        .set('Authorization', accessToken);

      expect(res.status).toBe(401);
      expect(res.body.error.code).toBe('MISSING_TOKEN');
    });

    it('returns 401 for a garbage token', async () => {
      const res = await request(app)
        .get(`${BASE}/me`)
        .set('Authorization', 'Bearer not.a.real.token');

      expect(res.status).toBe(401);
      expect(res.body.error.code).toBe('INVALID_TOKEN');
    });

    it('returns 401 for a token signed with the wrong secret', async () => {
      const forged = jwt.sign({ sub: '000000000000000000000000', type: 'access' }, 'other-secret', {
        expiresIn: '15m',
        issuer: config.jwt.issuer,
        audience: config.jwt.audience,
      });
      const res = await request(app).get(`${BASE}/me`).set('Authorization', `Bearer ${forged}`);

      expect(res.status).toBe(401);
      expect(res.body.error.code).toBe('INVALID_TOKEN');
    });

    it('returns 401 for an expired token', async () => {
      const user = await User.findOne({ email: validUser.email });
      const expired = jwt.sign(
        { sub: user._id.toString(), role: user.role, type: 'access' },
        config.jwt.accessSecret,
        { expiresIn: '-10s', issuer: config.jwt.issuer, audience: config.jwt.audience }
      );
      const res = await request(app).get(`${BASE}/me`).set('Authorization', `Bearer ${expired}`);

      expect(res.status).toBe(401);
      expect(res.body.error.code).toBe('TOKEN_EXPIRED');
    });

    it('returns 401 when a refresh token is presented as an access token', async () => {
      const loginRes = await login(validUser.email, validUser.password);
      const res = await request(app)
        .get(`${BASE}/me`)
        .set('Authorization', `Bearer ${loginRes.body.data.refreshToken}`);

      expect(res.status).toBe(401);
      expect(res.body.error.code).toBe('INVALID_TOKEN');
    });

    it('returns 200 and the current user with a valid token', async () => {
      const res = await request(app)
        .get(`${BASE}/me`)
        .set('Authorization', `Bearer ${accessToken}`);

      expect(res.status).toBe(200);
      expect(res.body.success).toBe(true);
      expect(res.body.data.user.email).toBe(validUser.email);
      expect(res.body.data.user.password).toBeUndefined();
    });

    it('returns 401 once the account is deactivated', async () => {
      await User.updateOne({ email: validUser.email }, { isActive: false });
      const res = await request(app)
        .get(`${BASE}/me`)
        .set('Authorization', `Bearer ${accessToken}`);

      expect(res.status).toBe(401);
      expect(res.body.error.code).toBe('ACCOUNT_INACTIVE');
    });
  });

  describe('POST /auth/refresh', () => {
    let refreshToken;

    beforeEach(async () => {
      const { res } = await registerUser();
      refreshToken = res.body.data.refreshToken;
    });

    it('issues a new working access token', async () => {
      const res = await request(app).post(`${BASE}/refresh`).send({ refreshToken });

      expect(res.status).toBe(200);
      expect(typeof res.body.data.accessToken).toBe('string');
      expect(typeof res.body.data.refreshToken).toBe('string');

      const me = await request(app)
        .get(`${BASE}/me`)
        .set('Authorization', `Bearer ${res.body.data.accessToken}`);
      expect(me.status).toBe(200);
    });

    it('rotates the refresh token - the old one stops working', async () => {
      const first = await request(app).post(`${BASE}/refresh`).send({ refreshToken });
      expect(first.status).toBe(200);
      expect(first.body.data.refreshToken).not.toBe(refreshToken);

      const replay = await request(app).post(`${BASE}/refresh`).send({ refreshToken });
      expect(replay.status).toBe(401);
      expect(replay.body.error.code).toBe('REFRESH_TOKEN_REVOKED');
    });

    it('rejects a garbage refresh token with 401', async () => {
      const res = await request(app)
        .post(`${BASE}/refresh`)
        .send({ refreshToken: 'nonsense' });

      expect(res.status).toBe(401);
      expect(res.body.error.code).toBe('INVALID_TOKEN');
    });

    it('rejects a missing refresh token with 422', async () => {
      const res = await request(app).post(`${BASE}/refresh`).send({});

      expect(res.status).toBe(422);
      expect(res.body.error.code).toBe('VALIDATION_ERROR');
    });

    it('never stores the refresh token in plaintext', async () => {
      const user = await User.findOne({ email: validUser.email }).select('+refreshTokens');
      expect(user.refreshTokens).toHaveLength(1);
      expect(user.refreshTokens[0].tokenHash).not.toBe(refreshToken);
      expect(user.refreshTokens[0].tokenHash).toMatch(/^[a-f0-9]{64}$/);
    });
  });

  describe('POST /auth/logout', () => {
    it('invalidates the refresh token', async () => {
      const { res: reg } = await registerUser();
      const { refreshToken } = reg.body.data;

      const out = await request(app).post(`${BASE}/logout`).send({ refreshToken });
      expect(out.status).toBe(200);
      expect(out.body.success).toBe(true);

      const reuse = await request(app).post(`${BASE}/refresh`).send({ refreshToken });
      expect(reuse.status).toBe(401);
      expect(reuse.body.error.code).toBe('REFRESH_TOKEN_REVOKED');

      const user = await User.findOne({ email: validUser.email }).select('+refreshTokens');
      expect(user.refreshTokens).toHaveLength(0);
    });

    it('leaves other sessions signed in', async () => {
      await registerUser();
      const sessionA = await login(validUser.email, validUser.password);
      const sessionB = await login(validUser.email, validUser.password);

      await request(app)
        .post(`${BASE}/logout`)
        .send({ refreshToken: sessionA.body.data.refreshToken });

      const stillValid = await request(app)
        .post(`${BASE}/refresh`)
        .send({ refreshToken: sessionB.body.data.refreshToken });
      expect(stillValid.status).toBe(200);
    });

    it('is idempotent for an unusable token', async () => {
      const res = await request(app)
        .post(`${BASE}/logout`)
        .send({ refreshToken: 'garbage' });

      expect(res.status).toBe(200);
      expect(res.body.success).toBe(true);
    });
  });

  describe('password change revokes existing sessions', () => {
    const NEW_PASSWORD = 'An0ther!Passw0rd';

    async function changePassword(email, newPassword) {
      const user = await User.findOne({ email }).select('+password');
      user.password = newPassword;
      await user.save();
      return user;
    }

    it('rejects a refresh token minted before the password change', async () => {
      const { res } = await registerUser();
      const { refreshToken } = res.body.data;

      await changePassword(validUser.email, NEW_PASSWORD);

      const attempt = await request(app).post(`${BASE}/refresh`).send({ refreshToken });

      expect(attempt.status).toBe(401);
      expect(['PASSWORD_CHANGED', 'REFRESH_TOKEN_REVOKED']).toContain(
        attempt.body.error.code
      );
      expect(attempt.body.data).toBeUndefined();
    });

    it('purges every stored refresh-token digest on password change', async () => {
      await registerUser();
      await login(validUser.email, validUser.password);
      await login(validUser.email, validUser.password);

      const before = await User.findOne({ email: validUser.email }).select('+refreshTokens');
      expect(before.refreshTokens.length).toBeGreaterThan(1);

      await changePassword(validUser.email, NEW_PASSWORD);

      const after = await User.findOne({ email: validUser.email }).select('+refreshTokens');
      expect(after.refreshTokens).toHaveLength(0);
    });

    it('revokes all devices, not just one', async () => {
      await registerUser();
      const deviceA = await login(validUser.email, validUser.password);
      const deviceB = await login(validUser.email, validUser.password);

      await changePassword(validUser.email, NEW_PASSWORD);

      for (const session of [deviceA, deviceB]) {
        const attempt = await request(app)
          .post(`${BASE}/refresh`)
          .send({ refreshToken: session.body.data.refreshToken });
        expect(attempt.status).toBe(401);
      }
    });

    it('also rejects pre-change access tokens', async () => {
      await registerUser();
      const user = await User.findOne({ email: validUser.email });

      const accessToken = jwt.sign(
        {
          sub: user._id.toString(),
          role: user.role,
          type: 'access',
          iat: Math.floor(Date.now() / 1000) - 60,
        },
        config.jwt.accessSecret,
        {
          expiresIn: '15m',
          issuer: config.jwt.issuer,
          audience: config.jwt.audience,
        }
      );

      await changePassword(validUser.email, NEW_PASSWORD);

      const me = await request(app)
        .get(`${BASE}/me`)
        .set('Authorization', `Bearer ${accessToken}`);

      expect(me.status).toBe(401);
      expect(me.body.error.code).toBe('PASSWORD_CHANGED');
    });

    it('rejects a pre-change refresh token even before the digests are purged', async () => {
      const { res } = await registerUser();
      const { refreshToken } = res.body.data;

      await User.updateOne(
        { email: validUser.email },
        { passwordChangedAt: new Date(Date.now() + 60 * 1000) }
      );

      const attempt = await request(app).post(`${BASE}/refresh`).send({ refreshToken });

      expect(attempt.status).toBe(401);
      expect(attempt.body.error.code).toBe('PASSWORD_CHANGED');
    });

    it('lets the user log in again with the new password', async () => {
      await registerUser();
      await changePassword(validUser.email, NEW_PASSWORD);

      const stale = await login(validUser.email, validUser.password);
      expect(stale.status).toBe(401);

      const fresh = await login(validUser.email, NEW_PASSWORD);
      expect(fresh.status).toBe(200);

      const refreshed = await request(app)
        .post(`${BASE}/refresh`)
        .send({ refreshToken: fresh.body.data.refreshToken });
      expect(refreshed.status).toBe(200);
    });
  });
});

describe('Module 1 - Authorization (restrictTo)', () => {
  it('returns 403 for a patient hitting an admin-only route', async () => {
    const { res } = await registerUser();
    const admin = await request(app)
      .get(`${BASE}/admin/users`)
      .set('Authorization', `Bearer ${res.body.data.accessToken}`);

    expect(admin.status).toBe(403);
    expect(admin.body.success).toBe(false);
    expect(admin.body.error.code).toBe('INSUFFICIENT_ROLE');
  });

  it('returns 403 for a clinician hitting an admin-only route', async () => {
    await createUserWithRole('clinician', { email: 'doc@example.com' });
    const res = await login('doc@example.com', validUser.password);
    const admin = await request(app)
      .get(`${BASE}/admin/users`)
      .set('Authorization', `Bearer ${res.body.data.accessToken}`);

    expect(admin.status).toBe(403);
    expect(admin.body.error.code).toBe('INSUFFICIENT_ROLE');
  });

  it('returns 401 for an admin-only route without a token', async () => {
    const res = await request(app).get(`${BASE}/admin/users`);
    expect(res.status).toBe(401);
  });

  it('allows an admin through', async () => {
    await createUserWithRole('admin', { email: 'root@example.com' });
    const res = await login('root@example.com', validUser.password);
    const admin = await request(app)
      .get(`${BASE}/admin/users`)
      .set('Authorization', `Bearer ${res.body.data.accessToken}`);

    expect(admin.status).toBe(200);
    expect(admin.body.data.count).toBe(1);
  });
});

describe('Module 1 - Error shape and unknown routes', () => {
  it('returns the standard error envelope for an unknown route', async () => {
    const res = await request(app).get(`${config.apiPrefix}/does-not-exist`);

    expect(res.status).toBe(404);
    expect(res.body).toEqual({
      success: false,
      error: { code: 'NOT_FOUND', message: expect.any(String) },
    });
  });

  it('returns 400 for malformed JSON', async () => {
    const res = await request(app)
      .post(`${BASE}/login`)
      .set('Content-Type', 'application/json')
      .send('{"email": ');

    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe('BAD_REQUEST');
  });

  it('returns 413 (not 500) for an oversized body, with no stack trace', async () => {
    const oversized = { email: 'a@example.com', password: 'x'.repeat(20 * 1024) };
    const res = await request(app)
      .post(`${BASE}/login`)
      .set('Content-Type', 'application/json')
      .send(JSON.stringify(oversized));

    expect(res.status).toBe(413);
    expect(res.body).toEqual({
      success: false,
      error: { code: 'PAYLOAD_TOO_LARGE', message: 'Request body is too large' },
    });
    expect(JSON.stringify(res.body)).not.toMatch(/node_modules|\.js:\d+|PayloadTooLargeError/);
  });

  it('returns 413 for an oversized urlencoded body', async () => {
    const res = await request(app)
      .post(`${BASE}/login`)
      .set('Content-Type', 'application/x-www-form-urlencoded')
      .send(`password=${'x'.repeat(20 * 1024)}`);

    expect(res.status).toBe(413);
    expect(res.body.error.code).toBe('PAYLOAD_TOO_LARGE');
    expect(res.body.error.stack).toBeUndefined();
  });

  it('never exposes a stack trace on any 4xx response', async () => {
    const responses = await Promise.all([
      request(app).get(`${config.apiPrefix}/does-not-exist`),
      request(app).post(`${BASE}/login`).send({}),
      request(app).get(`${BASE}/me`),
      request(app).post(`${BASE}/refresh`).send({ refreshToken: 'nope' }),
    ]);

    for (const res of responses) {
      expect(res.status).toBeGreaterThanOrEqual(400);
      expect(res.status).toBeLessThan(500);
      expect(res.body.error.stack).toBeUndefined();
    }
  });
});
