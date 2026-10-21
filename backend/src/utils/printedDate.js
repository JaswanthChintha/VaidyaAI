'use strict';


const STATUS = Object.freeze({
  READ: 'read',
  AMBIGUOUS: 'ambiguous',
  UNREADABLE: 'unreadable',
  ABSENT: 'absent',
});

const MONTHS = {
  jan: 1, january: 1,
  feb: 2, february: 2,
  mar: 3, march: 3,
  apr: 4, april: 4,
  may: 5,
  jun: 6, june: 6,
  jul: 7, july: 7,
  aug: 8, august: 8,
  sep: 9, sept: 9, september: 9,
  oct: 10, october: 10,
  nov: 11, november: 11,
  dec: 12, december: 12,
};

const MONTH = '(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)';
const SEP = '[\\s\\-/.,]+';
const YEAR = '([0-9A-Za-z]{2,4})';

const PATTERNS = [
  { re: /\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b/g, read: (m) => ({ y: m[1], mo: Number(m[2]), d: Number(m[3]) }) },
  { re: new RegExp(`\\b(\\d{1,2})(?:st|nd|rd|th)?${SEP}${MONTH}${SEP}${YEAR}\\b`, 'gi'), read: (m) => ({ y: m[3], mo: MONTHS[m[2].toLowerCase()], d: Number(m[1]) }) },
  { re: new RegExp(`\\b${MONTH}${SEP}(\\d{1,2})(?:st|nd|rd|th)?${SEP}${YEAR}\\b`, 'gi'), read: (m) => ({ y: m[3], mo: MONTHS[m[1].toLowerCase()], d: Number(m[2]) }) },
  { re: /\b(\d{1,2})[-/.](\d{1,2})[-/.]([0-9A-Za-z]{2,4})\b/g, read: (m) => ({ y: m[3], a: Number(m[1]), b: Number(m[2]) }) },
];

const EARLIEST = Date.UTC(1950, 0, 1);
const DAY_MS = 24 * 60 * 60 * 1000;

function calendarDay(y, mo, d) {
  if (!(mo >= 1 && mo <= 12 && d >= 1 && d <= 31)) return null;
  const t = Date.UTC(y, mo - 1, d);
  const back = new Date(t);
  if (back.getUTCFullYear() !== y || back.getUTCMonth() !== mo - 1 || back.getUTCDate() !== d) {
    return null;
  }
  return t;
}

function resolve(parts) {
  if (!/^\d{4}$/.test(parts.y)) return { status: STATUS.UNREADABLE };
  const y = Number(parts.y);

  if (parts.mo !== undefined) {
    const t = calendarDay(y, parts.mo, parts.d);
    return t === null ? { status: STATUS.UNREADABLE } : { time: t };
  }

  const dayFirst = calendarDay(y, parts.b, parts.a);
  const monthFirst = calendarDay(y, parts.a, parts.b);
  if (dayFirst !== null && monthFirst !== null && dayFirst !== monthFirst) {
    return { status: STATUS.AMBIGUOUS };
  }
  const t = dayFirst !== null ? dayFirst : monthFirst;
  return t === null ? { status: STATUS.UNREADABLE } : { time: t };
}

function parsePrintedDate(raw, { notAfter } = {}) {
  const text = typeof raw === 'string' ? raw.trim() : '';
  if (!text) return { status: STATUS.ABSENT, date: null, raw: null };
  const kept = text.slice(0, 64);

  const times = new Set();
  let refused = null;
  const claimed = [];
  for (const { re, read } of PATTERNS) {
    re.lastIndex = 0;
    let m;
    while ((m = re.exec(text)) !== null) {
      const start = m.index;
      const end = m.index + m[0].length;
      if (claimed.some(([s, e]) => start < e && end > s)) continue;
      claimed.push([start, end]);
      const r = resolve(read(m));
      if (r.status) refused = refused === STATUS.AMBIGUOUS ? refused : r.status;
      else times.add(r.time);
    }
  }

  if (times.size > 1) return { status: STATUS.AMBIGUOUS, date: null, raw: kept };
  if (times.size === 0) {
    return { status: refused || STATUS.UNREADABLE, date: null, raw: kept };
  }
  if (refused === STATUS.AMBIGUOUS) return { status: STATUS.AMBIGUOUS, date: null, raw: kept };

  const [time] = times;
  const latest = notAfter instanceof Date && !Number.isNaN(notAfter.getTime())
    ? notAfter.getTime() + DAY_MS
    : Infinity;
  if (time < EARLIEST || time > latest) {
    return { status: STATUS.UNREADABLE, date: null, raw: kept };
  }
  return { status: STATUS.READ, date: new Date(time), raw: kept };
}

function printedDateText(extraction) {
  const meta = extraction && extraction.report_metadata;
  return meta && typeof meta.report_date === 'string' ? meta.report_date : null;
}

module.exports = { STATUS, parsePrintedDate, printedDateText };
