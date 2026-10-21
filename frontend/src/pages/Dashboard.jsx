import { useEffect, useRef, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, ApiError } from '../lib/api';
import { Absent, Risk, Value, WarningList } from '../components/Absent';
import { isPresent, pageList } from '../lib/absence';
import RiskGauge from '../components/RiskGauge';
import CoverageRadar from '../components/CoverageRadar';
import ReadAloud from '../components/ReadAloud';
import { PATIENT_LABEL } from '../lib/labels';
import { ProfileIdentityNotice } from '../components/IdentityNotice';
import { isPatientDetail } from '../lib/sources';
import Icon from '../components/Icon';
import { READING_LINKS, READING_SOURCE } from '../lib/readingLinks';
import { readableName } from '../lib/displayName';
import { friendlyPageError } from '../lib/friendlyErrors';


function OverallCard({ overall }) {
  if (!overall) return null;
  const assessed = overall.anyAssessed === true;
  const riskClass =
    assessed && typeof overall.risk === 'string' ? ` overall--${overall.risk.toLowerCase()}` : '';

  return (
    <section className={`card overall${riskClass}`}>
      <h2>Overall</h2>

      <p className="overall__status">
        {isPresent(overall.statusLabel) ? (
          <strong>{overall.statusLabel}</strong>
        ) : (
          <Absent
            label="Not assessed"
            reason="No overall status was established for this report."
          />
        )}
      </p>

      <p className="overall__risk">
        Overall risk: <Risk risk={overall.risk} assessed={assessed} />
      </p>


      {overall.sourcesFailed?.length ? (
        <p className="caveat">
          Some analysis stages did not complete: {overall.sourcesFailed.join(', ')}.
        </p>
      ) : null}
    </section>
  );
}


const PATIENT_STATUS = {
  'Indicated': 'These results point to this — worth discussing with a doctor',
  'Borderline': 'Close to the usual limit — worth keeping an eye on',
  'Not Indicated': 'Nothing in these results points to this',
  'Insufficient Data': 'Not enough information in this report to check this',
  'Inconclusive': 'The checks did not agree, so this is unresolved',
};

const RISK_FACTOR_STATUS = {
  'Indicated': 'Several things here are known to raise this risk — worth discussing with a doctor',
  'Borderline': 'Some things here are known to raise this risk — worth keeping an eye on',
  'Not Indicated': 'Nothing in these results points to this',
  'Insufficient Data': 'Not enough information in this report to check this',
  'Inconclusive': 'The checks did not agree, so this is unresolved',
};

const MODEL_STATUS = {
  'Indicated': 'A statistical model flagged this — worth discussing with a doctor',
  'Borderline': 'A statistical model flagged this as borderline — worth keeping an eye on',
};

function countsRiskFactors(evidence) {
  const sources = evidence?.sources || [];
  if (!sources.length) return false;
  const counted = sources.some(
    (s) => s.assessmentBasisFamily === 'risk_factor_burden'
      || s.assessmentBasis === 'risk_factor_count'
  );
  const compared = sources.some((s) => s.assessmentBasis === 'threshold_comparison');
  return counted && !compared;
}

const statusText = (status, basis = 'default') => {
  if (!isPresent(status)) return null;
  const table =
    basis === 'model' ? MODEL_STATUS : basis === 'risk_factors' ? RISK_FACTOR_STATUS : PATIENT_STATUS;
  return table[status] || PATIENT_STATUS[status] || status;
};


const GENERAL_PREFIXES = [
  'General educational guidance for most adults includes ',
];

function trimGeneralPrefix(text) {
  if (typeof text !== 'string') return text;
  for (const prefix of GENERAL_PREFIXES) {
    if (text.startsWith(prefix)) {
      const rest = text.slice(prefix.length);
      return rest.charAt(0).toUpperCase() + rest.slice(1);
    }
  }
  return text;
}

const ALWAYS_ON_SCREEN_CODES = new Set([
  'NOT_A_DIAGNOSIS',
  'MONITOR_OVER_TIME',
  'DISCUSS_WITH_CLINICIAN',
]);

function groupGuidance(items, flaggedConditions) {
  const relevant = [];
  for (const item of items || []) {
    if (ALWAYS_ON_SCREEN_CODES.has(item.code)) continue;
    const because = matchedConditions(item, flaggedConditions);
    if (because.length) relevant.push({ ...item, because });
  }
  return { relevant };
}

function matchedConditions(item, flaggedConditions) {
  return (item.becauseOfConditions || []).filter((name) =>
    flaggedConditions.has(name)
  );
}

function becausePhrase(item) {
  const names = item.because || [];
  if (!names.length) return null;
  if (names.length === 1) return names[0];
  if (names.length === 2) return `${names[0]} and ${names[1]}`;
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
}

function sharedBecausePhrase(items) {
  if (!items?.length) return null;
  const key = (item) => [...new Set(item.because || [])].sort().join(' ');
  const first = key(items[0]);
  if (!items.every((item) => key(item) === first)) return null;
  return becausePhrase(items[0]);
}

function Explanations({
  explanations,
  resultFeatures,
  unassessedCount = 0,
  unassessedItems = [],
  assessedResultCount = 0,
}) {
  const entries = explanations?.entries || [];

  const written = entries.filter((entry) => entry.available === true
    && isPresent(entry.explanation));
  const missing = entries.filter((entry) => entry.available !== true);

  const notAttempted = (explanations?.notExplained || []).filter(
    (item) => item && resultFeatures?.has(item.feature)
  );

  const describedUnassessed = (unassessedItems || []).filter(
    (item) => item.descriptionAvailable === true || item.descriptionAvailable === false
  );
  const disclosures = [
    ...written.map((entry, index) => ({
      key: entry.feature || `written-${index}`,
      subject: PATIENT_LABEL[entry.feature] || entry.subject,
      body: (
        <p className="explanation__text">{trimClosingAdvice(entry.explanation)}</p>
      ),
      speech: trimClosingAdvice(entry.explanation),
    })),
    ...describedUnassessed.map((item, index) => ({
      key: `${item.testName}-${index}`,
      subject: readableName(item.testName),
      body: (
        <div className="explanation__body">
          <ParameterDescription item={item} />
        </div>
      ),
      speech: item.descriptionAvailable === true ? item.description : null,
    })),
  ];

  if (
    !written.length
    && !missing.length
    && !describedUnassessed.length
  ) {
    return null;
  }

  return (
    <section className="explanations">
      <h2>
        What these results mean
        {disclosures.length ? (
          <span className="disclosure__count">{disclosures.length}</span>
        ) : null}
      </h2>
      {disclosures.length ? (
        <p className="explanations__lead">Open a result to read what it measures and what yours means.</p>
      ) : null}

      <div className="explanation-list">
        {disclosures.map((entry) => (
          <details className="card explanation disclosure" key={entry.key}>
            <summary className="disclosure__summary">
              <span className="explanation__mark" aria-hidden="true">
                {subjectInitials(entry.subject)}
              </span>
              <h3 className="explanation__subject">{entry.subject}</h3>
              <span className="explanation__open" aria-hidden="true">
                <span className="disclosure__chevron" />
              </span>
            </summary>
            {entry.body}
            {entry.speech ? (
              <ReadAloud text={`${entry.subject}. ${entry.speech}`} label={entry.subject} />
            ) : null}
          </details>
        ))}
      </div>

      {missing.length ? (
        <p className="hint explanations__absent">
          No plain-language explanation could be prepared for{' '}
          {missing
            .map((entry) => PATIENT_LABEL[entry.feature] || entry.subject)
            .join(', ')}
          . The results themselves are unaffected — they were produced by the
          analysis, not by the writing step.
        </p>
      ) : null}

      {notAttempted.length && written.length ? (
        <p className="hint explanations__absent">
          {andList(notAttempted.map((item) => PATIENT_LABEL[item.feature] || item.feature))}{' '}
          {notAttempted.length === 1 ? 'has' : 'have'} no explanation above.
          Only a set number of explanations is written for each report, and
          this one has more results than that — nothing was wrong with{' '}
          {notAttempted.length === 1 ? 'this result' : 'these results'}, and{' '}
          {notAttempted.length === 1 ? 'its value is' : 'their values are'} in
          the table above.
        </p>
      ) : null}

      <p className="hint explanations__provenance">
        Unless marked otherwise, these were written by a language model from
        your measured values and reviewed reference material, and checked
        before being shown. They explain what
        each test measures — they do not diagnose, and no single laboratory
        value settles anything on its own. Take anything flagged above to a
        qualified healthcare professional.
      </p>
    </section>
  );
}

function valueVerdicts(evidenceConditions) {
  const byFeature = new Map();

  for (const condition of evidenceConditions || []) {
    for (const line of condition.lines || []) {
      if (line.rejected || !isPresent(line.value)) continue;
      const existing = byFeature.get(line.feature);
      if (existing && existing.direction) continue;

      const crossed = crossing(line);
      if (crossed) {
        const above = line.comparator === '>' || line.comparator === '>=';
        byFeature.set(line.feature, {
          direction: above ? 'high' : 'low',
          label: above ? 'High' : 'Low',
          crossedText: crossed,
        });
        continue;
      }

      byFeature.set(line.feature, { direction: null, label: 'In range' });
    }
  }
  return byFeature;
}

function trimClosingAdvice(text) {
  if (typeof text !== 'string') return text;

  const sentences = text.split(/(?<=[.!?])\s+(?=[A-Z])/);
  if (sentences.length < 2) return text;

  const kept = [...sentences];
  while (
    kept.length > 1
    && /qualified healthcare professional|consult a (doctor|clinician)/i.test(
      kept[kept.length - 1]
    )
  ) {
    kept.pop();
  }
  return kept.join(' ').trim();
}

const SKIP_REASON = {
  no_canonical_feature:
    'this tool does not assess this test',
  unsupported_specimen:
    'this tool only assesses blood tests',
  distinct_analyte:
    'this is a related but different measurement from the one assessed',
};

function ParameterDescription({ item }) {
  if (item.descriptionAvailable === true) {
    return (
      <>
        <p className="unanalysed__description">{item.description}</p>
        {item.descriptionOrigin === 'reviewed' ? (
          <p className="hint unanalysed__origin">
            From VaidyaAI’s reviewed reference material, not written by the
            language model.
          </p>
        ) : null}
      </>
    );
  }
  if (item.descriptionAvailable === false) {
    return (
      <p className="unanalysed__description unanalysed__description--withheld">
        {isPresent(item.descriptionNotice)
          ? item.descriptionNotice
          : 'No description of this test was produced. The value shown for it comes from your report and is unaffected.'}
      </p>
    );
  }
  return null;
}


const STATUS_IN_ENGLISH = {
  Healthy: 'Nothing this tool checked was outside its usual range.',
  'Healthy (partial assessment)':
    'Nothing this tool was able to check was outside its usual range — but it could not check everything, so this is not a clean bill of health.',
  'Needs Monitoring':
    'One of the things this tool checked was outside its usual range. It is worth keeping an eye on and worth raising at your next appointment.',
  'Needs Medical Attention':
    'One of the things this tool checked was outside its usual range by enough that it should be looked at by a doctor.',
  'Not Assessed':
    'This report could not be assessed. That is not a result — it means no finding was reached either way.',
};

function isProfileDerived(evidence) {
  const lines = evidence?.lines || [];
  if (!lines.length) return false;
  return lines.every((line) => isPatientDetail(line.sourceStage));
}

function usesReportDetails(cards, evidenceFor) {
  return cards.some((card) =>
    (evidenceFor.get(card.condition)?.lines || []).some(
      (line) => line.sourceStage === 'report_details'
    )
  );
}

const commaSafeSeparator = (names) =>
  names.some((name) => String(name).includes(',')) ? '; ' : ', ';

const nameList = (names) => names.join(commaSafeSeparator(names));

const listOfNames = (cards) => nameList(cards.map((card) => card.condition));

const andList = (names) => {
  if (!names.length) return '';
  if (names.length === 1) return String(names[0]);
  return `${names.slice(0, -1).join(commaSafeSeparator(names))} and ${names[names.length - 1]}`;
};

function UnreadablePagesNotice({ document }) {
  const pages = document?.pagesUnreadable || [];
  if (!pages.length && document?.partialDocument !== true) return null;
  return (
    <section
      className="card identity-warning unreadable-pages"
      role="note"
      aria-label="Part of this report could not be read"
    >
      <h2>
        {pages.length ? pageList(pages) : 'Part'} of this report could not be read this time
      </h2>
      <p>
        The tests on {pages.length === 1 ? 'that page' : pages.length ? 'those pages' : 'that part'} are
        not in this analysis, so they were not checked, and the result below may change once they are.
      </p>
      <p>
        Go to the <Link to="/reports">Reports</Link> page and press <strong>Re-analyse</strong> to try
        again.
      </p>
    </section>
  );
}

function InShort({
  dashboard,
  flaggedCards,
  clearCards,
  reportId,
  verdicts,
}) {
  const bodyRef = useRef(null);
  const [prose, setProse] = useState(null);
  const [context, setContext] = useState([]);
  const overall = dashboard.overall;

  useEffect(() => {
    let cancelled = false;
    if (!reportId || !overall) return undefined;

    const direction = (word) => {
      const w = String(word || '').toLowerCase();
      if (w === 'high' || w === 'raised') return 'raised';
      if (w === 'low' || w === 'lowered') return 'lowered';
      return null;
    };

    const findings = [];
    for (const [feature, verdict] of (verdicts || new Map()).entries()) {
      const d = direction(verdict?.direction || verdict?.label);
      if (!d) continue;
      const row = (dashboard.laboratory || []).find((r) => r.feature === feature);
      if (!row || isPatientDetail(row.source)) continue;
      const name = row.originalTestName || PATIENT_LABEL[feature] || row.displayName;
      if (name) findings.push({ test_name: name, direction: d });
    }
    for (const item of dashboard.unanalysed?.items || []) {
      if (item.labFlaggedAbnormal !== true) continue;
      const d = direction(item.labFlag);
      if (d && item.testName) findings.push({ test_name: item.testName, direction: d });
    }
    if (!findings.length) return undefined;

    (async () => {
      try {
        const res = await api.describeFindings(reportId, findings);
        const entries = (res?.context?.entries || []).filter(
          (e) => e && typeof e.test_name === 'string' && e.test_name.trim()
        );
        const described = entries.some(
          (e) => e.available === true && typeof e.text === 'string' && e.text.trim()
        );
        const coming = entries.some((e) => e.refused_by === 'in_progress');
        if (!cancelled && (described || coming)) setContext(entries);
      } catch {
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reportId]);

  useEffect(() => {
    let cancelled = false;
    if (!reportId || !overall || !bodyRef.current) return undefined;
    const sentences = [...bodyRef.current.querySelectorAll('p')]
      .map((node) => node.textContent.replace(/\s+/g, ' ').trim())
      .filter(Boolean);
    if (!sentences.length) return undefined;
    const names = [
      ...[...flaggedCards, ...clearCards].map(
        (card) => card.condition
      ),
      ...(dashboard.unanalysed?.items || [])
        .filter((item) => item.labFlaggedAbnormal === true)
        .map((item) => item.testName),
    ].filter(Boolean);

    (async () => {
      try {
        const res = await api.rewriteSummary(reportId, sentences, names);
        const text = res?.prose?.text;
        if (!cancelled && typeof text === 'string' && text.trim()) {
          setProse(text.trim());
        }
      } catch {
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reportId]);

  if (!overall) return null;

  const label = isPresent(overall.statusLabel) ? overall.statusLabel : null;
  const inEnglish =
    label === null ? null : STATUS_IN_ENGLISH[label] ?? null;

  const checked = flaggedCards.length + clearCards.length;
  const unanalysed = dashboard.unanalysed || {};
  const coveredByACondition = new Set(
    (dashboard.conditions || []).flatMap((item) => item.evidenceFeatures || [])
  );
  const furtherRows = (dashboard.laboratory || [])
    .filter((row) => {
      if (isPatientDetail(row.source)) return false;
      if (coveredByACondition.has(row.feature)) return false;
      const verdict = verdicts?.get(row.feature);
      return Boolean(verdict?.direction && verdict.direction !== 'normal');
    })
    .map((row) => ({
      testName:
        row.originalTestName || PATIENT_LABEL[row.feature] || row.displayName,
    }))
    .filter((row) => Boolean(row.testName));

  const labFlagged = [
    ...furtherRows,
    ...(unanalysed.items || []).filter((item) => item.labFlaggedAbnormal === true),
  ];
  const evidenceFor = new Map(
    (dashboard.evidence?.conditions || []).map((item) => [item.condition, item])
  );
  const fromProfile = flaggedCards.filter((card) =>
    isProfileDerived(evidenceFor.get(card.condition))
  );

  return (
    <section className="card in-short">
      <h2>In short</h2>

      <p className="in-short__headline">
        {inEnglish !== null ? (
          <strong>{inEnglish}</strong>
        ) : label !== null ? (
          <>
            <strong>This report was assessed as “{label}”.</strong> This screen
            has no plain-English wording for that result, so it is shown exactly
            as the analysis recorded it.
          </>
        ) : (
          <Absent
            label="No overall result"
            reason="No overall status was established for this report, so there is nothing to summarise here."
          />
        )}
      </p>

      <div className="in-short__body" ref={bodyRef} hidden={Boolean(prose)}>


      {checked > 0 ? (
        <p>
          This tool checked <strong>{checked}</strong> condition
          {checked === 1 ? '' : 's'} against a fixed set of thresholds.{' '}
          {flaggedCards.length ? (
            <>
              <strong>
                {flaggedCards.length} need
                {flaggedCards.length === 1 ? 's' : ''} a closer look
              </strong>
              : {listOfNames(flaggedCards)}.
              {clearCards.length
                ? ` The other ${clearCards.length} showed nothing: ${listOfNames(
                    clearCards
                  )}.`
                : ''}
            </>
          ) : (
            <>
              None of them showed anything outside its usual range
              {clearCards.length ? `: ${listOfNames(clearCards)}` : ''}.
            </>
          )}
        </p>
      ) : null}

      {fromProfile.length ? (
        <p className="hint">
          {nameList(fromProfile.map((card) => card.condition))}{' '}
          {fromProfile.length === 1 ? 'comes' : 'come'} from{' '}
          {usesReportDetails(fromProfile, evidenceFor)
            ? 'details about you — your profile, and the age and sex printed on the report —'
            : 'the details you entered — your height, weight, age and the answers you gave —'}{' '}
          not from anything measured in this report.
          {fromProfile.length === flaggedCards.length ? (
            <>
              {' '}
              That is why{' '}
              {fromProfile.length === 1 ? 'it can be flagged' : 'they can be flagged'}{' '}
              while every laboratory result on the page is in range.
            </>
          ) : null}
        </p>
      ) : null}

      {labFlagged.length ? (
        <p className="caveat">
          <strong>
            {labFlagged.length} further result
            {labFlagged.length === 1 ? ' is' : 's are'} outside the range
            printed on the report
          </strong>{' '}
          — {nameList(labFlagged.map((item) => readableName(item.testName)))}. Worth raising
          with a qualified healthcare professional.
        </p>
      ) : null}



      {overall.sourcesFailed?.length ? (
        <p className="caveat">
          Some stages of the analysis did not complete:{' '}
          {overall.sourcesFailed.join(', ')}. What they would have contributed
          is missing from everything above.
        </p>
      ) : null}

      </div>

      {prose ? <p className="in-short__prose">{prose}</p> : null}

      {context.length ? (
        <div className="in-short__context">
          {context.map((entry, index) => {
            const described =
              entry.available === true
              && typeof entry.text === 'string'
              && entry.text.trim();
            return (
              <p key={`${entry.test_name}-${index}`}>
                <strong>
                  {entry.test_name}
                  {entry.direction === 'raised' ? ' (raised)' : ' (lowered)'}
                </strong>{' '}
                {described ? (
                  entry.text
                ) : entry.refused_by === 'in_progress' ? (
                  <span className="absent">
                    A description is still being prepared; it will appear when
                    you open this page again. The value itself is in the table
                    above and is unaffected.
                  </span>
                ) : (
                  <span className="absent">
                    No general description could be prepared for this result.
                    The value itself is in the table above and is unaffected.
                  </span>
                )}
              </p>
            );
          })}
        </div>
      ) : null}

      <p className="in-short__closing">
        This is health education and decision support. It is not a diagnosis,
        and it is not a substitute for advice from a qualified healthcare
        professional. Take this report — and anything marked above — to one.
      </p>
    </section>
  );
}

const RADAR_LABEL = {
  'High Cholesterol': 'Cholesterol',
  'High Triglycerides': 'Triglycerides',
  'Vitamin D Deficiency': 'Vitamin D',
  'Elevated Vitamin D': 'Vitamin D (high)',
  'Vitamin B12 Deficiency': 'Vitamin B12',
  'Elevated Hemoglobin': 'Haemoglobin (high)',
  'Kidney Disease': 'Kidney',
  'Heart Disease': 'Heart',
  'Liver Disease': 'Liver',
};


const labelFor = (line) =>
  PATIENT_LABEL[line.feature] || line.displayName || line.feature;

const titleCase = (text) =>
  (typeof text === 'string' && text ? text.charAt(0).toUpperCase() + text.slice(1) : text);

function crossing(line) {
  const { comparator, threshold, value, unit } = line;
  if (!isPresent(threshold) || !isPresent(value) || !isPresent(comparator)) {
    return null;
  }
  const suffix = isPresent(unit) ? ` ${unit}` : '';
  const above = comparator === '>' || comparator === '>=';
  const crossed = above ? value >= threshold : value <= threshold;
  if (!crossed) return null;
  return `${above ? 'above' : 'below'} ${threshold}${suffix}`;
}

function printedPosition(value, low, high) {
  if (!isPresent(value)) return null;
  const hasLow = isPresent(low);
  const hasHigh = isPresent(high);
  if (!hasLow && !hasHigh) return null;
  if (hasHigh && value > high) return 'high';
  if (hasLow && value < low) return 'low';
  return 'normal';
}

function printedRange(line) {
  const { referenceLow: low, referenceHigh: high, unit } = line;
  const suffix = isPresent(unit) ? ` ${unit}` : '';
  if (isPresent(low) && isPresent(high)) return `report range ${low}–${high}${suffix}`;
  if (isPresent(high)) return `report limit ${high}${suffix}`;
  if (isPresent(low)) return `report minimum ${low}${suffix}`;
  return null;
}

function summariseEvidence(evidence) {
  const byFeature = new Map();

  for (const line of evidence?.lines || []) {
    if (line.rejected) continue;
    const existing = byFeature.get(line.feature);
    const score = (isPresent(line.value) ? 2 : 0) + (isPresent(line.threshold) ? 1 : 0);
    const existingScore = existing
      ? (isPresent(existing.value) ? 2 : 0) + (isPresent(existing.threshold) ? 1 : 0)
      : -1;
    if (score > existingScore) byFeature.set(line.feature, line);
  }

  const measured = [];
  const context = [];
  const missing = [];
  for (const line of byFeature.values()) {
    if ((line.sourceStage === 'lab_report' || line.sourceStage === 'calculated')
      && isPresent(line.value)) {
      measured.push(line);
    } else if (PATIENT_LABEL[line.feature]) {
      if (line.availability === 'observed') context.push(line);
      else missing.push(line);
    }
  }
  return { measured, context, missing };
}

const FINDING_STATUS = ['Indicated', 'Borderline'];

function flaggedByModelAlone(evidence) {
  const sources = (evidence?.sources || []).filter((s) => s.assessed !== false);
  const rule = sources.find((s) => s.sourceKind === 'clinical_rule');
  const model = sources.find((s) => s.sourceKind === 'machine_learning');
  if (!rule || !model) return false;

  const ruleFoundNothing = rule.status === 'Not Indicated';
  const modelFoundSomething = FINDING_STATUS.includes(model.status);
  return ruleFoundNothing && modelFoundSomething;
}

function plainSources(sourceKinds) {
  const kinds = new Set(sourceKinds || []);
  const rule = kinds.has('clinical_rule');
  const model = kinds.has('machine_learning');
  if (rule && model) {
    return 'Checked against standard clinical thresholds, and also assessed '
      + 'by a statistical model.';
  }
  if (rule) return 'Checked against standard clinical thresholds.';
  if (model) return 'Assessed by a statistical model trained on population data.';
  return null;
}

function contextPhrase(context) {
  const names = context.map(labelFor).filter(Boolean);
  if (!names.length) return null;
  return andList(names);
}

function subjectInitials(subject) {
  const words = String(subject || '')
    .replace(/\(.*?\)/g, ' ')
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!words.length) return '?';
  if (words.length === 1) return words[0].slice(0, 2);
  return (words[0][0] + words[1][0]).toUpperCase();
}

function ConditionCard({ card, evidence }) {
  const assessed = card.assessed !== false;
  const { measured, context, missing } = summariseEvidence(evidence);
  const alsoConsidered = contextPhrase(context);
  const notAvailable = contextPhrase(missing);

  const verdictUnexplained = !measured.some((line) => crossing(line));

  const modelAlone = flaggedByModelAlone(evidence);

  const statusWording = statusText(
    card.status,
    modelAlone ? 'model' : countsRiskFactors(evidence) ? 'risk_factors' : 'default'
  );

  const riskClass =
    assessed && typeof card.risk === 'string' ? ` condition--${card.risk.toLowerCase()}` : '';

  return (
    <li className={`card condition${riskClass}`}>
      <div className="condition__head">
        <strong>{card.condition}</strong>
        <Risk
          risk={card.risk}
          assessed={assessed}
          reason={
            assessed
              ? 'No risk level was established for this condition.'
              : 'This condition was not assessed, so it carries no risk level.'
          }
        />
      </div>

      <p className="condition__status">
        {statusWording ? (
          statusWording
        ) : (
          <Absent reason="No decision was reached for this condition." />
        )}
      </p>

      {measured.length ? (
        <dl className="measured">
          {measured.map((line) => {
            const calculated = line.sourceStage === 'calculated';
            const note = calculated
              ? [crossing(line), 'calculated by VaidyaAI, not printed on the report']
                .filter(Boolean)
                .join('; ')
              : crossing(line) || printedRange(line);
            return (
              <div className="measured__row" key={line.feature}>
                <dt className="measured__name">{labelFor(line)}</dt>
                <dd className="measured__value">
                  {line.value}
                  {isPresent(line.unit) ? ` ${line.unit}` : ''}
                </dd>
                <dd className={`measured__note${crossing(line) ? ' measured__note--crossed' : ''}`}>
                  {note || ''}
                </dd>
              </div>
            );
          })}
        </dl>
      ) : null}

      {notAvailable ? (
        <p className="caveat">
          No value was available for your {notAvailable}, so{' '}
          {missing.length === 1 ? 'it' : 'they'} could not be taken into
          account here.
        </p>
      ) : null}

      {alsoConsidered ? (
        <p className="hint">
          Your {alsoConsidered} {context.length === 1 ? 'was' : 'were'} also taken
          into account.
        </p>
      ) : null}

      {card.partiallyAssessed === true ? (
        <p className="caveat">
          This topic could only be partly assessed, so the picture is
          incomplete.
        </p>
      ) : null}


      {modelAlone ? (
        <p className="caveat">
          No measured value crossed a standard limit for this. The model
          compares your results with patterns in population data — it cannot
          confirm a condition.
        </p>
      ) : null}

      {!modelAlone && verdictUnexplained && plainSources(card.sourceKinds) ? (
        <p className="hint">{plainSources(card.sourceKinds)}</p>
      ) : null}
    </li>
  );
}

const REJECTED_FOR_READER =
  'This result could not be used, so nothing on this page is based on it.';

function LabRow({ row, showVerdict, verdict, fromProfile }) {
  const usable = row.usable === true;
  const friendly = PATIENT_LABEL[row.feature];
  const printed = fromProfile
    ? null
    : (isPresent(row.originalTestName) ? row.originalTestName : null);
  const canonical = friendly
    || (isPresent(row.displayName) ? row.displayName : row.feature);

  const numericText =
    typeof row.value === 'string' &&
    row.value.trim() !== '' &&
    Number.isFinite(Number(row.value.replace(/,/g, '')));
  const numericValue =
    (typeof row.value === 'number' && Number.isFinite(row.value)) || numericText;
  const displayValue =
    !numericValue && typeof row.value === 'string' && row.value.length
      ? row.value.charAt(0).toUpperCase() + row.value.slice(1)
      : row.value;

  return (
    <tr className={`lab lab--${row.state || 'unknown'}`}>
      <th scope="row">
        {readableName(printed || titleCase(canonical))}
        {printed && canonical.toLowerCase() !== printed.toLowerCase() ? (
          <span className="lab__printed">{canonical}</span>
        ) : null}
      </th>

      <td className={numericValue ? undefined : 'lab__word'}>
        <Value
          value={displayValue}
          unit={row.unit}
          available={usable}
          reason={
            row.state === 'rejected'
              ? REJECTED_FOR_READER
              : isPresent(row.availabilityExplanation)
                ? row.availabilityExplanation
                : undefined
          }
          label={row.state === 'rejected' ? 'Not usable' : undefined}
        />
      </td>

      {showVerdict ? (
        <td>
          {verdict ? (
            <>
              <span
                className={`verdict verdict--${
                  verdict.mixed ? 'mixed' : verdict.direction || 'normal'
                }`}
              >
                {verdict.label}
              </span>
              {verdict.detail ? (
                <span className="verdict__detail">{verdict.detail}</span>
              ) : null}
              {verdict.secondary ? (
                <span className="verdict__secondary">{verdict.secondary}</span>
              ) : null}
            </>
          ) : (
            <>
              <span className="absent">not checked</span>
              {isPresent(row.referenceRangeRaw) ? (
                <span className="verdict__secondary">
                  The report prints “{row.referenceRangeRaw}” beside this
                  value — a band label, not a normal range.
                </span>
              ) : null}
            </>
          )}
        </td>
      ) : null}

    </tr>
  );
}

const COLUMN_TITLES = {
  lab: ['Test', 'Result'],
  profile: ['Detail', 'You entered'],
  report: ['Detail', 'Printed on the report'],
};

function LabTable({ rows, caption, verdicts, fromProfile = false, source }) {
  if (!rows.length) return null;
  const showVerdict = !fromProfile;
  const [nameTitle, valueTitle] = COLUMN_TITLES[source || (fromProfile ? 'profile' : 'lab')];

  return (
    <>
      <table className={fromProfile ? 'lab-table lab-table--details' : 'lab-table'}>
        <thead>
          <tr>
            <th scope="col">{nameTitle}</th>
            <th scope="col">{valueTitle}</th>
            {showVerdict ? (
              <th scope="col">Compared with usual limits</th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <LabRow
              key={`${row.feature}-${row.state}`}
              row={row}
              showVerdict={showVerdict}
              verdict={verdicts?.get(row.feature)}
              fromProfile={fromProfile}
            />
          ))}
        </tbody>
      </table>
      {caption ? <p className="hint">{caption}</p> : null}
    </>
  );
}

export default function Dashboard() {
  const { id } = useParams();
  const [dashboard, setDashboard] = useState(null);
  const [report, setReport] = useState(null);
  const [identity, setIdentity] = useState(null);
  const [error, setError] = useState(null);
  const [notAnalysed, setNotAnalysed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await api.getDashboard(id);
        if (cancelled) return;
        setDashboard(data.dashboard);
        setReport(data.report);
        setIdentity(data.identity || null);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setNotAnalysed(true);
        }
        setError(friendlyPageError(err.message));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (error && notAnalysed) {
    return (
      <main>
        <p className="empty">{error}</p>
        <Link to="/reports">Back to your reports</Link>
      </main>
    );
  }
  if (error) return <p className="error" role="alert">{error}</p>;
  if (!dashboard) return <p className="loading">Loading your dashboard…</p>;

  const labs = dashboard.laboratory || [];
  const profileLabs = labs.filter((row) => row.source === 'patient_profile');
  const otherPerson = report?.subject?.owner === 'other';
  const reportDetailLabs = labs.filter((row) => row.source === 'report_details');
  const measuredLabs = labs.filter((row) => !isPatientDetail(row.source));
  const reportedLabs = measuredLabs.filter(
    (row) => isPresent(row.value) || row.state === 'rejected'
  );

  const labFlagVerdict = (item) => {
    if (item.labFlaggedAbnormal === true && isPresent(item.labFlag)) {
      return { label: titleCase(item.labFlag), direction: item.labFlag };
    }
    if (item.labFlag === 'normal' || isPresent(item.labReferenceLow)
        || isPresent(item.labReferenceHigh)) {
      return { label: 'In range', direction: 'normal' };
    }
    return undefined;
  };

  const unassessedItems = dashboard.unanalysed?.items || [];
  const unassessedRows = unassessedItems.map((item, index) => ({
    feature: `lab:${item.testName}:${index}`,
    displayName: item.testName,
    value: item.value,
    unit: item.unit,
    state: 'measured',
    usable: true,
    referenceRangeRaw: item.labReferenceRangeRaw,
  }));
  const allResultRows = [
    ...reportedLabs,
    ...unassessedRows.filter(
      (_, i) => unassessedItems[i].labFlaggedAbnormal === true
    ),
    ...unassessedRows.filter(
      (_, i) => unassessedItems[i].labFlaggedAbnormal !== true
    ),
  ];
  const conditionCards = dashboard.conditions || [];

  const isUnassessed = (card) =>
    card.assessed === false || card.status === 'Insufficient Data';
  const isClear = (card) =>
    card.flagged !== true && !isUnassessed(card) && card.status === 'Not Indicated';

  const unassessedCards = conditionCards.filter(isUnassessed);
  const clearCards = conditionCards.filter(
    (card) => !isUnassessed(card) && isClear(card)
  );
  const flaggedCards = conditionCards.filter(
    (card) => !isUnassessed(card) && !isClear(card)
  );

  const verdicts = valueVerdicts(dashboard.evidence?.conditions);

  unassessedItems.forEach((item, index) => {
    const verdict = labFlagVerdict(item);
    if (verdict) verdicts.set(`lab:${item.testName}:${index}`, verdict);
  });

  const reportedVerdict = (row) => {
    const flag = isPresent(row.flag) ? String(row.flag).toLowerCase() : null;
    if (flag && flag !== 'normal') {
      return { label: titleCase(row.flag), direction: flag };
    }
    const position = printedPosition(row.value, row.referenceLow, row.referenceHigh);
    if (position === 'high') return { label: 'High', direction: 'high' };
    if (position === 'low') return { label: 'Low', direction: 'low' };
    if (position === 'normal' || flag === 'normal') {
      return { label: 'In range', direction: 'normal' };
    }
    return undefined;
  };

  reportedLabs.forEach((row) => {
    const printed = reportedVerdict(row);
    const rule = verdicts.get(row.feature);

    if (!rule) {
      if (printed) verdicts.set(row.feature, printed);
      return;
    }
    if (!printed) return;

    const ruleDirection = rule.direction || 'normal';
    const printedDirection = printed.direction || 'normal';
    if (ruleDirection === printedDirection) return;

    verdicts.set(row.feature, {
      ...printed,
      mixed: true,
      detail: printedRange(row),
      secondary: rule.crossedText
        ? `${rule.crossedText}, the threshold this tool applies`
        : `this tool recorded it as ${String(rule.label).toLowerCase()}`,
    });
  });


  const evidenceByCondition = new Map(
    (dashboard.evidence?.conditions || []).map((item) => [item.condition, item])
  );

  const coverageFor = (condition) => {
    const lines = evidenceByCondition.get(condition)?.lines || [];
    const byFeature = new Map();
    for (const line of lines) {
      const seen = byFeature.get(line.feature) === true;
      byFeature.set(line.feature, seen || line.availability === 'observed');
    }
    const cited = byFeature.size;
    if (!cited) return null;
    const available = [...byFeature.values()].filter(Boolean).length;
    return { cited, available, coverage: available / cited };
  };

  const radarTopics = [...flaggedCards, ...clearCards, ...unassessedCards]
    .map((card) => {
      const assessed = !isUnassessed(card);
      const counts = coverageFor(card.condition);
      if (assessed && !counts) return null;
      return {
        name: card.condition,
        short: RADAR_LABEL[card.condition] || card.condition,
        assessed,
        coverage: assessed ? counts.coverage : 0,
        cited: counts?.cited,
        available: counts?.available,
      };
    })
    .filter(Boolean)
    .slice(0, 5);

  const recommendations = dashboard.recommendations || {};
  const flaggedConditions = new Set(
    (dashboard.conditions || [])
      .filter((card) => card.flagged === true)
      .map((card) => card.condition)
  );
  const guidance = groupGuidance(recommendations.guidance?.items, flaggedConditions);
  const sharedBecause = sharedBecausePhrase(guidance.relevant);

  return (
    <main className="dashboard">
      <header className="report-hero">
        <span className="report-hero__icon" aria-hidden="true">
          <Icon name="reports" size={26} />
        </span>
        <nav className="crumbs" aria-label="Breadcrumb">
          <Link to="/reports">Reports</Link>
          <span aria-hidden="true">/</span>
          <span className="crumbs__here">{report?.originalName || 'This report'}</span>
        </nav>
        <div className="page-links">
          <Link className="page-link" to={`/reports/${id}/doctor-summary`}>
            <Icon name="doctor" size={17} />
            Summary for a clinician
          </Link>
          <Link className="page-link" to={`/reports/${id}/population`}>
            <Icon name="people" size={17} />
            How your results compare
          </Link>
        </div>
      </header>

      <ProfileIdentityNotice identity={identity} />

      <UnreadablePagesNotice document={dashboard.document} />

      <OverallCard overall={dashboard.overall} />

      {dashboard.conditions?.length ? (
        <ul className="stats" aria-label="This report at a glance">
          <li className="stat">
            <span className="stat__num">{flaggedCards.length}</span>
            <span className="stat__label">
              {flaggedCards.length === 1 ? 'condition' : 'conditions'} worth a closer look
            </span>
          </li>
          <li className="stat">
            <span className="stat__num">{clearCards.length}</span>
            <span className="stat__label">checked, with nothing pointing to them</span>
          </li>
          <li className="stat">
            <span className="stat__num">{allResultRows.length}</span>
            <span className="stat__label">
              {allResultRows.length === 1 ? 'result' : 'results'} read from the report
            </span>
          </li>
        </ul>
      ) : null}

      <div className="chart-grid">
        <section className="card">
          <h2>Overall risk</h2>
          <RiskGauge
            risk={dashboard.overall?.risk}
            assessed={dashboard.overall?.anyAssessed === true}
            caption="The needle reflects the highest risk level any single condition reached — it is not an average."
          />
        </section>

        {radarTopics.length ? (
          <section className="card">
            <h2>Coverage of the conditions checked</h2>
            <CoverageRadar
              topics={radarTopics}
              absenceCaption="A dotted point sits at zero because nothing was measured for that condition — it is not a low score."
            />
          </section>
        ) : null}
      </div>


      {flaggedCards.length ? (
        <>
          <h2>Worth a closer look</h2>
          <ul className="condition-list">
            {flaggedCards.map((card) => (
              <ConditionCard
                key={card.condition}
                card={card}
                evidence={evidenceByCondition.get(card.condition)}
              />
            ))}
          </ul>
        </>
      ) : null}

      {clearCards.length ? (
        <>
          <h2>Everything else that was checked</h2>
          {clearCards.length ? (
            <div className="roundup">
              <p className="roundup__lead">
                <strong>Nothing in these results pointed to</strong> these{' '}
                {clearCards.length}{' '}
                {clearCards.length === 1 ? 'condition' : 'conditions'}.
              </p>
              <ul className="chips">
                {clearCards.map((card) => (
                  <li className="chip chip--clear" key={card.condition}>
                    <span className="chip__mark" aria-hidden="true">
                      ✓
                    </span>
                    {card.condition}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      ) : null}

      {!dashboard.conditions?.length ? (
        <p className="empty">No conditions were assessed for this report.</p>
      ) : null}

      <h2>Your results</h2>
      {allResultRows.length ? (
        <LabTable rows={allResultRows} verdicts={verdicts} />
      ) : (
        <p className="empty">No laboratory values were read from this report.</p>
      )}

      {profileLabs.length ? (
        <>
          <h2>{otherPerson ? 'Entered for this report' : 'From your profile'}</h2>
          <LabTable
            rows={profileLabs}
            fromProfile
            caption={
              otherPerson
                ? 'These were entered for this report when it was marked as someone else’s — not taken from your profile, and not from the report. They are used to interpret the results — they are not results themselves.'
                : 'These came from the details you entered, not from this report. They are used to interpret your results — they are not results themselves.'
            }
          />
        </>
      ) : null}

      {reportDetailLabs.length ? (
        <>
          <h2>From the report&rsquo;s patient details</h2>
          <LabTable
            rows={reportDetailLabs}
            fromProfile
            source="report"
            caption="The sex and age printed on this report. They were used in place of your profile's to interpret your results — they are not results themselves."
          />
        </>
      ) : null}

      {guidance.relevant.length ? (
        <>
          <details className="disclosure disclosure--section">
            <summary className="disclosure__summary">
              <h2>Topics you could read about</h2>
              <span className="disclosure__count">
                {guidance.relevant.length}
              </span>
              <span className="disclosure__spacer" />
              <span className="disclosure__chevron" aria-hidden="true" />
            </summary>
            <div className="disclosure__body">
          {sharedBecause ? (
            <p className="guidance__shared">
              Shown because this report flagged {sharedBecause}.
            </p>
          ) : null}
          <ul className="guidance bullets">
            {guidance.relevant.map((item, index) => (
              <li key={item.code || index}>
                <div className="guidance__body">
                  <span className="guidance__text">
                    {trimGeneralPrefix(item.text || item.title)}
                  </span>
                  {!sharedBecause && becausePhrase(item) ? (
                    <span className="guidance__because">
                      {' '}
                      Related to: {becausePhrase(item)}.
                    </span>
                  ) : null}
                  {READING_LINKS[item.code] ? (
                    <a
                      className="guidance__link"
                      href={READING_LINKS[item.code].url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Read “{READING_LINKS[item.code].title}” on the {READING_SOURCE}
                      <span aria-hidden="true"> ↗</span>
                      <span className="visually-hidden"> (opens in a new tab)</span>
                    </a>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
          <p className="hint">
            General educational topics, matched to what this report flagged.
            They are not written for you, are not personalised treatment
            advice, and are not instructions.
            {guidance.relevant.some((item) => READING_LINKS[item.code])
              ? ` The links open the ${READING_SOURCE} (the UK's National Health Service) in a new tab; VaidyaAI does not run that site.`
              : ''}
          </p>
            </div>
          </details>
        </>
      ) : null}



      <Explanations
        explanations={recommendations.explanations}
        resultFeatures={new Set(measuredLabs.map((row) => row.feature))}
        unassessedCount={(dashboard.unanalysed?.items || []).length}
        assessedResultCount={reportedLabs.length}
        unassessedItems={dashboard.unanalysed?.items || []}
      />

      <InShort
        dashboard={dashboard}
        flaggedCards={flaggedCards}
        clearCards={clearCards}
        reportId={id}
        verdicts={verdicts}
      />
    </main>
  );
}
