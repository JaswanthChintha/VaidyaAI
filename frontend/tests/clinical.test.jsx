import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import DoctorSummary from '../src/pages/DoctorSummary';
import Population from '../src/pages/Population';
import { api } from '../src/lib/api';

/**
 * Modules 31 and 32 at the rendering layer.
 *
 * Module 32 is the page a CLINICIAN may act on, which makes it the
 * higher-stakes surface, and Module 31 is the one whose refusals ARE the
 * product. Both are tested on exactly those properties.
 */

function mountSummary(doctorSummary, history, narrative, unassessed) {
  vi.spyOn(api, 'getDoctorSummary').mockResolvedValue({
    report: { originalName: 'r.pdf' },
    history: history || {},
    doctorSummary,
    narrative: narrative ?? null,
    // The parameters the laboratory reported and this platform does not
    // assess. Absent by default so every existing call is unchanged.
    unassessed,
  });
  return render(
    <MemoryRouter initialEntries={['/reports/abc/doctor-summary']}>
      <Routes>
        <Route path="/reports/:id/doctor-summary" element={<DoctorSummary />} />
      </Routes>
    </MemoryRouter>
  );
}

function mountPopulation(populationContext, subject) {
  vi.spyOn(api, 'getPopulationContext').mockResolvedValue({
    report: { originalName: 'r.pdf' },
    subject: subject || { profileExists: true, ageProvided: true, genderProvided: true },
    populationContext,
  });
  return render(
    <MemoryRouter initialEntries={['/reports/abc/population']}>
      <Routes>
        <Route path="/reports/:id/population" element={<Population />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('Module 32 -- the clinician summary, as one passage', () => {
  // The page is a handover note now, so every assertion is about the PASSAGE:
  // what it says, and what it must never leave out under compression. A
  // summary's failure mode is omission, and the four things below are the ones
  // whose omission would make it lie.
  const passage = () => document.querySelector('.passage').textContent;

  const REPORT = {
    overall: { status_label: 'Needs Medical Attention', clean_bill_of_health: false },
    attribution: { report_date: '2026-09-07T04:00:14.776000Z' },
    patient: { age: 58, gender: 'male', bmi: 26.42, hypertension: null, heart_disease: null, smoking_history: null },
    data_quality: { page_count: 1, pages_unreadable: [], partial_document: false },
    laboratory: {
      total: 2,
      features_not_present: ['smoking_history'],
      rows: [
        {
          feature: 'hba1c',
          display_name: 'Glycated haemoglobin, NGSP %',
          value: 8.4,
          unit: '%',
          usable: true,
          provenance: {
            source: 'lab_report',
            original_test_name: { text: 'HbA1C (Glycosylated Haemoglobin)', state: 'CLEAN' },
          },
        },
        {
          feature: 'creatinine',
          display_name: 'Serum creatinine',
          value: 1.1,
          unit: 'mg/dl',
          usable: true,
          provenance: { source: 'lab_report', original_test_name: { text: 'Serum Creatinine', state: 'CLEAN' } },
        },
        {
          feature: 'bmi',
          display_name: 'Self-described gender as stored by Module 2.',
          value: 26.42,
          unit: 'kg/m2',
          usable: true,
          provenance: { source: 'patient_profile' },
        },
      ],
    },
    abnormal_findings: ['Diabetes', 'Kidney Disease'],
    assessments: [
      {
        condition: 'Diabetes',
        status: 'Indicated',
        assessed: true,
        bases: [
          { source_kind: 'clinical_rule', status: 'Indicated', rule: { rule_ids: ['RULE_DIABETES_HBA1C'] } },
        ],
      },
      {
        // THE CASE THAT MATTERS. The rule did NOT fire; the model did.
        condition: 'Kidney Disease',
        status: 'Indicated',
        assessed: true,
        bases: [
          { source_kind: 'clinical_rule', status: 'Not Indicated', rule: { rule_ids: ['RULE_KIDNEY_CREATININE'] } },
          {
            source_kind: 'machine_learning',
            status: 'Indicated',
            ml: {
              model_name: 'Random Forest',
              probability: 0.7,
              limitations: {
                roc_auc: 0.9987,
                // COPIED FROM THE PRODUCER, not written to suit the page:
                // this is `app/ml/kidney.py`'s `honest_read` verbatim. The
                // previous fixture held the wording the note USED to have, so
                // it would have gone on passing after the source was rewritten
                // -- §6w's `basis.limitations` hazard, one layer along.
                author_note: {
                  text:
                    'Its measured accuracy there is high because that separation was easy, '
                    + 'and nothing shows it holds in a screening population where kidney '
                    + 'disease is far less common.',
                },
              },
            },
          },
        ],
      },
      { condition: 'Anemia', status: 'Not Indicated', assessed: true, bases: [] },
    ],
    unassessed_conditions: [],
  };

  it('gives the values, in the wording printed on the source report', async () => {
    await mountSummary(REPORT);
    await screen.findByText(/Reported values/);
    // A clinician reads this beside the paper, so it matches on the paper's
    // wording -- not on the catalog's internal display name.
    expect(passage()).toMatch(/HbA1C \(Glycosylated Haemoglobin\) 8\.4 %/);
    expect(passage()).toMatch(/Serum Creatinine 1\.1 mg\/dl/);
  });

  it('never lets bare numbers read as in range', async () => {
    // Eight values and no intervals is the common case, and without this one
    // sentence the list reads as a normal panel.
    await mountSummary(REPORT);
    await screen.findByText(/Reported values/);
    expect(passage()).toMatch(/printed no reference intervals/);
    expect(passage()).toMatch(/no value here is placed relative to a range/);
  });

  it('SAYS WHEN ONLY THE MODEL FLAGGED SOMETHING', async () => {
    // The single most important thing this passage carries. Creatinine 1.1
    // does not cross the kidney rule; the model flagged it anyway. A clinician
    // told "kidney disease flagged" without that is being told something the
    // analysis did not find.
    await mountSummary(REPORT);
    await screen.findByText(/Flagged/);
    // The DISTINCTION, not one phrasing of it: flagged by the model, with no
    // measured value crossing a cut-off. The wording moved to the words a
    // clinician uses; the claim it carries is unchanged.
    expect(passage()).toMatch(
      /Kidney Disease was flagged by the statistical model alone/
    );
    expect(passage()).toMatch(/no measured value crossed a cut-off/);
    // And a rule-flagged topic is not described that way.
    expect(passage()).toMatch(/Diabetes .*crossed one of this tool's cut-offs/);
  });

  /* ======================================================================
     THE MODEL PARAGRAPH WAS REMOVED ON THE OWNER'S INSTRUCTION -- 2026-09-20
     ======================================================================

     TWO TESTS STOOD HERE and both asserted the paragraph's PRESENCE:
     'qualifies a model flag in one sentence, and does not pad it' and
     'does not put model-development vocabulary in front of a clinician'.
     They encoded §6w -- a model-derived flag may never appear without its
     limitation -- which had been violated three times.

     THEY ARE REPLACED, NOT DELETED AND NOT WEAKENED. The owner read the
     paragraph on the real page and asked for it to go, twice, with the spec
     for the whole document: "just show what parameters are there in report
     and what flagged and why flagged, that's it ... i don't need words like
     model and output". A test asserting the paragraph is present can only be
     satisfied now by putting it back, so keeping it would mean the suite
     demanded a state the owner rejected.

     WHAT REPLACES THEM IS THE STRONGER HALF OF WHAT THEY GUARDED: the
     vocabulary ban, now absolute rather than partial, plus the requirement
     that the WHY of every flag survives -- which is what the owner asked to
     keep and is the only reason the old paragraph could be spared. */

  it('shows no model-output paragraph at all', async () => {
    await mountSummary(REPORT);
    await screen.findByText(/Flagged/);
    expect(passage()).not.toMatch(/On the model output/i);
    expect(passage()).not.toMatch(/an estimate from patterns/i);
    expect(passage()).not.toMatch(/not a measurement of this patient/i);
  });

  it('puts no model performance figure in front of a clinician', async () => {
    /* THE BAN IS NOW ABSOLUTE. It used to permit a qualification sentence and
       forbid only the development vocabulary; nothing about a model's
       performance may reach this page now. `N in N` is included because the
       natural-frequency version of these figures lived here for one day. */
    await mountSummary(REPORT);
    await screen.findByText(/Flagged/);
    const text = passage();
    for (const jargon of [
      'AUC', 'precision 0.', 'recall 0.', 'Random Forest',
      'operating threshold', 'held-out', 'flatters', 'screening population',
    ]) {
      expect(text).not.toContain(jargon);
    }
    expect(text).not.toMatch(/\d+ in \d+ of the patients/);
    expect(text).not.toMatch(/missed about/);
  });

  it('still says WHY each topic was flagged', async () => {
    /* THE OWNER'S ACTUAL SPEC, AND THE REASON THE PARAGRAPH COULD GO. What
       was flagged and why is the whole document. A model-only flag keeps its
       reason too -- "no measured value crossed a cut-off" -- because without
       it the page states a finding with no reason at all, which is a worse
       failure than the one removing the paragraph fixed. */
    await mountSummary(REPORT);
    await screen.findByText(/Flagged/);
    expect(passage()).toMatch(/Diabetes .*crossed one of this tool's cut-offs/);
    expect(passage()).toMatch(/no measured value crossed a cut-off/);
  });

  it('omits the model paragraph entirely when no model flagged anything', async () => {
    await mountSummary({
      ...REPORT,
      abnormal_findings: ['Diabetes'],
      assessments: [REPORT.assessments[0], REPORT.assessments[2]],
    });
    await screen.findByText(/Flagged/);
    expect(passage()).not.toMatch(/statistical model alone/);
    expect(passage()).not.toMatch(/On the model output/);
  });

  it('names what was assessed and not flagged, without calling it ruled out', async () => {
    await mountSummary(REPORT);
    await screen.findByText(/Assessed, not flagged/);
    expect(passage()).toMatch(/Anemia/);
    expect(passage()).toMatch(/none was crossed/);
  });

  /* ======================================================================
     "Not assessed." WAS REMOVED ON THE OWNER'S INSTRUCTION -- 2026-09-20
     ======================================================================

     TWO TESTS STOOD HERE and both asserted the paragraph's PRESENCE:
     'NEVER DROPS AN ABSENCE UNDER COMPRESSION' and 'names a parameter the
     report lacked that the patient DID supply'. They encoded this page's own
     KEPT item 3 -- "WHAT WAS NOT AVAILABLE ... absence is not a negative
     result", the rule the codebase is built on.

     The owner removed it with the standing spec for this document: the
     parameters, what was flagged and why, nothing else. A test asserting the
     paragraph is present can only be satisfied now by putting it back, so
     these are REPLACED rather than weakened, and the reversal is recorded.

     ⚠ WHAT SURVIVES IS ASSERTED BELOW, AND IT IS NOT NOTHING. The document
     readability clause stays, because it is a different kind of fact: not
     what this tool failed to cover, but whether the PARAMETERS SHOWN ARE ALL
     OF THEM. An extraction timeout lost page 2 of `Test 3.pdf` on 2026-09-20
     and seven parameters with it. So is the profile line in the subject
     paragraph, which was never part of the removed block. */

  it('no longer names the conditions it could not assess', async () => {
    await mountSummary({
      ...REPORT,
      unassessed_conditions: ['Vitamin D Deficiency'],
      data_quality: { page_count: 3, pages_unreadable: [], partial_document: false, sources_failed: [] },
    });
    await screen.findByText(/Flagged/);
    expect(passage()).not.toMatch(/Not assessed\./);
    expect(passage()).not.toMatch(/could not be assessed/);
    expect(passage()).not.toMatch(/Vitamin D Deficiency/);
  });

  it('no longer names a parameter the report did not carry', async () => {
    await mountSummary({
      ...REPORT,
      patient: { ...REPORT.patient, hypertension: false, heart_disease: false, smoking_history: 'never' },
      laboratory: { ...REPORT.laboratory, features_not_present: ['vitamin_b12'] },
      data_quality: { page_count: 1, pages_unreadable: [], partial_document: false, sources_failed: [] },
    });
    await screen.findByText(/Flagged/);
    expect(passage()).not.toMatch(/not present in this report/);
    expect(passage()).not.toMatch(/Vitamin b12/i);
  });

  it('⚠ STILL says when part of the document could not be read', async () => {
    /* THE CLAUSE THAT DID NOT GO, AND THE REASON IT DID NOT. This is not a
       statement about this tool's coverage -- it is the reader's only signal
       that the parameter list above may be incomplete. On 2026-09-20 page 2
       of `Test 3.pdf` timed out and seven parameters vanished from the
       table, including the HbA1c and glucose behind the diabetes flag. */
    await mountSummary({
      ...REPORT,
      data_quality: { page_count: 3, pages_unreadable: [2], partial_document: true, sources_failed: [] },
    });
    await screen.findByText(/Not fully read/);
    expect(passage()).toMatch(/Part of the document could not be read \(page 2\)/);
    expect(passage()).toMatch(/may be missing from the reading rather than from the report/);
    expect(passage()).toMatch(/None of this is a negative finding/);
  });

  it('still reports an analysis source that did not complete', async () => {
    await mountSummary({
      ...REPORT,
      data_quality: { page_count: 1, pages_unreadable: [], partial_document: false, sources_failed: ['Random Forest'] },
    });
    await screen.findByText(/Not fully read/);
    expect(passage()).toMatch(/did not complete/);
  });

  it('renders no readability paragraph when the document was read whole', async () => {
    // The paragraph must not appear to say nothing. A clean document gets no
    // sentence about what did not happen to it.
    await mountSummary({
      ...REPORT,
      data_quality: { page_count: 1, pages_unreadable: [], partial_document: false, sources_failed: [] },
    });
    await screen.findByText(/Flagged/);
    expect(passage()).not.toMatch(/Not fully read/);
  });

  it('⚠ never lists an UNASSESSED condition as "Assessed, not flagged"', async () => {
    /* THE DEFECT REMOVING "Not assessed." EXPOSED, AND 6bg's PATTERN AGAIN:
       the fault was not in the code that changed but in a neighbouring
       sentence whose meaning depended on it.

       `clear` was "everything not flagged", which swept up the conditions no
       rule could run on. On `Test 3.pdf` that is the four below -- the report
       carries no vitamin D, B12, cholesterol or triglyceride value -- and
       they were printed under "Each was compared against this tool's cut-offs
       and none was crossed". False of all four, and once the "Not assessed."
       paragraph went it was the ONLY thing the document said about them.

       SAYING NOTHING ABOUT A CONDITION IS NOT SAYING IT WAS CHECKED. */
    await mountSummary({
      ...REPORT,
      abnormal_findings: ['Diabetes'],
      unassessed_conditions: ['Vitamin D Deficiency'],
      assessments: [
        {
          condition: 'Diabetes',
          status: 'Indicated',
          assessed: true,
          bases: [{ source_kind: 'clinical_rule', status: 'Indicated' }],
        },
        {
          condition: 'Heart Disease',
          status: 'Not Indicated',
          assessed: true,
          bases: [{ source_kind: 'clinical_rule', status: 'Not Indicated' }],
        },
        // NEVER ASSESSED -- no input was available. Must appear in NEITHER
        // list, not merely out of the flagged one.
        {
          condition: 'Vitamin D Deficiency',
          status: 'Insufficient Data',
          assessed: false,
          bases: [],
        },
      ],
      data_quality: { page_count: 1, pages_unreadable: [], partial_document: false, sources_failed: [] },
    });

    await screen.findByText(/Assessed, not flagged/);
    const text = passage();
    // The genuinely assessed one is still named.
    expect(text).toMatch(/Assessed, not flagged\..*Heart Disease/);
    // The unassessed one appears nowhere at all.
    expect(text).not.toMatch(/Vitamin D Deficiency/);
  });

  it('drops the "Assessed, not flagged" line when nothing was assessed and clear', async () => {
    // A heading with an empty list, or worse one listing the unassessed, is
    // how the defect above reads to a clinician.
    await mountSummary({
      ...REPORT,
      abnormal_findings: ['Diabetes'],
      assessments: [
        {
          condition: 'Diabetes',
          status: 'Indicated',
          assessed: true,
          bases: [{ source_kind: 'clinical_rule', status: 'Indicated' }],
        },
        { condition: 'Vitamin D Deficiency', status: 'Insufficient Data', assessed: false, bases: [] },
      ],
      data_quality: { page_count: 1, pages_unreadable: [], partial_document: false, sources_failed: [] },
    });

    await screen.findByText(/Flagged/);
    expect(passage()).not.toMatch(/Assessed, not flagged/);
  });

  it('still says which profile fields were not supplied', async () => {
    // NEVER PART OF THE REMOVED BLOCK -- it lives in the subject paragraph,
    // and a clinician needs to know the analysis was run without them.
    await mountSummary({
      ...REPORT,
      data_quality: { page_count: 1, pages_unreadable: [], partial_document: false, sources_failed: [] },
    });
    await screen.findByText(/Flagged/);
    expect(passage()).toMatch(/were not supplied and (were )?unavailable to the analysis/);
  });

  describe('the written version', () => {
    // The prose is generated, Module-24 approved and fact-checked in the
    // ai-service (app/services/clinician_narrative.py). This page's job is
    // only to render it WHEN THERE IS ONE and to fall back silently when
    // there is not -- so the worst case of the whole feature is the composed
    // passage this page has always shown.
    const WRITTEN = {
      outcome: 'generated',
      text: 'First written paragraph about the results.\n\nSecond written paragraph.',
    };

    it('breaks paragraphs on a double space as well as a blank line', async () => {
      // The model groups its sentences with two spaces after a full stop,
      // whatever the prompt asks, so the whole note arrived as one ten-line
      // block. Reflowed here; not one character of the approved text changes.
      await mountSummary(REPORT, undefined, {
        outcome: 'generated',
        text: 'First group ends here.  Second group starts here.',
      });
      await screen.findByText(/First group ends here/);
      /* INDEXED OFF THE PROSE, NOT OFF THE PASSAGE. This read `paras[0]` and
         `paras[1]`, which was only ever true while the narrative branch
         rendered nothing but the narrative. The reported values now open both
         branches, so a positional assertion here was testing the layout of
         the page rather than the reflow it is about. */
      const paras = [...document.querySelectorAll('.passage p')].map(
        (p) => p.textContent
      );
      const first = paras.indexOf('First group ends here.');
      expect(first).toBeGreaterThanOrEqual(0);
      expect(paras[first + 1]).toBe('Second group starts here.');
    });

    it('renders the written prose when one was approved', async () => {
      await mountSummary(REPORT, undefined, WRITTEN);
      expect(await screen.findByText(/First written paragraph/)).toBeInTheDocument();
      expect(screen.getByText(/Second written paragraph/)).toBeInTheDocument();
      /* ⚠ THIS ASSERTED `Reported values` WAS ABSENT, AND THAT IS NOW WRONG.
         The intent was right -- two differently worded summaries of one
         report is worse than either alone -- but the reported values are not
         a second summary. They are the parameters and their readings, and
         they rendered ONLY when the narrative failed, so the day Gemini began
         generating reliably a clinician stopped being shown any parameter
         that was measured and not flagged. The owner asked for them back on
         2026-09-20. This now asserts the opposite, and the thing the original
         was guarding is asserted below it. */
      expect(screen.getByText(/Reported values/)).toBeInTheDocument();
      // What must still NOT appear: the composed branch's OWN prose about
      // what was flagged, which would be a second summary beside the written
      // one. `Flagged.` is that paragraph's lead-in.
      expect(screen.queryByText(/^Flagged\.$/)).not.toBeInTheDocument();
    });

    it('says a model wrote the wording, and that it did not decide anything', async () => {
      // The reader is entitled to know. The findings were not produced by a
      // model and the distinction is the whole reason the composed version
      // existed in the first place.
      await mountSummary(REPORT, undefined, WRITTEN);
      await screen.findByText(/First written paragraph/);
      expect(screen.getByText(/written by a language model/)).toBeInTheDocument();
      expect(
        screen.getByText(/findings themselves were not produced by a language model/)
      ).toBeInTheDocument();
    });

    it('falls back to the composed passage when there is no narrative', async () => {
      await mountSummary(REPORT, undefined, null);
      expect(await screen.findByText(/Reported values/)).toBeInTheDocument();
      expect(screen.queryByText(/written by a language model/)).not.toBeInTheDocument();
    });

    it('falls back when the narrative was REFUSED, not merely absent', async () => {
      // A refusal is an object with an outcome and no text. Branching on the
      // object being truthy would render an empty article -- a blank page
      // where the document used to be.
      await mountSummary(REPORT, undefined, {
        outcome: 'facts_missing',
        text: null,
        notice: 'A written summary could not be prepared for this report.',
        missing_facts: ['value:186 mg/dl'],
      });
      expect(await screen.findByText(/Reported values/)).toBeInTheDocument();
      expect(screen.getByText(/Kidney Disease was flagged/)).toBeInTheDocument();
    });
  });

  it('closes on one line, not a scope statement', async () => {
    await mountSummary(REPORT);
    await screen.findByText(/Not a diagnosis/);
    expect(passage()).toMatch(/original laboratory report remains the primary record/);
    // The page no longer explains itself: no legend, no provenance block, no
    // reference appendix, no source-file paths.
    for (const noise of [
      'Clinical Rule Engine',
      'Random Forest',
      'RULE_',
      'app/services',
      'What each source answers',
      'How this document was produced',
      'Reference material consulted',
      'Technical details',
    ]) {
      expect(passage()).not.toContain(noise);
    }
    // The metrics TABLE is gone. "ROC-AUC" is not on the forbidden list
    // because it survives inside the model author's own caveat, and rewriting
    // an author's safety note to strip a term is not a licence this page has.
    expect(passage()).not.toMatch(/Detection at the operating threshold/);
    expect(passage()).not.toMatch(/Precision at that threshold/);
    expect(passage()).not.toMatch(/majority-class baseline/);
  });

  it('says so plainly when nothing was flagged', async () => {
    await mountSummary({
      ...REPORT,
      abnormal_findings: [],
      assessments: [REPORT.assessments[2]],
    });
    await screen.findByText(/Flagged/);
    expect(passage()).toMatch(/No measured value crossed a cut-off/);
    // And that is still not a clean bill: the absences paragraph stands.
    expect(passage()).toMatch(/not supplied/);
  });

  it('excludes a rejected reading from the values and says it was excluded', async () => {
    await mountSummary({
      ...REPORT,
      laboratory: {
        ...REPORT.laboratory,
        rows: [
          ...REPORT.laboratory.rows,
          {
            feature: 'vitamin_d',
            display_name: 'Vitamin D',
            value: 9999,
            unit: 'ng/ml',
            usable: false,
            provenance: { source: 'lab_report', original_test_name: { text: 'Vitamin D', state: 'CLEAN' } },
          },
        ],
      },
    });
    await screen.findByText(/Reported values/);
    // A rejected reading must never appear among the results as a number.
    expect(passage()).not.toMatch(/9999/);
    expect(passage()).toMatch(/Vitamin D did not pass validation/);
  });
});

describe('Module 31 -- population context', () => {
  // WHICH REFUSALS EARN A CARD, AND WHICH ARE THE PAGE TALKING ABOUT ITSELF.
  //
  // Every feature the service declines to compare came back as a full card,
  // including three that nobody expected a percentile for: age and gender are
  // what the cohort is MATCHED ON (asking for their percentile is circular)
  // and smoking history is a word. Three cards explaining that is the page
  // explaining its own mechanics.
  //
  // The refusals that DO earn one are the ones a reader would otherwise
  // wonder about, and they must keep earning one.

  it('keeps a card for a refusal a reader would wonder about', async () => {
    // A glucose of 186 with no comparison beside it is a real question.
    await mountPopulation({
      features: {
        blood_glucose: {
          feature: 'blood_glucose',
          available: false,
          reason_code: 'NO_VERIFIED_DISTRIBUTION',
          message:
            'A glucose result means something different depending on whether the sample was taken fasting.',
        },
      },
    });

    expect(await screen.findByText(/taken fasting/)).toBeInTheDocument();
    expect(document.querySelectorAll('.population__entry')).toHaveLength(1);
  });

  it('drops the not-a-measurement cards and says it once instead', async () => {
    await mountPopulation({
      features: {
        age: {
          feature: 'age',
          available: false,
          reason_code: 'FEATURE_NOT_CONTINUOUS',
          message: 'Age is one of the things the population group is matched ON.',
        },
        gender: {
          feature: 'gender',
          available: false,
          reason_code: 'FEATURE_NOT_CONTINUOUS',
          message: 'Gender is one of the things the population group is matched ON.',
        },
        smoking_history: {
          feature: 'smoking_history',
          available: false,
          reason_code: 'FEATURE_NOT_CONTINUOUS',
          message: 'Smoking history is a category, not a measured number.',
        },
      },
    });

    await screen.findByText(/How your results compare/);
    // No cards...
    expect(document.querySelectorAll('.population__entry')).toHaveLength(0);
    // ...but NOT silently dropped: still named, once, in a line.
    const body = document.querySelector('main').textContent;
    expect(body).toMatch(/Age, sex and smoking history/);
    expect(body).toMatch(/not measured values, so no percentile is offered/);
  });

  it('renders a refusal as an answer, in the service own words', async () => {
    await mountPopulation({
      features: {
        hba1c: {
          feature: 'hba1c',
          available: false,
          reason_code: 'SEX_COHORT_NOT_AVAILABLE',
          message:
            'The published survey groups results by male and female only, and no group matches the gender recorded on your profile. No other group is substituted.',
        },
      },
    });

    expect(await screen.findByText(/No other group is substituted/)).toBeInTheDocument();
    // The reason CODE is not shown to the reader (2026-10-02); the sentence
    // above says it in words. It is still carried on the card for debugging.
    expect(screen.queryByText('SEX_COHORT_NOT_AVAILABLE')).toBeNull();
    expect(document.querySelector('[data-reason="SEX_COHORT_NOT_AVAILABLE"]')).toBeTruthy();
    expect(screen.getByText('No comparison offered')).toBeInTheDocument();
  });

  it('shows no percentile at all on an unavailable entry', async () => {
    // The guarantee is structural server-side -- there is no `comparison`
    // object to read from. The screen must not invent one.
    await mountPopulation({
      features: {
        creatinine: {
          feature: 'creatinine',
          available: false,
          reason_code: 'AGE_BELOW_ADULT_TABLE',
          message: 'The published tables cover adults aged 20 and over.',
        },
      },
    });

    await screen.findByText('The published tables cover adults aged 20 and over.');
    expect(screen.queryByText(/percentile/)).not.toBeInTheDocument();
    expect(screen.queryByText('0')).not.toBeInTheDocument();
  });

  it('renders an available comparison as a BAND with its caveats', async () => {
    await mountPopulation({
      features: {
        hba1c: {
          feature: 'hba1c',
          available: true,
          comparison: {
            value: 5.2,
            unit: '%',
            band: { label: 'between the 50th and the 75th percentile' },
            cohort: { age_band_label: '20-29 years', sex: 'male' },
            what_this_means:
              'Of people of this age and sex in the survey, this is the share whose HbA1c was at or below yours.',
            what_this_does_not_mean:
              'This does not say whether your HbA1c is normal, high, or low.',
          },
        },
      },
    });

    expect(
      await screen.findByText('between the 50th and the 75th percentile')
    ).toBeInTheDocument();
    // "at or below", not "lower than" -- the band is built on <=.
    expect(screen.getByText(/at or below yours/)).toBeInTheDocument();
    expect(screen.getByText(/does not say whether/)).toBeInTheDocument();
  });

  it('tells the patient which missing profile answer to act on', async () => {
    // "No profile at all" and "a profile that said prefer_not_to_say" both
    // produce SEX_COHORT_NOT_AVAILABLE; only the subject block distinguishes
    // them, and only one of them is actionable.
    await mountPopulation(
      { features: {} },
      { profileExists: true, ageProvided: true, genderProvided: false }
    );

    expect(await screen.findByText(/missing gender/)).toBeInTheDocument();
    expect(screen.getByText('Update your details')).toBeInTheDocument();
  });
});

/**
 * THE METHOD-NOTES PANEL, AND WHY IT IS NOT A DISCLOSURE.
 *
 * The population page ended in three stacked `.hint` blocks -- browser
 * bullets, no container, one flat grey -- and the user asked for a design.
 * The dashboard's answer to the same complaint was to collapse the section.
 * THAT ANSWER IS WRONG HERE, and these tests are what stops someone applying
 * it later for consistency.
 *
 * These bullets are the caveats on the comparison above them. Section 6ag:
 * what may never go is the CAVEAT -- this platform has found it missing three
 * separate times and recorded it each time as the worst thing on the page.
 * A caveat behind a toggle is a caveat most readers never open: the same
 * outcome as deleting it, reached more slowly.
 */
describe('the population page method notes', () => {
  const context = {
    comparisons: [],
    limitations: [
      'The reference population is the United States civilian non-institutionalised population surveyed by NHANES.',
      'Pregnant participants were excluded from every group.',
    ],
    disclaimer:
      'Population context is educational information, not a medical assessment. Discuss your results with a qualified healthcare professional.',
  };

  it('shows every limitation without anything to click first', async () => {
    await mountPopulation(context);

    await screen.findByText(/What this comparison cannot account for/);
    const panel = document.querySelector('.notes');
    expect(panel).not.toBeNull();
    // NOT a disclosure. If this ever becomes one, this assertion is the thing
    // that has to be deleted -- deliberately, by someone who has read why.
    expect(panel.tagName).not.toBe('DETAILS');
    expect(panel.querySelector('details')).toBeNull();
    expect(panel.querySelectorAll('.bullets > li')).toHaveLength(2);
  });

  it('keeps the closing disclaimer inside the same panel, divided off', async () => {
    // It read as page text that merely followed the bullets. It is the
    // conclusion OF the bullets, so it lives with them and is separated by a
    // rule rather than by a paragraph break.
    await mountPopulation(context);

    await screen.findByText(/What this comparison cannot account for/);
    const close = screen.getByText(/educational information, not a medical assessment/);
    expect(close.className).toContain('notes__close');
    expect(close.closest('.notes')).toBe(document.querySelector('.notes'));
  });

  it('still shows the disclaimer when there are no limitations to list', async () => {
    // The panel is rendered when EITHER exists. A disclaimer that disappears
    // because the limitations array came back empty would be an absence
    // created by a layout condition.
    await mountPopulation({ ...context, limitations: [] });

    const close = await screen.findByText(/educational information, not a medical assessment/);
    expect(close.closest('.notes')).not.toBeNull();
    expect(screen.queryByText(/What this comparison cannot account for/)).not.toBeInTheDocument();
  });

  it('uses the SHARED row style, not a second copy of it', async () => {
    // The dashboard's guidance list and this one are the same shape. They
    // share `.bullets`; two copies is how they drift, and this file has
    // already paid for that once with two `.nav` blocks.
    await mountPopulation(context);

    await screen.findByText(/What this comparison cannot account for/);
    expect(document.querySelector('.notes ul').className).toContain('bullets');
  });
});

/**
 * THE REPEATED SENTENCES, AND WHERE THEY WENT.
 *
 * Measured on the live payload before any of this was written: seven
 * comparison cards, each carrying "Compared with: 20-29 years, male"
 * (byte-identical across all seven) plus two sentences that were "unique"
 * only because the parameter name was interpolated into one template. That is
 * twenty-one lines saying three things.
 *
 * They are hoisted, not deleted -- and the caveat among them is now read
 * BEFORE the first band rather than after each one, which is better
 * placement and not merely less of it (section 6ag: what may never go is the
 * caveat).
 */
describe('the population page, without the repetition', () => {
  const comparison = (name, cohort) => ({
    available: true,
    comparison: {
      value: 5.2,
      unit: '%',
      cohort: cohort || { age_band_label: '20-29 years', sex: 'male' },
      band: {
        position: 'between_published_percentiles',
        lower_percentile: 50,
        upper_percentile: 75,
        lower_value: 5.2,
        upper_value: 5.4,
        label: 'between the 50th and the 75th percentile',
      },
      what_this_means: `Of people of this age and sex in the survey, this is the share whose ${name} was at or below yours.`,
      what_this_does_not_mean: `This does not say whether your ${name} is normal, high, or low.`,
    },
  });

  it('states the cohort ONCE when every comparison shares it', async () => {
    await mountPopulation({
      features: { hba1c: comparison('HbA1c'), hemoglobin: comparison('haemoglobin') },
      limitations: [],
    });

    await screen.findByText(/Each bar below shows/);
    // Once on the page, in the method statement -- and not repeated per card.
    expect(screen.getAllByText(/20-29 years, male/)).toHaveLength(1);
    expect(screen.queryByText(/^Compared with:/)).not.toBeInTheDocument();
  });

  it('drops each card back to its OWN cohort line when they differ', async () => {
    // THE GUARD THAT MATTERS, and it is clinical rather than cosmetic.
    // Module 31 matches on (sex, age band). One line above the list saying
    // "20-29 years" over a card compared against 30-39 would misstate which
    // population the reader is being measured against.
    await mountPopulation({
      features: {
        hba1c: comparison('HbA1c'),
        hemoglobin: comparison('haemoglobin', {
          age_band_label: '30-39 years',
          sex: 'male',
        }),
      },
      limitations: [],
    });

    await screen.findByText(/Each bar below shows/);
    expect(screen.getByText(/Compared with: 20-29 years/)).toBeInTheDocument();
    expect(screen.getByText(/Compared with: 30-39 years/)).toBeInTheDocument();
    // ...and the hoisted clause does not name a cohort it cannot vouch for.
    expect(screen.getByText(/Each bar below shows/).textContent)
      .not.toMatch(/20-29 years/);
  });

  it('keeps the caveat, once, and NOT in the page’s quietest type', async () => {
    // It used to appear seven times. Reducing it to one copy is only safe if
    // that copy is prominent: demoting the sole surviving caveat to `.hint`
    // is how a caveat stops being read.
    await mountPopulation({
      features: { hba1c: comparison('HbA1c') },
      limitations: [],
    });

    const method = await screen.findByText(/Each bar below shows/);
    expect(method.className).toContain('method');
    expect(method.className).not.toContain('hint');
    expect(method.textContent).toMatch(/does not say whether a result is normal, high, or low/);
  });

  it('draws a bar for each comparison and none for a refusal', async () => {
    await mountPopulation({
      features: {
        hba1c: comparison('HbA1c'),
        blood_glucose: {
          available: false,
          reason_code: 'NO_VERIFIED_DISTRIBUTION',
          message: 'No population comparison is offered for blood glucose.',
        },
      },
      limitations: [],
    });

    await screen.findByText(/Each bar below shows/);
    expect(document.querySelectorAll('.pctbar')).toHaveLength(1);
    // The refusal is still stated in the service's own words.
    expect(screen.getByText(/No population comparison is offered/)).toBeInTheDocument();
  });

  it('says nothing about bars when no comparison was made at all', async () => {
    // A method statement describing bars, above a page with no bars, is the
    // "shaded band = usual range" legend over a chart with no band (6ac).
    await mountPopulation({
      features: {
        blood_glucose: {
          available: false,
          reason_code: 'NO_VERIFIED_DISTRIBUTION',
          message: 'No population comparison is offered for blood glucose.',
        },
      },
      limitations: [],
    });

    await screen.findByText(/No population comparison is offered/);
    expect(screen.queryByText(/Each bar below shows/)).not.toBeInTheDocument();
  });
});

/**
 * Module 32 -- the parameters the laboratory reported and this tool skips.
 *
 * THE DEFECT THIS SECTION EXISTS FOR. The clinician document listed the four
 * values this platform ASSESSES under the words "The reported values are", on
 * a report carrying twenty-one. The seventeen omitted included a CRP of 12.1,
 * an SGPT of 101.9 and an ESR of 35. A clinician reads that sentence as the
 * panel.
 *
 * The narrative now states the COUNT; this table is the list behind it.
 */
/**
 * The out-of-range sentence, as one string.
 *
 * It is a PARAGRAPH now, not a table: the reader asked for these as ordinary
 * prose. Asserting on cell text no longer means anything, so every check here
 * reads the sentence and looks for the facts inside it.
 */
async function outOfRangeLine() {
  await waitFor(() =>
    expect(document.querySelector('.passage__outofrange')).toBeTruthy()
  );
  return document.querySelector('.passage__outofrange').textContent;
}

describe('Module 32 - reported, not assessed', () => {
  const MINIMAL = {
    overall: { status_label: 'Needs Medical Attention', clean_bill_of_health: false },
    attribution: { report_date: '2026-09-07T04:00:14.776000Z' },
    patient: { age: 20, gender: 'male' },
    data_quality: { page_count: 4, pages_unreadable: [], partial_document: false },
    laboratory: { total: 0, rows: [] },
    assessments: [],
  };

  const UNASSESSED = {
    count: 3,
    labFlaggedCount: 2,
    descriptionsPresent: false,
    describedCount: 0,
    withheldCount: 0,
    items: [
      {
        testName: 'CRP (C-REACTIVE PROTEIN)',
        value: '12.1',
        unit: 'mg/L',
        labFlag: 'high',
        labFlaggedAbnormal: true,
        labReferenceLow: 0,
        labReferenceHigh: 6,
      },
      {
        testName: 'SGPT',
        value: '101.9',
        unit: 'U/L',
        labFlag: 'high',
        labFlaggedAbnormal: true,
        labReferenceHigh: 50,
      },
      {
        testName: 'ESR',
        value: '35',
        unit: 'mm/hr',
        labFlag: 'normal',
        labFlaggedAbnormal: false,
      },
    ],
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('shows the out-of-range parameters with their values and units', async () => {
    mountSummary(MINIMAL, {}, null, UNASSESSED);
    const line = await outOfRangeLine();
    // TWO of the three, because ESR is flagged `normal` by the laboratory.
    expect(line).toContain('CRP (C-REACTIVE PROTEIN) 12.1 mg/L');
    expect(line).toContain('SGPT 101.9 U/L');
  });

  it('leaves out a parameter the laboratory did NOT mark', async () => {
    mountSummary(MINIMAL, {}, null, UNASSESSED);
    const line = await outOfRangeLine();
    // ESR is present in the payload and flagged "normal". It is not out of
    // range and must not be listed as though it were.
    expect(line).not.toContain('ESR');
    expect(line).not.toContain('35 mm/hr');
  });

  it('says nothing about what this tool did or did not assess', async () => {
    // THE READER'S INSTRUCTION: present them as out of range, and do not
    // label the section by this platform's coverage. A clinician wants the
    // results, not a statement about our scope.
    mountSummary(MINIMAL, {}, null, UNASSESSED);
    await outOfRangeLine();
    const page = document.body.textContent.toLowerCase();
    for (const banned of [
      'not assessed',
      'does not assess',
      'set aside',
      'not found normal',
      'no assessment rule',
    ]) {
      expect(page).not.toContain(banned);
    }
  });

  it("states the fact and NOT an agent, because the agent is not known", async () => {
    /* THIS TEST ASSERTED THE OPPOSITE AND WAS WRONG ABOUT THE WORLD.
       It pinned "marked outside the reference interval by the laboratory",
       and the page said exactly that -- in bold, on the document a clinician
       reads. Reading `Test 3.pdf` on 2026-09-18 showed that laboratory prints
       FOUR COLUMNS and not one H, L or asterisk on either page, including
       beside NEUTROPHILS 82 against 40-70. All four rows under that heading
       had been inferred by a model from the printed interval.

       Module 4's contract sets `flag` when the report states it OR when the
       range makes the comparison unambiguous, and the stored row cannot tell
       the two apart. So the heading now states what IS checkable from this
       page -- the value against the interval beside it -- and one sentence
       says plainly that which of the two it was is not recorded.

       REPLACED, NOT WEAKENED: the old assertion is inverted below, so the
       false attribution cannot come back without failing a test. */
    mountSummary(MINIMAL, {}, null, UNASSESSED);
    const line = await outOfRangeLine();

    expect(line).toMatch(/outside the reference interval printed on the report/i);
    expect(line).not.toMatch(/by the laboratory/i);
    // The ambiguity, named rather than resolved in the flattering direction.
    expect(line).toMatch(/this tool does not record which/i);

    // The printed interval, and the one-sided form when only a limit exists.
    expect(line).toContain('0\u20136');
    expect(line).toContain('\u2264 50');
  });

  it('renders nothing when the laboratory marked none of them', async () => {
    mountSummary(MINIMAL, {}, null, { count: 0, items: [], labFlaggedCount: 0 });
    await waitFor(() => expect(document.querySelector('.passage')).toBeTruthy());
    expect(document.querySelector('.passage__outofrange')).toBeNull();
  });

  it('renders nothing when every skipped parameter is in range', async () => {
    // A SECTION HEADED "Out of range" MUST NOT APPEAR OVER AN EMPTY TABLE.
    mountSummary(MINIMAL, {}, null, {
      count: 1,
      labFlaggedCount: 0,
      items: [
        { testName: 'MCV', value: '85.1', unit: 'fL', labFlag: 'normal', labFlaggedAbnormal: false },
      ],
    });
    await waitFor(() => expect(document.querySelector('.passage')).toBeTruthy());
    expect(document.querySelector('.passage__outofrange')).toBeNull();
  });

  it('renders nothing when the section is absent from the payload', async () => {
    // An older analysis has no section. Absent and empty both render nothing,
    // and neither may invent a claim that something was skipped.
    mountSummary(MINIMAL, {}, null, undefined);
    await waitFor(() => expect(document.querySelector('.passage')).toBeTruthy());
    expect(document.querySelector('.passage__outofrange')).toBeNull();
  });
});

/**
 * Module 32 -- THE SECTIONS THAT ARE NOT PART OF THE NARRATIVE.
 *
 * THE DEFECT: this page is a ternary -- the written narrative, OR the composed
 * passage -- and the Module 34 context blocks and the unassessed table both
 * sat inside the ELSE. They rendered only when the narrative FAILED.
 *
 * The block's own comment said "outside everything the narrative may rewrite",
 * which was the intent and not the code. It stayed invisible while the
 * narrative was usually refused; the moment it generated reliably, both
 * sections vanished and the reader asked where they had gone.
 *
 * Every existing test on this page mounts with `narrative: null`, so all of
 * them exercised the branch that worked.
 */
describe('Module 32 - the out-of-range line survives a generated narrative', () => {
  const MINIMAL = {
    overall: { status_label: 'Needs Medical Attention', clean_bill_of_health: false },
    attribution: { report_date: '2026-09-07T04:00:14.776000Z' },
    patient: { age: 20, gender: 'male' },
    data_quality: { page_count: 2, pages_unreadable: [], partial_document: false },
    // A ROW THE LABORATORY ITSELF MARKED. The context effect derives its
    // findings from printed_flag, so a fixture with no rows never asks and
    // the test would pass with the section absent for the wrong reason.
    laboratory: {
      total: 1,
      rows: [
        {
          feature: 'neutrophils',
          display_name: 'Neutrophils',
          value: 78,
          unit: '%',
          usable: true,
          printed_flag: 'high',
          provenance: {
            source: 'lab_report',
            original_test_name: { text: 'NEUTROPHILS', state: 'CLEAN' },
          },
        },
      ],
    },
    assessments: [],
  };

  const UNASSESSED = {
    count: 1,
    labFlaggedCount: 1,
    items: [
      {
        testName: 'CRP (C-REACTIVE PROTEIN)',
        value: '12.1',
        unit: 'mg/L',
        labFlag: 'high',
        labFlaggedAbnormal: true,
        labReferenceLow: 0,
        labReferenceHigh: 6,
      },
    ],
  };

  const NARRATIVE = {
    outcome: 'generated',
    text: 'This tool flagged Diabetes because HbA1c was 7 %.',
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders inside the passage when a narrative WAS generated', async () => {
    mountSummary(MINIMAL, {}, NARRATIVE, UNASSESSED);
    await screen.findByText(/This tool flagged Diabetes/);
    const line = await outOfRangeLine();
    expect(line).toContain('CRP (C-REACTIVE PROTEIN) 12.1 mg/L');
  });

  it('still renders it when there is NO narrative', async () => {
    mountSummary(MINIMAL, {}, null, UNASSESSED);
    expect(await outOfRangeLine()).toContain('CRP (C-REACTIVE PROTEIN)');
  });
});

describe('Module 32 - no model caveat, and the WHY survives', () => {
  /* ======================================================================
     THIS WHOLE BLOCK ONCE ASSERTED THE MODEL CAVEAT WAS PRESENT
     ======================================================================

     It was written for 6az's defect: every model qualification vanished from
     this page the moment Gemini began generating reliably, because the block
     lived inside the composed branch. Its tests therefore asserted the caveat
     rendered in BOTH branches, and a later set asserted the hit and miss
     rates it carried.

     THE OWNER REMOVED THE PARAGRAPH ON 2026-09-20, having read it on the real
     page twice: "just show what parameters are there in report and what
     flagged and why flagged, that's it ... i don't need words like model and
     output". Every test that asserted its presence can now be satisfied only
     by reintroducing it, so they are REPLACED here rather than weakened, and
     the reason is written down because this reverses a constraint 6w marks
     non-negotiable.

     WHAT IS ASSERTED INSTEAD is the half of 6az that still holds and that the
     owner explicitly wants: the WHY of a flag must survive in BOTH branches.
     That was the real lesson -- a fact that renders in only one branch
     disappears the day the other branch starts working. */

  const WITH_MODEL = {
    overall: { status_label: 'Needs Medical Attention', clean_bill_of_health: false },
    attribution: { report_date: '2026-09-07T04:00:14.776000Z' },
    patient: { age: 20, gender: 'male' },
    data_quality: { page_count: 2, pages_unreadable: [], partial_document: false },
    laboratory: {
      total: 1,
      rows: [
        {
          feature: 'creatinine',
          display_name: 'Serum creatinine',
          value: 0.75,
          unit: 'mg/dl',
          usable: true,
          provenance: {
            source: 'lab_report',
            original_test_name: { text: 'Serum Creatinine', state: 'CLEAN' },
          },
        },
      ],
    },
    abnormal_findings: ['Kidney Disease'],
    assessments: [
      {
        condition: 'Kidney Disease',
        status: 'Indicated',
        assessed: true,
        bases: [
          { status: 'Not Indicated', assessed: true, source_kind: 'clinical_rule' },
          {
            status: 'Indicated',
            assessed: true,
            source_kind: 'machine_learning',
            //: The real artifact values. Nothing derived from them may reach
            //: the page any more, and that is what these tests check.
            ml: {
              limitations: {
                metrics_available: true,
                roc_auc: 0.9987129987129988,
                precision_at_operating_threshold: 0.968421052631579,
                recall_at_operating_threshold: 0.983957219251337,
              },
            },
          },
        ],
      },
    ],
  };

  /* THE PRODUCER ALWAYS APPENDS THE CLOSING LINE.
     `write_clinician_summary` ends with `parts = [approved_text, CLOSING_LINE]`
     and joins them, so every generated narrative carries it as the final
     paragraph -- all four stored on this account do. A fixture without it
     describes a state the ai-service cannot produce. */
  const NARRATIVE = {
    outcome: 'generated',
    text:
      'Kidney Disease was flagged by the statistical model alone, and no '
      + 'measured value crossed a cut-off for it.\n\n'
      + 'Not a diagnosis and not a clinical conclusion. The original '
      + 'laboratory report remains the primary record.',
  };

  const passageText = async () => {
    await waitFor(() => expect(document.querySelector('.passage')).toBeTruthy());
    return document.querySelector('.passage').textContent;
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('shows no model-output paragraph WHEN A NARRATIVE WAS GENERATED', async () => {
    mountSummary(WITH_MODEL, {}, NARRATIVE, null);
    const text = await passageText();
    expect(text).not.toMatch(/On the model output/i);
    expect(text).not.toMatch(/an estimate from patterns/i);
  });

  it('shows no model-output paragraph WHEN THERE IS NO NARRATIVE', async () => {
    // BOTH BRANCHES, which is 6az's lesson kept pointing the other way: a
    // difference between the branches is what went unnoticed for weeks.
    mountSummary(WITH_MODEL, {}, null, null);
    const text = await passageText();
    expect(text).not.toMatch(/On the model output/i);
    expect(text).not.toMatch(/an estimate from patterns/i);
  });

  it('leaks no model performance figure into the narrative branch', async () => {
    mountSummary(WITH_MODEL, {}, NARRATIVE, null);
    const text = await passageText();
    for (const jargon of ['AUC', '0.99', '0.97', '0.98', 'Random Forest']) {
      expect(text).not.toContain(jargon);
    }
    expect(text).not.toMatch(/\d+ in \d+ of the patients/);
    expect(text).not.toMatch(/missed about/);
  });

  it('leaks no model performance figure into the composed branch', async () => {
    mountSummary(WITH_MODEL, {}, null, null);
    const text = await passageText();
    for (const jargon of ['AUC', '0.99', '0.97', '0.98', 'Random Forest']) {
      expect(text).not.toContain(jargon);
    }
    expect(text).not.toMatch(/\d+ in \d+ of the patients/);
    expect(text).not.toMatch(/missed about/);
  });

  it('still says WHY in the narrative branch', async () => {
    /* THE OWNER'S SPEC AND THE CONDITION ON REMOVING THE PARAGRAPH. A flag
       with no reason is a worse document than one with a caveat too many. */
    mountSummary(WITH_MODEL, {}, NARRATIVE, null);
    expect(await passageText()).toMatch(/no measured value crossed a cut-off/);
  });

  it('still says WHY in the composed branch', async () => {
    mountSummary(WITH_MODEL, {}, null, null);
    expect(await passageText()).toMatch(/no measured value crossed a cut-off/);
  });

  it('still gives the parameter and its value', async () => {
    // ASKED FOR EXPLICITLY on 2026-09-20, alongside the removal: the summary
    // must carry what parameters are in the report and what they read.
    mountSummary(WITH_MODEL, {}, NARRATIVE, null);
    expect(await passageText()).toMatch(/Serum Creatinine 0\.75 mg\/dl/);
  });

  it('closes the document last, exactly once', async () => {
    /* `CLOSING_LINE` is appended server-side and so arrived as the last
       paragraph of the narrative, leaving the page to print its own caveats
       AFTER it: the document ended, then kept talking. */
    mountSummary(WITH_MODEL, {}, NARRATIVE, null);
    await waitFor(() => expect(document.querySelector('.passage')).toBeTruthy());
    const paras = [...document.querySelectorAll('.passage p')].map((p) => p.textContent);
    const closing = paras.filter((t) => /remains the primary record/.test(t));
    expect(closing).toHaveLength(1);
    const closingAt = paras.findIndex((t) => /remains the primary record/.test(t));
    expect(closingAt).toBe(paras.length - 1);
  });

  /* ====================================================================
     ONE VALUE LIST, NEVER TWO AND NEVER NONE
     ====================================================================

     The reported values were made to render in both branches so a clinician
     stops losing every parameter that was measured and not flagged. On a
     report whose narrative ALSO enumerates them that printed the same panel
     twice, four paragraphs apart -- 6bf's out-of-range defect in a second
     place, found by the owner on the real page the same day.

     ⚠ THE NARRATIVE ENUMERATES THEM ONLY SOMETIMES, from identical code:
     `required_values` is `trigger_values`, so the full panel is asked for in
     the prompt and never enforced by the fact check. Both fixtures below are
     therefore states the producer really reaches, and both are asserted --
     deleting either side of this would reintroduce the other's bug. */

  const VALUES_REPORT = {
    overall: { status_label: 'Needs Medical Attention', clean_bill_of_health: false },
    attribution: { report_date: '2026-09-07T04:00:14.776000Z' },
    patient: { age: 20, gender: 'male' },
    data_quality: { page_count: 1, pages_unreadable: [], partial_document: false },
    laboratory: {
      total: 2,
      rows: [
        {
          feature: 'hba1c',
          display_name: 'Glycated haemoglobin',
          value: 5.2,
          unit: '%',
          usable: true,
          provenance: {
            source: 'lab_report',
            original_test_name: { text: 'Glycated Haemoglobin (HbA1c)', state: 'CLEAN' },
          },
        },
        {
          feature: 'cholesterol',
          display_name: 'Total cholesterol',
          value: 172,
          unit: 'mg/dl',
          usable: true,
          provenance: {
            source: 'lab_report',
            original_test_name: { text: 'Cholesterol, Total', state: 'CLEAN' },
          },
        },
      ],
    },
    abnormal_findings: [],
    assessments: [],
  };

  const CLOSING =
    'Not a diagnosis and not a clinical conclusion. The original laboratory '
    + 'report remains the primary record.';

  const countOf = (needle) =>
    [...document.querySelectorAll('.passage p')].filter((p) =>
      p.textContent.includes(needle)
    ).length;

  it('prints the values once when the narrative already listed them all', async () => {
    /* THE DEFECT, VERBATIM. The narrative's own sentence is built by
       `_value_strings`, which uses the same printed name, value and unit this
       page does -- so the two lists were character-identical. */
    const listing = {
      outcome: 'generated',
      text:
        'The reported values are Glycated Haemoglobin (HbA1c) 5.2 %, and '
        + 'Cholesterol, Total 172 mg/dl.\n\n'
        + CLOSING,
    };
    mountSummary(VALUES_REPORT, {}, listing, null);
    await waitFor(() => expect(document.querySelector('.passage')).toBeTruthy());
    expect(countOf('Glycated Haemoglobin (HbA1c) 5.2 %')).toBe(1);
    expect(countOf('Cholesterol, Total 172 mg/dl')).toBe(1);
    // The page's own paragraph is the one that stood down.
    expect(document.querySelector('.passage').textContent).not.toMatch(/Reported values\./);
  });

  it('prints the values itself when the narrative listed none of them', async () => {
    // The regenerated 03-renal narrative is exactly this: it explains the
    // flags and never enumerates the panel. Without the page's list a
    // clinician sees no value for anything that was not flagged.
    const silent = {
      outcome: 'generated',
      text: 'This tool flagged nothing on this report.\n\n' + CLOSING,
    };
    mountSummary(VALUES_REPORT, {}, silent, null);
    await waitFor(() => expect(document.querySelector('.passage')).toBeTruthy());
    expect(document.querySelector('.passage').textContent).toMatch(/Reported values\./);
    expect(countOf('Glycated Haemoglobin (HbA1c) 5.2 %')).toBe(1);
    expect(countOf('Cholesterol, Total 172 mg/dl')).toBe(1);
  });

  it('prints its own list when the narrative names only SOME of the values', async () => {
    /* A PARTIAL MATCH IS NOT A LIST. A narrative that names one value inside
       a "flagged X because Y was Z" sentence has explained a flag, not
       published the panel, and the complete list still belongs on the page.
       Suppressing on a partial match would drop every value the narrative
       did not happen to mention -- the omission bug wearing the other hat. */
    const partial = {
      outcome: 'generated',
      text:
        'This tool flagged nothing, though Glycated Haemoglobin (HbA1c) 5.2 % '
        + 'was noted.\n\n'
        + CLOSING,
    };
    mountSummary(VALUES_REPORT, {}, partial, null);
    await waitFor(() => expect(document.querySelector('.passage')).toBeTruthy());
    expect(document.querySelector('.passage').textContent).toMatch(/Reported values\./);
    // Cholesterol appears nowhere else, so it must come from the page's list.
    expect(countOf('Cholesterol, Total 172 mg/dl')).toBe(1);
  });

  it('leaves an unrecognised closing line where it is, rather than losing it', async () => {
    /* FAIL-SAFE, NOT FAIL-SILENT. If the ai-service rewords `CLOSING_LINE`,
       the page must not drop the sentence and must not print it twice. */
    const reworded = {
      ...NARRATIVE,
      text: 'A body paragraph.\n\nSome NEW closing wording entirely.',
    };
    mountSummary(WITH_MODEL, {}, reworded, null);
    await waitFor(() => expect(document.querySelector('.passage')).toBeTruthy());
    const paras = [...document.querySelectorAll('.passage p')].map((p) => p.textContent);
    expect(paras.filter((t) => /Some NEW closing wording entirely/.test(t))).toHaveLength(1);
  });
});
