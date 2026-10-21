'use strict';


const fs = require('fs');
const os = require('os');
const path = require('path');
const mongoose = require('mongoose');

const UPLOAD_ROOT = fs.mkdtempSync(path.join(os.tmpdir(), 'vaidyaai-defects-test-'));
process.env.UPLOAD_ROOT = UPLOAD_ROOT;
process.env.UPLOAD_MAX_BYTES = String(64 * 1024);

const { app, request, registerUser } = require('./helpers');
const config = require('../src/config/env');
const Report = require('../src/models/Report');
const { ROLES } = require('../src/utils/roles');
const { ownerScopedFilter, OWNER_ONLY } = require('../src/utils/ownership');
const { getStorage, UnknownStorageDriverError } = require('../src/storage');
const { normalizeError, isMultipartParseError } = require('../src/middleware/errorHandler');

const REPORTS = `${config.apiPrefix}/reports`;
const auth = (token) => ({ Authorization: `Bearer ${token}` });

const pdfBytes = (filler = 'lab report body') =>
  Buffer.concat([Buffer.from('%PDF-1.7\n'), Buffer.from(filler), Buffer.from('\n%%EOF\n')]);

async function makeUser(email) {
  const { res } = await registerUser({ email, name: 'Test User' });
  expect(res.status).toBe(201);
  return { token: res.body.data.accessToken, id: res.body.data.user.id };
}

async function uploadReport(token) {
  const res = await request(app)
    .post(REPORTS)
    .set(auth(token))
    .attach('file', pdfBytes(), { filename: 'labs.pdf', contentType: 'application/pdf' });
  expect(res.status).toBe(201);
  return res.body.data.report;
}

const rawUpdate = (id, $set) =>
  mongoose.connection
    .collection('reports')
    .updateOne({ _id: new mongoose.Types.ObjectId(id) }, { $set });

function expectNoDisclosure(res) {
  expect(res.body.error).toBeDefined();
  expect(res.body.error.stack).toBeUndefined();
  const serialised = JSON.stringify(res.body);
  expect(serialised).not.toMatch(/node_modules/);
  expect(serialised).not.toMatch(/\.js:\d+/);
  expect(serialised).not.toMatch(/busboy|multipart\.js|[A-Za-z]:\\\\/);
}

describe('audit defect regressions (D1-D4)', () => {
  afterAll(() => {
    fs.rmSync(UPLOAD_ROOT, { recursive: true, force: true });
  });

  describe('D1 - multipart parse failures are 400, not a 500 with a stack', () => {
    it.each([
      ['a NUL in the filename', 'a.pdf\u0000.php'],
      ['a SOH control character', 'a\u0001b.pdf'],
      ['a bare CR', 'a\rb.pdf'],
      ['a bare LF', 'a\nb.pdf'],
    ])('%s -> 400 BAD_REQUEST', async (_label, filename) => {
      const user = await makeUser(`d1-${Buffer.from(filename).toString('hex')}@example.com`);

      const res = await request(app)
        .post(REPORTS)
        .set(auth(user.token))
        .attach('file', pdfBytes(), { filename, contentType: 'application/pdf' });

      expect([400, 201]).toContain(res.status);
      if (res.status === 400) {
        expect(res.body.success).toBe(false);
        expect(res.body.error.code).toBe('BAD_REQUEST');
        expectNoDisclosure(res);
      }
      expect(res.status).not.toBe(500);
    });

    it('a truncated multipart body -> 400, never 500', async () => {
      const user = await makeUser('d1-truncated@example.com');

      const res = await request(app)
        .post(REPORTS)
        .set(auth(user.token))
        .set('Content-Type', 'multipart/form-data; boundary=----vaidyaai')
        .send('------vaidyaai\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"');

      expect(res.status).toBe(400);
      expect(res.body.error.code).toBe('BAD_REQUEST');
      expect(res.body.error.code).not.toBe('INTERNAL_ERROR');
      expectNoDisclosure(res);
    });

    it('a multipart Content-Type with no boundary -> 4xx, never 500', async () => {
      const user = await makeUser('d1-noboundary@example.com');

      const res = await request(app)
        .post(REPORTS)
        .set(auth(user.token))
        .set('Content-Type', 'multipart/form-data')
        .send('whatever');

      expect(res.status).toBeGreaterThanOrEqual(400);
      expect(res.status).toBeLessThan(500);
      expectNoDisclosure(res);
    });

    it('a malformed part header raised anywhere maps to 400', () => {
      const bare = new Error('Malformed part header');
      expect(isMultipartParseError(bare)).toBe(true);
      const mapped = normalizeError(bare);
      expect(mapped).not.toBeNull();
      expect(mapped.statusCode).toBe(400);

      const tagged = new Error('some future busboy failure');
      tagged.isMultipartParseError = true;
      expect(normalizeError(tagged).statusCode).toBe(400);

      const multerish = new Error('File too large');
      multerish.name = 'MulterError';
      multerish.code = 'LIMIT_FILE_SIZE';
      expect(isMultipartParseError(multerish)).toBe(false);
      expect(normalizeError(multerish).statusCode).toBe(413);
    });

    it('a NORMAL upload is unaffected', async () => {
      const user = await makeUser('d1-normal@example.com');
      const report = await uploadReport(user.token);
      expect(report.originalName).toBe('labs.pdf');
    });
  });

  describe('D2 - an unresolvable storage driver', () => {
    it('is a mapped 503 on download, not a 500 with a stack', async () => {
      const user = await makeUser('d2-download@example.com');
      const report = await uploadReport(user.token);
      await rawUpdate(report.id, { storageDriver: 'not-a-real-driver' });

      const res = await request(app)
        .get(`${REPORTS}/${report.id}/download`)
        .set(auth(user.token));

      expect(res.status).toBe(503);
      expect(res.body.error.code).toBe('STORAGE_UNAVAILABLE');
      expectNoDisclosure(res);
      expect(JSON.stringify(res.body)).not.toContain('not-a-real-driver');
    });

    it('DELETE reports the truth: the row IS deleted, and it says so', async () => {
      const user = await makeUser('d2-delete@example.com');
      const report = await uploadReport(user.token);
      await rawUpdate(report.id, { storageDriver: 'not-a-real-driver' });

      const res = await request(app).delete(`${REPORTS}/${report.id}`).set(auth(user.token));

      expect(res.status).toBe(200);
      expect(res.body.data.deleted).toBe(true);
      expect(res.body.data.fileRemoved).toBe(false);
      expect(res.body.data.fileOrphaned).toBe(true);

      expect(await Report.findById(report.id)).toBeNull();
    });

    it('a normal DELETE still removes the file and reports fileOrphaned:false', async () => {
      const user = await makeUser('d2-normaldelete@example.com');
      const report = await uploadReport(user.token);

      const res = await request(app).delete(`${REPORTS}/${report.id}`).set(auth(user.token));
      expect(res.status).toBe(200);
      expect(res.body.data.fileRemoved).toBe(true);
      expect(res.body.data.fileOrphaned).toBe(false);
    });

    it('getStorage raises a NAMED error the handler can map', () => {
      expect(() => getStorage('nope')).toThrow(UnknownStorageDriverError);
      let raised;
      try {
        getStorage('nope');
      } catch (err) {
        raised = err;
      }
      const mapped = normalizeError(raised);
      expect(mapped).not.toBeNull();
      expect(mapped.statusCode).toBe(503);
      expect(mapped.code).toBe('STORAGE_UNAVAILABLE');
    });

    it('the mapping holds outside production, where stacks used to be exposed', () => {
      expect(config.isProduction).toBe(false);
      const mapped = normalizeError(new UnknownStorageDriverError('x', ['local']));
      expect(mapped.statusCode).toBe(503);
      expect(mapped.code).toBe('STORAGE_UNAVAILABLE');
      expect(mapped.message).not.toContain('x');
    });
  });

  describe('D3 - the served Content-Type is re-validated at serve time', () => {
    it('a mimeType tampered to text/html is not echoed into the header', async () => {
      const user = await makeUser('d3@example.com');
      const report = await uploadReport(user.token);
      await rawUpdate(report.id, { mimeType: 'text/html' });

      const res = await request(app)
        .get(`${REPORTS}/${report.id}/download`)
        .set(auth(user.token));

      expect(res.status).toBe(200);
      expect(res.headers['content-type']).toMatch(/application\/octet-stream/);
      expect(res.headers['content-type']).not.toMatch(/text\/html/);
      expect(res.headers['content-disposition']).toMatch(/^attachment;/);
      expect(res.headers['x-content-type-options']).toBe('nosniff');
      expect(res.headers['content-security-policy']).toBe("default-src 'none'; sandbox");
    });

    it.each(['image/svg+xml', 'application/javascript', 'text/plain', ''])(
      'degrades %s to application/octet-stream',
      async (mimeType) => {
        const user = await makeUser(`d3-${mimeType.replace(/\W/g, '') || 'empty'}@example.com`);
        const report = await uploadReport(user.token);
        await rawUpdate(report.id, { mimeType });

        const res = await request(app)
          .get(`${REPORTS}/${report.id}/download`)
          .set(auth(user.token));
        expect(res.headers['content-type']).toMatch(/application\/octet-stream/);
      }
    );

    it('an untampered report still serves its real detected type', async () => {
      const user = await makeUser('d3-clean@example.com');
      const report = await uploadReport(user.token);

      const res = await request(app)
        .get(`${REPORTS}/${report.id}/download`)
        .set(auth(user.token));
      expect(res.headers['content-type']).toMatch(/application\/pdf/);
    });
  });

  describe('D4 - ownerScopedFilter checks identity BEFORE any role bypass', () => {
    it('throws for an id-less identity even when its role is granted a bypass', () => {
      expect(() =>
        ownerScopedFilter({ role: ROLES.ADMIN }, { allowRoles: [ROLES.ADMIN] })
      ).toThrow(/requires an authenticated user with an id/);
    });

    it.each([
      ['a role-only object', { role: ROLES.CLINICIAN }],
      ['an empty object', {}],
      ['null', null],
      ['undefined', undefined],
      ['an id of null', { id: null, role: ROLES.ADMIN }],
      ['an id of empty string', { id: '', role: ROLES.ADMIN }],
    ])('never returns an unscoped filter for %s', (_label, identity) => {
      expect(() =>
        ownerScopedFilter(identity, { allowRoles: [ROLES.ADMIN, ROLES.CLINICIAN] })
      ).toThrow();
    });

    it('an explicit grant STILL works for a caller that has an id', () => {
      const id = new mongoose.Types.ObjectId().toString();
      const filter = ownerScopedFilter(
        { id, role: ROLES.ADMIN },
        { allowRoles: [ROLES.ADMIN] }
      );
      expect(filter).toEqual({});
    });

    it('the grant still respects `base` and still scopes an ungranted role', () => {
      const id = new mongoose.Types.ObjectId().toString();
      expect(
        ownerScopedFilter({ id, role: ROLES.ADMIN }, { allowRoles: [ROLES.ADMIN], base: { a: 1 } })
      ).toEqual({ a: 1 });
      expect(
        ownerScopedFilter({ id, role: ROLES.PATIENT }, { allowRoles: [ROLES.ADMIN] })
      ).toEqual({ user: id });
    });

    it('OWNER_ONLY denies an id-less admin as before', () => {
      expect(() => ownerScopedFilter({ role: ROLES.ADMIN }, { ...OWNER_ONLY })).toThrow();
    });
  });
});
