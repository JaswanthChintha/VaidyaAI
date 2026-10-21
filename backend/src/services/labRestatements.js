const LAB_RESTATEMENTS = [
  {
    id: 'estimated_average_glucose',
    names: [
      'AVERAGE BLOOD GLUCOSE',
      'Estimated Average Glucose',
      'Estimated Average Glucose (eAG)',
      'eAG',
      'Mean Blood Glucose',
    ],
    restates: 'hba1c',
    basis:
      'Estimated average glucose is derived from HbA1c by the ADAG equation, ' +
      'eAG(mg/dL) = 28.7 x HbA1c(%) - 46.7. It carries no information HbA1c ' +
      'does not. CHECKED ON THIS ACCOUNT: HbA1c 5.9 % and 7 % give 122.6 and ' +
      '154.2 mg/dL, and the reports store 121.94 and 154. Module 28 assesses ' +
      'hba1c with a reviewed polarity and its own stability band, so that is ' +
      'the verdict a reader should be given.',
  },
];

module.exports = { LAB_RESTATEMENTS };
