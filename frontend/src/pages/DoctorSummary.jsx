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
  const [findingContext, setFindingContext] = useState([]);

  useEffect(() => {
    let cancelled = false;
    // A LOCAL FLAG, NOT THE `data` STATE. The catch below runs inside the
    // closure this effect was created in, where `data` is null for the whole
    // life of the effect however many times `setData` has been called -- so
    // reading it would make every context failure replace a rendered summary
    // with an error page. A test caught exactly that.
    let summaryRendered = false;
    (async () => {
      try {
        const result = await api.getDoctorSummary(id);
        if (cancelled) return;
        setData(result);
        summaryRendered = true;

        /* MODULE 34 -- what the values the LABORATORY marked are generally
           associated with.
           DERIVED FROM `printed_flag`, which is the reporting laboratory's own
           marking and the only direction on this page that is not this tool's
           own verdict. Profile rows are excluded upstream by `measured`'s own
           filter, so a questionnaire answer can never reach it. The request
           carries a printed NAME and the word raised/lowered; no value goes
           with it, which is what keeps the answer about the test.
           IT LIVES IN THIS EFFECT because `labFlagged` is computed after the
           early returns below, and a second hook cannot follow them. */
        const rows = result?.doctorSummary?.laboratory?.rows || [];
        const direction = (word) => {
          const w = String(word || '').toLowerCase();
          if (w.includes('high') || w.includes('raised')) return 'raised';
          if (w.includes('low') || w.includes('lowered')) return 'lowered';
          return null;
        };
        const findings = [];
        for (const row of rows) {
          if (row?.provenance?.source === 'patient_profile') continue;
          if (row?.usable === false) continue;
          const d = direction(row?.printed_flag);
          if (!d) continue;
          const name = parameterName(row);
          if (name) findings.push({ test_name: name, direction: d });
        }
        if (!findings.length) return;

        const ctx = await api.describeFindings(id, findings);
        const entries = (ctx?.context?.entries || []).filter(
          (e) => e && e.available === true && typeof e.text === 'string' && e.text.trim()
        );
        if (!cancelled && entries.length) setFindingContext(entries);
      } catch (err) {
        // ONLY THE SUMMARY ITSELF IS AN ERROR. A missing context block is not
        // something a clinician has any use for being told about, and the
        // document is complete without it -- so a failure after `setData` must
        // not replace a rendered summary with an error.
        if (!cancelled && !summaryRendered) setError(err.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (error) return <p className="error" role="alert">{error}</p>;
  if (!data) return <p className="loading">Preparing the clinical summary…</p>;

  const summary = data.doctorSummary || {};
  // WHAT THE LABORATORY REPORTED AND THIS PLATFORM DOES NOT ASSESS.
  // `count: 0` is an ordinary answer and is rendered as nothing; the section
  // is never absent from the payload, so "none" and "not computed" stay
  // distinguishable here rather than collapsing into one blank space.
  const unassessed = data.unassessed || null;
  const narrative = data.narrative || null;
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

      {/* THE WRITTEN VERSION, WHEN THERE IS ONE.
          `narrative.text` is non-null only after the ai-service generated it,
          Module 24 approved it, AND every required fact was verified present
          in the output (app/services/clinician_narrative.py). Any one of those
          failing sends `text: null`, and the composed passage below is what
          renders -- which is what this page has always shown, so the worst
          case of the whole feature is today's document.
          BRANCHED ON `text`, NEVER ON `narrative` BEING TRUTHY: a refusal is
          an object with an outcome and no text, and `{narrative && ...}` would
          render an empty article. */}
      {isPresent(narrative?.text) ? (
        <article className="passage">
          {narrative.text
            /* A DOUBLE SPACE AFTER A FULL STOP IS A PARAGRAPH BREAK TOO.
               The model groups its sentences that way and not with blank
               lines, however the prompt asks -- so the whole note arrived as
               one ten-line block. This reflows already-approved text and
               changes not one character of it; the alternative was another
               round of prompt-tuning at a model call each. */
            .replace(/\.\s{2,}/g, '.\n\n')
            .split(/\n\s*\n/)
            .map((para) => para.trim())
            .filter(Boolean)
            .map((para, index) => (
              <p key={index}>{para}</p>
            ))}
          {/* SAID, NOT IMPLIED. The reader is entitled to know a model wrote
              the prose -- the findings in it were not decided by one, and the
              distinction is the whole reason the composed version existed. */}
          <p className="passage__close">
            The wording above was written by a language model from the findings
            of this analysis and checked before being shown. The findings
            themselves were not produced by a language model.
          </p>

          {/* MODEL PERFORMANCE, OUT OF THE PROSE AND STILL REACHABLE.
              These figures used to be two paragraphs in the middle of the
              note. A clinician reading a handover is not reading a model
              card, so they sit here, collapsed, instead -- but §6w's rule
              holds: a model-derived flag must never reach a reader with no
              way to see what produced it. Derived once, in the service; this
              only renders what it is given. */}
          {narrative.model_notes?.length ? (
            <details className="passage__models">
              <summary>Model performance for the flags above</summary>
              {narrative.model_notes.map((note, index) => (
                <p key={index}>{note}</p>
              ))}
            </details>
          ) : null}
        </article>
      ) : (
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
            different claims, and one real report contains one of each.
            SAID AS A CLINICIAN WOULD SAY IT. "Threshold comparison against the
            platform's configured cut-offs" is how this system describes its
            own components; the reader is a clinician, and the thing they need
            is which KIND of check fired, in ordinary clinical words. */}
        {flagged.length ? (
          <p>
            <strong>Flagged.</strong>{' '}
            {byBoth.length
              ? `${nameList(byBoth)} ${
                  byBoth.length === 1 ? 'was' : 'were'
                } flagged two ways: a measured value crossed one of this tool's cut-offs, and the statistical model agreed. `
              : ''}
            {byRule.length
              ? `${nameList(byRule)} ${
                  byRule.length === 1 ? 'was' : 'were'
                } flagged because a measured value crossed one of this tool's cut-offs. `
              : ''}
            {byModel.length
              ? `${nameList(byModel)} ${
                  byModel.length === 1 ? 'was' : 'were'
                } flagged by the statistical model alone — no measured value crossed a cut-off for ${
                  byModel.length === 1 ? 'it' : 'them'
                }. `
              : ''}
          </p>
        ) : (
          <p>
            <strong>Flagged.</strong> No measured value crossed a cut-off, and
            the statistical model flagged nothing.
          </p>
        )}

        {/* ONE SENTENCE OF MODEL LIMITATION, in the model author's own words.
            Found missing from this page three separate times.

            THE LEAD-IN IS WRITTEN FOR THE READER THIS PAGE IS ADDRESSED TO.
            "A likelihood derived from patterns in training data" is how the
            people who build these things describe them; a clinician is not
            obliged to know it, and this is the sentence that decides how much
            weight they give everything after it. The notes that follow were
            rewritten at source for the same reason (app/ml/heart.py,
            app/ml/kidney.py) -- every fact kept, the vocabulary of model
            development dropped. */}
        {byBoth.length + byModel.length > 0 ? (
          <p>
            <strong>On the model output.</strong> A model estimate is a
            comparison against patterns in past data, not a measurement of this
            patient, and it is not a statement that a condition is present.
            {modelNotes.length ? ` ${modelNotes.join(' ')}` : ''}
          </p>
        ) : null}

        {/* Assessed and not flagged, named -- a clinician needs to know which
            topics were covered, and "not flagged" is not "ruled out". */}
        {clear.length ? (
          <p>
            <strong>Assessed, not flagged.</strong>{' '}
            {nameList(clear.map((a) => a.condition))}. Each was compared
            against this tool&rsquo;s cut-offs and none was crossed.
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

        {/* WHAT THE LABORATORY'S OWN MARKINGS ARE GENERALLY ASSOCIATED WITH.
            Above the closing line, which keeps the last word, and outside
            everything the narrative may rewrite. Each sentence is about the
            TEST and the DIRECTION -- the same sentence for any report with a
            raised neutrophil count -- so it carries no attribution: there is
            no claim about this patient in it to attribute. */}
        {findingContext.length ? (
          <div className="passage__context">
            {findingContext.map((entry, index) => (
              <p key={`${entry.test_name}-${index}`}>
                <strong>
                  {entry.test_name}
                  {entry.direction === 'raised' ? ' (raised)' : ' (lowered)'}
                </strong>{' '}
                {entry.text}
              </p>
            ))}
          </div>
        ) : null}

        {/* THE PARAMETERS THIS PLATFORM DOES NOT ASSESS, WITH THEIR VALUES.
            The paragraphs above state how many; a clinician needs to read
            them. These are the laboratory's own values, units, flags and
            printed intervals, carried forward untouched -- this tool asserts
            nothing about any of them, which is exactly why they are here
            rather than in the assessed table.

            No descriptions. The patient page explains what ESR measures;
            this reader knows. */}
        {unassessed && unassessed.count > 0 ? (
          <div className="passage__unassessed">
            <h3>
              Reported, not assessed by this tool ({unassessed.count})
            </h3>
            <p>
              Read from the document and set aside because no assessment rule
              here covers them &mdash; <strong>not</strong> found normal. Values,
              units and flags are the laboratory&rsquo;s own.
            </p>
            <table className="lab-table">
              <caption className="visually-hidden">
                Parameters reported by the laboratory that this tool does not
                assess
              </caption>
              <thead>
                <tr>
                  <th scope="col">Parameter</th>
                  <th scope="col">Value</th>
                  <th scope="col">Reference</th>
                  <th scope="col">Lab flag</th>
                </tr>
              </thead>
              <tbody>
                {unassessed.items.map((item, index) => (
                  <tr key={`${item.testName}-${index}`}>
                    <th scope="row">{item.testName}</th>
                    <td>
                      {item.value}
                      {item.unit ? ` ${item.unit}` : ''}
                    </td>
                    <td>
                      {item.labReferenceLow !== undefined &&
                      item.labReferenceHigh !== undefined
                        ? `${item.labReferenceLow}–${item.labReferenceHigh}`
                        : item.labReferenceHigh !== undefined
                          ? `≤ ${item.labReferenceHigh}`
                          : item.labReferenceLow !== undefined
                            ? `≥ ${item.labReferenceLow}`
                            : '—'}
                    </td>
                    <td>
                      {/* THE LABORATORY'S VERDICT, NAMED AS THEIRS. This tool
                          has no opinion on these rows and must not appear to. */}
                      {item.labFlag ? item.labFlag : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        <p className="passage__close">
          Not a diagnosis and not a clinical conclusion. The original laboratory
          report remains the primary record.
        </p>
      </article>
      )}
    </main>
  );
}
