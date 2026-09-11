import { isPresent } from '../lib/absence';

/**
 * Every result, shown against the thing it was compared to.
 *
 * ==========================================================================
 * THE CHART IS THE EXPLANATION
 * ==========================================================================
 *
 * The platform's claim is that its decisions are evidenced, so a bare number
 * is the wrong rendering: `8.4 %` says nothing on its own, and `8.4 %` sitting
 * past the end of a shaded band says the entire finding without a sentence.
 *
 * ==========================================================================
 * THE THREE ABSENCES, WHICH ARE THE REASON THIS IS NOT A TABLE OF NUMBERS
 * ==========================================================================
 *
 *   NOT ON THE REPORT   the band is a dashed outline with NO FILL, there is no
 *                       marker at all, and the value column is an em dash. A
 *                       marker at zero would be a measurement of zero.
 *   REJECTED READING    the same dashed treatment plus the reason validation
 *                       refused it -- a rejected 999 is not a high result, it
 *                       is not a result.
 *   IN RANGE / FLAGGED  the only two states that get a filled marker.
 *
 * `rows` is already derived by the caller: `{ name, state, value, unit, low,
 * high, flagged, note }` with `state` one of 'measured' | 'not_on_report' |
 * 'rejected'. No threshold is applied here and none may be.
 */

/**
 * A per-row display domain.
 *
 * PRESENTATION ONLY -- it decides where a dot sits, never whether the dot is
 * red. The domain is stretched to hold both the reference interval and the
 * value so a result far past its ceiling stays on the track instead of
 * disappearing off the end, which would hide the very rows that matter most.
 */
function domainFor({ low, high, value }) {
  const numbers = [low, high, value].filter((n) => typeof n === 'number' && Number.isFinite(n));
  if (!numbers.length) return null;
  const ceiling = Math.max(...numbers);
  const max = ceiling * 1.35 || 1;
  return { min: 0, max };
}

const pct = (n, domain) => Math.max(0, Math.min(100, ((n - domain.min) / (domain.max - domain.min)) * 100));

export default function RangeChart({ rows = [], title, footnote, note }) {
  if (!rows.length) return null;

  return (
    <div className="range">
      <div className="range__head">
        <h2>{title || 'Where each result sits against its reference range'}</h2>
        <span className="micro">Shaded band = usual range</span>
      </div>

      {note ? <p className="range__note-all">{note}</p> : null}

      <div className="range__rows">
        {rows.map((row, index) => {
          const state = row.state || 'measured';
          const measured = state === 'measured';
          const domain = domainFor(row);
          const hasBand =
            domain && typeof row.low === 'number' && typeof row.high === 'number';

          // THREE BAND STATES, NOT TWO, and conflating the middle one was a
          // real defect on a real report:
          //
          //   a printed interval  -> the shaded band. A comparison exists.
          //   MEASURED, none printed -> NO BAND AT ALL. The value is real and
          //     is shown; there is simply nothing to compare it to. Drawing a
          //     dashed empty band here says "this value is missing", which is
          //     the opposite of true -- and on a report that prints no
          //     intervals, that was every single row.
          //   not on the report / rejected -> the dashed empty band. Here the
          //     VALUE is what is absent, which is what that treatment means.
          const bandState = hasBand ? 'range' : measured ? 'none' : 'absent';

          const bandLeft = hasBand ? pct(row.low, domain) : 12;
          const bandWidth = hasBand ? Math.max(2, pct(row.high, domain) - bandLeft) : 46;
          const markerAt =
            measured && domain && typeof row.value === 'number' ? pct(row.value, domain) : null;

          // The excess bar runs from the band's edge to the marker, and only
          // when the marker is actually outside the band -- it is the visual
          // statement "by this much", so drawing one of zero length, or one
          // for a value inside its range, would be a claim of an overshoot
          // that did not happen.
          const overshoot =
            markerAt !== null && hasBand && markerAt > bandLeft + bandWidth
              ? { left: bandLeft + bandWidth, width: markerAt - (bandLeft + bandWidth) }
              : null;

          const tone = row.flagged ? 'var(--rust)' : 'var(--green)';

          return (
            <div
              className={measured ? 'range__row' : 'range__row range__row--absent'}
              style={{ '--i': index }}
              key={`${row.name}-${index}`}
            >
              <div className="range__name">
                {row.name}
                {state === 'not_on_report' ? (
                  <span className="range__flag micro">Not on report</span>
                ) : null}
                {state === 'rejected' ? (
                  <>
                    <span className="range__flag micro">Not usable</span>
                    {isPresent(row.note) ? (
                      <span className="range__note">{row.note}</span>
                    ) : null}
                  </>
                ) : null}
              </div>

              {/* THE BARS ARE DECORATION FOR ASSISTIVE TECH, and the results
                  table further down the page is the real record (design.md
                  section 8). The name and the value stay readable, so a screen
                  reader gets a usable summary here and the full table after it
                  -- rather than every number twice with a shape in between. */}
              <div className="range__track" aria-hidden="true">
                <span className="range__baseline" />
                {bandState === 'none' ? null : (
                  <span
                    className={
                      bandState === 'range' ? 'range__band' : 'range__band range__band--absent'
                    }
                    style={{ left: `${bandLeft}%`, width: `${bandWidth}%` }}
                  />
                )}
                {overshoot ? (
                  <span
                    className="range__excess"
                    style={{
                      left: `${overshoot.left}%`,
                      width: `${overshoot.width}%`,
                      '--i': index,
                    }}
                  />
                ) : null}
                {markerAt !== null ? (
                  <span
                    className="range__marker"
                    style={{ left: `${markerAt}%`, background: tone, '--i': index }}
                  />
                ) : null}
              </div>

              <div
                className="range__value"
                style={{ color: measured ? (row.flagged ? 'var(--rust)' : 'var(--green-text)') : 'var(--mono)' }}
              >
                {measured && isPresent(row.value)
                  ? `${row.value}${isPresent(row.unit) ? ` ${row.unit}` : ''}`
                  : '—'}
              </div>
            </div>
          );
        })}
      </div>

      {footnote ? <p className="range__footnote">{footnote}</p> : null}
    </div>
  );
}
