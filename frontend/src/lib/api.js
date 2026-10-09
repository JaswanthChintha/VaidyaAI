/**
 * The one place this app talks to the backend.
 *
 * EVERY call goes through the Node backend. The frontend never contacts
 * `ai-service` directly: authentication, owner scoping and the 404-before-403
 * rule all live in the backend, and a browser reaching past it would bypass
 * all three.
 *
 * ==========================================================================
 * WHERE THE TOKENS LIVE, AND WHY
 * ==========================================================================
 *
 * The access token is held in memory only. The refresh token is held in
 * `localStorage`, which is a deliberate and stated trade-off rather than an
 * oversight:
 *
 *   - In memory alone, a page reload logs the patient out. For a tool people
 *     open to read a lab result, that is bad enough to push them toward
 *     staying signed in on a shared device, which is worse.
 *   - `localStorage` is readable by any script that achieves XSS on this
 *     origin. The mitigation that actually matters is the backend's: refresh
 *     tokens ROTATE on every use, only a SHA-256 digest is stored server-side,
 *     replaying a rotated token returns 401, and a password change purges
 *     every session (MEMORY.md section 6, defect 4).
 *   - The correct end state is an httpOnly, SameSite cookie, which needs a
 *     backend change. RECORDED AS A KNOWN LIMITATION rather than left as an
 *     unexamined default.
 *
 * A 401 triggers exactly ONE refresh attempt, and concurrent 401s share it.
 * Without that, a dashboard firing five requests on load would burn five
 * refresh tokens against a rotating store and log the patient out.
 */

const ACCESS = { token: null };
const REFRESH_KEY = 'vaidyaai.refresh';

let refreshInFlight = null;

export function getRefreshToken() {
  try {
    return window.localStorage.getItem(REFRESH_KEY);
  } catch {
    // Private mode, disabled storage, or a sandboxed iframe. Not fatal: the
    // session simply does not survive a reload.
    return null;
  }
}

export function setSession({ accessToken, refreshToken }) {
  ACCESS.token = accessToken || null;
  try {
    if (refreshToken) window.localStorage.setItem(REFRESH_KEY, refreshToken);
  } catch {
    /* see getRefreshToken */
  }
}

export function clearSession() {
  ACCESS.token = null;
  refreshInFlight = null;
  try {
    window.localStorage.removeItem(REFRESH_KEY);
  } catch {
    /* see getRefreshToken */
  }
}

export function hasSession() {
  return Boolean(ACCESS.token || getRefreshToken());
}

/**
 * An error carrying the backend's own code and message.
 *
 * The backend's envelope is `{success: false, error: {code, message}}` and its
 * messages are written to be shown -- they are fixed strings that never echo
 * submitted input and never leak whether another patient's report exists.
 * So the message is surfaced as-is rather than replaced with a generic one,
 * which would throw away the only useful thing in the response.
 */
export class ApiError extends Error {
  constructor(status, code, message) {
    super(message || 'The request failed.');
    this.name = 'ApiError';
    this.status = status;
    this.code = code || 'UNKNOWN';
  }
}

async function parse(response) {
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok || body?.success === false) {
    throw new ApiError(
      response.status,
      body?.error?.code,
      body?.error?.message
    );
  }
  return body?.data;
}

/**
 * True only when the SERVER rejected the session -- the one case where the
 * stored refresh token is worthless and must go. 422 is the backend's
 * validator refusing a malformed token (`middleware/validate.js`); without it
 * a corrupted token would be kept and retried on every load, forever.
 */
export function isSessionRejected(error) {
  return error instanceof ApiError && [400, 401, 403, 422].includes(error.status);
}

const REFRESH_RETRY_DELAYS_MS = [1000, 2000, 4000];
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/*
 * ONLY A REJECTION SIGNS THE PATIENT OUT (2026-10-02). Every failure used to
 * clear the session, so a backend restart signed the owner out: the page
 * reloaded while the server was still starting, the dev proxy answered 500
 * for a request the backend never received, and the refresh token was
 * deleted. A 5xx, a 429 or no connection at all says nothing about the
 * token, so it is retried a few times (long enough for a restart) and, if
 * the server is still unreachable, KEPT -- the next reload can still use it.
 */
async function refreshSession() {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  // Shared across concurrent callers: one rotation, not five.
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        for (let attempt = 0; ; attempt += 1) {
          try {
            const response = await fetch('/api/v1/auth/refresh', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ refreshToken }),
            });
            const data = await parse(response);
            setSession(data);
            return true;
          } catch (error) {
            if (isSessionRejected(error)) {
              clearSession();
              return false;
            }
            if (attempt >= REFRESH_RETRY_DELAYS_MS.length) return false;
            await sleep(REFRESH_RETRY_DELAYS_MS[attempt]);
          }
        }
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

/**
 * `request('GET', '/reports')`. Paths are relative to `/api/v1`.
 *
 * `retry` is internal: it stops one 401 from becoming an infinite refresh
 * loop when the refresh itself yields a token the server will not accept.
 */
export async function request(method, path, { body, formData, retry = true } = {}) {
  const headers = {};
  if (ACCESS.token) headers.Authorization = `Bearer ${ACCESS.token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  const response = await fetch(`/api/v1${path}`, {
    method,
    headers,
    body: formData || (body !== undefined ? JSON.stringify(body) : undefined),
  });

  if (response.status === 401 && retry && getRefreshToken()) {
    const refreshed = await refreshSession();
    if (refreshed) {
      return request(method, path, { body, formData, retry: false });
    }
  }

  return parse(response);
}

/**
 * The only content types a stored report may be VIEWED as.
 *
 * The download route deliberately sends `Content-Disposition: attachment` so a
 * stored file is never rendered inside the app's origin -- if it were, an
 * uploaded HTML or SVG file could run script here and read the access token.
 * Opening a blob in a tab would hand that protection straight back, because a
 * `blob:` URL inherits the origin that created it.
 *
 * So the blob is rebuilt with a type from THIS list and nothing else. A PDF
 * renders in the browser's sandboxed viewer and an image renders as an image;
 * neither can execute. Anything else is downloaded instead of opened, which is
 * exactly the behaviour the server asked for.
 */
const VIEWABLE_TYPES = ['application/pdf', 'image/jpeg', 'image/png'];

/**
 * Fetch a stored report and show it, without ever losing the auth header.
 *
 * A plain `<a href>` cannot be used: the route is owner-scoped and needs the
 * bearer token, which a link does not send.
 */
async function openReportFile(id, mimeType) {
  // OPEN THE TAB FIRST, SYNCHRONOUSLY. This is the whole reason the function
  // is shaped this way.
  //
  // `window.open` is only permitted while the browser still considers itself
  // inside the user's click. The moment this function awaits the fetch, that
  // gesture context is gone and every popup blocker silently refuses -- the
  // call returns null, no tab appears, and nothing is thrown, so the button
  // looks simply dead. The first version of this did exactly that.
  //
  // So a blank tab is claimed while the click is still trusted, and its
  // location is set once the file arrives.
  // NOT `noopener` in the feature string: specifying it makes `window.open`
  // return NULL by definition, and the reference is the thing this whole
  // arrangement exists to keep. `opener` is severed on the handle instead,
  // which achieves the same isolation without discarding the tab.
  const tab = window.open('', '_blank');
  if (tab) tab.opener = null;

  const fail = (message) => {
    if (tab && !tab.closed) tab.close();
    throw new ApiError(0, 'REPORT_FILE_UNAVAILABLE', message);
  };

  const headers = {};
  if (ACCESS.token) headers.Authorization = `Bearer ${ACCESS.token}`;

  let response;
  try {
    response = await fetch(`/api/v1/reports/${id}/download`, { headers });
    if (response.status === 401 && getRefreshToken() && (await refreshSession())) {
      response = await fetch(`/api/v1/reports/${id}/download`, {
        headers: ACCESS.token ? { Authorization: `Bearer ${ACCESS.token}` } : {},
      });
    }
  } catch {
    fail('The report file could not be fetched. Check your connection.');
  }

  if (!response.ok) {
    // The body is a file, not an envelope, so there is no error code to read.
    fail(
      response.status === 404
        ? 'This report no longer has a stored file.'
        : 'This report file could not be opened.'
    );
  }

  const raw = await response.blob();
  const declared = (mimeType || raw.type || '').toLowerCase();
  const safe = VIEWABLE_TYPES.includes(declared);
  const url = URL.createObjectURL(safe ? new Blob([raw], { type: declared }) : raw);

  if (safe && tab && !tab.closed) {
    tab.location.href = url;
  } else {
    // Either the type is not one we will render, or the popup was blocked
    // anyway. Saving the file is the honest fallback -- it is also exactly
    // what the server's `Content-Disposition: attachment` asked for.
    if (tab && !tab.closed) tab.close();
    const link = document.createElement('a');
    link.href = url;
    link.download = `report-${id}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  // The tab has already read the URL; revoking frees the in-memory copy.
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}


/**
 * `?baseline=…&comparison=…`, or nothing at all.
 *
 * BOTH OR NEITHER. The backend refuses exactly one of the pair rather than
 * guessing the other, so sending a half-pair would turn a user's half-finished
 * choice into an error instead of into the default comparison.
 */
function pairQuery(pair) {
  const baseline = pair && pair.baseline;
  const comparison = pair && pair.comparison;
  if (!baseline || !comparison) return '';
  return `?baseline=${encodeURIComponent(baseline)}&comparison=${encodeURIComponent(comparison)}`;
}

export const api = {
  register: (payload) => request('POST', '/auth/register', { body: payload }),
  login: (payload) => request('POST', '/auth/login', { body: payload }),
  me: () => request('GET', '/auth/me'),
  // Both re-check the current password server-side. A wrong one is a 400,
  // never a 401, so it cannot trigger the refresh-and-resend path above.
  changePassword: (currentPassword, newPassword) =>
    request('POST', '/auth/change-password', { body: { currentPassword, newPassword } }),
  deleteAccount: (password) => request('DELETE', '/auth/me', { body: { password } }),
  logout: () => {
    const refreshToken = getRefreshToken();
    return request('POST', '/auth/logout', { body: { refreshToken } });
  },

  getProfile: () => request('GET', '/profile/me'),
  // PUT, not POST/PATCH: it upserts, and its REPLACE semantics are what let
  // a patient change a tri-state answer back to 'not sure'. An omitted key is
  // cleared; PATCH would leave the old answer in place, and an explicit null
  // is rejected outright as a type error.
  saveProfile: (payload) => request('PUT', '/profile/me', { body: payload }),

  // The chatbot (2026-10-09). `reportId` only from a report's own pages; the
  // backend checks it is the caller's before reading it.
  chat: (question, reportId) =>
    request('POST', '/chat', { body: reportId ? { question, reportId } : { question } }),

  listReports: () => request('GET', '/reports'),
  uploadReport: (formData) => request('POST', '/reports', { formData }),
  analyzeReport: (id) => request('POST', `/reports/${id}/analyze`),
  // Whose report this is (2026-10-03). `subject` is { owner, age?, sex? };
  // age and sex only for someone else's.
  setReportSubject: (id, subject) =>
    request('PATCH', `/reports/${id}/subject`, {
      body: {
        subjectOwner: subject.owner,
        ...(subject.owner === 'other' && subject.age !== '' && subject.age != null
          ? { subjectAge: Number(subject.age) }
          : {}),
        ...(subject.owner === 'other' && subject.sex ? { subjectSex: subject.sex } : {}),
      },
    }),
  deleteReport: (id) => request('DELETE', `/reports/${id}`),
  openReportFile: (id, mimeType) => openReportFile(id, mimeType),
  getDashboard: (id) => request('GET', `/reports/${id}/dashboard`),
  getDoctorSummary: (id) => request('GET', `/reports/${id}/doctor-summary`),
  /**
   * Module 33 -- rewrite the summary sentences THIS PAGE composed.
   *
   * POST, and the sentences go out in the body, because the page composes
   * them from the cards it is rendering. A server-side recomposition would be
   * a second implementation of those rules that could disagree with the
   * first, and the screen would then argue with its own summary.
   */
  /**
   * Module 34 -- general context for tests already marked out of range.
   *
   * A NAME AND A DIRECTION, and there is nowhere to put anything else. The
   * backend rebuilds the body and the ai-service forbids extra fields, so a
   * value cannot reach the model even by accident -- which is what keeps the
   * answer about the TEST rather than about the reader.
   */
  describeFindings: (id, findings) =>
    request('POST', `/reports/${id}/finding-context`, { body: { findings } }),
  rewriteSummary: (id, sentences, names) =>
    request('POST', `/reports/${id}/summary-prose`, {
      body: { sentences, names },
    }),
  getPopulationContext: (id) => request('GET', `/reports/${id}/population-context`),

  getTrends: () => request('GET', '/timeline/trends'),
  /**
   * Modules 29 and 30, for a NAMED pair of reports or the service's own choice.
   *
   * `pair` is `{ baseline, comparison }` or nothing. Both endpoints have taken
   * these query parameters since they were written; sending neither is what
   * produces `selection: "first_vs_latest"`, and sending one without the other
   * is refused by the backend rather than half-applied.
   *
   * THE TWO ARE ALWAYS ASKED THE SAME QUESTION. A comparison table describing
   * one pair beside a progress score computed from another is two answers to
   * different questions presented as one screen.
   */
  getComparison: (pair) => request('GET', `/timeline/comparison${pairQuery(pair)}`),
  getProgress: (pair) => request('GET', `/timeline/progress${pairQuery(pair)}`),
};

export { refreshSession };
