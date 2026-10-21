import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Dashboard from '../src/pages/Dashboard';
import { api } from '../src/lib/api';


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

function withProse(text) {
  return vi.spyOn(api, 'rewriteSummary').mockResolvedValue({
    prose: { outcome: 'generated', text },
  });
}

function withRefusal(outcome) {
  return vi.spyOn(api, 'rewriteSummary').mockResolvedValue({
    prose: { outcome, text: null },
  });
}


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
    expect(prose()).toBeVisible();
    expect(body()).not.toBeVisible();
    expect(body().hasAttribute('hidden')).toBe(true);
  });

  it('NEVER replaces or hides the closing line', async () => {
    withDashboard();
    withProse('A rewritten summary.');
    renderDashboard();

    await waitFor(() => expect(prose()).not.toBeNull());
    expect(closing()).toBeVisible();
    expect(closing().textContent).toMatch(/not a diagnosis/i);
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
    expect(visible).toHaveLength(3);
    expect(visible.map((n) => n.className)).toEqual(
      expect.arrayContaining(['in-short__prose', 'in-short__closing'])
    );
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
    withDashboard();
    vi.spyOn(api, 'rewriteSummary').mockResolvedValue({ prose: { text: 42 } });
    renderDashboard();

    await screen.findByText(/In short/);
    await waitFor(() => expect(api.rewriteSummary).toHaveBeenCalled());
    expect(prose()).toBeNull();
    expect(body()).toBeVisible();
  });

  it('treats an all-whitespace rewrite as no rewrite', async () => {
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
    expect(names).toEqual(expect.arrayContaining(['Anemia', 'Diabetes', 'Potassium']));
  });

  const WITH_UNASSESSED = {
    ...DASHBOARD,
    conditions: [
      ...DASHBOARD.conditions,
      {
        condition: 'Vitamin D Deficiency',
        status: 'Insufficient Data',
        risk: null,
        flagged: false,
        assessed: false,
      },
    ],
  };

  it('never requires a name the sentences do not contain', async () => {
    withDashboard(WITH_UNASSESSED);
    const spy = withProse('rewritten');
    renderDashboard();

    await waitFor(() => expect(spy).toHaveBeenCalled());
    const [, sentences, names] = spy.mock.calls[0];

    expect(names.length).toBeGreaterThan(0);

    const sent = sentences.join(' ').toLowerCase();
    const impossible = names.filter((n) => !sent.includes(String(n).toLowerCase()));
    expect(impossible).toEqual([]);
  });

  it('does not send a condition it could not check as a must-survive name', async () => {
    withDashboard(WITH_UNASSESSED);
    const spy = withProse('rewritten');
    renderDashboard();

    await waitFor(() => expect(spy).toHaveBeenCalled());
    const names = spy.mock.calls[0][2];
    expect(names).not.toContain('Vitamin D Deficiency');
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

describe('Module 34 -- general context in the summary', () => {
  const ctx = () => document.querySelector('.in-short__context');

  function withContext(entries) {
    return vi.spyOn(api, 'describeFindings').mockResolvedValue({
      context: { entries },
    });
  }

  const GOOD = {
    test_name: 'C-REACTIVE PROTEIN',
    direction: 'raised',
    text: 'A raised result of this kind is commonly associated with inflammation.',
    available: true,
  };

  it('shows an approved entry, outside the rewritable body', async () => {
    withDashboard();
    vi.spyOn(api, 'rewriteSummary').mockResolvedValue({ prose: null });
    withContext([GOOD]);
    renderDashboard();

    await waitFor(() => expect(ctx()).not.toBeNull());
    expect(ctx()).toBeVisible();
    expect(ctx().textContent).toMatch(/commonly associated with inflammation/);
    expect(ctx().closest('.in-short__body')).toBeNull();
  });

  it('stays visible when the summary rewrite replaces the composed body', async () => {
    withDashboard();
    vi.spyOn(api, 'rewriteSummary').mockResolvedValue({
      prose: { outcome: 'generated', text: 'A rewritten summary.' },
    });
    withContext([GOOD]);
    renderDashboard();

    await waitFor(() => expect(document.querySelector('.in-short__prose')).not.toBeNull());
    expect(ctx()).toBeVisible();
    expect(closing()).toBeVisible();
  });

  it('names a finding whose description was refused, instead of dropping it', async () => {
    withDashboard();
    vi.spyOn(api, 'rewriteSummary').mockResolvedValue({ prose: null });
    withContext([
      GOOD,
      {
        test_name: 'Vitamin D, 25-Hydroxy',
        direction: 'lowered',
        text: null,
        available: false,
        refused_by: 'number',
      },
    ]);
    renderDashboard();

    await screen.findByText(/In short/);
    await waitFor(() => expect(api.describeFindings).toHaveBeenCalled());

    const box = ctx();
    expect(box).not.toBeNull();
    expect(box.textContent).toMatch(/Vitamin D, 25-Hydroxy/);
    expect(box.textContent).toMatch(/\(lowered\)/);
    expect(box.textContent).toMatch(/No general description could be prepared/i);
    expect(box.textContent).toMatch(/commonly associated with inflammation/);
  });

  it('renders NOTHING when every entry was refused', async () => {
    withDashboard();
    vi.spyOn(api, 'rewriteSummary').mockResolvedValue({ prose: null });
    withContext([
      { test_name: 'CRP', direction: 'raised', text: null, available: false },
    ]);
    renderDashboard();

    await screen.findByText(/In short/);
    await waitFor(() => expect(api.describeFindings).toHaveBeenCalled());
    expect(ctx()).toBeNull();
    expect(document.body.textContent).not.toMatch(/could not be prepared/i);
  });


  it('says a description is still being prepared, not that it could not be', async () => {
    withDashboard();
    vi.spyOn(api, 'rewriteSummary').mockResolvedValue({ prose: null });
    withContext([
      GOOD,
      { test_name: 'ESR', direction: 'raised', text: null, available: false, refused_by: 'in_progress' },
    ]);
    renderDashboard();

    await screen.findByText(/In short/);
    await waitFor(() => expect(api.describeFindings).toHaveBeenCalled());
    const box = ctx();
    expect(box.textContent).toMatch(/ESR/);
    expect(box.textContent).toMatch(/still being prepared/i);
    expect(box.textContent).toMatch(/open this page again/i);
    expect(box.textContent).not.toMatch(/could not be prepared/i);
  });

  it('shows the box when NOTHING is finished yet but something is coming', async () => {
    withDashboard();
    vi.spyOn(api, 'rewriteSummary').mockResolvedValue({ prose: null });
    withContext([
      { test_name: 'CRP', direction: 'raised', text: null, available: false, refused_by: 'in_progress' },
    ]);
    renderDashboard();

    await screen.findByText(/In short/);
    await waitFor(() => expect(ctx()).not.toBeNull());
    expect(ctx().textContent).toMatch(/still being prepared/i);
  });

  it('renders nothing when the request fails', async () => {
    withDashboard();
    vi.spyOn(api, 'rewriteSummary').mockResolvedValue({ prose: null });
    vi.spyOn(api, 'describeFindings').mockRejectedValue(new Error('network'));
    renderDashboard();

    await screen.findByText(/In short/);
    await waitFor(() => expect(api.describeFindings).toHaveBeenCalled());
    expect(ctx()).toBeNull();
    expect(closing()).toBeVisible();
  });

  it('SENDS A NAME AND A DIRECTION, AND NO VALUE', async () => {
    withDashboard();
    vi.spyOn(api, 'rewriteSummary').mockResolvedValue({ prose: null });
    const spy = withContext([GOOD]);
    renderDashboard();

    await waitFor(() => expect(spy).toHaveBeenCalled());
    const [, findings] = spy.mock.calls[0];
    expect(findings.length).toBeGreaterThan(0);
    for (const f of findings) {
      expect(Object.keys(f).sort()).toEqual(['direction', 'test_name']);
      expect(['raised', 'lowered']).toContain(f.direction);
    }
    expect(findings.some((f) => /Potassium/i.test(f.test_name))).toBe(true);
  });

  it('never asks about a PROFILE answer, and never sends a feature key', async () => {
    withDashboard({
      ...DASHBOARD,
      laboratory: [
        { feature: 'bmi', displayName: 'Body mass index', value: 31, unit: 'kg/m2', state: 'valid', usable: true, source: 'patient_profile' },
        { feature: 'hemoglobin', originalTestName: 'HEMOGLOBIN', displayName: 'Haemoglobin', value: 12.5, unit: 'g/dl', state: 'valid', usable: true, source: 'lab_report' },
      ],
      evidence: {
        conditions: [
          { condition: 'Obesity', lines: [{ feature: 'bmi', value: 31, threshold: 30, comparator: '>=', classification: 'high', availability: 'observed' }] },
          { condition: 'Anemia', lines: [{ feature: 'hemoglobin', value: 12.5, threshold: 13, comparator: '<', classification: 'low', availability: 'observed' }] },
        ],
      },
    });
    vi.spyOn(api, 'rewriteSummary').mockResolvedValue({ prose: null });
    const spy = withContext([GOOD]);
    renderDashboard();

    await waitFor(() => expect(spy).toHaveBeenCalled());
    const names = spy.mock.calls[0][1].map((f) => f.test_name);
    expect(names).not.toContain('bmi');
    expect(names.some((n) => /body mass index/i.test(n))).toBe(false);
    expect(names).toContain('HEMOGLOBIN');
  });

  it('asks for nothing when no result is out of range', async () => {
    withDashboard({
      overall: { statusLabel: 'Healthy', risk: 'Low', anyAssessed: true, complete: true },
      conditions: [
        { condition: 'Anemia', status: 'Not Indicated', risk: 'Low', flagged: false, assessed: true },
      ],
      unanalysed: { count: 0, items: [] },
    });
    vi.spyOn(api, 'rewriteSummary').mockResolvedValue({ prose: null });
    const spy = withContext([GOOD]);
    renderDashboard();

    await screen.findByText(/In short/);
    expect(spy).not.toHaveBeenCalled();
    expect(ctx()).toBeNull();
  });
});
