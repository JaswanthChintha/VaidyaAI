'use strict';

const asyncHandler = require('../utils/asyncHandler');
const { sendSuccess } = require('../utils/apiResponse');
const aiService = require('../services/aiServiceClient');
const historyService = require('../services/historyService');
const labSeriesService = require('../services/labSeriesService');

/**
 * Modules 28, 29 and 30 - the longitudinal endpoints.
 *
 *   GET /timeline/trends       Module 28. Per-feature trajectory across every
 *                              report the patient has that carries a validated
 *                              feature set.
 *   GET /timeline/comparison   Module 29. Two of those reports, side by side.
 *   GET /timeline/progress     Module 30. The same pair, scored.
 *
 * ==========================================================================
 * WHAT THIS CONTROLLER DOES AND DELIBERATELY DOES NOT DO
 * ==========================================================================
 *
 * It assembles the patient's history (`historyService`), posts it to the
 * ai-service, and returns what came back. It reaches NO clinical conclusion of
 * its own, and in particular it does not interpret, re-map, flatten or improve
 * on the outcome codes it is given.
 *
 * THAT RESTRAINT IS THE POINT, not laziness. Modules 28/29/30 each answer with
 * an `outcome` field drawn from a fixed vocabulary whose entire purpose is to
 * let "we could not tell" survive the trip to the client:
 *
 *   INSUFFICIENT_DATA        fewer than two usable readings. NOT `stable`.
 *   NO_PAIR                  fewer than two reports. NOT a score of 50.
 *   NOTHING_ASSESSED         a pair was compared and nothing could be placed
 *                            on the scale. NOT "no change".
 *   INSUFFICIENT_COVERAGE    too few contributing parameters for a headline
 *                            number. The contributions found are still
 *                            returned; the number is not.
 *   UNIT_MISMATCH, NOT_TRENDABLE, CLINICAL_DIRECTION_UNKNOWN, ...
 *
 * Every one of those arrives as an HTTP 200 carrying a structured refusal, and
 * every one is passed through untouched. A patient with zero or one analysed
 * report therefore gets an explicit, machine-readable "not enough history" -
 * never an empty-but-successful trend object, and never a fabricated "stable".
 * Collapsing any of them into a friendlier answer here would destroy exactly
 * the distinction the vocabularies exist to carry, and would do it at the last
 * hop before a screen.
 *
 * A CALL IS MADE EVEN WHEN THE HISTORY IS EMPTY. Short-circuiting on "fewer
 * than two reports" and synthesising a refusal locally would put a second
 * definition of "not enough history" in this file, in this backend's own
 * words, which could drift from the one the ai-service applies. The service
 * owns that vocabulary; it answers `NO_PAIR` itself, and it is cheap and
 * model-free, so it is asked.
 *
 * ==========================================================================
 * OWNERSHIP
 * ==========================================================================
 *
 * ENFORCED IN `historyService`, NOT HERE - and that is on purpose. Every query
 * this controller's answers rest on is built there by `ownerScopedFilter(user,
 * { ...OWNER_ONLY })` and every loaded row is re-checked with
 * `assertCanAccess`, exactly as `analysisController` and `dashboardController`
 * do for a single report, with NO `allowRoles` grant. So an admin and a
 * clinician are exactly as unable to read a patient's history as any other
 * user, and 404-before-403 is preserved.
 *
 * That deny-by-default matters more here than anywhere else in the
 * application: every other endpoint leaks at most one report if it is wrong,
 * and a widened filter here would leak a patient's entire library.
 *
 * A REPORT ID NAMED IN THE QUERY STRING IS RE-CHECKED, NOT MERELY FILTERED.
 * `?baseline=` and `?comparison=` name specific reports, and being able to
 * name one is not permission to read it - see
 * `historyService.resolveNamedPair`.
 *
 * LOGGING: nothing here logs. Not a value, not a finding, not an id.
 */

/**
 * The opaque patient reference echoed back by the ai-service.
 *
 * The user's own id: opaque, stable, and NEVER a name or an email. The service
 * echoes it into its response and nothing else, and it is not logged on either
 * side, but it is still identity - so it is the id and never a profile field.
 */
const patientRefOf = (req) => String(req.user.id ?? req.user._id);

/**
 * A correlation id for one history call.
 *
 * Unlike the analyze pipeline, whose correlation id is the report id, there is
 * no single report here - so a fresh uuid is used. Opaque by construction and
 * never derived from anything in a report.
 */
const historyRequestId = () => aiService.newRequestId();

/**
 * Re-check the `?baseline=`/`?comparison=` pair against the caller's ownership
 * and against the assembled history.
 *
 * The check itself lives in `historyService.resolveNamedPair` - ONE
 * implementation, shared with the Module 32 endpoint, because two copies of an
 * ownership check are two chances to weaken one of them. See that function for
 * why a non-owner gets a 404 and an owner naming an unanalysed report gets a
 * 422.
 */
const resolvePair = (req, snapshotIds) =>
  historyService.resolveNamedPair({
    user: req.user,
    baseline: req.query.baseline,
    comparison: req.query.comparison,
    snapshotIds,
  });

/**
 * Load the history and the explanation of what it left out, together.
 *
 * `describeExcluded` is run for every one of these endpoints rather than only
 * when something is missing: a caller cannot ask "why is my timeline short"
 * against a response that does not carry the answer, and a silently short
 * timeline is indistinguishable from a patient with little history. It reads
 * no payloads - see historyService.
 */
async function loadHistory(req) {
  const history = await historyService.assembleHistory({ user: req.user });
  const excluded = await historyService.describeExcluded({ user: req.user });
  return { history, excluded };
}

// ---------------------------------------------------------- Module 28 -------

/**
 * GET /timeline/trends
 *
 * 200 ALWAYS, INCLUDING FOR A PATIENT WITH NO HISTORY AT ALL. This is a
 * deliberate departure from `/reports/:id/analysis`, which 404s when there is
 * nothing stored, and the reason is that the two are asking different
 * questions. "Does this report have an analysis" has a yes/no answer, and a
 * synthesised empty one would be a lie. "How has this patient changed over
 * time" is answered, correctly and usefully, by "we cannot tell yet, and here
 * is exactly why" - which is a result, not an absence. The answer carries
 * `outcome: INSUFFICIENT_DATA` per feature plus the service's own request-level
 * warning, and `history.included` says how many reports it had to work with.
 *
 * A 404 here would also be wrong in a subtler way: it is the patient's own
 * timeline, and it exists whether or not anything is on it yet.
 */
const getTrends = asyncHandler(async (req, res) => {
  if (!aiService.isConfigured()) throw aiService.notConfigured();

  const { history, excluded } = await loadHistory(req);

  const trends = await aiService.analyseTrends({
    reports: history.snapshots,
    patientRef: patientRefOf(req),
    requestId: historyRequestId(),
  });

  return sendSuccess(res, 200, {
    history: historyService.summariseHistory(history, excluded),
    // THE LABORATORY'S OWN REPEATED PARAMETERS, which Module 28 cannot trend.
    //
    // Module 28 works on canonical features -- the ones this pipeline can
    // identify across reports and express in one unit -- so everything the
    // platform does not assess was absent from the timeline entirely. A
    // reader asked why, having reports full of parameters that never appeared.
    //
    // Built here, from the SAME snapshots Module 28 receives, so the two
    // cannot disagree about which reports are in the history. It carries no
    // direction and no classification: see labSeriesService.
    labSeries: labSeriesService.buildLabSeries(history.snapshots),
    // Module 28's `TimelineTrendsData`, VERBATIM. `outcome` is the field to
    // branch on, never `trend` - and neither is touched here.
    trends,
  });
});

// ---------------------------------------------------------- Module 29 -------

/**
 * GET /timeline/comparison?baseline=<id>&comparison=<id>
 *
 * With no pair named, Module 29 compares the patient's earliest report to
 * their latest over its own total ordering. With a pair named, the caller's
 * naming is honoured exactly - including when the named baseline is the later
 * report, which Module 29 flags in its own warnings rather than silently
 * swapping, because swapping would invert every reported direction of change.
 *
 * 200 for a patient with fewer than two comparable reports, carrying
 * `pair: null` and the service's own warning. Same reasoning as `/trends`.
 */
const getComparison = asyncHandler(async (req, res) => {
  if (!aiService.isConfigured()) throw aiService.notConfigured();

  const { history, excluded } = await loadHistory(req);
  const snapshotIds = new Set(history.snapshots.map((s) => s.report_id));
  const pair = await resolvePair(req, snapshotIds);

  const comparison = await aiService.compareReports({
    reports: history.snapshots,
    patientRef: patientRefOf(req),
    baselineRef: pair ? pair.baselineRef : undefined,
    comparisonRef: pair ? pair.comparisonRef : undefined,
    requestId: historyRequestId(),
  });

  return sendSuccess(res, 200, {
    history: historyService.summariseHistory(history, excluded),
    // Which two reports the caller asked for, so the response says whether the
    // pair was chosen or named. Module 29's own `pair.selection` says which
    // reports were actually used; this says what was requested, and the two
    // are kept separate rather than merged.
    requestedPair: pair
      ? { baseline: pair.baselineRef, comparison: pair.comparisonRef }
      : null,
    // Module 29's `ReportComparisonData`, VERBATIM.
    comparison,
  });
});

// ---------------------------------------------------------- Module 30 -------

/**
 * GET /timeline/progress?baseline=<id>&comparison=<id>
 *
 * The same pair as `/comparison`, scored 0-100. `outcome` is the field to
 * branch on and `score` is non-null for exactly one value, `SCORE_COMPUTED`.
 * NO_PAIR, NOTHING_ASSESSED and INSUFFICIENT_COVERAGE all carry `score: null`
 * - never 50, never 0, and never a band label standing in for a missing
 * number - and all three are passed through exactly as they arrive.
 *
 * `coverage` says how many parameters the number was built from, and it
 * matters: a score computed from two parameters and a score computed from
 * twelve print identically. It is not summarised or omitted here.
 */
const getProgress = asyncHandler(async (req, res) => {
  if (!aiService.isConfigured()) throw aiService.notConfigured();

  const { history, excluded } = await loadHistory(req);
  const snapshotIds = new Set(history.snapshots.map((s) => s.report_id));
  const pair = await resolvePair(req, snapshotIds);

  const progress = await aiService.scoreProgress({
    reports: history.snapshots,
    patientRef: patientRefOf(req),
    baselineRef: pair ? pair.baselineRef : undefined,
    comparisonRef: pair ? pair.comparisonRef : undefined,
    requestId: historyRequestId(),
  });

  return sendSuccess(res, 200, {
    history: historyService.summariseHistory(history, excluded),
    requestedPair: pair
      ? { baseline: pair.baselineRef, comparison: pair.comparisonRef }
      : null,
    // Module 30's `HealthProgressData`, VERBATIM.
    progress,
  });
});

module.exports = { getTrends, getComparison, getProgress };
