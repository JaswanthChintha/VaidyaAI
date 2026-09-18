/**
 * PRINTED TESTS THAT RESTATE A FEATURE THIS PLATFORM ALREADY ASSESSES.
 *
 * ==========================================================================
 * WHY THIS EXISTS: ONE MEASUREMENT WAS GETTING TWO OPPOSITE VERDICTS
 * ==========================================================================
 *
 * `labSeriesService` trends the parameters Module 28 has no canonical feature
 * for. A few printed rows are not new measurements at all -- they are a
 * DIFFERENT PRESENTATION of one the platform already assesses, with its own
 * reviewed polarity and its own stability band. Trending those a second time
 * means the same change can be classified twice, by two different routes, and
 * the two can disagree.
 *
 * IT DID. On the reader's own two reports:
 *
 *     HbA1c (average blood sugar)   5.9 % -> 7 %            worsening
 *     AVERAGE BLOOD GLUCOSE         121.94 -> 154 mg/dL      improving
 *
 * Those are THE SAME CHANGE. Estimated average glucose is a fixed restatement
 * of HbA1c -- eAG(mg/dL) = 28.7 x HbA1c - 46.7 -- and 5.9 % and 7 % give
 * 122.6 and 154.2, which is what the reports carry. One card was about to show
 * a reader that their diabetes control improved and worsened at the same time,
 * and the reassuring one was the false one.
 *
 * ==========================================================================
 * WHAT WENT WRONG UNDERNEATH, AND WHY THIS IS NOT THE FIX FOR THAT
 * ==========================================================================
 *
 * The `improving` came from the interval the extraction stored for that row:
 *
 *     reference_range_raw = "151 - 180 - Average Control"   low=151 high=180
 *
 * That is a band from an HbA1c INTERPRETATION TABLE, not this patient's
 * reference range, and Module 4's parser accepted it as one. Judged against a
 * target of 151-180, a rise from 121.94 to 154 moves INTO range and reads as
 * an improvement. An average glucose of 154 mg/dL is HbA1c around 7 %, which
 * is worse control, not better.
 *
 * THAT PARSER DEFECT IS STILL OPEN and this file does not fix it. Excluding
 * the row removes the contradiction and the false verdict; a band label read
 * as a reference interval could still reach another parameter, and the honest
 * place to stop that is Module 4.
 *
 * ==========================================================================
 * EXCLUDED FROM TRENDING, NOT FROM THE PAGE
 * ==========================================================================
 *
 * The reader asked for every parameter on their reports to be visible, and
 * 6au records what happens when one is not: a row they can find on their
 * document and not on the screen reads as missing, whatever the reason. So an
 * entry here is still SHOWN, with its readings and its dates -- it just gets
 * no chart, no direction and no scale, and it says which assessed feature
 * carries the same measurement, so a reader can go and read the verdict that
 * was actually reviewed.
 *
 * ==========================================================================
 * WHAT MAY GO IN HERE
 * ==========================================================================
 *
 * ONLY a row that is a restatement of an ASSESSED feature by a FIXED
 * relationship -- a formula, a unit change, or the same quantity under another
 * name. NOT a test that is merely related, correlated, or clinically adjacent:
 * fasting and random glucose are different measurements of the same analyte
 * and both belong on the page in their own right, and the platform's refusal
 * to trend them together is a separate and correct decision.
 *
 * Each entry names the canonical feature key it restates, so the page can
 * resolve the reader-facing label from the one vocabulary that already exists
 * rather than this file inventing a second one.
 */

/**
 * @typedef {Object} LabRestatement
 * @property {string} id        Stable machine name, used in payloads.
 * @property {string[]} names   Printed names, matched by `nameKey`.
 * @property {string} restates  The canonical feature key this restates.
 * @property {string} basis     The fixed relationship, and how it was checked.
 */

/** @type {LabRestatement[]} */
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
