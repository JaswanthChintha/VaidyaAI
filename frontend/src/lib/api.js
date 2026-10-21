const ACCESS = { token: null };
const REFRESH_KEY = 'vaidyaai.refresh';

let refreshInFlight = null;

export function getRefreshToken() {
  try {
    return window.localStorage.getItem(REFRESH_KEY);
  } catch {
    return null;
  }
}

export function setSession({ accessToken, refreshToken }) {
  ACCESS.token = accessToken || null;
  try {
    if (refreshToken) window.localStorage.setItem(REFRESH_KEY, refreshToken);
  } catch {
  }
}

export function clearSession() {
  ACCESS.token = null;
  refreshInFlight = null;
  try {
    window.localStorage.removeItem(REFRESH_KEY);
  } catch {
  }
}

export function hasSession() {
  return Boolean(ACCESS.token || getRefreshToken());
}

export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message || 'The request failed.');
    this.name = 'ApiError';
    this.status = status;
    this.code = code || 'UNKNOWN';
    this.details = Array.isArray(details) ? details : [];
  }
}

function validationMessage(error) {
  if (error?.code !== 'VALIDATION_ERROR' || !Array.isArray(error.details)) return null;
  const reasons = [];
  for (const detail of error.details) {
    const text = typeof detail?.message === 'string' ? detail.message.trim() : '';
    if (text && !reasons.includes(text)) reasons.push(text);
  }
  if (!reasons.length) return null;
  return reasons.map((r) => (/[.!?]$/.test(r) ? r : `${r}.`)).join(' ');
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
      validationMessage(body?.error) || body?.error?.message,
      body?.error?.details
    );
  }
  return body?.data;
}

export function isSessionRejected(error) {
  return error instanceof ApiError && [400, 401, 403, 422].includes(error.status);
}

const REFRESH_RETRY_DELAYS_MS = [1000, 2000, 4000];
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function refreshSession() {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return false;

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

const VIEWABLE_TYPES = ['application/pdf', 'image/jpeg', 'image/png'];

async function openReportFile(id, mimeType) {
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
    if (tab && !tab.closed) tab.close();
    const link = document.createElement('a');
    link.href = url;
    link.download = `report-${id}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}


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
  changePassword: (currentPassword, newPassword) =>
    request('POST', '/auth/change-password', { body: { currentPassword, newPassword } }),
  deleteAccount: (password) => request('DELETE', '/auth/me', { body: { password } }),
  logout: () => {
    const refreshToken = getRefreshToken();
    return request('POST', '/auth/logout', { body: { refreshToken } });
  },

  getProfile: () => request('GET', '/profile/me'),
  saveProfile: (payload) => request('PUT', '/profile/me', { body: payload }),

  chat: (question, reportId) =>
    request('POST', '/chat', { body: reportId ? { question, reportId } : { question } }),

  listReports: () => request('GET', '/reports'),
  uploadReport: (formData) => request('POST', '/reports', { formData }),
  analyzeReport: (id) => request('POST', `/reports/${id}/analyze`),
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
  describeFindings: (id, findings) =>
    request('POST', `/reports/${id}/finding-context`, { body: { findings } }),
  rewriteSummary: (id, sentences, names) =>
    request('POST', `/reports/${id}/summary-prose`, {
      body: { sentences, names },
    }),
  getPopulationContext: (id) => request('GET', `/reports/${id}/population-context`),

  getTrends: () => request('GET', '/timeline/trends'),
  getComparison: (pair) => request('GET', `/timeline/comparison${pairQuery(pair)}`),
  getProgress: (pair) => request('GET', `/timeline/progress${pairQuery(pair)}`),
};

export { refreshSession };
