import { isPresent, formatValue, NOT_MEASURED } from '../lib/absence';

/**
 * The components that put a possibly-absent clinical value on screen.
 *
 * Read `src/lib/absence.js` first -- it explains why these exist and why not
 * one of them takes a fallback VALUE. Every prop here that looks like it
 * might accept "what to show instead" accepts a REASON, never a number.
 */

/**
 * "There is nothing here, and here is why."
 *
 * The reason is required. An absence with no explanation is the failure this
 * whole file exists to prevent: a reader cannot tell "we did not look" from
 * "we looked and found nothing", and will generally assume the second.
 */
export function Absent({ reason, label = NOT_MEASURED }) {
  return (
    <span className="absent" title={reason || undefined}>
      <span className="absent__label">{label}</span>
      {reason ? <span className="absent__reason">{reason}</span> : null}
    </span>
  );
}

/**
 * A measured value, or a stated absence. Never a zero standing in for either.
 *
 * `available` is the API's own flag and takes precedence over the value:
 * Module 31 sends `available: false` with no `comparison` object at all, and
 * Module 23 sends `generated_explanation_available` beside a possibly-empty
 * string. When a flag is supplied, the flag decides. When it is not, presence
 * of the value decides -- and presence means `!= null`, not truthiness, so a
 * genuine `0` still prints.
 */
export function Value({ value, unit, available, reason, label }) {
  const usable = available === undefined ? isPresent(value) : available === true;
  if (!usable) return <Absent reason={reason} label={label} />;

  const text = formatValue(value, unit);
  // `available: true` with nothing to show is a contract violation upstream,
  // not something to paper over with an empty span.
  if (text === null) {
    return <Absent reason={reason} label={label} />;
  }
  return <span className="value">{text}</span>;
}

/**
 * A risk level, which may legitimately not exist.
 *
 * `INSUFFICIENT_DATA` carries no risk -- that is a type-level guarantee in
 * `decisions.py` and a fixed rule in MEMORY.md section 11 -- and an audit
 * found the backend substituting "Low" for an explicit `null` right up until
 * it was fixed. A missing risk is NOT low risk, and this component has no way
 * to express that it is.
 */
export function Risk({ risk, assessed, reason }) {
  if (assessed === false || !isPresent(risk)) {
    return <Absent reason={reason || 'No risk level was established.'} label={NOT_MEASURED} />;
  }
  const tone = String(risk).toLowerCase();
  return <span className={`risk risk--${tone}`}>{risk}</span>;
}

/**
 * An optional section, which is absent WITH A STATED REASON or not at all.
 *
 * Modules 28-32 all use this shape: `{present: boolean, reason_code, reason}`.
 * With one report a trend section is absent because a trend needs two
 * readings -- and rendering that as "stable" would state something nobody
 * measured. `reason_code` is shown as a machine-readable hint because the
 * codes are stable API surface a support conversation can refer to.
 */
export function Section({ status, title, children }) {
  const present = status?.present === true;
  return (
    <section className="section">
      <h3 className="section__title">{title}</h3>
      {present ? (
        children
      ) : (
        <p className="section__absent">
          {status?.reason || 'This section is not available.'}
          {status?.reason_code ? (
            <code className="section__code">{status.reason_code}</code>
          ) : null}
        </p>
      )}
    </section>
  );
}
