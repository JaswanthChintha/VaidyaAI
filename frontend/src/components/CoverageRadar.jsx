const CENTRE = { x: 139, y: 106 };

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

const LABEL_OFFSET = 1.17;

const isNum = (n) => typeof n === 'number' && Number.isFinite(n);
const clamp01 = (n) => (isNum(n) ? Math.max(0, Math.min(1, n)) : 0);

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

  const placed = points.map((topic, index) => {
    const t = topic.assessed === true ? clamp01(topic.coverage) : 0;
    return { topic, index, ...along(index, t) };
  });

  const polygon = placed.map(({ x, y }) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');

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
    || `Coverage of ${points.length} conditions.`;

  return (
    <figure className="radar">
      <svg
        width="438"
        height="240"
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

      {absenceCaption && missing.length ? (
        <figcaption className="chart__caption">{absenceCaption}</figcaption>
      ) : null}
    </figure>
  );
}
