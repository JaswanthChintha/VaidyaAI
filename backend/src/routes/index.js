'use strict';

const express = require('express');
const mongoose = require('mongoose');

const authRoutes = require('./authRoutes');
const profileRoutes = require('./profileRoutes');
const reportRoutes = require('./reportRoutes');
const timelineRoutes = require('./timelineRoutes');
const chatRoutes = require('./chatRoutes');
const { sendSuccess, sendError } = require('../utils/apiResponse');
const config = require('../config/env');
const aiService = require('../services/aiServiceClient');

const router = express.Router();

const DB_STATES = ['disconnected', 'connected', 'connecting', 'disconnecting'];

const AI_HEALTH_TTL_MS = 15000;
let cachedAiHealth = null;
let aiHealthInFlight = null;

function refreshAiHealth() {
  if (aiHealthInFlight) return aiHealthInFlight;
  aiHealthInFlight = aiService
    .health()
    .then((verdict) => {
      cachedAiHealth = verdict;
      return verdict;
    })
    .catch(() => cachedAiHealth)
    .finally(() => {
      aiHealthInFlight = null;
    });
  return aiHealthInFlight;
}

function isAiHealthStale() {
  if (!cachedAiHealth) return true;
  return Date.now() - Date.parse(cachedAiHealth.checkedAt) > AI_HEALTH_TTL_MS;
}

function resetAiHealthCache() {
  cachedAiHealth = null;
  aiHealthInFlight = null;
}

router.get('/health', (req, res) => {
  if (aiService.isConfigured() && !config.isTest && isAiHealthStale()) {
    refreshAiHealth().catch(() => {});
  }

  return sendSuccess(res, 200, {
    status: 'ok',
    service: 'vaidyaai-backend',
    modules: [
      'module-1-authentication',
      'module-2-patient-profile',
      'module-3-report-upload',
      'modules-4-5-analysis-orchestration',
      'module-27-dashboard',
      'modules-28-30-timeline-comparison-progress',
      'module-32-doctor-summary',
    ],
    database: DB_STATES[mongoose.connection.readyState] || 'unknown',
    aiService: {
      configured: aiService.isConfigured(),
      reachable: cachedAiHealth ? cachedAiHealth.reachable : null,
      lastCheckedAt: cachedAiHealth ? cachedAiHealth.checkedAt : null,
    },
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
  });
});

router.get('/health/ai', async (req, res) => {
  const verdict = (isAiHealthStale() ? await refreshAiHealth() : cachedAiHealth) || {
    configured: aiService.isConfigured(),
    reachable: false,
    error: 'AI_SERVICE_UNAVAILABLE',
    checkedAt: new Date().toISOString(),
  };

  if (verdict.configured && !verdict.reachable) {
    return sendError(
      res,
      503,
      verdict.error || 'AI_SERVICE_UNAVAILABLE',
      'The analysis service is not reachable',
      { aiService: verdict }
    );
  }
  return sendSuccess(res, 200, { aiService: verdict });
});

router.use('/auth', authRoutes);
router.use('/profile', profileRoutes);
router.use('/reports', reportRoutes);
router.use('/chat', chatRoutes);

router.use('/timeline', timelineRoutes);

module.exports = router;
module.exports.resetAiHealthCache = resetAiHealthCache;
