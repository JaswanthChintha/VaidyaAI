const usable = (value) => {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
};

export function calendarDay(value) {
  const date = usable(value);
  return date ? date.toLocaleDateString(undefined, { timeZone: 'UTC' }) : null;
}

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
