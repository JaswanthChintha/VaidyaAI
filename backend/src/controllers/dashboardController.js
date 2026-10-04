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

/**
 * Module 27 - Health Dashboard.
 *
 *   GET /reports/:id/dashboard   the stored analysis, projected into the card
 *                                groups the spec names
 *
 * A READ MODEL, NOT A PIPELINE STAGE. Nothing here calls the ai-service, calls
 * a model, or reaches a clinical conclusion; it re-shapes what
 * `POST /reports/:id/analyze` already produced and stored. It is therefore not
 * separately rate-limited, for the same reason `/explanation` is not: the
 * expensive work happened once, behind `analysisLimiter`.
 *
 * A SIBLING OF `/report` AND `/explanation`, NOT A REPLACEMENT. `/analysis`
 * returns everything stored, `/report` the clinical deliverable, `/explanation`
 * the patient-facing layer; this returns the subset of all three that a
 * dashboard draws, already joined, so a renderer does not pull the extraction,
 * the feature map and both decision payloads to draw one screen.
 *
 * OWNERSHIP IS THE SAME CODE as every other report route - the identical
 * `ownerScopedFilter` + `assertCanAccess` pair with `OWNER_ONLY`, 404 before
 * 403 - so user B, an admin and a clinician all get the 404 a random id
 * produces. No `allowRoles` grant is passed and none should be: staff do not
 * read patient medical data through this endpoint.
 *
 * LOGGING: nothing here logs. Not a value, not a finding, not a filename.
 */

/** Filter matching only the caller's own reports. Throws if unauthenticated. */
const ownFilter = (req, base = {}) => ownerScopedFilter(req.user, { ...OWNER_ONLY, base });

/**
 * The `select: false` payloads this endpoint needs, AND NO MORE.
 *
 * Deliberately narrower than `analysisController.ANALYSIS_PROJECTION`: the
 * extraction, the engineered features, the raw validation verdict and both raw
 * decision payloads are not read here at all, because Modules 17-20 already
 * folded everything the cards need into `clinicalReport` - the laboratory
 * values with their Module 6 verdict, the evidence lines with the
 * rejected-feature join, and the fusion. Pulling the rest would drag the
 * largest and most sensitive documents in the collection through the app to
 * render a screen that never shows them.
 */
// `features` carries Module 5's `unmapped` list -- every parameter read off
// the page that this platform has no feature for. Without it the dashboard
// cannot tell the reader what it skipped.
// `extraction` carries each parameter's PRINTED reference interval and the
// laboratory's own high/low marking -- including for parameters this
// platform does not assess. Without it those markings are lost.
// `parameterGlossary` carries one plain-language description per test the
// LABORATORY flagged and this platform does not assess. It is generated from
// the test NAME alone -- no value, range or flag is ever sent -- so it says
// what the test measures and nothing about this patient. Without it the
// unassessed section lists names a reader has no way to interpret.
const DASHBOARD_PROJECTION =
  '+clinicalReport +patientExplanation +lifestyleGuidance +features +extraction +parameterGlossary';

/**
 * GET /reports/:id/dashboard
 *
 * 404 WHEN THERE IS NOTHING TO DRAW, AND THAT IS THE POINT. A report that was
 * never analysed, or whose report stage did not answer, has no dashboard - and
 * a synthesised empty one would be indistinguishable from the dashboard of a
 * report that genuinely found nothing. That is the fourth-case failure this
 * codebase refuses everywhere else (`overallStatus: null` is not `Healthy`),
 * and a dashboard is precisely where it would be rendered as a clean bill of
 * health. So the two cases are separated in the message, exactly as
 * `/report` separates them, and neither invents a card.
 *
 * `status` is not consulted for this decision: `uploaded`, `processing` and
 * `failed` all have `analysis.version === 0` or no stored `clinicalReport`, and
 * a `partial` run that DID produce a report has a perfectly good dashboard -
 * one whose `overall.caveat`, `document.pagesUnreadable` and `sourcesFailed`
 * say what was missing. Gating on status would hide those.
 */
const getDashboard = asyncHandler(async (req, res) => {
  const report = await Report.findOne(ownFilter(req, { _id: req.params.id })).select(
    DASHBOARD_PROJECTION
  );
  assertCanAccess(req.user, report, { ...OWNER_ONLY });

  const version = (report.analysis && report.analysis.version) || 0;
  // THE GATE IS THE SERVICE'S OWN PREDICATE, not a second spelling of it. A
  // bare `!report.clinicalReport` passes an array or a string, which
  // `buildDashboard` then rejects with a `TypeError` - a 500 and a stack trace
  // where the honest answer is that there is no clinical report here to draw.
  if (version === 0 || !analysisService.isUsableClinicalReport(report.clinicalReport)) {
    throw ApiError.notFound(
      version === 0
        ? 'This report has not been analysed yet. Run POST /reports/:id/analyze first.'
        : 'No clinical report was produced for this analysis, so there is no dashboard to show. See GET /reports/:id/analysis for which stage did not complete.'
    );
  }

  const dashboard = dashboardService.buildDashboard({
    clinicalReport: report.clinicalReport,
    // `null`, not absent, when a stage did not answer. Modules 23 and 26 are
    // separate stages and either can be missing while the report is intact -
    // the recommendations section reports that as a fact rather than as an
    // empty list, which would read as "there is nothing to recommend".
    explanationSet: report.patientExplanation === undefined ? null : report.patientExplanation,
    guidance: report.lifestyleGuidance === undefined ? null : report.lifestyleGuidance,
    engineeredFeatures: report.features === undefined ? null : report.features,
    extraction: report.extraction === undefined ? null : report.extraction,
    // `null`, not absent, for the same reason as the two above: a report
    // analysed before this stage existed has no glossary, and that is a
    // different fact from a glossary that described nothing.
    parameterGlossary:
      report.parameterGlossary === undefined ? null : report.parameterGlossary,
  });

  // DOES THE REPORT AGREE WITH THE READER'S PROFILE, AND WHICH DID THE
  // ANALYSIS USE? Since 2026-09-25 the sex and age the report prints are used
  // in place of the profile's (Module 5, `report_details`); an analysis from
  // before that used the profile. Either way a disagreement is said, because
  // it can mean the report is someone else's. Compared with the profile AS IT
  // STANDS -- the question is "is this yours". `not_checked` for a report
  // analysed before printed sex and age were read.
  //
  // NOT FOR SOMEONE ELSE's REPORT (2026-10-03): "is this yours" has been
  // answered -- no -- so the comparison would only restate it as a mismatch.
  // The page says the report is marked as someone else's instead.
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
    // The file the dashboard describes, so a renderer can title the screen
    // without a second request. Metadata only - `toPublicJSON` carries no
    // medical values and no storage key.
    report: report.toPublicJSON(),
    dashboard,
    identity,
  });
});

module.exports = { getDashboard };
