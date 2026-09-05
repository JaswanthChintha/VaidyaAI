import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { api, ApiError } from '../lib/api';
import { Absent, Risk, Value } from '../components/Absent';
import { isPresent } from '../lib/absence';

/**
 * Module 27 -- the health dashboard.
 *
 * ==========================================================================
 * THIS IS THE SCREEN THE ABSENCE PRIMITIVES EXIST FOR
 * ==========================================================================
 *
 * A dashboard has a box for every value, and a box has to show SOMETHING.
 * That pressure is what turns an absence into a value, and every failure of
 * that kind found on this project so far has been one hop from a screen like
 * this one. The specific ones this component must not commit:
 *
 *   `status: null` + `anyAssessed: false` IS NOT "Healthy". It is Module 18's
 *   fourth case -- nothing could be assessed -- and the difference between
 *   "we looked and it was fine" and "we could not look" is the difference
 *   between reassurance and a lie.
 *
 *   `statusLabel` has FIVE values, not four. `Healthy (partial assessment)`
 *   exists precisely because a partial clean result was otherwise
 *   byte-identical to a full one, and an audit found the backend flattening
 *   it to "Healthy" right up until it was fixed. So the LABEL is printed,
 *   never the status.
 *
 *   A missing risk is NOT low risk. `INSUFFICIENT_DATA` carries no risk, and
 *   the `Risk` component has no way to express otherwise.
 *
 *   A rejected reading is NOT a zero, and is NOT the same as a reading that
 *   was never on the report. Both are absences; they are different absences,
 *   and the laboratory card says which.
 *
 * Every value below goes through `Value`, `Risk` or `Absent`. There is no
 * bare `{x}` on a clinical field and no `||` anywhere in this file.
 */

function OverallCard({ overall }) {
  if (!overall) return null;
  const assessed = overall.anyAssessed === true;

  return (
    <section className="card overall">
      <h2>Overall</h2>

      <p className="overall__status">
        {/* The LABEL, never the status: the label is the five-valued one. */}
        {isPresent(overall.statusLabel) ? (
          <strong>{overall.statusLabel}</strong>
        ) : (
          <Absent
            label="Not assessed"
            reason="No overall status was established for this report."
          />
        )}
      </p>

      <p>
        Overall risk: <Risk risk={overall.risk} assessed={assessed} />
      </p>

      {/* `complete: false` is a real fact and is stated, not hidden. */}
      {overall.complete === false ? (
        <p className="caveat">
          This assessment is incomplete
          {isPresent(overall.unassessedConditionCount) &&
          overall.unassessedConditionCount > 0
            ? ` — ${overall.unassessedConditionCount} condition(s) could not be assessed`
            : ''}
          .
        </p>
      ) : null}

      {isPresent(overall.caveat) ? <p className="caveat">{overall.caveat}</p> : null}

      {overall.unassessedConditions?.length ? (
        <p className="hint">
          Not assessed: {overall.unassessedConditions.join(', ')}. An
          unassessed condition is an open question, not a negative result.
        </p>
      ) : null}

      {overall.sourcesFailed?.length ? (
        <p className="caveat">
          Some analysis stages did not complete: {overall.sourcesFailed.join(', ')}.
        </p>
      ) : null}
    </section>
  );
}

function ConditionCard({ card }) {
  const assessed = card.assessed !== false;

  return (
    <li className="card condition">
      <div className="condition__head">
        <strong>{card.condition}</strong>
        <Risk
          risk={card.risk}
          assessed={assessed}
          reason={
            assessed
              ? 'No risk level was established for this condition.'
              : 'This condition was not assessed, so it carries no risk level.'
          }
        />
      </div>

      <p className="condition__status">
        {isPresent(card.status) ? (
          card.status
        ) : (
          <Absent reason="No decision was reached for this condition." />
        )}
      </p>

      {/* A model that declined to predict is not a low probability. */}
      {assessed && isPresent(card.confidence) ? (
        <p className="hint">
          Model probability: <Value value={card.confidence} />
          {isPresent(card.confidenceBasis) ? ` (${card.confidenceBasis})` : ''}
        </p>
      ) : null}

      {card.partiallyAssessed === true ? (
        <p className="caveat">
          Only some sources assessed this condition
          {card.unassessedSources?.length
            ? ` — no answer from: ${card.unassessedSources.join(', ')}`
            : ''}
          .
        </p>
      ) : null}

      {/* Module 16 stamps this so a risk-factor tally and a model probability
          are shown side by side rather than averaged into one figure. */}
      {card.basisConflict === true ? (
        <p className="caveat">
          {isPresent(card.basisNote)
            ? card.basisNote
            : 'This condition was assessed in two different ways, which answer different questions.'}
        </p>
      ) : null}

      {card.sources?.length ? (
        <p className="hint">Based on: {card.sources.join(', ')}</p>
      ) : null}
    </li>
  );
}

/** The four laboratory states, each rendered as the distinct fact it is. */
function LabRow({ row }) {
  const usable = row.usable === true;

  return (
    <tr className={`lab lab--${row.state || 'unknown'}`}>
      <th scope="row">
        {isPresent(row.displayName) ? row.displayName : row.feature}
        {isPresent(row.originalTestName) && row.originalTestName !== row.displayName ? (
          <span className="lab__printed"> (printed as “{row.originalTestName}”)</span>
        ) : null}
      </th>

      <td>
        <Value
          value={row.value}
          unit={row.unit}
          available={usable}
          reason={
            isPresent(row.rejectionReason)
              ? row.rejectionReason
              : isPresent(row.availabilityExplanation)
                ? row.availabilityExplanation
                : undefined
          }
          label={row.state === 'rejected' ? 'Not usable' : undefined}
        />
      </td>

      <td className="lab__range">
        {isPresent(row.referenceLow) || isPresent(row.referenceHigh) ? (
          <span>
            {isPresent(row.referenceLow) ? row.referenceLow : '—'} to{' '}
            {isPresent(row.referenceHigh) ? row.referenceHigh : '—'}
            {isPresent(row.unit) ? ` ${row.unit}` : ''}
          </span>
        ) : (
          <Absent
            label="No range printed"
            reason="The laboratory did not print a reference interval for this test."
          />
        )}
      </td>

      <td>
        {isPresent(row.flag) ? (
          <span className={`flag flag--${row.flag}`}>{row.flag}</span>
        ) : (
          <span className="absent">—</span>
        )}
      </td>
    </tr>
  );
}

export default function Dashboard() {
  const { id } = useParams();
  const [dashboard, setDashboard] = useState(null);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const [notAnalysed, setNotAnalysed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await api.getDashboard(id);
        if (cancelled) return;
        setDashboard(data.dashboard);
        setReport(data.report);
      } catch (err) {
        if (cancelled) return;
        // 404 here means "not analysed yet", which the backend states rather
        // than returning an empty dashboard that would read as "all clear".
        if (err instanceof ApiError && err.status === 404) {
          setNotAnalysed(true);
          setError(err.message);
        } else {
          setError(err.message);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (error && notAnalysed) {
    return (
      <main>
        <p className="empty">{error}</p>
        <Link to="/reports">Back to your reports</Link>
      </main>
    );
  }
  if (error) return <p className="error" role="alert">{error}</p>;
  if (!dashboard) return <p className="loading">Loading your dashboard…</p>;

  const labs = dashboard.laboratory || [];
  const recommendations = dashboard.recommendations || {};

  return (
    <main className="dashboard">
      <p className="crumbs">
        <Link to="/reports">Reports</Link> ·{' '}
        {report?.originalName || 'This report'}
      </p>

      <OverallCard overall={dashboard.overall} />

      <h2>Conditions</h2>
      {dashboard.conditions?.length ? (
        <ul className="condition-list">
          {dashboard.conditions.map((card) => (
            <ConditionCard key={card.condition} card={card} />
          ))}
        </ul>
      ) : (
        <p className="empty">No conditions were assessed for this report.</p>
      )}

      <h2>Laboratory values</h2>
      {labs.length ? (
        <table className="lab-table">
          <thead>
            <tr>
              <th scope="col">Test</th>
              <th scope="col">Result</th>
              <th scope="col">Reference interval</th>
              <th scope="col">Flag</th>
            </tr>
          </thead>
          <tbody>
            {labs.map((row) => (
              <LabRow key={`${row.feature}-${row.state}`} row={row} />
            ))}
          </tbody>
        </table>
      ) : (
        <p className="empty">No laboratory values were read from this report.</p>
      )}

      <h2>Guidance</h2>
      {recommendations.guidance?.available === true &&
      recommendations.guidance.items?.length ? (
        <ul className="guidance">
          {recommendations.guidance.items.map((item, index) => (
            <li key={item.code || index}>{item.text || item.title}</li>
          ))}
        </ul>
      ) : (
        <p className="empty">
          No educational guidance accompanied this report.
        </p>
      )}

      <p className="hint">
        Guidance here is reviewed educational material selected by code. It is
        not generated, and it is not personalised treatment advice.
      </p>

      {dashboard.warnings?.length ? (
        <>
          <h2>Notes from the analysis</h2>
          <ul className="warnings">
            {dashboard.warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </>
      ) : null}
    </main>
  );
}
