import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Reports from '../src/pages/Reports';
import { api } from '../src/lib/api';

/**
 * Module 3's report list -- the screen with NO tests, which is where the two
 * worst live defects on this project have been.
 *
 * MEMORY.md section 6t D1: the client sent the multipart part as `report`
 * while the backend accepts only `file`, so NO REPORT COULD EVER BE UPLOADED,
 * and "zero hits for FormData in frontend/tests" is why nothing said so.
 *
 * And then: an already-analysed report offered no way to run it again, so a
 * catalog fix could never reach a stored report. Both are contract bugs
 * between this page and the backend, and neither is visible from any other
 * suite.
 */

const REPORT = {
  id: 'r1',
  originalName: 'labs.pdf',
  mimeType: 'application/pdf',
  status: 'processed',
  uploadedAt: '2026-09-06T08:00:00Z',
  chronoDate: '2026-09-06T08:00:00Z',
};

function mount(reports) {
  vi.spyOn(api, 'listReports').mockResolvedValue({ reports });
  return render(
    <MemoryRouter>
      <Reports />
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('Module 3 -- the report list', () => {
  it('offers Analyse for a report that has never been analysed', async () => {
    mount([{ ...REPORT, status: 'uploaded' }]);
    expect(await screen.findByRole('button', { name: 'Analyse' })).toBeInTheDocument();
  });

  it('offers Analyse again after a failed run', async () => {
    mount([{ ...REPORT, status: 'failed' }]);
    expect(await screen.findByRole('button', { name: 'Analyse' })).toBeInTheDocument();
  });

  it.each(['processed', 'partial'])(
    'lets an already-analysed report (%s) be run again',
    async (status) => {
      // THE DEFECT. `POST /reports/:id/analyze` has always accepted a re-run,
      // but this page only ever showed the button for `uploaded` and `failed`.
      // Every stored report was frozen against the pipeline that produced it:
      // fix a synonym and no existing report could benefit, with nothing on
      // screen to say why.
      const analyze = vi.spyOn(api, 'analyzeReport').mockResolvedValue({});
      mount([{ ...REPORT, status }]);

      fireEvent.click(await screen.findByRole('button', { name: 'Re-analyse' }));
      // Behind a confirm: it REPLACES the stored analysis and costs model calls.
      expect(screen.getByText(/current result is replaced, not kept alongside/)).toBeInTheDocument();
      expect(analyze).not.toHaveBeenCalled();

      fireEvent.click(screen.getByRole('button', { name: 'Re-analyse' }));
      await waitFor(() => expect(analyze).toHaveBeenCalledWith('r1'));
    }
  );

  it('does not re-analyse when the confirm is cancelled', async () => {
    const analyze = vi.spyOn(api, 'analyzeReport').mockResolvedValue({});
    mount([REPORT]);

    fireEvent.click(await screen.findByRole('button', { name: 'Re-analyse' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(screen.queryByText(/current result is replaced/)).not.toBeInTheDocument();
    expect(analyze).not.toHaveBeenCalled();
  });

  it('names the report in the confirm, so the reader knows which one', async () => {
    mount([REPORT]);
    fireEvent.click(await screen.findByRole('button', { name: 'Re-analyse' }));
    // Scoped to the confirm: the filename is also the row's own link, and a
    // confirm that does not name its target is the thing this asserts against.
    expect(
      document.querySelector('.report__confirm-text').textContent
    ).toMatch(/labs\.pdf/);
  });

  it('sends the upload in the `file` field the backend accepts', async () => {
    // SECTION 6t D1, PINNED. Any other field name is rejected by multer as
    // LIMIT_UNEXPECTED_FILE and surfaces as "Unexpected file upload" -- which
    // blamed the user for sending several files when they sent one. No
    // frontend test covered upload at all when that shipped.
    const upload = vi.spyOn(api, 'uploadReport').mockResolvedValue({});
    mount([]);
    await screen.findByText(/Upload a report/i);

    const file = new File(['%PDF-1.4'], 'labs.pdf', { type: 'application/pdf' });
    const input = document.querySelector('input[type="file"]');
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    fireEvent.change(input);
    fireEvent.submit(screen.getByRole('button', { name: /^Upload$/ }).closest('form'));

    await waitFor(() => expect(upload).toHaveBeenCalled());
    const form = upload.mock.calls[0][0];
    expect(form.get('file')).toBeInstanceOf(File);
    expect(form.get('report')).toBeNull();
  });
});
