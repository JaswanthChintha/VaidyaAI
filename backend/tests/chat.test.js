'use strict';


process.env.ENABLE_RATE_LIMIT = 'true';
process.env.RATE_LIMIT_MAX = '1000';
process.env.LOGIN_RATE_LIMIT_MAX = '50';
process.env.CHAT_RATE_LIMIT_MAX = '5';

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
const { resetRateLimiters } = require('../src/middleware/rateLimiter');
const { reportContext } = require('../src/controllers/chatController');

const CHAT = `${config.apiPrefix}/chat`;
const auth = (token) => ({ Authorization: `Bearer ${token}` });

const ANSWER = {
  outcome: 'answered',
  answer: 'Open the Reports page and press Upload.',
  sources: [{ kind: 'app_help', title: 'Uploading a report' }],
  model_used: true,
};

async function makeUser(email) {
  const { res } = await registerUser({ email, name: 'Test User' });
  expect(res.status).toBe(201);
  return { token: res.body.data.accessToken, id: res.body.data.user.id };
}

function clinicalReport() {
  return {
    report_version: '1.0.0',
    laboratory_values: [
      {
        feature: 'hba1c',
        display_name: 'HbA1c',
        value: 5.6,
        unit: '%',
        status: 'valid',
        usable: true,
        reference_range_raw: '4.0 - 5.6',
        original_test_name: 'Glycated Haemoglobin',
      },
      { feature: 'creatinine', value: 3.0, status: 'rejected', usable: false },
    ],
    conditions: [{ condition: 'Diabetes', status: 'NOT_INDICATED', risk: 'Low' }],
    overall: { status: 'Healthy', status_label: 'Healthy', any_assessed: true },
    patient: { name: 'SHOULD NOT BE SENT' },
  };
}

async function seedReport(userId) {
  const doc = await Report.create({
    user: userId,
    originalName: 'labs.pdf',
    storageKey: `${userId}/${new mongoose.Types.ObjectId().toString()}.pdf`,
    storageDriver: 'local',
    mimeType: 'application/pdf',
    sizeBytes: 1024,
    checksumSha256: 'a'.repeat(64),
    status: 'processed',
    clinicalReport: clinicalReport(),
    analysis: { version: 1, runCount: 1 },
  });
  return doc._id.toString();
}

const ask = (token, body) => request(app).post(CHAT).set(auth(token)).send(body);

beforeEach(async () => {
  await resetRateLimiters();
  mockAxios.post.mockReset();
  mockAxios.post.mockResolvedValue({ status: 200, data: { success: true, data: ANSWER } });
});

describe('POST /chat', () => {
  it('needs a signed-in user', async () => {
    const res = await request(app).post(CHAT).send({ question: 'What is HbA1c?' });
    expect(res.status).toBe(401);
    expect(mockAxios.post).not.toHaveBeenCalled();
  });

  it.each([
    [{}, 'no question'],
    [{ question: '' }, 'empty'],
    [{ question: '   ' }, 'blank'],
    [{ question: 'x'.repeat(301) }, 'too long'],
    [{ question: ['a', 'b'] }, 'an array'],
    [{ question: 'hi', reportId: { $ne: null } }, 'an object id'],
    [{ question: 'hi', reportId: 'not-an-id' }, 'a malformed id'],
  ])('refuses %j (%s) without calling the ai-service', async (body) => {
    const user = await makeUser(`bad-${Math.random()}@example.com`);
    const res = await ask(user.token, body);
    expect(res.status).toBe(422);
    expect(mockAxios.post).not.toHaveBeenCalled();
  });

  it('a general question sends the question only and returns the answer', async () => {
    const user = await makeUser('general@example.com');
    const res = await ask(user.token, { question: '  How do I upload a report?  ' });

    expect(res.status).toBe(200);
    expect(res.body.data.chat).toEqual(ANSWER);
    expect(res.body.data.usedReport).toBe(false);
    const [url, payload, options] = mockAxios.post.mock.calls[0];
    expect(url).toBe('/api/v1/chat');
    expect(payload).toEqual({ question: 'How do I upload a report?' });
    expect(options.headers['X-Service-Key']).toBe(config.aiService.apiKey);
  });

  it("a report question sends a compact summary of the caller's own report", async () => {
    const user = await makeUser('owner@example.com');
    const reportId = await seedReport(user.id);

    const res = await ask(user.token, { question: 'Is my HbA1c ok?', reportId });

    expect(res.status).toBe(200);
    expect(res.body.data.usedReport).toBe(true);
    const sent = mockAxios.post.mock.calls[0][1].report;
    expect(sent).toEqual({
      results: [{ name: 'HbA1c', value: '5.6', unit: '%', reference: '4.0 - 5.6' }],
      topics: [{ condition: 'Diabetes', status: 'Not flagged' }],
      overall: 'Healthy',
    });
    expect(JSON.stringify(mockAxios.post.mock.calls[0][1])).not.toMatch(/SHOULD NOT BE SENT/);
  });

  it("another user's report id is never read -- the question goes out as a general one", async () => {
    const owner = await makeUser('owner2@example.com');
    const other = await makeUser('other2@example.com');
    const reportId = await seedReport(owner.id);

    const res = await ask(other.token, { question: 'Is my HbA1c ok?', reportId });

    expect(res.status).toBe(200);
    expect(res.body.data.usedReport).toBe(false);
    expect(mockAxios.post.mock.calls[0][1].report).toBeUndefined();
  });

  it('is limited per user, and one user hitting it does not block another', async () => {
    expect(config.chat.rateLimitMax).toBe(5);
    const limited = await makeUser('busy@example.com');
    const fresh = await makeUser('fresh@example.com');
    const statuses = [];
    for (let i = 0; i < 6; i += 1) {
      statuses.push((await ask(limited.token, { question: `question ${i}` })).status);
    }
    expect(statuses).toEqual([200, 200, 200, 200, 200, 429]);
    expect((await ask(fresh.token, { question: 'hello' })).status).toBe(200);
  });

  it('a slow or failing ai-service is a clean error, never a stack trace', async () => {
    mockAxios.post.mockRejectedValue(Object.assign(new Error('timeout'), { code: 'ECONNABORTED' }));
    const user = await makeUser('slow@example.com');
    const res = await ask(user.token, { question: 'What is HbA1c?' });
    expect(res.status).toBeGreaterThanOrEqual(500);
    expect(res.body.success).toBe(false);
    expect(JSON.stringify(res.body)).not.toMatch(/\.js:\d+/);
    expect(mockAxios.post).toHaveBeenCalledTimes(1);
  });
});

describe('POST /chat with a sleeping ai-service', () => {
  const saved = {};
  const badGateway = () => Object.assign(new Error('bad gateway'), { response: { status: 502, data: '' } });
  const healthy = { status: 200, data: { success: true, data: { status: 'ok' } } };

  beforeEach(() => {
    saved.wait = config.aiService.chatWakeWaitMs;
    saved.interval = config.aiService.wakeIntervalMs;
    config.aiService.chatWakeWaitMs = 2000;
    config.aiService.wakeIntervalMs = 1;
    mockAxios.get.mockReset();
  });
  afterEach(() => {
    config.aiService.chatWakeWaitMs = saved.wait;
    config.aiService.wakeIntervalMs = saved.interval;
  });

  it('waits until it answers /health, and only THEN sends the question', async () => {
    let probes = 0;
    mockAxios.get.mockImplementation(async () => {
      probes += 1;
      if (probes < 3) throw badGateway();
      return healthy;
    });
    const user = await makeUser('wake.ok@example.com');
    const res = await ask(user.token, { question: 'What is HbA1c?' });

    expect(res.status).toBe(200);
    expect(res.body.data.chat).toEqual(ANSWER);
    expect(probes).toBe(3);
    const lastProbe = Math.max(...mockAxios.get.mock.invocationCallOrder);
    expect(lastProbe).toBeLessThan(mockAxios.post.mock.invocationCallOrder[0]);
  });

  it('still asleep at the deadline: says so plainly and does NOT send the question', async () => {
    config.aiService.chatWakeWaitMs = 30;
    config.aiService.wakeIntervalMs = 10;
    mockAxios.get.mockRejectedValue(badGateway());
    const user = await makeUser('wake.never@example.com');
    const res = await ask(user.token, { question: 'What is HbA1c?' });

    expect(res.status).toBe(503);
    expect(res.body.error).toEqual({
      code: 'ASSISTANT_WAKING',
      message: 'The assistant is waking up. Please try again in a minute.',
    });
    expect(mockAxios.get.mock.calls.length).toBeGreaterThan(1);
    expect(mockAxios.post).not.toHaveBeenCalled();
  });

  it('waiting switched off (laptop, tests): no /health probe at all', async () => {
    config.aiService.chatWakeWaitMs = 0;
    const user = await makeUser('wake.off@example.com');
    const res = await ask(user.token, { question: 'What is HbA1c?' });
    expect(res.status).toBe(200);
    expect(mockAxios.get).not.toHaveBeenCalled();
  });
});

describe('chatWakeWaitMs', () => {
  it('follows AI_SERVICE_WAKE_WAIT_MS but never waits more than 2 minutes', () => {
    const load = (value) => {
      let loaded;
      jest.isolateModules(() => {
        const before = process.env.AI_SERVICE_WAKE_WAIT_MS;
        if (value === undefined) delete process.env.AI_SERVICE_WAKE_WAIT_MS;
        else process.env.AI_SERVICE_WAKE_WAIT_MS = value;
        try {
          loaded = require('../src/config/env').aiService.chatWakeWaitMs;
        } finally {
          if (before === undefined) delete process.env.AI_SERVICE_WAKE_WAIT_MS;
          else process.env.AI_SERVICE_WAKE_WAIT_MS = before;
        }
      });
      return loaded;
    };
    expect(load('180000')).toBe(120000);
    expect(load('60000')).toBe(60000);
    expect(load('0')).toBe(0);
  });
});

describe('reportContext', () => {
  it('returns null for a report with no clinical report, and nothing invented for an empty one', () => {
    expect(reportContext(undefined)).toBeNull();
    expect(reportContext({})).toEqual({ results: [], topics: [] });
  });
});
