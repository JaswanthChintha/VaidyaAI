'use strict';


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
    const changes = await backfillPrintedDates({ apply, log: (line) => console.log(line) });
    console.log(`${changes.length} report(s) ${apply ? 'updated' : 'would be updated (dry run; pass --apply)'}`);
  } finally {
    await disconnectDatabase();
  }
}

if (require.main === module) {
  main().catch((err) => {
    console.error(err.message);
    process.exit(1);
  });
}

module.exports = { backfillPrintedDates };
