'use strict';

// The declared unit equivalences, as plain data. Kept in its own file because
// a clinical reviewer should be able to find and read the claims without
// reading this service -- see its header for why `%` equals `g/dL` for MCHC
// and for nothing else.
const { UNIT_EQUIVALENCE } = require('./unitEquivalence');

/**
 * The laboratory's OWN repeated parameters, over time.
 *
 * ==========================================================================
 * WHY THIS EXISTS
 * ==========================================================================
 *
 * The timeline showed 14 parameters and a reader asked why, when their
 * reports carry far more. The answer was structural: Module 28 trends
 * CANONICAL features, and a canonical feature is one the pipeline can
 * identify across two reports and express in one unit. The parameters this
 * platform does not assess have neither -- they carry only the name the
 * laboratory printed.
 *
 * So CRP 12.1 -> 38.9 mg/L, a tripling across two reports, was nowhere on the
 * timeline. Not refused, not explained: absent.
 *
 * This builds the series the laboratory's own numbers can support, and
 * nothing beyond them.
 *
 * ==========================================================================
 * WHAT THIS IS NOT ALLOWED TO DO
 * ==========================================================================
 *
 * 1. NO DIRECTION, EVER. There is no polarity for these parameters and no
 *    stability band -- nothing here knows whether a rising ESR is better or
 *    worse, or how much movement is noise. Module 28 refuses to classify
 *    without both, and so does this. It reports readings over time and says
 *    nothing about what they mean.
 *
 *    THE LABORATORY'S PRINTED INTERVAL DOES NOT CHANGE THAT. It sets the
 *    SCALE these readings are drawn against and nothing else -- see
 *    `referenceScale` below. A scale is not a judgement: it makes a move
 *    within the usual range look small and a move outside it look large,
 *    which is arithmetic the laboratory's own numbers already support. What
 *    it must never become is a verdict on the parameter, which would need a
 *    threshold and a knowledge document this platform does not have for these
 *    tests.
 *
 * 2. NO UNIT IS ASSUMED. If two reports print different units for the same
 *    parameter the series is BLOCKED and both units are named. `U/L` and
 *    `IU/L` are the same thing to a clinician and `g/dL` and `%` for MCHC are
 *    numerically close -- and this file treats none of that as known, because
 *    a chart that plots two scales on one axis is the failure §6z already
 *    caught once. A blocked series still shows its readings; it just draws no
 *    line.
 *
 * 3. NOTHING IS DROPPED SILENTLY. A parameter seen on only one report cannot
 *    make a series, and that is reported as a count rather than by omission.
 *
 * ==========================================================================
 * MATCHING NAMES, WHICH IS THE WHOLE DIFFICULTY
 * ==========================================================================
 *
 * On the project's own account: 28 distinct printed names across 4 reports,
 * of which only SIX repeat as exact strings. Five more are the same test in a
 * different case (`Platelet count` / `PLATELET COUNT`). And the one that
 * matters most does not match either way:
 *
 *     "CRP (C-REACTIVE PROTEIN)"   vs   "C-REACTIVE PROTEIN(CRP)"
 *
 * Same test, same words, different order. That is §6aq's parenthetical and
 * §6ar's "Grams/dL" a third time: a laboratory's own spelling defeating a
 * lookup, and the consequence reaching the reader as an absence.
 *
 * So the key is the SET OF WORDS, sorted. `crp` + `creactive` + `protein` in
 * either arrangement is one key.
 *
 * THIS IS SET EQUALITY, NOT SIMILARITY. Two names match only when they are
 * built from exactly the same words; nothing is fuzzy, nothing is scored, and
 * a name with one extra word does not match one without it. That line is
 * deliberate -- a similarity threshold here would be this file guessing that
 * two tests are the same, which is the class of guess this codebase refuses
 * everywhere else.
 */

/** Words of a printed test name, lower-cased, in a stable order. */
function nameKey(printed) {
  const words = String(printed || '')
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter(Boolean);
  if (!words.length) return null;
  // Sorted, so word ORDER cannot decide whether two reports are talking about
  // the same test. Duplicates are kept: a name is not a set of distinct words,
  // and collapsing them would make "total total protein" match "total protein".
  return words.slice().sort().join(' ');
}

/** The unit as written, reduced to what makes two units the SAME unit. */
/*
 * IT REPAIRS SPELLING. IT ASSERTS NO EQUIVALENCE BETWEEN DIFFERENT UNITS.
 *
 * ==========================================================================
 * THE DEFECT: ONE TEST, ONE UNIT, TWO SPELLINGS, NO TREND
 * ==========================================================================
 *
 * TSH is printed `1.81 µIU/mL` on one of the reader's reports and
 * `3.51 ulU/mL` on the other. THAT IS THE SAME UNIT. The extraction read the
 * micro sign as a `u` and the capital I as a lowercase l -- the two classic
 * OCR confusions, both in one short string. Lowercasing alone left `µiu/ml`
 * against `ulu/ml`, so the series was blocked, drew no line, carried no
 * movement word and no pair, and the panel told the reader their two reports
 * disagreed about the unit. They do not; one of them was misread.
 *
 * SO TWO CHARACTER CLASSES ARE FOLDED, AND ONLY TWO:
 *
 *   - THE MICRO SIGN. `µ` (U+00B5), the Greek mu `μ` (U+03BC) and the ASCII
 *     `u` all fold to `u`. This is not only an OCR repair: `ug/dL` for µg/dL
 *     is how laboratories print it when the character set will not carry the
 *     sign, so the three spellings were always one unit.
 *   - `i` AND `l`, WHICH ARE THE SAME GLYPH TO AN OCR ENGINE in most fonts
 *     once case is gone.
 *
 * ==========================================================================
 * WHAT IT MUST NOT DO, CHECKED AGAINST THE REAL DATA
 * ==========================================================================
 *
 * A folding that merged two GENUINELY different units would put two
 * incomparable readings on one line -- far worse than the blocked panel it
 * replaced. So it was run over every distinct unit string on this account's
 * reports plus the plausible neighbours, and the only pairs it merges are:
 *
 *     ulU/mL  +  µIU/mL      <- the defect
 *     umol/L  +  µmol/L      <- also one unit, also two spellings
 *
 * AND THESE STAY APART, which is the part that matters:
 *
 *     mg/L    -> mg/i        vs  mg/dL  -> mg/di
 *     U/L     -> u/i         vs  IU/L   -> iu/i
 *     mmol/L  -> mmoi/i      vs  µmol/L -> umoi/i
 *     10^3/µL -> 10^3/ui     vs  10^6/µL -> 10^6/ui
 *
 * `U/L` AGAINST `IU/L` IS LEFT BLOCKED ON PURPOSE. Enzyme activity in U/L and
 * IU/L is conventionally the same number, but `U` and `IU` are formally
 * different units and saying they are equal is a clinical claim, not a
 * spelling repair. SGPT therefore still shows both readings and no line --
 * and `MCHC` in `g/dL` against `%` likewise, for the same reason.
 *
 * DIGITS ARE NEVER FOLDED. `10^3/µL` and `10^6/µL` are different units and a
 * confusable class containing `1` would be a step towards merging them.
 *
 * FOR COMPARISON ONLY. The reader is always shown the unit their laboratory
 * printed, misread or not -- `points[].unit` is untouched, and this key never
 * reaches a screen.
 */
const _MICRO = /[µμ]/g;
const _I_L = /[il]/g;

function unitKey(unit) {
  const text = String(unit === null || unit === undefined ? '' : unit)
    .toLowerCase()
    .replace(/\s+/g, '');
  return text.replace(_MICRO, 'u').replace(_I_L, 'i');
}

/*
 * THE DECLARED EQUIVALENCES, INDEXED. See `unitEquivalence.js` for the table
 * and for why `%` may be equal to `g/dL` for MCHC and for nothing else.
 *
 * SPELLING IS FOLDED FIRST. The table is written in the units a laboratory
 * prints (`U/L`, `g/dL`) and indexed through `unitKey`, so the entries stay
 * readable and nobody has to hand-write a post-fold string.
 *
 * THE CANONICAL MEMBER IS THE FIRST LISTED, by rule rather than by judgement,
 * so the key a series ends up grouped under does not depend on which report
 * happened to arrive first.
 */
const _EQUIV_GLOBAL = new Map();
const _EQUIV_SCOPED = new Map();

for (const entry of UNIT_EQUIVALENCE) {
  const keys = entry.units.map((u) => unitKey(u)).filter(Boolean);
  if (keys.length < 2) continue;
  const canonical = keys[0];
  if (entry.tests === null) {
    for (const key of keys) {
      if (!_EQUIV_GLOBAL.has(key)) _EQUIV_GLOBAL.set(key, { canonical, entry });
    }
  } else {
    // NESTED MAPS, NOT A COMPOSITE STRING KEY. The first version joined the
    // test and the unit with a separator and there is no character safe for
    // that job: a unit key can hold `/`, `%`, `^` and `.`, and the escape
    // chosen to avoid them put two real NUL BYTES INTO THIS SOURCE FILE,
    // which made git treat it as binary and drop the diff. Two maps have no
    // separator to get wrong.
    for (const test of entry.tests) {
      const scope = nameKey(test);
      if (!scope) continue;
      if (!_EQUIV_SCOPED.has(scope)) _EQUIV_SCOPED.set(scope, new Map());
      const byUnit = _EQUIV_SCOPED.get(scope);
      for (const key of keys) {
        if (!byUnit.has(key)) byUnit.set(key, { canonical, entry });
      }
    }
  }
}

/**
 * The declared equivalence covering this test and unit, or null.
 *
 * TEST-SCOPED FIRST, THEN GLOBAL. A claim about one test is more specific than
 * a claim about a unit string, so it wins -- and a future scoped entry cannot
 * be silently overridden by a broader one added later.
 */
function equivalenceFor(testKey, key) {
  if (!key) return null;
  const byUnit = _EQUIV_SCOPED.get(testKey);
  const scoped = byUnit ? byUnit.get(key) : undefined;
  if (scoped) return scoped;
  return _EQUIV_GLOBAL.get(key) || null;
}

/** This unit's key, moved onto its declared shared scale where there is one. */
function canonicalUnitKey(testKey, key) {
  const found = equivalenceFor(testKey, key);
  return found ? found.canonical : key;
}

/**
 * A laboratory value, or null.
 *
 * `value_raw` is the string the extraction read. Thousands separators are
 * removed because "7,290" is a number a laboratory prints; nothing else is
 * repaired, and anything that does not parse cleanly is not a point.
 */
function numericValue(raw) {
  if (typeof raw === 'number') return Number.isFinite(raw) ? raw : null;
  if (typeof raw !== 'string') return null;
  const cleaned = raw.replace(/,/g, '').trim();
  if (cleaned === '') return null;
  const value = Number(cleaned);
  return Number.isFinite(value) ? value : null;
}

/**
 * A reference bound, or null.
 *
 * STRICTLY A NUMBER, deliberately. Module 4 has already decided what the
 * printed range means -- `"< 6 mg/l"` becomes `high: 6, low: null`, and
 * `"F: 36 - 46 M: 40 - 50"` becomes NEITHER, because a sex-specific interval
 * cannot be reduced to one pair without knowing whose report it is. Parsing a
 * string here would be this file re-deciding a question the extraction
 * already answered more carefully, and the one case it would "fix" is the one
 * case that must stay unanswered.
 */
function numericBound(raw) {
  return typeof raw === 'number' && Number.isFinite(raw) ? raw : null;
}

/**
 * THE LABORATORY'S OWN HIGH/LOW MARKING, lower-cased, or null.
 *
 * `high`, `low`, `normal` or `critical` as Module 4 recorded it. Not this
 * platform's verdict and never presented as one -- every field carrying it is
 * named `labFlag` for that reason.
 */
function labFlagOf(raw) {
  if (typeof raw !== 'string') return null;
  const text = raw.trim().toLowerCase();
  return text === '' ? null : text;
}

/**
 * WHICH WAY THE NUMBERS WENT. Arithmetic, not a judgement.
 *
 * ==========================================================================
 * WHY THIS IS NOT `improving` / `worsening` / `stable`, AND CANNOT BE
 * ==========================================================================
 *
 * Those three words are Module 28's, and each needs something this module does
 * not have and must not invent:
 *
 *   - `improving` / `worsening` need POLARITY -- whether a rising value is
 *     better or worse for the patient. Nothing here knows that for an
 *     unassessed test. Module 28 refuses with CLINICAL_DIRECTION_UNKNOWN
 *     rather than guess, and so does this.
 *   - `stable` needs a STABILITY BAND -- the reference change value below
 *     which two draws from an unchanged person differ anyway. Without one,
 *     calling a 7 % move "stable" states something nobody measured, which is
 *     the single most repeated hazard on this project.
 *
 * `rose`, `fell` and `same` need neither. They describe the reader's own two
 * numbers and claim nothing about what the change means. Module 28 keeps the
 * same separation for exactly this reason -- cholesterol came back
 * `trend: stable` with `direction: falling`, and both were true.
 *
 * FIRST TO LATEST, which is what the word means and all it means. A series
 * whose first and last readings match reports `same` even if it moved in
 * between; the chart beside it shows every point.
 */
/*
 * THE WORD AND THE TWO VALUES IT IS ABOUT, FROM ONE COMPARISON.
 *
 * This returned the word alone. The page now prints the pair beside it on the
 * collapsed row, so the values are returned WITH the word rather than left to
 * be picked out again by the consumer.
 *
 * WHAT THIS IS NOT. It is not guarding against a null in the middle of a
 * series: `points` is built from `numeric`, which is already
 * `entries.filter((e) => e.value !== null)`, so every point a series carries
 * has a number and the filter below can remove nothing. Checked, rather than
 * assumed -- the first version of this comment claimed the opposite and was
 * wrong. The filter stays as this file's belt-and-braces convention for a
 * caller who later widens what a point may hold, the same reasoning 6au
 * recorded for the re-check in `assembleHistory`.
 *
 * WHAT IT IS FOR: one comparison, one place. `points[0]` and the last point
 * happen to give the same answer today, and a frontend reading them would be
 * a second copy of the rule that decides WHICH readings this word describes.
 * If that rule ever changes -- to skip a questionable reading, say -- the word
 * and the numbers beside it move together instead of drifting apart. A row
 * whose numbers disagree with its own direction word is the failure 6z caught
 * on the assessed charts.
 */
function movementOf(points) {
  const values = points.map((p) => p.value).filter((v) => v !== null);
  if (values.length < 2) return null;
  const first = values[0];
  const last = values[values.length - 1];
  const word = last === first ? 'same' : last > first ? 'rose' : 'fell';
  return { word, first, last };
}

/**
 * THE SCALE, AS THE UNION OF WHAT THE REPORTS PRINTED.
 *
 * ==========================================================================
 * WHY A UNION AND NOT "THE" INTERVAL
 * ==========================================================================
 *
 * There is no single interval for a series. Measured on this project's own
 * two real reports: of ten plotted parameters, NINE are printed with
 * different reference ranges by the two laboratories -- lymphocytes 22-45 and
 * 20-40, MCV 78-100 and 80-97, CRP `< 6` and `< 5.0`. Only ESR agrees.
 *
 * Methods and populations differ and both laboratories are right about their
 * own assay, so there is no basis here for preferring one. The union contains
 * both, which is the only choice that asserts nothing: a reading inside it is
 * inside SOMEBODY's usual range, and the scale is then at least as wide as
 * every interval the reader's own documents printed.
 *
 * EACH BOUND IS TAKEN INDEPENDENTLY, because a one-sided interval is normal.
 * `< 6` gives a high and no low, and pairing it with a fabricated zero would
 * be inventing the half the laboratory declined to print.
 *
 * ==========================================================================
 * UNITS
 * ==========================================================================
 *
 * A bound is in the units of the row it was printed beside, so a union across
 * two units would be two scales added together -- the failure 6z caught. It
 * cannot happen for a series that is drawn, because `blocked` is exactly the
 * test that the units agree, and the interval comes from the same extraction
 * row as the value. A BLOCKED SERIES IS GIVEN NO SCALE AT ALL anyway, so a
 * future caller that starts plotting blocked readings cannot reach a mixed
 * one by forgetting this.
 */
function referenceScaleOf(points) {
  const lows = points.map((p) => p.labReferenceLow).filter((v) => v !== null);
  const highs = points.map((p) => p.labReferenceHigh).filter((v) => v !== null);
  if (!lows.length && !highs.length) return null;
  return {
    low: lows.length ? Math.min(...lows) : null,
    high: highs.length ? Math.max(...highs) : null,
  };
}

/**
 * WHETHER THE READER'S OWN REPORTS AGREE ABOUT THE RANGE.
 *
 * Three states, and the page says a different thing for each. `differ` covers
 * two situations that look different and mean the same thing to a reader: the
 * printed ranges are not identical, or one report printed a range this
 * pipeline could not reduce to numbers while another did. In both, "your
 * reports do not all print the same range for this test" is true, and in
 * both, a single drawn band would be a claim about which one applies.
 *
 * `agree` requires EVERY point to carry a bound. A series where one report
 * printed 35-48 and the other printed nothing usable is not agreement; it is
 * one opinion and a silence, and calling that agreement is how an absence
 * becomes a reassuring value.
 *
 * THAT RULE IS THE SET COMPARISON, NOT A SEPARATE BRANCH, and the distinction
 * cost a mutant to learn. An explicit `some(s => s === null) -> 'differ'` test
 * was written here and SURVIVED mutation: a null shape beside a non-null one
 * already makes the set size 2, and a set of size 1 containing null is the
 * all-null case `every` has already answered. No input could reach it. It is
 * deleted rather than kept as a guard that reads like it is doing work.
 */
function referenceAgreementOf(points) {
  const shapes = points.map((p) =>
    p.labReferenceLow === null && p.labReferenceHigh === null
      ? null
      : `${p.labReferenceLow}|${p.labReferenceHigh}`
  );
  if (shapes.every((s) => s === null)) return 'none';
  return new Set(shapes).size === 1 ? 'agree' : 'differ';
}

/**
 * Build one series per repeated parameter.
 *
 * `snapshots` are `historyService`'s own, so this reads the same objects
 * Module 28 reads and cannot disagree with it about which reports are in the
 * history or what order they are in.
 *
 * `printed` is OPTIONAL and is `historyService.loadPrintedParameters`'s own
 * shape: `Map<reportId, Map<test_name, extractedParameter>>`. It carries the
 * reference interval each report printed beside the value, which
 * `featureValidation.unmapped` does not keep. Omitted, every series comes back
 * with no scale and the page says so -- which is exactly what it did before
 * this existed, so an older caller degrades to the old behaviour rather than
 * to a wrong one.
 *
 * THE JOIN IS PER REPORT AND BY THE EXACT PRINTED NAME, which is the same
 * join `dashboardService.buildUnanalysedSection` already makes. It works
 * across reports that spell a test differently precisely BECAUSE it is per
 * report: each point is matched against its own document's extraction, so
 * `Lymphocytes` and `LYMPHOCYTES` each find their own row without this file
 * needing to decide they are the same string. (That they are the same TEST is
 * `nameKey`'s job, above, and is a separate question.)
 */
/*
 * `aliases` IS OPTIONAL AND IS MODULE 36'S ANSWER, NOTHING MORE.
 *
 * A `Map` from one `nameKey` to the key it should be grouped under, so two
 * names built from different WORDS can form one series -- which word-set
 * equality cannot do and was never going to. Omit it and every group is
 * exactly what it was before this existed, which is the same degradation
 * `printed` offers: an older caller, a spent quota and an unconfigured key all
 * land on the previous behaviour rather than on a wrong one.
 *
 * IT REGROUPS AND DOES NOTHING ELSE. No value is created, no unit converted,
 * no name rewritten. When a join turns out to unite two units, `blocked`
 * catches it one screen later exactly as it already does -- so a wrong join
 * cannot produce a drawn line across two units even if one gets through.
 */
function buildLabSeries(snapshots, printed, aliases) {
  const rows = Array.isArray(snapshots) ? snapshots : [];
  const groups = new Map();

  for (const snapshot of rows) {
    const when = snapshot && snapshot.chrono_date;
    const unmapped =
      (snapshot && snapshot.validated && Array.isArray(snapshot.validated.unmapped)
        ? snapshot.validated.unmapped
        : []) || [];

    const byName =
      printed instanceof Map ? printed.get(snapshot && snapshot.report_id) : undefined;

    for (const entry of unmapped) {
      const name = entry && entry.test_name;
      const own = nameKey(name);
      if (!own || !when) continue;
      // MODULE 36'S REGROUPING, OR THIS ROW'S OWN KEY. `own` is kept on the
      // entry so a group can afterwards say whether it was assembled from more
      // than one printed vocabulary -- a join the reader can see is the whole
      // difference between regrouping their data and quietly rewriting it.
      const key = (aliases instanceof Map && aliases.get(own)) || own;
      // The extraction row this reading was read off, in THIS report. Absent
      // whenever the caller supplied no printed parameters at all, and absent
      // for a single row whose name the extraction and the feature engineer
      // spell differently -- which is counted rather than assumed away, see
      // `referenceCoverage`.
      const source = byName instanceof Map ? byName.get(String(name)) : undefined;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push({
        date: when,
        reportId: snapshot.report_id,
        printed: String(name),
        sourceKey: own,
        unit: entry.unit === null || entry.unit === undefined ? null : String(entry.unit),
        value: numericValue(entry.value_raw),
        // AS THE LABORATORY PRINTED IT. A reading that is not a number is
        // still a result -- "Negative", "Trace", "Not Detected" -- and the
        // only way to show one is to show the text.
        valueRaw:
          entry.value_raw === null || entry.value_raw === undefined
            ? null
            : String(entry.value_raw),
        labFlag: labFlagOf(source && source.flag),
        labReferenceLow: numericBound(source && source.reference_low),
        labReferenceHigh: numericBound(source && source.reference_high),
        // AS PRINTED. The only honest thing to show for `F: 36 - 46 M: 40 -
        // 50`, which has no numeric form here on purpose.
        labReferenceRaw:
          source && typeof source.reference_range_raw === 'string' && source.reference_range_raw
            ? source.reference_range_raw
            : null,
      });
    }
  }

  const series = [];
  // PARAMETERS THAT CANNOT MAKE A SERIES, BUT ARE STILL ON THE REPORT.
  //
  // These used to be counted and discarded. A reader holding two reports with
  // 22 parameters between them saw twelve, and a number saying twenty-two had
  // been "considered" -- which answers the question "how many did you look at"
  // and not the question they were asking, which is "where are the rest".
  //
  // A parameter seen once cannot be trended and nothing here pretends
  // otherwise: these carry readings and dates, no line, no direction and no
  // scale. But "we cannot draw this" is not a reason to withhold the
  // laboratory's own number, and withholding it is this file's standing
  // failure mode -- an absence that reads as though there were nothing there.
  const readings = [];
  let singleReportCount = 0;
  let notNumericCount = 0;

  for (const [key, entries] of groups) {
    // OLDEST FIRST. The history arrives newest-first; a chart read right to
    // left would invert every series on the page.
    entries.sort((a, b) => new Date(a.date) - new Date(b.date));

    const numeric = entries.filter((e) => e.value !== null);

    // The name the reader saw most recently, so the label matches the report
    // in their hand rather than an older spelling of the same test.
    //
    // THIS RULE IS KEPT FOR JOINED GROUPS TOO, in preference to Module 36's
    // own `display_name`. The newest report is the one the reader is holding,
    // and a panel titled with the words on it is easier to find than a panel
    // titled with the longest name available.
    const name = entries[entries.length - 1].printed;

    // WAS THIS GROUP ASSEMBLED FROM MORE THAN ONE PRINTED NAME?
    //
    // More than one `sourceKey` means Module 36 joined names that word-set
    // equality kept apart, and the reader is entitled to know which -- their
    // report says `Polymorphs` and this panel says `NEUTROPHILS`, and without
    // the list that looks like a parameter they never had. Null when nothing
    // was joined, which is every group when no aliases were supplied.
    const sourceKeys = new Set(entries.map((e) => e.sourceKey));
    const joinedFrom =
      sourceKeys.size > 1 ? [...new Set(entries.map((e) => e.printed))] : null;

    // THE MARKING ON THE MOST RECENT REPORT, AND ONLY THAT ONE.
    //
    // Strictly the last row's flag, never the last row that HAPPENED to carry
    // one. PCV is the case that decides it: the older report marked it low and
    // the newer marked nothing, and reaching back for the older marking would
    // present a stale verdict as the reader's current status. Null here means
    // "the latest laboratory marked nothing", which is a different fact from
    // "normal" and stays different all the way to the screen.
    const latestFlagOf = (rows) => (rows.length ? rows[rows.length - 1].labFlag : null);

    // EVERY row, numeric or not, as printed. Used only by `readings`.
    const asPrinted = () =>
      entries.map((e) => ({
        date: e.date,
        reportId: e.reportId,
        printed: e.printed,
        value: e.value,
        valueRaw: e.valueRaw,
        unit: e.unit,
        labFlag: e.labFlag,
      }));

    if (entries.length < 2) {
      singleReportCount += 1;
      readings.push({ key, name, joinedFrom, reason: 'one_report', rows: asPrinted(), latestFlag: latestFlagOf(entries) });
      continue;
    }
    if (numeric.length < 2) {
      notNumericCount += 1;
      readings.push({ key, name, joinedFrom, reason: 'not_numeric', rows: asPrinted(), latestFlag: latestFlagOf(entries) });
      continue;
    }

    // THE UNIT KEYS, MOVED ONTO ANY DECLARED SHARED SCALE FIRST.
    //
    // `unitKey` folds spelling; this folds two unit strings that mean one
    // scale, which is a clinical claim and lives in `unitEquivalence.js`.
    // SGPT in `U/L` and `IU/L`, and MCHC in `g/dL` and `%`, are the two on
    // these reports. Applied per test, because `%` is a mass concentration on
    // MCHC and a proportion of the white cell count on the differential.
    //
    // NO READING IS ALTERED. The declarations carry no factor and cannot: the
    // numbers were already the same, and this only decides whether they may
    // share an axis.
    const rawKeys = numeric.map((e) => unitKey(e.unit));
    const units = [...new Set(rawKeys.map((k) => canonicalUnitKey(key, k)))];
    // WHICH DECLARATION WAS RELIED ON, or null. Carried to the screen so a
    // reader can be told that two differently-labelled readings were treated
    // as one scale, and on whose authority -- `verified` is false on every
    // row today, and a reader must not be told a checked equivalence and an
    // unchecked one in the same words.
    const appliedEquivalence = (() => {
      if (new Set(rawKeys).size < 2) return null;
      for (const k of rawKeys) {
        const found = equivalenceFor(key, k);
        if (found && found.canonical !== k) {
          return {
            id: found.entry.id,
            label: found.entry.label,
            verified: found.entry.verified === true,
          };
        }
      }
      return null;
    })();
    // A MISSING UNIT IS NOT A DIFFERENT UNIT.
    //
    // `AVERAGE BLOOD GLUCOSE` is `154 mg/dL` on one report and `121.94` with
    // NO unit on the other, and the panel was telling the reader the two
    // reports gave it in different units. They do not: one of them gave none.
    // The outcome is the same -- there is no basis for drawing a line, because
    // an absent unit cannot be confirmed to match a present one -- but the
    // STATED REASON was false, and `blocked.units` could name only one unit
    // while claiming they differed.
    //
    // This is the project's standing failure mode in miniature: an absence
    // rendered as a negative result. The values are still shown; only the
    // sentence changes.
    const named = units.filter((u) => u !== '');
    const unitMissing = named.length !== units.length;
    const blocked =
      units.length > 1
        ? {
            reason: unitMissing && named.length <= 1 ? 'unit_missing' : 'units_differ',
            // AS PRINTED, not as compared. The reader is being told these two
            // reports disagree; showing them the folded key would be showing
            // them this file's arithmetic instead of their own documents.
            units: [...new Set(numeric.map((e) => e.unit).filter(Boolean))],
          }
        : null;

    const points = numeric.map((e) => ({
      date: e.date,
      value: e.value,
      reportId: e.reportId,
      // Kept per point: a series whose name changed spelling between
      // reports should be able to say so rather than quietly presenting the
      // newest name as though it had always been used.
      printed: e.printed,
      unit: e.unit,
      // THE LABORATORY'S OWN, and named so no reader of this object can
      // mistake whose numbers they are -- the same naming
      // `dashboardService.buildUnanalysedSection` uses for the same fact.
      labFlag: e.labFlag,
      labReferenceLow: e.labReferenceLow,
      labReferenceHigh: e.labReferenceHigh,
      labReferenceRaw: e.labReferenceRaw,
    }));

    // ONE CALL, because the word and the pair below come out of it together.
    const movement = blocked ? null : movementOf(points);

    series.push({
      key,
      name,
      // The other printed names merged into this one, or null. See above.
      joinedFrom,
      // The declared unit equivalence this series relied on, or null.
      unitEquivalence: appliedEquivalence,
      unit: blocked ? null : numeric[numeric.length - 1].unit,
      blocked,
      points,
      // WHICH WAY THE NUMBERS WENT -- arithmetic, never a verdict. See
      // `movementOf` for why this is not improving/worsening/stable.
      //
      // NULL ON A BLOCKED SERIES. Two reports printing different units have
      // not been shown to have moved at all: 101.9 U/L and 13 IU/L may be the
      // same measurement twice, and "fell" would be this file asserting a
      // change it refused to plot one line above.
      movement: movement ? movement.word : null,
      // THE TWO READINGS THE WORD IS ABOUT, so the collapsed row can show
      // them without choosing them. Null exactly when `movement` is null --
      // a blocked series and a series with fewer than two usable numbers both
      // get no pair, because in neither case has a change been established.
      movementFrom: movement ? movement.first : null,
      movementTo: movement ? movement.last : null,
      // The laboratory's marking for the MOST RECENT reading -- the report in
      // the reader's hand. Null when that laboratory marked nothing.
      latestFlag: latestFlagOf(points),
      // SETS THE SCALE, IS NOT A BAND, AND IS NEVER DRAWN. Null on a blocked
      // series, so a mixed-unit union cannot be handed to anything.
      referenceScale: blocked ? null : referenceScaleOf(points),
      referenceAgreement: referenceAgreementOf(points),
      // STATED, NOT INFERRED FROM THE SCALE BEING NARROW. A reader -- and the
      // next person to debug this -- can tell "eight of nine reports printed
      // a range" from "they disagree", which `differ` alone cannot.
      referenceCoverage: {
        withBounds: points.filter(
          (p) => p.labReferenceLow !== null || p.labReferenceHigh !== null
        ).length,
        total: points.length,
      },
    });
  }

  // Alphabetical, because there is no clinical ordering available here and an
  // incidental one -- the order the extraction happened to read them in --
  // would look like a ranking.
  series.sort((a, b) => a.name.localeCompare(b.name));
  readings.sort((a, b) => a.name.localeCompare(b.name));

  return {
    series,
    // Shown, not just counted. See the declaration above.
    readings,
    // STATED, NOT IMPLIED BY ABSENCE. A reader who sees nine charts should be
    // able to tell that eighteen parameters were considered.
    consideredCount: groups.size,
    plottedCount: series.filter((s) => !s.blocked).length,
    blockedCount: series.filter((s) => s.blocked).length,
    singleReportCount,
    notNumericCount,
    // HOW MANY SERIES GOT A SCALE, so the page can say which sentence it is
    // entitled to say without re-deriving it and getting a different answer.
    //
    // A blocked series is excluded by having no scale, not by being named
    // here. `!s.blocked && ...` was written first and SURVIVED mutation --
    // `referenceScale` is already null for every blocked series, so the extra
    // clause could never change the count. One guard, in the place that does
    // the work.
    scaledCount: series.filter((s) => s.referenceScale !== null).length,
  };
}

/**
 * THE SERIES MODULE 35 CAN BE ASKED ABOUT.
 *
 * A series qualifies only when it has everything the classifier needs and
 * nothing it must not be given:
 *
 *   - NOT BLOCKED. Two units have not been shown to have moved at all, so
 *     there is no change to classify -- the same reason `movement` is null.
 *   - TWO NUMERIC READINGS, because a trend needs two ends.
 *
 * The laboratory's own interval travels with it, for a "both extremes are
 * unfavourable" polarity to measure against. The model is never asked for one.
 */
function classifiableSeries(built) {
  const rows = (built && Array.isArray(built.series) ? built.series : []).filter(
    (s) => !s.blocked && s.points.length >= 2
  );
  return rows.map((s) => ({
    test_name: s.name,
    first_value: s.points[0].value,
    last_value: s.points[s.points.length - 1].value,
    unit: s.unit === undefined ? null : s.unit,
    reference_low: s.referenceScale ? s.referenceScale.low : null,
    reference_high: s.referenceScale ? s.referenceScale.high : null,
  }));
}

/**
 * Attach Module 35's verdicts to the series they belong to.
 *
 * ==========================================================================
 * A VERDICT IS ONLY ATTACHED WHEN IT CLASSIFIED SOMETHING
 * ==========================================================================
 *
 * `outcome` is what decides this, never `trend` -- the same rule the assessed
 * timeline branches on, and for the same reason: a payload carrying a
 * direction without a classification must not be rendered as though it had
 * one. §6z printed the string "null" as a direction once already.
 *
 * A series with no verdict, or a refused one, keeps the `movement` word it
 * already had and gains nothing. That is the designed degradation: a spent
 * quota, an unconfigured key and a test whose direction of benefit is not
 * established all land in the same place, which is the panel saying what the
 * numbers did and not what it means.
 *
 * MATCHED BY THE NAME THAT WAS SENT. `classifiableSeries` sends `s.name` and
 * this reads `test_name` back, so a service that echoes the name it was given
 * matches exactly. Nothing is normalised here -- a fuzzy match would let one
 * test's verdict land on another's panel, which is the worst failure this
 * whole feature can have.
 */
function attachVerdicts(built, verdicts) {
  const byName = new Map();
  for (const entry of Array.isArray(verdicts) ? verdicts : []) {
    const row = entry && typeof entry === 'object' ? entry : {};
    if (typeof row.test_name === 'string' && row.test_name && !byName.has(row.test_name)) {
      byName.set(row.test_name, row);
    }
  }
  if (!byName.size) return built;

  const series = (built.series || []).map((s) => {
    const verdict = byName.get(s.name);
    const classified =
      verdict &&
      verdict.outcome === 'TREND_CLASSIFIED' &&
      typeof verdict.trend === 'string' &&
      verdict.trend !== '';
    if (!classified) return s;
    return {
      ...s,
      trend: verdict.trend,
      classified: true,
      // THE ARITHMETIC, CARRIED. A reader who asks why a fall is "stable" is
      // entitled to the threshold it was measured against, and a reviewer is
      // entitled to recompute it.
      significantChangePct: verdict.significant_change_pct ?? null,
      trendBasis: typeof verdict.basis === 'string' ? verdict.basis : null,
      // WHERE THE THRESHOLD CAME FROM, carried to the screen. A reviewable
      // figure and a model-supplied one must not be described in the same
      // words -- the same separation `labFlag` keeps between the laboratory's
      // verdict and this platform's. `null` is treated as unknown provenance
      // by the page, which renders the more cautious of the two.
      trendSource: typeof verdict.variation_source === 'string' ? verdict.variation_source : null,
      trendVerified: verdict.variation_verified === true,
    };
  });

  return {
    ...built,
    series,
    classifiedCount: series.filter((s) => s.classified === true).length,
  };
}

/**
 * The printed names that could not make a series, to ask Module 36 about.
 *
 * ==========================================================================
 * READINGS ONLY, AND THAT IS A DELIBERATE LIMIT
 * ==========================================================================
 *
 * A `readings` entry is a parameter seen on one report, or one whose results
 * are not numbers. Those are the rows a join can rescue: two of them under
 * different words become a two-point series and can carry a direction.
 *
 * SERIES ARE NOT OFFERED FOR JOINING. A series already has its points, and
 * merging two of them would silently redraw charts the reader has already
 * looked at on the strength of a model call. The case exists -- a third
 * spelling of an already-trended test -- and it is left alone until somebody
 * asks for it, because the cost of being wrong is higher there and the gain
 * is smaller.
 */
function unjoinedNames(built) {
  const rows = built && Array.isArray(built.readings) ? built.readings : [];
  const names = [];
  for (const row of rows) {
    if (row && typeof row.name === 'string' && row.name) names.push(row.name);
  }
  return [...new Set(names)];
}

/**
 * Module 36's groups, turned into the `aliases` map `buildLabSeries` takes.
 *
 * ==========================================================================
 * THE CANONICAL KEY IS CHOSEN BY A RULE, NOT BY THE MODEL
 * ==========================================================================
 *
 * Every name in a group is pointed at the SMALLEST of the group's own keys,
 * sorted as strings. Any member would group them equally well; picking the
 * smallest makes the result stable across calls, so two page loads that get
 * the same groups in a different order produce the same `key` -- and `key`
 * reaches React as a list key. A group whose identity wandered between
 * requests would remount panels for no reason.
 *
 * A NAME THAT DOES NOT FOLD TO A KEY IS DROPPED, and a group left with fewer
 * than two keys is skipped: aliasing a single key to itself is a no-op that
 * would only make `joinedFrom` claim a join that did not happen.
 */
function aliasMap(groups) {
  const out = new Map();
  for (const group of Array.isArray(groups) ? groups : []) {
    const names = group && Array.isArray(group.names) ? group.names : [];
    const keys = [...new Set(names.map((n) => nameKey(n)).filter(Boolean))];
    if (keys.length < 2) continue;
    const canonical = keys.slice().sort()[0];
    for (const key of keys) {
      // FIRST GROUP WINS. Module 36 already refuses a name that appears in two
      // groups, so this cannot normally fire; if a future producer stops
      // enforcing that, one test's readings must not migrate onto another's
      // chart on the strength of emission order.
      if (!out.has(key)) out.set(key, canonical);
    }
  }
  return out;
}

/*
 * MODULE 29's TABLE COVERS THE FEATURES THIS PLATFORM ASSESSES. THIS COVERS
 * THE REST OF THE REPORT.
 *
 * The comparison card showed twelve rows while the two reports carried 28
 * parameters between them -- the same gap the timeline had before
 * `buildLabSeries`, and the reader found it the same way: by counting what was
 * on their reports and what was on the screen.
 *
 * IT IS A TRANSFORM OVER `buildLabSeries`, NOT A SECOND COMPARATOR. Run that
 * over ONLY the two chosen reports and it already answers everything a
 * comparison row needs: which parameters both reports carry, which only one
 * does, which disagree about units, what the laboratory marked, and -- once
 * Module 35's verdicts are attached -- whether the change was better or worse.
 * Writing a second grouping would mean two files deciding that
 * `Polymorphs` and `NEUTROPHILS` are one test, and eventually disagreeing.
 *
 * PREVIOUS AND CURRENT ARE THE REQUESTED PAIR, NOT THE DATE ORDER. The picker
 * allows an out-of-order pair and the card says so; Module 29 keys its own
 * rows off the requested baseline and comparison, so these are keyed off the
 * report ids too. Otherwise one table would have two ideas of which column is
 * "previous".
 */
const COMPARISON_CATEGORY = {
  improving: 'improved',
  worsening: 'worsened',
  stable: 'unchanged',
};

/** The laboratory's own transition, and ONLY when it marked both reports. */
function transitionOf(previousFlag, currentFlag) {
  // A NULL FLAG IS NOT "NORMAL". PCV is marked low on the older report and
  // unmarked on the newer, and reading the absence as normal would invent a
  // recovery. Both sides must carry a marking before a crossing is claimed.
  if (!previousFlag || !currentFlag) return null;
  const wasNormal = previousFlag === 'normal';
  const isNormal = currentFlag === 'normal';
  if (wasNormal && !isNormal) return 'newly_abnormal';
  if (!wasNormal && isNormal) return 'newly_normal';
  return null;
}

function symbolOf(previous, current) {
  if (previous === null || current === null) return null;
  if (current > previous) return '↑';
  if (current < previous) return '↓';
  return '→';
}

function buildLabComparison(built, baselineId, comparisonId) {
  const rows = [];
  const pick = (entries, reportId) =>
    (entries || []).find((e) => e.reportId === reportId) || null;

  for (const entry of (built && built.series) || []) {
    const before = pick(entry.points, baselineId);
    const after = pick(entry.points, comparisonId);
    if (!before && !after) continue;

    const previous = before ? before.value : null;
    const current = after ? after.value : null;
    const blocked = Boolean(entry.blocked);
    const comparable = !blocked && previous !== null && current !== null;

    // THE SAME PRECEDENCE MODULE 29 USES, in its own words: a reference
    // interval crossing outranks the change axis, then the change axis, then
    // "it moved but nobody will say whether that is better".
    const transition = comparable
      ? transitionOf(before.labFlag, after.labFlag)
      : null;
    let category = 'not_classifiable';
    if (!comparable) {
      category = 'not_classifiable';
    } else if (transition) {
      category = transition;
    } else if (entry.classified === true && COMPARISON_CATEGORY[entry.trend]) {
      category = COMPARISON_CATEGORY[entry.trend];
    } else if (previous !== current) {
      // It moved and no polarity would call that better or worse -- which is
      // what `changed_direction_only` means in `report_comparator._category`.
      category = 'changed_direction_only';
    } else {
      // Two identical numbers. Arithmetic, not a judgement about a band.
      category = 'unchanged';
    }

    rows.push({
      key: entry.key,
      name: entry.name,
      joinedFrom: entry.joinedFrom,
      // The declared equivalence that let two unit strings share a scale.
      unitEquivalence: entry.unitEquivalence || null,
      previous,
      current,
      // AS PRINTED ON EACH SIDE. A blocked row's two units are the whole
      // reason it is not classifiable, so both are carried rather than one
      // being chosen to stand for the pair.
      previousUnit: before ? before.unit : null,
      currentUnit: after ? after.unit : null,
      unit: blocked ? null : entry.unit,
      blocked: entry.blocked || null,
      previousFlag: before ? before.labFlag : null,
      currentFlag: after ? after.labFlag : null,
      category,
      symbol: comparable ? symbolOf(previous, current) : null,
      trend: entry.trend === undefined ? null : entry.trend,
      classified: entry.classified === true,
      significantChangePct:
        entry.significantChangePct === undefined ? null : entry.significantChangePct,
      trendSource: entry.trendSource === undefined ? null : entry.trendSource,
      trendVerified: entry.trendVerified === true,
    });
  }

  // A PARAMETER ON ONE OF THE TWO REPORTS IS STILL ON A REPORT.
  //
  // The existing table already has a shape for this -- "Not measured. This
  // parameter was not on the later report." -- so these rows use it rather
  // than being dropped, which is what made the card look short in the first
  // place.
  for (const entry of (built && built.readings) || []) {
    const before = pick(entry.rows, baselineId);
    const after = pick(entry.rows, comparisonId);
    if (!before && !after) continue;

    rows.push({
      key: entry.key,
      name: entry.name,
      joinedFrom: entry.joinedFrom,
      previous: before ? before.value : null,
      current: after ? after.value : null,
      // AS PRINTED, so a non-numeric result is shown as the text it is.
      previousRaw: before ? before.valueRaw : null,
      currentRaw: after ? after.valueRaw : null,
      previousUnit: before ? before.unit : null,
      currentUnit: after ? after.unit : null,
      unit: (after && after.unit) || (before && before.unit) || null,
      blocked: null,
      previousFlag: before ? before.labFlag : null,
      currentFlag: after ? after.labFlag : null,
      // NEVER a change: one reading cannot be compared with nothing, and a
      // non-numeric result cannot be compared at all.
      category: 'not_classifiable',
      symbol: null,
      trend: null,
      classified: false,
      significantChangePct: null,
      trendSource: null,
      trendVerified: false,
    });
  }

  rows.sort((a, b) => String(a.name).localeCompare(String(b.name)));
  return { rows, count: rows.length };
}

module.exports = {
  buildLabSeries,
  buildLabComparison,
  classifiableSeries,
  attachVerdicts,
  unjoinedNames,
  aliasMap,
  nameKey,
  unitKey,
  numericValue,
  numericBound,
  referenceScaleOf,
  referenceAgreementOf,
};
