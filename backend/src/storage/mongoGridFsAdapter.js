'use strict';

const mongoose = require('mongoose');

const StorageAdapter = require('./StorageAdapter');
const ApiError = require('../utils/ApiError');
const { generateStoredFilename } = require('../utils/fileSecurity');


const BUCKET_NAME = 'reportFiles';
const KEY_PATTERN = /^[a-f0-9]{24}\/[a-f0-9]{64}\.[a-z0-9]{1,8}$/;
const USER_ID_PATTERN = /^[a-fA-F0-9]{24}$/;

class MongoGridFsAdapter extends StorageAdapter {
  get name() {
    return 'mongo';
  }

  bucket() {
    const { db } = mongoose.connection;
    if (!db) {
      throw new Error('MongoGridFsAdapter: the database is not connected');
    }
    return new mongoose.mongo.GridFSBucket(db, { bucketName: BUCKET_NAME });
  }

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
      await upload.abort().catch(() => {});
      throw err;
    }
    return { key, size: buffer.length };
  }

  async createReadStream(key) {
    const file = await this.findOne(key);
    if (!file) throw ApiError.notFound('Stored file not found');
    return this.bucket().openDownloadStream(file._id);
  }

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
        if (!/FileNotFound|File not found/i.test(String(err && err.message))) throw err;
      }
    }
    return removed;
  }

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
