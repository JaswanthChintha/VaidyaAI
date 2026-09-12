import { isPresent } from '../lib/absence';

/**
 * One parameter's trajectory across reports, in the range chart's vocabulary.
 *
 * ==========================================================================
 * A FLAT LINE AND "WE HAVE NO DATA" LOOK IDENTICAL IF YOU LET THEM
 * ==========================================================================
 *
 * This is the easiest place in the whole product to state something nobody
 * measured, because a timeline with nothing on it looks exactly like a
 * timeline that did not move. Four situations arrive here and every one of
 * them has a different meaning:
 *
 *   A REAL CHANGE          two or more readings, and the service classified a
 *                          direction against a declared stability band.
 *   FEWER THAN TWO         `INSUFFICIENT_DATA`. NO LINE IS DRAWN, ever. One
 *                          reading is one dot and a sentence saying so; a line
 *                          needs two ends and there is only one.
 *   A GAP                  a report that carried no reading for this
 *                          parameter. The line BREAKS across it. Drawing
 *                          straight through says the value moved smoothly
 *                          through a period nobody measured.
 *   A REJECTED READING     validation refused it. It has no value -- Module
 *                          28's `TimelineGap` structurally has no `value`
 *                          field -- so it is never a y position. A rejected
 *                          999 is not a high result; it is not a result.
 *
 * ==========================================================================
 * WHAT THIS COMPONENT IS NOT ALLOWED TO KNOW
 * ==========================================================================
 *
 * No threshold, no stability band, no polarity, no condition. `classified`
 * and `trend` arrive already decided by Module 28 and are only ever REPEATED
 * here. The chart cannot promote a change to significant, and a change to
 * what counts as significant happens in one place and cannot make this
 * picture disagree with the words beside it.
 *
 * Two rules below ARE decided here, and both are presentation rather than
 * clinical -- the same class as the range chart's display domain:
 *
 *   - readings in two different units are never placed on one axis at all.
 *     Two units on one y scale is a false comparison drawn as a true one, and
 *     it is exactly what the service's own `UNIT_MISMATCH` outcome is about.
 *     Withholding only the LINE is not enough: two dots positioned by one
 *     shared scale make the same comparison.
 *   - the y axis prints its own endpoints whenever they mean anything. A
 *     slope read without its scale is not a reading, and a padded axis can
 *     make 6.1 -> 6.2 look like a cliff -- but around a SINGLE reading the
 *     same padding invents a scale nothing was compared against, so there it
 *     is not printed.
 *
 * Props, all already derived by the caller:
 *   points  [{ date, value, questionable }]  real readings only, oldest first
 *   gaps    [{ date, kind, reason }]         kind: 'rejected' | 'not_reported'
 *                                            | 'unusable'. NO value field.
 *   band    { low, high } | null             a printed interval, if there is one
 *   classified / trend                       Module 28's outcome, repeated
 */

const W = 560;
const H = 196;
const PLOT = { x0: 58, x1: 538, y0: 18, y1: 134 };

/* THE FRAME IS PADDED AROUND THE PLOT, and the plot geometry is untouched --
   the same fix the radar needed, for the same reason.
   `186 mg/dl` is set right-anchored at x=50 and runs about 60 units wide, so
   at a `0 0 560 196` viewBox it started off the left edge and rendered as
   "16 mg/dl". A clipped axis label on a medical chart does not look broken; it
   looks like a smaller number. This gutter is what stops that. */
const GUTTER = 72;
/* Absences live BELOW the axis, in their own lane. They have no y position --
   putting them anywhere inside the plot would give them a value. */
const LANE_Y = 166;

/* "Nothing was there" and "something was there and could not be used" are
   different facts, and Module 7's own vocabulary already separates them.
   Collapsing `unusable` into "No reading" claims the report was silent when it
   was not -- the same conflation that put "NOT USABLE" against three rows
   nobody had rejected. An unrecognised kind claims NEITHER. */
const GAP_LABEL = {
  rejected: 'Not usable',
  not_reported: 'No reading',
  unusable: 'Not usable',
};
const GAP_LABEL_UNKNOWN = 'No usable reading';

const isNum = (n) => typeof n === 'number' && Number.isFinite(n);

/* Above this many readings the summary gives the two ends and the count
   instead of the whole series: a sentence naming fourteen dates is not a
   summary, and the per-point tooltips carry the detail. */
const MAX_SPOKEN_READINGS = 6;

/* Module 28's whole trend vocabulary. A word outside it is not a direction
   this chart knows how to state, and it does not guess at one. */
const TREND_WORDS = ['improving', 'worsening', 'stable'];

/** A date we can actually place on an axis, or null. Never a guess. */
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

/** Trim a number for a micro-label without inventing precision. */
function axisNumber(n) {
  const rounded = Math.abs(n) >= 100 ? Math.round(n) : Number(n.toFixed(2));
  return String(rounded);
}

/**
 * The y display domain: every reading, plus the reference band when there is
 * one, padded so nothing sits on the frame.
 *
 * A degenerate domain (every reading identical) is widened deliberately. The
 * alternative is a divide-by-zero that collapses every point onto one pixel
 * row -- which is a flat line drawn for a reason that has nothing to do with
 * the readings being flat.
 */
function domainFor(values, band) {
  const numbers = values.slice();
  if (band && isNum(band.low)) numbers.push(band.low);
  if (band && isNum(band.high)) numbers.push(band.high);
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
  caption,
}) {
  // A reading we cannot place is not silently dropped -- it is counted and
  // said out loud below the chart.
  const placeable = points
    .map((p) => ({ ...p, t: timeOf(p.date) }))
    .filter((p) => p.t !== null && isNum(p.value));
  const unplaceable = points.length - placeable.length;

  const placedGaps = gaps
    .map((g) => ({ ...g, t: timeOf(g.date) }))
    .filter((g) => g.t !== null);

  // TWO UNITS ARE NEVER JOINED. Presentation, not clinical: one axis can
  // carry one scale, and mmol/L plotted beside mg/dL is a false comparison
  // rendered as a true one.
  const units = new Set(placeable.map((p) => p.unit).filter((u) => isPresent(u)));
  const mixedUnits = units.size > 1;

  // THE GUARD THIS WHOLE COMPONENT EXISTS FOR. A line needs two ends. One
  // reading joined to a baseline, or to the frame, is a change nobody
  // measured -- and it would be drawn flat, which is the word this screen may
  // not print without earning it.
  const plottable = placeable.length >= 2 && !mixedUnits;

  // MIXED UNITS ARE NOT PLOTTED AT ALL, not merely left unjoined. Two dots
  // positioned by one shared y scale make the comparison just as firmly as a
  // line between them does -- 7.2 mmol/L would sit near the floor and 100
  // mg/dL at the ceiling, which reads as a collapse and is the same number
  // twice. The readings are still in the table beside this chart.
  const plotReadings = placeable.length > 0 && !mixedUnits;

  const domain = plotReadings ? domainFor(placeable.map((p) => p.value), band) : null;

  // THE AXIS NUMBERS ARE ONLY PRINTED WHEN THEY MEAN SOMETHING. With one
  // reading and no declared band the domain is pure padding -- a 10% nudge
  // either side of the only value -- so printing 5.34 and 6.86 around a single
  // 6.1 offers a scale nobody chose and nothing was compared against.
  const showScale = Boolean(domain) && (plottable || (domain && band && isNum(band.low) && isNum(band.high)));

  // EVERY NUMBER PRINTED ON THIS CHART IS A READING SOMEBODY TOOK.
  //
  // Labelling the axis with the DOMAIN prints the padding: readings of 8.4 and
  // 5.2 came out as "8.78" and "4.82", two numbers that appear on a medical
  // chart, look like measurements, and are neither. So the labels are the
  // highest and lowest actual readings, sitting at their own heights.
  const values = placeable.map((p) => p.value);
  const highest = values.length ? Math.max(...values) : null;
  const lowest = values.length ? Math.min(...values) : null;

  // The x axis spans every report that had something to say about this
  // parameter, INCLUDING the ones that had nothing -- a gap must sit at its
  // own date, not be squeezed off the end.
  const times = [...placeable.map((p) => p.t), ...placedGaps.map((g) => g.t)];
  const tMin = times.length ? Math.min(...times) : 0;
  const tMax = times.length ? Math.max(...times) : 0;

  const x = (t) =>
    tMax === tMin ? (PLOT.x0 + PLOT.x1) / 2 : PLOT.x0 + ((t - tMin) / (tMax - tMin)) * (PLOT.x1 - PLOT.x0);
  const y = (v) =>
    !domain ? PLOT.y1 : PLOT.y1 - ((v - domain.min) / (domain.max - domain.min)) * (PLOT.y1 - PLOT.y0);

  // ---- the line, BROKEN AT EVERY GAP ------------------------------------
  //
  // Walk the reports in date order and start a new run whenever a gap falls
  // between two readings. A run of one reading gets no path at all: the same
  // "a line needs two ends" rule, applied inside the series rather than to it.
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

  // BOTH HALVES, the same shape as the gauge's `assessed && known risk`. A
  // payload carrying `classified` without a trend word, or a trend word
  // without the classification, is a contradiction the service's own model
  // validator forbids -- and if one ever arrives, the unclassified reading
  // wins, because it is the safer of the two. Without this, `classified: true`
  // with `trend: null` renders the string "null" as the direction.
  const declared = classified === true && TREND_WORDS.includes(trend);

  // COLOUR IS CATEGORICAL AND ONLY A CLASSIFIED DIRECTION EARNS ONE.
  // `stable` is classified but takes no risk hue -- green in this palette
  // means "in range", which is a different statement from "did not move".
  const tone =
    declared && trend === 'worsening'
      ? 'var(--rust)'
      : declared && trend === 'improving'
        ? 'var(--green)'
        : 'var(--ink)';

  const hasBand = band && isNum(band.low) && isNum(band.high) && domain;

  // ---- the finding, in words (design.md section 8) -----------------------
  const first = placeable[0];
  const last = placeable[placeable.length - 1];
  const unitText = isPresent(unit) ? ` ${unit}` : '';

  let title;
  if (mixedUnits) {
    title = `${label}: readings were recorded in more than one unit, so they are not drawn on one scale.`;
  } else if (placeable.length >= 2) {
    // EVERY READING, NOT JUST THE TWO ENDS.
    //
    // "8.4 % on 7 Sept to 5.2 % on 11 Sept, across 3 readings" names the
    // first and the last and leaves the middle one nowhere: not on the axis,
    // which is deliberately two dates rather than a ruler, and not in the
    // only sentence describing the series. A reader asking what the middle
    // dot is had nothing to read -- and a screen reader user had nothing at
    // all. Listed in full while the list stays readable; past that the ends
    // and the count are the honest summary.
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

  // Nothing to place and nothing to explain: the table row already carries the
  // service's own refusal sentence, and an empty frame adds nothing to it.
  if (!placeable.length && !placedGaps.length) return null;

  // An empty frame is not a chart. When nothing can be placed -- readings in
  // two units, and no gap to show either -- the sentence below stands alone.
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

        {/* The reference band, when the report printed one. Same vocabulary
            as the range chart: a shaded band IS a comparison, so it is drawn
            only when a real interval exists -- never as an empty frame. */}
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

        {/* The axis. Always drawn -- it is the frame the readings sit in, and
            it carries no claim of its own. */}
        <line
          x1={PLOT.x0}
          y1={PLOT.y1}
          x2={PLOT.x1}
          y2={PLOT.y1}
          stroke="var(--track)"
          strokeWidth="3"
          strokeLinecap="round"
        />

        {/* THE SCALE IS PART OF THE READING. A slope without its endpoints
            can be made to say anything by the padding alone. */}
        {/* Deduplicated: two readings of 26.42 are ONE number, and printing
            it twice at the same height stacks it on itself. Printing it zero
            times -- which is what a plain high/low pair does when they are
            equal -- leaves a genuinely flat line with no scale at all. */}
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

        {/* One path per unbroken run. A gap ends a run, so the ink stops
            where the evidence stops. */}
        {runs.map((run, index) => (
          <path
            key={`run-${index}`}
            className="trend-chart__line"
            style={{ '--i': index }}
            /* Normalised so the draw-on animation needs no measured length --
               and so its rest state is a fully drawn line, not a blank one. */
            pathLength="1"
            d={run.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(p.t).toFixed(1)} ${y(p.value).toFixed(1)}`).join(' ')}
            fill="none"
            stroke={tone}
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ))}

        {/* Every real reading gets a marker, whether or not a line could be
            drawn through it -- a lone reading is still a reading, and hiding
            it would be the absence failure from the other side. A reading
            Module 6 marked questionable is hollow: shown, and not asserted as
            firm. */}
        {(plotReadings ? placeable : []).map((p, index) => (
          /* ITS OWN TITLE, so pointing at a dot says what THAT dot is.
             With only the chart-level <title>, hovering any point showed the
             whole-series summary -- so the middle reading of a three-point
             series, which the axis does not label either, could not be read
             off the chart at all. A child <title> takes precedence over the
             parent's for the element under the pointer. */
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

        {/* THE ABSENCE LANE. Below the axis, dashed and unfilled, in --mono:
            the app's absence treatment, and deliberately nowhere near a y
            position. The hairline anchors each one to its own date so the
            break in the line above it is legible as "here". */}
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

        {/* The x axis is two dates, not a ruler: the readings are irregular
            and evenly spaced ticks would imply a cadence nobody kept. */}
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

      {/* Below the chart, the absences in words. The table beside this chart
          counts the gaps; only here does a reader learn WHY each one is a
          gap, and a refused reading's reason is the service's own. */}
      {/* The range chart's own legend, in the range chart's words, because a
          shaded band with no explanation is a shape a reader has to guess at.
          Shown only when a band was actually drawn. */}
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
