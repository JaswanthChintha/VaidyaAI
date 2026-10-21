'use strict';

const { UNIT_EQUIVALENCE } = require('./unitEquivalence');
const { LAB_RESTATEMENTS } = require('./labRestatements');


function nameKey(printed) {
  const words = String(printed || '')
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter(Boolean);
  if (!words.length) return null;
  return words.slice().sort().join(' ');
}

const _MICRO = /[µμ]/g;
const _I_L = /[il]/g;

function unitKey(unit) {
  const text = String(unit === null || unit === undefined ? '' : unit)
    .toLowerCase()
    .replace(/\s+/g, '');
  return text.replace(_MICRO, 'u').replace(_I_L, 'i');
}

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

function equivalenceFor(testKey, key) {
  if (!key) return null;
  const byUnit = _EQUIV_SCOPED.get(testKey);
  const scoped = byUnit ? byUnit.get(key) : undefined;
  if (scoped) return scoped;
  return _EQUIV_GLOBAL.get(key) || null;
}

const _RESTATEMENTS = new Map();
for (const entry of LAB_RESTATEMENTS) {
  for (const printed of entry.names) {
    const key = nameKey(printed);
    if (key && !_RESTATEMENTS.has(key)) _RESTATEMENTS.set(key, entry);
  }
}

function canonicalUnitKey(testKey, key) {
  const found = equivalenceFor(testKey, key);
  return found ? found.canonical : key;
}

function numericValue(raw) {
  if (typeof raw === 'number') return Number.isFinite(raw) ? raw : null;
  if (typeof raw !== 'string') return null;
  const cleaned = raw.replace(/,/g, '').trim();
  if (cleaned === '') return null;
  const value = Number(cleaned);
  return Number.isFinite(value) ? value : null;
}

function numericBound(raw) {
  return typeof raw === 'number' && Number.isFinite(raw) ? raw : null;
}

function labFlagOf(raw) {
  if (typeof raw !== 'string') return null;
  const text = raw.trim().toLowerCase();
  return text === '' ? null : text;
}

function movementOf(points) {
  const values = points.map((p) => p.value).filter((v) => v !== null);
  if (values.length < 2) return null;
  const first = values[0];
  const last = values[values.length - 1];
  const word = last === first ? 'same' : last > first ? 'rose' : 'fell';
  return { word, first, last };
}

function referenceScaleOf(points) {
  const lows = points.map((p) => p.labReferenceLow).filter((v) => v !== null);
  const highs = points.map((p) => p.labReferenceHigh).filter((v) => v !== null);
  if (!lows.length && !highs.length) return null;
  return {
    low: lows.length ? Math.min(...lows) : null,
    high: highs.length ? Math.max(...highs) : null,
  };
}

function referenceAgreementOf(points) {
  const shapes = points.map((p) =>
    p.labReferenceLow === null && p.labReferenceHigh === null
      ? null
      : `${p.labReferenceLow}|${p.labReferenceHigh}`
  );
  if (shapes.every((s) => s === null)) return 'none';
  return new Set(shapes).size === 1 ? 'agree' : 'differ';
}

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
      const key = (aliases instanceof Map && aliases.get(own)) || own;
      const source = byName instanceof Map ? byName.get(String(name)) : undefined;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push({
        date: when,
        reportId: snapshot.report_id,
        printed: String(name),
        sourceKey: own,
        unit: entry.unit === null || entry.unit === undefined ? null : String(entry.unit),
        value: numericValue(entry.value_raw),
        valueRaw:
          entry.value_raw === null || entry.value_raw === undefined
            ? null
            : String(entry.value_raw),
        labFlag: labFlagOf(source && source.flag),
        labReferenceLow: numericBound(source && source.reference_low),
        labReferenceHigh: numericBound(source && source.reference_high),
        labReferenceRaw:
          source && typeof source.reference_range_raw === 'string' && source.reference_range_raw
            ? source.reference_range_raw
            : null,
      });
    }
  }

  const series = [];
  const readings = [];
  let singleReportCount = 0;
  let notNumericCount = 0;
  let restatedCount = 0;

  for (const [key, entries] of groups) {
    entries.sort((a, b) => new Date(a.date) - new Date(b.date));

    const numeric = entries.filter((e) => e.value !== null);

    const name = entries[entries.length - 1].printed;

    const sourceKeys = new Set(entries.map((e) => e.sourceKey));
    const joinedFrom =
      sourceKeys.size > 1 ? [...new Set(entries.map((e) => e.printed))] : null;

    const latestFlagOf = (rows) => (rows.length ? rows[rows.length - 1].labFlag : null);

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

    const restatement = _RESTATEMENTS.get(key);
    if (restatement) {
      restatedCount += 1;
      readings.push({
        key,
        name,
        joinedFrom,
        reason: 'restates_assessed_feature',
        restates: restatement.restates,
        rows: asPrinted(),
        latestFlag: latestFlagOf(entries),
      });
      continue;
    }

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

    const rawKeys = numeric.map((e) => unitKey(e.unit));
    const canonKeys = rawKeys.map((k) => canonicalUnitKey(key, k));
    const distinctKeys = [...new Set(canonKeys)];
    const presentKeys = distinctKeys.filter((u) => u !== '');

    const someReadingIsSilent = distinctKeys.length > presentKeys.length;
    const units = someReadingIsSilent ? presentKeys : distinctKeys;
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
    const blocked =
      units.length > 1
        ? {
            reason: 'units_differ',
            units: [...new Set(numeric.map((e) => e.unit).filter(Boolean))],
          }
        : null;

    const printedUnit = (() => {
      for (let i = numeric.length - 1; i >= 0; i -= 1) {
        if (numeric[i].unit) return numeric[i].unit;
      }
      return null;
    })();

    const unitAssumed =
      someReadingIsSilent && !blocked && printedUnit
        ? { unit: printedUnit, reason: 'not_printed' }
        : null;

    const points = numeric.map((e) => ({
      date: e.date,
      value: e.value,
      reportId: e.reportId,
      printed: e.printed,
      unit: e.unit,
      labFlag: e.labFlag,
      labReferenceLow: e.labReferenceLow,
      labReferenceHigh: e.labReferenceHigh,
      labReferenceRaw: e.labReferenceRaw,
    }));

    const movement = blocked ? null : movementOf(points);

    series.push({
      key,
      name,
      joinedFrom,
      unitEquivalence: appliedEquivalence,
      unit: blocked ? null : printedUnit,
      unitAssumed,
      blocked,
      points,
      movement: movement ? movement.word : null,
      movementFrom: movement ? movement.first : null,
      movementTo: movement ? movement.last : null,
      latestFlag: latestFlagOf(points),
      referenceScale: blocked ? null : referenceScaleOf(points),
      referenceAgreement: referenceAgreementOf(points),
      referenceCoverage: {
        withBounds: points.filter(
          (p) => p.labReferenceLow !== null || p.labReferenceHigh !== null
        ).length,
        total: points.length,
      },
    });
  }

  series.sort((a, b) => a.name.localeCompare(b.name));
  readings.sort((a, b) => a.name.localeCompare(b.name));

  return {
    series,
    readings,
    consideredCount: groups.size,
    plottedCount: series.filter((s) => !s.blocked).length,
    blockedCount: series.filter((s) => s.blocked).length,
    singleReportCount,
    notNumericCount,
    restatedCount,
    scaledCount: series.filter((s) => s.referenceScale !== null).length,
  };
}

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
      significantChangePct: verdict.significant_change_pct ?? null,
      trendBasis: typeof verdict.basis === 'string' ? verdict.basis : null,
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

function unjoinedNames(built) {
  const rows = built && Array.isArray(built.readings) ? built.readings : [];
  const names = [];
  for (const row of rows) {
    if (row && typeof row.name === 'string' && row.name) names.push(row.name);
  }
  return [...new Set(names)];
}

function aliasMap(groups) {
  const out = new Map();
  for (const group of Array.isArray(groups) ? groups : []) {
    const names = group && Array.isArray(group.names) ? group.names : [];
    const keys = [...new Set(names.map((n) => nameKey(n)).filter(Boolean))];
    if (keys.length < 2) continue;
    const canonical = keys.slice().sort()[0];
    for (const key of keys) {
      if (!out.has(key)) out.set(key, canonical);
    }
  }
  return out;
}

const COMPARISON_CATEGORY = {
  improving: 'improved',
  worsening: 'worsened',
  stable: 'unchanged',
};

function transitionOf(previousFlag, currentFlag) {
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
      category = 'changed_direction_only';
    } else {
      category = 'unchanged';
    }

    rows.push({
      key: entry.key,
      name: entry.name,
      joinedFrom: entry.joinedFrom,
      unitEquivalence: entry.unitEquivalence || null,
      unitAssumed: entry.unitAssumed || null,
      previous,
      current,
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
      previousRaw: before ? before.valueRaw : null,
      currentRaw: after ? after.valueRaw : null,
      previousUnit: before ? before.unit : null,
      currentUnit: after ? after.unit : null,
      unit: (after && after.unit) || (before && before.unit) || null,
      blocked: null,
      previousFlag: before ? before.labFlag : null,
      currentFlag: after ? after.labFlag : null,
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
