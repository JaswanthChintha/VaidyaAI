import { render, screen } from '@testing-library/react';
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

function mountSummary(doctorSummary, history) {
  vi.spyOn(api, 'getDoctorSummary').mockResolvedValue({
    report: { originalName: 'r.pdf' },
    history: history || {},
    doctorSummary,
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
                author_note: { text: 'A ROC-AUC near 0.99 says the separation was easy, not that this would hold on a screening population.' },
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
    expect(passage()).toMatch(
      /Kidney Disease was flagged by the statistical model only/
    );
    expect(passage()).toMatch(/no measured value crossed a configured threshold/);
    // And a rule-flagged topic is not described that way.
    expect(passage()).toMatch(/configured cut-offs flagged Diabetes/);
  });

  it('carries one sentence of model limitation, in the author own words', async () => {
    // Found missing from this page three separate times (6o D8, 6p, and the
    // `basis.ml.limitations` path bug).
    await mountSummary(REPORT);
    await screen.findByText(/Flagged/);
    expect(passage()).toMatch(/not a measurement/);
    expect(passage()).toMatch(/says the separation was easy/);
  });

  it('omits the model paragraph entirely when no model flagged anything', async () => {
    await mountSummary({
      ...REPORT,
      abnormal_findings: ['Diabetes'],
      assessments: [REPORT.assessments[0], REPORT.assessments[2]],
    });
    await screen.findByText(/Flagged/);
    expect(passage()).not.toMatch(/statistical model only/);
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
    expect(passage()).toMatch(/No topic crossed a configured threshold/);
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
