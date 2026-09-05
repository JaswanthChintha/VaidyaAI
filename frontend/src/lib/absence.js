/**
 * Rendering primitives for a platform whose central rule is that ABSENCE IS
 * NEVER A VALUE.
 *
 * ==========================================================================
 * WHY THIS FILE EXISTS BEFORE ANY SCREEN DOES
 * ==========================================================================
 *
 * Every layer beneath this one has already been made careful about absence,
 * repeatedly and at cost. `INSUFFICIENT_DATA` carries no risk. A timeline gap
 * structurally has no `value` field. Fewer than two readings is
 * `INSUFFICIENT_DATA`, never `stable`. An unassessed condition is its own
 * category and is never folded in with `normal`. A model that declined to
 * predict says so rather than returning a low probability.
 *
 * ALL OF THAT CAN BE UNDONE BY ONE LINE OF JSX. `{risk ?? 'Low'}` renders a
 * missing risk as reassurance. `{value || 0}` renders a rejected reading as
 * zero. `{trend || 'stable'}` states that nothing changed when nothing was
 * measured. A dashboard has to show SOMETHING in every box, which is exactly
 * the pressure that turns an absence into a value -- and the audits behind
 * MEMORY.md section 11 found this happening at every other layer already.
 *
 * So the components in this file are the only sanctioned way to put a
 * possibly-absent value on screen, and none of them accepts a fallback
 * VALUE -- only a fallback EXPLANATION. There is deliberately no
 * `defaultValue` prop anywhere here, because the whole class of bug is
 * someone reaching for one under deadline.
 *
 * ==========================================================================
 * THE ONE RULE
 * ==========================================================================
 *
 * Branch on the explicit flag the API sends -- `available`, `present`,
 * `any_assessed`, `generated_explanation_available` -- and NEVER on the
 * truthiness of the value itself. A real `0`, a real `false` and a real
 * empty string are all falsy and all meaningful; `hba1c: 0` is not "no
 * reading", and `complete: false` is not "no answer".
 */

/** Nothing was measured, and this is what the reader is told instead. */
export const NOT_MEASURED = 'Not measured';
/** Something was measured but could not be interpreted. */
export const NOT_DETERMINABLE = 'Not determinable';
/** Nothing was assessed at all -- distinct from "assessed and normal". */
export const NOT_ASSESSED = 'Not assessed';

/**
 * Is this a value we may print as itself?
 *
 * `0` and `false` are values. `null`, `undefined` and `NaN` are not. This is
 * the distinction `??` gets right and `||` gets wrong, and it is the reason
 * `||` should not appear next to a clinical value anywhere in this app.
 */
export function isPresent(value) {
  if (value === null || value === undefined) return false;
  if (typeof value === 'number' && Number.isNaN(value)) return false;
  return true;
}

/**
 * Format a number for display without inventing precision or a zero.
 *
 * Returns `null` when there is nothing to show, so a caller cannot
 * accidentally render the string "null" or "undefined" -- both of which have
 * reached production screens on other projects and read, to a patient, as a
 * result.
 */
export function formatValue(value, unit) {
  if (!isPresent(value)) return null;
  if (typeof value === 'number') {
    const text = Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)));
    return unit ? `${text} ${unit}` : text;
  }
  return unit ? `${value} ${unit}` : String(value);
}
