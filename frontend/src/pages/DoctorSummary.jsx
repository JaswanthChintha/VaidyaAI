import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../lib/api';
import { isPresent } from '../lib/absence';
import { isPatientDetail } from '../lib/sources';

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

/**
 * The sentence the written narrative closes on.
 *
 * ⚠ THIS IS A COPY OF `CLOSING_LINE` IN
 * ai-service/app/services/clinician_narrative.py, WHICH IS THE OWNER OF THE
 * WORDING. It is appended there after approval and is never written by the
 * model. Duplicated here only so this page can tell that paragraph apart from
 * the model's own prose; a mismatch degrades to leaving it in place, never to
 * dropping it. Pinned by a test so the copy cannot drift unnoticed.
 */
const NARRATIVE_CLOSING_LINE =
  'Not a diagnosis and not a clinical conclusion. The original laboratory '
  + 'report remains the primary record.';

/**
 * The narrative split into paragraphs.
 *
 * A DOUBLE SPACE AFTER A FULL STOP IS A PARAGRAPH BREAK TOO. The model groups
 * its sentences that way and not with blank lines, however the prompt asks --
 * so the whole note arrived as one ten-line block. This reflows already
 * approved text and changes not one character of it; the alternative was
 * another round of prompt-tuning at a model call each.
 */
function narrativeParagraphs(text) {
  return String(text || '')
    .replace(/\.\s{2,}/g, '.\n\n')
    .split(/\n\s*\n/)
    .map((para) => para.trim())
    .filter(Boolean);
}

/** The narrative WITHOUT its closing line, which the page re-renders last. */
function narrativeBody(text) {
  const paragraphs = narrativeParagraphs(text);
  const last = paragraphs[paragraphs.length - 1];
  return last === NARRATIVE_CLOSING_LINE ? paragraphs.slice(0, -1) : paragraphs;
}

/** The closing line, only when it was recognised and lifted out. */
function narrativeClosing(text) {
  const paragraphs = narrativeParagraphs(text);
  const last = paragraphs[paragraphs.length - 1];
  return last === NARRATIVE_CLOSING_LINE ? last : null;
}

/**
 * Has the written narrative already listed EVERY reported value?
 *
 * ⚠ TWO IDENTICAL VALUE LISTS, FOUR PARAGRAPHS APART. This is 6bf's
 * out-of-range defect in a second place, and this page produced it the day
 * the reported values were made to render in both branches.
 *
 * THE NARRATIVE LISTS THEM ONLY SOMETIMES, WHICH IS WHY NEITHER SIDE COULD
 * SIMPLY BE DELETED. `required_values` is `trigger_values` -- the values that
 * crossed a threshold -- so the full panel is asked for in the prompt but
 * never enforced by the fact check. One report gets a "The reported values
 * are ..." sentence and the next does not, from identical code. Dropping this
 * page's list loses the values on the reports where the model omits them,
 * which is the defect it was added to fix; dropping the narrative's would
 * mean editing approved model prose.
 *
 * SO: EVERY value, or the page prints its own. The comparison is exact and
 * needs no heuristic -- `_value_strings` in clinician_narrative.py builds each
 * entry from the same printed name, value and unit that `parameterName` and
 * the row do here, so the two render the same characters.
 *
 * A PARTIAL MATCH IS NOT A LIST. Where a narrative names three values inside
 * "flagged X because Y was Z" sentences, those are explanations, not a panel,
 * and the complete list still belongs on the page. Hence every, not some.
 */
function narrativeListsAllValues(text, rows) {
  if (!rows.length) return false;
  const body = String(text || '');
  return rows.every((row) => {
    const value = `${row.value}${isPresent(row.unit) ? ` ${row.unit}` : ''}`;
    return body.includes(`${parameterName(row)} ${value}`);
  });
}

/* -------------------------------------------------------------------- page */

/**
 * The interval the laboratory printed, as a clinician would read it.
 *
 * An empty string when the report printed none -- the caller then writes the
 * flag alone rather than an em dash standing in for a range that was never
 * there. A missing interval is not a range of nothing.
 */
function referenceText(item) {
  const low = item.labReferenceLow;
  const high = item.labReferenceHigh;
  if (low !== undefined && high !== undefined) return `${low}\u2013${high}`;
  if (high !== undefined) return `\u2264 ${high}`;
  if (low !== undefined) return `\u2265 ${low}`;
  return '';
}


export default function DoctorSummary() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

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
  // ONLY THE ONES OUT OF RANGE, AND PRESENTED AS THAT.
  //
  // The payload carries every parameter this platform does not assess; the
  // page shows the ones the LABORATORY marked outside its own interval. The
  // reader asked for exactly that and for the section not to be labelled by
  // what this tool did or did not do with them: a clinician wants the out-of-
  // range results, not a statement about our coverage.
  //
  // `labFlaggedAbnormal` is the producer's own boolean -- true only for a flag
  // that is present and not "normal" -- so "unflagged" and "flagged normal"
  // stay distinct from "flagged abnormal" here, as they do on the patient page.
  /* ONE LIST. IT WAS TWO, AND THE SPLIT WAS THIS PLATFORM'S ARCHITECTURE
     SHOWING THROUGH THE DOCUMENT.

     The page printed out-of-range parameters in two separate places:

       narrative  "The parameters out of range were RANDOM BLOOD GLUCOSE
                   ( RBS ) at 168 mg/dl ..., NEUTROPHILS at 82 %, and
                   LYMPHOCYTES at 14 %."
       this block "Outside the reference interval printed on the report:
                   ESR 45 mm/hr (0-20, high); CRP 38.9 mg/L."

     Same fact, same report, DISJOINT SETS, four paragraphs apart. The
     dividing line was whether this platform holds a canonical feature for
     the parameter: assessed ones reached the narrative, unassessed ones
     reached here. A clinician has no idea that line exists and no reason to
     care -- the comment that used to sit here said exactly that, "a
     clinician wants the out-of-range results, not a statement about our
     coverage", and the page was doing the opposite two inches lower.

     IT BECAME VISIBLE WHEN THE BLOOD COUNT WAS ADDED (2026-09-19). Before
     that, neutrophils and lymphocytes had no canonical feature, so all four
     rows sat in this block together and the narrative listed only the
     glucose. Making them features moved two of the four across the boundary
     and left the reader with two lists that each looked incomplete. The
     split was always there; the CBC work only exposed it.

     SO BOTH SOURCES ARE MERGED HERE AND THE NARRATIVE NO LONGER LISTS THEM
     -- see `_out_of_range` in ai-service/app/services/clinician_narrative.py,
     which no longer reaches the prompt. This list is composed, not written by
     a model, which is what 6az wanted of it in the first place.

     `labFlaggedAbnormal` is the producer's own boolean for the unassessed
     rows -- true only for a flag present and not "normal" -- so "unflagged"
     and "flagged normal" stay distinct from "flagged abnormal". The assessed
     rows carry the same distinction as `position` plus `printed_flag`, and
     both are honoured below rather than one standing in for the other. */
  /* ⚠ READS `summary.laboratory.rows` AND NOT THE `rows` CONST. That const is
     declared ~100 lines BELOW this point, and a `const` is not hoisted: using
     it here is a temporal dead zone error that takes the whole page down at
     render. This file has paid for that once already -- the comment on
     `modelOutputLine` records it costing 26 failing tests -- so the source is
     read directly rather than the declaration moved, which would just put the
     next reader in the same trap from the other side. */
  const ROW_ABNORMAL_POSITIONS = ['below_reference_interval', 'above_reference_interval'];
  const assessedOutOfRange = (summary.laboratory?.rows || [])
    .filter((row) => {
      // A patient detail -- the profile's, or the sex / age printed on the
      // report (2026-09-25) -- is never an out-of-range RESULT.
      if (isPatientDetail(row.provenance?.source)) return false;
      if (row.usable === false || row.value === null || row.value === undefined) return false;
      const flag = String(row.printed_flag ?? '').trim().toLowerCase();
      const flagged = flag !== '' && flag !== 'none' && flag !== 'null' && flag !== 'normal';
      return ROW_ABNORMAL_POSITIONS.includes(String(row.position ?? '')) || flagged;
    })
    .map((row) => ({
      testName: parameterName(row),
      value: row.value,
      unit: row.unit,
      labReferenceLow: row.reference_low ?? undefined,
      labReferenceHigh: row.reference_high ?? undefined,
      labFlag: row.printed_flag ?? '',
    }));

  const unassessedOutOfRange = (unassessed?.items || []).filter(
    (item) => item.labFlaggedAbnormal === true
  );

  // REPORT ORDER, NOT SOURCE ORDER. Grouping by which list a row came from
  // would rebuild the seam this merge exists to remove.
  const outOfRange = [...assessedOutOfRange, ...unassessedOutOfRange].sort((a, b) =>
    String(a.testName).localeCompare(String(b.testName))
  );

  /* OUT OF RANGE, AND IT BELONGS INSIDE THE DOCUMENT.

     Built once and rendered in BOTH branches of the passage rather than
     after them: as a sibling of the <article> it drew its own box on the
     page, which is the separate-document look the reader asked to be rid
     of. One constant, two call sites -- the alternative is duplicating
     the markup and letting the two copies drift.

     ==================================================================
     IT NO LONGER SAYS "BY THE LABORATORY", BECAUSE THAT WAS NOT TRUE
     ==================================================================

     The heading read "Marked outside the reference interval by the
     laboratory", and the comment here used to justify it: values, units,
     intervals and flags are the laboratory's own and carried forward
     untouched. THE FLAGS ARE NOT.

     Module 4's contract (MEMORY.md 8) sets `flag` when the report states it
     OR when the reference range makes the comparison unambiguous -- two
     different provenances that the stored row cannot tell apart. Reading
     `Test 3.pdf` on 2026-09-18 settled which one this report uses: it prints
     FOUR COLUMNS -- name, value, unit, range -- and not one H, L or asterisk
     on either page, including beside NEUTROPHILS 82 against 40-70 and ESR 45
     against 0-20. **That laboratory marks nothing.** All four rows under this
     heading were inferred by a model from the printed interval, and the page
     was attributing them to the laboratory in bold, on the document a
     clinician reads.

     THE HEADING NOW STATES THE FACT AND NOT AN AGENT. That the value falls
     outside the interval printed beside it is checkable from this page --
     both numbers are right there. WHO decided that is not knowable until
     `flag_source` exists (section 0, item 5), so the line below says plainly
     that it is not known rather than picking the flattering answer.

     THE SAME DEFECT, one screen along, as the timeline chip whose tooltip
     said "your laboratory's own marking" -- fixed the same morning. */
  const outOfRangeLine = outOfRange.length ? (
    <p className="passage__outofrange">
        <strong>Outside the reference interval printed on the report:</strong>{' '}
        {outOfRange.map((item, index) => (
          <span key={`${item.testName}-${index}`}>
            {index > 0 ? '; ' : ''}
            {item.testName} {item.value}
            {item.unit ? ` ${item.unit}` : ''}
            {referenceText(item) ? ` (${referenceText(item)}` : ' ('}
            {item.labFlag ? `${referenceText(item) ? ', ' : ''}${item.labFlag}` : ''}
            {')'}
          </span>
        ))}
        .{' '}
        {/* ONE SENTENCE, ON THE CLINICIAN PAGE ONLY, and it is the difference
            between a fact and a false attribution. A reader who believes the
            laboratory marked these weighs them differently from one told this
            tool compared the numbers. This service cannot yet tell the two
            apart, so it says so. */}
        <span className="passage__provenance">
          Either marked on the report or determined from the interval printed
          beside it; this tool does not record which.
        </span>
      </p>
  ) : null;
  /* WHAT A MODEL ESTIMATE IS, AND WHAT ITS AUTHORS SAY ABOUT IT.

     BUILT ONCE AND RENDERED IN BOTH BRANCHES, for exactly the reason the
     comment at the foot of this file gives about the two sections below it --
     and this is the THIRD section to have had that fault. It lived inside the
     composed branch, so it rendered only when the written narrative FAILED.
     While the narrative was usually refused that went unnoticed; the moment
     Gemini started generating reliably, every model caveat left the page.

     WHAT THAT COST, MEASURED ON A REAL REPORT (Test 3, 2026-09-18): the page
     said "Kidney Disease was flagged by the statistical model alone" and
     showed nothing else about it, while the payload carried probability
     0.885, risk band `high`, ROC-AUC 0.999 from a 399-row dataset at 62.7%
     prevalence with 19 of the CKD dataset's 24 attributes unavailable -- and
     a 348-character note written for this exact moment, ending "It is a
     reason to consider further assessment, never a finding in itself."
     A clinician was told a model flagged kidney disease in a 20-year-old
     whose creatinine is normal, and given nothing to weigh it with.

     THE THIRD RECURRENCE OF 6w's DEFECT: model output shown with no ROC-AUC,
     no recall and no caveat. The first two were wrong FIELD PATHS; this one
     is a wrong PLACE IN THE TREE, which no fixture can catch -- the data was
     always there and always correct. */
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
    (row) => !isPatientDetail(row.provenance?.source) && row.usable !== false
  );
  const rejected = rows.filter((row) => row.usable === false);
  const anyInterval = measured.some(
    (row) => isPresent(row.reference_low) || isPresent(row.reference_high)
  );
  const labFlagged = measured.filter((row) => isPresent(row.printed_flag));

  /* THE PARAMETERS AND THEIR VALUES, IN BOTH BRANCHES.
     ========================================================================

     ⚠ THIS BLOCK RENDERED ONLY WHEN THE NARRATIVE FAILED, AND THAT IS THE
     THIRD SECTION ON THIS PAGE TO HAVE HAD EXACTLY THAT FAULT. It sat inside
     the composed branch, so the day Gemini began generating reliably the
     reported values left the clinician page altogether -- the same shape as
     6az's model caveat and the out-of-range line, both fixed for the same
     reason and recorded at the foot of this file.

     It was invisible because the narrative NAMES a value when it explains a
     flag ("Serum Creatinine was 2.4 mg/dl"), so the page did not look empty.
     What went missing was every parameter that was MEASURED AND NOT FLAGGED
     -- on 03-renal that is HbA1c 5.4, glucose 92, cholesterol 186 and
     triglycerides 132, none of which appeared anywhere on the document.

     The owner asked for them back on 2026-09-20: "i also want what parameters
     are there and values in these summary". A handover note whose values
     depend on whether a language model happened to succeed is not a handover
     note. Built once here and rendered in both branches. */
  const reportedValuesLine = measured.length ? (
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
  ) : null;

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
  /* ⚠ "ASSESSED, NOT FLAGGED" MUST MEAN ASSESSED.
     ======================================================================

     This was `assessments.filter((a) => !flagged.includes(a))` -- everything
     that is not flagged -- which swept up the conditions that were never
     assessed at all. On `Test 3.pdf` that is Vitamin D Deficiency, Vitamin
     B12 Deficiency, High Cholesterol and High Triglycerides: no vitamin D,
     B12, cholesterol or triglyceride value was on the report, so no rule ran.
     They were printed under a sentence reading "Each was compared against
     this tool's cut-offs and none was crossed", which is false of all four.

     IT WAS SURVIVABLE ONLY WHILE THE "Not assessed." PARAGRAPH NAMED THEM
     four lines below, and that paragraph was removed on the owner's
     instruction on 2026-09-20 -- so the false claim became the ONLY thing
     the document said about them. Exactly 6bg's pattern: the defect was not
     in the code that changed, it was in a neighbouring statement whose
     meaning depended on it.

     The unassessed are now in neither list. That is what the owner asked
     for -- the page does not discuss what it could not check -- and it is
     honest, because saying nothing about a condition is not the same as
     saying it was checked and clear. */
  const assessedNotFlagged = (a) =>
    !flagged.includes(a) && a.assessed !== false && a.status !== 'Insufficient Data';
  const clear = assessments.filter(assessedNotFlagged);

  /* `modelNotes` WAS HERE AND IS GONE. It collected
     `basis.ml.limitations.author_note.text` -- the artifact's `honest_read`,
     written in patient register -- and appended it to the model paragraph on
     the CLINICIAN page. It is still carried in the payload, still scanned,
     and still the right text for the patient-facing screens; it was simply
     addressed to the wrong reader here.

     ⚠ THE REAL LOGIC IT CARRIED IS NOW CARRIED BY `byModel`/`byBoth`, WHICH
     ARE BUILT FROM `flaggingKinds` AND SKIP A `Not Indicated` BASIS THE SAME
     WAY. That guard is not decoration: on a real report the heart model's
     note printed beside a Heart Disease flag that the heart model itself had
     DISAGREED with. Anything reintroduced here must skip a non-flagging
     basis, or it will caption a finding its model did not make. */

  /* THE MODEL PARAGRAPH IS GONE, ON THE OWNER'S INSTRUCTION -- 2026-09-20.
     ========================================================================

     A paragraph stood here headed "On the model output." It said what a model
     estimate is and, in its last version, how often the model that flagged was
     right and how often it missed. The owner read it on the real page and
     asked for it to go, with the spec for this whole document:

         "just show what parameters are there in report and what flagged and
          why flagged, that's it ... i don't need words like model and output"

     THIS REVERSES §6w's STANDING CONSTRAINT AND THAT IS RECORDED, NOT HIDDEN.
     "A model-derived flag may never appear without its limitation" was found
     violated three times (6o D8, 6p, 6w) and 6az found it a fourth. The
     objection was put to the owner in those terms before this was removed and
     the instruction was repeated. It is the owner's document and their call;
     what is not acceptable is for it to be reversed quietly, so this comment
     and the replaced tests are the record.

     ⚠ WHAT IS NOT AFFECTED, AND MUST NOT BE. The WHY of a flag stays -- it is
     the thing the owner asked for. Where a model alone flagged a topic and no
     measured value crossed a cut-off, the narrative and the composed passage
     both still say so in the sentence that names the flag, because otherwise
     the page states a finding with no reason at all. That is not a model
     caveat, it is the answer to "why flagged". */

  // `alsoMissing` STOOD HERE and is gone with the paragraph that read it --
  // `features_not_present`, minus the three profile fields already reported
  // as "not supplied" so that one gap was never named twice. The owner
  // removed the parameters-not-present sentence on 2026-09-20; nothing else
  // consumed this, and a derived value with no consumer is a future reader's
  // wrong turn. `features_not_present` is untouched on the payload.

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
          {/* VALUES FIRST, THEN WHAT WAS FLAGGED AND WHY -- the order the
              owner asked for, and the order the composed branch already
              used. The narrative supplies the flags and their reasons; it
              does not reliably list the parameters that were measured and
              not flagged, so without this the document can omit them
              entirely.

              UNLESS THE NARRATIVE ALREADY LISTED THEM ALL, in which case
              this would be the same panel printed twice -- see
              `narrativeListsAllValues`. */}
          {narrativeListsAllValues(narrative.text, measured) ? null : reportedValuesLine}
          {narrativeBody(narrative.text).map((para, index) => (
            <p key={index}>{para}</p>
          ))}
          {/* SAID, NOT IMPLIED. The reader is entitled to know a model wrote
              the prose -- the findings in it were not decided by one, and the
              distinction is the whole reason the composed version existed. */}
          {outOfRangeLine}

          {/* THE DOCUMENT CLOSES LAST. `CLOSING_LINE` is appended to the text
              server-side, so it arrived as the narrative's final paragraph and
              the page then printed two more caveats AFTER it -- the document
              ended, then kept talking. `narrativeBody` lifts it out and it is
              re-rendered here.

              ⚠ FAIL-SAFE, NOT FAIL-SILENT. If the server ever rewords the
              line, `narrativeBody` will not recognise it, will leave it in the
              body where it has always been, and this renders nothing. The line
              is then in the old place rather than missing, and it can never be
              printed twice. */}
          <p className="passage__close">
            The wording above was written by a language model from the findings
            of this analysis and checked before being shown. The findings
            themselves were not produced by a language model.
          </p>

          {/* LAST, AND THAT IS THE POINT. The provenance line above is about
              who wrote the prose; this is the document's closing statement,
              and a document that closes and then adds two more paragraphs is
              what the owner read on the real page. */}
          {narrativeClosing(narrative.text) ? (
            <p>{narrativeClosing(narrative.text)}</p>
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

        {reportedValuesLine}

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

        {/* Assessed and not flagged, named -- a clinician needs to know which
            topics were covered, and "not flagged" is not "ruled out". */}
        {clear.length ? (
          <p>
            <strong>Assessed, not flagged.</strong>{' '}
            {nameList(clear.map((a) => a.condition))}. Each was compared
            against this tool&rsquo;s cut-offs and none was crossed.
          </p>
        ) : null}

        {/* WHAT THIS TOOL DID NOT COVER IS GONE, ON THE OWNER'S INSTRUCTION
            -- 2026-09-20.
            ====================================================================

            This paragraph opened "Not assessed." and named the conditions with
            no inputs and the parameters the report did not carry. The owner
            removed it with the spec they have given for this whole document:
            show the parameters, what was flagged and why, and nothing else.

            ⚠ IT WAS ONE OF THE FOUR THINGS THIS PAGE'S OWN HEADER CALLS KEPT
            "because removing them would make the passage lie by omission",
            and the codebase's standing rule is that an absence must never
            read as a negative result. Recorded here rather than done quietly.
            What a clinician loses: the page no longer says that Vitamin D
            Deficiency, Vitamin B12 Deficiency, High Cholesterol and High
            Triglycerides were never assessed, so "Assessed, not flagged"
            above is now the only list of what was covered.

            ⚠⚠ WHAT IS **NOT** REMOVED, AND WHY IT IS A DIFFERENT FACT.
            The document-readability clause stays. "Part of the document could
            not be read (page 2)" is not a statement about this tool's
            coverage -- it is a statement about whether the PARAMETERS SHOWN
            ARE ALL OF THEM, which is the owner's own first requirement. On
            2026-09-20 an extraction timeout lost page 2 of `Test 3.pdf` and
            seven parameters with it, including the HbA1c and glucose behind
            the diabetes flag; this sentence is how a reader finds that out.
            `sources_failed` stays with it for the same reason. */}
        {unreadable.length ||
        quality.partial_document === true ||
        quality.sources_failed?.length ? (
          <p>
            <strong>Not fully read.</strong>{' '}
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

        {outOfRangeLine}

        <p className="passage__close">
          Not a diagnosis and not a clinical conclusion. The original laboratory
          report remains the primary record.
        </p>
      </article>
      )}

      {/* SHARED BY BOTH VERSIONS OF THE DOCUMENT, AND THAT IS THE POINT.

          These two sections were inside the composed branch, so they
          rendered ONLY when the written narrative failed. The comment
          below already said "outside everything the narrative may
          rewrite" -- that was the intent; the ternary was the code. It
          went unnoticed while the narrative was usually refused, and the
          moment it started generating reliably both sections disappeared
          from the page.

          Neither depends on the narrative: one is general context for a
          direction the laboratory or this tool already decided, the other
          is the laboratory's own rows. */}
    </main>
  );
}
