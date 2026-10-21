import { useEffect, useRef, useState } from 'react';
import Icon from '../components/Icon';
import { api } from '../lib/api';
import { Absent, Value, WarningList } from '../components/Absent';
import TrendChart from '../components/TrendChart';
import { PATIENT_LABEL } from '../lib/labels';
import { isPresent } from '../lib/absence';
import { reportDateInfo } from '../lib/reportDates';
import { PairIdentityNotice } from '../components/IdentityNotice';
import { readableName } from '../lib/displayName';


function HistorySummary({ history }) {
  if (!history) return null;
  const dropped = history.droppedByCap;
  const someoneElse = (history.excluded || []).filter((r) => r?.reasonCode === 'SOMEONE_ELSE').length;
  const otherExcluded = isPresent(history.excludedCount)
    ? Math.max(0, history.excludedCount - someoneElse)
    : null;

  return (
    <p className="history">
      Built from <strong>{history.included}</strong> of{' '}
      <strong>{history.considered}</strong> report(s).
      {someoneElse > 0 ? (
        <>
          {' '}
          {someoneElse} report{someoneElse === 1 ? ' is' : 's are'} marked as someone
          else&rsquo;s and {someoneElse === 1 ? 'is' : 'are'} not included.
        </>
      ) : null}
      {otherExcluded ? <> {otherExcluded} could not contribute.</> : null}
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


function ChangePair({ from, to, unit }) {
  if (!isPresent(from) || !isPresent(to)) return null;
  return (
    <span className="disclosure__pair">
      <Value value={from} />
      {' → '}
      <Value value={to} unit={unit} />
    </span>
  );
}

const NOT_A_TRAJECTORY = new Set(['NOT_TRENDABLE', 'NOT_NUMERIC']);

function noDirectionWord(trend) {
  if (trend.outcome === 'NOT_COMPARABLE_SAMPLE_TIMING') {
    const timings = [
      ...new Set((trend.points || []).map((p) => p.sample_timing).filter(isPresent)),
    ];
    return timings.length === 2 ? `${timings[0]} vs ${timings[1]}` : 'not comparable';
  }
  if (trend.outcome === 'INSUFFICIENT_DATA' && (trend.points || []).length === 1) {
    return 'one report only';
  }
  return 'no direction';
}

const PERSON_DETAILS = new Set(['age', 'gender', 'smoking_history']);

function chartPropsFor(trend) {
  const polarity = trend.polarity || {};
  const band = { low: polarity.optimal_low, high: polarity.optimal_high };

  return {
    label: PATIENT_LABEL[trend.feature] || trend.feature,
    unit: trend.canonical_unit,
    points: (trend.points || []).map((point) => ({
      date: point.date,
      value: point.value,
      unit: point.unit,
      questionable: point.questionable === true,
    })),
    gaps: (trend.gaps || []).map((gap) => ({
      date: gap.date,
      kind: gap.availability,
      reason: gap.reason,
    })),
    band,
    classified: trend.outcome === 'TREND_CLASSIFIED',
    trend: trend.trend,
    stability: trend.stability || null,
    baseline: trend.change ? trend.change.first_value : null,
  };
}

function readingDate(value) {
  const date = value ? new Date(value) : null;
  return date && !Number.isNaN(date.getTime()) ? date.toLocaleDateString() : 'undated';
}

const MOVEMENT_WORD = { rose: 'rose', fell: 'fell', same: 'no change' };
const LAB_FLAG_WORD = { high: 'High', low: 'Low', critical: 'High', normal: 'In range' };

const TREND_WORDS = ['improving', 'worsening', 'stable'];

function noLineWord(panel) {
  if (panel.blocked) return 'units differ';
  if ((panel.rows || []).length === 1) return 'one report only';
  return 'not a number';
}

const PRINTED_RANGE_SENTENCE = {
  high: 'Above the range printed on the report.',
  critical: 'Above the range printed on the report.',
  low: 'Below the range printed on the report.',
  normal: 'Within the range printed on the report.',
};

function LabStatus({ movement, latestFlag, trend, classified }) {
  const declared = panelTrendWord({ classified, trend }) !== null;

  const moved = declared ? null : movement ? MOVEMENT_WORD[movement] : null;
  const flag = latestFlag ? LAB_FLAG_WORD[latestFlag] : null;
  if (!declared && !moved && !flag) return null;

  return (
    <span className="lab-status">
      {declared ? <span className={`trend trend--${trend}`}>{trend}</span> : null}
      {moved ? <span className="lab-status__move">{moved}</span> : null}
      {flag ? (
        <span
          className={`lab-status__flag lab-status__flag--${latestFlag}`}
          title="The latest reading against the range printed on that laboratory report"
        >
          {flag}
        </span>
      ) : null}
    </span>
  );
}

function labPanelsOf(data) {
  const series = data?.series || [];
  const readings = data?.readings || [];

  const panels = [
    ...series.map((entry) =>
      entry.blocked
        ? {
            key: entry.key,
            name: entry.name,
            rows: entry.points.map((p) => ({
              date: p.date,
              valueRaw: p.value,
              unit: p.unit,
            })),
            movement: entry.movement,
            blocked: true,
            latestFlag: entry.latestFlag,
            joinedFrom: entry.joinedFrom,
          }
        : {
            key: entry.key,
            name: entry.name,
            chart: entry,
            movement: entry.movement,
            latestFlag: entry.latestFlag,
            trend: entry.trend,
            classified: entry.classified,
            joinedFrom: entry.joinedFrom,
            unitEquivalence: entry.unitEquivalence,
            unitAssumed: entry.unitAssumed,
            significantChangePct: entry.significantChangePct,
            trendSource: entry.trendSource,
            trendVerified: entry.trendVerified,
          }
    ),
    ...readings.map((entry) => ({
      key: entry.key,
      name: entry.name,
      rows: entry.rows,
      movement: null,
      latestFlag: entry.latestFlag,
      joinedFrom: entry.joinedFrom,
      restates: entry.restates,
    })),
  ];

  return panels;
}

function panelTrendWord(panel) {
  return panel && panel.classified === true && TREND_WORDS.includes(panel.trend)
    ? panel.trend
    : null;
}

function featureTrendWord(trend) {
  return trend &&
    trend.outcome === 'TREND_CLASSIFIED' &&
    isPresent(trend.trend) &&
    TREND_WORDS.includes(trend.trend)
    ? trend.trend
    : null;
}

function cardTally(charted, labPanels) {
  const counts = { improving: 0, worsening: 0, stable: 0, undirected: 0 };
  const add = (word) => {
    if (word && counts[word] !== undefined) counts[word] += 1;
    else counts.undirected += 1;
  };
  for (const trend of charted) add(featureTrendWord(trend));
  for (const panel of labPanels) add(panelTrendWord(panel));
  return { ...counts, total: charted.length + labPanels.length };
}

function provenanceNote(labPanels) {
  let uncheckedTable = false;
  let fromModel = false;
  let uncheckedEquivalence = false;

  for (const panel of labPanels) {
    if (panelTrendWord(panel) && isPresent(panel.significantChangePct)) {
      if (panel.trendSource === 'table') {
        if (panel.trendVerified !== true) uncheckedTable = true;
      } else {
        fromModel = true;
      }
    }
    if (panel.unitEquivalence && !panel.unitEquivalence.verified) {
      uncheckedEquivalence = true;
    }
  }

  const unchecked = [];
  if (uncheckedTable || fromModel) unchecked.push('change thresholds');
  if (uncheckedEquivalence) unchecked.push('unit equivalences');
  if (!unchecked.length) return null;

  return (
    <>
      The {unchecked.join(' and ')} used here have not been checked against a
      published source.
      {fromModel
        ? ' Some were produced by a language model from the test name alone.'
        : ''}
    </>
  );
}

function LabPanels({ panels }) {
  if (!panels.length) return null;

  return (
    <>
      {panels.map((panel) => (
        <details className="trend-chart__block disclosure" key={`lab-${panel.key}`}>
          <summary className="disclosure__summary">
            <h3 className="trend-chart__title">{readableName(panel.name)}</h3>
            <span className="disclosure__spacer" />
            <ChangePair
              from={panel.chart?.movementFrom}
              to={panel.chart?.movementTo}
              unit={panel.chart?.unit}
            />
            {panel.chart ? (
              <LabStatus
                movement={panel.movement}
                latestFlag={panel.latestFlag}
                trend={panel.trend}
                classified={panel.classified}
              />
            ) : (
              <span className="trend-chart__nodirection">{noLineWord(panel)}</span>
            )}
            <span className="disclosure__chevron" aria-hidden="true" />
          </summary>
          {panelTrendWord(panel) && isPresent(panel.significantChangePct) ? (
            <p className="trend-chart__threshold">
              Counted as a change only past {panel.significantChangePct}%.
            </p>
          ) : null}
          {panel.restates ? (
            <p className="trend-chart__joined">
              This is the same measurement as{' '}
              {PATIENT_LABEL[panel.restates] || panel.restates}, which is
              assessed in its own right on this page — so it is shown here but
              not given a second direction of its own.
            </p>
          ) : null}
          {panel.unitAssumed ? (
            <p className="trend-chart__joined">
              One of your reports did not print a unit for this test. That
              reading is shown in {panel.unitAssumed.unit}, the unit your other
              report gives for it.
            </p>
          ) : null}
          {panel.unitEquivalence ? (
            <p className="trend-chart__joined">
              Your reports label this test two ways, both meaning{' '}
              {panel.unitEquivalence.label}, so the readings are shown on one
              scale.
            </p>
          ) : null}
          {Array.isArray(panel.joinedFrom) && panel.joinedFrom.length > 1 ? (
            <p className="trend-chart__joined">
              Your reports print this test under{' '}
              {panel.joinedFrom.length} names: {panel.joinedFrom.join(' · ')}. They
              are shown here as one test.
            </p>
          ) : null}
          {panel.chart ? (
            <TrendChart
              label={panel.chart.name}
              unit={panel.chart.unit}
              points={panel.chart.points.map((p) => ({
                date: p.date,
                value: p.value,
                unit: p.unit,
              }))}
              scaleOnly={panel.chart.referenceScale}
              classified={panel.classified === true}
              trend={panel.trend}
            />
          ) : (
            <>
              <p className="trend-chart__readings">
                {panel.rows
                  .map(
                    (r) =>
                      `${r.valueRaw ?? ''}${r.unit ? ` ${r.unit}` : ''} (${readingDate(r.date)})`
                  )
                  .join(' · ')}
              </p>
              {PRINTED_RANGE_SENTENCE[panel.latestFlag] ? (
                <p className="trend-chart__joined">
                  {PRINTED_RANGE_SENTENCE[panel.latestFlag]}
                </p>
              ) : null}
            </>
          )}
        </details>
      ))}
    </>
  );
}

function Trends({ data, history, labSeries }) {
  const features = data?.features ? Object.values(data.features) : [];
  const labPanels = labPanelsOf(labSeries);
  const hasLab = labPanels.length > 0;

  const charted = features.filter(
    (trend) =>
      !NOT_A_TRAJECTORY.has(trend.outcome) && (trend.points || []).length > 0
  );

  const tally = cardTally(charted, labPanels);
  const provenance = provenanceNote(labPanels);

  return (
    <section className="card tl-section">
      <h2>
        <span className="tl-section__icon tl-section__icon--trends" aria-hidden="true" />
        Trends over time
      </h2>
      <HistorySummary history={history} />

      {tally.total ? (
        <p className="hint">
          {tally.total} parameter{tally.total === 1 ? '' : 's'} · {tally.improving}{' '}
          improving · {tally.worsening} worsening · {tally.stable} stable ·{' '}
          {tally.undirected} with no direction stated
        </p>
      ) : null}

      {provenance ? <p className="hint">{provenance}</p> : null}

      {charted.map((trend) => {
        const props = chartPropsFor(trend);
        const declared = trend.outcome === 'TREND_CLASSIFIED' && isPresent(trend.trend);
        return (
          <details
            className="trend-chart__block disclosure"
            key={`chart-${trend.feature}`}
          >
            <summary className="disclosure__summary">
              <h3 className="trend-chart__title">{props.label}</h3>
              <ChangePair
                from={trend.change?.first_value}
                to={trend.change?.last_value}
                unit={trend.canonical_unit}
              />
              {declared ? (
                <span className={`trend trend--${trend.trend}`}>{trend.trend}</span>
              ) : (
                <span className="trend-chart__nodirection">{noDirectionWord(trend)}</span>
              )}
              <span className="disclosure__chevron" aria-hidden="true" />
            </summary>
            {(!declared || trend.trend === 'stable') && isPresent(trend.reason) ? (
              <p className="trend-chart__why">{trend.reason}</p>
            ) : null}
            <TrendChart {...props} />
          </details>
        );
      })}

      <LabPanels panels={labPanels} />

      {charted.length || hasLab ? null : (
        <p className="empty">
          No parameters could be followed across your reports yet.
        </p>
      )}

      {data?.disclaimer ? <p className="hint">{data.disclaimer}</p> : null}
    </section>
  );
}


function reportLabel(entry, namesById) {
  const info = reportDateInfo(entry);
  const when =
    info.source === 'typed'
      ? info.printedDisagrees
        ? `${info.shown} (report prints ${info.printedDisagrees})`
        : info.shown
      : info.source === 'printed'
        ? info.shown
        : info.source === 'uploaded'
          ? `uploaded ${info.shown}`
          : 'undated';

  const name = namesById.get(entry.reportId);
  return name ? `${when} — ${name}` : when;
}

function PairPicker({ reports, namesById, pair, onChange, busy }) {
  if (!reports || reports.length < 2) return null;

  const baseline = pair?.baseline || '';
  const comparison = pair?.comparison || '';

  const choose = (which) => (event) => {
    const chosen = event.target.value;

    const next =
      which === 'baseline'
        ? chosen === comparison
          ? { baseline: chosen, comparison: baseline }
          : { baseline: chosen, comparison }
        : { baseline, comparison: chosen };

    if (next.baseline && next.comparison && next.baseline !== next.comparison) {
      onChange(next);
    }
  };

  return (
    <div className="pair-picker">
      <label>
        <span className="pair-picker__label">Compare</span>
        <select value={baseline} onChange={choose('baseline')} disabled={busy}>
          {reports.map((entry) => (
            <option key={entry.reportId} value={entry.reportId}>
              {reportLabel(entry, namesById)}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span className="pair-picker__label">with</span>
        <select value={comparison} onChange={choose('comparison')} disabled={busy}>
          {reports
            .filter((entry) => entry.reportId !== baseline)
            .map((entry) => (
              <option key={entry.reportId} value={entry.reportId}>
                {reportLabel(entry, namesById)}
              </option>
            ))}
        </select>
      </label>
      {busy ? <span className="hint">Comparing…</span> : null}
    </div>
  );
}

const COMPARISON_WORD = {
  unchanged: 'no real change',
  changed_direction_only: 'real change, not rated better or worse',
};

function comparisonWord(category) {
  return (
    COMPARISON_WORD[category] || String(category || '').replace(/_/g, ' ')
  );
}

const ARROW_WORD = { '↑': 'went up', '↓': 'went down' };

const VERDICT_WORD = {
  unchanged: 'within normal variation',
  changed_direction_only: 'real change, not rated better or worse',
};

function comparisonText(category, symbol) {
  const movement = ARROW_WORD[symbol];
  if (symbol === '→' && category === 'unchanged') return '→ no change';
  if (!movement) {
    return `${isPresent(symbol) ? `${symbol} ` : ''}${comparisonWord(category)}`;
  }
  const verdict =
    VERDICT_WORD[category] || String(category || '').replace(/_/g, ' ');
  return `${symbol} ${movement} · ${verdict}`;
}

function LabComparisonRow({ row }) {
  const blocked = Boolean(row.blocked);
  const side = (value, raw, unit) => {
    if (isPresent(value)) {
      return <Value value={value} unit={blocked ? unit : row.unit} />;
    }
    if (isPresent(raw)) {
      return (
        <span className="value">
          {raw}
          {unit ? ` ${unit}` : ''}
        </span>
      );
    }
    return (
      <Absent
        label="Not measured"
        reason="This parameter was not on that report."
      />
    );
  };

  return (
    <tr>
      <th scope="row">
        {readableName(row.name)}
        {Array.isArray(row.joinedFrom) && row.joinedFrom.length > 1 ? (
          <span className="hint" title={`Also printed as: ${row.joinedFrom.join(', ')}`}>
            {' '}
            ·{' '}
            {row.joinedFrom.length} names
          </span>
        ) : null}
      </th>
      <td>{side(row.previous, row.previousRaw, row.previousUnit)}</td>
      <td>{side(row.current, row.currentRaw, row.currentUnit)}</td>
      <td>
        {isPresent(row.category) && row.category !== 'not_classifiable' ? (
          <span className={`category category--${row.category}`}>
            {comparisonText(row.category, row.symbol)}
          </span>
        ) : (
          <Absent
            label="Not classifiable"
            reason={
              blocked
                ? 'The two reports give this parameter in different units, so the readings were not compared.'
                : 'This parameter is not on both of these reports.'
            }
          />
        )}
      </td>
    </tr>
  );
}

function Comparison({ data, lab, identity, reports, namesById, pair, onPairChange, busy }) {
  const rows = (data?.table || []).filter((row) => !PERSON_DETAILS.has(row.feature));
  const labRows = lab?.rows || [];

  return (
    <section className="card tl-section">
      <h2>
        <span className="tl-section__icon tl-section__icon--compare" aria-hidden="true" />
        Comparing two reports
      </h2>

      <PairPicker
        reports={reports}
        namesById={namesById}
        pair={pair}
        onChange={onPairChange}
        busy={busy}
      />

      {data?.pair ? (
        <p className="hint">
          Comparing the report of{' '}
          {new Date(data.pair.baseline_date || data.pair.baseline?.date).toLocaleDateString()}{' '}
          with {new Date(data.pair.comparison_date || data.pair.comparison?.date).toLocaleDateString()}
          {Number.isFinite(data.pair.days_between)
            ? `, ${Math.abs(data.pair.days_between)} day${Math.abs(data.pair.days_between) === 1 ? '' : 's'} apart`
            : ''}
          {data.pair.chronological === false
            ? ' — these were given out of date order, so the direction of every change is reversed.'
            : '.'}
        </p>
      ) : null}

      <PairIdentityNotice identity={identity} />

      {rows.length + labRows.length ? (
        <p className="hint">
          {rows.length + labRows.length} parameter
          {rows.length + labRows.length === 1 ? '' : 's'} across these two reports.
        </p>
      ) : null}
      {rows.length + labRows.length ? (
        <p className="hint comparison-key">
          In the Change column, the arrow shows which way the number moved; the
          words after the dot say whether that move counts.
        </p>
      ) : null}

      {rows.length + labRows.length ? (
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
                      {comparisonText(row.category, row.symbol)}
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
            {labRows.map((row) => (
              <LabComparisonRow key={`lab-${row.key}`} row={row} />
            ))}
          </tbody>
        </table>
      ) : (
        <p className="empty">Nothing could be compared between these reports.</p>
      )}

      {data?.warnings?.length ? (
        <WarningList warnings={data.warnings} />
      ) : null}
    </section>
  );
}

function ScoreScale({ score }) {
  const value = Number(score);
  if (!Number.isFinite(value) || value < 0 || value > 100) return null;
  const x = 10 + (value / 100) * 240;
  return (
    <svg
      className="scorescale"
      viewBox="0 0 260 22"
      width="260"
      height="22"
      role="img"
      aria-label={`${value} out of 100 on this scale.`}
    >
      <title>{`${value} out of 100 on this scale.`}</title>
      <line
        x1="10"
        y1="11"
        x2="250"
        y2="11"
        stroke="var(--track)"
        strokeWidth="8"
        strokeLinecap="round"
      />
      <circle className="scorescale__mark" cx={x} cy="11" r="6" fill="var(--brand)" />
    </svg>
  );
}

function Progress({ data, alreadyWarned }) {
  const computed = data?.outcome === 'SCORE_COMPUTED';
  const seen = new Set(alreadyWarned || []);
  const ownWarnings = (data?.warnings || []).filter((w) => !seen.has(w));

  return (
    <section className="card tl-section">
      <h2>
        <span className="tl-section__icon tl-section__icon--progress" aria-hidden="true" />
        Progress score
      </h2>

      {computed && isPresent(data.score) ? (
        <>
          <div className="progress__panel">
            <div className="progress__figure">
              <p className="progress__score">
                <strong>{data.score}</strong>
                <span className="hint"> / 100</span>
              </p>
              {data.band ? (
                <p className="progress__band">
                  <strong>{data.band.label}</strong>
                </p>
              ) : null}
            </div>
            <div className="progress__scale">
              <ScoreScale score={data.score} />
              <div className="progress__ticks" aria-hidden="true">
                <span>0</span>
                <span>50</span>
                <span>100</span>
              </div>
            </div>
          </div>
          {data.scale?.direction_text ? (
            <p className="progress__meaning">{data.scale.direction_text}</p>
          ) : null}
        </>
      ) : (
        <Absent
          label="No score"
          reason={
            data?.summary?.headline ||
            'There was not enough comparable data to calculate a progress score.'
          }
        />
      )}

      {data?.coverage ? (
        <p className="progress__coverage">
          Worked out from {data.coverage.contributing_count}{' '}
          {data.coverage.contributing_count === 1 ? 'result' : 'results'}: the
          ones whose change between the two reports could be judged.
          {data.coverage.excluded_count > 0
            ? ' Everything else above is not in the number.'
            : ''}
          {!computed
            ? ` At least ${data.coverage.minimum_required} are needed before a score is shown.`
            : ''}
        </p>
      ) : null}

      {ownWarnings.length ? <WarningList warnings={ownWarnings} /> : null}

      {data?.what_this_is_not ? (
        <p className="hint">{data.what_this_is_not}</p>
      ) : null}
    </section>
  );
}

export default function Timeline() {
  const [state, setState] = useState({ loading: true });
  const [pair, setPair] = useState(null);
  const [busy, setBusy] = useState(false);
  const [names, setNames] = useState(new Map());
  const requestSeq = useRef(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [trends, comparison, progress, reports] = await Promise.allSettled([
          api.getTrends(),
          api.getComparison(),
          api.getProgress(),
          api.listReports(),
        ]);
        if (cancelled) return;
        if (reports.status === 'fulfilled') {
          const list = reports.value?.reports || reports.value?.items || [];
          setNames(new Map(list.map((r) => [r.id, r.originalName])));
        }
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

  const choosePair = async (next) => {
    requestSeq.current += 1;
    const mine = requestSeq.current;
    setPair(next);
    setBusy(true);
    setState((current) => ({
      ...current,
      comparison: null,
      comparisonError: null,
      progress: null,
      progressError: null,
    }));
    const [comparison, progress] = await Promise.allSettled([
      api.getComparison(next),
      api.getProgress(next),
    ]);
    if (mine !== requestSeq.current) return;
    setBusy(false);
    setState((current) => ({
      ...current,
      comparison: comparison.status === 'fulfilled' ? comparison.value : null,
      comparisonError:
        comparison.status === 'rejected' ? comparison.reason.message : null,
      progress: progress.status === 'fulfilled' ? progress.value : null,
      progressError: progress.status === 'rejected' ? progress.reason.message : null,
    }));
  };

  if (state.loading) return <p className="loading">Loading your timeline…</p>;
  if (state.error) return <p className="error" role="alert">{state.error}</p>;

  return (
    <main className="timeline">
      <header className="page-hero">
        <span className="page-hero__icon" aria-hidden="true">
          <Icon name="timeline" size={26} />
        </span>
        <div>
          <h1>Your timeline</h1>
          <p className="hint">
            These views describe how measured values changed between your reports.
            They report arithmetic and a declared direction of change &mdash; they
            do not interpret those changes or identify any condition.
          </p>
        </div>
      </header>

      {state.trendsError ? (
        <p className="error" role="alert">{state.trendsError}</p>
      ) : (
        <>
          <Trends
            data={state.trends?.trends}
            history={state.trends?.history}
            labSeries={state.trends?.labSeries}
          />
        </>
      )}

      {state.comparisonError ? (
        <p className="error" role="alert">{state.comparisonError}</p>
      ) : (
        <Comparison
          data={state.comparison?.comparison}
          lab={state.comparison?.labComparison}
          identity={state.comparison?.identity}
          reports={state.comparison?.history?.reports || state.trends?.history?.reports}
          namesById={names}
          pair={
            pair || {
              baseline: state.comparison?.comparison?.pair?.baseline_report_id,
              comparison: state.comparison?.comparison?.pair?.comparison_report_id,
            }
          }
          onPairChange={choosePair}
          busy={busy}
        />
      )}

      {state.progressError ? (
        <p className="error" role="alert">{state.progressError}</p>
      ) : (
        <Progress
          data={state.progress?.progress}
          alreadyWarned={state.comparison?.comparison?.warnings}
        />
      )}
    </main>
  );
}
