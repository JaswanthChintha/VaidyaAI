'use strict';

const Report = require('../models/Report');
const Profile = require('../models/Profile');
const ApiError = require('../utils/ApiError');
const asyncHandler = require('../utils/asyncHandler');
const { sendSuccess } = require('../utils/apiResponse');
const { ownerScopedFilter, assertCanAccess, OWNER_ONLY } = require('../utils/ownership');
const analysisService = require('../services/analysisService');
const dashboardService = require('../services/dashboardService');
const { compareWithProfile } = require('../utils/printedIdentity');


const ownFilter = (req, base = {}) => ownerScopedFilter(req.user, { ...OWNER_ONLY, base });

const DASHBOARD_PROJECTION =
  '+clinicalReport +patientExplanation +lifestyleGuidance +features +extraction +parameterGlossary';

const getDashboard = asyncHandler(async (req, res) => {
  const report = await Report.findOne(ownFilter(req, { _id: req.params.id })).select(
    DASHBOARD_PROJECTION
  );
  assertCanAccess(req.user, report, { ...OWNER_ONLY });

  const version = (report.analysis && report.analysis.version) || 0;
  if (version === 0 || !analysisService.isUsableClinicalReport(report.clinicalReport)) {
    throw ApiError.notFound(
      version === 0
        ? 'This report has not been analysed yet. Run POST /reports/:id/analyze first.'
        : 'No clinical report was produced for this analysis, so there is no dashboard to show. See GET /reports/:id/analysis for which stage did not complete.'
    );
  }

  const dashboard = dashboardService.buildDashboard({
    clinicalReport: report.clinicalReport,
    explanationSet: report.patientExplanation === undefined ? null : report.patientExplanation,
    guidance: report.lifestyleGuidance === undefined ? null : report.lifestyleGuidance,
    engineeredFeatures: report.features === undefined ? null : report.features,
    extraction: report.extraction === undefined ? null : report.extraction,
    parameterGlossary:
      report.parameterGlossary === undefined ? null : report.parameterGlossary,
  });

  let identity;
  if (report.subject?.owner === 'other') {
    identity = { status: 'other_person' };
  } else {
    const profile = await Profile.findOne(ownerScopedFilter(req.user, { ...OWNER_ONLY })).lean();
    identity = compareWithProfile({
      identity: report.printedIdentity || null,
      profile,
      features: report.features,
      reportDate: report.chronoDate,
    });
  }

  return sendSuccess(res, 200, {
    report: report.toPublicJSON(),
    dashboard,
    identity,
  });
});

module.exports = { getDashboard };
