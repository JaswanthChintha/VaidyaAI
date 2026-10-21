'use strict';

const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');

const StorageAdapter = require('./StorageAdapter');
const ApiError = require('../utils/ApiError');
const { generateStoredFilename } = require('../utils/fileSecurity');

class LocalDiskAdapter extends StorageAdapter {
  constructor({ root }) {
    super();
    if (!root || typeof root !== 'string') {
      throw new Error('LocalDiskAdapter requires an absolute `root` path');
    }
    this.root = path.resolve(root);
  }

  get name() {
    return 'local';
  }

  resolveKey(key) {
    if (typeof key !== 'string' || key.length === 0 || key.includes('\u0000')) {
      throw ApiError.notFound('Stored file not found');
    }

    const absolute = path.resolve(this.root, key);
    const rootWithSep = this.root.endsWith(path.sep) ? this.root : this.root + path.sep;

    if (absolute !== this.root && !absolute.startsWith(rootWithSep)) {
      throw ApiError.notFound('Stored file not found');
    }
    return absolute;
  }

  userDir(userId) {
    const id = String(userId);
    if (!/^[a-fA-F0-9]{24}$/.test(id)) {
      throw new Error('LocalDiskAdapter: userId must be a 24-character hex ObjectId');
    }
    return path.join(this.root, id);
  }

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
      await fsp.writeFile(temp, buffer, { flag: 'wx', mode: 0o600 });
      await fsp.rename(temp, absolute);
    } catch (err) {
      await fsp.rm(temp, { force: true }).catch(() => {});
      throw err;
    }

    return { key, size: buffer.length };
  }

  async createReadStream(key) {
    const absolute = this.resolveKey(key);
    const stats = await fsp.stat(absolute).catch(() => null);
    if (!stats || !stats.isFile()) {
      throw ApiError.notFound('Stored file not found');
    }
    return fs.createReadStream(absolute);
  }

  async stat(key) {
    const absolute = this.resolveKey(key);
    const stats = await fsp.stat(absolute).catch(() => null);
    if (!stats || !stats.isFile()) return null;
    return { size: stats.size };
  }

  async remove(key) {
    let absolute;
    try {
      absolute = this.resolveKey(key);
    } catch (err) {
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

  async removeUserScope(userId) {
    const dir = this.userDir(userId);
    await fsp.rm(dir, { recursive: true, force: true });
  }
}

module.exports = LocalDiskAdapter;
