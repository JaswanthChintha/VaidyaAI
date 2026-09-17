'use strict';

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
function unitKey(unit) {
  const text = String(unit === null || unit === undefined ? '' : unit)
    .toLowerCase()
    .replace(/\s+/g, '');
  return text;
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
function buildLabSeries(snapshots, printed) {
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
      const key = nameKey(name);
      if (!key || !when) continue;
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
    const name = entries[entries.length - 1].printed;

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
      readings.push({ key, name, reason: 'one_report', rows: asPrinted(), latestFlag: latestFlagOf(entries) });
      continue;
    }
    if (numeric.length < 2) {
      notNumericCount += 1;
      readings.push({ key, name, reason: 'not_numeric', rows: asPrinted(), latestFlag: latestFlagOf(entries) });
      continue;
    }

    const units = [...new Set(numeric.map((e) => unitKey(e.unit)))];
    const blocked =
      units.length > 1
        ? {
            reason: 'units_differ',
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
    };
  });

  return {
    ...built,
    series,
    classifiedCount: series.filter((s) => s.classified === true).length,
  };
}

module.exports = {
  buildLabSeries,
  classifiableSeries,
  attachVerdicts,
  nameKey,
  unitKey,
  numericValue,
  numericBound,
  referenceScaleOf,
  referenceAgreementOf,
};
