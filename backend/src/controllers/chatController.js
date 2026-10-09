'use strict';

const Report = require('../models/Report');
const asyncHandler = require('../utils/asyncHandler');
const { sendSuccess } = require('../utils/apiResponse');
const { ownerScopedFilter, assertCanAccess, OWNER_ONLY } = require('../utils/ownership');
const aiService = require('../services/aiServiceClient');
const analysisService = require('../services/analysisService');

/**
 * POST /api/v1/chat -- the chatbot (2026-10-09).
 *
 * A general question needs nothing but a signed-in user. A question asked on a
 * report's dashboard also names that report; it is loaded OWNER-SCOPED, so
 * another user's id matches nothing and the question is answered as a general
 * one rather than confirming the report exists. Only a compact summary of the
 * stored analysis is sent -- names, values, the report's printed ranges and
 * the topics' statuses -- never the file, the patient's name or the raw text.
 *
 * Nothing is stored: the question and the answer live only in the response.
 * LOGGING: none of the question, the context or the answer.
 */

const MAX_RESULTS = 60;
const MAX_TOPICS = 20;

const STATUS_WORDS = {
  INDICATED: 'Flagged',
  BORDERLINE: 'Borderline',
  NOT_INDICATED: 'Not flagged',
  INSUFFICIENT_DATA: 'Not assessed',
};

const clip = (value, max) => (value === undefined || value === null ? undefined : String(value).slice(0, max));

/** The compact, PHI-light context the ai-service is given for ONE report. */
function reportContext(clinicalReport) {
  if (!analysisService.isUsableClinicalReport(clinicalReport)) return null;
  const results = (clinicalReport.laboratory_values || [])
    .filter((v) => v && v.usable !== false && v.value !== null && v.value !== undefined)
    .slice(0, MAX_RESULTS)
    .map((v) => {
      const range =
        v.reference_range_raw ||
        (v.reference_low !== null && v.reference_low !== undefined &&
        v.reference_high !== null && v.reference_high !== undefined
          ? `${v.reference_low} - ${v.reference_high}`
          : undefined);
      return {
        name: clip(v.display_name || v.original_test_name || v.feature, 120),
        value: clip(v.value, 60),
        unit: clip(v.unit, 30),
        reference: clip(range, 80),
        flag: clip(v.flag, 30),
      };
    })
    .filter((r) => r.name);
  const topics = (clinicalReport.conditions || [])
    .slice(0, MAX_TOPICS)
    .map((c) => ({
      condition: clip(c.condition, 80),
      status: clip(STATUS_WORDS[c.status] || c.status, 40),
    }))
    .filter((t) => t.condition && t.status);
  const overall = clip(clinicalReport.overall && clinicalReport.overall.status_label, 80);
  // Undefined keys are dropped by JSON; the ai-service forbids unknown ones.
  return JSON.parse(JSON.stringify({ results, topics, overall }));
}

const ask = asyncHandler(async (req, res) => {
  const { question, reportId } = req.body;

  let report;
  if (reportId) {
    const doc = await Report.findOne(
      ownerScopedFilter(req.user, { ...OWNER_ONLY, base: { _id: reportId } })
    ).select('+clinicalReport');
    if (doc) {
      assertCanAccess(req.user, doc, { ...OWNER_ONLY });
      report = reportContext(doc.clinicalReport) || undefined;
    }
  }

  const answer = await aiService.chat({
    question,
    report,
    requestId: aiService.newRequestId(),
  });
  return sendSuccess(res, 200, { chat: answer, usedReport: Boolean(report) });
});

module.exports = { ask, reportContext };
