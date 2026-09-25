'use strict';

const Report = require('../models/Report');
const config = require('../config/env');
const ApiError = require('../utils/ApiError');
const { ownerScopedFilter, assertCanAccess, OWNER_ONLY } = require('../utils/ownership');
const { comparePair } = require('../utils/printedIdentity');

/**
 * Modules 28-30 and 32 - the patient's REPORT HISTORY, assembled once.
 *
 * ==========================================================================
 * WHAT THIS IS
 * ==========================================================================
 *
 * Everything else in this backend answers questions about ONE report. Trends
 * (28), comparison (29), the progress score (30) and the doctor-friendly
 * summary (32) all ask what has changed ACROSS a patient's reports, and all
 * four take their history in one shared shape - `TimelineReportInput`, defined
 * in `ai-service/app/schemas/timeline.py`:
 *
 *   { report_id, chrono_date, validated: <Module 6's data object> }
 *
 * This module is the single place that turns Mongo rows into that shape. Four
 * endpoints, one assembler: a second projection of the same reports would be a
 * second thing to get wrong, and the two could disagree about which reports a
 * patient's timeline contains - which would show up as a trend and a progress
 * score computed over different series.
 *
 * IT CALLS NOTHING AND COMPUTES NO CLINICAL JUDGEMENT. No model, no
 * ai-service call, no derived value. It selects rows, states why it excluded
 * the ones it excluded, and copies stored payloads through untouched. Which
 * feature is improving, whether two readings are comparable, and what counts
 * as "stable" are all decided on the Python side, where the canonical unit
 * table and the polarity declarations live. Comparing two stored values here
 * would be exactly the "silently corrupts data across a boundary" defect this
 * project audits for: 6.5 and 48 are the same HbA1c.
 *
 * ==========================================================================
 * WHY THE ORDERING QUERY LOOKS THE WAY IT DOES
 * ==========================================================================
 *
 * `Report.chronoDate` exists, and `{ user: 1, chronoDate: -1, _id: -1 }` is
 * indexed, for exactly this module - see the Report schema's own comment.
 * `chronoDate` is `reportDate ?? uploadedAt` MATERIALISED at write time, so a
 * patient uploading three years of history in one sitting still gets a
 * timeline ordered by when the labs were drawn rather than by when they hit
 * the server.
 *
 * The query below therefore sorts on `{ chronoDate: -1, _id: -1 }` - the
 * index's own declared direction, so it is an index-covered scan and not a
 * sort - and the result is reversed in memory into the oldest-first order a
 * reader expects. `_id` is the tiebreaker for reports that share a
 * `chronoDate`, which is the normal case for a bulk upload.
 *
 * `sequence` is deliberately NOT sent to the ai-service. Its purpose there is
 * to break `chrono_date` ties, and the service's fallback tiebreak - ascending
 * `report_id` - is byte-for-byte the same ordering our `_id` tiebreak
 * produces, because a Mongo ObjectId's hex string sorts in the same order as
 * the ObjectId itself. Sending a `sequence` derived from our own array index
 * would make the answer depend on the order this backend happened to serialise
 * the array in, which is precisely what both sides are trying to avoid.
 *
 * ==========================================================================
 * PHI
 * ==========================================================================
 *
 * Nothing here logs. Not a value, not a finding, not a filename, not a count.
 * The snapshots carry laboratory values because that is what a trend is
 * computed from, but they leave this process only over the same authenticated,
 * service-keyed channel every other stage uses.
 */

// ---------------------------------------------------------------- inclusion --

/**
 * WHY A REPORT IS NOT ON THE TIMELINE. Fixed machine codes of our own, from
 * this table and nowhere else - the same construction that makes
 * `statusMessage` and `analysis.stages` structurally PHI-safe. Never built
 * from a service response, never from user input.
 */
const EXCLUSION_REASONS = Object.freeze({
  /**
   * `analysis.version === 0` - no analysis has ever succeeded for this report.
   * Covers `uploaded` and `processing` (nothing has run yet) and a `failed`
   * first attempt (extraction or feature engineering is load-bearing, so a
   * failure there stores nothing at all).
   */
  NOT_ANALYSED: 'NOT_ANALYSED',
  /**
   * An analysis DID succeed but stored no Module 6 verdict, so this report has
   * no validated feature set. That is the `partial` case where validation
   * itself was the stage that failed: features were engineered, but nothing
   * downstream was allowed to run against unvalidated input, and
   * `featureValidation` was explicitly unset rather than left stale.
   *
   * There is nothing to put on a timeline for such a report. `validated` is
   * the ONLY feature source `TimelineReportInput` accepts from this backend,
   * and substituting the raw `features` payload would hand a trend calculation
   * readings that Module 6 never approved.
   */
  NO_VALIDATED_FEATURES: 'NO_VALIDATED_FEATURES',
});

/**
 * THE INCLUSION RULE, STATED ONCE.
 *
 * A report enters a timeline if and only if BOTH hold:
 *
 *   1. `analysis.version > 0`  - at least one analysis has succeeded for it.
 *   2. `featureValidation` is stored - Module 6 produced a verdict, which is
 *      the one feature shape the history contract accepts.
 *
 * Consequences worth being explicit about, because each one is a decision:
 *
 * `status` IS NOT CONSULTED. Three reasons.
 *   - `partial` reports are INCLUDED when they satisfy (2). A partial run is
 *     one where validation succeeded and the rules or the ML predictors did
 *     not; its features are exactly as validated as a `processed` report's,
 *     and excluding them would silently shorten a timeline over a failure that
 *     has nothing to do with the readings.
 *   - `partial` reports are EXCLUDED when validation was itself the failed
 *     stage, and (2) is what excludes them - the same test, not a special
 *     case.
 *   - `failed` reports may still be included. `runAnalysis`'s failure path
 *     writes only status bookkeeping and never touches the stored payloads or
 *     `analysis.version`, so a report that analysed successfully and then
 *     failed a LATER re-run still holds a real, complete Module 6 verdict of
 *     its own document. Dropping it would remove a genuine reading from the
 *     series because of a subsequent unrelated failure. The report's `status`
 *     travels with it in the response so this is visible rather than assumed.
 *
 * A REPORT WITH NO USABLE FEATURES IS STILL INCLUDED. If Module 6 rejected
 * every reading, `validated.valid` and `validated.questionable` are empty. It
 * is still sent, because Module 28 renders it as a `TimelineGap` carrying the
 * reason each feature was unavailable - which is strictly more informative
 * than the report vanishing from the series. A gap has no `value` field on
 * either side of the wire, so it can never be read back as a zero.
 */
const INCLUSION_FILTER = Object.freeze({
  'analysis.version': { $gt: 0 },
  featureValidation: { $exists: true, $ne: null },
});

/**
 * Fields loaded for every row in the examined window.
 *
 * NARROW ON PURPOSE. `featureValidation` is the only `select: false` payload
 * asked for; `extraction`, `features`, `ruleDecisions`, `mlDecisions`,
 * `clinicalReport`, `patientExplanation` and `lifestyleGuidance` are NOT read
 * here at all. `GET /reports` already lists up to 100 rows and the schema
 * keeps those payloads unselected precisely so a listing cannot drag them
 * through the app; a history call touches up to `config.history.maxReports`
 * rows at once, so the same restraint matters more here, not less.
 *
 * `user` is selected because the loaded rows are re-checked against the caller
 * even though the query was already owner-scoped - the same deliberate
 * redundancy every other report route applies.
 */
/*
 * `reportDate` IS CARRIED BESIDE `chronoDate`, AND THE DIFFERENCE IS THE POINT.
 *
 * `chronoDate` is `reportDate ?? uploadedAt` -- a materialised SORT KEY, and
 * correct as one. But it is never absent, so a consumer holding only that
 * cannot tell a report dated by the person who uploaded it from one dated by
 * the clock when they left the field blank. Both arrive as a date.
 *
 * FOUND ON THE REAL PAGE, 2026-09-19. A report printed 13 September, uploaded
 * on the 19th with the optional date blank, was labelled `9/19/2026 —
 * Test 3.pdf` in the comparison picker and `9/19/2026` on the reports list.
 * **The upload clock was being presented as the date on the document.**
 *
 * Sending the raw `reportDate` -- null when none was given -- lets the screen
 * say which it is. Nothing about ordering changes; `chronoDate` remains the
 * sort key and `chrono_date` still goes to the ai-service unchanged.
 */
//
// `printedDate` TRAVELS WITH IT FOR THE SAME REASON (2026-09-24): the typed
// date and the date the document prints can disagree -- two reports printing
// 05-Sep-2026 were typed as the 9th and the 11th -- and a picker holding only
// one of them cannot say so.
const HISTORY_PROJECTION =
  'user chronoDate reportDate printedDate printedDateStatus status analysis.version +featureValidation';

// ------------------------------------------------------------------ assembly --

/**
 * Assemble one patient's report history.
 *
 * @param {object} args
 * @param {{id?: *, _id?: *, role?: string}} args.user The AUTHENTICATED user.
 *        Ownership is enforced here, not by the caller: `ownerScopedFilter`
 *        throws rather than building an unscoped filter when there is no
 *        identity, and no `allowRoles` grant is passed, so no role - admin or
 *        clinician included - can read another patient's history through this
 *        function.
 * @returns {Promise<{
 *   snapshots: object[],  // TimelineReportInput[], OLDEST FIRST
 *   included: {reportId: string, chronoDate: Date,
 *              reportDate: Date|null, printedDate: Date|null,
 *              printedDateStatus: string|null, status: string}[],
 *   totalReports: number, examined: number, includedCount: number,
 *   cap: number, truncated: boolean,
 *   window: {from: Date, to: Date}|null
 * }>}
 *
 * There is deliberately NO `excluded` key here. This block used to document
 * one, and it was never returned - exclusions come from `describeExcluded`,
 * a separate and optional query. A caller trusting the old doc read
 * `undefined` and would reasonably have rendered "nothing was excluded",
 * which is absence quietly becoming a reassuring value in the one place
 * built to prevent exactly that.
 */
async function assembleHistory({ user }) {
  const cap = config.history.maxReports;
  const ownFilter = (base = {}) => ownerScopedFilter(user, { ...OWNER_ONLY, base });

  // How many reports this patient has AT ALL, so the response can say
  // "considered N, included M" rather than leaving a short timeline
  // indistinguishable from a patient with little history. Index-covered on the
  // leading `user` key of `{ user, chronoDate, _id }`.
  const totalReports = await Report.countDocuments(ownFilter());

  // THE WINDOW IS THE MOST RECENT `cap` REPORTS, NOT THE OLDEST.
  //
  // A cap has to drop something. Dropping the oldest keeps the series that a
  // trend is actually read off; dropping the newest would answer a question
  // about the patient's past while claiming to describe their present, which
  // is the more dangerous of the two failures.
  //
  // `cap + 1` rows are requested so truncation can be reported EXACTLY rather
  // than guessed: getting cap+1 back proves an eligible report was left out,
  // and getting cap or fewer proves none was. Inferring it from
  // `rows.length === cap` would call a patient with exactly `cap` reports
  // truncated, and comparing against the total report count would call a
  // patient with many unanalysed reports truncated. The extra row is
  // discarded, not sent.
  const rows = await Report.find(ownFilter(INCLUSION_FILTER))
    .select(HISTORY_PROJECTION)
    .sort({ chronoDate: -1, _id: -1 })
    .limit(cap + 1)
    .lean();

  const truncated = rows.length > cap;
  if (truncated) rows.length = cap;

  // Deliberately redundant: the query above cannot return another user's row,
  // and this re-checks each one anyway. Same belt-and-braces reasoning as
  // every controller that re-checks an already owner-scoped `findOne` - a
  // future widened filter still denies.
  for (const row of rows) assertCanAccess(user, row, { ...OWNER_ONLY });

  // Back to oldest-first for the caller. The service sorts the array itself, so
  // this is for the response's own report list rather than for the analysis.
  rows.reverse();

  const snapshots = [];
  const included = [];
  for (const row of rows) {
    const reportId = String(row._id);
    snapshots.push({
      report_id: reportId,
      // ISO-8601 with an explicit offset. `chronoDate` is a real Date and the
      // far side reads a naive datetime as UTC, so sending the offset removes
      // the only way the two could disagree about a report's position.
      chrono_date: new Date(row.chronoDate).toISOString(),
      // Module 6's data object, VERBATIM. Not sliced, not re-keyed, not
      // filtered: `ValidatedFeatureSetInput` reads `valid`, `questionable`
      // AND `rejected`, and it is the `rejected` map that lets a gap say why a
      // reading is missing instead of the report simply having no point.
      validated: row.featureValidation,
    });
    included.push({
      reportId,
      chronoDate: row.chronoDate,
      // NULL WHEN THE PERSON GAVE NO DATE, so a screen can say "uploaded on"
      // instead of printing the upload clock as the date on the report. See
      // HISTORY_PROJECTION. Explicitly null rather than absent: the two mean
      // the same here and one of them is easy to read as "not sent".
      reportDate: row.reportDate || null,
      // The date the document prints, when it was READ. Null otherwise, and
      // `printedDateStatus` says why -- null status meaning nobody looked.
      printedDate: row.printedDate || null,
      printedDateStatus: row.printedDateStatus || null,
      // Carried so a `failed` or `partial` report on the timeline is visible
      // as such - see the inclusion rule above.
      status: row.status,
    });
  }

  return {
    snapshots,
    included,
    includedCount: included.length,
    // Every report the patient owns, whether or not it could contribute.
    totalReports,
    // How many rows the window actually examined.
    examined: rows.length,
    cap,
    // TRUE only when an ELIGIBLE report was dropped by the cap - proven by the
    // cap+1 probe above, not inferred from the total report count.
    truncated,
    window: included.length
      ? { from: included[0].chronoDate, to: included[included.length - 1].chronoDate }
      : null,
  };
}

/**
 * Why the reports that are NOT on the timeline are not on it.
 *
 * A SEPARATE, OPTIONAL QUERY, run only by endpoints that report it. It reads
 * the complement of `INCLUSION_FILTER` over the same owner scope and loads NO
 * payload at all - just enough to attribute a reason code to a report id.
 * Kept apart from `assembleHistory` so the expensive path (which pulls Module 6
 * verdicts) is never widened to cover reports that by definition have none.
 *
 * @param {object} args
 * @param {object} args.user The authenticated user.
 * @param {number} [args.limit] Cap on the rows returned; the count is exact
 *        regardless, only the itemised list is capped.
 */
async function describeExcluded({ user, limit = 50 }) {
  const filter = ownerScopedFilter(user, {
    ...OWNER_ONLY,
    base: {
      $or: [
        { 'analysis.version': { $lte: 0 } },
        { 'analysis.version': { $exists: false } },
        { featureValidation: { $exists: false } },
        { featureValidation: null },
      ],
    },
  });

  const [count, rows] = await Promise.all([
    Report.countDocuments(filter),
    Report.find(filter)
      // No payload. `featureValidation` is asked for ONLY as an existence test
      // and these rows are the ones that do not have it, so nothing large is
      // read; the field is not selected at all.
      .select('user chronoDate status analysis.version')
      .sort({ chronoDate: -1, _id: -1 })
      .limit(Math.max(0, limit))
      .lean(),
  ]);

  for (const row of rows) assertCanAccess(user, row, { ...OWNER_ONLY });

  const reports = rows.map((row) => ({
    reportId: String(row._id),
    chronoDate: row.chronoDate,
    status: row.status,
    reasonCode:
      (row.analysis && row.analysis.version) > 0
        ? EXCLUSION_REASONS.NO_VALIDATED_FEATURES
        : EXCLUSION_REASONS.NOT_ANALYSED,
  }));

  return { count, reports, listed: reports.length };
}

// ------------------------------------------- the laboratory's printed ranges --

/**
 * Fields read for the printed reference intervals. FOUR, not a payload.
 *
 * `extraction` is `select: false` and is a large document -- every parameter
 * row with its raw text, plus report metadata and warnings. This projects
 * into the array and takes only what a scale needs, so the narrowness
 * `HISTORY_PROJECTION` argues for is not quietly abandoned one function down.
 *
 * ⚠ NO `+` PREFIX, AND THAT IS NOT AN OVERSIGHT. `+path` re-includes a
 * deselected path BY ITS OWN NAME; written on a SUBPATH of one
 * (`+extraction.extracted_parameters.test_name`) mongoose returns
 * `extraction: undefined` -- no error, no warning, just an absent payload and
 * every chart silently back to spanning its own readings. It was caught here
 * only because a test asserted on the loaded value. Naming a subpath plainly
 * is what re-includes it; measured against this schema, not assumed.
 */
const PRINTED_PROJECTION = [
  'user',
  'extraction.extracted_parameters.test_name',
  'extraction.extracted_parameters.reference_low',
  'extraction.extracted_parameters.reference_high',
  'extraction.extracted_parameters.reference_range_raw',
  // THE LABORATORY'S OWN HIGH/LOW MARKING. Carried for the same reason the
  // interval is: the laboratory already compared this value to its own range,
  // and that comparison is the one status available for a parameter this
  // platform does not assess. `dashboardService` reads the same field from
  // the same place, so the two screens cannot disagree about it.
  'extraction.extracted_parameters.flag',
].join(' ');

/**
 * THE REFERENCE INTERVAL EACH REPORT PRINTED BESIDE EACH VALUE.
 *
 * ==========================================================================
 * WHY THIS IS A SEPARATE QUERY
 * ==========================================================================
 *
 * Module 4 extracts every parameter's printed reference interval, and feature
 * engineering discards it along with the parameter: `UnmappedItem` keeps the
 * name, the raw value and the unit, and nothing else. So the readings that
 * reach `labSeriesService` have no scale, and their charts spanned only the
 * readings themselves -- which makes any change fill the box, the exact
 * defect fixed for the assessed charts.
 *
 * Reuniting them is the same move `dashboardService.buildUnanalysedSection`
 * already makes for a single report, and it asserts nothing new: the range is
 * the laboratory's own and this only carries it forward.
 *
 * IT IS A SEPARATE, OPTIONAL QUERY for the same reason `describeExcluded` is
 * one. `assembleHistory` is the expensive path, it is shared by four
 * endpoints, and three of them have no use for this at all. Widening
 * `HISTORY_PROJECTION` would make every trend, comparison, progress-score and
 * doctor-summary call drag extraction rows through the app to serve one
 * section of one page.
 *
 * ==========================================================================
 * WHAT IT DOES NOT DO
 * ==========================================================================
 *
 * It does not reach the ai-service. The snapshots `assembleHistory` builds
 * are untouched, so `TimelineReportInput` is unchanged and Module 28 receives
 * exactly what it received before. The join happens in this backend, at read
 * time, on the way to one page.
 *
 * It computes nothing. Same rule as the rest of this module: rows in, rows
 * out, no clinical judgement and no arithmetic on a patient value.
 *
 * @param {object} args
 * @param {object} args.user The AUTHENTICATED user. Ownership is enforced
 *        here and re-checked per row, exactly as everywhere else in this
 *        file -- being handed a report id is not permission to read it, and
 *        these ids arrive from a caller's own history rather than from the
 *        request, which is a reason to keep the check, not to drop it.
 *
 *        ⚠ THE PER-ROW `assertCanAccess` BELOW SURVIVES MUTATION, AND SO DOES
 *        THE ONE IN `assembleHistory` -- checked, not assumed. The query is
 *        already owner-scoped, so neither can fire today. That is the same
 *        deliberate redundancy this file and every report controller applies,
 *        and the reason is a filter someone widens later. Do not delete it as
 *        dead code on the strength of a surviving mutant without deleting
 *        every other one in this backend first.
 * @param {string[]} args.reportIds Reports to load, normally
 *        `assembleHistory`'s own `snapshots.map(s => s.report_id)`.
 * @returns {Promise<Map<string, Map<string, object>>>} reportId -> test_name
 *        as printed -> `{test_name, reference_low, reference_high,
 *        reference_range_raw}`. Reports with no extraction are simply absent,
 *        and a caller that finds nothing gets a series with no scale rather
 *        than a series with a wrong one.
 */
async function loadPrintedParameters({ user, reportIds }) {
  const ids = Array.isArray(reportIds) ? reportIds.filter(Boolean) : [];
  const byReport = new Map();
  if (!ids.length) return byReport;

  const rows = await Report.find(
    ownerScopedFilter(user, { ...OWNER_ONLY, base: { _id: { $in: ids } } })
  )
    .select(PRINTED_PROJECTION)
    .lean();

  for (const row of rows) {
    assertCanAccess(user, row, { ...OWNER_ONLY });
    const params =
      (row.extraction && Array.isArray(row.extraction.extracted_parameters)
        ? row.extraction.extracted_parameters
        : []) || [];
    const byName = new Map();
    for (const param of params) {
      // FIRST WINS, matching `buildUnanalysedSection`'s own join. A report
      // that prints the same test name twice is a duplicate the extraction
      // preserved; picking between them is a question this function is not
      // equipped to answer, and answering it differently from the dashboard
      // would put two different ranges on one reader's two screens.
      if (typeof param.test_name === 'string' && param.test_name && !byName.has(param.test_name)) {
        byName.set(param.test_name, param);
      }
    }
    byReport.set(String(row._id), byName);
  }

  return byReport;
}

/**
 * COULD THESE TWO REPORTS BE ONE PERSON'S?
 *
 * The comparison card compares two reports as one person's history, and
 * nothing checked that they were: 03-renal ("63 Years / Male") and
 * 01-all-normal ("34 Years / Female") were compared as haemoglobin
 * 9.2 -> 13.6 "in 2 days" (2026-09-24). Owner-scoped like every loader here,
 * and it reads only the stored printed sex and age -- no payload.
 *
 * @returns {Promise<object>} `utils/printedIdentity.comparePair`'s answer.
 */
async function checkPairIdentity({ user, baselineId, comparisonId }) {
  const rows = await Report.find(
    ownerScopedFilter(user, { ...OWNER_ONLY, base: { _id: { $in: [baselineId, comparisonId] } } })
  )
    .select('user chronoDate printedIdentity')
    .lean();
  const byId = new Map();
  for (const row of rows) {
    assertCanAccess(user, row, { ...OWNER_ONLY });
    byId.set(String(row._id), { identity: row.printedIdentity || null, date: row.chronoDate });
  }
  return comparePair(byId.get(String(baselineId)), byId.get(String(comparisonId)));
}

// ------------------------------------------------- explicitly named reports --

/**
 * RE-CHECK AN EXPLICITLY NAMED PAIR OF REPORT IDS, AND RESOLVE IT.
 *
 * This function exists because "the id appears in a filter" is not the same
 * guarantee as "the caller may read this report", and here the difference is a
 * whole patient's data. `?baseline=` and `?comparison=` let a caller NAME a
 * specific report, and being able to name one is not permission to read it -
 * so each id is loaded through the owner-scoped filter and then re-checked
 * with `assertCanAccess` before it is allowed anywhere near an analysis
 * request. Consequently:
 *
 *   - another patient's report id produces the SAME 404 a random id produces,
 *     with no way to tell the two apart (404 before 403, preserved);
 *   - an admin or a clinician naming a patient's report gets that same 404,
 *     because no `allowRoles` grant is passed;
 *   - and no id can reach the ai-service unless the caller owns the report.
 *
 * The second check - that the named report is actually IN the assembled
 * history - is separate, and is a 422 rather than a 404: the report
 * demonstrably exists and belongs to the caller, it simply has no validated
 * feature set to compare, or fell outside the window cap. Answering 404 there
 * would tell an owner their own report does not exist. The message names the
 * machine reason and never echoes the submitted id.
 *
 * It also spares the caller a confusing failure: the ai-service answers a
 * 400 (`COMPARISON_REPORT_NOT_FOUND`) for a ref it was not given a report for,
 * and this client maps every unclassified 4xx to a 502 contract-mismatch
 * error. That would be an accurate description of a bug and a poor one of a
 * user naming a report they have not analysed yet.
 *
 * @param {object} args
 * @param {object} args.user The AUTHENTICATED user.
 * @param {string|undefined} args.baseline Validated id, or undefined.
 * @param {string|undefined} args.comparison Validated id, or undefined.
 * @param {Set<string>} args.snapshotIds Report ids actually in the history.
 * @returns {Promise<{baselineRef: string, comparisonRef: string}|null>}
 */
async function resolveNamedPair({ user, baseline, comparison, snapshotIds }) {
  if (baseline === undefined && comparison === undefined) return null;

  // Both-or-neither is enforced by the validator; this is the authorisation
  // half, which a validator cannot do. If only one arrived anyway, the loop
  // below would query `_id: undefined` - so it is refused explicitly instead.
  if (baseline === undefined || comparison === undefined) {
    throw new ApiError(
      422,
      'VALIDATION_ERROR',
      'Name both baseline and comparison, or neither. One alone does not identify a pair.'
    );
  }

  // THE ID THAT IS COMPARED AND SENT IS THE ONE MONGO ACTUALLY RESOLVED, NEVER
  // THE SUBMITTED STRING.
  //
  // `OBJECT_ID` in `timelineValidators.js` is `/^[a-fA-F0-9]{24}$/`, so an
  // UPPERCASE hex id is valid input, and Mongo casts it to the same ObjectId as
  // its lowercase spelling - the `findOne` below finds the report. But
  // `snapshotIds` holds `String(row._id)`, which is always lowercase, so
  // testing the submitted string against that set said the caller's own
  // analysed, owned, in-window report "has no analysed feature set to compare".
  // That is a false statement about missing data from the module whose entire
  // job is not to make them, and it is fixed by using the identity of the
  // document that was just loaded instead of discarding it. The same canonical
  // id is what leaves for the ai-service, so `baseline_ref` matches a
  // `report_id` in the history it is sent beside - a mismatch there is the
  // 400 the pre-check exists to avoid.
  const resolved = [];
  for (const id of [baseline, comparison]) {
    // eslint-disable-next-line no-await-in-loop
    const owned = await Report.findOne(
      ownerScopedFilter(user, { ...OWNER_ONLY, base: { _id: id } })
    ).select('_id user');
    assertCanAccess(user, owned, { ...OWNER_ONLY });
    resolved.push(String(owned._id));
  }

  const missing = resolved.filter((id) => !snapshotIds.has(id));
  if (missing.length) {
    throw new ApiError(
      422,
      'REPORT_NOT_IN_HISTORY',
      'A report named as the comparison pair has no analysed feature set to compare, ' +
        'or falls outside the history window. Analyse it first, then try again.'
    );
  }

  return { baselineRef: resolved[0], comparisonRef: resolved[1] };
}

/**
 * The history block every one of these endpoints returns beside its answer.
 *
 * `considered` versus `included` is not decoration. A timeline built from two
 * of a patient's nine reports and a timeline built from a patient's only two
 * reports look identical in the analysis payload, and they mean completely
 * different things. This block is what tells them apart.
 *
 * THE ACCOUNTING IS TOTAL, AND THAT IS ASSERTED RATHER THAN CLAIMED:
 *
 *     considered === included + excludedCount + droppedByCap
 *
 * `droppedByCap` is why this identity needs three terms and not two. An
 * audit found the two-term version breaking silently the moment the cap
 * engaged: 55 eligible plus 3 unanalysed reports returned
 * `considered: 58, included: 50, excludedCount: 3` and left FIVE reports in
 * neither bucket, with `truncated: true` the only hint and no reason code
 * attributing them. The comment here claimed at the time that `excludedCount`
 * plus the reason codes said where every other report went. It did not, and a
 * block whose entire purpose is to make a short timeline distinguishable from
 * a thin history must not itself lose reports.
 *
 * `excludedListed` is the same honesty one level down: `excluded[]` is capped,
 * so a client comparing its length against `excludedCount` would otherwise
 * silently conclude the list was complete.
 */
function summariseHistory(history, excluded) {
  const considered = history.totalReports;
  const included = history.includedCount;
  const excludedCount = excluded ? excluded.count : undefined;

  // Eligible reports that existed but fell outside the most-recent-N window.
  // Derived by subtraction rather than counted separately so it cannot
  // disagree with the other three terms; clamped at 0 because a negative
  // count would be a nonsense a reader might take at face value.
  const droppedByCap =
    excludedCount === undefined
      ? undefined
      : Math.max(0, considered - included - excludedCount);

  return {
    // Every report this patient owns.
    considered,
    // How many contributed a snapshot.
    included,
    excludedCount,
    // Eligible, but beyond the cap. Distinct from `excludedCount`, which
    // counts reports that could not contribute at all: these ones could have.
    droppedByCap,
    // How many of `excludedCount` are itemised in `excluded[]` below.
    excludedListed: excluded ? excluded.listed : undefined,
    // The window's own bounds, so a reader can see WHICH stretch of history
    // the answer describes.
    from: history.window ? history.window.from : null,
    to: history.window ? history.window.to : null,
    // TRUE means reports were left out because of the cap, not because they
    // were unusable. A short timeline and a truncated one are different facts.
    cap: history.cap,
    truncated: history.truncated,
    reports: history.included,
    excluded: excluded ? excluded.reports : undefined,
  };
}

module.exports = {
  EXCLUSION_REASONS,
  INCLUSION_FILTER,
  HISTORY_PROJECTION,
  PRINTED_PROJECTION,
  assembleHistory,
  describeExcluded,
  loadPrintedParameters,
  checkPairIdentity,
  resolveNamedPair,
  summariseHistory,
};
