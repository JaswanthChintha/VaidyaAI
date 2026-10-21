'use strict';

const app = require('./app');
const config = require('./config/env');
const { connectDatabase, disconnectDatabase } = require('./config/database');
const aiServiceClient = require('./services/aiServiceClient');

let server;

async function start() {
  await connectDatabase();

  server = app.listen(config.port, () => {
    console.log(
      `VaidyaAI backend listening on port ${config.port} [${config.env}]`
    );

    const ai = aiServiceClient.describeConfig();
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
  console.error('Unhandled promise rejection:', reason);
  shutdown('unhandledRejection').catch(() => process.exit(1));
});

start().catch((err) => {
  console.error('Failed to start server:', err);
  process.exit(1);
});
