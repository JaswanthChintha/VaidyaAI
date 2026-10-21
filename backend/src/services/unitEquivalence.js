const UNIT_EQUIVALENCE = [
  {
    id: 'enzyme_activity_per_litre',
    units: ['U/L', 'IU/L'],
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
