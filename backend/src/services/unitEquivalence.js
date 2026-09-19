/**
 * DECLARED UNIT EQUIVALENCES for laboratory tests this platform does not assess.
 *
 * ==========================================================================
 * WHAT THIS FILE IS, AND THE ONE THING IT CANNOT DO
 * ==========================================================================
 *
 * Two reports can print one measurement under two unit strings that mean the
 * same scale. `labSeriesService.unitKey` already folds SPELLING -- case,
 * spacing, the micro sign, and the OCR confusion between `i` and `l` -- and
 * that is enough for `µIU/mL` against `ulU/mL`, which is one unit misread.
 *
 * It is NOT enough for these two, which is why this file exists:
 *
 *     SGPT   101.9 U/L   and  13 IU/L
 *     MCHC   30.8 g/dL   and  33 %
 *
 * Those are different unit STRINGS denoting the same scale. Saying so is a
 * clinical claim, not a spelling repair, so it is written down here where a
 * reviewer can find it rather than folded into a regular expression.
 *
 * ==========================================================================
 * THERE IS NO CONVERSION FACTOR IN THIS FILE, AND THERE MUST NEVER BE ONE
 * ==========================================================================
 *
 * Every entry declares units whose NUMBERS ARE ALREADY THE SAME. 101.9 U/L is
 * 101.9 IU/L; 33 % MCHC is 33 g/dL. Nothing is multiplied, nothing is
 * rescaled, and no reading is altered by anything here -- the entries only
 * decide whether two readings may share an axis.
 *
 * A pair that needed a multiplier -- mg/dL against mmol/L, say -- IS A
 * CONVERSION and does not belong here. It belongs in Module 5
 * (`ai-service/app/data/unit_conversions.py`), upstream of storage, whose own
 * header calls itself safety-critical and records the molar mass each factor
 * came from. This file is deliberately incapable of expressing one: there is
 * no field for a factor, and a test asserts there is not.
 *
 * ==========================================================================
 * SCOPE: `tests: null` IS A CLAIM ABOUT THE UNIT, A LIST IS A CLAIM ABOUT ONE TEST
 * ==========================================================================
 *
 * THIS IS THE MOST IMPORTANT LINE IN THE FILE. `%` means different things on
 * different rows of one report:
 *
 *   - for MCHC it is a mass concentration, and 33 % IS 33 g/dL;
 *   - for EOSINOPHILS it is a proportion of the white cell count, and 2 % is
 *     not 2 of anything per decilitre.
 *
 * So `g/dL` and `%` may be declared equal FOR MCHC ONLY. Declaring it
 * globally -- which is what putting it in Module 5's `UNIT_ALIASES` would do,
 * since that table is a flat string map -- would make every haemoglobin in
 * g/dL interchangeable with a percentage. That is the worst defect available
 * in this area and it is the reason this table is scoped per test at all.
 *
 * `tests: null` is therefore reserved for pairs where the unit strings
 * themselves are synonymous whatever the analyte, and each such entry has to
 * argue for it in its own `basis`.
 *
 * ==========================================================================
 * EVERY ENTRY IS `verified: false`
 * ==========================================================================
 *
 * Same discipline as `ai-service/app/data/lab_variation.py`, and for the same
 * reason. These are widely used conventions recorded with the ground they
 * rest on -- they were not checked against a standards document when this
 * file was written. `verified: true` may only be set by a human who has done
 * that. Not by a model, not by this file's author, and not because the
 * convention is well known.
 *
 * WHAT THE FLAG CHANGES: nothing about the arithmetic, because there is none.
 * It changes what the page says about why two readings were joined, so a
 * reader is never told a checked equivalence and an unchecked one in the same
 * words.
 */

/**
 * @typedef {Object} UnitEquivalence
 * @property {string} id            Stable machine name, used in payloads.
 * @property {string[]} units       Unit strings as laboratories print them.
 *                                  Folded through `unitKey` when indexed, so
 *                                  case and spacing need not be repeated.
 * @property {string[]|null} tests  Test names this applies to, matched by
 *                                  `nameKey`. `null` means any test -- see the
 *                                  scope note above before using it.
 * @property {string} label         What the shared scale is, for a reader.
 * @property {string} basis         WHY these are the same scale, and for a
 *                                  `tests: null` entry, why it holds for any
 *                                  analyte.
 * @property {boolean} verified     TRUE only when a human has checked it.
 */

/** @type {UnitEquivalence[]} */
const UNIT_EQUIVALENCE = [
  {
    id: 'enzyme_activity_per_litre',
    units: ['U/L', 'IU/L'],
    // ANY TEST. `U` and `IU` of catalytic activity are both defined as the
    // amount converting one micromole of substrate per minute, so the number
    // per litre is the same figure under either name. That is a property of
    // the units and not of the enzyme, which is what justifies `null` here --
    // no analyte prints `U/L` meaning something else.
    //
    // ==================================================================
    // "IU" IS AMBIGUOUS AND THE GLOBAL SCOPE SURVIVES IT ANYWAY
    // ==================================================================
    //
    // Raised while checking this entry on 2026-09-19, because it looks at
    // first like the `%` hazard one entry down. **IU also names the
    // International Unit of BIOLOGICAL ACTIVITY** -- the potency unit for
    // vitamins and hormones, set by an arbitrary standard per substance.
    // Wikipedia's own enzyme-unit article warns about exactly this: "there
    // is no relation between the two units, despite their identical names".
    // hCG, LH and FSH are reported in IU/L and mean potency, not catalysis.
    //
    // SO WHY IS `null` STILL RIGHT? For this entry to join two readings
    // wrongly, ONE TEST would have to be printed `IU/L` as a potency on one
    // report and `U/L` on another. `U/L` is only ever catalytic activity, so
    // that test would have to be an enzyme -- and then both readings are
    // catalytic and the join is correct. The ambiguity is real and it cannot
    // reach this entry.
    //
    // IT IS WRITTEN DOWN BECAUSE THE DOUBT RECURS. The next reader will
    // notice the ambiguity too, and a scoped list added in response would be
    // strictly worse: `nameKey` folds a whole word set, so `SGPT` and
    // `SGPT PHOTOMETRIC` are different keys, and a scoped entry would start
    // MISSING joins the moment a method suffix reappeared.
    tests: null,
    label: 'units of enzyme activity per litre',
    basis:
      'U and IU of catalytic activity are the same quantity -- the amount of ' +
      'enzyme converting one micromole of substrate per minute under defined ' +
      'conditions, adopted by the International Union of Biochemistry in ' +
      '1964 -- so U/L and IU/L are the same number. Laboratories print both ' +
      'for the same assay. NOT a conversion: no factor is applied and no ' +
      'reading changes. (The SI unit is the katal, 1 U = 16.67 nkat, adopted ' +
      'by CGPM Resolution 12 of 1999 on a petition from the IFCC; nothing ' +
      'here converts to it.) ' +
      'CHECKED AGAINST: en.wikipedia.org/wiki/Enzyme_unit and the IUPAC ' +
      'technical report "Unit katal for catalytic activity" (Pure Appl Chem ' +
      '2001;73:927-931), read 2026-09-19. NOT YET CONFIRMED by a human.',
    verified: false,
  },
  {
    id: 'mchc_mass_concentration',
    units: ['g/dL', '%'],
    // MCHC ONLY, AND THIS SCOPE IS LOAD-BEARING. MCHC is haemoglobin mass
    // divided by packed cell volume; expressed per 100 mL it is both grams
    // per decilitre and a percentage, and the figure is identical. The same
    // `%` on the differential count is a proportion of the white cell count
    // and has nothing to do with g/dL, so this must never be global.
    tests: ['MCHC', 'MEAN CORPUSCULAR HAEMOGLOBIN CONCENTRATION'],
    label: 'grams per decilitre, which for MCHC is also written as a percentage',
    basis:
      'MCHC is a mass concentration: haemoglobin per unit packed cell ' +
      'volume, per 100 mL. 33 g/dL and 33 % are the same figure, and ' +
      'laboratories print both -- many report MCHC as a percentage as ' +
      'though it were a mass fraction. NOT a conversion: no factor is ' +
      'applied. ' +
      'THE EQUIVALENCE IS NOT UNCONDITIONAL, and this was added on checking: ' +
      'it holds ASSUMING a red-cell density of 1 g/mL and negligible ' +
      'haemoglobin in plasma. Both are standard assumptions and neither is ' +
      'stated on a report, so a grossly haemolysed sample is the case where ' +
      'the two readings drift -- which this entry cannot detect. ' +
      'SCOPED TO MCHC because % on a differential count is a proportion of ' +
      'the white cell count and is not a mass concentration at all. ' +
      'CHECKED AGAINST: en.wikipedia.org/wiki/Mean_corpuscular_hemoglobin_' +
      'concentration, read 2026-09-19 (reference range 32-36 g/dL). ' +
      'NOT YET CONFIRMED by a human against a haematology text.',
    verified: false,
  },
];

module.exports = { UNIT_EQUIVALENCE };
