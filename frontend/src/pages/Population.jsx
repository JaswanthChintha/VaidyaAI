import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../lib/api';
import { Absent } from '../components/Absent';
import { isPresent } from '../lib/absence';
import PercentileBar from '../components/PercentileBar';

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

/** The same wording `Entry` puts in its heading, so the two cannot drift. */
const humanName = (key) => String(key).replace(/_/g, ' ');

/** "a, b and c" -- an Oxford-less list for a sentence, not a data dump. */
function readableList(names) {
  if (names.length <= 1) return names[0] || '';
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
}

/**
 * The cohort line, hoisted -- but ONLY when every card really shares it.
 *
 * On this report all seven comparisons carry "20-29 years, male", byte for
 * byte: the cohort is chosen from the patient's own age and sex, so it is the
 * same for every parameter that got one. Printed per card that is the same
 * line seven times.
 *
 * HOISTING AN UNSHARED COHORT WOULD BE A CLINICAL FALSEHOOD, not untidiness.
 * Module 31 matches on (sex, age band) and refuses rather than falling back,
 * so a future table with different age bands per parameter is possible -- and
 * one line above the list saying "20-29 years" over a card compared against
 * 30-39 would misstate which population a reader is being measured against.
 * So: every AVAILABLE comparison must agree, or every card keeps its own.
 * The same shape as the dashboard's `sharedBecausePhrase`.
 */
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
    <li className="card population__entry">
      <h3>{humanName(name)}</h3>

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
          <PercentileBar
            position={entry.comparison.band.position}
            lowerPercentile={entry.comparison.band.lower_percentile}
            upperPercentile={entry.comparison.band.upper_percentile}
            label={entry.comparison.band.label}
          />
          {/* THE METHOD SENTENCES ARE STATED ONCE, ABOVE THE LIST.
              `what_this_means` and `what_this_does_not_mean` are ONE template
              each with the parameter name interpolated -- measured on the
              live payload: seven cards, seven "unique" strings, one sentence.
              Printed per card that is the same paragraph seven times, which
              is 6ag's repetition fault and 6w's burial fault together.
              They are NOT deleted. Both are hoisted verbatim-in-meaning to
              the method statement above the cards, where the caveat is read
              BEFORE any band rather than after each one. Keeping the cohort
              line here too is the only part that is conditional: see
              `sharedCohortLabel`. */}
          {cohortLabel ? null : (
            <p className="hint">
              Compared with: {entry.comparison.cohort.age_band_label},{' '}
              {entry.comparison.cohort.sex}
            </p>
          )}
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
  const allFeatures = context?.features ? Object.entries(context.features) : [];

  // A CARD PER REFUSAL IS NOT THE SAME AS A USEFUL REFUSAL.
  //
  // `FEATURE_NOT_CONTINUOUS` covers age, gender and smoking history, and the
  // page was giving each of them a full card to explain that it has no
  // percentile. Nobody expected one: age and gender are what the cohort is
  // MATCHED ON, so asking for their percentile is circular, and smoking
  // history is a word rather than a number. Those cards were the page
  // explaining its own mechanics.
  //
  // The refusals that DO earn a card are the ones a reader would otherwise
  // wonder about -- a glucose of 186 with no comparison beside it is a real
  // question, and "fasting status is not recorded, so the comparison would
  // look precise and be wrong" is a real answer.
  //
  // NOTHING IS HIDDEN FROM THE PAYLOAD. The reason code is still on the API
  // for anyone reading it, and the features are still named below in one
  // line -- an absence must stay visible even when it stops being a card.
  const notMeasurements = allFeatures.filter(
    ([, entry]) => entry?.reason_code === 'FEATURE_NOT_CONTINUOUS'
  );
  const features = allFeatures.filter(
    ([, entry]) => entry?.reason_code !== 'FEATURE_NOT_CONTINUOUS'
  );
  const cohortLabel = sharedCohortLabel(features);

  return (
    <main className="population">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to={`/reports/${id}`}>Dashboard</Link>
        <span aria-hidden="true">/</span>
        <span className="crumbs__here">Population context</span>
      </nav>

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

      {/* THE METHOD, ONCE, ABOVE THE CARDS THAT USE IT.
          Every card repeated two sentences that differed only by the
          parameter name, and one cohort line that did not differ at all.
          Stated here they are read BEFORE the first band rather than after
          each one -- which for the caveat is strictly better placement, not
          merely less of it (6ag: what may never go is the caveat; this moves
          it forward, it does not remove it).
          The cohort clause appears only when every comparison agrees on it. */}
      {features.some(([, entry]) => entry?.available === true) ? (
        <p className="method">
          {/* The cohort reads as an aside, not as a noun phrase glued into
              the sentence: "among people of 20-29 years, male in the survey"
              was the first version and it is not English. */}
          Each bar below shows where your result sits among people of your age
          and sex in the survey
          {cohortLabel ? ` (${cohortLabel})` : ''} — the share whose result was
          at or below yours, with people whose result equals yours counted in
          that share.{' '}
          <strong>
            It does not say whether a result is normal, high, or low. It only
            says how common it is.
          </strong>
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

      {/* Said once, in a line, instead of three cards. */}
      {notMeasurements.length ? (
        <p className="hint">
          {/* The trailing "age and sex are what the group is chosen by" read
              as a repeat of the list it followed, and it was only true of two
              of the three names. One clause, true of all of them. */}
          {readableList(notMeasurements.map(([name]) => humanName(name)))}{' '}
          {notMeasurements.length === 1 ? 'is' : 'are'} not measured values, so
          no percentile is offered for{' '}
          {notMeasurements.length === 1 ? 'it' : 'them'}.
        </p>
      ) : null}

      {/* THE LIMITATIONS AND THE DISCLAIMER ARE ONE OBJECT, AND IT IS NOT
          COLLAPSIBLE.
          They were three consecutive `.hint` blocks -- browser bullets, no
          container, every line the same muted grey -- so the page ended in a
          grey wall and the closing statement read as text that merely
          followed the list.
          Panelled together now: they answer the same question ("how far can
          this comparison be trusted"), and the disclaimer is that question's
          conclusion rather than a separate remark.

          DELIBERATELY NOT PUT BEHIND A DISCLOSURE, unlike the dashboard's
          guidance topics. Section 6ag: what may never go is the CAVEAT --
          this platform has found it missing three separate times and recorded
          it each time as the worst thing on the page. A caveat behind a
          toggle is a caveat most readers never open, which is the same
          outcome by a slower route. Length was the complaint; hiding is not
          the only answer to it, and here it is the wrong one. */}
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
