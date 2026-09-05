'use strict';

const crypto = require('crypto');

/**
 * Module 3 - file-level security helpers.
 *
 * Two independent jobs live here, both of which exist because NOTHING the
 * client sends about a file may be trusted:
 *
 *   1. Content sniffing. The declared `Content-Type` of a multipart part and
 *      the extension of the declared filename are both attacker-controlled
 *      strings. The only trustworthy statement about a file's type is what its
 *      own leading bytes say, so the allow-list is keyed on magic bytes and the
 *      DETECTED type is what gets persisted and later served.
 *
 *   2. Filename sanitisation. The client filename is kept for display only and
 *      is never used to build a path - the stored name is generated from
 *      crypto.randomBytes. Even so it is scrubbed hard, because it ends up in a
 *      `Content-Disposition` header and in API responses.
 *
 * SVG is deliberately absent from the allow-list. It is an XML document that
 * can carry <script>, so accepting it would hand an attacker stored XSS on any
 * origin that ever renders an uploaded report.
 */

/**
 * Allowed report types, keyed by the canonical MIME type we store.
 * `match(buffer)` inspects real bytes; `extension` is the extension WE choose
 * for the stored file (never one supplied by the client).
 */
const ALLOWED_TYPES = Object.freeze([
  Object.freeze({
    mimeType: 'application/pdf',
    extension: '.pdf',
    // "%PDF-" at offset 0. Some readers tolerate leading junk; we do not,
    // because a file that begins with anything else (e.g. "<script>", "<?php")
    // is exactly the payload this check exists to reject.
    match: (b) => b.length >= 5 && b.subarray(0, 5).toString('latin1') === '%PDF-',
  }),
  Object.freeze({
    mimeType: 'image/jpeg',
    extension: '.jpg',
    // SOI marker FF D8 FF.
    match: (b) => b.length >= 3 && b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff,
  }),
  Object.freeze({
    mimeType: 'image/png',
    extension: '.png',
    // 89 50 4E 47 0D 0A 1A 0A
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

/**
 * Identify a buffer by its magic bytes.
 * @param {Buffer} buffer
 * @returns {{mimeType: string, extension: string}|null} null when unrecognised
 */
function detectFileType(buffer) {
  if (!Buffer.isBuffer(buffer) || buffer.length === 0) return null;
  const found = ALLOWED_TYPES.find((type) => type.match(buffer));
  return found ? { mimeType: found.mimeType, extension: found.extension } : null;
}

/** Windows reserved device names - a file called `CON` or `NUL.pdf` is trouble. */
const RESERVED_DEVICE_NAMES =
  /^(con|prn|aux|nul|com[0-9\u00b2\u00b3\u00b9]|lpt[0-9\u00b2\u00b3\u00b9])$/i;

const MAX_DISPLAY_NAME_LENGTH = 200;

/**
 * Reduce a client-supplied filename to something safe to store and echo back.
 *
 * Removes, in order: null bytes and control characters; Windows drive letters
 * and UNC prefixes; every path segment (so `../../etc/passwd` and
 * `C:\Windows\system32\x` both collapse to their last component); characters
 * that are illegal or meaningful on Windows/POSIX paths; leading dots, and
 * trailing dots and spaces (Windows strips those itself, which is how
 * `evil.php.` becomes `evil.php`). A name that reduces to nothing, or to a
 * reserved device name, is replaced with a fixed placeholder.
 *
 * The result is NEVER used to build a filesystem path - see
 * generateStoredFilename - it exists for display and for Content-Disposition.
 *
 * @param {*} name
 * @returns {string} always a non-empty, path-free string
 */
function sanitizeFilename(name) {
  if (typeof name !== 'string') return 'report';

  let value = name
    // Strip null bytes and other control characters (a NUL truncates the name
    // in some C-based syscalls, turning "a.pdf\0.php" into two different names
    // depending on who is looking).
    // eslint-disable-next-line no-control-regex
    .replace(/[\u0000-\u001f\u007f]/g, '');

  // Normalise separators, then take the last segment: this discards every
  // traversal component and any absolute-path prefix in one step.
  value = value.replace(/\\/g, '/');
  value = value.split('/').pop() || '';

  // A leftover `C:` prefix (from "C:file.pdf", which has no separator).
  value = value.replace(/^[A-Za-z]:/, '');

  // `.` and `..` are not names.
  if (value === '.' || value === '..') value = '';

  // Characters that are illegal on Windows or awkward everywhere.
  value = value.replace(/[<>:"|?*]/g, '_');

  // Collapse whitespace runs, strip leading dots/spaces and trailing dots/spaces.
  value = value.replace(/\s+/g, ' ').replace(/^[.\s]+/, '').replace(/[.\s]+$/, '');

  if (value.length > MAX_DISPLAY_NAME_LENGTH) {
    value = value.slice(0, MAX_DISPLAY_NAME_LENGTH);
  }

  if (!value) return 'report';

  // Reserved device name, with or without an extension (`NUL`, `nul.pdf`).
  const stem = value.split('.')[0];
  if (RESERVED_DEVICE_NAMES.test(stem)) return `file_${value}`;

  return value;
}

/**
 * Generate the name a file is actually stored under: 32 bytes of randomness
 * plus the extension implied by the DETECTED content type. No part of it comes
 * from the client, so no client input can influence where a write lands.
 *
 * @param {string} extension leading-dot extension chosen from ALLOWED_TYPES
 * @returns {string}
 */
function generateStoredFilename(extension) {
  if (!ALLOWED_EXTENSIONS.includes(extension)) {
    throw new Error(`Refusing to generate a stored filename for "${extension}"`);
  }
  return `${crypto.randomBytes(32).toString('hex')}${extension}`;
}

/**
 * SHA-256 of the file contents, hex encoded. Used for integrity checks and, for
 * later modules, duplicate detection. Hashing the bytes is not the same as
 * logging them - the digest is not reversible and is safe to store.
 * @param {Buffer} buffer
 * @returns {string}
 */
function checksum(buffer) {
  return crypto.createHash('sha256').update(buffer).digest('hex');
}

/**
 * Build a `Content-Disposition: attachment` value that is safe to emit.
 *
 * The header is a structured field: a raw quote or newline in the filename
 * would let an attacker inject header content. The ASCII fallback is therefore
 * reduced to a conservative character set, and the exact (possibly non-ASCII)
 * name is offered separately via RFC 5987 `filename*`.
 *
 * @param {string} displayName already passed through sanitizeFilename
 * @returns {string}
 */
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
