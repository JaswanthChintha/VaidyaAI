import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Dashboard from '../src/pages/Dashboard';
import { api } from '../src/lib/api';


function renderDashboard() {
  return render(
    <MemoryRouter initialEntries={['/reports/abc']}>
      <Routes>
        <Route path="/reports/:id" element={<Dashboard />} />
      </Routes>
    </MemoryRouter>
  );
}

function withDashboard(dashboard) {
  vi.spyOn(api, 'getDashboard').mockResolvedValue({
    report: { originalName: 'report.pdf' },
    dashboard,
  });
}

beforeEach(() => {
  vi.restoreAllMocks();
});

const overallCardText = () => document.querySelector('.overall').textContent;

function riskWordShown(word) {
  return screen
    .queryAllByText(word)
    .some((node) => !node.closest('.gauge__scale'));
}

describe('the overall card', () => {
  it('prints the five-valued LABEL, never the three-valued status', async () => {
    withDashboard({
      overall: {
        status: 'Healthy',
        statusLabel: 'Healthy (partial assessment)',
        risk: 'Low',
        anyAssessed: true,
        complete: false,
        unassessedConditionCount: 2,
      },
    });
    renderDashboard();

    await screen.findAllByText('Healthy (partial assessment)');
    expect(overallCardText()).toContain('Healthy (partial assessment)');
    expect(overallCardText()).not.toMatch(/Healthy(?! \(partial assessment\))/);
    expect(screen.queryByText(/assessment is incomplete/)).not.toBeInTheDocument();
  });

  it('never renders a missing risk as Low', async () => {
    withDashboard({
      overall: {
        status: null,
        statusLabel: 'Not Assessed',
        risk: null,
        anyAssessed: false,
        complete: false,
      },
    });
    renderDashboard();

    await screen.findAllByText('Not Assessed');
    expect(overallCardText()).toContain('Not Assessed');
    expect(riskWordShown('Low')).toBe(false);
  });

  it('refuses a risk when nothing was assessed, even if one arrives', async () => {
    withDashboard({
      overall: {
        status: null,
        statusLabel: 'Not Assessed',
        risk: 'Low',
        anyAssessed: false,
        complete: false,
      },
    });
    renderDashboard();

    await screen.findAllByText('Not Assessed');
    expect(overallCardText()).toContain('Not Assessed');
    expect(riskWordShown('Low')).toBe(false);
  });
});

describe('condition cards', () => {
  it('renders an unassessed condition as unassessed, not as low risk', async () => {
    withDashboard({
      overall: { statusLabel: 'Not Assessed', anyAssessed: false },
      conditions: [
        {
          condition: 'Kidney Disease',
          status: 'Insufficient Data',
          risk: null,
          assessed: false,
        },
      ],
    });
    renderDashboard();

    await screen.findByText(/In short/);
    expect(riskWordShown('Low')).toBe(false);
    expect(screen.queryByText(/Nothing in these results pointed to/)).not.toBeInTheDocument();
  });

  it('keeps the two-checks-disagreed lecture OFF the patient card', async () => {
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true },
      conditions: [
        {
          condition: 'Heart Disease',
          status: 'Indicated',
          risk: 'Medium',
          flagged: true,
          assessed: true,
          basisConflict: true,
          basisNote: 'A risk-factor count and a model probability answer different questions.',
        },
      ],
    });
    renderDashboard();

    await screen.findAllByText(/Heart Disease/);
    expect(screen.queryByText(/answer different questions/)).not.toBeInTheDocument();
    expect(screen.queryByText(/did not agree/)).not.toBeInTheDocument();
    expect(screen.queryByText(/risk-factor count and a model probability/)).not.toBeInTheDocument();
  });

  describe('a topic the model flagged and the thresholds did not', () => {
    const kidney = (sources) => ({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true },
      conditions: [
        {
          condition: 'Kidney Disease',
          status: 'Indicated',
          risk: 'High',
          flagged: true,
          assessed: true,
          sourceKinds: ['clinical_rule', 'machine_learning'],
        },
      ],
      evidence: { conditions: [{ condition: 'Kidney Disease', sources }] },
    });

    const RULE_CLEAR = {
      source: 'Clinical Rule Engine',
      sourceKind: 'clinical_rule',
      status: 'Not Indicated',
      risk: 'Low',
      assessed: true,
    };
    const MODEL_FOUND = {
      source: 'Random Forest',
      sourceKind: 'machine_learning',
      status: 'Indicated',
      risk: 'High',
      assessed: true,
    };

    it('says so, in the framing the model author uses', async () => {
      withDashboard(kidney([RULE_CLEAR, MODEL_FOUND]));
      renderDashboard();

      expect(
        await screen.findByText(/No measured value crossed a standard limit/)
      ).toBeInTheDocument();
      expect(screen.getByText(/cannot confirm a condition/)).toBeInTheDocument();
    });

    it('names the model in the headline, not "these results"', async () => {
      withDashboard(kidney([RULE_CLEAR, MODEL_FOUND]));
      renderDashboard();

      expect(
        await screen.findByText(/A statistical model flagged this/)
      ).toBeInTheDocument();
      expect(
        screen.queryByText(/These results point to this/)
      ).not.toBeInTheDocument();
    });

    it('keeps "these results" when a measured value DID decide it', async () => {
      withDashboard(
        kidney([{ ...RULE_CLEAR, status: 'Indicated', risk: 'High' }, MODEL_FOUND])
      );
      renderDashboard();

      expect(
        await screen.findByText(/These results point to this/)
      ).toBeInTheDocument();
      expect(
        screen.queryByText(/A statistical model flagged this/)
      ).not.toBeInTheDocument();
    });

    it('does not claim risk factors were counted when none were found', async () => {
      withDashboard(
        kidney([
          {
            ...RULE_CLEAR,
            assessmentBasis: 'risk_factor_count',
            assessmentBasisFamily: 'risk_factor_burden',
          },
          MODEL_FOUND,
        ])
      );
      renderDashboard();

      expect(
        await screen.findByText(/A statistical model flagged this/)
      ).toBeInTheDocument();
      expect(
        screen.queryByText(/known to raise this risk/)
      ).not.toBeInTheDocument();
    });

    it('replaces the generic methods line rather than joining it', async () => {
      withDashboard(kidney([RULE_CLEAR, MODEL_FOUND]));
      renderDashboard();

      await screen.findByText(/No measured value crossed a standard limit/);
      expect(
        screen.queryByText(/Checked against standard clinical thresholds/)
      ).not.toBeInTheDocument();
    });

    it('stays silent when the threshold check ALSO found something', async () => {
      withDashboard(
        kidney([{ ...RULE_CLEAR, status: 'Indicated', risk: 'High' }, MODEL_FOUND])
      );
      renderDashboard();

      await screen.findAllByText(/Kidney Disease/);
      expect(
        screen.queryByText(/No measured value crossed a standard limit/)
      ).not.toBeInTheDocument();
    });

    it('stays silent when the model is the one that found nothing', async () => {
      withDashboard(
        kidney([
          { ...RULE_CLEAR, status: 'Indicated', risk: 'High' },
          { ...MODEL_FOUND, status: 'Not Indicated', risk: 'Low' },
        ])
      );
      renderDashboard();

      await screen.findAllByText(/Kidney Disease/);
      expect(
        screen.queryByText(/No measured value crossed a standard limit/)
      ).not.toBeInTheDocument();
    });

    it('needs PROOF of both verdicts, and says nothing without it', async () => {
      withDashboard(kidney([]));
      renderDashboard();

      await screen.findAllByText(/Kidney Disease/);
      expect(
        screen.queryByText(/No measured value crossed a standard limit/)
      ).not.toBeInTheDocument();
    });

    it('needs BOTH verdicts, not just the model’s', async () => {
      withDashboard(kidney([MODEL_FOUND]));
      renderDashboard();

      await screen.findAllByText(/Kidney Disease/);
      expect(
        screen.queryByText(/No measured value crossed a standard limit/)
      ).not.toBeInTheDocument();
    });

    it('does not take a clear verdict from a source that was not assessed', async () => {
      withDashboard(kidney([{ ...RULE_CLEAR, assessed: false }, MODEL_FOUND]));
      renderDashboard();

      await screen.findAllByText(/Kidney Disease/);
      expect(
        screen.queryByText(/No measured value crossed a standard limit/)
      ).not.toBeInTheDocument();
    });

    it('never reads an absence as the model having found something', async () => {
      withDashboard(
        kidney([RULE_CLEAR, { ...MODEL_FOUND, status: 'Insufficient Data', risk: null }])
      );
      renderDashboard();

      await screen.findAllByText(/Kidney Disease/);
      expect(
        screen.queryByText(/No measured value crossed a standard limit/)
      ).not.toBeInTheDocument();
    });

    it('never reads an unrecognised status as a finding', async () => {
      withDashboard(
        kidney([RULE_CLEAR, { ...MODEL_FOUND, status: 'Something New' }])
      );
      renderDashboard();

      await screen.findAllByText(/Kidney Disease/);
      expect(
        screen.queryByText(/No measured value crossed a standard limit/)
      ).not.toBeInTheDocument();
    });
  });

  it('agrees its verb with a single contributing value', async () => {
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true },
      conditions: [
        {
          condition: 'Obesity',
          status: 'Borderline',
          risk: 'Low',
          flagged: true,
          assessed: true,
        },
      ],
      evidence: {
        conditions: [
          {
            condition: 'Obesity',
            lines: [
              {
                feature: 'bmi',
                value: 26.42,
                unit: 'kg/m2',
                availability: 'observed',
                sourceStage: 'profile',
              },
            ],
          },
        ],
      },
    });
    renderDashboard();

    expect(await screen.findByText(/was also taken into account/)).toBeInTheDocument();
    expect(screen.queryByText(/BMI were also taken/)).not.toBeInTheDocument();
  });

  it('never glosses a status it does not recognise', async () => {
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true },
      conditions: [
        {
          condition: 'Heart Disease',
          status: 'Provisionally Indicated',
          risk: 'Medium',
          flagged: true,
          assessed: true,
        },
      ],
    });
    renderDashboard();

    expect(await screen.findByText('Provisionally Indicated')).toBeInTheDocument();
    expect(screen.queryByText(/These results point to this/)).not.toBeInTheDocument();
  });

  it('explains a Borderline finding too, not just a flagged one', async () => {
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true },
      conditions: [
        {
          condition: 'Heart Disease',
          status: 'Borderline',
          risk: 'Medium',
          assessed: true,
          sourceKinds: ['machine_learning'],
        },
      ],
    });
    renderDashboard();

    expect(await screen.findByText(/Assessed by a statistical model/)).toBeInTheDocument();
  });

  it('still explains a verdict the values on the card do not explain', async () => {
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true },
      conditions: [
        {
          condition: 'Kidney Disease',
          status: 'Indicated',
          risk: 'Medium',
          flagged: true,
          assessed: true,
          sourceKinds: ['machine_learning'],
        },
      ],
    });
    renderDashboard();

    expect(await screen.findByText(/Assessed by a statistical model/)).toBeInTheDocument();
  });

  it('does not narrate its own mechanics over a row that already shows them', async () => {
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true },
      conditions: [
        {
          condition: 'High Cholesterol',
          status: 'Indicated',
          risk: 'Medium',
          flagged: true,
          assessed: true,
          sourceKinds: ['clinical_rule', 'machine_learning'],
        },
      ],
      evidence: {
        conditions: [
          {
            condition: 'High Cholesterol',
            lines: [
              {
                feature: 'cholesterol',
                value: 268,
                unit: 'mg/dl',
                availability: 'observed',
                threshold: 240,
                comparator: '>=',
                sourceStage: 'lab_report',
              },
            ],
          },
        ],
      },
    });
    renderDashboard();

    expect(await screen.findByText(/above 240/)).toBeInTheDocument();
    expect(screen.queryByText(/Checked against standard clinical thresholds/)).not.toBeInTheDocument();
  });
});

describe('a calculated eGFR on the Kidney card (2026-10-04)', () => {
  const kidneyCard = (egfrLine) => ({
    overall: { statusLabel: 'Attention Needed', anyAssessed: true, risk: 'Medium' },
    conditions: [
      {
        condition: 'Kidney Disease',
        status: 'Indicated',
        risk: 'Medium',
        flagged: true,
        assessed: true,
        sourceKinds: ['clinical_rule'],
      },
    ],
    evidence: {
      conditions: [
        {
          condition: 'Kidney Disease',
          lines: [
            {
              feature: 'creatinine',
              value: 1.0,
              unit: 'mg/dl',
              availability: 'observed',
              sourceStage: 'lab_report',
            },
            egfrLine,
          ],
        },
      ],
    },
  });

  const EGFR = {
    feature: 'egfr',
    displayName: 'eGFR (estimated from creatinine, age and sex)',
    value: 59,
    unit: 'mL/min/1.73 m²',
    threshold: 60,
    comparator: '<',
    availability: 'observed',
    sourceStage: 'calculated',
  };

  it('shows the estimate with its crossing, and says it was calculated', async () => {
    withDashboard(kidneyCard(EGFR));
    renderDashboard();

    expect(await screen.findByText('eGFR (estimated from creatinine, age and sex)'))
      .toBeInTheDocument();
    expect(
      screen.getByText(/below 60 mL\/min\/1.73 m²; calculated by VaidyaAI, not printed on the report/)
    ).toBeInTheDocument();
  });

  it('still says calculated when no cut-off was crossed', async () => {
    withDashboard(kidneyCard({ ...EGFR, value: 72, threshold: null, comparator: null }));
    renderDashboard();

    await screen.findByText('eGFR (estimated from creatinine, age and sex)');
    const note = screen.getByText('calculated by VaidyaAI, not printed on the report');
    expect(note.className).not.toMatch(/crossed/);
  });
});

describe('what a condition card says it took into account', () => {
  const heartCard = (lines) => ({
    overall: { statusLabel: 'Attention Needed', anyAssessed: true },
    conditions: [
      {
        condition: 'Heart Disease',
        status: 'Borderline',
        risk: 'Medium',
        flagged: true,
        assessed: true,
      },
    ],
    evidence: { conditions: [{ condition: 'Heart Disease', lines }] },
  });

  const OBSERVED_BMI = {
    feature: 'bmi',
    value: 25.25,
    sourceStage: 'patient_profile',
    availability: 'observed',
  };
  const ABSENT_HYPERTENSION = {
    feature: 'hypertension',
    value: null,
    sourceStage: 'patient_profile',
    availability: 'not_present_in_report',
  };

  it('does not claim an absent feature was taken into account', async () => {
    withDashboard(heartCard([OBSERVED_BMI, ABSENT_HYPERTENSION]));
    renderDashboard();

    await screen.findAllByText(/Heart Disease/);
    const card = document.querySelector('.condition');
    expect(card.textContent).toMatch(/Your BMI were also taken into account|Your BMI was/);
    expect(card.textContent).not.toMatch(
      /history of high blood pressure[^.]*were also taken into account/
    );
  });

  it('NAMES the absent feature rather than dropping it silently', async () => {
    withDashboard(heartCard([OBSERVED_BMI, ABSENT_HYPERTENSION]));
    renderDashboard();

    await screen.findAllByText(/Heart Disease/);
    const card = document.querySelector('.condition');
    expect(card.textContent).toMatch(/No value was available for your/);
    expect(card.textContent).toMatch(/history of high blood pressure/);
    expect(card.textContent).toMatch(/could not be taken into account/);
  });

  it('does not say "close to the usual limit" when nothing was compared to one', async () => {
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true },
      conditions: [
        { condition: 'Heart Disease', status: 'Borderline', risk: 'Medium', flagged: true, assessed: true },
      ],
      evidence: {
        conditions: [
          {
            condition: 'Heart Disease',
            lines: [OBSERVED_BMI],
            sources: [
              { assessmentBasis: 'risk_factor_count', assessmentBasisFamily: 'risk_factor_burden' },
              { assessmentBasis: 'model_probability', assessmentBasisFamily: 'estimated_likelihood' },
            ],
          },
        ],
      },
    });
    renderDashboard();

    await screen.findAllByText(/Heart Disease/);
    const card = document.querySelector('.condition');
    expect(card.textContent).not.toMatch(/Close to the usual limit/);
    expect(card.textContent).toMatch(/known to raise this risk/);
  });

  it('KEEPS threshold wording when a value really was compared to a cut-off', async () => {
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true },
      conditions: [
        { condition: 'Diabetes', status: 'Borderline', risk: 'Low', flagged: true, assessed: true },
      ],
      evidence: {
        conditions: [
          {
            condition: 'Diabetes',
            lines: [OBSERVED_BMI],
            sources: [
              { assessmentBasis: 'threshold_comparison', assessmentBasisFamily: 'measured_value' },
            ],
          },
        ],
      },
    });
    renderDashboard();

    await screen.findAllByText(/Diabetes/);
    expect(document.querySelector('.condition').textContent).toMatch(
      /Close to the usual limit/
    );
  });

  it('prefers threshold wording when a topic has BOTH bases', async () => {
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true },
      conditions: [
        { condition: 'Heart Disease', status: 'Borderline', risk: 'Medium', flagged: true, assessed: true },
      ],
      evidence: {
        conditions: [
          {
            condition: 'Heart Disease',
            lines: [OBSERVED_BMI],
            sources: [
              { assessmentBasis: 'risk_factor_count', assessmentBasisFamily: 'risk_factor_burden' },
              { assessmentBasis: 'threshold_comparison', assessmentBasisFamily: 'measured_value' },
            ],
          },
        ],
      },
    });
    renderDashboard();

    await screen.findAllByText(/Heart Disease/);
    const card = document.querySelector('.condition');
    expect(card.textContent).toMatch(/Close to the usual limit/);
    expect(card.textContent).not.toMatch(/known to raise this risk/);
  });

  it('says nothing about missing inputs when every one was observed', async () => {
    withDashboard(heartCard([OBSERVED_BMI]));
    renderDashboard();

    await screen.findAllByText(/Heart Disease/);
    const card = document.querySelector('.condition');
    expect(card.textContent).toMatch(/taken into account/);
    expect(card.textContent).not.toMatch(/No value was available/);
  });
});

describe('what the charts and the table are told about each row', () => {
  it('measures radar coverage as inputs AVAILABLE, never as the verdict', async () => {
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true, risk: 'High' },
      conditions: [
        { condition: 'Diabetes', status: 'Indicated', risk: 'High', flagged: true, assessed: true },
        { condition: 'Anemia', status: 'Not Indicated', risk: 'Low', flagged: false, assessed: true },
      ],
      evidence: {
        conditions: [
          {
            condition: 'Diabetes',
            lines: [
              { feature: 'hba1c', availability: 'observed' },
              { feature: 'blood_glucose', availability: 'observed' },
              { feature: 'hypertension', availability: 'not_present_in_report' },
              { feature: 'smoking_history', availability: 'not_present_in_report' },
            ],
          },
          {
            condition: 'Anemia',
            lines: [{ feature: 'hemoglobin', availability: 'observed' }],
          },
        ],
      },
    });
    renderDashboard();

    const radar = await screen.findByRole('img', { name: /Inputs available/ });
    const label = radar.getAttribute('aria-label');
    expect(label).toMatch(/Diabetes 2 of 4/);
    expect(label).toMatch(/Anemia 1 of 1/);
    const vertices = document.querySelectorAll('.radar__vertex');
    expect(Number(vertices[0].getAttribute('cy'))).toBeCloseTo(64, 0);
  });

  it('counts one input once, however many rules cite it', async () => {
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true, risk: 'High' },
      conditions: [
        { condition: 'Diabetes', status: 'Indicated', risk: 'High', flagged: true, assessed: true },
      ],
      evidence: {
        conditions: [
          {
            condition: 'Diabetes',
            lines: [
              { feature: 'hba1c', availability: 'observed' },
              { feature: 'hba1c', availability: 'not_present_in_report' },
              { feature: 'hypertension', availability: 'not_present_in_report' },
            ],
          },
        ],
      },
    });
    renderDashboard();

    const radar = await screen.findByRole('img', { name: /Inputs available/ });
    expect(radar.getAttribute('aria-label')).toMatch(/Diabetes 1 of 2/);
  });

  it('keeps an UNASSESSED topic on the radar, as its dotted point', async () => {
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true, risk: 'High' },
      conditions: [
        { condition: 'Diabetes', status: 'Indicated', risk: 'High', flagged: true, assessed: true },
        { condition: 'Kidney Disease', status: 'Insufficient Data', assessed: false },
      ],
      evidence: {
        conditions: [
          { condition: 'Diabetes', lines: [{ feature: 'hba1c', availability: 'observed' }] },
        ],
      },
    });
    renderDashboard();

    await screen.findByRole('img', { name: /Inputs available/ });
    expect(document.querySelectorAll('.radar__vertex--absent')).toHaveLength(1);
    expect(screen.getByText(/dotted point sits at zero/)).toBeInTheDocument();
  });

  it('leaves a topic off the radar when its coverage cannot be computed', async () => {
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true, risk: 'High' },
      conditions: [
        { condition: 'Diabetes', status: 'Indicated', risk: 'High', flagged: true, assessed: true },
        { condition: 'Anemia', status: 'Not Indicated', risk: 'Low', flagged: false, assessed: true },
      ],
      evidence: {
        conditions: [
          { condition: 'Anemia', lines: [{ feature: 'hemoglobin', availability: 'observed' }] },
        ],
      },
    });
    renderDashboard();

    const radar = await screen.findByRole('img', { name: /Inputs available/ });
    expect(radar.getAttribute('aria-label')).not.toMatch(/Diabetes/);
    expect(screen.getAllByText(/Diabetes/).length).toBeGreaterThan(0);
  });

  describe('results with no explanation prepared', () => {
    const withSkipped = (notExplained) => ({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true, risk: 'High' },
      laboratory: [
        { feature: 'hba1c', displayName: 'HbA1c', value: 8.4, unit: '%', state: 'measured', usable: true },
        { feature: 'cholesterol', displayName: 'Total Cholesterol', value: 268, unit: 'mg/dl', state: 'measured', usable: true },
        { feature: 'triglycerides', displayName: 'Triglyceride', value: 320, unit: 'mg/dl', state: 'measured', usable: true },
        { feature: 'bmi', displayName: 'BMI', value: 26.4, unit: 'kg/m2', state: 'measured', usable: true, source: 'patient_profile' },
      ],
      recommendations: {
        explanations: {
          available: true,
          entries: [
            {
              feature: 'hba1c',
              subject: 'the hba1c result',
              available: true,
              explanation: 'HbA1c reflects average blood sugar over recent months.',
            },
          ],
          notExplained,
        },
      },
    });

    it('names the results it never attempted to explain', async () => {
      withDashboard(
        withSkipped([
          { feature: 'cholesterol', reason: 'explanation_limit_reached' },
          { feature: 'triglycerides', reason: 'explanation_limit_reached' },
        ])
      );
      renderDashboard();

      await screen.findAllByText(/average blood sugar/);
      const said = screen.getByText(/have no explanation above/);
      expect(said.textContent).toMatch(/Total cholesterol/);
      expect(said.textContent).toMatch(/Triglycerides/);
    });

    it('says nothing went wrong with them, because nothing did', async () => {
      withDashboard(
        withSkipped([{ feature: 'cholesterol', reason: 'explanation_limit_reached' }])
      );
      renderDashboard();

      await screen.findAllByText(/average blood sugar/);
      expect(screen.getByText(/nothing was wrong with this result/)).toBeInTheDocument();
      expect(
        screen.queryByText(/No plain-language explanation could be prepared/)
      ).not.toBeInTheDocument();
    });

    it('does not announce a missing explanation for age, sex or BMI', async () => {
      withDashboard(
        withSkipped([
          { feature: 'age', reason: 'explanation_limit_reached' },
          { feature: 'gender', reason: 'explanation_limit_reached' },
          { feature: 'bmi', reason: 'explanation_limit_reached' },
        ])
      );
      renderDashboard();

      await screen.findAllByText(/average blood sugar/);
      expect(screen.queryByText(/no explanation above/)).not.toBeInTheDocument();
    });

    it('does not point at an "above" that is not there', async () => {
      withDashboard({
        ...withSkipped([{ feature: 'cholesterol', reason: 'explanation_limit_reached' }]),
        recommendations: {
          explanations: {
            available: true,
            entries: [],
            notExplained: [{ feature: 'cholesterol', reason: 'explanation_limit_reached' }],
          },
        },
      });
      renderDashboard();

      await screen.findAllByText(/Total Cholesterol/i);
      expect(screen.queryByText(/no explanation above/)).not.toBeInTheDocument();
      expect(document.querySelector('.explanation__text')).toBeNull();
    });

    it('says nothing at all when every result was explained', async () => {
      withDashboard(withSkipped([]));
      renderDashboard();

      await screen.findAllByText(/average blood sugar/);
      expect(screen.queryByText(/no explanation above/)).not.toBeInTheDocument();
    });

    it('accounts for the tests this tool does not check, and shows them', async () => {
      withDashboard({
        ...withSkipped([]),
        unanalysed: {
          count: 4,
          items: [
            { testName: 'LDL Cholesterol, Direct' },
            { testName: 'HDL Cholesterol' },
            { testName: 'Blood Urea' },
            { testName: 'Potassium, Serum' },
          ],
        },
      });
      renderDashboard();

      await screen.findAllByText(/average blood sugar/);
      for (const name of ['LDL Cholesterol, Direct', 'HDL Cholesterol',
                          'Blood Urea', 'Potassium, Serum']) {
        expect(screen.getAllByText(name).length).toBeGreaterThan(0);
      }
      expect(screen.getAllByText('Blood Urea').length).toBeGreaterThan(0);
      expect(screen.getAllByText('Potassium, Serum').length).toBeGreaterThan(0);
    });

    it('does not mention other tests when the report has none', async () => {
      withDashboard(withSkipped([]));
      renderDashboard();

      await screen.findAllByText(/average blood sugar/);
      expect(screen.queryByText(/other tests it does not check/)).not.toBeInTheDocument();
      expect(screen.queryByText(/other test it does not check/)).not.toBeInTheDocument();
    });

    it('counts the tests off the items, never off the payload counter', async () => {
      withDashboard({
        ...withSkipped([]),
        unanalysed: {
          count: 0,
          items: [{ testName: 'Blood Urea' }, { testName: 'Potassium, Serum' }],
        },
      });
      renderDashboard();

      await screen.findAllByText(/average blood sugar/);
      expect(screen.getAllByText('Blood Urea').length).toBeGreaterThan(0);
      expect(screen.getAllByText('Potassium, Serum').length).toBeGreaterThan(0);
    });

    it('joins two names with "and", not a bare comma', async () => {
      withDashboard(
        withSkipped([
          { feature: 'cholesterol', reason: 'explanation_limit_reached' },
          { feature: 'triglycerides', reason: 'explanation_limit_reached' },
        ])
      );
      renderDashboard();

      const said = await screen.findByText(/have no explanation above/);
      expect(said.textContent).toMatch(/Total cholesterol and Triglycerides/);
    });
  });

  describe('a profile answer is not a measurement', () => {
    const profileRows = {
      overall: { statusLabel: 'Healthy', anyAssessed: true, risk: 'Low' },
      laboratory: [
        {
          feature: 'hba1c',
          displayName: 'HbA1c',
          value: 5.2,
          unit: '%',
          state: 'measured',
          usable: true,
        },
        {
          feature: 'bmi',
          displayName: 'BMI',
          value: 26.42,
          unit: 'kg/m2',
          state: 'measured',
          usable: true,
          source: 'patient_profile',
        },
        {
          feature: 'gender',
          displayName: 'Sex',
          value: 'male',
          state: 'measured',
          usable: true,
          source: 'patient_profile',
        },
      ],
    };

    const cellFor = (text) =>
      [...document.querySelectorAll('.lab-table td')].find((td) =>
        td.textContent.trim().startsWith(text)
      );

    it('does not set a word in the figures face', async () => {
      withDashboard(profileRows);
      renderDashboard();

      await screen.findAllByText(/Sex/);
      expect(cellFor('Male').classList.contains('lab__word')).toBe(true);
    });

    it('keeps the figures face for an actual figure', async () => {
      withDashboard(profileRows);
      renderDashboard();

      await screen.findAllByText(/BMI/);
      expect(cellFor('26.42').classList.contains('lab__word')).toBe(false);
    });

    it('capitalises the answer without rewording it', async () => {
      withDashboard(profileRows);
      renderDashboard();

      await screen.findAllByText(/Sex/);
      expect(screen.getByText('Male')).toBeInTheDocument();
      expect(screen.queryByText('male')).not.toBeInTheDocument();
    });
  });

  it('drops a never-measured row but KEEPS a rejected one', async () => {
    withDashboard({
      overall: { statusLabel: 'Healthy', anyAssessed: true, risk: 'Low' },
      laboratory: [
        {
          feature: 'vitamin_b12',
          displayName: 'Vitamin B12',
          value: 420,
          unit: 'pg/ml',
          state: 'measured',
          usable: true,
        },
        {
          feature: 'smoking_history',
          displayName: 'Smoking history',
          value: null,
          state: 'unavailable',
          usable: false,
          source: null,
        },
        {
          feature: 'vitamin_d',
          displayName: 'Vitamin D',
          value: null,
          state: 'rejected',
          usable: false,
        },
      ],
    });
    renderDashboard();

    await screen.findAllByText(/Vitamin B12/i);
    expect(screen.queryByText('Smoking history')).not.toBeInTheDocument();
    expect(screen.getAllByText(/Vitamin D/i).length).toBeGreaterThan(0);
    expect(screen.getByText('Not usable')).toBeInTheDocument();
  });
});

describe('laboratory rows', () => {
  it('keeps the pipeline’s own warnings off the patient page', async () => {
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true },
      warnings: [
        {
          stage: 'feature_engineering',
          message:
            "'25-Hydroxy Vitamin D' reported unit 'ng/dL', which is not a recognised unit for feature 'vitamin_d' (canonical: 'ng/ml'). The value was left unconverted and flagged canonical_unit=false.",
        },
      ],
      conditions: [
        { condition: 'Diabetes', status: 'Indicated', risk: 'High', flagged: true, assessed: true },
      ],
    });
    renderDashboard();

    await screen.findAllByText(/Diabetes/);
    expect(screen.queryByText(/Worth knowing about this analysis/)).not.toBeInTheDocument();
    expect(screen.queryByText(/canonical_unit/)).not.toBeInTheDocument();
    expect(screen.queryByText(/feature 'vitamin_d'/)).not.toBeInTheDocument();
  });

  it('renders a rejected reading as unusable, never as 0', async () => {
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true },
      laboratory: [
        {
          feature: 'vitamin_b12',
          displayName: 'Vitamin B12',
          value: 420,
          unit: 'pg/ml',
          referenceLow: 200,
          referenceHigh: 900,
          state: 'measured',
          usable: true,
        },
        {
          feature: 'creatinine',
          displayName: 'Creatinine',
          value: 999,
          unit: 'mg/dl',
          state: 'rejected',
          usable: false,
          rejectionReason: 'This value is outside the physiologically possible range.',
        },
      ],
    });
    renderDashboard();

    expect(await screen.findAllByText(/Creatinine/)).not.toHaveLength(0);
    expect(screen.queryByText('999 mg/dl')).not.toBeInTheDocument();
    expect(screen.queryByText('0 mg/dl')).not.toBeInTheDocument();
    expect(screen.getAllByText(/could not be used/)).not.toHaveLength(0);
    expect(
      screen.queryByText(/outside the physiologically possible range/)
    ).not.toBeInTheDocument();
  });

  it('prints a real zero rather than treating it as missing', async () => {
    withDashboard({
      overall: { statusLabel: 'Healthy', anyAssessed: true },
      laboratory: [
        {
          feature: 'vitamin_d',
          displayName: 'Vitamin D',
          value: 0,
          unit: 'ng/ml',
          state: 'valid',
          usable: true,
        },
      ],
    });
    renderDashboard();

    expect(await screen.findAllByText('0 ng/ml')).not.toHaveLength(0);
  });


});

describe('the closing "In short" summary', () => {
  const summaryText = () => document.querySelector('.in-short').textContent;


  const flagged = (condition, risk = 'High') => ({
    condition,
    status: 'Indicated',
    risk,
    flagged: true,
    assessed: true,
  });
  const clear = (condition) => ({
    condition,
    status: 'Not Indicated',
    risk: 'Low',
    flagged: false,
    assessed: true,
  });
  const unassessed = (condition) => ({
    condition,
    status: 'Insufficient Data',
    risk: null,
    assessed: false,
  });

  it('says the verdict in English and does NOT restate the internal labels', async () => {
    withDashboard({
      overall: {
        status: 'Needs Medical Attention',
        statusLabel: 'Needs Medical Attention',
        risk: 'High',
        anyAssessed: true,
        complete: true,
      },
      conditions: [flagged('Diabetes'), clear('Anemia')],
    });
    renderDashboard();

    await screen.findByText(/In short/);
    expect(summaryText()).toMatch(/should be looked at by a doctor/);
    expect(summaryText()).not.toMatch(/Recorded as/);
    expect(summaryText()).not.toMatch(/Needs Medical Attention/);
  });

  it('refuses to invent English for a label it does not know', async () => {
    withDashboard({
      overall: {
        statusLabel: 'Something New',
        risk: 'Low',
        anyAssessed: true,
        complete: true,
      },
      conditions: [clear('Anemia')],
    });
    renderDashboard();

    await screen.findByText(/In short/);
    expect(summaryText()).toMatch(/no plain-English wording for that result/);
    expect(summaryText()).toMatch(/Something New/);
  });

  it('counts the cards on screen, not a counter that can disagree', async () => {
    withDashboard({
      overall: {
        statusLabel: 'Needs Monitoring',
        risk: 'Medium',
        anyAssessed: true,
        complete: true,
        abnormalConditionCount: 99,
        assessedConditionCount: 99,
      },
      conditions: [flagged('Diabetes'), flagged('High Cholesterol'), clear('Anemia')],
    });
    renderDashboard();

    await screen.findByText(/In short/);
    expect(summaryText()).toMatch(/2 need a closer look/);
    expect(summaryText()).not.toMatch(/99/);
  });

  it('keeps an UNRECOGNISED verdict out of the "showed nothing" list', async () => {
    withDashboard({
      overall: {
        statusLabel: 'Needs Monitoring',
        risk: 'Medium',
        anyAssessed: true,
        complete: true,
      },
      conditions: [
        { condition: 'Mystery Condition', status: 'Indicated' },
        clear('Anemia'),
      ],
    });
    renderDashboard();

    await screen.findByText(/In short/);
    expect(summaryText()).toMatch(/1 needs a closer look: Mystery Condition/);
    expect(summaryText()).not.toMatch(/showed nothing: Mystery Condition/);
  });


  it('carries the laboratory-flagged tests it does not assess into the summary', async () => {
    withDashboard({
      overall: {
        statusLabel: 'Healthy',
        risk: 'Low',
        anyAssessed: true,
        complete: true,
      },
      conditions: [clear('Anemia')],
      unanalysed: {
        count: 2,
        labFlaggedCount: 1,
        items: [
          { testName: 'Potassium', value: '5.2', labFlaggedAbnormal: true, labFlag: 'high' },
          { testName: 'Urine Colour', value: 'Pale Yellow', labFlaggedAbnormal: false },
        ],
      },
    });
    renderDashboard();

    await screen.findByText(/In short/);
    expect(summaryText()).toMatch(/1 further result is outside the range printed on the report/);
    expect(summaryText()).not.toMatch(/laboratory marked/i);
    expect(summaryText()).toMatch(/Potassium/);
    expect(screen.getAllByText('Urine Colour').length).toBeGreaterThan(0);
  });


  it('never says a report is out of range when the finding came from the form', async () => {
    withDashboard({
      overall: {
        statusLabel: 'Needs Monitoring',
        risk: 'Low',
        anyAssessed: true,
        complete: true,
        abnormalConditionCount: 1,
      },
      conditions: [
        { condition: 'Obesity', status: 'Borderline', risk: 'Low', flagged: true, assessed: true },
        clear('Diabetes'),
      ],
      evidence: {
        conditions: [
          {
            condition: 'Obesity',
            lines: [{ feature: 'bmi', value: 26.42, sourceStage: 'patient_profile' }],
          },
        ],
      },
    });
    renderDashboard();

    await screen.findByText(/In short/);
    expect(summaryText()).not.toMatch(/in this report is outside/);
    expect(summaryText()).toMatch(/Obesity comes from the details you entered/);
    expect(summaryText()).toMatch(
      /not from anything measured in this report/
    );
  });

  it('does not claim the labs are all in range when they are not', async () => {
    withDashboard({
      overall: {
        statusLabel: 'Needs Medical Attention',
        risk: 'High',
        anyAssessed: true,
        complete: true,
        abnormalConditionCount: 2,
      },
      conditions: [flagged('Obesity', 'Low'), flagged('Diabetes', 'High')],
      evidence: {
        conditions: [
          {
            condition: 'Obesity',
            lines: [{ feature: 'bmi', sourceStage: 'patient_profile' }],
          },
          {
            condition: 'Diabetes',
            lines: [{ feature: 'hba1c', sourceStage: 'lab_report' }],
          },
        ],
      },
    });
    renderDashboard();

    await screen.findByText(/In short/);
    expect(summaryText()).toMatch(/Obesity comes from the details you entered/);
    expect(summaryText()).not.toMatch(/every laboratory result on the page is in range/);
  });

  it('does NOT claim a measured finding came from the form', async () => {
    withDashboard({
      overall: {
        statusLabel: 'Needs Monitoring',
        risk: 'Low',
        anyAssessed: true,
        complete: true,
        abnormalConditionCount: 1,
      },
      conditions: [flagged('Diabetes', 'Low')],
      evidence: {
        conditions: [
          {
            condition: 'Diabetes',
            lines: [{ feature: 'hba1c', value: 6.8, sourceStage: 'lab_report' }],
          },
        ],
      },
    });
    renderDashboard();

    await screen.findByText(/In short/);
    expect(summaryText()).not.toMatch(/details you entered/);
  });

  it('makes no provenance claim when the evidence does not say', async () => {
    withDashboard({
      overall: {
        statusLabel: 'Needs Monitoring',
        risk: 'Low',
        anyAssessed: true,
        complete: true,
        abnormalConditionCount: 1,
      },
      conditions: [flagged('Obesity', 'Low')],
      evidence: { conditions: [{ condition: 'Obesity', lines: [] }] },
    });
    renderDashboard();

    await screen.findByText(/In short/);
    expect(summaryText()).not.toMatch(/details you entered/);
  });

  it('keeps the status/risk vocabulary off the patient summary entirely', async () => {
    withDashboard({
      overall: {
        statusLabel: 'Needs Monitoring',
        risk: 'Low',
        anyAssessed: true,
        complete: true,
        abnormalConditionCount: 1,
      },
      conditions: [flagged('Obesity', 'Low')],
    });
    renderDashboard();

    await screen.findByText(/In short/);
    expect(summaryText()).toMatch(/worth keeping an eye on/);
    expect(summaryText()).not.toMatch(/Needs Monitoring/);
    expect(summaryText()).not.toMatch(/answer different questions/);
    expect(overallCardText()).not.toMatch(/These measure different things/);
    expect(overallCardText()).not.toMatch(/answer different questions/);
  });

  it('does not let a comma inside a test name split it into two tests', async () => {
    withDashboard({
      overall: {
        statusLabel: 'Healthy',
        risk: 'Low',
        anyAssessed: true,
        complete: true,
      },
      conditions: [clear('Anemia')],
      unanalysed: {
        count: 2,
        labFlaggedCount: 2,
        items: [
          { testName: 'LDL Cholesterol, Direct', labFlaggedAbnormal: true },
          { testName: 'Potassium, Serum', labFlaggedAbnormal: true },
        ],
      },
    });
    renderDashboard();

    await screen.findByText(/In short/);
    expect(summaryText()).toMatch(
      /LDL Cholesterol, Direct; Potassium, Serum/
    );
  });

  it('says when part of the document could not be read -- at the top, as not checked', async () => {
    withDashboard({
      overall: {
        statusLabel: 'Healthy',
        risk: 'Low',
        anyAssessed: true,
        complete: true,
      },
      conditions: [clear('Anemia')],
      document: { pagesUnreadable: [2, 3], partialDocument: true },
    });
    renderDashboard();

    await screen.findByText(/In short/);
    const notice = screen.getByRole('note', { name: 'Part of this report could not be read' });
    expect(notice).toHaveTextContent('Pages 2 and 3 of this report could not be read this time');
    expect(notice).toHaveTextContent('so they were not checked');
    expect(notice).toHaveTextContent('press Re-analyse to try again');
    const verdict = screen.getByText('Healthy');
    expect(notice.compareDocumentPosition(verdict) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(summaryText()).not.toMatch(/could not be read/);
  });

  it('a partial document with no page numbers still says part could not be read', async () => {
    withDashboard({
      overall: { statusLabel: 'Healthy', risk: 'Low', anyAssessed: true, complete: true },
      conditions: [clear('Anemia')],
      document: { pagesUnreadable: [], partialDocument: true },
    });
    renderDashboard();
    await screen.findByText(/In short/);
    expect(screen.getByRole('note', { name: 'Part of this report could not be read' })).toHaveTextContent(
      'Part of this report could not be read this time'
    );
  });

  it('every page read: no notice', async () => {
    withDashboard({
      overall: { statusLabel: 'Healthy', risk: 'Low', anyAssessed: true, complete: true },
      conditions: [clear('Anemia')],
      document: { pagesUnreadable: [], partialDocument: false },
    });
    renderDashboard();
    await screen.findByText(/In short/);
    expect(screen.queryByRole('note', { name: 'Part of this report could not be read' })).toBeNull();
  });

  it('states what this is even when everything came back clear', async () => {
    withDashboard({
      overall: {
        statusLabel: 'Healthy',
        risk: 'Low',
        anyAssessed: true,
        complete: true,
      },
      conditions: [clear('Anemia')],
    });
    renderDashboard();

    await screen.findByText(/In short/);
    expect(summaryText()).toMatch(/It is not a diagnosis/);
    expect(summaryText()).toMatch(/qualified healthcare professional/);
  });

  it('summarises nothing when there is no overall result', async () => {
    withDashboard({
      overall: {
        status: null,
        statusLabel: null,
        risk: null,
        anyAssessed: false,
        complete: false,
      },
      conditions: [],
    });
    renderDashboard();

    await screen.findByText(/In short/);
    expect(summaryText()).toMatch(/No overall status was established/);
    expect(riskWordShown('Low')).toBe(false);
  });
});

describe('descriptions of tests this platform does not assess', () => {
  const unanalysed = {
    count: 3,
    labFlaggedCount: 2,
    descriptionsPresent: true,
    describedCount: 1,
    withheldCount: 1,
    items: [
      {
        testName: 'Potassium',
        value: '5.2',
        unit: 'mmol/L',
        labFlag: 'high',
        labFlaggedAbnormal: true,
        labReferenceLow: 3.5,
        labReferenceHigh: 5.1,
        descriptionAvailable: true,
        description: 'A mineral your body uses for nerve and muscle function.',
      },
      {
        testName: 'LDL Cholesterol',
        value: '160',
        unit: 'mg/dL',
        labFlag: 'high',
        labFlaggedAbnormal: true,
        descriptionAvailable: false,
        descriptionNotice: 'The description did not pass safety review.',
      },
      {
        testName: 'Urine Colour',
        value: 'Pale Yellow',
        labFlaggedAbnormal: false,
        reason: 'no_feature',
      },
    ],
  };

  it('shows the description under the test it describes', async () => {
    withDashboard({ unanalysed });
    renderDashboard();

    expect(
      await screen.findByText(/A mineral your body uses for nerve and muscle function./)
    ).toBeInTheDocument();
    const markings = [...document.querySelectorAll('.verdict--high')];
    expect(markings.length).toBeGreaterThanOrEqual(2);
    for (const mark of markings) expect(mark.textContent).toMatch(/high/i);
  });

  it('marks a reviewed description as not written by the model, and only that one (2026-10-04)', async () => {
    withDashboard({
      unanalysed: {
        ...unanalysed,
        items: [
          {
            ...unanalysed.items[0],
            testName: 'SGPT',
            description: 'ALT, also printed as SGPT, measures an enzyme found mainly inside liver cells.',
            descriptionOrigin: 'reviewed',
          },
          { ...unanalysed.items[0], descriptionOrigin: 'model' },
        ],
      },
    });
    renderDashboard();

    await screen.findByText(/measures an enzyme found mainly inside liver cells/);
    const tags = screen.getAllByText(/reviewed reference material, not written by the\s+language model/);
    expect(tags).toHaveLength(1);
    expect(screen.getByText(/Unless marked otherwise, these were written by a language model/))
      .toBeInTheDocument();
  });

  it('says a description was WITHHELD rather than showing an empty space', async () => {
    withDashboard({ unanalysed });
    renderDashboard();

    expect(
      await screen.findByText(/The description did not pass safety review./)
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/No description of this test was produced/)
    ).not.toBeInTheDocument();
  });

  it('still says something when a withheld entry carries no notice', async () => {
    withDashboard({
      unanalysed: {
        ...unanalysed,
        items: [{ testName: 'Blood Urea', value: '53', descriptionAvailable: false }],
      },
    });
    renderDashboard();

    expect(
      await screen.findByText(/No description of this test was produced/)
    ).toBeInTheDocument();
  });


  it('says nothing at all about a test nobody asked about', async () => {
    withDashboard({ unanalysed });
    renderDashboard();

    await screen.findByText(/Urine Colour/);
    expect(
      screen.getAllByText(/did not pass safety review|No description of this test/)
    ).toHaveLength(1);
  });

  it('offers no explanatory sentence when there are no descriptions', async () => {
    withDashboard({
      unanalysed: {
        count: 1,
        labFlaggedCount: 0,
        descriptionsPresent: false,
        describedCount: 0,
        withheldCount: 0,
        items: [{ testName: 'Urine Colour', value: 'Pale Yellow', reason: 'no_feature' }],
      },
    });
    renderDashboard();

    expect((await screen.findAllByText('Urine Colour')).length).toBeGreaterThan(0);
    expect(screen.queryByText(/your result was not used/)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/No description of this test was produced/)
    ).not.toBeInTheDocument();
  });
});

describe('an unanalysed report', () => {
  it('states that it has not been analysed rather than showing an empty all-clear', async () => {
    const error = new Error('This report has not been analysed yet.');
    error.status = 404;
    error.name = 'ApiError';
    Object.setPrototypeOf(error, (await import('../src/lib/api')).ApiError.prototype);
    vi.spyOn(api, 'getDashboard').mockRejectedValue(error);

    renderDashboard();

    expect(
      await screen.findByText(
        'This report has not been analysed yet. Go back to your reports and press Analyse.'
      )
    ).toBeInTheDocument();
  });
});

describe('the round-up of everything else', () => {
  const clear = (name) => ({
    condition: name,
    status: 'Not Indicated',
    risk: 'Low',
    assessed: true,
    flagged: false,
  });
  const unassessed = (name) => ({
    condition: name,
    status: 'Insufficient Data',
    risk: null,
    assessed: false,
  });

  const chipText = (selector) =>
    [...document.querySelectorAll(selector)].map((el) => el.textContent);


  it('counts the cleared topics, and agrees with the chips it drew', async () => {
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true, risk: 'High' },
      conditions: [clear('Anemia'), clear('Underweight'), clear('Hypoglycemia')],
    });
    renderDashboard();

    await screen.findByText(/Everything else that was checked/);
    expect(document.querySelectorAll('.chip--clear')).toHaveLength(3);
    expect(document.querySelector('.roundup__lead').textContent).toMatch(/these 3 conditions/);
  });

  it('says "condition", singular, when there is one of them', async () => {
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true, risk: 'High' },
      conditions: [clear('Anemia')],
    });
    renderDashboard();

    await screen.findByText(/Everything else that was checked/);
    expect(document.querySelector('.roundup__lead').textContent).toMatch(/these 1 condition\./);
  });

  it('draws no unchecked group when nothing was unchecked', async () => {
    withDashboard({
      overall: { statusLabel: 'Healthy', anyAssessed: true, risk: 'Low' },
      conditions: [clear('Anemia')],
    });
    renderDashboard();

    await screen.findByText(/Everything else that was checked/);
    expect(document.querySelectorAll('.chip--unassessed')).toHaveLength(0);
    expect(screen.queryByText(/open question, not a negative result/)).not.toBeInTheDocument();
  });
});

describe('guidance attribution', () => {
  const withGuidance = (items, conditions) => ({
    overall: { statusLabel: 'Attention Needed', anyAssessed: true, risk: 'High' },
    conditions,
    recommendations: { guidance: { items } },
  });

  const flagged = (name) => ({
    condition: name,
    status: 'Indicated',
    risk: 'High',
    assessed: true,
    flagged: true,
  });

  it('links a known topic to its fixed NHS page, safely', async () => {
    withDashboard(
      withGuidance(
        [{ code: 'GENERAL_VITAMIN_D_SOURCES', text: 'Vitamin D sources.', becauseOfConditions: ['Obesity'] }],
        [flagged('Obesity')]
      )
    );
    renderDashboard();
    await screen.findByText(/Topics you could read about/);
    const link = document.querySelector('.guidance__link');
    expect(link).not.toBeNull();
    expect(link.getAttribute('href')).toBe('https://www.nhs.uk/conditions/vitamins-and-minerals/vitamin-d/');
    expect(link.getAttribute('href')).not.toContain('?');
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
    expect(link.textContent).toMatch(/opens in a new tab/);
    expect(screen.getByText(/The links open the NHS website/)).toBeInTheDocument();
  });

  it('gives an unknown topic no link at all, and no note about links', async () => {
    withDashboard(
      withGuidance(
        [{ code: 'DIET', text: 'A varied diet.', becauseOfConditions: ['Obesity'] }],
        [flagged('Obesity')]
      )
    );
    renderDashboard();
    await screen.findByText(/Topics you could read about/);
    expect(document.querySelector('.guidance__link')).toBeNull();
    expect(screen.queryByText(/The links open the NHS website/)).toBeNull();
  });

  it('states one shared reason once, not once per row', async () => {
    withDashboard(
      withGuidance(
        [
          { code: 'DIET', text: 'A varied diet.', becauseOfConditions: ['Obesity'] },
          { code: 'MOVE', text: 'Regular activity.', becauseOfConditions: ['Obesity'] },
        ],
        [flagged('Obesity')]
      )
    );
    renderDashboard();

    await screen.findByText(/Topics you could read about/);
    expect(screen.getByText(/Shown because this report flagged Obesity/)).toBeInTheDocument();
    expect(document.querySelectorAll('.guidance__because')).toHaveLength(0);
  });

  it('REFUSES to hoist when the rows do not share a reason', async () => {
    withDashboard(
      withGuidance(
        [
          { code: 'DIET', text: 'A varied diet.', becauseOfConditions: ['Obesity'] },
          {
            code: 'SUGAR',
            text: 'Watch added sugar.',
            becauseOfConditions: ['Obesity', 'Diabetes'],
          },
        ],
        [flagged('Obesity'), flagged('Diabetes')]
      )
    );
    renderDashboard();

    await screen.findByText(/Topics you could read about/);
    expect(screen.queryByText(/Shown because this report flagged/)).not.toBeInTheDocument();
    const perRow = [...document.querySelectorAll('.guidance__because')].map(
      (el) => el.textContent
    );
    expect(perRow).toHaveLength(2);
    expect(perRow[0]).toMatch(/Obesity\./);
    expect(perRow[1]).toMatch(/Obesity and Diabetes\./);
  });

  it('hoists on set equality, not on list order', async () => {
    withDashboard(
      withGuidance(
        [
          {
            code: 'DIET',
            text: 'A varied diet.',
            becauseOfConditions: ['Obesity', 'Diabetes'],
          },
          {
            code: 'MOVE',
            text: 'Regular activity.',
            becauseOfConditions: ['Diabetes', 'Obesity'],
          },
        ],
        [flagged('Obesity'), flagged('Diabetes')]
      )
    );
    renderDashboard();

    await screen.findByText(/Topics you could read about/);
    expect(screen.getByText(/Shown because this report flagged/)).toBeInTheDocument();
    expect(document.querySelectorAll('.guidance__because')).toHaveLength(0);
  });

  it('drops a row whose topics were not flagged, and attributes only what is left', async () => {
    withDashboard(
      withGuidance(
        [
          { code: 'DIET', text: 'A varied diet.', becauseOfConditions: ['Obesity'] },
          { code: 'SLEEP', text: 'Sleep well.', becauseOfConditions: ['Insomnia'] },
        ],
        [flagged('Obesity')]
      )
    );
    renderDashboard();

    await screen.findByText(/Topics you could read about/);
    expect(document.querySelectorAll('.guidance > li')).toHaveLength(1);
    const shared = screen.getByText(/Shown because this report flagged/);
    expect(shared.textContent).toMatch(/Obesity/);
    expect(shared.textContent).not.toMatch(/Insomnia/);
  });

  it('keeps the "not personalised advice" line', async () => {
    withDashboard(
      withGuidance(
        [{ code: 'DIET', text: 'A varied diet.', becauseOfConditions: ['Obesity'] }],
        [flagged('Obesity')]
      )
    );
    renderDashboard();

    await screen.findByText(/Topics you could read about/);
    expect(screen.getByText(/are not instructions/)).toBeInTheDocument();
  });
});

describe('what may be collapsed, and what may not', () => {
  const withExplanations = (extra = {}) => ({
    overall: { statusLabel: 'Attention Needed', anyAssessed: true, risk: 'High' },
    laboratory: [
      { feature: 'hba1c', displayName: 'HbA1c', value: 8.4, unit: '%', state: 'measured', usable: true },
      { feature: 'cholesterol', displayName: 'Total Cholesterol', value: 268, unit: 'mg/dl', state: 'measured', usable: true },
    ],
    recommendations: {
      explanations: {
        available: true,
        entries: [
          {
            feature: 'hba1c',
            subject: 'the hba1c result',
            available: true,
            explanation: 'HbA1c reflects average blood sugar over recent months.',
          },
        ],
        notExplained: [{ feature: 'cholesterol', reason: 'explanation_limit_reached' }],
      },
      ...extra,
    },
  });

  it('closes each explanation by default but keeps its subject readable', async () => {
    withDashboard(withExplanations());
    renderDashboard();

    await screen.findByText(/What these results mean/);
    const panels = [...document.querySelectorAll('.explanation')];
    expect(panels.length).toBeGreaterThan(0);
    for (const panel of panels) {
      expect(panel.tagName).toBe('DETAILS');
      expect(panel.hasAttribute('open')).toBe(false);
      expect(panel.querySelector('summary .explanation__subject').textContent.trim())
        .not.toBe('');
    }
  });

  it('never puts a NEVER-ATTEMPTED explanation notice inside a disclosure', async () => {
    withDashboard(withExplanations());
    renderDashboard();

    const said = await screen.findByText(/have no explanation above|has no explanation above/);
    expect(said.closest('details')).toBeNull();
  });

  it('never puts a WITHHELD explanation notice inside a disclosure', async () => {
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true, risk: 'High' },
      laboratory: [
        { feature: 'hba1c', displayName: 'HbA1c', value: 8.4, unit: '%', state: 'measured', usable: true },
      ],
      recommendations: {
        explanations: {
          available: true,
          entries: [
            { feature: 'hba1c', subject: 'the hba1c result', available: true, explanation: 'A paragraph.' },
            { feature: 'creatinine', subject: 'the creatinine result', available: false },
          ],
        },
      },
    });
    renderDashboard();

    const said = await screen.findByText(/No plain-language explanation could be prepared/);
    expect(said.closest('details')).toBeNull();
  });

  it('never puts the "other tests we do not check" notice inside a disclosure', async () => {
    withDashboard({
      ...withExplanations(),
      unassessed: [
        { testName: 'LDL Cholesterol', value: 150, unit: 'mg/dl' },
        { testName: 'Urea', value: 30, unit: 'mg/dl' },
      ],
    });
    renderDashboard();

    await screen.findByText(/What these results mean/);
    const said = screen.queryByText(/other test[s]? it does not check/);
    if (said) expect(said.closest('details')).toBeNull();
  });

  it('keeps the model-provenance line out of a disclosure too', async () => {
    withDashboard(withExplanations());
    renderDashboard();

    await screen.findByText(/What these results mean/);
    const said = screen.getByText(/written by a language model/i);
    expect(said.closest('details')).toBeNull();
  });

  it('collapses the guidance section as a whole, with its count and qualifier', async () => {
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true, risk: 'High' },
      conditions: [
        { condition: 'Obesity', status: 'Indicated', risk: 'High', assessed: true, flagged: true },
      ],
      recommendations: {
        guidance: {
          items: [
            { code: 'DIET', text: 'A varied diet.', becauseOfConditions: ['Obesity'] },
            { code: 'MOVE', text: 'Regular activity.', becauseOfConditions: ['Obesity'] },
          ],
        },
      },
    });
    renderDashboard();

    const heading = await screen.findByText(/Topics you could read about/);
    const panel = heading.closest('details');
    expect(panel).not.toBeNull();
    expect(panel.hasAttribute('open')).toBe(false);
    expect(panel.querySelector('.disclosure__count').textContent.trim()).toBe('2');
    expect(screen.getByText(/are not instructions/).closest('details')).toBe(panel);
  });
});

describe('the guidance panel', () => {
  const open = () => ({
    overall: { statusLabel: 'Attention Needed', anyAssessed: true, risk: 'High' },
    conditions: [
      { condition: 'Obesity', status: 'Indicated', risk: 'High', assessed: true, flagged: true },
    ],
    recommendations: {
      guidance: {
        items: [
          { code: 'DIET', text: 'A varied diet.', becauseOfConditions: ['Obesity'] },
          { code: 'MOVE', text: 'Regular activity.', becauseOfConditions: ['Obesity'] },
          { code: 'WEIGHT', text: 'Body weight is one factor.', becauseOfConditions: ['Obesity'] },
        ],
      },
    },
  });

  it('offers no false link: the summary is the only control', async () => {
    withDashboard(open());
    renderDashboard();

    await screen.findByText(/Topics you could read about/);
    const list = document.querySelector('.disclosure__body .guidance');
    expect(list).not.toBeNull();
    expect(list.querySelectorAll('a, button, [role="button"], [role="link"], [tabindex]'))
      .toHaveLength(0);
    expect(document.querySelector('.disclosure--section > summary')).not.toBeNull();
  });

  it('puts the count next to the heading it counts', async () => {
    withDashboard(open());
    renderDashboard();

    const heading = await screen.findByText(/Topics you could read about/);
    const count = heading.nextElementSibling;
    expect(count).not.toBeNull();
    expect(count.className).toContain('disclosure__count');
    expect(count.textContent.trim()).toBe('3');
  });

  it('holds the attribution, the topics and the qualifier in ONE panel', async () => {
    withDashboard(open());
    renderDashboard();

    await screen.findByText(/Topics you could read about/);
    const body = document.querySelector('.disclosure--section .disclosure__body');
    expect(body).not.toBeNull();
    expect(body.querySelector('.guidance__shared')).not.toBeNull();
    expect(body.querySelector('.guidance')).not.toBeNull();
    expect(screen.getByText(/are not instructions/).closest('.disclosure__body')).toBe(body);
  });
});

describe('parameters this tool does not assess', () => {
  const withUnassessed = (items) => ({
    overall: { statusLabel: 'Healthy', anyAssessed: true, risk: 'Low' },
    laboratory: [
      { feature: 'hba1c', displayName: 'HbA1c', value: 5.2, unit: '%', state: 'measured', usable: true },
    ],
    unanalysed: { count: items.length, items },
  });

  const cellFor = (testName) => {
    const row = [...document.querySelectorAll('.lab-table tr')].find((tr) =>
      tr.querySelector('th').textContent.includes(testName)
    );
    return row ? row.children[2].textContent.replace(/\s+/g, ' ').trim() : null;
  };

  it('compares against the range the LABORATORY printed, and attributes it', async () => {
    withDashboard(
      withUnassessed([
        {
          testName: 'Ferritin',
          value: 12,
          unit: 'ng/ml',
          labFlag: 'low',
          labFlaggedAbnormal: true,
          labReferenceLow: 15,
          labReferenceHigh: 150,
        },
      ])
    );
    renderDashboard();

    await screen.findAllByText('Ferritin');
    expect(cellFor('Ferritin')).toMatch(/low/i);
  });

  it('says NO RANGE rather than implying the result is fine', async () => {
    withDashboard(
      withUnassessed([{ testName: 'Urine Colour', value: 'Yellow', unit: null }])
    );
    renderDashboard();

    await screen.findAllByText('Urine Colour');
    expect(cellFor('Urine Colour')).toMatch(/not checked/i);
  });

  it('KEEPS a laboratory marking that arrives with no printed range', async () => {
    withDashboard(
      withUnassessed([
        {
          testName: 'Blood Urea',
          value: 58,
          unit: 'mg/dl',
          labFlag: 'high',
          labFlaggedAbnormal: true,
        },
      ])
    );
    renderDashboard();

    await screen.findAllByText('Blood Urea');
    const cell = cellFor('Blood Urea');
    expect(cell).toMatch(/high/i);
    expect(cell).not.toMatch(/not checked/i);
  });


  it('offers no entry, and no qualifier, when nothing was described', async () => {
    withDashboard({
      ...withUnassessed([{ testName: 'Urine Colour', value: 'Yellow' }]),
      recommendations: {
        explanations: {
          available: true,
          entries: [
            {
              feature: 'hba1c',
              subject: 'the hba1c result',
              available: true,
              explanation: 'HbA1c reflects average blood sugar.',
            },
          ],
        },
      },
    });
    renderDashboard();

    await screen.findByText(/What these results mean/);
    const subjects = [...document.querySelectorAll('.explanation__subject')]
      .map((node) => node.textContent.trim());
    expect(subjects).toContain('HbA1c (average blood sugar)');
    expect(subjects).not.toContain('Urine Colour');
    expect(
      screen.queryByText(/written from the name of the test alone/)
    ).not.toBeInTheDocument();
  });

  it('shows each parameter exactly ONCE on the page', async () => {
    withDashboard(
      withUnassessed([
        {
          testName: 'Potassium, Serum',
          value: 5.9,
          unit: 'mmol/l',
          labFlag: 'high',
          labFlaggedAbnormal: true,
          descriptionAvailable: true,
          description: 'A mineral your body uses for nerve and muscle function.',
        },
      ])
    );
    renderDashboard();

    await screen.findAllByText('Potassium, Serum');
    expect(screen.queryByText(/Also on your report, but not assessed here/)).not.toBeInTheDocument();
    const rows = [...document.querySelectorAll('.lab-table tr')].filter((tr) =>
      tr.querySelector('th')?.textContent.startsWith('Potassium, Serum')
    );
    expect(rows).toHaveLength(1);
    expect(
      screen.getAllByText(/A mineral your body uses for nerve and muscle function./)
    ).toHaveLength(1);
  });
});


describe('a row the laboratory compared but no rule read', () => {
  const withLabRows = (rows) => ({
    overall: { statusLabel: 'Healthy', anyAssessed: true, risk: 'Low' },
    laboratory: rows,
    unanalysed: { count: 0, items: [] },
  });

  const verdictFor = (name) => {
    const row = [...document.querySelectorAll('.lab-table tr')].find((tr) =>
      tr.querySelector('th')?.textContent.includes(name)
    );
    return row ? row.children[2].textContent.replace(/\s+/g, ' ').trim() : null;
  };

  const row = (extra) => ({
    feature: 'neutrophils',
    displayName: 'Neutrophils',
    value: 82,
    unit: '%',
    state: 'measured',
    usable: true,
    ...extra,
  });

  it('reports the laboratory flag instead of "not checked"', async () => {
    withDashboard(
      withLabRows([row({ flag: 'high', referenceLow: 40, referenceHigh: 70 })])
    );
    renderDashboard();

    await screen.findAllByText('Neutrophils');
    expect(verdictFor('Neutrophils')).toMatch(/high/i);
    expect(verdictFor('Neutrophils')).not.toMatch(/not checked/i);
  });

  it('says In range when the value sits inside the printed interval', async () => {
    withDashboard(
      withLabRows([
        row({
          feature: 'mcv',
          originalTestName: 'MCV',
          displayName: 'Mean corpuscular volume',
          value: 88.6,
          unit: 'fl',
          flag: 'normal',
          referenceLow: 80,
          referenceHigh: 97,
        }),
      ])
    );
    renderDashboard();

    await screen.findAllByText('MCV');
    expect(verdictFor('MCV')).toMatch(/in range/i);
  });

  it('STILL says not checked when nothing compared it', async () => {
    withDashboard(
      withLabRows([
        row({
          feature: 'hematocrit',
          originalTestName: 'PCV',
          displayName: 'Haematocrit (PCV)',
          value: 37.9,
          unit: '%',
          flag: null,
          referenceLow: null,
          referenceHigh: null,
        }),
      ])
    );
    renderDashboard();

    await screen.findAllByText('PCV');
    expect(verdictFor('PCV')).toMatch(/not checked/i);
  });
});

describe('the count of further out-of-range results', () => {
  const summaryText = () =>
    document.querySelector('.in-short')?.textContent.replace(/\s+/g, ' ').trim()
    || document.body.textContent.replace(/\s+/g, ' ').trim();

  const report = {
    overall: { statusLabel: 'Needs Monitoring', risk: 'Low', anyAssessed: true, complete: true },
    conditions: [
      {
        condition: 'Anemia',
        status: 'Indicated',
        risk: 'Low',
        assessed: true,
        flagged: true,
        evidenceFeatures: ['hemoglobin'],
        sources: ['Clinical Rule Engine'],
        sourceKinds: ['clinical_rule'],
      },
    ],
    laboratory: [
      {
        feature: 'hemoglobin', originalTestName: 'HEMOGLOBIN', value: 12.5, unit: 'g/dl',
        state: 'measured', usable: true, flag: 'low', referenceLow: 13, referenceHigh: 17,
      },
      {
        feature: 'neutrophils', originalTestName: 'NEUTROPHILS', value: 82, unit: '%',
        state: 'measured', usable: true, flag: 'high', referenceLow: 40, referenceHigh: 70,
      },
      {
        feature: 'lymphocytes', originalTestName: 'LYMPHOCYTES', value: 14, unit: '%',
        state: 'measured', usable: true, flag: 'low', referenceLow: 20, referenceHigh: 40,
      },
      {
        feature: 'mcv', originalTestName: 'MCV', value: 88.6, unit: 'fl',
        state: 'measured', usable: true, flag: 'normal', referenceLow: 80, referenceHigh: 97,
      },
    ],
    unanalysed: {
      count: 1,
      labFlaggedCount: 1,
      items: [{ testName: 'ESR', value: '45', labFlaggedAbnormal: true, labFlag: 'high' }],
    },
  };

  it('counts every out-of-range result no condition above accounts for', async () => {
    withDashboard(report);
    renderDashboard();

    await screen.findByText(/In short/);
    const text = summaryText();
    expect(text).toMatch(/3 further results are outside the range printed on the report/);
    expect(text).toMatch(/Neutrophils/);
    expect(text).toMatch(/Lymphocytes/);
    expect(text).toMatch(/ESR/);
  });

  it('does not repeat a result the named conditions already explain', async () => {
    withDashboard(report);
    renderDashboard();

    await screen.findByText(/In short/);
    const caveat = [...document.querySelectorAll('.caveat')]
      .map((p) => p.textContent)
      .find((t) => /further result/.test(t)) || '';
    expect(caveat).not.toMatch(/HEMOGLOBIN/);
    expect(caveat).not.toMatch(/MCV/);
  });
});

describe('a row whose printed interval and rule threshold disagree', () => {
  const withRows = (rows, evidence) => ({
    overall: { statusLabel: 'Needs Medical Attention', anyAssessed: true, risk: 'High' },
    laboratory: rows,
    unanalysed: { count: 0, items: [] },
    ...(evidence ? { evidence: { conditions: evidence } } : {}),
  });

  const verdictFor = (name) => {
    const row = [...document.querySelectorAll('.lab-table tr')].find((tr) =>
      tr.querySelector('th')?.textContent.includes(name)
    );
    return row ? row.children[2].textContent.replace(/\s+/g, ' ').trim() : null;
  };

  const classesFor = (name) => {
    const row = [...document.querySelectorAll('.lab-table tr')].find((tr) =>
      tr.querySelector('th')?.textContent.includes(name)
    );
    return row ? row.children[2].querySelector('.verdict')?.className || '' : '';
  };

  const PCV = {
    feature: 'hematocrit',
    displayName: 'Haematocrit',
    value: 37.9,
    unit: '%',
    state: 'measured',
    usable: true,
    flag: null,
    referenceLow: 40,
    referenceHigh: 50,
  };

  const HAEMOGLOBIN = {
    feature: 'hemoglobin',
    displayName: 'Haemoglobin',
    value: 12.5,
    unit: 'g/dl',
    state: 'measured',
    usable: true,
    flag: null,
    referenceLow: 12,
    referenceHigh: 16,
  };

  const ANAEMIA_EVIDENCE = [
    {
      condition: 'Anemia',
      lines: [
        {
          feature: 'hemoglobin',
          value: 12.5,
          unit: 'g/dl',
          comparator: '<',
          threshold: 13,
        },
      ],
    },
  ];

  it('⚠ does NOT call a value below its printed interval "In range"', async () => {
    withDashboard(withRows([PCV]));
    renderDashboard();

    await screen.findAllByText('Haematocrit');
    expect(verdictFor('Haematocrit')).toMatch(/low/i);
    expect(verdictFor('Haematocrit')).not.toMatch(/in range/i);
    expect(verdictFor('Haematocrit')).not.toMatch(/not checked/i);
  });

  it('says both references when they disagree, and names each', async () => {
    withDashboard(withRows([HAEMOGLOBIN], ANAEMIA_EVIDENCE));
    renderDashboard();

    await screen.findAllByText('Haemoglobin');
    const cell = verdictFor('Haemoglobin');
    expect(cell).toMatch(/in range/i);
    expect(cell).toMatch(/12.*16/);
    expect(cell).toMatch(/below 13 g\/dl/i);
    expect(cell).toMatch(/the threshold this tool applies/i);
  });

  it('⚠ does not style a disagreement as a settled "In range"', async () => {
    withDashboard(withRows([HAEMOGLOBIN], ANAEMIA_EVIDENCE));
    renderDashboard();

    await screen.findAllByText('Haemoglobin');
    expect(classesFor('Haemoglobin')).toMatch(/verdict--mixed/);
    expect(classesFor('Haemoglobin')).not.toMatch(/verdict--normal/);
  });

  it('says it once when the two references AGREE', async () => {
    const low = { ...HAEMOGLOBIN, value: 10.5 };
    withDashboard(
      withRows([low], [
        {
          condition: 'Anemia',
          lines: [
            { feature: 'hemoglobin', value: 10.5, unit: 'g/dl', comparator: '<', threshold: 13 },
          ],
        },
      ])
    );
    renderDashboard();

    await screen.findAllByText('Haemoglobin');
    expect(verdictFor('Haemoglobin')).toMatch(/low/i);
    expect(verdictFor('Haemoglobin')).not.toMatch(/the threshold this tool applies/i);
  });

  it('still says "not checked" when there is no interval and no rule', async () => {
    withDashboard(withRows([{ ...PCV, referenceLow: null, referenceHigh: null }]));
    renderDashboard();

    await screen.findAllByText('Haematocrit');
    expect(verdictFor('Haematocrit')).toMatch(/not checked/i);
  });

  it('keeps an abnormal laboratory flag even when the arithmetic disagrees', async () => {
    withDashboard(withRows([{ ...PCV, value: 45, flag: 'low' }]));
    renderDashboard();

    await screen.findAllByText('Haematocrit');
    expect(verdictFor('Haematocrit')).toMatch(/low/i);
  });
});

describe('a printed band label, which is not a reference range', () => {
  const withRows = (rows) => ({
    overall: { statusLabel: 'Needs Medical Attention', anyAssessed: true, risk: 'High' },
    laboratory: rows,
    unanalysed: { count: 0, items: [] },
  });

  const cellFor = (name) => {
    const tr = [...document.querySelectorAll('.lab-table tr')].find((r) =>
      r.querySelector('th')?.textContent.includes(name)
    );
    return tr ? tr.children[2].textContent.replace(/\s+/g, ' ').trim() : null;
  };

  const EAG = {
    feature: 'estimated_average_glucose',
    displayName: 'Average blood glucose',
    value: 154,
    unit: 'mg/dL',
    state: 'measured',
    usable: true,
    flag: null,
    referenceLow: null,
    referenceHigh: null,
    referenceRangeRaw: '151 - 180 - Average Control',
  };

  it('still says "not checked" -- the absence is the verdict', async () => {
    withDashboard(withRows([EAG]));
    renderDashboard();

    await screen.findAllByText('Average blood glucose');
    expect(cellFor('Average blood glucose')).toMatch(/not checked/i);
  });

  it('⚠ never renders the band as a result of "In range"', async () => {
    withDashboard(withRows([EAG]));
    renderDashboard();

    await screen.findAllByText('Average blood glucose');
    expect(cellFor('Average blood glucose')).not.toMatch(/in range/i);
    expect(cellFor('Average blood glucose')).not.toMatch(/\bnormal\b(?!\s+range)/i);
  });

  it('quotes what the report printed, and says what it is not', async () => {
    withDashboard(withRows([EAG]));
    renderDashboard();

    await screen.findAllByText('Average blood glucose');
    const cell = cellFor('Average blood glucose');
    expect(cell).toMatch(/151 - 180 - Average Control/);
    expect(cell).toMatch(/The report prints/i);
    expect(cell).toMatch(/not a normal range/i);
  });

  it('adds nothing when the report printed no text at all', async () => {
    withDashboard(withRows([{ ...EAG, referenceRangeRaw: null }]));
    renderDashboard();

    await screen.findAllByText('Average blood glucose');
    expect(cellFor('Average blood glucose')).toMatch(/not checked/i);
    expect(cellFor('Average blood glucose')).not.toMatch(/The report prints/i);
  });

  it('adds nothing to a row that WAS compared', async () => {
    withDashboard(
      withRows([{ ...EAG, referenceLow: 70, referenceHigh: 140, referenceRangeRaw: '70 - 140' }])
    );
    renderDashboard();

    await screen.findAllByText('Average blood glucose');
    expect(cellFor('Average blood glucose')).not.toMatch(/The report prints/i);
  });
});
