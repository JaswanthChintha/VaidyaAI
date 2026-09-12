/**
 * Where a published percentile BAND sits on the 0-100 scale.
 *
 * WHY THIS EXISTS. Every comparison card carried three sentences, and two of
 * them differed only by the parameter name interpolated into an identical
 * template -- seven copies of "Of people of this age and sex in the survey,
 * this is the share whose X was at or below yours", and seven of "This does
 * not say whether your X is normal, high, or low." The method is now stated
 * ONCE above the list, and each card needs something that is actually about
 * ITS OWN result. A band on a scale is that: it is per-card, it cannot be
 * said in fewer words, and it is the one thing the label alone makes a reader
 * do arithmetic for.
 *
 * A BAND, NOT A POINT. Module 31 publishes cut-points and reports the bracket
 * between two of them; it interpolates nothing. Drawing a single marker would
 * invent a precision the service deliberately refuses (its own limitations
 * list says so). So the band is drawn as a band.
 *
 * NO RISK COLOUR, EVER. The page states in as many words that a percentile
 * "does not say whether your result is normal, high, or low". Painting the
 * segment green or rust would contradict that sentence from two inches away,
 * and a picture that disagrees with the words beside it is the defect this
 * whole family of components exists to prevent. The fill is `--brand`, the
 * app's neutral accent.
 *
 * NO THRESHOLD, NO CONDITION, NO POLARITY inside this component -- the same
 * contract as RangeChart, CoverageRadar and TrendChart. It takes numbers that
 * are already derived and draws them.
 */

const X0 = 10;
const X1 = 250;
const SPAN = X1 - X0;

/** The service's own position vocabulary, verbatim (`schemas/population.py`). */
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
  // ABSENCE IS NOT A GUESS. An unrecognised position, or a band with neither
  // end, has no honest geometry -- and inventing one would put a shape on a
  // medical page that no data supports. Nothing is drawn; the card's own
  // label still states the band in words, so nothing is lost.
  const known =
    position === BETWEEN || position === BELOW_LOWEST || position === AT_OR_ABOVE;
  if (!known) return null;

  const lower = typeof lowerPercentile === 'number' ? lowerPercentile : null;
  const upper = typeof upperPercentile === 'number' ? upperPercentile : null;

  // Each position must carry the ends it claims to have. A `between` band
  // missing one of them is a contradictory payload, and absence wins.
  if (position === BETWEEN && (lower === null || upper === null)) return null;
  if (position === BELOW_LOWEST && upper === null) return null;
  if (position === AT_OR_ABOVE && lower === null) return null;

  // THE OPEN END RUNS TO THE FRAME AND IS MARKED AS OPEN.
  // "Below the 5th percentile" has no floor in the published data: the survey
  // does not say where within that tail the value sits. Drawing a closed
  // segment from 0 would assert a lower bound nobody published -- the same
  // one-sided-interval fault the range chart (6ab) and the trend chart (6z)
  // each had to fix. So the segment reaches the edge and the cap that would
  // close it is simply not drawn.
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

      {/* The full 0-100 scale. A percentile's domain really is 0 to 100, so
          the track is the whole of it and never a padded window -- 6z's
          "every number printed on a chart is a reading somebody took" does
          not bite here, because these two numbers are the scale itself. */}
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

      {/* Quartile orientation marks. Not labelled: the band's own words are
          printed above the bar, and three numbers under a 240px rule is
          clutter that says nothing the sentence does not. */}
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

      {/* The closed ends get a cap; the open end does not, so the shape reads
          as running off the scale rather than stopping at a bound. */}
      {!openLeft ? (
        <line className="pctbar__cap" x1={left} y1="4" x2={left} y2="22" stroke="var(--brand)" strokeWidth="2" />
      ) : null}
      {!openRight ? (
        <line className="pctbar__cap" x1={right} y1="4" x2={right} y2="22" stroke="var(--brand)" strokeWidth="2" />
      ) : null}
    </svg>
  );
}
