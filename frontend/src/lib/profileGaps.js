export const KEY_PROFILE_DETAILS = [
  { key: 'age', label: 'age' },
  { key: 'gender', label: 'sex' },
];

export function missingKeyDetails(profile) {
  if (!profile) return KEY_PROFILE_DETAILS.map((d) => d.label);
  return KEY_PROFILE_DETAILS.filter(({ key }) => {
    const value = profile[key];
    return value === undefined || value === null || value === '';
  }).map((d) => d.label);
}

export function joinDetails(labels) {
  if (labels.length <= 1) return labels.join('');
  return `${labels.slice(0, -1).join(', ')} and ${labels[labels.length - 1]}`;
}
