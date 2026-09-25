import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PairIdentityNotice, ProfileIdentityNotice } from '../src/components/IdentityNotice';
import Dashboard from '../src/pages/Dashboard';
import Timeline from '../src/pages/Timeline';
import { api } from '../src/lib/api';

/**
 * WHOSE REPORT IS THIS? -- 2026-09-24.
 *
 * `01-all-normal.pdf` prints "34 Years / Female" and was analysed as the
 * profile's "20, male"; it was compared with `03-renal...pdf` ("63 Years /
 * Male") as haemoglobin 9.2 -> 13.6 "in 2 days". Nothing on screen said
 * either. The four states, and above all: "not checked" is never silence.
 */

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('ProfileIdentityNotice', () => {
  it('names both sides of a disagreement, as a warning', () => {
    render(
      <ProfileIdentityNotice
        identity={{
          status: 'conflict',
          conflicts: [{ field: 'sex' }, { field: 'age' }],
          printed: { sex: 'female', ageYears: 34 },
          used: { sex: 'male', ageYears: 20 },
        }}
      />
    );
    const note = screen.getByRole('note', { name: /may not match your profile/i });
    expect(note.textContent).toMatch(/prints: female, 34 years old/);
    expect(note.textContent).toMatch(/used your profile: male, 20 years old/);
    expect(note.textContent).toMatch(/judged with your profile.s values/);
  });

  it('says "not checked" -- never nothing -- for a report that predates the check', () => {
    render(<ProfileIdentityNotice identity={{ status: 'not_checked', conflicts: [] }} />);
    expect(screen.getByText(/have not been read, so they have not been checked/i)).toBeInTheDocument();
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
  });

  it('says a partial check is partial', () => {
    render(<ProfileIdentityNotice identity={{ status: 'incomplete', conflicts: [] }} />);
    expect(screen.getByText(/could only partly be checked/i)).toBeInTheDocument();
  });

  it('says nothing when both were read and agree', () => {
    const { container } = render(<ProfileIdentityNotice identity={{ status: 'consistent', conflicts: [] }} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('PairIdentityNotice', () => {
  it('THE CASE ON SCREEN: a different sex and an impossible age', () => {
    render(
      <PairIdentityNotice
        identity={{
          status: 'conflict',
          conflicts: [
            { field: 'sex', baseline: 'male', comparison: 'female' },
            { field: 'age', baseline: 63, comparison: 34, expected: 63 },
          ],
          notChecked: [],
        }}
      />
    );
    const note = screen.getByRole('note', { name: /different people/i });
    expect(note.textContent).toMatch(/one prints male, the other female/);
    expect(note.textContent).toMatch(/63 years old, then 34 years old/);
    expect(note.textContent).toMatch(/differences between two people, not changes/);
  });

  it.each([
    [['baseline'], /the earlier report has not had/],
    [['comparison'], /the later report has not had/],
    [['baseline', 'comparison'], /neither has had/],
  ])('names which report was not checked: %p', (notChecked, pattern) => {
    render(<PairIdentityNotice identity={{ status: 'not_checked', conflicts: [], notChecked }} />);
    expect(screen.getByText(/has not been checked/i).textContent).toMatch(pattern);
  });
});

describe('on the pages', () => {
  it('the dashboard puts the profile warning above the verdict', async () => {
    vi.spyOn(api, 'getDashboard').mockResolvedValue({
      report: { originalName: '01-all-normal.pdf' },
      dashboard: { overall: { status: 'Healthy', statusLabel: 'Healthy', risk: 'Low', anyAssessed: true, complete: true } },
      identity: {
        status: 'conflict',
        conflicts: [{ field: 'sex' }],
        printed: { sex: 'female', ageYears: 34 },
        used: { sex: 'male', ageYears: 20 },
      },
    });
    render(
      <MemoryRouter initialEntries={['/reports/abc']}>
        <Routes>
          <Route path="/reports/:id" element={<Dashboard />} />
        </Routes>
      </MemoryRouter>
    );
    const note = await screen.findByRole('note', { name: /may not match your profile/i });
    const verdict = document.querySelector('.overall');
    // eslint-disable-next-line no-bitwise
    expect(note.compareDocumentPosition(verdict) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('the comparison card puts the pair warning before the table', async () => {
    vi.spyOn(api, 'getTrends').mockResolvedValue({ trends: {}, history: {} });
    vi.spyOn(api, 'getProgress').mockResolvedValue({ progress: {} });
    vi.spyOn(api, 'listReports').mockResolvedValue({ reports: [] });
    vi.spyOn(api, 'getComparison').mockResolvedValue({
      history: { reports: [] },
      comparison: {
        pair: {
          baseline_report_id: 'a',
          comparison_report_id: 'b',
          baseline_date: '2026-09-09T00:00:00Z',
          comparison_date: '2026-09-11T00:00:00Z',
          chronological: true,
        },
        table: [{ feature: 'hemoglobin', description: 'Haemoglobin', previous: 9.2, current: 13.6, unit: 'g/dl', category: 'changed_direction_only' }],
      },
      identity: {
        status: 'conflict',
        conflicts: [{ field: 'sex', baseline: 'male', comparison: 'female' }],
        notChecked: [],
      },
    });
    render(
      <MemoryRouter>
        <Timeline />
      </MemoryRouter>
    );
    const note = await screen.findByRole('note', { name: /different people/i });
    const table = document.querySelector('table');
    // eslint-disable-next-line no-bitwise
    expect(note.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
