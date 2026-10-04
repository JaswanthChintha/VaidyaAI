'use strict';

const Report = require('../models/Report');
const Profile = require('../models/Profile');
const ApiError = require('../utils/ApiError');
const asyncHandler = require('../utils/asyncHandler');
const { sendSuccess } = require('../utils/apiResponse');
const { ownerScopedFilter, assertCanAccess, OWNER_ONLY } = require('../utils/ownership');
const aiService = require('../services/aiServiceClient');
const { valuesUsed } = require('../utils/printedIdentity');

/**
 * Module 31 - Population Context and Percentiles.
 *
 *   GET /reports/:id/population-context
 *
 * "Among people of the same sex and a similar age in a real, published health
 * survey, how common is a value like this one?" The tables are survey-weighted
 * NHANES (CDC/NCHS) percentiles, and the answer is always a BAND between two
 * adjacent published cut-points - never an interpolated percentile, because no
 * such number is computed.
 *
 * ==========================================================================
 * A SIXTH VIEW OF ONE REPORT
 * ==========================================================================
 *
 * `/analysis` returns everything stored, `/report` the clinical deliverable,
 * `/explanation` the patient-facing layer, `/dashboard` the read model a screen
 * draws, `/doctor-summary` the clinician-facing document. This one places that
 * report's validated readings in a population - and it is the only one of the
 * six whose answer depends on WHO the patient is as well as what the report
 * says, which is what the whole of the section below is about.
 *
 * IT IS NOT AN INTERPRETATION. Module 31 makes no clinical claim: no risk word,
 * no normal/abnormal judgement, no recommendation. Module 8 owns "is this value
 * in range"; this owns only "how common is this value". A response's
 * `what_this_does_not_mean` says so in the patient's own words and is passed
 * through with everything else.
 *
 * ==========================================================================
 * WHERE AGE AND GENDER COME FROM - THE ONE THING THIS FILE MUST GET RIGHT
 * ==========================================================================
 *
 * THE SAME SEX AND AGE THE ANALYSIS USED (2026-10-02). Since 2026-09-25
 * Module 5 uses the sex and age PRINTED ON THE REPORT in place of the
 * profile's (`report_details`), so every other screen judges a 63-year-old's
 * report as a 63-year-old's. This endpoint kept reading the profile and scored
 * that same report against 20-29-year-olds -- the account owner's group, not
 * the person whose blood it is. Now, per field: a value the analysis took from
 * the report is used; otherwise the AUTHENTICATED user's own Module 2 profile,
 * loaded through the same owner-scoped filter as the report, exactly as before.
 *
 * NEVER from a query parameter or the request body. The printed values are
 * read from the stored analysis, which the caller cannot set.
 *
 * The reason is that age and sex do not describe the value - they CHOOSE the
 * cohort it is scored against. A caller who could set them could score any
 * value against any group and read back a percentile that looks precise and
 * describes somebody else. There is deliberately no parameter to do it with:
 * the endpoint takes a report id and nothing else.
 *
 * ==========================================================================
 * ABSENCE IS A REFUSAL, NEVER A DEFAULT - AND THE REFUSAL IS THE PRODUCT
 * ==========================================================================
 *
 * A missing age is omitted from the request and comes back as
 * `AGE_NOT_PROVIDED`. A gender of `other` or `prefer_not_to_say`, an
 * unrecognised one, or a profile without one, comes back as
 * `SEX_COHORT_NOT_AVAILABLE`. An age below the tables' adult range comes back
 * as `AGE_BELOW_ADULT_TABLE`, which the service keeps separate precisely
 * because scoring a child against an adult table is a clinical error rather
 * than a miss.
 *
 * EVERY ONE OF THOSE IS PASSED THROUGH VERBATIM - the `reason_code`, the
 * reviewed `message`, and the `available: false` that carries them. Nothing
 * here re-interprets, flattens, or falls back to an unmatched cohort. Module 31
 * publishes no all-adults distribution to fall back TO, and that is a deliberate
 * design decision rather than a gap: haemoglobin and creatinine differ enough
 * between the published strata that an unmatched percentile would be a
 * different claim in the same words.
 *
 * A STATED GENDER IS NEVER COERCED INTO A BINARY CATEGORY to force a lookup.
 * Module 2 stores the user's real answer (`male | female | other |
 * prefer_not_to_say`) for exactly this reason, and it is forwarded verbatim -
 * this file contains no mapping table, no `=== 'male'` test and no fallback
 * branch. Both halves of the answer survive: the service reports
 * `gender_recognised` (we understood you) separately from
 * `sex_cohort_available` (the survey has a group for you), which are different
 * things to say to a person.
 *
 * ==========================================================================
 * OWNERSHIP
 * ==========================================================================
 *
 * The identical `ownerScopedFilter` + `assertCanAccess` pair every other report
 * route uses, with `OWNER_ONLY` and NO `allowRoles` grant, so user B, an admin
 * and a clinician all get the 404 a random id produces, 404 before 403. The
 * profile is loaded under the same scoping, so there is no path by which one
 * user's report could be scored against another user's cohort.
 *
 * LOGGING: nothing here logs. Not a value, not a percentile, not an age, not a
 * gender, not an id.
 */

/** Filter matching only the caller's own documents. Throws if unauthenticated. */
const ownFilter = (req, base = {}) => ownerScopedFilter(req.user, { ...OWNER_ONLY, base });

/**
 * The `select: false` payload this endpoint needs, AND NO MORE.
 *
 * `featureValidation` - Module 6's verdict, which is the one place a value
 * this platform is willing to stand behind lives - and `features`, read ONLY
 * for which sex and age the analysis used and where each came from (see the
 * header). No value is taken from `features` into `measurements`. The
 * extraction, both decision payloads, the clinical report, the patient
 * explanation and the guidance are not read at all. Same restraint, and the same reason, as
 * `dashboardController` and `doctorSummaryController`.
 */
const POPULATION_PROJECTION = '+featureValidation +features';

/**
 * The report's validated readings, in Module 31's `measurements` shape.
 *
 * ONLY `valid` IS READ. `rejected` holds values Module 6 refused to trust, and
 * a refused value must not acquire a percentile through a side door - the same
 * rule `historyService` states about `TimelineReportInput`. `questionable` needs
 * no separate handling: it is a SUBSET VIEW of `valid` on Module 6's contract,
 * so those readings are already here exactly once.
 *
 * NOTHING IS FILTERED BY FEATURE. Every entry is forwarded, including the ones
 * Module 31 does not cover (`blood_glucose` and `triglycerides` are excluded by
 * name, because fasting status is recorded nowhere in this pipeline) and the
 * ones that are not measurements at all (`age`, `gender`, `hypertension`,
 * `heart_disease`, `smoking_history`). Each comes back as its own
 * `available: false` entry carrying the service's own reason and wording.
 * Deciding here which features are covered would be a second copy of the
 * service's coverage table, free to drift from it, and a feature dropped by
 * that copy would be indistinguishable from a feature the report never had.
 *
 * VALUE AND UNIT ARE COPIED, NEVER CONVERTED OR ASSUMED. A unit-less reading is
 * forwarded without one and answered with `UNIT_NOT_PROVIDED`; supplying a
 * canonical unit on its behalf here would be this backend inventing the one
 * fact the refusal exists to report. Non-numeric values (a `gender` string, a
 * `heart_disease` boolean) are forwarded as they are and answered with the
 * service's own code - `value` is typed `Any` on that contract for this reason.
 */
function measurementsFrom(featureValidation) {
  const valid = (featureValidation && featureValidation.valid) || {};
  return Object.keys(valid).map((name) => {
    const feature = valid[name] || {};
    return {
      // The map key is the canonical name and is what every other consumer
      // keys on; `feature.name` is the same string on Module 6's contract.
      feature: name,
      value: feature.value,
      // `null` and `undefined` both mean "no unit was established". Either is
      // sent as an absent unit; the service refuses rather than assuming one.
      unit: typeof feature.unit === 'string' ? feature.unit : undefined,
    };
  });
}

/**
 * GET /reports/:id/population-context
 *
 * 404 WHEN THERE IS NOTHING TO PLACE, in two distinguishable cases, and for the
 * reason `/report`, `/dashboard` and `/doctor-summary` all 404 rather than
 * synthesising an empty document: an answer with no values in it would be
 * indistinguishable from an answer that found nothing to say.
 *
 *   - no analysis has ever succeeded (`analysis.version === 0`), or the
 *     validation stage did not store a verdict;
 *   - a verdict exists but Module 6 accepted no reading in it, so the report
 *     contributes no value at all.
 *
 * THE SECOND CASE IS NOT A MODULE 31 REFUSAL AND IS NOT DRESSED UP AS ONE. The
 * service's request contract refuses an empty measurement list outright ("an
 * empty request would return an empty answer that looks like a service fault"),
 * so there is no per-feature reason code to pass through here; inventing one in
 * this backend's own words would be exactly the second vocabulary the timeline
 * endpoints go out of their way not to create. The message says which case it
 * is and points at `/analysis`, where the rejection reasons already live.
 *
 * 200 IN EVERY OTHER CASE, INCLUDING WHEN NO COHORT COULD BE MATCHED. A patient
 * with no age on their profile, or one whose gender the published survey has no
 * stratum for, gets an ordinary 200 whose entries are `available: false` with a
 * reason code and reviewed copy. That is an answer, not a failure, and it is the
 * answer this module was built to give.
 */
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

  // THE SUBJECT. Loaded under the caller's own scope, and re-checked even
  // though the query was already scoped - the same deliberate redundancy every
  // report route applies, so a future widened filter still denies.
  //
  // A MISSING PROFILE IS NOT A 404. `assertCanAccess` would turn an absent
  // document into one, and that would be wrong twice over: the report exists
  // and is readable, and "we do not know your age" is a refusal Module 31
  // already words better than this file could. So the ownership re-check runs
  // only over a document that was actually found.
  // SOMEONE ELSE's REPORT (2026-10-03): the account profile is not read at
  // all. Its place is taken by the age and sex typed for this report, which
  // the analysis used under the same `patient_profile` source -- so the
  // "fallback" below is the typed values, never the account holder's.
  const otherPerson = report.subject?.owner === 'other';
  let profile = null;
  if (!otherPerson) {
    profile = await Profile.findOne(ownFilter(req)).select('user age gender').lean();
    if (profile) assertCanAccess(req.user, profile, { ...OWNER_ONLY });
  }
  const fallback = otherPerson
    ? { age: report.subject.age, gender: report.subject.sex }
    : profile;

  // Neither field is defaulted, coerced or inferred. `Number.isFinite` rather
  // than a truthiness test, so a real age of 0 is sent and an absent one is
  // omitted; the gender string is forwarded exactly as Module 2 stored it.
  const profileAge = fallback && Number.isFinite(fallback.age) ? fallback.age : undefined;
  const profileGender =
    fallback && typeof fallback.gender === 'string' && fallback.gender
      ? fallback.gender
      : undefined;

  // A value the analysis took from the REPORT wins, field by field -- the
  // cohort must describe the person the values belong to. Anything else
  // (printed nothing, or an analysis from before printed values were read)
  // falls back to the profile exactly as before.
  const used = valuesUsed(report.features);
  const ageFromReport = used.ageSource === 'report_details' && used.ageYears !== null;
  const genderFromReport = used.sexSource === 'report_details' && used.sex !== null;
  const age = ageFromReport ? used.ageYears : profileAge;
  const gender = genderFromReport ? used.sex : profileGender;
  // 'entered' for a value typed for someone else's report: it is not the
  // account profile, and saying "profile" would claim it was.
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

  // THE TESTS THIS PLATFORM DOES NOT ASSESS, BY NAME ONLY (2026-10-02). They
  // have no canonical feature, so they never reach Module 31 and the page
  // listed sixteen comparisons with no word about ESR, CRP, SGPT, TSH or the
  // average glucose printed on the same report -- "not compared" rendering as
  // nothing. The same source the dashboard's unanalysed section reads
  // (`report.features.unmapped`); names only, no values, so this endpoint
  // carries no medical data it did not carry before.
  const unmapped = Array.isArray(report.features?.unmapped) ? report.features.unmapped : [];
  const notCompared = [
    ...new Set(
      unmapped
        .map((item) => (item && typeof item.test_name === 'string' ? item.test_name.trim() : ''))
        .filter(Boolean)
    ),
  ];

  return sendSuccess(res, 200, {
    // The file the comparison describes. Metadata only - `toPublicJSON` carries
    // no medical values and no storage key.
    report: report.toPublicJSON(),
    notCompared,
    // WHERE THE COHORT CAME FROM - no age, no gender, no value. Without it,
    // "no profile at all" and "a profile that answered `prefer_not_to_say`"
    // produce the same `SEX_COHORT_NOT_AVAILABLE` and a reader cannot tell
    // which one to act on. `ageSource` / `genderSource` are 'report' (printed
    // on the report, as the analysis used), 'profile', or null (neither).
    // `source` summarises the two: 'report', 'profile' or 'mixed'.
    subject: {
      source:
        ageSource === 'report' && genderSource === 'report'
          ? 'report'
          : ageSource === 'report' || genderSource === 'report'
            ? 'mixed'
            : typedSource,
      ageSource,
      genderSource,
      // Someone else's report (2026-10-03): the account profile was not used,
      // so "fill in your details" is not the remedy for a missing age or sex.
      otherPerson,
      profileExists: Boolean(profile),
      ageProvided: age !== undefined,
      genderProvided: gender !== undefined,
    },
    // Module 31's `PopulationContextData`, VERBATIM. `available` is the field
    // to branch on, per feature, and it is never `comparison`: an unavailable
    // entry has no `comparison` object at all, so it cannot hold a value, a
    // percentile or an empty band that a template would render as "0th".
    // `reason_code` and `message` arrive exactly as the service wrote them.
    populationContext,
  });
});

module.exports = { getPopulationContext, measurementsFrom, POPULATION_PROJECTION };
