import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Dashboard from '../src/pages/Dashboard';
import { api } from '../src/lib/api';

/**
 * Module 33 at the rendering layer -- the closing summary, rewritten.
 *
 * ==========================================================================
 * WHY EVERY ASSERTION HERE IS ABOUT DOM SHAPE
 * ==========================================================================
 *
 * jsdom renders a `hidden` element's children exactly like any others, which
 * is the same trap §6an records for `<details>`: every `getByText` still finds
 * text no reader can see, so "is this sentence present" cannot answer "can the
 * reader see it". When the rewrite lands, the composed body is HIDDEN rather
 * than unmounted -- so a test written the obvious way would pass whether the
 * page showed the rewrite, the composed text, or both at once.
 *
 * `toBeVisible()` honours the `hidden` attribute. That is the matcher this
 * whole file turns on.
 *
 * ==========================================================================
 * WHAT MUST BE TRUE, WHATEVER THE MODEL DOES
 * ==========================================================================
 *
 *   1. The reader sees exactly ONE of the two -- never both, never neither.
 *   2. THE CLOSING LINE IS NEVER TOUCHED. It is the one sentence stating what
 *      this tool is, and it lives outside the rewritable body by construction.
 *   3. Every failure path lands on the composed text, which is what the page
 *      showed before Module 33 existed. There is no error state because there
 *      is nothing to report: the page is complete either way.
 *   4. What is SENT is what is RENDERED. The sentences are read out of the
 *      DOM, so the request cannot drift from the screen.
 */

const DASHBOARD = {
  overall: {
    statusLabel: 'Needs Medical Attention',
    risk: 'High',
    anyAssessed: true,
    complete: true,
  },
  conditions: [
    {
      condition: 'Anemia',
      status: 'Indicated',
      risk: 'Medium',
      flagged: true,
      assessed: true,
    },
    {
      condition: 'Diabetes',
      status: 'Not Indicated',
      risk: 'Low',
      flagged: false,
      assessed: true,
    },
  ],
  unanalysed: {
    count: 1,
    items: [
      { testName: 'Potassium', value: '5.2', labFlag: 'high', labFlaggedAbnormal: true },
    ],
  },
};

function renderDashboard() {
  return render(
    <MemoryRouter initialEntries={['/reports/abc']}>
      <Routes>
        <Route path="/reports/:id" element={<Dashboard />} />
      </Routes>
    </MemoryRouter>
  );
}

function withDashboard(dashboard = DASHBOARD) {
  vi.spyOn(api, 'getDashboard').mockResolvedValue({
    report: { originalName: 'report.pdf' },
    dashboard,
  });
}

/** The ai-service answered with an approved rewrite. */
function withProse(text) {
  return vi.spyOn(api, 'rewriteSummary').mockResolvedValue({
    prose: { outcome: 'generated', text },
  });
}

/** Every refusal shape: a 200 carrying an outcome and no text. */
function withRefusal(outcome) {
  return vi.spyOn(api, 'rewriteSummary').mockResolvedValue({
    prose: { outcome, text: null },
  });
}

/* MUTATION-TESTED, AND ONE SURVIVED HONESTLY.
 *
 *   KILLED  the composed body never hidden (2 tests)
 *   KILLED  the closing line moved inside the rewritable body (5)
 *   KILLED  the names no longer sent (1)
 *   SURVIVED `typeof text === 'string' && text.trim()` removed
 *
 * The survivor is recorded rather than papered over. Asking which INPUT
 * reaches it answers why: without the guard, whitespace calls `setProse('')`
 * which is falsy downstream, and a number, a null or a missing key make
 * `text.trim()` throw into the effect's own catch -- so EVERY input still
 * lands on the composed text and nothing observable changes. The check is
 * correct defensive code (control flow through an exception is worse than an
 * explicit test) but it is not independently observable, so this file does
 * not claim to test it.
 *
 * Worth recording how that was nearly got wrong: a scratch probe printed the
 * thrown string as though it were a value and concluded the mutant would show
 * prose. It would not -- the throw propagates to the catch. A probe's output
 * is a claim about the probe.
 */

const body = () => document.querySelector('.in-short__body');
const prose = () => document.querySelector('.in-short__prose');
const closing = () => document.querySelector('.in-short__closing');

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('when the rewrite is approved', () => {
  it('shows the rewrite and HIDES the composed body', async () => {
    withDashboard();
    withProse('A rewritten summary that reads better.');
    renderDashboard();

    await waitFor(() => expect(prose()).not.toBeNull());
    // ONE OF THE TWO, NEVER BOTH. `toBeInTheDocument` cannot tell these apart
    // -- the composed body is still in the DOM and jsdom will happily find
    // its text.
    expect(prose()).toBeVisible();
    expect(body()).not.toBeVisible();
    expect(body().hasAttribute('hidden')).toBe(true);
  });

  it('NEVER replaces or hides the closing line', async () => {
    // The one sentence on this panel that says what this tool is. A model may
    // not reword it and a rewrite may not swallow it, which is why it sits
    // outside the rewritable body by construction.
    withDashboard();
    withProse('A rewritten summary.');
    renderDashboard();

    await waitFor(() => expect(prose()).not.toBeNull());
    expect(closing()).toBeVisible();
    expect(closing().textContent).toMatch(/not a diagnosis/i);
    // And it is not INSIDE the part that gets hidden.
    expect(closing().closest('.in-short__body')).toBeNull();
  });

  it('does not leave the reader reading the same thing twice', async () => {
    withDashboard();
    withProse('A rewritten summary.');
    renderDashboard();

    await waitFor(() => expect(prose()).not.toBeNull());
    const visible = [...document.querySelectorAll('.in-short p')].filter(
      (node) => !node.closest('[hidden]')
    );
    // THREE, and each is there for a reason: the headline verdict, the
    // rewrite, and the closing line. The headline sits outside the rewritable
    // body deliberately -- it is the one sentence a reader takes away, and it
    // is composed straight from Module 18's label.
    expect(visible).toHaveLength(3);
    expect(visible.map((n) => n.className)).toEqual(
      expect.arrayContaining(['in-short__prose', 'in-short__closing'])
    );
    // And NOTHING composed inside the body is visible alongside the rewrite.
    const compositionStillShowing = [...body().querySelectorAll('p')].filter(
      (node) => !node.closest('[hidden]')
    );
    expect(compositionStillShowing).toHaveLength(0);
  });
});

describe('every refusal lands on the composed text', () => {
  it.each([
    ['model_unavailable'],
    ['withheld_by_safety'],
    ['facts_missing'],
    ['facts_invented'],
    ['nothing_to_write'],
  ])('renders the composed body on %s', async (outcome) => {
    withDashboard();
    withRefusal(outcome);
    renderDashboard();

    await screen.findByText(/In short/);
    await waitFor(() => expect(api.rewriteSummary).toHaveBeenCalled());
    expect(prose()).toBeNull();
    expect(body()).toBeVisible();
    expect(body().hasAttribute('hidden')).toBe(false);
  });

  it('renders the composed body when the request itself fails', async () => {
    // A rewrite that did not happen is not an error the reader has any use
    // for. There must be no error state and no empty panel.
    withDashboard();
    vi.spyOn(api, 'rewriteSummary').mockRejectedValue(new Error('network'));
    renderDashboard();

    await screen.findByText(/In short/);
    await waitFor(() => expect(api.rewriteSummary).toHaveBeenCalled());
    expect(prose()).toBeNull();
    expect(body()).toBeVisible();
    expect(closing()).toBeVisible();
  });

  it('renders the composed body when the reply has a shape nobody expected', async () => {
    // NOT A CRASH AND NOT A BLANK PANEL. `prose` stays null unless a real
    // string arrived, so a null, a number or a missing key all land here.
    withDashboard();
    vi.spyOn(api, 'rewriteSummary').mockResolvedValue({ prose: { text: 42 } });
    renderDashboard();

    await screen.findByText(/In short/);
    await waitFor(() => expect(api.rewriteSummary).toHaveBeenCalled());
    expect(prose()).toBeNull();
    expect(body()).toBeVisible();
  });

  it('treats an all-whitespace rewrite as no rewrite', async () => {
    // An empty rewrite that replaced the body would blank the summary -- the
    // worst of the three outcomes, and the one a truthy check would allow.
    withDashboard();
    withProse('   \n  ');
    renderDashboard();

    await screen.findByText(/In short/);
    await waitFor(() => expect(api.rewriteSummary).toHaveBeenCalled());
    expect(prose()).toBeNull();
    expect(body()).toBeVisible();
  });
});

describe('what is sent is what is rendered', () => {
  it('posts the composed sentences verbatim, read off the page', async () => {
    withDashboard();
    const spy = withProse('rewritten');
    renderDashboard();

    await waitFor(() => expect(spy).toHaveBeenCalled());
    const [id, sentences] = spy.mock.calls[0];
    expect(id).toBe('abc');
    // THE SENTENCES ARE THE PAGE'S OWN. Asserted against the rendered body
    // rather than against a fixture, because a fixture would be a second
    // composition and could drift from the screen without failing.
    const rendered = [...body().querySelectorAll('p')].map((node) =>
      node.textContent.replace(/\s+/g, ' ').trim()
    );
    expect(sentences).toEqual(rendered.filter(Boolean));
    expect(sentences.some((s) => /checked 2 conditions/.test(s))).toBe(true);
  });

  it('sends the names that must survive the rewrite', async () => {
    withDashboard();
    const spy = withProse('rewritten');
    renderDashboard();

    await waitFor(() => expect(spy).toHaveBeenCalled());
    const names = spy.mock.calls[0][2];
    // Every condition on the page, and the laboratory's own flagged test --
    // the service must not have to guess which tokens are names.
    expect(names).toEqual(expect.arrayContaining(['Anemia', 'Diabetes', 'Potassium']));
  });

  it('never sends the closing line to the model', async () => {
    withDashboard();
    const spy = withProse('rewritten');
    renderDashboard();

    await waitFor(() => expect(spy).toHaveBeenCalled());
    const sentences = spy.mock.calls[0][1];
    expect(sentences.join(' ')).not.toMatch(/not a substitute for advice/i);
  });

  it('asks once, not once per render', async () => {
    // One model call per report. The free tier is twenty a day.
    withDashboard();
    const spy = withProse('rewritten');
    const { rerender } = renderDashboard();

    await waitFor(() => expect(spy).toHaveBeenCalled());
    rerender(
      <MemoryRouter initialEntries={['/reports/abc']}>
        <Routes>
          <Route path="/reports/:id" element={<Dashboard />} />
        </Routes>
      </MemoryRouter>
    );
    await waitFor(() => expect(prose()).not.toBeNull());
    expect(spy).toHaveBeenCalledTimes(1);
  });
});
