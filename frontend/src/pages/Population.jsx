import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../lib/api';
import { Absent } from '../components/Absent';
import PercentileBar from '../components/PercentileBar';
import Icon from '../components/Icon';
import { PATIENT_LABEL } from '../lib/labels';
import { readableName } from '../lib/displayName';
import { friendlyPageError } from '../lib/friendlyErrors';


const humanName = (key) => String(key).replace(/_/g, ' ');

const cardTitle = (key) => {
  const label = PATIENT_LABEL[key];
  const text = label || humanName(key);
  return text.charAt(0).toUpperCase() + text.slice(1);
};

function readableList(names) {
  if (names.length <= 1) return names[0] || '';
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
}

export function sharedCohortLabel(features) {
  const labels = (features || [])
    .filter(([, entry]) => entry?.available === true && entry?.comparison?.cohort)
    .map(
      ([, entry]) =>
        `${entry.comparison.cohort.age_band_label}, ${entry.comparison.cohort.sex}`
    );
  if (!labels.length) return null;
  return labels.every((label) => label === labels[0]) ? labels[0] : null;
}

function Entry({ name, entry, cohortLabel }) {
  const available = entry.available === true;

  return (
    <li
      className={available ? 'card population__entry' : 'card population__entry population__entry--none'}
      data-reason={available ? undefined : entry.reason_code || undefined}
    >
      <h3>{cardTitle(name)}</h3>

      {available ? (
        <>
          <p className="population__band">
            <strong>{entry.comparison.band.label}</strong>
          </p>
          <p className="population__value">
            Your value:{' '}
            <span className="population__valnum">
              {entry.comparison.value} {entry.comparison.unit}
            </span>
            {entry.comparison.submitted &&
            entry.comparison.submitted.unit !== entry.comparison.unit ? (
              <span className="hint">
                {' '}
                (you gave {entry.comparison.submitted.value}{' '}
                {entry.comparison.submitted.unit}; converted for comparison)
              </span>
            ) : null}
          </p>
          <PercentileBar
            position={entry.comparison.band.position}
            lowerPercentile={entry.comparison.band.lower_percentile}
            upperPercentile={entry.comparison.band.upper_percentile}
            label={entry.comparison.band.label}
          />
          {cohortLabel ? null : (
            <p className="hint">
              Compared with: {entry.comparison.cohort.age_band_label},{' '}
              {entry.comparison.cohort.sex}
            </p>
          )}
        </>
      ) : (
        <Absent label="No comparison offered" reason={entry.message} />
      )}

    </li>
  );
}

export default function Population() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const result = await api.getPopulationContext(id);
        if (!cancelled) setData(result);
      } catch (err) {
        if (!cancelled) setError(friendlyPageError(err.message));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (error) return <p className="error" role="alert">{error}</p>;
  if (!data) return <p className="loading">Loading population context…</p>;

  const context = data.populationContext;
  const subject = data.subject;
  const allFeatures = context?.features ? Object.entries(context.features) : [];

  const notMeasurements = allFeatures.filter(
    ([, entry]) => entry?.reason_code === 'FEATURE_NOT_CONTINUOUS'
  );
  const features = allFeatures.filter(
    ([, entry]) => entry?.reason_code !== 'FEATURE_NOT_CONTINUOUS'
  );
  const cohortLabel = sharedCohortLabel(features);
  const fromReport = subject?.source === 'report' || subject?.source === 'mixed';
  const reportFields = subject
    ? [
        subject.ageSource === 'report' ? 'age' : null,
        subject.genderSource === 'report' ? 'sex' : null,
      ].filter(Boolean)
    : [];

  return (
    <main className="population">
      <header className="page-hero population-hero">
        <span className="page-hero__icon" aria-hidden="true">
          <Icon name="people" size={26} />
        </span>
        <div>
          <nav className="crumbs" aria-label="Breadcrumb">
            <Link to={`/reports/${id}`}>Dashboard</Link>
            <span aria-hidden="true">/</span>
            <span className="crumbs__here">Population context</span>
          </nav>
          <h1>How your results compare</h1>
          {context?.what_this_means ? <p className="hint">{context.what_this_means}</p> : null}
          {data.report?.originalName ? (
            <p className="doctor-hero__file">Report: {data.report.originalName}</p>
          ) : null}
        </div>
      </header>

      {subject?.otherPerson && (!subject.ageProvided || !subject.genderProvided) ? (
        <p className="caveat">
          No {[
            !subject.ageProvided ? 'age' : null,
            !subject.genderProvided ? 'sex' : null,
          ]
            .filter(Boolean)
            .join(' or ')}{' '}
          is known for the person this report describes, so comparisons that need
          it were not made.{' '}
          <Link to="/reports">Enter them under &ldquo;Whose report?&rdquo;</Link>
        </p>
      ) : null}
      {subject && !subject.otherPerson && (!subject.ageProvided || !subject.genderProvided) ? (
        <p className="caveat">
          {!subject.profileExists
            ? 'You have not filled in your details yet, so no age- or sex-matched group could be chosen.'
            : `Your profile is missing ${[
                !subject.ageProvided ? 'age' : null,
                !subject.genderProvided ? 'gender' : null,
              ]
                .filter(Boolean)
                .join(' and ')}. Comparisons that need it were not made.`}{' '}
          <Link to="/profile">Update your details</Link>
        </p>
      ) : null}

      {features.some(([, entry]) => entry?.available === true) ? (
        <p className="method">
          Each bar below shows where your result sits among people of{' '}
          {fromReport || subject?.otherPerson
            ? 'the age and sex of the person this report describes'
            : 'your age and sex'}{' '}
          in the survey
          {cohortLabel ? ` (${cohortLabel})` : ''} — the share whose result was
          at or below yours, with people whose result equals yours counted in
          that share.{' '}
          <strong>
            It does not say whether a result is normal, high, or low. It only
            says how common it is.
          </strong>
        </p>
      ) : null}

      {fromReport && reportFields.length ? (
        <p className="hint population__note">
          The {reportFields.join(' and ')} printed on this report{' '}
          {reportFields.length === 1 ? 'was' : 'were'} used to choose the group,
          as for the rest of this report&rsquo;s analysis
          {subject.source === 'mixed'
            ? subject.otherPerson
              ? '; the rest was entered for this report'
              : '; the rest came from your profile'
            : ''}
          .
        </p>
      ) : null}

      {subject?.source === 'entered' &&
      features.some(([, entry]) => entry?.available === true) ? (
        <p className="hint population__note">
          The age and sex entered for this report were used to choose the group
          &mdash; this report is marked as someone else&rsquo;s, so your profile
          was not used.
        </p>
      ) : null}

      {subject?.source === 'profile' && subject.ageProvided && subject.genderProvided &&
      features.some(([, entry]) => entry?.available === true) ? (
        <p className="hint population__note">
          No age or sex could be read from this report, so the ones in your
          profile were used to choose the group. Several results &mdash; haemoglobin among them
          &mdash; are very different for men and women, so if the profile does
          not describe the person on this report, these comparisons do not
          apply.
        </p>
      ) : null}

      {features.length ? (
        <ul className="population__list">
          {features.map(([name, entry]) => (
            <Entry
              key={name}
              name={name}
              entry={entry}
              cohortLabel={cohortLabel}
            />
          ))}
        </ul>
      ) : (
        <p className="empty">
          No parameters from this report have a published population
          distribution.
        </p>
      )}

      {notMeasurements.length ? (
        <p className="hint population__note">
          {(() => {
            const list = readableList(
              notMeasurements.map(([name]) => (name === 'gender' ? 'sex' : humanName(name)))
            );
            return list.charAt(0).toUpperCase() + list.slice(1);
          })()}{' '}
          {notMeasurements.length === 1 ? 'is' : 'are'} not measured values, so
          no percentile is offered for{' '}
          {notMeasurements.length === 1 ? 'it' : 'them'}.
        </p>
      ) : null}

      {Array.isArray(data.notCompared) && data.notCompared.length ? (
        <p className="hint population__note">
          Also on this report but not compared, because this tool has no
          population data for {data.notCompared.length === 1 ? 'it' : 'them'}:{' '}
          {readableList(data.notCompared.map(readableName))}.
        </p>
      ) : null}

      {context?.limitations?.length || context?.disclaimer ? (
        <section className="notes">
          {context?.limitations?.length ? (
            <>
              <h2 className="notes__title">
                What this comparison cannot account for
              </h2>
              <ul className="bullets">
                {context.limitations.map((limitation, index) => (
                  <li key={index}>{limitation}</li>
                ))}
              </ul>
            </>
          ) : null}
          {context?.disclaimer ? (
            <p className="notes__close">{context.disclaimer}</p>
          ) : null}
        </section>
      ) : null}
    </main>
  );
}
