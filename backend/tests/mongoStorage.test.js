'use strict';


process.env.STORAGE_DRIVER = 'mongo';
process.env.UPLOAD_MAX_BYTES = String(64 * 1024);

const mongoose = require('mongoose');

const { app, request, registerUser, BASE } = require('./helpers');
const config = require('../src/config/env');
const { getStorage, resetStorage } = require('../src/storage');
const MongoGridFsAdapter = require('../src/storage/mongoGridFsAdapter');

const REPORTS = `${config.apiPrefix}/reports`;
const PASSWORD = 'Str0ng!Passw0rd';
const auth = (token) => ({ Authorization: `Bearer ${token}` });

const pdfBytes = (filler = 'lab report body') =>
  Buffer.concat([Buffer.from('%PDF-1.7\n'), Buffer.from(filler), Buffer.from('\n%%EOF\n')]);

const filesCollection = () =>
  mongoose.connection.collection(`${MongoGridFsAdapter.BUCKET_NAME}.files`);
const chunksCollection = () =>
  mongoose.connection.collection(`${MongoGridFsAdapter.BUCKET_NAME}.chunks`);

async function makeUser(email) {
  const { res } = await registerUser({ email, password: PASSWORD });
  expect(res.status).toBe(201);
  return { token: res.body.data.accessToken, id: res.body.data.user.id };
}

async function upload(token, bytes = pdfBytes()) {
  const res = await request(app)
    .post(REPORTS)
    .set(auth(token))
    .attach('file', bytes, { filename: 'labs.pdf', contentType: 'application/pdf' });
  expect(res.status).toBe(201);
  return res.body.data.report;
}

const binary = (res, callback) => {
  const parts = [];
  res.on('data', (chunk) => parts.push(chunk));
  res.on('end', () => callback(null, Buffer.concat(parts)));
};

beforeEach(async () => {
  resetStorage();
  await filesCollection().deleteMany({});
  await chunksCollection().deleteMany({});
});

describe('STORAGE_DRIVER=mongo', () => {
  it('is the configured driver and is registered', () => {
    expect(config.upload.driver).toBe('mongo');
    expect(getStorage().name).toBe('mongo');
  });

  it('stores an upload in GridFS, not on disk, tagged with its owner', async () => {
    const user = await makeUser('gridfs.save@example.com');
    const report = await upload(user.token);

    const stored = await mongoose.connection
      .collection('reports')
      .findOne({ _id: new mongoose.Types.ObjectId(report.id) });
    expect(stored.storageDriver).toBe('mongo');

    const files = await filesCollection().find({}).toArray();
    expect(files).toHaveLength(1);
    expect(files[0].filename).toBe(stored.storageKey);
    expect(files[0].metadata.user).toBe(user.id.toLowerCase());
    expect(files[0].length).toBe(pdfBytes().length);
  });

  it('downloads exactly the bytes that were uploaded', async () => {
    const user = await makeUser('gridfs.download@example.com');
    const bytes = pdfBytes('a distinctive body 0123456789');
    const report = await upload(user.token, bytes);

    const res = await request(app)
      .get(`${REPORTS}/${report.id}/download`)
      .set(auth(user.token))
      .buffer(true)
      .parse(binary);
    expect(res.status).toBe(200);
    expect(Buffer.compare(res.body, bytes)).toBe(0);
  });

  it('another user cannot download it', async () => {
    const owner = await makeUser('gridfs.owner@example.com');
    const other = await makeUser('gridfs.other@example.com');
    const report = await upload(owner.token);

    const res = await request(app).get(`${REPORTS}/${report.id}/download`).set(auth(other.token));
    expect(res.status).toBe(404);
  });

  it('deleting the report removes its file and every chunk', async () => {
    const user = await makeUser('gridfs.delete@example.com');
    const report = await upload(user.token);
    expect(await chunksCollection().countDocuments()).toBeGreaterThan(0);

    const res = await request(app).delete(`${REPORTS}/${report.id}`).set(auth(user.token));
    expect(res.status).toBe(200);
    expect(await filesCollection().countDocuments()).toBe(0);
    expect(await chunksCollection().countDocuments()).toBe(0);
  });

  it("deleting the account removes that user's files and leaves others'", async () => {
    const leaving = await makeUser('gridfs.leaving@example.com');
    const staying = await makeUser('gridfs.staying@example.com');
    await upload(leaving.token);
    await upload(leaving.token, pdfBytes('second report'));
    const kept = await upload(staying.token);

    const res = await request(app)
      .delete(`${BASE}/me`)
      .set(auth(leaving.token))
      .send({ password: PASSWORD });
    expect(res.status).toBe(200);
    expect(res.body.data.filesRemoved).toBe(2);

    const files = await filesCollection().find({}).toArray();
    expect(files).toHaveLength(1);
    expect(files[0].metadata.user).toBe(staying.id.toLowerCase());
    const keptRow = await mongoose.connection
      .collection('reports')
      .findOne({ _id: new mongoose.Types.ObjectId(kept.id) });
    expect(files[0].filename).toBe(keptRow.storageKey);
  });
});

describe('MongoGridFsAdapter on its own', () => {
  const adapter = new MongoGridFsAdapter();
  const userId = new mongoose.Types.ObjectId().toString();

  it('round-trips bytes and reports their size', async () => {
    const bytes = Buffer.from('%PDF-1.7\nhello\n%%EOF\n');
    const { key, size } = await adapter.save({ userId, buffer: bytes, extension: '.pdf' });
    expect(key).toMatch(new RegExp(`^${userId}/[a-f0-9]{64}\\.pdf$`));
    expect(size).toBe(bytes.length);
    expect(await adapter.stat(key)).toEqual({ size: bytes.length });

    const stream = await adapter.createReadStream(key);
    const parts = [];
    for await (const chunk of stream) parts.push(chunk);
    expect(Buffer.compare(Buffer.concat(parts), bytes)).toBe(0);
  });

  it('treats a missing or malformed key as absent, never as a query', async () => {
    const missing = `${userId}/${'a'.repeat(64)}.pdf`;
    expect(await adapter.stat(missing)).toBeNull();
    await expect(adapter.createReadStream(missing)).rejects.toMatchObject({ statusCode: 404 });

    for (const bad of [
      '../etc/passwd',
      { $ne: null },
      `${userId}/${'a'.repeat(64)}.pdf\u0000`,
      '',
      null,
    ]) {
      expect(await adapter.stat(bad)).toBeNull();
      await expect(adapter.createReadStream(bad)).rejects.toMatchObject({ statusCode: 404 });
      expect(await adapter.remove(bad)).toBe(false);
    }
  });

  it('remove is idempotent', async () => {
    const { key } = await adapter.save({ userId, buffer: Buffer.from('x'), extension: '.pdf' });
    expect(await adapter.remove(key)).toBe(true);
    expect(await adapter.remove(key)).toBe(false);
  });

  it('refuses a user id that is not an ObjectId', async () => {
    await expect(
      adapter.save({ userId: '../x', buffer: Buffer.from('x'), extension: '.pdf' })
    ).rejects.toThrow(/ObjectId/);
  });
});
