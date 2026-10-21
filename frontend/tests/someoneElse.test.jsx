import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Reports from '../src/pages/Reports';
import DoctorSummary from '../src/pages/DoctorSummary';
import Population from '../src/pages/Population';
import Dashboard from '../src/pages/Dashboard';
import Timeline from '../src/pages/Timeline';
import { ProfileIdentityNotice } from '../src/components/IdentityNotice';
import { api } from '../src/lib/api';


beforeEach(() => {
  vi.restoreAllMocks();
});

const REPORT = (over = {}) => ({
  id: 'r1',
  originalName: 'mum.pdf',
  status: 'processed',
  uploadedAt: '2026-10-03T08:00:00Z',
  chronoDate: '2026-10-03T08:00:00Z',
  subject: { owner: 'self' },
  subjectChangedSinceAnalysis: false,
  ...over,
});

function mountReports(reports) {
  vi.spyOn(api, 'listReports').mockResolvedValue({ reports });
  return render(
    <MemoryRouter>
      <Reports />
    </MemoryRouter>
  );
}

describe('reports page -- whose report', () => {
  it('asks on upload, defaults to mine, and shows age and sex only for someone else', async () => {
    mountReports([]);
    await screen.findByText(/up to 10 MB/);
    expect(screen.getByLabelText('Mine')).toBeChecked();
    expect(screen.queryByLabelText(/Their age/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/Someone else/));
    expect(screen.getByLabelText(/Their age/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Their sex/)).toBeInTheDocument();
    expect(screen.getByText(/Your profile is not used for someone else/)).toBeInTheDocument();
  });

  it("sends someone else's age and sex with the upload", async () => {
    const upload = vi.spyOn(api, 'uploadReport').mockResolvedValue({});
    mountReports([]);
    await screen.findByText(/up to 10 MB/);
    fireEvent.click(screen.getByLabelText(/Someone else/));
    fireEvent.change(screen.getByLabelText(/Their age/), { target: { value: '63' } });
    fireEvent.change(screen.getByLabelText(/Their sex/), { target: { value: 'male' } });
    const input = document.querySelector('input[type="file"]');
    fireEvent.change(input, { target: { files: [new File(['%PDF-1.4'], 'mum.pdf', { type: 'application/pdf' })] } });
    fireEvent.submit(input.form);

    await waitFor(() => expect(upload).toHaveBeenCalledTimes(1));
    const form = upload.mock.calls[0][0];
    expect(form.get('subjectOwner')).toBe('other');
    expect(form.get('subjectAge')).toBe('63');
    expect(form.get('subjectSex')).toBe('male');
  });

  it('sends no age or sex for my own report', async () => {
    const upload = vi.spyOn(api, 'uploadReport').mockResolvedValue({});
    mountReports([]);
    await screen.findByText(/up to 10 MB/);
    const input = document.querySelector('input[type="file"]');
    fireEvent.change(input, { target: { files: [new File(['%PDF-1.4'], 'me.pdf', { type: 'application/pdf' })] } });
    fireEvent.submit(input.form);

    await waitFor(() => expect(upload).toHaveBeenCalledTimes(1));
    const form = upload.mock.calls[0][0];
    expect(form.get('subjectOwner')).toBe('self');
    expect(form.has('subjectAge')).toBe(false);
    expect(form.has('subjectSex')).toBe(false);
  });

  it("labels someone else's report in the list", async () => {
    mountReports([REPORT({ subject: { owner: 'other', age: 63, sex: 'male' } })]);
    expect(await screen.findByText(/Someone else’s report \(male, 63\) · not in your timeline/)).toBeInTheDocument();
  });

  it('changes whose report it is from the list, and says to re-analyse', async () => {
    const save = vi.spyOn(api, 'setReportSubject').mockResolvedValue({});
    const list = vi.spyOn(api, 'listReports')
      .mockResolvedValueOnce({ reports: [REPORT()] })
      .mockResolvedValueOnce({
        reports: [REPORT({ subject: { owner: 'other', age: 63 }, subjectChangedSinceAnalysis: true })],
      });
    render(
      <MemoryRouter>
        <Reports />
      </MemoryRouter>
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Whose report?' }));
    const editor = within(document.querySelector('.report__subject-editor'));
    fireEvent.click(editor.getByLabelText(/Someone else/));
    fireEvent.change(editor.getByLabelText(/Their age/), { target: { value: '63' } });
    fireEvent.click(editor.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(save).toHaveBeenCalledWith('r1', { owner: 'other', age: '63', sex: '' }));
    expect(await screen.findByText(/Press\s+Re-analyse to apply it/)).toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(2);
  });
});

describe('dashboard -- someone else’s report', () => {
  it('says the profile was not used, instead of comparing with it', () => {
    render(<ProfileIdentityNotice identity={{ status: 'other_person' }} />);
    expect(screen.getByText(/Marked as someone else’s report\. Your profile was not used/)).toBeInTheDocument();
    expect(screen.queryByText(/may not match your profile/)).not.toBeInTheDocument();
  });

  it('titles the typed details "Entered for this report", not "From your profile"', async () => {
    vi.spyOn(api, 'getDashboard').mockResolvedValue({
      report: { originalName: 'mum.pdf', subject: { owner: 'other', age: 63 } },
      identity: { status: 'other_person' },
      dashboard: {
        overall: { status: 'Needs Monitoring', risk: 'Low', anyAssessed: true, complete: true },
        conditions: [{ condition: 'Diabetes', status: 'Not Indicated', risk: 'Low', assessed: true, normal: true }],
        laboratory: [
          { feature: 'hba1c', value: 5.2, unit: '%', source: 'lab_report', state: 'valid', usable: true },
          { feature: 'age', value: 63, unit: 'years', source: 'patient_profile', state: 'valid', usable: true },
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
    expect(await screen.findByRole('heading', { name: 'Entered for this report' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'From your profile' })).not.toBeInTheDocument();
  });
});

describe('clinician summary -- someone else’s report', () => {
  it('says the typed details were entered for this report', async () => {
    vi.spyOn(api, 'getDoctorSummary').mockResolvedValue({
      report: { originalName: 'mum.pdf', subject: { owner: 'other', age: 63, sex: 'male' } },
      history: {},
      doctorSummary: {
        overall: {},
        attribution: {},
        patient: {},
        data_quality: { page_count: 1, pages_unreadable: [] },
        laboratory: {
          rows: [
            { feature: 'gender', value: 'male', usable: true, provenance: { source: 'patient_profile' } },
            { feature: 'age', value: 63, usable: true, provenance: { source: 'patient_profile' } },
          ],
        },
        assessments: [],
      },
      narrative: { outcome: 'generated', text: 'This tool flagged nothing on this report.' },
    });
    render(
      <MemoryRouter initialEntries={['/reports/abc/doctor-summary']}>
        <Routes>
          <Route path="/reports/:id/doctor-summary" element={<DoctorSummary />} />
        </Routes>
      </MemoryRouter>
    );
    await waitFor(() => expect(document.querySelector('.passage')).toBeTruthy());
    const text = document.querySelector('.passage').textContent;
    expect(text).toMatch(/Male, 63 years — sex and age as entered for this report/);
    expect(text).not.toMatch(/patient's profile/);
  });
});

describe('population -- someone else’s report', () => {
  const mount = (subject) => {
    vi.spyOn(api, 'getPopulationContext').mockResolvedValue({
      report: { originalName: 'mum.pdf' },
      subject,
      notCompared: [],
      populationContext: {
        features: {
          hemoglobin: {
            feature: 'hemoglobin',
            available: true,
            comparison: {
              value: 12.5,
              unit: 'g/dl',
              band: { label: 'between the 5th and the 10th percentile' },
              cohort: { age_band_label: '60-69 years', sex: 'male' },
            },
          },
        },
      },
    });
    return render(
      <MemoryRouter initialEntries={['/reports/abc/population']}>
        <Routes>
          <Route path="/reports/:id/population" element={<Population />} />
        </Routes>
      </MemoryRouter>
    );
  };

  it('says the entered age and sex chose the group, not the profile', async () => {
    mount({ source: 'entered', ageSource: 'entered', genderSource: 'entered', otherPerson: true,
      profileExists: false, ageProvided: true, genderProvided: true });
    expect(await screen.findByText(/The age and sex entered for this report were used to choose the group/)).toBeInTheDocument();
    expect(screen.getByText(/the age and sex of the person this report describes/)).toBeInTheDocument();
    expect(screen.queryByText(/your profile were used/)).not.toBeInTheDocument();
  });

  it('points a missing age to the report, not to "your details"', async () => {
    mount({ source: 'entered', ageSource: null, genderSource: 'entered', otherPerson: true,
      profileExists: false, ageProvided: false, genderProvided: true });
    expect(await screen.findByText(/No age is known for the person this report describes/)).toBeInTheDocument();
    expect(screen.queryByText(/You have not filled in your details/)).not.toBeInTheDocument();
    expect(screen.queryByText('Update your details')).not.toBeInTheDocument();
  });
});

describe('timeline -- someone else’s reports are left out, and said to be', () => {
  it('names them apart from reports that could not contribute', async () => {
    vi.spyOn(api, 'getTrends').mockResolvedValue({
      trends: { features: {} },
      history: {
        included: 2,
        considered: 4,
        excludedCount: 2,
        excluded: [
          { reportId: 'a', reasonCode: 'SOMEONE_ELSE' },
          { reportId: 'b', reasonCode: 'NOT_ANALYSED' },
        ],
      },
    });
    vi.spyOn(api, 'getComparison').mockResolvedValue({});
    vi.spyOn(api, 'getProgress').mockResolvedValue({});
    vi.spyOn(api, 'listReports').mockResolvedValue({ reports: [] });
    render(
      <MemoryRouter>
        <Timeline />
      </MemoryRouter>
    );
    const line = await screen.findByText(/Built from/);
    expect(line.textContent).toMatch(/1 report is marked as someone else’s and is not included\./);
    expect(line.textContent).toMatch(/1 could not contribute\./);
  });
});
