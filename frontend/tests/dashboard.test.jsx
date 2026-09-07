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
    expect(screen.queryByText('Low')).not.toBeInTheDocument();
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
    expect(screen.queryByText('Low')).not.toBeInTheDocument();
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
    expect(screen.queryByText('Low')).not.toBeInTheDocument();
  });

  it('shows a basis conflict rather than merging two kinds of answer', async () => {
    // Module 16 stamps `basis_conflict` so a risk-factor tally and a model
    // probability are shown side by side rather than averaged into one
    // undifferentiated figure.
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true },
      conditions: [
        {
          condition: 'Heart Disease',
          status: 'Indicated',
          risk: 'Medium',
          assessed: true,
          basisConflict: true,
          basisNote: 'A risk-factor count and a model probability answer different questions.',
        },
      ],
    });
    renderDashboard();

    expect(
      await screen.findByText(/answer different questions/)
    ).toBeInTheDocument();
  });
});

describe('laboratory rows', () => {
  it('renders a rejected reading as unusable, never as 0', async () => {
    withDashboard({
      overall: { statusLabel: 'Attention Needed', anyAssessed: true },
      laboratory: [
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
    expect(await screen.findByText(/Creatinine/)).toBeInTheDocument();
    expect(screen.queryByText('999 mg/dl')).not.toBeInTheDocument();
    expect(screen.queryByText('0 mg/dl')).not.toBeInTheDocument();
    expect(
      screen.getByText(/outside the physiologically possible range/)
    ).toBeInTheDocument();
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

    expect(await screen.findByText('0 ng/ml')).toBeInTheDocument();
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
    expect(screen.queryByText('Low')).not.toBeInTheDocument();
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
    // And the laboratory's own facts are still beside it, unchanged - both
    // flagged results keep their marking, description or not.
    expect(screen.getAllByText(/lab: high/)).toHaveLength(2);
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

    expect(await screen.findByText(/Also on your report, but not assessed here/)).toBeInTheDocument();
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
