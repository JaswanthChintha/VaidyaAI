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

const { buildLabSeries, nameKey, unitKey, numericValue } = require('../src/services/labSeriesService');

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
