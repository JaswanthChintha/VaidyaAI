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

  it('qualifies a model flag in one sentence, and does not pad it', async () => {
    // RENAMED AND NARROWED FROM 'carries one sentence of model limitation, in
    // the author own words'. It asserted /screening population/ -- a phrase
    // from `ml.limitations.author_note`, which is written in PATIENT register
    // and is no longer printed on the clinician page. Keeping that assertion
    // would mean the only way to pass is to put five sentences of lay prose
    // back in front of a doctor, which is the thing the owner objected to on
    // the real page.
    //
    // WHAT MUST NOT BE LOST is why this test existed at all: the
    // qualification went MISSING from this page three separate times (6o D8,
    // 6p, and the `basis.ml.limitations` path bug), and 6az found it gone
    // again. So its presence is still asserted -- only its length changed.
    await mountSummary(REPORT);
    await screen.findByText(/Flagged/);
    const text = passage();
    expect(text).toMatch(/not a measurement/);
    // One sentence, not a paragraph. The author note ran to five, and the
    // phrases below are the ones it and the metrics version brought with them.
    for (const padding of [
      'screening population',
      'flatters',
      'never a finding in itself',
      'Random Forest',
      'AUC',
    ]) {
      expect(text).not.toContain(padding);
    }
  });

  it('does not put model-development vocabulary in front of a clinician', async () => {
    // THE READER IS A CLINICIAN, NOT A MODEL REVIEWER. "ROC-AUC", "recall",
    // "precision", "training rows", "UCI cohort" are how the people who build
    // these things describe them; a clinician handed a patient's phone reads
    // past them, and the model's limits are the part they most need. The notes
    // were rewritten at source (app/ml/heart.py, app/ml/kidney.py) with every
    // fact kept.
    await mountSummary(REPORT);
    await screen.findByText(/Flagged/);
    const text = passage();
    // 'training data' is in the list because of THIS PAGE'S OWN lead-in
    // sentence, not the model's note: "a likelihood derived from patterns in
    // training data" is the same register, written here rather than upstream,
    // and a list that only policed the upstream note let it straight through.
    for (const jargon of [
      'ROC-AUC', 'ROC AUC', 'PR-AUC', 'UCI', 'held-out', 'training data',
      // How this system names its own parts. A clinician reads a handover
      // note, not a description of the software that produced it.
      'Threshold comparison', 'configured threshold', 'configured cut-off',
      "platform's configured",
    ]) {
      expect(text).not.toContain(jargon);
    }
    // AND THE SAME LIST NOW COVERS WHAT REPLACED THE NOTE, BRIEFLY. When the
    // author note was cut, it was first swapped for the model's own figures
    // -- 'Random Forest, p 0.85, high band. AUC 0.97, precision 0.92, recall
    // 0.70'. That is a different wrong register, not a fix, and this test
    // caught it along with the sibling test below that bans 'Random Forest'
    // by name. The vocabulary list is the guard; it is extended, not relaxed.
    for (const jargon of ['AUC', 'precision 0.', 'recall 0.', 'Random Forest']) {
      expect(text).not.toContain(jargon);
    }
    // The substance that survives is the one clinical fact: an estimate is
    // not a measurement. The former assertion here was /screening population/,
    // a phrase of the patient-register note that no longer prints.
    expect(text).toMatch(/not a measurement/);
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

  it('NEVER DROPS AN ABSENCE UNDER COMPRESSION', async () => {
    // The rule the whole codebase is built on, and the one a summary is most
    // likely to lose. Three separate absences, all in the payload.
    await mountSummary({
      ...REPORT,
      unassessed_conditions: ['Vitamin D Deficiency'],
      data_quality: { page_count: 3, pages_unreadable: [2], partial_document: true, sources_failed: [] },
    });
    await screen.findByText(/Not assessed/);
    // Profile fields that were never supplied. Said once, in sentence case.
    expect(passage()).toMatch(/Hypertension, heart disease, smoking history were not supplied/);
    // A condition with no inputs.
    expect(passage()).toMatch(/Vitamin D Deficiency could not be assessed/);
    // NOT repeated as "not present in this report": for these three the two
    // lists hold the same names, and a field the patient never supplied
    // cannot also be a parameter the report failed to carry.
    expect(passage()).not.toMatch(/not present in this report/);
    // A page that could not be read.
    expect(passage()).toMatch(/Part of the document could not be read \(page 2\)/);
    expect(passage()).toMatch(/None of this is a negative finding/);
  });

  it('names a parameter the report lacked that the patient DID supply', async () => {
    // The other half of the pair above: `features_not_present` that is not
    // simply a restatement of the unsupplied profile fields must still be
    // named, or a real gap in the report goes unmentioned.
    await mountSummary({
      ...REPORT,
      patient: { ...REPORT.patient, hypertension: false, heart_disease: false, smoking_history: 'never' },
      laboratory: { ...REPORT.laboratory, features_not_present: ['vitamin_b12'] },
    });
    await screen.findByText(/Not assessed/);
    expect(passage()).toMatch(/Vitamin b12 was not present in this report/);
    expect(passage()).not.toMatch(/were not supplied/);
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
      const paras = [...document.querySelectorAll('.passage p')];
      expect(paras.length).toBeGreaterThanOrEqual(2);
      expect(paras[0].textContent).toBe('First group ends here.');
      expect(paras[1].textContent).toBe('Second group starts here.');
    });

    it('renders the written prose when one was approved', async () => {
      await mountSummary(REPORT, undefined, WRITTEN);
      expect(await screen.findByText(/First written paragraph/)).toBeInTheDocument();
      expect(screen.getByText(/Second written paragraph/)).toBeInTheDocument();
      // The composed passage is NOT also on the page -- two summaries of the
      // same report, differing in wording, is worse than either alone.
      expect(screen.queryByText(/Reported values/)).not.toBeInTheDocument();
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
    expect(body).toMatch(/age, gender and smoking history/);
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
    expect(screen.getByText('SEX_COHORT_NOT_AVAILABLE')).toBeInTheDocument();
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

describe('Module 32 - the model caveat survives a generated narrative', () => {
  /* THE THIRD TIME MODEL LIMITATIONS HAVE GONE MISSING FROM THIS PAGE, and
     the first two were wrong FIELD PATHS (6w, 6o D8). This one was a wrong
     PLACE IN THE TREE: the paragraph sat inside the composed branch, so it
     rendered only when the written narrative FAILED. No fixture could catch
     it -- the data was always present and always correct.

     MEASURED ON A REAL REPORT (Test 3, 2026-09-18). The page said "Kidney
     Disease was flagged by the statistical model alone" and nothing more,
     while the payload carried probability 0.885, risk band `high`, ROC-AUC
     0.999 off 399 rows at 62.7% prevalence, and the note asserted below --
     for a 20-year-old whose creatinine is normal. */

  const NOTE =
    'This came from a pattern model, not from a measurement. It is a reason ' +
    'to consider further assessment, never a finding in itself.';

  const WITH_MODEL = {
    overall: { status_label: 'Needs Medical Attention', clean_bill_of_health: false },
    attribution: { report_date: '2026-09-07T04:00:14.776000Z' },
    patient: { age: 20, gender: 'male' },
    data_quality: { page_count: 2, pages_unreadable: [], partial_document: false },
    laboratory: { total: 0, rows: [] },
    abnormal_findings: ['Kidney Disease'],
    // TWO BASES, AS THE PRODUCER ACTUALLY RETURNS. Read off the live payload
    // rather than imagined: the rule basis says Not Indicated (creatinine
    // 0.75 is normal) and the MODEL basis is the one that flagged. A
    // single-basis fixture would not exercise the skip in `modelNotes`.
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
            ml: { limitations: { author_note: { text: NOTE } } },
          },
        ],
      },
    ],
  };

  const NARRATIVE = {
    outcome: 'generated',
    text: 'Kidney Disease was flagged by the statistical model alone.',
  };

  const modelLine = async () => {
    await waitFor(() => expect(document.querySelector('.passage')).toBeTruthy());
    const match = [...document.querySelectorAll('.passage p')].find((p) =>
      /On the model output/i.test(p.textContent)
    );
    return match ? match.textContent : null;
  };

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  /* THESE THREE ASSERTED THE AUTHOR NOTE'S OWN WORDS AND NOW ASSERT THE
     GUARANTEE THAT MATTERS. 6az's finding was NOT that a particular sentence
     appeared -- it was that EVERY model qualification vanished from the page
     the moment Gemini started generating reliably, because the block lived
     inside the composed branch. That is what is tested here, and it is
     untouched: the line must render whether or not a narrative was produced.

     What changed is the text. `never a finding in itself` is from
     `ml.limitations.author_note`, patient register, cut from this page after
     the owner read five sentences of it on a real report. Asserting it here
     would mean the only way to pass is to put the padding back. */

  it('qualifies the model flag WHEN A NARRATIVE WAS GENERATED', async () => {
    // THE DEFECT, DIRECTLY. This is the state the live page was in.
    mountSummary(WITH_MODEL, {}, NARRATIVE, null);
    await screen.findByText(/flagged by the statistical model alone/);
    const line = await modelLine();
    expect(line).toBeTruthy();
    expect(line).toMatch(/not a measurement of this patient/i);
  });

  it('still qualifies it when there is NO narrative', async () => {
    mountSummary(WITH_MODEL, {}, null, null);
    const line = await modelLine();
    expect(line).toMatch(/not a measurement of this patient/i);
  });

  it('says it in one sentence and imports nothing from the model artifact', async () => {
    // The qualification must not depend on a model having supplied a note --
    // that dependency is how it went missing before -- and it must not grow
    // back into a paragraph. Both halves are asserted, because the page has
    // now failed in both directions: silence when Gemini worked, then padding
    // when the note was wired in.
    mountSummary(WITH_MODEL, {}, NARRATIVE, null);
    const line = await modelLine();
    expect(line).toMatch(/not a measurement of this patient/i);
    expect(line.length).toBeLessThan(200);
    for (const imported of [
      'never a finding in itself',
      'screening population',
      'flatters',
      'Random Forest',
      'AUC',
    ]) {
      expect(line).not.toContain(imported);
    }
  });

  it('omits the paragraph entirely when no model flagged anything', async () => {
    // A model that returned Not Indicated produced no output this passage
    // reports, so its caveat would sit under findings it did not make.
    const ruleOnly = {
      ...WITH_MODEL,
      abnormal_findings: ['Anemia'],
      assessments: [
        {
          condition: 'Anemia',
          status: 'Indicated',
          assessed: true,
          bases: [{ status: 'Indicated', assessed: true, source_kind: 'clinical_rule' }],
        },
      ],
    };
    mountSummary(ruleOnly, {}, NARRATIVE, null);
    await waitFor(() => expect(document.querySelector('.passage')).toBeTruthy());
    expect(await modelLine()).toBeNull();
  });
});
