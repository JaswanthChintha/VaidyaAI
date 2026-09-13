'use strict';

/**
 * Module 33 as it is reachable by a client.
 *
 *   POST /api/v1/reports/:id/summary-prose   { sentences, names }
 *
 * THIS SUITE EXISTS BECAUSE OF MEMORY.md section 6w. The parameter glossary
 * shipped returning a bare payload instead of the `{success, data}` envelope,
 * so the backend rejected every 200 as malformed and the feature was dead on
 * every call. Its fourteen unit tests were excellent and none of them went
 * through HTTP. Anything with a route needs one test that uses the route.
 *
 * In priority order:
 *
 *   1. OWNERSHIP. Another patient's report id must produce the same 404 a
 *      random id produces, and naming one is not permission to rewrite its
 *      summary.
 *   2. A REFUSAL IS NOT AN ERROR. No model, a safety rejection, a dropped
 *      fact, a transport failure -- all of them are 200 with no text, because
 *      the page renders the sentences it already has. A 500 here would turn a
 *      configuration state into a broken screen.
 *   3. THE CACHE IS KEYED ON THE SENTENCES, not only on the analysis version.
 *      The page can change what it composes without the analysis changing, and
 *      serving prose about different sentences is worse than serving none.
 *
 * axios is mocked at the transport layer, as `tests/timeline.test.js` does it.
 */

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

/** The ai-service's `{success, data}` envelope, carrying one outcome. */
function serviceReplies(data) {
  mockAxios.post.mockResolvedValue({ status: 200, data: { success: true, data } });
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
    // NAMING A REPORT IS NOT PERMISSION, and the reply must not confirm the
    // id exists by differing from the one for an id that does not.
    expect(theirs.body.error.code).toBe(random.body.error.code);
    // And nothing was sent anywhere on a refused request.
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
    // THE CONTRACT: this rewrites finished text. Anything that would let the
    // service summarise a payload instead is the thing `InShort`'s comment
    // refuses, so the request must carry no report and no analysis.
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
    // The page renders the sentences it already had. A 500 would turn a
    // configuration state into a broken screen.
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
    // THE REASON THE KEY IS NOT THE ANALYSIS VERSION ALONE. The page can
    // change what it composes without the analysis changing at all, and prose
    // about last week's sentences is worse than none.
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
    // Caching it would leave the page permanently without prose after a key
    // outage, with nothing to trigger another attempt.
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
    // THE CONTRACT THIS ENDPOINT EXISTS UNDER. A client that attaches the
    // reader's own number must not be able to get it to the model -- that is
    // what would turn "generally associated with" into a statement about a
    // named person.
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

  it('NEVER caches a result where nothing at all was generated', async () => {
    // FOUND LIVE, and it would have hidden until the next day. When the Gemini
    // quota is spent every model in the chain refuses and `generated_count` is
    // 0. Caching that pins an empty result to this report and these findings
    // forever: the quota resets, the cache key has not changed, and nothing
    // ever asks again.
    const owner = await makeUser('ctx.quota@example.com');
    const id = await seedReport(owner.id);
    serviceReplies({ entries: [], generated_count: 0, withheld_count: 2 });

    await postCtx(id, owner.token);
    await postCtx(id, owner.token);
    expect(mockAxios.post).toHaveBeenCalledTimes(2);
  });

  it('DOES cache a partial result, because those refusals will recur', async () => {
    // A gate refusal is an answer about this text, not about the service.
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
});
