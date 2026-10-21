'use strict';

const Report = require('../models/Report');
const Profile = require('../models/Profile');
const ApiError = require('../utils/ApiError');
const asyncHandler = require('../utils/asyncHandler');
const { sendSuccess } = require('../utils/apiResponse');
const { ownerScopedFilter, assertCanAccess, OWNER_ONLY } = require('../utils/ownership');
const aiService = require('../services/aiServiceClient');
const { valuesUsed } = require('../utils/printedIdentity');


const ownFilter = (req, base = {}) => ownerScopedFilter(req.user, { ...OWNER_ONLY, base });

const POPULATION_PROJECTION = '+featureValidation +features';

function measurementsFrom(featureValidation) {
  const valid = (featureValidation && featureValidation.valid) || {};
  return Object.keys(valid).map((name) => {
    const feature = valid[name] || {};
    return {
      feature: name,
      value: feature.value,
      unit: typeof feature.unit === 'string' ? feature.unit : undefined,
    };
  });
}

const getPopulationContext = asyncHandler(async (req, res) => {
  if (!aiService.isConfigured()) throw aiService.notConfigured();

  const report = await Report.findOne(ownFilter(req, { _id: req.params.id })).select(
    POPULATION_PROJECTION
  );
  assertCanAccess(req.user, report, { ...OWNER_ONLY });

  const version = (report.analysis && report.analysis.version) || 0;
  if (version === 0 || !report.featureValidation) {
    throw ApiError.notFound(
      version === 0
        ? 'This report has not been analysed yet. Run POST /reports/:id/analyze first.'
        : 'No validated feature set was stored for this analysis, so there is nothing to place in a population. See GET /reports/:id/analysis for which stage did not complete.'
    );
  }

  const measurements = measurementsFrom(report.featureValidation);
  if (measurements.length === 0) {
    throw ApiError.notFound(
      'This analysis accepted no reading, so there is no value to place in a population. See GET /reports/:id/analysis for why each reading was rejected.'
    );
  }

  const otherPerson = report.subject?.owner === 'other';
  let profile = null;
  if (!otherPerson) {
    profile = await Profile.findOne(ownFilter(req)).select('user age gender').lean();
    if (profile) assertCanAccess(req.user, profile, { ...OWNER_ONLY });
  }
  const fallback = otherPerson
    ? { age: report.subject.age, gender: report.subject.sex }
    : profile;

  const profileAge = fallback && Number.isFinite(fallback.age) ? fallback.age : undefined;
  const profileGender =
    fallback && typeof fallback.gender === 'string' && fallback.gender
      ? fallback.gender
      : undefined;

  const used = valuesUsed(report.features);
  const ageFromReport = used.ageSource === 'report_details' && used.ageYears !== null;
  const genderFromReport = used.sexSource === 'report_details' && used.sex !== null;
  const age = ageFromReport ? used.ageYears : profileAge;
  const gender = genderFromReport ? used.sex : profileGender;
  const typedSource = otherPerson ? 'entered' : 'profile';
  const sourceOf = (fromReport, value) =>
    fromReport ? 'report' : value !== undefined ? typedSource : null;
  const ageSource = sourceOf(ageFromReport, age);
  const genderSource = sourceOf(genderFromReport, gender);

  const populationContext = await aiService.populationContext({
    measurements,
    age,
    gender,
    patientRef: String(req.user.id ?? req.user._id),
    requestId: aiService.newRequestId(report._id.toString()),
  });

  const unmapped = Array.isArray(report.features?.unmapped) ? report.features.unmapped : [];
  const notCompared = [
    ...new Set(
      unmapped
        .map((item) => (item && typeof item.test_name === 'string' ? item.test_name.trim() : ''))
        .filter(Boolean)
    ),
  ];

  return sendSuccess(res, 200, {
    report: report.toPublicJSON(),
    notCompared,
    subject: {
      source:
        ageSource === 'report' && genderSource === 'report'
          ? 'report'
          : ageSource === 'report' || genderSource === 'report'
            ? 'mixed'
            : typedSource,
      ageSource,
      genderSource,
      otherPerson,
      profileExists: Boolean(profile),
      ageProvided: age !== undefined,
      genderProvided: gender !== undefined,
    },
    populationContext,
  });
});

module.exports = { getPopulationContext, measurementsFrom, POPULATION_PROJECTION };
