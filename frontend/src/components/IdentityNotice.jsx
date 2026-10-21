const sexWord = (sex) => (sex === 'male' || sex === 'female' ? sex : null);
const ageWords = (years) => {
  if (typeof years !== 'number') return null;
  if (years < 1) return 'under a year old';
  const whole = Math.floor(years);
  return `${whole} year${whole === 1 ? '' : 's'} old`;
};
const describe = (sex, years) =>
  [sexWord(sex), ageWords(years)].filter(Boolean).join(', ') || 'no sex or age';

export function ProfileIdentityNotice({ identity }) {
  if (!identity || identity.status === 'consistent') return null;

  if (identity.status === 'other_person') {
    return (
      <p className="hint identity-note">
        Marked as someone else&rsquo;s report. Your profile was not used: age and
        sex come from the report or from what was entered for it, and your BMI,
        smoking and health history were not applied. It is not part of your
        timeline.
      </p>
    );
  }

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
  const profile = identity.profile || {};
  const used = identity.used || {};
  const conflicting = (identity.conflicts || []).map((c) => c.field);
  const sourceOf = (field) => used[field === 'sex' ? 'sexSource' : 'ageSource'];
  const usedReport = conflicting.length > 0
    && conflicting.every((field) => sourceOf(field) === 'report_details');
  const usedProfile = conflicting.length > 0
    && conflicting.every((field) => sourceOf(field) === 'patient_profile');
  return (
    <section className="card identity-warning" role="note" aria-label="This report may not match your profile">
      <h2>This report may not match your profile</h2>
      <p>
        The report prints: <strong>{describe(printed.sex, printed.ageYears)}</strong>.
        Your profile says: <strong>{describe(profile.sex, profile.ageYears)}</strong>.
      </p>
      {usedReport ? (
        <p>
          This analysis used the sex and age printed on the report, so anything
          that depends on them was judged for the person the report describes.
          If this report is someone else&rsquo;s, its results are theirs, not yours.
          Check that this report is yours and that your profile is right.
        </p>
      ) : usedProfile ? (
        <p>
          This analysis used your profile&rsquo;s values, not the report&rsquo;s
          &mdash; it was run before reports&rsquo; own sex and age were used.
          Analysing the report again uses the report&rsquo;s. Check that this
          report is yours and that your profile is right.
        </p>
      ) : (
        <p>
          This analysis used the report&rsquo;s values for some of these and your
          profile&rsquo;s for others. Check that this report is yours and that
          your profile is right.
        </p>
      )}
    </section>
  );
}

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
