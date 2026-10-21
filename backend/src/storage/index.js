'use strict';

const config = require('../config/env');
const LocalDiskAdapter = require('./localDiskAdapter');
const MongoGridFsAdapter = require('./mongoGridFsAdapter');


class UnknownStorageDriverError extends Error {
  constructor(driver, known) {
    super(`Unknown storage driver "${driver}". Known drivers: ${known.join(', ')}`);
    this.name = 'UnknownStorageDriverError';
    this.driver = String(driver);
  }
}

const DRIVERS = {
  local: () => new LocalDiskAdapter({ root: config.upload.root }),
  mongo: () => new MongoGridFsAdapter(),
};

const instances = new Map();

function getStorage(driver = config.upload.driver) {
  const key = String(driver || '').toLowerCase();
  const factory = DRIVERS[key];
  if (!factory) {
    throw new UnknownStorageDriverError(driver, Object.keys(DRIVERS));
  }
  if (!instances.has(key)) instances.set(key, factory());
  return instances.get(key);
}

function resetStorage() {
  instances.clear();
}

module.exports = { getStorage, resetStorage, DRIVERS, UnknownStorageDriverError };
