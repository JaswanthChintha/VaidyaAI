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
 * Build one series per repeated parameter.
 *
 * `snapshots` are `historyService`'s own, so this reads the same objects
 * Module 28 reads and cannot disagree with it about which reports are in the
 * history or what order they are in.
 */
function buildLabSeries(snapshots) {
  const rows = Array.isArray(snapshots) ? snapshots : [];
  const groups = new Map();

  for (const snapshot of rows) {
    const when = snapshot && snapshot.chrono_date;
    const unmapped =
      (snapshot && snapshot.validated && Array.isArray(snapshot.validated.unmapped)
        ? snapshot.validated.unmapped
        : []) || [];

    for (const entry of unmapped) {
      const printed = entry && entry.test_name;
      const key = nameKey(printed);
      if (!key || !when) continue;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push({
        date: when,
        reportId: snapshot.report_id,
        printed: String(printed),
        unit: entry.unit === null || entry.unit === undefined ? null : String(entry.unit),
        value: numericValue(entry.value_raw),
      });
    }
  }

  const series = [];
  let singleReportCount = 0;
  let notNumericCount = 0;

  for (const [key, entries] of groups) {
    // OLDEST FIRST. The history arrives newest-first; a chart read right to
    // left would invert every series on the page.
    entries.sort((a, b) => new Date(a.date) - new Date(b.date));

    const numeric = entries.filter((e) => e.value !== null);
    if (entries.length < 2) {
      singleReportCount += 1;
      continue;
    }
    if (numeric.length < 2) {
      notNumericCount += 1;
      continue;
    }

    // The name the reader saw most recently, so the label matches the report
    // in their hand rather than an older spelling of the same test.
    const name = entries[entries.length - 1].printed;

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

    series.push({
      key,
      name,
      unit: blocked ? null : numeric[numeric.length - 1].unit,
      blocked,
      points: numeric.map((e) => ({
        date: e.date,
        value: e.value,
        reportId: e.reportId,
        // Kept per point: a series whose name changed spelling between
        // reports should be able to say so rather than quietly presenting the
        // newest name as though it had always been used.
        printed: e.printed,
        unit: e.unit,
      })),
    });
  }

  // Alphabetical, because there is no clinical ordering available here and an
  // incidental one -- the order the extraction happened to read them in --
  // would look like a ranking.
  series.sort((a, b) => a.name.localeCompare(b.name));

  return {
    series,
    // STATED, NOT IMPLIED BY ABSENCE. A reader who sees nine charts should be
    // able to tell that eighteen parameters were considered.
    consideredCount: groups.size,
    plottedCount: series.filter((s) => !s.blocked).length,
    blockedCount: series.filter((s) => s.blocked).length,
    singleReportCount,
    notNumericCount,
  };
}

module.exports = { buildLabSeries, nameKey, unitKey, numericValue };
