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
  // 2026-09-25: the report's own sex and age are USED. The notice names both
  // sides and says truthfully which one the analysis took.
  const conflict = (sexSource, ageSource) => ({
    status: 'conflict',
    conflicts: [{ field: 'sex' }, { field: 'age' }],
    printed: { sex: 'female', ageYears: 34 },
    profile: { sex: 'male', ageYears: 20 },
    used: { sexSource, ageSource },
  });

  it('names both sides, and says the REPORT\'s values were used', () => {
    render(<ProfileIdentityNotice identity={conflict('report_details', 'report_details')} />);
    const note = screen.getByRole('note', { name: /may not match your profile/i });
    expect(note.textContent).toMatch(/prints: female, 34 years old/);
    expect(note.textContent).toMatch(/Your profile says: male, 20 years old/);
    expect(note.textContent).toMatch(/used the sex and age printed on the report/);
    expect(note.textContent).toMatch(/someone else.s, its results are theirs/);
  });

  it('an analysis from before the change says it used the PROFILE, and how to change that', () => {
    render(<ProfileIdentityNotice identity={conflict('patient_profile', 'patient_profile')} />);
    const note = screen.getByRole('note', { name: /may not match your profile/i });
    expect(note.textContent).toMatch(/used your profile.s values, not the report.s/);
    expect(note.textContent).toMatch(/Analysing the report again uses the report.s/);
    expect(note.textContent).not.toMatch(/used the sex and age printed on the report/);
  });

  it('a mix is said as a mix, not as either', () => {
    render(<ProfileIdentityNotice identity={conflict('report_details', 'patient_profile')} />);
    expect(screen.getByRole('note').textContent).toMatch(/report.s values for some of these and your\s+profile.s for others/);
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

describe('the report\'s own sex and age are details, never results (2026-09-25)', () => {
  it('shows them under their own heading, not in the results table and not as "your profile"', async () => {
    vi.spyOn(api, 'getDashboard').mockResolvedValue({
      report: { originalName: '01-all-normal.pdf' },
      dashboard: {
        overall: { status: 'Healthy', statusLabel: 'Healthy', risk: 'Low', anyAssessed: true, complete: true },
        laboratory: [
          { feature: 'hemoglobin', displayName: 'Haemoglobin', value: 13.6, unit: 'g/dl', state: 'measured', usable: true, source: 'lab_report' },
          { feature: 'age', displayName: 'Age', value: 34, unit: 'years', state: 'measured', usable: true, source: 'report_details' },
          { feature: 'gender', displayName: 'Sex', value: 'female', state: 'measured', usable: true, source: 'report_details' },
          { feature: 'bmi', displayName: 'BMI', value: 22.1, unit: 'kg/m2', state: 'measured', usable: true, source: 'patient_profile' },
        ],
      },
    });
    render(
      <MemoryRouter initialEntries={['/reports/abc']}>
        <Routes>
          <Route path="/reports/:id" element={<Dashboard />} />
        </Routes>
      </MemoryRouter>
    );
    const heading = await screen.findByRole('heading', { name: /From the report.s patient details/i });
    const detailsTable = heading.nextElementSibling;
    expect(detailsTable.textContent).toMatch(/34/);
    expect(detailsTable.textContent).toMatch(/female/i);
    expect(detailsTable.textContent).not.toMatch(/BMI/);

    const results = screen.getByRole('heading', { name: /^Your results$/ }).nextElementSibling;
    expect(results.textContent).toMatch(/13\.6/);
    expect(results.textContent).not.toMatch(/\b34\b/);
    expect(results.textContent).not.toMatch(/female/i);

    const profile = screen.getByRole('heading', { name: /From your profile/ }).nextElementSibling;
    expect(profile.textContent).toMatch(/BMI/);
    expect(profile.textContent).not.toMatch(/female/i);

    // 2026-10-02: the printed details' column said "You entered" -- nobody
    // entered them, the report printed them -- and called age a "Test".
    const head = (table) => [...table.querySelectorAll('thead th')].map((th) => th.textContent);
    expect(head(detailsTable)).toEqual(['Detail', 'Printed on the report']);
    expect(head(profile)).toEqual(['Detail', 'You entered']);
    expect(head(results)[0]).toBe('Test');
    expect(head(results)[1]).toBe('Result');
  });

  it('isPatientDetail covers both kinds of detail and nothing measured', async () => {
    const { isPatientDetail } = await import('../src/lib/sources');
    expect(isPatientDetail('patient_profile')).toBe(true);
    expect(isPatientDetail('report_details')).toBe(true);
    expect(isPatientDetail('lab_report')).toBe(false);
    expect(isPatientDetail(undefined)).toBe(false);
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
        profile: { sex: 'male', ageYears: 20 },
        used: { sex: 'female', sexSource: 'report_details', ageYears: 34, ageSource: 'report_details' },
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
