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

/**
 * Module 3 - Medical Report Upload and Management.
 *
 * OWNERSHIP MODEL. Identical in shape to Module 2, but reports differ in one
 * important way: they have client-addressable ids, so there IS something to
 * tamper with in the URL. Three layers:
 *
 *  1. Every query is built with `ownerScopedFilter(req.user, { ...OWNER_ONLY })`,
 *     so `GET /reports/<someone else's id>` cannot match a document at all.
 *     A non-owner therefore gets the same 404 as a caller using a random id -
 *     the record's existence is never disclosed, which is the strongest form of
 *     `assertCanAccess`'s 404-before-403 rule.
 *  2. `requireOwnership` re-checks the loaded document with `assertCanAccess`
 *     before any handler sees it (deliberately redundant: if a future refactor
 *     widens the filter, this still denies).
 *  3. `OWNER_ONLY` is passed explicitly at every call site. Medical data has no
 *     staff exception - an administrator gets exactly the same 404 as any other
 *     non-owner. This is stated at the call site even though it now matches the
 *     helper's default, so the intent survives a change of default.
 *
 * LOGGING. Nothing here logs file contents, buffers, or report text. Only
 * identifiers, sizes and digests are ever written to a log.
 */

/** Filter matching only the caller's own reports. Throws if unauthenticated. */
const ownFilter = (req, base = {}) =>
  ownerScopedFilter(req.user, { ...OWNER_ONLY, base });

/**
 * Middleware: load `:id` as one of the caller's OWN reports and attach it to
 * `req.report`. A report belonging to somebody else simply does not match, so
 * `assertCanAccess` raises its 404 branch.
 */
const loadOwnReport = requireOwnership(
  (req) => Report.findOne(ownFilter(req, { _id: req.params.id })),
  { ...OWNER_ONLY, attachAs: 'report' }
);

// ---------------------------------------------------------------- upload ----

/**
 * POST /reports
 * multipart/form-data with a single `file` part, plus an optional `reportDate`.
 *
 * ORPHAN HANDLING. A file and a database row must either both exist or neither
 * do. Two failure directions, handled explicitly:
 *
 *   file write fails  -> nothing is inserted; the request errors out and the
 *                        adapter has already removed its own temp file.
 *   DB insert fails   -> the just-written file is removed in the catch before
 *                        the error is re-thrown, so no unreferenced blob is
 *                        left on disk.
 *
 * The cleanup itself is best-effort and never masks the original error: if
 * removal also fails, the original failure is what the caller sees.
 */
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
  // Defence in depth: multer's limit already aborts oversized streams, but the
  // cap is re-asserted here so a misconfigured limit cannot let a large buffer
  // through to the filesystem.
  if (file.buffer.length > config.upload.maxBytes) {
    throw new ApiError(
      413,
      'PAYLOAD_TOO_LARGE',
      `The uploaded file exceeds the ${config.upload.maxBytes}-byte limit`
    );
  }

  // The ONLY trustworthy statement about the file's type is its own bytes.
  // `file.mimetype` and the extension inside `file.originalname` are both
  // attacker-controlled and are used for nothing.
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
      // Validated above as an ISO-8601 date that is neither absurdly old nor in
      // the future. Re-coerced here rather than relying on the sanitizer.
      reportDate: req.body.reportDate ? new Date(req.body.reportDate) : undefined,
      // Validated above; age and sex only ever arrive with `other`.
      subject: subjectFromBody(req.body),
    });
  } catch (err) {
    // Roll the file back so a failed insert cannot leave an orphan blob.
    await storage.remove(saved.key).catch(() => {});
    throw err;
  }

  return sendSuccess(res, 201, { report: report.toPublicJSON() });
});

// ------------------------------------------------------------------ list ----

/**
 * GET /reports
 * The caller's own reports, chronologically ordered and paginated.
 *
 * Default order is newest-first on `chronoDate` (= the date on the report when
 * known, else the upload date), which is the ordering Modules 28-30 need. `_id`
 * is always appended as a tiebreaker so paging is stable when several reports
 * share a date - without it, two pages can both contain, or both skip, the same
 * document.
 */
const listReports = asyncHandler(async (req, res) => {
  // The validators have already proven these are in range and in the allowed
  // set. They are re-read defensively rather than trusted to have been
  // sanitized in place: Express recomputes `req.query` from the raw query
  // string on access, so an express-validator sanitizer's write-back is not
  // something to depend on for a value that ends up in a Mongo query or in
  // pagination arithmetic.
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

// -------------------------------------------------------------- retrieve ----

/** GET /reports/:id - metadata for one of the caller's own reports. */
const getReport = asyncHandler(async (req, res) => {
  assertCanAccess(req.user, req.report, { ...OWNER_ONLY });
  return sendSuccess(res, 200, { report: req.report.toPublicJSON() });
});

/**
 * Whose report, from a validated body (2026-10-03). `self` carries no age or
 * sex -- those belong to the profile -- and the validator refuses them there.
 */
function subjectFromBody(body) {
  if (body.subjectOwner !== 'other') return { owner: 'self', updatedAt: new Date() };
  return {
    owner: 'other',
    age: Number.isFinite(body.subjectAge) ? body.subjectAge : undefined,
    sex: typeof body.subjectSex === 'string' && body.subjectSex ? body.subjectSex : undefined,
    updatedAt: new Date(),
  };
}

/**
 * PATCH /reports/:id/subject - change whose report this is (2026-10-03).
 *
 * Does NOT re-run the analysis: that spends model quota and is the owner's
 * call. The stored analysis keeps describing the old answer until then, and
 * `subjectChangedSinceAnalysis` on the report says so.
 */
const setReportSubject = asyncHandler(async (req, res) => {
  assertCanAccess(req.user, req.report, { ...OWNER_ONLY });
  req.report.subject = subjectFromBody(req.body);
  await req.report.save();
  return sendSuccess(res, 200, { report: req.report.toPublicJSON() });
});

// -------------------------------------------------------------- download ----

/**
 * GET /reports/:id/download - stream the stored file back to its owner.
 *
 * Headers are the security control here. An uploaded file is untrusted content
 * that an authenticated user's browser is about to receive:
 *   Content-Disposition: attachment  - never rendered in the app's origin, so a
 *                                      crafted file cannot become stored XSS.
 *   X-Content-Type-Options: nosniff  - the browser may not second-guess the
 *                                      declared type and execute it as HTML.
 *   Cache-Control: private, no-store - medical data must not sit in shared or
 *                                      on-disk caches.
 * The declared Content-Type is the type DETECTED at upload, not anything the
 * uploader claimed.
 */
const downloadReport = asyncHandler(async (req, res) => {
  assertCanAccess(req.user, req.report, { ...OWNER_ONLY });

  const storage = getStorage(req.report.storageDriver);
  const stats = await storage.stat(req.report.storageKey);
  if (!stats) {
    throw ApiError.notFound('The stored file for this report is no longer available');
  }

  const stream = await storage.createReadStream(req.report.storageKey);

  // DEFECT D3. The stored `mimeType` was written from the file's own magic
  // bytes and is constrained by the model enum, so on the normal write path it
  // is already trustworthy. It is nevertheless re-checked against the
  // allow-list HERE, at the moment it becomes a response header, because this
  // is the one value in the download path that a raw-driver write could turn
  // into `text/html` - and the header is what a browser acts on. `attachment` +
  // `nosniff` + `default-src 'none'; sandbox` already contain the consequences;
  // this closes the gap itself rather than relying on three mitigations.
  // Anything unrecognised degrades to a type no browser will ever render.
  const declaredType = ALLOWED_MIME_TYPES.includes(req.report.mimeType)
    ? req.report.mimeType
    : 'application/octet-stream';

  res.setHeader('Content-Type', declaredType);
  res.setHeader('Content-Length', String(stats.size));
  res.setHeader('Content-Disposition', contentDispositionAttachment(req.report.originalName));
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Cache-Control', 'private, no-store, max-age=0');
  res.setHeader('Content-Security-Policy', "default-src 'none'; sandbox");

  // A read failure after the first byte is on the wire cannot become a JSON
  // error response - the status line is already sent - so the connection is
  // destroyed instead of trickling a truncated file that looks complete.
  stream.on('error', () => {
    if (!res.headersSent) {
      res.status(500);
    }
    res.destroy();
  });
  res.on('close', () => stream.destroy());

  return stream.pipe(res);
});

// ---------------------------------------------------------------- delete ----

/**
 * DELETE /reports/:id - remove both the record and the file.
 *
 * ORDER MATTERS. The database row goes first, then the file. If the sequence is
 * interrupted between the two, the residue is an unreferenced file (invisible
 * to users, reclaimable by a sweep) rather than a record pointing at a file
 * that no longer exists (visible to users as a broken download). A file that is
 * already missing is not an error - `remove` is idempotent - because otherwise
 * a report whose file was lost could never be deleted.
 */
const deleteReport = asyncHandler(async (req, res) => {
  assertCanAccess(req.user, req.report, { ...OWNER_ONLY });

  const { storageKey, storageDriver } = req.report;

  // DEFECT D2. The storage adapter is resolved BEFORE the row is removed.
  //
  // Previously `getStorage(storageDriver)` ran after the delete, and a row
  // naming an unregistered driver made it throw - so the caller got a 500 while
  // the row had genuinely been deleted. The reported outcome contradicted
  // reality: a retry returned 404, and the file was orphaned with no record
  // that it ever existed. Resolving first means the two possible outcomes are
  // both honest:
  //
  //   driver resolves      -> row deleted, file removal attempted, reported.
  //   driver unresolvable  -> the row is STILL deleted (it is the caller's data
  //                           and they asked for it gone; refusing would leave
  //                           them permanently unable to delete it), and the
  //                           response says so - `fileRemoved: false` with
  //                           `fileOrphaned: true`, a 200, not a 500.
  //
  // An orphaned file is the same residue the row-first ordering already accepts
  // on an interrupted delete: invisible to users and reclaimable by a sweep.
  let storage = null;
  let driverResolved = true;
  try {
    storage = getStorage(storageDriver);
  } catch (err) {
    driverResolved = false;
  }

  const result = await Report.deleteOne(ownFilter(req, { _id: req.report._id }));
  if (result.deletedCount === 0) {
    // Lost a race with a concurrent delete; the file belongs to whichever call
    // actually removed the row.
    throw ApiError.notFound('Report not found');
  }

  const fileRemoved = driverResolved ? await storage.remove(storageKey) : false;

  return sendSuccess(res, 200, {
    deleted: true,
    id: req.report._id.toString(),
    fileRemoved,
    // Only ever true for a row whose driver this build cannot resolve.
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
