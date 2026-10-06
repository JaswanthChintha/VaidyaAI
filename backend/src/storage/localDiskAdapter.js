'use strict';

const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');

const StorageAdapter = require('./StorageAdapter');
const ApiError = require('../utils/ApiError');
const { generateStoredFilename } = require('../utils/fileSecurity');

/**
 * Local-disk implementation of the storage adapter.
 *
 * Layout:
 *
 *   <UPLOAD_ROOT>/<userId>/<64 hex chars><ext>
 *
 * Per-user subdirectories are a containment measure, not an access-control one:
 * access control is enforced in Mongo by the owner-scoped query. They make it
 * trivially auditable which files belong to whom, and they keep directory sizes
 * sane.
 *
 * PATH SAFETY. Two rules, both enforced here rather than at the call site:
 *   - The stored filename is generated from crypto.randomBytes and the DETECTED
 *     extension. No byte of it comes from the client.
 *   - Every key is re-resolved to an absolute path and checked to be inside the
 *     upload root before ANY read, write or unlink. Even if a malicious or
 *     buggy key were ever persisted, it cannot address a path outside the root.
 */
class LocalDiskAdapter extends StorageAdapter {
  /**
   * @param {{root: string}} options
   */
  constructor({ root }) {
    super();
    if (!root || typeof root !== 'string') {
      throw new Error('LocalDiskAdapter requires an absolute `root` path');
    }
    // Resolve once, and keep the trailing separator for prefix comparisons.
    this.root = path.resolve(root);
  }

  get name() {
    return 'local';
  }

  /**
   * Resolve a storage key to an absolute path, refusing anything that escapes
   * the upload root.
   * @param {string} key
   * @returns {string} absolute path inside the root
   */
  resolveKey(key) {
    if (typeof key !== 'string' || key.length === 0 || key.includes('\u0000')) {
      throw ApiError.notFound('Stored file not found');
    }

    // path.resolve collapses `..` segments; joining a key that begins with `/`
    // or `C:\` would otherwise discard the root entirely, so resolve against
    // the root and then VERIFY containment rather than trusting the join.
    const absolute = path.resolve(this.root, key);
    const rootWithSep = this.root.endsWith(path.sep) ? this.root : this.root + path.sep;

    if (absolute !== this.root && !absolute.startsWith(rootWithSep)) {
      // Not a 403: a caller should not learn that a path outside the root was
      // even considered. Whatever this key is, it addresses nothing we serve.
      throw ApiError.notFound('Stored file not found');
    }
    return absolute;
  }

  /** Directory holding one user's files. */
  userDir(userId) {
    const id = String(userId);
    // Ids come from Mongo ObjectIds, but assert the shape anyway: this value is
    // about to become a directory name.
    if (!/^[a-fA-F0-9]{24}$/.test(id)) {
      throw new Error('LocalDiskAdapter: userId must be a 24-character hex ObjectId');
    }
    return path.join(this.root, id);
  }

  /**
   * Write a file and return its opaque key.
   *
   * The write is atomic-ish: bytes go to a temporary name in the same directory
   * and are renamed into place. A crash mid-write therefore leaves a `.part`
   * file rather than a truncated file that the database claims is complete.
   *
   * @param {{userId: string, buffer: Buffer, extension: string}} input
   * @returns {Promise<{key: string, size: number}>}
   */
  async save({ userId, buffer, extension }) {
    if (!Buffer.isBuffer(buffer)) {
      throw new Error('LocalDiskAdapter.save requires a Buffer');
    }
    const dir = this.userDir(userId);
    await fsp.mkdir(dir, { recursive: true });

    const filename = generateStoredFilename(extension);
    const key = `${String(userId)}/${filename}`;
    const absolute = this.resolveKey(key);
    const temp = `${absolute}.part`;

    try {
      // `wx` - fail rather than overwrite. A collision on 32 random bytes means
      // something is very wrong; silently clobbering another report would be worse.
      await fsp.writeFile(temp, buffer, { flag: 'wx', mode: 0o600 });
      await fsp.rename(temp, absolute);
    } catch (err) {
      await fsp.rm(temp, { force: true }).catch(() => {});
      throw err;
    }

    return { key, size: buffer.length };
  }

  /**
   * @param {string} key
   * @returns {Promise<import('stream').Readable>}
   */
  async createReadStream(key) {
    const absolute = this.resolveKey(key);
    const stats = await fsp.stat(absolute).catch(() => null);
    if (!stats || !stats.isFile()) {
      throw ApiError.notFound('Stored file not found');
    }
    return fs.createReadStream(absolute);
  }

  /**
   * @param {string} key
   * @returns {Promise<{size: number}|null>}
   */
  async stat(key) {
    const absolute = this.resolveKey(key);
    const stats = await fsp.stat(absolute).catch(() => null);
    if (!stats || !stats.isFile()) return null;
    return { size: stats.size };
  }

  /**
   * Idempotent delete.
   * @param {string} key
   * @returns {Promise<boolean>} true when a file was actually removed
   */
  async remove(key) {
    let absolute;
    try {
      absolute = this.resolveKey(key);
    } catch (err) {
      // An unresolvable key addresses no file of ours; there is nothing to
      // delete and nothing to report.
      return false;
    }
    try {
      await fsp.unlink(absolute);
      return true;
    } catch (err) {
      if (err && err.code === 'ENOENT') return false;
      throw err;
    }
  }

  /** Best-effort removal of a whole user namespace. */
  async removeUserScope(userId) {
    const dir = this.userDir(userId);
    await fsp.rm(dir, { recursive: true, force: true });
  }
}

module.exports = LocalDiskAdapter;
