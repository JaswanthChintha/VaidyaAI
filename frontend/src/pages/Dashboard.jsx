import { useEffect, useRef, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, ApiError } from '../lib/api';
import { Absent, Risk, Value, WarningList } from '../components/Absent';
import { isPresent } from '../lib/absence';
import RiskGauge from '../components/RiskGauge';
import CoverageRadar from '../components/CoverageRadar';
import { PATIENT_LABEL } from '../lib/labels';
import { ProfileIdentityNotice } from '../components/IdentityNotice';

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

      {/* REMOVED ON THE READER'S INSTRUCTION: "This assessment is incomplete"
          and the producer's `overall.caveat` paragraph beneath it. Both said
          the overall status rests only on what could be assessed.

          `complete` and `caveat` are STILL IN THE PAYLOAD and are still
          produced, so nothing upstream changed and the clinician summary is
          untouched -- this card simply no longer prints them. The list of
          conditions that could not be assessed stays below, because that
          names them rather than qualifying the verdict in the abstract. */}

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

/**
 * The same verdicts, for a topic decided by COUNTING RISK FACTORS.
 *
 * "Close to the usual limit" describes a comparison against a cut-off, and a
 * risk-factor count is not one. On a real Heart Disease card it appeared
 * directly above two rows reading "268 mg/dl above 240 mg/dl" and "8.4 %
 * above 6.5 %" -- so the card simultaneously said the values were close to
 * the limit and above it. Both sentences were true of different things and
 * the reader had no way to know that.
 *
 * The count is what was borderline; the individual values were not.
 */
const RISK_FACTOR_STATUS = {
  'Indicated': 'Several things here are known to raise this risk — worth discussing with a doctor',
  'Borderline': 'Some things here are known to raise this risk — worth keeping an eye on',
  'Not Indicated': 'Nothing in these results points to this',
  'Insufficient Data': 'Not enough information in this report to check this',
  'Inconclusive': 'The checks did not agree, so this is unresolved',
};

/**
 * The same verdicts again, for a topic ONLY the statistical model flagged.
 *
 * "These results point to this" describes a comparison of measured values,
 * and on a model-only topic no comparison found anything -- the threshold
 * check returned `Not Indicated`. On the live report that sentence sat above
 * `creatinine 1.1 mg/dl`, a value in range, under a verdict of High. It is the
 * same fault RISK_FACTOR_STATUS exists to fix, in a third basis: a headline
 * describing a kind of reasoning the card did not use.
 *
 * Only the two statuses that differ are defined. `statusText` falls back to
 * PATIENT_STATUS for the rest, so the three lines these tables would otherwise
 * hold identically cannot drift apart in three places.
 */
const MODEL_STATUS = {
  'Indicated': 'A statistical model flagged this — worth discussing with a doctor',
  'Borderline': 'A statistical model flagged this as borderline — worth keeping an eye on',
};

/**
 * Was this verdict reached by counting risk factors rather than by comparing
 * a value to a cut-off?
 *
 * Requires POSITIVE proof of a count and the ABSENCE of any threshold
 * comparison. A topic with both is described in threshold language, because
 * a crossing did happen and that is the more concrete thing to say. A topic
 * whose sources are unknown keeps the default wording -- an unfamiliar basis
 * must not silently acquire a different description.
 */
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

/**
 * `basis` is 'model' | 'risk_factors' | anything else for the default.
 *
 * THE MODEL CASE OUTRANKS THE RISK-FACTOR CASE, and the shape where that
 * matters is real: a rule that counted risk factors and found NONE returns
 * `Not Indicated` with no threshold comparison anywhere, so `countsRiskFactors`
 * is true at the same time as `flaggedByModelAlone`. Describing that card as
 * "several things here are known to raise this risk" would state the opposite
 * of what the count found. Whichever analysis actually produced the verdict
 * gets to name it.
 *
 * An unrecognised basis falls through to PATIENT_STATUS, and an unrecognised
 * STATUS to the raw word -- a missing gloss is cosmetic, a guessed one is
 * clinical.
 */
const statusText = (status, basis = 'default') => {
  if (!isPresent(status)) return null;
  const table =
    basis === 'model' ? MODEL_STATUS : basis === 'risk_factors' ? RISK_FACTOR_STATUS : PATIENT_STATUS;
  return table[status] || PATIENT_STATUS[status] || status;
};

/* `shouldShowBasisNote` lived here: it decided when to print the basis-conflict
   paragraph, by proving the contributing analyses had NOT agreed. The
   paragraph itself is gone from this screen (see ConditionCard), so the guard
   went with it rather than being left as an unreachable branch. The reasoning
   it encoded is worth keeping if it ever comes back: `basisConflict` does not
   mean the analyses disagreed -- it means they answer different questions --
   and the test was "can we prove they agreed", never "did they disagree",
   because missing per-source verdicts are not agreement. */

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
 * The attribution to print ONCE above the list, or null to print it per item.
 *
 * On a report flagging one topic, every bullet carried the identical trailing
 * "Related to: Obesity." -- the same sentence three times, which is §6ag's
 * repetition fault and §6w's burial fault arriving in a list.
 *
 * HOISTING IS ONLY CORRECT WHEN THE SETS ARE IDENTICAL. If one bullet is there
 * because of Obesity and another because of Obesity and Diabetes, a single
 * line above the list is FALSE for one of them -- and it is false in the
 * direction that announces a condition to a reader whose bullet had nothing to
 * do with it, which is the exact hazard `matchedConditions` was written to
 * prevent. So: every item must carry a non-empty `because`, and all of them
 * must be the same set. Anything else keeps the per-item spans.
 *
 * Order is not significance here -- the catalog's list order is incidental --
 * so the comparison is set-wise, not positional.
 */
function sharedBecausePhrase(items) {
  if (!items?.length) return null;
  // `groupGuidance` pushes an item ONLY when `matchedConditions` returned a
  // non-empty list, so every row that reaches here has a reason. An empty-key
  // guard was written, MUTATION-SURVIVED, and was deleted rather than kept:
  // it is unreachable from the one caller, and this file already has a
  // catalogue of branches nobody can find out are wrong. If a future caller
  // passes unfiltered items, `becausePhrase` returns null for an empty list
  // and the per-row spans come back -- the safe direction.
  const key = (item) => [...new Set(item.because || [])].sort().join(' ');
  const first = key(items[0]);
  if (!items.every((item) => key(item) === first)) return null;
  return becausePhrase(items[0]);
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

  // NEVER ASKED IS NOT WITHHELD, and the two need separate sentences.
  //
  // Module 23 writes up to six explanations per report. A report carrying more
  // results than that has the rest recorded as skipped -- they were not
  // refused by the safety layer and nothing went wrong with them; they were
  // simply not attempted. Reading six cards under "What these results mean"
  // with no eighth and no ninth is a partial set that looks complete, which is
  // the same failure as a withheld paragraph rendering as a blank space.
  //
  // ONLY THE ROWS THIS PAGE SHOWS AS RESULTS. `skipped` also names `age`,
  // `gender` and `bmi` -- the profile answers the assessment used. "No
  // explanation was prepared for your age" is the screen describing its own
  // mechanics; nobody was waiting to be told what age measures.
  const notAttempted = (explanations?.notExplained || []).filter(
    (item) => item && resultFeatures?.has(item.feature)
  );

  // THE SENTENCE BELOW SAYS "not explained ABOVE", so there has to be an
  // above. With no explanation on screen there is no partial set to mistake
  // for a complete one -- the absent section already says nothing was
  // explained -- and a lone sentence pointing at nothing is §6w's scope-
  // statement fault ("No line BELOW asserts..." moved to the foot of a page).
  // THE SECTION ALSO CARRIES THE NOT-ASSESSED DESCRIPTIONS NOW, so it may be
  // worth rendering even when the pipeline explained nothing: a report whose
  // every parameter is unassessed still has tests worth describing.
  const describedUnassessed = (unassessedItems || []).filter(
    (item) => item.descriptionAvailable === true || item.descriptionAvailable === false
  );
  // THE GATE HAS TO KNOW EVERYTHING THIS SECTION NOW CARRIES. It listed only
  // the explanation entries, so a report with ranges to show and a provenance
  // sentence to make -- but nothing the writer had explained -- rendered
  // neither. The section stopped being only about explanations when the
  // ranges moved into it.
  // ONE LIST, BUILT ONCE. The written explanations interpret the reader's own
  // value; the descriptions say what a test measures and were written from its
  // NAME alone. They are rendered identically on the reader's instruction, so
  // the difference between them is stated in the provenance sentence instead
  // of in a heading above a group.
  const disclosures = [
    ...written.map((entry, index) => ({
      key: entry.feature || `written-${index}`,
      subject: PATIENT_LABEL[entry.feature] || entry.subject,
      body: (
        <p className="explanation__text">{trimClosingAdvice(entry.explanation)}</p>
      ),
    })),
    ...describedUnassessed.map((item, index) => ({
      key: `${item.testName}-${index}`,
      subject: item.testName,
      body: (
        <div className="explanation__body">
          <ParameterDescription item={item} />
        </div>
      ),
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
      <h2>What these results mean</h2>

      {/* ONE DISCLOSURE PER RESULT, CLOSED BY DEFAULT.
          Six paragraphs of five to eight lines each is most of this page, and
          a reader looking for one of them has to scroll past the other five.
          The SUBJECT stays visible in every summary, so the list still says
          what is available and the reader chooses what to open.

          NATIVE `<details>`, not a button and a state hook: it is keyboard
          operable, exposes the right role to a screen reader, and still opens
          with no JavaScript. The chevron is CSS on `[open]`, and the global
          `prefers-reduced-motion` block already switches its transition off.

          WHAT IS NOT COLLAPSED, and this is the part that matters: every
          sentence BELOW is an absence -- a withheld explanation, one never
          attempted, and the tests this tool does not check. An absence put
          behind a disclosure is an absence the reader never learns about,
          which is the one failure this page exists to prevent. They stay on
          the page whether anything is open or not. */}
      {/* ONE LIST. The tests this tool does not assess had their own heading
          and their own paragraph of qualification; they are ordinary entries
          here now, in the same position and the same shape as the rest.
          WHAT THE HEADING CARRIED IS NOT DROPPED -- these are written from
          the NAME of the test alone, with no patient data in the prompt
          (§6v), and a reader who took one for an interpretation of their own
          value would be making exactly the inference the architecture exists
          to prevent. It is said once, in the provenance sentence below, and
          not as a label on a group. */}
      {disclosures.map((entry) => (
        <details className="card explanation disclosure" key={entry.key}>
          <summary className="disclosure__summary">
            <h3 className="explanation__subject">{entry.subject}</h3>
            <span className="disclosure__chevron" aria-hidden="true" />
          </summary>
          {entry.body}
        </details>
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

      {/* "has no explanation ABOVE" NEEDS AN ABOVE. This used to be guaranteed
          by the section's own early return, which fired whenever nothing had
          been explained. The section renders for ranges and the provenance
          sentence now, so the gate has to be stated here or the sentence
          points at an empty list -- §6w's scope-statement fault exactly. */}
      {notAttempted.length && written.length ? (
        <p className="hint">
          {/* `andList`, not a plain join: a bare comma reads as a sentence
              fragment, and a laboratory name containing a comma turns a list
              of two into a list of four (§6w). */}
          {andList(notAttempted.map((item) => PATIENT_LABEL[item.feature] || item.feature))}{' '}
          {notAttempted.length === 1 ? 'has' : 'have'} no explanation above.
          Only a set number of explanations is written for each report, and
          this one has more results than that — nothing was wrong with{' '}
          {notAttempted.length === 1 ? 'this result' : 'these results'}, and{' '}
          {notAttempted.length === 1 ? 'its value is' : 'their values are'} in
          the table above.
        </p>
      ) : null}

      {/* REMOVED ON THE READER'S INSTRUCTION, TWICE GIVEN.
         A paragraph stood here saying how many of the listed results this
         tool had assessed, that the rest did not contribute to the topics
         above, that the notes on them describe the test rather than the
         reader's value, and that not checked is not the same as normal. It
         was kept back when the tables were merged and again when the
         explanation lists were, on the argument that a uniform page would
         otherwise imply an assessment nobody made. The reader has asked for
         it to go both times. It is their page and their call; this note
         records what was removed and why it was there, so the next person to
         read this file does not reintroduce it by accident. */}
      {/* REMOVED ON THE READER'S INSTRUCTION: a "Normal ranges for these
          results" disclosure listing each test against its interval, and the
          notice above it saying a report had printed none of its own. The
          ranges came out of the results table in aaae0d7 and landed here;
          they are simply not shown now. `referenceLow` / `referenceHigh` and
          the laboratory's own bounds are untouched in the payload. */}
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
          // KEPT SO THE ROW CAN NAME THIS REFERENCE when it disagrees with
          // the one the laboratory printed. `crossing` already renders it as
          // "below 13 g/dl", which is the phrase a reader needs; recomposing
          // it at the point of use would be a second implementation of the
          // same sentence.
          crossedText: crossed,
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
/**
 * What a test measures — never what this reader's result means.
 *
 * THREE STATES, AND THE SILENT ONE IS DELIBERATE. Only tests the laboratory
 * itself marked abnormal are ever described, so an item with no description
 * fields was never asked about and gets nothing rendered: inventing a line for
 * it would say "there is nothing to tell you about this test" when the truth is
 * that nobody asked. An item whose description was WITHHELD — the model did not
 * answer, or the safety validator refused what it said — is different, and says
 * so out loud, because a blank space there would read as an absence of content
 * rather than a suppression of it.
 */
function ParameterDescription({ item }) {
  if (item.descriptionAvailable === true) {
    return <p className="unanalysed__description">{item.description}</p>;
  }
  if (item.descriptionAvailable === false) {
    // THE PRODUCER'S NOTICE IS ALREADY A WHOLE SENTENCE, written for a patient
    // and chosen to fit the reason. Prefixing it with a sentence of our own
    // said the same thing twice on screen. Ours is the fallback for a withheld
    // entry that arrived with no notice at all, which must still not render as
    // a blank line.
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



/* `Unanalysed` STOOD HERE AND IS DELETED, not left unused.
   It rendered the whole bottom-of-page section: the lab-flagged list with its
   ranges, the skip-reason groups, and the descriptions. Every one of those
   now has a home in the section a reader is already reading. An unused
   component that still renders a complete version of a screen is the most
   expensive kind of dead code -- the next person to touch this file cannot
   tell which of the two is live. `ParameterDescription` above is kept: the
   new group uses it. */

/**
 * The whole report, in one place, in English -- COMPOSED, NEVER GENERATED.
 *
 * ==========================================================================
 * WHY THIS IS NOT A MODEL CALL, WHICH IS THE OBVIOUS WAY TO BUILD IT
 * ==========================================================================
 *
 * "Summarise this report for the patient" is one prompt away and it would be
 * the single most dangerous string on this screen. A generated overall summary
 * is a new patient-facing conclusion with no rule, no threshold, no model and
 * no evidence chain behind it -- rendered underneath fourteen findings that
 * have all four, and indistinguishable from them. It could also contradict the
 * cards above it while looking more authoritative than any of them, because it
 * is the part a reader will actually read.
 *
 * So every sentence below is assembled from a decision some stage already
 * made and this file only puts into words. Nothing here can say anything the
 * page above does not already say.
 *
 * THE COUNTS COME FROM THE CARDS ON SCREEN, NOT FROM THE COUNTERS. `overall`
 * carries `abnormalConditionCount` and it would be the easy thing to print --
 * but the page groups cards with its own predicate (`Not Indicated` + assessed
 * + not flagged, and anything unrecognised stays flagged), so a counter and
 * the cards can disagree. A summary that says six while five cards are shown
 * is worse than no summary, and MEMORY.md section 6u records this project
 * printing `unmapped_count: 0` over a list of sixty-three. So the already
 * grouped arrays are passed in and counted here.
 *
 * WHAT IT MUST NEVER DO is the failure this whole codebase is built against:
 * report an absence as a negative result. Three separate paragraphs exist
 * only to prevent that -- the topics that could not be checked, the tests the
 * laboratory flagged that this platform does not assess at all, and the pages
 * that could not be read. Any of them being silently dropped turns "we did not
 * look" into "we looked and found nothing".
 */

/**
 * Module 18's five labels, in the words a patient uses.
 *
 * AN UNRECOGNISED LABEL GETS NO SENTENCE. If Module 18 ever grows a sixth
 * value, guessing at its meaning here would put a fabricated conclusion under
 * a real one; the label is shown as it stands instead, and the reader is told
 * plainly that this screen has no plain-English wording for it. A missing
 * gloss is a cosmetic problem. A wrong one is a clinical problem.
 */
/*
 * NOTE THE ABSENCE OF THE WORDS "IN THIS REPORT". The first version of this
 * table said "Something in this report is outside its usual range", and on a
 * report whose every laboratory value was in range and whose only finding was
 * Obesity, that sentence was FALSE: Obesity is decided from BMI, BMI is
 * computed from the height and weight the patient typed into the profile form,
 * and nothing about it was measured in the document. A reader looking at a
 * table of in-range results and a summary claiming their report was out of
 * range has been handed a contradiction the page created itself.
 *
 * The lab table already keeps the two apart -- "Your results" and "From your
 * profile" are separate sections for exactly this reason -- and the summary
 * had flattened that distinction back. So the wording claims no location, and
 * the source of a flagged finding is stated explicitly below where it is known.
 */
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

/**
 * Was every value behind this finding typed in rather than measured?
 *
 * BMI drives Obesity and Underweight, and BMI comes from the profile form. A
 * finding resting entirely on it is a finding about what the patient told us,
 * not about their blood, and saying otherwise invents a measurement.
 *
 * NO EVIDENCE MEANS NO CLAIM. An empty `lines` array returns false, so a
 * finding whose provenance is unknown is never labelled as coming from the
 * profile -- unknown provenance must not become a statement, in either
 * direction. `every` over an empty array is `true`, which is why the length
 * check is here and not an oversight.
 */
function isProfileDerived(evidence) {
  const lines = evidence?.lines || [];
  if (!lines.length) return false;
  return lines.every((line) => line.sourceStage === 'patient_profile');
}

/**
 * Join names into prose WITHOUT merging them into each other.
 *
 * A laboratory prints "LDL Cholesterol, Direct" and "Potassium, Serum", so a
 * comma-joined list of three tests read as five: *"LDL Cholesterol, Direct,
 * Blood Urea, Potassium, Serum"*. On a line that begins "your laboratory
 * marked 3 results outside its own range" the count and the list then
 * contradict each other, and the reader cannot tell which names are real.
 *
 * The separator is chosen from the data rather than assumed: a semicolon only
 * where a name actually contains a comma, so the ordinary case still reads as
 * ordinary English.
 */
const commaSafeSeparator = (names) =>
  names.some((name) => String(name).includes(',')) ? '; ' : ', ';

const nameList = (names) => names.join(commaSafeSeparator(names));

const listOfNames = (cards) => nameList(cards.map((card) => card.condition));

/**
 * The same list, as prose: "A, B and C".
 *
 * Comma-aware for the same reason `nameList` is -- a laboratory name with a
 * comma in it turns two tests into four -- and it exists because a bare
 * `join(', ')` reads as a fragment mid-sentence: "Total cholesterol,
 * Triglycerides are not explained above" is not English.
 */
const andList = (names) => {
  if (!names.length) return '';
  if (names.length === 1) return String(names[0]);
  // The SAME separator rule as `nameList`, not a second copy of it.
  return `${names.slice(0, -1).join(commaSafeSeparator(names))} and ${names[names.length - 1]}`;
};

function InShort({
  dashboard,
  flaggedCards,
  clearCards,
  // NO `unassessedCards`. This panel stopped naming them at `251c971` and
  // must not be handed them again: the only thing it could do with the list
  // is send it to the rewrite, which is the defect described at `names`.
  reportId,
  // PASSED, NOT RECOMPUTED. These are the engine's own threshold crossings as
  // the page read them; deriving them a second time here would be a second
  // implementation free to disagree with the table above.
  verdicts,
}) {
  const bodyRef = useRef(null);
  const [prose, setProse] = useState(null);
  const [context, setContext] = useState([]);
  const overall = dashboard.overall;

  /* MODULE 34 -- what the results already marked out of range are GENERALLY
     associated with.
     THE FINDINGS ARE DERIVED FROM WHAT THE PAGE ALREADY SHOWS: a verdict
     direction this tool reached, or a direction the laboratory marked. No
     value is collected here and none is sent -- the request carries a test
     NAME and the word "raised" or "lowered", which is what keeps the answer
     about the test rather than about the reader.
     Anything that comes back empty renders NOTHING. There is no notice and no
     placeholder: the reader loses a paragraph they never saw. */
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
      // A PROFILE ANSWER IS NOT A LABORATORY RESULT. BMI, age, sex and smoking
      // history come from the questionnaire, and "a raised BMI is commonly
      // associated with..." under a heading about this report's results is the
      // same category error §6t found in the summary: a finding computed from
      // what the reader typed, presented as something the laboratory measured.
      if (!row || row.source === 'patient_profile') continue;
      // The laboratory's own printed name first, then this page's own label --
      // never the internal feature key, which is what §6an-i swept off every
      // reader-facing screen.
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
        /* A WITHHELD DESCRIPTION IS NOT A FINDING THAT DOES NOT EXIST.
           ==============================================================

           This filtered on `available === true` and dropped the rest, so a
           finding whose sentence was refused vanished from the page
           completely. On `03-renal-anaemia-deficiency.pdf` the payload
           carried FOUR findings and the reader was shown THREE:

               Serum Creatinine       raised    available=true
               Haemoglobin            lowered   available=true
               Vitamin D, 25-Hydroxy  lowered   available=FALSE  <-- gone
               Vitamin B12            lowered   available=true

           Vitamin D was correctly identified as out of range -- the rule
           engine recorded `vitamin_d 12 < 20`, and "Vitamin D Deficiency" is
           named four lines above as one of the five needing a closer look.
           Only its SENTENCE was missing, and the page turned that into the
           finding itself being absent.

           `refused_by: "number"` is why: Module 24 refused the generated text
           because a number appeared in it, which the finding-context policy
           forbids. That refusal is correct and is not the defect. Rendering
           nothing is.

           THE STANDING FAILURE MODE, ON THE SCREEN MOST PEOPLE SEE: "we
           could not describe it" rendered as "it is not a finding". The
           glossary beside it already solves this for unassessed tests -- it
           keeps the row and prints a notice -- and this now does the same.

           A NAME AND A DIRECTION ARE KEPT even with no text, because both
           are facts this tool derived and neither came from the model: the
           request carries only the test name and the word raised/lowered. */
        const entries = (res?.context?.entries || []).filter(
          (e) => e && typeof e.test_name === 'string' && e.test_name.trim()
        );
        /* ⚠ IF NOTHING WAS DESCRIBED, STILL RENDER NOTHING. That is a
           SEPARATE and already-settled decision, and it survives this change
           unweakened: a box containing only notices gives the reader nothing
           they did not have, and "an absence is not created by withholding
           one" -- the wording of the test that pins it.

           The defect fixed above is the PARTIAL list, where three findings
           are described, a fourth is silently dropped, and the shorter list
           reads as the complete one. So the box appears only when it has
           something to say, and when it does it names EVERY finding. */
        const described = entries.some(
          (e) => e.available === true && typeof e.text === 'string' && e.text.trim()
        );
        /* ONE EXCEPTION, and it is not a notice-only box (2026-09-24): a
           description STILL BEING WRITTEN tells the reader something they did
           not have -- that it is coming. During an outage the first view is
           exactly the one where nothing is finished, and rendering nothing
           there hid the fact that the work was under way. */
        const coming = entries.some((e) => e.refused_by === 'in_progress');
        if (!cancelled && (described || coming)) setContext(entries);
      } catch {
        // Nothing to report. The page is complete without this.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reportId]); // eslint-disable-line react-hooks/exhaustive-deps

  /* MODULE 33, AND EVERY PATH THROUGH IT ENDS AT THE COMPOSED TEXT.
     The sentences are read out of the rendered body, so what is sent is
     exactly what the reader would otherwise see. `prose` stays null on a
     refusal, on a transport failure, and on a response whose shape is not
     what this expects -- and null renders the composed body, which is what
     this panel shows today. There is no error state because there is nothing
     to report: the page is complete either way. */
  useEffect(() => {
    let cancelled = false;
    if (!reportId || !overall || !bodyRef.current) return undefined;
    const sentences = [...bodyRef.current.querySelectorAll('p')]
      .map((node) => node.textContent.replace(/\s+/g, ' ').trim())
      .filter(Boolean);
    if (!sentences.length) return undefined;
    // Every name that must survive the rewrite. The caller knows which tokens
    // are names; the service must not guess at them.
    //
    // ⚠ A NAME MAY ONLY BE REQUIRED TO SURVIVE IF IT IS IN THE SENTENCES.
    // `unassessedCards` USED TO BE HERE AND WAS NEVER IN THE BODY.
    //
    // `251c971` removed the paragraph that named the conditions this tool
    // could not check -- on the reader's own instruction, and rightly -- but
    // left those names in this list. From then on the rewrite was required to
    // reproduce names the model had never been shown, which no rewrite can do.
    // `_missing` in summary_prose.py refuses on exactly that, and the refusal
    // discards the whole rewrite: both real laboratory reports on this account
    // ended with NO prose, permanently, through the two different routes that
    // impossibility produces --
    //
    //   Test 3.pdf   outcome facts_missing    dropped: the 4 unassessed names
    //   Test 2.pdf   outcome facts_invented   the retry fed the model the
    //                names it had "dropped", the model duly wrote about
    //                conditions that were never described, and it tripped
    //                `_invented` instead. THAT IS THE WORSE FAILURE: an
    //                impossible must-survive list does not just refuse, it
    //                pressures the model into inventing the missing content.
    //
    // Measured across all four reports: 0 unassessed -> `generated` (2 of 2),
    // 4 unassessed -> no text at all (2 of 2). The two remaining sources are
    // safe and must stay -- `listOfNames` writes the flagged and clear cards
    // into the body below, and `nameList` writes the laboratory-flagged rows.
    // The test asserts the INVARIANT (every name sent appears in the sentences
    // sent) rather than this one absence, because the defect is re-introduced
    // by adding any name whose paragraph is later removed.
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
        // Deliberately swallowed. A rewrite that did not happen is not an
        // error the reader has any use for -- they are reading the composed
        // sentences, which say the same things.
      }
    })();
    return () => {
      cancelled = true;
    };
    // Recomposed only when the report changes. The sentences are derived from
    // the same payload, so a dependency on them would re-request on every
    // render for no new input.
  }, [reportId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!overall) return null;

  const label = isPresent(overall.statusLabel) ? overall.statusLabel : null;
  // `?? null` is load-bearing. A bare lookup yields `undefined` for an
  // unrecognised label, `undefined !== null` is true, and the headline then
  // rendered an EMPTY `<strong>` -- the summary silently said nothing about
  // the verdict instead of falling through to the wording below. Found by the
  // test for exactly that case.
  const inEnglish =
    label === null ? null : STATUS_IN_ENGLISH[label] ?? null;

  const checked = flaggedCards.length + clearCards.length;
  const unanalysed = dashboard.unanalysed || {};
  /* EVERYTHING OUT OF RANGE THAT NOTHING ABOVE ALREADY ACCOUNTS FOR.
     ==================================================================

     This counted ONLY `unanalysed.items` -- the rows with no canonical
     feature -- so on Test 3 it said:

         "2 further results are outside the range printed on the report
          — ESR, C-REACTIVE PROTEIN(CRP)"

     while the findings list four inches below it named SEVEN, including
     NEUTROPHILS 82 % and LYMPHOCYTES 14 %, both outside their printed
     intervals and neither mentioned in the sentence counting them.

     THE SAME ARCHITECTURE LEAK AS THE CLINICIAN PAGE'S TWO OUT-OF-RANGE
     LISTS, which was fixed earlier today: the dividing line was whether this
     platform holds a canonical feature, and a reader neither knows nor cares
     that such a line exists. It became visible when the blood count made
     neutrophils and lymphocytes features, moving them out of the only list
     that was being counted.

     WHAT "FURTHER" MEANS, AND IT IS THE POINT OF THE WORD. Further than the
     conditions already named above. A raised HbA1c is not a further result
     -- it is the evidence for the Diabetes card the reader just read, and
     repeating it here would pad the summary with things it has already said.
     So a row is counted when it is out of range AND its feature contributed
     to NO condition on this page. Neutrophils and lymphocytes qualify
     because no rule here reads them; haemoglobin does not, because Anemia
     is named above and cites it.

     THE VERDICTS ARE THE PAGE'S OWN, passed in rather than recomputed, for
     the reason given where they arrive: a second derivation here would be a
     second implementation free to disagree with the table. */
  const coveredByACondition = new Set(
    (dashboard.conditions || []).flatMap((item) => item.evidenceFeatures || [])
  );
  const furtherRows = (dashboard.laboratory || [])
    .filter((row) => {
      // A profile answer is not a laboratory result -- same exclusion, and
      // the same reason, as the findings list above.
      if (row.source === 'patient_profile') return false;
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
  // The skipped results the laboratory did NOT mark. Counted off the same
  // items list rather than from `unanalysed.count` alone, so the two
  // paragraphs about skipped tests can never overlap or double-count.
  const unreadable = dashboard.document?.pagesUnreadable || [];

  // WHICH FLAGGED FINDINGS CAME FROM THE FORM RATHER THAN THE REPORT.
  // Obesity and Underweight rest entirely on BMI, which is computed from the
  // height and weight the patient entered. Without this, a report whose every
  // laboratory value is in range can carry a summary saying something is out
  // of range, and nothing on the page explains where it came from.
  const evidenceFor = new Map(
    (dashboard.evidence?.conditions || []).map((item) => [item.condition, item])
  );
  const fromProfile = flaggedCards.filter((card) =>
    isProfileDerived(evidenceFor.get(card.condition))
  );

  return (
    <section className="card in-short">
      <h2>In short</h2>

      {/* THE HEADLINE, and the only place on this page that puts Module 18's
          verdict into a sentence. The label itself is kept beside it: the
          sentence is this screen's wording, the label is the pipeline's, and
          a reader comparing this section with the card at the top must be
          able to see they are the same verdict. */}
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

      {/* THE COMPOSED BODY, AND THE ONLY PART A REWRITE MAY TOUCH.
          The sentences sent to Module 33 are read back out of THIS element,
          not composed a second time: the DOM is what the page actually says,
          so there is no second implementation of the counting rules that
          could disagree with the first. The headline above and the closing
          line below sit outside it deliberately -- the closing line is the
          one sentence on this panel that states what this tool is, and a
          model may not reword it. `clinician_narrative` appends its own
          closing line verbatim for the same reason. */}
      <div className="in-short__body" ref={bodyRef} hidden={Boolean(prose)}>

      {/* NO "Recorded as Needs Monitoring · overall risk: Low" LINE HERE.
          It restated two internal labels the card at the top of the page
          already shows, and restating them is what made them look like a
          contradiction in the first place: a reader asked why something
          "needs monitoring" if the risk is "low". Those two words come from
          different scales, and the honest fix on a PATIENT screen is not a
          paragraph reconciling them -- it is not to put the reader in front of
          the pair at all. The sentence above already carries the severity
          ("worth keeping an eye on" against "should be looked at by a
          doctor"), which is the part a patient can act on. The vocabulary
          lives on the Overall card and on the clinician summary, which is the
          split section 6u established. */}

      {/* WHAT WAS CHECKED AND WHAT CAME BACK. Counted off the cards above. */}
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

      {/* WHERE A FLAGGED FINDING ACTUALLY CAME FROM. Only stated where it is
          known and where it is the whole of the finding -- a mixed finding
          rests partly on measurements and saying "not from your report" about
          it would be its own false claim. */}
      {fromProfile.length ? (
        <p className="hint">
          {nameList(fromProfile.map((card) => card.condition))}{' '}
          {fromProfile.length === 1 ? 'comes' : 'come'} from the details you
          entered — your height, weight, age and the answers you gave — not
          from anything measured in this report.
          {/* THE SECOND SENTENCE IS ONLY TRUE WHEN THE PROFILE FINDINGS ARE
              THE ONLY FINDINGS. On a report that also flagged Diabetes from a
              raised HbA1c, "while every laboratory result on the page is in
              range" is false -- the same mistake as the locative this
              paragraph exists to fix, one clause further down. Caught by
              reading the sentence on a real mixed report. */}
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

      {/* ABSENCE #1: topics that could not be checked at all. */}
      {/* ABSENCE #2: results outside their printed interval that no topic
          here assessed. A reader will stop on these and a doctor will want
          them raised, and they sit outside every count above -- so leaving
          them out would let the reader think the flagged topics were the
          whole story.

          ⚠ IT NO LONGER SAYS "YOUR LABORATORY MARKED", WHICH IS 6az's FIX
          ARRIVING ON A SECOND SCREEN. `labFlaggedAbnormal` is now true when
          the value sits outside the interval printed beside it, whether or
          not the report marked it -- because a re-extraction of `Test 3.pdf`
          dropped the flag on CRP and the page then showed 38.9 mg/L against
          a printed <= 5 as "In range". See the note on the producer in
          backend/src/services/dashboardService.js.

          So the claim had to stop naming an agent it cannot know. That the
          value falls outside the printed interval is checkable from this
          screen; WHO decided it is not knowable until `flag_source` exists
          (MEMORY.md section 0, item 5). The clinician page carries the same
          sentence for the same reason. */}
      {labFlagged.length ? (
        <p className="caveat">
          <strong>
            {labFlagged.length} further result
            {labFlagged.length === 1 ? ' is' : 's are'} outside the range
            printed on the report
          </strong>{' '}
          — {nameList(labFlagged.map((item) => item.testName))}. Worth raising
          with a qualified healthcare professional.
        </p>
      ) : null}

      {/* REMOVED ON THE READER'S INSTRUCTION. A paragraph stood here saying
          how many further results had been read but not assessed, and that
          not checked is not the same as normal. The reader asked for the
          summary to read as a summary and not as an account of what this tool
          does and does not do. The laboratory's own flagged results are still
          named above, which is the part a doctor is asked to look at. */}

      {/* ABSENCE #3: the document itself. A test missing from the analysis
          because its page could not be read is not a test that was absent
          from the report, and only this says which. */}
      {unreadable.length || dashboard.document?.partialDocument === true ? (
        <p className="caveat">
          <strong>Part of this document could not be read</strong>
          {unreadable.length
            ? ` (page${unreadable.length === 1 ? '' : 's'} ${unreadable.join(', ')})`
            : ''}
          . A test missing from this analysis may be missing from the reading
          rather than absent from your report.
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

      {/* THE REWRITE, WHEN THERE IS ONE. It replaces the composed paragraphs
          and never the closing line. The composed body stays in the DOM,
          hidden -- removing it would leave nothing to read the sentences back
          out of if this ever needs to re-ask, and `hidden` keeps it out of
          the accessibility tree so a screen reader does not hear both. */}
      {prose ? <p className="in-short__prose">{prose}</p> : null}

      {/* WHAT THE OUT-OF-RANGE RESULTS ARE GENERALLY ASSOCIATED WITH.
          OUTSIDE the rewritable body, so a summary rewrite can neither reword
          these nor swallow them, and above the closing line, which still has
          the last word. Each sentence is about the TEST and the DIRECTION --
          the same sentence for every reader with a raised CRP -- so it
          carries no attribution: there is no claim about this reader in it to
          attribute. */}
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
                  /* STILL BEING WRITTEN, which is not the same as "could not
                     be prepared" (2026-09-24). The ai-service answers within a
                     deadline and leaves slow descriptions running; the next
                     view has them. Saying "could not" here would be false. */
                  <span className="absent">
                    A description is still being prepared; it will appear when
                    you open this page again. The value itself is in the table
                    above and is unaffected.
                  </span>
                ) : (
                  /* THE FINDING SURVIVES ITS MISSING SENTENCE. Same shape as
                     the glossary's notice for a test with no description, and
                     the same reason: the reader is told what is absent rather
                     than shown a shorter list. The VALUE is unaffected and is
                     in the table above, which is the reassurance that
                     actually matters here. */
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

      {/* THE CLOSING LINE IS NOT OPTIONAL and is deliberately not conditional
          on anything having been flagged: a reader whose report came back
          clear is exactly the reader most likely to treat this page as a
          medical opinion. It states what this is and what to do, and it
          recommends no treatment, no test and no action beyond seeing someone
          qualified. */}
      <p className="in-short__closing">
        This is health education and decision support. It is not a diagnosis,
        and it is not a substitute for advice from a qualified healthcare
        professional. Take this report — and anything marked above — to one.
      </p>
    </section>
  );
}

/**
 * A condition name short enough to sit beside a radar spoke.
 *
 * "Vitamin B12 Deficiency" is 22 characters and there is no honest way to fit
 * it against an axis without shrinking the type below the 11px floor. The full
 * name still reaches assistive technology through the chart's own title, and
 * every one of these keeps the ANALYTE -- which is the part a reader matches
 * against the table below.
 */
const RADAR_LABEL = {
  'High Cholesterol': 'Cholesterol',
  'High Triglycerides': 'Triglycerides',
  'Vitamin D Deficiency': 'Vitamin D',
  'Elevated Vitamin D': 'Vitamin D (high)',
  'Vitamin B12 Deficiency': 'Vitamin B12',
  'Elevated Hemoglobin': 'Haemoglobin (high)',
  'Kidney Disease': 'Kidney',
  'Heart Disease': 'Heart',
};

/* PATIENT_LABEL (patient-facing names; the catalog's own wording is for
   clinicians) moved to ../lib/labels.js, because the timeline's trend charts
   name the same features and a second copy of that table is how one of them
   drifts. */

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

/**
 * Where a value sits against the interval printed beside it.
 *
 * ⚠ THE COMPARISON THAT `labFlagVerdict` DOES NOT MAKE. That function returns
 * "In range" whenever an interval was printed at all, reasoning that a
 * laboratory which printed one has compared it. That was safe only while the
 * rows it served carried `labFlaggedAbnormal` from the PRODUCER, which does
 * compare the two numbers (dashboardService.js, and 6bg finding 4 -- CRP 38.9
 * against a printed limit of 5, shown to a patient as "In range").
 *
 * The assessed rows never had bounds to compare, because the only intervals
 * they were missing were the sex-specific ones. The moment those parse, PCV
 * 37.9 against a printed 40-50 would have rendered as "In range" on exactly
 * the reasoning that defect was made of. So the arithmetic arrives with the
 * ranges, in the same change.
 *
 * `null` means there was nothing to compare against -- never "normal".
 */
function printedPosition(value, low, high) {
  if (!isPresent(value)) return null;
  const hasLow = isPresent(low);
  const hasHigh = isPresent(high);
  if (!hasLow && !hasHigh) return null;
  if (hasHigh && value > high) return 'high';
  if (hasLow && value < low) return 'low';
  return 'normal';
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
  const missing = [];
  for (const line of byFeature.values()) {
    if (line.sourceStage === 'lab_report' && isPresent(line.value)) {
      measured.push(line);
    } else if (PATIENT_LABEL[line.feature]) {
      // AVAILABILITY DECIDES, NOT THE PRESENCE OF A LABEL.
      //
      // Every cited feature landed here regardless of whether it had a value,
      // so a card said "Your history of heart disease, history of high blood
      // pressure, smoking history, BMI, age and sex were also taken into
      // account" -- on a report where heart_disease and hypertension were
      // `not_present_in_report` with a null value. Two of the six named were
      // not taken into account, because they do not exist.
      //
      // That is absence rendered as a value, in the one place it does most
      // damage: a HEART DISEASE card, naming BLOOD PRESSURE. The heart model's
      // own author note says "Blood pressure, the strongest known predictor,
      // is still not collected by VaidyaAI" -- so the card asserted the
      // opposite of the single most important limitation of the assessment
      // above it.
      //
      // The absent ones are NOT silently dropped either. Dropping them is the
      // same failure from the other side: the reader would never learn that
      // the strongest predictor was missing. They are named as missing.
      if (line.availability === 'observed') context.push(line);
      else missing.push(line);
    }
  }
  return { measured, context, missing };
}

/**
 * Was this topic flagged by the MODEL, with the threshold check coming back
 * clear?
 *
 * THE CARD CANNOT EXPLAIN ITSELF IN THAT CASE, and it is a real shape rather
 * than a hypothetical: on the analysed report, Kidney Disease shows
 * `creatinine 1.1 mg/dl` crossing nothing, under a verdict of High. The
 * Clinical Rule Engine returned `Not Indicated` for it and the Random Forest
 * returned `Indicated`. A reader is shown a normal-looking number and a
 * serious word with nothing connecting them.
 *
 * PROOF IN BOTH DIRECTIONS, OR NOTHING. This never infers "no threshold was
 * crossed" from the absence of a crossing on screen -- that is a clinical
 * claim and the render layer has no business making it. It reads the
 * producer's own per-source verdicts, and stays silent unless BOTH are
 * present and assessed. `shouldShowBasisNote` (removed above) got this exact
 * reasoning right and it is worth repeating: missing information is not
 * agreement, and it is not disagreement either.
 *
 * A FINDING IS AN EXPLICIT STATUS, never "not Not Indicated". `Insufficient
 * Data` is an absence and must never be read as the model having found
 * something, and an unrecognised status must not silently become a finding.
 */
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
  return andList(names);
}

function ConditionCard({ card, evidence }) {
  const assessed = card.assessed !== false;
  const { measured, context, missing } = summariseEvidence(evidence);
  const alsoConsidered = contextPhrase(context);
  const notAvailable = contextPhrase(missing);

  // Does this card explain its own verdict? A row reading `268 mg/dl above
  // 240 mg/dl` does. A card with no crossing shown does not.
  //
  // NO `card.flagged === true` CLAUSE HERE, and that is deliberate after
  // trying one. ConditionCard is rendered ONLY for the flagged group (see the
  // call site: not unassessed and not clear), so "this card carries a verdict"
  // is the caller's guarantee and a second copy of it here is unreachable --
  // an unkillable mutation and a test that passes without asserting anything.
  // It was also WRONG: `flagged` is not true on every card in that group. A
  // `Borderline` topic lands there because `isClear` requires the exact status
  // `Not Indicated`, so gating on `flagged` would have stripped the
  // explanation from exactly the cards least able to speak for themselves.
  const verdictUnexplained = !measured.some((line) => crossing(line));

  // Said instead of the generic "how it was checked" line, not alongside it:
  // this sentence carries everything that one did, and more precisely.
  const modelAlone = flaggedByModelAlone(evidence);

  // Which kind of reasoning actually reached this verdict, so the headline
  // describes that one and not a comparison nobody made.
  const statusWording = statusText(
    card.status,
    modelAlone ? 'model' : countsRiskFactors(evidence) ? 'risk_factors' : 'default'
  );

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
        {statusWording ? (
          statusWording
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

      {/* THE BASIS-CONFLICT PARAGRAPH IS GONE, and this is the second time
          this exact shape has been removed from a patient screen.
          "Two checks were made and they did not agree. One counts risk factors
          from your profile; the other is a statistical estimate. They answer
          different questions, so neither settles the other" is four lines
          explaining why two of this screen's OWN FIELDS do not contradict each
          other -- §6w: when a screen needs that paragraph, the fields are the
          bug, not the missing paragraph. A patient cannot adjudicate between a
          risk-factor tally and a model probability; the decision engine
          already did, and the fused verdict is what this card shows. The
          sentence ended on "worth raising with a doctor", which the status
          line above says already.
          NOT LOST: `basisConflict` and `basisNote` are still in the payload,
          and the clinician passage still states which kind of check flagged
          what -- including the model-only case, which is the one a reader can
          be misled by. */}

      {/* HOW IT WAS CHECKED, ONLY WHEN THE CARD DOES NOT ALREADY SAY SO.
          Above a row reading `268 mg/dl  above 240 mg/dl`, "checked against
          standard clinical thresholds" is the screen narrating its own
          mechanics -- §6u removed "Based on: Clinical Rule Engine, Random
          Forest" from this very card for that reason, and this is the same
          sentence in friendlier words.
          But it cannot go unconditionally. A topic the statistical model
          flagged where NO measured value crossed a limit has nothing on the
          card explaining where the verdict came from, and a verdict with no
          reason is a thing to be believed or not. So it is stated exactly
          there, and nowhere else. */}
      {/* WHERE THE VERDICT CAME FROM, when the values on the card do not say.
          The model author's own framing, in the register of this page: a high
          score from a pattern model is a reason to discuss something, never a
          finding. Saying only "a statistical model also looked" leaves the
          reader to reconcile a normal number with a serious word themselves. */}
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

/**
 * What a reader is told when validation refused a reading.
 *
 * NOT the validator's own message. That is written for whoever has to fix the
 * unit -- "'vitamin_d' was reported in a unit that could not be recognised, so
 * it was never converted to the canonical ng/ml" -- and it names an internal
 * feature key, a canonical unit and a conversion step. The fact a patient can
 * act on is that the number was not used, and that is what this says. The
 * validator's wording is untouched in the stored analysis and on
 * GET /reports/:id/analysis.
 */
const REJECTED_FOR_READER =
  'This result could not be used, so nothing on this page is based on it.';

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
function LabRow({ row, showVerdict, verdict, fromProfile }) {
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

  // A WORD IS NOT A MEASUREMENT AND MUST NOT BE SET LIKE ONE.
  //
  // `.lab-table td` is monospace with tabular numerals, which is right for
  // the reason design.md §3 gives -- numbers align down the column and that
  // is what makes a results table scannable. A word aligns with nothing, so
  // the only thing the treatment carries there is the LOOK of a measured
  // value: on the profile table, `male` was set in the same face as
  // `26.42 kg/m2` directly above it, under a heading about results.
  // A NUMBER PRINTED AS A STRING IS STILL A NUMBER. The laboratory's own
  // rows arrive as text ("4.04", "7,290", "05"), and deciding on `typeof`
  // alone set them in the word face while the assessed rows beside them kept
  // tabular numerals -- the two kinds of row looking different in a table
  // whose point is that they do not. The printed text is shown UNCHANGED;
  // only the treatment is decided here.
  const numericText =
    typeof row.value === 'string' &&
    row.value.trim() !== '' &&
    Number.isFinite(Number(row.value.replace(/,/g, '')));
  const numericValue =
    (typeof row.value === 'number' && Number.isFinite(row.value)) || numericText;
  // First letter only, and only on a string. Not `text-transform: capitalize`,
  // which would render an absence sentence as "Not Measured", and not a
  // rewording of the producer's text -- "male" and "Male" are the same answer.
  const displayValue =
    !numericValue && typeof row.value === 'string' && row.value.length
      ? row.value.charAt(0).toUpperCase() + row.value.slice(1)
      : row.value;

  return (
    <tr className={`lab lab--${row.state || 'unknown'}`}>
      <th scope="row">
        {printed || titleCase(canonical)}
        {printed && canonical.toLowerCase() !== printed.toLowerCase() ? (
          <span className="lab__printed">{canonical}</span>
        ) : null}
      </th>

      <td className={numericValue ? undefined : 'lab__word'}>
        {/* THE REASON A VALUE WAS REFUSED IS NOT WRITTEN FOR THIS READER.
            `rejectionReason` is the validator's own message -- "'vitamin_d'
            was reported in a unit that could not be recognised, so it was
            never converted to the canonical ng/ml" -- naming the internal
            feature key and the canonical unit. A patient cannot act on it and
            most will not finish it.
            WHAT THEY CAN ACT ON IS THE FACT ITSELF, and that is kept: the
            value was not used, said in one line. The validator's wording stays
            in the stored analysis and on GET /reports/:id/analysis, which is
            where someone debugging a bad unit needs it. */}
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
              {/* BOTH REFERENCES, WHEN THEY DISAGREE. The printed interval
                  the laboratory compared against, then the threshold this
                  tool applies. Neither is dropped and neither is presented
                  as the whole answer. */}
              {verdict.detail ? (
                <span className="verdict__detail">{verdict.detail}</span>
              ) : null}
              {verdict.secondary ? (
                <span className="verdict__secondary">{verdict.secondary}</span>
              ) : null}
            </>
          ) : (
            // No rule checked this value. Saying "in range" here would be a
            // finding nobody made.
            <>
              <span className="absent">not checked</span>
              {/* WHAT THE REPORT DID PRINT, WHEN IT IS NOT A RANGE.
                  ====================================================

                  `AVERAGE BLOOD GLUCOSE 154 mg/dL` carries
                  `"151 - 180 - Average Control"` -- one row of a glycaemic
                  CONTROL band table, not an interval of normality. The
                  extraction prompt names that exact string as text which is
                  not a range, and `printed_range_is_only_a_range` refuses it,
                  so the row has no bounds and nothing compared it.

                  ⚠ AND IT MUST NEVER BE PARSED AS ONE. 154 sits inside
                  151-180, so reading that band as a reference range would
                  print "In range" for an average glucose matching the HbA1c
                  of 7 % flagged HIGH two rows above -- 6bg finding 4 exactly,
                  a finding rendering as a reassurance. "Average Control"
                  means average control FOR SOMEONE WITH DIABETES.

                  SO THE TEXT IS QUOTED, ATTRIBUTED, AND DENIED. Verbatim and
                  in quotation marks because it is the report's wording and
                  the reader can find it on their own paper; attributed to the
                  report because this tool did not say it; and followed by
                  what it is not, because "Average" reads as reassurance to a
                  patient and the one thing this row may not do is imply a
                  normal result. "not checked" stays above it -- the absence
                  is still the verdict. */}
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
  // THREE COLUMNS, ALWAYS. The reference interval and the laboratory's flag
  // used to be columns of their own, appearing only when some row could fill
  // them -- so the same report rendered a three-column table or a five-column
  // one depending on what its laboratory chose to print. The ranges are in
  // "What these results mean" now, said once per test, where a range is a
  // sentence rather than a cell that is empty on most rows.
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
  // The report's printed sex and age against the profile the analysis used.
  // See `components/IdentityNotice`.
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
  // Rows the reader is shown: a value that is there, or one that was
  // taken and refused. `measuredLabs` itself is left whole -- it still
  // feeds `resultFeatures`, which stops a test being described twice.
  const reportedLabs = measuredLabs.filter(
    (row) => isPresent(row.value) || row.state === 'rejected'
  );

  // ---- ONE TABLE ---------------------------------------------------------
  //
  // The tests this tool does not assess used to sit in a second table under
  // their own heading, each row tagged "not assessed by this tool" and each
  // comparison footnoted "your laboratory's own range". On a real report that
  // was three rows above and eighteen below, and the reader asked for one
  // list -- a result is a result, and which engine formed an opinion about it
  // is this platform's business, not theirs.
  //
  // WHAT THAT FACT IS STILL WORTH IS KEPT, and moved to "What these results
  // mean", which is where a sentence can carry it. It has to be somewhere:
  // SGPT, CRP and ESR are markedly abnormal on this report and fed no verdict
  // at all, so a page implying the overall status weighed all twenty-one rows
  // would be claiming an assessment nobody made.
  const labFlagVerdict = (item) => {
    if (item.labFlaggedAbnormal === true && isPresent(item.labFlag)) {
      return { label: titleCase(item.labFlag), direction: item.labFlag };
    }
    // A laboratory that marked the row normal, or printed an interval the
    // value sits inside, has compared it -- and said it is not out.
    if (item.labFlag === 'normal' || isPresent(item.labReferenceLow)
        || isPresent(item.labReferenceHigh)) {
      return { label: 'In range', direction: 'normal' };
    }
    // NOTHING COMPARED IT. Falls through to the same "not checked" the
    // assessed rows show when no rule read them -- never to a blank cell,
    // which in a column headed "Compared with usual limits" reads as fine.
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
    // The printed text, for the rows nothing compared. See the band-label
    // note in `LabRow` -- it is quoted and denied, never parsed.
    referenceRangeRaw: item.labReferenceRangeRaw,
  }));
  // The laboratory's own abnormal markings lead: they are the reason these
  // rows are on the page at all.
  const allResultRows = [
    ...reportedLabs,
    ...unassessedRows.filter(
      (_, i) => unassessedItems[i].labFlaggedAbnormal === true
    ),
    ...unassessedRows.filter(
      (_, i) => unassessedItems[i].labFlaggedAbnormal !== true
    ),
  ];
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

  // The laboratory's own comparison, entered in the SAME map the assessed
  // rows read from, so one row component renders both and the column cannot
  // drift into two vocabularies. Set here rather than where the rows are
  // built, because `verdicts` does not exist until this line.
  unassessedItems.forEach((item, index) => {
    const verdict = labFlagVerdict(item);
    if (verdict) verdicts.set(`lab:${item.testName}:${index}`, verdict);
  });

  /* THE LABORATORY'S OWN COMPARISON, FOR ROWS NO RULE READ.
     ==================================================================

     "not checked" was correct and was reading as an absence of information
     the report does not actually have. On Test 3 it sat beside ELEVEN rows
     the laboratory had compared and printed an interval for:

         RBC COUNT   4.2  (3.8-5.8, normal)      NEUTROPHILS  82  (40-70, high)
         MCV        88.6  (80-97,   normal)      LYMPHOCYTES  14  (20-40, low)
         PLATELETS   303  (150-400, normal)      ...and five more

     The page had all of it and threw it away, because `valueVerdicts` only
     reads CLINICAL RULE EVIDENCE and this platform holds no rule for any
     complete-blood-count parameter. It holds rules for CONDITIONS -- Diabetes,
     Anemia -- and a CBC row contributes to none of them, so nothing ever
     looked at it. That is a fact about this tool's coverage, and the column
     was reporting it as a fact about the reader's blood.

     ⚠ AND IT CONTRADICTED THE SAME PAGE'S OWN SUMMARY. The clinician view
     names NEUTROPHILS 82 % (40-70, high) as outside its printed interval
     while the results table called the same row "not checked".

     THE JUSTIFICATION IS THE ONE ALREADY ACCEPTED DIRECTLY ABOVE. For the
     unassessed rows, `labFlagVerdict` reasons that a laboratory which printed
     an interval the value sits inside HAS compared it. That is equally true
     of a row that happens to have a canonical feature; whether this platform
     also holds a rule for it is our business, not the laboratory's. Applying
     one rule to both halves is what stops the column carrying two vocabularies
     -- which is the reason given for writing into this same map a few lines up.

     WHAT STILL SAYS "not checked", AND CORRECTLY: hemoglobin and haematocrit.
     Both print SEX-SPECIFIC intervals ("F:11 - 15 M:12 - 16") which do not
     parse to a single low/high, so `referenceLow`/`referenceHigh` really are
     absent and nothing has compared them. Haemoglobin still shows Low from
     the Anemia rule; PCV shows "not checked" because that is the truth.
     ⚠ PARSING A SEX-SPECIFIC PRINTED RANGE IS A SEPARATE, UNDONE JOB. */
  /* WHAT THE REPORT ITSELF SAYS ABOUT THIS ROW.
     ======================================================================

     ABNORMAL WHEN THE VALUE IS OUTSIDE THE PRINTED INTERVAL **OR** THE
     LABORATORY MARKED IT SO -- 6bg finding 4's rule, arriving on the second
     of the two code paths. The comparison leads because it is CHECKABLE from
     two numbers on the page, and the flag is kept as an OR so it is never
     discarded when the arithmetic disagrees. Fail-safe toward flagging. */
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

  /* TWO REFERENCES, AND THE ROW MAY NOT COLLAPSE THEM INTO ONE WORD.
     ======================================================================

     Haemoglobin 12.5 g/dl on `Test 3.pdf` is INSIDE the interval the report
     prints for a male reader (12-16) and BELOW the 13 g/dl this tool applies
     for anaemia. Both statements are true, they are about different
     references, and until the sex-specific interval parsed the row could only
     ever have shown one of them -- it showed "Low", the rule's, with nothing
     saying the laboratory's own range disagreed.

     WHEN THEY AGREE, NOTHING CHANGES and one word is right. When they
     disagree the row says both, and the owner chose that the laboratory's
     comparison leads: it is the one a clinician reads off the paper.

     ⚠ AND IT IS NOT STYLED AS CLEAR. `verdict--mixed` exists so that a row
     whose two references disagree cannot render in the reassuring green of a
     settled "In range" -- which is the shape of the worst defect this page
     has had. The disagreement is the finding. */
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

  // ---- chart data -------------------------------------------------------
  //
  // DERIVED HERE, NOT IN THE CHARTS. The chart components take a shape and a
  // state; they hold no threshold, no condition and no clinical rule, so a
  // change to what counts as flagged happens in exactly one place and cannot
  // make a picture disagree with the words beside it.
  //
  // Everything below reuses what this page ALREADY computed -- `verdicts`,
  // the grouped condition cards, `dashboard.overall` -- so nothing on screen
  // is counted twice or counted differently.

  // Declared before the radar, which reads it to work out how much of each
  // topic the report could actually speak to.
  const evidenceByCondition = new Map(
    (dashboard.evidence?.conditions || []).map((item) => [item.condition, item])
  );

  /**
   * The radar's five topics, most-serious first.
   *
   * COVERAGE IS WHAT THE TITLE SAYS IT IS: of the inputs this assessment
   * cites, how many the report actually carried. Diabetes cites eight and five
   * were available; Heart Disease the same; a single-threshold topic like High
   * Cholesterol cites one and has it.
   *
   * IT USED TO BE THE VERDICT -- `isClear(card) ? 0.55 : 0.95` -- and that made
   * the chart say the opposite of its own title. A flagged topic sat at the
   * rim, so a report with everything abnormal drew a full pentagon under the
   * word "Coverage", and a full shape reads as thorough and reassuring. The
   * radius now says how completely each topic could be examined, which is the
   * one question the condition cards below do NOT answer.
   *
   * A topic whose coverage cannot be computed is left OFF the chart rather
   * than given a radius. There is no number for "we do not know how much we
   * saw", and inventing one is the failure this whole screen exists to
   * prevent; the card below still reports the topic in full.
   */
  const coverageFor = (condition) => {
    const lines = evidenceByCondition.get(condition)?.lines || [];
    // ONE ENTRY PER FEATURE: two rules citing the same input is one input, and
    // the same value counted twice would inflate the coverage of exactly the
    // topics that have several rules. A feature counts as available if ANY of
    // its lines observed it -- an input the assessment had is an input it had,
    // and "first line wins" would have made that an accident of ordering.
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
      // An unassessed topic keeps its spoke and its dashed point at zero --
      // that is the chart's whole reason for existing. An ASSESSED topic with
      // no citable inputs has no coverage to draw and is dropped.
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
  // Only conditions this report actually flagged. `flagged` is the dashboard's
  // own predicate, so guidance can never claim a finding the cards do not show.
  const flaggedConditions = new Set(
    (dashboard.conditions || [])
      .filter((card) => card.flagged === true)
      .map((card) => card.condition)
  );
  const guidance = groupGuidance(recommendations.guidance?.items, flaggedConditions);
  const sharedBecause = sharedBecausePhrase(guidance.relevant);

  return (
    <main className="dashboard">
      {/* THE FILENAME IS THE PAGE TITLE, not a breadcrumb tail. Two rows of
          identical underlined links read as a list of four equal things, none
          of which is the heading -- so the trail is mono micro-type, the file
          is set as the title it actually is, and the two cross-links become
          affordances you can see the edges of. */}
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to="/reports">Reports</Link>
        <span aria-hidden="true">/</span>
        <span className="crumbs__here">{report?.originalName || 'This report'}</span>
      </nav>

      <div className="page-links">
        <Link className="page-link" to={`/reports/${id}/doctor-summary`}>
          Summary for a clinician
        </Link>
        <Link className="page-link" to={`/reports/${id}/population`}>
          How your results compare
        </Link>
      </div>

      {/* ABOVE THE VERDICT, because it qualifies it: a verdict judged with the
          wrong sex's thresholds is only as good as the profile it used. */}
      <ProfileIdentityNotice identity={identity} />

      <OverallCard overall={dashboard.overall} />

      {/* THE CHARTS SAY THE SAME THINGS THE CARDS BELOW SAY, in the one
          register a reader takes in at a glance. Every number is drawn against
          the thing it was compared to, because the platform's claim is that
          its decisions are evidenced -- and a bare 8.4 evidences nothing. */}
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

      {clearCards.length ? (
        <>
          <h2>Everything else that was checked</h2>
          {clearCards.length ? (
            <div className="roundup">
              {/* "CONDITIONS", NOT "TOPICS". `topic` is this project's
                  INTERNAL word for an entry in the fixed catalogue the rule
                  engine walks, and it leaked onto the reader's screen in four
                  places while the same page called them conditions in two
                  others -- "This tool checked 8 conditions" in the closing
                  summary, "No conditions were assessed" in the empty state.
                  A reader has no idea the two words mean the same thing, and
                  "topic" says nothing about what is being checked. */}
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
          {/* REMOVED ON THE READER'S INSTRUCTION, AND THEY HAD TO ASK MORE
              THAN ONCE. A group of dashed NOT CHECKED chips stood here for
              the topics with no test on the report, with a line underneath
              saying an unchecked topic is an open question rather than a
              negative result. The same fact was also on the Overall card and
              in the closing summary; all three are gone.

              It only ever rendered because b4d14ad made the rule engine emit
              those topics at all -- before that they were dropped in silence
              and this group had never had data. The engine still emits them
              and `overall.unassessedConditions` still names them, so the
              clinician summary and every other consumer are unchanged. This
              screen does not show them. */}
        </>
      ) : null}

      {!dashboard.conditions?.length ? (
        <p className="empty">No conditions were assessed for this report.</p>
      ) : null}

      <h2>Your results</h2>
      {/* A TEST THAT WAS NEVER ON THE REPORT GETS NO ROW.
          Four of eleven rows here said "Not measured -- this value was not
          found in the submitted report", which is a row per test the pipeline
          hoped for and a table that is mostly about what is not in front of
          you. The absence is still reported, in the places that can say
          something useful about it: the condition card names the input it
          could not take into account.

          A REJECTED READING IS NOT AN ABSENT ONE AND KEEPS ITS ROW. It was
          printed on the report and this tool refused it, which the reader has
          to be told -- dropping it would let a value that exists disappear
          without a word. So the test is "has a value, or had one taken and
          refused", never `usable`. */}
      {allResultRows.length ? (
        <LabTable rows={allResultRows} verdicts={verdicts} />
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
          {/* THE WHOLE GROUP BEHIND ONE DISCLOSURE, not one per row.
              These items are a line each and reading them as a set is the
              point -- six separate toggles for six short lines is more
              chrome than content. The count is in the summary so the reader
              knows the size of what they are opening.

              NOTHING HERE IS AN ABSENCE, which is why the whole section may
              close. It is general educational material matched to a flag,
              and the qualifier that says so travels INSIDE with the items it
              qualifies -- it has nothing to qualify while the group is shut.
              The explanations above are the opposite case and are treated as
              such. */}
          <details className="disclosure disclosure--section">
            <summary className="disclosure__summary">
              <h2>Topics you could read about</h2>
              {/* THE COUNT BELONGS TO THE HEADING, so it sits against it.
                  It was reading as a stray number: the heading was `flex: 1`
                  and stretched to 672px, parking the badge 680px away at the
                  far right beside the chevron, where it looked like a second
                  control rather than "there are three of these". The spacer
                  does the pushing now. */}
              <span className="disclosure__count">
                {guidance.relevant.length}
              </span>
              <span className="disclosure__spacer" />
              <span className="disclosure__chevron" aria-hidden="true" />
            </summary>
            {/* THE OPENED CONTENT NEEDS AN EDGE. Revealed straight onto the
                page ground it had no boundary, so the reader could not tell
                where the disclosure ended and the next section began -- the
                closing qualifier in particular read as page text that
                happened to follow. One panel holds the attribution, the
                topics and the qualifier: opening the toggle produces ONE
                object, not three loose paragraphs. */}
            <div className="disclosure__body">
          {/* ONE ATTRIBUTION ABOVE THE LIST WHEN IT IS THE SAME ONE.
              Three bullets each ending "Related to: Obesity." is the same
              sentence three times. Hoisted only when every item's set is
              identical (see `sharedBecausePhrase`) -- otherwise each keeps its
              own, because a single line that is true of most bullets is FALSE
              of the rest, and false here means naming a condition at a reader
              whose bullet had nothing to do with it. */}
          {sharedBecause ? (
            <p className="guidance__shared">
              Shown because this report flagged {sharedBecause}.
            </p>
          ) : null}
          <ul className="guidance bullets">
            {guidance.relevant.map((item, index) => (
              <li key={item.code || index}>
                <span className="guidance__text">
                  {trimGeneralPrefix(item.text || item.title)}
                </span>
                {!sharedBecause && becausePhrase(item) ? (
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
            </div>
          </details>
        </>
      ) : null}

      {/* "WORTH KNOWING ABOUT THIS ANALYSIS" IS GONE FROM THIS PAGE.
          It printed the pipeline's own stage warnings at a patient:
          "'25-Hydroxy Vitamin D' reported unit 'ng/dL', which is not a
          recognised unit for feature 'vitamin_d' (canonical: 'ng/ml'). The
          value was left unconverted and flagged canonical_unit=false." That is
          a bug report. A patient cannot act on a field name, a canonical unit
          or a boolean flag, and the facts they CAN act on are already on the
          page in their own words -- a value that could not be used says so on
          its own row, an unreadable page is stated in the summary, and a stage
          that failed is stated there too.
          NOT DELETED, RELOCATED: every warning is still in the stored analysis
          and on GET /reports/:id/analysis, which is where a maintainer looks.
          `readerWarnings` and its methodology filter went with the section --
          a filter whose only consumer is gone is a branch nobody can reach. */}

      {/* THE "Also on your report, but not assessed here" SECTION IS GONE.
          Everything it carried now sits where the reader already is: the
          values and the laboratory's own ranges in "Your results", the
          descriptions in "What these results mean", both as labelled groups
          of their own. Keeping the section as well would print every one of
          these parameters TWICE on one page -- the repetition this screen has
          spent a whole session removing. Its safety sentence ("not checked is
          not the same as normal") moved to the results group's header, which
          is the first place a reader meets these rows. */}

      {/* LAST, deliberately. The numbers and what was flagged come first --
          that is what the reader opened the page for. The long-form
          explanation is the thing you read once you know which result you
          care about, so it sits at the end rather than pushing the findings
          below the fold. */}
      <Explanations
        explanations={recommendations.explanations}
        /* The features this page shows as RESULTS, so a skipped profile answer
           (age, sex, BMI) is not announced as a missing explanation. */
        resultFeatures={new Set(measuredLabs.map((row) => row.feature))}
        /* The tests on the report this tool has no feature for. Counted off
           the items list, not `unanalysed.count` -- §6u: `unmapped_count` said
           0 on a report with 63 of them, and the dashboard repeated it. */
        unassessedCount={(dashboard.unanalysed?.items || []).length}
        assessedResultCount={reportedLabs.length}
        unassessedItems={dashboard.unanalysed?.items || []}
      />

      {/* THE LAST THING ON THE PAGE, and the only place the whole report is
          said in one breath. It comes after the detail rather than before it
          because it is a recap, not a headline -- the card at the top already
          carries the verdict, and a summary that appeared first would be read
          INSTEAD OF the findings rather than after them.

          The grouped card arrays are handed down rather than recomputed, so
          the sentence "5 need a closer look" is counting the same five cards
          the reader just scrolled past. Two independent counts of one thing
          is two things to get wrong. */}
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
