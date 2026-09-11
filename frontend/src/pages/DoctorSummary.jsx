import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../lib/api';
import { isPresent } from '../lib/absence';

/**
 * Module 32 -- the summary a patient hands to a clinician, as ONE PASSAGE.
 *
 * ==========================================================================
 * WHAT THIS PAGE IS NOW, AND WHY
 * ==========================================================================
 *
 * It was a structured document: purpose statement, scope bullets, a card per
 * condition, a source legend, retrieved reference passages, a data-quality
 * block, a provenance block. Every part was accurate and the whole was
 * unreadable -- and most of it was the page talking about ITSELF rather than
 * about the report. A clinician handed a patient's phone for thirty seconds
 * does not read a document that explains its own architecture first.
 *
 * So it is a handover note. Values, what was flagged and on what basis, what
 * was not available, one line to close. The register is professional: a
 * clinician reads `HbA1c 8.4 %` and does not need it translated.
 *
 * ==========================================================================
 * THE PASSAGE IS COMPOSED. NO LANGUAGE MODEL WRITES IT.
 * ==========================================================================
 *
 * "Summarise these results for a doctor" is one prompt away and would be the
 * worst possible use of one: a clinical narrative with no rule, no threshold
 * and no evidence chain behind it, in a register that invites action. The
 * service also publishes `integrity.llm_calls_made: 0` and
 * `model_generated_text_included: false` ABOUT THIS VERY DOCUMENT, so
 * generating the prose here would make both of those claims false. Every
 * sentence below is assembled from a decision some stage already made.
 *
 * ==========================================================================
 * WHAT WAS CUT, AND THE FOUR THINGS THAT WERE NOT
 * ==========================================================================
 *
 * Cut: the scope bullets, the source legend, "how this document was
 * produced", the retrieved reference passages, rule identifiers, ROC-AUC and
 * the rest of the metrics table, and every source-file path. None of it told
 * a clinician anything about this patient.
 *
 * KEPT, because removing them would make the passage lie by omission:
 *
 *   1. WHICH KIND OF CHECK FLAGGED WHAT. A topic flagged by a threshold
 *      comparison and a topic flagged only by a statistical model are not the
 *      same claim, and on one real report they differ: creatinine 1.1 mg/dL
 *      does NOT cross the kidney rule and the model flagged it anyway. A
 *      clinician told "kidney disease flagged" without that is being told
 *      something the analysis did not find.
 *
 *   2. ONE SENTENCE OF MODEL LIMITATION wherever a model contributed to a
 *      flag. The heart model's own author note reads "most patients it flags
 *      will NOT have heart disease -- a high score is a reason to discuss
 *      testing with a clinician, never a finding." A probability printed
 *      without that has been found and re-found on this project three times.
 *
 *   3. WHAT WAS NOT AVAILABLE. Fields not supplied, parameters the report did
 *      not carry, pages that could not be read. Absence is not a negative
 *      result -- the rule the whole codebase is built on, and the one a
 *      compressed summary is most likely to drop.
 *
 *   4. ONE CLOSING LINE. Not the ten-sentence scope statement; one line
 *      saying this is not a diagnosis and the original report is the record.
 */

/* ------------------------------------------------------------------ utils */

/** Join without merging names that contain their own commas. */
const nameList = (names) =>
  names.join(names.some((name) => String(name).includes(',')) ? '; ' : ', ');

const humanFeature = (key) => String(key).replace(/_/g, ' ');

/** First letter capitalised, for a list that opens a sentence. */
const sentenceCase = (text) =>
  text.length ? text[0].toUpperCase() + text.slice(1) : text;

/** `2026-09-07T04:00:14Z` -> `7 September 2026`, or null if unparseable. */
function readableDate(value) {
  if (typeof value !== 'string' || value === '') return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });
}

/**
 * The name a clinician will find on the paper report, falling back to ours.
 *
 * They are reading this beside the original, so matching on the printed
 * wording is what they actually do. A row whose transcription the safety
 * scanner withheld has no printed text and falls back silently -- the value
 * is what matters and it is unaffected.
 */
function parameterName(row) {
  const printed = row.provenance?.original_test_name;
  if (row.provenance?.source === 'lab_report' && isPresent(printed?.text)) {
    return printed.text;
  }
  return row.display_name || row.feature;
}

/**
 * Which kinds of source flagged this topic.
 *
 * A `Not Indicated` from one source beside an `Indicated` from another is the
 * single most informative thing on this page, so the two are counted
 * separately rather than collapsed into "flagged".
 */
function flaggingKinds(assessment) {
  const kinds = new Set();
  for (const basis of assessment.bases || []) {
    if (basis.status === 'Not Indicated' || basis.assessed === false) continue;
    kinds.add(basis.source_kind === 'machine_learning' ? 'model' : 'rule');
  }
  return kinds;
}

/* -------------------------------------------------------------------- page */

export default function DoctorSummary() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const result = await api.getDoctorSummary(id);
        if (!cancelled) setData(result);
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (error) return <p className="error" role="alert">{error}</p>;
  if (!data) return <p className="loading">Preparing the clinical summary…</p>;

  const summary = data.doctorSummary || {};
  const patient = summary.patient || {};
  const laboratory = summary.laboratory || {};
  const quality = summary.data_quality || {};
  const rows = laboratory.rows || [];
  const assessments = summary.assessments || [];

  // ---- subject line -------------------------------------------------------
  const context = [];
  if (isPresent(patient.age)) context.push(`${patient.age}-year-old`);
  if (isPresent(patient.gender)) context.push(String(patient.gender));
  const subject = context.join(' ');
  const notSupplied = ['hypertension', 'heart_disease', 'smoking_history'].filter(
    (key) => !isPresent(patient[key])
  );

  // ---- values -------------------------------------------------------------
  const measured = rows.filter(
    (row) => row.provenance?.source !== 'patient_profile' && row.usable !== false
  );
  const rejected = rows.filter((row) => row.usable === false);
  const anyInterval = measured.some(
    (row) => isPresent(row.reference_low) || isPresent(row.reference_high)
  );
  const labFlagged = measured.filter((row) => isPresent(row.printed_flag));

  // ---- findings, split by WHAT flagged them -------------------------------
  const abnormal = new Set(summary.abnormal_findings || []);
  const flagged = assessments.filter(
    (a) => abnormal.has(a.condition) || (a.assessed !== false && a.status !== 'Not Indicated')
  );
  const byBoth = [];
  const byRule = [];
  const byModel = [];
  for (const assessment of flagged) {
    const kinds = flaggingKinds(assessment);
    const entry = `${assessment.condition}${
      isPresent(assessment.status) && assessment.status !== 'Indicated'
        ? ` (${String(assessment.status).toLowerCase()})`
        : ''
    }`;
    if (kinds.has('rule') && kinds.has('model')) byBoth.push(entry);
    else if (kinds.has('model')) byModel.push(entry);
    else byRule.push(entry);
  }
  const clear = assessments.filter((a) => !flagged.includes(a));

  // The model's own statement of its limits, deduplicated -- one sentence per
  // distinct note, however many topics a model contributed to.
  // ONLY FROM A MODEL THAT ACTUALLY FLAGGED. A note qualifies an output, and
  // a model that returned `Not Indicated` produced no output this passage
  // reports -- its caveat would sit under findings it did not make. On one
  // real report that printed the heart model's four-sentence note beside a
  // Heart Disease flag the heart model had DISAGREED with.
  const modelNotes = [];
  for (const assessment of flagged) {
    for (const basis of assessment.bases || []) {
      if (basis.status === 'Not Indicated' || basis.assessed === false) continue;
      const note = basis.ml?.limitations?.author_note?.text;
      if (isPresent(note) && !modelNotes.includes(note)) modelNotes.push(note);
    }
  }

  // THE SAME THREE FIELDS WERE BEING NAMED TWICE -- once as "not supplied"
  // and again as "not present in this report". For hypertension, heart
  // disease and smoking history those are the same three names, so a reader
  // saw the list, read a paragraph, and saw it again. They are different
  // facts and only one of them needs saying: a field the patient never
  // supplied cannot also be a parameter the report failed to carry.
  const alsoMissing = (laboratory.features_not_present || []).filter(
    (key) => !notSupplied.includes(key)
  );

  const unreadable = quality.pages_unreadable || [];
  const reportDate = readableDate(summary.attribution?.report_date);

  return (
    <main className="doctor-summary">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to={`/reports/${id}`}>Dashboard</Link>
        <span aria-hidden="true">/</span>
        <span className="crumbs__here">Clinical summary</span>
      </nav>

      <h1>Summary for a healthcare professional</h1>

      <article className="passage">
        {/* Subject, context, and what the analysis did not have. */}
        <p>
          {subject ? `${subject}. ` : ''}
          {isPresent(patient.bmi) ? `BMI ${patient.bmi} kg/m². ` : ''}
          Single laboratory report
          {isPresent(quality.page_count)
            ? `, ${quality.page_count} page${quality.page_count === 1 ? '' : 's'}`
            : ''}
          {reportDate ? `, analysed ${reportDate}` : ''}.
          {notSupplied.length
            ? ` ${sentenceCase(nameList(notSupplied.map(humanFeature)))} ${
                notSupplied.length === 1 ? 'was' : 'were'
              } not supplied and unavailable to the analysis.`
            : ''}
        </p>

        {/* The values, in the wording printed on the report they came from. */}
        {measured.length ? (
          <p>
            <strong>Reported values.</strong>{' '}
            {measured
              .map((row) => {
                const value = `${row.value}${isPresent(row.unit) ? ` ${row.unit}` : ''}`;
                const flag = isPresent(row.printed_flag)
                  ? ` (${row.printed_flag}, per the reporting laboratory)`
                  : '';
                return `${parameterName(row)} ${value}${flag}`;
              })
              .join('; ')}
            .
            {/* AN ABSENT INTERVAL IS NOT AN UNREMARKABLE ONE, and this is the
                one sentence that stops eight bare numbers reading as in range. */}
            {!anyInterval
              ? ' The source report printed no reference intervals, so no value here is placed relative to a range.'
              : ''}
            {anyInterval && !labFlagged.length
              ? ' The reporting laboratory marked none of these outside its own intervals.'
              : ''}
          </p>
        ) : null}

        {rejected.length ? (
          <p>
            <strong>Not used.</strong> {nameList(rejected.map(parameterName))} did
            not pass validation and {rejected.length === 1 ? 'was' : 'were'}{' '}
            excluded from the analysis below.
          </p>
        ) : null}

        {/* WHAT WAS FLAGGED, AND BY WHAT. The three groups are the point of
            this paragraph: a threshold crossing and a model estimate are
            different claims, and one real report contains one of each. */}
        {flagged.length ? (
          <p>
            <strong>Flagged.</strong>{' '}
            {byBoth.length
              ? `Threshold comparison and the statistical model both flagged ${nameList(
                  byBoth
                )}. `
              : ''}
            {byRule.length
              ? `Threshold comparison against the platform's configured cut-offs flagged ${nameList(
                  byRule
                )}. `
              : ''}
            {byModel.length
              ? `${nameList(byModel)} ${
                  byModel.length === 1 ? 'was' : 'were'
                } flagged by the statistical model only — no measured value crossed a configured threshold for ${
                  byModel.length === 1 ? 'it' : 'them'
                }. `
              : ''}
          </p>
        ) : (
          <p>
            <strong>Flagged.</strong> No topic crossed a configured threshold and
            no model flagged one.
          </p>
        )}

        {/* ONE SENTENCE OF MODEL LIMITATION, in the model author's own words.
            Found missing from this page three separate times. */}
        {byBoth.length + byModel.length > 0 ? (
          <p>
            <strong>On the model output.</strong> A model estimate is a
            likelihood derived from patterns in training data, not a
            measurement, and it is not a statement that a condition is present.
            {modelNotes.length ? ` ${modelNotes.join(' ')}` : ''}
          </p>
        ) : null}

        {/* Assessed and not flagged, named -- a clinician needs to know which
            topics were covered, and "not flagged" is not "ruled out". */}
        {clear.length ? (
          <p>
            <strong>Assessed, not flagged.</strong>{' '}
            {nameList(clear.map((a) => a.condition))}. Each was compared against
            the platform&rsquo;s configured thresholds and none was crossed.
          </p>
        ) : null}

        {/* ABSENCE, WHICH A COMPRESSED SUMMARY IS MOST LIKELY TO DROP. */}
        {summary.unassessed_conditions?.length ||
        alsoMissing.length ||
        unreadable.length ||
        quality.partial_document === true ||
        quality.sources_failed?.length ? (
          <p>
            <strong>Not assessed.</strong>{' '}
            {summary.unassessed_conditions?.length
              ? `${nameList(
                  summary.unassessed_conditions
                )} could not be assessed; the required inputs were not available. `
              : ''}
            {alsoMissing.length
              ? `${sentenceCase(nameList(alsoMissing.map(humanFeature)))} ${
                  alsoMissing.length === 1 ? 'was' : 'were'
                } not present in this report. `
              : ''}
            {unreadable.length || quality.partial_document === true
              ? `Part of the document could not be read${
                  unreadable.length
                    ? ` (page${unreadable.length === 1 ? '' : 's'} ${unreadable.join(', ')})`
                    : ''
                }, so a parameter missing above may be missing from the reading rather than from the report. `
              : ''}
            {quality.sources_failed?.length
              ? `${nameList(quality.sources_failed)} did not complete. `
              : ''}
            None of this is a negative finding.
          </p>
        ) : null}

        <p className="passage__close">
          Not a diagnosis and not a clinical conclusion. The original laboratory
          report remains the primary record.
        </p>
      </article>
    </main>
  );
}
