const KEEP_UPPER = new Set(['SGPT', 'SGOT', 'TSH', 'LDL', 'HDL', 'VLDL', 'MCHC', 'HBA1C', 'ALT', 'AST']);
const SMALL_WORDS = new Set(['OF', 'AND', 'IN', 'PER', 'TO', 'BY', 'ON', 'AT', 'FOR']);

export function readableName(name) {
  if (typeof name !== 'string' || !name.trim()) return name;
  if (/[a-z]/.test(name)) return name;

  const spaced = name.replace(/\s*\(\s*/g, ' (').replace(/\s*\)/g, ')').trim();
  let inBracket = false;
  const words = spaced.split(/\s+/).map((word) => {
    if (word.startsWith('(')) inBracket = true;
    const letters = word.replace(/[^A-Z0-9]/g, '');
    const keep =
      inBracket ||
      /\d/.test(word) ||
      KEEP_UPPER.has(letters) ||
      (letters.length <= 3 && !SMALL_WORDS.has(letters));
    if (word.endsWith(')')) inBracket = false;
    return keep ? word : word.toLowerCase();
  });
  const joined = words.join(' ');
  return joined.charAt(0).toUpperCase() + joined.slice(1);
}
