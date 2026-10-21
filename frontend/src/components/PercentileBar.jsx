const X0 = 10;
const X1 = 250;
const SPAN = X1 - X0;

const BETWEEN = 'between_published_percentiles';
const BELOW_LOWEST = 'below_lowest_published_percentile';
const AT_OR_ABOVE = 'at_or_above_highest_published_percentile';

const xOf = (percentile) => X0 + (percentile / 100) * SPAN;

export default function PercentileBar({
  position,
  lowerPercentile,
  upperPercentile,
  label,
}) {
  const known =
    position === BETWEEN || position === BELOW_LOWEST || position === AT_OR_ABOVE;
  if (!known) return null;

  const lower = typeof lowerPercentile === 'number' ? lowerPercentile : null;
  const upper = typeof upperPercentile === 'number' ? upperPercentile : null;

  if (position === BETWEEN && (lower === null || upper === null)) return null;
  if (position === BELOW_LOWEST && upper === null) return null;
  if (position === AT_OR_ABOVE && lower === null) return null;

  const openLeft = position === BELOW_LOWEST;
  const openRight = position === AT_OR_ABOVE;
  const left = openLeft ? X0 : xOf(lower);
  const right = openRight ? X1 : xOf(upper);

  return (
    <svg
      className="pctbar"
      viewBox="0 0 260 26"
      width="260"
      height="26"
      role="img"
      aria-label={label ? `On the population scale: ${label}.` : 'Population percentile band'}
    >
      <title>{label ? `On the population scale: ${label}.` : 'Population percentile band'}</title>

      <line
        className="pctbar__track"
        x1={X0}
        y1="13"
        x2={X1}
        y2="13"
        stroke="var(--track)"
        strokeWidth="8"
        strokeLinecap="round"
      />

      {[25, 50, 75].map((p) => (
        <line
          key={p}
          className="pctbar__tick"
          x1={xOf(p)}
          y1="6"
          x2={xOf(p)}
          y2="20"
          stroke="var(--grid)"
          strokeWidth="1"
        />
      ))}

      <rect
        className="pctbar__band"
        x={left}
        y="8"
        width={Math.max(right - left, 3)}
        height="10"
        rx={openLeft || openRight ? 0 : 5}
        fill="var(--brand)"
      />

      {!openLeft ? (
        <line className="pctbar__cap" x1={left} y1="4" x2={left} y2="22" stroke="var(--brand)" strokeWidth="2" />
      ) : null}
      {!openRight ? (
        <line className="pctbar__cap" x1={right} y1="4" x2={right} y2="22" stroke="var(--brand)" strokeWidth="2" />
      ) : null}
    </svg>
  );
}
