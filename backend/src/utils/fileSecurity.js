'use strict';

const crypto = require('crypto');


const ALLOWED_TYPES = Object.freeze([
  Object.freeze({
    mimeType: 'application/pdf',
    extension: '.pdf',
    match: (b) => b.length >= 5 && b.subarray(0, 5).toString('latin1') === '%PDF-',
  }),
  Object.freeze({
    mimeType: 'image/jpeg',
    extension: '.jpg',
    match: (b) => b.length >= 3 && b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff,
  }),
  Object.freeze({
    mimeType: 'image/png',
    extension: '.png',
    match: (b) =>
      b.length >= 8 &&
      b[0] === 0x89 &&
      b[1] === 0x50 &&
      b[2] === 0x4e &&
      b[3] === 0x47 &&
      b[4] === 0x0d &&
      b[5] === 0x0a &&
      b[6] === 0x1a &&
      b[7] === 0x0a,
  }),
]);

const ALLOWED_MIME_TYPES = Object.freeze(ALLOWED_TYPES.map((t) => t.mimeType));
const ALLOWED_EXTENSIONS = Object.freeze(['.pdf', '.jpg', '.jpeg', '.png']);

function detectFileType(buffer) {
  if (!Buffer.isBuffer(buffer) || buffer.length === 0) return null;
  const found = ALLOWED_TYPES.find((type) => type.match(buffer));
  return found ? { mimeType: found.mimeType, extension: found.extension } : null;
}

const RESERVED_DEVICE_NAMES =
  /^(con|prn|aux|nul|com[0-9\u00b2\u00b3\u00b9]|lpt[0-9\u00b2\u00b3\u00b9])$/i;

const MAX_DISPLAY_NAME_LENGTH = 200;

function sanitizeFilename(name) {
  if (typeof name !== 'string') return 'report';

  let value = name
    .replace(/[\u0000-\u001f\u007f]/g, '');

  value = value.replace(/\\/g, '/');
  value = value.split('/').pop() || '';

  value = value.replace(/^[A-Za-z]:/, '');

  if (value === '.' || value === '..') value = '';

  value = value.replace(/[<>:"|?*]/g, '_');

  value = value.replace(/\s+/g, ' ').replace(/^[.\s]+/, '').replace(/[.\s]+$/, '');

  if (value.length > MAX_DISPLAY_NAME_LENGTH) {
    value = value.slice(0, MAX_DISPLAY_NAME_LENGTH);
  }

  if (!value) return 'report';

  const stem = value.split('.')[0];
  if (RESERVED_DEVICE_NAMES.test(stem)) return `file_${value}`;

  return value;
}

function generateStoredFilename(extension) {
  if (!ALLOWED_EXTENSIONS.includes(extension)) {
    throw new Error(`Refusing to generate a stored filename for "${extension}"`);
  }
  return `${crypto.randomBytes(32).toString('hex')}${extension}`;
}

function checksum(buffer) {
  return crypto.createHash('sha256').update(buffer).digest('hex');
}

function contentDispositionAttachment(displayName) {
  const safe = sanitizeFilename(displayName);
  const ascii = safe.replace(/[^\x20-\x7e]/g, '_').replace(/["\\]/g, '_') || 'report';
  const encoded = encodeURIComponent(safe);
  return `attachment; filename="${ascii}"; filename*=UTF-8''${encoded}`;
}

module.exports = {
  ALLOWED_TYPES,
  ALLOWED_MIME_TYPES,
  ALLOWED_EXTENSIONS,
  MAX_DISPLAY_NAME_LENGTH,
  detectFileType,
  sanitizeFilename,
  generateStoredFilename,
  checksum,
  contentDispositionAttachment,
};
