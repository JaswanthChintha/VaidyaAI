import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../lib/api';
import { Absent } from '../components/Absent';

/**
 * Module 3's report list, plus upload and analyse.
 *
 * STATUS IS SHOWN AS THE FIVE-VALUE THING IT IS. `uploaded`, `processing`,
 * `processed`, `partial` and `failed` are not decoration: `partial` means
 * every load-bearing stage succeeded but something downstream did not, and
 * flattening it into "done" would tell a patient their analysis is complete
 * when a stage failed. `analysis.stages` says which one, and that is offered
 * rather than hidden.
 *
 * Analysis is slow -- a real extraction runs 45s to 190s against the model --
 * so the button says so rather than appearing broken.
 */

const STATUS_COPY = {
  uploaded: 'Uploaded, not yet analysed',
  processing: 'Being analysed…',
  processed: 'Analysed',
  partial: 'Analysed, with some stages incomplete',
  failed: 'Analysis failed',
};

export default function Reports() {
  const [reports, setReports] = useState(null);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [uploading, setUploading] = useState(false);
  // The report whose delete is awaiting confirmation. Deleting a medical
  // report destroys the file AND its analysis, and there is no undo, so the
  // confirmation is inline in the row rather than a browser confirm() the
  // user can dismiss without reading.
  const [confirmingId, setConfirmingId] = useState(null);
  const [reanalysingId, setReanalysingId] = useState(null);

  const load = useCallback(async () => {
    try {
      const data = await api.listReports();
      setReports(data.reports || data || []);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function onUpload(event) {
    event.preventDefault();
    const input = event.target.elements.report;
    if (!input.files?.length) return;

    const form = new FormData();
    // The multipart part MUST be named `file` -- that is the backend's
    // contract (`upload.single('file')` in src/middleware/upload.js). Any
    // other name is rejected by multer as LIMIT_UNEXPECTED_FILE, which
    // surfaces to the user as "Unexpected file upload".
    form.append('file', input.files[0]);
    const reportDate = event.target.elements.reportDate.value;
    // The date PRINTED on the report, not today. Uploading three years of
    // history in one sitting would otherwise produce a timeline in which
    // every report happened today -- which is why `chronoDate` exists.
    if (reportDate) form.append('reportDate', reportDate);

    setUploading(true);
    setError(null);
    try {
      await api.uploadReport(form);
      input.value = '';
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  }

  async function onAnalyze(id) {
    setBusyId(id);
    setError(null);
    try {
      await api.analyzeReport(id);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  async function onOpenFile(report) {
    setError(null);
    try {
      await api.openReportFile(report.id, report.mimeType);
    } catch (err) {
      setError(err.message);
    }
  }

  async function onDelete(id) {
    setBusyId(id);
    setError(null);
    try {
      await api.deleteReport(id);
      setConfirmingId(null);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  if (reports === null && !error) return <p className="loading">Loading your reports…</p>;

  return (
    <main className="reports">
      <h2>Your reports</h2>

      <form onSubmit={onUpload} className="card">
        <h3>Upload a report</h3>
        <label>
          PDF, JPEG or PNG
          <input type="file" name="report" accept=".pdf,.jpg,.jpeg,.png" required />
        </label>
        <label>
          Date printed on the report (optional)
          <input type="date" name="reportDate" />
          <span className="hint">
            Used to order your timeline. Leave blank and today&rsquo;s date is
            used instead.
          </span>
        </label>
        <button type="submit" disabled={uploading}>
          {uploading ? 'Uploading…' : 'Upload'}
        </button>
      </form>

      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}

      {reports?.length === 0 ? (
        <p className="empty">
          No reports yet. Upload one above to get started.
        </p>
      ) : null}

      <ul className="report-list">
        {(reports || []).map((report) => (
          <li key={report.id} className="card report">
            <div className="report__head">
              {/* The name opens the ORIGINAL document. A plain <a href> cannot
                  be used: the download route is owner-scoped and needs the
                  bearer token, which a link does not send. */}
              <button
                type="button"
                className="link report__name"
                onClick={() => onOpenFile(report)}
                title="Open the original file"
              >
                {report.originalName}
              </button>
              <span className={`status status--${report.status}`}>
                {STATUS_COPY[report.status] || report.status}
              </span>
            </div>
            <p className="report__meta">
              {report.chronoDate ? (
                new Date(report.chronoDate).toLocaleDateString()
              ) : (
                <Absent reason="No date was recorded for this report." label="No date" />
              )}
            </p>
            {report.statusMessage ? (
              <p className="report__note">{report.statusMessage}</p>
            ) : null}
            <div className="report__actions">
              {report.status === 'processed' || report.status === 'partial' ? (
                <Link className="button-link" to={`/reports/${report.id}`}>
                  View dashboard
                </Link>
              ) : null}
              {report.status === 'uploaded' || report.status === 'failed' ? (
                <button
                  type="button"
                  onClick={() => onAnalyze(report.id)}
                  disabled={busyId === report.id}
                >
                  {busyId === report.id ? 'Analysing… this can take a few minutes' : 'Analyse'}
                </button>
              ) : null}

              {/* RE-ANALYSING AN ALREADY-ANALYSED REPORT WAS IMPOSSIBLE FROM
                  THE UI, and that is a bigger gap than it looks.
                  `POST /reports/:id/analyze` has always accepted a re-run --
                  MEMORY.md section 6f documents the semantics as "overwrite,
                  not versioned" -- but this list only ever offered the button
                  for `uploaded` and `failed`. So every stored report was
                  frozen against the pipeline that produced it: fix a synonym,
                  a threshold or a model, and no existing report could ever
                  benefit, with nothing on screen to say why.

                  It surfaced as a report whose only test was
                  "GLYCOSYLATED HEMOGLOBIN, HbA1c" mapping to nothing. The
                  catalog was fixed; the dashboard kept showing the old stored
                  result, because a dashboard renders what was stored and
                  there was no way to store anything new.

                  Behind a confirm, because it REPLACES the stored analysis
                  rather than adding a version, and costs model calls. */}
              {report.status === 'processed' || report.status === 'partial' ? (
                reanalysingId === report.id ? (
                  <span className="report__confirm">
                    <span className="report__confirm-text">
                      Run {report.originalName} through the analysis again? The
                      current result is replaced, not kept alongside.
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        setReanalysingId(null);
                        onAnalyze(report.id);
                      }}
                      disabled={busyId === report.id}
                    >
                      Re-analyse
                    </button>
                    <button
                      type="button"
                      className="link"
                      onClick={() => setReanalysingId(null)}
                      disabled={busyId === report.id}
                    >
                      Cancel
                    </button>
                  </span>
                ) : (
                  <button
                    type="button"
                    className="link"
                    onClick={() => setReanalysingId(report.id)}
                    disabled={busyId === report.id}
                  >
                    {busyId === report.id
                      ? 'Analysing… this can take a few minutes'
                      : 'Re-analyse'}
                  </button>
                )
              ) : null}

              {confirmingId === report.id ? (
                <span className="report__confirm">
                  {/* NAMED, not "are you sure?". The whole point of a
                      confirmation is that the reader can tell WHICH report is
                      about to go, and what goes with it. */}
                  <span className="report__confirm-text">
                    Delete {report.originalName} and its analysis? This cannot
                    be undone.
                  </span>
                  <button
                    type="button"
                    className="danger"
                    onClick={() => onDelete(report.id)}
                    disabled={busyId === report.id}
                  >
                    {busyId === report.id ? 'Deleting…' : 'Delete permanently'}
                  </button>
                  <button
                    type="button"
                    className="link"
                    onClick={() => setConfirmingId(null)}
                    disabled={busyId === report.id}
                  >
                    Keep it
                  </button>
                </span>
              ) : (
                <button
                  type="button"
                  className="link report__delete"
                  onClick={() => setConfirmingId(report.id)}
                >
                  Delete
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
