'use strict';

const express = require('express');
const helmet = require('helmet');
const cors = require('cors');
const mongoSanitize = require('express-mongo-sanitize');
const hpp = require('hpp');
const morgan = require('morgan');

const config = require('./config/env');
const routes = require('./routes');
const { errorHandler, notFoundHandler } = require('./middleware/errorHandler');
const { mountFrontend } = require('./frontend');

const app = express();

// SECURITY: `req.ip` is the rate limiter's key. When `trust proxy` is enabled,
// Express derives it from the client-supplied X-Forwarded-For header, so
// trusting a proxy that is not really in front of the app lets any caller
// rotate that header and bypass rate limiting. Default is `false` (trust
// nobody); set TRUST_PROXY to the real hop count only when deployed behind a
// load balancer. See .env.example and the README.
app.set('trust proxy', config.trustProxy);
app.disable('x-powered-by');

// --- Security middleware -------------------------------------------------
app.use(helmet());
app.use(
  cors({
    origin: config.cors.origin,
    credentials: true,
    methods: ['GET', 'POST', 'PATCH', 'PUT', 'DELETE', 'OPTIONS'],
  })
);

// --- Body parsing --------------------------------------------------------
app.use(express.json({ limit: '10kb' }));
app.use(express.urlencoded({ extended: true, limit: '10kb' }));

// --- Injection / pollution guards ---------------------------------------
// Strips keys containing `$` or `.` from body/params/query (NoSQL injection).
app.use(mongoSanitize({ replaceWith: '_' }));
app.use(hpp());

// --- Logging -------------------------------------------------------------
if (!config.isTest) {
  app.use(morgan(config.isProduction ? 'combined' : 'dev'));
}

// --- Routes --------------------------------------------------------------
app.use(config.apiPrefix, routes);

// --- The built React app, when FRONTEND_DIST is set (deployment) ---------
if (config.frontendDist) {
  mountFrontend(app, { distDir: config.frontendDist, apiPrefix: config.apiPrefix });
}

// --- Error handling ------------------------------------------------------
app.use(notFoundHandler);
app.use(errorHandler);

module.exports = app;
