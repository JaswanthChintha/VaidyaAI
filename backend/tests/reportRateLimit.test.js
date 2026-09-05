'use strict';

// These env vars MUST be set before src/config/env.js is first required. Jest
// gives every test file its own module registry, so this file gets a freshly
// configured app with rate limiting switched ON and a tiny upload budget.
process.env.ENABLE_RATE_LIMIT = 'true';
process.env.UPLOAD_RATE_LIMIT_MAX = '3';
process.env.RATE_LIMIT_MAX = '1000';
process.env.LOGIN_RATE_LIMIT_MAX = '50';
process.env.TRUST_PROXY = 'false';

const fs = require('fs');
const os = require('os');
const path = require('path');

const UPLOAD_ROOT = fs.mkdtempSync(path.join(os.tmpdir(), 'vaidyaai-reports-rl-'));
process.env.UPLOAD_ROOT = UPLOAD_ROOT;

const request = require('supertest');
const app = require('../src/app');
const config = require('../src/config/env');
const { resetRateLimiters } = require('../src/middleware/rateLimiter');

const AUTH = `${config.apiPrefix}/auth`;
const REPORTS = `${config.apiPrefix}/reports`;

const user = {
  name: 'Asha Patel',
  email: 'asha.patel@example.com',
  password: 'Str0ng!Passw0rd',
};

const pdf = () => Buffer.from('%PDF-1.7\nrate limit fixture\n%%EOF\n');

let token;

beforeEach(async () => {
  await resetRateLimiters();
  const res = await request(app).post(`${AUTH}/register`).send(user);
  token = res.body.data.accessToken;
});

afterEach(() => {
  for (const entry of fs.readdirSync(UPLOAD_ROOT)) {
    fs.rmSync(path.join(UPLOAD_ROOT, entry), { recursive: true, force: true });
  }
});

afterAll(() => {
  fs.rmSync(UPLOAD_ROOT, { recursive: true, force: true });
});

describe('Module 3 - upload rate limiting', () => {
  it('throttles uploads at their own, separate budget', async () => {
    const statuses = [];
    for (let i = 0; i < 5; i += 1) {
      // eslint-disable-next-line no-await-in-loop
      const res = await request(app)
        .post(REPORTS)
        .set({ Authorization: `Bearer ${token}` })
        .attach('file', pdf(), { filename: `labs-${i}.pdf` });
      statuses.push(res.status);
    }

    expect(statuses.slice(0, 3)).toEqual([201, 201, 201]);
    expect(statuses.slice(3)).toEqual([429, 429]);
  });

  it('returns the standard error envelope when throttled', async () => {
    for (let i = 0; i < 3; i += 1) {
      // eslint-disable-next-line no-await-in-loop
      await request(app)
        .post(REPORTS)
        .set({ Authorization: `Bearer ${token}` })
        .attach('file', pdf(), { filename: 'labs.pdf' });
    }
    const res = await request(app)
      .post(REPORTS)
      .set({ Authorization: `Bearer ${token}` })
      .attach('file', pdf(), { filename: 'labs.pdf' });

    expect(res.status).toBe(429);
    expect(res.body).toEqual({
      success: false,
      error: {
        code: 'RATE_LIMIT_EXCEEDED',
        message: 'Too many requests, please try again later',
      },
    });
  });

  it('does not consume the auth limiter budget, and reads are not throttled', async () => {
    for (let i = 0; i < 4; i += 1) {
      // eslint-disable-next-line no-await-in-loop
      await request(app)
        .post(REPORTS)
        .set({ Authorization: `Bearer ${token}` })
        .attach('file', pdf(), { filename: 'labs.pdf' });
    }

    // Uploads are exhausted...
    const blocked = await request(app)
      .post(REPORTS)
      .set({ Authorization: `Bearer ${token}` })
      .attach('file', pdf(), { filename: 'labs.pdf' });
    expect(blocked.status).toBe(429);

    // ...but logging in and listing reports still work.
    const login = await request(app)
      .post(`${AUTH}/login`)
      .send({ email: user.email, password: user.password });
    expect(login.status).toBe(200);

    const list = await request(app).get(REPORTS).set({ Authorization: `Bearer ${token}` });
    expect(list.status).toBe(200);
  });
});
