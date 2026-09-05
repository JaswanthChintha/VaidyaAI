# VaidyaAI AI service — Module 4 (OCR & Extraction) + Module 5 (Feature Engineering)

A standalone **Python / FastAPI** service that

* **Module 4** — turns an uploaded laboratory report (PDF, JPEG or PNG) into
  **structured, machine-readable parameters**, and
* **Module 5** — turns those parameters (plus optional patient-profile
  context) into **canonical, unit-normalised medical features** with full
  provenance.

The service **transcribes and standardises**. It does not validate values
against physiologic ranges, store anything, or diagnose. Those are later
modules.

Jump to [Authentication](#authentication--service-to-service), the
[backend integration guide](#driving-this-service-as-a-pipeline-stage), or the
[Module 5 section](#module-5--medical-feature-engineering).

---

## What this module does

Per the project spec (Module 4), the pipeline stage is:

```
Upload Medical Report -> PDF / Image Processing -> OCR -> Text Extraction
                                                              |
                                                              v
                                                 Medical Feature Extraction  (Module 5)
```

Concretely:

| Step | Implementation |
|---|---|
| File intake | Type detected from **magic bytes**, not the extension. Size and page caps enforced. |
| PDF → image | **PyMuPDF** renders each page to PNG. Pure-Python wheel — no Poppler, no system binaries. |
| Image preprocessing | EXIF orientation, alpha flattened onto white, RGB conversion, resolution cap. |
| OCR + extraction | The page image goes to **Google Gemini vision**, which reads the layout and returns structured fields in one step. |
| Response validation | The model's JSON is validated into a strict **pydantic v2** schema before it leaves the service. |
| Reporting | Per-row and overall confidence, plus a `warnings[]` channel for the downstream pipeline. |

### Why Gemini vision instead of Tesseract

A deliberate architectural choice:

- Classical OCR returns a flat character stream, so multi-column lab tables
  have to be reassembled with brittle geometry heuristics. Gemini reads the
  table structure directly and returns the row's fields already associated.
- No native binaries to install on Windows.
- The vision model handles skew, faint print and scan noise better than a
  fixed threshold/denoise pipeline, which is why preprocessing here is
  deliberately light.

---

## Setup

Requires **Python 3.10+**.

```bash
cd ai-service

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

cp .env.example .env        # then fill in the two required secrets
```

Two secrets are required:

* `GEMINI_API_KEY` — get one at <https://aistudio.google.com/apikey>.
* `AI_SERVICE_API_KEY` — the shared secret the Node backend presents. **The
  service refuses to start without it.** Generate one:

  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(48))"
  ```

Run it:

```bash
uvicorn app.main:app --reload --port 8001
```

- Interactive docs: <http://localhost:8001/docs>
- Health: <http://localhost:8001/api/v1/health> (the only unauthenticated route)

Quick check:

```bash
curl -X POST http://localhost:8001/api/v1/ocr/extract \
  -H "X-Service-Key: $AI_SERVICE_API_KEY" \
  -H "X-Request-Id: 68b1f0c2a4d9e7b3c1a2f4d6" \
  -F "file=@/path/to/report.pdf"
```

---

## Authentication — service to service

This service processes protected health information. Spec §19 requires
protected APIs and least privilege, and the only legitimate caller is the Node
`backend/`, so the protection is a **shared secret**, not a user session.

**The contract, verbatim — the backend must implement exactly this:**

| | |
|---|---|
| Env var (both services) | **`AI_SERVICE_API_KEY`** |
| Request header | **`X-Service-Key: <the secret>`** |
| Protected | `POST /api/v1/ocr/extract`, `POST /api/v1/features/engineer`, `GET /api/v1/features/catalog` |
| Unauthenticated | `GET /api/v1/health` (so the backend can health-check before it holds a key), and `GET /` |
| Rejection | **HTTP 401**, body `{"success": false, "error": {"code": "UNAUTHORIZED", "message": "..."}}` |
| Minimum key length | 32 characters (`MIN_SERVICE_KEY_LENGTH`) |

### Failure modes

A **missing header**, a **wrong key**, an **empty key** and a **whitespace-only
key** are all rejected identically: the same 401, the same single error code,
the same fixed message, and the same amount of work. There is exactly one
`UNAUTHORIZED` code — nothing tells a prober which check failed.

The comparison runs over **SHA-256 digests of both sides** via
`hmac.compare_digest`, so it is fixed-length constant time: neither the secret
nor its *length* is recoverable by timing. `hmac.compare_digest` on the raw
strings would short-circuit on a length mismatch, so the hashing step is
load-bearing, not decorative.

Leading/trailing whitespace on an otherwise-correct header value is tolerated
(a stray space is not a different secret). Nothing else is.

### Fail closed

**An unset `AI_SERVICE_API_KEY` never means "open".** At import time,
`app/main.py` calls `enforce_service_auth_configuration()`, which raises and
aborts `uvicorn app.main:app` with a `REFUSING TO START:` message when the key
is unset, blank, whitespace-only, or shorter than 32 characters.

There is **one** escape hatch, for local development only:

```bash
ALLOW_UNAUTHENTICATED=true
```

It must be set deliberately (`false`, `0`, `no` and garbage all still refuse to
start), and it prints a `SECURITY WARNING` banner on **every** startup saying
the service is accepting unauthenticated requests. **If
`AI_SERVICE_API_KEY` is also set, the key wins and the flag does nothing** — the
hatch can only ever open a service that has no key, never disable one that has.

### What is never logged or disclosed

The secret is a pydantic `SecretStr`, so it is redacted from `repr()`. It never
appears in a log line, an error body, or the health payload — not the value,
not a prefix, not a hash. The rejection log line is
`service_auth_rejected {request_id, path, method}` and nothing else. Tests
assert all of this, including that the presented key is not echoed back.

`GET /api/v1/health` is open, so it was audited: it returns only `status`,
`service`, `module`, `environment`, `model`, `model_configured` (a **bool** —
whether a Gemini key is set, never the key), `prompt_version` and `limits`. No
PHI, no secret, and deliberately **no** indication of whether authentication is
enabled — that would be a probe oracle. The escape hatch is surfaced through
the startup banner instead.

---

## Environment variables

`GEMINI_API_KEY` and `AI_SERVICE_API_KEY` are required. See `.env.example`.

| Variable | Default | Purpose |
|---|---|---|
| `AI_SERVICE_API_KEY` | *(required)* | Shared secret for the `X-Service-Key` header. **Service refuses to start if unset.** Never logged. |
| `ALLOW_UNAUTHENTICATED` | `false` | **Local dev escape hatch.** Starts the service with no auth; warns loudly every startup. Ignored when a key is set. |
| `MIN_SERVICE_KEY_LENGTH` | `32` | Minimum accepted length of the shared secret. |
| `GEMINI_API_KEY` | *(required)* | Google AI Studio key. Never logged. |
| `GEMINI_MODEL` | `gemini-3.6-flash` | Vision model used for extraction. |
| `GEMINI_TIMEOUT_SECONDS` | `120` | Per-request timeout. |
| `GEMINI_MAX_RETRIES` | `3` | Attempts for transient failures (exponential backoff + jitter). |
| `GEMINI_TEMPERATURE` | `0.0` | Low, for extraction determinism. |
| `GEMINI_MAX_OUTPUT_TOKENS` | `32768` | Truncation guard. |
| `MAX_FILE_SIZE_BYTES` | `15728640` (15 MB) | Upload cap, enforced during the read. |
| `MAX_PAGE_COUNT` | `10` | Page cap. |
| `PDF_RENDER_DPI` | `200` | PDF rasterisation DPI. |
| `MAX_IMAGE_EDGE_PIXELS` | `2200` | Longest-edge cap on images sent to the model. |
| `LOW_CONFIDENCE_THRESHOLD` | `0.6` | At or below this, a warning is added. |
| `CORS_ALLOW_ORIGINS` | *(empty)* | Comma-separated **browser** origins. Empty = none. See below. |
| `LOG_LEVEL` | `INFO` | |

### CORS

Default is **empty — no browser origin is allowed**, changed from the previous
`*`. This is correct and needs no widening: the Node backend is a *server-side*
caller, and the browser same-origin policy does not apply to server-to-server
HTTP, so CORS is simply irrelevant to the one legitimate client. The only thing
a permissive `CORS_ALLOW_ORIGINS` would enable is a browser calling this
service directly — which must never happen, because that browser would have to
be holding `AI_SERVICE_API_KEY`.

CORS is a browser convention, not an access control. It is `X-Service-Key` that
protects the endpoints.

---

## Driving this service as a pipeline stage

The backend calls Module 4 and then Module 5 in sequence for one stored report.

```
backend ──POST /api/v1/ocr/extract────────► {"success": true, "data": {...}}
        │                                                    │
        │            unwrap `data`, put it under `extraction` │
        ▼                                                    ▼
backend ──POST /api/v1/features/engineer──► {"success": true, "data": {...}}
```

Every call carries `X-Service-Key` and `X-Request-Id`.

### The exact body to POST to `/api/v1/features/engineer`

Module 4 returns `{"success": true, "data": {...}}`. The features endpoint
takes the extraction under an `extraction` key. **The canonical form — send
this:**

```json
{
  "extraction": { "...Module 4's `data` object, verbatim..." },
  "profile":    { "age": 45, "gender": "male", "bmi": 27.4,
                  "hypertension": true, "heartDisease": false,
                  "smokingHistory": "never" }
}
```

In Node:

```js
const { data } = (await axios.post(`${AI}/api/v1/ocr/extract`, form, {
  headers: { 'X-Service-Key': KEY, 'X-Request-Id': reportId, ...form.getHeaders() },
})).data;                                     // <- unwrap the envelope

const features = (await axios.post(`${AI}/api/v1/features/engineer`,
  { extraction: data, profile },              // <- `data` goes under `extraction`
  { headers: { 'X-Service-Key': KEY, 'X-Request-Id': reportId } },
)).data.data;
```

**Two other forms are also accepted**, so a mismatch here cannot silently break
the pipeline:

| Body | Behaviour |
|---|---|
| `{"extraction": {...}, "profile": {...}}` | **Canonical.** Use this. |
| `{"success": true, "data": {...}, "profile": {...}}` | Module 4's response relayed verbatim; `data` is used as the extraction. |
| `{"extracted_parameters": [...], ...}` | A bare Module 4 `data` object at the top level. No place for `profile`. |

Precedence: an explicit `extraction` key **always wins**. Without it, a body
carrying **both** `data` and a top-level `extracted_parameters` is **rejected
with 422 as ambiguous** rather than guessed at. Validation is not weakened —
whichever object is selected is validated against the Module 4 contract exactly
as before, so a row missing `test_name` is still a 422 in all three forms.

> **Why this matters.** Before this was added, posting Module 4's response
> envelope straight through was *silently accepted* and produced an **empty
> feature set** — a 200 with `features: {}`. A pipeline wired that way would
> have looked healthy and produced nothing.

### Correlation id — `X-Request-Id`

Send an **opaque** identifier (the Mongo report id). The service echoes it on
the response — success and error alike, including 401s — and stamps it on every
log line it writes, so a failure can be matched across both services.

* Absent, or unusable → the service generates one and returns that.
* **It must never contain PHI.** The service cannot detect PHI, so it enforces
  the next best thing: `[A-Za-z0-9._:-]`, 1–128 characters. Anything else —
  a space, an `@`, a newline, an ANSI escape, an over-long value — is
  **discarded** and replaced with a generated id, rather than logged as sent.
  That charset also makes log and header injection impossible. Send an
  ObjectId or a UUID; never a patient name, an email or a filename.

### Timeouts — worst case

Every Gemini call is bounded by `GEMINI_TIMEOUT_SECONDS`. A slow model cannot
hang the backend indefinitely, but the bound is per attempt per page:

```
worst case = (GEMINI_MAX_RETRIES × GEMINI_TIMEOUT_SECONDS + backoff) × MAX_PAGE_COUNT
backoff    = Σ  GEMINI_RETRY_BASE_DELAY_SECONDS × 2ⁿ × 1.25   (n = 0 … retries-2)
```

**With the shipped defaults (3 × 120 s + 3.75 s) × 10 pages = 3 637.5 s ≈ 61
minutes.** That is the number `Settings.worst_case_extraction_seconds`
computes, and it is unit-tested.

A typical single-page extraction was measured at **~20 s** live.

The 61-minute figure is a genuine bound, not a comfortable one. Recommended for
a real deployment:

| Setting | Suggested | Worst case |
|---|---|---|
| Defaults | — | 3 637.5 s (~61 min) |
| `GEMINI_TIMEOUT_SECONDS=45`, `GEMINI_MAX_RETRIES=2` | typical | 912.5 s (~15 min) |
| …plus `MAX_PAGE_COUNT=5` | tight | 456.25 s (~8 min) |

**The backend's HTTP client timeout must be set above whichever value it
configures**, or the backend will give up on a request the service is still
working on. `/api/v1/features/engineer` is pure CPU with no upstream call and
returns in milliseconds; only `/ocr/extract` needs a long timeout.

---

## API

### `GET /api/v1/health`

**Unauthenticated** — the backend health-checks it. Liveness plus configuration
readiness. Reports **whether** a Gemini key is configured (`model_configured`),
never the key itself, and discloses nothing about the service key or whether
authentication is enabled.

### `POST /api/v1/ocr/extract`

**Requires `X-Service-Key`.** `multipart/form-data` with a single `file` field.
Accepts PDF, JPEG, PNG.

#### Output contract — binding

**Module 5 consumes this shape. Do not change it without coordinating.**

```json
{
  "success": true,
  "data": {
    "source": {
      "filename": "report.pdf",
      "mime_type": "application/pdf",
      "page_count": 2,
      "size_bytes": 12345
    },
    "raw_text": "full text as read from the document",
    "pages": [ { "page_number": 1, "raw_text": "..." } ],
    "extracted_parameters": [
      {
        "test_name": "HbA1c",
        "value_raw": "6.8",
        "value_numeric": 6.8,
        "unit": "%",
        "reference_range_raw": "4.0 - 5.6",
        "reference_low": 4.0,
        "reference_high": 5.6,
        "flag": "high",
        "page_number": 1,
        "confidence": 0.94
      }
    ],
    "report_metadata": {
      "lab_name": null,
      "report_date": null,
      "patient_name_present": true
    },
    "extraction_confidence": 0.91,
    "warnings": []
  }
}
```

**Contract rules**

- `test_name` is the name **exactly as printed on the report**. It is *not*
  normalised to a canonical feature name — Module 5 does that. Expect
  `"HbA1c (Glycated Haemoglobin)"`, not `"hba1c"`.
- `value_numeric` is `null` for non-numeric results (`"Negative"`, `"Trace"`).
  `value_raw` always preserves what was printed.
- `flag` is `"low" | "normal" | "high" | "critical" | null`, set only when the
  report itself indicates it or the reference range makes it unambiguous.
  **No clinical inference happens at this stage.**
- Every field is nullable except `test_name` and `value_raw`. Missing
  information is `null` — **never invented**.
- Nulls are **emitted, not omitted**, so downstream code can read keys directly.
- `page_number` is stamped by the service, never taken from the model.
- `warnings[]` carries anything downstream should know: low confidence,
  unreadable regions, ambiguous units, suspected multi-patient documents,
  recovered/damaged files, skipped pages.

#### Errors

Every failure returns the same envelope with a meaningful status:

```json
{ "success": false, "error": { "code": "UNSUPPORTED_FILE_TYPE", "message": "..." } }
```

| HTTP | Codes |
|---|---|
| 401 | `UNAUTHORIZED` (missing / wrong / empty / whitespace `X-Service-Key`) |
| 400 | `EMPTY_FILE`, `TOO_MANY_PAGES` |
| 413 | `FILE_TOO_LARGE` |
| 415 | `UNSUPPORTED_FILE_TYPE` |
| 422 | `NO_FILE`, `CORRUPT_FILE`, `ENCRYPTED_PDF`, `NO_RENDERABLE_PAGES` |
| 429 | `MODEL_RATE_LIMITED` |
| 502 | `MODEL_REQUEST_FAILED`, `MODEL_RESPONSE_MALFORMED`, `MODEL_RESPONSE_TRUNCATED`, `MODEL_RESPONSE_BLOCKED`, `MODEL_RESPONSE_EMPTY` |
| 503 | `MODEL_NOT_CONFIGURED`, `MODEL_UNAVAILABLE` |
| 504 | `MODEL_TIMEOUT` |
| 500 | `INTERNAL_ERROR` |

**Partial degradation:** if one page of a multi-page document fails, the
request still returns `200` with that page's `raw_text` as `null` and a
warning naming it. Only when *every* page fails does the request return `502`.

---

## Medical data handling

This service processes protected health information.

- **Nothing sensitive is ever logged** — not file bytes, not transcribed text,
  not extracted values, not patient identifiers, not the API key. Only
  operational metadata (mime type, byte size, page count, duration, error
  code, counts). `app/core/logging.py` enforces this via `safe_meta()`, and
  the SDK's HTTP loggers are pinned to `WARNING` so request bodies cannot leak
  through them.
- **The patient's name is never extracted.** `report_metadata` reports only
  `patient_name_present: true|false`.
- The API key is held as a pydantic `SecretStr`, so it is redacted from
  `repr()` and never appears in an error message returned to a caller.
- Upstream SDK error text is not echoed to callers — it can embed request
  fragments. Errors are mapped to stable generic messages.
- No document is written to disk; processing is entirely in memory.
- There is **no database** in this module — nothing is persisted.

---

## Tests

```bash
pytest
```

The suite passes with **no `GEMINI_API_KEY` and no network** — the Gemini
client is mocked throughout, and `tests/conftest.py` strips any real key from
the environment so a developer's own credentials can never make a test pass
that would otherwise fail.

Coverage: content-based type sniffing (including extension spoofing and
hostile payloads), size and page caps, PDF rendering, corrupt/truncated/
encrypted/zero-page documents, image normalisation, the full response
contract, non-numeric null handling, flag normalisation, malformed and
truncated model responses, Gemini timeout / rate-limit / server-error /
safety-block / empty-response paths, retry and backoff behaviour, PHI
log-leak canaries, and the health endpoint.

**Module 5** adds: every synonym in the table (each in four case/punctuation
variants), every unit conversion in **both** directions against hand-verified
arithmetic, unrecognised-unit handling, unmapped-test preservation, the
specimen and lipid-subfraction guards, non-numeric and censored values,
thousands separators, every branch of the duplicate-resolution rank, missing
and null fields throughout, the patient-profile merge including **tri-state
boolean preservation (absent != false)**, provenance completeness, empty
input, determinism, and an end-to-end test that feeds the **actual observed
Module 4 output** (HbA1c 6.8 %, Fasting Blood Glucose 112 mg/dL, Haemoglobin
14.2 g/dL, Creatinine 1.0 mg/dL, Total Cholesterol 190 mg/dL, Vitamin D
(25-OH) 35 ng/mL, Urine Ketones "Negative") and asserts the resulting
canonical feature set.

**Pipeline and security** add: warnings crossing the Module 4 → 5 boundary with
their origin preserved, every other field carried forward (confidence, report
metadata, source, per-page readability), a canary proving `raw_text` is *not*
carried, all three accepted request shapes plus the ambiguous-body rejection,
an end-to-end extract-then-engineer run, correlation-id echo on success / 422 /
401 and its presence in log lines, hostile correlation ids (spaces, `@`, CRLF,
ANSI escapes, over-length) being discarded rather than logged, the worst-case
timeout arithmetic, the shared-secret comparison, 401 for a missing / wrong /
empty / whitespace / truncated / extended / wrong-case key with byte-identical
bodies, health reachable without auth and disclosing nothing, a route-coverage
test that fails if a future `/api/v1` route is added without the auth
dependency, and — in a **real subprocess** — startup being refused when the key
is unset, blank or too short, the escape hatch starting the service with a loud
banner, and non-truthy hatch values still refusing.

Current totals: **803 passed, 2 skipped** (194 of those are Module 4's
pre-existing suite and 502 Module 5's, both unchanged; 107 are new).

The suite runs under `ALLOW_UNAUTHENTICATED=true`, set in `tests/conftest.py`
*before* any `app` module is imported (the service fails closed at import).
Tests that exercise authentication build their own clients with an explicit key
via the `authed_client_factory` fixture.

The synthetic lab report fixture is **generated at test time with PyMuPDF**
(`tests/conftest.py`) from invented values for a fictional laboratory. **No
real medical data is used anywhere in this repository.**

### Opt-in live test

Skipped by default. It hits the real API with the synthetic fixture:

```bash
# Windows PowerShell
$env:RUN_LIVE_TESTS=1; pytest tests/test_live_gemini.py -v -s

# bash
RUN_LIVE_TESTS=1 pytest tests/test_live_gemini.py -v -s
```

It requires `RUN_LIVE_TESTS=1` **and** a real `GEMINI_API_KEY`. It verifies
that the configured `GEMINI_MODEL` exists in the live model list, and that a
real extraction round-trip satisfies the contract.

---

# Module 5 — Medical Feature Engineering

Converts Module 4's `extracted_parameters[]` (plus optional Module 2 patient
profile context) into a **canonical, unit-normalised feature set with full
provenance**.

> **The Module 5 / Module 6 line.**
> Module 5 answers *"what feature is this, and in what canonical unit?"*
> Module 6 answers *"is this value believable?"*
> Module 5 emits warnings where it is uncertain. It **never rejects a value as
> implausible** and never applies a range check.

## Endpoint

### `POST /api/v1/features/engineer`

Request (`application/json`):

```json
{
  "extraction": { "extracted_parameters": [ "...Module 4 rows..." ] },
  "profile": {
    "age": 45, "gender": "male", "bmi": 27.4,
    "hypertension": true, "heartDisease": false, "smokingHistory": "never"
  }
}
```

**Requires `X-Service-Key`.**

`extraction` accepts **Module 4's `data` object verbatim**. `source`, `pages`,
`report_metadata`, `extraction_confidence` and `warnings` are **parsed and
carried forward** (see below); `raw_text` is deliberately dropped. `profile` is
optional and accepts both camelCase (Module 2's Node representation) and
snake_case keys. Two alternative body shapes are also accepted — see
[the exact body to POST](#the-exact-body-to-post-to-apiv1featuresengineer).

Response — **binding for Modules 6, 7 and 20**:

```json
{ "success": true, "data": {
  "features": {
    "hba1c": {
      "name": "hba1c",
      "value": 6.8,
      "unit": "%",
      "canonical_unit": true,
      "source": "lab_report",
      "provenance": {
        "source": "lab_report",
        "original_test_name": "HbA1c",
        "original_value_raw": "6.8",
        "original_value_numeric": 6.8,
        "original_unit": "%",
        "normalized_unit": "%",
        "matched_synonym": "HbA1c",
        "parameter_index": 0,
        "page_number": 1,
        "confidence": 0.94,
        "reference_range_raw": "4.0 - 5.6",
        "reference_low": 4.0,
        "reference_high": 5.6,
        "flag": "high",
        "unit_converted": false,
        "unit_assumed": false,
        "unit_recognised": true,
        "conversion": null,
        "censored": null,
        "derived": null,
        "notes": []
      }
    }
  },
  "unmapped": [
    { "test_name": "Urine Ketones", "value_raw": "Negative", "unit": null,
      "reason": "non_numeric_value", "source": "lab_report",
      "parameter_index": 6, "page_number": 1, "confidence": 0.9,
      "detail": "..." }
  ],
  "conversions_applied": [
    { "feature": "creatinine", "original_test_name": "Creatinine",
      "original_value": 88.4017, "original_unit": "µmol/L",
      "canonical_value": 1.0, "canonical_unit": "mg/dl",
      "factor": 0.011312, "offset": 0.0,
      "formula": "mg/dl = umol/l x 0.011312" }
  ],
  "duplicates_resolved": [
    { "feature": "blood_glucose", "policy": "deterministic_rank: ...",
      "chosen": { "test_name": "Fasting Blood Glucose" },
      "discarded": [ { "test_name": "PPBS" } ] }
  ],
  "missing_features": ["vitamin_b12", "triglycerides", "heart_disease"],

  "warnings": ["...raised by Module 5 itself..."],
  "upstream_warnings": [
    { "stage": "extraction", "module": 4,
      "message": "page 1 was recovered by the PDF repairer" }
  ],
  "all_warnings": [
    { "stage": "extraction", "module": 4, "message": "..." },
    { "stage": "feature_engineering", "module": 5, "message": "..." }
  ],
  "upstream": {
    "stage": "extraction", "module": 4, "provided": true,
    "source": { "filename": "report.pdf", "mime_type": "application/pdf",
                "page_count": 2, "size_bytes": 20481 },
    "report_metadata": { "lab_name": "Northfield Diagnostic Laboratory",
                         "report_date": "12/03/2024",
                         "patient_name_present": true },
    "extraction_confidence": 0.87,
    "pages": [ { "page_number": 1, "raw_text_available": true },
               { "page_number": 2, "raw_text_available": false } ],
    "pages_unreadable": [2],
    "warning_count": 2
  },

  "summary": { "feature_count": 11, "lab_feature_count": 6,
               "profile_feature_count": 5, "unmapped_count": 2,
               "conversion_count": 1, "duplicate_count": 1,
               "parameters_received": 7, "profile_provided": true,
               "upstream_warning_count": 2, "pages_unreadable_count": 1 }
} }
```

### Carrying Module 4 forward — warnings and provenance

**Binding, and part of the Module 4 → 5 contract.**

Module 4's warnings are the *only* signal that MuPDF silently repaired a
damaged PDF, or that one page of a multi-page scan could not be read (that page
comes back with `raw_text: null` plus a warning naming it — Module 4's
deliberate partial-degradation behaviour). Spec Module 17 requires validation
warnings to reach the final report metadata.

If those warnings are dropped, **a report built from a partially unreadable
scan becomes indistinguishable from one built from a clean scan**, and a lab
row that is missing *because a page could not be read* silently reads as "that
test was not performed". Module 5 therefore carries them forward, with their
origin preserved.

| Key | Contains |
|---|---|
| `warnings[]` | Plain strings. Warnings **Module 5 itself** raised: assumed units, unrecognised units, censored values, duplicate resolutions, profile categories. Unchanged from before. |
| `upstream_warnings[]` | `{stage, module, message}`. Warnings **received from Module 4**, relayed **verbatim** — never edited, filtered, deduplicated or reordered. |
| `all_warnings[]` | `{stage, module, message}`. **Every** warning from both stages, **upstream first**, each tagged with its origin. **This is the list Module 6 and the final report should consume.** |
| `upstream{}` | Module 4's `source`, `report_metadata`, `extraction_confidence`, per-page readability and warning count. |

`stage` is `"extraction"` (module `4`) or `"feature_engineering"` (module `5`).
The two lists are kept **separate rather than merged** precisely so origin is
never lost: a Module 4 warning is about *reading the document* and a Module 5
warning is about *interpreting a row*, and they are actionable by different
people. `all_warnings` is the convenience view, still origin-tagged.

**What else survives the boundary:**

* `upstream.extraction_confidence` — how confident Module 4 was overall.
* `upstream.report_metadata` — `lab_name`, `report_date`, and
  `patient_name_present` (presence only; the name itself is never extracted by
  Module 4 and never carried here).
* `upstream.source` — `filename`, `mime_type`, `page_count`, `size_bytes`.
* `upstream.pages[]` — `{page_number, raw_text_available}`, plus the shortcut
  `upstream.pages_unreadable[]`. **`raw_text_available: false` means Module 4
  could not read that page.** A non-empty `pages_unreadable` means the feature
  set was built from a partially unreadable document.
* `upstream.provided` — `false` when the caller sent only
  `extracted_parameters` with no surrounding extraction context.

**Deliberately NOT carried:** `raw_text` and per-page `raw_text`. That is the
full transcribed report — bulk PHI — and no consumer of a feature set needs it.
The safety-critical fact (*which* pages were unreadable) is carried as a boolean
per page instead of the text itself.

Module 5 does not *interpret* any of this; it relays it. Deciding what a low
`extraction_confidence` or an unreadable page means is Module 6's job.

**Contract rules**

* `features` is keyed by canonical feature name. A feature that could not be
  produced is **absent** — never present with a fabricated value, never
  defaulted to `false`/`0`.
* `missing_features` lists every canonical feature with no value. For
  `hypertension` and `heart_disease` this means **UNKNOWN, not false.**
* **`canonical_unit: false` means `value` is NOT in the canonical unit.**
  Consumers must check it before using the number.
* `unmapped[]` preserves every extracted row that did not become a feature —
  nothing is silently dropped.
* `provenance.parameter_index` is the index into the submitted
  `extracted_parameters[]` array. Module 20 (Explainability) uses it to point
  a user at the exact report line behind each feature.
* Errors use the service-wide envelope:
  `{"success": false, "error": {"code": "INVALID_REQUEST", "message": "..."}}`
  with HTTP 422. Submitted values are never echoed back.

### `GET /api/v1/features/catalog`

**Requires `X-Service-Key`.** Machine-readable description of the canonical feature space: every feature,
its canonical unit, value type, source, accepted units and the duplicate
policy. Useful for Module 6/7 and for clinical review.

### Direct import (no HTTP)

```python
from app.services.feature_engineer import engineer_features, engineer_from_extraction

# PREFERRED -- carries Module 4's warnings and provenance forward.
data = engineer_from_extraction(module4_data_object, profile)

# Rows only. `upstream.provided` is False and upstream_warnings is empty.
data = engineer_features(extracted_parameters, profile)     # both may be dicts

# Equivalent to engineer_from_extraction:
data = engineer_features(None, profile, extraction=module4_data_object)
```

`engineer_features` is a plain function — no FastAPI, no I/O, no global state,
deterministic. Module 7 and the ML layer call it directly. It raises
`pydantic.ValidationError` if the input violates the Module 4 / Module 2
contracts.

---

## Canonical feature table

| Feature | Canonical unit | Type | Source |
|---|---|---|---|
| `hba1c` | `%` (NGSP) | number | lab report |
| `blood_glucose` | `mg/dl` | number | lab report |
| `hemoglobin` | `g/dl` | number | lab report |
| `vitamin_d` | `ng/ml` | number | lab report |
| `vitamin_b12` | `pg/ml` | number | lab report |
| `creatinine` | `mg/dl` | number | lab report |
| `cholesterol` (**total**) | `mg/dl` | number | lab report |
| `triglycerides` | `mg/dl` | number | lab report |
| `bmi` | `kg/m2` | number | patient profile |
| `age` | `years` | integer | patient profile |
| `hypertension` | — | boolean, **tri-state** | patient profile |
| `heart_disease` | — | boolean, **tri-state** | patient profile |
| `smoking_history` | — | category | patient profile |
| `gender` | — | category | patient profile |

`gender` is not in the spec's 13-item list but is stored by Module 2 and
consumed by Module 11 (heart-disease predictor), so it is carried here rather
than translated later.

Profile categories (exactly Module 2's vocabularies):

* `smoking_history`: `never | former | current | ever | not_current | no_info`
* `gender`: `male | female | other | prefer_not_to_say`

---

## Synonym table

Source of truth: **`app/data/feature_catalog.py`** — a data-only module so a
clinician can audit it without reading Python control flow. Matching is
case-, punctuation-, hyphen-, accent- and spelling-insensitive
(`Haemoglobin` → `hemoglobin`), strips parentheticals (`Vitamin D (25-OH)`),
and strips leading/trailing method qualifiers (`serum`, `plasma`, `level`,
`test`, `assay`, `HPLC`, `CLIA`, …).

| Feature | Accepted printed names |
|---|---|
| `hba1c` | HbA1c · Hb A1c · HbA1C% · A1c · HgbA1c · Hgb A1c · Haemoglobin A1c · Hemoglobin A1c · Glycated Haemoglobin · Glycated Hemoglobin · Glycosylated Haemoglobin · Glycosylated Hemoglobin · Glycated Hb · Glycosylated Hb · Glycohemoglobin · Glycohaemoglobin · HbA1c (Glycated Haemoglobin) · Glycated Haemoglobin (HbA1c) · HbA1c NGSP · Average Blood Glucose HbA1c |
| `blood_glucose` | Glucose · Blood Glucose · Blood Sugar · Serum Glucose · Plasma Glucose · Sugar · Glucose Blood · **Fasting**: Fasting Blood Glucose · Fasting Blood Sugar · Fasting Plasma Glucose · Fasting Glucose · Glucose Fasting · FBS · FPG · Blood Sugar Fasting · **Random**: Random Blood Sugar · Random Blood Glucose · Random Glucose · RBS · Blood Sugar Random · **Post-prandial**: Postprandial Blood Sugar · Post Prandial Blood Sugar · Post Prandial Glucose · Postprandial Glucose · PPBS · PP Blood Sugar · Glucose PP · 2 Hour Postprandial Glucose · Blood Sugar Post Prandial |
| `hemoglobin` | Hemoglobin · Haemoglobin · Hb · Hgb · HGB · Total Hemoglobin · Total Haemoglobin · Hemoglobin (Hb) · Haemoglobin (Hb) · Blood Hemoglobin |
| `vitamin_d` | Vitamin D · Vitamin D3 · Vitamin D (25-OH) · 25-OH Vitamin D · 25 OH Vitamin D3 · 25-Hydroxy Vitamin D · 25-Hydroxyvitamin D · 25-OHD · Vitamin D Total · Total 25-Hydroxyvitamin D · Vit D · Vit D3 · Vitamin D 25 Hydroxy · 25 Hydroxycholecalciferol · Calcidiol |
| `vitamin_b12` | Vitamin B12 · Vitamin B-12 · Vit B12 · B12 · Vitamin B 12 · Cobalamin · Cyanocobalamin · Vitamin B12 (Cobalamin) · Serum Vitamin B12 |
| `creatinine` | Creatinine · Serum Creatinine · Creatinine Serum · S. Creatinine · Creat · Blood Creatinine · Creatinine (Jaffe) · Plasma Creatinine |
| `cholesterol` | Cholesterol · Total Cholesterol · Cholesterol Total · Serum Cholesterol · Total Cholesterol Serum · T. Cholesterol · Chol · TC · Cholesterol (Total) |
| `triglycerides` | Triglycerides · Triglyceride · Serum Triglycerides · Triglycerides Serum · TG · TGL · Trig · Triglycerides (TG) |

Because normalisation folds British to American spelling, the two spellings of
a term share one table entry; `provenance.matched_synonym` reports the entry
(e.g. `Glycated Hemoglobin`) while `provenance.original_test_name` always
preserves what was printed.

### Deliberate non-matches (safety guards)

| Printed name contains | Result | Why |
|---|---|---|
| `urine`, `urinary`, `csf`, `saliva`, `stool`, `sputum`, `synovial`, `pleural`, `ascitic`, `amniotic`, `dialysate`, `semen`, `sweat`, `faecal`/`fecal` | `unsupported_specimen` | A urine creatinine is **not** a serum creatinine |
| `hdl`, `ldl`, `vldl`, `idl`, `chylomicron` | `distinct_analyte` | `cholesterol` means **total** cholesterol |
| anything else unrecognised | `no_canonical_feature` | Never guessed; preserved in `unmapped[]` |

---

## Unit conversions

Source of truth: **`app/data/unit_conversions.py`**. Every conversion is
affine — `canonical = raw × factor + offset` — and every factor is derived
from a documented molar mass or decimal prefix. Each one is unit-tested in
**both** directions against hand-verified values.

| Feature | From | To (canonical) | factor | offset | Basis / inverse |
|---|---|---|---|---|---|
| `hba1c` | `%` | `%` | 1 | 0 | identity |
| `hba1c` | `mmol/mol` (IFCC) | `%` (NGSP) | **0.09148** | **2.152** | NGSP/IFCC master equation. **Affine, not a ratio.** 48 → 6.543 % · inverse `IFCC = (% − 2.152) / 0.09148` |
| `blood_glucose` | `mg/dl` | `mg/dl` | 1 | 0 | identity |
| `blood_glucose` | `mmol/l` | `mg/dl` | **18.0156** | 0 | MW glucose 180.156 g/mol ÷ 10 · inverse ×0.05551 · 5.5 → 99.09 |
| `blood_glucose` | `g/l` | `mg/dl` | 100 | 0 | decimal prefix · inverse ×0.01 |
| `blood_glucose` | `mg/l` | `mg/dl` | 0.1 | 0 | decimal prefix · inverse ×10 |
| `hemoglobin` | `g/dl` | `g/dl` | 1 | 0 | identity |
| `hemoglobin` | `g/l` | `g/dl` | 0.1 | 0 | decimal prefix · 142 → 14.2 |
| `hemoglobin` | `mmol/l` | `g/dl` | **1.61145** | 0 | MW Hb per heme 16114.5 g/mol ÷ 10000 · inverse ×0.6206 · 8.8 → 14.18 |
| `vitamin_d` | `ng/ml` | `ng/ml` | 1 | 0 | identity |
| `vitamin_d` | `ug/l` (`µg/L`, `mcg/L`) | `ng/ml` | 1 | 0 | identical magnitude |
| `vitamin_d` | `nmol/l` | `ng/ml` | **0.400641** | 0 | MW 25-OH-D 400.64 g/mol · **inverse ×2.496** · 75 → 30.05 |
| `vitamin_b12` | `pg/ml` | `pg/ml` | 1 | 0 | identity |
| `vitamin_b12` | `ng/l` | `pg/ml` | 1 | 0 | identical magnitude |
| `vitamin_b12` | `pmol/l` | `pg/ml` | **1.35537** | 0 | MW cobalamin 1355.37 g/mol · **inverse ×0.7378** · 300 → 406.6 |
| `creatinine` | `mg/dl` | `mg/dl` | 1 | 0 | identity |
| `creatinine` | `umol/l` (`µmol/L`, `mcmol/L`) | `mg/dl` | **0.011312** | 0 | MW creatinine 113.12 g/mol · **inverse ×88.4017** · 88.4 → 1.00 |
| `creatinine` | `mmol/l` | `mg/dl` | 11.312 | 0 | 1000× the µmol/L factor |
| `creatinine` | `mg/l` | `mg/dl` | 0.1 | 0 | decimal prefix |
| `creatinine` | `ug/dl` | `mg/dl` | 0.001 | 0 | decimal prefix |
| `cholesterol` | `mg/dl` | `mg/dl` | 1 | 0 | identity |
| `cholesterol` | `mmol/l` | `mg/dl` | **38.6654** | 0 | MW cholesterol 386.654 g/mol ÷ 10 · inverse ×0.02586 · 5.17 → 199.9 |
| `cholesterol` | `g/l` / `mg/l` | `mg/dl` | 100 / 0.1 | 0 | decimal prefix |
| `triglycerides` | `mg/dl` | `mg/dl` | 1 | 0 | identity |
| `triglycerides` | `mmol/l` | `mg/dl` | **88.57** | 0 | MW triolein 885.7 g/mol ÷ 10 · inverse ×0.01129 · 1.7 → 150.6 |
| `triglycerides` | `g/l` / `mg/l` | `mg/dl` | 100 / 0.1 | 0 | decimal prefix |
| `bmi` | `kg/m2` | `kg/m2` | 1 | 0 | identity |
| `age` | `years` | `years` | 1 | 0 | identity |

Accepted spellings are normalised first (`mg/dL`, `mg / dL`, `MG/DL`,
`mgs/dl`, `mg%`, `mg/100mL` → `mg/dl`; `µmol/L`, `μmol/L`, `mcmol/L` →
`umol/l`; `gm/dl`, `g%` → `g/dl`; `kg/m²` → `kg/m2`; `percent` → `%`).
`ng/L` and `ng/mL` are deliberately kept distinct.

### Unit handling policy

| Situation | Behaviour |
|---|---|
| Unit matches the canonical unit | Value used as-is; not listed in `conversions_applied` |
| Unit is convertible | Converted; recorded in `conversions_applied` and in `provenance.conversion` |
| **No unit printed** | The canonical unit is **assumed**, `provenance.unit_assumed = true`, and a warning is emitted |
| **Unit printed but unrecognised for the feature** | **Never assumed canonical.** The feature is still emitted so Module 6 can see it, but with the value **unconverted**, `unit` set to the **original string**, `canonical_unit = false`, `provenance.unit_recognised = false`, and a warning |

---

## Value handling policy

| Input | Behaviour |
|---|---|
| `value_numeric` present | Used directly (Module 4's parse wins) |
| `value_numeric` null, `value_raw` numeric | Re-parsed conservatively |
| `"1,234"` | Thousands separators removed → `1234.0` |
| `"<0.1"` / `"≤0.1"` | Value kept at the stated detection limit (`0.1`), `provenance.censored = "left"`, warning emitted |
| `">500"` / `"≥500"` | Value kept at the limit (`500`), `provenance.censored = "right"`, warning emitted |
| `"Negative"`, `"Trace"`, `"Not Detected"` | **Never coerced to a number.** Row preserved in `unmapped[]` with reason `non_numeric_value` |
| Any nullable Module 4 field missing | Carried through as `null`; nothing is invented |

Censored values are kept at the limit because that bound is a real reported
fact. Discarding it loses information; shifting it invents one. Module 6 owns
the decision about whether a censored value may be used.

---

## Duplicate resolution policy

Two report rows can map to the same canonical feature (fasting *and*
post-prandial glucose; creatinine repeated across pages). The winner is chosen
by a **total, deterministic rank** — the same payload always yields the same
winner:

1. **Higher synonym specificity.** Declared per synonym in the catalog. For
   glucose: fasting (3) > unqualified (2) > random (1) > post-prandial (0).
   Fasting glucose is what the diabetes models are trained on.
2. **Recognised unit** beats unrecognised-or-assumed.
3. **Uncensored** beats censored.
4. **Higher extraction confidence** (a missing confidence ranks last).
5. **Earlier `page_number`** (a missing page ranks last).
6. **Earlier position in `extracted_parameters[]`** — the final tie-break, so
   the result never depends on dict or timing order.

Every resolution is recorded in `duplicates_resolved[]` (chosen + all
discarded candidates, with the policy string), a warning is emitted, **and**
each discarded row is additionally listed in `unmapped[]` with reason
`duplicate_discarded`. Nothing disappears.

---

## Patient profile merge — tri-state booleans

`hypertension` and `heart_disease` are **tri-state**: `true`, `false`, or
**absent meaning unknown**. Absent is **never** collapsed to `false` — that
would fabricate a negative clinical finding.

| Profile input | Result |
|---|---|
| `true` / `"yes"` / `1` | Feature present, value `true` |
| `false` / `"no"` / `0` | Feature present, value `false` |
| absent, `null`, `"unknown"`, `"no info"` | Feature **absent**; the name appears in `missing_features` |
| unrecognised token | Feature **absent**, warning + `unmapped[]` entry (`unrecognised_category`); still never `false` |

The same "report, don't default" rule applies to `smoking_history` and
`gender`: an unrecognised category produces a warning and an `unmapped[]`
entry, not a guessed value.

`bmi` is taken from Module 2, which derives it server-side. If `bmi` is absent
but both `heightCm` and `weightKg` are supplied, Module 5 derives
`weightKg / (heightCm/100)²` as a **fallback only**, records
`provenance.derived`, and warns that Module 2 is authoritative.

---

## Module 5 — not in scope

Module 5 does **none** of the following:

| Not here | Belongs to |
|---|---|
| Range checks, physiologic plausibility, "is this value believable?" | **Module 6** |
| Rejecting a value for unit inconsistency (Module 5 only *flags* it) | **Module 6** |
| Storing features, cross-report history, the shared access interface | **Module 7** |
| Clinical rules, risk scoring, decision structures | Rule / Decision engines |
| ML prediction and imputation | Modules 10–12 |
| RAG, LLM explanations, safety validation | Modules 18–24 |
| Any database, auth, or frontend | Node `backend/` and the React app |

Module 5 also does not modify Module 4: it consumes
`app/schemas/extraction.ExtractedParameter` as a read-only contract.


---

## Layout

```
ai-service/
  app/
    main.py                       FastAPI app, error handlers, CORS
    config.py                     pydantic-settings configuration
    api/
      routes_ocr.py               POST /api/v1/ocr/extract          (M4)
      routes_features.py          POST /api/v1/features/engineer    (M5)
                                  GET  /api/v1/features/catalog     (M5)
      routes_health.py            GET  /api/v1/health
    schemas/
      extraction.py               the binding Module 4 contract (pydantic v2)
      features.py                 the binding Module 5 contract (pydantic v2)
    data/                         CLINICIAN-AUDITABLE reference tables (M5)
      feature_catalog.py          canonical features + test-name synonyms
      unit_conversions.py         unit spellings + conversion factors
    services/
      document_loader.py          sniffing, limits, PDF render, image prep
      gemini_client.py            SDK wrapper, retries, error classification
      extractor.py                page orchestration and assembly
      feature_engineer.py         Module 5 logic (framework-independent)
    prompts/extraction_prompt.py  the versioned extraction prompt
    core/
      errors.py                   error taxonomy and JSON envelope
      logging.py                  PHI-safe logging
      auth.py                     X-Service-Key auth + fail-closed startup
      request_context.py          X-Request-Id correlation ids
  tests/
  requirements.txt
  .env.example
```

The extraction prompt is isolated in its own module so it can be reviewed and
versioned independently; `PROMPT_VERSION` is reported by `/api/v1/health`.

---

## Not in scope (future modules)

This service deliberately does **none** of the following. Do not add them here.

| Not here | Belongs to |
|---|---|
| Feature validation, plausibility/range checking, unit-consistency rejection | **Module 6** |
| Storing accepted features, cross-report history | **Module 7** — Feature Repository |
| Clinical rules, risk scoring, decision logic | Rule Engine / Decision Engine |
| ML prediction (diabetes, heart, kidney) | ML Predictors |
| Retrieval over medical knowledge documents | RAG Layer |
| Patient-friendly explanations, XAI, final report generation | LLM / XAI layers |
| Persistence of reports, values or history | Database (MongoDB, via the Node backend) |
| Authentication, patient profiles, report management | **Module 1–3** — the Node/Express `backend/` |
| Frontend, dashboards, timelines | React frontend |

Module 4's contract is the boundary: it reports **what the document says**,
with confidence and caveats. Everything about what those values *mean* happens
downstream.

---

## Integration note

This is a separate service from the Node/Express `backend/`. The backend
handles user auth, profiles and persistence, and calls this service over HTTP
when a report is uploaded — Module 4 first, then Module 5 with the result. See
[Driving this service as a pipeline stage](#driving-this-service-as-a-pipeline-stage)
for the exact request shapes, headers and timeouts.

This service is stateless and **authenticates its caller with a shared secret**
(`X-Service-Key` / `AI_SERVICE_API_KEY`) — it fails closed and will not start
without one. That is defence in depth, not a licence to expose it: **still keep
it on an internal network and do not publish the port.** `CORS_ALLOW_ORIGINS`
defaults to empty and should stay that way.

Known remaining gaps, honestly stated:

* **One shared secret, no rotation window.** Changing it requires restarting
  both services together. There is no key-id / dual-key overlap.
* **No rate limiting.** A caller holding the key can drive unlimited Gemini
  spend. Bound it at the backend or at the network edge.
* **No mTLS and no request signing.** The secret is a bearer credential: anyone
  who can read it can use it. It must travel over TLS or a private network.
* **No audit log of extractions** — nothing is persisted here by design.

---

<!-- BEGIN MODULE 6 -- Medical Feature Validation Engine (added by the Module 6 build) -->

## Module 6 — Medical Feature Validation Engine

Module 5 answers *"what feature is this, and in what canonical unit?"*.
**Module 6 answers "is this value believable?"** — and nothing else. It does not
diagnose, and it does **not** reject a value for being abnormal.

| | |
|---|---|
| Endpoint | `POST /api/v1/features/validate` |
| Rule table | `GET /api/v1/features/validation-rules` |
| Router | `app/api/routes_validation.py` (service-auth applied at router level) |
| In-process API | `app.services.validator.validate_features(engineered)` |
| Rules (clinician-auditable) | `app/data/validation_rules.py` |
| Schemas | `app/schemas/validation.py` |

### The two bands

Every numeric feature carries two, and they mean different things:

* **Possible band** (`possible_low`..`possible_high`) — what a living human can
  actually have, taken from the extremes of the case-report literature.
  Outside it, the value is treated as an **extraction error** and **rejected**.
* **Extreme band** (`extreme_low`/`extreme_high`) — inside the possible band
  but clinically critical. Such values are **valid and fully usable**, merely
  tagged `clinically_extreme` for downstream prioritisation.

```
blood_glucose 400   mg/dL -> VALID, clinically_extreme (real, serious diabetes)
blood_glucose 40000 mg/dL -> REJECTED, IMPLAUSIBLE_VALUE_HIGH (OCR digit run)
```

### Output partition

* `valid` — **the usable feature set**. Same `name/value/unit/canonical_unit/
  source/provenance` fields as Module 5's `EngineeredFeature`, plus `status`,
  `questionable`, `clinically_extreme`, `extreme_direction`, `flags[]`.
* `questionable` — a **subset view of `valid`**, not a separate partition.
  Usable, but confidence-degraded (`UNIT_ASSUMED`, `CENSORED_VALUE`,
  `DERIVED_VALUE`, `LOW_EXTRACTION_CONFIDENCE`, `PARTIAL_DOCUMENT`).
* `rejected` — **disjoint from `valid`**. Original value and full provenance
  preserved, with a machine-readable `reason_code` and a human-readable
  `reason`.

Invariants: `set(valid) & set(rejected) == set()` and
`set(questionable) <= set(valid)`.

### Rules that are not negotiable

* **Nothing is ever repaired.** No clamping, no rescaling, no unit guessing. A
  value is passed through, flagged, or rejected — always untouched.
* **`canonical_unit: false` is a rejection.** Module 5 did not convert the
  value, so its magnitude is meaningless and no range check can rescue it.
* **Absent tri-state booleans stay UNKNOWN.** `hypertension` / `heart_disease`
  absent from `valid`, `questionable` and `rejected` means unknown — never
  `false`.
* **Warnings keep their origin.** Module 4's stay `stage="extraction"`,
  Module 5's stay `stage="feature_engineering"`, Module 6 adds
  `stage="validation"`. `all_warnings[]` is the list the final report consumes.
* `upstream{}`, `extraction_confidence`, `pages_unreadable`, `unmapped[]` and
  `missing_features[]` are carried forward unchanged. A rejected feature is
  **not** added to `missing_features` — "read and refused" is not "absent".

<!-- END MODULE 6 -->

<!-- BEGIN MODULE 8 -- Clinical Rule Engine (added by the Module 8 build) -->

## Module 8 — Clinical Rule Engine

Deterministic, transparent, threshold-based analysis. Every decision is
traceable to a threshold configured in a reviewable data file, and every
threshold cites its clinical basis.

**Endpoints** (all require `X-Service-Key`):

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/rules/evaluate` | Apply the rule table; returns `ClinicalDecision[]` |
| GET | `/api/v1/rules/clinical-rules` | The rule table, thresholds and clinical basis |
| GET | `/api/v1/rules/conditions` | The canonical condition vocabulary |
| GET | `/api/v1/rules/recommendations` | The recommendation catalogue and its safety rules |

Also exposed framework-independently as `evaluate_rules()` in
`app/services/rule_engine.py`, so Module 15 can call it in-process.

### Files

| File | What lives there |
|---|---|
| `app/data/clinical_rules.py` | **The medicine.** Every rule, band, threshold and its guideline citation. Self-checks against the feature catalog at import. |
| `app/data/conditions.py` | The canonical condition vocabulary Modules 10–12 must match. |
| `app/data/recommendation_catalog.py` | The fixed, reviewed recommendation text plus the safety scanner. |
| `app/schemas/rules.py` | Request/response contract. |
| `app/services/rule_engine.py` | The logic. No thresholds live here. |
| `app/api/routes_rules.py` | Thin HTTP wrapper. |

### Input

`{"validated": <Module 6's data object>}` is canonical. A bare Module 6 object,
a relayed `{success, data}` envelope, and a raw Module 5 feature set (under
`engineered`, bare, or enveloped) are all accepted. Anything ambiguous is a
**422** — nothing is guessed. A raw Module 5 set is passed through
`validate_features()` in-process first, so rules only ever see validated values.

### Rules never read rejected features

`ValidatedFeaturesInput` deliberately has **no `rejected` field**. Module 6's
rejected map holds suspected extraction errors; because it is never parsed,
there is no attribute for a rule to read. The guarantee is structural.

### Missing data never reads as normal

* A rule whose feature is absent **does not fire** — it never falls through to
  its "nothing found" band.
* The tri-state booleans are read only as **positive** risk factors, counted
  when the value is exactly `true`. Absent and `false` both add nothing.
* `Diabetes`, `Heart Disease` and `Kidney Disease` always produce exactly one
  decision; when their inputs are missing that decision is `INSUFFICIENT_DATA`
  with `risk=None`, so Module 16 can tell "not assessed" from "nothing found".
* When the document was **partially unreadable**, an absent analyte also yields
  `INSUFFICIENT_DATA` rather than silence.
* Adult-only rules emit `INSUFFICIENT_DATA` for a recorded age under 18 rather
  than applying an adult reference interval to a child.

### Recommendation safety is structural

1. `recommendation(code)` is the only way Module 8 builds a `Recommendation`,
   and it takes a **code** — there is no text parameter to inject through.
2. Every catalogue entry, every rule band label and every factor label is
   scanned at **import time** for medication names, dosages, treatment
   instructions, diagnostic assertions and certainty claims. A violation is an
   `ImportError`, so the service refuses to start rather than emit bad advice.
3. The scanner is itself tested against planted violations, so it cannot rot
   into a regex that matches nothing.

### Other properties

* Every decision carries `confidence=None` (no probability is produced) — never
  `0.0`.
* `clinically_extreme` is treated as a **prioritisation signal**, never as a
  reason to distrust a value.
* `questionable` inputs surface in `metadata.questionable_inputs`, in the
  evidence note, and as an `INPUT_QUALITY_CAVEAT` recommendation.
* `metadata` carries the rule id, rule version, table version and engine
  version — and **no measured values and no report text**.
* Every warning from Modules 4, 5 and 6 is carried through with its origin
  intact; Module 8's own are appended under `stage="rules"`, `module=8`.

### Mounting

`app/main.py` needs one line, added next to the other routers:

```python
app.include_router(routes_rules.router)
```

with `routes_rules` added to the existing `from app.api import ...` line. Until
that lands, `tests/test_rules_endpoint.py` mounts the router itself at import
time, idempotently.

<!-- END MODULE 8 -->

<!-- BEGIN MODULE 9-10 -- ML Prediction Engine & Diabetes Model (added by the Module 9-10 build) -->

## Modules 9, 10 & 13 — ML Prediction Engine, Predictor Registry, Diabetes Model

Condition-specific predictors, registered dynamically, each emitting the shared
`ClinicalDecision` from `app/schemas/decisions.py`.

```
Module 6 (validated features)
        |
        v
  PredictorRegistry            <- Module 13
        |
        +-- DiabetesPredictor      Module 10  (built)
        +-- HeartPredictor         Module 11  (not built)
        +-- KidneyPredictor        Module 12  (not built)
        |
        v
  ClinicalDecision[]  ->  Module 15  ->  Module 16
```

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/ml/predict` | Run every registered predictor over a feature set |
| `GET` | `/api/v1/ml/predictors` | Registry introspection: names, required features, availability |
| `GET` | `/api/v1/ml/models` | Model provenance and the full recorded evaluation metrics |

All three carry the `require_service_key` dependency, exactly as
`routes_rules.py` does. Also exposed framework-independently for Module 15:

```python
from app.ml import predict_all
data = predict_all(validated_features)          # or predict_all(engineered=...)
```

**Input tolerance is inherited, not re-implemented.** `MLPredictionRequest`
subclasses `RuleEvaluationRequest`, so every shape `POST /api/v1/rules/evaluate`
accepts, `POST /api/v1/ml/predict` accepts identically, with the same 422s on
ambiguity. Re-implementing the unwrap logic would let the two tolerances drift,
and the failure mode of a drift is not an error — it is an HTTP 200 carrying
`decisions: []`.

### The registry interface Modules 11 and 12 implement

Subclass `app.ml.base.Predictor`, declare four attributes, implement one method:

```python
class KidneyPredictor(Predictor):
    name = "kidney_rf"
    condition = C.KIDNEY_DISEASE        # imported constant, never spelled out
    source_label = "Random Forest"
    required_features = ("creatinine",)
    optional_features = ("age", "hemoglobin", "hypertension")

    def _predict(self, features, context) -> ClinicalDecision:
        ...
```

then add **one line** to `_register_defaults()` in `app/ml/registry.py`. Nothing
else changes — not `predict_all()`, not `routes_ml.py`, not the response schema.
`tests/test_ml_registry.py` proves this by running the whole engine over a fake
predictor for a condition no model exists for.

`predict()` is a **template method and must not be overridden**. It runs the
sufficiency check, returns `INSUFFICIENT_DATA` itself when inputs are missing
(so `_predict` is never even called), and then **audits** what the subclass
returned: canonical condition, `source_kind=MACHINE_LEARNING`, non-`None`
confidence. A subclass author cannot skip the sufficiency gate by forgetting it.

### Information sufficiency (spec Module 12)

The diabetes predictor requires **`hba1c` and `blood_glucose`**. Those two carry
~69% of the model's global importance; if either is absent the median imputer
would substitute a population value for the single most discriminative input,
and the probability would be driven mostly by the training set rather than by
the patient. So it **skips**, returning `INSUFFICIENT_DATA` with `risk=None` and
`confidence=None`.

That is not a hole in the report: Module 8's rule engine still assesses
`Diabetes` from whichever value *is* present, and `Diabetes` is
`always_assessed` in `app/data/conditions.py`. Only the ML opinion is withheld.

---

## Module 10 — the Diabetes model

**Random Forest** inside one scikit-learn `Pipeline` (median imputation for
numerics, most-frequent + one-hot for categoricals), persisted whole with
`joblib`.

| | |
|---|---|
| Training script | `ml/train_diabetes.py` — **run by hand**, never at import or request time |
| Model artifact | `ml/artifacts/diabetes_rf_v1.joblib` (15.1 MB) |
| Metrics artifact | `ml/artifacts/diabetes_rf_v1.metrics.json` |
| Dataset | `datasets/raw/diabetes_prediction_dataset.csv`, sha256 `f233fc47…` |
| Hyperparameters | `n_estimators=200`, `min_samples_leaf=50`, `class_weight="balanced_subsample"`, `random_state=42` |

Nothing generates, augments or synthesises a row. `synthetic_rows: 0` and
`resampling: "none"` are recorded in the artifact and asserted by tests. **No
SMOTE** — synthetic minority oversampling would violate the real-data-only rule;
class weighting plus threshold tuning does the same job on real rows.

Tests **load** this artifact. They never fit a model.

### Evaluation (spec §11) — held-out test split, n = 19,230, prevalence 8.82%

Threshold-independent first, because at 8.8% positive these are the numbers that
mean anything:

| Metric | Value |
|---|---|
| **PR-AUC (average precision)** | **0.872** |
| **ROC-AUC** | **0.974** |

At the tuned decision threshold **0.795**:

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| Positive (diabetes) | 0.911 | 0.703 | 0.794 | 1,696 |
| Negative | 0.972 | 0.993 | 0.983 | 17,534 |

Confusion matrix (rows = actual, columns = predicted):

|  | pred. negative | pred. positive |
|---|---|---|
| **actual negative** | 17,418 | 116 |
| **actual positive** | 504 | 1,192 |

**Accuracy 0.968 — against a majority-class baseline of 0.912.** Accuracy is
listed last deliberately. Predicting "no diabetes" for everyone scores 91.2% on
this data, so accuracy mostly measures the prevalence. The model does beat the
baseline, but the precision/recall pair above is what actually describes it.

**5-fold stratified cross-validation** (training portion, fresh pipeline fitted
inside every fold, scored at sklearn's default 0.5 threshold):

| Metric | Mean ± SD |
|---|---|
| ROC-AUC | 0.9756 ± 0.0013 |
| PR-AUC | 0.8778 ± 0.0060 |
| Recall | 0.9129 ± 0.0051 |
| Precision | 0.4774 ± 0.0040 |
| F1 | 0.6269 ± 0.0030 |

Standard deviations in the third or fourth decimal place across folds: the model
is **stable**, not split-lucky. Note the CV precision (0.48) is far below the
test precision (0.91) — that is not a contradiction, it is the whole reason the
threshold was tuned. At 0.5, class weighting makes the model very sensitive and
very unspecific; the deployed cut-off of 0.795 trades recall for precision.

### An honest read of whether this model is good

**Genuinely good:** ROC-AUC 0.974 and PR-AUC 0.872 against an 8.8% base rate are
strong, and 5-fold CV shows they are stable. The risk bands calibrate well
(below).

**Caveats an auditor should weigh:**

1. **It recalls only 70% of positives at the deployed threshold.** Roughly 3 in
   10 positive cases are not flagged INDICATED. Most land in the middle band
   rather than the low one — 12 of 1,696 positives fall below the low cut-off —
   but the headline is not "catches everyone".
2. **The task is partly circular.** HbA1c ≥ 6.5% is itself a diagnostic
   criterion for diabetes, and HbA1c alone carries ~40% of the model's
   importance. A forest scoring 0.97 AUC here is substantially rediscovering a
   threshold that already exists in `app/data/clinical_rules.py`. That is fine
   for a decision-support second opinion, but it should not be read as the model
   finding something the rules cannot.
3. **BMI is a weak, partly-corrupted feature.** 25,495 rows (25.5%) carry
   `bmi = 27.32` because the dataset's author median-filled missing BMI, and
   which rows those are is unrecoverable. The learned BMI effect near that value
   is therefore attenuated.
4. **This is one public dataset with unstated provenance and demographics.** It
   has not been validated on any Indian cohort, on this project's users, or on
   any prospective data.

### The tri-state problem — the most important modelling decision here

Module 2 stores `hypertension` and `heart_disease` as **true / false /
absent-means-unknown**. The dataset has only 0 and 1 — no unknown state.
Encoding an absent answer as 0 would fabricate a negative clinical finding.
Median-imputing is the same act with better manners: the median of a 92%-zero
column *is* 0.

**Solution: four fitted pipelines, one per availability pattern.**

| Patient answered | Variant used | Columns in the matrix |
|---|---|---|
| both | `both` | includes both |
| hypertension only | `hypertension_only` | includes hypertension only |
| heart disease only | `heart_disease_only` | includes heart disease only |
| neither | `neither` | includes neither |

Each was fitted on the same real rows; each variant's `ColumnTransformer` simply
does not contain the column it cannot know. The matrix handed to the forest
**never contains a value that was not observed** — not a zero, not a median.
`tests/test_diabetes_predictor.py` asserts this against the real DataFrame
columns, not against metadata, because encoding absence as a negative produces
an entirely plausible-looking prediction that would otherwise never surface.

Only a real Python `bool` counts as an answer. `bool("false")` is `True` and
`bool(0)` is `False`; both would fabricate, so anything that is not a `bool` is
treated as unknown.

**Why this is different from imputing `bmi` or `age`:** imputing a continuous
*measurement* substitutes a population value for an unmeasured quantity — a
documented statistical choice, and the one spec §10 explicitly asks for.
Imputing a boolean *clinical finding* invents a diagnosis the patient never gave.

**The honest footnote:** the `neither` variant scores ROC-AUC 0.9734 against
`both`'s 0.9738. Dropping the tri-state pair costs essentially nothing, because
HbA1c and glucose carry almost all the signal. The variant machinery buys
correctness at no measurable accuracy cost — the best possible outcome, but it
also means nobody should claim these two features do much work.

| Variant | ROC-AUC | PR-AUC | F1 (pos) | `indicated` | `borderline` |
|---|---|---|---|---|---|
| `both` | 0.9738 | 0.8721 | 0.794 | 0.7948 | 0.1173 |
| `hypertension_only` | 0.9739 | 0.8719 | 0.795 | 0.7958 | 0.1151 |
| `heart_disease_only` | 0.9737 | 0.8718 | 0.791 | 0.7853 | 0.1157 |
| `neither` | 0.9734 | 0.8712 | 0.797 | 0.7932 | 0.1239 |

### Duplicates, imputed BMI, unseen categories

**Duplicates — 3,854 exact duplicate rows, dropped BEFORE splitting.**
De-duplicating *after* the split would let the same row sit in train and test,
and the test score would then partly measure memorisation. Dropping first
guarantees no exact row appears on both sides. The cost is stated rather than
hidden: some of those rows are probably distinct patients who coincidentally
match on eight coarse features, so a little real information is discarded to
protect the evaluation. 100,000 rows → 96,146; prevalence 8.50% → 8.82%.

**Imputed BMI — kept, not dropped.** See caveat 3 above. Dropping 25% of the
rows would discard 25% of the positives and would bias the sample if the fill
was not missing-at-random.

**Unseen categories — encoded as all zeros, never as the majority category.**
`OneHotEncoder(handle_unknown="ignore")`. Module 2 allows
`gender="prefer_not_to_say"`, which has no dataset equivalent; it reaches the
encoder as a value it never saw and becomes an all-zero block — *no category
asserted*. An absent categorical uses an explicit `__absent__` sentinel for the
same reason, so the spec-required most-frequent imputer (present and fitted)
never gets the chance to assert the majority gender.

**Smoking normalisation.** The training script lower-cases and underscores the
dataset spellings (`No Info` → `no_info`, `not current` → `not_current`), so the
encoder's levels *are* Module 2's vocabulary. A mismatch here would silently
drop the feature — nothing raises, the encoder just zeroes it. Note that in the
HTTP path Module 6 rejects dataset-spelled values upstream anyway, since Module 2
only ever stores the underscore forms; the predictor's own normaliser is
defence-in-depth for in-process callers.

### Probability → risk cut-offs

Both are read off the **measured precision-recall curve of a held-out validation
split**, stored per variant in the artifact, and neither is a round number.

| Band | Rule | Value (`both`) | Status / Risk |
|---|---|---|---|
| high | smallest threshold whose cumulative **precision ≥ 0.90** | **0.7948** | `INDICATED` / `HIGH` |
| medium | between the two | — | `BORDERLINE` / `MEDIUM` |
| low | below the largest threshold holding cumulative **recall ≥ 0.99** | **0.1173** | `NOT_INDICATED` / `LOW` |

**The asymmetry is the point.** The upper cut-off is set by *precision* because a
false INDICATED costs unnecessary worry. The lower one is set by *sensitivity*
because a false NOT_INDICATED is false reassurance — which `decisions.py` calls
"the most dangerous failure mode this type can have".

**Evidence the upper cut-off is not an artefact of the criterion:** the
F1-maximising threshold on the same validation data is **0.7925**, within 0.003
of the precision-targeted 0.7948. Two independent criteria agree.

**Measured band composition on the held-out test split** (variant `both`):

| Band | Patients | Actual positives | Observed positive rate |
|---|---|---|---|
| low | 11,713 (60.9%) | 12 | **0.10%** |
| medium | 6,209 (32.3%) | 492 | **7.92%** |
| high | 1,308 (6.8%) | 1,192 | **91.13%** |

**Read the middle band honestly.** Its own positive rate (7.9%) is a shade
*below* the cohort prevalence of 8.8%, because everyone genuinely high-scoring
has already been pulled out into the high band. It therefore means **"not ruled
out"**, not "elevated". It is mapped to `BORDERLINE`/`MEDIUM` because that is the
vocabulary `decisions.py` offers, and `metadata.band_meaning` carries the real
meaning — with these measured rates — forward so Module 20 can render it without
overclaiming.

### Confidence semantics — read before using the field

`ClinicalDecision.confidence` is **always P(positive class)**, never "how sure
the model is of whatever it concluded". A `NOT_INDICATED` decision carries a
*low* number (e.g. 0.012), meaning "1.2% probability of diabetes" — a confident
negative, not a shaky verdict. `decisions.py` defines the field as "model
probability in [0,1]" and Module 16 fuses on it, so a single consistent
direction is the only workable choice. Every decision records
`metadata.confidence_semantics = "probability_of_positive_class"`.

### Evidence and explainability

Every feature the model was given appears as an `EvidenceItem` — **including the
absent ones**, because "the model was not told whether you have hypertension" is
exactly what spec Module 20 exists to show. `threshold` and `comparator` are
`None` throughout: `decisions.py` reserves them for rule-based producers, and no
single threshold explains a forest.

Feature importances are **global / model-level** (mean impurity decrease over the
whole training set). They order the evidence list, and that is all. Every
decision carries `feature_importance_scope: "global_model_level"` plus an
explicit caveat that this is **not** a per-patient explanation — spec §24 forbids
unsupported certainty, and a global importance says nothing about one patient.

Recommendations come from `app/data/recommendation_catalog.py` **by code only**.
There is no code path in the ML layer that composes recommendation text.
`NOT_A_DIAGNOSIS` is attached to every decision. All user-facing note fragments
are scanned by the catalogue's own safety scanner in the test suite.

### Failure containment

* **Missing / unloadable artifact** → `is_available()` returns False, every
  decision is `INSUFFICIENT_DATA` with `skipped_reason="model_unavailable"`, and
  `GET /api/v1/ml/predictors` shows it. A deployment that forgot the model
  produces visibly unassessed topics, never fabricated predictions and never a
  500 on every report.
* **A predictor that raises** is contained: a warning plus an
  `INSUFFICIENT_DATA` decision. One broken model must not take down the analysis
  of every other condition. Only the exception **type** is logged and surfaced —
  a model exception message can echo medical values.

### Tests

`tests/test_ml_registry.py` (40) · `tests/test_diabetes_predictor.py` (82) ·
`tests/test_ml_endpoint.py` (36) — **158 new, all offline, none of them train.**

### Mounting

`app/main.py` needs one line, added next to the other routers:

```python
app.include_router(routes_ml.router)
```

with `routes_ml` added to the existing `from app.api import ...` line. Until that
lands, `tests/test_ml_endpoint.py` mounts the router itself at import time,
idempotently.

### Retraining

```bash
python ml/train_diabetes.py
```

Rewrites both artifacts. The metrics JSON records the sha256 of the joblib it was
produced from, and `test_the_metrics_document_describes_the_committed_model`
recomputes it — so committing one file without the other fails the suite.

<!-- END MODULE 9-10 -->

<!-- BEGIN MODULE 7 -- Feature Repository (added by the Module 7 build) -->

## Module 7 — Feature Repository

The spec's **storage** step: `Extraction → Validation → Storage → Analysis`.
Module 6 answers *"is this value believable?"*. **Module 7 answers "what do we
have, and how do I read it?"** — one access point, so no analytical component
re-derives a laboratory value that has already been extracted and validated.

| | |
|---|---|
| In-process API (**primary**) | `app.services.feature_repository.load_features(validated, ...)` |
| Repository class | `FeatureRepository` |
| Storage backends | `app/services/repository_backend.py` (`RepositoryBackend` + `InMemoryRepositoryBackend`) |
| Schemas | `app/schemas/repository.py` |
| Router | `app/api/routes_repository.py` (service-auth applied at router level) |
| Endpoints | `POST /api/v1/repository/load` · `GET /api/v1/repository/snapshots/{id}` · `GET .../snapshots/{id}/features/{name}` · `GET /api/v1/repository/patients/{ref}/snapshots` · `GET /api/v1/repository/interface` |

### The interface consumers use

```python
from app.services.feature_repository import ABSENT, load_features

repo = load_features(validation_result, patient_ref="...", report_date="2024-03-12")

repo.has("hba1c")                  # bool -- the safe thing to branch on
repo.get("hba1c")                  # value, or the ABSENT sentinel
repo.get("hba1c", default=None)    # value, or your own default
repo.require("hba1c")              # value, or FeatureUnavailableError(reason)
repo.get_or_none("hba1c")          # value or None -- opt in, by name
repo.tristate("hypertension")      # True / False / None(unknown)
repo.numeric("creatinine")         # float, or ABSENT
repo.unit("hba1c")                 # "%", or ABSENT
repo.source("hba1c")               # "lab_report" | "patient_profile"
repo.provenance("hba1c")           # FeatureProvenance, unflattened
repo.feature("hba1c")              # the whole StoredFeature record
repo.values()                      # {name: value} -- the whole usable set, once
repo.available() / repo.missing()  # tuple[str, ...], catalogue order
repo.questionable() / repo.clinically_extreme() / repo.rejected()
repo.why_unavailable("creatinine") # UnavailableFeature -- reason, NO value
repo.warnings() / repo.upstream() / repo.summary()
repo.to_validated_input()          # hand straight to evaluate_rules / predict_all
```

`load_features(engineered=...)` is also accepted and is validated **in-process
through Module 6 first**, so the repository only ever stores values Module 6
accepted. `validated` wins when both are given.

### Absence is never silently coerced

The property the module is built around. Three mechanisms together:

1. **`get()` returns `ABSENT`**, a singleton that **raises** on `bool()`,
   `float()`, `int()`, indexing, iteration, arithmetic and comparison. The
   classic bug — `if repo.get("hypertension"):` reading a missing feature as
   "no" — raises `AbsentValueError` instead of fabricating a negative finding.
2. **`require()` raises** `FeatureUnavailableError`, carrying the reason code.
3. **`get_or_none()`** exists for callers that genuinely want `None`, but they
   ask for it by name. Nothing hands out `None` by default.

`tristate()` refuses to be pointed at a number (so a `0.0` can never be read as
a negative), and `numeric()` refuses booleans (so `True` never becomes `1.0`)
and refuses a value whose unit was not recognised. A **typo** in a feature name
raises `UnknownFeatureError` — a different failure from an absent value.

### Rejected features are structurally unreadable

`app/schemas/rules.py` makes this structural for the rule engine by not parsing
Module 6's `rejected` map at all. The repository *must* keep the reasons, so it
goes one level deeper: rejections parse into **`UnavailableFeature`, which has
no `value` field**, and the rejected value is dropped at the parse boundary
(`IncomingRejection` is `extra="ignore"` and declares no `value`). No accessor
reads the `unavailable` map — `get`, `require`, `values`, `numeric`, `tristate`
and `unit` read `features` only.

`provenance` **is** kept on a rejection so Module 20 can explain the refusal
against the printed report line. It is explanation metadata reached through
`provenance`; nothing can return it as a feature value.

`why_unavailable()` answers for every canonical feature: `rejected` (Module 6
refused it), `not_reported` (never present — and a distinct reason code when the
document had unreadable pages, since it may have been *unread* rather than
absent), or `unusable`.

### Storage backends

`RepositoryBackend` is six methods — `put`, `get`, `delete`, `for_patient`,
`patients`, `count` — with `latest_for_patient` / `require` derived. The shipped
`InMemoryRepositoryBackend` returns deep copies, so a caller mutating what it
got back cannot corrupt the store.

This mirrors `backend/src/storage/` for uploaded files: an opaque, swappable
adapter. **No database, no MongoDB dependency.** `backend/` currently persists
analysis results on the `Report` document as an explicitly interim arrangement;
formalising that means adding a persistent `RepositoryBackend`, installed with
`set_default_backend()`, with **no consumer change**. `FeatureSnapshot` is fully
JSON round-trippable, so such a backend needs no serialisation logic of its own.

**Caveats of the in-memory backend, stated rather than hidden:** it holds PHI in
process memory, loses everything on restart, is process-local (two uvicorn
workers do not share it), and is unbounded unless
`max_snapshots_per_patient` is set.

### Multiple reports per patient (Modules 28–30 groundwork)

Each snapshot carries a `SnapshotIdentity`: `snapshot_id`, opaque `patient_ref`
and `report_ref`, a `report_date` — **the ordering key, aligned conceptually
with the backend's `Report.chronoDate`** — a `recorded_at` fallback, and a
monotonic `sequence` that makes the order total and stable. Datetimes are
normalised to UTC so a naive/aware mix cannot raise mid-query.

```python
history("patient-1")   # every snapshot, chronological, oldest first
latest("patient-1")    # the most recent
references("patient-1")# identities + shape, no values
```

**Module 7 provides the order and the data only.** No trend, no delta, no
comparison, no progress score is computed here — those are Modules 28, 29 and 30.

### Rules that are not negotiable

* **Nothing is stored that Module 6 did not accept**, and nothing is repaired,
  converted, re-derived or defaulted on the way in.
* **Absent is never false, zero or normal**, for tri-states and numerics alike.
* **A rejected feature has no value field to read.**
* **Provenance is passed through whole** — never flattened, never summarised.
* **Every warning keeps its origin.** `all_warnings[]` carries stages 4, 5 and 6
  through unchanged, and Module 7 appends its own as `stage="repository"`.
  `upstream{}`, `extraction_confidence` and `pages_unreadable` are carried
  verbatim.
* **No PHI in logs.** Only counts are logged; feature names, values and
  patient/report references never are.

<!-- END MODULE 7 -->

<!-- BEGIN MODULE 11-12 -->

## Modules 11 & 12 — Heart Disease and Kidney Disease Predictors

Two more `Predictor` subclasses registered in `app/ml/registry.py`. Nothing else
in the service changed: the engine already iterated the registry, so
`GET /api/v1/ml/predictors` now lists three and `POST /api/v1/ml/predict`
returns three decisions per request.

### Files

| File | Role |
|---|---|
| `app/ml/heart.py` | Module 11 predictor |
| `app/ml/kidney.py` | Module 12 predictor |
| `ml/train_heart.py` | Training script — run by hand, never at import |
| `ml/train_kidney.py` | Training script — run by hand, never at import |
| `ml/artifacts/heart_rf_v1.joblib` + `.metrics.json` | Shipped model, metrics sha256-bound to it |
| `ml/artifacts/kidney_rf_v1.joblib` + `.metrics.json` | Shipped model, metrics sha256-bound to it |
| `tests/test_heart_predictor.py` (95 tests) | Loads the artifact; never trains |
| `tests/test_kidney_predictor.py` (75 tests) | Loads the artifact; never trains |

Both models are a Random Forest inside one sklearn `Pipeline` (median impute
numerics → most-frequent impute + one-hot categoricals → forest), persisted
whole via joblib. Both use **real published data only** — no synthetic rows, no
augmentation, no SMOTE.

---

## `"Heart Disease"` means two different things, and the decisions say so

Module 8's `RULE_HEART_DISEASE_RISK_FACTORS` emits `condition="Heart Disease"`
from a **tally of risk factors**. Module 11 emits the same string as a **disease
likelihood**. Module 16 fuses by condition name, so they *will* merge.

The condition string is deliberately **not** renamed — that would break fusion,
which is the one thing Module 16 exists to do. Instead every ML decision carries:

```python
metadata["assessment_kind"]  = "disease_likelihood"   # app.ml.heart.ASSESSMENT_KIND_KEY
metadata["assessment_basis"] = "model_probability"    # app.schemas.fusion.BASIS_MODEL_PROBABILITY
metadata["assessment_kind_note"] = "...the same condition string from a COUNT OF RISK FACTORS..."
```

**Two keys, deliberately.** `assessment_kind` is this module's own statement of
what the number means. `assessment_basis` is **Module 15/16's vocabulary** for
the same distinction (`risk_factor_count` / `threshold_comparison` /
`model_probability` / `not_assessed`), imported from `app/schemas/fusion.py`
rather than spelled out, so a rename there fails loudly here instead of silently
reverting these decisions to Module 16's default. Module 16 already *defaults* a
machine-learning decision to `model_probability`; a default is an assumption, and
this states it.

On the **`INSUFFICIENT_DATA` path** the basis is `not_assessed`, not
`model_probability` — no model ran, and claiming a probability for a model that
never executed would be exactly the kind of lie this key exists to prevent.

**Contract for Modules 16/17:** a decision with **no** `assessment_kind` key is a
risk-factor burden, not a probability. Surface the difference; do not average
across it. Both keys are stamped by Module 11 and Module 12 alike.
`tests/test_heart_predictor.py` asserts both halves of the contract — that the
predictor sets them and that the rule engine's decision for the same condition
does not carry `assessment_kind`.

---

## Module 11 — the Heart Disease model

`datasets/raw/cardio_train.csv` — Kaggle Cardiovascular Disease, 70,000 rows,
semicolon-delimited, byte-identical across three independent GitHub sources.

### The blood-pressure decision — the key modelling call

`ap_hi` / `ap_lo` are by far the strongest predictors in this dataset. **They are
excluded from the shipped model**, because VaidyaAI collects no blood pressure
anywhere: Module 2 does not ask, `feature_catalog.py` has no such feature, and
Module 4 does not extract it from a laboratory report. Training on them would
mean median-imputing the model's most important input for **every real patient**,
and publishing metrics for a model that never runs.

The cost is measured rather than hidden. The training script fits the
BP-inclusive model anyway and records it under
`blood_pressure_reference_model` with `shipped: false`:

| Model | ROC-AUC (held-out) |
|---|---|
| Shipped (age, BMI, cholesterol band, gender, smoking) | **0.697** |
| Reference, adds `ap_hi` + `ap_lo` — **not shipped** | 0.800 |

**Collecting systolic blood pressure in Module 2 is the single highest-value
change anyone could make to Module 11.**

### The four other traps, and what was done about each

**1. `age` is in DAYS.** Converted with `floor(days / 365.25)` to **whole
years**, because `feature_catalog.py` types `age` as an integer in years, which
is exactly what arrives at prediction time. Training on fractional years would
place split points the deployed model can never see. Recorded range after
conversion: 29–64 years.

**2. `cholesterol` is an ORDINAL BAND, not mg/dL.** The dataset's column is
1 = normal / 2 = above normal / 3 = well above normal. VaidyaAI's `cholesterol`
is TOTAL cholesterol in mg/dL. The model column is named `cholesterol_band` and
`app/ml/heart.py::cholesterol_band()` is the only place the conversion happens:

| Total cholesterol | Band | NCEP ATP III label |
|---|---|---|
| `< 200 mg/dL` | 1 | desirable |
| `200 – 239 mg/dL` | 2 | borderline high |
| `>= 240 mg/dL` | 3 | high |

ATP III is the same reference `validation_rules.py` and Module 8's cholesterol
rule already use, and its three labels are the dataset's three labels in the same
order — so this is a translation, not an invention. Boundaries (199.999 → 1,
200.0 → 2, 239.999 → 2, 240.0 → 3) are asserted in the tests.

*A consequence, stated rather than hidden:* 205 and 235 mg/dL are the same band
and the model cannot tell them apart. There is a test for that too.

`gluc` is the same kind of ordinal and is **deliberately unused**: it is worth
+0.003 ROC-AUC, and unlike cholesterol the source does not document whether its
bands are fasting or random glucose, so a mapping would be an unverifiable
assumption. +0.003 does not buy that.

**3. `gender` is 1/2 and the source does not say which is which.** Inferred:

| | n | mean height | mean weight | smokers |
|---|---|---|---|---|
| `gender = 1` | 45,530 | 161.4 cm | 72.6 kg | 1.8% |
| `gender = 2` | 24,470 | 169.9 cm | 77.3 kg | 21.9% |

An 8.6 cm mean height gap in that direction plus a 12-fold smoking difference
admits one reading: **1 = female, 2 = male**. Both signals agree, which is why
this is recorded as an inference with a stated basis (`gender_mapping_basis` in
the artifact) rather than a coin toss. The model then treats gender as a *string*
categorical, so Module 2's `other` and `prefer_not_to_say` reach a
`handle_unknown="ignore"` encoder and become an all-zero block.

**4. The dataset is dirty.** Raw height spans 55–250 cm and weight 10–200 kg,
giving derived BMI 3.5–298.7. The cleaning rule, applied **only to columns the
shipped model reads**:

| Bound | Rows failing it |
|---|---|
| height outside 120–220 cm | 53 |
| weight outside 30–250 kg | 7 |
| BMI outside 8–200 (Module 6's own `possible` band) | 7 |
| **total rows removed (bounds overlap)** | **60** |

**69,940 of 70,000 rows kept.** Cleaning is restricted to modelled columns
deliberately: dropping a row for an implausible value in a column the model never
reads discards a real (features, label) pair for no benefit. The number of rows
kept despite implausible blood pressure is recorded, and a sensitivity fit on the
BP-plausible subset is too (ROC-AUC 0.6971 vs the shipped 0.6970 — the choice
does not matter).

### Smoking is tri-state here too

| Module 2 value | → | Model |
|---|---|---|
| `never`, `former`, `not_current` | → | `smoking_current = 0` |
| `current` | → | `smoking_current = 1` |
| `ever`, `no_info`, absent | → | **UNKNOWN** |

`ever` covers current *and* former smokers, so it does not determine the flag.
An unknown does **not** become 0: the artifact holds two fitted pipelines,
`with_smoking` and `without_smoking`, and the variant whose ColumnTransformer
lacks the column is used. The tests assert this on the real DataFrame.

Honest footnote: `smoking_current` carries **0.5%** of global importance and the
two variants differ by 0.002 ROC-AUC. The machinery is correctness at no
measurable cost; smoking is a spec feature, not a driver, in this model.

### Information sufficiency

`required_features = ("age", "bmi", "cholesterol")` — 98.4% of global importance
between them. Blanking one at prediction time costs 0.049 (age), 0.019 (bmi) or
0.027 (cholesterol) ROC-AUC against a total headroom of 0.197 over chance.
`gender` and `smoking_history` are optional (0.011 and 0.005 importance; blanking
either moves ROC-AUC by less than 0.001).

### Evaluation (spec §11) — held-out test split, n = 13,988, prevalence 49.97%

| Metric | Value |
|---|---|
| **ROC-AUC** | **0.697** |
| **PR-AUC (average precision)** | **0.684** |

At the tuned decision threshold **0.673**:

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| Positive (cardiovascular disease) | 0.747 | 0.277 | 0.404 | 6,990 |
| Negative | 0.557 | 0.906 | 0.690 | 6,998 |

Confusion matrix (rows = actual, columns = predicted):

|  | pred. negative | pred. positive |
|---|---|---|
| **actual negative** | 6,341 | 657 |
| **actual positive** | 5,053 | 1,937 |

**Accuracy 0.592 — against a majority-class baseline of 0.500.** Here the cohort
is near-balanced, so accuracy *is* meaningful — and it is only 9 points above
coin-flipping.

**5-fold stratified cross-validation** (training portion, fresh pipeline fitted
inside every fold, scored at sklearn's default 0.5 threshold):

| Metric | Mean ± SD |
|---|---|
| ROC-AUC | 0.6960 ± 0.0051 |
| PR-AUC | 0.6833 ± 0.0048 |
| Recall | 0.6346 ± 0.0039 |
| Precision | 0.6388 ± 0.0067 |
| F1 | 0.6366 ± 0.0031 |

Global feature importance: `age` 0.383, `bmi` 0.339, `cholesterol_band` 0.263,
`gender` 0.011, `smoking_current` 0.005.

### An honest read of whether this model is good

**No. It is weak, and the reason is measured, not guessed.** ROC-AUC 0.697 is a
poor discriminator by any standard, and the tuned operating point flags fewer
than 3 in 10 true positives. Cross-validation shows the weakness is *stable*, not
split-luck — this really is how well the model performs.

**But the weakness is a data-availability problem, not a modelling failure.** The
same pipeline with blood pressure scores 0.800. What is left after removing it is
age, BMI and a three-level cholesterol band — three coarse demographic and
anthropometric signals with no cardiac measurement among them. No amount of
tuning fixes that.

**What it is still good for:** a coarse risk indicator that is transparent about
its inputs, fused with Module 8's risk-factor tally, which draws on
`heart_disease`, `hypertension` and `hba1c` that this model cannot see. Read the
two together; neither is sufficient alone.

**What nobody should claim:** that this predicts heart disease. It nudges a
50/50 prior to roughly 75/25 at its most confident, and it almost never rules
anything out.

### Probability → risk cut-offs

Module 10's rule (smallest threshold reaching 0.90 cumulative precision) is
**not** reused, for a measured reason: at 50% prevalence and ROC-AUC 0.70 **no
threshold on this curve reaches 0.90 precision at any usable recall**, so the
absolute rule would fall through to its own "target unreachable" branch and pick
the most selective point on the curve — a cut-off chosen by an error path.

So the target is expressed as a **lift over the cohort's own base rate**, which
means the same thing at any prevalence:

* **`indicated = 0.673`** — the smallest out-of-fold threshold whose cumulative
  precision reaches **1.5 × prevalence** (0.7495). Achieved precision 0.750.
* **`borderline = 0.285`** — the largest out-of-fold threshold still holding
  **0.95 cumulative recall**. (Module 10's 0.99 floor would leave a Low band
  holding about 3% of the cohort, which is not a usable rule-out.)

Both are read off the measured precision-recall curve of **out-of-fold**
predictions over the training portion — every training row contributes and none
is scored by a model that saw it. The test split is never touched.

Measured band composition on the held-out split:

| Band | Patients | Positive | Rate |
|---|---|---|---|
| Low | 1,716 (12.3%) | 362 | 21.1% |
| Medium | 9,678 (69.2%) | 4,691 | 48.5% |
| High | 2,594 (18.5%) | 1,937 | 74.7% |

Read that honestly: the middle band *is* the base rate and means **not ruled
out**, not "elevated". The Low band holds only 12% of the cohort at a 21%
positive rate — **this model rarely rules heart disease out, and it never says
"safe"**. `metadata.band_meaning` carries this onto every decision.

### Recommendations

`SEEK_PROMPT_MEDICAL_ADVICE` is deliberately **not** attached to an INDICATED
heart decision. Module 10 attaches it where precision at the cut-off is about
0.91; here it is 0.75. An urgency instruction on a 3-in-4 call would be
unsupported certainty, which spec §24 forbids. A weak model gets
`DISCUSS_WITH_CLINICIAN`. `GENERAL_SMOKING_CESSATION_SUPPORT` is attached only on
a *positively stated* current smoking history, never on an unknown one.

---

## Module 12 — the Kidney Disease model

`datasets/raw/chronic_kidney_disease_full.csv` — the official UCI Chronic Kidney
Disease archive (id 336), 400 rows, 25 attributes, converted from UCI's own ARFF
with `?` preserved as empty cells. UCI's units (`sc` mg/dL, `bgr` mg/dL, `hemo`
g/dL, `age` years) match `feature_catalog.py` exactly — **no unit conversion is
applied or needed**, and a test asserts that.

### Information sufficiency — the headline feature of this module

`required_features = ("creatinine", "hemoglobin")`. Without both, `predict()`
returns `INSUFFICIENT_DATA` with `risk=None` and `confidence=None`, and the model
is never reached.

The training script measures **all 30 usable feature subsets** by 5-fold CV
ROC-AUC and writes them into the metrics artifact:

| Feature set | CV ROC-AUC |
|---|---|
| all five | 0.9957 |
| **creatinine + hemoglobin** | **0.9860** |
| hemoglobin alone | 0.9611 |
| creatinine alone | 0.9095 |
| blood_glucose alone | 0.7380 |
| age alone | 0.5860 |

The pair carries essentially the whole model; the other three are a 0.010
refinement, which is why `blood_glucose`, `age` and `hypertension` are
**optional**. A predictor that skips too eagerly is not safer, only silent.

And the number that actually justifies the skip — **the shipped pipeline with one
input blanked at run time**, which is what really happens in production (the
ablation table above refits *without* the feature, which is strictly kinder):

| Blanked input | ROC-AUC | Δ |
|---|---|---|
| hemoglobin | 0.9622 | **−0.0360** |
| creatinine | 0.9910 | −0.0073 |
| blood_glucose | 0.9931 | −0.0051 |
| age | 0.9966 | −0.0017 |
| hypertension | 0.9979 | −0.0004 |

**Haemoglobin's case is made by the numbers. Creatinine's is not, and pretending
otherwise would be dishonest** — on this cohort the model barely misses it.
Creatinine is required anyway on **clinical rather than statistical grounds**:
serum creatinine is the analyte that *defines* renal function, and the only
reason haemoglobin can stand in for it here is that anaemia of CKD is
near-universal in this single-centre 399-patient cohort. A kidney prediction made
without creatinine would be an anaemia signal wearing a kidney label, and in a
screening population — where anaemia has many other causes — that substitution
would fail quietly and in the dangerous direction. The cost of the refusal is a
**skip**, which the reader sees, rather than a wrong answer, which they would not.

That is not a hole in the report: `Kidney Disease` is `always_assessed`, so
Module 8's creatinine rule still produces a decision. Only the ML opinion is
withheld.

### The malformed class label

Class values are `ckd` 250 / `notckd` 149 / **`no` 1**. **That row is dropped,
not repaired.** It is not merely mislabelled — the whole tail of the record is
shifted: `dm` is empty, `appet` holds `no` (documented domain: good/poor) and
`pe` holds `good` (domain: no/yes). Repairing the label would mean *guessing*
whether that patient had CKD, which is fabricating training data. **399 rows used
(250 ckd / 149 notckd).**

### Missingness

1,013 missing cells across 400 rows; among the five features used, `hemo` is
missing 52 times, `bgr` 44, `sc` 17, `age` 9, `htn` 2. **No row is dropped for
missingness** — with 399 rows that would gut the file and bias it towards
patients whose workup was complete, which correlates with being ill. Median /
most-frequent imputation is fitted **inside** the pipeline, per fold, exactly as
spec Module 12 describes.

### Only 5 of 24 attributes are used — a reported gap

The other 19 (blood urea, albumin, specific gravity, sodium, potassium, packed
cell volume, cell counts…) are real and useful, but **absent from
`app/data/feature_catalog.py`**, so VaidyaAI cannot supply them at prediction
time. Same principle as Module 11's blood-pressure exclusion. **Adding blood urea
and albumin to the feature catalogue is the obvious next improvement to this
module.** Also noted: `bgr` is *random* blood glucose while VaidyaAI's
`blood_glucose` prefers fasting where the report distinguishes them — recorded
rather than silently corrected.

### The tri-state — absent must never become "no"

Module 2's `hypertension` is TRUE / FALSE / ABSENT; the dataset has only
`yes` / `no`. Encoding absent as `no` would tell the forest the patient does not
have hypertension when nobody asked, and most-frequent imputation is the same act
with better manners (the majority value **is** `no`).

Two fitted pipelines, `with_hypertension` and `without_hypertension`; the latter's
ColumnTransformer has no hypertension column at all, not even an encoder.
`tests/test_kidney_predictor.py` asserts on the **actual DataFrame** that the
column is absent — and that `hypertension=False` is still included as a real
answer, which is the mirror bug.

### Evaluation (spec §11) — held-out test split, n = 100, prevalence 63.0%

| Metric | Value |
|---|---|
| **ROC-AUC** | **0.998** |
| **PR-AUC (average precision)** | **0.999** |

At the tuned decision threshold **0.411**:

| Class | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| Positive (CKD) | 0.969 | 0.984 | 0.976 | 63 |
| Negative | 0.972 | 0.946 | 0.959 | 37 |

Confusion matrix (rows = actual, columns = predicted):

|  | pred. negative | pred. positive |
|---|---|---|
| **actual negative** | 35 | 2 |
| **actual positive** | 1 | 62 |

**Accuracy 0.970 — against a majority-class baseline of 0.630.**

**5-fold stratified cross-validation** (training portion, scored at 0.5):

| Metric | Mean ± SD |
|---|---|
| ROC-AUC | 0.9957 ± 0.0040 |
| PR-AUC | 0.9976 ± 0.0023 |
| Recall | 0.9788 ± 0.0197 |
| Precision | 0.9845 ± 0.0206 |
| F1 | 0.9813 ± 0.0106 |

Global feature importance: `hemoglobin` 0.452, `creatinine` 0.255,
`hypertension` 0.188, `blood_glucose` 0.068, `age` 0.037.

### An honest read of whether this model is good

**The numbers are near-perfect and the dataset is the reason.** This is a
399-row, single-centre UCI cohort in which serum creatinine and haemoglobin
separate CKD from not-CKD almost cleanly. A ROC-AUC of 0.998 says *the separation
was easy*, not that the model would perform this way on a screening population.

**The test split is 100 patients.** One misclassification moves recall by about
1.6 points; a 95% binomial interval around 0.97 accuracy on n=100 spans roughly
0.91–0.99. The **cross-validated** figures are the trustworthy ones, and they
also show fold-to-fold spread (recall ±0.020) that the single test split hides.

**What is genuinely defensible:** the pipeline is honest about missing data, the
tri-state is handled without fabricating answers, and every claim above is
reproducible from the committed artifact. **Read the sufficiency skip — not the
accuracy — as this module's contribution.**

### Probability → risk cut-offs

Module 10's rule is **recorded but not applied**, and the artifact says what it
would have given (0.1116). The reason: this model reaches 0.90 cumulative
precision at threshold **0.11**, before it has committed to anything. That would
put 79% of the cohort in the INDICATED band and collapse BORDERLINE to nothing,
because the sensitivity-derived lower cut-off lands at the same 0.11. **A
non-binding criterion is not a criterion.**

Both cut-offs are therefore stated as **sensitivity guarantees**, which is the
quantity that matters when a missed case is the dangerous failure:

* **`indicated = 0.411`** — the *most precise* out-of-fold operating point still
  catching **98 of every 100** positives. Achieved precision 0.984, comfortably
  above Module 10's 0.90 floor, so that floor is honoured as well as superseded.
* **`borderline = 0.180`** — the *most selective* out-of-fold point still
  catching **99 of every 100**.

Measured band composition on the held-out split:

| Band | Patients | Positive | Rate |
|---|---|---|---|
| Low | 35 (35%) | 1 | 2.9% |
| Medium | 1 (1%) | 0 | 0.0% |
| High | 64 (64%) | 62 | 96.9% |

The middle band holds one patient because this cohort's scores are strongly
bimodal — the model is rarely uncertain about a UCI CKD patient. **A near-empty
BORDERLINE band is a property of this test cohort, not evidence that borderline
patients do not exist**, and `metadata.band_meaning` says so.

`SEEK_PROMPT_MEDICAL_ADVICE` *is* attached to an INDICATED kidney decision,
unlike Module 11's — the difference is measured, not stylistic: precision at the
cut-off is 0.97 held-out (0.98 out-of-fold) against Module 11's 0.75.

---

## Properties shared by both

* **Recommendations only by catalogue code.** No code path composes text;
  `recommendation_catalog.recommendation()` raises on an unknown code, so nothing
  either predictor can do emits unvetted medical wording. `NOT_A_DIAGNOSIS` is on
  every decision, including the skips.
* **Feature importances are global / model-level** and every decision says so in
  `feature_importance_caveat`. They order the evidence; they are never presented
  as a per-patient explanation.
* **Confidence is always P(positive)**, never "how sure the model is". A low
  number on a `Not Indicated` decision is a *confident negative*.
  `metadata.confidence_semantics` records this.
* **Thresholds are read from the artifact**, not hard-coded, and were selected on
  out-of-fold training predictions — the test split is never used for selection.
* **A missing or unreadable artifact is never fatal.** `is_available()` returns
  False, every decision becomes `INSUFFICIENT_DATA` with
  `skipped_reason="model_unavailable"`, and the introspection endpoint shows it.
* **Every metrics JSON records** dataset sha256 and row count, feature list,
  sklearn / numpy / pandas / joblib versions, timestamp, hyperparameters,
  decision thresholds and the **sha256 of the joblib it was produced from** — so
  a test proves the committed metrics describe the committed model.

### Retraining

```bash
python ml/train_heart.py     # ~6 min: 2 variants, 5-fold CV, ablation, BP reference
python ml/train_kidney.py    # ~1 min: 2 variants, 5-fold CV, all 30 feature subsets
```

Both are idempotent given the same dataset and `RANDOM_STATE`. Retraining rewrites
both the joblib and the metrics JSON; **commit them together**, or the
sha256-binding test fails — which is the point.

<!-- END MODULE 11-12 -->

<!-- BEGIN MODULE 15-16 -->

# Modules 15 & 16 — Decision Engine and Hybrid Decision Fusion Engine

> To be merged into `README.md` by the coordinator. Written to a separate file
> because another agent owns `README.md` concurrently.

```
Module 8  Clinical Rule Engine  ─┐
                                 ├─> collect_decisions()  ─> fuse_decisions() ─> Modules 17-20
Module 9/10-12 ML Predictors    ─┘        Module 15             Module 16
```

`POST /api/v1/decisions/fuse` · `GET /api/v1/decisions/policy`

## Files

| File | What |
|---|---|
| `app/schemas/fusion.py` | The Module 15/16 contract (new) |
| `app/services/decision_engine.py` | Module 15 — `collect_decisions`, `group_decisions`, the shared merge core (new) |
| `app/services/fusion_engine.py` | Module 16 — `fuse_decisions`, `run_decision_fusion` (new) |
| `app/api/routes_decisions.py` | The endpoint (new) |
| `app/schemas/decisions.py` | **Modified**: condition-vocabulary validator only |
| `tests/test_decision_engine.py` · `test_fusion_engine.py` · `test_decisions_endpoint.py` · `test_decision_vocabulary.py` | 150 new tests (new) |

**Mount line for `app/main.py`** (add the import to the existing `from app.api import (...)` block, then):

```python
app.include_router(routes_decisions.router)
```

Place it after `app.include_router(routes_ml.router)`. Until it is added,
`tests/test_decisions_endpoint.py` mounts the router itself at import time,
idempotently — the same pattern `tests/test_ml_endpoint.py` already uses — so
the route is covered by `tests/test_auth.py`'s recursive route walk either way.

---

## Module 15 — what the Decision Engine guarantees

1. **One source failing never loses the other's decisions.** Each of
   `evaluate_rules()` and `predict_all()` is called inside its own guard. A
   raise becomes a `SourceRunSummary(failed=True, error_type=...)` plus a
   warning; the other source's decisions come through untouched. Only the
   exception **type** is logged or reported — a model's exception message can
   echo input values, which are medical data.

2. **No upstream warning is ever dropped.** Modules 4/5/6/8/9-10 warnings are
   carried with `{stage, module, message}` intact and de-duplicated **on the
   whole triple**, so a warning both engines relayed appears once *with its
   original origin*, and two different stages that genuinely said the same
   thing still appear twice.

3. **Every decision gets a deterministic id**: `rules:diabetes:hba1c-high`,
   `ml:diabetes:diabetes-rf`, with `#2` on a genuine tie. Same input, same ids,
   every run — a UUID would make the grouping unauditable and Module 20's
   "trace this back to the exact rule" unverifiable.

4. **Grouping by `(condition, source)`** — the integration-audit requirement.
   HbA1c 6.8 + fasting glucose 112 makes the rule engine emit *two* correct
   `Diabetes` decisions. They collapse to **one group with `member_count=2`**,
   so fusion sees one `Clinical Rule Engine` entry, Module 19 counts the
   condition once, and the dashboard renders one card. Module 8 is unchanged;
   per-rule traceability is preserved in `collection.collected`.

---

## Module 16 — the six spec behaviours

| # | Spec | Implementation |
|---|---|---|
| 1 | Condition | grouped by exact string; enforced by the new vocabulary validator |
| 2 | Risk | `RiskLevel.highest()` — the type's own ordering; `highest([])` is `None`, never `LOW` |
| 3 | Confidence | max over contributors that produced one — see below |
| 4 | Evidence | union, de-duplicated by `EvidenceItem.dedup_key()` |
| 5 | Recommendations | union, de-duplicated by `Recommendation.dedup_key()`; **never invented** |
| 6 | Source | `sources` de-duplicated; `source_kinds` + `hybrid` say whether a rule *and* a model contributed |

### Status fusion (mine to design — the rule)

> A fused decision is `INSUFFICIENT_DATA` **only when no contributing decision
> actually assessed the condition**; its risk is then `None`. Otherwise the
> status is the **most severe status among the decisions that did assess**
> (`Not Indicated < Borderline < Indicated`) and the risk is the **highest**
> among them. A contributor that could not assess never downgrades the result,
> and is never silently discarded.

**Reasoning.** Two failure modes had to be excluded simultaneously.

*A rule fired, the model abstained.* If the abstention won, a real `Indicated /
High` finding would render as "insufficient data" — a genuine finding hidden
behind a missing model input. So abstentions are excluded from the status.

*Nothing assessed.* If a fused decision could present as assessed with nothing
behind it, an unreadable report would produce a reassuring card. So when the
assessed set is empty the result is `INSUFFICIENT_DATA` with `risk=None`, which
`ClinicalDecision` itself then enforces.

*The abstention still has to reach the reader.* It is recorded four ways:
`unassessed_sources`, `partially_assessed`, the fused decision's own
`metadata.unassessed_sources`, and a Module 16 warning that lands in
`all_warnings` — which is exactly what Module 17 renders as its validation
warnings. "The rules flagged this; the model could not assess it" is a
materially different statement from "both agreed".

Status and risk each take their own maximum independently, which is the
safety-conservative reading if a producer ever emits an unusual pairing.

### "Strongest available confidence", with `None` in play

> The **maximum over the contributors that actually produced a probability**.
> `confidence=None` means the component produces no probability at all (a
> deterministic rule) and is therefore **absent from the maximum** — never read
> as `0.0`, and never able to suppress a real probability from another source.
> `confidence=0.0` means a model *ran* and was maximally unconfident: it **is**
> a value and does take part, so a fused `0.0` is a real confident negative and
> stays distinct from `None`. When nobody produced a probability the fused
> confidence is `None`, never `0.0`.

`confidence_basis` says which case applied (`none_produced` /
`max_of_model_probabilities`), and each source's own number survives in
`contributions[].confidence` and `metadata.source_confidence`, so Module 17/20
never has to guess whose number the maximum was.

Additionally, a fused decision with status `INSUFFICIENT_DATA` carries
`confidence=None` unconditionally: no probability can describe a result that
nothing assessed.

### Evidence vs recommendations — a deliberate asymmetry

Evidence is taken from the **assessed** contributors whenever any assessed;
recommendations from **all** contributors. An abstaining model's evidence says
"this value was not available in the submitted report" about the very feature an
assessed rule has just quoted a number for — a contradiction in front of the
reader. A recommendation ("one analysis could not be completed") stays true
beside a finding, so it is unioned. When *nothing* assessed, the evidence **is**
the list of what was missing, and is kept.

---

## The `Heart Disease` semantic hazard

The composite clinical rule emits `Heart Disease` from a **count of recorded
risk factors** (burden). Module 11's predictor will emit it as an **estimated
likelihood** (probability). Renaming either breaks fusion — the one thing
Module 16 exists to do — so **neither is renamed and they still fuse**.

Instead:

* Every contribution carries a machine-readable `assessment_basis`
  (`risk_factor_count` / `threshold_comparison` / `model_probability` /
  `not_assessed`), derived from the producer's own metadata. **Module 11 can
  override it by setting `metadata["assessment_basis"]`**; the default for a
  model is `model_probability`.
* Each contribution keeps its producer's own wording verbatim in `band_labels`
  — the rule's "three or more major cardiovascular risk factors were counted",
  the model's `band_meaning` — so Module 17 can state what each source actually
  claimed rather than paraphrasing a status enum.
* When a **risk-factor burden** sits beside a different kind of claim, the fused
  decision sets `basis_conflict=True` and carries the fixed, safety-scanned
  `basis_note`; the condition is listed in
  `summary.basis_conflict_conditions` and a warning reaches `all_warnings`.
  **Module 17 should render those contributions side by side rather than as one
  blended sentence.**

Deliberately **not** flagged: a threshold comparison beside a model probability
(HbA1c + the diabetes model). Those are two *methods* of answering **one**
question, which is the normal hybrid case; caveating it would caveat
everything. Only the burden family conflicts — see `CONFLICTING_FAMILY` in
`app/schemas/fusion.py`.

---

## The condition-vocabulary validator

`ClinicalDecision(condition="diabetes mellitus", ...)` now raises. The message
names `app/data/conditions.py` and lists the permitted values.

**Circular imports: none, and it is structurally impossible to introduce one
accidentally.** `app/data/conditions.py` imports nothing from `app` (only
`dataclasses` and `typing`), and `app/data/__init__.py` is docstring-only. The
one module that could close a loop — `app/data/recommendation_catalog.py`,
which imports `Recommendation` *from* `decisions.py` — is a different module and
is never pulled in by `conditions`. The import is nonetheless kept
**function-local** inside the validator so that `decisions.py`, the most widely
imported module in the service, stays a leaf and none of its importers gains a
transitive dependency on the data package's import order. Cost: one lookup of an
already-cached module per construction.
`tests/test_decision_vocabulary.py` runs seven import orders in **fresh
interpreters** (plus a negative control proving the harness can fail), so a
future edit that does create a cycle fails loudly rather than depending on which
module happened to be imported first.

All existing producers already source their condition from `conditions.py`
constants; nothing broke.

---

## Output shape — Module 17 will be built against this

`POST /api/v1/decisions/fuse` → `{"success": true, "data": DecisionFusionData}`

```
DecisionFusionData
├─ fused: FusedDecision[]           # ONE PER CONDITION, canonical order
├─ collection: DecisionCollectionData   # Module 15's layer, nested verbatim
├─ warnings: str[]                  # Module 16's own
├─ upstream_warnings: StageWarning[]
├─ all_warnings: StageWarning[]     # <- Module 17's "validation warnings"
├─ upstream: UpstreamExtraction
├─ upstream_summary: FeatureValidationSummary
├─ summary: FusionSummary
└─ metadata: {...}
```

```
FusedDecision
├─ condition: str
├─ decision: ClinicalDecision       # source_kind = "fusion"; all invariants hold
├─ status / risk / confidence       # mirrors of decision.*, for convenience
├─ sources: str[]                   # DE-DUPLICATED
├─ source_kinds: DecisionSourceKind[]
├─ hybrid: bool                     # a rule AND a model both ASSESSED
├─ contributions: DecisionContribution[]
├─ decision_ids: str[]              # every raw decision fused here
├─ assessed_source_count: int
├─ unassessed_sources: str[]
├─ partially_assessed: bool
├─ confidence_basis: "none_produced" | "max_of_model_probabilities"
├─ assessment_bases: str[]
├─ basis_conflict: bool
├─ basis_note: str | null
├─ evidence_count: int
└─ recommendation_count: int

DecisionContribution                # ONE PER SOURCE — Module 20's trace
  source · source_kind · status · risk · confidence · assessment_basis
  decision_ids[] · traces[]         # rule ids / predictor names
  band_labels[] · evidence_features[] · recommendation_codes[]
```

```
FusionSummary
├─ fused_count · condition_count · hybrid_condition_count
├─ raw_decision_count · collapsed_decision_count
│  ── Module 18 ──
├─ overall_status: "Healthy" | "Needs Monitoring" | "Needs Medical Attention" | null
├─ overall_risk: RiskLevel | null
├─ any_assessed: bool · assessment_incomplete: bool
├─ critical_conditions[]   # flagged AND High
├─ abnormal_conditions[]   # Indicated or Borderline
├─ normal_conditions[]     # Not Indicated
├─ unassessed_conditions[] # Insufficient Data
│  ── Module 19 ──
├─ prioritized: PrioritizedCondition[]   # ONE ROW PER CONDITION,
│      {condition, status, risk, flagged, hybrid, sources[]}
│      flagged first, then High > Medium > Low, then canonical order
│  ── provenance ──
└─ sources_used[] · sources_failed[] · basis_conflict_conditions[]
   partially_assessed_conditions[] · partial_document · input_kind
```

```
DecisionCollectionData (Module 15)
├─ collected: CollectedDecision[]   # RAW, ungrouped, per-rule traceability
│     {decision_id, origin: "rules"|"ml", trace, band_label,
│      assessment_basis, decision}
├─ groups: DecisionGroup[]          # one per (condition, source)
│     {condition, source, source_kind, member_count, decision_ids[],
│      traces[], band_labels[], assessment_basis, assessed, decision}
├─ sources: SourceRunSummary[]      # {name, module, kind, ran, failed,
│                                      error_type, decision_count}
├─ warnings / upstream_warnings / all_warnings / upstream / upstream_summary
├─ summary: DecisionCollectionSummary
│     decision_count · group_count · condition_count · sources_run[]
│     sources_failed[] · conditions_assessed[] · conditions_flagged[]
│     highest_risk · multi_decision_groups[] · partial_document · input_kind
└─ metadata
```

### `overall_status` can be `null` — read it with `any_assessed`

The spec's Module 18 rule has three outcomes. It does not name the fourth case:
**nothing was assessed at all**. "No abnormal findings" is then vacuously true,
and rendering *Healthy* for a report whose every test was unreadable is exactly
the failure `decisions.py` calls the most dangerous this type can have. So
`overall_status` is `null` there, `any_assessed` is `false`, and
`assessment_incomplete` is `true`. Module 17 must handle the null — the three
named values are otherwise produced exactly as the spec specifies.

`assessment_incomplete` is also true when *some* conditions were unassessed, a
source failed, or any condition is `partially_assessed`, so Module 17 can
caveat an otherwise-clean status.

---

## Framework-independent surface (Module 17 calls these in-process)

```python
from app.services.decision_engine import collect_decisions   # Module 15
from app.services.fusion_engine import fuse_decisions, run_decision_fusion  # Module 16

collection = collect_decisions(validated, engineered=..., registry=...)
data       = fuse_decisions(collection)          # or fuse_decisions([ClinicalDecision, ...])
data       = run_decision_fusion(validated)      # both, in one call
```

`fuse_decisions` also accepts a bare `list[ClinicalDecision]` — it routes
through the same id assignment and the same grouping, so a stored analysis
cannot be fused by a different code path and quietly get a different answer.

Input tolerance is **inherited**, not re-implemented: `DecisionFusionRequest`
subclasses `RuleEvaluationRequest`, so `/decisions/fuse` accepts every shape
`/rules/evaluate` and `/ml/predict` accept and returns the same 422s on the same
ambiguities. A drift would not raise — it would be a 200 with `fused: []`.

Auth is the same `require_service_key` dependency as every other PHI-bearing
route.

---

## Known limits / not done

* **`app/main.py` is not modified** (file ownership). The mount line is above.
* **The rejected-feature join (audit item 3) is not implemented.** It belongs to
  Module 20 and touches Module 8's evidence construction, which this work does
  not own. Rejection reasons do reach `all_warnings` unchanged.
* **Input-coercion errors inside an engine are contained like any other
  failure**, so a malformed feature set passed *directly in-process* yields an
  empty result plus a `failed` source rather than an exception. Over HTTP this
  cannot happen: the request model validates the payload before the engines run
  (that is where the 422 comes from). Callers of `collect_decisions()` should
  check `summary.sources_failed`.
* Nothing here trains, hits the network, or needs an API key.

<!-- END MODULE 15-16 -->

<!-- BEGIN MODULE 17-20 -->

# Modules 17, 18, 19 & 20 — Clinical Report, Overall Health Status, Risk Prioritization, Evidence & Explainability

> To be merged into `README.md` by the coordinator. Written between markers
> because another agent owns `README.md` concurrently.

```
Module 16 fusion ─> generate_report() ─> Module 27 dashboard
                          │              Module 32 doctor summary
                          ├─ Module 18 overall_status()
                          ├─ Module 19 prioritise()
                          └─ Module 20 build_explainability()
```

`POST /api/v1/report/generate` · `GET /api/v1/report/policy`

## Files

| File | What |
|---|---|
| `app/schemas/report.py` | The Module 17–20 contract (new) |
| `app/services/report_builder.py` | `generate_report`, `overall_status`, `prioritise`, `build_explainability`, `extract_rejected_features`, `report_text_violations` (new) |
| `app/api/routes_report.py` | The endpoint (new) |
| `tests/test_report_builder.py` · `tests/test_report_endpoint.py` | 68 new tests (new) |

**No existing file was modified.**

**Mount line for `app/main.py`** (add `routes_report` to the existing
`from app.api import (...)` block, then):

```python
app.include_router(routes_report.router)
```

Place it after `app.include_router(routes_decisions.router)`. Until it is
added, `tests/test_report_endpoint.py` mounts the router itself at import time,
idempotently — the same pattern `tests/test_decisions_endpoint.py` uses — so
the route is covered by `tests/test_auth.py`'s recursive route walk either way.

## Module 18 — the overall health status, including the case the spec omits

The specification names three outcomes. There is a fourth, and it is the
dangerous one.

| Case | Rule id | `status` | `status_label` |
|---|---|---|---|
| Nothing could be assessed | `nothing_assessed` | `null` | **`Not Assessed`** |
| Assessed, no abnormal finding | `no_abnormal_findings` | `Healthy` | `Healthy` |
| Abnormal finding, no High risk | `abnormal_without_high_risk` | `Needs Monitoring` | `Needs Monitoring` |
| Abnormal finding + High risk | `abnormal_with_high_risk` | `Needs Medical Attention` | `Needs Medical Attention` |

**Why the fourth case exists.** "No abnormal findings ⇒ Healthy" is *vacuously
true* for a report whose every test was unreadable, in exactly the way an empty
set has no members. Rendering that as `Healthy` would tell a reader whose
document could not be read that they are well — the same failure class as an
`INSUFFICIENT_DATA` decision carrying a risk level, which `decisions.py`
forbids at the type level and calls "the most dangerous failure mode this type
can have". So `status` stays `null` (a consumer that knows only the spec's
three vocabulary values cannot silently read it as one of them) and
`status_label` is a fourth word that is not one of them.

**The fifth case: partial assessment.** When *some* topics could be assessed
and others could not, the status of what *was* assessed is kept — downgrading a
clean partial report to `Needs Monitoring` would report a finding nobody made,
which is its own fabrication. The incompleteness is made **structural instead
of editorial**:

* `complete: false` — machine-readable, a renderer cannot miss it
* `caveat` — fixed reviewed wording, **non-null exactly when `complete` is false**
* `unassessed_conditions` — named, so the gap is specific rather than a vague hedge
* a `stage: "report"` warning saying the same thing

`overall.status` is taken from Module 16's `summary.overall_status` rather than
recomputed; the branch is re-derived only to record *which* rule fired, and a
disagreement between the two layers raises rather than being papered over.

## Module 19 — prioritisation, by condition

Sort key: `(tier, risk, canonical condition rank)`. **Decision count is not in
it.**

| Tier | Contents | Order within tier |
|---|---|---|
| 0 | Flagged findings | High → Medium → Low |
| 1 | **`Not Assessed`** | canonical order |
| 2 | Normal findings (assessed, nothing flagged) | High → Medium → Low |

* **By condition, never by decision count.** The rule engine emits one decision
  per *rule*, so a patient with HbA1c 6.8 *and* fasting glucose 112 produces two
  `Diabetes` decisions. Prioritisation reads Module 16's `fused` — already one
  per condition — and counts nothing. `contributing_decision_count` is carried
  for display and is deliberately absent from the sort key.
* **An unassessed condition is not a low-risk condition.** It has `risk: null` —
  not "low", *none*. It gets its own band, above every settled normal finding
  and below every flagged one: a flagged Low-risk finding is still a finding and
  somebody looked, whereas "we looked and found nothing" is settled and "we
  could not look" is an open question that must not be buried under settled ones.

## Module 20 — the rejected-feature join (audit §6h item 3)

Module 6 keeps a value it refuses (`rejected`, with `reason_code` and `reason`)
rather than deleting it. Modules 8 and 9/10 never parse that map — that absence
is what makes "a clinical rule can never read a rejected value" *structural* —
so their evidence says `"this value was not available in the submitted report"`,
which is **factually wrong**: the value was in the report, it was read, and it
was refused.

This layer is the first that holds both halves, so this is where they are
joined. Every evidence item becomes an `EvidenceLine` with:

| `availability` | Means |
|---|---|
| `observed` | read and used |
| `not_present_in_report` | genuinely absent |
| `unreadable_document` | may be missing rather than absent |
| **`found_but_not_trusted`** | **read, and refused** |

For a rejected feature the line carries `rejection_code`, `rejection_reason`,
the value that was actually printed (`rejected_value` / `rejected_unit`), and
the `validation`-stage warnings that name it — origins intact. The producer's
original `note` is preserved **unedited**, so the trace back to what Module 8
actually said survives; only `availability` and `explanation`, which are what a
renderer shows, are corrected. A feature that really was absent still reads as
absent. `explainability.rejected_features_joined` lists every correction, so
the join is auditable.

A rejected value also still appears as a **laboratory row** with
`usable: false` — hiding it would reproduce the same defect one layer up,
leaving a reader to conclude the test was never ordered.

## Module 20 — ML explanations are not overstated

Module 10/11/12 feature importances are **mean impurity decrease over the whole
training set**, and every artifact says so in its own metadata. They rank
features *for the model* and they are why the evidence is ordered as it is.
They are **not** a per-patient reason, and spec §24 forbids unsupported
certainty. So `MLExplanation` carries:

```
importance_scope:            "global_model_level"
importance_is_per_patient:   false          <- a literal false on the wire
importance_caveat:           the predictor's own caveat, verbatim
```

`probability_semantics` says the same about the probability: an estimate from
records resembling this one, not a measurement of this person.

## Module 17 — the report shape

`ClinicalReport` (pydantic v2, `extra="forbid"`), section order following the
spec's own list:

| Field | Type | Notes |
|---|---|---|
| `report_version`, `generated_at` | — | |
| `patient` | `PatientInformation` | age / gender / bmi / tri-states / smoking. **No identity fields exist**; `contains_identity` is always `false` |
| `laboratory_values[]` | `LaboratoryValue` | value, unit, reference range, lab flag, original printed test name, page, extraction confidence, `status` ∈ valid/questionable/rejected, `usable` |
| `conditions[]` | `ReportedCondition` | one per condition, in priority order; `contributions[]` side by side |
| `overall` | `OverallHealthStatus` | Module 18 |
| `overall_risk` | `RiskLevel?` | `null` when nothing assessed |
| `critical_conditions[]`, `abnormal_findings[]`, `normal_findings[]`, `unassessed_conditions[]` | `str[]` | |
| `prioritized[]` | `PrioritizedFinding` | Module 19 |
| `explainability` | `ExplainabilitySection` | Module 20 |
| `recommendations[]` | `ReportRecommendation` | consolidated, de-duplicated, catalogue-sourced |
| `document` | `DocumentQuality` | `pages_unreadable`, `extraction_confidence`, `partial_document`, rejected/missing feature names |
| `validation_warnings[]` | `StageWarning` | **every** stage, origins intact |
| `warnings_by_stage` | `dict[str,int]` | |
| `summary` | `ReportSummary` | counts for a page header |
| `metadata` | `dict` | versions, policies, `input_received` |
| `fusion` | `DecisionFusionData` | Module 16 **nested verbatim**, and through it Module 15's collection |

The report is a **view, not a replacement**: `fusion` is carried whole, so
Module 32 and Modules 28–30 can always reach the exact rule, model or raw
decision behind any line above.

### Recommendations

Consolidated across conditions and de-duplicated by catalogue code, and the
**text is re-read from `app/data/recommendation_catalog.py` by code** rather
than copied from the decision that carried it. So no wording that is not in the
reviewed, import-time-scanned catalogue can reach a report even if some producer
constructed a `Recommendation` with its own string. A code that is not in the
catalogue is dropped **with a warning** — the safe direction, and not silent.
`report_text_violations(report)` scans every user-facing string with the safety
scanner and is asserted empty over four different reports, plus a negative
control proving the scanner can still fail.

### `basis_conflict` is surfaced, not blended

Where Module 16 flagged that a risk-factor *burden* sits beside a different kind
of claim (the `Heart Disease` hazard), `ReportedCondition.contributions[]`
carries each source separately with its **own** band labels, status and risk,
`render_contributions_separately: true` states the obligation in a field, and
`basis_note` carries Module 16's fixed wording. Merging them into one sentence
would tell the reader a tally was a probability.

## Endpoint

`POST /api/v1/report/generate` accepts **byte-for-byte what `/decisions/fuse`
accepts** — `ClinicalReportRequest` subclasses `DecisionFusionRequest`
subclasses `RuleEvaluationRequest`, so the tolerances cannot drift and every
ambiguity is the same 422. Nothing is guessed: a wrong guess here would not
raise, it would return HTTP 200 carrying an empty report.

The route additionally lifts Module 6's `rejected` map out of the **raw body**
(`extract_rejected_features`), because the decision chain's request models
deliberately do not parse it. The rules and the models still receive exactly
what they received before — an object with no `rejected` attribute to read.

`Depends(require_service_key)` on the router, exactly as `routes_decisions.py`
does.

When Module 5 output is posted, this layer runs Module 6 **in-process** first,
so the report's laboratory values and its rejected map are the real ones rather
than an approximation. `metadata.input_received` records what the caller sent;
`summary.input_kind` records what the decision chain saw. A test asserts that
posting Module 5 output and posting Module 6 output produce the same clinical
outcome.

## In-process API (Modules 27/32 and the backend)

```python
from app.services.report_builder import (
    generate_report, overall_status, prioritise, build_explainability,
)

report = generate_report(validated_data)                 # Module 6 output
report = generate_report(engineered=module_5_output)     # Module 6 run here
report = generate_report(fusion=stored_fusion_data)      # no re-prediction
card   = overall_status(fusion_data)
rows   = prioritise(fusion_data.fused)
why    = build_explainability(fusion_data, rejected_map)
```

## Tests

68 new, `pytest`, no API key, no network, no training. All previously existing
tests still pass.

## Known limits, stated plainly

* **`generate_report(fusion=...)` cannot recover laboratory values**, because
  Module 16's output carries decisions, not values. Passing a stored fusion
  gives the full status / priority / explainability layers with an empty
  `laboratory_values` and an empty rejected map. Pass `validated` alongside it
  when the values are wanted.
* **The warning⇄feature join is exact-substring on the feature name**, and it is
  applied only to features that are actually in the rejected map. A broad match
  across all features would attach a `hemoglobin` warning to an `hba1c` line,
  and a wrong join is worse than no join. The authoritative half of the join is
  the rejected map itself, not the warning text.
* **`overall_status()` raises if it disagrees with Module 16's summary.** That
  is deliberate — two layers reporting different overall statuses is not a
  condition to degrade gracefully through — but it means a hand-built
  `DecisionFusionData` with an inconsistent `summary` will raise rather than
  return.
* Modules 28–30 (trends) and Module 32 (doctor summary) are **not** built here.
  Nothing blocks them: every value, reference range, model prediction and raw
  decision they need is already in the report or in the nested `fusion`.
* Nothing here trains, hits the network, or needs an API key.

<!-- END MODULE 17-20 -->

<!-- BEGIN MODULE 21-22 -->

## Modules 21-22 — Medical Knowledge Base and RAG

Module 22 is the curated corpus. Module 21 chunks, indexes and retrieves from
it. Together they are spec section 12:

```
Documents -> Chunking -> Embeddings -> Vector Index -> Query
          -> Similarity Search -> Relevant Chunks -> LLM Prompt (Module 23)
```

### Layout

| Path | What it is |
| --- | --- |
| `app/data/knowledge_types.py` | The `KnowledgeDocument` type and topic vocabulary |
| `app/data/knowledge_documents/` | **The corpus.** Seven files, one per topic area |
| `app/data/knowledge_base.py` | Assembly, accessors, and the import-time self-check |
| `app/data/knowledge_safety.py` | The corpus intake scanner |
| `app/rag/chunking.py` | Paragraph chunking, two-field chunks |
| `app/rag/embeddings.py` | Tokenising, TF-IDF, cosine, the domain gate |
| `app/rag/index.py` | Index build/load/persist, similarity search, the floors |
| `app/rag/query.py` | Finding-driven query construction |
| `app/rag/retriever.py` | `retrieve()` / `build_index()` — the in-process API |
| `app/rag/schemas.py` | Pydantic v2 request/response contract |
| `app/api/routes_knowledge.py` | HTTP wrapper, service-key protected |
| `knowledge/build_index.py` | The re-runnable build script (`--check` for CI) |
| `knowledge/artifacts/knowledge_index_v1.json` | **The committed index** |
| `knowledge/evaluate_embeddings.py` | The retrieval evaluation harness |

### Module 22 — the corpus

**62 documents, 377 paragraphs, 243 chunks.** Content lives in reviewable data
files, not embedded in code — the same principle as `clinical_rules.py` and
`recommendation_catalog.py`. Every document carries its topic, the canonical
features and conditions it relates to, its **basis** (the guideline it
reflects), and a last-reviewed date.

Coverage is complete and enforced at import — all 14 canonical features and all
13 canonical conditions have documents:

| Topic | Docs |
| --- | --- |
| `health_condition` | 13 (one per entry in `conditions.py`) |
| `lifestyle_guidance` | 12 (Module 26's pre-approved material) |
| `reference_information` | 9 (the published bands) |
| `laboratory_test` | 8 (one per lab feature) |
| `terminology` | 8 (Module 25 reads these) |
| `general_interpretation` | 6 |
| `educational_explanation` | 6 (the profile features) |

**Vocabulary alignment is load-bearing, not tidiness.** Feature and condition
names are checked byte-for-byte against `feature_catalog.py` and
`conditions.py` at import. A document tagged `"diabetes"` instead of
`"Diabetes"` is not untidy — it is *invisible* to retrieval, silently never
joining the finding it exists to explain. So a typo fails the service at
startup.

#### Safety

The corpus is what an LLM is grounded on, which **inverts** the usual safety
argument: elsewhere an unsafe string is a bug in one output; here it is a bug
in every output that retrieves it, and a grounded model reproduces its sources
*faithfully*. Module 24 is the last line of defence, not the first.

Two independent gates, and the corpus passes both:

1. **`knowledge_safety.py`, at import time.** Scans every reader-visible field
   of every document. A violation raises and the service refuses to start —
   never a warning, never a silently dropped document. A `_self_check()` canary
   asserts the scanner still fires on an obviously unsafe sentence, so it
   cannot be quietly broken.
2. **Module 24's `validate_text`, asserted by `tests/test_knowledge_base.py`.**
   All **1027** corpus strings pass. This is the authoritative cross-check —
   see "Two scanners" below.

**Reviewed exemptions.** Exactly one document (`cond_diabetes`) holds one
exemption, for `medication_name`: diabetes is *defined* by insulin, and a
corpus that cannot use the word cannot explain the condition. An exemption
requires a written justification, may only name a pattern in
`EXEMPTIBLE_PATTERNS`, relaxes nothing else, and is re-checked by
`scan_administration` so the noun is permitted while any instruction to take it
is still refused. Exemptions are surfaced in `knowledge_base_document()` and in
`GET /documents/{id}` so an audit sees every carve-out and why.

### Module 21 — retrieval

#### Chunking

One chunk per **authored paragraph**, not a fixed-width window. The corpus was
written with one idea per paragraph and an explicit instruction that each stand
alone; that is a semantic boundary a human put there. A sliding window ignores
it and produces chunks that begin mid-sentence and straddle two ideas — exactly
the chunk that, handed to an LLM, yields a confident sentence built from half of
one claim and half of another. Fixed windows earn their place on scraped text;
this corpus is not that.

Each chunk carries two texts, scored separately: `text` (the paragraph, what a
reader sees) and `retrieval_text` (paragraph + document title, keywords and
tags). A paragraph of `ref_hba1c_bands` may say "from 5.7 % up to 6.4 %" without
containing the word "HbA1c" — the enriched surface finds it; the reader still
sees only the paragraph.

#### Embedding choice — measured, not asserted

Evaluated on 30 positive and 5 negative realistic queries
(`knowledge/evaluate_embeddings.py`), same chunks both times:

| | Recall@1 | Recall@3 | Recall@5 | MRR | P@3 |
| --- | --- | --- | --- | --- | --- |
| **TF-IDF (shipped)** | 0.733 | 0.900 | 0.900 | 0.806 | 0.578 |
| all-MiniLM-L6-v2 | **0.967** | **0.967** | **0.967** | **0.971** | **0.678** |

**The neural model is better, and materially so at rank 1.** Any claim of parity
would be false. What the decision rests on is narrower: at k=5, where Module 23
takes its grounding, the gap is roughly one query in thirty.

Against that, the neural option costs PyTorch (~2.5 GB), a first-use weights
download, and the offline-test guarantee this suite requires. It is not
theoretical friction — installing it here **failed first time on the Windows
260-character path limit**. Query-time embedding needs the model in-process, so
committing vectors does not avoid it.

Lexical holds up as well as it does because of *this* corpus, not lexical
retrieval generally: queries are built from canonical vocabulary by
`query.py`, and the corpus is tagged with those same strings by construction.
The hardest problem embeddings solve is largely designed out before retrieval.

**FAISS was not used.** It earns its place across millions of vectors; over 243
chunks an exhaustive dot product is faster (no index overhead) and *exact*,
where FAISS's approximate indexes trade recall for unneeded speed. If the corpus
ever justifies it, the change is confined to `index.py::search`.

#### The two floors

Retrieval returns **nothing** rather than something irrelevant. Two independent
gates catch different failures:

**`DOMAIN_COVERAGE_FLOOR = 0.40`** — is the question about this corpus at all?
Measured as the fraction of query tokens present in the corpus vocabulary.

This exists because the similarity floor provably cannot do the job. A nonsense
query collapses, after stopword and vocabulary filtering, to a single term, and
the unit query vector then points entirely at that one word: *"why does my
python script raise a KeyError on line 40"* scored **0.204** on the shared word
"raise" — above eight genuine medical queries. Coverage separates them cleanly
because it looks at what was *discarded*:

```
negatives   0.00, 0.00, 0.00, 0.17, 0.25
positives   0.67, 0.75, then 1.00 for the other fourteen
```

A wide empty gap, so 0.40 is robust rather than tuned.

**`SIMILARITY_FLOOR = 0.12`** — on-topic, but does anything match well enough?
Sweep over the eval set:

| floor | Recall@3 | P@3 | negatives excluded |
| --- | --- | --- | --- |
| 0.05 | 1.000 | 0.611 | 5/5 |
| 0.10 | 0.967 | 0.600 | 5/5 |
| **0.12** | **0.900** | **0.578** | **5/5** |
| 0.15 | 0.767 | 0.522 | 5/5 |
| 0.20 | 0.667 | 0.478 | 5/5 |
| 0.30 | 0.467 | 0.400 | 5/5 |

0.12 keeps genuine matches while discarding weak ones; by 0.15 real matches for
short single-feature queries start disappearing.

#### Result diversity

`MAX_CHUNKS_PER_DOCUMENT = 2`. Without it one document monopolises the result:
on the spec's own example, three of the top five chunks came from
`cond_diabetes` and the two documents holding the actual thresholds did not
appear. Measured mean per query over the 30 positives:

| cap | distinct docs in top-5 | *relevant* docs in top-5 |
| --- | --- | --- |
| 1 | 3.90 | 2.10 |
| **2** | **2.93** | **1.87** |
| none | 2.67 | 1.70 |

A cap of 1 maximises both; 2 is the default because paragraphs of one document
are complementary (what a test is / what its bands are), so a genuinely
best-matching document earns a second. Set to 1 to prefer breadth.

#### Known limitation — read before relying on free text

**TF-IDF cannot tell a medical question this corpus covers from one it does
not.** The domain gate catches non-medical questions; nothing catches a medical
question about an analyte outside the fourteen canonical features. Measured top
scores for questions about TSH, ferritin, white cell count, ALT, PSA and CRP:

| | uncovered questions | covered questions |
| --- | --- | --- |
| TF-IDF | 0.141 – 0.271 | 0.121 – 0.27 (**overlapping**) |
| all-MiniLM | 0.332 – 0.453 | 0.595 – 0.691 (**cleanly separated**) |

No floor fixes this: the ranges overlap completely, because generic medical
prose ("level", "result", "raised") is shared between any two medical topics.
In practice *"what does my TSH result mean"* retrieves triglyceride content at
0.187. **This is the one place the lexical choice is materially worse, and the
difference is a safety difference, not a quality one.**

It is bounded by how the platform calls this module: Module 23 retrieves from
**findings**, which are always canonical, so the primary path cannot ask about
an uncovered analyte. The exposure is the secondary free-text path — Module 25
should map a term to a canonical feature before asking rather than passing raw
user text through.

Two other measured misses, both lay free-text: *"sugar disease"* to
`life_added_sugar` (lexical "sugar" beats the tagged synonym) and *"slightly
above the range"* to `profile_bmi_derived`.

### The index

Built by a **separate, re-runnable script**, never at import or request time —
the `ml/` pattern, for the same reasons:

```bash
python knowledge/build_index.py           # writes the committed artifact
python knowledge/build_index.py --check   # asserts it matches a fresh build (CI)
python knowledge/evaluate_embeddings.py   # re-run the measurements above
```

The artifact is **JSON, not a pickle**: it describes a curated medical corpus
and a reviewer should be able to open it, and unlike the scikit-learn artifacts
it cannot be invalidated by a library upgrade. The build is deterministic —
`--check` proves the committed index is the one the committed corpus produces.

**Staleness is detected, not assumed away.** The artifact stores a SHA-256
fingerprint of every document. Loading an index that disagrees with the live
corpus raises `StaleIndexError` rather than silently serving old text under
provenance pointing at the current document — a citation that does not say what
the cited document says.

### API

In-process (how Modules 23 and 25 will call it — no FastAPI import):

```python
from app.rag import retrieve, build_index

chunks = retrieve(conditions=["Diabetes"], features=["hba1c", "blood_glucose"])
for c in chunks:
    c.chunk.doc_id, c.chunk.basis, c.score      # full provenance travels with it
```

Over HTTP — **every route carries the service-key dependency**:

| Route | Purpose |
| --- | --- |
| `POST /api/v1/knowledge/retrieve` | Retrieval, by finding and/or free text |
| `GET /api/v1/knowledge/index` | Index stats and the retrieval policy |
| `GET /api/v1/knowledge/coverage` | Which vocabulary the corpus covers |
| `GET /api/v1/knowledge/documents` | Browse the corpus (filterable) |
| `GET /api/v1/knowledge/documents/{id}` | One document in full |

These return no PHI, but a **retrieval request is itself PHI in the other
direction** — `{"conditions": ["Diabetes"], "features": ["hba1c"]}` is a
clinical statement about a patient — so the router is protected at router level.

Every retrieved chunk carries `chunk_id`, `doc_id`, `title`, `topic`, `basis`,
`features`, `conditions`, `last_reviewed`, and the score split into its
`text_score` and `tag_score` components, so Module 23 can cite it and a reader
can see *why* it was selected. An empty result is a successful 200 with
`grounding_available: false` — "there is no good grounding for this" is a real
answer, not an error.

### Two scanners — reconciliation still outstanding

`app/data/knowledge_safety.py` and `app/data/recommendation_catalog.py` carry
**separate implementations** of the same idea, and Module 24 now carries a
third, richer one. This is reported, not hidden.

The corpus is held to **Module 24's validator** as the authoritative gate
(`tests/test_knowledge_base.py` asserts all 1027 strings pass), so the two are
in agreement and any drift becomes a red test rather than a rejected generation
in front of a user. `knowledge_safety.py` remains the **import-time intake**
gate because it does things Module 24's does not need to: whitespace
normalisation, `scan_administration`, and the reviewed-exemption mechanism.

A full merge should keep the strictly-wider union — Module 24's rule table and
severities as the vocabulary, plus this module's intake-specific extras
registered against the same codes. It must not keep whichever list is shorter.

**One defect found and fixed here that the sibling scanners share:** patterns
containing literal spaces (`you have`, `not a diagnosis`) were evaluated against
raw wrapped prose, so a line break both *disarmed* detection (`"you\nhave
diabetes"` matched nothing) and *falsely tripped* the disclaiming carve-out
(`"not a\ndiagnosis"` was rejected). `knowledge_safety.normalise()` collapses
whitespace before scanning. `recommendation_catalog.py` has the same latent
defect — not live there, since its entries are short single-line strings, but
any merge must carry the fix.

### Tests

`tests/test_knowledge_base.py`, `tests/test_knowledge_index.py`,
`tests/test_knowledge_endpoint.py` — **407 tests, no network, no API key, no
model download.** They cover chunking, index build determinism and the
byte-identity of the committed artifact, staleness refusal, finding-driven
retrieval, both floors returning empty rather than junk, provenance
completeness, vocabulary alignment in both directions, the corpus self-check
catching a planted unsafe document, exemption abuse, and Module 24 agreement.

<!-- END MODULE 21-22 -->

<!-- BEGIN MODULE 23-26 -->

## Modules 23, 25 and 26 - Patient Explanation, Terminology, Lifestyle Guidance

Module 23 is the **first component in this system that puts unreviewed prose in
front of a patient.** Everything before it emits structured objects or text a
human wrote into `app/data/`. Modules 25 and 26 sit alongside it and are
deliberately much more conservative.

### The architecture (spec section 14)

```
Structured findings + retrieved knowledge  ->  LLM  ->  Safety Validation  ->  Approved response
```

and never

```
LLM output  ->  shown to patient
```

`app/services/explanation.py` implements the top row. **Every generation goes
through Module 24's `guarded_generation()`** - it is imported, not
reimplemented - and `PatientExplanation.explanation` is assigned in exactly one
place, from `GuardedGenerationResult.approved_text`, which is `None` unless the
safety layer approved the text. The refused text is discarded inside
`guarded_generation` and this module never holds it.

That property is tested three ways: behaviourally (a planted unsafe paragraph
must not appear anywhere in the serialised response), structurally (the test
suite reads the source and asserts the only values ever assigned to
`explanation=` are `None` and `guarded.approved_text`), and by call-site count
(`.generate_text(` appears at most once per service module).

### Files

| File | What it is |
|---|---|
| `app/prompts/explanation_prompt.py` | The prompts, in their own reviewable module, like `extraction_prompt.py`. `PROHIBITIONS` is the reviewed list and is **interpolated** into the prompt, so the list and the sent text cannot drift. |
| `app/services/gemini_text.py` | `GeminiTextClient(GeminiClient)` - **subclasses** the Module 4 client and adds one method, `generate_text`. No second client, no duplicated retry/timeout/error-taxonomy logic. Temperature pinned at 0.2. |
| `app/services/explanation.py` | Module 23. `explain_feature`, `explain_report`, `explain_terminology_entry`. Framework-independent. |
| `app/services/terminology.py` | Module 25. Exact term mapping, curated answers. |
| `app/services/lifestyle.py` | Module 26. Catalogue only; no model. |
| `app/api/routes_explain.py` | The HTTP layer. Thin wrapper, service-key dependency on the router. |

### Endpoints

```
POST /api/v1/explain/feature     Module 23 -- explain one canonical parameter
POST /api/v1/explain/report      Module 23 -- explain a Module 17 report
POST /api/v1/explain/term        Module 25 -- explain a term, or refuse it
GET  /api/v1/explain/terms       Module 25 -- covered vocabulary + known gaps
POST /api/v1/explain/guidance    Module 26 -- educational lifestyle guidance
GET  /api/v1/explain/policy      what all three do and refuse to do
```

All six carry `Depends(require_service_key)` on the router, exactly as
`routes_report.py` does.

### What the model is and is not given

The prompt receives the **structured findings** (parameter, the patient's
validated value, reference bounds, the interpretation the analysis already
reached, contributing conditions) and the **Module 21 retrieved chunks**, each
labelled with its `doc_id`, `topic` and `basis`. It receives no raw report
text, nothing the patient typed, and no medical knowledge beyond those chunks.

Module 24 enforces **numeric grounding**, so the prompt also carries an explicit
`PERMITTED NUMBERS` block - the patient's own value and the reference bounds -
and forbids numbered lists, approximations and unit conversions, each of which
would produce a number the validator cannot find in the sources. When no
numbers are permitted the prompt says *write no digits at all*.

`permitted_numbers` is built from validated values only. Callers that hold
rule-table thresholds can vouch for them explicitly via
`additional_permitted_numbers`; nothing is harvested automatically from a
free-text label.

### Refusal, and what the patient sees

Five outcomes, all of which return HTTP 200 with the structured fallback:

| `outcome` | When | Model called |
|---|---|---|
| `generated` | approved | yes |
| `withheld_by_safety` | Module 24 rejected both attempts | yes |
| `not_grounded` | Module 21 returned nothing above its floor | **no** |
| `model_unavailable` | no `GEMINI_API_KEY`, or the model failed | no / failed |
| `unknown_subject` | the feature is not canonical | **no** |

There is no empty screen and no silent substitution: every non-generated
outcome carries `safe_fallback()` - `generated_explanation_available: false`,
the reviewed notice, and the catalogue recommendations - plus the retrieval
provenance, so a reader can still see what the analysis was working from. The
violation **codes** are reported; the refused text and the offending span never
are.

**Retries.** `guarded_generation(attempts=2)`. A second attempt happens only
after a *safety rejection*, and only with a **different prompt**: the violated
codes, reasons and offending spans are quoted back. A transport failure is not
retried here, because `GeminiTextClient` already retried it with backoff.

**A live-only failure mode worth knowing about.** `gemini-3.6-flash` is a
thinking model, and its reasoning tokens are drawn from `max_output_tokens`
before any prose is emitted. The first live run returned
`MODEL_RESPONSE_TRUNCATED` on every call with a 700-token cap. The cap is now
4096 with a low thinking level. No offline test could have found this - a
mocked client has no thinking budget - which is the argument for the opt-in
live test existing at all.

### Module 25 and the TF-IDF coverage hazard

**This is the most important design decision in these three modules.**

The shipped retriever is TF-IDF. The Modules 21/22 build measured that terms
the corpus does **not** cover (TSH, ferritin, WBC, ALT, PSA, CRP) score
0.141-0.271, while terms it **does** cover score 0.121-0.27. Those ranges
overlap completely - **no similarity floor separates them.** "what does my TSH
mean" retrieves triglyceride content and scores it respectably.

Module 23 is insulated because it retrieves from canonical findings, whose
vocabulary is in the corpus by construction. **Module 25's free-text path is
the exposure**, so it does not retrieve on free text at all:

```
term  ->  EXACT mapping to a canonical feature or a named document
      ->  maps:        serve THAT document
      ->  does not:    say the term is not covered. Stop.
```

The mapping is exact-key lookup against tables the platform already maintains -
`feature_catalog`'s synonym index via `lookup_test_name`, canonical feature
names by dictionary membership, plus a small curated `TERM_ALIASES` table for
terms the corpus covers that are not features (eGFR, LDL, HDL, reference range,
fasting sample, anaemia, risk factor, mg/dL). No similarity, no threshold, no
nearest match, no fallback to search. `_self_check()` verifies at import that
every alias names a document that exists and that every advertised term
actually resolves.

The default answer is **served from the curated corpus**, not generated: the
Module 22 text was written for patients and scanned at import, and an LLM
rewriting it adds only a hallucination surface. `simplify=true` opts into a
generated rewrite of that same curated text, gated by the identical
`guarded_generation`; if it is refused, the curated text is served instead.

**Accepted cost, stated openly.** The spec names SGPT, and the corpus holds no
liver document, so **SGPT is refused.** That is a Module 22 content gap, and
the honest failure is a refusal rather than an explanation of the nearest
unrelated test. `GET /api/v1/explain/terms` publishes `known_gaps`.

The refusal message is the one place a human-typed string reaches
patient-facing output. It is filtered to a conservative character set, capped,
**and the finished sentence is put through Module 24**; if the echo makes it
unsafe - which is what an injection through the `term` field looks like - the
echo is dropped from the whole response and an anonymous refusal is used.

### Module 26 serves catalogue text and calls no model

The spec asks for "**pre-approved** educational guidance rather than
unrestricted AI-generated medical treatment advice", and this is the module
most likely to drift into treatment advice. The safety property that has held
across this project is structural: **recommendation text has no free-text entry
point.** `recommendation(code)` takes a code, every entry is scanned at import,
and an unsafe addition is an `ImportError` rather than a bad report. Adding a
generator here would be the first crack in that property, in the module where
it matters most - and generation buys nothing, because the catalogue already
holds the guidance the spec lists in reviewed wording.

The codes are not a mapping invented for this module. They are read from
`clinical_rules.py`'s **`always_recommend`** sets - the guidance attached to a
*topic* - and never the band-specific recommendations, which depend on how
abnormal a particular value was. `EDUCATIONAL_CODES` is computed at import and
is the complete reachable set through *every* entry point, including the
explicit `codes` parameter, so a risk-tier sentence such as
`SEEK_PROMPT_MEDICAL_ADVICE` cannot be fetched and presented as general advice.
`lifestyle_guidance` takes only `conditions`, `features` and `codes` - there is
no text parameter - and the route declares no LLM dependency, so the absence of
generation is visible in the signature.

The assembled text is still put through Module 24 as defence in depth.

### Tests

`tests/test_explanation.py`, `tests/test_terminology.py`,
`tests/test_lifestyle.py`, `tests/test_explain_endpoint.py`,
`tests/test_gemini_text.py` - **no network, no API key.** The Gemini client is
mocked exactly as Module 4's tests mock it.

Coverage worth naming: every generation path passing through
`guarded_generation`; a rejected generation falling back with the structured
findings intact and the failure visible; a hallucinated number caught;
citations carrying `doc_id`/`topic`/`basis`; **TSH, ferritin, WBC, ALT, PSA and
CRP each refused, never reaching the model and never reaching the retriever**;
seven Gemini failure modes (timeout, rate limit, empty, malformed, blocked,
unconfigured, unexpected) each producing no text and no 500; the prompt module
containing every required prohibition and those prohibitions reaching the sent
prompt; and PHI canaries absent from logs at every level.

`tests/test_live_explanation.py` is opt-in (`RUN_LIVE_TESTS=1` +
`GEMINI_API_KEY`) and asserts that **real** model output clears Module 24 -
first attempt, no ungrounded number. A mocked test proves the wiring; only this
proves the prompt is narrow enough that the gate is not doing all the work.

### Mounting

`app/main.py` is owned by the integrator. The router needs one line alongside
the other `include_router` calls:

```python
app.include_router(routes_explain.router)
```

and `routes_explain` added to the `from app.api import (...)` block. Until then
`tests/test_explain_endpoint.py` builds its own app for the HTTP tests, and one
test skips with an explanatory message rather than passing vacuously.

<!-- END MODULE 23-26 -->
