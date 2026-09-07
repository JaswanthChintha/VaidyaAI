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

async function refreshSession() {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

  // Shared across concurrent callers: one rotation, not five.
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const response = await fetch('/api/v1/auth/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refreshToken }),
        });
        const data = await parse(response);
        setSession(data);
        return true;
      } catch {
        clearSession();
        return false;
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


export const api = {
  register: (payload) => request('POST', '/auth/register', { body: payload }),
  login: (payload) => request('POST', '/auth/login', { body: payload }),
  me: () => request('GET', '/auth/me'),
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

  listReports: () => request('GET', '/reports'),
  uploadReport: (formData) => request('POST', '/reports', { formData }),
  analyzeReport: (id) => request('POST', `/reports/${id}/analyze`),
  deleteReport: (id) => request('DELETE', `/reports/${id}`),
  openReportFile: (id, mimeType) => openReportFile(id, mimeType),
  getDashboard: (id) => request('GET', `/reports/${id}/dashboard`),
  getDoctorSummary: (id) => request('GET', `/reports/${id}/doctor-summary`),
  getPopulationContext: (id) => request('GET', `/reports/${id}/population-context`),

  getTrends: () => request('GET', '/timeline/trends'),
  getComparison: () => request('GET', '/timeline/comparison'),
  getProgress: () => request('GET', '/timeline/progress'),
};

export { refreshSession };
