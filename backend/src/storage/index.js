'use strict';

const config = require('../config/env');
const LocalDiskAdapter = require('./localDiskAdapter');
const MongoGridFsAdapter = require('./mongoGridFsAdapter');

/**
 * Storage adapter factory - the single place that knows which implementation is
 * in use.
 *
 * TO SWAP STORAGE PROVIDERS:
 *   1. Add `src/storage/<provider>Adapter.js` implementing StorageAdapter.
 *   2. Register it in DRIVERS below.
 *   3. Set STORAGE_DRIVER=<provider> and whatever credentials it needs.
 * Nothing else in the codebase changes: reports already record which driver
 * produced their key, so existing rows keep resolving through the old adapter
 * if both are registered.
 */

/**
 * Raised when a report row names a driver this build does not register.
 *
 * It used to be a plain `Error`, which meant it missed every branch of
 * `normalizeError` and landed in the generic 500 handler - the only branch that
 * prints a stack trace. A row can only acquire an unknown driver through a raw
 * driver write or a rolled-back deploy, so this is robustness rather than a
 * security hole, but an unmapped error class reaching the stack-printing branch
 * is exactly the defect shape this codebase has now hit three times. Giving it
 * a name lets the error handler map it to a clean, stack-free response.
 */
class UnknownStorageDriverError extends Error {
  constructor(driver, known) {
    super(`Unknown storage driver "${driver}". Known drivers: ${known.join(', ')}`);
    this.name = 'UnknownStorageDriverError';
    this.driver = String(driver);
  }
}

const DRIVERS = {
  local: () => new LocalDiskAdapter({ root: config.upload.root }),
  // Files in MongoDB GridFS, for hosts whose disk does not survive a restart.
  mongo: () => new MongoGridFsAdapter(),
};

/** Lazily-built singletons, keyed by driver name. */
const instances = new Map();

/**
 * @param {string} [driver] defaults to config.upload.driver
 * @returns {import('./StorageAdapter')}
 */
function getStorage(driver = config.upload.driver) {
  const key = String(driver || '').toLowerCase();
  const factory = DRIVERS[key];
  if (!factory) {
    throw new UnknownStorageDriverError(driver, Object.keys(DRIVERS));
  }
  if (!instances.has(key)) instances.set(key, factory());
  return instances.get(key);
}

/** Test hook: drop cached adapters (e.g. after changing UPLOAD_ROOT). */
function resetStorage() {
  instances.clear();
}

module.exports = { getStorage, resetStorage, DRIVERS, UnknownStorageDriverError };
