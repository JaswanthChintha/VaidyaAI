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
