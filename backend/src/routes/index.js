'use strict';

const express = require('express');
const mongoose = require('mongoose');

const authRoutes = require('./authRoutes');
const profileRoutes = require('./profileRoutes');
const reportRoutes = require('./reportRoutes');
const timelineRoutes = require('./timelineRoutes');
const { sendSuccess, sendError } = require('../utils/apiResponse');
const config = require('../config/env');
const aiService = require('../services/aiServiceClient');

const router = express.Router();

const DB_STATES = ['disconnected', 'connected', 'connecting', 'disconnecting'];

/**
 * ai-service reachability, surfaced WITHOUT making this service's own liveness
 * depend on another process.
 *
 * `/health` must answer immediately and must keep answering when the Python
 * service is down - if it blocked on a cross-service probe, one unreachable
 * dependency would take the backend out of a load balancer that is only asking
 * whether the backend itself is alive. So `/health` reports the LAST KNOWN
 * verdict from this small cache and, at most, kicks off a refresh it never
 * awaits. `/health/ai` is the endpoint that actually probes, for an operator or
 * a readiness check that genuinely wants to wait.
 */
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

/** Test hook: forget the cached verdict. */
function resetAiHealthCache() {
  cachedAiHealth = null;
  aiHealthInFlight = null;
}

router.get('/health', (req, res) => {
  // Fire-and-forget. Never awaited, so a hung ai-service cannot slow this down.
  // Suppressed under NODE_ENV=test so the suite does not leave stray sockets.
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
      // `null` = not probed yet. Deliberately distinct from `false`.
      reachable: cachedAiHealth ? cachedAiHealth.reachable : null,
      lastCheckedAt: cachedAiHealth ? cachedAiHealth.checkedAt : null,
    },
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
  });
});

/**
 * GET /health/ai - actively probe the ai-service.
 *
 * Unauthenticated like `/health`, and like `/health` it discloses only
 * reachability, never a response body. 503 when configured but unreachable, so
 * a readiness check can act on it; 200 when reachable, and 200 with
 * `configured: false` on a deployment that deliberately runs without the
 * pipeline.
 */
router.get('/health/ai', async (req, res) => {
  // THROTTLED AND COALESCED. This route is unauthenticated and makes an
  // OUTBOUND request, so without a cache it would be a free amplifier: anyone
  // who can reach it could turn one cheap inbound request into one outbound
  // request against the ai-service indefinitely. A fresh verdict is reused, and
  // concurrent callers share a single in-flight probe, so the outbound rate is
  // bounded at one probe per AI_HEALTH_TTL_MS regardless of inbound load.
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

/**
 * Modules 28-30. A SIBLING OF `/reports`, not a child of it: a trend is a
 * property of the patient across their reports, not of any one report, and
 * there is no id in these URLs to tamper with - the owner comes from the
 * verified JWT, exactly as it does for `/profile/me`.
 *
 * Module 32's doctor summary is deliberately NOT here. It summarises ONE
 * report - the history only adds sections to it - so it is addressed by that
 * report's id and lives with the other views of a report, under
 * `/reports/:id/doctor-summary`.
 */
router.use('/timeline', timelineRoutes);

module.exports = router;
module.exports.resetAiHealthCache = resetAiHealthCache;
