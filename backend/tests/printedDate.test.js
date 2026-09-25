'use strict';

/**
 * The date a report PRINTS -- read, or declared unreadable, never guessed.
 *
 * Found 2026-09-24: extraction returned `report_metadata.report_date` on every
 * report and nothing read it, so two reports printing `05-Sep-2026 17:40` were
 * compared as "9 September to 11 September, 2 days apart" -- the dates typed
 * at upload. See `src/utils/printedDate.js`.
 */

const mongoose = require('mongoose');

const Report = require('../src/models/Report');
const { deriveChronoDate } = require('../src/models/Report');
const { parsePrintedDate, printedDateText, STATUS } = require('../src/utils/printedDate');
const { backfillPrintedDates } = require('../scripts/backfillPrintedDates');

const day = (s) => new Date(`${s}T00:00:00.000Z`).getTime();
const read = (raw, options) => parsePrintedDate(raw, options);

describe('parsePrintedDate -- what is read', () => {
  it.each([
    ['05-Sep-2026 17:40', '2026-09-05'], // the synthetic fixtures, exactly
    ['5 September 2026', '2026-09-05'],
    ['05 Sep, 2026', '2026-09-05'],
    ['Sep 5, 2026', '2026-09-05'],
    ['September 05 2026', '2026-09-05'],
    ['5th Sep 2026', '2026-09-05'],
    ['2026-09-05', '2026-09-05'],
    ['2026/09/05', '2026-09-05'],
    ['Reported On: 05-Sep-2026 17:40', '2026-09-05'],
    // Digits, where only one order is a real date.
    ['25/09/2026', '2026-09-25'], // 25 cannot be a month
    ['09/25/2026', '2026-09-25'],
    ['05/05/2026', '2026-05-05'], // both orders are the same day
  ])('%s -> %s', (raw, expected) => {
    const r = read(raw);
    expect(r.status).toBe(STATUS.READ);
    expect(r.date.getTime()).toBe(day(expected));
    expect(r.raw).toBe(raw);
  });
});

describe('parsePrintedDate -- what is refused rather than guessed', () => {
  it('refuses DD/MM against MM/DD when both are real dates', () => {
    // 5 September in India, 9 May in the United States. Four months out of
    // place on a timeline read for trends.
    const r = read('05/09/2026');
    expect(r.status).toBe(STATUS.AMBIGUOUS);
    expect(r.date).toBeNull();
    expect(r.raw).toBe('05/09/2026');
  });

  it('refuses two different dates in one string', () => {
    expect(read('Collected 05-Sep-2026 Reported 06-Sep-2026').status).toBe(STATUS.AMBIGUOUS);
  });

  it('accepts the same date printed twice', () => {
    expect(read('05-Sep-2026 / 2026-09-05').status).toBe(STATUS.READ);
  });

  it.each([
    ['02 Dec, 2X'], // real OCR output on this project (drlogy-hba1c-normal.pdf)
    ['05-Sep-26'], // a century is a guess
    ['31-Feb-2026'], // does not exist
    ['yesterday'],
    ['17:40'],
  ])('%s is unreadable', (raw) => {
    const r = read(raw);
    expect(r.status).toBe(STATUS.UNREADABLE);
    expect(r.date).toBeNull();
  });

  it('refuses a date after the report was uploaded, with a day of slack', () => {
    const uploaded = new Date('2026-09-10T04:00:00.000Z');
    expect(read('11-Sep-2026', { notAfter: uploaded }).status).toBe(STATUS.READ);
    expect(read('12-Sep-2026', { notAfter: uploaded }).status).toBe(STATUS.UNREADABLE);
  });

  it('refuses a date before 1950', () => {
    expect(read('05-Sep-1926').status).toBe(STATUS.UNREADABLE);
  });

  it.each([[null], [undefined], [''], ['   '], [42]])('%p is absent', (raw) => {
    expect(read(raw)).toEqual({ status: STATUS.ABSENT, date: null, raw: null });
  });

  it('keeps at most 64 characters of the raw text', () => {
    expect(read(`${'x'.repeat(100)}`).raw).toHaveLength(64);
  });
});

describe('printedDateText', () => {
  it('reads the extraction field and nothing else', () => {
    expect(printedDateText({ report_metadata: { report_date: '05-Sep-2026' } })).toBe('05-Sep-2026');
    expect(printedDateText({ report_metadata: { report_date: null } })).toBeNull();
    expect(printedDateText({})).toBeNull();
    expect(printedDateText(null)).toBeNull();
  });
});

describe('the sort key: typed, then printed, then uploaded', () => {
  const typed = new Date(day('2026-09-09'));
  const printed = new Date(day('2026-09-05'));
  const uploaded = new Date('2026-09-11T16:25:26.821Z');

  it('deriveChronoDate', () => {
    expect(deriveChronoDate({ reportDate: typed, printedDate: printed, uploadedAt: uploaded })).toBe(typed);
    expect(deriveChronoDate({ printedDate: printed, uploadedAt: uploaded })).toBe(printed);
    expect(deriveChronoDate({ uploadedAt: uploaded })).toBe(uploaded);
  });

  it('the save hook uses the same rule', async () => {
    const doc = await Report.create({
      user: new mongoose.Types.ObjectId(),
      originalName: 'labs.pdf',
      storageKey: `k/${new mongoose.Types.ObjectId()}.pdf`,
      storageDriver: 'local',
      mimeType: 'application/pdf',
      sizeBytes: 10,
      checksumSha256: 'a'.repeat(64),
      uploadedAt: uploaded,
      printedDate: printed,
    });
    expect(doc.chronoDate.getTime()).toBe(printed.getTime());
    doc.reportDate = typed;
    await doc.save();
    expect(doc.chronoDate.getTime()).toBe(typed.getTime());
  });
});

describe('backfillPrintedDates -- from the extraction already stored', () => {
  async function seed({ reportDate, reportDateText, extraction = true, status } = {}) {
    const uploadedAt = new Date('2026-09-11T16:25:26.821Z');
    const doc = await Report.create({
      user: new mongoose.Types.ObjectId(),
      originalName: 'labs.pdf',
      storageKey: `k/${new mongoose.Types.ObjectId()}.pdf`,
      storageDriver: 'local',
      mimeType: 'application/pdf',
      sizeBytes: 10,
      checksumSha256: 'b'.repeat(64),
      uploadedAt,
      reportDate,
      status: 'processed',
      extraction: extraction ? { report_metadata: { report_date: reportDateText } } : undefined,
      printedDateStatus: status,
    });
    return doc._id;
  }

  it('a dry run writes nothing', async () => {
    const id = await seed({ reportDateText: '05-Sep-2026 17:40' });
    const changes = await backfillPrintedDates();
    expect(changes).toHaveLength(1);
    const stored = await Report.findById(id).lean();
    expect(stored.printedDateStatus).toBeUndefined();
    expect(stored.chronoDate.toISOString()).toBe('2026-09-11T16:25:26.821Z');
  });

  it('--apply sets the printed date and moves the sort key when nothing was typed', async () => {
    const id = await seed({ reportDateText: '05-Sep-2026 17:40' });
    await backfillPrintedDates({ apply: true });
    const stored = await Report.findById(id).lean();
    expect(stored.printedDateStatus).toBe('read');
    expect(stored.printedDate.toISOString()).toBe('2026-09-05T00:00:00.000Z');
    expect(stored.chronoDate.toISOString()).toBe('2026-09-05T00:00:00.000Z');
  });

  it('keeps a typed date as the sort key and reports the disagreement', async () => {
    const id = await seed({ reportDate: new Date(day('2026-09-09')), reportDateText: '05-Sep-2026 17:40' });
    const [change] = await backfillPrintedDates({ apply: true });
    expect(change.typedDisagrees).toBe(true);
    const stored = await Report.findById(id).lean();
    expect(stored.chronoDate.toISOString()).toBe('2026-09-09T00:00:00.000Z');
    expect(stored.printedDate.toISOString()).toBe('2026-09-05T00:00:00.000Z');
  });

  it('records unreadable text without inventing a date', async () => {
    const id = await seed({ reportDateText: '02 Dec, 2X' });
    await backfillPrintedDates({ apply: true });
    const stored = await Report.findById(id).lean();
    expect(stored.printedDateStatus).toBe('unreadable');
    expect(stored.printedDate).toBeUndefined();
    expect(stored.printedDateRaw).toBe('02 Dec, 2X');
  });

  it('skips reports never analysed, and reports already read -- so a second run is a no-op', async () => {
    await seed({ extraction: false });
    const done = await seed({ reportDateText: '05-Sep-2026', status: 'absent' });
    await seed({ reportDateText: '05-Sep-2026' });

    expect(await backfillPrintedDates({ apply: true })).toHaveLength(1);
    expect(await backfillPrintedDates({ apply: true })).toHaveLength(0);
    // The one already marked was left exactly as it was.
    expect((await Report.findById(done).lean()).printedDateStatus).toBe('absent');
  });
});
