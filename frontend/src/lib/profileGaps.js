/**
 * Which KEY profile details are missing (owner, 2026-10-06).
 *
 * Age and sex are the two the analysis cannot do without: eGFR needs both,
 * the ALT limit differs for men and women, and the models are given both. A
 * new user is reminded until they are filled in -- a NUDGE, never a block,
 * because a report can be someone else's and a user may decline to answer.
 *
 * "Prefer not to say" is an ANSWER, so it does not count as missing: asking
 * again someone who has deliberately declined is nagging, not helping.
 */
export const KEY_PROFILE_DETAILS = [
  { key: 'age', label: 'age' },
  { key: 'gender', label: 'sex' },
];

/** Labels of the key details missing from `profile`; all of them when there is none. */
export function missingKeyDetails(profile) {
  if (!profile) return KEY_PROFILE_DETAILS.map((d) => d.label);
  return KEY_PROFILE_DETAILS.filter(({ key }) => {
    const value = profile[key];
    return value === undefined || value === null || value === '';
  }).map((d) => d.label);
}

/** "age", "age and sex". */
export function joinDetails(labels) {
  if (labels.length <= 1) return labels.join('');
  return `${labels.slice(0, -1).join(', ')} and ${labels[labels.length - 1]}`;
}
