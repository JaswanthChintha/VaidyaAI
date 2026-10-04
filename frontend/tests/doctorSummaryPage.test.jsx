import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, Link } from 'react-router-dom';
import DoctorSummary from '../src/pages/DoctorSummary';
import { api, ApiError } from '../src/lib/api';

/**
 * 2026-10-02: moving from one report's clinical summary to another kept the
 * first one's error on screen. React Router keeps the page mounted when only
 * `:id` changes, and nothing cleared the old state.
 */
const SUMMARY = {
  overall: { status_label: 'Healthy', clean_bill_of_health: true },
  attribution: { report_date: '2026-09-07T04:00:14.776000Z' },
  patient: { age: 34, gender: 'female' },
  data_quality: { page_count: 1, pages_unreadable: [], partial_document: false },
  laboratory: { total: 0, rows: [] },
  assessments: [],
};

afterEach(() => vi.restoreAllMocks());

it('clears the previous report\'s error when another report is opened', async () => {
  vi.spyOn(api, 'getDoctorSummary').mockImplementation(async (id) => {
    if (id === 'gone') throw new ApiError(404, 'NOT_FOUND', 'Resource not found');
    return { report: { originalName: 'r.pdf' }, history: {}, doctorSummary: SUMMARY, narrative: null };
  });

  render(
    <MemoryRouter initialEntries={['/reports/gone/doctor-summary']}>
      <Link to="/reports/real/doctor-summary">open the other one</Link>
      <Routes>
        <Route path="/reports/:id/doctor-summary" element={<DoctorSummary />} />
      </Routes>
    </MemoryRouter>
  );

  expect(await screen.findByRole('alert')).toHaveTextContent('Resource not found');
  fireEvent.click(screen.getByText('open the other one'));

  await waitFor(() => expect(document.querySelector('.passage')).toBeTruthy());
  expect(screen.queryByText('Resource not found')).toBeNull();
});

it('offers to print the summary', async () => {
  vi.spyOn(api, 'getDoctorSummary').mockResolvedValue({
    report: { originalName: 'r.pdf' }, history: {}, doctorSummary: SUMMARY, narrative: null,
  });
  const print = vi.spyOn(window, 'print').mockImplementation(() => {});
  render(
    <MemoryRouter initialEntries={['/reports/real/doctor-summary']}>
      <Routes>
        <Route path="/reports/:id/doctor-summary" element={<DoctorSummary />} />
      </Routes>
    </MemoryRouter>
  );
  fireEvent.click(await screen.findByRole('button', { name: /Print or save as PDF/ }));
  expect(print).toHaveBeenCalled();
});
