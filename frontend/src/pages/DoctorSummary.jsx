import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, ApiError } from '../lib/api';
import { Absent, Section, Value } from '../components/Absent';
import { isPresent } from '../lib/absence';

/**
 * Module 32 -- the summary a patient hands to a clinician.
 *
 * ==========================================================================
 * A CLINICIAN MAY ACT ON THIS PAGE
 * ==========================================================================
 *
 * That makes it a HIGHER-stakes surface than the patient dashboard, not a
 * lower one, and it changes what the rendering rules have to protect:
 *
 *   EVERY MODEL ESTIMATE TRAVELS WITH THAT MODEL'S LIMITS. Module 11 has
 *   ROC-AUC 0.697 and flags about 27% of true positives at its operating
 *   threshold -- an unflagged heart result from it rules NOTHING out. A
 *   probability shown without that is actively misleading, and this was a
 *   real defect twice: the recall never left the metrics artifact (6o D8),
 *   and then the fix was applied to two models out of three (6p). So the
 *   caveats are rendered with the probability, in the same block, never
 *   behind a toggle.
 *
 *   `metrics_absent_code` IS SHOWN. A record with figures but no operating
 *   point is not a complete record, and a clinician reading ROC-AUC alone
 *   would reasonably assume the missing numbers were unremarkable.
 *
 *   TRENDS AND COMPARISON ARE OPTIONAL SECTIONS. With one report they are
 *   absent WITH A STATED REASON. If the report this summary describes is not
 *   in the history behind it, the service refuses both with
 *   SUBJECT_NOT_IN_HISTORY rather than attributing another report's trend to
 *   this one -- and that refusal must reach the page, not be swallowed.
 *
 * The document generates no prose. Everything below is assembled from
 * already-validated structures, and every sentence originates in a reviewed
 * template on the service side.
 */

function ModelLimits({ limits }) {
  if (!limits) return null;

  return (
    <div className="limits">
      {limits.metrics_available === true ? (
        <ul className="limits__figures">
          {isPresent(limits.roc_auc) ? <li>ROC-AUC {limits.roc_auc}</li> : null}
          <li>
            Detection at the operating threshold:{' '}
            <Value
              value={limits.recall_at_operating_threshold}
              reason="Not recorded for this model."
            />
          </li>
          <li>
            Precision at that threshold:{' '}
            <Value
              value={limits.precision_at_operating_threshold}
              reason="Not recorded for this model."
            />
          </li>
          {isPresent(limits.accuracy) ? (
            <li>
              Accuracy {limits.accuracy}
              {isPresent(limits.baseline_accuracy)
                ? ` against a majority-class baseline of ${limits.baseline_accuracy}`
                : ''}
            </li>
          ) : null}
        </ul>
      ) : (
        <Absent
          label="No performance figures"
          reason="No recorded performance accompanied this model's output."
        />
      )}

      {/* A partial record must not read as a complete one. */}
      {isPresent(limits.metrics_absent_code) ? (
        <p className="caveat">
          Incomplete performance record: <code>{limits.metrics_absent_code}</code>
        </p>
      ) : null}

      {limits.caveats?.length ? (
        <ul className="limits__caveats">
          {limits.caveats.map((caveat, index) => (
            <li key={index}>{caveat}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function Assessment({ assessment }) {
  const assessed = assessment.assessed !== false;

  return (
    <li className="card assessment">
      <div className="condition__head">
        <strong>{assessment.condition}</strong>
        <span>{assessment.status}</span>
      </div>

      {assessment.reading_note ? (
        <p className="hint">{assessment.reading_note}</p>
      ) : null}

      {/* Module 16 stamps the basis so a risk-factor tally and a model
          probability are shown separately rather than averaged. */}
      {assessment.basis_conflict === true && assessment.basis_note ? (
        <p className="caveat">{assessment.basis_note}</p>
      ) : null}

      {assessment.bases?.length ? (
        <div className="bases">
          {assessment.bases.map((basis, index) => (
            <div key={index} className="basis">
              <p className="basis__head">
                <strong>{basis.source || basis.assessment_basis}</strong>
                {isPresent(basis.status) ? ` — ${basis.status}` : ''}
              </p>
              {basis.what_this_source_answered ? (
                <p className="hint">{basis.what_this_source_answered}</p>
              ) : null}
              {basis.rule?.rule_ids?.length ? (
                <p className="hint">Rules: {basis.rule.rule_ids.join(', ')}</p>
              ) : null}
              {basis.ml ? (
                <>
                  <p className="hint">
                    {basis.ml.model_name}
                    {isPresent(basis.ml.probability)
                      ? ` — probability ${basis.ml.probability}`
                      : ''}
                  </p>
                  <ModelLimits limits={basis.limitations} />
                </>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <Absent
          reason={
            assessed
              ? 'No contributing source was recorded for this assessment.'
              : 'This condition was not assessed.'
          }
        />
      )}
    </li>
  );
}

export default function DoctorSummary() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const result = await api.getDoctorSummary(id);
        if (!cancelled) setData(result);
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (error) return <p className="error" role="alert">{error}</p>;
  if (!data) return <p className="loading">Preparing the clinical summary…</p>;

  const summary = data.doctorSummary;
  const history = data.history;

  return (
    <main className="doctor-summary">
      <p className="crumbs">
        <Link to={`/reports/${id}`}>Dashboard</Link> · Clinical summary
      </p>

      <h1>Summary for a healthcare professional</h1>

      {summary?.purpose?.is_not?.length ? (
        <p className="hint">{summary.purpose.is_not.join(' ')}</p>
      ) : null}

      {/* The report this summary describes must be IN the history behind it.
          When it is not, the service refuses the trend and comparison
          sections and this states why rather than leaving a silent gap. */}
      {history && history.subjectInHistory === false ? (
        <p className="caveat">
          This report is not among the reports used for the trend and
          comparison sections below, so those sections were withheld.
        </p>
      ) : null}

      <section className="card">
        <h2>Overall</h2>
        <p>
          <strong>{summary?.overall?.status_label || 'Not assessed'}</strong>
        </p>
        {summary?.overall?.assessment_reading ? (
          <p>{summary.overall.assessment_reading}</p>
        ) : null}
        {summary?.overall?.clean_bill_of_health === false ? (
          <p className="caveat">
            This is not a clean bill of health. An absent assessment is not a
            normal result.
          </p>
        ) : null}
      </section>

      <h2>Assessments</h2>
      {summary?.assessments?.length ? (
        <ul className="assessment-list">
          {summary.assessments.map((assessment) => (
            <Assessment key={assessment.condition} assessment={assessment} />
          ))}
        </ul>
      ) : (
        <p className="empty">No conditions were assessed.</p>
      )}

      {summary?.unassessed_conditions?.length ? (
        <p className="caveat">
          Not assessed: {summary.unassessed_conditions.join(', ')}. These are
          open questions, not negative results.
        </p>
      ) : null}

      <Section status={summary?.trends} title="Trends">
        <p className="hint">
          {summary?.trend_data?.summary
            ? `${summary.trend_data.summary.improving} improving, ${summary.trend_data.summary.worsening} worsening, ${summary.trend_data.summary.stable} stable.`
            : null}
        </p>
      </Section>

      <Section status={summary?.comparison} title="Comparison with a previous report">
        <p className="hint">
          {summary?.comparison_data?.summary?.headline || null}
        </p>
      </Section>

      <Section status={summary?.knowledge} title="Retrieved reference information">
        <ul>
          {(summary?.knowledge?.references || []).map((reference, index) => (
            <li key={index}>
              {reference.title || reference.doc_id}
              {reference.last_reviewed ? (
                <span className="hint"> (reviewed {reference.last_reviewed})</span>
              ) : null}
            </li>
          ))}
        </ul>
      </Section>

      {summary?.warnings?.length ? (
        <>
          <h2>Notes</h2>
          <ul className="warnings">
            {summary.warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </>
      ) : null}

      {summary?.disclaimer ? <p className="hint">{summary.disclaimer}</p> : null}
    </main>
  );
}
