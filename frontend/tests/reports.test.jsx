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

  // =================================== the date ON the report, or the upload ==
  //
  // `chronoDate` is `reportDate ?? uploadedAt`, so printing it bare showed the
  // upload clock as the date on the document. A report printed 13 September,
  // uploaded on the 19th with the optional field blank, read `9/19/2026`.
  //
  // The `Absent` branch this row already had could never fire: `chronoDate` is
  // `required: true` on the schema and always falls back, so the honest state
  // the component was written for was unreachable.

  it('prints the date the person gave for the report', async () => {
    mount([
      {
        ...REPORT,
        reportDate: '2026-09-13T00:00:00Z',
        chronoDate: '2026-09-13T00:00:00Z',
      },
    ]);
    const row = (await screen.findByText('labs.pdf')).closest('li');
    expect(row.textContent).toContain(new Date('2026-09-13T00:00:00Z').toLocaleDateString());
    expect(row.textContent).not.toMatch(/uploaded/i);
    expect(row.textContent).not.toMatch(/No date on the report/i);
  });

  it('SAYS SO when no date was given, instead of printing the upload clock', async () => {
    // THE CASE THAT WAS WRONG ON THE REAL PAGE.
    mount([{ ...REPORT, reportDate: null, chronoDate: '2026-09-19T04:22:13Z' }]);
    const row = (await screen.findByText('labs.pdf')).closest('li');

    expect(row.textContent).toMatch(/No date on the report/i);
    // The upload day is still shown -- it is real information and it is what
    // the ordering uses -- but it is LABELLED, not passed off as the other.
    expect(row.textContent).toMatch(/uploaded/i);
    expect(row.textContent).toContain(new Date('2026-09-19T04:22:13Z').toLocaleDateString());
  });

  // ========================== the date the DOCUMENT prints (2026-09-24) ==
  //
  // Two reports that both print 05-Sep-2026 were typed as the 9th and the
  // 11th, and nothing on this page said the documents disagreed.
  const utcDay = (iso) => new Date(iso).toLocaleDateString(undefined, { timeZone: 'UTC' });

  it('SAYS SO when the typed date and the printed date disagree', async () => {
    mount([
      {
        ...REPORT,
        reportDate: '2026-09-09T00:00:00Z',
        printedDate: '2026-09-05T00:00:00Z',
        printedDateStatus: 'read',
        chronoDate: '2026-09-09T00:00:00Z',
      },
    ]);
    const row = (await screen.findByText('labs.pdf')).closest('li');
    // The typed date still leads -- it is what the timeline is ordered by.
    expect(row.textContent).toContain(utcDay('2026-09-09T00:00:00Z'));
    expect(row.textContent).toMatch(/the report itself prints/i);
    expect(row.textContent).toContain(utcDay('2026-09-05T00:00:00Z'));
  });

  it('says nothing extra when the two agree', async () => {
    mount([
      {
        ...REPORT,
        reportDate: '2026-09-05T00:00:00Z',
        printedDate: '2026-09-05T00:00:00Z',
        printedDateStatus: 'read',
        chronoDate: '2026-09-05T00:00:00Z',
      },
    ]);
    const row = (await screen.findByText('labs.pdf')).closest('li');
    expect(row.textContent).not.toMatch(/prints/i);
  });

  it('uses the printed date when none was typed, and says where it came from', async () => {
    mount([
      {
        ...REPORT,
        reportDate: null,
        printedDate: '2026-09-05T00:00:00Z',
        printedDateStatus: 'read',
        chronoDate: '2026-09-05T00:00:00Z',
      },
    ]);
    const row = (await screen.findByText('labs.pdf')).closest('li');
    expect(row.textContent).toContain(utcDay('2026-09-05T00:00:00Z'));
    expect(row.textContent).toMatch(/read from the report/i);
    expect(row.textContent).not.toMatch(/No date on the report/i);
  });

  it('quotes a printed date it could not read, and never uses it', async () => {
    mount([
      {
        ...REPORT,
        reportDate: null,
        printedDateStatus: 'ambiguous',
        printedDateRaw: '05/09/2026',
        chronoDate: '2026-09-19T04:22:13Z',
      },
    ]);
    const row = (await screen.findByText('labs.pdf')).closest('li');
    expect(row.textContent).toMatch(/No date on the report/i);
    expect(row.textContent).toMatch(/05\/09\/2026/);
    expect(row.textContent).toMatch(/day-first or month-first/i);
    expect(row.textContent).toMatch(/uploaded/i);
  });

  // ================ "Being analysed…" must find out when it stops (2026-09-25)
  //
  // A list loaded while an analysis was running showed "Being analysed…" for
  // 18 minutes after the report had been stored as processed: the page only
  // refreshed when its OWN Analyse click returned.

  it('re-checks a report being analysed, and shows it done without a click', async () => {
    const { PROCESSING_POLL_MS } = await import('../src/pages/Reports');
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const list = vi
        .spyOn(api, 'listReports')
        .mockResolvedValueOnce({ reports: [{ ...REPORT, status: 'processing' }] })
        .mockResolvedValue({ reports: [{ ...REPORT, status: 'processed' }] });
      render(
        <MemoryRouter>
          <Reports />
        </MemoryRouter>
      );
      await screen.findByText('Being analysed…');
      expect(screen.getByText(/updates by itself when the analysis finishes/i)).toBeInTheDocument();

      await vi.advanceTimersByTimeAsync(PROCESSING_POLL_MS);
      await screen.findByText('Analysed');
      expect(screen.queryByText('Being analysed…')).not.toBeInTheDocument();
      expect(list).toHaveBeenCalledTimes(2);

      // Nothing processing any more: the asking stops.
      await vi.advanceTimersByTimeAsync(PROCESSING_POLL_MS * 3);
      expect(list).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it('never polls a list with nothing being analysed', async () => {
    const { PROCESSING_POLL_MS } = await import('../src/pages/Reports');
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const list = vi.spyOn(api, 'listReports').mockResolvedValue({ reports: [REPORT] });
      const { unmount } = render(
        <MemoryRouter>
          <Reports />
        </MemoryRouter>
      );
      await screen.findByText('Analysed');
      await vi.advanceTimersByTimeAsync(PROCESSING_POLL_MS * 3);
      expect(list).toHaveBeenCalledTimes(1);
      unmount();
    } finally {
      vi.useRealTimers();
    }
  });

  it('stops asking when the page is left', async () => {
    const { PROCESSING_POLL_MS } = await import('../src/pages/Reports');
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const list = vi
        .spyOn(api, 'listReports')
        .mockResolvedValue({ reports: [{ ...REPORT, status: 'processing' }] });
      const { unmount } = render(
        <MemoryRouter>
          <Reports />
        </MemoryRouter>
      );
      await screen.findByText('Being analysed…');
      unmount();
      await vi.advanceTimersByTimeAsync(PROCESSING_POLL_MS * 3);
      expect(list).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('tells the uploader a blank date falls back to the printed one', async () => {
    mount([]);
    await screen.findByText(/Upload a report/i);
    expect(screen.getByText(/date printed on the report is used, if it can be read/i)).toBeInTheDocument();
  });
});
