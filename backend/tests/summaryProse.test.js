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
