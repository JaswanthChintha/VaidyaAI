'use strict';

/**
 * The laboratory's own repeated parameters, over time.
 *
 * ==========================================================================
 * EVERY FIXTURE HERE IS INVENTED ON PURPOSE
 * ==========================================================================
 *
 * Not one of these names is a parameter from this project's real reports. The
 * feature has to work for ANY report carrying ANY parameter this platform
 * does not assess -- there is no list of known tests in the service and there
 * must be none in its tests either, or the suite would pass by recognising
 * the fixtures rather than by the rule working.
 *
 * So: "Zorblex", "Quibblease", "Frimbulator". If the implementation ever
 * starts depending on knowing what a test IS, these break.
 */

const {
  buildLabSeries,
  nameKey,
  unitKey,
  numericValue,
  numericBound,
  classifiableSeries,
  attachVerdicts,
  unjoinedNames,
  aliasMap,
  buildLabComparison,
} = require('../src/services/labSeriesService');

/** A history snapshot in `historyService`'s own shape. */
const snap = (date, unmapped, reportId = `r-${date}`) => ({
  report_id: reportId,
  chrono_date: `${date}T00:00:00.000Z`,
  validated: { unmapped },
});

const row = (test_name, value_raw, unit) => ({ test_name, value_raw, unit });

describe('labSeriesService - names', () => {
  it('matches the same words in any order', () => {
    // THE DEFECT THIS EXISTS FOR, in an invented vocabulary: one laboratory
    // prints "ZBX (ZORBLEX FACTOR)" and the next "ZORBLEX FACTOR(ZBX)". Same
    // test, same words, different arrangement -- and before this they were two
    // different parameters, each seen once, so neither made a series.
    const out = buildLabSeries([
      snap('2026-01-01', [row('ZBX (ZORBLEX FACTOR)', '12.1', 'mg/L')]),
      snap('2026-02-01', [row('ZORBLEX FACTOR(ZBX)', '38.9', 'mg/L')]),
    ]);

    expect(out.series).toHaveLength(1);
    expect(out.series[0].points.map((p) => p.value)).toEqual([12.1, 38.9]);
  });

  it('matches across case and punctuation', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Quibblease count', '2.60', 'Lakhs/Cumm')]),
      snap('2026-02-01', [row('QUIBBLEASE COUNT', '3.03', 'Lakhs/cumm')]),
    ]);
    expect(out.series).toHaveLength(1);
    expect(out.series[0].points).toHaveLength(2);
  });

  it('does NOT match a name with an extra word', () => {
    // The line between set equality and guessing. "Free Frimbulator" is not
    // "Frimbulator", and a file that decided otherwise would be inventing an
    // identity -- the class of guess that has produced three defects here.
    const out = buildLabSeries([
      snap('2026-01-01', [row('Frimbulator', '1', 'U/L')]),
      snap('2026-02-01', [row('Free Frimbulator', '2', 'U/L')]),
    ]);
    expect(out.series).toHaveLength(0);
    expect(out.singleReportCount).toBe(2);
  });

  it('keeps repeated words, so two names are not collapsed by chance', () => {
    expect(nameKey('total total protein')).not.toBe(nameKey('total protein'));
  });

  it('labels the series with the MOST RECENT spelling', () => {
    // The reader is holding the newest report.
    const out = buildLabSeries([
      snap('2026-01-01', [row('ZBX (ZORBLEX FACTOR)', '1', 'mg/L')]),
      snap('2026-02-01', [row('ZORBLEX FACTOR(ZBX)', '2', 'mg/L')]),
    ]);
    expect(out.series[0].name).toBe('ZORBLEX FACTOR(ZBX)');
  });
});

describe('labSeriesService - units', () => {
  it('BLOCKS a series whose reports disagree about the unit', () => {
    // Two scales on one axis is the failure 6z already caught. The series
    // still exists and still carries its readings; it simply draws no line.
    const out = buildLabSeries([
      snap('2026-01-01', [row('Frimbulator', '101.9', 'U/L')]),
      snap('2026-02-01', [row('Frimbulator', '13', 'IU/L')]),
    ]);

    expect(out.series).toHaveLength(1);
    const s = out.series[0];
    expect(s.blocked).not.toBeNull();
    expect(s.blocked.reason).toBe('units_differ');
    expect(s.blocked.units.sort()).toEqual(['IU/L', 'U/L']);
    expect(s.unit).toBeNull();
    // NOT DROPPED. The values are still there to be shown.
    expect(s.points.map((p) => p.value)).toEqual([101.9, 13]);
    expect(out.blockedCount).toBe(1);
    expect(out.plottedCount).toBe(0);
  });

  it('treats the same unit written differently as the same unit', () => {
    // Case and spacing only -- "fL" and "fl" are one unit typed twice.
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex volume', '85.1', 'fL')]),
      snap('2026-02-01', [row('Zorblex volume', '88.6', 'fl ')]),
    ]);
    expect(out.series[0].blocked).toBeNull();
    expect(out.plottedCount).toBe(1);
  });

  it('does not decide that two DIFFERENT units are equal', () => {
    // g/dL and % are numerically close for some tests and are not the same
    // quantity. This file knows no equivalences at all, deliberately.
    const out = buildLabSeries([
      snap('2026-01-01', [row('Quibblease concentration', '30.8', 'g/dL')]),
      snap('2026-02-01', [row('Quibblease concentration', '33.0', '%')]),
    ]);
    expect(out.series[0].blocked.reason).toBe('units_differ');
  });
});

describe('labSeriesService - what is not a series', () => {
  it('needs two reports, and says how many had only one', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '1', 'U/L'), row('Frimbulator', '2', 'U/L')]),
      snap('2026-02-01', [row('Zorblex', '3', 'U/L')]),
    ]);
    expect(out.series.map((s) => s.name)).toEqual(['Zorblex']);
    expect(out.singleReportCount).toBe(1);
    expect(out.consideredCount).toBe(2);
  });

  it('needs two NUMERIC readings', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', 'Not Detected', null)]),
      snap('2026-02-01', [row('Zorblex', 'Trace', null)]),
    ]);
    expect(out.series).toHaveLength(0);
    expect(out.notNumericCount).toBe(1);
  });

  it('reads a thousands separator, and nothing else', () => {
    expect(numericValue('7,290')).toBe(7290);
    expect(numericValue('12.1')).toBe(12.1);
    expect(numericValue('< 5')).toBeNull();
    expect(numericValue('Not Detected')).toBeNull();
    expect(numericValue('')).toBeNull();
  });

  it('carries NO direction and NO classification, ever', () => {
    // There is no polarity for these parameters and no stability band. A
    // direction word here would be this platform interpreting a test it does
    // not assess.
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '1', 'U/L')]),
      snap('2026-02-01', [row('Zorblex', '99', 'U/L')]),
    ]);
    const s = out.series[0];
    expect(s.trend).toBeUndefined();
    expect(s.direction).toBeUndefined();
    expect(s.outcome).toBeUndefined();
    expect(JSON.stringify(s)).not.toMatch(/worsening|improving|stable|rising|falling/i);
  });
});

/**
 * THE PRINTED REFERENCE INTERVAL, WHICH SETS THE SCALE AND NOTHING ELSE.
 *
 * The shapes here are the ones the real reports produced, in the invented
 * vocabulary: two laboratories printing different ranges for the same test
 * (nine of ten parameters on this project's own reports), a one-sided range
 * (`< 6 mg/l` -> a high and no low), and a range that extracted to no numbers
 * at all (`F: 36 - 46 M: 40 - 50`, which cannot be reduced to one pair
 * without knowing whose report it is).
 */
const printedFor = (byReport) =>
  new Map(
    Object.entries(byReport).map(([reportId, rows]) => [
      reportId,
      new Map(rows.map((r) => [r.test_name, r])),
    ])
  );

const ref = (test_name, reference_low, reference_high, reference_range_raw = null) => ({
  test_name,
  reference_low,
  reference_high,
  reference_range_raw,
});

describe('labSeriesService - the printed reference interval', () => {
  it('joins per report and by the EXACT printed name, so two spellings both match', () => {
    // The join that makes this work across reports: `Zorblex` is looked up in
    // its own report and `ZORBLEX` in its own. Neither has to know about the
    // other -- that they are the same TEST is nameKey's separate job.
    const out = buildLabSeries(
      [
        snap('2026-01-01', [row('Zorblex', '15', '%')], 'r1'),
        snap('2026-02-01', [row('ZORBLEX', '14', '%')], 'r2'),
      ],
      printedFor({
        r1: [ref('Zorblex', 22, 45, '22-45')],
        r2: [ref('ZORBLEX', 20, 40, '20-40')],
      })
    );

    const s = out.series[0];
    expect(s.points.map((p) => [p.labReferenceLow, p.labReferenceHigh])).toEqual([
      [22, 45],
      [20, 40],
    ]);
  });

  it('takes the UNION when the two reports disagree about the range', () => {
    // There is no single interval, and preferring one laboratory's would be
    // asserting its assay applies to the other's reading. 22-45 and 20-40
    // become 20-45: at least as wide as either, so nothing is excluded that
    // one of the reader's own documents called usual.
    const out = buildLabSeries(
      [
        snap('2026-01-01', [row('Zorblex', '15', '%')], 'r1'),
        snap('2026-02-01', [row('ZORBLEX', '14', '%')], 'r2'),
      ],
      printedFor({
        r1: [ref('Zorblex', 22, 45)],
        r2: [ref('ZORBLEX', 20, 40)],
      })
    );

    expect(out.series[0].referenceScale).toEqual({ low: 20, high: 45 });
    expect(out.series[0].referenceAgreement).toBe('differ');
  });

  it('keeps a one-sided range one-sided instead of inventing the other half', () => {
    // `< 6 mg/l` is a high and no low. A fabricated zero would put a number
    // on the scale that no laboratory printed.
    const out = buildLabSeries(
      [
        snap('2026-01-01', [row('Quibblease', '12.1', 'mg/L')], 'r1'),
        snap('2026-02-01', [row('Quibblease', '38.9', 'mg/L')], 'r2'),
      ],
      printedFor({
        r1: [ref('Quibblease', null, 6, '< 6 mg/l')],
        r2: [ref('Quibblease', null, 5, '< 5.0')],
      })
    );

    expect(out.series[0].referenceScale).toEqual({ low: null, high: 6 });
  });

  it('reads NO bound from a range that extracted to no numbers, and keeps the text', () => {
    // A sex-specific interval. The extraction deliberately declined to pick a
    // pair; parsing the string here would be undoing that decision.
    const out = buildLabSeries(
      [
        snap('2026-01-01', [row('Frimbulator', '34.4', '%')], 'r1'),
        snap('2026-02-01', [row('Frimbulator', '37.9', '%')], 'r2'),
      ],
      printedFor({
        r1: [ref('Frimbulator', 35, 48, '35-48')],
        r2: [ref('Frimbulator', null, null, 'F: 36 - 46 M: 40 - 50')],
      })
    );

    const s = out.series[0];
    expect(s.points[1].labReferenceLow).toBeNull();
    expect(s.points[1].labReferenceHigh).toBeNull();
    expect(s.points[1].labReferenceRaw).toBe('F: 36 - 46 M: 40 - 50');
    // One opinion and a silence is NOT agreement.
    expect(s.referenceAgreement).toBe('differ');
    expect(s.referenceCoverage).toEqual({ withBounds: 1, total: 2 });
  });

  it('says `agree` only when EVERY point carries the same bounds', () => {
    const out = buildLabSeries(
      [
        snap('2026-01-01', [row('Zorblex', '35', 'mm/hr')], 'r1'),
        snap('2026-02-01', [row('Zorblex', '45', 'mm/hr')], 'r2'),
      ],
      printedFor({
        r1: [ref('Zorblex', 0, 20, '00 - 20')],
        r2: [ref('Zorblex', 0, 20, '0 - 20')],
      })
    );

    expect(out.series[0].referenceAgreement).toBe('agree');
    expect(out.series[0].referenceScale).toEqual({ low: 0, high: 20 });
  });

  it('says `none`, and gives no scale, when no report printed a range', () => {
    const out = buildLabSeries(
      [
        snap('2026-01-01', [row('Zorblex', '1', 'U/L')], 'r1'),
        snap('2026-02-01', [row('Zorblex', '2', 'U/L')], 'r2'),
      ],
      printedFor({ r1: [ref('Zorblex', null, null)], r2: [ref('Zorblex', null, null)] })
    );

    expect(out.series[0].referenceAgreement).toBe('none');
    expect(out.series[0].referenceScale).toBeNull();
    expect(out.scaledCount).toBe(0);
  });

  it('never parses a range out of a string bound', () => {
    // Module 4 already decided what the printed text means. A string arriving
    // in a numeric field is a contract violation, not an invitation to parse.
    expect(numericBound('22')).toBeNull();
    expect(numericBound(22)).toBe(22);
    expect(numericBound(null)).toBeNull();
    expect(numericBound(Number.NaN)).toBeNull();
    expect(numericBound(undefined)).toBeNull();
  });

  it('gives a BLOCKED series no scale, so a mixed-unit union cannot be handed on', () => {
    // Two units means two scales, and adding their intervals together would
    // be the failure the blocking rule exists to prevent.
    const out = buildLabSeries(
      [
        snap('2026-01-01', [row('Zorblex', '101.9', 'U/L')], 'r1'),
        snap('2026-02-01', [row('Zorblex', '13', 'IU/L')], 'r2'),
      ],
      printedFor({
        r1: [ref('Zorblex', null, 40, 'UP TO 40')],
        r2: [ref('Zorblex', 5, 40, '5 - 40')],
      })
    );

    expect(out.series[0].blocked).not.toBeNull();
    expect(out.series[0].referenceScale).toBeNull();
    // The per-point facts are still carried; only the union is withheld.
    expect(out.series[0].points[1].labReferenceLow).toBe(5);
  });

  it('counts only PLOTTED series in scaledCount', () => {
    const out = buildLabSeries(
      [
        snap('2026-01-01', [row('Zorblex', '1', 'U/L'), row('Quibblease', '5', 'mg/L')], 'r1'),
        snap('2026-02-01', [row('Zorblex', '2', 'IU/L'), row('Quibblease', '6', 'mg/L')], 'r2'),
      ],
      printedFor({
        r1: [ref('Zorblex', 0, 40), ref('Quibblease', 1, 9)],
        r2: [ref('Zorblex', 0, 40), ref('Quibblease', 1, 9)],
      })
    );

    // Zorblex is blocked on units; only Quibblease is drawn and scaled.
    expect(out.blockedCount).toBe(1);
    expect(out.scaledCount).toBe(1);
  });

  it('degrades to NO scale, never a wrong one, when the caller supplies nothing', () => {
    // An older caller -- or one whose extraction query found nothing -- gets
    // exactly the behaviour this page had before the scale existed.
    for (const printed of [undefined, null, new Map(), printedFor({ other: [] })]) {
      const out = buildLabSeries(
        [
          snap('2026-01-01', [row('Zorblex', '1', 'U/L')], 'r1'),
          snap('2026-02-01', [row('Zorblex', '2', 'U/L')], 'r2'),
        ],
        printed
      );
      expect(out.series[0].referenceScale).toBeNull();
      expect(out.series[0].referenceAgreement).toBe('none');
      expect(out.scaledCount).toBe(0);
    }
  });

  it('leaves a point unbounded when the extraction spells the name differently', () => {
    // Not assumed away: the point simply has no bound and the coverage count
    // says so, rather than borrowing the other report's range.
    const out = buildLabSeries(
      [
        snap('2026-01-01', [row('Zorblex', '1', 'U/L')], 'r1'),
        snap('2026-02-01', [row('Zorblex', '2', 'U/L')], 'r2'),
      ],
      printedFor({ r1: [ref('Zorblex', 0, 5)], r2: [ref('Zorblex (total)', 0, 5)] })
    );

    expect(out.series[0].referenceCoverage).toEqual({ withBounds: 1, total: 2 });
    expect(out.series[0].points[1].labReferenceLow).toBeNull();
  });
});

/**
 * THE PARAMETERS THAT CANNOT MAKE A SERIES ARE STILL ON THE REPORT.
 *
 * A reader holding two reports with 22 parameters between them saw twelve
 * panels and a line saying twenty-two had been "considered". They asked where
 * the rest were, which is the right question: a count of what was looked at is
 * not an answer about what was found.
 *
 * These carry readings and dates and NOTHING ELSE -- no line, no direction, no
 * scale. "We cannot draw this" is not a reason to withhold the laboratory's
 * own number.
 */
describe('labSeriesService - readings that cannot be trended', () => {
  it('lists a parameter seen on only ONE report instead of only counting it', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '3.51', 'ulU/mL')], 'r1'),
      snap('2026-02-01', [row('Quibblease', '1.81', 'mg/L')], 'r2'),
    ]);

    // Still counted, exactly as before -- the count did not become wrong.
    expect(out.singleReportCount).toBe(2);
    // AND now visible.
    expect(out.readings.map((r) => r.name)).toEqual(['Quibblease', 'Zorblex']);
    expect(out.readings[1].rows).toEqual([
      expect.objectContaining({ valueRaw: '3.51', unit: 'ulU/mL', value: 3.51 }),
    ]);
    expect(out.readings[1].reason).toBe('one_report');
  });

  it('shows a NON-NUMERIC result as the laboratory printed it', () => {
    // "Negative" is a result. Rendering it as a missing value, or as nothing,
    // is this file's standing failure mode: an absence that reads as though
    // there were nothing there.
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', 'Pale Yellow', null)], 'r1'),
      snap('2026-02-01', [row('Zorblex', 'Negative', null)], 'r2'),
    ]);

    expect(out.notNumericCount).toBe(1);
    expect(out.readings).toHaveLength(1);
    expect(out.readings[0].reason).toBe('not_numeric');
    expect(out.readings[0].rows.map((r) => r.valueRaw)).toEqual(['Pale Yellow', 'Negative']);
    // A value that is not a number is not given one.
    expect(out.readings[0].rows.every((r) => r.value === null)).toBe(true);
  });

  it('gives a reading NO line, NO direction and NO scale', () => {
    // The whole point of keeping these out of `series`: nothing downstream
    // can draw a trend through a single point or an unordered word.
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '3.51', 'mg/L')], 'r1'),
      snap('2026-02-01', [row('Quibblease', '1.81', 'mg/L')], 'r2'),
    ]);

    expect(out.series).toHaveLength(0);
    for (const reading of out.readings) {
      expect(reading.referenceScale).toBeUndefined();
      expect(reading.blocked).toBeUndefined();
      expect(reading.points).toBeUndefined();
    }
  });

  it('never lists a parameter that DID make a series', () => {
    // Otherwise the same test appears twice on one page, once as a chart and
    // once as a reading, which reads as two different tests.
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '1', 'U/L')], 'r1'),
      snap('2026-02-01', [row('Zorblex', '2', 'U/L')], 'r2'),
    ]);

    expect(out.series).toHaveLength(1);
    expect(out.readings).toHaveLength(0);
  });

  it('lists a BLOCKED series nowhere either -- it already shows its readings', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '101.9', 'U/L')], 'r1'),
      snap('2026-02-01', [row('Zorblex', '13', 'IU/L')], 'r2'),
    ]);

    expect(out.blockedCount).toBe(1);
    expect(out.readings).toHaveLength(0);
  });

  it('accounts for EVERY considered parameter, in one bucket or another', () => {
    // The identity a reader is entitled to: nothing looked at is unaccounted
    // for. considered === plotted + blocked + listed.
    const out = buildLabSeries([
      snap('2026-01-01', [
        row('Zorblex', '1', 'U/L'),
        row('Quibblease', '101.9', 'U/L'),
        row('Frimbulator', '5', 'mg/L'),
        row('Snarflax', 'Negative', null),
      ], 'r1'),
      snap('2026-02-01', [
        row('Zorblex', '2', 'U/L'),
        row('Quibblease', '13', 'IU/L'),
        row('Snarflax', 'Negative', null),
      ], 'r2'),
    ]);

    expect(out.consideredCount).toBe(4);
    expect(out.plottedCount + out.blockedCount + out.readings.length).toBe(
      out.consideredCount
    );
  });
});

/**
 * THE STATUS A PARAMETER THIS PLATFORM DOES NOT ASSESS IS ALLOWED TO CARRY.
 *
 * A reader asked why these panels showed no status when the assessed ones say
 * improving, worsening or stable. Those three cannot be said here -- two need
 * polarity and one needs a stability band, and neither exists for a test this
 * platform does not assess. What IS available is arithmetic on the reader's
 * own numbers, and the laboratory's own marking.
 */
describe('labSeriesService - movement and the laboratory\'s marking', () => {
  const flagged = (test_name, value_raw, unit, flag) => ({ test_name, value_raw, unit, flag });

  it('says which way the numbers went, and never a clinical word', () => {
    const rising = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '12.1', 'mg/L')], 'r1'),
      snap('2026-02-01', [row('Zorblex', '38.9', 'mg/L')], 'r2'),
    ]);
    const falling = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '38.9', 'mg/L')], 'r1'),
      snap('2026-02-01', [row('Zorblex', '12.1', 'mg/L')], 'r2'),
    ]);
    const flat = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '0', '%')], 'r1'),
      snap('2026-02-01', [row('Zorblex', '0', '%')], 'r2'),
    ]);

    expect(rising.series[0].movement).toBe('rose');
    expect(falling.series[0].movement).toBe('fell');
    expect(flat.series[0].movement).toBe('same');

    // THE GUARD THIS MODULE EXISTS FOR. None of the three clinical words may
    // ever appear, under any key.
    for (const out of [rising, falling, flat]) {
      expect(JSON.stringify(out)).not.toMatch(/improving|worsening|stable/i);
    }
  });

  it('withholds movement from a BLOCKED series', () => {
    // 101.9 U/L and 13 IU/L may be the same measurement twice. Saying "fell"
    // would assert a change the same file refused to draw a line through.
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '101.9', 'U/L')], 'r1'),
      snap('2026-02-01', [row('Zorblex', '13', 'IU/L')], 'r2'),
    ]);

    expect(out.series[0].blocked).not.toBeNull();
    expect(out.series[0].movement).toBeNull();
  });

  it('carries the two readings the movement word is about', () => {
    // The collapsed row prints these beside the word. They come from the same
    // comparison that produced it, so the two cannot disagree.
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '12.1', 'mg/L')], 'r1'),
      snap('2026-02-01', [row('Zorblex', '20.0', 'mg/L')], 'r2'),
      snap('2026-03-01', [row('Zorblex', '38.9', 'mg/L')], 'r3'),
    ]);

    // FIRST AND LATEST, never first and second.
    expect(out.series[0].movement).toBe('rose');
    expect(out.series[0].movementFrom).toBe(12.1);
    expect(out.series[0].movementTo).toBe(38.9);
  });

  it('carries a pair of zeroes rather than treating 0 as absent', () => {
    // BASOPHILS is 0 on both of this account's real reports. A zero dropped
    // as "missing" would put an empty pair beside the word "same".
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '0', '%')], 'r1'),
      snap('2026-02-01', [row('Zorblex', '0', '%')], 'r2'),
    ]);

    expect(out.series[0].movement).toBe('same');
    expect(out.series[0].movementFrom).toBe(0);
    expect(out.series[0].movementTo).toBe(0);
  });

  it('withholds the PAIR from a blocked series, not only the word', () => {
    // 101.9 U/L and 13 IU/L beside each other with an arrow between them
    // would assert the comparison this file refused to draw -- the word being
    // absent is not enough if the numbers still claim it.
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '101.9', 'U/L')], 'r1'),
      snap('2026-02-01', [row('Zorblex', '13', 'IU/L')], 'r2'),
    ]);

    expect(out.series[0].movementFrom).toBeNull();
    expect(out.series[0].movementTo).toBeNull();
  });

  it('carries the laboratory\'s marking for the LATEST reading', () => {
    const out = buildLabSeries(
      [
        snap('2026-01-01', [flagged('Zorblex', '35', 'mm/hr', 'high')], 'r1'),
        snap('2026-02-01', [flagged('Zorblex', '45', 'mm/hr', 'high')], 'r2'),
      ],
      printedFor({
        r1: [{ test_name: 'Zorblex', flag: 'high' }],
        r2: [{ test_name: 'Zorblex', flag: 'high' }],
      })
    );

    expect(out.series[0].latestFlag).toBe('high');
    expect(out.series[0].points.map((p) => p.labFlag)).toEqual(['high', 'high']);
  });

  it('does NOT reach back for an older marking when the latest report has none', () => {
    // PCV is the real case: the older report marked it low and the newer
    // marked nothing. Presenting the older verdict as the current status
    // would be a stale claim about the reading in the reader's hand.
    const out = buildLabSeries(
      [
        snap('2026-01-01', [row('Zorblex', '34.4', '%')], 'r1'),
        snap('2026-02-01', [row('Zorblex', '37.9', '%')], 'r2'),
      ],
      printedFor({
        r1: [{ test_name: 'Zorblex', flag: 'low' }],
        r2: [{ test_name: 'Zorblex', flag: null }],
      })
    );

    expect(out.series[0].points[0].labFlag).toBe('low');
    expect(out.series[0].latestFlag).toBeNull();
  });

  it('gives a listed reading its marking too, and no movement', () => {
    const out = buildLabSeries(
      [snap('2026-01-01', [row('Zorblex', '3.51', 'ulU/mL')], 'r1')],
      printedFor({ r1: [{ test_name: 'Zorblex', flag: 'normal' }] })
    );

    expect(out.readings[0].latestFlag).toBe('normal');
    expect(out.readings[0].movement).toBeUndefined();
  });

  it('leaves the marking null when the caller supplied no printed parameters', () => {
    // Null is "not checked". It must never arrive as "normal", which is a
    // laboratory saying it looked and the value was in range.
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '1', 'U/L')], 'r1'),
      snap('2026-02-01', [row('Zorblex', '2', 'U/L')], 'r2'),
    ]);

    expect(out.series[0].latestFlag).toBeNull();
    expect(out.series[0].points.every((p) => p.labFlag === null)).toBe(true);
  });
});

/**
 * MODULE 35'S VERDICTS, ATTACHED TO THE SERIES THEY BELONG TO.
 *
 * The classification itself happens in the ai-service, using Module 28's own
 * classifier. This half is only about which verdict lands on which panel, and
 * what happens when one does not arrive -- which, on a free-tier key, is the
 * common case rather than the edge case.
 */
describe('labSeriesService - attaching a trend verdict', () => {
  const twoReports = () =>
    buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '12.1', 'mg/L')], 'r1'),
      snap('2026-02-01', [row('Zorblex', '38.9', 'mg/L')], 'r2'),
    ]);

  it('sends only series that CAN be classified, with the lab\'s own interval', () => {
    const built = buildLabSeries(
      [
        snap('2026-01-01', [row('Zorblex', '15', '%'), row('Quibblease', '1', 'U/L')], 'r1'),
        snap('2026-02-01', [row('Zorblex', '14', '%'), row('Quibblease', '2', 'IU/L')], 'r2'),
      ],
      printedFor({
        r1: [ref('Zorblex', 22, 45), ref('Quibblease', 0, 40)],
        r2: [ref('Zorblex', 20, 40), ref('Quibblease', 0, 40)],
      })
    );

    const outbound = classifiableSeries(built);
    // Quibblease is blocked on units: two units have not been shown to have
    // moved at all, so there is no change to classify.
    expect(outbound.map((s) => s.test_name)).toEqual(['Zorblex']);
    expect(outbound[0]).toEqual(
      expect.objectContaining({
        first_value: 15,
        last_value: 14,
        reference_low: 20,
        reference_high: 45,
      })
    );
  });

  it('attaches a classified verdict to the matching series', () => {
    const out = attachVerdicts(twoReports(), [
      {
        test_name: 'Zorblex',
        outcome: 'TREND_CLASSIFIED',
        trend: 'worsening',
        significant_change_pct: 57,
        basis: 'RCV = ...',
      },
    ]);

    expect(out.series[0].trend).toBe('worsening');
    expect(out.series[0].classified).toBe(true);
    expect(out.series[0].significantChangePct).toBe(57);
    expect(out.classifiedCount).toBe(1);
  });

  it('branches on OUTCOME, never on the presence of a trend word', () => {
    // A payload carrying a direction without a classification is a
    // contradiction, and §6z rendered the string "null" as a direction once
    // on exactly this mistake. The unclassified reading wins.
    const out = attachVerdicts(twoReports(), [
      {
        test_name: 'Zorblex',
        outcome: 'CLINICAL_DIRECTION_UNKNOWN',
        trend: 'worsening',
      },
    ]);

    expect(out.series[0].trend).toBeUndefined();
    expect(out.series[0].classified).toBeUndefined();
  });

  it('leaves the series untouched when no verdict arrives', () => {
    // THE DESIGNED DEGRADATION. A spent quota, an unconfigured key and a
    // service that is down all land here, and the panel keeps the movement
    // word it already had.
    for (const verdicts of [undefined, null, [], [{}], [{ test_name: 'Other' }]]) {
      const out = attachVerdicts(twoReports(), verdicts);
      expect(out.series[0].trend).toBeUndefined();
      expect(out.series[0].movement).toBe('rose');
    }
  });

  it('never lands one test\'s verdict on another test\'s panel', () => {
    // The worst failure this feature can have. Matched on the exact name that
    // was sent; nothing is normalised, because a fuzzy match here would be
    // silent and wrong.
    const out = attachVerdicts(twoReports(), [
      { test_name: 'zorblex', outcome: 'TREND_CLASSIFIED', trend: 'improving' },
      { test_name: 'Zorblex (total)', outcome: 'TREND_CLASSIFIED', trend: 'improving' },
    ]);

    expect(out.series[0].trend).toBeUndefined();
  });

  it('refuses an empty trend word, which is not a classification', () => {
    const out = attachVerdicts(twoReports(), [
      { test_name: 'Zorblex', outcome: 'TREND_CLASSIFIED', trend: '' },
    ]);
    expect(out.series[0].trend).toBeUndefined();
  });
});

describe('labSeriesService - order', () => {
  it('puts the oldest reading first, whatever order the history arrives in', () => {
    // The history is assembled newest-first. A chart drawn from it unreversed
    // runs backwards.
    const out = buildLabSeries([
      snap('2026-03-01', [row('Zorblex', '3', 'U/L')]),
      snap('2026-01-01', [row('Zorblex', '1', 'U/L')]),
      snap('2026-02-01', [row('Zorblex', '2', 'U/L')]),
    ]);
    expect(out.series[0].points.map((p) => p.value)).toEqual([1, 2, 3]);
  });

  it('orders series by name, not by the order they were read', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '1', 'U/L'), row('Frimbulator', '1', 'U/L')]),
      snap('2026-02-01', [row('Zorblex', '2', 'U/L'), row('Frimbulator', '2', 'U/L')]),
    ]);
    expect(out.series.map((s) => s.name)).toEqual(['Frimbulator', 'Zorblex']);
  });
});

describe('labSeriesService - nothing to do', () => {
  it('answers with an empty result, never a throw', () => {
    for (const input of [undefined, null, [], [snap('2026-01-01', [])], [{}]]) {
      const out = buildLabSeries(input);
      expect(out.series).toEqual([]);
      expect(out.consideredCount).toBe(0);
    }
  });

  it('ignores a snapshot with no date rather than placing it at the epoch', () => {
    const out = buildLabSeries([
      { report_id: 'a', validated: { unmapped: [row('Zorblex', '1', 'U/L')] } },
      snap('2026-02-01', [row('Zorblex', '2', 'U/L')]),
    ]);
    expect(out.series).toHaveLength(0);
  });
});

describe('labSeriesService - the comparison table for unassessed tests', () => {
  const pairOf = (oldRows, newRows) => [
    snap('2026-01-01', oldRows, 'A'),
    snap('2026-02-01', newRows, 'B'),
  ];

  it('compares a parameter both reports carry', () => {
    const built = buildLabSeries(pairOf([row('Zorblex', '12.1', 'mg/L')], [row('Zorblex', '38.9', 'mg/L')]));
    const [only] = buildLabComparison(built, 'A', 'B').rows;

    expect(only.previous).toBe(12.1);
    expect(only.current).toBe(38.9);
    expect(only.symbol).toBe('↑');
    // It moved and nothing declared whether that is better -- which is what
    // `changed_direction_only` means in report_comparator._category.
    expect(only.category).toBe('changed_direction_only');
  });

  it('keeps a parameter that is on only ONE of the two reports', () => {
    // THE WHOLE REASON THIS EXISTS. These were absent from the card, so two
    // reports carrying 28 parameters showed twelve rows.
    const built = buildLabSeries(pairOf([row('OldOnly', '5', '%')], [row('NewOnly', '9', '%')]));
    const rows = buildLabComparison(built, 'A', 'B').rows;

    expect(rows.map((r) => r.name).sort()).toEqual(['NewOnly', 'OldOnly']);
    const old = rows.find((r) => r.name === 'OldOnly');
    expect(old.previous).toBe(5);
    expect(old.current).toBeNull();
    expect(old.category).toBe('not_classifiable');
    expect(old.symbol).toBeNull();
  });

  it('refuses to classify two different units, and carries BOTH of them', () => {
    // 101.9 U/L against 13 IU/L. Hiding one unit would hide the reason the
    // row cannot be classified.
    const built = buildLabSeries(pairOf([row('Zorblex', '101.9', 'U/L')], [row('Zorblex', '13', 'IU/L')]));
    const [only] = buildLabComparison(built, 'A', 'B').rows;

    expect(only.category).toBe('not_classifiable');
    expect(only.symbol).toBeNull();
    expect(only.previousUnit).toBe('U/L');
    expect(only.currentUnit).toBe('IU/L');
    expect(only.unit).toBeNull();
  });

  it("uses Module 29's own words for a Module 35 verdict", () => {
    const built = buildLabSeries(pairOf([row('Zorblex', '12.1', 'mg/L')], [row('Zorblex', '38.9', 'mg/L')]));
    const withVerdict = attachVerdicts(built, [
      { test_name: 'Zorblex', outcome: 'TREND_CLASSIFIED', trend: 'worsening' },
    ]);
    const [only] = buildLabComparison(withVerdict, 'A', 'B').rows;

    // `worsening` on the timeline is `worsened` here. ONE vocabulary per
    // table -- not a third set of words invented for these rows.
    expect(only.category).toBe('worsened');
  });

  it("lets the laboratory's own crossing outrank the change axis", () => {
    // Module 29's documented precedence: a reference-interval crossing is the
    // more consequential fact. This is the LABORATORY's marking, not ours.
    //
    // THE FLAG COMES FROM THE PRINTED EXTRACTION, NOT FROM THE UNMAPPED ROW.
    // The first version of this test put `flag` on the row and asserted on it,
    // and `buildLabSeries` never looks there -- it joins each point to its own
    // report's extraction. The test failed with `previousFlag: null`, which is
    // the producer telling the fixture it was wrong.
    const built = buildLabSeries(
      pairOf([row('Zorblex', '12.1', 'mg/L')], [row('Zorblex', '38.9', 'mg/L')]),
      printedFor({
        A: [{ test_name: 'Zorblex', flag: 'normal' }],
        B: [{ test_name: 'Zorblex', flag: 'high' }],
      })
    );
    const withVerdict = attachVerdicts(built, [
      { test_name: 'Zorblex', outcome: 'TREND_CLASSIFIED', trend: 'stable' },
    ]);
    const [only] = buildLabComparison(withVerdict, 'A', 'B').rows;

    // `stable` would have given `unchanged`. The crossing outranks it.
    expect(only.category).toBe('newly_abnormal');
  });

  it('claims NO crossing when one report marked nothing', () => {
    // PCV is the case that decides it: marked low on the older report and
    // unmarked on the newer. Reading the absence as normal would invent a
    // recovery the laboratory never stated.
    const built = buildLabSeries(
      pairOf([row('Zorblex', '34.4', '%')], [row('Zorblex', '37.9', '%')]),
      printedFor({
        A: [{ test_name: 'Zorblex', flag: 'low' }],
        B: [{ test_name: 'Zorblex' }],
      })
    );
    const [only] = buildLabComparison(built, 'A', 'B').rows;

    expect(only.category).not.toBe('newly_normal');
    expect(only.previousFlag).toBe('low');
    expect(only.currentFlag).toBeNull();
  });

  it('follows the REQUESTED pair, not the date order', () => {
    // The picker allows an out-of-order pair and the card says so. Module 29
    // keys its rows off the requested baseline, so these must too, or one
    // table would have two ideas of which column is "previous".
    const built = buildLabSeries(pairOf([row('Zorblex', '12.1', 'mg/L')], [row('Zorblex', '38.9', 'mg/L')]));
    const [reversed] = buildLabComparison(built, 'B', 'A').rows;

    expect(reversed.previous).toBe(38.9);
    expect(reversed.current).toBe(12.1);
    expect(reversed.symbol).toBe('↓');
  });

  it('carries a non-numeric result as the text the laboratory printed', () => {
    const built = buildLabSeries(
      pairOf([row('Zorblex', 'Negative', null)], [row('Zorblex', 'Negative', null)])
    );
    const [only] = buildLabComparison(built, 'A', 'B').rows;

    expect(only.previousRaw).toBe('Negative');
    expect(only.currentRaw).toBe('Negative');
    expect(only.category).toBe('not_classifiable');
  });

  it('returns nothing rather than throwing when there is nothing to compare', () => {
    expect(buildLabComparison(buildLabSeries([]), 'A', 'B')).toEqual({ rows: [], count: 0 });
    expect(buildLabComparison(undefined, 'A', 'B')).toEqual({ rows: [], count: 0 });
  });
});

describe('labSeriesService - Module 36 name joining', () => {
  // TWO INVENTED NAMES FOR ONE TEST, sharing no words, so `nameKey` cannot
  // join them and only an alias can. The real pair this stands in for is
  // NEUTROPHILS / Polymorphs.
  const twoNames = () => [
    snap('2026-01-01', [row('Zorblex Factor', '12.1', 'mg/L')], 'r1'),
    snap('2026-02-01', [row('Frimbulin', '38.9', 'mg/L')], 'r2'),
  ];

  it('leaves them as two readings when no aliases are supplied', () => {
    // THE DEGRADATION, PINNED FIRST. This is what a spent quota, an
    // unconfigured key and an older caller all get, and it must stay exactly
    // what the endpoint returned before Module 36 existed.
    const out = buildLabSeries(twoNames());

    expect(out.series).toHaveLength(0);
    expect(out.readings).toHaveLength(2);
    expect(out.readings.every((r) => r.joinedFrom === null)).toBe(true);
  });

  it('joins them into one series when an alias says they are one test', () => {
    const aliases = aliasMap([{ names: ['Zorblex Factor', 'Frimbulin'] }]);
    const out = buildLabSeries(twoNames(), undefined, aliases);

    expect(out.readings).toHaveLength(0);
    expect(out.series).toHaveLength(1);
    expect(out.series[0].points.map((p) => p.value)).toEqual([12.1, 38.9]);
    // OLDEST FIRST, and the movement pair with it -- a join must not reorder.
    expect(out.series[0].movement).toBe('rose');
    expect(out.series[0].movementFrom).toBe(12.1);
    expect(out.series[0].movementTo).toBe(38.9);
  });

  it('titles the joined panel with the NEWEST report\'s wording', () => {
    const aliases = aliasMap([{ names: ['Zorblex Factor', 'Frimbulin'] }]);
    const out = buildLabSeries(twoNames(), undefined, aliases);

    // The reader is holding the newer report. A panel titled with the words
    // on it is findable; one titled with the older spelling is not.
    expect(out.series[0].name).toBe('Frimbulin');
  });

  it('says which names it merged, so no join is silent', () => {
    const aliases = aliasMap([{ names: ['Zorblex Factor', 'Frimbulin'] }]);
    const out = buildLabSeries(twoNames(), undefined, aliases);

    // Their report says `Zorblex Factor` and this panel says `Frimbulin`.
    // Without the list that reads as a parameter they never had.
    expect(out.series[0].joinedFrom).toEqual(['Zorblex Factor', 'Frimbulin']);
  });

  it('claims NO join when the group only restates one name', () => {
    // A group of one key aliases nothing, and `joinedFrom` must not announce
    // a merge that did not happen.
    const aliases = aliasMap([{ names: ['Zorblex Factor'] }]);
    expect(aliases.size).toBe(0);

    const out = buildLabSeries(
      [
        snap('2026-01-01', [row('Zorblex Factor', '12.1', 'mg/L')], 'r1'),
        snap('2026-02-01', [row('Zorblex Factor', '38.9', 'mg/L')], 'r2'),
      ],
      undefined,
      aliases
    );
    expect(out.series[0].joinedFrom).toBeNull();
  });

  it('BLOCKS a join that unites two units instead of drawing across them', () => {
    // THE SAFETY NET UNDER A WRONG JOIN. Even if the model were wrong about
    // two names, a series whose units disagree is blocked, gets no scale, no
    // movement word and no pair -- so the worst a bad join can produce is two
    // numbers listed side by side, never a line.
    const aliases = aliasMap([{ names: ['Zorblex Factor', 'Frimbulin'] }]);
    const out = buildLabSeries(
      [
        snap('2026-01-01', [row('Zorblex Factor', '101.9', 'U/L')], 'r1'),
        snap('2026-02-01', [row('Frimbulin', '13', 'IU/L')], 'r2'),
      ],
      undefined,
      aliases
    );

    expect(out.series).toHaveLength(1);
    expect(out.series[0].blocked).not.toBeNull();
    expect(out.series[0].movement).toBeNull();
    expect(out.series[0].movementFrom).toBeNull();
    expect(out.series[0].referenceScale).toBeNull();
  });

  it('offers only the unjoinable names, never the ones already trending', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '1', 'mg/L'), row('Frimbulin', '5', 'mg/L')], 'r1'),
      snap('2026-02-01', [row('Zorblex', '2', 'mg/L'), row('Quixotor', '9', 'mg/L')], 'r2'),
    ]);

    // Zorblex is on both reports and already a series; it is NOT offered for
    // joining, because merging an existing series would redraw a chart the
    // reader has already looked at.
    expect(out.series.map((s) => s.name)).toEqual(['Zorblex']);
    expect(unjoinedNames(out).sort()).toEqual(['Frimbulin', 'Quixotor']);
  });

  it('picks a canonical key by a rule, so two calls agree', () => {
    // `key` reaches React as a list key. A group whose identity depended on
    // the order the model emitted it would remount panels between requests.
    const forwards = aliasMap([{ names: ['Zorblex Factor', 'Frimbulin'] }]);
    const backwards = aliasMap([{ names: ['Frimbulin', 'Zorblex Factor'] }]);

    expect([...forwards.entries()].sort()).toEqual([...backwards.entries()].sort());
  });

  it('keeps a name out of a second group rather than letting it migrate', () => {
    // Module 36 already refuses an overlapping name. If a future producer
    // stops, one test's readings must not land on another test's chart
    // because of emission order.
    const aliases = aliasMap([
      { names: ['Zorblex Factor', 'Frimbulin'] },
      { names: ['Frimbulin', 'Quixotor'] },
    ]);

    expect(aliases.get(nameKey('Frimbulin'))).toBe(aliases.get(nameKey('Zorblex Factor')));
  });
});
