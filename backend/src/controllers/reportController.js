'use strict';

const Report = require('../models/Report');
const { SORT_FIELDS, REPORT_STATUS_VALUES } = require('../models/Report');
const ApiError = require('../utils/ApiError');
const asyncHandler = require('../utils/asyncHandler');
const config = require('../config/env');
const { sendSuccess } = require('../utils/apiResponse');
const { getStorage } = require('../storage');
const {
  ownerScopedFilter,
  assertCanAccess,
  requireOwnership,
  OWNER_ONLY,
} = require('../utils/ownership');
const {
  detectFileType,
  sanitizeFilename,
  checksum,
  contentDispositionAttachment,
  ALLOWED_EXTENSIONS,
  ALLOWED_MIME_TYPES,
} = require('../utils/fileSecurity');
const { PAGINATION } = require('../middleware/reportValidators');


const ownFilter = (req, base = {}) =>
  ownerScopedFilter(req.user, { ...OWNER_ONLY, base });

const loadOwnReport = requireOwnership(
  (req) => Report.findOne(ownFilter(req, { _id: req.params.id })),
  { ...OWNER_ONLY, attachAs: 'report' }
);


const uploadReport = asyncHandler(async (req, res) => {
  const file = req.file;
  if (!file || !file.buffer) {
    throw ApiError.badRequest(
      'No file was uploaded. Send multipart/form-data with a `file` part.'
    );
  }
  if (file.buffer.length === 0) {
    throw ApiError.badRequest('The uploaded file is empty');
  }
  if (file.buffer.length > config.upload.maxBytes) {
    throw new ApiError(
      413,
      'PAYLOAD_TOO_LARGE',
      `The uploaded file exceeds the ${config.upload.maxBytes}-byte limit`
    );
  }

  const detected = detectFileType(file.buffer);
  if (!detected) {
    throw new ApiError(
      415,
      'UNSUPPORTED_MEDIA_TYPE',
      `Unsupported file type. Allowed report formats: ${ALLOWED_EXTENSIONS.join(', ')}`
    );
  }

  const storage = getStorage();
  const originalName = sanitizeFilename(file.originalname);
  const digest = checksum(file.buffer);

  const saved = await storage.save({
    userId: req.user._id.toString(),
    buffer: file.buffer,
    extension: detected.extension,
  });

  let report;
  try {
    report = await Report.create({
      user: req.user._id,
      originalName,
      storageKey: saved.key,
      storageDriver: storage.name,
      mimeType: detected.mimeType,
      sizeBytes: saved.size,
      checksumSha256: digest,
      uploadedAt: new Date(),
      reportDate: req.body.reportDate ? new Date(req.body.reportDate) : undefined,
      subject: subjectFromBody(req.body),
    });
  } catch (err) {
    await storage.remove(saved.key).catch(() => {});
    throw err;
  }

  return sendSuccess(res, 201, { report: report.toPublicJSON() });
});


const listReports = asyncHandler(async (req, res) => {
  const page = Number.parseInt(req.query.page, 10) || 1;
  const limit = Number.parseInt(req.query.limit, 10) || PAGINATION.defaultLimit;

  const requestedSort = String(req.query.sort || '').trim();
  const sortField = SORT_FIELDS.includes(requestedSort) ? requestedSort : 'chronoDate';
  const direction = String(req.query.order || '').trim().toLowerCase() === 'asc' ? 1 : -1;

  const base = {};
  const requestedStatus = String(req.query.status || '').trim().toLowerCase();
  if (REPORT_STATUS_VALUES.includes(requestedStatus)) base.status = requestedStatus;

  const filter = ownFilter(req, base);

  const [total, reports] = await Promise.all([
    Report.countDocuments(filter),
    Report.find(filter)
      .sort({ [sortField]: direction, _id: direction })
      .skip((page - 1) * limit)
      .limit(limit),
  ]);

  return sendSuccess(res, 200, {
    reports: reports.map((report) => report.toPublicJSON()),
    pagination: {
      page,
      limit,
      total,
      totalPages: Math.ceil(total / limit) || 0,
      hasNextPage: page * limit < total,
      hasPrevPage: page > 1,
      sort: sortField,
      order: direction === 1 ? 'asc' : 'desc',
    },
  });
});


const getReport = asyncHandler(async (req, res) => {
  assertCanAccess(req.user, req.report, { ...OWNER_ONLY });
  return sendSuccess(res, 200, { report: req.report.toPublicJSON() });
});

function subjectFromBody(body) {
  if (body.subjectOwner !== 'other') return { owner: 'self', updatedAt: new Date() };
  return {
    owner: 'other',
    age: Number.isFinite(body.subjectAge) ? body.subjectAge : undefined,
    sex: typeof body.subjectSex === 'string' && body.subjectSex ? body.subjectSex : undefined,
    updatedAt: new Date(),
  };
}

const setReportSubject = asyncHandler(async (req, res) => {
  assertCanAccess(req.user, req.report, { ...OWNER_ONLY });
  req.report.subject = subjectFromBody(req.body);
  await req.report.save();
  return sendSuccess(res, 200, { report: req.report.toPublicJSON() });
});


const downloadReport = asyncHandler(async (req, res) => {
  assertCanAccess(req.user, req.report, { ...OWNER_ONLY });

  const storage = getStorage(req.report.storageDriver);
  const stats = await storage.stat(req.report.storageKey);
  if (!stats) {
    throw ApiError.notFound('The stored file for this report is no longer available');
  }

  const stream = await storage.createReadStream(req.report.storageKey);

  const declaredType = ALLOWED_MIME_TYPES.includes(req.report.mimeType)
    ? req.report.mimeType
    : 'application/octet-stream';

  res.setHeader('Content-Type', declaredType);
  res.setHeader('Content-Length', String(stats.size));
  res.setHeader('Content-Disposition', contentDispositionAttachment(req.report.originalName));
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Cache-Control', 'private, no-store, max-age=0');
  res.setHeader('Content-Security-Policy', "default-src 'none'; sandbox");

  stream.on('error', () => {
    if (!res.headersSent) {
      res.status(500);
    }
    res.destroy();
  });
  res.on('close', () => stream.destroy());

  return stream.pipe(res);
});


const deleteReport = asyncHandler(async (req, res) => {
  assertCanAccess(req.user, req.report, { ...OWNER_ONLY });

  const { storageKey, storageDriver } = req.report;

  let storage = null;
  let driverResolved = true;
  try {
    storage = getStorage(storageDriver);
  } catch (err) {
    driverResolved = false;
  }

  const result = await Report.deleteOne(ownFilter(req, { _id: req.report._id }));
  if (result.deletedCount === 0) {
    throw ApiError.notFound('Report not found');
  }

  const fileRemoved = driverResolved ? await storage.remove(storageKey) : false;

  return sendSuccess(res, 200, {
    deleted: true,
    id: req.report._id.toString(),
    fileRemoved,
    fileOrphaned: !driverResolved,
  });
});

module.exports = {
  loadOwnReport,
  uploadReport,
  listReports,
  getReport,
  setReportSubject,
  downloadReport,
  deleteReport,
};
