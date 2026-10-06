import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Reports from '../src/pages/Reports';
import Dashboard from '../src/pages/Dashboard';
import { api, ApiError } from '../src/lib/api';
import { friendlyPageError, friendlyStatus } from '../src/lib/friendlyErrors';

/**
 * Plain words for analysis failures (owner, 2026-10-06). Seen live on Render:
 * "ANALYSIS_PARTIAL: Some analysis stages did not complete; see
 * analysis.stages" and "See GET /reports/:id/analysis ..." shown to a patient.
 */

beforeEach(() => vi.restoreAllMocks());

describe('friendlyStatus', () => {
  it('turns the live message into plain words and keeps the code', () => {
    expect(
      friendlyStatus('ANALYSIS_PARTIAL: Some analysis stages did not complete; see analysis.stages')
    ).toEqual({
      text: 'The analysis stopped partway, so some results are missing. Press Re-analyse to try again.',
      code: 'ANALYSIS_PARTIAL',
    });
  });

  it('tells the user to try again in a minute when the service did not answer', () => {
    expect(friendlyStatus('AI_SERVICE_ERROR: The analysis service failed to process this report').text).toMatch(
      /starting up .* Press Analyse again in a minute/
    );
  });

  it('an unknown code still gets plain words, never the raw text', () => {
    const out = friendlyStatus('SOMETHING_NEW: internal detail');
    expect(out.code).toBe('SOMETHING_NEW');
    expect(out.text).not.toContain('internal detail');
  });

  it('nothing to say -> nothing shown', () => {
    expect(friendlyStatus(undefined)).toBeNull();
    expect(friendlyStatus('')).toBeNull();
  });
});

describe('friendlyPageError', () => {
  it.each([
    [
      'No clinical report was produced for this analysis, so there is no dashboard to show. See GET /reports/:id/analysis for which stage did not complete.',
      /stopped partway.*press Re-analyse/,
    ],
    [
      'This report has not been analysed yet. Run POST /reports/:id/analyze first.',
      /not been analysed yet\. Go back to your reports and press Analyse/,
    ],
  ])('%s', (input, expected) => {
    const out = friendlyPageError(input);
    expect(out).toMatch(expected);
    expect(out).not.toMatch(/GET|POST|\/reports\//);
  });

  it('other messages pass through unchanged', () => {
    expect(friendlyPageError('Report not found')).toBe('Report not found');
  });
});

describe('on the pages', () => {
  it('Reports shows the plain words and the code, not "see analysis.stages"', async () => {
    vi.spyOn(api, 'getProfile').mockResolvedValue({ profile: { age: 30, gender: 'male' } });
    vi.spyOn(api, 'listReports').mockResolvedValue({
      reports: [
        {
          id: 'r1',
          originalName: 'labs.pdf',
          mimeType: 'application/pdf',
          status: 'partial',
          statusMessage: 'ANALYSIS_PARTIAL: Some analysis stages did not complete; see analysis.stages',
          uploadedAt: '2026-10-06T08:00:00Z',
          chronoDate: '2026-10-06T08:00:00Z',
        },
      ],
    });
    render(
      <MemoryRouter>
        <Reports />
      </MemoryRouter>
    );
    expect(await screen.findByText(/The analysis stopped partway/)).toBeInTheDocument();
    expect(screen.getByText(/code: ANALYSIS_PARTIAL/)).toBeInTheDocument();
    expect(screen.queryByText(/analysis\.stages/)).not.toBeInTheDocument();
  });

  it('the dashboard for a run with no results says what to do, not which endpoint to call', async () => {
    vi.spyOn(api, 'getDashboard').mockRejectedValue(
      new ApiError(
        404,
        'NOT_FOUND',
        'No clinical report was produced for this analysis, so there is no dashboard to show. See GET /reports/:id/analysis for which stage did not complete.'
      )
    );
    render(
      <MemoryRouter initialEntries={['/reports/r1']}>
        <Routes>
          <Route path="/reports/:id" element={<Dashboard />} />
        </Routes>
      </MemoryRouter>
    );
    expect(await screen.findByText(/stopped partway/)).toBeInTheDocument();
    expect(screen.queryByText(/GET \/reports/)).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back to your reports' })).toBeInTheDocument();
  });
});
