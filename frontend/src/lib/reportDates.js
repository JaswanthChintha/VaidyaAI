/**
 * WHICH DATE A REPORT IS SHOWN WITH, AND WHERE THAT DATE CAME FROM.
 *
 * Three dates exist and they are not interchangeable:
 *
 *   reportDate   typed into the upload form
 *   printedDate  read off the document itself (only when it could be READ)
 *   chronoDate   the sort key: typed, else printed, else the upload clock
 *
 * Found 2026-09-24: two reports that both PRINT 05-Sep-2026 were typed as the
 * 9th and the 11th, and the comparison called them "2 days apart" with
 * nothing on screen saying the documents disagreed. The typed date still wins
 * -- a reader may date a report by collection on purpose -- but when the two
 * disagree the page SAYS so rather than settling it silently.
 *
 * ONE HELPER FOR THE REPORTS LIST AND THE COMPARISON PICKER, so the two cannot
 * come to describe the same report differently.
 *
 * CALENDAR DAYS ARE SHOWN IN UTC. Both typed and printed dates are stored at
 * UTC midnight of their day; formatting one in a time zone west of UTC would
 * print the day before. The upload clock is a real instant and is shown in
 * the reader's own zone.
 */

const usable = (value) => {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
};

/** A calendar day (typed or printed), formatted as that day everywhere. */
export function calendarDay(value) {
  const date = usable(value);
  return date ? date.toLocaleDateString(undefined, { timeZone: 'UTC' }) : null;
}

/**
 * @returns {{
 *   shown: string|null,              the date to print, or null
 *   source: 'typed'|'printed'|'uploaded'|null,
 *   printedDisagrees: string|null,   the document's own date, when it differs
 *                                    from the typed one
 *   printedStatus: string|null,      read | ambiguous | unreadable | absent,
 *                                    or null when nobody has looked
 *   printedRaw: string|null,         the unreadable text, when sent
 * }}
 */
export function reportDateInfo(entry) {
  const typed = usable(entry?.reportDate);
  const printed = usable(entry?.printedDate);
  const sortKey = usable(entry?.chronoDate);
  const printedStatus = entry?.printedDateStatus || null;
  const printedRaw = entry?.printedDateRaw || null;

  if (typed) {
    const differs = printed && printed.getTime() !== typed.getTime();
    return {
      shown: calendarDay(typed),
      source: 'typed',
      printedDisagrees: differs ? calendarDay(printed) : null,
      printedStatus,
      printedRaw,
    };
  }
  if (printed) {
    return { shown: calendarDay(printed), source: 'printed', printedDisagrees: null, printedStatus, printedRaw };
  }
  return {
    shown: sortKey ? sortKey.toLocaleDateString() : null,
    source: sortKey ? 'uploaded' : null,
    printedDisagrees: null,
    printedStatus,
    printedRaw,
  };
}

/** Why a report with no usable date is ordered by its upload day. */
export function whyUploadDate(info) {
  const quoted = info.printedRaw ? `“${info.printedRaw}”` : 'a date';
  switch (info.printedStatus) {
    case 'ambiguous':
      return `The report prints ${quoted}, which could be read day-first or month-first, and none was given, so it is ordered by when it was uploaded.`;
    case 'unreadable':
      return `The report prints ${quoted}, which could not be read as a date, and none was given, so it is ordered by when it was uploaded.`;
    case 'absent':
      return 'The report prints no date and none was given, so it is ordered by when it was uploaded.';
    default:
      return 'No date was given for this report, so it is ordered by when it was uploaded.';
  }
}
