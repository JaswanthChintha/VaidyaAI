'use strict';

const Report = require('../models/Report');
const ApiError = require('../utils/ApiError');
const asyncHandler = require('../utils/asyncHandler');
const { sendSuccess } = require('../utils/apiResponse');
const { ownerScopedFilter, assertCanAccess, OWNER_ONLY } = require('../utils/ownership');
const aiService = require('../services/aiServiceClient');
const dashboardService = require('../services/dashboardService');
const historyService = require('../services/historyService');
const config = require('../config/env');

/**
 * Module 32 - the Doctor-Friendly Clinical Summary.
 *
 *   GET /reports/:id/doctor-summary
 *
 * THE COMMUNICATION BRIDGE, not a diagnosis. The spec's own framing: a
 * structured document a patient can hand to a healthcare professional, so the
 * conversation starts from what was actually measured rather than from a
 * remembered summary of a screen.
 *
 * ==========================================================================
 * A FIFTH VIEW OF ONE REPORT - WITH THE PATIENT'S HISTORY BESIDE IT
 * ==========================================================================
 *
 * `/analysis` returns everything stored, `/report` the clinical deliverable,
 * `/explanation` the patient-facing layer, `/dashboard` the read model a
 * screen draws. This returns the clinician-facing document, and it is the only
 * one of the five that is not a function of a single report: Module 32 takes
 * the stored `clinicalReport` verbatim AND the patient's report history, which
 * drive its trend and historical-comparison sections.
 *
 * The history changes NO clinical field of the document. Module 32 does not
 * re-run fusion, re-run the rule engine or re-derive the overall status - all
 * of that comes from `report` alone, so this document cannot disagree with the
 * report the patient was already shown. The history adds sections; it never
 * edits one.
 *
 * NO MODEL IS CALLED, on either side of the wire. Every sentence Module 32
 * emits comes from a fixed template table safety-scanned at import time, and
 * its request model has no field that can carry generated prose. That is why
 * this endpoint is cheap despite being the highest-stakes surface in the
 * product: a clinician may act on it.
 *
 * ==========================================================================
 * OWNERSHIP
 * ==========================================================================
 *
 * The report is loaded with the identical `ownerScopedFilter` +
 * `assertCanAccess` pair every other report route uses, with `OWNER_ONLY` and
 * no `allowRoles` grant, so a non-owner - an admin and a clinician included -
 * gets the 404 a random id produces, 404 before 403.
 *
 * THE FACT THAT THIS DOCUMENT IS MEANT FOR A CLINICIAN DOES NOT GIVE A
 * CLINICIAN ACCOUNT ACCESS TO IT. The patient requests it and shares it; the
 * platform does not hand a staff role a route into another person's medical
 * record. Any sharing mechanism is a separate, explicit, consented feature and
 * is not this endpoint.
 *
 * The history behind the trend and comparison sections is assembled by
 * `historyService` under the same scoping, and `?baseline=`/`?comparison=` -
 * if named - are re-checked against ownership there before they are sent.
 *
 * LOGGING: nothing here logs. Not a value, not a finding, not an id.
 */

/** Filter matching only the caller's own reports. Throws if unauthenticated. */
const ownFilter = (req, base = {}) => ownerScopedFilter(req.user, { ...OWNER_ONLY, base });

/**
 * The `select: false` payload this endpoint needs, AND NO MORE.
 *
 * Only `clinicalReport`. The extraction, the engineered features, the raw
 * validation verdict and both raw decision payloads are not read for THIS
 * report at all - Modules 17-20 already folded everything the document needs
 * into the clinical report, and Module 32's request model accepts nothing
 * else. Deliberately narrower than `analysisController.ANALYSIS_PROJECTION`
 * for the same reason `dashboardController` is: a history call already reads
 * up to `HISTORY_MAX_REPORTS` Module 6 verdicts, and adding six unread
 * payloads on top of that is exactly the cost the schema's `select: false`
 * exists to prevent.
 *
 * The patient explanation is deliberately NOT loaded. Module 23's output
 * cannot be posted to Module 32 - `DoctorSummaryRequest` has no field for it -
 * and that is a structural guarantee that model prose cannot reach a
 * clinician's page. Loading it here would serve no purpose but to put it one
 * careless edit away from doing so.
 */
// `+features +extraction` FOR THE PARAMETERS THIS PLATFORM DOES NOT ASSESS.
// The clinician document listed the four assessed values and nothing else; the
// laboratory had reported twenty-one. The rows and the laboratory's own flags
// live on these two fields, which is where the patient dashboard reads them.
const DOCTOR_SUMMARY_PROJECTION =
  '+clinicalReport +doctorNarrative +features +extraction';

/**
 * GET /reports/:id/doctor-summary
 *
 * 404 WHEN THERE IS NO CLINICAL REPORT TO SUMMARISE, exactly as `/report` and
 * `/dashboard` do, and for the same reason: a synthesised empty document would
 * be indistinguishable from the summary of a report that genuinely found
 * nothing, and this is the surface where that would be read as a clean bill of
 * health by someone qualified to act on it.
 *
 * 200 WITH NO TREND OR COMPARISON SECTION when the patient has only this one
 * analysed report. Those two sections are OPTIONAL on Module 32's contract and
 * they are absent WITH A STATED REASON (`trends.present` / `comparison.present`
 * are the fields to branch on, never the emptiness of the data beside them).
 * Absent-with-a-reason is the correct answer; "stable" would not be, and
 * Module 28 reserves that word for a change measured against a declared
 * stability band.
 */
const getDoctorSummary = asyncHandler(async (req, res) => {
  if (!aiService.isConfigured()) throw aiService.notConfigured();

  const report = await Report.findOne(ownFilter(req, { _id: req.params.id })).select(
    DOCTOR_SUMMARY_PROJECTION
  );
  assertCanAccess(req.user, report, { ...OWNER_ONLY });

  const version = (report.analysis && report.analysis.version) || 0;
  if (version === 0 || !report.clinicalReport) {
    throw ApiError.notFound(
      version === 0
        ? 'This report has not been analysed yet. Run POST /reports/:id/analyze first.'
        : 'No clinical report was produced for this analysis, so there is nothing to summarise. See GET /reports/:id/analysis for which stage did not complete.'
    );
  }

  // The SAME assembler the timeline endpoints use, so the history behind this
  // document and the history behind `/timeline/trends` cannot disagree about
  // which of the patient's reports count.
  const history = await historyService.assembleHistory({ user: req.user });
  const excluded = await historyService.describeExcluded({ user: req.user });

  const snapshotIds = new Set(history.snapshots.map((s) => s.report_id));
  const pair = await historyService.resolveNamedPair({
    user: req.user,
    baseline: req.query.baseline,
    comparison: req.query.comparison,
    snapshotIds,
  });

  const summary = await aiService.generateDoctorSummary({
    report: report.clinicalReport,
    // Opaque identity, so every clinical line in the document can be
    // attributed to a source document. The id and its `chronoDate` - never the
    // filename, which is user-supplied text.
    reportRef: report._id.toString(),
    reportDate: report.chronoDate ? new Date(report.chronoDate).toISOString() : undefined,
    // THE SUMMARISED REPORT SHOULD BE IN THIS HISTORY, and when it is not,
    // that fact is REPORTED rather than assumed away.
    //
    // The trend and comparison sections describe a series this report belongs
    // to. A series that omits it describes other reports under this report's
    // name - the document says "your creatinine is rising" about a trend
    // computed from reports that are not the one on the page.
    //
    // This comment used to assert that the inclusion rule guaranteed
    // membership and that "the sections say so" otherwise. AN AUDIT FOUND BOTH
    // HALVES FALSE, by two live routes:
    //
    //   (a) a report with a stored `clinicalReport` but no `featureValidation`
    //       passes this controller's 404 gate and is then excluded by
    //       INCLUSION_FILTER, so the subject is simply absent;
    //   (b) the history window is capped at HISTORY_MAX_REPORTS and takes the
    //       most RECENT N, so asking about an older report drops it - and the
    //       response said `excludedCount: 0`, naming nothing as missing.
    //
    // Two things changed. The ai-service now refuses both sections with
    // `SUBJECT_NOT_IN_HISTORY` when `report_ref` is not among the snapshots -
    // the backstop belongs there, at the layer that renders the claim, where
    // no caller's accounting can route around it. And this response now states
    // `subjectInHistory` so the omission is visible here too, rather than
    // being inferable only by comparing ids by hand.
    history: history.snapshots,
    patientRef: String(req.user.id ?? req.user._id),
    options: pair
      ? { baseline_ref: pair.baselineRef, comparison_ref: pair.comparisonRef }
      : undefined,
    requestId: aiService.newRequestId(report._id.toString()),
  });

  // THE WRITTEN VERSION, ONCE PER ANALYSIS.
  //
  // Cached on the report and keyed to `analysis.version`: a re-analysis makes
  // the stored prose describe findings that are no longer on the page, and
  // prose about the previous run is worse than no prose at all.
  //
  // EVERY FAILURE IS A NULL, NEVER AN ERROR. No model, a safety refusal, a
  // failed fact check, the ai-service being unreachable -- all of them leave
  // `narrative` absent and the client renders the composed passage it renders
  // today. A page that is one Gemini outage away from a 500 would be a worse
  // document than the one this replaces.
  const narrative = await resolveNarrative(report, version, summary);

  return sendSuccess(res, 200, {
    // The file the document describes. Metadata only - `toPublicJSON` carries
    // no medical values and no storage key.
    report: report.toPublicJSON(),
    // How much history the trend and comparison sections had to work with, and
    // what was left out. Without it, a document whose trend section is absent
    // because the patient has one report looks identical to one whose trend
    // section is absent because eight of their nine reports failed to analyse.
    history: {
      ...historyService.summariseHistory(history, excluded),
      // IS THE REPORT THIS DOCUMENT DESCRIBES ACTUALLY IN THAT HISTORY?
      //
      // False is an ordinary, reachable answer - the subject can be excluded
      // by the inclusion rule, or dropped by the cap when an older report is
      // asked about. It is stated explicitly because it was previously
      // inferable only by comparing `report._id` against the snapshot ids by
      // hand, and because `excludedCount: 0` actively suggested nothing was
      // missing. When this is false the ai-service withholds the trend and
      // comparison sections with `SUBJECT_NOT_IN_HISTORY`; every other
      // section is unaffected.
      subjectInHistory: snapshotIds.has(report._id.toString()),
    },
    requestedPair: pair
      ? { baseline: pair.baselineRef, comparison: pair.comparisonRef }
      : null,
    // Module 32's `DoctorSummaryData`, VERBATIM. Branch on `trends.present`
    // and `comparison.present`, and on `overall.any_assessed` - which being
    // false is NOT a clean bill of health.
    doctorSummary: summary,
    // WHAT THE LABORATORY REPORTED AND THIS PLATFORM DOES NOT ASSESS.
    //
    // The narrative states the COUNT; this is the list behind it, so a
    // clinician can read the values rather than be told how many they cannot
    // see. Built by the dashboard's own assembler, with no glossary: the
    // descriptions on the patient page answer "what is ESR", which is not a
    // question this reader has.
    //
    // A raised CRP, an SGPT of 101.9 and an ESR of 35 were all in here on
    // `Test 2.pdf` while the document above listed four values.
    unassessed: dashboardService.buildUnanalysedSection(
      report.features === undefined ? null : report.features,
      report.extraction === undefined ? null : report.extraction,
      null
    ),
    // Module 32 as prose, or null. `null` is an ordinary answer and the
    // client MUST be able to render without it -- see resolveNarrative.
    narrative,
  });
});

/**
 * The cached narrative, or a fresh one, or null.
 *
 * Never throws. This is a presentation improvement on a document that already
 * renders without it, so a failure here must cost nothing: the catch is
 * deliberate and the reason is logged rather than surfaced.
 */
async function resolveNarrative(report, version, summary) {
  const cached = report.doctorNarrative;
  // A REFUSAL IS CACHED TOO, and deliberately: a safety rejection costs two
  // model calls, and retrying it on every page view would spend a day's quota
  // on one reader. `model_unavailable` is the exception -- that is a
  // configuration state, not an answer about this report, and caching it would
  // leave the page permanently without prose after a key outage.
  if (
    cached
    && cached.analysisVersion === version
    && cached.outcome
    && cached.outcome !== 'model_unavailable'
  ) {
    return cached;
  }

  let written = null;
  try {
    written = await aiService.writeClinicianSummary({
      summary,
      requestId: aiService.newRequestId(report._id.toString()),
    });
  } catch (err) {
    // Correlation only: a stage, an opaque id, no body. The same shape
    // aiServiceClient.logFailure uses, and silent under test.
    if (!config.isTest) {
      // eslint-disable-next-line no-console
      console.warn(
        `[narrative] reportId=${report._id} outcome=unavailable ${err.message}`
      );
    }
    return null;
  }
  if (!written || typeof written !== 'object') return null;

  const stored = { ...written, analysisVersion: version };
  // Persisted best-effort. A write failure means the next request writes it
  // again, which is a wasted call and not a broken page.
  try {
    await Report.updateOne(
      { _id: report._id },
      { $set: { doctorNarrative: stored } }
    );
  } catch (err) {
    if (!config.isTest) {
      // eslint-disable-next-line no-console
      console.warn(`[narrative] reportId=${report._id} outcome=not_cached ${err.message}`);
    }
  }
  return stored;
}

module.exports = { getDoctorSummary };
