import { isPresent } from '../lib/absence';


const W = 560;
const H = 196;
const PLOT = { x0: 58, x1: 538, y0: 18, y1: 134 };

const GUTTER = 72;
const LANE_Y = 166;

const GAP_LABEL = {
  rejected: 'Not usable',
  not_reported: 'No reading',
  unusable: 'Not usable',
};
const GAP_LABEL_UNKNOWN = 'No usable reading';

const isNum = (n) => typeof n === 'number' && Number.isFinite(n);

const MAX_SPOKEN_READINGS = 6;

const TREND_WORDS = ['improving', 'worsening', 'stable'];

function timeOf(value) {
  if (!isPresent(value)) return null;
  const t = new Date(value).getTime();
  return Number.isFinite(t) ? t : null;
}

function formatDate(t) {
  return new Date(t).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

function axisNumber(n) {
  const rounded = Math.abs(n) >= 100 ? Math.round(n) : Number(n.toFixed(2));
  return String(rounded);
}

function significanceSpan(stability, baseline) {
  if (!stability || !isNum(baseline)) return null;
  const pct = Number(stability.significant_change_pct);
  const floor = Number(stability.min_absolute_change);
  const byPct = Number.isFinite(pct) ? Math.abs(baseline) * (pct / 100) : 0;
  const byFloor = Number.isFinite(floor) ? Math.abs(floor) : 0;
  const threshold = Math.max(byPct, byFloor);
  if (!Number.isFinite(threshold) || threshold <= 0) return null;
  return { low: baseline - threshold, high: baseline + threshold };
}

function domainFor(values, band, span, scaleOnly) {
  const numbers = values.slice();
  if (band && isNum(band.low)) numbers.push(band.low);
  if (band && isNum(band.high)) numbers.push(band.high);
  if (span && isNum(span.low) && isNum(span.high)) {
    numbers.push(span.low, span.high);
  }
  if (scaleOnly && isNum(scaleOnly.low)) numbers.push(scaleOnly.low);
  if (scaleOnly && isNum(scaleOnly.high)) numbers.push(scaleOnly.high);
  if (!numbers.length) return null;

  let min = Math.min(...numbers);
  let max = Math.max(...numbers);
  if (min === max) {
    const nudge = Math.abs(min) * 0.1 || 1;
    min -= nudge;
    max += nudge;
  }
  const pad = (max - min) * 0.12;
  return { min: min - pad, max: max + pad };
}

export default function TrendChart({
  label,
  unit,
  points = [],
  gaps = [],
  band = null,
  classified = false,
  trend = null,
  stability = null,
  baseline = null,
  scaleOnly = null,
  caption,
}) {
  const placeable = points
    .map((p) => ({ ...p, t: timeOf(p.date) }))
    .filter((p) => p.t !== null && isNum(p.value));
  const unplaceable = points.length - placeable.length;

  const placedGaps = gaps
    .map((g) => ({ ...g, t: timeOf(g.date) }))
    .filter((g) => g.t !== null);

  const units = new Set(placeable.map((p) => p.unit).filter((u) => isPresent(u)));
  const mixedUnits = units.size > 1;

  const plottable = placeable.length >= 2 && !mixedUnits;

  const plotReadings = placeable.length > 0 && !mixedUnits;

  const span = significanceSpan(stability, baseline);
  const domain = plotReadings
    ? domainFor(placeable.map((p) => p.value), band, span, scaleOnly)
    : null;

  const showScale = Boolean(domain) && (plottable || (domain && band && isNum(band.low) && isNum(band.high)));

  const values = placeable.map((p) => p.value);
  const highest = values.length ? Math.max(...values) : null;
  const lowest = values.length ? Math.min(...values) : null;

  const times = [...placeable.map((p) => p.t), ...placedGaps.map((g) => g.t)];
  const tMin = times.length ? Math.min(...times) : 0;
  const tMax = times.length ? Math.max(...times) : 0;

  const x = (t) =>
    tMax === tMin ? (PLOT.x0 + PLOT.x1) / 2 : PLOT.x0 + ((t - tMin) / (tMax - tMin)) * (PLOT.x1 - PLOT.x0);
  const y = (v) =>
    !domain ? PLOT.y1 : PLOT.y1 - ((v - domain.min) / (domain.max - domain.min)) * (PLOT.y1 - PLOT.y0);

  const runs = [];
  if (plottable) {
    const events = [
      ...placeable.map((p) => ({ t: p.t, point: p })),
      ...placedGaps.map((g) => ({ t: g.t, point: null })),
    ].sort((a, b) => a.t - b.t);

    let run = [];
    for (const event of events) {
      if (event.point) {
        run.push(event.point);
      } else {
        if (run.length > 1) runs.push(run);
        run = [];
      }
    }
    if (run.length > 1) runs.push(run);
  }

  const declared = classified === true && TREND_WORDS.includes(trend);

  const tone =
    declared && trend === 'worsening'
      ? 'var(--rust)'
      : declared && trend === 'improving'
        ? 'var(--green)'
        : 'var(--ink)';

  const hasBand = band && isNum(band.low) && isNum(band.high) && domain;

  const first = placeable[0];
  const last = placeable[placeable.length - 1];
  const unitText = isPresent(unit) ? ` ${unit}` : '';

  let title;
  if (mixedUnits) {
    title = `${label}: readings were recorded in more than one unit, so they are not drawn on one scale.`;
  } else if (placeable.length >= 2) {
    const readings = placeable
      .map((point) => `${axisNumber(point.value)}${unitText} on ${formatDate(point.t)}`)
      .join('; ');
    const movement =
      placeable.length <= MAX_SPOKEN_READINGS
        ? readings
        : `${axisNumber(first.value)}${unitText} on ${formatDate(first.t)} to ${axisNumber(
            last.value
          )}${unitText} on ${formatDate(last.t)}`;
    title = declared
      ? `${label}: ${trend} — ${movement}, across ${placeable.length} readings.`
      : `${label}: ${movement}, across ${placeable.length} readings. No direction was classified for them.`;
  } else if (placeable.length === 1) {
    title = `${label}: one reading only, ${axisNumber(first.value)}${unitText} on ${formatDate(
      first.t
    )}. Two are needed before any change can be described, and this is not the same as no change having occurred.`;
  } else {
    title = `${label}: no usable reading was recorded, so nothing is plotted.`;
  }
  if (placedGaps.length) {
    title += ` ${placedGaps.length} report${placedGaps.length === 1 ? '' : 's'} carried no usable reading for it.`;
  }

  if (!placeable.length && !placedGaps.length) return null;

  const showPlot = plotReadings || placedGaps.length > 0;

  return (
    <figure className="trend-chart">
      {showPlot ? (
      <svg
        width={W + GUTTER}
        height={H}
        viewBox={`${-GUTTER} 0 ${W + GUTTER} ${H}`}
        role="img"
        aria-label={title}
        className="trend-chart__svg"
      >
        <title>{title}</title>

        {hasBand ? (
          <rect
            className="trend-chart__band"
            x={PLOT.x0}
            y={Math.min(y(band.high), y(band.low))}
            width={PLOT.x1 - PLOT.x0}
            height={Math.max(2, Math.abs(y(band.low) - y(band.high)))}
            fill="var(--band)"
            rx="4"
          />
        ) : null}

        <line
          x1={PLOT.x0}
          y1={PLOT.y1}
          x2={PLOT.x1}
          y2={PLOT.y1}
          stroke="var(--track)"
          strokeWidth="3"
          strokeLinecap="round"
        />

        {showScale
          ? [...new Set([highest, lowest])].map((value) => (
              <text
                key={value}
                className="trend-chart__axis"
                x={PLOT.x0 - 8}
                y={y(value) + 4}
                textAnchor="end"
              >
                {axisNumber(value)}
                {unitText}
              </text>
            ))
          : null}

        {runs.map((run, index) => (
          <path
            key={`run-${index}`}
            className="trend-chart__line"
            style={{ '--i': index }}
            pathLength="1"
            d={run.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(p.t).toFixed(1)} ${y(p.value).toFixed(1)}`).join(' ')}
            fill="none"
            stroke={tone}
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ))}

        {(plotReadings ? placeable : []).map((p, index) => (
          <circle
            key={`${p.date}-${index}`}
            className="trend-chart__point"
            style={{ '--i': index }}
            cx={x(p.t)}
            cy={y(p.value)}
            r="4.5"
            fill={p.questionable === true ? 'var(--panel)' : tone}
            stroke={tone}
            strokeWidth="2"
          >
            <title>
              {`${axisNumber(p.value)}${unitText} on ${formatDate(p.t)}${
                p.questionable === true ? ' (flagged questionable by validation)' : ''
              }`}
            </title>
          </circle>
        ))}

        {placedGaps.map((g, index) => (
          <g key={`gap-${g.date}-${index}`}>
            <line
              x1={x(g.t)}
              y1={PLOT.y1 + 6}
              x2={x(g.t)}
              y2={LANE_Y - 8}
              stroke="var(--band-line)"
              strokeWidth="1"
              strokeDasharray="2 3"
            />
            <circle
              className="trend-chart__gap"
              cx={x(g.t)}
              cy={LANE_Y}
              r="4.5"
              fill="none"
              stroke="var(--mono)"
              strokeWidth="1.5"
              strokeDasharray="2 2"
            >
              <title>
                {`${GAP_LABEL[g.kind] || GAP_LABEL_UNKNOWN} — ${formatDate(g.t)}${
                  isPresent(g.reason) ? `. ${g.reason}` : ''
                }`}
              </title>
            </circle>
          </g>
        ))}

        {times.length ? (
          <>
            <text className="trend-chart__axis" x={PLOT.x0} y={PLOT.y1 + 18} textAnchor="start">
              {formatDate(tMin)}
            </text>
            {tMax !== tMin ? (
              <text className="trend-chart__axis" x={PLOT.x1} y={PLOT.y1 + 18} textAnchor="end">
                {formatDate(tMax)}
              </text>
            ) : null}
          </>
        ) : null}
      </svg>
      ) : null}

      {hasBand ? <p className="micro trend-chart__legend">Shaded band = usual range</p> : null}

      {mixedUnits ? (
        <p className="trend-chart__absence">
          These readings were recorded in more than one unit
          {` (${[...units].join(', ')})`}, so they are not drawn on one scale.
        </p>
      ) : null}

      {placeable.length === 1 ? (
        <p className="trend-chart__absence">
          One reading — no line is drawn, because a change needs two. This is not
          the same as no change having occurred.
        </p>
      ) : null}

      {unplaceable > 0 ? (
        <p className="trend-chart__absence">
          {unplaceable} further reading(s) could not be placed on this chart.
        </p>
      ) : null}

      {placedGaps.length ? (
        <ul className="trend-chart__gaps">
          {placedGaps.map((g, index) => (
            <li key={`gapnote-${g.date}-${index}`}>
              <span className="micro">{GAP_LABEL[g.kind] || GAP_LABEL_UNKNOWN}</span>{' '}
              {formatDate(g.t)}
              {isPresent(g.reason) ? <span className="trend-chart__reason"> — {g.reason}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}

      {caption ? <figcaption className="chart__caption">{caption}</figcaption> : null}
    </figure>
  );
}
