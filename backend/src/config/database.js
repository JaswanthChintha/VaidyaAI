'use strict';

const mongoose = require('mongoose');
const config = require('./env');

mongoose.set('strictQuery', true);

/**
 * Connect to MongoDB.
 * @param {string} [uri] Optional override (used by the test harness with an in-memory server).
 */
async function connectDatabase(uri = config.mongoUri) {
  const connection = await mongoose.connect(uri, {
    serverSelectionTimeoutMS: 10000,
  });

  if (!config.isTest) {
    // eslint-disable-next-line no-console
    console.log(`MongoDB connected: ${connection.connection.host}`);
  }

  return connection;
}

async function disconnectDatabase() {
  await mongoose.connection.close();
}

module.exports = { connectDatabase, disconnectDatabase };
