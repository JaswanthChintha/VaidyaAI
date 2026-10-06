'use strict';

/**
 * FRONTEND_DIST -- the backend serving the built React app (2026-10-06).
 *
 * A throwaway "build" is written to a temp folder: an index.html with one
 * inline script (like the real theme stamp) and one hashed asset. The tests
 * prove the page loads on every client-side route, the inline script is
 * allowed by its hash and by nothing broader, and the API is untouched --
 * an unknown /api path is still the JSON 404, never the HTML page.
 */

const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');

const DIST = fs.mkdtempSync(path.join(os.tmpdir(), 'vaidyaai-frontend-test-'));
const INLINE = "document.documentElement.dataset.theme = 'light';";
fs.mkdirSync(path.join(DIST, 'assets'));
fs.writeFileSync(
  path.join(DIST, 'index.html'),
  `<!doctype html><html><head><script>${INLINE}</script>` +
    '<script type="module" src="/assets/app-abc123.js"></script></head>' +
    '<body><div id="root"></div></body></html>'
);
fs.writeFileSync(path.join(DIST, 'assets', 'app-abc123.js'), 'console.log("app");');
process.env.FRONTEND_DIST = DIST;

const { app, request } = require('./helpers');
const config = require('../src/config/env');
const { inlineScriptHashes } = require('../src/frontend');

const expectedHash = `'sha256-${crypto.createHash('sha256').update(INLINE, 'utf8').digest('base64')}'`;

afterAll(() => fs.rmSync(DIST, { recursive: true, force: true }));

describe('serving the built frontend', () => {
  it('reads FRONTEND_DIST into config', () => {
    expect(config.frontendDist).toBe(path.resolve(DIST));
  });

  it.each(['/', '/dashboard', '/reports/abc/explained'])('%s answers with the page', async (url) => {
    const res = await request(app).get(url).set('Accept', 'text/html');
    expect(res.status).toBe(200);
    expect(res.headers['content-type']).toMatch(/text\/html/);
    expect(res.text).toContain('<div id="root"></div>');
    expect(res.headers['cache-control']).toBe('no-cache');
  });

  it('allows the inline script by its hash, and no inline script otherwise', async () => {
    const res = await request(app).get('/').set('Accept', 'text/html');
    const policy = res.headers['content-security-policy'];
    const scriptSrc = policy.split(';').map((d) => d.trim()).find((d) => d.startsWith('script-src'));
    expect(scriptSrc).toContain(expectedHash);
    expect(scriptSrc).toContain("'self'");
    expect(scriptSrc).not.toContain('unsafe-inline');
  });

  it('serves hashed assets with a long cache', async () => {
    const res = await request(app).get('/assets/app-abc123.js');
    expect(res.status).toBe(200);
    expect(res.text).toContain('console.log');
    expect(res.headers['cache-control']).toMatch(/immutable/);
  });

  it('leaves the API alone: an unknown API path is still the JSON 404', async () => {
    const res = await request(app).get(`${config.apiPrefix}/no-such-route`).set('Accept', 'text/html');
    expect(res.status).toBe(404);
    expect(res.headers['content-type']).toMatch(/json/);
    expect(res.body.success).toBe(false);
  });

  it('the API itself still answers', async () => {
    const res = await request(app).get(`${config.apiPrefix}/health`);
    expect(res.status).toBe(200);
    expect(res.headers['content-type']).toMatch(/json/);
  });
});

describe('inlineScriptHashes', () => {
  it('hashes inline scripts and skips scripts loaded from a file', () => {
    const html = `<script>${INLINE}</script><script type="module" src="/a.js"></script>`;
    expect(inlineScriptHashes(html)).toEqual([expectedHash]);
  });

  it('hashes what the BROWSER hashes: Windows line endings count as plain newlines', () => {
    const lf = 'var a = 1;\nvar b = 2;\n';
    const crlf = lf.replace(/\n/g, '\r\n');
    const browserHash = `'sha256-${crypto.createHash('sha256').update(lf, 'utf8').digest('base64')}'`;
    expect(inlineScriptHashes(`<script>${crlf}</script>`)).toEqual([browserHash]);
  });
});
