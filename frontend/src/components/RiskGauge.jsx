/**
 * Overall risk, as an instrument dial.
 *
 * ==========================================================================
 * THE POINT OF THIS COMPONENT IS THE CASE WHERE IT DRAWS NO NEEDLE
 * ==========================================================================
 *
 * A gauge has a resting position, and on every gauge ever built that resting
 * position is the left-hand end -- which here is `low`. So a report where
 * NOTHING could be assessed would park the needle on "Low" and hand a reader
 * the single most dangerous sentence this platform can produce: "we could not
 * look" rendered as "we looked and it was fine".
 *
 * So `assessed === false` draws the rest arc, the bands, and NO NEEDLE AND NO
 * HUB, with the verdict word replaced by a dashed absence marker. There is no
 * angle for "unknown" and this component does not invent one.
 *
 * It takes a risk WORD and an assessed FLAG. It does not know a threshold, a
 * probability or a condition, and it must not learn one.
 */

/* Degrees about the hub. -90 is straight up; the arc spans -96..+42. */
const ANGLE = { low: -60, medium: -10, high: 38 };

export default function RiskGauge({ risk, assessed = true, caption }) {
  const key = typeof risk === 'string' ? risk.toLowerCase() : null;
  // BOTH conditions. A risk word with `assessed: false` is a contradiction the
  // backend should never send, and if it ever does, absence wins -- the safer
  // of the two readings.
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

        {/* Rest arc -- the full sweep, always drawn, so the bands read as a
            portion of something rather than as the whole instrument. */}
        <path
          d="M25 152 A120 120 0 0 1 265 152"
          fill="none"
          stroke="var(--track)"
          strokeWidth="18"
          strokeLinecap="round"
        />

        {/* The three bands. Drawn even when nothing was assessed: the scale is
            a property of the instrument, not of this patient. */}
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
            /* The angle is a STATIC transform as well as the animation's end
               state. Under `prefers-reduced-motion` the keyframes are switched
               off entirely, and a needle whose only angle lived in a keyframe
               would rest at zero -- pointing at "low" on a high-risk report. */
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

        {/* NOT MEASURED, drawn the way every absence in this app is drawn: a
            dashed outline with no fill, in --mono, never a risk colour. */}
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
          /* The word takes its own risk colour, as it does on every card --
             and only when known: an absence keeps the absence treatment. */
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
