'use strict';

const Report = require('../models/Report');
const config = require('../config/env');
const ApiError = require('../utils/ApiError');
const { ownerScopedFilter, assertCanAccess, OWNER_ONLY } = require('../utils/ownership');
const { comparePair } = require('../utils/printedIdentity');


const EXCLUSION_REASONS = Object.freeze({
  NOT_ANALYSED: 'NOT_ANALYSED',
  NO_VALIDATED_FEATURES: 'NO_VALIDATED_FEATURES',
  SOMEONE_ELSE: 'SOMEONE_ELSE',
});

const INCLUSION_FILTER = Object.freeze({
  'analysis.version': { $gt: 0 },
  featureValidation: { $exists: true, $ne: null },
  'subject.owner': { $ne: 'other' },
});

const HISTORY_PROJECTION =
  'user chronoDate reportDate printedDate printedDateStatus status analysis.version +featureValidation';


async function assembleHistory({ user }) {
  const cap = config.history.maxReports;
  const ownFilter = (base = {}) => ownerScopedFilter(user, { ...OWNER_ONLY, base });

  const totalReports = await Report.countDocuments(ownFilter());

  const rows = await Report.find(ownFilter(INCLUSION_FILTER))
    .select(HISTORY_PROJECTION)
    .sort({ chronoDate: -1, _id: -1 })
    .limit(cap + 1)
    .lean();

  const truncated = rows.length > cap;
  if (truncated) rows.length = cap;

  for (const row of rows) assertCanAccess(user, row, { ...OWNER_ONLY });

  rows.reverse();

  const snapshots = [];
  const included = [];
  for (const row of rows) {
    const reportId = String(row._id);
    snapshots.push({
      report_id: reportId,
      chrono_date: new Date(row.chronoDate).toISOString(),
      validated: row.featureValidation,
    });
    included.push({
      reportId,
      chronoDate: row.chronoDate,
      reportDate: row.reportDate || null,
      printedDate: row.printedDate || null,
      printedDateStatus: row.printedDateStatus || null,
      status: row.status,
    });
  }

  return {
    snapshots,
    included,
    includedCount: included.length,
    totalReports,
    examined: rows.length,
    cap,
    truncated,
    window: included.length
      ? { from: included[0].chronoDate, to: included[included.length - 1].chronoDate }
      : null,
  };
}

async function describeExcluded({ user, limit = 50 }) {
  const filter = ownerScopedFilter(user, {
    ...OWNER_ONLY,
    base: {
      $or: [
        { 'analysis.version': { $lte: 0 } },
        { 'analysis.version': { $exists: false } },
        { featureValidation: { $exists: false } },
        { featureValidation: null },
        { 'subject.owner': 'other' },
      ],
    },
  });

  const [count, rows] = await Promise.all([
    Report.countDocuments(filter),
    Report.find(filter)
      .select('user chronoDate status analysis.version subject.owner')
      .sort({ chronoDate: -1, _id: -1 })
      .limit(Math.max(0, limit))
      .lean(),
  ]);

  for (const row of rows) assertCanAccess(user, row, { ...OWNER_ONLY });

  const reports = rows.map((row) => ({
    reportId: String(row._id),
    chronoDate: row.chronoDate,
    status: row.status,
    reasonCode:
      row.subject?.owner === 'other'
        ? EXCLUSION_REASONS.SOMEONE_ELSE
        : (row.analysis && row.analysis.version) > 0
          ? EXCLUSION_REASONS.NO_VALIDATED_FEATURES
          : EXCLUSION_REASONS.NOT_ANALYSED,
  }));

  return { count, reports, listed: reports.length };
}


const PRINTED_PROJECTION = [
  'user',
  'extraction.extracted_parameters.test_name',
  'extraction.extracted_parameters.reference_low',
  'extraction.extracted_parameters.reference_high',
  'extraction.extracted_parameters.reference_range_raw',
  'extraction.extracted_parameters.flag',
].join(' ');

async function loadPrintedParameters({ user, reportIds }) {
  const ids = Array.isArray(reportIds) ? reportIds.filter(Boolean) : [];
  const byReport = new Map();
  if (!ids.length) return byReport;

  const rows = await Report.find(
    ownerScopedFilter(user, { ...OWNER_ONLY, base: { _id: { $in: ids } } })
  )
    .select(PRINTED_PROJECTION)
    .lean();

  for (const row of rows) {
    assertCanAccess(user, row, { ...OWNER_ONLY });
    const params =
      (row.extraction && Array.isArray(row.extraction.extracted_parameters)
        ? row.extraction.extracted_parameters
        : []) || [];
    const byName = new Map();
    for (const param of params) {
      if (typeof param.test_name === 'string' && param.test_name && !byName.has(param.test_name)) {
        byName.set(param.test_name, param);
      }
    }
    byReport.set(String(row._id), byName);
  }

  return byReport;
}

async function checkPairIdentity({ user, baselineId, comparisonId }) {
  const rows = await Report.find(
    ownerScopedFilter(user, { ...OWNER_ONLY, base: { _id: { $in: [baselineId, comparisonId] } } })
  )
    .select('user chronoDate printedIdentity')
    .lean();
  const byId = new Map();
  for (const row of rows) {
    assertCanAccess(user, row, { ...OWNER_ONLY });
    byId.set(String(row._id), { identity: row.printedIdentity || null, date: row.chronoDate });
  }
  return comparePair(byId.get(String(baselineId)), byId.get(String(comparisonId)));
}


async function resolveNamedPair({ user, baseline, comparison, snapshotIds }) {
  if (baseline === undefined && comparison === undefined) return null;

  if (baseline === undefined || comparison === undefined) {
    throw new ApiError(
      422,
      'VALIDATION_ERROR',
      'Name both baseline and comparison, or neither. One alone does not identify a pair.'
    );
  }

  const resolved = [];
  for (const id of [baseline, comparison]) {
    const owned = await Report.findOne(
      ownerScopedFilter(user, { ...OWNER_ONLY, base: { _id: id } })
    ).select('_id user');
    assertCanAccess(user, owned, { ...OWNER_ONLY });
    resolved.push(String(owned._id));
  }

  const missing = resolved.filter((id) => !snapshotIds.has(id));
  if (missing.length) {
    throw new ApiError(
      422,
      'REPORT_NOT_IN_HISTORY',
      'A report named as the comparison pair has no analysed feature set to compare, ' +
        'or falls outside the history window. Analyse it first, then try again.'
    );
  }

  return { baselineRef: resolved[0], comparisonRef: resolved[1] };
}

function summariseHistory(history, excluded) {
  const considered = history.totalReports;
  const included = history.includedCount;
  const excludedCount = excluded ? excluded.count : undefined;

  const droppedByCap =
    excludedCount === undefined
      ? undefined
      : Math.max(0, considered - included - excludedCount);

  return {
    considered,
    included,
    excludedCount,
    droppedByCap,
    excludedListed: excluded ? excluded.listed : undefined,
    from: history.window ? history.window.from : null,
    to: history.window ? history.window.to : null,
    cap: history.cap,
    truncated: history.truncated,
    reports: history.included,
    excluded: excluded ? excluded.reports : undefined,
  };
}

module.exports = {
  EXCLUSION_REASONS,
  INCLUSION_FILTER,
  HISTORY_PROJECTION,
  PRINTED_PROJECTION,
  assembleHistory,
  describeExcluded,
  loadPrintedParameters,
  checkPairIdentity,
  resolveNamedPair,
  summariseHistory,
};
