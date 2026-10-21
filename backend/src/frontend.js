'use strict';

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const express = require('express');
const helmet = require('helmet');

function inlineScriptHashes(html) {
  const hashes = [];
  const pattern = /<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi;
  let match;
  while ((match = pattern.exec(html)) !== null) {
    const text = match[1].replace(/\r\n?/g, '\n');
    const digest = crypto.createHash('sha256').update(text, 'utf8').digest('base64');
    hashes.push(`'sha256-${digest}'`);
  }
  return hashes;
}

function mountFrontend(app, { distDir, apiPrefix }) {
  const indexPath = path.join(distDir, 'index.html');
  if (!fs.existsSync(indexPath)) {
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

  app.use(
    '/assets',
    express.static(path.join(distDir, 'assets'), { immutable: true, maxAge: '1y', index: false })
  );
  app.use(express.static(distDir, { index: false }));

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
