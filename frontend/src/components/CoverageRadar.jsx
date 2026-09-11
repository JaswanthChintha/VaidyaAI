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
 * `topics` is `[{ name, assessed, coverage }]`, coverage 0..1, already derived
 * by the caller. This component knows no thresholds and no conditions.
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

const clamp01 = (n) => (typeof n === 'number' && Number.isFinite(n) ? Math.max(0, Math.min(1, n)) : 0);

/** A point `t` of the way from the centre out to vertex `i`. */
function along(index, t) {
  const outer = OUTER[index % OUTER.length];
  return {
    x: CENTRE.x + (outer.x - CENTRE.x) * t,
    y: CENTRE.y + (outer.y - CENTRE.y) * t,
  };
}

export default function CoverageRadar({ topics = [], caption }) {
  const points = topics.slice(0, OUTER.length);
  if (!points.length) return null;

  const assessedCount = points.filter((t) => t.assessed === true).length;
  const missing = points.filter((t) => t.assessed !== true).map((t) => t.name);

  const polygon = points
    .map((topic, index) => {
      // AN UNASSESSED TOPIC IS PINNED TO ZERO, never to its coverage number.
      // If a caller ever sends `coverage: 0.4` alongside `assessed: false`,
      // the absence wins -- drawing the 0.4 would put a filled shape over a
      // topic nothing was measured for.
      const t = topic.assessed === true ? clamp01(topic.coverage) : 0;
      const { x, y } = along(index, t);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');

  const title =
    assessedCount === points.length
      ? `All ${points.length} topics were assessed.`
      : `${assessedCount} of ${points.length} topics were assessed. Not assessed: ${missing.join(', ')} — nothing was measured for ${missing.length === 1 ? 'it' : 'them'}, which is not a low score.`;

  return (
    <figure className="radar">
      <svg
        width="278"
        height="212"
        /* THE PENTAGON GEOMETRY IS THE MOCKUP'S, UNCHANGED -- the viewBox is
           merely widened around it. Axis labels sit outside the shape, and at
           the spec's exact 0 0 278 212 a name like "High Cholesterol" was
           rendering as "olesterol": clipped at the frame edge, which on a
           chart about what was measured is the worst possible thing to
           truncate. Padding the frame moves nothing and cuts nothing. */
        viewBox="-56 -12 390 240"
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

        {points.map((topic, index) => {
          const assessed = topic.assessed === true;
          const { x, y } = along(index, assessed ? clamp01(topic.coverage) : 0);
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

      {caption ? <figcaption className="chart__caption">{caption}</figcaption> : null}
    </figure>
  );
}
