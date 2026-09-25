'use strict';

/**
 * THE DATE THE REPORT PRINTS, READ -- OR DECLARED UNREADABLE, NEVER GUESSED.
 *
 * ==========================================================================
 * WHY THIS EXISTS
 * ==========================================================================
 *
 * Extraction has always returned `report_metadata.report_date`, "exactly as
 * printed, in the report's own format" -- and nothing read it. The timeline
 * was ordered by `reportDate ?? uploadedAt`, where `reportDate` is whatever
 * was typed into the upload form. Found 2026-09-24: two reports that both
 * print `05-Sep-2026 17:40` were compared as "2026-09-09 to 2026-09-11, 2 days
 * apart", because those were the dates typed at upload, and nothing anywhere
 * said the document disagreed.
 *
 * ==========================================================================
 * WHAT THIS REFUSES TO DO
 * ==========================================================================
 *
 * The extraction prompt forbids the model to "resolve ambiguity between DD/MM
 * and MM/DD", and this does not resolve it either. `05/09/2026` is 5 September
 * in India and 9 May in the United States; a laboratory report does not say
 * which convention it uses, and picking one would put the report four months
 * out of place on a timeline read for trends. So:
 *
 *   - a month NAME is read (`05-Sep-2026`, `Sep 5, 2026`, `5 September 2026`)
 *   - ISO year-first is read (`2026-09-05`), which has one reading only
 *   - day/month/year in DIGITS is read only when one part exceeds 12; when
 *     both could be a month and they differ, it is `ambiguous`
 *   - a two-digit or garbled year is `unreadable` (`02 Dec, 2X` is real OCR
 *     output on this project), because a century is a guess too
 *   - two DIFFERENT dates in one string are `ambiguous`: which one is the
 *     report's date is not something a regex knows
 *   - an impossible date (31 February) or an implausible one (before 1950, or
 *     after the day it was uploaded) is `unreadable`
 *
 * The result is a calendar day at UTC midnight, the same shape a date typed
 * into `<input type="date">` is stored in, so the two compare by `getTime()`.
 */

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
// A YEAR TOKEN is anything year-shaped that ends the date, so a garbled or
// two-digit year is FOUND and then refused, rather than skipped past.
const YEAR = '([0-9A-Za-z]{2,4})';

const PATTERNS = [
  // 2026-09-05, 2026/09/05
  { re: /\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b/g, read: (m) => ({ y: m[1], mo: Number(m[2]), d: Number(m[3]) }) },
  // 05-Sep-2026, 5 September, 2026
  { re: new RegExp(`\\b(\\d{1,2})(?:st|nd|rd|th)?${SEP}${MONTH}${SEP}${YEAR}\\b`, 'gi'), read: (m) => ({ y: m[3], mo: MONTHS[m[2].toLowerCase()], d: Number(m[1]) }) },
  // Sep 5, 2026
  { re: new RegExp(`\\b${MONTH}${SEP}(\\d{1,2})(?:st|nd|rd|th)?${SEP}${YEAR}\\b`, 'gi'), read: (m) => ({ y: m[3], mo: MONTHS[m[1].toLowerCase()], d: Number(m[2]) }) },
  // 05/09/2026, 5-9-2026, 05.09.26 -- digits only; the order is decided below
  { re: /\b(\d{1,2})[-/.](\d{1,2})[-/.]([0-9A-Za-z]{2,4})\b/g, read: (m) => ({ y: m[3], a: Number(m[1]), b: Number(m[2]) }) },
];

const EARLIEST = Date.UTC(1950, 0, 1);
const DAY_MS = 24 * 60 * 60 * 1000;

function calendarDay(y, mo, d) {
  if (!(mo >= 1 && mo <= 12 && d >= 1 && d <= 31)) return null;
  const t = Date.UTC(y, mo - 1, d);
  const back = new Date(t);
  // 31 February rolls into March; a date that does not survive the round trip
  // does not exist.
  if (back.getUTCFullYear() !== y || back.getUTCMonth() !== mo - 1 || back.getUTCDate() !== d) {
    return null;
  }
  return t;
}

/**
 * One candidate reading -> { time } | { status }.
 * `status` is AMBIGUOUS or UNREADABLE; `time` is a UTC-midnight epoch.
 */
function resolve(parts) {
  if (!/^\d{4}$/.test(parts.y)) return { status: STATUS.UNREADABLE };
  const y = Number(parts.y);

  if (parts.mo !== undefined) {
    const t = calendarDay(y, parts.mo, parts.d);
    return t === null ? { status: STATUS.UNREADABLE } : { time: t };
  }

  // Digits only. Day-first and month-first both considered; only a reading
  // that is the ONLY valid one is accepted.
  const dayFirst = calendarDay(y, parts.b, parts.a);
  const monthFirst = calendarDay(y, parts.a, parts.b);
  if (dayFirst !== null && monthFirst !== null && dayFirst !== monthFirst) {
    return { status: STATUS.AMBIGUOUS };
  }
  const t = dayFirst !== null ? dayFirst : monthFirst;
  return t === null ? { status: STATUS.UNREADABLE } : { time: t };
}

/**
 * @param {*} raw  `extraction.report_metadata.report_date`, as printed.
 * @param {{notAfter?: Date}} [options]  Nothing can be printed after it was
 *        uploaded; a day of slack covers the time-zone difference.
 * @returns {{status: string, date: Date|null, raw: string|null}}
 */
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
      // A span an earlier pattern already read is not read twice: `2026-09-05`
      // must not ALSO be seen by the digits-only pattern as `26-09-05`.
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
  // One date read, and another part of the string that could not be read:
  // which of the two the report meant is not known.
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

/** The raw printed date from a stored or fresh extraction, or null. */
function printedDateText(extraction) {
  const meta = extraction && extraction.report_metadata;
  return meta && typeof meta.report_date === 'string' ? meta.report_date : null;
}

module.exports = { STATUS, parsePrintedDate, printedDateText };
