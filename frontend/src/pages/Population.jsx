import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../lib/api';
import { Absent } from '../components/Absent';
import { isPresent } from '../lib/absence';

/**
 * Module 31 -- how a value compares with an age- and sex-matched group.
 *
 * ==========================================================================
 * THE REFUSALS ARE THE PRODUCT
 * ==========================================================================
 *
 * This module was built to say "no" well. `SEX_COHORT_NOT_AVAILABLE` for a
 * gender the published survey has no stratum for, `AGE_BELOW_ADULT_TABLE`
 * rather than scoring a child against an adult table, no unmatched cohort
 * ever substituted for a missing age. Those are deliberate answers, and a
 * screen that renders them as blank space or "unavailable" would throw away
 * the entire point.
 *
 * So an unavailable entry shows the service's own message, in full. And
 * `subject` is shown too: "no profile at all" and "a profile that answered
 * prefer_not_to_say" both produce SEX_COHORT_NOT_AVAILABLE, and only the
 * subject block tells a reader which one they can act on.
 *
 * ==========================================================================
 * WHAT A BAND IS, AND WHAT IT IS NOT
 * ==========================================================================
 *
 * A band, never an interpolated percentile -- the value is bracketed between
 * two published cut-points and no number is reported that was not measured.
 * The copy says "at or below", not "lower than", because the band is built on
 * a `<=` comparison and an audit found the older wording overstating how many
 * people sat below the patient by up to 14 points.
 *
 * And this is CONTEXT, not a finding. A percentile is not a reference range
 * and not an interpretation; Module 8 owns "is this in range", this owns only
 * "how common is this". The service's own `what_this_does_not_mean` is
 * rendered rather than paraphrased.
 */

function Entry({ name, entry }) {
  const available = entry.available === true;

  return (
    <li className="card population__entry">
      <h3>{name.replace(/_/g, ' ')}</h3>

      {available ? (
        <>
          <p className="population__band">
            <strong>{entry.comparison.band.label}</strong>
          </p>
          <p>
            Your value: {entry.comparison.value} {entry.comparison.unit}
            {entry.comparison.submitted &&
            entry.comparison.submitted.unit !== entry.comparison.unit ? (
              <span className="hint">
                {' '}
                (you gave {entry.comparison.submitted.value}{' '}
                {entry.comparison.submitted.unit}; converted for comparison)
              </span>
            ) : null}
          </p>
          <p className="hint">
            Compared with: {entry.comparison.cohort.age_band_label},{' '}
            {entry.comparison.cohort.sex}
          </p>
          <p className="hint">{entry.comparison.what_this_means}</p>
          <p className="hint">{entry.comparison.what_this_does_not_mean}</p>
        </>
      ) : (
        // The refusal, in the service's own words. This is an answer.
        <Absent label="No comparison offered" reason={entry.message} />
      )}

      {!available && isPresent(entry.reason_code) ? (
        <p className="hint">
          <code>{entry.reason_code}</code>
        </p>
      ) : null}
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
        if (!cancelled) setError(err.message);
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
  const features = context?.features ? Object.entries(context.features) : [];

  return (
    <main className="population">
      <p className="crumbs">
        <Link to={`/reports/${id}`}>Dashboard</Link> · Population context
      </p>

      <h1>How your results compare</h1>
      {context?.what_this_means ? <p>{context.what_this_means}</p> : null}

      {/* Which missing answer to act on -- see the header. */}
      {subject && (!subject.ageProvided || !subject.genderProvided) ? (
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

      {features.length ? (
        <ul className="population__list">
          {features.map(([name, entry]) => (
            <Entry key={name} name={name} entry={entry} />
          ))}
        </ul>
      ) : (
        <p className="empty">
          No parameters from this report have a published population
          distribution.
        </p>
      )}

      {context?.limitations?.length ? (
        <>
          <h2>What this comparison cannot account for</h2>
          <ul className="hint">
            {context.limitations.map((limitation, index) => (
              <li key={index}>{limitation}</li>
            ))}
          </ul>
        </>
      ) : null}

      {context?.disclaimer ? <p className="hint">{context.disclaimer}</p> : null}
    </main>
  );
}
