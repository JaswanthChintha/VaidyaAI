'use strict';

const app = require('./app');
const config = require('./config/env');
const { connectDatabase, disconnectDatabase } = require('./config/database');
const aiServiceClient = require('./services/aiServiceClient');

let server;

async function start() {
  await connectDatabase();

  server = app.listen(config.port, () => {
    // eslint-disable-next-line no-console
    console.log(
      `VaidyaAI backend listening on port ${config.port} [${config.env}]`
    );

    // The ai-service answers a byte-identical 401 for a missing header, a wrong
    // key, an empty key and a whitespace key, so a runtime 401 cannot tell an
    // operator which it is. State OUR side of the configuration here, at
    // startup, where it is unambiguous. The key is never printed - only whether
    // one exists and its length.
    const ai = aiServiceClient.describeConfig();
    // eslint-disable-next-line no-console
    console.log(
      ai.configured
        ? `ai-service: configured url=${ai.url} apiKeyLength=${ai.apiKeyLength} ` +
            `timeoutMs=${ai.timeoutMs} retries=${ai.retries}`
        : 'ai-service: NOT configured (AI_SERVICE_URL unset) - ' +
            'POST /reports/:id/analyze will answer 503'
    );
  });
}

async function shutdown(signal) {
  // eslint-disable-next-line no-console
  console.log(`\n${signal} received. Shutting down gracefully...`);
  if (server) {
    await new Promise((resolve) => server.close(resolve));
  }
  await disconnectDatabase();
  process.exit(0);
}

['SIGINT', 'SIGTERM'].forEach((signal) => {
  process.on(signal, () => {
    shutdown(signal).catch(() => process.exit(1));
  });
});

process.on('unhandledRejection', (reason) => {
  // eslint-disable-next-line no-console
  console.error('Unhandled promise rejection:', reason);
  shutdown('unhandledRejection').catch(() => process.exit(1));
});

start().catch((err) => {
  // eslint-disable-next-line no-console
  console.error('Failed to start server:', err);
  process.exit(1);
});
