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

app.set('trust proxy', config.trustProxy);
app.disable('x-powered-by');

app.use(helmet());
app.use(
  cors({
    origin: config.cors.origin,
    credentials: true,
    methods: ['GET', 'POST', 'PATCH', 'PUT', 'DELETE', 'OPTIONS'],
  })
);

app.use(express.json({ limit: '10kb' }));
app.use(express.urlencoded({ extended: true, limit: '10kb' }));

app.use(mongoSanitize({ replaceWith: '_' }));
app.use(hpp());

if (!config.isTest) {
  app.use(morgan(config.isProduction ? 'combined' : 'dev'));
}

app.use(config.apiPrefix, routes);

if (config.frontendDist) {
  mountFrontend(app, { distDir: config.frontendDist, apiPrefix: config.apiPrefix });
}

app.use(notFoundHandler);
app.use(errorHandler);

module.exports = app;
