'use strict';

/**
 * ONE-OFF: read the printed date of every report analysed before
 * `printedDate` existed, from the extraction ALREADY STORED on it.
 *
 *   node scripts/backfillPrintedDates.js           # dry run: prints, writes nothing
 *   node scripts/backfillPrintedDates.js --apply   # writes
 *
 * No re-analysis and no model call: `extraction.report_metadata.report_date`
 * has been stored on every analysed report all along; nothing read it. Only
 * reports with an extraction and no `printedDateStatus` are touched, so a
 * second run finds nothing to do.
 *
 * WRITES `chronoDate` TOO, by the model's own `deriveChronoDate`: `updateOne`
 * skips the pre-validate hook, and MEMORY.md records a hand `$set` that left
 * the sort key disagreeing with its inputs for exactly that reason.
 *
 * Prints ids, filenames and dates only -- never a value from the report.
 */

const Report = require('../src/models/Report');
const { deriveChronoDate } = require('../src/models/Report');
const { parsePrintedDate, printedDateText } = require('../src/utils/printedDate');

const day = (d) => (d ? new Date(d).toISOString().slice(0, 10) : '-');

async function backfillPrintedDates({ apply = false, log = () => {} } = {}) {
  const rows = await Report.find({
    printedDateStatus: { $exists: false },
    extraction: { $exists: true, $ne: null },
  })
    .select('+extraction originalName reportDate uploadedAt chronoDate')
    .lean();

  const changes = [];
  for (const row of rows) {
    const printed = parsePrintedDate(printedDateText(row.extraction), {
      notAfter: row.uploadedAt,
    });
    const chronoDate = deriveChronoDate({
      reportDate: row.reportDate,
      printedDate: printed.date,
      uploadedAt: row.uploadedAt,
    });
    const typedDisagrees = Boolean(
      row.reportDate && printed.date && row.reportDate.getTime() !== printed.date.getTime()
    );
    changes.push({ id: String(row._id), status: printed.status, typedDisagrees });
    log(
      `${row._id}  ${row.originalName}  printed=${printed.status}` +
        `${printed.date ? ` ${day(printed.date)}` : ''}  typed=${day(row.reportDate)}` +
        `  chrono ${day(row.chronoDate)} -> ${day(chronoDate)}` +
        `${typedDisagrees ? '  TYPED DATE DISAGREES WITH THE DOCUMENT' : ''}`
    );

    if (!apply) continue;
    const $set = { printedDateStatus: printed.status, chronoDate };
    const $unset = {};
    if (printed.date) $set.printedDate = printed.date;
    else $unset.printedDate = '';
    if (printed.raw) $set.printedDateRaw = printed.raw;
    else $unset.printedDateRaw = '';
    // Conditioned on the field still being absent, so a report re-analysed
    // while this runs keeps what its analysis wrote.
    await Report.updateOne(
      { _id: row._id, printedDateStatus: { $exists: false } },
      Object.keys($unset).length ? { $set, $unset } : { $set }
    );
  }
  return changes;
}

async function main() {
  const apply = process.argv.includes('--apply');
  const { connectDatabase, disconnectDatabase } = require('../src/config/database');
  await connectDatabase();
  try {
    // eslint-disable-next-line no-console
    const changes = await backfillPrintedDates({ apply, log: (line) => console.log(line) });
    // eslint-disable-next-line no-console
    console.log(`${changes.length} report(s) ${apply ? 'updated' : 'would be updated (dry run; pass --apply)'}`);
  } finally {
    await disconnectDatabase();
  }
}

if (require.main === module) {
  main().catch((err) => {
    // eslint-disable-next-line no-console
    console.error(err.message);
    process.exit(1);
  });
}

module.exports = { backfillPrintedDates };
