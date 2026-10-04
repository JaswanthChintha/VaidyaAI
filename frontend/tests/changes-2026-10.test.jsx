import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import DoctorSummary from '../src/pages/DoctorSummary';
import Population from '../src/pages/Population';
import Reports from '../src/pages/Reports';
import SignIn from '../src/pages/SignIn';
import Dashboard from '../src/pages/Dashboard';
import { AuthProvider } from '../src/lib/auth';
import { api, ApiError, isSessionRejected, refreshSession } from '../src/lib/api';
import { readableName } from '../src/lib/displayName';

/**
 * The changes of 2026-10-02 / 10-03, each pinned on the property the owner
 * asked for -- found by reading the real screens, so each test names the
 * screen it came from.
 */

beforeEach(() => {
  vi.restoreAllMocks();
});

// ------------------------------------------------------------ readableName

describe('readableName -- printed capitals, as a reader would write them', () => {
  it.each([
    ['C-REACTIVE PROTEIN(CRP)', 'C-reactive protein (CRP)'],
    ['AVERAGE BLOOD GLUCOSE', 'Average blood glucose'],
    ['RANDOM BLOOD GLUCOSE ( RBS )', 'Random blood glucose (RBS)'],
    ['GLYCATED HAEMOGLOBIN (HBA1C)', 'Glycated haemoglobin (HBA1C)'],
    ['TOTAL WBC COUNT', 'Total WBC count'],
    ['VITAMIN B12', 'Vitamin B12'],
    ['TOTAL IRON BINDING CAPACITY', 'Total iron binding capacity'],
    ['ESR', 'ESR'],
    ['SGPT', 'SGPT'],
  ])('%s -> %s', (printed, readable) => {
    expect(readableName(printed)).toBe(readable);
  });

  it('leaves a name with any lower-case letter exactly as written', () => {
    expect(readableName('HbA1c (average blood sugar)')).toBe('HbA1c (average blood sugar)');
  });

  it('passes empty and absent values through', () => {
    expect(readableName('')).toBe('');
    expect(readableName(null)).toBe(null);
  });
});

// ------------------------------------------------------------ clinician page

const LAB_ROW = (feature, printed, value, unit, flag = null) => ({
  feature,
  display_name: printed,
  value,
  unit,
  usable: true,
  printed_flag: flag,
  reference_low: null,
  reference_high: null,
  provenance: { source: 'lab_report', original_test_name: { text: printed } },
});

const PERSON_ROW = (feature, value, source) => ({
  feature,
  display_name: feature,
  value,
  unit: feature === 'bmi' ? 'kg/m2' : null,
  usable: true,
  provenance: { source },
});

function mountSummary(rows, unassessed) {
  vi.spyOn(api, 'getDoctorSummary').mockResolvedValue({
    report: { originalName: 'r.pdf' },
    history: {},
    doctorSummary: {
      overall: { status_label: 'Needs Monitoring' },
      attribution: {},
      patient: {},
      data_quality: { page_count: 1, pages_unreadable: [] },
      laboratory: { rows },
      assessments: [],
    },
    // The WRITTEN branch -- where "Analysed as." had to be added.
    narrative: { outcome: 'generated', text: 'This tool flagged Diabetes because HbA1c was 8.4 %.' },
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

const passage = async () => {
  await waitFor(() => expect(document.querySelector('.passage')).toBeTruthy());
  return document.querySelector('.passage').textContent;
};

describe('clinician summary -- Test 3 and 02-diabetes, 2026-10-02/03', () => {
  it('says who the analysis took the patient to be, and from where', async () => {
    mountSummary([
      LAB_ROW('hba1c', 'HBA1C', 8.4, '%'),
      PERSON_ROW('gender', 'male', 'patient_profile'),
      PERSON_ROW('age', 20, 'patient_profile'),
      PERSON_ROW('bmi', 25.25, 'patient_profile'),
    ]);
    const text = await passage();
    expect(text).toMatch(/Analysed as\.\s*Male, 20 years, BMI 25\.25 kg\/m²/);
    expect(text).toMatch(/sex, age and BMI from the patient's profile/);
    // "could be read", not "prints": a profile value is also used for a
    // printed one this tool could not read.
    expect(text).toMatch(/no sex or age could be read from the report/);
  });

  it('credits printed values to the report', async () => {
    mountSummary([
      LAB_ROW('hba1c', 'HbA1c', 5.2, '%'),
      PERSON_ROW('gender', 'female', 'report_details'),
      PERSON_ROW('age', 34, 'report_details'),
      PERSON_ROW('bmi', 25.25, 'patient_profile'),
    ]);
    const text = await passage();
    expect(text).toMatch(/Female, 34 years/);
    expect(text).toMatch(/sex and age as printed on the report; BMI from the patient's profile/);
    expect(text).not.toMatch(/could be read/);
  });

  it('lists the tests this tool does not assess with the rest, and says nothing about coverage', async () => {
    mountSummary([LAB_ROW('hba1c', 'HBA1C', 7, '%', 'high')], {
      items: [
        { testName: 'SGPT', value: '13', unit: 'IU/L', labFlag: 'normal', labFlaggedAbnormal: false },
        { testName: 'AVERAGE BLOOD GLUCOSE', value: '154', unit: 'mg/dL', labFlag: null },
      ],
    });
    const text = await passage();
    expect(text).toMatch(/Reported values\..*SGPT 13 IU\/L \(normal\)/);
    expect(text).toMatch(/Average blood glucose 154 mg\/dL/);
    // The owner's standing rule (clinical.test.jsx pins it page-wide too).
    expect(text.toLowerCase()).not.toContain('does not assess');
    // A flag may have been inferred from the interval, so no agent is named.
    expect(text).not.toMatch(/per the reporting laboratory/);
    expect(text).toMatch(/HBA1C|Hba1c|HbA1c/);
  });
});

// ------------------------------------------------------------ population page

function mountPopulation(features, subject, notCompared) {
  vi.spyOn(api, 'getPopulationContext').mockResolvedValue({
    report: { originalName: 'r.pdf' },
    subject,
    notCompared,
    populationContext: { features },
  });
  return render(
    <MemoryRouter initialEntries={['/reports/abc/population']}>
      <Routes>
        <Route path="/reports/:id/population" element={<Population />} />
      </Routes>
    </MemoryRouter>
  );
}

const HB = {
  hemoglobin: {
    feature: 'hemoglobin',
    available: true,
    comparison: {
      value: 12.5,
      unit: 'g/dl',
      band: { label: 'below the 1st percentile' },
      cohort: { age_band_label: '20-29 years', sex: 'male' },
    },
  },
};

describe('population page -- Test 3, 2026-10-02', () => {
  it('says when the group was chosen from the profile', async () => {
    mountPopulation(HB, {
      source: 'profile', ageSource: 'profile', genderSource: 'profile',
      profileExists: true, ageProvided: true, genderProvided: true,
    });
    expect(
      await screen.findByText(/No age or sex could be read from this report, so the ones in your profile were used/)
    ).toBeInTheDocument();
  });

  it('does not say so when the report printed them', async () => {
    mountPopulation(HB, {
      source: 'report', ageSource: 'report', genderSource: 'report',
      profileExists: true, ageProvided: true, genderProvided: true,
    });
    await screen.findByText(/printed on this report/);
    expect(screen.queryByText(/No age or sex could be read/)).not.toBeInTheDocument();
  });

  it('names the tests that were not compared, in readable case', async () => {
    mountPopulation(
      HB,
      { source: 'profile', ageSource: 'profile', genderSource: 'profile', profileExists: true, ageProvided: true, genderProvided: true },
      ['ESR', 'C-REACTIVE PROTEIN(CRP)']
    );
    expect(
      await screen.findByText(/not compared, because this tool has no population data for them: ESR and C-reactive protein \(CRP\)\./)
    ).toBeInTheDocument();
  });
});

// ------------------------------------------------------------ reports page

function mountReports(reports) {
  vi.spyOn(api, 'listReports').mockResolvedValue({ reports });
  return render(
    <MemoryRouter>
      <Reports />
    </MemoryRouter>
  );
}

describe('reports page -- 2026-10-02', () => {
  it('says analysis is a separate step', async () => {
    mountReports([]);
    expect(await screen.findByText(/press/)).toHaveTextContent('Upload a report, press Analyse, then open its dashboard.');
  });

  it('states the size limit', async () => {
    mountReports([]);
    expect(await screen.findByText(/up to 10 MB/)).toBeInTheDocument();
  });

  it('does not offer a future date', async () => {
    mountReports([]);
    await screen.findByText(/up to 10 MB/);
    const input = document.querySelector('input[type="date"]');
    const now = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    expect(input.max).toBe(`${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`);
    expect(input.min).toBe('1900-01-01');
  });

  it('asks for a file in its own words', async () => {
    mountReports([]);
    await screen.findByText(/up to 10 MB/);
    const input = document.querySelector('input[type="file"]');
    expect(input.form.checkValidity()).toBe(false);
    expect(input.validationMessage).toBe('Choose a report file to upload first.');
  });

  it('says where a typed date came from when the report prints none', async () => {
    mountReports([
      {
        id: 'r1', originalName: 'Test 3.pdf', status: 'processed',
        uploadedAt: '2026-09-19T04:22:13Z', reportDate: '2026-09-13T00:00:00Z',
        chronoDate: '2026-09-13T00:00:00Z', printedDateStatus: 'absent',
      },
    ]);
    expect(await screen.findByText(/typed in; the report prints no date/)).toBeInTheDocument();
  });
});

// ------------------------------------------------------------ sign-in page

function mountSignIn() {
  return render(
    <MemoryRouter initialEntries={['/signin']}>
      <AuthProvider>
        <Routes>
          <Route path="/signin" element={<SignIn />} />
          <Route path="/reports" element={<p>reports page</p>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );
}

const field = (label) => screen.getByLabelText(label, { exact: false });

describe('sign-in page -- 2026-10-02 (there is no "forgot password")', () => {
  it('refuses mismatched passwords on register without calling the server', async () => {
    const register = vi.spyOn(api, 'register');
    mountSignIn();
    fireEvent.click(await screen.findByRole('button', { name: 'Create an account' }));
    fireEvent.change(field('Name'), { target: { value: 'Layout Check' } });
    fireEvent.change(field('Email'), { target: { value: 'a@example.invalid' } });
    fireEvent.change(document.querySelectorAll('.auth input')[2], { target: { value: 'Sample-1a!' } });
    fireEvent.change(field('Confirm password'), { target: { value: 'Sample-1b!' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/The two passwords do not match/);
    expect(register).not.toHaveBeenCalled();
  });

  it('shows and hides the password', async () => {
    mountSignIn();
    const toggle = await screen.findByRole('button', { name: 'Show password' });
    const input = document.querySelector('.auth__password input');
    expect(input.type).toBe('password');
    fireEvent.click(toggle);
    expect(input.type).toBe('text');
    expect(screen.getByRole('button', { name: 'Hide password' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('says how long to wait after too many attempts', async () => {
    vi.spyOn(api, 'login').mockRejectedValue(
      new ApiError(429, 'RATE_LIMIT_EXCEEDED', 'Too many requests, please try again later')
    );
    mountSignIn();
    fireEvent.change(await screen.findByLabelText('Email', { exact: false }), { target: { value: 'a@example.invalid' } });
    fireEvent.change(document.querySelector('.auth__password input'), { target: { value: 'whatever' } });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Too many sign-in attempts. Please wait up to 15 minutes and try again.'
    );
  });
});

// ------------------------------------------------------------ session refresh

describe('a server hiccup does not sign the user out (2026-10-02)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    window.localStorage.setItem('vaidyaai.refresh', 'stored-token');
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    window.localStorage.removeItem('vaidyaai.refresh');
  });

  it('classifies only a server REJECTION as fatal', () => {
    for (const status of [400, 401, 403, 422]) expect(isSessionRejected(new ApiError(status))).toBe(true);
    for (const status of [429, 500, 502, 503]) expect(isSessionRejected(new ApiError(status))).toBe(false);
    expect(isSessionRejected(new TypeError('Failed to fetch'))).toBe(false);
  });

  it('retries a 500 and keeps the stored session', async () => {
    const fetchMock = vi.fn(async () => ({ ok: false, status: 500, json: async () => null }));
    vi.stubGlobal('fetch', fetchMock);
    const pending = refreshSession();
    await vi.runAllTimersAsync();
    expect(await pending).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(window.localStorage.getItem('vaidyaai.refresh')).toBe('stored-token');
  });

  it('clears the session at once on a 401', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: false,
      status: 401,
      json: async () => ({ success: false, error: { code: 'INVALID_REFRESH_TOKEN' } }),
    }));
    vi.stubGlobal('fetch', fetchMock);
    expect(await refreshSession()).toBe(false);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(window.localStorage.getItem('vaidyaai.refresh')).toBeNull();
  });
});

// ------------------------------------------------------------ dashboard tile

describe('dashboard -- "results read from the report" (01-all-normal read 10 for 8)', () => {
  it('counts the rows the results table shows, not empty catalogue rows', async () => {
    vi.spyOn(api, 'getDashboard').mockResolvedValue({
      report: { originalName: 'r.pdf' },
      dashboard: {
        overall: { status: 'Needs Monitoring', risk: 'Low', anyAssessed: true, complete: true },
        conditions: [{ condition: 'Diabetes', status: 'Not Indicated', risk: 'Low', assessed: true, normal: true, flagged: false }],
        laboratory: [
          { feature: 'hba1c', value: 5.2, unit: '%', source: 'lab_report', state: 'valid', usable: true },
          { feature: 'blood_glucose', value: 88, unit: 'mg/dl', source: 'lab_report', state: 'valid', usable: true },
          // Unanswered profile questions: no value, no source.
          { feature: 'heart_disease', value: null, source: null, state: 'unavailable', usable: false },
          { feature: 'hypertension', value: null, source: null, state: 'unavailable', usable: false },
        ],
        unanalysed: { count: 0, items: [] },
        recommendations: {},
      },
    });
    render(
      <MemoryRouter initialEntries={['/reports/abc']}>
        <Routes>
          <Route path="/reports/:id" element={<Dashboard />} />
        </Routes>
      </MemoryRouter>
    );
    const label = await screen.findByText(/read from the report/);
    expect(label.closest('.stat').querySelector('.stat__num').textContent).toBe('2');
  });
});
