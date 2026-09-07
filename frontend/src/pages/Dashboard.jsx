import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, ApiError } from '../lib/api';
import { Absent, Risk, Value, WarningList } from '../components/Absent';
import { isPresent } from '../lib/absence';

/**
 * Module 27 -- the health dashboard.
 *
 * ==========================================================================
 * THIS IS THE SCREEN THE ABSENCE PRIMITIVES EXIST FOR
 * ==========================================================================
 *
 * A dashboard has a box for every value, and a box has to show SOMETHING.
 * That pressure is what turns an absence into a value, and every failure of
 * that kind found on this project so far has been one hop from a screen like
 * this one. The specific ones this component must not commit:
 *
 *   `status: null` + `anyAssessed: false` IS NOT "Healthy". It is Module 18's
 *   fourth case -- nothing could be assessed -- and the difference between
 *   "we looked and it was fine" and "we could not look" is the difference
 *   between reassurance and a lie.
 *
 *   `statusLabel` has FIVE values, not four. `Healthy (partial assessment)`
 *   exists precisely because a partial clean result was otherwise
 *   byte-identical to a full one, and an audit found the backend flattening
 *   it to "Healthy" right up until it was fixed. So the LABEL is printed,
 *   never the status.
 *
 *   A missing risk is NOT low risk. `INSUFFICIENT_DATA` carries no risk, and
 *   the `Risk` component has no way to express otherwise.
 *
 *   A rejected reading is NOT a zero, and is NOT the same as a reading that
 *   was never on the report. Both are absences; they are different absences,
 *   and the laboratory card says which.
 *
 * Every value below goes through `Value`, `Risk` or `Absent`. There is no
 * bare `{x}` on a clinical field and no `||` anywhere in this file.
 */

function OverallCard({ overall }) {
  if (!overall) return null;
  const assessed = overall.anyAssessed === true;

  return (
    <section className="card overall">
      <h2>Overall</h2>

      <p className="overall__status">
        {/* The LABEL, never the status: the label is the five-valued one. */}
        {isPresent(overall.statusLabel) ? (
          <strong>{overall.statusLabel}</strong>
        ) : (
          <Absent
            label="Not assessed"
            reason="No overall status was established for this report."
          />
        )}
      </p>

      <p>
        Overall risk: <Risk risk={overall.risk} assessed={assessed} />
      </p>

      {/* `complete: false` is a real fact and is stated, not hidden. */}
      {overall.complete === false ? (
        <p className="caveat">
          This assessment is incomplete
          {isPresent(overall.unassessedConditionCount) &&
          overall.unassessedConditionCount > 0
            ? ` — ${overall.unassessedConditionCount} condition(s) could not be assessed`
            : ''}
          .
        </p>
      ) : null}

      {isPresent(overall.caveat) ? <p className="caveat">{overall.caveat}</p> : null}

      {overall.unassessedConditions?.length ? (
        <p className="hint">
          Not assessed: {overall.unassessedConditions.join(', ')}. An
          unassessed condition is an open question, not a negative result.
        </p>
      ) : null}

      {overall.sourcesFailed?.length ? (
        <p className="caveat">
          Some analysis stages did not complete: {overall.sourcesFailed.join(', ')}.
        </p>
      ) : null}
    </section>
  );
}

/**
 * THE PATIENT SCREEN SPEAKS ENGLISH. The clinician screen speaks statistics.
 *
 * This card used to print "Based on: Clinical Rule Engine, Random Forest" and
 * "Model probability: 0.0089 (max_of_model_probabilities)". Both are true and
 * both are useless to the person whose blood it is: those are internal
 * component names, and a bare 0.0089 reads as precision this model does not
 * have. None of it is lost -- it is on the clinician summary, beside the
 * ROC-AUC and operating threshold that make it readable.
 *
 * The first replacement was a flat list of "Your result for X was Y."
 * sentences, and it was worse in a different way: `age` and `bmi` appeared
 * twice because two rules each contributed a line, profile answers sat among
 * blood results as though they were measurements, and the catalog's internal
 * display names leaked -- "Self-described gender as stored by Module 2".
 *
 * So the evidence is RESHAPED rather than transcribed:
 *
 *   1. one entry per feature, not one per contributing rule;
 *   2. measured blood values are separated from profile answers, because
 *      "your creatinine was 2.4" and "you said you have never smoked" are
 *      different kinds of fact and only the first was measured today;
 *   3. names come from a patient-facing table keyed by the canonical feature,
 *      so the clinician-precise catalog wording stays where it belongs;
 *   4. a comparison is printed ONLY where one was actually crossed, so the
 *      eye lands on the value that decided the verdict.
 */

/**
 * The verdict, said to the person it is about.
 *
 * "Not Indicated" is precise and it is not English. A reader who does not
 * already know the vocabulary cannot tell whether it means "you are fine",
 * "we could not tell", or something worse -- and those are exactly the three
 * things this project refuses to let collapse into each other.
 *
 * The wording below is careful about the one thing that matters most: NOT
 * INDICATED IS NOT THE SAME AS "YOU DO NOT HAVE THIS". A blood test that shows
 * nothing is evidence about the blood test, not a clean bill of health, so the
 * phrasing stays anchored to "these results" rather than to the person. The
 * canonical status words are still on the clinician summary, where the reader
 * knows what they mean.
 */
const PATIENT_STATUS = {
  'Indicated': 'These results point to this — worth discussing with a doctor',
  'Borderline': 'Close to the usual limit — worth keeping an eye on',
  'Not Indicated': 'Nothing in these results points to this',
  'Insufficient Data': 'Not enough information in this report to check this',
  'Inconclusive': 'The checks did not agree, so this is unresolved',
};

const statusText = (status) =>
  (isPresent(status) ? PATIENT_STATUS[status] || status : null);

/**
 * Did the contributing analyses actually reach DIFFERENT verdicts?
 *
 * `basisConflict` does NOT mean they disagreed -- it means they answer
 * different questions (a risk-factor tally is not a probability). Module 16
 * stamps it so the two are shown side by side instead of being averaged into
 * one number, which is a real and important guarantee.
 *
 * But it fires even when both said the same thing, and a paragraph beginning
 * "the analyses answer different questions" under a calm verdict reads as a
 * warning that something is wrong. On a patient screen that is worse than
 * unhelpful. So the methodological note is shown when the verdicts DIFFER --
 * where the reader genuinely needs to know why one says one thing and one says
 * another -- and stays on the clinician summary the rest of the time.
 *
 * THE TEST IS "CAN WE PROVE THEY AGREED", NOT "DID THEY DISAGREE". A first
 * version asked the second question and was wrong in a way that matters: when
 * the evidence section carried no per-source verdicts at all, it concluded
 * "no disagreement" and silently dropped a note Module 16 had deliberately
 * stamped. Missing information is not agreement. So the note is suppressed
 * ONLY where two or more assessed sources are present and every one of them
 * reached the same verdict; anything less certain shows it.
 */
function shouldShowBasisNote(evidence) {
  const verdicts = (evidence?.sources || [])
    .filter((source) => source.assessed !== false && isPresent(source.status))
    .map((source) => source.status);

  const provablyAgreed = verdicts.length >= 2 && new Set(verdicts).size === 1;
  return !provablyAgreed;
}

/**
 * Guidance, grouped by WHY it is there.
 *
 * Thirteen bullets arrived in one undifferentiated list, five of them opening
 * with the identical twelve words "General educational guidance for most
 * adults includes ...". The repetition is not just ugly: it hides the two
 * items that were actually selected because of THIS person's results among
 * nine that would appear for anybody.
 *
 * THE CATALOG TEXT IS NOT REWRITTEN. These strings are reviewed material
 * selected by code, and paraphrasing them here would mean the screen no longer
 * shows what was reviewed. Only the shared opening clause is lifted off the
 * front of each bullet -- and the qualifier it carries ("general", "for most
 * adults") is not lost, because it is stated once as the heading that governs
 * the whole group.
 */
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

/**
 * Split guidance into "because of your results" and "for everyone".
 *
 * `alwaysIncluded` items are the standing disclaimers. One of them repeats the
 * page footer word for word ("This is an automated educational analysis, not a
 * diagnosis..."), which is already on every screen, so it is dropped here
 * rather than shown twice -- the footer is not going anywhere.
 */
/**
 * Standing text that is already on the screen, or is not a topic at all.
 *
 * `NOT_A_DIAGNOSIS` repeats the page footer word for word. `MONITOR_OVER_TIME`
 * and `DISCUSS_WITH_CLINICIAN` are always included regardless of findings, and
 * out of context they read strangely -- "This finding may warrant discussion"
 * under a report with no findings, "Tracking this parameter" with no parameter
 * named. Both points are already made where they mean something: the footer
 * carries the disclaimer on every screen, and a flagged card says in plain
 * words that it is worth discussing with a doctor.
 */
const ALWAYS_ON_SCREEN_CODES = new Set([
  'NOT_A_DIAGNOSIS',
  'MONITOR_OVER_TIME',
  'DISCUSS_WITH_CLINICIAN',
]);

/**
 * Only topics tied to something this report actually flagged.
 *
 * The catalog selects an item when the ANALYTE WAS MEASURED, not when it was
 * abnormal -- so a person with perfectly normal haemoglobin was being offered
 * "dietary sources of iron ... when haemoglobin is low", and normal B12 earned
 * a bullet about B12 sources. Ten of thirteen bullets were like that. It is
 * not neutral filler: a reader scanning a list of deficiency topics under
 * their own results reasonably concludes the topics are about them.
 *
 * An unmatched item is DROPPED rather than demoted to a "general" heading. It
 * was never general -- it is condition-specific guidance for a condition this
 * person does not have, and putting a heading above it does not make it
 * relevant. Nothing clinical is lost: guidance is educational material, every
 * finding is on a card, and the clinician summary still carries the full set.
 */
function groupGuidance(items, flaggedConditions) {
  const relevant = [];
  for (const item of items || []) {
    if (ALWAYS_ON_SCREEN_CODES.has(item.code)) continue;
    const because = matchedConditions(item, flaggedConditions);
    if (because.length) relevant.push({ ...item, because });
  }
  return { relevant };
}

/**
 * The conditions that were ACTUALLY FLAGGED on this report and that this
 * guidance item is associated with.
 *
 * `becauseOfConditions` is the catalog's topic list -- every condition the item
 * is filed under -- NOT a statement about this patient. A first version of this
 * printed it directly, and on a report where nothing was flagged it rendered
 * "Shown because of: Diabetes, Obesity, Underweight and Heart Disease" under a
 * clean set of results. That is the single worst thing this screen could say:
 * it announces four conditions to someone who has none of them, in the
 * confident voice of an explanation.
 */
function matchedConditions(item, flaggedConditions) {
  return (item.becauseOfConditions || []).filter((name) =>
    flaggedConditions.has(name)
  );
}

/** "Diabetes and High Cholesterol" -- why this bullet is on the page. */
function becausePhrase(item) {
  const names = item.because || [];
  if (!names.length) return null;
  if (names.length === 1) return names[0];
  if (names.length === 2) return `${names[0]} and ${names[1]}`;
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
}

/**
 * Module 23's plain-language explanations -- THE MOST PATIENT-FACING THING THE
 * PIPELINE PRODUCES, and until now the dashboard threw it away.
 *
 * The service writes a paragraph per result ("Creatinine is produced as muscle
 * uses energy, enters your blood, and is removed almost entirely by your
 * kidneys. Your serum creatinine value is 1.41 mg/dl, which is above the
 * standard reference interval..."), grounds it in retrieved clinical documents,
 * and passes it through the Module 24 safety validator before it is stored.
 * Every one of those paragraphs costs a model call. They were being generated,
 * safety-checked, persisted -- and never rendered.
 *
 * A WITHHELD EXPLANATION IS STATED, NOT SKIPPED. `outcome` distinguishes one
 * that was written from one the model could not produce, and silently omitting
 * the second would make a partial set look complete: the reader would have no
 * way to know that the cholesterol paragraph is missing rather than
 * unnecessary.
 */
function Explanations({ explanations }) {
  const entries = explanations?.entries || [];
  if (!entries.length) return null;

  const written = entries.filter((entry) => entry.available === true
    && isPresent(entry.explanation));
  const missing = entries.filter((entry) => entry.available !== true);

  if (!written.length && !missing.length) return null;

  return (
    <section className="explanations">
      <h2>What these results mean</h2>

      {written.map((entry, index) => (
        <article className="card explanation" key={entry.feature || index}>
          <h3 className="explanation__subject">
            {PATIENT_LABEL[entry.feature] || entry.subject}
          </h3>
          <p className="explanation__text">
            {trimClosingAdvice(entry.explanation)}
          </p>
        </article>
      ))}

      {missing.length ? (
        <p className="hint">
          No plain-language explanation could be prepared for{' '}
          {missing
            .map((entry) => PATIENT_LABEL[entry.feature] || entry.subject)
            .join(', ')}
          . The results themselves are unaffected — they were produced by the
          analysis, not by the writing step.
        </p>
      ) : null}

      <p className="hint">
        Written by a language model from your measured values and reviewed
        reference material, and checked before being shown. They explain what
        each test measures — they do not diagnose, and no single laboratory
        value settles anything on its own. Take anything flagged above to a
        qualified healthcare professional.
      </p>
    </section>
  );
}

/**
 * HIGH / LOW / IN RANGE for one measured value.
 *
 * The laboratory printed no reference intervals, and nothing in the payload
 * carries a per-value verdict -- `flag` is null on every row. But the rule
 * engine already decided, for each threshold it checked, whether this value
 * crossed it and in which direction. That decision is reused here rather than
 * re-derived: this file compares nothing and knows no clinical thresholds, it
 * only reads back what the engine recorded.
 *
 * `null` means no rule covered the value, and it renders as nothing at all --
 * NOT as "in range". A value nobody checked has not been found normal.
 */
function valueVerdicts(evidenceConditions) {
  const byFeature = new Map();

  for (const condition of evidenceConditions || []) {
    for (const line of condition.lines || []) {
      if (line.rejected || !isPresent(line.value)) continue;
      const existing = byFeature.get(line.feature);
      // A crossing beats a non-crossing: one rule finding a value high is not
      // cancelled by another rule that only checked a different boundary.
      if (existing && existing.direction) continue;

      const crossed = crossing(line);
      if (crossed) {
        const above = line.comparator === '>' || line.comparator === '>=';
        byFeature.set(line.feature, {
          direction: above ? 'high' : 'low',
          label: above ? 'High' : 'Low',
        });
        continue;
      }

      // APPEARING IN A RULE'S EVIDENCE *IS* HAVING BEEN CHECKED.
      //
      // A first version only recorded "In range" when the line carried a
      // threshold, and marked everything else "not checked". But the band a
      // rule falls into when nothing is exceeded is the catch-all band, and it
      // has no comparator and no threshold by construction -- so six of eight
      // perfectly normal results were reported to the patient as unchecked.
      // That is a false absence, and this screen exists to not produce those.
      // The value reached a rule and the rule reported on it; that is the
      // definition of checked.
      byFeature.set(line.feature, { direction: null, label: 'In range' });
    }
  }
  return byFeature;
}

/**
 * Strip the trailing "speak to a doctor" sentence from a generated paragraph.
 *
 * Every explanation ends with one, and with six on a page the effect is not
 * caution but noise -- a reader asked "then what is this platform for?", which
 * is the correct question. The advice is not removed: it is stated ONCE under
 * the section, and the page footer carries it on every screen already.
 *
 * ONLY TRAILING SENTENCES ARE DROPPED, and only those naming a healthcare
 * professional. Nothing in the middle of a paragraph is touched, and if the
 * whole paragraph turns out to be one such sentence it is kept intact -- an
 * empty explanation would be worse than a repetitive one.
 */
function trimClosingAdvice(text) {
  if (typeof text !== 'string') return text;

  // SPLIT ON SENTENCE BOUNDARIES, NOT ON EVERY FULL STOP.
  //
  // The obvious `/[^.!?]+[.!?]+/` splits "5.2 %" straight down the middle, so
  // the final "sentence" became "2 % value may mean for you." -- which does
  // not mention a healthcare professional, so nothing was ever trimmed and the
  // whole function silently did nothing. Lab prose is full of decimals; the
  // boundary is a terminator followed by space and a capital.
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

/**
 * Why a result on the report was not assessed, said to the person who uploaded
 * it. The pipeline's own reason codes are machine words.
 */
const SKIP_REASON = {
  no_canonical_feature:
    'this tool does not assess this test',
  unsupported_specimen:
    'this tool only assesses blood tests',
  distinct_analyte:
    'this is a related but different measurement from the one assessed',
};

/**
 * EVERYTHING ON THE REPORT THAT WAS NOT ASSESSED.
 *
 * This is the most important honesty on the page and it did not exist. A real
 * report carries far more than the fourteen measurements this platform knows:
 * of the 67 parameters read off PK0016, four were assessed and 63 -- HDL
 * cholesterol, the entire urine panel, liver and kidney measurements -- were
 * read and then dropped in silence.
 *
 * The reader saw four results and an overall verdict. Nothing on the screen
 * suggested that most of their report had been set aside, so the only
 * available conclusion was that the whole document had been checked and was
 * fine. `document.unmapped_count` even said 0, which is not a gap but a false
 * statement -- the true figure sits in the fusion block and says 63.
 *
 * Listing them is not an admission of weakness; it is the difference between
 * "your report is clear" and "here is the part of your report I can read".
 * Only the second is true, and only the second lets someone know they still
 * need a person to look at the rest.
 */
function Unanalysed({ unanalysed }) {
  const items = unanalysed?.items || [];
  if (!items.length) return null;

  const labFlagged = items.filter((item) => item.labFlaggedAbnormal === true);
  const rest = items.filter((item) => item.labFlaggedAbnormal !== true);

  const groups = new Map();
  for (const item of rest) {
    const reason = SKIP_REASON[item.reason] || 'this tool does not assess this test';
    if (!groups.has(reason)) groups.set(reason, []);
    groups.get(reason).push(item);
  }

  const range = (item) => {
    const low = item.labReferenceLow;
    const high = item.labReferenceHigh;
    if (isPresent(low) && isPresent(high)) return `${low}–${high}`;
    if (isPresent(high)) return `up to ${high}`;
    if (isPresent(low)) return `${low} and above`;
    return null;
  };

  return (
    <section className="unanalysed">
      <h2>Also on your report, but not assessed here</h2>
      <p>
        This tool checks a fixed set of measurements. Your report contained{' '}
        <strong>{items.length}</strong> other result
        {items.length === 1 ? '' : 's'} that it read but did not assess.{' '}
        <strong>
          Nothing above says anything about these — they were not checked, which
          is not the same as being normal.
        </strong>
      </p>

      {/* THE LABORATORY'S OWN MARKINGS, WHICH COST NOTHING TO HONOUR.
          Module 4 already read each parameter's printed range and the lab's
          own high/low flag, and both were being discarded with the parameter.
          On one real report that buried nine results the laboratory itself had
          marked abnormal -- including the urea and potassium that corroborate
          the raised creatinine the page DID flag. Showing them asserts nothing
          new: the range is the laboratory's and so is the verdict. This
          platform has still not assessed them, and says so. */}
      {labFlagged.length ? (
        <div className="unanalysed__flagged">
          <h3>
            Your laboratory marked {labFlagged.length} of them outside its own
            reference range
          </h3>
          <p className="hint">
            This is your laboratory&rsquo;s own marking, not an assessment by
            this tool — it does not check these tests. They are shown so they
            are not lost. Take them to a qualified healthcare professional.
          </p>
          <ul className="unanalysed__list unanalysed__list--flagged">
            {labFlagged.map((item, index) => (
              <li key={`${item.testName}-${index}`}>
                <span className="unanalysed__name">{item.testName}</span>{' '}
                <span className="unanalysed__value">
                  {item.value}
                  {isPresent(item.unit) ? ` ${item.unit}` : ''}
                </span>{' '}
                <span className={`verdict verdict--${item.labFlag === 'low' ? 'low' : 'high'}`}>
                  lab: {item.labFlag}
                </span>
                {range(item) ? (
                  <span className="unanalysed__range"> (range {range(item)})</span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {[...groups.entries()].map(([reason, group]) => (
        <details className="unanalysed__group" key={reason}>
          <summary>
            {group.length} result{group.length === 1 ? '' : 's'} — {reason}
          </summary>
          <ul className="unanalysed__list">
            {group.map((item, index) => (
              <li key={`${item.testName}-${index}`}>
                <span className="unanalysed__name">{item.testName}</span>
                {isPresent(item.value) ? (
                  <span className="unanalysed__value">
                    {' '}
                    {item.value}
                    {isPresent(item.unit) ? ` ${item.unit}` : ''}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        </details>
      ))}
    </section>
  );
}

/** Patient-facing names. The catalog's own wording is for clinicians. */
const PATIENT_LABEL = {
  hba1c: 'HbA1c (average blood sugar)',
  blood_glucose: 'Blood sugar',
  cholesterol: 'Total cholesterol',
  triglycerides: 'Triglycerides',
  creatinine: 'Creatinine (kidney marker)',
  hemoglobin: 'Haemoglobin',
  vitamin_d: 'Vitamin D',
  vitamin_b12: 'Vitamin B12',
  bmi: 'BMI',
  age: 'age',
  gender: 'sex',
  smoking_history: 'smoking history',
  hypertension: 'history of high blood pressure',
  heart_disease: 'history of heart disease',
};

const labelFor = (line) =>
  PATIENT_LABEL[line.feature] || line.displayName || line.feature;

/**
 * The same label, capitalised for a table cell.
 *
 * PATIENT_LABEL is written lower-case because its other use is inside a
 * sentence -- "your age, BMI and smoking history were also taken into
 * account". Reusing those strings as table headings gave rows titled "age" and
 * "sex". One table is not worth a second set of names, so the case is fixed at
 * the point of use. `BMI` is untouched because only the first letter changes.
 */
const titleCase = (text) =>
  (typeof text === 'string' && text ? text.charAt(0).toUpperCase() + text.slice(1) : text);

/** Was a threshold actually crossed? Only then is it worth printing. */
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

/** The range printed on the report, when the lab printed one. */
function printedRange(line) {
  const { referenceLow: low, referenceHigh: high, unit } = line;
  const suffix = isPresent(unit) ? ` ${unit}` : '';
  if (isPresent(low) && isPresent(high)) return `report range ${low}–${high}${suffix}`;
  if (isPresent(high)) return `report limit ${high}${suffix}`;
  if (isPresent(low)) return `report minimum ${low}${suffix}`;
  return null;
}

/**
 * ONE entry per feature, measured values first.
 *
 * Two rules naming the same feature produce two identical lines; the richer of
 * the pair is kept so a duplicate never reaches the screen and no information
 * is dropped with it.
 */
function summariseEvidence(evidence) {
  const byFeature = new Map();

  for (const line of evidence?.lines || []) {
    if (line.rejected) continue;
    const existing = byFeature.get(line.feature);
    // Prefer the line that actually carries a value, then one with a crossing.
    const score = (isPresent(line.value) ? 2 : 0) + (isPresent(line.threshold) ? 1 : 0);
    const existingScore = existing
      ? (isPresent(existing.value) ? 2 : 0) + (isPresent(existing.threshold) ? 1 : 0)
      : -1;
    if (score > existingScore) byFeature.set(line.feature, line);
  }

  const measured = [];
  const context = [];
  for (const line of byFeature.values()) {
    if (line.sourceStage === 'lab_report' && isPresent(line.value)) {
      measured.push(line);
    } else if (PATIENT_LABEL[line.feature]) {
      context.push(line);
    }
  }
  return { measured, context };
}

/** How the verdict was reached, said without naming internal components. */
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

/** "your age, BMI and smoking history" -- a phrase, not a bullet list. */
function contextPhrase(context) {
  const names = context.map(labelFor).filter(Boolean);
  if (!names.length) return null;
  if (names.length === 1) return names[0];
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
}

function ConditionCard({ card, evidence }) {
  const assessed = card.assessed !== false;
  const { measured, context } = summariseEvidence(evidence);
  const alsoConsidered = contextPhrase(context);

  return (
    <li className="card condition">
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
        {statusText(card.status) ? (
          statusText(card.status)
        ) : (
          <Absent reason="No decision was reached for this condition." />
        )}
      </p>

      {/* WHY, as something the reader can check against the paper report in
          their hand. A verdict with no reason is a thing to be believed or
          not. */}
      {measured.length ? (
        <dl className="measured">
          {measured.map((line) => {
            const note = crossing(line) || printedRange(line);
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

      {alsoConsidered ? (
        <p className="hint">Your {alsoConsidered} were also taken into account.</p>
      ) : null}

      {card.partiallyAssessed === true ? (
        <p className="caveat">
          This topic could only be partly assessed, so the picture is
          incomplete.
        </p>
      ) : null}

      {/* Shown only when the two checks actually reached different verdicts --
          see sourcesDisagree. The stored `basisNote` is written for a
          clinician, so it is replaced here rather than printed. */}
      {card.basisConflict === true && shouldShowBasisNote(evidence) ? (
        <p className="caveat">
          Two checks were made and they did not agree. One counts risk factors
          from your profile; the other is a statistical estimate. They answer
          different questions, so neither settles the other — this is worth
          raising with a doctor.
        </p>
      ) : null}

      {plainSources(card.sourceKinds) ? (
        <p className="hint">{plainSources(card.sourceKinds)}</p>
      ) : null}
    </li>
  );
}

/** The four laboratory states, each rendered as the distinct fact it is. */
/**
 * One row of the results table.
 *
 * THE NAME THE PATIENT SEES IS THE NAME ON THEIR PAPER REPORT. This printed
 * "Glycated haemoglobin, NGSP % (printed as: Glycated Haemoglobin (HbA1c))"
 * -- the internal canonical name first, and the lab's own wording demoted to a
 * parenthetical. That is backwards for the person holding the report: the
 * whole value of showing a name here is that they can find the same row on the
 * paper in front of them. So the lab's wording leads, and our normalised name
 * follows only when it adds something.
 *
 * `showRange` and `showFlag` are passed in rather than decided per row,
 * because a column is a property of the TABLE. When no lab printed a range --
 * which is every row of a report that prints none -- a per-row "No range
 * printed / The laboratory did not print a reference interval for this test"
 * repeats the same two lines ten times and buries the results. The table drops
 * the column instead and says it once underneath.
 */
function LabRow({ row, showRange, showFlag, showVerdict, verdict, fromProfile }) {
  const usable = row.usable === true;
  const friendly = PATIENT_LABEL[row.feature];
  // A PROFILE ROW HAS NO LABORATORY NAME. Its `originalTestName` is the
  // storage key the answer was saved under -- "bmi", "smokingHistory" --
  // and showing that as though a laboratory had printed it is both ugly and
  // wrong. Nothing printed it; the patient typed the answer.
  const printed = fromProfile
    ? null
    : (isPresent(row.originalTestName) ? row.originalTestName : null);
  const canonical = friendly
    || (isPresent(row.displayName) ? row.displayName : row.feature);

  return (
    <tr className={`lab lab--${row.state || 'unknown'}`}>
      <th scope="row">
        {printed || titleCase(canonical)}
        {printed && canonical.toLowerCase() !== printed.toLowerCase() ? (
          <span className="lab__printed">{canonical}</span>
        ) : null}
      </th>

      <td>
        <Value
          value={row.value}
          unit={row.unit}
          available={usable}
          reason={
            isPresent(row.rejectionReason)
              ? row.rejectionReason
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
            <span
              className={`verdict verdict--${verdict.direction || 'normal'}`}
            >
              {verdict.label}
            </span>
          ) : (
            // No rule checked this value. Saying "in range" here would be a
            // finding nobody made.
            <span className="absent">not checked</span>
          )}
        </td>
      ) : null}

      {showRange ? (
        <td className="lab__range">
          {isPresent(row.referenceLow) || isPresent(row.referenceHigh) ? (
            <span>
              {isPresent(row.referenceLow) ? row.referenceLow : '—'} to{' '}
              {isPresent(row.referenceHigh) ? row.referenceHigh : '—'}
              {isPresent(row.unit) ? ` ${row.unit}` : ''}
            </span>
          ) : (
            <span className="absent">not printed</span>
          )}
        </td>
      ) : null}

      {showFlag ? (
        <td>
          {isPresent(row.flag) ? (
            <span className={`flag flag--${row.flag}`}>{row.flag}</span>
          ) : (
            <span className="absent">—</span>
          )}
        </td>
      ) : null}
    </tr>
  );
}

/**
 * The results table, with only the columns this report can actually fill.
 *
 * "Reference interval" and "Flag" are laboratory words, and both were rendered
 * unconditionally -- so a report that prints neither still paid for two columns
 * of "No range printed" and "—".
 */
function LabTable({ rows, caption, verdicts, fromProfile = false }) {
  if (!rows.length) return null;
  // NONE OF THE LABORATORY COLUMNS APPLY TO A PROFILE ANSWER. "Compared
  // with usual limits" against a stated sex is not a weak comparison, it
  // is a category error -- and printing "not checked" beside it invents a
  // shortcoming where there is nothing to check. A reference interval and a
  // laboratory flag are equally meaningless for something no laboratory
  // measured.
  const showRange = !fromProfile && rows.some(
    (row) => isPresent(row.referenceLow) || isPresent(row.referenceHigh)
  );
  const showFlag = !fromProfile && rows.some((row) => isPresent(row.flag));
  const showVerdict = !fromProfile;

  return (
    <>
      <table className="lab-table">
        <thead>
          <tr>
            <th scope="col">Test</th>
            <th scope="col">{fromProfile ? 'You entered' : 'Result'}</th>
            {showVerdict ? (
              <th scope="col">Compared with usual limits</th>
            ) : null}
            {showRange ? <th scope="col">Normal range</th> : null}
            {showFlag ? <th scope="col">Lab&rsquo;s note</th> : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <LabRow
              key={`${row.feature}-${row.state}`}
              row={row}
              showRange={showRange}
              showFlag={showFlag}
              showVerdict={showVerdict}
              verdict={verdicts?.get(row.feature)}
              fromProfile={fromProfile}
            />
          ))}
        </tbody>
      </table>
      {/* Said ONCE, not on every row. It is a fact about the report, and the
          reader needs it to understand why nothing is marked high or low. */}
      {!showRange && !fromProfile ? (
        <p className="hint">
          This report did not print normal ranges, so results are compared with
          standard clinical thresholds instead of the laboratory&rsquo;s own.
        </p>
      ) : null}
      {caption ? <p className="hint">{caption}</p> : null}
    </>
  );
}

export default function Dashboard() {
  const { id } = useParams();
  const [dashboard, setDashboard] = useState(null);
  const [report, setReport] = useState(null);
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
      } catch (err) {
        if (cancelled) return;
        // 404 here means "not analysed yet", which the backend states rather
        // than returning an empty dashboard that would read as "all clear".
        if (err instanceof ApiError && err.status === 404) {
          setNotAnalysed(true);
          setError(err.message);
        } else {
          setError(err.message);
        }
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
  // `source` is the honest divider -- but ONLY an explicit `patient_profile`
  // moves a row out of the results table.
  //
  // The obvious form of this (`source === 'lab_report'` for one side,
  // everything else for the other) is wrong in the dangerous direction: a row
  // arriving without a source would be captioned "these came from the details
  // you entered", asserting about a measured blood value that it was typed in
  // by the patient. Unknown provenance must not become a claim, so it stays
  // where the reader already expects it and only a stated profile source is
  // moved.
  const profileLabs = labs.filter((row) => row.source === 'patient_profile');
  const measuredLabs = labs.filter((row) => row.source !== 'patient_profile');
  // Module 20's Input -> Evidence -> Decision chain, keyed by condition, so
  // each card can say which measured value produced its verdict.
  // Three groups, never merged -- and ONLY A PROVABLY CLEAR CARD IS COLLAPSED.
  //
  // The obvious version of this keys everything off `flagged`, and it is
  // dangerous: a card carrying `status: 'Indicated'` but no `flagged` field
  // falls through to the "nothing pointed to this" line, and an indicated
  // finding is then reported to the patient as clear. That is the worst thing
  // this screen can do, and it is one missing boolean away.
  //
  // So the collapse requires positive proof: `Not Indicated`, assessed, and
  // not flagged. Everything else keeps a full card, including anything with an
  // unrecognised status. An unfamiliar verdict shown too prominently is a
  // cosmetic problem; an unfamiliar verdict silently filed under "nothing to
  // see" is a clinical one.
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

  // High / Low / In range per measured value, read back from the engine's own
  // threshold crossings.
  const verdicts = valueVerdicts(dashboard.evidence?.conditions);

  const evidenceByCondition = new Map(
    (dashboard.evidence?.conditions || []).map((item) => [item.condition, item])
  );
  const recommendations = dashboard.recommendations || {};
  // Only conditions this report actually flagged. `flagged` is the dashboard's
  // own predicate, so guidance can never claim a finding the cards do not show.
  const flaggedConditions = new Set(
    (dashboard.conditions || [])
      .filter((card) => card.flagged === true)
      .map((card) => card.condition)
  );
  const guidance = groupGuidance(recommendations.guidance?.items, flaggedConditions);

  // NOTES THE READER CAN DO SOMETHING WITH.
  //
  // `warnings` mixes two unrelated things: facts about whether the document
  // was read properly ("part of this report could not be read"), which change
  // what the patient should trust, and methodology notes from the fusion stage
  // about how two analyses relate to each other, which are clinician material.
  // The second kind was being printed here verbatim -- "Heart Disease: The
  // analyses contributing to this topic answer different questions..." -- and
  // it is both unreadable and redundant, because the card itself says it in
  // plain words on the only occasion it matters, when the two disagree.
  //
  // Methodology stages are filtered out of the PATIENT view only. The clinician
  // summary and the stored report keep every warning untouched.
  const METHODOLOGY_STAGES = new Set(['fusion', 'decision']);
  const readerWarnings = (dashboard.warnings || []).filter(
    (warning) =>
      !(warning && typeof warning === 'object'
        && METHODOLOGY_STAGES.has(warning.stage))
  );

  return (
    <main className="dashboard">
      <p className="crumbs">
        <Link to="/reports">Reports</Link> ·{' '}
        {report?.originalName || 'This report'}
      </p>

      <p className="dashboard__links">
        <Link to={`/reports/${id}/doctor-summary`}>Summary for a clinician</Link>
        {' · '}
        <Link to={`/reports/${id}/population`}>How your results compare</Link>
      </p>

      <OverallCard overall={dashboard.overall} />

      {/* FLAGGED FIRST, AND ONLY FLAGGED AS FULL CARDS.
          The pipeline evaluates the same fixed list of topics on every report,
          so a normal result produced ten cards of which seven said some form of
          nothing. Ten near-identical "nothing points to this" panels do not
          reassure -- they bury the one or two that matter and make the page
          look like a list of things wrong with you.

          The three outcomes stay strictly separate, because collapsing them is
          the failure this whole screen exists to prevent: CHECKED AND CLEAR is
          not COULD NOT CHECK. Each keeps its own sentence. */}
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

      {clearCards.length || unassessedCards.length ? (
        <>
          <h2>Everything else that was checked</h2>
          {clearCards.length ? (
            <p className="condition__roundup">
              <strong>Nothing in these results pointed to:</strong>{' '}
              {clearCards.map((card) => card.condition).join(', ')}.
            </p>
          ) : null}
          {unassessedCards.length ? (
            <p className="condition__roundup condition__roundup--unassessed">
              <strong>Not enough information to check:</strong>{' '}
              {unassessedCards.map((card) => card.condition).join(', ')}. An
              unchecked topic is an open question, not a negative result — it
              needs a test this report did not include.
            </p>
          ) : null}
        </>
      ) : null}

      {!dashboard.conditions?.length ? (
        <p className="empty">No conditions were assessed for this report.</p>
      ) : null}

      <h2>Your results</h2>
      {measuredLabs.length ? (
        <LabTable rows={measuredLabs} verdicts={verdicts} />
      ) : (
        <p className="empty">No laboratory values were read from this report.</p>
      )}

      {/* PROFILE ANSWERS ARE NOT LABORATORY VALUES. Age, BMI, sex and smoking
          history came from the questionnaire, not from blood, and listing them
          under "Laboratory values" claimed the report measured them. They are
          still shown -- they were used, so the reader is entitled to see
          them -- but as what they are. */}
      {profileLabs.length ? (
        <>
          <h2>From your profile</h2>
          <LabTable
            rows={profileLabs}
            fromProfile
            caption="These came from the details you entered, not from this report. They are used to interpret your results — they are not results themselves."
          />
        </>
      ) : null}

      {guidance.relevant.length ? (
        <>
          <h2>Topics you could read about</h2>
          <ul className="guidance">
            {guidance.relevant.map((item, index) => (
              <li key={item.code || index}>
                {trimGeneralPrefix(item.text || item.title)}
                {becausePhrase(item) ? (
                  <span className="guidance__because">
                    {' '}
                    Related to: {becausePhrase(item)}.
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
          <p className="hint">
            General educational topics, matched to what this report flagged.
            They are not written for you, are not personalised treatment
            advice, and are not instructions.
          </p>
        </>
      ) : null}

      {readerWarnings.length ? (
        <>
          <h2>Worth knowing about this analysis</h2>
          <WarningList warnings={readerWarnings} />
        </>
      ) : null}

      <Unanalysed unanalysed={dashboard.unanalysed} />

      {/* LAST, deliberately. The numbers and what was flagged come first --
          that is what the reader opened the page for. The long-form
          explanation is the thing you read once you know which result you
          care about, so it sits at the end rather than pushing the findings
          below the fold. */}
      <Explanations explanations={recommendations.explanations} />
    </main>
  );
}
