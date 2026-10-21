import { isPresent } from '../lib/absence';


function domainFor({ low, high, value }) {
  const numbers = [low, high, value].filter((n) => typeof n === 'number' && Number.isFinite(n));
  if (!numbers.length) return null;
  const ceiling = Math.max(...numbers);
  const max = ceiling * 1.35 || 1;
  return { min: 0, max };
}

const pct = (n, domain) => Math.max(0, Math.min(100, ((n - domain.min) / (domain.max - domain.min)) * 100));

export function hasComparableRange(rows = []) {
  return rows.some(
    (row) => typeof row.low === 'number' && typeof row.high === 'number'
  );
}

export default function RangeChart({ rows = [], title, footnote }) {
  if (!rows.length) return null;
  if (!hasComparableRange(rows)) return null;

  return (
    <div className="range">
      <div className="range__head">
        <h2>{title || 'Where each result sits against its reference range'}</h2>
        <span className="micro">Shaded band = usual range</span>
      </div>

      <div className="range__rows">
        {rows.map((row, index) => {
          const state = row.state || 'measured';
          const measured = state === 'measured';
          const domain = domainFor(row);
          const hasBand =
            domain && typeof row.low === 'number' && typeof row.high === 'number';

          const bandState = hasBand ? 'range' : measured ? 'none' : 'absent';

          const bandLeft = hasBand ? pct(row.low, domain) : 12;
          const bandWidth = hasBand ? Math.max(2, pct(row.high, domain) - bandLeft) : 46;
          const markerAt =
            measured && domain && typeof row.value === 'number' ? pct(row.value, domain) : null;

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
