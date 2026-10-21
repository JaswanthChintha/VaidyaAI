const ANGLE = { low: -60, medium: -10, high: 38 };

export default function RiskGauge({ risk, assessed = true, caption }) {
  const key = typeof risk === 'string' ? risk.toLowerCase() : null;
  const known = assessed === true && Object.prototype.hasOwnProperty.call(ANGLE, key);
  const angle = known ? ANGLE[key] : null;
  const label = known ? risk : 'Not assessed';

  const title = known
    ? `Overall risk: ${String(risk).toLowerCase()}.`
    : 'Overall risk was not established: nothing on this report could be assessed.';

  return (
    <figure className="gauge">
      <svg
        width="290"
        height="216"
        viewBox="0 0 290 216"
        role="img"
        aria-label={title}
        className="gauge__svg"
      >
        <title>{title}</title>

        <path
          d="M25 152 A120 120 0 0 1 265 152"
          fill="none"
          stroke="var(--track)"
          strokeWidth="18"
          strokeLinecap="round"
        />

        <path
          className="gauge__band gauge__band--low"
          style={{ '--len': 200 }}
          d="M25 152 A120 120 0 0 1 105 40"
          fill="none"
          stroke="var(--green)"
          strokeWidth="18"
          strokeLinecap="round"
          strokeDasharray="200"
        />
        <path
          className="gauge__band gauge__band--medium"
          style={{ '--len': 90 }}
          d="M112 37 A120 120 0 0 1 182 38"
          fill="none"
          stroke="var(--amber)"
          strokeWidth="18"
          strokeLinecap="round"
          strokeDasharray="90"
        />
        <path
          className="gauge__band gauge__band--high"
          style={{ '--len': 200 }}
          d="M188 42 A120 120 0 0 1 265 152"
          fill="none"
          stroke="var(--rust)"
          strokeWidth="18"
          strokeLinecap="round"
          strokeDasharray="200"
        />

        {known ? (
          <g
            className="gauge__needle"
            style={{ transform: `rotate(${angle}deg)`, '--angle': `${angle}deg` }}
          >
            <line
              x1="145"
              y1="152"
              x2="145"
              y2="56"
              stroke="var(--ink)"
              strokeWidth="3.5"
              strokeLinecap="round"
            />
          </g>
        ) : null}

        {known ? <circle className="gauge__hub" cx="145" cy="152" r="8" fill="var(--ink)" /> : null}

        {known ? null : (
          <circle
            className="gauge__absent"
            cx="145"
            cy="152"
            r="8"
            fill="none"
            stroke="var(--mono)"
            strokeWidth="1.5"
            strokeDasharray="2 2"
          />
        )}

        <text
          x="145"
          y="188"
          textAnchor="middle"
          className={known ? `gauge__verdict gauge__verdict--${key}` : 'gauge__verdict gauge__verdict--absent'}
        >
          {label}
        </text>
      </svg>

      <div className="gauge__scale micro">
        <span>Low</span>
        <span>Medium</span>
        <span>High</span>
      </div>

      {caption ? <figcaption className="chart__caption">{caption}</figcaption> : null}
    </figure>
  );
}
