'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const express = require('express');
const helmet = require('helmet');

/**
 * Serve the built React app (frontend/dist) from this same server.
 * Opt-in: only when FRONTEND_DIST is set (deployment, 2026-10-06).
 *
 * WHY THE BACKEND SERVES IT. The frontend calls `/api/...` on its own origin.
 * Serving both from one origin needs no CORS and no forwarding proxy -- and a
 * forwarding proxy would add a hop in front of `req.ip`, which with a wrong
 * TRUST_PROXY makes every user share one address and one login rate limit.
 *
 * THE ONE INLINE SCRIPT. `index.html` stamps the light/dark theme before first
 * paint with an inline <script>. helmet's default policy (`script-src 'self'`)
 * blocks inline scripts, so the page's own inline scripts are allowed by their
 * sha256 hash, computed from the built file at startup. Nothing else inline
 * runs, and editing the script changes its hash automatically on the next build.
 */
function inlineScriptHashes(html) {
  const hashes = [];
  const pattern = /<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi;
  let match;
  // eslint-disable-next-line no-cond-assign
  while ((match = pattern.exec(html)) !== null) {
    // The browser hashes the script AFTER its HTML parser has turned every
    // CRLF / CR into LF. A build checked out on Windows has CRLF, and hashing
    // those raw bytes gave a hash the browser never matched -- the script was
    // silently blocked (found 2026-10-06 in the browser, not by a test).
    const text = match[1].replace(/\r\n?/g, '\n');
    const digest = crypto.createHash('sha256').update(text, 'utf8').digest('base64');
    hashes.push(`'sha256-${digest}'`);
  }
  return hashes;
}

/**
 * @param {import('express').Express} app
 * @param {{distDir: string, apiPrefix: string}} options
 * @returns {boolean} whether the frontend was mounted
 */
function mountFrontend(app, { distDir, apiPrefix }) {
  const indexPath = path.join(distDir, 'index.html');
  if (!fs.existsSync(indexPath)) {
    // A missing build must be loud: the site would otherwise answer every page
    // with the API's JSON 404 and look like an outage with no cause.
    // eslint-disable-next-line no-console
    console.error(`FRONTEND_DIST is set but ${indexPath} does not exist; the frontend is not served`);
    return false;
  }
  const indexHtml = fs.readFileSync(indexPath, 'utf8');
  const defaults = helmet.contentSecurityPolicy.getDefaultDirectives();
  const pagePolicy = helmet.contentSecurityPolicy({
    directives: {
      ...defaults,
      'script-src': ["'self'", ...inlineScriptHashes(indexHtml)],
    },
  });

  const isApi = (req) => req.path === apiPrefix || req.path.startsWith(`${apiPrefix}/`);

  // Hashed build assets never change under the same name: cache them hard.
  app.use(
    '/assets',
    express.static(path.join(distDir, 'assets'), { immutable: true, maxAge: '1y', index: false })
  );
  app.use(express.static(distDir, { index: false }));

  // Client-side routes (/dashboard, /reports/...) all load the same page.
  app.get('*', (req, res, next) => {
    if (isApi(req) || !req.accepts('html')) return next();
    return pagePolicy(req, res, () => {
      res.set('Cache-Control', 'no-cache');
      res.type('html').send(indexHtml);
    });
  });
  return true;
}

module.exports = { mountFrontend, inlineScriptHashes };
