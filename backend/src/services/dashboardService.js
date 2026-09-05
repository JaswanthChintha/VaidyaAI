'use strict';

const analysisService = require('./analysisService');

/**
 * Module 27 - Health Dashboard.
 *
 * WHAT THIS IS, AND WHAT IT DELIBERATELY IS NOT.
 *
 * The spec calls Module 27 "the frontend dashboard". There is no frontend in
 * this project, so what is built here is the half a frontend cannot build for
 * itself: the READ MODEL a dashboard renders. It takes the analysis that
 * Modules 16-20, 23 and 26 already produced and stored on the report, and
 * re-shapes it into the five card groups the spec names -
 *
 *   Overall Health Card . Condition Cards . Laboratory Cards .
 *   Evidence Section . Recommendations Section
 *
 * IT CALLS NO MODEL, NO AI SERVICE, AND COMPUTES NO CLINICAL JUDGEMENT. Every
 * status, every risk level, every band and every sentence in the output was
 * decided upstream and is carried through unchanged. The only things derived
 * here are (a) the four-valued laboratory `state`, derived in exactly one
 * place, and (b) the joins between lists that were already stored side by side.
 * If a fact is not in the stored payload, this module does not produce it.
 *
 * ==========================================================================
 * THE RULE THIS FILE EXISTS TO NOT BREAK: ABSENCE IS NOT A VALUE
 * ==========================================================================
 *
 * A dashboard is where absence gets quietly turned into a value, because a
 * card has to show SOMETHING. The three ways that happens, and what is done
 * about each:
 *
 *   `status: null` + `any_assessed: false` is NOT "Healthy". It is Module 18's
 *   fourth case - nothing could be assessed. `statusLabel` is CARRIED FROM the
 *   service's `overall.status_label`, which has FIVE values, not four: the
 *   fifth is `Healthy (partial assessment)`, and it exists because a partial
 *   clean result was otherwise byte-identical to a full one. This module used
 *   to state four, back when the backend re-derived the label from `status`
 *   and a partial assessment printed on a card as a flat "Healthy". Both come
 *   from `analysisService.summariseReport`, the SAME function that derives the
 *   persisted copy, so a dashboard and a listing can never disagree.
 *
 *   A condition with no risk level has NO risk level. `risk` is passed through
 *   verbatim - `null` stays `null` and is never coalesced to `Low`, which
 *   would file an open question below a settled one. Module 19's `Not
 *   Assessed` priority band is carried for exactly this reason.
 *
 *   A missing number is `undefined`, never `0`; a missing boolean is
 *   `undefined`, never `false`. `numberOrUndefined` and `booleanOrUndefined`
 *   below are the only way a number or a boolean enters this projection, so
 *   there is no path on which a defaulted zero can appear.
 *
 * A laboratory value that was READ AND REFUSED is never rendered as missing:
 * it keeps `state: 'rejected'` with Module 6's reason. A value that was never
 * in the document at all appears only if Module 20 wrote an evidence line
 * saying so, and it carries Module 20's own fixed wording for why.
 *
 * NO PROSE IS COMPOSED HERE. Every human-readable string in the output is a
 * reviewed sentence written upstream (Module 20's availability explanations,
 * Module 23's notices, Module 26's catalogue text) and copied, not built.
 */

// ------------------------------------------------------------- primitives --

/**
 * A number, or `undefined`.
 *
 * NOT `?? 0`. A count that is absent means "this was not reported", and a
 * dashboard showing `0` for it states a fact the analysis never established -
 * "0 abnormal findings" reads exactly like a clean bill of health.
 */
function numberOrUndefined(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

/**
 * A boolean, or `undefined`.
 *
 * NOT `=== true`. That collapses "we do not know" into "no", which is the same
 * mistake as defaulting a count to zero: `complete: false` means the assessment
 * is known to rest on partial information, and `undefined` means the producer
 * did not say. A caller may treat them alike; this module may not decide that
 * for them.
 */
function booleanOrUndefined(value) {
  return typeof value === 'boolean' ? value : undefined;
}

/** A non-empty string, or `null`. Empty strings render as blanks; nulls do not. */
function stringOrNull(value) {
  return typeof value === 'string' && value.trim() !== '' ? value : null;
}

/** An array, or `[]`. Never `undefined`, so a renderer never type-checks a list. */
function listOf(value) {
  return Array.isArray(value) ? value : [];
}

/** A plain object, or `{}`. */
function objectOf(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
}

/**
 * Pass a value through UNTOUCHED, `null` included.
 *
 * Used for `risk`, `status`, `confidence` and every other field where the
 * producer's `null` is a decision rather than a gap. It exists as a named
 * function so that "this was deliberately not defaulted" is visible at the call
 * site instead of looking like a forgotten fallback.
 */
function asIs(value) {
  return value === undefined ? null : value;
}

// --------------------------------------------------- overall health card ----

/**
 * Module 18's verdict, plus the counts a summary tile shows.
 *
 * `status`, `statusLabel`, `risk`, `anyAssessed` and `complete` come from
 * `analysisService.summariseReport` - not re-derived here. That function is
 * where the vocabulary is validated and where anything unrecognised degrades
 * TOWARDS "not assessed"; a second derivation in this file would be a second
 * chance to get it wrong, and the two could then disagree on the same report.
 *
 * `caveat` is Module 18's own sentence explaining why an assessment is
 * incomplete. It is non-null exactly when `complete` is false, and it is
 * carried verbatim - a card that shows an incomplete status without it is
 * showing a conclusion without its qualifier.
 */
function buildOverallCard(clinicalReport) {
  const overall = objectOf(clinicalReport.overall);
  const summary = objectOf(clinicalReport.summary);
  const derived = analysisService.summariseReport(clinicalReport);

  return {
    // Module 18's four STATUS cases; `status` is `null` for the fourth. But
    // `statusLabel` is what a card actually prints, and it carries FIVE values
    // -- `Healthy (partial assessment)` is a distinct label, never flattened
    // to "Healthy" here. Never render `status` where the label belongs.
    status: asIs(derived.overallStatus),
    statusLabel: derived.overallStatusLabel,
    risk: asIs(derived.overallRisk),
    anyAssessed: derived.anyAssessed,
    complete: derived.assessmentComplete,
    caveat: stringOrNull(overall.caveat),

    // Which of Module 18's rules produced the status, and the policy it
    // implements. Both are fixed strings written upstream.
    ruleApplied: stringOrNull(overall.rule_applied),
    policy: stringOrNull(overall.policy),

    // What was and was not assessed. These are the numbers that make an
    // "assessed nothing" report visibly different from a healthy one.
    assessedConditionCount: numberOrUndefined(overall.assessed_condition_count),
    unassessedConditionCount: numberOrUndefined(overall.unassessed_condition_count),
    unassessedConditions: listOf(overall.unassessed_conditions),
    partiallyAssessedConditions: listOf(overall.partially_assessed_conditions),
    abnormalConditionCount: numberOrUndefined(overall.abnormal_condition_count),
    highRiskConditionCount: numberOrUndefined(overall.high_risk_condition_count),
    // Decision sources that did not answer at all. A status resting on one of
    // two sources is not the same as one resting on both.
    sourcesFailed: listOf(overall.sources_failed),

    counts: {
      conditions: numberOrUndefined(summary.condition_count),
      abnormal: numberOrUndefined(summary.abnormal_count),
      critical: numberOrUndefined(summary.critical_count),
      normal: numberOrUndefined(summary.normal_count),
      unassessed: numberOrUndefined(summary.unassessed_count),
      hybrid: numberOrUndefined(summary.hybrid_count),
      laboratoryValues: numberOrUndefined(summary.laboratory_value_count),
      usableLaboratoryValues: numberOrUndefined(summary.usable_laboratory_value_count),
      rejectedLaboratoryValues: numberOrUndefined(summary.rejected_laboratory_value_count),
      recommendations: numberOrUndefined(summary.recommendation_count),
      evidenceLines: numberOrUndefined(summary.evidence_line_count),
      warnings: numberOrUndefined(summary.warning_count),
    },

    sourcesUsed: listOf(summary.sources_used),
    basisConflictConditions: listOf(summary.basis_conflict_conditions),
  };
}

// ------------------------------------------------------- condition cards ----

/**
 * One card per CONDITION - never one per decision.
 *
 * Two stored lists describe the same conditions from two angles and both are
 * needed: Module 19's `prioritized` supplies the ORDER and the priority band,
 * and Module 17's `conditions` (which carries Module 16's fusion through
 * `hybrid`, `basis_conflict` and the per-source contributions) supplies the
 * detail. They are joined by condition name, which is the key Module 19 itself
 * groups by.
 *
 * ORDER COMES FROM MODULE 19 AND IS NOT RECOMPUTED. Its tiers put flagged
 * findings first, then conditions that could NOT be assessed, then settled
 * normal ones - the unassessed band sits above normal deliberately, so an open
 * question is never buried under a resolved one. Re-sorting here would silently
 * undo that.
 *
 * When `prioritized` is absent (an older stored report, or a producer that did
 * not emit it) the `conditions` list is used in its stored order and `rank`,
 * `priority` and `tier` are left `undefined` rather than invented - an
 * unranked card is honest; a card claiming rank 1 because it happened to be
 * first in an unordered list is not.
 */
function buildConditionCards(clinicalReport) {
  const conditions = listOf(clinicalReport.conditions);
  const prioritized = listOf(clinicalReport.prioritized);

  const byCondition = new Map();
  for (const item of conditions) {
    const row = objectOf(item);
    if (typeof row.condition === 'string') byCondition.set(row.condition, row);
  }

  // Module 19's order when it exists; the stored order otherwise. Anything
  // `prioritized` names that `conditions` does not is still rendered - from the
  // prioritized row alone - because dropping it would hide a finding.
  const ordered = [];
  const seen = new Set();

  for (const item of prioritized) {
    const row = objectOf(item);
    if (typeof row.condition !== 'string') continue;
    ordered.push({ priority: row, detail: objectOf(byCondition.get(row.condition)) });
    seen.add(row.condition);
  }
  for (const item of conditions) {
    const row = objectOf(item);
    if (typeof row.condition !== 'string' || seen.has(row.condition)) continue;
    ordered.push({ priority: {}, detail: row });
  }

  return ordered.map(({ priority, detail }) => ({
    condition: priority.condition || detail.condition,

    // Module 19. `priority` has FOUR bands and `Not Assessed` is one of them:
    // it is a band, not a risk level, and a condition in it has no risk at all.
    rank: numberOrUndefined(priority.rank),
    priority: stringOrNull(priority.priority),
    tier: numberOrUndefined(priority.tier),

    // Module 15/16's verdict, verbatim. `risk` is `null` for anything that was
    // not assessed and is NEVER coalesced - INSUFFICIENT_DATA carries no risk.
    status: asIs(priority.status !== undefined ? priority.status : detail.status),
    risk: asIs(priority.risk !== undefined ? priority.risk : detail.risk),
    confidence: asIs(
      priority.confidence !== undefined ? priority.confidence : detail.confidence
    ),
    confidenceBasis: stringOrNull(detail.confidence_basis),

    // `assessed: false` is the fact that stops a card rendering as "fine".
    assessed: booleanOrUndefined(
      priority.assessed !== undefined ? priority.assessed : detail.assessed
    ),
    partiallyAssessed: booleanOrUndefined(
      priority.partially_assessed !== undefined
        ? priority.partially_assessed
        : detail.partially_assessed
    ),
    unassessedSources: listOf(detail.unassessed_sources),
    flagged: booleanOrUndefined(
      priority.flagged !== undefined ? priority.flagged : detail.flagged
    ),
    critical: booleanOrUndefined(
      priority.critical !== undefined ? priority.critical : detail.critical
    ),
    normal: booleanOrUndefined(detail.normal),

    // Module 16's fusion. `hybrid` says a rule and a model both contributed;
    // `basisConflict` says they did NOT measure the same thing, and `basisNote`
    // is the upstream sentence explaining that - a card that shows a fused
    // verdict without it is hiding a disagreement.
    hybrid: booleanOrUndefined(priority.hybrid !== undefined ? priority.hybrid : detail.hybrid),
    basisConflict: booleanOrUndefined(
      priority.basis_conflict !== undefined ? priority.basis_conflict : detail.basis_conflict
    ),
    basisNote: stringOrNull(detail.basis_note),
    renderContributionsSeparately: booleanOrUndefined(detail.render_contributions_separately),

    sources: listOf(listOf(priority.sources).length ? priority.sources : detail.sources),
    sourceKinds: listOf(detail.source_kinds),
    contributingDecisionCount: numberOrUndefined(
      priority.contributing_decision_count !== undefined
        ? priority.contributing_decision_count
        : detail.contributing_decision_count
    ),

    // The join keys a renderer needs to link this card to the other sections.
    evidenceFeatures: listOf(detail.evidence_features),
    recommendationCodes: listOf(detail.recommendation_codes),
  }));
}

// ------------------------------------------------------ laboratory cards ----

/** The four states a laboratory card can be in. There is no fifth. */
const LAB_STATE = Object.freeze({
  VALID: 'valid',
  QUESTIONABLE: 'questionable',
  REJECTED: 'rejected',
  /**
   * NOT a Module 6 partition. This is the card for a value the analysis wanted
   * and did not get, and it exists only where Module 20 wrote an evidence line
   * saying the value was absent or unreadable. It is the difference between
   * "your creatinine is fine" and "we never saw your creatinine".
   */
  UNAVAILABLE: 'unavailable',
});

/** Module 20 availabilities that mean "there is no value to show". */
const ABSENT_AVAILABILITIES = Object.freeze(['not_present_in_report', 'unreadable_document']);

/**
 * The one place a laboratory state is decided.
 *
 * Returns `null` - not `'valid'` - for a status this build does not recognise.
 * A future partition name must render as "we do not know how reliable this is",
 * never as a value the analysis was entitled to rely on.
 */
function labState(status) {
  if (status === LAB_STATE.VALID) return LAB_STATE.VALID;
  if (status === LAB_STATE.QUESTIONABLE) return LAB_STATE.QUESTIONABLE;
  if (status === LAB_STATE.REJECTED) return LAB_STATE.REJECTED;
  return null;
}

/**
 * One card per laboratory value, plus one per value the report needed and did
 * not have.
 *
 * The value cards come from Module 17's `laboratory_values`, which already
 * carries Module 6's verdict, the reference range and the high/low flag. The
 * UNAVAILABLE cards are a join onto Module 20's evidence lines: a line whose
 * `availability` is `not_present_in_report` or `unreadable_document` names a
 * feature that no laboratory value covers, and it carries Module 20's own FIXED
 * wording for why. That wording is copied, never composed here.
 *
 * The distinction those two availabilities keep is the whole point of the join:
 * "this test is not on your report" and "the page it was on could not be read"
 * are different facts, and only the second one means the analysis may be
 * missing something the patient actually had measured.
 *
 * A REJECTED VALUE IS NOT AN UNAVAILABLE ONE. It was printed, it was read, and
 * Module 6 refused it - it keeps its own card, its `rejectedValue` and the
 * reason, because reporting it as missing would be false.
 */
function buildLaboratoryCards(clinicalReport, evidenceLinesByFeature) {
  const values = listOf(clinicalReport.laboratory_values);
  const covered = new Set();

  const cards = values.map((item) => {
    const row = objectOf(item);
    if (typeof row.feature === 'string') covered.add(row.feature);

    return {
      feature: row.feature,
      displayName: stringOrNull(row.display_name),
      value: asIs(row.value),
      unit: stringOrNull(row.unit),
      valueType: stringOrNull(row.value_type),

      // The four-state field a card branches on. `null` when the producer's
      // partition name is not one this build knows.
      state: labState(row.status),
      // Module 6's own word, unmapped, so an unrecognised partition is still
      // visible rather than silently becoming `null` and nothing else.
      status: stringOrNull(row.status),
      // Whether the analysis was allowed to rely on it.
      usable: booleanOrUndefined(row.usable),
      questionable: booleanOrUndefined(row.questionable),
      clinicallyExtreme: booleanOrUndefined(row.clinically_extreme),
      extremeDirection: stringOrNull(row.extreme_direction),

      // Reference range and the producer's high/low flag. `null`, not 0, when
      // a bound is unknown - a range of 0 to 0 is a clinical statement.
      referenceLow: asIs(row.reference_low),
      referenceHigh: asIs(row.reference_high),
      referenceRangeRaw: stringOrNull(row.reference_range_raw),
      flag: stringOrNull(row.flag),

      // Provenance. What the lab actually printed, before any conversion.
      originalTestName: stringOrNull(row.original_test_name),
      originalUnit: stringOrNull(row.original_unit),
      unitConverted: booleanOrUndefined(row.unit_converted),
      // An ASSUMED unit is a card-level caveat: the number is only as good as
      // the guess about what it was measured in.
      unitAssumed: booleanOrUndefined(row.unit_assumed),
      derived: stringOrNull(row.derived),
      censored: stringOrNull(row.censored),
      pageNumber: numberOrUndefined(row.page_number),
      extractionConfidence: asIs(row.extraction_confidence),
      source: stringOrNull(row.source),

      // Populated only when Module 6 refused the value.
      rejectionCode: stringOrNull(row.rejection_code),
      rejectionReason: stringOrNull(row.rejection_reason),

      availability: null,
      availabilityExplanation: null,
    };
  });

  // The join. One card per feature Module 20 recorded as absent or unreadable
  // and that no laboratory value above already covers.
  const unavailable = [];
  for (const [feature, line] of evidenceLinesByFeature) {
    if (covered.has(feature)) continue;
    if (!ABSENT_AVAILABILITIES.includes(line.availability)) continue;

    unavailable.push({
      feature,
      displayName: stringOrNull(line.display_name),
      // There is no value, and none is invented. `null` is the honest answer.
      value: null,
      unit: null,
      valueType: null,
      state: LAB_STATE.UNAVAILABLE,
      status: null,
      usable: false,
      questionable: undefined,
      clinicallyExtreme: undefined,
      extremeDirection: null,
      referenceLow: asIs(line.reference_low),
      referenceHigh: asIs(line.reference_high),
      referenceRangeRaw: null,
      flag: null,
      originalTestName: null,
      originalUnit: null,
      unitConverted: undefined,
      unitAssumed: undefined,
      derived: null,
      censored: null,
      pageNumber: undefined,
      extractionConfidence: null,
      source: null,
      rejectionCode: null,
      rejectionReason: null,
      // Module 20's verdict and Module 20's fixed sentence for it, copied.
      availability: stringOrNull(line.availability),
      availabilityExplanation: stringOrNull(line.explanation),
    });
  }

  return cards.concat(unavailable);
}

// ------------------------------------------------------ evidence section ----

/** One `Input -> Evidence -> Decision` line, projected field for field. */
function projectEvidenceLine(item) {
  const line = objectOf(item);
  return {
    feature: line.feature,
    displayName: stringOrNull(line.display_name),
    value: asIs(line.value),
    unit: stringOrNull(line.unit),
    // Rule decisions only; `null` for a model, which compares nothing.
    threshold: asIs(line.threshold),
    comparator: stringOrNull(line.comparator),
    // The producer's OWN band wording, verbatim. Never re-phrased here.
    classification: stringOrNull(line.classification),
    referenceLow: asIs(line.reference_low),
    referenceHigh: asIs(line.reference_high),
    note: stringOrNull(line.note),
    sourceStage: stringOrNull(line.source_stage),

    // The Module 6 join. `availability` plus its fixed explanation is how a
    // value that was READ AND REFUSED avoids being drawn as "not present".
    availability: stringOrNull(line.availability),
    availabilityExplanation: stringOrNull(line.explanation),
    rejected: booleanOrUndefined(line.rejected),
    rejectionCode: stringOrNull(line.rejection_code),
    rejectionReason: stringOrNull(line.rejection_reason),
    rejectedValue: asIs(line.rejected_value),
    rejectedUnit: stringOrNull(line.rejected_unit),
    questionable: booleanOrUndefined(line.questionable),
    clinicallyExtreme: booleanOrUndefined(line.clinically_extreme),
    // Upstream warnings naming this feature, origin stage intact. A silently
    // repaired PDF or an unreadable page surfaces ONLY here.
    relatedWarnings: listOf(line.related_warnings),
  };
}

/**
 * Spec Module 27: "Displays the values responsible for important decisions."
 *
 * Module 20 already produced exactly that, per condition, as an ordered
 * `Input -> Evidence -> Decision` chain. This projects it and adds nothing.
 *
 * The per-source blocks are kept alongside the condition-level lines because a
 * fused condition has two answers behind one card, and `basisConflict` on the
 * card is only actionable if the reader can see which source said what. Rule
 * ids and the model's own identity, prediction and probability travel with
 * them, along with the caveat that a model's feature importance is a
 * whole-dataset ranking and not a statement about this patient.
 */
function buildEvidenceSection(clinicalReport) {
  const explainability = objectOf(clinicalReport.explainability);

  const conditions = listOf(explainability.conditions).map((item) => {
    const row = objectOf(item);

    return {
      condition: row.condition,
      status: asIs(row.status),
      risk: asIs(row.risk),
      confidence: asIs(row.confidence),
      hybrid: booleanOrUndefined(row.hybrid),
      basisConflict: booleanOrUndefined(row.basis_conflict),
      basisNote: stringOrNull(row.basis_note),
      fusionExplanation: stringOrNull(row.fusion_explanation),
      chain: listOf(row.chain),
      lines: listOf(row.evidence).map(projectEvidenceLine),

      sources: listOf(row.sources).map((entry) => {
        const source = objectOf(entry);
        const rule = objectOf(source.rule);
        const ml = objectOf(source.ml);

        return {
          source: source.source,
          sourceKind: stringOrNull(source.source_kind),
          status: asIs(source.status),
          risk: asIs(source.risk),
          confidence: asIs(source.confidence),
          assessed: booleanOrUndefined(source.assessed),
          // WHAT this source actually measured. Two sources agreeing on a
          // condition while measuring different things is the conflict
          // `basisConflict` above reports.
          assessmentBasis: stringOrNull(source.assessment_basis),
          assessmentBasisFamily: stringOrNull(source.assessment_basis_family),
          bandLabels: listOf(source.band_labels),

          rule: source.rule
            ? {
                ruleIds: listOf(rule.rule_ids),
                classifications: listOf(rule.classifications),
                deterministic: booleanOrUndefined(rule.deterministic),
                triggeringValues: listOf(rule.triggering_values).map(projectEvidenceLine),
              }
            : null,

          ml: source.ml
            ? {
                modelName: stringOrNull(ml.model_name),
                modelVersion: stringOrNull(ml.model_version),
                prediction: asIs(ml.prediction),
                riskBand: stringOrNull(ml.risk_band),
                bandMeaning: stringOrNull(ml.band_meaning),
                probability: asIs(ml.probability),
                // Fixed upstream sentence: a probability is not a measurement
                // of this person and is not a diagnosis.
                probabilitySemantics: stringOrNull(ml.probability_semantics),
                featuresObserved: listOf(ml.features_observed),
                // Values the model was given that the patient did not supply.
                // A card that hid this would present a guess as an observation.
                featuresImputed: listOf(ml.features_imputed),
                featuresMissing: listOf(ml.features_missing),
                importanceScope: stringOrNull(ml.importance_scope),
                importanceIsPerPatient: booleanOrUndefined(ml.importance_is_per_patient),
                importanceCaveat: stringOrNull(ml.importance_caveat),
                skipped: booleanOrUndefined(ml.skipped),
                skipReason: stringOrNull(ml.skip_reason),
                skipExplanation: stringOrNull(ml.skip_explanation),
                inputEvidence: listOf(ml.input_evidence).map(projectEvidenceLine),
              }
            : null,

          lines: listOf(source.evidence).map(projectEvidenceLine),
        };
      }),
    };
  });

  return {
    chain: listOf(explainability.chain),
    policy: stringOrNull(explainability.policy),
    conditions,
    // Features Module 6 refused, joined so the evidence section can state that
    // a value was found and not trusted rather than leaving it unexplained.
    rejectedFeaturesJoined: listOf(explainability.rejected_features_joined),
    mlImportanceScope: stringOrNull(explainability.ml_importance_scope),
    mlImportanceCaveat: stringOrNull(explainability.ml_importance_caveat),
  };
}

// ----------------------------------------------- recommendations section ----

/**
 * Module 26's pre-approved educational guidance, and Module 23's patient-facing
 * explanations.
 *
 * MODULE 26 IS CATALOGUE TEXT AND NO MODEL WAS INVOLVED. `generated` is carried
 * through from the payload rather than asserted here, so the absence of
 * generation is checkable from the data - a `true` would be a defect somebody
 * can see instead of a promise in a comment.
 *
 * MODULE 23 IS BRANCHED ON `generated_explanation_available`, NEVER ON THE
 * PRESENCE OF THE STRING. That boolean was derived once, on the way in
 * (`analysisService.normaliseExplanation`), and it is the only correct thing to
 * branch on: "the safety layer withheld this" and "there was nothing to say"
 * are different facts, and `{explanation && ...}` renders the first as a blank
 * space - a report with a hole where the platform's own safety layer refused to
 * speak, and nothing saying so. `notice` is non-empty whenever the boolean is
 * false, so there is always something to show - AND THAT IS ENFORCED HERE, not
 * merely inherited. `analysisService.normaliseExplanation` does guarantee it on
 * the write path, but a guarantee made only by the writer is not a guarantee at
 * the reader: a stored `{generated_explanation_available: false}` with no
 * notice - a document written by an older build, a partial restore, a hand
 * edit - emitted `explanation: null` beside `notice: null`, which is a card
 * with nothing on it and nothing saying why. The last-resort string is
 * `analysisService.EXPLANATION_NOTICE_FALLBACK`, the SAME reviewed sentence the
 * write path falls back to, so the two layers cannot word the same fact
 * differently. `outcome` is the producer's own verdict and is never rewritten.
 *
 * Nothing that was refused is here to leak: the refused text never left the
 * ai-service, and `analysisService.stripRefusedText` removed the key shapes
 * that could carry an offending span before any of this was stored.
 */
function buildRecommendationsSection(clinicalReport, explanationSet, guidance) {
  const set = objectOf(explanationSet);
  const life = objectOf(guidance);

  const entries = listOf(set.explanations).map((item) => {
    const entry = objectOf(item);
    // THE BOOLEAN. `=== true` is correct HERE and only here: this field is
    // derived by us on the way in and is a hard three-state guarantee, so
    // anything that is not literally `true` means no approved text exists.
    const available = entry.generated_explanation_available === true;

    return {
      subject: stringOrNull(entry.subject),
      feature: stringOrNull(entry.feature),
      conditions: listOf(entry.conditions),
      // The producer's verdict on its own generation, verbatim, including a
      // value this build does not recognise.
      outcome: stringOrNull(entry.outcome),
      available,
      // Populated ONLY when `available` is true. Never `''`.
      explanation: available ? stringOrNull(entry.explanation) : null,
      // Populated whenever it is false, WITHOUT EXCEPTION. The reviewed
      // sentence that says an explanation could not be prepared, and which
      // case it was - or, when the stored row carries none, the generic one
      // that at least says an explanation could not be prepared. Never null
      // beside `available: false`.
      notice: available
        ? null
        : stringOrNull(entry.notice) || analysisService.EXPLANATION_NOTICE_FALLBACK,
      // Module 26's structured catalogue answer for the same finding, which is
      // what a withheld explanation falls back to.
      fallback: entry.fallback === undefined ? null : entry.fallback,
      groundingAvailable: booleanOrUndefined(entry.grounding_available),
      // Module 20's chain applied to retrieval: what the sentence was grounded
      // in, so a claim is traceable to a reviewed document.
      sources: listOf(entry.sources).map((source) => {
        const cite = objectOf(source);
        return {
          docId: stringOrNull(cite.doc_id),
          title: stringOrNull(cite.title),
          topic: stringOrNull(cite.topic),
          basis: stringOrNull(cite.basis),
          lastReviewed: stringOrNull(cite.last_reviewed),
        };
      }),
      findings: listOf(entry.findings),
    };
  });

  return {
    // Module 26 - pre-approved educational guidance. The spec's own wording:
    // educational, not personalised treatment advice.
    guidance: {
      // TWO states only, unlike Module 23's three below: Module 26 has no
      // "withheld" outcome - it resolves reviewed catalogue text or the stage
      // did not answer. `false` therefore means exactly "no guidance stage
      // result is stored", and a renderer must show that rather than an empty
      // list, which reads as "there is nothing to recommend".
      available: Boolean(guidance),
      // Carried from the payload, not asserted. Always false in a healthy build.
      generated: booleanOrUndefined(life.generated),
      source: stringOrNull(life.source),
      conditions: listOf(life.conditions),
      features: listOf(life.features),
      items: listOf(life.items).map((item) => {
        const row = objectOf(item);
        return {
          code: stringOrNull(row.code),
          // Reviewed catalogue text. Scanned at import on the Python side.
          text: stringOrNull(row.text),
          category: stringOrNull(row.category),
          // Module 20's principle: whatever justified showing this travels
          // with it, so a card can say why the reader is being told it.
          becauseOfConditions: listOf(row.because_of_conditions),
          becauseOfFeatures: listOf(row.because_of_features),
          alwaysIncluded: booleanOrUndefined(row.always_included),
        };
      }),
      furtherReading: listOf(life.further_reading).map((item) => {
        const row = objectOf(item);
        return {
          docId: stringOrNull(row.doc_id),
          title: stringOrNull(row.title),
          topic: stringOrNull(row.topic),
          summary: stringOrNull(row.summary),
          basis: stringOrNull(row.basis),
          lastReviewed: stringOrNull(row.last_reviewed),
        };
      }),
      // The concatenated item text after Module 24 saw it. `null` only if the
      // safety layer refused catalogue text, which would itself be a defect.
      text: stringOrNull(life.text),
      fallback: life.fallback === undefined ? null : life.fallback,
    },

    // Module 23 - the same findings in patient language, safety-approved.
    explanations: {
      // `null` = the stage never answered. `false` = it answered and NOTHING
      // was approved, and there is a reviewed notice to show. Different facts.
      available: explanationSet ? set.explanation_available === true : null,
      // Non-empty whenever `available` is false and the stage did answer, and
      // that is ENFORCED here for the same reason as the per-entry `notice`
      // above: the write path's guarantee is not this layer's guarantee. `null`
      // is kept only for `available: null` - the stage never answered, so there
      // is no refusal to explain and the section's own `available` says so.
      notice:
        explanationSet && set.explanation_available !== true
          ? stringOrNull(set.notice) || analysisService.EXPLANATION_SET_NOTICE
          : stringOrNull(set.notice),
      generatedCount: numberOrUndefined(set.generated_count),
      withheldCount: numberOrUndefined(set.withheld_count),
      entries,
    },

    // Module 17's own recommendation list, keyed to the conditions that caused
    // each code. Included because it is the link between a condition card and
    // the guidance text above; it is the SAME catalogue codes Module 26
    // resolves, not a second source of advice.
    fromReport: listOf(clinicalReport.recommendations).map((item) => {
      const row = objectOf(item);
      return {
        code: stringOrNull(row.code),
        text: stringOrNull(row.text),
        category: stringOrNull(row.category),
        conditions: listOf(row.conditions),
        occurrences: numberOrUndefined(row.occurrences),
      };
    }),
  };
}

// ---------------------------------------------------- document quality ------

/**
 * How good the source document was.
 *
 * Not one of the spec's five cards, and deliberately small. It is here because
 * every card above is only as trustworthy as the document behind it: a report
 * with two unreadable pages produces the same clean-looking cards as a perfect
 * scan, and `pagesUnreadable` is the only thing that says otherwise.
 */
function buildDocumentQuality(clinicalReport) {
  const document = objectOf(clinicalReport.document);
  return {
    extractionProvided: booleanOrUndefined(document.extraction_provided),
    extractionConfidence: asIs(document.extraction_confidence),
    pageCount: numberOrUndefined(document.page_count),
    pagesUnreadable: listOf(document.pages_unreadable),
    pagesUnreadableCount: numberOrUndefined(document.pages_unreadable_count),
    // True when part of the document could not be read. A missing test may then
    // be missing from the ANALYSIS rather than absent from the report.
    partialDocument: booleanOrUndefined(document.partial_document),
    featuresReceived: numberOrUndefined(document.features_received),
    validCount: numberOrUndefined(document.valid_count),
    questionableCount: numberOrUndefined(document.questionable_count),
    rejectedCount: numberOrUndefined(document.rejected_count),
    rejectedFeatures: listOf(document.rejected_features),
    missingFeatures: listOf(document.missing_features),
    unmappedCount: numberOrUndefined(document.unmapped_count),
  };
}

// --------------------------------------------------------------- assemble ---

/**
 * Index every evidence line in the report by feature, keeping the MOST
 * INFORMATIVE availability for each.
 *
 * A feature can appear on several lines - one per rule or model that cited it -
 * and they can disagree about availability only in one direction: a line that
 * says the value was observed and a line that says the page was unreadable
 * describe different citations of the same feature. `observed` wins, because a
 * value that was read somewhere is not unavailable; among the absent
 * availabilities `unreadable_document` wins over `not_present_in_report`,
 * because "we could not read it" is the weaker, more cautious claim and
 * downgrading it to "it was not there" would assert something the analysis does
 * not know.
 */
const AVAILABILITY_RANK = Object.freeze({
  observed: 0,
  found_but_not_trusted: 1,
  unreadable_document: 2,
  not_present_in_report: 3,
});

function indexEvidenceLines(clinicalReport) {
  const byFeature = new Map();
  const consider = (item) => {
    const line = objectOf(item);
    if (typeof line.feature !== 'string' || line.feature === '') return;
    const existing = byFeature.get(line.feature);
    if (!existing) {
      byFeature.set(line.feature, line);
      return;
    }
    const rank = AVAILABILITY_RANK[line.availability];
    const existingRank = AVAILABILITY_RANK[existing.availability];
    // An unrecognised availability never displaces a recognised one.
    if (rank === undefined) return;
    if (existingRank === undefined || rank < existingRank) byFeature.set(line.feature, line);
  };

  const explainability = objectOf(clinicalReport.explainability);
  for (const item of listOf(explainability.conditions)) {
    const row = objectOf(item);
    listOf(row.evidence).forEach(consider);
    for (const entry of listOf(row.sources)) {
      const source = objectOf(entry);
      listOf(source.evidence).forEach(consider);
      listOf(objectOf(source.rule).triggering_values).forEach(consider);
      listOf(objectOf(source.ml).input_evidence).forEach(consider);
    }
  }
  return byFeature;
}

/**
 * Build the whole dashboard from what is already stored.
 *
 * `clinicalReport` is REQUIRED and the caller must have checked it: this
 * function does not synthesise a dashboard for a report that was never
 * analysed. An empty-looking dashboard is indistinguishable from the dashboard
 * of a report that genuinely found nothing, which is the fourth-case failure
 * every layer of this pipeline is built to refuse. The controller answers 404
 * instead.
 *
 * @param {object} params.clinicalReport  Modules 17-20, as stored.
 * @param {object|null} params.explanationSet  Module 23, as stored, or null.
 * @param {object|null} params.guidance  Module 26, as stored, or null.
 */
function buildDashboard({ clinicalReport, explanationSet = null, guidance = null }) {
  if (!analysisService.isUsableClinicalReport(clinicalReport)) {
    throw new TypeError('buildDashboard requires a stored clinical report');
  }

  const evidenceLinesByFeature = indexEvidenceLines(clinicalReport);

  return {
    module: 27,
    reportVersion: stringOrNull(clinicalReport.report_version),
    generatedAt: clinicalReport.generated_at === undefined ? null : clinicalReport.generated_at,

    overall: buildOverallCard(clinicalReport),
    conditions: buildConditionCards(clinicalReport),
    laboratory: buildLaboratoryCards(clinicalReport, evidenceLinesByFeature),
    evidence: buildEvidenceSection(clinicalReport),
    recommendations: buildRecommendationsSection(clinicalReport, explanationSet, guidance),
    document: buildDocumentQuality(clinicalReport),

    // Every warning from every stage, with its origin intact. A card is only as
    // good as the document behind it and these are how that shows.
    warnings: listOf(clinicalReport.validation_warnings),
    warningsByStage: objectOf(clinicalReport.warnings_by_stage),
  };
}

module.exports = {
  buildDashboard,
  LAB_STATE,
  // Exported for the module's own tests; not part of the route's contract.
  buildOverallCard,
  buildConditionCards,
  buildLaboratoryCards,
  buildEvidenceSection,
  buildRecommendationsSection,
  buildDocumentQuality,
  indexEvidenceLines,
  labState,
};
