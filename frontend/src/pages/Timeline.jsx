import { useEffect, useState } from 'react';
import { api } from '../lib/api';
import { Absent, Value, WarningList } from '../components/Absent';
import { isPresent } from '../lib/absence';

/**
 * Modules 28, 29 and 30 -- trends, comparison and the progress score.
 *
 * ==========================================================================
 * THE WORD THIS SCREEN MUST NEVER PRINT WITHOUT EARNING
 * ==========================================================================
 *
 * "Stable". Module 28 reserves it for a change measured against a declared
 * stability band -- a reference change value, not a round percentage. Fewer
 * than two usable readings is `INSUFFICIENT_DATA` with `trend: null`, and
 * rendering that as "stable", "no change" or a flat line states something
 * nobody measured. It is the single most repeated hazard on this project and
 * it would be trivially easy to commit here, because a timeline with nothing
 * on it looks like a timeline that did not move.
 *
 * So `outcome` is what this screen branches on, never `trend`. Every refusal
 * outcome carries its own sentence from the service, and those sentences are
 * shown rather than replaced with a friendlier summary -- they are the
 * product, not an error path.
 *
 * ==========================================================================
 * THE HISTORY BLOCK IS SHOWN, NOT HIDDEN
 * ==========================================================================
 *
 * A timeline built from two of a patient's nine reports and a timeline built
 * from a patient's only two reports look identical unless the accounting is
 * on screen. `considered`, `included`, `excludedCount` and `droppedByCap` are
 * rendered for exactly that reason -- the backend added `droppedByCap`
 * because an audit found five reports falling into neither bucket when the
 * cap engaged.
 */

function HistorySummary({ history }) {
  if (!history) return null;
  const dropped = history.droppedByCap;

  return (
    <p className="history">
      Built from <strong>{history.included}</strong> of{' '}
      <strong>{history.considered}</strong> report(s).
      {isPresent(history.excludedCount) && history.excludedCount > 0 ? (
        <> {history.excludedCount} could not contribute.</>
      ) : null}
      {isPresent(dropped) && dropped > 0 ? (
        <>
          {' '}
          {dropped} older report(s) fell outside the most recent{' '}
          {history.cap} and were not included.
        </>
      ) : null}
    </p>
  );
}

/** One feature's trajectory, or the stated reason there isn't one. */
function TrendRow({ trend }) {
  const classified = trend.outcome === 'TREND_CLASSIFIED';

  return (
    <tr>
      <th scope="row">{trend.feature}</th>
      <td>
        {classified && isPresent(trend.trend) ? (
          <span className={`trend trend--${trend.trend}`}>{trend.trend}</span>
        ) : (
          // NOT "stable". The service's own sentence says why there is no
          // trend, and it is shown verbatim.
          <Absent
            label="No trend"
            reason={trend.reason || 'Not enough usable readings to describe a change.'}
          />
        )}
      </td>
      <td>
        {classified && trend.change ? (
          <>
            <Value value={trend.change.first_value} unit={trend.canonical_unit} />
            {' → '}
            <Value value={trend.change.last_value} unit={trend.canonical_unit} />
          </>
        ) : (
          <span className="absent">—</span>
        )}
      </td>
      <td className="hint">
        {trend.usable_point_count} usable reading(s)
        {trend.gaps?.length ? `, ${trend.gaps.length} gap(s)` : ''}
      </td>
    </tr>
  );
}

function Trends({ data, history }) {
  const features = data?.features ? Object.values(data.features) : [];
  const summary = data?.summary;

  return (
    <section className="card">
      <h2>Trends over time</h2>
      <HistorySummary history={history} />

      {summary ? (
        <p className="hint">
          {summary.improving} improving · {summary.worsening} worsening ·{' '}
          {summary.stable} stable · {summary.not_determinable} not determinable
        </p>
      ) : null}

      {features.length ? (
        <table className="lab-table">
          <thead>
            <tr>
              <th scope="col">Parameter</th>
              <th scope="col">Direction</th>
              <th scope="col">First → latest</th>
              <th scope="col">Readings</th>
            </tr>
          </thead>
          <tbody>
            {features.map((trend) => (
              <TrendRow key={trend.feature} trend={trend} />
            ))}
          </tbody>
        </table>
      ) : (
        <p className="empty">
          No parameters could be followed across your reports yet.
        </p>
      )}

      {data?.disclaimer ? <p className="hint">{data.disclaimer}</p> : null}
    </section>
  );
}

/** The spec's Parameter / Previous / Current / Trend table. */
function Comparison({ data }) {
  const rows = data?.table || [];

  return (
    <section className="card">
      <h2>Comparing two reports</h2>

      {data?.pair ? (
        <p className="hint">
          Comparing the report of{' '}
          {new Date(data.pair.baseline_date || data.pair.baseline?.date).toLocaleDateString()}{' '}
          with {new Date(data.pair.comparison_date || data.pair.comparison?.date).toLocaleDateString()}
          {data.pair.chronological === false
            ? ' — these were given out of date order, so the direction of every change is reversed.'
            : ''}
          .
        </p>
      ) : null}

      {rows.length ? (
        <table className="lab-table">
          <thead>
            <tr>
              <th scope="col">Parameter</th>
              <th scope="col">Previous</th>
              <th scope="col">Current</th>
              <th scope="col">Change</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.feature}>
                <th scope="row">{row.description || row.feature}</th>
                <td>
                  <Value
                    value={row.previous}
                    unit={row.unit}
                    reason="This parameter was not on the earlier report."
                  />
                </td>
                <td>
                  <Value
                    value={row.current}
                    unit={row.unit}
                    reason="This parameter was not on the later report."
                  />
                </td>
                <td>
                  {isPresent(row.category) ? (
                    <span className={`category category--${row.category}`}>
                      {isPresent(row.symbol) ? `${row.symbol} ` : ''}
                      {row.category.replace(/_/g, ' ')}
                    </span>
                  ) : (
                    <Absent
                      label="Not classifiable"
                      reason="This parameter could not be compared across the two reports."
                    />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="empty">Nothing could be compared between these reports.</p>
      )}

      {data?.summary?.headline ? <p>{data.summary.headline}</p> : null}
      {data?.warnings?.length ? (
        <WarningList warnings={data.warnings} />
      ) : null}
    </section>
  );
}

/** Module 30. A refusal here is `score: null`, and it is shown as one. */
function Progress({ data }) {
  const computed = data?.outcome === 'SCORE_COMPUTED';

  return (
    <section className="card">
      <h2>Progress score</h2>

      {computed && isPresent(data.score) ? (
        <>
          <p className="progress__score">
            <strong>{data.score}</strong>
            <span className="hint"> / 100</span>
          </p>
          {data.band ? (
            <p>
              <strong>{data.band.label}</strong>
              {data.band.description ? (
                <span className="hint"> {data.band.description}</span>
              ) : null}
            </p>
          ) : null}
          {data.scale ? (
            <p className="hint">
              Higher is better. {data.scale.direction_text}
            </p>
          ) : null}
        </>
      ) : (
        // No score is a real answer, and the reason is the service's own.
        <Absent
          label="No score"
          reason={
            data?.summary?.headline ||
            'There was not enough comparable data to calculate a progress score.'
          }
        />
      )}

      {data?.coverage ? (
        <p className="hint">
          Based on {data.coverage.contributing_count} of{' '}
          {data.coverage.features_examined} parameter(s) examined
          {data.coverage.excluded_count > 0
            ? `; ${data.coverage.excluded_count} could not be placed on the scale`
            : ''}
          . At least {data.coverage.minimum_required} are needed for a score.
        </p>
      ) : null}

      {data?.warnings?.length ? (
        <WarningList warnings={data.warnings} />
      ) : null}

      {data?.what_this_is_not ? (
        <p className="hint">{data.what_this_is_not}</p>
      ) : null}
    </section>
  );
}

export default function Timeline() {
  const [state, setState] = useState({ loading: true });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // Three independent calls: one failing must not blank the other two.
        const [trends, comparison, progress] = await Promise.allSettled([
          api.getTrends(),
          api.getComparison(),
          api.getProgress(),
        ]);
        if (cancelled) return;
        setState({
          loading: false,
          trends: trends.status === 'fulfilled' ? trends.value : null,
          trendsError: trends.status === 'rejected' ? trends.reason.message : null,
          comparison: comparison.status === 'fulfilled' ? comparison.value : null,
          comparisonError:
            comparison.status === 'rejected' ? comparison.reason.message : null,
          progress: progress.status === 'fulfilled' ? progress.value : null,
          progressError: progress.status === 'rejected' ? progress.reason.message : null,
        });
      } catch (err) {
        if (!cancelled) setState({ loading: false, error: err.message });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.loading) return <p className="loading">Loading your timeline…</p>;
  if (state.error) return <p className="error" role="alert">{state.error}</p>;

  return (
    <main className="timeline">
      <h1>Your timeline</h1>
      <p className="hint">
        These views describe how measured values changed between your reports.
        They report arithmetic and a declared direction of change &mdash; they
        do not interpret those changes or identify any condition.
      </p>

      {state.trendsError ? (
        <p className="error" role="alert">{state.trendsError}</p>
      ) : (
        <Trends data={state.trends?.trends} history={state.trends?.history} />
      )}

      {state.comparisonError ? (
        <p className="error" role="alert">{state.comparisonError}</p>
      ) : (
        <Comparison data={state.comparison?.comparison} />
      )}

      {state.progressError ? (
        <p className="error" role="alert">{state.progressError}</p>
      ) : (
        <Progress data={state.progress?.progress} />
      )}
    </main>
  );
}
