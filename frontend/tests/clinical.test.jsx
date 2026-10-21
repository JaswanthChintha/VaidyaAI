import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import DoctorSummary from '../src/pages/DoctorSummary';
import Population from '../src/pages/Population';
import { api } from '../src/lib/api';


function mountSummary(doctorSummary, history, narrative, unassessed) {
  vi.spyOn(api, 'getDoctorSummary').mockResolvedValue({
    report: { originalName: 'r.pdf' },
    history: history || {},
    doctorSummary,
    narrative: narrative ?? null,
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
    expect(passage()).toMatch(/HbA1C \(Glycosylated Haemoglobin\) 8\.4 %/);
    expect(passage()).toMatch(/Serum Creatinine 1\.1 mg\/dl/);
  });

  it('never lets bare numbers read as in range', async () => {
    await mountSummary(REPORT);
    await screen.findByText(/Reported values/);
    expect(passage()).toMatch(/printed no reference intervals/);
    expect(passage()).toMatch(/no value here is placed relative to a range/);
  });

  it('SAYS WHEN ONLY THE MODEL FLAGGED SOMETHING', async () => {
    await mountSummary(REPORT);
    await screen.findByText(/Flagged/);
    expect(passage()).toMatch(
      /Kidney Disease was flagged by the statistical model alone/
    );
    expect(passage()).toMatch(/no measured value crossed a cut-off/);
    expect(passage()).toMatch(/Diabetes .*crossed one of this tool's cut-offs/);
  });


  it('shows no model-output paragraph at all', async () => {
    await mountSummary(REPORT);
    await screen.findByText(/Flagged/);
    expect(passage()).not.toMatch(/On the model output/i);
    expect(passage()).not.toMatch(/an estimate from patterns/i);
    expect(passage()).not.toMatch(/not a measurement of this patient/i);
  });

  it('puts no model performance figure in front of a clinician', async () => {
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
    await mountSummary({
      ...REPORT,
      data_quality: { page_count: 1, pages_unreadable: [], partial_document: false, sources_failed: [] },
    });
    await screen.findByText(/Flagged/);
    expect(passage()).not.toMatch(/Not fully read/);
  });

  it('⚠ never lists an UNASSESSED condition as "Assessed, not flagged"', async () => {
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
    expect(text).toMatch(/Assessed, not flagged\..*Heart Disease/);
    expect(text).not.toMatch(/Vitamin D Deficiency/);
  });

  it('drops the "Assessed, not flagged" line when nothing was assessed and clear', async () => {
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
    await mountSummary({
      ...REPORT,
      data_quality: { page_count: 1, pages_unreadable: [], partial_document: false, sources_failed: [] },
    });
    await screen.findByText(/Flagged/);
    expect(passage()).toMatch(/were not supplied and (were )?unavailable to the analysis/);
  });

  describe('the written version', () => {
    const WRITTEN = {
      outcome: 'generated',
      text: 'First written paragraph about the results.\n\nSecond written paragraph.',
    };

    it('breaks paragraphs on a double space as well as a blank line', async () => {
      await mountSummary(REPORT, undefined, {
        outcome: 'generated',
        text: 'First group ends here.  Second group starts here.',
      });
      await screen.findByText(/First group ends here/);
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
      expect(screen.getByText(/Reported values/)).toBeInTheDocument();
      expect(screen.queryByText(/^Flagged\.$/)).not.toBeInTheDocument();
    });

    it('says a model wrote the wording, and that it did not decide anything', async () => {
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
    expect(passage()).not.toMatch(/9999/);
    expect(passage()).toMatch(/Vitamin D did not pass validation/);
  });
});

describe('Module 31 -- population context', () => {

  it('keeps a card for a refusal a reader would wonder about', async () => {
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
    expect(document.querySelectorAll('.population__entry')).toHaveLength(0);
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
    expect(screen.queryByText('SEX_COHORT_NOT_AVAILABLE')).toBeNull();
    expect(document.querySelector('[data-reason="SEX_COHORT_NOT_AVAILABLE"]')).toBeTruthy();
    expect(screen.getByText('No comparison offered')).toBeInTheDocument();
  });

  it('shows no percentile at all on an unavailable entry', async () => {
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
    expect(screen.getByText(/at or below yours/)).toBeInTheDocument();
    expect(screen.getByText(/does not say whether/)).toBeInTheDocument();
  });

  it('tells the patient which missing profile answer to act on', async () => {
    await mountPopulation(
      { features: {} },
      { profileExists: true, ageProvided: true, genderProvided: false }
    );

    expect(await screen.findByText(/missing gender/)).toBeInTheDocument();
    expect(screen.getByText('Update your details')).toBeInTheDocument();
  });
});

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
    expect(panel.tagName).not.toBe('DETAILS');
    expect(panel.querySelector('details')).toBeNull();
    expect(panel.querySelectorAll('.bullets > li')).toHaveLength(2);
  });

  it('keeps the closing disclaimer inside the same panel, divided off', async () => {
    await mountPopulation(context);

    await screen.findByText(/What this comparison cannot account for/);
    const close = screen.getByText(/educational information, not a medical assessment/);
    expect(close.className).toContain('notes__close');
    expect(close.closest('.notes')).toBe(document.querySelector('.notes'));
  });

  it('still shows the disclaimer when there are no limitations to list', async () => {
    await mountPopulation({ ...context, limitations: [] });

    const close = await screen.findByText(/educational information, not a medical assessment/);
    expect(close.closest('.notes')).not.toBeNull();
    expect(screen.queryByText(/What this comparison cannot account for/)).not.toBeInTheDocument();
  });

  it('uses the SHARED row style, not a second copy of it', async () => {
    await mountPopulation(context);

    await screen.findByText(/What this comparison cannot account for/);
    expect(document.querySelector('.notes ul').className).toContain('bullets');
  });
});

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
    expect(screen.getAllByText(/20-29 years, male/)).toHaveLength(1);
    expect(screen.queryByText(/^Compared with:/)).not.toBeInTheDocument();
  });

  it('drops each card back to its OWN cohort line when they differ', async () => {
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
    expect(screen.getByText(/Each bar below shows/).textContent)
      .not.toMatch(/20-29 years/);
  });

  it('keeps the caveat, once, and NOT in the page’s quietest type', async () => {
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
    expect(screen.getByText(/No population comparison is offered/)).toBeInTheDocument();
  });

  it('says nothing about bars when no comparison was made at all', async () => {
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
    expect(line).toContain('CRP (C-REACTIVE PROTEIN) 12.1 mg/L');
    expect(line).toContain('SGPT 101.9 U/L');
  });

  it('leaves out a parameter the laboratory did NOT mark', async () => {
    mountSummary(MINIMAL, {}, null, UNASSESSED);
    const line = await outOfRangeLine();
    expect(line).not.toContain('ESR');
    expect(line).not.toContain('35 mm/hr');
  });

  it('says nothing about what this tool did or did not assess', async () => {
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
    mountSummary(MINIMAL, {}, null, UNASSESSED);
    const line = await outOfRangeLine();

    expect(line).toMatch(/outside the reference interval printed on the report/i);
    expect(line).not.toMatch(/by the laboratory/i);
    expect(line).toMatch(/this tool does not record which/i);

    expect(line).toContain('0\u20136');
    expect(line).toContain('\u2264 50');
  });

  it('renders nothing when the laboratory marked none of them', async () => {
    mountSummary(MINIMAL, {}, null, { count: 0, items: [], labFlaggedCount: 0 });
    await waitFor(() => expect(document.querySelector('.passage')).toBeTruthy());
    expect(document.querySelector('.passage__outofrange')).toBeNull();
  });

  it('renders nothing when every skipped parameter is in range', async () => {
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
    mountSummary(MINIMAL, {}, null, undefined);
    await waitFor(() => expect(document.querySelector('.passage')).toBeTruthy());
    expect(document.querySelector('.passage__outofrange')).toBeNull();
  });
});

describe('Module 32 - the out-of-range line survives a generated narrative', () => {
  const MINIMAL = {
    overall: { status_label: 'Needs Medical Attention', clean_bill_of_health: false },
    attribution: { report_date: '2026-09-07T04:00:14.776000Z' },
    patient: { age: 20, gender: 'male' },
    data_quality: { page_count: 2, pages_unreadable: [], partial_document: false },
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
    mountSummary(WITH_MODEL, {}, NARRATIVE, null);
    expect(await passageText()).toMatch(/no measured value crossed a cut-off/);
  });

  it('still says WHY in the composed branch', async () => {
    mountSummary(WITH_MODEL, {}, null, null);
    expect(await passageText()).toMatch(/no measured value crossed a cut-off/);
  });

  it('still gives the parameter and its value', async () => {
    mountSummary(WITH_MODEL, {}, NARRATIVE, null);
    expect(await passageText()).toMatch(/Serum Creatinine 0\.75 mg\/dl/);
  });

  it('closes the document last, exactly once', async () => {
    mountSummary(WITH_MODEL, {}, NARRATIVE, null);
    await waitFor(() => expect(document.querySelector('.passage')).toBeTruthy());
    const paras = [...document.querySelectorAll('.passage p')].map((p) => p.textContent);
    const closing = paras.filter((t) => /remains the primary record/.test(t));
    expect(closing).toHaveLength(1);
    const closingAt = paras.findIndex((t) => /remains the primary record/.test(t));
    expect(closingAt).toBe(paras.length - 1);
  });


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
    expect(document.querySelector('.passage').textContent).not.toMatch(/Reported values\./);
  });

  it('prints the values itself when the narrative listed none of them', async () => {
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
    expect(countOf('Cholesterol, Total 172 mg/dl')).toBe(1);
  });

  it('leaves an unrecognised closing line where it is, rather than losing it', async () => {
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
