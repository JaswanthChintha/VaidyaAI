export const NOT_MEASURED = 'Not measured';
export const NOT_DETERMINABLE = 'Not determinable';
export const NOT_ASSESSED = 'Not assessed';

export function isPresent(value) {
  if (value === null || value === undefined) return false;
  if (typeof value === 'number' && Number.isNaN(value)) return false;
  return true;
}

export function formatValue(value, unit) {
  if (!isPresent(value)) return null;
  if (typeof value === 'number') {
    const text = Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)));
    return unit ? `${text} ${unit}` : text;
  }
  return unit ? `${value} ${unit}` : String(value);
}

export function pageList(pages) {
  const list = (pages || []).map(String);
  if (list.length === 1) return `Page ${list[0]}`;
  return `Pages ${list.slice(0, -1).join(', ')} and ${list[list.length - 1]}`;
}
