# VaidyaAI Backend — Modules 1–3 + the §16 pipeline orchestration layer (Modules 4, 5, 6, 8, 9/10)

This is the Node.js / Express / MongoDB backend for **VaidyaAI**. It currently
implements **Module 1** (secure registration, login, session management and
access control for protected APIs), **Module 2** (patient profile
management — the structured health profile that later modules use as patient
context) and **Module 3** (medical report upload and management — chronological
storage of lab reports, with the files themselves held behind a storage-adapter
interface). It also contains the **orchestration layer** that makes the spec's
§16 data flow real end to end: `POST /reports/:id/analyze` streams a stored
report to the Python `ai-service/` for OCR extraction, joins the caller's
profile, engineers and validates features, runs the clinical rules and the ML
predictors, and finally generates the **clinical report** (Modules 17–20, with
Modules 15/16's decision fusion produced inside it) — persisting every stage.
Modules 4–20 themselves live in `ai-service/`; only the client, the
orchestration and the persistence live here.

## What Module 1 delivers

Per section 7 (Module 1) and section 19 (Security and Privacy) of the project
specification:

| Spec requirement | How it is met |
| --- | --- |
| Users can securely register | `POST /api/v1/auth/register`, validated input, bcrypt-hashed password (cost 12) |
| Users can log in | `POST /api/v1/auth/login`, generic failure message (no account enumeration) |
| Unauthorized users cannot access protected information | `protect` middleware rejects every authentication failure (missing, malformed, expired, forged token; deleted/deactivated user; token predating a password change) with **401**. Other request faults are classified by the central error handler — malformed JSON → 400, oversized body → 413 — so an unauthenticated caller never receives a 500 with a stack trace |
| Patient records remain associated with the correct account | Generic, reusable ownership helpers in `src/utils/ownership.js` (see below) |
| Protected backend APIs can verify authenticated requests | Bearer access token verified per request; `req.user` loaded from the DB |
| Principle of least privilege | `restrictTo(...roles)` → **403**, plus `ownerScopedFilter` / `requireOwnership` |
| Password hashing | bcryptjs, cost factor 12, `pre('save')` hook, `select: false` |
| Input validation | `express-validator` chains + Mongoose schema validation |
| Protected APIs / secure storage | helmet, CORS allowlist, NoSQL-injection sanitisation, strict type-checking on every input field, HPP guard, and rate limiting keyed on a non-spoofable `req.ip` (**requires `TRUST_PROXY` to be set correctly for your deployment — see below**) |

## Quick start

```bash
cd backend
npm install
cp .env.example .env        # then edit .env and set real secrets
npm run dev                 # or: npm start
```

MongoDB must be reachable at `MONGODB_URI` (local `mongod` or an Atlas cluster).
The server refuses to start if `MONGODB_URI`, `JWT_SECRET` or `JWT_REFRESH_SECRET`
is missing — there are no hard-coded fallback secrets outside the test environment.

Generate secrets with:

```bash
node -e "console.log(require('crypto').randomBytes(48).toString('hex'))"
```

## Tests

```bash
npm test
```

Tests use **jest + supertest** with **mongodb-memory-server**, so no external
MongoDB is required. Current status: **450 passing (9 suites)**, plus **3
opt-in live tests** that are skipped by default.

Every ai-service call is mocked at the **axios transport layer**, so the suite
passes with no Python service running and no network. Mocking the transport
rather than the client is deliberate: the tri-state field genuinely absent from
the wire body, the auth and correlation headers, and the unwrapped `extraction`
envelope are only observable in the real outgoing request.

The live end-to-end test is opt-in:

```bash
RUN_LIVE_INTEGRATION=1 AI_SERVICE_URL=http://127.0.0.1:8000 AI_SERVICE_API_KEY=<the key the ai-service is running with> npx cross-env NODE_ENV=test npx jest tests/liveIntegration.test.js --runInBand --forceExit
```

Optionally set `LIVE_REPORT_PATH` to a real lab-report PDF or image.

- `tests/auth.test.js` — integration tests for every endpoint, the `protect`
  middleware, the `restrictTo` guard, refresh rotation and the error envelope.
- `tests/rateLimit.test.js` — runs with the limiter enabled: brute-force
  throttling, the 429 envelope, and proof that `X-Forwarded-For` / `X-Real-IP`
  spoofing cannot bypass it.
- `tests/ownership.test.js` — unit tests for the ownership helpers.
- `tests/reports.test.js` — Module 3 integration tests: upload of each allowed
  type, magic-byte rejection, 413 on oversize, path-traversal filenames,
  cross-user access on all four operations, admin/clinician non-bypass,
  chronological ordering, pagination, download headers, delete, orphan
  rollback. Writes to a `mkdtemp` directory under the OS temp dir and removes
  it afterwards — nothing is written inside the repository.
- `tests/reportRateLimit.test.js` — Module 3 upload throttling, with the
  limiter enabled and its own small budget.
- `tests/profile.test.js` — Module 2 integration tests: CRUD, authentication,
  cross-user access, admin/clinician non-bypass, derived BMI, every
  physiological bound at its boundary, type-confusion payloads on every field,
  free-text caps and sanitisation.
- `tests/ownershipHardening.test.js` — regression tests for the two
  `ownership.js` footguns fixed in Module 2: the identity-less filter now throws,
  and ownership denies by default while an explicit grant still works.
- `tests/analysis.test.js` — the whole §16 pipeline, Modules 4 → 17–20: happy
  path end to end, the canonical request body, the **tri-state profile field
  asserted on the actual outgoing payload**, no-profile, every ai-service
  failure mode handled distinctly and never as a 500-with-stack, the
  empty-but-200 silent failure, raw text never persisted, warning provenance
  across **all seven origins** (fusion and report included), **Module 18's four
  overall statuses reaching the API with the null case intact**, a partial
  assessment never presenting as complete, an unrecognised status degrading to
  `Not Assessed` rather than `Healthy`, each stage failing independently, the
  status lifecycle, the concurrency lock, re-run semantics, cross-user 404s on
  all three routes, and health/readiness.
- `tests/auditDefects.test.js` — regressions for audit defects **D1–D4**. Each
  was verified to **fail** against the pre-fix code by reverting the fixes in a
  scratch copy and re-running.
- `tests/liveIntegration.test.js` — **opt-in** (`RUN_LIVE_INTEGRATION=1`); the
  only test that touches the network.

The first run downloads a MongoDB binary (cached under `node_modules/.cache`);
later runs are offline.

## Environment variables

All variables are listed in `.env.example`.

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `NODE_ENV` | no | `development` | Runtime mode; `production` suppresses stack traces |
| `PORT` | no | `5000` | HTTP port |
| `API_PREFIX` | no | `/api/v1` | Base path for all routes |
| `MONGODB_URI` | **yes** | — | MongoDB connection string |
| `TRUST_PROXY` | no | `false` | **Security-critical**, see below |
| `JWT_SECRET` | **yes** | — | Access-token signing secret. Enforced at startup: ≥ 32 chars |
| `JWT_EXPIRES_IN` | no | `15m` | Access-token lifetime |
| `JWT_REFRESH_SECRET` | **yes** | — | Refresh-token signing secret. Enforced at startup: ≥ 32 chars **and** different from `JWT_SECRET` — the process refuses to start otherwise |
| `JWT_REFRESH_EXPIRES_IN` | no | `7d` | Refresh-token lifetime |
| `JWT_ISSUER` / `JWT_AUDIENCE` | no | `vaidyaai` / `vaidyaai-clients` | Verified JWT claims |
| `BCRYPT_COST_FACTOR` | no | `12` | bcrypt work factor |
| `CORS_ORIGIN` | no | `http://localhost:3000` | Comma-separated allowed origins |
| `RATE_LIMIT_WINDOW_MS` | no | `900000` | Rate-limit window |
| `RATE_LIMIT_MAX` | no | `100` | Requests per window across `/auth` |
| `LOGIN_RATE_LIMIT_MAX` | no | `5` | Failed credential attempts per window |
| `STORAGE_DRIVER` | no | `local` | Which storage adapter backs report files (Module 3) |
| `UPLOAD_ROOT` | no | `backend/storage/uploads` | Directory holding uploaded report files. Relative paths resolve against the backend directory. **Must not be served statically** |
| `UPLOAD_MAX_BYTES` | no | `10485760` (10 MiB) | Hard per-file cap; exceeding it is a clean `413` |
| `UPLOAD_RATE_LIMIT_MAX` | no | `20` | Uploads per window, throttled separately from `/auth` |
| `UPLOAD_RATE_LIMIT_WINDOW_MS` | no | `900000` | Upload rate-limit window |
| `AI_SERVICE_URL` | no | — | Base URL of the Python `ai-service`. Unset ⇒ the analysis endpoints answer `503` and nothing else changes |
| `AI_SERVICE_API_KEY` | **if `AI_SERVICE_URL` is set** | — | Shared service key sent as `X-Service-Key`. **≥ 32 chars**, enforced at startup on both sides. A set URL with an empty or short key **refuses to start** |
| `AI_SERVICE_TIMEOUT_MS` | no | `300000` | Extraction call timeout. **Must exceed the deployed ai-service's own worst case** — see Known limitations |
| `AI_SERVICE_HEALTH_TIMEOUT_MS` | no | `3000` | Health-probe timeout |
| `AI_SERVICE_STAGE_TIMEOUT_MS` | no | `30000` | Default timeout for the fast stages (validation, rules, ML, clinical report). **Never the extraction timeout** — see Analysis pipeline |
| `AI_SERVICE_VALIDATE_TIMEOUT_MS` | no | stage default | Module 6 timeout |
| `AI_SERVICE_RULES_TIMEOUT_MS` | no | stage default | Module 8 timeout |
| `AI_SERVICE_ML_TIMEOUT_MS` | no | stage default | Modules 9/10 timeout |
| `AI_SERVICE_REPORT_TIMEOUT_MS` | no | stage default | Modules 17–20 (clinical report) timeout |
| `AI_SERVICE_RETRIES` | no | `1` | Extra attempts for **transient** failures only (never 401/422) |
| `AI_SERVICE_RETRY_DELAY_MS` | no | `500` | Base backoff between attempts |
| `AI_SERVICE_LOCK_TTL_MS` | no | `600000` | How long a report may sit in `processing` before another analyze may take the lock |
| `ANALYSIS_RATE_LIMIT_MAX` | no | `20` | Analyses per window. The ai-service has no limiter of its own, so this is the only Gemini-spend control |
| `ANALYSIS_RATE_LIMIT_WINDOW_MS` | no | `900000` | Analysis rate-limit window |
| `GEMINI_API_KEY` | no | — | **Belongs to the `ai-service`, not here. The backend never calls an LLM directly.** |
| `GEMINI_MODEL` | no | `gemini-3.6-flash` | **Belongs to the `ai-service`, not here.** |

## Endpoints

Base path: `/api/v1`

| Method | Path | Auth | Success | Description |
| --- | --- | --- | --- | --- |
| `GET` | `/health` | public | 200 | Service + database health, plus the **last known** ai-service reachability (never blocks on it) |
| `GET` | `/health/ai` | public | 200 / 503 | Actively probes the ai-service |
| `POST` | `/auth/register` | public | 201 | Create a patient account; returns user + token pair |
| `POST` | `/auth/login` | public | 200 | Authenticate; returns user + token pair |
| `POST` | `/auth/refresh` | refresh token in body | 200 | Rotate the refresh token, issue a new access token |
| `POST` | `/auth/logout` | refresh token in body | 200 | Revoke that refresh token (this session only) |
| `GET` | `/auth/me` | Bearer access token | 200 | Current authenticated user |
| `GET` | `/auth/admin/users` | Bearer + role `admin` | 200 | Admin-only listing — exists to exercise `restrictTo` |
| `GET` | `/profile/me` | Bearer access token | 200 | The caller's own health profile (404 if none) |
| `POST` | `/profile/me` | Bearer access token | 201 | Create the caller's profile (409 if one exists) |
| `PUT` | `/profile/me` | Bearer access token | 200 / 201 | Create-or-replace the caller's profile |
| `PATCH` | `/profile/me` | Bearer access token | 200 | Partially update the caller's profile (404 if none) |
| `DELETE` | `/profile/me` | Bearer access token | 200 | Delete the caller's profile (404 if none) |
| `POST` | `/reports` | Bearer access token | 201 | Upload one report file (multipart, part named `file`) |
| `GET` | `/reports` | Bearer access token | 200 | The caller's reports, chronological + paginated |
| `GET` | `/reports/:id` | Bearer access token | 200 | Metadata for one of the caller's reports (404 otherwise) |
| `GET` | `/reports/:id/download` | Bearer access token | 200 | Stream the stored file back as an attachment |
| `DELETE` | `/reports/:id` | Bearer access token | 200 | Delete the row and the file |
| `POST` | `/reports/:id/analyze` | Bearer access token | 200 | Run the whole Modules 4-20 chain on the report (409 if one is already running, 503 if unconfigured) |
| `GET` | `/reports/:id/analysis` | Bearer access token | 200 | The stored analysis, clinical report included (404 until a run has succeeded) |
| `GET` | `/reports/:id/report` | Bearer access token | 200 | Modules 17-20's clinical report on its own (404 until one has been generated) |
| `GET` | `/reports/:id/explanation` | Bearer access token | 200 | Modules 23 + 26 - the patient-facing explanation and the pre-approved guidance (404 until the stage has answered) |
| `GET` | `/reports/:id/dashboard` | Bearer access token | 200 | Module 27 - the stored analysis projected into dashboard cards (404 until a clinical report exists) |

### Response shapes

Success:

```json
{ "success": true, "data": { "user": { "id": "…", "name": "…", "email": "…", "role": "patient" }, "accessToken": "…", "refreshToken": "…" } }
```

Error:

```json
{ "success": false, "error": { "code": "VALIDATION_ERROR", "message": "Invalid request payload", "details": [{ "field": "password", "message": "…" }] } }
```

Error codes in use: `BAD_REQUEST`, `VALIDATION_ERROR`, `MISSING_TOKEN`,
`INVALID_TOKEN`, `TOKEN_EXPIRED`, `INVALID_CREDENTIALS`, `ACCOUNT_INACTIVE`,
`PASSWORD_CHANGED`, `USER_NOT_FOUND`, `REFRESH_TOKEN_REVOKED`,
`INSUFFICIENT_ROLE`, `OWNERSHIP_REQUIRED`, `NOT_FOUND`, `CONFLICT`,
`PAYLOAD_TOO_LARGE`, `UNSUPPORTED_MEDIA_TYPE`, `RATE_LIMIT_EXCEEDED`,
`INTERNAL_ERROR`.

### Example

```bash
curl -X POST http://localhost:5000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Asha Patel","email":"asha@example.com","password":"Str0ng!Passw0rd"}'

curl http://localhost:5000/api/v1/auth/me -H "Authorization: Bearer <accessToken>"
```

## Design decisions

**Module system.** CommonJS throughout, for friction-free jest/supertest support.

**Refresh-token storage.** Refresh tokens are JWTs signed with a *separate*
secret and carrying a random `jti`. Only a **SHA-256 digest** of each token is
stored, in a `refreshTokens` subdocument array on the user document
(`select: false`). Rationale: one array entry per active session means a single
device can be logged out without killing the user's other sessions, and a
`select: false` embedded array avoids an extra collection and an extra query on
every refresh. Tokens are **rotated** on every refresh — the presented token is
deleted before the replacement is issued, so a replayed token is rejected with
`REFRESH_TOKEN_REVOKED`. A maximum of 5 concurrent sessions is retained; expired
entries are pruned on each issue. Plain SHA-256 (not bcrypt) is appropriate here
because the token is already high-entropy random material, not a human password.

**Password policy.** Minimum 8 characters with upper, lower, digit and symbol,
**and a hard maximum of 72 bytes**. bcrypt silently ignores every byte past 72,
so without that cap a 100-character password would authenticate against any
string sharing its first 72 bytes. Of the two standard remedies — cap at 72
bytes, or SHA-256 pre-hash before bcrypt to support unlimited length — this
codebase **caps**, because pre-hashing adds a second hash construction to reason
about (and the base64/hex-encoding pitfalls that come with it) for a benefit no
user of this platform needs.

The cap is enforced in **three** places, and the model is the one that matters:

1. `registerValidator` — rejects an over-long password with 422 before it
   reaches the model.
2. **The `password` schema path itself** (`models/User.js`) — a Mongoose
   validator, so the limit holds for every entry path that never touches a
   route: seed scripts, admin provisioning, tests, and any future
   change-password or reset flow. Mongoose runs document validation *before*
   user-defined `pre('save')` hooks, so it sees the plaintext, not the hash.
   `User.create({ password: <100 bytes> })` throws a `ValidationError`, which
   the central error handler already renders as a clean 422 when it happens on
   a request. This is the same "put the guarantee in the model" reasoning used
   for session revocation below.
3. `loginValidator` — caps the *submitted candidate* too. bcrypt truncates
   whatever it is handed, so for an account whose password is exactly 72 bytes,
   `<password> + anything` would otherwise compare equal and authenticate.
   Registration can no longer produce a password longer than 72 bytes, so this
   locks out nobody legitimate.

The limit is measured with `Buffer.byteLength`, never `String.length`. A
four-byte emoji is a surrogate pair that `String.length` counts as 2, so a
48-character password of 20 emoji plus 8 ASCII characters is 88 bytes — under
the limit by character count, over it by bytes.

**`TRUST_PROXY` (security-critical).** `req.ip` is the rate limiter's key, and
Express derives it from the client-supplied `X-Forwarded-For` header whenever
`trust proxy` is enabled. This is therefore **`false` by default** and must be
set deliberately per deployment:

- Exposed directly (no proxy) → leave `false`. Setting it otherwise lets any
  caller rotate `X-Forwarded-For` and get unlimited login attempts. Verified:
  with `TRUST_PROXY=1` and no real proxy, 8 failed logins with rotating
  `X-Forwarded-For` returned `401` eight times — zero throttling.
- Behind a load balancer / reverse proxy (nginx, ELB, Cloudflare, Heroku) → set
  it to the real hop count (usually `1`). If you leave it `false` there, every
  request appears to come from the proxy's IP and a single abusive client
  rate-limits all of your users.

Getting this wrong in either direction breaks rate limiting.

**Input type checking.** Every validator chain begins with `.isString().bail()`
before any sanitizer. A JSON body can carry arrays and objects; `hpp()` only
touches query strings and urlencoded bodies, and `express-mongo-sanitize` only
strips `$`/`.` keys, so neither stops an array. Without the type check an array
email reaches Mongo, whose scalar-vs-array matching treats it as "any of these"
— letting one request spray a single password across thousands of harvested
addresses for the cost of one `bcrypt.compare`.

**Session revocation on password change.** Changing a password backdates
`passwordChangedAt` **and** purges every stored refresh-token digest. Both are
driven from the model's `pre('save')` hook rather than an endpoint, so any
future change-password or reset flow inherits the behaviour automatically. The
refresh endpoint independently re-checks `passwordChangedAfter`, so a token that
somehow survived the purge is still rejected.

**Role escalation.** `role` is **rejected**, not ignored, on self-registration:
sending anything other than `"patient"` fails validation with 422. The
controller additionally hard-codes `ROLES.PATIENT` when creating the user, so
the guarantee holds even if the validator is ever loosened. `clinician` and
`admin` accounts must be provisioned out-of-band (seed script or an admin tool
in a later module).

**Ownership helper.** `src/utils/ownership.js` is deliberately storage-agnostic,
because Module 1 owns no patient-record collection. It exports:

- `isOwner(user, resource, { ownerField })` — id comparison that normalises
  `ObjectId`, string and populated-document owners; supports dotted paths.
- `canAccess(user, resource, { ownerField, allowRoles })` — ownership **or** a
  role listed in `allowRoles`, which **defaults to `[]` (deny by default)**.
- `assertCanAccess(...)` — throwing variant: **404** when the resource is absent
  (so a non-owner cannot probe whether another user's record exists), **403**
  when it exists but belongs to somebody else.
- `ownerScopedFilter(user, { ownerField, base, allowRoles })` — a Mongo filter
  scoped to the requesting user; unscoped only for roles `allowRoles` explicitly
  grants. **Throws** when there is no authenticated identity to scope to.
- `OWNER_ONLY` — `{ allowRoles: [] }`, the medical-data preset.
- `requireOwnership(loadResource, options)` — Express middleware that loads the
  resource, enforces access and attaches it to `req.resource`.

Later modules apply these by pointing `ownerField` at whatever attribute holds
the owning user id (e.g. `requireOwnership((req) => Report.findById(req.params.id))`).

**Error handling.** Every error passes through one handler. Only `ApiError`
instances (and a few recognised driver errors) expose their message; anything
else becomes an opaque 500. Stack traces appear only when `NODE_ENV !== production`.

**Rate limiting.** Off by default under `NODE_ENV=test` so the integration suite
is not throttled; `ENABLE_RATE_LIMIT=true` turns it back on, which is how
`tests/rateLimit.test.js` exercises the limiter for real (including the
`X-Forwarded-For` spoofing attempts).

## Module 2 — Patient Profile Management

Each user has **at most one** health profile, stored in its own `profiles`
collection referencing `User` by id, with a **unique index on `user`**. Medical
data is deliberately *not* embedded in the `User` document: section 19 asks for
"restricted medical information exposure", and keeping the two apart means an
authentication query never loads health data, and credentials and medical
records can be retained, encrypted or deleted independently.

### Units — fixed, explicit, and never inferred

| Field | Unit | Notes |
| --- | --- | --- |
| `age` | whole years | integer only |
| `heightCm` | **centimetres** | never inches |
| `weightKg` | **kilograms** | never pounds |
| `bmi` | **kg/m²** | derived, read-only |

Numeric fields accept **JSON numbers only**. Numeric *strings* are rejected
(422), so a unit can never be smuggled in as `"70kg"` and silently parsed as
`70`. A unit mix-up here would corrupt every downstream ML prediction, so the
field names carry the unit and the API has no unit parameter.

### BMI is derived, never trusted

`bmi = weightKg / (heightCm / 100)²`, rounded to 2 decimal places.

Two independent guards:

1. The controller allow-lists writable fields, and `bmi` is not among them, so a
   client-supplied `bmi` is dropped before it reaches the model.
2. The model's `pre('validate')` hook recomputes `bmi` on **every** save, so no
   code path — route, seed script or future module — can persist a client value
   or a stale one. When either height or weight is missing, `bmi` is `undefined`
   rather than a guess.

### Field reference

| Field | Type | Bounds / values |
| --- | --- | --- |
| `age` | integer | 0–120 |
| `gender` | enum | `male`, `female`, `other`, `prefer_not_to_say` |
| `heightCm` | number | 30–275 |
| `weightKg` | number | 1–650 |
| `bmi` | number | **derived, read-only** |
| `hypertension` | boolean | `true` / `false` / absent (= unknown) |
| `heartDisease` | boolean | `true` / `false` / absent (= unknown) |
| `heartDiseaseDetails` | string[] | ≤ 30 entries, ≤ 200 chars each |
| `smokingHistory` | enum | `never`, `former`, `current`, `ever`, `not_current`, `no_info` |
| `allergies` | string[] | ≤ 30 entries, ≤ 200 chars each |
| `medicalConditions` | string[] | ≤ 30 entries, ≤ 200 chars each |
| `medications` | string[] | ≤ 30 entries, ≤ 200 chars each |
| `previousHealthInformation` | string[] | ≤ 10 entries, ≤ 500 chars each |
| `completeness` | object | derived: `{ fields, filled, percent, missing[] }` |

Bounds are deliberately **generous** — they exist to reject data-entry nonsense
(a 5 cm height, a 4000 kg weight) that would poison a model, not to second-guess
real outliers. Validation of *laboratory* values is Module 6 and is not done
here.

Free-text entries are sanitised after the caps are enforced: control characters
are stripped, whitespace runs collapse, and blank entries are dropped. Error
messages are static and **never echo the submitted value back**.

`null` is not a valid value for any field — it fails the type guard with a 422.

### Representation for the ML predictors (Modules 10–12)

These are the exact stored forms; downstream predictors consume them without
guesswork or a translation table.

- **`gender`** — the profile always stores the user's *actual* answer. The
  predictors are trained on a binary Male/Female feature, so `male` / `female`
  map straight onto it, while `other` and `prefer_not_to_say` are **not**
  coerced into a category: a predictor must treat them as "gender unavailable"
  and degrade, exactly as it does for an absent value. `Profile.ML_GENDER_VALUES`
  exports the subset a binary model can consume.
- **`smokingHistory`** — the six strings are exactly the categories of the
  public diabetes-prediction dataset Module 10 is modelled on, so the stored
  string is directly encodable. `no_info` is a real level of the feature (an
  explicit "unknown"), not a null; an **absent** field should be treated as
  `no_info`.
- **`hypertension`** and **`heartDisease`** — tri-state on purpose: `true`,
  `false`, or **absent meaning unknown**. They map to the datasets' 1/0 flags,
  but "we never asked" is not the same as "no", and collapsing absent to `0`
  would fabricate a negative finding. Predictors must check for absence.
- **`bmi`** — kg/m², or `undefined` when height or weight is missing.
- **`completeness`** — `{ fields, filled, percent, missing[] }` over the seven
  ML-relevant fields (`age`, `gender`, `heightCm`, `weightKg`, `hypertension`,
  `heartDisease`, `smokingHistory`). Module 12's kidney predictor explicitly
  skips prediction when information is insufficient; this lets it decide without
  probing field by field.

### Endpoint semantics

- `GET /me` → **404** when no profile exists, not an empty 200 object. "No
  profile" and "an empty profile" are different states: the client needs to know
  whether to `POST` or `PATCH`, and a synthesised empty body would report a
  misleading 0% completeness for a record that does not exist.
- `POST /me` → strict create; **409** if a profile already exists.
- `PUT /me` → create-or-replace (upsert). **201** on create, **200** on replace.
  **Replace semantics**: writable fields omitted from the body are *cleared*.
  This keeps `PUT` idempotent and is the only way to unset a field.
- `PATCH /me` → partial update; **404** when no profile exists. It never creates.
- `DELETE /me` → **200** with `{ deleted: true, id }`; **404** when there is
  nothing to delete.

### How ownership is enforced

Module 2 is the first module with records to own, so it is where
`src/utils/ownership.js` is actually wired up rather than merely available.

1. **No addressable ids.** Every route is `/profile/me`. No endpoint accepts a
   profile id or a user id from the client, so the whole "change the id in the
   URL" class of attacks has nothing to target. The owner is taken from the
   verified JWT via `protect`, never from the request body — `user`, `_id` and
   `id` are not in the writable allow-list, so they are dropped. The model's
   `user` field is also `immutable`, so a profile can never be re-pointed at
   another account.
2. **Owner-scoped queries.** Every read and write goes through
   `ownerScopedFilter(req.user, { ...OWNER_ONLY })`, so the Mongo query can only
   ever match the caller's own document.
3. **A redundant post-load check.** `assertCanAccess(req.user, profile,
   { ...OWNER_ONLY })` re-verifies the loaded document before it is returned or
   mutated. Redundant by design: if a future refactor widens the filter, this
   still denies.
4. **No staff bypass.** Ownership denies by default, and the profile call
   sites additionally spell it out with `OWNER_ONLY`. Section 19 says users may access only
   their own medical information, with no exception carved out for staff, so an
   **admin or clinician reading another patient's profile gets the same 404 any
   other non-owner gets**. This is covered by tests.
5. **No existence leak.** `assertCanAccess` answers 404 before 403. Because the
   query is owner-scoped, a non-owner never loads the document at all and always
   sees the plain "no profile" 404 — indistinguishable from simply not having
   created one.

### Fixes made to `ownership.js`

Both footguns flagged by Module 1's audit were fixed before first use.

**1. `ownerScopedFilter` with no identity now throws** instead of returning
`{ user: null }`. That old return value was a *valid* Mongo filter matching
every document with a null or absent owner — a malformed caller got a query
that silently succeeded instead of one that denied. It now raises, which becomes
a 500, never a data leak.

**2. `allowRoles` now denies by default.** The default changed from
`[ROLES.ADMIN]` to `[]`: **no role bypasses ownership unless a call site
explicitly grants one.**

An opt-*out* security default fails open. Modules 3, 7, 17, 28, 29 and 32 all
touch patient data, and under the old default every one of them would silently
inherit an administrator bypass on medical records if its author simply forgot
to opt out. That is the same failure shape this codebase has already hit twice:
the 72-byte password cap enforced only at the validator (any other code path
reintroduced the flaw), and `.isString()` present on four validator chains but
missing on the fifth — a live authentication bypass. Both times the fix that
held was the one at the lowest layer, applied by default. Section 19 requires
least privilege with no staff exception carved out, so the safe behaviour is now
the one you get for free.

**The capability is unchanged — only the default is.** Where staff access is
genuinely warranted (audit logs, user administration, a future admin console),
grant it explicitly and deliberately at the call site:

```js
const { ROLES } = require('../utils/roles');

ownerScopedFilter(req.user, { allowRoles: [ROLES.ADMIN] }); // unscoped for admins
assertCanAccess(req.user, resource, { allowRoles: [ROLES.ADMIN] });
```

Medical resources should never do this. `OWNER_ONLY` (`{ allowRoles: [] }`)
remains exported and is still spread at every profile call site: it is now
*identical to the default* and therefore redundant, kept deliberately as
belt-and-braces — the same reasoning that makes the controller re-check with
`assertCanAccess` after an already owner-scoped query. It states intent at the
call site and keeps health data denying even if the default is ever loosened.

`assertCanAccess`'s 404-before-403 ordering was **not** changed, and is covered
by a new regression test under `OWNER_ONLY`.

Two assertions in Module 1's `tests/ownership.test.js` pinned the old
permissive default. They were **inverted, not deleted** — they now assert the
secure default — and paired with new tests proving an explicit
`allowRoles: [ROLES.ADMIN]` still restores the bypass.

### Example

```bash
TOKEN=<accessToken>

curl -X POST http://localhost:5000/api/v1/profile/me \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"age":41,"gender":"female","heightCm":165,"weightKg":68,
       "hypertension":true,"heartDisease":false,"smokingHistory":"former",
       "allergies":["Penicillin"],"medications":["Metformin 500mg"]}'

curl http://localhost:5000/api/v1/profile/me -H "Authorization: Bearer $TOKEN"
```

## Module 3 — Medical Report Upload and Management

Users upload laboratory reports (**PDF, JPG, JPEG, PNG**); the platform keeps
them associated with the uploading account and ordered **chronologically**, so
Modules 28–30 (trend analysis, report comparison, progress monitoring) have
data they can sort and diff. Module 3 implements storage and retrieval **only**
— there is no OCR, no text extraction, no parsing of report contents anywhere
in this module.

### Endpoints

Base path `/api/v1/reports`. Every route requires a valid access token, and
every route is scoped to the caller's own reports.

| Method | Path | Body / query | Success | Description |
| --- | --- | --- | --- | --- |
| `POST` | `/reports` | `multipart/form-data`: `file` (required), `reportDate` (optional ISO-8601) | `201` | Upload one report |
| `GET` | `/reports` | `page`, `limit`, `sort`, `order`, `status` | `200` | List own reports, chronologically ordered and paginated |
| `GET` | `/reports/:id` | — | `200` | Metadata for one own report |
| `GET` | `/reports/:id/download` | — | `200` | Stream the stored file back |
| `DELETE` | `/reports/:id` | — | `200` | Delete the record **and** the file |

Listing parameters: `page` ≥ 1, `limit` 1–100 (default 20), `sort` one of
`chronoDate` (default) / `uploadedAt` / `reportDate`, `order` `asc` | `desc`
(default `desc` — newest first), `status` one of the processing-status enum.
`_id` is always appended as a secondary sort key so paging stays stable when
several reports share a date.

Status codes: `400` no file / empty file / unexpected field, `401`
unauthenticated, `404` unknown id **and** somebody else's id (see below),
`413` file too large, `415` file type not allowed, `422` invalid `reportDate`
or listing parameters, `429` upload rate limit.

Example:

```bash
curl -X POST http://localhost:5000/api/v1/reports \
  -H "Authorization: Bearer $ACCESS" \
  -F "file=@bloodwork.pdf" \
  -F "reportDate=2026-03-14"
```

```json
{
  "success": true,
  "data": {
    "report": {
      "id": "68e0…",
      "user": "68df…",
      "originalName": "bloodwork.pdf",
      "mimeType": "application/pdf",
      "sizeBytes": 184213,
      "checksumSha256": "9f2c…",
      "storageDriver": "local",
      "uploadedAt": "2026-08-28T09:14:02.113Z",
      "reportDate": "2026-03-14T00:00:00.000Z",
      "chronoDate": "2026-03-14T00:00:00.000Z",
      "status": "uploaded"
    }
  }
}
```

### Chronological storage — two dates, one sort key

Two dates are kept, because they are genuinely different facts:

- **`uploadedAt`** — when the file reached the server. Always present, always
  the server clock, never settable by a client.
- **`reportDate`** — the date printed on the lab report. Optional, supplied by
  the user, and frequently *much* earlier than `uploadedAt`: a patient
  uploading three years of history in one sitting would otherwise produce a
  timeline in which every report happened today.

Ordering must therefore mean *"the report's own date if we know it, else the
upload date"*. Computing that at query time (`$ifNull`) would defeat any index,
so it is **materialised** into `chronoDate` by a `pre('validate')` hook and
indexed together with the owner:

```js
reportSchema.index({ user: 1, chronoDate: -1, _id: -1 });
```

Modules 28–30 get an index-covered scan for "this patient's reports in order",
which is exactly the query they are built on. The hook recomputes `chronoDate`
on **every** save, so it can never drift from its inputs.

### Storage layout

Files live on local disk; **metadata lives in MongoDB**. Nothing binary is
stored in Mongo (Atlas' free tier is 512 MB, and GridFS was explicitly ruled
out).

```
<UPLOAD_ROOT>/
  <userId>/                       # 24-hex Mongo ObjectId
    <64 hex chars>.pdf            # 32 random bytes + the DETECTED extension
    <64 hex chars>.png
```

- The directory is **outside any statically served path** — this app serves no
  static files at all. The only way to read a stored file is the authenticated,
  owner-scoped `/download` route.
- Per-user subdirectories are a *containment* measure, not an access-control
  one: access control is enforced by the owner-scoped Mongo query. They make
  ownership auditable on disk and keep directory sizes sane.
- The stored filename contains **no byte of client input**. The client's
  filename is sanitised and kept for display (and for the
  `Content-Disposition` header) only.
- Writes go to `<name>.part` and are `rename`d into place, so an interrupted
  write leaves a stray part-file rather than a truncated file the database
  claims is complete. `wx` is used so a name collision fails loudly instead of
  clobbering an existing report.

### The storage adapter, and how to swap it

`src/storage/StorageAdapter.js` defines the contract; `localDiskAdapter.js` is
the only implementation today; `src/storage/index.js` is the factory that maps
`STORAGE_DRIVER` to an instance.

```js
get name(): string                                    // persisted per report
async save({ userId, buffer, extension }): { key, size }
async createReadStream(key): Readable
async stat(key): { size } | null
async remove(key): boolean                            // idempotent
async removeUserScope(userId): void
```

The `key` is **opaque**. The database stores it verbatim alongside the
`storageDriver` that produced it, and nothing outside the adapter may parse,
join, or otherwise interpret it. The controller never touches `fs`.

**To move to Cloudinary / Supabase / Firebase later:**

1. Add `src/storage/<provider>Adapter.js` implementing the six methods above.
2. Register it in the `DRIVERS` map in `src/storage/index.js`.
3. Set `STORAGE_DRIVER=<provider>` plus whatever credentials it needs.

No model, controller, route or test changes. Because every report records the
driver that produced its key, rows written by the old adapter keep resolving
through the old adapter as long as both stay registered — so a migration can be
gradual rather than a flag day.

### Security measures

File upload is the most-attacked surface in the app. What is actually enforced:

- **Type is decided by magic bytes, never by the client.** The declared
  `Content-Type` and the extension inside the declared filename are used for
  *nothing*. `%PDF-` at offset 0, `FF D8 FF`, and the 8-byte PNG signature are
  the entire allow-list. An HTML, PHP, ZIP or PE payload named `report.pdf` is
  a `415`, and the **detected** type is what gets persisted and later served.
  **SVG is deliberately excluded** — it is XML that can carry `<script>`, so
  accepting it would be handing out stored XSS.
- **The client filename is never trusted.** `sanitizeFilename` strips null
  bytes and control characters, discards every path segment (so `../../x` and
  `C:\Windows\x` both collapse to their last component), replaces characters
  that are illegal on Windows, strips leading dots and trailing dots/spaces
  (`evil.php.` → `evil.php`), rejects reserved device names (`CON`, `NUL.pdf`,
  `LPT1.png` → `file_…`), caps the length, and can never return a value
  containing a separator. It is used for display only.
- **Every path is verified before use.** `resolveKey` re-resolves any key
  against `UPLOAD_ROOT` and refuses anything that does not land inside it —
  including absolute paths and drive letters, which would otherwise make
  `path.join` discard the root. This holds even for a malicious key already in
  the database (there is a test that writes one through the raw driver).
- **Size cap, cleanly.** `UPLOAD_MAX_BYTES` is enforced by multer, which aborts
  the stream, and re-asserted after buffering. A `MulterError` is mapped in the
  central error handler to a `413` with the standard envelope — never a `500`,
  never a stack trace, never a hung request. The global
  `express.json({ limit: '10kb' })` is **untouched**: multipart bodies bypass
  the JSON parser entirely, so uploads got their own budget without widening
  the JSON surface.
- **Owner scoping on every operation.** Reads, downloads and deletes all go
  through `ownerScopedFilter(req.user, { ...OWNER_ONLY })`, so another user's
  id simply does not match. A non-owner therefore gets a `404` that is
  byte-identical to the one a random id produces — the existence of another
  patient's report is never disclosed. `requireOwnership` +`assertCanAccess`
  re-check the loaded document afterwards, deliberately redundantly.
- **No administrator bypass.** `OWNER_ONLY` is passed explicitly at every call
  site. An admin or clinician reading, downloading or deleting another
  patient's report gets the same `404` as anyone else. Tested for both roles on
  all four operations.
- **Downloads cannot become XSS.** `Content-Disposition: attachment` (with a
  header-injection-safe filename plus an RFC 5987 `filename*`),
  `X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store`, and
  `Content-Security-Policy: default-src 'none'; sandbox`.
- **Uploads are rate-limited separately** from the auth limiters, with their
  own store and budget — an upload costs orders of magnitude more than a login
  attempt, and neither surface should be able to exhaust the other.
- **Nothing logs file contents.** Only ids, sizes and digests are ever written
  to a log. The SHA-256 checksum is stored (integrity, and duplicate detection
  for later modules); hashing is not logging, and the digest is not reversible.
- **`user` and `storageKey` are immutable at the model layer**, so a report can
  never be re-pointed at another account or at another file.
- Validators follow the project rule: every chain starts with a type guard and
  `.bail()`. This matters more here than elsewhere, because `express-mongo-
  sanitize` and `hpp()` run *before* multer parses the multipart body and
  therefore protect nothing on an upload request.

### Orphan handling

A file and its database row must either both exist or neither do.

| Failure | Handling |
| --- | --- |
| Type/size/validation rejection | The file was never written — multer buffers in memory, so a rejected payload never touches the filesystem at all. |
| File write fails | The adapter removes its own `.part` file and rethrows; **no** database row is created. |
| Database insert fails | The just-written file is removed in the `catch` before the error is re-thrown, so no unreferenced blob is left behind. Cleanup is best-effort and never masks the original error. |
| Delete | The **row goes first, then the file**. If the sequence is interrupted, the residue is an unreferenced file (invisible to users, reclaimable by a sweep) rather than a record pointing at a missing file (visible to users as a broken download). |
| File already missing on delete | Not an error — `remove` is idempotent, so a report whose file was lost is still deletable. The response reports `fileRemoved: false`. |

All five are covered by tests, including a simulated database failure and a
simulated cleanup failure.

### What Module 4 inherits

Module 4 (OCR) is a **separate Python service**. It is now called from here —
see *Analysis pipeline* below. A report row carries everything it needs:

- `storageDriver` + `storageKey` — hand these to `getStorage(driver)` and call
  `createReadStream(key)` (or `stat`) to obtain the bytes. Do **not** build a
  path by hand; the key is opaque and the adapter is the only thing that may
  resolve it.
- `mimeType` — the **verified** type, so a PDF branch and an image branch can
  be chosen without re-sniffing.
- `sizeBytes`, `checksumSha256` — integrity check, and a cheap way to skip
  re-processing an identical file.
- `status` (`uploaded` → `processing` → `processed` | `failed`) and
  `statusMessage` — Module 4 owns these transitions; Module 3 only ever writes
  `uploaded`. `statusMessage` is for an error label only and must **never** hold
  report text or medical values.
- `chronoDate` — already correct for Modules 28–30; extraction must not alter
  it.

## Analysis pipeline — Modules 4, 5, 6, 8, 9/10 orchestration

This is the layer that makes the spec's §16 data flow real. Until it existed,
Module 3 stored files and nothing ever extracted them; `status` was declared but
only ever `uploaded`. It originally stopped after feature engineering, then
after clinical decisions; it now runs the whole chain through to the **clinical
report** — the user-visible deliverable, not raw decisions.

```
POST /reports/:id/analyze
  -> claim the report (uploaded|processed|partial|failed -> processing)  [atomic lock]
  -> getStorage(driver).createReadStream(key)                     [never a path]
  -> POST {AI_SERVICE_URL}/api/v1/ocr/extract        multipart, part named `file`
                                                     Module 4   [LOAD-BEARING]
  -> load the caller's Module 2 profile (optional)
  -> POST {AI_SERVICE_URL}/api/v1/features/engineer  { extraction, profile? }
                                                     Module 5   [LOAD-BEARING]
  -> POST {AI_SERVICE_URL}/api/v1/features/validate  { engineered }
                                                     Module 6
  -> CONCURRENTLY:
       POST {AI_SERVICE_URL}/api/v1/rules/evaluate   { validated }   Module 8
       POST {AI_SERVICE_URL}/api/v1/ml/predict       { validated }   Modules 9/10
       POST {AI_SERVICE_URL}/api/v1/report/generate  { validated }   Modules 17-20
                                                     (Modules 15+16 fused inside it)
  -> persist extraction + features + validation + both decision sets
     + the clinical report + the merged warning list; status -> processed
     (a downstream stage failing -> status partial, everything else still stored)
     (extraction or feature engineering failing -> status failed, nothing stored)

GET /reports/:id/analysis    the stored result, decisions AND the report included
GET /reports/:id/report      the clinical report on its own
GET /health/ai               active readiness probe for the ai-service
```

**`/api/v1/decisions/fuse` (Modules 15+16) is deliberately NOT called.**
`/report/generate` runs the decision engine and the fusion engine internally and
returns that exact fusion object nested **verbatim** under `report.fusion` —
and through it Module 15's `collection`. A separate `/decisions/fuse` call would
run the same work twice and hand the backend two fusion objects that a
non-deterministic predictor tie-break could make disagree: a second source of
truth for the same facts, which is the same objection that keeps Module 7 out of
this chain. So the fusion is **read out of the report**, not fetched separately,
and `analysis.stages.report` covers Modules 15 through 20 as one stage.

**The rule and ML calls are kept even though `/report/generate` re-derives them
internally.** That duplication is deliberate and bounded:

- The backend persists each stage's own output for auditability, and the
  report's fused view cannot be un-fused back into it. Module 15 groups by
  `(condition, source)`, so the **per-rule** traceability that makes "which rule
  fired, on what evidence" answerable exists only in the standalone Module 8
  response.
- `/report/generate` **contains** an engine failure internally, as a
  `sources_failed` entry inside an HTTP 200. Without the standalone calls the
  backend could not say "the ML stage failed" at all — it would store a report
  quietly resting on one source and call the run `processed`.
- The cost is CPU on the Python side, not latency: the three calls run
  **concurrently**, and none of them touches Gemini. Nothing is re-extracted.

Revisit this seam only if the ai-service grows a way to accept pre-computed
decisions over HTTP.

**Module 7 (Feature Repository) is deliberately NOT called.** The ai-service's
repository is in-memory and process-local — it does not survive a restart and is
not shared between workers, as its own module docstring states. MongoDB is this
pipeline's durable store, so `POST /repository/load` would put the same feature
set in a second place with a different lifetime and no owner scoping: a second
source of truth guaranteed to disagree with the first after any restart.
Modules 8 and 9/10 consume Module 6's output directly, so the repository is not
on the critical path. Reconsider when it grows a persistent backend — not before.

**Decisions are never de-duplicated or collapsed.** The unit of a rule decision
is one **rule**, not one condition: HbA1c 6.8 and fasting glucose 112 correctly
produce two separate `Diabetes` decisions from the rule engine (the live run
below produced five rule decisions across one flagged condition). That is what
makes per-rule traceability possible, and grouping or fusing them is Module
15/16's job. `analysis.decisionCount` counts **decisions**;
`analysis.conditionsFlagged` is a set of **conditions** and must not be read as
a count of anything.

### Endpoints

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/v1/reports/:id/analyze` | Runs the whole chain. 200 (`status` `processed` or `partial`), 409 if one is already running, 503 if unconfigured. Rate-limited separately. |
| `GET` | `/api/v1/reports/:id/analysis` | The stored analysis — extraction, features, validation, both decision sets **and the clinical report**. 404 until a run has succeeded. |
| `GET` | `/api/v1/reports/:id/report` | Modules 17–20's clinical report on its own, plus the Module 18 `overall` card. 404 until a report has been generated. |
| `GET` | `/api/v1/reports/:id/explanation` | Modules 23 + 26 — the safety-approved patient explanation and the catalogue guidance. 404 until that stage has answered; a run where **every** explanation was withheld is a 200, not a 404. |
| `GET` | `/api/v1/reports/:id/dashboard` | **Module 27.** The stored analysis projected into the spec's card groups — overall health, condition cards, laboratory cards, evidence, recommendations. Calls no model and no service; it is a read model over `clinicalReport`, `patientExplanation` and `lifestyleGuidance`. 404 until a clinical report exists, because a synthesised empty dashboard is indistinguishable from one that genuinely found nothing. |
| `GET` | `/api/v1/health/ai` | Unauthenticated. 200 reachable / 503 unreachable. |

All the report routes are authenticated and owner-scoped **exactly** like every
other report route: `ownerScopedFilter(req.user, { ...OWNER_ONLY })` on every
query plus an `assertCanAccess` re-check, 404-before-403, and an admin or
clinician gets a 404 byte-identical to a random id.

### The ai-service contract

| | |
|---|---|
| Auth | `X-Service-Key: $AI_SERVICE_API_KEY`. Minimum 32 chars, enforced at startup on both sides. |
| Correlation | `X-Request-Id`, echoed back. The **report id** — opaque, never PHI. Filtered to the service's `[A-Za-z0-9._:-]{1,128}` charset, because anything else is silently discarded there. |
| Extraction | `POST /api/v1/ocr/extract`, multipart, part named `file`. |
| Features | `POST /api/v1/features/engineer`, JSON `{ "extraction": <the unwrapped `data` object>, "profile": {...} }`. |
| Validation | `POST /api/v1/features/validate`, JSON `{ "engineered": <Module 5's unwrapped `data`> }`. |
| Rules | `POST /api/v1/rules/evaluate`, JSON `{ "validated": <Module 6's unwrapped `data`> }`. |
| ML | `POST /api/v1/ml/predict`, JSON `{ "validated": <Module 6's unwrapped `data`> }`. |
| Clinical report | `POST /api/v1/report/generate`, JSON `{ "validated": <Module 6's unwrapped `data`> }`. Module 20's rejected-feature join is built by lifting Module 6's `rejected` map out of the **raw** body, so the whole object is load-bearing here in a way it is nowhere else: slicing it down to `valid` would not fail, it would return 200 with a report saying "this value was not available in the submitted report" about a value that *was* there and was refused. |

Every stage is sent the **whole** upstream `data` object, never a slice of it.
Each one forwards `all_warnings`, `upstream`, `missing_features` and `unmapped`
into its own output, so sending only `features` / `valid` would destroy the
provenance Module 17 needs. The `data` envelope is always unwrapped first.

The rules and ML calls both take Module 6's output and never the `engineered`
fallback the service also accepts: that path re-validates in-process, so the
decisions would rest on a validation this backend never saw and never stored,
and the stored evidence would not explain the stored conclusion.

**Timeouts are per stage.** Extraction is the only slow one (Gemini calls per
page, 5-minute default). Validation, rules and ML are pure computation over an
already-extracted feature set and return in milliseconds — measured at 10 ms,
14 ms and 1657 ms respectively in the live run below — so they get their own
30-second default via `AI_SERVICE_STAGE_TIMEOUT_MS`, individually overridable
with `AI_SERVICE_VALIDATE_TIMEOUT_MS`, `AI_SERVICE_RULES_TIMEOUT_MS`,
`AI_SERVICE_ML_TIMEOUT_MS` and `AI_SERVICE_REPORT_TIMEOUT_MS`. Letting them
inherit the extraction timeout would pin four more Node handles for five minutes
each against a wedged service, after the expensive stage had already succeeded.
The report stage is the heaviest of the four (measured at 2113 ms live, since it
runs the whole decision chain in-process before building the report) and is
still three orders of magnitude inside its own budget.

### Partial failure — what a failed stage may and may not claim

Not all six stages are equal, and pretending they are loses information in both
directions.

| Stage | Class | If it fails |
|---|---|---|
| 4 extraction | **load-bearing** | Nothing is persisted. `status` → `failed`. Any previous successful analysis survives untouched. |
| 5 feature engineering | **load-bearing** | As above — without features there is no result at all. |
| 6 validation | downstream | Extraction + features are still persisted. Rules, ML **and the report** are **skipped** (`reasonCode: VALIDATION_UNAVAILABLE`), not re-pointed at unvalidated input. `status` → `partial`. |
| 8 clinical rules | downstream | Everything else, **including the ML decisions and the report**, is still persisted. `status` → `partial`. |
| 9/10 ML predictors | downstream | Everything else, **including the rule decisions and the report**, is still persisted. `status` → `partial`. |
| 17–20 clinical report | downstream | Everything else, **including both decision sets**, is still persisted. `clinicalReport` and the whole `analysis.overall*` summary are **unset** — no overall health status is ever invented for a report that was not produced. `status` → `partial`, and `GET /reports/:id/report` answers 404 rather than serving half a page. |

`processed` means **every** stage succeeded. `partial` is a 200 whose body says
so twice over — `report.status` is `partial`, and `analysis.stages` names each
failed stage with a machine error code — so nothing in the response claims a
stage succeeded when it did not. A partial result is genuinely more useful than
none: the validated features and whichever decision source did answer are
exactly what Module 17 consumes.

Rules, ML and the clinical report run **concurrently**. They take the same
input, none reads another's result, and §16 draws the first two in parallel; the
report endpoint re-derives its own decisions in-process, so it genuinely does
not depend on the two calls beside it. Each call is wrapped so it settles rather
than rejects, so one failing can never discard another's result — which a bare
`Promise.all` over the three raw calls would do.

### Module 18 has FOUR cases and all four reach the API

The spec names three overall statuses. There is a fourth case, and it is the
dangerous one: **nothing could be assessed at all**. "No abnormal findings" is
vacuously true of a report whose every test was unreadable, so rendering that as
`Healthy` would tell a patient whose document could not be read that they are
well.

| `analysis.overallStatus` | `analysis.overallStatusLabel` | `analysis.anyAssessed` | Meaning |
|---|---|---|---|
| `null` | `Not Assessed` | `false` | Nothing could be assessed |
| `Healthy` | `Healthy` | `true` | Assessed, no abnormal finding |
| `Needs Monitoring` | `Needs Monitoring` | `true` | Abnormal finding, no High risk |
| `Needs Medical Attention` | `Needs Medical Attention` | `true` | Abnormal finding + High risk |

How the fourth case is protected, structurally rather than by convention:

- `analysis.overallStatus` is schema type **`Mixed`, not `String`**, precisely so
  an explicit `null` **persists** and stays distinguishable from "the report
  stage did not run" (absent). A dedicated `storeNullable` writer is used for it
  and for `overallRisk`; the ordinary `store` helper unsets on `null` and would
  have erased the fourth case into "absent".
- `overallStatusLabel` is **derived from `overallStatus` in exactly one place**
  (`analysisService.summariseReport`), so the convenience field cannot drift
  from the authoritative one. A `null` status always yields `Not Assessed` and
  can never yield one of the spec's three words — *even if the service's own
  `status_label` claims otherwise*. That case is tested.
- Only the three spec words survive validation. Anything else — a future
  vocabulary, a typo, a non-string — degrades to `null` / `Not Assessed`.
  Unknown input fails **towards "we cannot say"**, never towards "you are well".
- `assessmentComplete` and `anyAssessed` use a strict `=== true` and are forced
  `false` whenever the status is `null`. A missing field means "we do not know
  it was complete", which is not the same as complete.
- `overallRisk` is `null`, never `Low`, when nothing was assessed.
- A **partial** assessment keeps the status of what *was* assessed (downgrading
  a clean partial report would report a finding nobody made) and makes the
  incompleteness structural instead: `assessmentComplete: false`,
  `unassessedConditionCount`, the report's own non-null `overall.caveat`, and a
  `stage: "report"` warning.

A stage that did not answer has its payload and its derived counts **removed**,
not left as they were. Leaving a previous run's rule decisions beside this run's
features would present stale clinical conclusions as current; the failure is
visible in `analysis.stages`, but nobody reads that before reading the
decisions. For the same reason a count is `undefined` rather than `0` when a
stage did not answer: "the rule engine produced no decisions" and "the rule
engine did not answer" are different facts, and collapsing them is the same
class of error as collapsing an absent tri-state into `false`.
| Profile | Module 2's **camelCase** JSON, passed through untranslated (pydantic aliases handle it). |
| Health | `GET /api/v1/health`, unauthenticated. |

**The envelope must be unwrapped.** Module 4 returns `{ success, data }` and
the features endpoint wants that `data` under `extraction`. Relaying the
envelope used to be accepted with **HTTP 200 and `features: {}`** — a pipeline
wired that way looks perfectly healthy and produces nothing. The client sends
the canonical form, and `assertProductiveFeatures` additionally **fails** a run
where the extraction had parameters and the features stage accounted for none
of them, so that shape can never be reported as a success again.

### Tri-state booleans — the highest-risk path

`hypertension` and `heartDisease` are tri-state in Module 2: `true`, `false`, or
**absent meaning unknown**. Absent must stay absent all the way onto the wire —
sending `false` fabricates a negative clinical finding, and Module 12's kidney
predictor uses exactly that distinction to decide when to skip.

`analysisService.buildProfilePayload` is therefore additive: no defaults, no
`||`, no `??`, no destructuring with fallbacks. A key is written only when the
profile carries a value; `false` is a value, `undefined`/`null` are not. The
tests assert on the **actual outgoing request body**, not on an intermediate
object, and the live test confirms the distinction survives the real language
boundary.

### Warnings

Module 5's output has four warning-bearing keys and picking the wrong one
silently loses data:

| Key | Contains |
|---|---|
| `warnings[]` | strings — Module 5's **own only** (backwards compatible) |
| `upstream_warnings[]` | `{stage, module, message}` — Module 4's, verbatim |
| `all_warnings[]` | both, upstream first — **this is the one that is read** |
| `upstream{}` | `pages_unreadable[]`, `extraction_confidence`, … |

All four are merged into `analysisWarnings`, tagged with their origin, exact
repeats collapsed. Module 4's own `warnings[]` off the extraction response is
folded in last as a safety net, so a regression on the Python side cannot make
a damaged scan look like a clean one.

**Module 17's `validation_warnings[]` is read FIRST**, ahead of every other
source. It is the report's own contract for "every warning from every stage —
extraction, feature engineering, validation, rules, ml, **fusion** and
**report** — with its origin `stage` and `module` intact", so it is the richest
list available and its entries win the de-duplication. It is also the **only**
place Module 16's fusion warnings appear at all: an abstaining predictor ("the
rules flagged this; the model could not assess it") and a `basis_conflict` are
carried by nothing else in this chain, and they are exactly what stops a fused
result being read as unanimous. Every other source is still read afterwards —
the report list is *preferred*, not *trusted alone*, because this is the last
hop and dropping upstream warnings at the last hop has been a real defect on
this project twice. An origin the service stated is never rewritten, so a
Module 4 warning relayed by the report still reads `stage: "extraction"`.

`upstream.pages_unreadable` and
`extraction_confidence` are lifted into the always-loaded `analysis` metadata:
"the test is not on the report" and "we could not read the page it was on" are
different statements and Module 17 has to be able to tell them apart.

### Persistence — MongoDB is the single durable store

The ai-service's Module 7 repository is in-memory and process-local, so it is
**not** this pipeline's persistence layer and is not called at all (see above).
Results live on the `Report` document that produced them, which inherits the
report's ownership scoping for free and is deleted with the report:

| Field | Contents |
|---|---|
| `extraction` | Module 4's `data`, **redacted of raw text** (`select: false`) |
| `features` | Module 5's `data`, verbatim (`select: false`) |
| `featureValidation` | Module 6's `data`, verbatim — `valid`/`questionable`/`rejected`, `clinically_extreme`, `missing_features`, `unmapped` (`select: false`) |
| `ruleDecisions` | Module 8's `data`, verbatim — every decision with its evidence and recommendations (`select: false`) |
| `mlDecisions` | Modules 9/10's `data`, verbatim (`select: false`) |
| `clinicalReport` | **Modules 17–20's `ClinicalReport`, verbatim** — patient block (no identity fields), `laboratory_values[]`, `conditions[]`, `overall`, `prioritized[]` (Module 19), `explainability` (Module 20), `recommendations[]`, `document`, `validation_warnings[]`, `summary`, and Module 16's `fusion` **nested whole** (`select: false`) |
| `analysisWarnings` | origin-tagged merged warnings from **all seven origins** — extraction, feature engineering, validation, rules, ml, fusion, report (`select: false`) |
| `analysis.{version,runCount,requestId,startedAt,completedAt,durationMs,profileUsed,extractionConfidence,pagesUnreadable,warningCount}` | small, always loaded |
| `analysis.{stages,stagesFailed}` | per-stage outcome: `{ ok, errorCode?, skipped?, reasonCode?, durationMs }` |
| `analysis.{ruleDecisionCount,mlDecisionCount,decisionCount,highestRisk,conditionsFlagged}` | decision summary, always loaded |
| `analysis.{validFeatureCount,questionableFeatureCount,rejectedFeatureCount}` | Module 6 partition sizes, always loaded |
| `analysis.{reportVersion,overallStatus,overallStatusLabel,overallRisk,assessmentComplete,anyAssessed}` | **Module 18's card**, always loaded. `overallStatus` and `overallRisk` are schema type `Mixed` so an explicit `null` persists — see *Module 18 has FOUR cases* above |
| `analysis.{conditionCount,criticalConditionCount,abnormalConditionCount,normalConditionCount,unassessedConditionCount,recommendationCount,laboratoryValueCount}` | report counts, always loaded |

The seven payload fields are `select: false` because `GET /reports` lists up to
100 rows; without it every listing would drag full extractions, decision sets
and clinical reports through the app. Only the three analysis endpoints select
them, explicitly. The
`analysis.*` summary is always loaded so a dashboard can answer "did every stage
run, how many decisions, what was the worst risk" without touching a payload.

`analysis.stages` carries the same structural PHI guarantee as `statusMessage`:
`errorCode` and `reasonCode` are drawn from fixed tables of this codebase's own
machine codes (`SAFE_STATUS_MESSAGES` / `STAGE_SKIP_REASONS`), and an error
carrying anything else — including a code built from a service response body —
degrades to `ANALYSIS_STAGE_FAILED`. Loss of detail is the correct failure
direction.

`highestRisk` fuses the two decision sources with §16's ordering
(`Low < Medium < High`). An unrecognised band is treated as no value rather than
ranked arbitrarily, and no decisions yields `undefined` — "no decisions" must
never silently become "low risk".

**Raw report text is never persisted.** `raw_text` (document and per page) is
replaced by a `raw_text_available` boolean, matching the principle the
ai-service already applies when forwarding pages. Everything structured —
`extracted_parameters`, `report_metadata`, `source`, `extraction_confidence` —
is kept verbatim, and the original file is still downloadable through Module 3.

The clinical report **does** contain laboratory values — that is what a clinical
report is for — but it carries no raw text either: the ai-service forwards pages
as `{page_number, raw_text_available}` only, and nothing in this backend re-adds
text. A test asserts the stored `clinicalReport` contains neither the string
`raw_text` nor the suite's PHI canary.

### Re-run semantics — overwrite, and non-destructive on failure

Re-analysing is always safe.

- A **successful** re-run replaces `extraction`, `features` and
  `analysisWarnings` wholesale and increments `analysis.version`. There is
  exactly one current analysis per report. History is not kept: it would
  multiply the most sensitive documents in the database for no consumer that
  exists, and the versioned store is Module 7's job.
- A **failed** re-run writes only `status`, `statusMessage` and timing. A report
  analysed successfully yesterday still returns yesterday's analysis after
  today's attempt fails. `status` describes the latest **attempt**;
  `analysis.version`/`completedAt` describe the stored **payload**.

### Concurrency

The move into `processing` *is* the lock: one conditional `findOneAndUpdate`
where the test and the claim are a single atomic Mongo operation. A second
simultaneous call matches nothing and gets `409 ANALYSIS_IN_PROGRESS`, so two
callers can never both spend an LLM call and then interleave their writes.
A `processing` state older than `AI_SERVICE_LOCK_TTL_MS` (default 10 min) can be
taken over, so a process that dies mid-analysis does not strand a report
forever; both terminal writes are conditioned on the run still owning the lock,
so a superseded run cannot overwrite the newer one.

### `statusMessage` never holds PHI

Module 3 reserved that field on the condition that it never holds report text.
`safeStatusMessage` is a **table lookup on an error code**, not a formatted
error message — so an unrecognised failure degrades to a generic phrase rather
than leaking. The failure mode is loss of detail, which is the right direction.

Extracted parameters belong in Module 7's feature repository long-term, **not**
permanently on this document.

### Live end-to-end verification (real `ai-service`, real Gemini)

Run against a really-running Python service and a real Gemini key, with the
opt-in `tests/liveIntegration.test.js`. `analyze` → **200, `status: processed`,
version 1, extraction confidence 0.99, all six stages `ok`** (validation 12 ms,
rules 2110 ms, ML 2113 ms, report 2113 ms — the three concurrent stages
finishing within 3 ms of each other, which is what running them in parallel
looks like).

The generated clinical report contained:

- `overall.status` **`Needs Medical Attention`**, `risk` `High`, rule
  `abnormal_with_high_risk`, `any_assessed: true`, **`complete: false`** with a
  non-null caveat naming the gap — a genuine live *partial* assessment.
- **5 conditions**: `Diabetes` Indicated/High (critical), `Kidney Disease`
  **Insufficient Data / risk `null`**, and `Heart Disease`, `Obesity`,
  `Underweight` all Not Indicated/Low.
- Module 19's `prioritized[]` in the documented three tiers: the flagged High
  finding first, then the **unassessed** `Kidney Disease` (tier 1, `risk: null`,
  `priority: "Not Assessed"`), then the three settled normal findings — an
  unassessed condition ranked *above* every settled normal one, exactly as the
  spec section requires.
- 6 laboratory values, 11 catalogue-sourced recommendations, 13 evidence lines,
  `sources_failed: []`.
- Module 16's `fusion.fused[]` nested verbatim, 5 entries with their `sources`.
- **3 warnings, all with origins intact**, and two of the three came from
  origins that only the report stage carries: two `stage: "fusion"` (module 16)
  abstentions — *"Diabetes was assessed by Clinical Rule Engine but Random
  Forest could not assess it"* — and one `stage: "report"` (module 17)
  incompleteness warning. Before this change those would have been lost
  entirely, because no other stage in the chain carries them.

`hypertension` stayed **absent** from features, from `validation.valid` and from
`validation.rejected`: the tri-state survives all the way to the report.

### Known limitation of this seam

`ruleDecisions` / `mlDecisions` are produced by the standalone Module 8 and 9/10
calls, while the report's own `fusion` re-derives the same decisions inside
`/report/generate`. Random-forest `predict_proba` with `n_jobs=-1` can differ in
the last float bit between calls, so the two copies of an ML probability are
**not guaranteed bit-identical**. They are two runs of the same deterministic
model on the same input, not two different answers — but if a consumer ever
needs to quote one number, `clinicalReport.fusion` is the authoritative one for
anything the report says, and `mlDecisions` is the audit record of the
standalone stage. Collapsing the duplication would require the ai-service to
accept pre-computed decisions over HTTP; it does not today.

## Known limitations (logged, not yet addressed)

Honest inventory of accepted debt in this module:

- `passwordChangedAt` is backdated by 1 second, so an access token minted within
  that same second as a password change still validates.
- `normalizeEmail()` strips `+` subaddresses, so `a+x@gmail.com` and
  `a@gmail.com` collapse to one account.
- `jwt.verify` does not pin an `algorithms` allowlist.
- Mongoose `CastError` echoes the offending field name back to the caller.
- `GET /api/v1/health` is unauthenticated and reports database connectivity.
- Profile history is not versioned: an update overwrites the previous values, so
  there is no audit trail of what a patient's profile said at the time an older
  analysis ran.
- `PATCH` cannot clear an individual field (`null` is rejected as a type error);
  clearing requires a full `PUT` that omits the field.
- Profile writes are not rate-limited separately; only the auth surface is.
- **Module 3:** uploaded files are stored **unencrypted at rest**. Encryption is
  a deployment concern (disk/volume encryption) until a cloud adapter is added.
- **Module 3:** report metadata is not versioned and there is no audit log of
  who downloaded what and when — §19 would eventually want one.
- **Module 3:** the whole file is buffered in memory (bounded by
  `UPLOAD_MAX_BYTES`) rather than streamed to disk. This is what allows a
  rejected payload to never touch the filesystem, but it means raising the cap
  raises per-request memory use; a very large cap would want a streaming
  redesign with post-write validation.
- **Module 3:** interrupted deletes and crashed writes can leave unreferenced
  files (`.part` files, or blobs whose row was removed first). Nothing sweeps
  them yet.
- **Module 3:** magic-byte detection proves the *container* type, not that the
  file is a well-formed or benign PDF/JPEG/PNG. A malformed PDF that exploits a
  downstream parser is out of scope here; Module 4 must not assume the file is
  safe to hand to a native library.
- **Module 3:** there is no duplicate-upload rejection. `checksumSha256` is
  stored and indexed so a later module can implement one.
- **Module 3:** upload throttling keys on `req.ip` like the existing limiters,
  not on the authenticated user id, so it inherits the `TRUST_PROXY` caveat.
- **Module 3:** there is no per-user storage quota — one account can fill the
  disk one `UPLOAD_MAX_BYTES` file at a time, subject only to the rate limit.
- **Module 3 (audit D1, now fixed — listed because it was missing from this
  inventory):** a control character in a multipart `filename`, or a malformed
  multipart body, made **busboy** throw a plain `Error: Malformed part header`.
  With no `code`, no `type` and no `expose` it missed every branch of
  `normalizeError` and landed in the generic 500 branch — the wrong status code
  everywhere (a malformed multipart body is a 400), a stack trace naming
  `node_modules/busboy/…` outside production, and a `console.error(...)` per
  occurrence that any authenticated user could trigger on demand. Fixed
  structurally at the parser boundary in `middleware/upload.js` (every error
  multer surfaces is tagged before it propagates) plus a message-matching
  fallback in `errorHandler`. This was the **third** time an unmapped error class
  reached that branch, after Module 1's `entity.too.large` and this one; a
  mapped error now never carries a stack at any status code.
- **Analysis:** `POST /reports/:id/analyze` **blocks until extraction
  completes**. A happy-path extraction is ~20 s, but the ai-service's worst case
  with its shipped defaults is ~61 minutes, so a pathological multi-page scan
  can plausibly exceed any reasonable client timeout and will fail here while
  the Python side is still working (and still spending quota). A background job
  queue is the real answer and is deliberately **not** built yet. Meanwhile
  `AI_SERVICE_TIMEOUT_MS` (default 5 min) must be tuned **together with** the
  ai-service's `GEMINI_TIMEOUT_SECONDS` / `GEMINI_MAX_RETRIES`; its README
  recommends 45 / 2 (~15 min worst case).
- **Analysis:** one shared service secret with **no rotation window** — changing
  `AI_SERVICE_API_KEY` requires restarting both services together.
- **Analysis:** the ai-service has **no rate limiting of its own**, so any
  key-holder can drive unlimited Gemini spend. `ANALYSIS_RATE_LIMIT_MAX` on this
  side is the only budget control in the system, and like every other limiter it
  keys on `req.ip` and inherits the `TRUST_PROXY` caveat.
- **Analysis:** a retried extraction re-uploads and re-processes the whole file,
  so a transient failure costs a second full LLM call. `AI_SERVICE_RETRIES`
  defaults to 1 for that reason; 401/422 are never retried.
- **Analysis:** the results live on the `Report` document as an interim home.
  **Module 7** will formalise a Feature Repository; nothing here should be
  mistaken for one.
- **Analysis:** a failed run leaves `status: failed` even when a previous
  successful analysis is still retrievable. That is deliberate (status describes
  the latest attempt) but a client must read `analysis.version` to know whether
  a payload exists.
- **Analysis:** an ai-service 401 is byte-identical for a missing header, a
  wrong key, an empty key and a whitespace key, so a runtime 401 cannot tell an
  operator which it is. The backend logs its own ai-service configuration at
  startup (URL, key length — never the key) so the two can be distinguished.

## Project structure

```
backend/
  src/
    config/       env.js (validated config), database.js (Mongo connection)
    models/       User.js, Profile.js, Report.js
    middleware/   auth.js (protect, restrictTo), errorHandler.js,
                  validate.js, authValidators.js, profileValidators.js,
                  reportValidators.js, upload.js (multer), rateLimiter.js
    controllers/  authController.js, profileController.js, reportController.js,
                  analysisController.js (Modules 4-20 orchestration endpoints)
    services/     aiServiceClient.js (the ONLY place that knows the Python
                  service exists), analysisService.js (status lifecycle,
                  concurrency lock, profile payload, warning provenance,
                  the Module 18 overall-status summary)
    routes/       index.js (health, health/ai), authRoutes.js,
                  profileRoutes.js, reportRoutes.js
    storage/      StorageAdapter.js (interface), localDiskAdapter.js,
                  index.js (driver factory)
    utils/        jwt.js, ownership.js, fileSecurity.js, ApiError.js,
                  apiResponse.js, asyncHandler.js, roles.js
    app.js        Express app (middleware + routes), exported for tests
    server.js     DB connection, listen, graceful shutdown
  storage/        DEFAULT UPLOAD_ROOT - uploaded report files (gitignored,
                  never served statically, contains medical data)
  tests/          setup.js, helpers.js, auth.test.js, rateLimit.test.js,
                  ownership.test.js, profile.test.js,
                  ownershipHardening.test.js, reports.test.js,
                  reportRateLimit.test.js, analysis.test.js,
                  auditDefects.test.js (D1-D4 regressions),
                  liveIntegration.test.js (opt-in)
```

## Not in scope (future modules)

This codebase intentionally contains **nothing** beyond Modules 1, 2 and 3. The
following are separate modules and are **not** implemented here:

- **Modules 4 and 5** — OCR/extraction and feature engineering themselves live
  in the Python `ai-service/`. What is implemented here is the **client and the
  orchestration** around them (see *Analysis pipeline* above); no extraction or
  feature logic of any kind runs in this codebase.
- **Module 6** — feature validation.
- **Module 7** — the Feature Repository. The analysis results currently sit on
  the `Report` document as an interim home; Module 7 will formalise the store.
- **Modules 8–16** — Clinical rule engine, ML predictors (diabetes / heart /
  kidney), predictor registry, decision engine, hybrid fusion.
- **Modules 17–20** — Clinical report generation, risk assessment and
  prioritisation, explainability.
- **Modules 21–26** — RAG, medical knowledge base, LLM explanations, medical
  safety validation, terminology explainer, lifestyle guidance.
  The `GEMINI_API_KEY` / `GEMINI_MODEL` entries in `.env.example` are commented
  placeholders for this work and are **not read by any code in Modules 1–2**.
- **Modules 27–32** — Dashboard, trends, comparison, progress, population
  context, doctor summary; and the React frontend generally.
