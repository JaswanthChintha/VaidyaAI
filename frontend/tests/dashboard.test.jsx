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

    expect(
      await screen.findByText('Healthy (partial assessment)')
    ).toBeInTheDocument();
    // The bare word must not appear as the headline on its own.
    expect(screen.queryByText('Healthy')).not.toBeInTheDocument();
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

    expect(await screen.findByText('Not Assessed')).toBeInTheDocument();
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

    expect(await screen.findByText('Not Assessed')).toBeInTheDocument();
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

    expect(await screen.findByText('Kidney Disease')).toBeInTheDocument();
    expect(screen.getByText('Insufficient Data')).toBeInTheDocument();
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

    expect(await screen.findByText('Creatinine')).toBeInTheDocument();
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

    expect(await screen.findByText('No range printed')).toBeInTheDocument();
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
