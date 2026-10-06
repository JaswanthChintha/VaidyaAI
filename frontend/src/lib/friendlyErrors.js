/**
 * Plain words for analysis failures (owner, 2026-10-06).
 *
 * The backend's messages are written for API callers -- "ANALYSIS_PARTIAL:
 * Some analysis stages did not complete; see analysis.stages", "See GET
 * /reports/:id/analysis ..." -- and they reached patients word for word. They
 * stay as they are (they are the API's contract and its tests); this file is
 * only what a PERSON is shown. The machine code is kept, small, so a report of
 * the problem can still say exactly which one it was.
 */

const RETRY_SOON =
  'The analysis service did not answer properly. It may have been starting up after a quiet spell. Press Analyse again in a minute.';

const BY_CODE = {
  ANALYSIS_PARTIAL:
    'The analysis stopped partway, so some results are missing. Press Re-analyse to try again.',
  ANALYSIS_STAGE_FAILED:
    'Part of the analysis did not finish. Press Re-analyse to try again.',
  ANALYSIS_SUPERSEDED: 'A newer analysis of this report replaced this one.',
  AI_SERVICE_UNAVAILABLE: RETRY_SOON,
  AI_SERVICE_TIMEOUT: RETRY_SOON,
  AI_SERVICE_BUSY: RETRY_SOON,
  AI_SERVICE_ERROR: RETRY_SOON,
  AI_SERVICE_MALFORMED_RESPONSE: RETRY_SOON,
  AI_SERVICE_NOT_CONFIGURED:
    'Analysis is not switched on for this site yet. Please contact whoever runs it.',
  AI_SERVICE_UNAUTHORIZED:
    'The analysis service refused this site. Please contact whoever runs it.',
  AI_SERVICE_REJECTED_REQUEST:
    'The analysis service refused the request. Please contact whoever runs it.',
  AI_SERVICE_REJECTED_INPUT:
    'This file could not be read as a lab report. Check that it is a clear PDF or photo of the report.',
  NO_LAB_RESULTS:
    'No test results were found in this file, so nothing was assessed. Please check it is a lab report (a clear PDF or photo of it).',
  AI_SERVICE_EMPTY_RESULT:
    'No test results could be read from this file. Check that it is a clear PDF or photo of the report.',
  UNSUPPORTED_MEDIA_TYPE: 'This file type cannot be analysed. Upload a PDF, JPG or PNG.',
  PAYLOAD_TOO_LARGE: 'This file is too large to analyse.',
  NOT_FOUND: 'The stored file for this report is no longer available. Please upload it again.',
  STORAGE_READ_FAILED: 'The stored file for this report could not be read. Please upload it again.',
  STORAGE_UNAVAILABLE: 'The stored file for this report could not be reached. Please try again later.',
};

const FALLBACK = 'Something went wrong during the analysis. Press Analyse again to retry.';

/**
 * A report row's `statusMessage` ("CODE: api wording") -> what to show.
 * @returns {{ text: string, code: string|null } | null}
 */
export function friendlyStatus(statusMessage) {
  if (!statusMessage || typeof statusMessage !== 'string') return null;
  const match = /^([A-Z][A-Z0-9_]+):/.exec(statusMessage);
  const code = match ? match[1] : null;
  return { text: (code && BY_CODE[code]) || FALLBACK, code };
}

/**
 * A page-level error from the backend -> what to show. Messages that tell an
 * API caller which endpoint to call next are rewritten; anything else passes
 * through with any "Run POST ..." / "See GET ..." sentence removed.
 */
export function friendlyPageError(message) {
  if (!message || typeof message !== 'string') return message;
  if (/has not been analysed yet/i.test(message)) {
    return 'This report has not been analysed yet. Go back to your reports and press Analyse.';
  }
  if (/No clinical report was produced/i.test(message)) {
    return 'The analysis of this report stopped partway, so there are no results to show yet. Go back to your reports and press Re-analyse.';
  }
  return message.replace(/\s*(Run|See) (GET|POST|PUT|PATCH|DELETE) \/\S+[^.]*\./g, '').trim();
}
