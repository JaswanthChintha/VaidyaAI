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
              <strong>{report.originalName}</strong>
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
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
