'use strict';

// These env vars MUST be set before src/config/env.js is first required.
// Jest gives every test file its own module registry, so this file gets a
// freshly configured app with rate limiting switched ON.
process.env.ENABLE_RATE_LIMIT = 'true';
process.env.LOGIN_RATE_LIMIT_MAX = '3';
process.env.RATE_LIMIT_MAX = '1000';
process.env.TRUST_PROXY = 'false';

const request = require('supertest');
const app = require('../src/app');
const config = require('../src/config/env');
const { parseTrustProxy } = require('../src/config/env');
const { resetRateLimiters } = require('../src/middleware/rateLimiter');

const BASE = `${config.apiPrefix}/auth`;

const user = {
  name: 'Asha Patel',
  email: 'asha.patel@example.com',
  password: 'Str0ng!Passw0rd',
};

/** Fire n failed logins, optionally setting X-Forwarded-For per request. */
async function failedLogins(count, xffForIndex) {
  const statuses = [];
  for (let i = 0; i < count; i += 1) {
    let req = request(app).post(`${BASE}/login`);
    if (xffForIndex) req = req.set('X-Forwarded-For', xffForIndex(i));
    // eslint-disable-next-line no-await-in-loop
    const res = await req.send({ email: user.email, password: 'Wr0ng!Password' });
    statuses.push(res.status);
  }
  return statuses;
}

beforeEach(async () => {
  await resetRateLimiters();
  await request(app).post(`${BASE}/register`).send(user);
  await resetRateLimiters(); // registration itself consumes limiter budget
});

describe('rate limiting is actually enforced', () => {
  it('is enabled in this test file', () => {
    expect(config.rateLimit.enabled).toBe(true);
    expect(config.rateLimit.loginMax).toBe(3);
  });

  it('blocks brute force after LOGIN_RATE_LIMIT_MAX failed attempts', async () => {
    const statuses = await failedLogins(8);

    expect(statuses).toEqual([401, 401, 401, 429, 429, 429, 429, 429]);
  });

  it('returns the standard error envelope on 429', async () => {
    await failedLogins(3);
    const res = await request(app)
      .post(`${BASE}/login`)
      .send({ email: user.email, password: 'Wr0ng!Password' });

    expect(res.status).toBe(429);
    expect(res.body).toEqual({
      success: false,
      error: {
        code: 'RATE_LIMIT_EXCEEDED',
        message: 'Too many requests, please try again later',
      },
    });
  });

  // Regression: defect 1. `trust proxy` used to be hard-coded to 1 with no
  // proxy in front, so req.ip - the limiter's key - came straight from the
  // client-supplied X-Forwarded-For header. Rotating that header gave an
  // attacker unlimited login attempts.
  it('cannot be bypassed by rotating X-Forwarded-For', async () => {
    const statuses = await failedLogins(8, (i) => `203.0.113.${i}`);

    expect(statuses).toEqual([401, 401, 401, 429, 429, 429, 429, 429]);
    expect(statuses.filter((s) => s === 429)).toHaveLength(5);
  });

  it('cannot be bypassed by a fixed spoofed X-Forwarded-For', async () => {
    const statuses = await failedLogins(5, () => '203.0.113.99');

    expect(statuses).toEqual([401, 401, 401, 429, 429]);
  });

  it('cannot be bypassed by a multi-hop X-Forwarded-For chain', async () => {
    const statuses = await failedLogins(
      5,
      (i) => `203.0.113.${i}, 198.51.100.${i}, 192.0.2.${i}`
    );

    expect(statuses).toEqual([401, 401, 401, 429, 429]);
  });

  it('ignores X-Real-IP too', async () => {
    const statuses = [];
    for (let i = 0; i < 5; i += 1) {
      // eslint-disable-next-line no-await-in-loop
      const res = await request(app)
        .post(`${BASE}/login`)
        .set('X-Real-IP', `203.0.113.${i}`)
        .send({ email: user.email, password: 'Wr0ng!Password' });
      statuses.push(res.status);
    }

    expect(statuses).toEqual([401, 401, 401, 429, 429]);
  });

  it('does not count successful logins against the login limiter', async () => {
    const statuses = [];
    for (let i = 0; i < 6; i += 1) {
      // eslint-disable-next-line no-await-in-loop
      const res = await request(app)
        .post(`${BASE}/login`)
        .send({ email: user.email, password: user.password });
      statuses.push(res.status);
    }

    expect(statuses.every((s) => s === 200)).toBe(true);
  });

  it('does not apply the strict login limit to /me', async () => {
    await failedLogins(5); // exhaust the login limiter

    const res = await request(app).get(`${BASE}/me`);
    expect(res.status).toBe(401); // rejected by protect, not by the limiter
  });
});

describe('parseTrustProxy', () => {
  it('defaults to trusting nobody', () => {
    expect(parseTrustProxy(undefined)).toBe(false);
    expect(parseTrustProxy('')).toBe(false);
    expect(parseTrustProxy(null)).toBe(false);
  });

  it('treats the usual falsey spellings as false', () => {
    ['false', 'FALSE', '0', 'no', 'off', ' false '].forEach((value) => {
      expect(parseTrustProxy(value)).toBe(false);
    });
  });

  it('parses an explicit hop count', () => {
    expect(parseTrustProxy('1')).toBe(1);
    expect(parseTrustProxy('2')).toBe(2);
  });

  it('supports true and Express trust-proxy expressions', () => {
    expect(parseTrustProxy('true')).toBe(true);
    expect(parseTrustProxy('loopback')).toBe('loopback');
    expect(parseTrustProxy('10.0.0.0/8')).toBe('10.0.0.0/8');
  });

  it('is what the app is configured with', () => {
    expect(app.get('trust proxy')).toBe(false);
    expect(config.trustProxy).toBe(false);
  });
});
