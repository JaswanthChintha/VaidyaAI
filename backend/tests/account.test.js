'use strict';

/**
 * Change password and permanent account deletion (2026-10-02).
 *
 *   POST   /api/v1/auth/change-password
 *   DELETE /api/v1/auth/me
 *
 * Both re-check the current password; both act on the caller only. Deletion
 * removes the account, the profile, every report row and every uploaded file,
 * and leaves another user's data alone. Real files are written to a throwaway
 * directory under the OS temp dir.
 */

const fs = require('fs');
const os = require('os');
const path = require('path');

const UPLOAD_ROOT = fs.mkdtempSync(path.join(os.tmpdir(), 'vaidyaai-account-test-'));
process.env.UPLOAD_ROOT = UPLOAD_ROOT;
process.env.UPLOAD_MAX_BYTES = String(64 * 1024);

const { app, request, BASE, registerUser, login } = require('./helpers');
const config = require('../src/config/env');
const User = require('../src/models/User');
const Profile = require('../src/models/Profile');
const Report = require('../src/models/Report');

const REPORTS = `${config.apiPrefix}/reports`;
const PASSWORD = 'Str0ng!Passw0rd';
const NEW_PASSWORD = 'N3w!Passw0rd-ok';
const auth = (token) => ({ Authorization: `Bearer ${token}` });
const pdfBytes = (filler = 'lab report body') =>
  Buffer.concat([Buffer.from('%PDF-1.7\n'), Buffer.from(filler), Buffer.from('\n%%EOF\n')]);

function listStoredFiles(dir = UPLOAD_ROOT) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    return entry.isDirectory() ? listStoredFiles(full) : [full];
  });
}

async function makeUser(email) {
  const { res } = await registerUser({ email, password: PASSWORD });
  expect(res.status).toBe(201);
  return {
    email,
    id: res.body.data.user.id,
    token: res.body.data.accessToken,
    refreshToken: res.body.data.refreshToken,
  };
}

async function upload(token, name = 'labs.pdf') {
  const res = await request(app)
    .post(REPORTS)
    .set(auth(token))
    .attach('file', pdfBytes(name), { filename: name, contentType: 'application/pdf' });
  expect(res.status).toBe(201);
  return res;
}

afterEach(() => {
  for (const entry of fs.readdirSync(UPLOAD_ROOT)) {
    fs.rmSync(path.join(UPLOAD_ROOT, entry), { recursive: true, force: true });
  }
});
afterAll(() => fs.rmSync(UPLOAD_ROOT, { recursive: true, force: true }));

const changePassword = (token, body) =>
  request(app).post(`${BASE}/change-password`).set(auth(token)).send(body);
const deleteAccount = (token, body) =>
  request(app).delete(`${BASE}/me`).set(auth(token)).send(body);

// =========================================================================
describe('POST /auth/change-password', () => {
  it('changes the password: the new one signs in, the old one does not', async () => {
    const u = await makeUser('change.ok@example.com');
    const res = await changePassword(u.token, { currentPassword: PASSWORD, newPassword: NEW_PASSWORD });
    expect(res.status).toBe(200);
    expect(res.body.data.accessToken).toEqual(expect.any(String));
    expect(res.body.data.refreshToken).toEqual(expect.any(String));

    expect((await login(u.email, NEW_PASSWORD)).status).toBe(200);
    expect((await login(u.email, PASSWORD)).status).toBe(401);
  });

  it('refuses a wrong current password with 400 (not 401), and changes nothing', async () => {
    const u = await makeUser('change.wrong@example.com');
    const res = await changePassword(u.token, { currentPassword: 'Wr0ng!Password', newPassword: NEW_PASSWORD });
    // 401 would make the client refresh and resend: a second password guess.
    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe('INVALID_CURRENT_PASSWORD');
    expect((await login(u.email, PASSWORD)).status).toBe(200);
  });

  it('applies the registration rules to the new password', async () => {
    const u = await makeUser('change.weak@example.com');
    const res = await changePassword(u.token, { currentPassword: PASSWORD, newPassword: 'weakpass' });
    expect(res.status).toBe(422);
    expect(res.body.error.details.some((d) => d.field === 'newPassword')).toBe(true);
  });

  it('refuses a "new" password that is the same as the current one', async () => {
    const u = await makeUser('change.same@example.com');
    const res = await changePassword(u.token, { currentPassword: PASSWORD, newPassword: PASSWORD });
    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe('PASSWORD_UNCHANGED');
  });

  it('signs out every other session; the new pair keeps this device signed in', async () => {
    const u = await makeUser('change.sessions@example.com');
    const other = (await login(u.email, PASSWORD)).body.data;

    // Token times are whole seconds and the model backdates the change by one
    // second, so wait past both before changing.
    await new Promise((r) => setTimeout(r, 2200));
    const res = await changePassword(u.token, { currentPassword: PASSWORD, newPassword: NEW_PASSWORD });
    expect(res.status).toBe(200);

    // The old refresh tokens -- this device's and the other device's -- are dead.
    for (const rt of [u.refreshToken, other.refreshToken]) {
      const r = await request(app).post(`${BASE}/refresh`).send({ refreshToken: rt });
      expect(r.status).toBe(401);
    }
    // Old access tokens stop working too.
    expect((await request(app).get(`${BASE}/me`).set(auth(other.accessToken))).status).toBe(401);
    // The fresh pair works.
    expect((await request(app).get(`${BASE}/me`).set(auth(res.body.data.accessToken))).status).toBe(200);
  });

  it('requires a signed-in caller', async () => {
    const res = await request(app)
      .post(`${BASE}/change-password`)
      .send({ currentPassword: PASSWORD, newPassword: NEW_PASSWORD });
    expect(res.status).toBe(401);
  });

  it('rejects a non-string current password before it reaches the database', async () => {
    const u = await makeUser('change.type@example.com');
    const res = await changePassword(u.token, { currentPassword: { $ne: '' }, newPassword: NEW_PASSWORD });
    expect(res.status).toBe(422);
  });
});

// =========================================================================
describe('DELETE /auth/me', () => {
  it('removes the account, the profile, every report and every file', async () => {
    const u = await makeUser('delete.all@example.com');
    const prof = await request(app).post(`${config.apiPrefix}/profile/me`).set(auth(u.token)).send({ age: 30, gender: 'female' });
    expect(prof.status).toBe(201);
    expect(await Profile.countDocuments({ user: u.id })).toBe(1);
    await upload(u.token, 'one.pdf');
    await upload(u.token, 'two.pdf');
    expect(await Report.countDocuments({ user: u.id })).toBe(2);
    expect(listStoredFiles().length).toBe(2);

    const res = await deleteAccount(u.token, { password: PASSWORD });
    expect(res.status).toBe(200);
    expect(res.body.data).toMatchObject({ deleted: true, reportsDeleted: 2, profileDeleted: true, filesRemoved: 2, filesFailed: 0 });

    expect(await User.countDocuments({ _id: u.id })).toBe(0);
    expect(await Profile.countDocuments({ user: u.id })).toBe(0);
    expect(await Report.countDocuments({ user: u.id })).toBe(0);
    expect(listStoredFiles()).toEqual([]);

    // Nothing of the account still works.
    expect((await login(u.email, PASSWORD)).status).toBe(401);
    expect((await request(app).get(`${BASE}/me`).set(auth(u.token))).status).toBe(401);
    expect((await request(app).post(`${BASE}/refresh`).send({ refreshToken: u.refreshToken })).status).toBe(401);
  });

  it('leaves another user\'s account, reports and files untouched', async () => {
    const alice = await makeUser('delete.alice@example.com');
    const bob = await makeUser('delete.bob@example.com');
    await upload(alice.token, 'alice.pdf');
    await upload(bob.token, 'bob.pdf');

    expect((await deleteAccount(alice.token, { password: PASSWORD })).status).toBe(200);

    expect(await User.countDocuments({ _id: bob.id })).toBe(1);
    expect(await Report.countDocuments({ user: bob.id })).toBe(1);
    const files = listStoredFiles();
    expect(files.length).toBe(1);
    expect(files[0]).toContain(bob.id);
    expect((await login(bob.email, PASSWORD)).status).toBe(200);
  });

  it('refuses a wrong password with 400 and deletes nothing', async () => {
    const u = await makeUser('delete.wrong@example.com');
    await upload(u.token);
    const res = await deleteAccount(u.token, { password: 'Wr0ng!Password' });
    expect(res.status).toBe(400);
    expect(res.body.error.code).toBe('INVALID_CURRENT_PASSWORD');
    expect(await User.countDocuments({ _id: u.id })).toBe(1);
    expect(await Report.countDocuments({ user: u.id })).toBe(1);
    expect(listStoredFiles().length).toBe(1);
  });

  it('refuses a missing password', async () => {
    const u = await makeUser('delete.nopass@example.com');
    const res = await deleteAccount(u.token, {});
    expect(res.status).toBe(422);
    expect(await User.countDocuments({ _id: u.id })).toBe(1);
  });

  it('requires a signed-in caller', async () => {
    const res = await request(app).delete(`${BASE}/me`).send({ password: PASSWORD });
    expect(res.status).toBe(401);
  });

  it('works for an account with no reports and no profile', async () => {
    const u = await makeUser('delete.empty@example.com');
    const res = await deleteAccount(u.token, { password: PASSWORD });
    expect(res.status).toBe(200);
    expect(res.body.data).toMatchObject({ reportsDeleted: 0, profileDeleted: false, filesRemoved: 0 });
    expect(await User.countDocuments({ _id: u.id })).toBe(0);
  });
});
