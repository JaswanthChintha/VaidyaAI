import { isPresent, formatValue, NOT_MEASURED } from '../lib/absence';


export function Absent({ reason, label = NOT_MEASURED }) {
  return (
    <span className="absent" title={reason || undefined}>
      <span className="absent__label">{label}</span>
      {reason ? <span className="absent__reason">{reason}</span> : null}
    </span>
  );
}

export function Value({ value, unit, available, reason, label }) {
  const usable = available === undefined ? isPresent(value) : available === true;
  if (!usable) return <Absent reason={reason} label={label} />;

  const text = formatValue(value, unit);
  if (text === null) {
    return <Absent reason={reason} label={label} />;
  }
  return <span className="value">{text}</span>;
}

export function Risk({ risk, assessed, reason }) {
  if (assessed === false || !isPresent(risk)) {
    return <Absent reason={reason || 'No risk level was established.'} label={NOT_MEASURED} />;
  }
  const tone = String(risk).toLowerCase();
  return <span className={`risk risk--${tone}`}>{risk}</span>;
}

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
        if (typeof warning === 'string') return <li key={index}>{warning}</li>;

        const message =
          warning && typeof warning === 'object' && typeof warning.message === 'string'
            ? warning.message
            : 'An unlabelled warning was recorded for this report.';
        const stage = warning && typeof warning === 'object' ? warning.stage : null;
        const stageLabel = STAGE_LABEL[stage];

        return (
          <li key={index}>
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
