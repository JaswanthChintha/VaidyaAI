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

/**
 * One list of analysis warnings, whatever shape the producing module used.
 *
 * WHY THIS IS NOT `warnings.map(w => <li>{w}</li>)`.
 *
 * The pipeline emits warnings in two shapes and both reach a screen. Module 27
 * and Module 32 carry the ORIGIN with the text -- `{ stage, module, message }`
 * -- because "which stage noticed this" is exactly what makes a warning
 * actionable ("extraction could not read page 5" is a different problem from
 * "the rule engine had no threshold for this feature"). Modules 28/30/31 emit
 * flat sentences, having no stage to attribute.
 *
 * Rendering the object form directly throws `Objects are not valid as a React
 * child` and takes the WHOLE PAGE down with it -- and it does so only when
 * there is something to warn about, so the screen works right up until the
 * moment it has something important to say. That is the worst possible failure
 * mode for this particular list: these are the notes that tell a patient their
 * report was read incompletely.
 *
 * So the shape is normalised here, once, and the stage is shown when present
 * rather than discarded.
 */
/**
 * Pipeline stage -> what a patient would call it.
 *
 * These names exist for engineers: `extraction`, `validation`, `rules`, `ml`,
 * `fusion`. Printing them verbatim in front of a warning turns a readable
 * sentence into "fusion: ...". Anything not in this table is shown WITHOUT a
 * prefix rather than with a raw one.
 */
const STAGE_LABEL = {
  extraction: 'Reading the report',
  validation: 'Checking the values',
  features: 'Checking the values',
  rules: 'Clinical checks',
  ml: 'Statistical model',
  fusion: 'Combining the checks',
  decision: 'Combining the checks',
  explanation: 'Writing the explanation',
  safety: 'Safety review',
  report: 'Building the report',
};

export function WarningList({ warnings, className = 'warnings' }) {
  const items = Array.isArray(warnings) ? warnings : [];
  if (!items.length) return null;

  return (
    <ul className={className}>
      {items.map((warning, index) => {
        // A plain sentence: nothing to attribute, render as-is.
        if (typeof warning === 'string') return <li key={index}>{warning}</li>;

        // Anything else is treated as the tagged form. `message` is the only
        // field required to be useful; a warning that somehow carries neither
        // a message nor a string body is still listed rather than silently
        // dropped, because a missing warning is worse than an ugly one.
        const message =
          warning && typeof warning === 'object' && typeof warning.message === 'string'
            ? warning.message
            : 'An unlabelled warning was recorded for this report.';
        const stage = warning && typeof warning === 'object' ? warning.stage : null;
        const stageLabel = STAGE_LABEL[stage];

        return (
          <li key={index}>
            {/* The stage is shown ONLY when there is a plain-English name for
                it. The raw values are pipeline stage names -- "fusion", "ml" --
                and a patient reading "fusion: Heart Disease: ..." learns
                nothing except that something internal happened. An unmapped
                stage is omitted rather than printed raw; a new stage on the
                Python side degrades to a bare sentence, which is still true. */}
            {stageLabel ? (
              <span className="warning__stage">{stageLabel}: </span>
            ) : null}
            {message}
          </li>
        );
      })}
    </ul>
  );
}
