'use strict';


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

const snap = (date, unmapped, reportId = `r-${date}`) => ({
  report_id: reportId,
  chrono_date: `${date}T00:00:00.000Z`,
  validated: { unmapped },
});

const row = (test_name, value_raw, unit) => ({ test_name, value_raw, unit });

describe('labSeriesService - names', () => {
  it('matches the same words in any order', () => {
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
    const out = buildLabSeries([
      snap('2026-01-01', [row('ZBX (ZORBLEX FACTOR)', '1', 'mg/L')]),
      snap('2026-02-01', [row('ZORBLEX FACTOR(ZBX)', '2', 'mg/L')]),
    ]);
    expect(out.series[0].name).toBe('ZORBLEX FACTOR(ZBX)');
  });
});

describe('labSeriesService - units', () => {
  it('BLOCKS a series whose reports disagree about the unit', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Frimbulator', '101.9', 'U/L')]),
      snap('2026-02-01', [row('Frimbulator', '13', 'U/mL')]),
    ]);

    expect(out.series).toHaveLength(1);
    const s = out.series[0];
    expect(s.blocked).not.toBeNull();
    expect(s.blocked.reason).toBe('units_differ');
    expect(s.blocked.units.sort()).toEqual(['U/L', 'U/mL']);
    expect(s.unit).toBeNull();
    expect(s.points.map((p) => p.value)).toEqual([101.9, 13]);
    expect(out.blockedCount).toBe(1);
    expect(out.plottedCount).toBe(0);
  });

  it('treats the same unit written differently as the same unit', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex volume', '85.1', 'fL')]),
      snap('2026-02-01', [row('Zorblex volume', '88.6', 'fl ')]),
    ]);
    expect(out.series[0].blocked).toBeNull();
    expect(out.plottedCount).toBe(1);
  });

  it('joins a unit the extraction MISREAD, because it is the same unit', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblexin', '3.51', 'ulU/mL')]),
      snap('2026-02-01', [row('Zorblexin', '1.81', 'µIU/mL')]),
    ]);

    expect(out.series[0].blocked).toBeNull();
    expect(out.series[0].movement).toBe('fell');
    expect(out.plottedCount).toBe(1);
    expect(out.series[0].points.map((p) => p.unit)).toEqual(['ulU/mL', 'µIU/mL']);
  });

  it('joins the micro sign with its ASCII substitute', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '4', 'µmol/L')]),
      snap('2026-02-01', [row('Zorblex', '6', 'umol/L')]),
    ]);
    expect(out.series[0].blocked).toBeNull();
  });

  it('still keeps GENUINELY different units apart', () => {
    const pairs = [
      ['mg/L', 'mg/dL'],
      ['U/L', 'U/mL'],
      ['mmol/L', 'µmol/L'],
      ['10^3/µL', '10^6/µL'],
      ['g/dL', '%'],
      ['IU/mL', 'mIU/L'],
    ];

    for (const [first, second] of pairs) {
      expect(unitKey(first)).not.toBe(unitKey(second));
      const out = buildLabSeries([
        snap('2026-01-01', [row('Zorblex', '10', first)]),
        snap('2026-02-01', [row('Zorblex', '20', second)]),
      ]);
      expect(out.series[0].blocked).not.toBeNull();
    }
  });

  it('NEVER folds a digit', () => {
    expect(unitKey('10^3/µL')).toContain('1');
    expect(unitKey('10^3/µL')).not.toBe(unitKey('10^6/µL'));
  });

  it('joins U/L with IU/L, because they are the same quantity', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Frimbulase', '101.9', 'U/L')], 'A'),
      snap('2026-02-01', [row('Frimbulase', '13', 'IU/L')], 'B'),
    ]);

    expect(out.series[0].blocked).toBeNull();
    expect(out.series[0].movement).toBe('fell');
    expect(out.series[0].movementFrom).toBe(101.9);
    expect(out.series[0].movementTo).toBe(13);
    expect(out.series[0].unitEquivalence.id).toBe('enzyme_activity_per_litre');
    expect(out.series[0].unitEquivalence.verified).toBe(false);
  });

  it('joins g/dL with % FOR MCHC', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('MCHC', '30.8', 'g/dL')], 'A'),
      snap('2026-02-01', [row('MCHC', '33', '%')], 'B'),
    ]);

    expect(out.series[0].blocked).toBeNull();
    expect(out.series[0].movementFrom).toBe(30.8);
    expect(out.series[0].movementTo).toBe(33);
    expect(out.series[0].unitEquivalence.id).toBe('mchc_mass_concentration');
  });

  it('does NOT let % mean g/dL on any other test', () => {
    for (const test of ['EOSINOPHILS', 'LYMPHOCYTES', 'Haemoglobin', 'Frimbulator']) {
      const out = buildLabSeries([
        snap('2026-01-01', [row(test, '5', '%')], 'A'),
        snap('2026-02-01', [row(test, '2', 'g/dL')], 'B'),
      ]);
      expect(out.series[0].blocked).not.toBeNull();
      expect(out.series[0].unitEquivalence).toBeNull();
    }
  });

  it('leaves a series with one unit entirely alone', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '35', 'mm/hr')], 'A'),
      snap('2026-02-01', [row('Zorblex', '45', 'mm/hr')], 'B'),
    ]);
    expect(out.series[0].unitEquivalence).toBeNull();
  });


  it('keeps the enzyme-activity equivalence global rather than per test', () => {
    const { UNIT_EQUIVALENCE } = require('../src/services/unitEquivalence');
    const enzyme = UNIT_EQUIVALENCE.find((e) => e.id === 'enzyme_activity_per_litre');
    expect(enzyme.tests).toBeNull();
  });

  it('states the assumptions the MCHC equivalence rests on', () => {
    const { UNIT_EQUIVALENCE } = require('../src/services/unitEquivalence');
    const mchc = UNIT_EQUIVALENCE.find((e) => e.id === 'mchc_mass_concentration');

    expect(mchc.basis).toMatch(/NOT UNCONDITIONAL/);
    expect(mchc.basis).toMatch(/density of 1 g\/mL/);
    expect(mchc.basis).toMatch(/negligible/);
    expect(mchc.basis).toMatch(/haemolysed/);
    expect(mchc.tests).toContain('MCHC');
  });

  it('declares NO conversion factor anywhere in the table', () => {
    const { UNIT_EQUIVALENCE } = require('../src/services/unitEquivalence');
    const allowed = new Set(['id', 'units', 'tests', 'label', 'basis', 'verified']);

    expect(UNIT_EQUIVALENCE.length).toBeGreaterThan(0);
    for (const entry of UNIT_EQUIVALENCE) {
      for (const field of Object.keys(entry)) {
        expect(allowed.has(field)).toBe(true);
      }
      for (const value of Object.values(entry)) {
        expect(typeof value).not.toBe('number');
      }
      expect(entry.basis.length).toBeGreaterThan(40);
      expect(entry.basis).toMatch(/CHECKED AGAINST:/);
      expect(entry.basis).toMatch(/read 2026-/);
      expect(entry.basis).toMatch(/NOT YET CONFIRMED/);
      expect(entry.verified).toBe(false);
    }
  });

  it('takes a reading that printed NO unit to be in the one unit the series prints', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '121.94', null)], 'A'),
      snap('2026-02-01', [row('Zorblex', '154', 'mg/dL')], 'B'),
    ]);

    expect(out.series[0].blocked).toBeNull();
    expect(out.series[0].unit).toBe('mg/dL');
    expect(out.series[0].movementFrom).toBe(121.94);
    expect(out.series[0].movementTo).toBe(154);
    expect(out.series[0].unitAssumed).toEqual({ unit: 'mg/dL', reason: 'not_printed' });
  });

  it('finds the newest PRINTED unit when the newest reading is the silent one', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '154', 'mg/dL')], 'A'),
      snap('2026-02-01', [row('Zorblex', '121.94', null)], 'B'),
    ]);

    expect(out.series[0].unit).toBe('mg/dL');
    expect(out.series[0].unitAssumed.unit).toBe('mg/dL');
  });

  it('claims nothing when NO reading printed a unit', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '1', null)], 'A'),
      snap('2026-02-01', [row('Zorblex', '2', null)], 'B'),
    ]);

    expect(out.series[0].blocked).toBeNull();
    expect(out.series[0].unit).toBeNull();
    expect(out.series[0].unitAssumed).toBeNull();
  });

  it('will NOT let a silent reading resolve a real disagreement', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '1', null)], 'A'),
      snap('2026-02-01', [row('Zorblex', '2', 'mg/L')], 'B'),
      snap('2026-03-01', [row('Zorblex', '3', 'mg/dL')], 'C'),
    ]);

    expect(out.series[0].blocked).not.toBeNull();
    expect(out.series[0].blocked.reason).toBe('units_differ');
    expect(out.series[0].unitAssumed).toBeNull();
    expect(out.series[0].movementFrom).toBeNull();
  });

  it('claims no assumed unit on an ordinary single-unit series', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '35', 'mm/hr')], 'A'),
      snap('2026-02-01', [row('Zorblex', '45', 'mm/hr')], 'B'),
    ]);
    expect(out.series[0].unitAssumed).toBeNull();
  });


  it('does not decide that two DIFFERENT units are equal', () => {
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
    expect(numericBound('22')).toBeNull();
    expect(numericBound(22)).toBe(22);
    expect(numericBound(null)).toBeNull();
    expect(numericBound(Number.NaN)).toBeNull();
    expect(numericBound(undefined)).toBeNull();
  });

  it('gives a BLOCKED series no scale, so a mixed-unit union cannot be handed on', () => {
    const out = buildLabSeries(
      [
        snap('2026-01-01', [row('Zorblex', '101.9', 'U/L')], 'r1'),
        snap('2026-02-01', [row('Zorblex', '13', 'U/mL')], 'r2'),
      ],
      printedFor({
        r1: [ref('Zorblex', null, 40, 'UP TO 40')],
        r2: [ref('Zorblex', 5, 40, '5 - 40')],
      })
    );

    expect(out.series[0].blocked).not.toBeNull();
    expect(out.series[0].referenceScale).toBeNull();
    expect(out.series[0].points[1].labReferenceLow).toBe(5);
  });

  it('counts only PLOTTED series in scaledCount', () => {
    const out = buildLabSeries(
      [
        snap('2026-01-01', [row('Zorblex', '1', 'U/L'), row('Quibblease', '5', 'mg/L')], 'r1'),
        snap('2026-02-01', [row('Zorblex', '2', 'U/mL'), row('Quibblease', '6', 'mg/L')], 'r2'),
      ],
      printedFor({
        r1: [ref('Zorblex', 0, 40), ref('Quibblease', 1, 9)],
        r2: [ref('Zorblex', 0, 40), ref('Quibblease', 1, 9)],
      })
    );

    expect(out.blockedCount).toBe(1);
    expect(out.scaledCount).toBe(1);
  });

  it('degrades to NO scale, never a wrong one, when the caller supplies nothing', () => {
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

describe('labSeriesService - readings that cannot be trended', () => {
  it('lists a parameter seen on only ONE report instead of only counting it', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '3.51', 'ulU/mL')], 'r1'),
      snap('2026-02-01', [row('Quibblease', '1.81', 'mg/L')], 'r2'),
    ]);

    expect(out.singleReportCount).toBe(2);
    expect(out.readings.map((r) => r.name)).toEqual(['Quibblease', 'Zorblex']);
    expect(out.readings[1].rows).toEqual([
      expect.objectContaining({ valueRaw: '3.51', unit: 'ulU/mL', value: 3.51 }),
    ]);
    expect(out.readings[1].reason).toBe('one_report');
  });

  it('shows a NON-NUMERIC result as the laboratory printed it', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', 'Pale Yellow', null)], 'r1'),
      snap('2026-02-01', [row('Zorblex', 'Negative', null)], 'r2'),
    ]);

    expect(out.notNumericCount).toBe(1);
    expect(out.readings).toHaveLength(1);
    expect(out.readings[0].reason).toBe('not_numeric');
    expect(out.readings[0].rows.map((r) => r.valueRaw)).toEqual(['Pale Yellow', 'Negative']);
    expect(out.readings[0].rows.every((r) => r.value === null)).toBe(true);
  });

  it('gives a reading NO line, NO direction and NO scale', () => {
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
      snap('2026-02-01', [row('Zorblex', '13', 'U/mL')], 'r2'),
    ]);

    expect(out.blockedCount).toBe(1);
    expect(out.readings).toHaveLength(0);
  });

  it('accounts for EVERY considered parameter, in one bucket or another', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [
        row('Zorblex', '1', 'U/L'),
        row('Quibblease', '101.9', 'U/L'),
        row('Frimbulator', '5', 'mg/L'),
        row('Snarflax', 'Negative', null),
      ], 'r1'),
      snap('2026-02-01', [
        row('Zorblex', '2', 'U/L'),
        row('Quibblease', '13', 'U/mL'),
        row('Snarflax', 'Negative', null),
      ], 'r2'),
    ]);

    expect(out.consideredCount).toBe(4);
    expect(out.plottedCount + out.blockedCount + out.readings.length).toBe(
      out.consideredCount
    );
  });
});

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

    for (const out of [rising, falling, flat]) {
      expect(JSON.stringify(out)).not.toMatch(/improving|worsening|stable/i);
    }
  });

  it('withholds movement from a BLOCKED series', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '101.9', 'U/L')], 'r1'),
      snap('2026-02-01', [row('Zorblex', '13', 'U/mL')], 'r2'),
    ]);

    expect(out.series[0].blocked).not.toBeNull();
    expect(out.series[0].movement).toBeNull();
  });

  it('carries the two readings the movement word is about', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '12.1', 'mg/L')], 'r1'),
      snap('2026-02-01', [row('Zorblex', '20.0', 'mg/L')], 'r2'),
      snap('2026-03-01', [row('Zorblex', '38.9', 'mg/L')], 'r3'),
    ]);

    expect(out.series[0].movement).toBe('rose');
    expect(out.series[0].movementFrom).toBe(12.1);
    expect(out.series[0].movementTo).toBe(38.9);
  });

  it('carries a pair of zeroes rather than treating 0 as absent', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '0', '%')], 'r1'),
      snap('2026-02-01', [row('Zorblex', '0', '%')], 'r2'),
    ]);

    expect(out.series[0].movement).toBe('same');
    expect(out.series[0].movementFrom).toBe(0);
    expect(out.series[0].movementTo).toBe(0);
  });

  it('withholds the PAIR from a blocked series, not only the word', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '101.9', 'U/L')], 'r1'),
      snap('2026-02-01', [row('Zorblex', '13', 'U/mL')], 'r2'),
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
    const out = buildLabSeries([
      snap('2026-01-01', [row('Zorblex', '1', 'U/L')], 'r1'),
      snap('2026-02-01', [row('Zorblex', '2', 'U/L')], 'r2'),
    ]);

    expect(out.series[0].latestFlag).toBeNull();
    expect(out.series[0].points.every((p) => p.labFlag === null)).toBe(true);
  });
});

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
        snap('2026-02-01', [row('Zorblex', '14', '%'), row('Quibblease', '2', 'U/mL')], 'r2'),
      ],
      printedFor({
        r1: [ref('Zorblex', 22, 45), ref('Quibblease', 0, 40)],
        r2: [ref('Zorblex', 20, 40), ref('Quibblease', 0, 40)],
      })
    );

    const outbound = classifiableSeries(built);
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
    for (const verdicts of [undefined, null, [], [{}], [{ test_name: 'Other' }]]) {
      const out = attachVerdicts(twoReports(), verdicts);
      expect(out.series[0].trend).toBeUndefined();
      expect(out.series[0].movement).toBe('rose');
    }
  });

  it('never lands one test\'s verdict on another test\'s panel', () => {
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
    expect(only.category).toBe('changed_direction_only');
  });

  it('keeps a parameter that is on only ONE of the two reports', () => {
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
    const built = buildLabSeries(pairOf([row('Zorblex', '101.9', 'U/L')], [row('Zorblex', '13', 'U/mL')]));
    const [only] = buildLabComparison(built, 'A', 'B').rows;

    expect(only.category).toBe('not_classifiable');
    expect(only.symbol).toBeNull();
    expect(only.previousUnit).toBe('U/L');
    expect(only.currentUnit).toBe('U/mL');
    expect(only.unit).toBeNull();
  });

  it("uses Module 29's own words for a Module 35 verdict", () => {
    const built = buildLabSeries(pairOf([row('Zorblex', '12.1', 'mg/L')], [row('Zorblex', '38.9', 'mg/L')]));
    const withVerdict = attachVerdicts(built, [
      { test_name: 'Zorblex', outcome: 'TREND_CLASSIFIED', trend: 'worsening' },
    ]);
    const [only] = buildLabComparison(withVerdict, 'A', 'B').rows;

    expect(only.category).toBe('worsened');
  });

  it("lets the laboratory's own crossing outrank the change axis", () => {
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

    expect(only.category).toBe('newly_abnormal');
  });

  it('claims NO crossing when one report marked nothing', () => {
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

describe('labSeriesService - a row that restates an assessed feature', () => {
  it('does NOT trend it, so one change cannot get two opposite verdicts', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('Estimated Average Glucose', '121.94', null)], 'A'),
      snap('2026-02-01', [row('AVERAGE BLOOD GLUCOSE', '154', 'mg/dL')], 'B'),
    ]);

    expect(out.series).toHaveLength(0);
    expect(out.restatedCount).toBeGreaterThan(0);
  });

  it('still SHOWS it, with its readings and the feature it restates', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('AVERAGE BLOOD GLUCOSE', '121.94', 'mg/dL')], 'A'),
      snap('2026-02-01', [row('AVERAGE BLOOD GLUCOSE', '154', 'mg/dL')], 'B'),
    ]);

    const [only] = out.readings;
    expect(only.reason).toBe('restates_assessed_feature');
    expect(only.restates).toBe('hba1c');
    expect(only.rows.map((r) => r.valueRaw)).toEqual(['121.94', '154']);
    expect(only.movement).toBeUndefined();
    expect(only.trend).toBeUndefined();
  });

  it('matches the printed spellings by word set, like every other lookup', () => {
    for (const printed of [
      'AVERAGE BLOOD GLUCOSE',
      'Average Blood Glucose',
      'Estimated Average Glucose',
      'eAG',
    ]) {
      const out = buildLabSeries([
        snap('2026-01-01', [row(printed, '1', 'mg/dL')], 'A'),
        snap('2026-02-01', [row(printed, '2', 'mg/dL')], 'B'),
      ]);
      expect(out.series).toHaveLength(0);
      expect(out.readings[0].reason).toBe('restates_assessed_feature');
    }
  });

  it('leaves every other parameter trending exactly as before', () => {
    const out = buildLabSeries([
      snap('2026-01-01', [row('RANDOM BLOOD GLUCOSE', '134', 'mg/dL'), row('ESR', '35', 'mm/hr')], 'A'),
      snap('2026-02-01', [row('RANDOM BLOOD GLUCOSE', '168', 'mg/dL'), row('ESR', '45', 'mm/hr')], 'B'),
    ]);

    expect(out.series.map((s) => s.name).sort()).toEqual(['ESR', 'RANDOM BLOOD GLUCOSE']);
    expect(out.restatedCount).toBe(0);
  });

  it('declares the fixed relationship it rests on, for a reviewer', () => {
    const { LAB_RESTATEMENTS } = require('../src/services/labRestatements');
    expect(LAB_RESTATEMENTS.length).toBeGreaterThan(0);
    for (const entry of LAB_RESTATEMENTS) {
      expect(entry.basis).toMatch(/CHECKED ON THIS ACCOUNT|CHECK AGAINST/);
      expect(entry.basis.length).toBeGreaterThan(60);
      expect(typeof entry.restates).toBe('string');
      expect(entry.names.length).toBeGreaterThan(0);
    }
  });
});

describe('labSeriesService - Module 36 name joining', () => {
  const twoNames = () => [
    snap('2026-01-01', [row('Zorblex Factor', '12.1', 'mg/L')], 'r1'),
    snap('2026-02-01', [row('Frimbulin', '38.9', 'mg/L')], 'r2'),
  ];

  it('leaves them as two readings when no aliases are supplied', () => {
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
    expect(out.series[0].movement).toBe('rose');
    expect(out.series[0].movementFrom).toBe(12.1);
    expect(out.series[0].movementTo).toBe(38.9);
  });

  it('titles the joined panel with the NEWEST report\'s wording', () => {
    const aliases = aliasMap([{ names: ['Zorblex Factor', 'Frimbulin'] }]);
    const out = buildLabSeries(twoNames(), undefined, aliases);

    expect(out.series[0].name).toBe('Frimbulin');
  });

  it('says which names it merged, so no join is silent', () => {
    const aliases = aliasMap([{ names: ['Zorblex Factor', 'Frimbulin'] }]);
    const out = buildLabSeries(twoNames(), undefined, aliases);

    expect(out.series[0].joinedFrom).toEqual(['Zorblex Factor', 'Frimbulin']);
  });

  it('claims NO join when the group only restates one name', () => {
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
    const aliases = aliasMap([{ names: ['Zorblex Factor', 'Frimbulin'] }]);
    const out = buildLabSeries(
      [
        snap('2026-01-01', [row('Zorblex Factor', '101.9', 'U/L')], 'r1'),
        snap('2026-02-01', [row('Frimbulin', '13', 'U/mL')], 'r2'),
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

    expect(out.series.map((s) => s.name)).toEqual(['Zorblex']);
    expect(unjoinedNames(out).sort()).toEqual(['Frimbulin', 'Quixotor']);
  });

  it('picks a canonical key by a rule, so two calls agree', () => {
    const forwards = aliasMap([{ names: ['Zorblex Factor', 'Frimbulin'] }]);
    const backwards = aliasMap([{ names: ['Frimbulin', 'Zorblex Factor'] }]);

    expect([...forwards.entries()].sort()).toEqual([...backwards.entries()].sort());
  });

  it('keeps a name out of a second group rather than letting it migrate', () => {
    const aliases = aliasMap([
      { names: ['Zorblex Factor', 'Frimbulin'] },
      { names: ['Frimbulin', 'Quixotor'] },
    ]);

    expect(aliases.get(nameKey('Frimbulin'))).toBe(aliases.get(nameKey('Zorblex Factor')));
  });
});
