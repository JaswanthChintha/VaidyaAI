'use strict';

process.env.NODE_ENV = 'test';
// Secrets must be >= 32 chars and distinct (enforced by src/config/env.js).
process.env.JWT_SECRET =
  process.env.JWT_SECRET || 'test-access-secret-0123456789abcdef-not-for-prod';
process.env.JWT_REFRESH_SECRET =
  process.env.JWT_REFRESH_SECRET || 'test-refresh-secret-0123456789abcdef-not-for-prod';
process.env.JWT_EXPIRES_IN = process.env.JWT_EXPIRES_IN || '15m';
process.env.JWT_REFRESH_EXPIRES_IN = process.env.JWT_REFRESH_EXPIRES_IN || '7d';
// Lower bcrypt cost in tests: the security property is exercised by the code
// path, not by the work factor, and 12 rounds x many tests is slow.
process.env.BCRYPT_COST_FACTOR = process.env.BCRYPT_COST_FACTOR || '4';

// --- ai-service (Modules 4 + 5) -------------------------------------------
// A deliberately unroutable base URL and a throwaway key. EVERY suite mocks
// axios, so nothing is ever sent; the URL exists only so `isConfigured()` is
// true and the analysis routes are exercisable offline. If a mock is ever
// missed, the request fails to connect rather than reaching a real service.
// Set AI_SERVICE_URL yourself (with RUN_LIVE_INTEGRATION=1) for the live test.
process.env.AI_SERVICE_URL = process.env.AI_SERVICE_URL || 'http://127.0.0.1:9';
// >= 32 chars: the ai-service refuses a shorter key and env.js enforces the
// same minimum, so a short test key would fail startup.
process.env.AI_SERVICE_API_KEY =
  process.env.AI_SERVICE_API_KEY || 'test-ai-service-key-0123456789abcdef-not-for-prod';
// No retries by default: retrying is exercised explicitly where it matters and
// would otherwise multiply every error-path test's runtime.
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
