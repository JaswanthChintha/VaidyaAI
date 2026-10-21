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

const REPORTS = `${config.apiPrefix}/reports`;

const SENTENCES = [
  'This tool checked 8 conditions against a fixed set of thresholds.',
  'Your laboratory marked 11 further results outside its own range.',
];
const NAMES = ['Kidney Disease'];

async function makeUser(email) {
  const { res } = await registerUser({ email, name: 'Test User' });
  expect(res.status).toBe(201);
  return { token: res.body.data.accessToken, id: res.body.data.user.id };
}

async function seedReport(userId) {
  const doc = await Report.create({
    user: userId,
    originalName: 'labs.pdf',
    storageKey: `${userId}/${new mongoose.Types.ObjectId().toString()}.pdf`,
    storageDriver: 'local',
    mimeType: 'application/pdf',
    sizeBytes: 1024,
    checksumSha256: 'f'.repeat(64),
    status: 'processed',
    analysis: { version: 1 },
  });
  return doc._id.toString();
}

function serviceReplies(data) {
  mockAxios.post.mockResolvedValue({ status: 200, data: { success: true, data } });
}

function serviceRepliesSlowly(data, ms = 400) {
  mockAxios.post.mockImplementation(
    () => new Promise((resolve) => {
      setTimeout(() => resolve({ status: 200, data: { success: true, data } }), ms);
    })
  );
}

function post(id, token, body = { sentences: SENTENCES, names: NAMES }) {
  return request(app).post(`${REPORTS}/${id}/summary-prose`).set('Authorization', `Bearer ${token}`).send(body);
}

beforeEach(() => {
  mockAxios.post.mockReset();
  mockAxios.get.mockReset();
});

describe('ownership', () => {
  it('refuses another patient’s report with the same 404 a random id gets', async () => {
    const owner = await makeUser('prose.owner@example.com');
    const other = await makeUser('prose.other@example.com');
    const id = await seedReport(owner.id);
    serviceReplies({ outcome: 'generated', text: 'rewritten' });

    const theirs = await post(id, other.token);
    const random = await post(new mongoose.Types.ObjectId().toString(), other.token);

    expect(theirs.status).toBe(404);
    expect(random.status).toBe(404);
    expect(theirs.body.error.code).toBe(random.body.error.code);
    expect(mockAxios.post).not.toHaveBeenCalled();
  });

  it('requires authentication at all', async () => {
    const owner = await makeUser('prose.anon@example.com');
    const id = await seedReport(owner.id);
    const res = await request(app).post(`${REPORTS}/${id}/summary-prose`).send({ sentences: SENTENCES });
    expect(res.status).toBe(401);
  });
});

describe('the rewrite, through the route', () => {
  it('returns the model’s text when it was approved', async () => {
    const owner = await makeUser('prose.ok@example.com');
    const id = await seedReport(owner.id);
    serviceReplies({ outcome: 'generated', text: 'A better-reading summary.' });

    const res = await post(id, owner.token);
    expect(res.status).toBe(200);
    expect(res.body.success).toBe(true);
    expect(res.body.data.prose.text).toBe('A better-reading summary.');
  });

  it('sends the sentences VERBATIM and sends no report', async () => {
    const owner = await makeUser('prose.verbatim@example.com');
    const id = await seedReport(owner.id);
    serviceReplies({ outcome: 'generated', text: 'x' });

    await post(id, owner.token);
    const [, body] = mockAxios.post.mock.calls[0];
    expect(body.sentences).toEqual(SENTENCES);
    expect(body.names).toEqual(NAMES);
    expect(body.report).toBeUndefined();
    expect(body.analysis).toBeUndefined();
    expect(body.dashboard).toBeUndefined();
  });
});

describe('a refusal is not an error', () => {
  it.each([
    ['model_unavailable'],
    ['withheld_by_safety'],
    ['facts_missing'],
    ['facts_invented'],
  ])('answers 200 with no text on %s', async (outcome) => {
    const owner = await makeUser(`prose.${outcome}@example.com`);
    const id = await seedReport(owner.id);
    serviceReplies({ outcome, text: null });

    const res = await post(id, owner.token);
    expect(res.status).toBe(200);
    expect(res.body.data.prose.text).toBeFalsy();
  });

  it('answers 200 with no prose when the ai-service cannot be reached', async () => {
    const owner = await makeUser('prose.down@example.com');
    const id = await seedReport(owner.id);
    mockAxios.post.mockRejectedValue(new Error('ECONNREFUSED'));

    const res = await post(id, owner.token);
    expect(res.status).toBe(200);
    expect(res.body.data.prose).toBeNull();
  });
});

describe('the cache', () => {
  it('does not call the model twice for the same sentences', async () => {
    const owner = await makeUser('prose.cache@example.com');
    const id = await seedReport(owner.id);
    serviceReplies({ outcome: 'generated', text: 'once' });

    await post(id, owner.token);
    await post(id, owner.token);
    expect(mockAxios.post).toHaveBeenCalledTimes(1);
  });

  it('DOES call again when the page composes different sentences', async () => {
    const owner = await makeUser('prose.rekey@example.com');
    const id = await seedReport(owner.id);
    serviceReplies({ outcome: 'generated', text: 'first' });

    await post(id, owner.token);
    await post(id, owner.token, {
      sentences: [...SENTENCES, 'And one more sentence.'],
      names: NAMES,
    });
    expect(mockAxios.post).toHaveBeenCalledTimes(2);
  });

  it('caches a safety refusal, because retrying it spends the day’s quota', async () => {
    const owner = await makeUser('prose.refusalcache@example.com');
    const id = await seedReport(owner.id);
    serviceReplies({ outcome: 'withheld_by_safety', text: null });

    await post(id, owner.token);
    await post(id, owner.token);
    expect(mockAxios.post).toHaveBeenCalledTimes(1);
  });

  it('NEVER caches model_unavailable, which is a configuration state', async () => {
    const owner = await makeUser('prose.nokey@example.com');
    const id = await seedReport(owner.id);
    serviceReplies({ outcome: 'model_unavailable', text: null });

    await post(id, owner.token);
    await post(id, owner.token);
    expect(mockAxios.post).toHaveBeenCalledTimes(2);
  });
});

describe('Module 34 -- general context for out-of-range findings', () => {
  const FINDINGS = [
    { test_name: 'C-REACTIVE PROTEIN', direction: 'raised' },
    { test_name: 'LYMPHOCYTES', direction: 'lowered' },
  ];

  function postCtx(id, token, body = { findings: FINDINGS }) {
    return request(app)
      .post(`${REPORTS}/${id}/finding-context`)
      .set('Authorization', `Bearer ${token}`)
      .send(body);
  }

  it('refuses another patient’s report with the same 404 a random id gets', async () => {
    const owner = await makeUser('ctx.owner@example.com');
    const other = await makeUser('ctx.other@example.com');
    const id = await seedReport(owner.id);
    serviceReplies({ entries: [] });

    const theirs = await postCtx(id, other.token);
    const random = await postCtx(new mongoose.Types.ObjectId().toString(), other.token);
    expect(theirs.status).toBe(404);
    expect(theirs.body.error.code).toBe(random.body.error.code);
    expect(mockAxios.post).not.toHaveBeenCalled();
  });

  it('SENDS NO VALUE, because the body is rebuilt and not forwarded', async () => {
    const owner = await makeUser('ctx.novalue@example.com');
    const id = await seedReport(owner.id);
    serviceReplies({ entries: [] });

    await postCtx(id, owner.token, {
      findings: [
        {
          test_name: 'C-REACTIVE PROTEIN',
          direction: 'raised',
          value: 38.9,
          unit: 'mg/L',
          referenceHigh: 5,
          age: 20,
        },
      ],
    });

    const [, body] = mockAxios.post.mock.calls[0];
    expect(body.findings).toEqual([
      { test_name: 'C-REACTIVE PROTEIN', direction: 'raised' },
    ]);
    const sent = JSON.stringify(body);
    for (const leaked of ['38.9', 'mg/L', '"age"', 'referenceHigh']) {
      expect(sent).not.toContain(leaked);
    }
  });

  it('drops an entry with no name or no direction rather than sending it', async () => {
    const owner = await makeUser('ctx.partial@example.com');
    const id = await seedReport(owner.id);
    serviceReplies({ entries: [] });

    await postCtx(id, owner.token, {
      findings: [
        { test_name: 'CRP', direction: 'raised' },
        { test_name: 'FERRITIN' },
        { direction: 'lowered' },
      ],
    });
    const [, body] = mockAxios.post.mock.calls[0];
    expect(body.findings).toHaveLength(1);
  });

  it('never calls the model when there is nothing to ask about', async () => {
    const owner = await makeUser('ctx.empty@example.com');
    const id = await seedReport(owner.id);
    serviceReplies({ entries: [] });

    const res = await postCtx(id, owner.token, { findings: [] });
    expect(res.status).toBe(200);
    expect(res.body.data.context).toBeNull();
    expect(mockAxios.post).not.toHaveBeenCalled();
  });

  it('answers 200 with no context when the ai-service cannot be reached', async () => {
    const owner = await makeUser('ctx.down@example.com');
    const id = await seedReport(owner.id);
    mockAxios.post.mockRejectedValue(new Error('ECONNREFUSED'));

    const res = await postCtx(id, owner.token);
    expect(res.status).toBe(200);
    expect(res.body.data.context).toBeNull();
  });

  it('DOES cache a result that was entirely cache hits upstream', async () => {
    const owner = await makeUser('ctx.allcached@example.com');
    const id = await seedReport(owner.id);
    serviceReplies({
      entries: [{ test_name: 'CRP', direction: 'raised', text: 'x', available: true, cached: true }],
      generated_count: 0,
      cached_count: 1,
      withheld_count: 0,
    });

    await postCtx(id, owner.token);
    await postCtx(id, owner.token);
    expect(mockAxios.post).toHaveBeenCalledTimes(1);
  });

  it('NEVER caches a result where nothing came back available', async () => {
    const owner = await makeUser('ctx.quota@example.com');
    const id = await seedReport(owner.id);
    serviceReplies({
      entries: [
        { test_name: 'CRP', direction: 'raised', available: false, refused_by: 'safety' },
        { test_name: 'ESR', direction: 'raised', available: false, refused_by: 'safety' },
      ],
      generated_count: 0,
      cached_count: 0,
      withheld_count: 2,
    });

    await postCtx(id, owner.token);
    await postCtx(id, owner.token);
    expect(mockAxios.post).toHaveBeenCalledTimes(2);
  });

  it('DOES cache a partial result, because those refusals will recur', async () => {
    const owner = await makeUser('ctx.partial2@example.com');
    const id = await seedReport(owner.id);
    serviceReplies({
      entries: [{ test_name: 'CRP', direction: 'raised', text: 'x', available: true }],
      generated_count: 1,
      withheld_count: 1,
    });

    await postCtx(id, owner.token);
    await postCtx(id, owner.token);
    expect(mockAxios.post).toHaveBeenCalledTimes(1);
  });

  it('DOES cache a partial result whose gap is a real safety refusal', async () => {
    const owner = await makeUser('ctx.partialsafety@example.com');
    const id = await seedReport(owner.id);
    serviceReplies({
      entries: [
        { test_name: 'CRP', direction: 'raised', text: 'x', available: true },
        { test_name: 'ESR', direction: 'raised', available: false, refused_by: 'safety' },
      ],
      generated_count: 1,
      withheld_count: 1,
    });

    await postCtx(id, owner.token);
    await postCtx(id, owner.token);
    expect(mockAxios.post).toHaveBeenCalledTimes(1);
  });

  it('NEVER caches a partial result carrying an outage, so the gap is asked again', async () => {
    const owner = await makeUser('ctx.partialoutage@example.com');
    const id = await seedReport(owner.id);
    serviceReplies({
      entries: [
        { test_name: 'CRP', direction: 'raised', text: 'x', available: true },
        { test_name: 'ESR', direction: 'raised', available: false, refused_by: 'model_unavailable' },
      ],
      generated_count: 1,
      withheld_count: 1,
    });

    const first = await postCtx(id, owner.token);
    expect(first.status).toBe(200);
    expect(first.body.data.context.entries).toHaveLength(2);
    await postCtx(id, owner.token);
    expect(mockAxios.post).toHaveBeenCalledTimes(2);

    const stored = await Report.findById(id).select('+findingContext').lean();
    expect(stored.findingContext).toBeUndefined();
  });

  it('asks once for the same findings, and again when they change', async () => {
    const owner = await makeUser('ctx.cache@example.com');
    const id = await seedReport(owner.id);
    serviceReplies({
      entries: [{ test_name: 'CRP', direction: 'raised', available: true }],
      generated_count: 1,
    });

    await postCtx(id, owner.token);
    await postCtx(id, owner.token);
    expect(mockAxios.post).toHaveBeenCalledTimes(1);

    await postCtx(id, owner.token, {
      findings: [...FINDINGS, { test_name: 'ESR', direction: 'raised' }],
    });
    expect(mockAxios.post).toHaveBeenCalledTimes(2);
  });

  it('NEVER caches a result with a description still being written', async () => {
    const owner = await makeUser('ctx.inprogress@example.com');
    const id = await seedReport(owner.id);
    serviceReplies({
      entries: [
        { test_name: 'CRP', direction: 'raised', text: 'x', available: true },
        { test_name: 'ESR', direction: 'raised', available: false, refused_by: 'in_progress' },
      ],
      generated_count: 1,
      in_progress_count: 1,
    });

    const first = await postCtx(id, owner.token);
    expect(first.body.data.context.entries).toHaveLength(2);
    await postCtx(id, owner.token);
    expect(mockAxios.post).toHaveBeenCalledTimes(2);
    const stored = await Report.findById(id).select('+findingContext').lean();
    expect(stored.findingContext).toBeUndefined();
  });

  describe('two identical requests in flight', () => {
    const DESCRIBED = {
      entries: [{ test_name: 'CRP', direction: 'raised', text: 'x', available: true }],
      generated_count: 1,
    };

    it('make ONE ai-service call, and both get its answer', async () => {
      const owner = await makeUser('ctx.twice@example.com');
      const id = await seedReport(owner.id);
      serviceRepliesSlowly(DESCRIBED);

      const [a, b] = await Promise.all([postCtx(id, owner.token), postCtx(id, owner.token)]);
      expect(mockAxios.post).toHaveBeenCalledTimes(1);
      expect(a.status).toBe(200);
      expect(b.status).toBe(200);
      expect(a.body.data.context.entries[0].text).toBe('x');
      expect(b.body.data).toEqual(a.body.data);
    });

    it('still ask separately when the findings differ', async () => {
      const owner = await makeUser('ctx.twicediff@example.com');
      const id = await seedReport(owner.id);
      serviceRepliesSlowly(DESCRIBED);

      await Promise.all([
        postCtx(id, owner.token),
        postCtx(id, owner.token, { findings: [{ test_name: 'ESR', direction: 'raised' }] }),
      ]);
      expect(mockAxios.post).toHaveBeenCalledTimes(2);
    });

    it('still ask separately for two different reports', async () => {
      const owner = await makeUser('ctx.tworeports@example.com');
      const first = await seedReport(owner.id);
      const second = await seedReport(owner.id);
      serviceRepliesSlowly(DESCRIBED);

      await Promise.all([postCtx(first, owner.token), postCtx(second, owner.token)]);
      expect(mockAxios.post).toHaveBeenCalledTimes(2);
    });

    it('do not replay a failure to a request that arrives after it', async () => {
      const owner = await makeUser('ctx.twicefail@example.com');
      const id = await seedReport(owner.id);
      mockAxios.post.mockImplementationOnce(
        () => new Promise((_, reject) => { setTimeout(() => reject(new Error('ECONNREFUSED')), 400); })
      );

      const [a, b] = await Promise.all([postCtx(id, owner.token), postCtx(id, owner.token)]);
      expect(a.body.data.context).toBeNull();
      expect(b.body.data.context).toBeNull();
      expect(mockAxios.post).toHaveBeenCalledTimes(1);

      serviceReplies(DESCRIBED);
      const later = await postCtx(id, owner.token);
      expect(mockAxios.post).toHaveBeenCalledTimes(2);
      expect(later.body.data.context.entries[0].text).toBe('x');
    });

    it('do not let another patient share the answer', async () => {
      const owner = await makeUser('ctx.twiceowner@example.com');
      const other = await makeUser('ctx.twiceother@example.com');
      const id = await seedReport(owner.id);
      serviceRepliesSlowly(DESCRIBED);

      const [mine, theirs] = await Promise.all([postCtx(id, owner.token), postCtx(id, other.token)]);
      expect(mine.status).toBe(200);
      expect(theirs.status).toBe(404);
      expect(theirs.body.data).toBeUndefined();
    });
  });
});

describe('Module 33 -- two identical summary requests in flight', () => {
  it('make ONE ai-service call, and both get its answer', async () => {
    const owner = await makeUser('prose.twice@example.com');
    const id = await seedReport(owner.id);
    serviceRepliesSlowly({ outcome: 'generated', text: 'rewritten' });

    const [a, b] = await Promise.all([post(id, owner.token), post(id, owner.token)]);
    expect(mockAxios.post).toHaveBeenCalledTimes(1);
    expect(a.body.data.prose.text).toBe('rewritten');
    expect(b.body.data).toEqual(a.body.data);
  });

  it('still ask separately when the sentences differ', async () => {
    const owner = await makeUser('prose.twicediff@example.com');
    const id = await seedReport(owner.id);
    serviceRepliesSlowly({ outcome: 'generated', text: 'rewritten' });

    await Promise.all([
      post(id, owner.token),
      post(id, owner.token, { sentences: ['A different sentence.'], names: [] }),
    ]);
    expect(mockAxios.post).toHaveBeenCalledTimes(2);
  });
});
