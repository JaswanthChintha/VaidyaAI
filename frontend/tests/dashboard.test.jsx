import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Dashboard from '../src/pages/Dashboard';
import { api } from '../src/lib/api';

/**
 * Module 27's screen, tested on the cases that have actually gone wrong.
 *
 * These are not invented edge cases. Every scenario below is a defect an
 * audit found somewhere in this system, reproduced at the rendering layer to
 * make sure the fix is not undone by a template:
 *
 *   - a partial assessment printing as a flat "Healthy"  (section 6n, D3)
 *   - a missing risk becoming "Low"                      (section 6p, D3)
 *   - an unassessed condition reading as a clean bill    (section 11)
 *   - a rejected reading rendering as 0                  (section 11)
 */

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

/**
 * The overall CARD, scoped to the card.
 *
 * These assertions were written page-wide and were correct while the verdict
 * appeared exactly once. The closing "In short" summary now legitimately
 * restates the label and the risk at the foot of the page, so a page-wide
 * `queryByText('Healthy')` would fail on a correct page and, worse, would
 * stop anyone adding a second honest mention of a verdict anywhere.
 *
 * The guarantee is unchanged and is about THIS CARD: it must print the
 * five-valued label rather than flattening it to the three-valued status, and
 * it must never turn a missing risk into a low one. Both are now asserted
 * against the card's own text.
 */
const overallCardText = () => document.querySelector('.overall').textContent;

/**
 * "Low" as a VALUE, anywhere on the page -- excluding the gauge's printed
 * scale.
 *
 * The risk gauge carries a permanent LOW / MEDIUM / HIGH axis, the way a dial
 * face is printed: it is part of the instrument, not a statement about this
 * patient, and it is `--mono` micro-type rather than the serif verdict word.
 * A page-wide `queryByText('Low')` cannot tell the two apart any more, so the
 * axis is excluded and the guarantee itself is untouched -- a missing risk
 * must still never surface as the word Low anywhere a reader would take it as
 * an answer.
 */
function riskWordShown(word) {
  return screen
    .queryAllByText(word)
    .some((node) => !node.closest('.gauge__scale'));
}

describe('the overall card', () => {
  it('prints the five-valued LABEL, never the three-valued status', async () => {
    // Module 18 emits `Healthy (partial assessment)` precisely because a
    // partial clean result was otherwise byte-identical to a full one. An
    // audit found the backend flattening it; the UI must not re-flatten it.
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
    // The bare word must not appear as this card's headline on its own.
    expect(overallCardText()).toContain('Healthy (partial assessment)');
    expect(overallCardText()).not.toMatch(/Healthy(?! \(partial assessment\))/);
    expect(screen.getByText(/assessment is incomplete/)).toBeInTheDocument();
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
    // Page-wide: a missing risk must not become "Low" ANYWHERE, summary
    // included. That one stays unscoped on purpose.
    expect(riskWordShown('Low')).toBe(false);
  });

  it('refuses a risk when nothing was assessed, even if one arrives', async () => {
    // Defence in depth: the backend now nulls this, but if a risk ever
    // arrives beside `anyAssessed: false`, the screen must not print it.
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

    // An unassessed topic is now summarised in one line rather than given a
    // full card, so it is matched inside its sentence. The guarantee is
    // unchanged and is the whole point of this test: it must be reported as
    // NOT CHECKED, and must never carry a risk level -- "we could not look"
    // must not be renderable as "we looked and it was fine".
    // Named in the round-up above AND in the closing summary -- both are
    // correct, and both matter: an unchecked topic must not go quiet in
    // either place.
    expect(await screen.findAllByText(/Kidney Disease/)).not.toHaveLength(0);
    expect(screen.getByText(/Not enough information to check/i)).toBeInTheDocument();
    expect(riskWordShown('Low')).toBe(false);
  });

  it('keeps the two-checks-disagreed lecture OFF the patient card', async () => {
    // SECOND REMOVAL OF THIS SHAPE. §6w took out the paragraph explaining that
    // "Needs Monitoring" and "risk Low" do not contradict each other, on the
    // user's own instruction -- "display only what is useful for the
    // patients" -- and the generalisation recorded then was: when a screen
    // needs a paragraph explaining why two of its own fields do not
    // contradict each other, the fields are the bug, not the missing
    // paragraph. A risk-factor tally versus a model probability is that, and a
    // patient cannot adjudicate between them.
    //
    // NOTHING IS HIDDEN BY THIS. `basisConflict` and `basisNote` stay in the
    // payload, and the clinician passage still says which kind of check
    // flagged what -- including the model-only case, which is the one a reader
    // can actually be misled by (tests/clinical.test.jsx).
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
    // The clinician's wording must not leak either.
    expect(screen.queryByText(/risk-factor count and a model probability/)).not.toBeInTheDocument();
  });

  describe('a topic the model flagged and the thresholds did not', () => {
    // THE REAL SHAPE, off a live report: Kidney Disease shows creatinine
    // 1.1 mg/dl crossing nothing, under a verdict of High, because the
    // Clinical Rule Engine returned Not Indicated and the Random Forest
    // returned Indicated. Without a sentence the reader has a normal-looking
    // number and a serious word with nothing joining them.
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
      // "These results point to this" describes a comparison of measured
      // values, and on this card no comparison found anything -- it sat above
      // a creatinine of 1.1 mg/dl, in range, under a verdict of High. Same
      // fault RISK_FACTOR_STATUS exists to fix, in a third basis.
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
      // THE ORDERING HAZARD. A rule that counts risk factors and finds NONE
      // returns Not Indicated with no threshold comparison anywhere, so
      // `countsRiskFactors` and `flaggedByModelAlone` are true at once. Taking
      // the risk-factor wording there would say "several things here are known
      // to raise this risk" about a count that came back empty.
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
      // Both would be on screen saying overlapping things, and the vaguer one
      // is the one that cannot explain the card.
      withDashboard(kidney([RULE_CLEAR, MODEL_FOUND]));
      renderDashboard();

      await screen.findByText(/No measured value crossed a standard limit/);
      expect(
        screen.queryByText(/Checked against standard clinical thresholds/)
      ).not.toBeInTheDocument();
    });

    it('stays silent when the threshold check ALSO found something', async () => {
      // Diabetes on the same report: both said Indicated. The rows carry the
      // crossings, and this sentence would be false.
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
      // Heart Disease on the same report: rule Indicated, model Not
      // Indicated. The opposite case, and this sentence would invert it.
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
      // No per-source verdicts at all. Missing information is not agreement
      // and it is not disagreement -- the same reasoning the removed
      // `shouldShowBasisNote` got right.
      withDashboard(kidney([]));
      renderDashboard();

      await screen.findAllByText(/Kidney Disease/);
      expect(
        screen.queryByText(/No measured value crossed a standard limit/)
      ).not.toBeInTheDocument();
    });

    it('needs BOTH verdicts, not just the model’s', async () => {
      // Only the model's verdict in the evidence. "No measured value crossed a
      // standard limit" is then a claim about a check whose result is not on
      // hand -- and with one source missing, a guard that only asks "are both
      // absent?" reads `undefined.status` and takes the page down with it.
      withDashboard(kidney([MODEL_FOUND]));
      renderDashboard();

      await screen.findAllByText(/Kidney Disease/);
      expect(
        screen.queryByText(/No measured value crossed a standard limit/)
      ).not.toBeInTheDocument();
    });

    it('does not take a clear verdict from a source that was not assessed', async () => {
      // `assessed: false` with a status of Not Indicated is not a threshold
      // check that came back clear -- it is a check that did not run.
      withDashboard(kidney([{ ...RULE_CLEAR, assessed: false }, MODEL_FOUND]));
      renderDashboard();

      await screen.findAllByText(/Kidney Disease/);
      expect(
        screen.queryByText(/No measured value crossed a standard limit/)
      ).not.toBeInTheDocument();
    });

    it('never reads an absence as the model having found something', async () => {
      // `Insufficient Data` is an absence. "Not Not-Indicated" would make it a
      // finding and print a sentence about a model that declined to answer.
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
    // "Your BMI were also taken into account" -- read off the live Obesity
    // card, which cites exactly one profile-derived feature. The sentence
    // above it already switches "it"/"they"; this one never learned to.
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
    // §6w: an unknown label never gets a guessed gloss -- a missing gloss is
    // cosmetic, a wrong one is clinical. The raw word is shown instead, and a
    // reader seeing an unfamiliar word is better served than one reading a
    // confident sentence the analysis did not support. Three status tables now
    // share this fallback, so it is worth an assertion of its own.
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
    // The shape that killed the first version of this gate. `isClear` requires
    // the exact status `Not Indicated`, so a Borderline topic is shown under
    // "Worth a closer look" with `flagged` NOT true. Gating the explanation on
    // `flagged === true` stripped it from exactly the cards least able to
    // speak for themselves.
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
    // The gate that stops the cut going too far. A topic the model flagged
    // with NO crossed value on screen has nothing saying where the verdict
    // came from, and a verdict with no reason is a thing to be believed or
    // not.
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
    // `268 mg/dl  above 240 mg/dl` IS the explanation. "Checked against
    // standard clinical thresholds" above it is the screen describing itself
    // -- §6u removed "Based on: Clinical Rule Engine, Random Forest" from this
    // same card for exactly that, and this is the same sentence in friendlier
    // words.
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
                // The producer's field names, read off a live dashboard
                // response -- not guessed. §6w: a fixture written against the
                // consumer's assumption cannot catch that assumption being
                // wrong.
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

describe('what a condition card says it took into account', () => {
  // THE CARD NAMED TWO THINGS IT DID NOT HAVE. Every cited feature with a
  // patient label was listed as "taken into account" regardless of
  // availability, so a Heart Disease card said "Your history of heart
  // disease, history of high blood pressure ... were also taken into account"
  // on a report where both were `not_present_in_report` with a null value.
  //
  // The heart model's own author note says blood pressure is "the strongest
  // known predictor" and is not collected by this platform. The card asserted
  // the opposite of the assessment's single most important limitation.
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
    // The absent one must not appear in the "taken into account" sentence.
    expect(card.textContent).not.toMatch(
      /history of high blood pressure[^.]*were also taken into account/
    );
  });

  it('NAMES the absent feature rather than dropping it silently', async () => {
    // Dropping it is the same failure from the other side: the reader would
    // never learn the strongest predictor was missing from the assessment.
    withDashboard(heartCard([OBSERVED_BMI, ABSENT_HYPERTENSION]));
    renderDashboard();

    await screen.findAllByText(/Heart Disease/);
    const card = document.querySelector('.condition');
    expect(card.textContent).toMatch(/No value was available for your/);
    expect(card.textContent).toMatch(/history of high blood pressure/);
    expect(card.textContent).toMatch(/could not be taken into account/);
  });

  it('does not say "close to the usual limit" when nothing was compared to one', async () => {
    // A Heart Disease card read "Close to the usual limit" directly above
    // "268 mg/dl above 240 mg/dl" and "8.4 % above 6.5 %". Both sentences
    // were true of different things -- the risk-factor COUNT was borderline,
    // the individual values were over -- and the reader could not tell.
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
    // The mirror: a topic decided by a threshold comparison must keep the
    // concrete description. Only a topic with no comparison at all changes.
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
    // The gate is `counted && !compared`, and the second half is what this
    // covers: if a value really did cross a cut-off, that is the more
    // concrete thing to tell the reader, even though a count also ran.
    // Without this the gate could be reduced to `counted` and every test
    // still passed.
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
    // IT USED TO BE THE VERDICT -- flagged 0.95, clear 0.55 -- so a report with
    // everything abnormal drew a full pentagon under the word "Coverage", and
    // a full shape reads as thorough. Diabetes here cites four inputs and two
    // were available, so it sits at half despite being flagged.
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
    // The flagged topic is the LESS covered one, and the chart says so.
    expect(label).toMatch(/Diabetes 2 of 4/);
    expect(label).toMatch(/Anemia 1 of 1/);
    // AND THE GEOMETRY AGREES. Asserting only the words let the radius go
    // quietly back to being the verdict: the top spoke runs from the centre
    // (139,106) to (139,22), so half coverage is cy 64 -- a flagged topic
    // sitting INSIDE a clear one, which the old version could never draw.
    const vertices = document.querySelectorAll('.radar__vertex');
    expect(Number(vertices[0].getAttribute('cy'))).toBeCloseTo(64, 0);
  });

  it('counts one input once, however many rules cite it', async () => {
    // Two rules naming the same feature produce two identical lines -- the
    // reason `summariseEvidence` exists. Counted twice they inflate the
    // coverage of exactly the topics that have several rules.
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
              // The SAME feature twice, observed first and absent second --
              // the ordering that decides whether "any line observed it" or
              // "the last line wins". An input the assessment had is an input
              // it had, whatever a second citation of it says.
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
    // An unassessed topic has no evidence lines either, so a guard that simply
    // dropped every topic without countable inputs would delete the dashed
    // point -- which is the entire reason this chart exists.
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
    // ...and the caption explaining that point comes back with it.
    expect(screen.getByText(/dotted point sits at zero/)).toBeInTheDocument();
  });

  it('leaves a topic off the radar when its coverage cannot be computed', async () => {
    // There is no number for "we do not know how much we saw", and a radius
    // would be inventing one. The condition card below still reports it.
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
    // ...and it is still on the page as a card.
    expect(screen.getAllByText(/Diabetes/).length).toBeGreaterThan(0);
  });

  describe('results with no explanation prepared', () => {
    // A REPORT WITH MORE RESULTS THAN EXPLANATIONS. Module 23 writes up to six
    // and records the rest as skipped; the page showed six cards and said
    // nothing about the other two. A partial set that looks complete is this
    // codebase's standing failure, and the entries array cannot carry it -- an
    // explanation that was never requested has no entry to be absent in.
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
      // "Never attempted" is not "withheld". The withheld sentence blames the
      // writing step; this one must not, or a reader is told their result was
      // refused when it was simply not reached.
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
      // `skipped` also names the profile answers the assessment used. "No
      // explanation was prepared for your age" is the screen describing its
      // own mechanics; nobody was waiting to be told what age measures.
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
      // No explanation rendered at all: there is no partial set to mistake for
      // a complete one, and "not explained above" would point at nothing.
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
      expect(screen.queryByText(/What these results mean/)).not.toBeInTheDocument();
      expect(screen.queryByText(/no explanation above/)).not.toBeInTheDocument();
    });

    it('says nothing at all when every result was explained', async () => {
      withDashboard(withSkipped([]));
      renderDashboard();

      await screen.findAllByText(/average blood sugar/);
      expect(screen.queryByText(/no explanation above/)).not.toBeInTheDocument();
    });

    it('says the report has tests this tool does not check, and where they are', async () => {
      // A READER'S COMPLAINT, on a real report: "this section doesn't contain
      // all parameters listed in the report". True -- the report prints
      // twelve, this tool assesses eight, and the other four are on the page
      // under their own heading further up. Nothing in a section titled "What
      // these results mean" said so, so eight read as all of them.
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
      expect(
        screen.getByText(/lists 4 other tests it does not check/)
      ).toBeInTheDocument();
      // THE INVARIANT IS UNCHANGED: the pointer must name a place that
      // exists. The place moved -- these rows are a labelled group inside
      // "Your results" now, rather than a section of their own further down
      // -- so the signpost points there and the group heading is asserted to
      // be on the page. A signpost to a section that does not exist is worse
      // than none, which is exactly what this test is for.
      expect(
        screen.getByText(/in .Your results. above, with your laboratory/)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Also on your report — not assessed by this tool/)
      ).toBeInTheDocument();
    });

    it('does not mention other tests when the report has none', async () => {
      withDashboard(withSkipped([]));
      renderDashboard();

      await screen.findAllByText(/average blood sugar/);
      expect(screen.queryByText(/other tests it does not check/)).not.toBeInTheDocument();
      expect(screen.queryByText(/other test it does not check/)).not.toBeInTheDocument();
    });

    it('counts the tests off the items, never off the payload counter', async () => {
      // §6u: `unmapped_count` said 0 on a report carrying 63 of them, and the
      // dashboard repeated it. The list on screen is the only honest count.
      withDashboard({
        ...withSkipped([]),
        unanalysed: {
          count: 0,
          items: [{ testName: 'Blood Urea' }, { testName: 'Potassium, Serum' }],
        },
      });
      renderDashboard();

      await screen.findAllByText(/average blood sugar/);
      expect(
        screen.getByText(/lists 2 other tests it does not check/)
      ).toBeInTheDocument();
    });

    it('joins two names with "and", not a bare comma', async () => {
      // "Total cholesterol, Triglycerides are not explained above" is not a
      // sentence. Read off the live page.
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
      // `.lab-table td` is monospace with tabular numerals so figures align
      // down the column (design.md §3). "male" aligns with nothing; the only
      // thing the treatment carries there is the look of a measured value,
      // and it sat directly under `26.42 kg/m2` on a real screen.
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
      // The producer's own word, first letter only -- not a relabelling.
      expect(screen.queryByText('male')).not.toBeInTheDocument();
    });
  });

  it('calls an unanswered profile question absent, NOT rejected', async () => {
    // `usable: false` covers two different things, and mapping both to
    // "rejected" put NOT USABLE against three rows of a real report --
    // claiming a reading was taken and refused when the patient had simply
    // never answered the question. `state: 'unavailable'` is the payload's
    // own word for never-there.
    withDashboard({
      overall: { statusLabel: 'Healthy', anyAssessed: true, risk: 'Low' },
      laboratory: [
        // A measured row alongside it: a row nobody answered is only ever
        // seen beside rows that were, and the rule is about telling the two
        // apart.
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
          feature: 'smoking_history',
          displayName: 'Smoking history',
          value: null,
          state: 'unavailable',
          usable: false,
          source: null,
        },
      ],
    });
    renderDashboard();

    await screen.findAllByText(/Smoking history/i);
    expect(screen.queryByText('Not usable')).not.toBeInTheDocument();
    // The table's own word for never-there. `Not usable` above is the one
    // it must never be, because that claims a reading was taken and refused.
    expect(screen.getAllByText('Not measured').length).toBeGreaterThan(0);
  });
});

describe('laboratory rows', () => {
  it('keeps the pipeline’s own warnings off the patient page', async () => {
    // "Worth knowing about this analysis" printed stage warnings verbatim:
    // "'25-Hydroxy Vitamin D' reported unit 'ng/dL', which is not a recognised
    // unit for feature 'vitamin_d' (canonical: 'ng/ml'). The value was left
    // unconverted and flagged canonical_unit=false." That is a bug report. It
    // is still in the stored analysis and on GET /reports/:id/analysis.
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
        // A banded row so the range chart actually renders -- without one the
        // chart is not drawn at all and the assertions below only ever see the
        // table, which let the chart keep printing the validator's message.
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

    // Matched loosely: the row is titled by whatever the LAB printed, falling
    // back to the patient-facing name ("Creatinine (kidney marker)"). Which of
    // those appears is not the guarantee here -- the guarantee is that the row
    // is named at all, and that the rejected value never renders as a number.
    // Named in the range chart AND in the results table below it.
    expect(await screen.findAllByText(/Creatinine/)).not.toHaveLength(0);
    expect(screen.queryByText('999 mg/dl')).not.toBeInTheDocument();
    expect(screen.queryByText('0 mg/dl')).not.toBeInTheDocument();
    // THE FACT, IN THE READER'S WORDS. design.md §6 asks for a reason under a
    // rejected row, and there is one -- but not the validator's own message.
    // That names an internal feature key and a canonical unit; a patient can
    // act on "it was not used", and nothing else in it.
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

    // Shown by the chart and by the table; both must print the real zero.
    expect(await screen.findAllByText('0 ng/ml')).not.toHaveLength(0);
  });

  it('says so when no reference interval was printed', async () => {
    withDashboard({
      overall: { statusLabel: 'Healthy', anyAssessed: true },
      laboratory: [
        {
          feature: 'hba1c',
          displayName: 'HbA1c',
          value: 5.4,
          unit: '%',
          state: 'valid',
          usable: true,
          referenceLow: null,
          referenceHigh: null,
        },
      ],
    });
    renderDashboard();

    // Said ONCE for the table, not repeated on every row. A report that prints
    // no ranges used to pay for a whole column of identical "No range printed"
    // cells, which buried the results it was meant to qualify. The guarantee
    // is unchanged: the reader must be told, so they understand why nothing is
    // marked high or low.
    expect(
      await screen.findByText(/did not print normal ranges/i)
    ).toBeInTheDocument();
  });
});

describe('the closing "In short" summary', () => {
  // Read the whole section's text rather than hunting single elements: these
  // sentences deliberately carry <strong> inside them, which splits the text
  // across nodes, and a matcher that broke on emphasis would be testing the
  // markup instead of what the reader sees.
  const summaryText = () => document.querySelector('.in-short').textContent;

  // The summary is COMPOSED from decisions already on the page, never
  // generated. So the properties worth testing are all about agreement: it
  // must say the same thing as the cards above it, and it must not let any of
  // the three absences disappear on the way into one paragraph.

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
    // "Recorded as Needs Monitoring · overall risk: Low" is the pipeline's
    // vocabulary, not the patient's, and putting the two labels side by side
    // is what made them read as a contradiction. The severity is carried by
    // the English sentence instead. The labels stay on the Overall card and
    // the clinician summary.
    expect(summaryText()).not.toMatch(/Recorded as/);
    expect(summaryText()).not.toMatch(/Needs Medical Attention/);
  });

  it('refuses to invent English for a label it does not know', async () => {
    // If Module 18 grows a sixth status, guessing at its meaning would put a
    // fabricated conclusion under a real one.
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
    // `abnormalConditionCount` deliberately lies here. The page groups cards
    // with its own predicate, so the summary must count those - a summary
    // saying six over five visible cards is worse than no summary.
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
    // The collapse rule of the cards above, restated here because this is the
    // paragraph where a card could quietly become reassurance: only a
    // provably clear card is listed as showing nothing.
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

  it('never lets an unchecked topic vanish into the summary', async () => {
    withDashboard({
      overall: {
        statusLabel: 'Healthy (partial assessment)',
        risk: 'Low',
        anyAssessed: true,
        complete: false,
        unassessedConditionCount: 1,
      },
      conditions: [clear('Anemia'), unassessed('Kidney Disease')],
    });
    renderDashboard();

    await screen.findByText(/In short/);
    expect(summaryText()).toMatch(/1 topic could not be checked/);
    expect(summaryText()).toMatch(/Kidney Disease/);
    expect(summaryText()).toMatch(/open question, not a clear result/);
    // A partial clean result must not read as a clean bill of health.
    expect(summaryText()).toMatch(/not a clean bill of health/);
  });

  it('carries the laboratory-flagged tests it does not assess into the summary', async () => {
    // These sit outside every condition count, so omitting them would let the
    // reader think the flagged topics were the whole story.
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
    expect(summaryText()).toMatch(/marked 1 further result outside its own range/);
    expect(summaryText()).toMatch(/Potassium/);
    // And the unflagged one is reported as unchecked, not as normal.
    expect(summaryText()).toMatch(/Not checked is not the same as normal/);
  });

  // Both cases below were reported by a reader looking at a real screen, and
  // both are the same underlying mistake: two things that come from different
  // places, presented as though they came from one.

  it('never says a report is out of range when the finding came from the form', async () => {
    // THE REPORTED BUG. Every laboratory value in range, and the only flagged
    // topic is Obesity -- which is decided from BMI, which is computed from
    // the height and weight the patient typed in. The old wording said
    // "Something in this report is outside its usual range", which was simply
    // false and contradicted the in-range table directly above it.
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
    // The same mistake one clause further down. On a MIXED report -- Obesity
    // from the form AND Diabetes from a raised HbA1c -- "while every
    // laboratory result on the page is in range" is false. The provenance
    // sentence stays; only the clause that depends on nothing else being
    // flagged is dropped.
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
    // The mirror of the above, and the more dangerous direction: telling a
    // patient a raised blood value was something they typed in.
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
    // Unknown provenance must not become a statement in either direction.
    // `[].every(...)` is true, so an empty evidence list would otherwise be
    // reported as "entirely from the form".
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
    // A reader asked why something "Needs Monitoring" if the risk is "Low".
    // The two words come from different scales, and the first fix was a
    // paragraph reconciling them - which is a lecture about internal fields,
    // not something a patient can act on. The real fix is not to put the
    // reader in front of the pair. The severity is in the English sentence.
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
    // And no lecture on the card either.
    expect(overallCardText()).not.toMatch(/These measure different things/);
    expect(overallCardText()).not.toMatch(/answer different questions/);
  });

  it('does not let a comma inside a test name split it into two tests', async () => {
    // A laboratory prints "Potassium, Serum". Joined with commas, a list of
    // two tests reads as four, and the count in the same sentence then
    // contradicts the list beside it.
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

  it('says when part of the document could not be read', async () => {
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
    expect(summaryText()).toMatch(/Part of this document could not be read/);
    expect(summaryText()).toMatch(/missing from the reading rather than absent/);
  });

  it('states what this is even when everything came back clear', async () => {
    // The reader whose report is clean is the one most likely to treat this
    // page as a medical opinion, so the closing line is not conditional.
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
    // And no risk word anywhere, in either the card or the summary.
    expect(riskWordShown('Low')).toBe(false);
  });
});

describe('descriptions of tests this platform does not assess', () => {
  // The backend hands each item one of three states, and the screen has to
  // keep them apart. The dangerous collapse is not the obvious one: rendering
  // nothing for a test that WAS asked about and refused looks identical to a
  // test nobody enquired about, which turns a suppression into an absence.
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
    // And the laboratory's own facts are still on the page, unchanged - both
    // flagged results keep their marking, description or not. The marking now
    // lives in the results table's own column and names the range it is
    // outside; what is pinned is that it is still THE LABORATORY'S verdict
    // and still attributed, not the wording of the cell.
    // BOTH FLAGGED RESULTS KEEP THEIR MARKING -- that is the invariant, and
    // it does NOT depend on a printed range. Asserting "high — outside ..."
    // on both was the test being over-specific: one fixture row has no
    // printed interval, and demanding the range there would re-create the
    // bug this pair of assertions exists to prevent (a lab-marked abnormal
    // result going silent because its range was missing).
    const markings = [...document.querySelectorAll('.lab-flag--out')];
    expect(markings).toHaveLength(2);
    for (const mark of markings) expect(mark.textContent).toMatch(/high/);
    // ...and whose judgement it is stays attached to every one of them.
    expect(
      document.querySelectorAll('.lab-table--unassessed .lab__note').length
    ).toBeGreaterThanOrEqual(2);
  });

  it('says a description was WITHHELD rather than showing an empty space', async () => {
    withDashboard({ unanalysed });
    renderDashboard();

    // The producer's own notice, verbatim. It is already a whole sentence
    // written for a patient, so nothing of ours is prefixed to it -- saying
    // the same thing twice is what this replaced.
    expect(
      await screen.findByText(/The description did not pass safety review./)
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/No description of this test was produced/)
    ).not.toBeInTheDocument();
  });

  it('still says something when a withheld entry carries no notice', async () => {
    // A blank line here would read as an absence of content rather than a
    // suppression of it, which is the whole distinction this component draws.
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

  it('states that a description is about the TEST, not about the reader', async () => {
    // This sentence is the entire safety argument for the feature: the
    // prompt held a test name and nothing else, so the text below it cannot
    // be a reading of anyone's result. Without it the paragraph sits under a
    // number flagged abnormal and invites exactly that reading.
    withDashboard({ unanalysed });
    renderDashboard();

    expect(
      await screen.findByText(/your result was not used and is not interpreted here/)
    ).toBeInTheDocument();
  });

  it('says nothing at all about a test nobody asked about', async () => {
    withDashboard({ unanalysed });
    renderDashboard();

    await screen.findByText(/Urine Colour/);
    // Exactly one withheld line on the page - LDL's. Urine Colour was never
    // sent to the model, and any line at all under it would assert an attempt
    // that never happened.
    expect(
      screen.getAllByText(/did not pass safety review|No description of this test/)
    ).toHaveLength(1);
  });

  it('offers no explanatory sentence when there are no descriptions', async () => {
    // A report analysed before this stage existed. The section still renders
    // every skipped test; it just makes no claim about descriptions.
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

    expect(
      await screen.findByText(/Also on your report — not assessed by this tool/)
    ).toBeInTheDocument();
    expect(screen.queryByText(/your result was not used/)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/No description of this test was produced/)
    ).not.toBeInTheDocument();
  });
});

describe('an unanalysed report', () => {
  it('states that it has not been analysed rather than showing an empty all-clear', async () => {
    // An empty dashboard would read as "nothing wrong". The backend 404s
    // deliberately; the screen must carry that through.
    const error = new Error('This report has not been analysed yet.');
    error.status = 404;
    error.name = 'ApiError';
    Object.setPrototypeOf(error, (await import('../src/lib/api')).ApiError.prototype);
    vi.spyOn(api, 'getDashboard').mockRejectedValue(error);

    renderDashboard();

    expect(
      await screen.findByText('This report has not been analysed yet.')
    ).toBeInTheDocument();
  });
});

/**
 * THE ROUND-UP, AND THE ONE DISTINCTION IT CARRIES.
 *
 * "Everything else that was checked" holds two groups that must never be
 * mistaken for each other: topics that were CHECKED AND CAME BACK CLEAR, and
 * topics NOBODY COULD CHECK. Before this suite existed the two were separated
 * by `color: var(--muted)` -- one step of grey on the distinction the whole
 * screen exists to preserve, and exactly the failure `styles.css`'s own
 * header forbids ("a grey number still reads as a number; a dashed empty
 * outline cannot").
 *
 * So these tests assert the SEPARATION, in the markup, not the wording: a
 * cleared topic is filled and ticked, an unchecked one has no fill and says
 * NOT CHECKED. A test that only read the text would pass with both groups
 * rendered identically, which is the bug.
 */
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

  it('gives a cleared topic and an unchecked topic DIFFERENT chips', async () => {
    // The core guarantee. Both topics are named; what separates them is the
    // class the reader can actually see, not a five-percent tint.
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true, risk: 'High' },
      conditions: [clear('Anemia'), unassessed('Kidney Disease')],
    });
    renderDashboard();

    await screen.findByText(/Everything else that was checked/);
    expect(chipText('.chip--clear').join()).toMatch(/Anemia/);
    expect(chipText('.chip--unassessed').join()).toMatch(/Kidney Disease/);
    // ...and neither has leaked into the other group.
    expect(chipText('.chip--clear').join()).not.toMatch(/Kidney Disease/);
    expect(chipText('.chip--unassessed').join()).not.toMatch(/Anemia/);
  });

  it('says NOT CHECKED on an unchecked topic, and never on a cleared one', async () => {
    // design.md section 6 requires the literal words. A dashed border is
    // invisible to a screen reader; the tag is the half of the signal that is
    // not visual.
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true, risk: 'High' },
      conditions: [clear('Anemia'), unassessed('Kidney Disease')],
    });
    renderDashboard();

    await screen.findByText(/Everything else that was checked/);
    const tags = [...document.querySelectorAll('.chip--unassessed .chip__tag')];
    expect(tags).toHaveLength(1);
    expect(tags[0].textContent).toBe('NOT CHECKED');
    expect(document.querySelectorAll('.chip--clear .chip__tag')).toHaveLength(0);
  });

  it('keeps the sentence saying what "could not check" MEANS', async () => {
    // The chips say WHICH topics. This says an absence is not a negative
    // result -- without it, "could not check" reads as reassurance. It has
    // been removed from this page by a redesign once already.
    withDashboard({
      overall: { statusLabel: 'Not Assessed', anyAssessed: false },
      conditions: [unassessed('Kidney Disease')],
    });
    renderDashboard();

    expect(
      await screen.findByText(/open question, not a negative result/)
    ).toBeInTheDocument();
  });

  it('counts the cleared topics, and agrees with the chips it drew', async () => {
    // A printed count that disagrees with the list beside it is worse than no
    // count: it is a second, contradicting answer to "how many".
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true, risk: 'High' },
      conditions: [clear('Anemia'), clear('Underweight'), clear('Hypoglycemia')],
    });
    renderDashboard();

    await screen.findByText(/Everything else that was checked/);
    expect(document.querySelectorAll('.chip--clear')).toHaveLength(3);
    expect(document.querySelector('.roundup__lead').textContent).toMatch(/these 3 topics/);
  });

  it('says "topic", singular, when there is one of them', async () => {
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true, risk: 'High' },
      conditions: [clear('Anemia')],
    });
    renderDashboard();

    await screen.findByText(/Everything else that was checked/);
    expect(document.querySelector('.roundup__lead').textContent).toMatch(/these 1 topic\./);
  });

  it('draws no unchecked group when nothing was unchecked', async () => {
    // Section 6ac: a caption for a mark that is not on the chart. An empty
    // dashed group under a report where everything was assessed invents a
    // doubt the data does not support.
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

/**
 * THE GUIDANCE LIST, AND THE ATTRIBUTION HOISTED OUT OF IT.
 *
 * Three bullets each ending "Related to: Obesity." is the same sentence three
 * times (section 6ag's repetition fault). It is hoisted to one line ONLY when
 * every item's set is identical -- a hoisted line that is true of most
 * bullets is FALSE of the rest, and false in the direction that announces a
 * condition to a reader whose bullet had nothing to do with it.
 */
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
    // The guard that matters. One line saying "Obesity" above a bullet that
    // is there because of Diabetes states a condition the bullet never
    // claimed.
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
    // The catalog's order is incidental. Two rows citing the same two topics
    // in opposite orders share a reason, and printing it twice would be the
    // repetition this change exists to remove.
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
    // `matchedConditions` filters to conditions ACTUALLY flagged, so a row
    // citing an unflagged topic leaves the list entirely rather than arriving
    // with an empty reason. The hoisted line must describe the rows that
    // remain, and must not mention the topic that went.
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

/**
 * COLLAPSING, AND THE ONE THING THAT MAY NEVER BE COLLAPSED.
 *
 * The explanation paragraphs are now closed by default. That is a display
 * choice and it is fine for prose. It is NOT fine for a sentence reporting
 * that something is missing: a reader who never opens a disclosure never
 * learns the absence exists, which turns "we did not explain this" into
 * silence -- the exact failure this page was built to prevent, arriving
 * through a layout change.
 *
 * WHY THESE TESTS HAD TO BE WRITTEN AS DOM-SHAPE ASSERTIONS: jsdom renders
 * the children of a closed `<details>` like any others, so every existing
 * `getByText` in this file still passes with the whole section collapsed.
 * The suite went 242 green on the commit that introduced the collapse and
 * could not have told anyone. Asking "is this text present" cannot answer
 * "can the reader see it"; asking "what is it nested inside" can.
 */
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
      // Closed on arrival: the reader opts in.
      expect(panel.hasAttribute('open')).toBe(false);
      // ...and the summary still names what is inside, so a closed list is
      // a table of contents rather than a row of blank toggles.
      expect(panel.querySelector('summary .explanation__subject').textContent.trim())
        .not.toBe('');
    }
  });

  it('never puts a NEVER-ATTEMPTED explanation notice inside a disclosure', async () => {
    // Section 6ad's sentence. Four layers carried this fact and the fifth
    // threw it away; putting it behind a toggle would throw it away again in
    // a new and harder-to-notice manner.
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
    // Not an absence, but a statement about WHERE the words came from. It
    // qualifies every paragraph in the section, including the closed ones,
    // so it cannot live inside any one of them.
    withDashboard(withExplanations());
    renderDashboard();

    await screen.findByText(/What these results mean/);
    const said = screen.getByText(/Written by a language model/);
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
    // The size of what is behind the toggle is stated on it.
    expect(panel.querySelector('.disclosure__count').textContent.trim()).toBe('2');
    // The "not personalised advice" qualifier travels WITH the items it
    // qualifies -- it has nothing to qualify while the group is shut.
    expect(screen.getByText(/are not instructions/).closest('details')).toBe(panel);
  });
});

/**
 * THE GUIDANCE PANEL, AND THE AFFORDANCE IT MUST NOT FAKE.
 *
 * The section was asked for as "hyperlinks". The summary became a real
 * control; the rows deliberately did not, because there is nowhere for them
 * to go. A row styled as a link that does nothing when clicked is a worse
 * answer than a plain row, and on a medical page it invites a reader to think
 * there is more to read about their result than there is.
 */
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
    // No anchors, no buttons, nothing focusable inside the rows.
    expect(list.querySelectorAll('a, button, [role="button"], [role="link"], [tabindex]'))
      .toHaveLength(0);
    // The disclosure's own summary IS the control, and it is a real one.
    expect(document.querySelector('.disclosure--section > summary')).not.toBeNull();
  });

  it('puts the count next to the heading it counts', async () => {
    // It was reading as a stray number beside the chevron: the heading was
    // `flex: 1`, which stretched it across the row and parked the badge ~680px
    // from the words it belongs to. Adjacency is the fix and the guarantee.
    withDashboard(open());
    renderDashboard();

    const heading = await screen.findByText(/Topics you could read about/);
    const count = heading.nextElementSibling;
    expect(count).not.toBeNull();
    expect(count.className).toContain('disclosure__count');
    expect(count.textContent.trim()).toBe('3');
  });

  it('holds the attribution, the topics and the qualifier in ONE panel', async () => {
    // Revealed onto the bare page the three read as loose paragraphs and the
    // closing qualifier looked like page text that merely followed the list.
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

/**
 * THE PARAMETERS THIS TOOL DOES NOT ASSESS, IN "YOUR RESULTS".
 *
 * Asked for directly: show them with the laboratory's own limits, describe
 * them in "What these results mean", and diagnose nothing new from them.
 *
 * The safety of the whole feature rests on three separations, and each has a
 * test here because each is one careless edit from collapsing:
 *
 *   1. the LIMIT is the laboratory's, never invented (a model-supplied
 *      reference range is a defect this platform already shipped once);
 *   2. the MARKING is the laboratory's and says so, and never borrows the
 *      verdict palette that means "this tool crossed a threshold";
 *   3. the DESCRIPTION is about the test, not the reader's value, and is
 *      labelled as such where it sits.
 */
describe('parameters this tool does not assess', () => {
  const withUnassessed = (items) => ({
    overall: { statusLabel: 'Healthy', anyAssessed: true, risk: 'Low' },
    laboratory: [
      { feature: 'hba1c', displayName: 'HbA1c', value: 5.2, unit: '%', state: 'measured', usable: true },
    ],
    unanalysed: { count: items.length, items },
  });

  const cellFor = (testName) => {
    const row = [...document.querySelectorAll('.lab-row--unassessed')].find((tr) =>
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

    await screen.findByText(/Also on your report — not assessed by this tool/);
    const cell = cellFor('Ferritin');
    expect(cell).toMatch(/low/);
    expect(cell).toMatch(/15–150/);
    // Whose judgement it is, in the cell, not only in a heading far above.
    expect(cell).toMatch(/your laboratory/i);
  });

  it('says NO RANGE rather than implying the result is fine', async () => {
    // A blank cell in a column headed "Compared with usual limits" reads as
    // "in range". Most real reports print no interval for most tests.
    withDashboard(
      withUnassessed([{ testName: 'Urine Colour', value: 'Yellow', unit: null }])
    );
    renderDashboard();

    await screen.findByText(/Also on your report — not assessed by this tool/);
    expect(cellFor('Urine Colour')).toMatch(/no range printed/i);
  });

  it('KEEPS a laboratory marking that arrives with no printed range', async () => {
    // THE BUG THIS FEATURE SHIPPED WITH FOR ONE COMMIT. The first version
    // printed the comparison only when a range existed, so a result the
    // laboratory had marked abnormal with no printed interval fell through
    // to "no range printed" and lost the marking entirely -- an absence
    // swallowing a real finding, in the cell added to surface real findings.
    // Labs routinely flag against sex-specific ranges they do not print.
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

    await screen.findByText(/Also on your report — not assessed by this tool/);
    const cell = cellFor('Blood Urea');
    expect(cell).toMatch(/high/);
    expect(cell).not.toMatch(/no range printed/i);
  });

  it('never dresses a laboratory marking as this tool’s own verdict', async () => {
    // `.verdict--high` on this page means THIS TOOL crossed a threshold it
    // holds. Nothing in this group was assessed by this tool.
    withDashboard(
      withUnassessed([
        {
          testName: 'Potassium, Serum',
          value: 5.9,
          unit: 'mmol/l',
          labFlag: 'high',
          labFlaggedAbnormal: true,
          labReferenceLow: 3.5,
          labReferenceHigh: 5.1,
        },
      ])
    );
    renderDashboard();

    await screen.findByText(/Also on your report — not assessed by this tool/);
    const table = document.querySelector('.lab-table--unassessed');
    expect(table.querySelectorAll('.verdict')).toHaveLength(0);
    expect(table.querySelector('.lab-flag--out')).not.toBeNull();
  });

  it('says "not checked is not the same as normal" where the rows are', async () => {
    withDashboard(
      withUnassessed([{ testName: 'Urine Colour', value: 'Yellow' }])
    );
    renderDashboard();

    const heading = await screen.findByText(
      /Also on your report — not assessed by this tool/
    );
    // SCOPED TO THIS GROUP. The closing "In short" summary legitimately says
    // the same thing again -- restating an absence at the foot of the page is
    // that section's job -- so a page-wide query finds two and proves
    // nothing about whether the sentence is WHERE THE ROWS ARE.
    const groupIntro = heading.nextElementSibling;
    expect(groupIntro.textContent).toMatch(/Not checked is not the same as normal/);
  });

  it('marks every row as not assessed, on the row itself', async () => {
    withDashboard(
      withUnassessed([
        { testName: 'Ferritin', value: 12, unit: 'ng/ml' },
        { testName: 'Blood Urea', value: 58, unit: 'mg/dl' },
      ])
    );
    renderDashboard();

    await screen.findByText(/Also on your report — not assessed by this tool/);
    const rows = [...document.querySelectorAll('.lab-row--unassessed')];
    expect(rows).toHaveLength(2);
    for (const row of rows) {
      expect(row.querySelector('th').textContent).toMatch(/not assessed by this tool/);
    }
  });

  it('labels the descriptions as being about the TEST, not the reader', async () => {
    // The reason a previous session kept these out of this section entirely:
    // every other card here interprets the reader's own value. The label is
    // what makes including them safe, so it is not decoration.
    withDashboard(
      withUnassessed([
        {
          testName: 'Potassium, Serum',
          value: 5.9,
          unit: 'mmol/l',
          descriptionAvailable: true,
          description: 'A mineral your body uses for nerve and muscle function.',
        },
      ])
    );
    renderDashboard();

    await screen.findByText(/About the tests this tool did not assess/);
    expect(
      screen.getByText(/your result was not used and is not interpreted here/)
    ).toBeInTheDocument();
  });

  it('offers no description group when nothing was described', async () => {
    // The glossary is only asked about tests the lab flagged, so most reports
    // have no entries at all. A heading over nothing is a section that says
    // there is something to read when there is not.
    //
    // THE FIXTURE MUST MAKE THE SURROUNDING SECTION RENDER. A first version
    // of this test supplied no explanations at all, so "What these results
    // mean" returned null and the heading was absent for a reason that had
    // nothing to do with the guard -- the mutation removing the guard
    // SURVIVED it. A vacuous green. One written explanation is what makes
    // the guard the only thing standing between the reader and an empty
    // heading.
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

    // The section itself IS on screen...
    await screen.findByText(/What these results mean/);
    // ...and the group for undescribed extras is not.
    expect(
      screen.queryByText(/About the tests this tool did not assess/)
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/your result was not used and is not interpreted here/)
    ).not.toBeInTheDocument();
  });

  it('shows each parameter exactly ONCE on the page', async () => {
    // The old bottom-of-page section was removed rather than kept alongside
    // these groups. Keeping both printed every one of these twice.
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

    await screen.findByText(/Also on your report — not assessed by this tool/);
    // Once in the results group, once as a description heading -- and those
    // are different things. What must not happen is the whole old section
    // reappearing with its own copy of both.
    expect(screen.queryByText(/Also on your report, but not assessed here/)).not.toBeInTheDocument();
    expect(document.querySelectorAll('.lab-row--unassessed')).toHaveLength(1);
    expect(
      screen.getAllByText(/A mineral your body uses for nerve and muscle function./)
    ).toHaveLength(1);
  });
});

describe('the laboratory range, in readable English', () => {
  const one = (item) => ({
    overall: { statusLabel: 'Healthy', anyAssessed: true, risk: 'Low' },
    laboratory: [
      { feature: 'hba1c', displayName: 'HbA1c', value: 5.2, unit: '%', state: 'measured', usable: true },
    ],
    unanalysed: { count: 1, items: [item] },
  });
  const limits = async () => {
    await screen.findByText(/Also on your report — not assessed by this tool/);
    return document
      .querySelector('.lab-row--unassessed')
      .children[2].textContent.replace(/\s+/g, ' ')
      .trim();
  };

  it('says "within" only for a two-sided interval', async () => {
    withDashboard(
      one({ testName: 'Albumin', value: 4.2, unit: 'g/dl', labReferenceLow: 3.5, labReferenceHigh: 5 })
    );
    renderDashboard();
    expect(await limits()).toMatch(/within 3.5–5/);
  });

  it('reads correctly when the laboratory printed only a ceiling', async () => {
    // "within up to 100" was the first version, and it is not English.
    withDashboard(
      one({ testName: 'LDL Cholesterol, Direct', value: 96, unit: 'mg/dl', labReferenceHigh: 100 })
    );
    renderDashboard();
    const text = await limits();
    expect(text).toMatch(/at or below 100/);
    expect(text).not.toMatch(/within up to/);
  });

  it('reads correctly when the laboratory printed only a floor', async () => {
    withDashboard(
      one({ testName: 'Vitamin B6', value: 22, unit: 'nmol/l', labReferenceLow: 15 })
    );
    renderDashboard();
    const text = await limits();
    expect(text).toMatch(/at or above 15/);
    expect(text).not.toMatch(/within 15 and above/);
  });
});

