/**
 * WHOSE REPORT IS THIS? -- said on the page, from the sex and age it prints.
 *
 * Found 2026-09-24. Every analysis takes sex and age from the account profile,
 * never from the report; and the comparison card compares any two reports as
 * one person's history. So a report printing "34 Years / Female" on a
 * "20, male" account was judged with male thresholds, and compared with a
 * report printing "63 Years / Male" as haemoglobin 9.2 -> 13.6 "in 2 days" --
 * with nothing on screen to say either.
 *
 * The backend decides (`utils/printedIdentity`); these components only say
 * what it decided, in four states:
 *
 *   conflict     said plainly, as a warning
 *   incomplete   said quietly: something was not printed, which is NOT
 *                agreement
 *   not_checked  said quietly: the report predates the check -- "we did not
 *                look" must never render as "we looked and found nothing"
 *   consistent   nothing to say
 *
 * No name is ever read, so two people of one sex and similar age are NOT told
 * apart. The notices do not claim otherwise.
 */

const sexWord = (sex) => (sex === 'male' || sex === 'female' ? sex : null);
const ageWords = (years) => {
  if (typeof years !== 'number') return null;
  if (years < 1) return 'under a year old';
  const whole = Math.floor(years);
  return `${whole} year${whole === 1 ? '' : 's'} old`;
};
const describe = (sex, years) =>
  [sexWord(sex), ageWords(years)].filter(Boolean).join(', ') || 'no sex or age';

/** On a report's dashboard: the report against the profile the analysis used. */
export function ProfileIdentityNotice({ identity }) {
  if (!identity || identity.status === 'consistent') return null;

  if (identity.status === 'not_checked') {
    return (
      <p className="hint identity-note">
        The sex and age printed on this report have not been read, so they have
        not been checked against your profile. Analysing the report again reads
        them.
      </p>
    );
  }

  if (identity.status === 'incomplete') {
    return (
      <p className="hint identity-note">
        This report could only partly be checked against your profile: it does
        not print a sex and age this tool could read.
      </p>
    );
  }

  const printed = identity.printed || {};
  const used = identity.used || {};
  return (
    <section className="card identity-warning" role="note" aria-label="This report may not match your profile">
      <h2>This report may not match your profile</h2>
      <p>
        The report prints: <strong>{describe(printed.sex, printed.ageYears)}</strong>.
        This analysis used your profile: <strong>{describe(used.sex, used.ageYears)}</strong>.
      </p>
      <p>
        Anything that depends on sex or age &mdash; some of the thresholds on this
        page among them &mdash; was judged with your profile&rsquo;s values, not the
        report&rsquo;s. Check that this report is yours and that your profile is
        right.
      </p>
    </section>
  );
}

/** On the comparison card: could the two reports be one person's? */
export function PairIdentityNotice({ identity }) {
  if (!identity || identity.status === 'consistent') return null;

  if (identity.status === 'not_checked') {
    const which = identity.notChecked || [];
    const detail =
      which.length === 2
        ? 'neither has had its printed sex and age read. Analysing them again reads them.'
        : `the ${which[0] === 'baseline' ? 'earlier' : 'later'} report has not had its printed sex and age read. Analysing it again reads them.`;
    return (
      <p className="hint identity-note">
        Whether these two reports are the same person&rsquo;s has not been checked: {detail}
      </p>
    );
  }

  if (identity.status === 'incomplete') {
    return (
      <p className="hint identity-note">
        Whether these two reports are the same person&rsquo;s could only partly be
        checked: a sex or age is not printed, or not readable, on one of them.
      </p>
    );
  }

  const reasons = (identity.conflicts || []).map((conflict) =>
    conflict.field === 'sex'
      ? `one prints ${conflict.baseline}, the other ${conflict.comparison}`
      : `the ages printed (${ageWords(conflict.baseline)}, then ${ageWords(
          conflict.comparison
        )}) cannot both be one person's at these two dates`
  );
  return (
    <section className="identity-warning" role="note" aria-label="These reports may be for different people">
      <p>
        <strong>These two reports may be for different people:</strong> {reasons.join('; ')}.
      </p>
      <p>
        The comparison below treats them as one person&rsquo;s history. If they are
        not, the changes it shows are differences between two people, not changes
        in anyone.
      </p>
    </section>
  );
}
