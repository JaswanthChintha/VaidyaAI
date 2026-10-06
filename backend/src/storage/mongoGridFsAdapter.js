'use strict';

const mongoose = require('mongoose');

const StorageAdapter = require('./StorageAdapter');
const ApiError = require('../utils/ApiError');
const { generateStoredFilename } = require('../utils/fileSecurity');

/**
 * MongoDB (GridFS) implementation of the storage adapter. STORAGE_DRIVER=mongo.
 *
 * WHY IT EXISTS. On a host whose disk is wiped on every restart (Render's free
 * plan, 2026-10-06), the local adapter loses every uploaded report the first
 * time the service sleeps: the analysis survives in MongoDB but the file behind
 * "download" and "re-analyse" does not. GridFS keeps the bytes in the same
 * database as the report row, so the two cannot drift apart that way.
 *
 * Layout: bucket `reportFiles` (collections `reportFiles.files` and
 * `reportFiles.chunks`). Each file's GridFS `filename` IS the opaque key,
 * `<userId>/<64 hex chars><ext>` -- the same shape the local adapter uses --
 * and `metadata.user` holds the owner id for `removeUserScope`.
 *
 * KEY SAFETY. There is no path to escape here, but a key is still checked
 * against the exact shape this adapter generates before any query, so a
 * tampered or foreign key addresses nothing instead of being handed to Mongo.
 * Access control stays where it already is: the owner-scoped report query.
 */

const BUCKET_NAME = 'reportFiles';
const KEY_PATTERN = /^[a-f0-9]{24}\/[a-f0-9]{64}\.[a-z0-9]{1,8}$/;
const USER_ID_PATTERN = /^[a-fA-F0-9]{24}$/;

class MongoGridFsAdapter extends StorageAdapter {
  get name() {
    return 'mongo';
  }

  /** The bucket, built on the CURRENT connection (tests reconnect). */
  // eslint-disable-next-line class-methods-use-this
  bucket() {
    const { db } = mongoose.connection;
    if (!db) {
      throw new Error('MongoGridFsAdapter: the database is not connected');
    }
    return new mongoose.mongo.GridFSBucket(db, { bucketName: BUCKET_NAME });
  }

  /** A key this adapter could have produced, or a 404. */
  // eslint-disable-next-line class-methods-use-this
  checkKey(key) {
    if (typeof key !== 'string' || !KEY_PATTERN.test(key)) {
      throw ApiError.notFound('Stored file not found');
    }
    return key;
  }

  async findOne(key) {
    const files = await this.bucket().find({ filename: this.checkKey(key) }).limit(1).toArray();
    return files[0] || null;
  }

  /**
   * @param {{userId: string, buffer: Buffer, extension: string}} input
   * @returns {Promise<{key: string, size: number}>}
   */
  async save({ userId, buffer, extension }) {
    if (!Buffer.isBuffer(buffer)) {
      throw new Error('MongoGridFsAdapter.save requires a Buffer');
    }
    const id = String(userId);
    if (!USER_ID_PATTERN.test(id)) {
      throw new Error('MongoGridFsAdapter: userId must be a 24-character hex ObjectId');
    }
    const key = `${id.toLowerCase()}/${generateStoredFilename(extension)}`;
    this.checkKey(key);

    const upload = this.bucket().openUploadStream(key, { metadata: { user: id.toLowerCase() } });
    try {
      await new Promise((resolve, reject) => {
        upload.once('finish', resolve);
        upload.once('error', reject);
        upload.end(buffer);
      });
    } catch (err) {
      // Leave nothing behind: a half-written GridFS file is chunks with no
      // complete files row, which nothing would ever clean up.
      await upload.abort().catch(() => {});
      throw err;
    }
    return { key, size: buffer.length };
  }

  /**
   * @param {string} key
   * @returns {Promise<import('stream').Readable>}
   */
  async createReadStream(key) {
    const file = await this.findOne(key);
    if (!file) throw ApiError.notFound('Stored file not found');
    return this.bucket().openDownloadStream(file._id);
  }

  /**
   * @param {string} key
   * @returns {Promise<{size: number}|null>}
   */
  async stat(key) {
    let file;
    try {
      file = await this.findOne(key);
    } catch (err) {
      if (err instanceof ApiError) return null;
      throw err;
    }
    return file ? { size: file.length } : null;
  }

  /**
   * Idempotent delete.
   * @param {string} key
   * @returns {Promise<boolean>} true when a file was actually removed
   */
  async remove(key) {
    if (typeof key !== 'string' || !KEY_PATTERN.test(key)) return false;
    const bucket = this.bucket();
    const files = await bucket.find({ filename: key }).toArray();
    let removed = false;
    for (const file of files) {
      try {
        await bucket.delete(file._id);
        removed = true;
      } catch (err) {
        // Already gone between the find and the delete: idempotent.
        if (!/FileNotFound|File not found/i.test(String(err && err.message))) throw err;
      }
    }
    return removed;
  }

  /** Best-effort removal of every file one user owns. */
  async removeUserScope(userId) {
    const id = String(userId);
    if (!USER_ID_PATTERN.test(id)) {
      throw new Error('MongoGridFsAdapter: userId must be a 24-character hex ObjectId');
    }
    const bucket = this.bucket();
    const files = await bucket.find({ 'metadata.user': id.toLowerCase() }).toArray();
    for (const file of files) {
      await bucket.delete(file._id).catch(() => {});
    }
  }
}

module.exports = MongoGridFsAdapter;
module.exports.BUCKET_NAME = BUCKET_NAME;
