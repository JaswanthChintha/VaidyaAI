import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../components/Icon';
import { api, ApiError } from '../lib/api';
import { joinDetails, missingKeyDetails } from '../lib/profileGaps';
import { friendlyStatus } from '../lib/friendlyErrors';
import { Absent } from '../components/Absent';
import { pageList } from '../lib/absence';
import { reportDateInfo, whyUploadDate } from '../lib/reportDates';

/**
 * The date line under a report's name. See `lib/reportDates` for which date
 * wins and why a disagreement is shown rather than settled.
 */
/** Today in the reader's own calendar, as `yyyy-mm-dd` for a date input's
    `max`. Local, not UTC: the backend allows 24 h of skew, so the reader's
    today is always accepted even where it is already tomorrow in UTC. */
function todayIso() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function ReportDate({ report }) {
  const info = reportDateInfo(report);
  if (info.source === 'typed') {
    return (
      <>
        {info.shown}
        {info.printedDisagrees ? (
          <span className="report__date-conflict">
            {' '}
            &middot; the report itself prints {info.printedDisagrees}
          </span>
        ) : (
          /* WHERE A TYPED DATE CAME FROM, SAID (2026-10-02). Test 3 read
             "9/13/2026" exactly as a date read off a document does, while
             the document prints none -- a reader had no way to tell. */
          <span className="report__uploaded">
            {' '}
            {info.printedStatus === 'absent'
              ? '(typed in; the report prints no date)'
              : '(typed in)'}
          </span>
        )}
      </>
    );
  }
  if (info.source === 'printed') {
    return (
      <>
        {info.shown} <span className="report__uploaded">(read from the report)</span>
      </>
    );
  }
  if (info.source === 'uploaded') {
    return (
      <>
        <Absent reason={whyUploadDate(info)} label="No date on the report" />{' '}
        <span className="report__uploaded">uploaded {info.shown}</span>
      </>
    );
  }
  return <Absent reason="No date was recorded for this report." label="No date" />;
}

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

/** How often a list with a report still being analysed is asked again. The
 *  list endpoint carries no rate limiter (only upload, analysis and the
 *  history routes do), and an analysis takes a minute or more.
 *  10 s -> 4 s (2026-10-04): the progress bar's later steps can pass in a few
 *  seconds, and at 10 s the reader never saw them. */
export const PROCESSING_POLL_MS = 4000;

/** How soon after an Analyse click the list is asked again, so the row turns
 *  into the progress bar instead of waiting for the whole run. */
export const ANALYSIS_FIRST_LOOK_MS = 1000;

/** The analysis steps, in the server's order (`Report.ANALYSIS_STEPS`). */
const ANALYSIS_STEP_LABEL = {
  reading: 'Reading the report',
  checking: 'Checking the values',
  deciding: 'Clinical rules and models',
  explaining: 'Writing explanations',
};
const ANALYSIS_STEP_ORDER = ['reading', 'checking', 'deciding', 'explaining'];

/** "45 s", "1 min 10 s". Never negative: two clocks can disagree slightly. */
export function elapsedText(ms) {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  if (seconds < 60) return `${seconds} s`;
  return `${Math.floor(seconds / 60)} min ${seconds % 60} s`;
}

/**
 * WHERE A RUNNING ANALYSIS HAS GOT TO (2026-10-04).
 *
 * REAL STEPS ONLY. The bar moves when the server records that a step began --
 * never a percentage that creeps forward on a timer. Reading the report is
 * usually most of the wait, so the time so far is shown to prove it is still
 * working; it ticks here, from the server's start time.
 */
function AnalysisProgress({ progress }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const current = ANALYSIS_STEP_ORDER.indexOf(progress?.step);
  const total = ANALYSIS_STEP_ORDER.length;
  const started = progress?.startedAt ? new Date(progress.startedAt).getTime() : NaN;
  const elapsed = Number.isFinite(started) ? elapsedText(now - started) : null;

  return (
    <div className="progress" role="group" aria-label="Analysis progress">
      <p className="progress__now" aria-live="polite">
        {current >= 0
          ? `Step ${current + 1} of ${total}: ${ANALYSIS_STEP_LABEL[progress.step]}`
          : 'Starting…'}
        {elapsed ? <span className="progress__time"> · {elapsed} so far</span> : null}
      </p>
      <ol className="progress__steps">
        {ANALYSIS_STEP_ORDER.map((step, index) => {
          const state = index < current ? 'done' : index === current ? 'current' : 'todo';
          return (
            <li
              key={step}
              className={`progress__step progress__step--${state}`}
              aria-current={state === 'current' ? 'step' : undefined}
            >
              <span className="progress__dot" aria-hidden="true" />
              <span className="progress__label">
                {ANALYSIS_STEP_LABEL[step]}
                {state === 'done' ? <span className="visually-hidden"> (done)</span> : null}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/*
 * WHOSE REPORT (2026-10-03). The same three fields on upload and when
 * changing it later: mine / someone else's, and for someone else an optional
 * age and sex. Blank stays unknown -- nothing is guessed, and the account
 * profile is never used for someone else's report.
 */
const SEX_OPTIONS = [
  { value: '', label: 'Not known' },
  { value: 'female', label: 'Female' },
  { value: 'male', label: 'Male' },
  { value: 'other', label: 'Other' },
];

function SubjectFields({ owner, onOwner, age, onAge, sex, onSex, idPrefix }) {
  return (
    <fieldset className="subject-fields">
      <legend>Whose report is this?</legend>
      <label className="subject-fields__choice">
        <input
          type="radio"
          name={`${idPrefix}-owner`}
          value="self"
          checked={owner === 'self'}
          onChange={() => onOwner('self')}
        />
        Mine
      </label>
      <label className="subject-fields__choice">
        <input
          type="radio"
          name={`${idPrefix}-owner`}
          value="other"
          checked={owner === 'other'}
          onChange={() => onOwner('other')}
        />
        Someone else&rsquo;s
      </label>
      {owner === 'other' ? (
        <div className="subject-fields__person">
          <label>
            Their age (optional)
            <input
              type="number"
              min="0"
              max="120"
              step="1"
              value={age}
              onChange={(e) => onAge(e.target.value)}
            />
          </label>
          <label>
            Their sex (optional)
            <select value={sex} onChange={(e) => onSex(e.target.value)}>
              {SEX_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <p className="hint">
            Your profile is not used for someone else&rsquo;s report. An age or sex
            printed on the report is used first; these fill in what it does not
            print. Their report is kept out of your timeline.
          </p>
        </div>
      ) : null}
    </fieldset>
  );
}

const describePerson = (subject) =>
  [subject?.sex && subject.sex !== 'other' ? subject.sex : null, Number.isFinite(subject?.age) ? `${subject.age}` : null]
    .filter(Boolean)
    .join(', ');

/** A report's "Whose report?" line, and its editor. */
function WhoseReport({ report, editing, onEdit, onDone, busy }) {
  const subject = report.subject || { owner: 'self' };
  const [owner, setOwner] = useState(subject.owner || 'self');
  const [age, setAge] = useState(Number.isFinite(subject.age) ? String(subject.age) : '');
  const [sex, setSex] = useState(subject.sex || '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  if (!editing) {
    return (
      <>
        {subject.owner === 'other' ? (
          <p className="report__subject">
            Someone else&rsquo;s report{describePerson(subject) ? ` (${describePerson(subject)})` : ''}
            {' '}&middot; not in your timeline
          </p>
        ) : null}
        {report.subjectChangedSinceAnalysis ? (
          <p className="report__note">
            Whose report this is was changed after it was analysed. Press
            Re-analyse to apply it &mdash; until then the results still reflect
            the previous answer.
          </p>
        ) : null}
      </>
    );
  }

  async function save(event) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.setReportSubject(report.id, { owner, age, sex });
      onDone(true);
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  return (
    <form className="report__subject-editor" onSubmit={save}>
      <SubjectFields
        idPrefix={`subject-${report.id}`}
        owner={owner}
        onOwner={setOwner}
        age={age}
        onAge={setAge}
        sex={sex}
        onSex={setSex}
      />
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
      <span className="report__confirm">
        <button type="submit" disabled={saving || busy}>
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button type="button" className="link" onClick={() => onDone(false)} disabled={saving}>
          Cancel
        </button>
      </span>
    </form>
  );
}

/**
 * Why the last analysis did not finish, in plain words (2026-10-06). The
 * machine code stays, small, so a problem report can still name it.
 */
function StatusNote({ statusMessage }) {
  const note = friendlyStatus(statusMessage);
  if (!note) return null;
  return (
    <p className="report__note">
      {note.text}
      {note.code ? <span className="report__code"> (code: {note.code})</span> : null}
    </p>
  );
}

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
  // Whose report (2026-10-03): the upload form's answer, and the row whose
  // answer is being changed.
  const [uploadOwner, setUploadOwner] = useState('self');
  const [uploadAge, setUploadAge] = useState('');
  const [uploadSex, setUploadSex] = useState('');
  const [subjectEditId, setSubjectEditId] = useState(null);

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

  // KEY PROFILE DETAILS STILL MISSING (owner, 2026-10-06): a reminder, never a
  // block. `null` = not known, and then NOTHING is shown -- a failed profile
  // request must not tell a user with a complete profile that theirs is empty.
  // A 404 is the backend's documented "no profile yet".
  const [profileGaps, setProfileGaps] = useState(null);
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const data = await api.getProfile();
        if (alive) setProfileGaps(missingKeyDetails(data.profile || data));
      } catch (err) {
        if (alive && err instanceof ApiError && err.status === 404) {
          setProfileGaps(missingKeyDetails(null));
        }
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  // A ROW THAT SAYS "Being analysed…" MUST FIND OUT WHEN IT STOPS (2026-09-25).
  // The list only refreshed when THIS page's own Analyse click returned. A
  // list loaded while an analysis was already running -- leave the page and
  // come back within the minute -- showed "Being analysed…" indefinitely:
  // 01-all-normal read that for 18 minutes after it had been stored as
  // processed. So while any row is processing, the list is asked again every
  // PROCESSING_POLL_MS, and the asking stops when none is, or the page goes.
  const anyProcessing = (reports || []).some((report) => report.status === 'processing');
  useEffect(() => {
    if (!anyProcessing) return undefined;
    const timer = setInterval(load, PROCESSING_POLL_MS);
    return () => clearInterval(timer);
  }, [anyProcessing, load]);

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
    // Whose report. Age and sex only for someone else's -- the backend refuses
    // them on one's own, where they would compete with the profile.
    form.append('subjectOwner', uploadOwner);
    if (uploadOwner === 'other') {
      if (uploadAge !== '') form.append('subjectAge', uploadAge);
      if (uploadSex) form.append('subjectSex', uploadSex);
    }

    setUploading(true);
    setError(null);
    try {
      await api.uploadReport(form);
      input.value = '';
      // The next upload starts as the reader's own again.
      setUploadOwner('self');
      setUploadAge('');
      setUploadSex('');
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
    // THE PROGRESS BAR NEVER APPEARED FOR THIS PAGE'S OWN CLICK (2026-10-05).
    // The request below takes a minute or two, and the list was only reloaded
    // when it returned -- so the row kept saying "Analysed", no progress was
    // ever asked for, and the bar showed only to someone who left and came
    // back. The server marks the report `processing` the moment it takes the
    // lock, so the list is asked again shortly after the click; from then the
    // processing poll above keeps it current. Nothing is faked here: the
    // first step shown is the one the server recorded.
    const early = setTimeout(load, ANALYSIS_FIRST_LOOK_MS);
    try {
      await api.analyzeReport(id);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      clearTimeout(early);
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
      <header className="page-hero reports-hero">
        <span className="page-hero__icon" aria-hidden="true">
          <Icon name="reports" size={26} />
        </span>
        <div className="reports-hero__text">
          <h1>Your reports</h1>
          {/* ANALYSIS IS NOT AUTOMATIC (2026-10-02): an upload waits at
              "Uploaded, not yet analysed" for its own Analyse button, and the
              old line read as though it would start by itself. */}
          <p className="hint">
            Upload a report, press <strong>Analyse</strong>, then open its
            dashboard.
          </p>
        </div>
        {/* Two counts of what is in the list below -- nothing inferred. */}
        {reports?.length ? (
          <dl className="reports-hero__stats">
            <div>
              <dt>Reports</dt>
              <dd>{reports.length}</dd>
            </div>
            <div>
              <dt>Ready to view</dt>
              <dd>
                {reports.filter((r) => r.status === 'processed' || r.status === 'partial').length}
              </dd>
            </div>
          </dl>
        ) : null}
      </header>

      {profileGaps?.length ? (
        <section className="card profile-nudge" aria-labelledby="profile-nudge-title">
          <h2 id="profile-nudge-title">Your profile is missing your {joinDetails(profileGaps)}</h2>
          <p>
            Without {profileGaps.length > 1 ? 'them' : 'it'}, some checks on your own
            reports &mdash; such as estimating kidney function &mdash; cannot be done,
            and others are less exact. The results will say what could not be
            checked; nothing is guessed.
          </p>
          <p>
            <Link to="/profile" className="button-link">
              Complete your profile
            </Link>
          </p>
        </section>
      ) : null}

      <form onSubmit={onUpload} className="card upload">
        <div className="upload__head">
          <span className="icon-disc" aria-hidden="true">
            <Icon name="upload" />
          </span>
          <div>
            <h3 className="upload__title">Upload a report</h3>
            {/* 10 MB is the backend's UPLOAD_MAX_BYTES (10485760). */}
            <p className="upload__sub">
              A PDF or a clear photo of a blood test report, up to 10 MB.
            </p>
          </div>
        </div>
        <div className="upload__fields">
          <label className="upload__file">
            PDF, JPEG or PNG
            {/* The browser's own "Please select a file" bubble is easy to
                miss and says nothing about this form; this is said instead. */}
            <input
              type="file"
              name="report"
              accept=".pdf,.jpg,.jpeg,.png"
              required
              onInvalid={(e) => e.target.setCustomValidity('Choose a report file to upload first.')}
              onChange={(e) => e.target.setCustomValidity('')}
            />
          </label>
          <label>
            Date printed on the report (optional)
            {/* No future dates: the backend refuses them ("Report date cannot
                be in the future"), but only after the file has been sent. */}
            <input type="date" name="reportDate" min="1900-01-01" max={todayIso()} />
            <span className="hint">
              Used to order your timeline. Leave blank and the date printed on
              the report is used, if it can be read; otherwise the day you
              upload it.
            </span>
          </label>
        </div>
        <SubjectFields
          idPrefix="upload"
          owner={uploadOwner}
          onOwner={setUploadOwner}
          age={uploadAge}
          onAge={setUploadAge}
          sex={uploadSex}
          onSex={setUploadSex}
        />
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

      {reports?.length ? (
        <h2 className="reports__heading">
          Your uploaded reports
          <span className="disclosure__count">{reports.length}</span>
        </h2>
      ) : null}
      <ul className="report-list">
        {(reports || []).map((report) => (
          <li key={report.id} className="card report">
            <div className="report__head">
              <span className="report__icon" aria-hidden="true">
                <Icon name="reports" />
              </span>
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
            {report.status === 'processing' ? (
              <>
                <AnalysisProgress progress={report.analysisProgress} />
                <p className="report__note">
                  This page updates by itself when the analysis finishes.
                </p>
              </>
            ) : null}
            {/* THE DATE ON THE REPORT, OR THE DAY IT WAS UPLOADED -- SAID.

                This printed `chronoDate` bare. `chronoDate` is
                `reportDate ?? uploadedAt`, so when the optional date field is
                left blank it IS the upload clock -- and the row showed it
                exactly as it shows a date somebody read off their document.
                A report printed 13 September, uploaded on the 19th, read
                `9/19/2026`.

                THE `Absent` BRANCH BELOW COULD NEVER FIRE, which is the tell.
                `chronoDate` is `required: true` on the schema and always
                falls back, so the honest state this component was written to
                show was unreachable. It is reachable now, off `reportDate`,
                which is null exactly when nobody gave one.

                2026-09-24: AND THE DOCUMENT'S OWN DATE NOW COUNTS. It is used
                when nothing was typed, and shown beside a typed date that
                disagrees with it -- see `ReportDate` above. */}
            <p className="report__meta">
              <ReportDate report={report} />
            </p>
            <WhoseReport
              // Remounted per edit so the editor starts from the stored answer.
              key={`${report.id}-${subjectEditId === report.id}`}
              report={report}
              editing={subjectEditId === report.id}
              busy={busyId === report.id}
              onDone={async (saved) => {
                setSubjectEditId(null);
                if (saved) await load();
              }}
            />
            <StatusNote statusMessage={report.statusMessage} />
            {/* A PAGE THE ANALYSIS COULD NOT READ (2026-10-10). Test 3's page 2
                was skipped while the reading service was down and nothing on
                this list said so; the report simply looked short and clear. */}
            {(report.status === 'processed' || report.status === 'partial') &&
            report.pagesUnreadable?.length ? (
              <p className="report__note report__unreadable" role="note">
                {pageList(report.pagesUnreadable)} could not be read, so the tests on{' '}
                {report.pagesUnreadable.length === 1 ? 'it' : 'them'} were not checked. Press
                Re-analyse to try again.
              </p>
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

              {subjectEditId === report.id ? null : (
                <button
                  type="button"
                  className="link"
                  onClick={() => setSubjectEditId(report.id)}
                  disabled={busyId === report.id}
                >
                  Whose report?
                </button>
              )}

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
