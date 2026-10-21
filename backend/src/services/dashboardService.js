'use strict';

const analysisService = require('./analysisService');


function numberOrUndefined(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function booleanOrUndefined(value) {
  return typeof value === 'boolean' ? value : undefined;
}

function stringOrNull(value) {
  return typeof value === 'string' && value.trim() !== '' ? value : null;
}

function listOf(value) {
  return Array.isArray(value) ? value : [];
}

function objectOf(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
}

function asIs(value) {
  return value === undefined ? null : value;
}


function buildOverallCard(clinicalReport) {
  const overall = objectOf(clinicalReport.overall);
  const summary = objectOf(clinicalReport.summary);
  const derived = analysisService.summariseReport(clinicalReport);

  return {
    status: asIs(derived.overallStatus),
    statusLabel: derived.overallStatusLabel,
    risk: asIs(derived.overallRisk),
    anyAssessed: derived.anyAssessed,
    complete: derived.assessmentComplete,
    caveat: stringOrNull(overall.caveat),

    ruleApplied: stringOrNull(overall.rule_applied),
    policy: stringOrNull(overall.policy),

    assessedConditionCount: numberOrUndefined(overall.assessed_condition_count),
    unassessedConditionCount: numberOrUndefined(overall.unassessed_condition_count),
    unassessedConditions: listOf(overall.unassessed_conditions),
    partiallyAssessedConditions: listOf(overall.partially_assessed_conditions),
    abnormalConditionCount: numberOrUndefined(overall.abnormal_condition_count),
    highRiskConditionCount: numberOrUndefined(overall.high_risk_condition_count),
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


function buildConditionCards(clinicalReport) {
  const conditions = listOf(clinicalReport.conditions);
  const prioritized = listOf(clinicalReport.prioritized);

  const byCondition = new Map();
  for (const item of conditions) {
    const row = objectOf(item);
    if (typeof row.condition === 'string') byCondition.set(row.condition, row);
  }

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

    rank: numberOrUndefined(priority.rank),
    priority: stringOrNull(priority.priority),
    tier: numberOrUndefined(priority.tier),

    status: asIs(priority.status !== undefined ? priority.status : detail.status),
    risk: asIs(priority.risk !== undefined ? priority.risk : detail.risk),
    confidence: asIs(
      priority.confidence !== undefined ? priority.confidence : detail.confidence
    ),
    confidenceBasis: stringOrNull(detail.confidence_basis),

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

    evidenceFeatures: listOf(detail.evidence_features),
    recommendationCodes: listOf(detail.recommendation_codes),
  }));
}


const LAB_STATE = Object.freeze({
  VALID: 'valid',
  QUESTIONABLE: 'questionable',
  REJECTED: 'rejected',
  UNAVAILABLE: 'unavailable',
});

const ABSENT_AVAILABILITIES = Object.freeze(['not_present_in_report', 'unreadable_document']);

function labState(status) {
  if (status === LAB_STATE.VALID) return LAB_STATE.VALID;
  if (status === LAB_STATE.QUESTIONABLE) return LAB_STATE.QUESTIONABLE;
  if (status === LAB_STATE.REJECTED) return LAB_STATE.REJECTED;
  return null;
}

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

      state: labState(row.status),
      status: stringOrNull(row.status),
      usable: booleanOrUndefined(row.usable),
      questionable: booleanOrUndefined(row.questionable),
      clinicallyExtreme: booleanOrUndefined(row.clinically_extreme),
      extremeDirection: stringOrNull(row.extreme_direction),

      referenceLow: asIs(row.reference_low),
      referenceHigh: asIs(row.reference_high),
      referenceRangeRaw: stringOrNull(row.reference_range_raw),
      flag: stringOrNull(row.flag),

      originalTestName: stringOrNull(row.original_test_name),
      originalUnit: stringOrNull(row.original_unit),
      unitConverted: booleanOrUndefined(row.unit_converted),
      unitAssumed: booleanOrUndefined(row.unit_assumed),
      derived: stringOrNull(row.derived),
      censored: stringOrNull(row.censored),
      pageNumber: numberOrUndefined(row.page_number),
      extractionConfidence: asIs(row.extraction_confidence),
      source: stringOrNull(row.source),

      rejectionCode: stringOrNull(row.rejection_code),
      rejectionReason: stringOrNull(row.rejection_reason),

      availability: null,
      availabilityExplanation: null,
    };
  });

  const unavailable = [];
  for (const [feature, line] of evidenceLinesByFeature) {
    if (covered.has(feature)) continue;
    if (!ABSENT_AVAILABILITIES.includes(line.availability)) continue;

    unavailable.push({
      feature,
      displayName: stringOrNull(line.display_name),
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
      availability: stringOrNull(line.availability),
      availabilityExplanation: stringOrNull(line.explanation),
    });
  }

  return cards.concat(unavailable);
}


function projectEvidenceLine(item) {
  const line = objectOf(item);
  return {
    feature: line.feature,
    displayName: stringOrNull(line.display_name),
    value: asIs(line.value),
    unit: stringOrNull(line.unit),
    threshold: asIs(line.threshold),
    comparator: stringOrNull(line.comparator),
    classification: stringOrNull(line.classification),
    referenceLow: asIs(line.reference_low),
    referenceHigh: asIs(line.reference_high),
    note: stringOrNull(line.note),
    sourceStage: stringOrNull(line.source_stage),

    availability: stringOrNull(line.availability),
    availabilityExplanation: stringOrNull(line.explanation),
    rejected: booleanOrUndefined(line.rejected),
    rejectionCode: stringOrNull(line.rejection_code),
    rejectionReason: stringOrNull(line.rejection_reason),
    rejectedValue: asIs(line.rejected_value),
    rejectedUnit: stringOrNull(line.rejected_unit),
    questionable: booleanOrUndefined(line.questionable),
    clinicallyExtreme: booleanOrUndefined(line.clinically_extreme),
    relatedWarnings: listOf(line.related_warnings),
  };
}

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
                probabilitySemantics: stringOrNull(ml.probability_semantics),
                featuresObserved: listOf(ml.features_observed),
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
    rejectedFeaturesJoined: listOf(explainability.rejected_features_joined),
    mlImportanceScope: stringOrNull(explainability.ml_importance_scope),
    mlImportanceCaveat: stringOrNull(explainability.ml_importance_caveat),
  };
}


function buildRecommendationsSection(clinicalReport, explanationSet, guidance) {
  const set = objectOf(explanationSet);
  const life = objectOf(guidance);

  const entries = listOf(set.explanations).map((item) => {
    const entry = objectOf(item);
    const available = entry.generated_explanation_available === true;

    return {
      subject: stringOrNull(entry.subject),
      feature: stringOrNull(entry.feature),
      conditions: listOf(entry.conditions),
      outcome: stringOrNull(entry.outcome),
      available,
      explanation: available ? stringOrNull(entry.explanation) : null,
      notice: available
        ? null
        : stringOrNull(entry.notice) || analysisService.EXPLANATION_NOTICE_FALLBACK,
      fallback: entry.fallback === undefined ? null : entry.fallback,
      groundingAvailable: booleanOrUndefined(entry.grounding_available),
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
    guidance: {
      available: Boolean(guidance),
      generated: booleanOrUndefined(life.generated),
      source: stringOrNull(life.source),
      conditions: listOf(life.conditions),
      features: listOf(life.features),
      items: listOf(life.items).map((item) => {
        const row = objectOf(item);
        return {
          code: stringOrNull(row.code),
          text: stringOrNull(row.text),
          category: stringOrNull(row.category),
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
      text: stringOrNull(life.text),
      fallback: life.fallback === undefined ? null : life.fallback,
    },

    explanations: {
      available: explanationSet ? set.explanation_available === true : null,
      notice:
        explanationSet && set.explanation_available !== true
          ? stringOrNull(set.notice) || analysisService.EXPLANATION_SET_NOTICE
          : stringOrNull(set.notice),
      notExplained: listOf(set.skipped)
        .map((item) => {
          const entry = objectOf(item);
          return {
            feature: stringOrNull(entry.feature),
            reason: stringOrNull(entry.reason),
          };
        })
        .filter((item) => item.feature),
      generatedCount: numberOrUndefined(set.generated_count),
      withheldCount: numberOrUndefined(set.withheld_count),
      entries,
    },

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


function buildDocumentQuality(clinicalReport) {
  const document = objectOf(clinicalReport.document);
  return {
    extractionProvided: booleanOrUndefined(document.extraction_provided),
    extractionConfidence: asIs(document.extraction_confidence),
    pageCount: numberOrUndefined(document.page_count),
    pagesUnreadable: listOf(document.pages_unreadable),
    pagesUnreadableCount: numberOrUndefined(document.pages_unreadable_count),
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

function buildUnanalysedSection(engineeredFeatures, extraction, parameterGlossary) {
  const glossary = parameterGlossary === null || parameterGlossary === undefined
    ? null
    : objectOf(parameterGlossary);
  const unmapped = listOf(objectOf(engineeredFeatures).unmapped);
  if (!unmapped.length) {
    return {
      count: 0,
      labFlaggedCount: 0,
      descriptionsPresent: glossary !== null,
      describedCount: 0,
      withheldCount: 0,
      items: [],
    };
  }

  const printed = new Map();
  for (const entry of listOf(objectOf(extraction).extracted_parameters)) {
    const row = objectOf(entry);
    if (stringOrNull(row.test_name)) printed.set(row.test_name, row);
  }

  const described = new Map();
  for (const entry of listOf(glossary && glossary.entries)) {
    const row = objectOf(entry);
    const name = stringOrNull(row.test_name);
    if (name !== null && !described.has(name)) described.set(name, row);
  }

  const items = unmapped.map((entry) => {
    const item = objectOf(entry);
    const source = objectOf(printed.get(item.test_name));
    const flag = stringOrNull(source.flag);

    const numericValue = numberOrUndefined(source.value_numeric);
    const printedLow = numberOrUndefined(source.reference_low);
    const printedHigh = numberOrUndefined(source.reference_high);
    const above = numericValue !== undefined && printedHigh !== undefined
      && numericValue > printedHigh;
    const below = numericValue !== undefined && printedLow !== undefined
      && numericValue < printedLow;
    const outsidePrintedInterval = above || below;
    const derivedDirection = outsidePrintedInterval
      ? (above ? "high" : "low")
      : null;
    const glossaryEntry = described.get(item.test_name);
    const descriptionFields = {};
    if (glossaryEntry !== undefined) {
      const description = stringOrNull(glossaryEntry.description);
      const available = glossaryEntry.available === true && description !== null;
      descriptionFields.descriptionAvailable = available;
      if (available) {
        descriptionFields.description = description;
        descriptionFields.descriptionOrigin =
          glossaryEntry.origin === 'reviewed' ? 'reviewed' : 'model';
      } else descriptionFields.descriptionNotice = stringOrNull(glossaryEntry.notice);
    }
    return {
      ...descriptionFields,
      testName: stringOrNull(item.test_name),
      value: asIs(item.value_raw),
      unit: stringOrNull(item.unit),
      reason: stringOrNull(item.reason),
      pageNumber: numberOrUndefined(item.page_number),
      labFlag: flag || derivedDirection,
      labFlaggedAbnormal:
        outsidePrintedInterval || (Boolean(flag) && flag.toLowerCase() !== "normal"),
      labReferenceLow: numberOrUndefined(source.reference_low),
      labReferenceHigh: numberOrUndefined(source.reference_high),
      labReferenceRangeRaw: stringOrNull(source.reference_range_raw),
    };
  });

  return {
    count: items.length,
    labFlaggedCount: items.filter((item) => item.labFlaggedAbnormal).length,
    descriptionsPresent: glossary !== null,
    describedCount: items.filter((item) => item.descriptionAvailable === true).length,
    withheldCount: items.filter((item) => item.descriptionAvailable === false).length,
    items,
  };
}


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

function buildDashboard({
  clinicalReport,
  explanationSet = null,
  guidance = null,
  engineeredFeatures = null,
  extraction = null,
  parameterGlossary = null,
}) {
  if (!analysisService.isUsableClinicalReport(clinicalReport)) {
    throw new TypeError('buildDashboard requires a stored clinical report');
  }

  const evidenceLinesByFeature = indexEvidenceLines(clinicalReport);

  return {
    module: 27,
    reportVersion: stringOrNull(clinicalReport.report_version),
    generatedAt: clinicalReport.generated_at === undefined ? null : clinicalReport.generated_at,

    overall: buildOverallCard(clinicalReport),
    unanalysed: buildUnanalysedSection(engineeredFeatures, extraction, parameterGlossary),
    conditions: buildConditionCards(clinicalReport),
    laboratory: buildLaboratoryCards(clinicalReport, evidenceLinesByFeature),
    evidence: buildEvidenceSection(clinicalReport),
    recommendations: buildRecommendationsSection(clinicalReport, explanationSet, guidance),
    document: buildDocumentQuality(clinicalReport),

    warnings: listOf(clinicalReport.validation_warnings),
    warningsByStage: objectOf(clinicalReport.warnings_by_stage),
  };
}

module.exports = {
  buildDashboard,
  LAB_STATE,
  buildOverallCard,
  buildConditionCards,
  buildLaboratoryCards,
  buildEvidenceSection,
  buildRecommendationsSection,
  buildDocumentQuality,
  indexEvidenceLines,
  labState,
  buildUnanalysedSection,
};
