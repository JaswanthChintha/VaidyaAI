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

describe('Module 32 -- the clinician summary', () => {
  it('shows a model probability WITH its detection rate, never alone', async () => {
    // Module 11 flags ~27% of true positives. A probability quoted without
    // that is actively misleading, and it was a real defect twice.
    await mountSummary({
      overall: { status_label: 'Attention Needed', clean_bill_of_health: false },
      assessments: [
        {
          condition: 'Heart Disease',
          status: 'Indicated',
          assessed: true,
          bases: [
            {
              source: 'Heart model',
              status: 'Indicated',
              ml: { model_name: 'Random Forest', probability: 0.71 },
              limitations: {
                metrics_available: true,
                roc_auc: 0.697,
                recall_at_operating_threshold: 0.2678,
                precision_at_operating_threshold: 0.7496,
                accuracy: 0.5918,
                baseline_accuracy: 0.5003,
                caveats: [
                  'At the operating threshold used here, this model flags a minority of the true positive cases. An unflagged result from this model therefore rules nothing out.',
                ],
              },
            },
          ],
        },
      ],
    });

    expect(await screen.findByText(/probability 0.71/)).toBeInTheDocument();
    expect(screen.getByText(/rules nothing out/)).toBeInTheDocument();
    expect(screen.getByText('0.2678')).toBeInTheDocument();
    expect(screen.getByText('0.7496')).toBeInTheDocument();
  });

  it('states an incomplete performance record rather than letting it read as complete', async () => {
    // Figures present, operating point absent. A clinician reading ROC-AUC
    // alone would assume the missing numbers were unremarkable.
    await mountSummary({
      overall: { status_label: 'Attention Needed' },
      assessments: [
        {
          condition: 'Diabetes',
          status: 'Indicated',
          assessed: true,
          bases: [
            {
              source: 'Diabetes model',
              ml: { model_name: 'Random Forest', probability: 0.8 },
              limitations: {
                metrics_available: true,
                metrics_absent_code: 'METRICS_OPERATING_POINT_INCOMPLETE',
                roc_auc: 0.94,
                recall_at_operating_threshold: null,
                precision_at_operating_threshold: null,
                caveats: [],
              },
            },
          ],
        },
      ],
    });

    expect(
      await screen.findByText('METRICS_OPERATING_POINT_INCOMPLETE')
    ).toBeInTheDocument();
    // The missing numbers are stated as missing, not omitted silently.
    expect(
      screen.getAllByText('Not recorded for this model.').length
    ).toBeGreaterThan(0);
  });

  it('renders a withheld trend section with its reason, never as stability', async () => {
    await mountSummary({
      overall: { status_label: 'Attention Needed' },
      assessments: [],
      trends: {
        present: false,
        reason_code: 'SUBJECT_NOT_IN_HISTORY',
        reason:
          'The report this summary describes is not among the reports supplied as its history, so no trend is shown. This is not a finding of stability.',
      },
    });

    expect(await screen.findByText(/not a finding of stability/)).toBeInTheDocument();
    expect(screen.getByText('SUBJECT_NOT_IN_HISTORY')).toBeInTheDocument();
  });

  it('says so when the report is not in its own history', async () => {
    await mountSummary(
      { overall: { status_label: 'Attention Needed' }, assessments: [] },
      { subjectInHistory: false }
    );

    expect(
      await screen.findByText(/not among the reports used for the trend/)
    ).toBeInTheDocument();
  });

  it('never renders an absent assessment as a clean bill', async () => {
    await mountSummary({
      overall: {
        status_label: 'Not Assessed',
        clean_bill_of_health: false,
        assessment_reading: 'Nothing could be assessed from this report.',
      },
      assessments: [],
      unassessed_conditions: ['Diabetes', 'Kidney Disease'],
    });

    expect(await screen.findByText(/not a clean bill of health/)).toBeInTheDocument();
    expect(screen.getByText(/open questions, not negative results/)).toBeInTheDocument();
  });
});

describe('Module 31 -- population context', () => {
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
