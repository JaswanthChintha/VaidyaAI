/**
 * How much of each topic this report could actually cover.
 *
 * ==========================================================================
 * A ZERO HERE MEANS "NOT MEASURED", AND IT MUST NOT READ AS "SCORED LOW"
 * ==========================================================================
 *
 * On any radar chart a vertex at the centre looks like a bad score. On this
 * one it usually means the report did not carry the test -- a completely
 * different statement, and the one this codebase exists to keep separate.
 *
 * So an unassessed topic gets the app's absence treatment rather than a small
 * filled dot: a DASHED, UNFILLED circle in `--mono`, its axis label dropped to
 * `--mono` too, and a slow shimmer -- the only looping animation in the app,
 * because a still dot at the centre is exactly what a low score looks like.
 *
 * `topics` is `[{ name, short, assessed, coverage, available, cited }]`,
 * coverage 0..1, already derived by the caller. This component knows no
 * thresholds and no conditions.
 *
 * COVERAGE IS HOW MUCH OF THE TOPIC THE REPORT COULD SPEAK TO -- the share of
 * the inputs the assessment cites that were actually available. `available`
 * and `cited` are those two counts, carried so the chart can say the fraction
 * in words rather than only as a distance. It is NOT the verdict: a topic
 * being flagged says nothing about how completely it could be examined, and
 * an earlier version that put flagged topics at the rim and clear ones inside
 * meant a full pentagon read as "we looked thoroughly" when it actually said
 * "everything here is abnormal".
 */

const CENTRE = { x: 139, y: 106 };

/* The mockup's pentagon, clockwise from the top. Kept as literal geometry
   rather than computed, so the rings and the spokes cannot drift apart. */
const OUTER = [
  { x: 139, y: 22 },
  { x: 250, y: 102 },
  { x: 207, y: 192 },
  { x: 71, y: 192 },
  { x: 28, y: 102 },
];

const RINGS = [
  '139,22 250,102 207,192 71,192 28,102',
  '139,56 205,104 179,158 99,158 73,104',
  '139,90 161,106 152,124 126,124 117,106',
];

/* Where an axis label sits: pushed a little further out than its vertex. */
const LABEL_OFFSET = 1.17;

const isNum = (n) => typeof n === 'number' && Number.isFinite(n);
const clamp01 = (n) => (isNum(n) ? Math.max(0, Math.min(1, n)) : 0);

/** A point `t` of the way from the centre out to vertex `i`. */
function along(index, t) {
  const outer = OUTER[index % OUTER.length];
  return {
    x: CENTRE.x + (outer.x - CENTRE.x) * t,
    y: CENTRE.y + (outer.y - CENTRE.y) * t,
  };
}

export default function CoverageRadar({ topics = [], absenceCaption }) {
  const points = topics.slice(0, OUTER.length);
  if (!points.length) return null;

  const assessedCount = points.filter((t) => t.assessed === true).length;
  const missing = points.filter((t) => t.assessed !== true).map((t) => t.name);

  // ONE RADIUS PER TOPIC, COMPUTED ONCE. The polygon and the vertices used to
  // derive this separately, so the pinning rule below was enforced twice and
  // could be broken in one place while the other still looked right: the
  // filled shape reaching out to a topic whose own point is drawn at the
  // centre as an absence. §6x's rule -- "the polygon must pass through the
  // centre on that axis" -- is now structurally the same number.
  //
  // AN UNASSESSED TOPIC IS PINNED TO ZERO, never to its coverage number. If a
  // caller ever sends `coverage: 0.4` alongside `assessed: false`, the absence
  // wins: drawing the 0.4 would put a filled shape over a topic nothing was
  // measured for.
  const placed = points.map((topic, index) => {
    const t = topic.assessed === true ? clamp01(topic.coverage) : 0;
    return { topic, index, ...along(index, t) };
  });

  const polygon = placed.map(({ x, y }) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');

  // The fractions in words. A radius is not readable by a screen reader and
  // is not precise to anyone else either -- "5 of 8" is both.
  const spoken = points
    .filter((t) => t.assessed === true && isNum(t.cited) && isNum(t.available))
    .map((t) => `${t.short || t.name} ${t.available} of ${t.cited}`)
    .join(', ');

  const coverageSentence = spoken
    ? `Inputs available for each topic: ${spoken}.`
    : '';
  const absenceSentence = missing.length
    ? ` Not assessed: ${missing.join(', ')} — nothing was measured for ${missing.length === 1 ? 'it' : 'them'}, which is not a low score.`
    : '';
  const title = `${coverageSentence}${absenceSentence}`.trim()
    // "conditions", matching the heading this chart sits under and the rest
    // of the reader-facing copy. `topics` stays as the PROP name, which is
    // this codebase's own vocabulary and is not read by anyone.
    || `Coverage of ${points.length} conditions.`;

  return (
    <figure className="radar">
      <svg
        /* MATCHED TO THE viewBox, not to the mockup's 278x212. Padding the
           frame while leaving the element at the pentagon's own width renders
           the whole chart scaled DOWN to fit the gutter inside it -- the
           shape shrinks every time a label needs more room. The element grows
           with the frame instead, and `max-width: 100%` keeps it inside the
           panel. */
        width="438"
        height="240"
        /* THE PENTAGON GEOMETRY IS THE MOCKUP'S, UNCHANGED -- the viewBox is
           merely widened around it. Axis labels sit outside the shape, and at
           the spec's exact 0 0 278 212 a name like "High Cholesterol" was
           rendering as "olesterol": clipped at the frame edge, which on a
           chart about what was measured is the worst possible thing to
           truncate. Padding the frame moves nothing and cuts nothing.
           WIDENED AGAIN 2026-09-11: -56 was not enough either. The left-hand
           label is right-anchored at x=9.1 and "Triglycerides" is ~83 units
           wide, so it began at -74 and rendered as ".glycerides" on a live
           report. The gutter now holds the longest label this map can
           produce ("Haemoglobin (high)") with room to spare. */
        viewBox="-104 -12 438 240"
        role="img"
        aria-label={title}
        className="radar__svg"
      >
        <title>{title}</title>

        {RINGS.map((ring) => (
          <polygon key={ring} points={ring} fill="none" stroke="var(--grid)" strokeWidth="1" />
        ))}

        {OUTER.map((vertex) => (
          <line
            key={`${vertex.x}-${vertex.y}`}
            x1={CENTRE.x}
            y1={CENTRE.y}
            x2={vertex.x}
            y2={vertex.y}
            stroke="var(--grid)"
            strokeWidth="1"
          />
        ))}

        <polygon
          className="radar__shape"
          points={polygon}
          fill="var(--radar-fill)"
          stroke="var(--rust)"
          strokeWidth="2.5"
          strokeLinejoin="round"
        />

        {placed.map(({ topic, index, x, y }) => {
          const assessed = topic.assessed === true;
          return assessed ? (
            <circle
              key={topic.name}
              className="radar__vertex"
              style={{ '--i': index }}
              cx={x}
              cy={y}
              r="4"
              fill="var(--rust)"
            />
          ) : (
            <circle
              key={topic.name}
              className="radar__vertex radar__vertex--absent"
              cx={x}
              cy={y}
              r="4.5"
              fill="none"
              stroke="var(--mono)"
              strokeWidth="1.5"
              strokeDasharray="2 2"
            />
          );
        })}

        {points.map((topic, index) => {
          const { x, y } = along(index, LABEL_OFFSET);
          const assessed = topic.assessed === true;
          return (
            <text
              key={topic.name}
              x={x}
              y={y}
              textAnchor={x > CENTRE.x + 6 ? 'start' : x < CENTRE.x - 6 ? 'end' : 'middle'}
              dominantBaseline="middle"
              className={assessed ? 'radar__label' : 'radar__label radar__label--absent'}
            >
              {topic.short || topic.name}
            </text>
          );
        })}
      </svg>

      {/* THE CAPTION EXPLAINS THE DOTTED POINT, so it appears only when there
          IS one. On a report where every topic was assessed it described a
          mark that is not on the chart -- the same fault as a
          "shaded band = usual range" legend above a chart with no band, and
          a reader hunting for the thing it names finds nothing. */}
      {absenceCaption && missing.length ? (
        <figcaption className="chart__caption">{absenceCaption}</figcaption>
      ) : null}
    </figure>
  );
}
