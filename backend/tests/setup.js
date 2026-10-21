'use strict';

process.env.NODE_ENV = 'test';
process.env.JWT_SECRET =
  process.env.JWT_SECRET || 'test-access-secret-0123456789abcdef-not-for-prod';
process.env.JWT_REFRESH_SECRET =
  process.env.JWT_REFRESH_SECRET || 'test-refresh-secret-0123456789abcdef-not-for-prod';
process.env.JWT_EXPIRES_IN = process.env.JWT_EXPIRES_IN || '15m';
process.env.JWT_REFRESH_EXPIRES_IN = process.env.JWT_REFRESH_EXPIRES_IN || '7d';
process.env.BCRYPT_COST_FACTOR = process.env.BCRYPT_COST_FACTOR || '4';

process.env.AI_SERVICE_URL = process.env.AI_SERVICE_URL || 'http://127.0.0.1:9';
process.env.AI_SERVICE_API_KEY =
  process.env.AI_SERVICE_API_KEY || 'test-ai-service-key-0123456789abcdef-not-for-prod';
process.env.AI_SERVICE_RETRIES = process.env.AI_SERVICE_RETRIES || '0';
process.env.AI_SERVICE_RETRY_DELAY_MS = process.env.AI_SERVICE_RETRY_DELAY_MS || '1';

const mongoose = require('mongoose');
const { MongoMemoryServer } = require('mongodb-memory-server');

let mongoServer;

beforeAll(async () => {
  mongoServer = await MongoMemoryServer.create();
  await mongoose.connect(mongoServer.getUri());
});

afterEach(async () => {
  const { collections } = mongoose.connection;
  await Promise.all(
    Object.values(collections).map((collection) => collection.deleteMany({}))
  );
});

afterAll(async () => {
  await mongoose.connection.dropDatabase().catch(() => {});
  await mongoose.disconnect();
  if (mongoServer) await mongoServer.stop();
});
