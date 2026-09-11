# VaidyaAI — Project Memory

> Living context file for the VaidyaAI build. Keep this in the project folder so the
> project's history, decisions, and state survive independently of any chat session.
>
> **Last updated:** 2026-09-07 · **All 32 modules + frontend built** · Module 11 retrained
> (§6s) · first real run (§6t) · Module 27 rewritten for patients (§6u) · the parameter
> glossary finished and live-verified (§6v design, §6w) · **three screens rewritten after
> a user read them aloud — every defect was in the rendering layer (§6w)**

---

## 0. RESUME HERE (read this first in a new session)

**State:** **ALL 32 SPEC MODULES BUILT, PLUS A REACT FRONTEND (§6q), UNDER GIT.** Modules 1–26
are wired end to end and the full spec §16 pipeline has been verified live against real Gemini.

**On 2026-09-06 the whole application was started and driven through a browser for the first
time** — see §6t. Three defects only reachable by running it were found and fixed, including
one that made **report upload impossible for every file**. A green suite had said nothing
about any of them. That is the fifth time on this project.

| | Tests |
|---|---|
| `backend/` (Node/Express) | **634** passing + 3 opt-in live |
| `ai-service/` (Python/FastAPI) | **3,739** passing + 7 skipped |
| `frontend/` (React/Vitest) | **111** passing |
| **Total** | **4,484** -- all green, counted by running them 2026-09-11 |

> ### ▶ NEW CHAT? START AT §6y.
>
> It has the run commands, the test account, and **the list of uncommitted
> work** — a whole session of it, including the entire frontend design system.
> `origin/master` has none of it. Commit before building on top.
>
> Everything runs and all 4,484 tests pass. §6x is the design system
> (`design.md`, tokens + dark-mode toggle + three charts); §6w is the parameter
> glossary and the rendering-layer defects found by reading the screens.

> ### ✅ THE HALF-BUILT FEATURE IS FINISHED (§6v design · §6w completion)
>
> `parameter_glossary` describes laboratory tests this platform does not assess
> (LDL, urea, potassium…) using Gemini, from the test NAME only, with no patient
> data in the prompt. **It now renders on the dashboard and has been driven end
> to end against real Gemini.** Read §6w.
>
> The one thing to carry forward: **the feature was dead on every call and no
> test said so.** The endpoint returned a bare payload instead of the
> `{success, data}` envelope, so the backend rejected every 200 as malformed and
> discarded descriptions it had already generated and safety-validated. The
> module's 14 tests were excellent and tested the wrong layer — none went
> through HTTP, and the shared route walk that asserts `success is True` simply
> never listed this route. **A module can be perfect and unreachable; anything
> with a route needs one test that goes through the route.** Sixth time a green
> suite has said nothing here.
>
> Also read §6v before touching the safety code — it records a real defect: an
> empty `permitted_numbers` turns the shared validator's numeric control OFF
> rather than forbidding all numbers, which let an invented reference range
> through. That rule is enforced locally in `parameter_glossary.py`, not by
> loosening the shared default.

> ### ▶ THEN THE SCREENS WERE READ ALOUD, AND THAT IS WHERE THE BUGS WERE (§6w)
>
> After the glossary shipped, the user drove the running app and reported what
> they saw. Three screens were rewritten as a result — the patient dashboard's
> closing summary, and the clinician page twice. **Every defect found was in the
> RENDERING layer of a pipeline that was producing correct output**, and none
> was visible from a green suite:
>
> * the clinician page read `basis.limitations`; the service writes
>   `basis.ml.limitations`, so **every model probability was shown with no
>   ROC-AUC, no recall and no caveat** — the third recurrence of §6o D8 / §6p.
>   The fixtures hid it by putting the field where the page looked;
> * a summary said "something in this report is outside its usual range" about
>   Obesity, which is computed from the height and weight the patient typed in;
> * `probability 0.9509128032443647` from a model with ROC-AUC 0.697;
> * ten retrieved reference passages rendered as "This section is not available"
>   because two payload fields nest `present` differently;
> * source-file paths and array indices on a page a patient opens.
>
> **The lesson, and it is the only one worth carrying:** a green suite plus three
> mutation rounds plus a live browser check still missed all of it. **A screen
> nobody has read aloud is untested.**

**Working state:** run the three services with the commands in §6t; MongoDB now
points at **Atlas** (`backend/.env`, standard non-SRV connection string — this
machine's Node DNS resolver cannot do SRV lookups). **Six** synthetic one-page
test reports with known expected outcomes live in
`backend/storage/samples/generated/` with an `expected.json`; regenerate with
`ai-service/.venv/Scripts/python.exe tools/make_test_reports.py`.
`04-exactly-on-the-boundary.pdf` is the one most likely to find a real bug, and
`06-lab-flagged-tests-we-do-not-assess.pdf` is the ONLY one carrying tests this
platform does not assess -- the other five are eight mapped tests each with no
printed reference intervals, so they cannot exercise the unassessed section or
the glossary at all (§6w).

**RESTART THE SERVICES BEFORE ANY LIVE CHECK.** Both were running code that
predated the feature under test on 2026-09-07, and a live run against a stale
process proves nothing. `curl http://127.0.0.1:8000/openapi.json` and look for
the route you are about to exercise.

> **THE ai-service SUITE ONLY PASSES WHEN NO `.env` EXISTS.** A real `AI_SERVICE_API_KEY`
> makes the endpoint tests receive 401 instead of 200, so ~30 fail. Nothing is wrong with the
> code; the tests are not isolated from the ambient dotenv. Move `.env` aside to run them, and
> fix `conftest.py` when you get a chance — a suite whose meaning depends on a gitignored file
> is a suite that will mislead someone.

Modules 27–32 now HAVE tests — **+911 written 2026-09-04/05** (see §6o). They found a real
patient-safety defect on their first run.

Run them: `cd backend && npm test` · `cd ai-service && .venv/Scripts/python.exe -m pytest`
(on this machine `pytest -q` may not print its summary to a redirected stream — use
`--junitxml` and parse it when scripting.)

**BASELINE RE-RUN 2026-09-04 after the 27–32 wave: BOTH SUITES GREEN.**
`backend/` 476 passed / 0 failures · `ai-service/` 2,876 passed, 6 skipped / 0 failures.
So the new code caused **no regressions**. But note what that does and does not prove: the
counts are unchanged because **no tests were written for Modules 27–32**, by explicit user
instruction ("build modules 27 to 32, don't test, we
will test later everything"). Those modules are verified only by import checks, their own
import-time `_self_check()`s, and ad-hoc in-process smoke runs by the agents that wrote
them. Treat every claim about them as unverified.

**What is NOT done:**
- **Modules 27–32 have NO TESTS and NO AUDIT.** They are new code on a project whose
  audits have repeatedly found live holes behind a fully green suite — and here there is
  no suite at all. This is the top priority.
- ~~No frontend at all.~~ **BUILT 2026-09-05 — see §6q.** `frontend/` is a React client
  covering every module: auth, profile, reports, the Module 27 dashboard, the timeline
  (28/29/30), the clinician summary (32) and population context (31). 44 tests.
- **Modules 21–26 have not been independently audited.** Modules 1–20 have.

> ## ⚠ START HERE: TWO OPEN **FAIL** VERDICTS, NOTHING FIXED
>
> On 2026-09-05 three auditors were sent at Modules 21–26 — the path where a model's words
> reach a patient, and the last unaudited region. **Two returned FAIL. None of their defects
> has been fixed.** The third never finished and must be re-run. **Read §6r first.**
>
> * **Modules 23/24 — FAIL, 14 defects.** A diagnosis stated as flat fact reaches the
>   patient (`'You have cirrhosis of the liver.'` → approve, zero violations). One adverb
>   defeats every multi-word rule. One zero-width space smuggles "no need to see a doctor"
>   through. **Of §6k's eight fixes: three DO NOT HOLD, four are PARTIAL.**
> * **Modules 21/22 — FAIL.** The §6k D7 anchoring fix is **bypassed on the public HTTP
>   endpoint**; every original D7 example reproduces verbatim today. Module 23 is not
>   exposed, but the endpoint is public and advertises a false claim about its own behaviour.
> * **Modules 25/26 — NEVER AUDITED.** The agent was killed mid-run.
>
> Both suites are green. 408 knowledge tests and 327 safety tests pass with these holes open.
> That is now the fourth time on this project that a green suite has said nothing.

**AUDITED AND FIXED 2026-09-04 — see §6n.** An end-to-end pass over Modules 1–32 (both
suites re-run, an independent contract audit, and a live run against real Gemini) found
seven defects. **ALL SEVEN ARE FIXED**, including a CRITICAL one that put a 60x-wrong
reference range into the patient-facing LLM prompt, a HIGH one where Module 32 was dead on
100% of calls, and D7, where one upload could make the whole ai-service unavailable for an
hour. Read §6n before doing anything else.

**Immediate known issues, none blocking:**
1. A live-test assertion expects an `explanation`-stage warning inside the stored clinical
   report's `warnings_by_stage`. It cannot be there — the report is generated BEFORE the
   explanation stage runs. Either the assertion is wrong or late-stage warnings need a
   home. Decide which; do not just delete the assertion.
2. **Gemini free-tier quota was exhausted** by repeated live runs on 2026-09-04. Live tests
   need quota to have reset.
3. The three safety scanners (`app/safety/policy.py`, `app/data/knowledge_safety.py`,
   `app/data/recommendation_catalog.py`) are **still not reconciled** into one rule table.
   Documented, not done.
4. ~~**A real latent bug in Module 5.**~~ **FIXED 2026-09-04 — see §6n D1.** The
   interval is now carried into the value's unit inside `feature_engineer._reference_bounds`,
   and Modules 29/32 short-circuit on `provenance.reference_converted` so nothing converts
   twice. Original description kept below for context.
   ORIGINAL: `feature_engineer.py` (~line 317) copies
   `reference_low` / `reference_high` through **unchanged** while converting the value to
   canonical units. On a report printed in µmol/L the stored value is mg/dL and the stored
   reference range is still µmol/L. Any consumer that compares a value to its own range is
   comparing two unit systems. Module 29 found this and works around it by re-applying the
   conversion recorded in `provenance.conversion`; Module 32 reuses that workaround. **The
   underlying field is still mismatched for every other consumer, including Module 27's
   dashboard, which places value and range side by side.** Decide whether to fix Module 5
   at source or make the workaround the documented contract.
5. ~~`tests/test_auth.py` route walk unproven against the five new routers.~~
   **RESOLVED 2026-09-04:** run, 59 passed. All five new routers carry the service-key
   dependency.
6. ~~**Contract mismatch between the services.**~~ **FIXED 2026-09-04:** 400 now joins the
   422 branch in `mapAxiosError`. Both are deterministic caller-content refusals, so
   reporting one as a 502 server fault was wrong. Still unreachable live (the backend
   pre-checks and 422s first), so verified by reading and the suite, not by execution.
   ORIGINAL: Module 29 raises
   HTTP 400 `COMPARISON_REPORT_NOT_FOUND` for a named report that is not in the supplied
   set, but `aiServiceClient.mapAxiosError` maps unclassified 4xx to 502
   `AI_SERVICE_REJECTED_REQUEST` ("contract mismatch"). The backend pre-checks and returns
   422 first, so it cannot fire today. Decide whether `mapAxiosError` should learn about
   400 before something else calls that endpoint.

**Working agreement with the user:** build with agents, one module (or tight group) per
agent; a SEPARATE agent audits; the auditor reports defects and does not fix them. The
user decides what gets fixed. **Agents have repeatedly found live holes that a fully green
suite missed — never take a build agent's self-report at face value.**

---

## 1. What this project is

**VaidyaAI** — an AI-powered health intelligence platform that turns unstructured lab
reports (PDF/image) into structured, explainable, safety-validated health insights.

Full specification: `Project Description.txt` (1,897 lines, 32 modules).

**Core thesis:** no single AI technique controls the interpretation. Deterministic clinical
rules, condition-specific ML, retrieved medical knowledge, and an LLM each do a specialised
job; their outputs are fused with evidence attached and passed through a safety validator.

It is explicitly an **AI-assisted education and decision-support platform, not an autonomous
diagnostic system.**

**Pipeline:**

```
Auth -> Profile -> Upload -> OCR -> Extraction -> Feature Engineering -> Validation
     -> Feature Repository -> (Clinical Rule Engine || ML Predictors)
     -> Decision Engine -> Fusion Engine -> (RAG || XAI) -> LLM
     -> Safety Validator -> Final Report -> (Dashboard / Trends / Doctor Summary)
```

---

## 2. Working method (agreed with the user)

- Build **one module at a time**, with **a dedicated agent per module**.
- A **separate, independent auditor agent** verifies each module against the spec.
  The auditor derives its own checklist from `Project Description.txt` before reading code,
  re-runs the test suite itself, and actively attacks the implementation.
  It **reports defects; it does not fix them**.
- Defects are reported to the user, who decides what gets fixed before moving on.
- **Cadence change (2026-08-28):** after Module 1, build Modules 2–5 (one agent each), then
  a **single combined test pass over Modules 1–5** that checks both per-module spec
  conformance *and* end-to-end process syncing between modules — not just isolated passes.

**Why this method:** controlled, verifiable progress instead of a large unreviewed codebase.
The auditor has repeatedly caught working-looking code with live security holes, so
build-agent self-reports are never taken at face value.

---

## 3. Technology decisions (locked)

| Area | Decision | Rationale |
|---|---|---|
| Backend | Node.js + Express 4 + MongoDB (Mongoose) + JWT | Per spec §15 |
| Module style | **CommonJS**, not ESM | Avoids jest/ESM friction; consistent everywhere |
| AI/ML service | **Python + FastAPI**, separate service in `ai-service/` | Per spec §15 |
| **LLM provider** | **Google Gemini**, model `gemini-3.6-flash` | User's choice — free tier |
| **OCR (Module 4)** | **Gemini vision**, NOT Tesseract | Better on multi-column lab tables; no native Windows binaries |
| **File storage (Module 3)** | **Local disk + MongoDB metadata**, behind a storage-adapter interface | Free, self-contained; swappable to Cloudinary/Supabase/Firebase later as a one-file change. NOT GridFS — Atlas free tier is only 512 MB |
| PDF rendering | `pymupdf` (fitz) | Pure-Python wheels on Windows; avoids Poppler dependency |
| ML algorithm | Random Forest + sklearn pipelines | Per spec §10 |
| Frontend | React (not started) | Per spec §15 |

### Resolved

- **`gemini-3.6-flash` model ID is VERIFIED** (2026-08-28). A `GEMINI_API_KEY` was found in the
  environment and the live model list queried: `models/gemini-3.6-flash` exists among 53 models.
  No substitution needed. Lives in `GEMINI_MODEL`, defaulting to `gemini-3.6-flash`.

- **ML datasets RESOLVED (2026-08-29).** All three are real, published, and verified —
  **no synthetic data anywhere**, by explicit user instruction. See
  `ai-service/datasets/PROVENANCE.md` for per-feature spec-match tables.
  * Module 10: Kaggle *Diabetes prediction* (100k rows) — 2 mirrors byte-identical.
  * Module 11: Kaggle *Cardiovascular Disease* (70k rows) — **3 GitHub sources byte-identical**.
  * Module 12: **UCI CKD, official full 25-attribute version** — UCI ships only a `.rar`;
    extracted with Windows' bundled `bsdtar` (`C:/Windows/System32/tar.exe`), which reads
    RAR via libarchive.
  Two earlier heart candidates (UCI Cleveland, Kaggle Heart Failure) were **removed** —
  both lack BMI *and* smoking history, which spec Module 11 explicitly names.

### Open items

- ~~**No Kaggle credentials and no Kaggle MCP**~~ **RESOLVED 2026-09-06.** A Kaggle MCP
  server is connected and authenticated; datasets can be searched and downloaded directly.
- ~~**Module 11's model is weak (ROC-AUC 0.697)**~~ **RETRAINED 2026-09-06 — see §6s.**
  Held-out ROC-AUC is now **0.837** (`with_smoking`) / 0.829 (`without_smoking`) on CDC
  NHANES 2017–2023, using the *same five inputs* v1 used. `heart_rf_v2` is shipped and
  loaded by `app/ml/heart.py`.
- **THE ~0.10 BLOOD-PRESSURE FIGURE WAS WRONG.** It is a property of `cardio_train`, not of
  the task, and it does not transfer. Re-measured on NHANES — reference model fitted and
  scored on the *same test rows*, not inherited — adding blood pressure is worth
  **+0.0066 ROC-AUC**, not +0.10. Adding a systolic field to Module 2 is therefore **no
  longer the highest-value change available to Module 11**; it is a small gain. Argue that
  profile change from +0.0066, and do not re-quote the old number.
- **Module 12 can only use 5 of the CKD dataset's 24 attributes** because
  `feature_catalog.py` has no entry for them. Adding `blood_urea` and `albumin` is likely the
  single biggest quality win available to Module 12.

---

## 4. Repository layout

```
Vaidhyaai/
  Project Description.txt     # the spec — source of truth
  MEMORY.md                   # this file
  backend/                    # Node/Express — Modules 1,2,3 + orchestration
    src/services/aiServiceClient.js   # the 8-stage HTTP client
    src/services/analysisService.js   # the pipeline itself
  ai-service/                 # Python/FastAPI — Modules 4-26 and 28-32
    app/rag/                  # Module 21
    app/safety/               # Module 24 (policy.py = rule table)
    app/population/           # Module 31 (policy.py + tables.py)
    app/ml/ + ml/artifacts/   # Modules 9-13 (3 committed .joblib models)
    app/data/                 # reviewable tables: features, rules, KB, catalogue,
                              #   trend_polarity.py (28), progress_scoring.py (30)
    datasets/                 # 3 REAL ML datasets + PROVENANCE.md
    datasets/population/      # Module 31: NHANES raw .xpt + build script +
                              #   7 tables + PROVENANCE.md
```

No git repository has been initialised. No commits have been made.

---

## 5. Module status

Legend: **Done** = built, independently audited, defects resolved. **In progress** = agent running.

| # | Module | Where | Status |
|---|---|---|---|
| 1 | User Authentication & Authorization | `backend/` | **Done** — audited PASS |
| 2 | Patient Profile Management | `backend/` | **Done** — audited PASS (no defect found) |
| 3 | Medical Report Upload & Management | `backend/` | **Done** — audited PASS WITH ISSUES; D1–D4 fixed |
| — | **Pipeline orchestration** (§16 data flow) | `backend/` | **Done** — full chain 4→5→6→(8‖9/10), live end-to-end verified 2026-08-30 |
| 4 | OCR & Medical Text Extraction | `ai-service/` | **Done** — live-verified against real Gemini |
| 5 | Medical Feature Engineering | `ai-service/` | **Done** — audited PASS (strong); all 9 conversion factors independently verified |
| 6 | Medical Feature Validation Engine | `ai-service/` | **Done** — audited PASS; bounds now clinically checked |
| 7 | Feature Repository | `ai-service/` | **Done** — audited PASS (strong) |
| 8 | Clinical Rule Engine | `ai-service/` | **Done** — audited PASS |
| 14 | Clinical Decision Object | `ai-service/` | **Done** — audited PASS with 2 latent gaps (see §6h) |
| 9/13 | ML Prediction Engine + Predictor Registry | `ai-service/` | **Done** — audited PASS |
| 10 | Diabetes Prediction Model | `ai-service/` | **Done** — audited PASS (strong); metrics reproduce bit-for-bit |
| 11 | Heart Disease Model | `ai-service/` | **Done** — trained on real data; **WEAK model, see §6i** |
| 12 | Kidney Disease Model | `ai-service/` | **Done** — trained on official UCI CKD; sufficiency skip working |
| 15 | Decision Engine | `ai-service/` | **Done** — groups by (condition, source) |
| 16 | Hybrid Decision Fusion Engine | `ai-service/` | **Done** — the hybrid AI layer |
| 17 | Clinical Report Generation | `ai-service/` | **Done** — the user-visible deliverable |
| 18 | Overall Health Status & Risk | `ai-service/` | **Done** — incl. the spec's missing 4th case |
| 19 | Risk Prioritization Engine | `ai-service/` | **Done** — by condition, not decision count |
| 20 | Evidence & Explainability | `ai-service/` | **Done** — rejected-feature join implemented |
| 21 | Retrieval-Augmented Generation | `ai-service/` | **Done** — TF-IDF; free text anchored to the catalogue (§6k D7) |
| 22 | Medical Knowledge Base | `ai-service/` | **Done** — 62 docs / 243 chunks, import-time safety-scanned |
| 23 | LLM Patient-Friendly Explanation | `ai-service/` | **Done** — gated by Module 24; per-feature calls now PARALLEL |
| 24 | Medical Safety & Validation Layer | `ai-service/` | **Done** — audited **FAIL**; D1–D8 all fixed (§6k) |
| 25 | Medical Terminology Explainer | `ai-service/` | **Done** — exact-map only; refusal echo validated alone |
| 26 | Educational Lifestyle Guidance | `ai-service/` | **Done** — catalogue only, calls no model |
| — | **Backend orchestration to explanation** | `backend/` | **Done** — 8 stages, live-verified |
| 27 | Health Dashboard | `backend/` | **Built 2026-09-04** — untested, unaudited |
| 28 | Health Timeline & Trend Analysis | `ai-service/` | **Built 2026-09-04** — untested, unaudited |
| 29 | Smart Report Comparison | `ai-service/` | **Built 2026-09-04** — untested, unaudited |
| 30 | Health Progress Analysis | `ai-service/` | **Built 2026-09-04** — untested, unaudited |
| 31 | Population Context & Percentiles | `ai-service/` | **Built 2026-09-04** — untested, unaudited |
| 32 | Doctor-Friendly Clinical Summary | `ai-service/` | **Built 2026-09-04** — untested, unaudited |
| — | **Longitudinal backend layer** (history + 28/29/30/32 endpoints) | `backend/` | **Built 2026-09-04** — untested, unaudited |

**Test counts:** `backend/` **476 passing + 3 opt-in live** ·
`ai-service/` **2,876 passing + 6 skipped**. Total **3,352**.

**Modules 21–26 were not audited as a group.** Module 24 WAS audited (verdict **FAIL**) and
every defect it raised is fixed — see §6k.

**Modules 11-20 AUDITED 2026-08-30.** One CRITICAL defect found and fixed (D1, below).
Verdicts: 11 PASS · 12 FAIL→fixed · 15 PASS · 16 PASS (strong) · 17 PASS w/ issues →fixed ·
18 PASS (strong) · 19 PASS (strong) · 20 PASS w/ issues →fixed.

**ORCHESTRATION GAP CLOSED.** `backend/` now runs the full §16 flow — see §6j.

**Integration audit 2026-08-30: PASS for Modules 4–10 as a whole.** No defect found in the
"silently corrupts data across a boundary" class. See §6h for what was verified and the
three items carried into the Module 15/16 brief.

---

## 6. Module 1 — Authentication (COMPLETE)

**Location:** `backend/` · **Tests:** 95 passing (3 suites) · **Verdict:** PASS, all raised defects closed.

### Endpoints

`POST /api/v1/auth/{register,login,refresh,logout}` · `GET /api/v1/auth/me` ·
`GET /api/v1/auth/admin/users` (admin-only; exists to exercise `restrictTo`) ·
`GET /api/v1/health`

### Design decisions

- **Refresh tokens:** JWT with a separate secret + random `jti`. Only a **SHA-256 digest**
  is stored, in a `select:false` array on the user doc. Max 5 sessions, oldest evicted.
  **Rotated on every refresh**; replaying a rotated token returns 401.
  SHA-256 rather than bcrypt because the token is high-entropy machine material, not a
  human password.
- **Logout is session-scoped** — other sessions survive.
- **DB role beats the JWT claim.** `protect` re-loads the user from Mongo each request, so a
  forged `role:"admin"` token gets 403.
- **Role escalation blocked at registration** in two places: the validator rejects any role
  other than `patient` (422), and the controller hard-codes `ROLES.PATIENT` regardless.
  Clinician/admin accounts must be provisioned **out-of-band** — no path exists yet, and
  one will be needed eventually.
- **Password policy:** bcryptjs cost 12 (4 in tests for speed), `select:false`,
  **72-byte cap enforced in three places** — register validator, **model layer**, and login
  validator. The model layer is the one that matters; see the truncation notes below.
- **Config fails fast:** missing `MONGODB_URI`/`JWT_SECRET`/`JWT_REFRESH_SECRET`, identical
  secrets, or secrets under 32 chars all refuse to start.

### Security defects found by audit and fixed

All five were **demonstrated live**, not theorised:

1. **HIGH — Rate limiting fully bypassable.** `trust proxy: 1` was set unconditionally with no
   proxy in front, so a client-supplied `X-Forwarded-For` became the rate-limiter key.
   8 failed logins with rotating XFF gave `401` ×8, zero 429s.
   **Fixed:** `TRUST_PROXY` env var, **defaults to false**, fails closed on garbage input.
2. **HIGH — Login type confusion.** The login `email` chain lacked `.isString()`, so a JSON
   **array** reached `findOne({email})` and Mongo's scalar-vs-array matching authenticated
   against any listed address — one request could spray a password across thousands of
   accounts for the cost of one `bcrypt.compare`.
   **Fixed:** `.isString().bail()` on **every** validator chain.
3. **MEDIUM — bcrypt 72-byte truncation.** Passwords over 72 bytes were silently truncated;
   a 103-char password authenticated with its first 72 chars plus arbitrary garbage.
   **Fixed** at validator, model, and login-candidate level (see below).
4. **MEDIUM — Password change did not revoke refresh sessions.** `protect` checked
   `passwordChangedAt`; `refresh` did not. An attacker kept a live session for up to 7 days
   after the victim's password reset.
   **Fixed:** `pre('save')` purges stored digests **and** refresh re-checks independently.
5. **MEDIUM-LOW — Oversized body returned 500 with a stack trace** leaking absolute
   filesystem paths to unauthenticated callers.
   **Fixed:** mapped to 413, plus 400/415/403 for other body-parser errors.

### Notable findings worth remembering

- **bcrypt truncates the candidate too.** While fixing #3 the agent found a second gap: for an
  account whose password was exactly 72 bytes, `<password> + JUNK` compared **equal** and
  returned 200. Hence the login-side cap.
- **Two tests were passing for the wrong reason** and were rewritten — one asserted a login
  failure that actually occurred because the account had never been created.
- The auditor verifies regression tests genuinely **fail against the old code** by reverting
  fixes in a scratch mirror. This has proven worth doing.

### Known limitations (accepted debt, documented in `backend/README.md`)

- 1-second `passwordChangedAt` grace window (a token minted in the same second survives).
- `normalizeEmail` strips subaddresses — `Foo.Bar+tag@GMail.com` stores as `foo.bar@gmail.com`.
- `jwt.verify` does not pin `algorithms` (not exploitable on jsonwebtoken 9.x, but relies on a library default).
- Mongoose `CastError` can echo submitted values (now largely unreachable via routes).
- `/health` is unauthenticated and unthrottled; discloses uptime and DB state.
- `GET /auth/admin/users` returns names + emails with only `.limit(100)` — a PII listing to revisit against §19.

### Operational caveat

**`TRUST_PROXY` is now a deploy-time security decision.** The default (false) is safe for
direct exposure, but **setting it to `1` without a real proxy fully reopens defect 1** — this
was measured. When deploying behind a load balancer it must be set to the real hop count;
leaving it false there means one abusive client throttles everyone.

---

## 6a. Module 2 — Patient Profile (BUILT)

**Endpoints:** `GET|POST|PUT|PATCH|DELETE /api/v1/profile/me` — no id in any URL, so there is
nothing to tamper with; the owner always comes from the verified JWT.

**Key decisions:**

- **Units are explicit and enforced:** `heightCm`, `weightKg`, `age` (whole years), `bmi` (kg/m²).
  Numeric fields accept JSON numbers only — `"70kg"` and `"170"` are 422, so a unit cannot be
  smuggled through as a string.
- **BMI is derived twice over** — excluded from the writable allow-list AND recomputed by a
  model `pre('validate')` hook. A client-supplied BMI is always ignored.
- **`gender`:** `male | female | other | prefer_not_to_say`. The user's real answer is stored and
  never coerced into a binary category; `Profile.ML_GENDER_VALUES` exports the subset a binary
  model can consume.
- **`smokingHistory`:** `never | former | current | ever | not_current | no_info` — exactly the
  diabetes-dataset categories, directly encodable with no translation layer.
- **`hypertension` / `heartDisease`: TRI-STATE** — `true`, `false`, or **absent meaning unknown**.
  Absent must never be collapsed to `false`; that fabricates a negative finding. Module 12's
  kidney predictor depends on this distinction to decide when to skip.
- **Semantics:** `GET` 404s when no profile exists (not an empty 200). `POST` strict-creates,
  409 on duplicate. `PUT` upserts with **replace** semantics (omitted fields cleared). `PATCH`
  partial, never creates. Free text is arrays only, 30 × 200 chars.
- **`completeness`** — `{ fields, filled, percent, missing[] }` over the 7 ML-relevant fields,
  so Module 12 can decide to skip without probing.

**Ownership is now ENFORCED, not merely available.** `ownership.js` was previously imported by
nothing; it now backs every profile operation, with queries owner-scoped AND loaded documents
re-checked (deliberately redundant, so a future widened filter still denies).

**`allowRoles` now DENIES BY DEFAULT** (`[]`, was `[ROLES.ADMIN]`). Admins do **not** bypass
ownership on medical data. The two Module 1 tests that pinned the old permissive behaviour were
**inverted, not deleted**, and two new tests prove an explicit `allowRoles: [ROLES.ADMIN]` grant
still works — the capability survives, only the default changed.
`ownerScopedFilter` now **throws** when there is no identity instead of returning `{user: null}`
(which matched null-owner documents). Call it only after `protect`.

**Reasoning for the default flip, worth remembering:** an opt-out security default fails open.
This is the same failure shape as the validator-only password cap and the missing `.isString()`
on one of five chains — in every case the fix that held was at the lowest layer, on by default.

---

## 6b. Module 3 — Report Upload (BUILT)

**Endpoints:** `POST /api/v1/reports` (multipart) · `GET /` (chronological, paginated) ·
`GET /:id` · `GET /:id/download` · `DELETE /:id` — all authenticated and owner-scoped.

**Storage adapter interface:** `name`, `save({userId, buffer, extension}) → {key, size}`,
`createReadStream(key)`, `stat(key)`, `remove(key)` (idempotent), `removeUserScope(userId)`.
The `key` is **opaque** — the DB stores it plus the driver that produced it, and only the adapter
may resolve it. **Never build a path from a key.**
Swapping to cloud = add one file, register it in the `DRIVERS` map, set `STORAGE_DRIVER`.
Because the driver is recorded **per row**, old rows keep resolving through the old adapter, so
migration can be gradual.
Local layout: `<UPLOAD_ROOT>/<userId>/<64 hex>.<detected ext>`, written to `.part` then renamed,
`wx` flag, mode 0600, outside any static-served directory.

**Orphan handling:** rejections never touch the filesystem (multer buffers in memory, so the
adapter is the only thing that ever writes report bytes). File-write failure removes its own
`.part`. DB-insert failure removes the just-written file without masking the original error.
Delete removes the **row first, then the file** — an interruption leaves an invisible orphan
file rather than a user-visible broken download. A missing file is not an error.

**Attacks verified:** HTML/PHP/SVG/PE/ZIP/text payloads named `.pdf`/`.jpg` with matching
declared `Content-Type` → **415** (magic bytes decide, not extension or client MIME; a PDF
signature at non-zero offset also 415). Path-traversal filenames collapse to their last
component. A `storageKey` tampered **through the raw driver** to `../secret.txt` → 404, no
disclosure. Oversized → **413** with no stack. User B, **admin**, and **clinician** each get
404 on A's report for all four operations, byte-identical to a random-id 404. Download sets
`attachment` + `nosniff` + `no-store`, and a header-injection filename still parses as exactly
one quoted filename.

**Known gaps (documented):** upload throttling keys on `req.ip`, not user id, so it inherits the
`TRUST_PROXY` caveat. Files are buffered in memory (bounded by `UPLOAD_MAX_BYTES`) — a much
larger cap would need a streaming redesign. No encryption at rest, no download audit log, no
per-user quota, no duplicate rejection (checksum is stored and indexed for it), no `.part`
sweeper.

**Module 4 inherits:** resolve files via `getStorage(driver).createReadStream(key)` — never build
a path. Verified `mimeType`, `sizeBytes`, `checksumSha256` are available. It owns the
`status`/`statusMessage` lifecycle (`uploaded → processing → processed|failed`), and
**`statusMessage` must never hold report text**. `chronoDate` is already correct for Modules
28–30 and must not be altered by extraction.
**Magic bytes prove the container type only, not that the file is benign** — Module 4 must not
assume a file is safe to hand to a native parser.

---

## 6c. Module 4 — OCR & Extraction (BUILT)

**Endpoint:** `POST /api/v1/ocr/extract` (multipart) · `GET /api/v1/health`.
**194 tests passing offline + 2 opt-in live.** Offline verified three ways, including with
outbound HTTP patched to raise — proving no hidden network dependency.

**The live integration works.** Real extraction of a synthetic 7-row report returned every row
correctly at confidence 0.99, with the contract holding: `Urine Ketones` → `value_numeric: null`
with `value_raw: "Negative"` preserved, and names left unnormalised (`Vitamin D (25-OH)`,
`Haemoglobin`).

**Decisions worth remembering:**

- **MuPDF silently repairs damaged PDFs.** A mildly truncated scan does not fail — MuPDF recovers
  and renders what it can. This is kept deliberately (a damaged scan should still be read) but
  surfaced via `doc.is_repaired` as a warning, since recovered pages may be missing content.
  Severely truncated files still fail cleanly with 422.
- **Partial degradation on multi-page documents:** one failed page returns 200 with that page's
  `raw_text: null` plus a warning naming it. Only if *every* page fails do you get 502. Module 5
  will therefore sometimes see partial results rather than nothing.
- **Truncated responses are NOT retried** (`MAX_TOKENS` is deterministic — a retry burns quota
  for the same outcome); **malformed/empty JSON IS** resampled.
- **Gemini's schema dialect is a restricted OpenAPI subset** that rejects `$defs`/`$ref`/`anyOf`
  — exactly what `pydantic.model_json_schema()` emits. The model-facing schema is therefore
  hand-written in `gemini_response_schema()`, with a test asserting it stays in the safe subset
  and its keys match `PageExtraction`. **Keep the two in sync if you edit either.**
- **The live model often sets `flag: "normal"` where the FLAG column was blank**, deriving it
  from an unambiguous reference range. Contract-compliant, but expect `"normal"` more often than
  `null`. The service itself never adds a flag the model did not return.
- Size cap trips **during** the read (1 MB chunks, aborts past the limit), so a huge upload
  cannot exhaust memory before validation.
- **PHI log-leak protection is enforced by canary tests** — planted strings must appear in the
  HTTP response but never in logs, including on the unhandled-exception path where only the
  exception *type* is logged.

---

## 6d. Module 5 — Feature Engineering (BUILT)

**Endpoints:** `POST /api/v1/features/engineer` · `GET /api/v1/features/catalog`.
Also exposed as a framework-independent `engineer_features()` so Module 7 and the ML layer can
call it without HTTP.

**Canonical units and conversion factors** (`canonical = raw × factor + offset`):

| Feature | Canonical | Conversions |
|---|---|---|
| `hba1c` | `%` NGSP | `mmol/mol` (IFCC) → `%`: **×0.09148 + 2.152** — **AFFINE, not a ratio** (48 → 6.543 %) |
| `blood_glucose` | `mg/dl` | `mmol/l` ×18.0156 · `g/l` ×100 · `mg/l` ×0.1 |
| `hemoglobin` | `g/dl` | `g/l` ×0.1 · `mmol/l` ×1.61145 |
| `vitamin_d` | `ng/ml` | `nmol/l` ×0.400641 (inv 2.496) · `ug/l` ×1 |
| `vitamin_b12` | `pg/ml` | `pmol/l` ×1.35537 (inv 0.7378) · `ng/l` ×1 |
| `creatinine` | `mg/dl` | `umol/l` ×0.011312 (inv 88.4017) · `mmol/l` ×11.312 · `mg/l` ×0.1 |
| `cholesterol` | `mg/dl` | `mmol/l` ×38.6654 · `g/l` ×100 · `mg/l` ×0.1 |
| `triglycerides` | `mg/dl` | `mmol/l` ×88.57 · `g/l` ×100 · `mg/l` ×0.1 |

**The HbA1c IFCC→NGSP conversion is affine, not a ratio.** Any code path treating it as a pure
multiplication is a serious defect. *(These factors have NOT yet been independently audited.)*

**Other decisions:**

- **Unrecognised units are never assumed canonical** — the feature is still emitted (Module 6 must
  see it) but unconverted, with `canonical_unit: false` and a warning. A **missing** unit is a
  separate case: canonical assumed, `unit_assumed: true`, warning.
- **Safety guards beyond the brief:** urine/CSF/stool specimens never map to blood features
  (`unsupported_specimen`); HDL/LDL/VLDL never fold into `cholesterol` (`distinct_analyte`).
- **Duplicate resolution** is a total deterministic rank: synonym specificity (fasting glucose 3 >
  unqualified 2 > random 1 > post-prandial 0) → recognised unit → uncensored → confidence → page →
  input order. Losers appear in both `duplicates_resolved[]` and `unmapped[]`.
- **Censored values** (`<0.1`) kept at the detection limit with `provenance.censored`.
- **Tri-state preserved by ABSENCE from the `features` map**, never by a default. Explicit `false`
  is present with value `false`; absent/null/unknown yields no feature plus the name in
  `missing_features`; an unrecognised token yields no feature plus a warning — **never `false`**.
- Added **`gender`** as a 14th feature (not in the spec's 13) since Module 2 stores it and Module 11
  consumes it. Also has a **BMI fallback derivation** from height/weight — the builder itself flags
  this as arguably scope creep, since Module 2 derives BMI authoritatively. *Possible second source
  of truth; unaudited.*
- Module 5 applies **no** range or plausibility check — that is entirely Module 6's job.

---

## 6e. Integration state — VERIFIED 2026-08-28

I pushed real data through the seams myself rather than reasoning from docs.

**Seam D (Module 4 → 5) WORKS.** Module 4's exact live output was accepted; all six lab features
mapped correctly (`hba1c` 6.8 %, `blood_glucose` 112 mg/dl, `hemoglobin` 14.2 g/dl, `creatinine`
1.0 mg/dl, `cholesterol` 190 mg/dl, `vitamin_d` 35 ng/ml) and non-numeric `Urine Ketones` was
correctly routed to `unmapped[]` rather than invented into a number.

**Seam B (Module 2 → 5) WORKS.** Module 5 accepts Module 2's actual **camelCase** JSON via pydantic
aliases (`smokingHistory` → `smoking_history`, `heartDisease` → `heart_disease`), and provenance
preserves the original field name. **The tri-state survives the language boundary**: with
`hypertension` absent, it stayed out of `features` and appeared in `missing_features` — it did
**not** become `false`. This was the highest-risk silent-corruption path and it holds.

**DEFECT — Module 4's warnings are silently dropped by Module 5.** Verified: input
`warnings: ["page 1 was recovered by the PDF repairer"]` → Module 5 output `warnings: []`.
MuPDF's silent repair and multi-page partial degradation surface **only** as warnings, and Module 17
requires validation warnings in the final report. A report from a damaged, partially-unreadable scan
is currently indistinguishable from one from a clean scan — an unreadable row silently becomes
"test not present". **Being fixed.**

**DEFECT — `ai-service` has no authentication of any kind.** Anyone who can reach the port can
submit medical documents and receive extractions. Against §19. **Being fixed** via
`AI_SERVICE_API_KEY` + `X-Service-Key` header, constant-time compare, fail-closed (an unset key must
refuse startup, never mean "open"); `/health` stays unauthenticated.

**All seams are now WIRED and live-verified** (see §6f). The pre-wiring state is kept above
because the defects it uncovered are worth remembering.

---

## 6f. Pipeline orchestration — WIRED AND LIVE-VERIFIED 2026-08-28

The §16 data flow is now real. `backend/` drives `ai-service/` over HTTP.

**Endpoints:** `POST /api/v1/reports/:id/analyze` · `GET /api/v1/reports/:id/analysis` ·
`GET /api/v1/health/ai`. Owner-scoped identically to every other report route — B/admin/clinician
get byte-identical 404s to a random id on both.

**Service-to-service contract (BINDING — both sides implement exactly this):**

| | |
|---|---|
| Env var (both services) | `AI_SERVICE_API_KEY`, **minimum 32 chars**, enforced at startup on both sides |
| Header | `X-Service-Key` |
| Backend base URL | `AI_SERVICE_URL` |
| Correlation | `X-Request-Id`, charset `[A-Za-z0-9._:-]{1,128}` — anything else silently discarded |
| Protected | `POST /ocr/extract`, `POST /features/engineer`, `GET /features/catalog` |
| Open | `GET /api/v1/health`, `GET /` |
| Rejection | **401** `{success:false, error:{code:"UNAUTHORIZED"}}` |
| Extraction call | multipart, file part named exactly **`file`** |
| Feature call body | **`{"extraction": <Module 4's `data`, UNWRAPPED>, "profile": {...}}`** |
| Profile format | Module 2's **camelCase**, sent untranslated (Module 5 has pydantic aliases) |

Auth is **fail-closed on both sides**: an unset or short key refuses startup. `ai-service` compares
`hmac.compare_digest` over SHA-256 digests of both sides, so key *length* does not leak either.
Missing / wrong / empty / whitespace keys are byte-identical 401s — **so a 401 cannot distinguish
"misconfigured" from "wrong key"**; the backend therefore logs its own config (URL + key length,
never the key) at startup.

**EXTENDED 2026-08-30 — the chain now runs all the way to decisions.** See §6g.

**Persistence.** On the `Report` document:
`extraction`, `features`, `analysisWarnings` — all `select:false` so listings do not drag them —
plus an always-loaded `analysis.{version, runCount, requestId, startedAt, completedAt, durationMs,
profileUsed, extractionConfidence, pagesUnreadable, warningCount}`.
**Raw report text is deliberately NOT persisted** (`raw_text` → `raw_text_available`, per page too),
mirroring the Python side's PHI stance. The full extraction is still forwarded to Module 5.

**Re-run semantics:** overwrite, `analysis.version` bumped. A *failed* run writes only
status/message/timing, so a prior successful analysis survives — `status` describes the latest
**attempt**, `analysis.version` the stored **payload**.

**Concurrency:** the transition to `processing` *is* the lock — a single conditional
`findOneAndUpdate` (test-and-claim atomic). A second caller gets 409; 5 parallel claims → exactly
1 winner. Stale locks past `AI_SERVICE_LOCK_TTL_MS` can be taken over, and both terminal writes are
conditioned on still owning the lock so a superseded run cannot clobber the winner.

**`statusMessage` PHI exclusion is structural** — it comes from a table lookup on an error code,
never a formatted message, so report text cannot reach it by construction.

**`assertProductiveFeatures`:** a 200 where the extraction had parameters but Module 5 accounted for
**none** of them fails as `AI_SERVICE_EMPTY_RESULT`. This exists because the empty-but-200 silent
failure (below) would otherwise be reported as success.

**Warnings:** the backend reads `all_warnings` first, folding in `upstream_warnings` / `warnings` /
the extraction's own as a safety net, never overwriting origins.

### Live end-to-end verification (real Gemini, real PDF)

`analyze → 200`, version 1, confidence 0.99, features
`[hba1c, age, bmi, heart_disease, smoking_history, gender]` — **`hypertension` correctly ABSENT**,
proving the tri-state survives the real Node→Python boundary. A wrong service key → clean 502, no
stack.

### Defects found and fixed during wiring

- **Everything except `extracted_parameters` was dropped at the 4→5 boundary.** `ExtractionInput`
  had `extra="ignore"` and only two fields, so `warnings`, `source`, `report_metadata` and `pages`
  were discarded **at parse time**, and `extraction_confidence` never reached the output. The
  warnings symptom I originally spotted was one visible part of a much broader bug.
- **Relaying Module 4's envelope unmodified was silently accepted → HTTP 200 with `features: {}`.**
  A pipeline wired that way looks healthy and produces nothing. Now 422-on-ambiguous rather than
  guessing.
- **`GET /health/ai` was an unauthenticated outbound-request amplifier** (one inbound → one
  outbound, unbounded). Now cached 15 s with in-flight coalescing; 8 inbound → 1 outbound.
- A `storage.stat()` throw on a tampered key could still reach the stack-printing 500 branch from
  the analyze path; now the same clean 404 a missing file gives.

### Known limitations (documented, deliberately not fixed)

- **`analyze` blocks until extraction completes.** `ai-service` worst case is
  `(GEMINI_MAX_RETRIES × GEMINI_TIMEOUT_SECONDS + backoff) × MAX_PAGE_COUNT` = **~61 min with
  shipped defaults**; the backend's default client timeout is 5 min. A pathological multi-page scan
  will time out on the backend while the Python side keeps spending Gemini quota.
  **A background job queue is the real fix** — deliberately out of scope so far.
  Recommended tightening: `GEMINI_TIMEOUT_SECONDS=45, GEMINI_MAX_RETRIES=2` (~15 min worst case).
  **The two services must be tuned together.**
- Retry re-uploads and re-processes the whole file on a transient failure (default 1 retry).
- One shared secret, no rotation window — changing it requires restarting both services together.
- No rate limiting on `ai-service`, so a key-holder can drive unlimited Gemini spend. Keep the
  backend's analyze endpoint rate-limited and the Python service off the public internet.
- No mTLS or request signing — `X-Service-Key` is a bearer credential and must travel over TLS or a
  private network.

---

## 6g. Pipeline orchestration COMPLETED to decisions — LIVE-VERIFIED 2026-08-30

`backend/` previously stopped at feature engineering: `aiServiceClient` knew only three
endpoints, so Modules 6–10 were live but **the backend called none of them**. The §16 flow
now runs end to end.

**Stage sequence** (`POST /reports/:id/analyze`):

```
extract (4) -> engineer (5) -> validate (6) -> [ rules (8)  ||  predict (9/10) ]  -> persist
```

Rules and ML are **parallelised** — same input, neither reads the other, §16 draws them in
parallel. Each is wrapped so it **settles rather than rejects**, so one failing cannot discard
the other's result (a bare `Promise.all` would).

**Module 7 (Feature Repository) is deliberately NOT called.** Its backend is in-memory and
process-local — lost on restart, not shared between workers. MongoDB is the durable copy, so
`/repository/load` would be a **second source of truth guaranteed to disagree after any
restart**, with no owner scoping. Modules 8 and 9/10 take Module 6's output directly, so it is
not on the critical path. Revisit only if it gains a persistent backend.

**Partial-failure semantics — two classes of stage:**

| Stage | Class | On failure |
|---|---|---|
| 4 extraction, 5 features | **load-bearing** | nothing persisted, `status=failed`, previous analysis survives |
| 6 validation | downstream | features still stored; rules+ML **skipped** (`VALIDATION_UNAVAILABLE`), never re-pointed at unvalidated input; `status=partial` |
| 8 rules | downstream | **ML result still stored**; `status=partial` |
| 9/10 ML | downstream | **rule decisions still stored**; `status=partial` |

New status **`partial`** added to the enum. `processed` now means *every* stage succeeded —
a failed stage may never hide behind it. A partial run is a **200** whose body says so twice
(`report.status` + `analysis.stages`). A stage that did not answer has its payload and counts
**unset**, never left stale beside a newer run's features. A count is `undefined`, never `0`,
when a stage did not answer — same class of error as collapsing an absent tri-state to `false`.

**New persisted fields** (all `select:false`): `featureValidation` (M6), `ruleDecisions` (M8),
`mlDecisions` (M9/10). Always-loaded additions: `analysis.{stages, stagesFailed,
ruleDecisionCount, mlDecisionCount, decisionCount, highestRisk, conditionsFlagged,
validFeatureCount, questionableFeatureCount, rejectedFeatureCount}`.

**`analysis.stages` is PHI-safe by the same construction as `statusMessage`** — `errorCode` /
`reasonCode` come from fixed tables of our own machine codes; anything else degrades to
`ANALYSIS_STAGE_FAILED`.

**DECISIONS ARE NEVER DE-DUPLICATED.** The unit of a rule decision is one **rule**, not one
condition — the live run produced **5 rule decisions across 1 flagged condition** (`Diabetes`).
That is what makes per-rule traceability possible; grouping/fusing is Module 15/16's job.
`decisionCount` counts decisions; `conditionsFlagged` is a **set of conditions** and is not a count.

**Timeouts are per stage.** Extraction keeps the 5-min default; validation/rules/ML get
`AI_SERVICE_STAGE_TIMEOUT_MS` (30 s) with per-stage overrides. Measured live: **10 ms / 14 ms /
1657 ms**. Letting them inherit the extraction timeout would pin three more Node handles for
five minutes each after the expensive stage had already succeeded.

**Warnings carry through all five stages** (`extraction`/`feature_engineering`/`validation`/
`rules`/`ml`), de-duplicated by (origin, code, message) so a warning propagated by every stage
collapses to one entry **with its original origin**. Every stage's own list is read as a
fallback, so a single propagation regression anywhere cannot erase upstream warnings.

### Live end-to-end verification (real ai-service, real Gemini, 2026-08-30)

`analyze -> 200`, `status: processed`, version 1, confidence 0.99, **all five stages ok**,
features `[hba1c, age, bmi, heart_disease, smoking_history, gender]`, `validFeatureCount: 6`,
`rejectedFeatureCount: 0`, **`ruleDecisionCount: 5`, `mlDecisionCount: 1`, `highestRisk: High`,
`conditionsFlagged: [Diabetes]`**. `hypertension` **correctly ABSENT** from features, from
`validation.valid` and from `validation.rejected` — the tri-state survives all four extra hops.

**Test counts:** `backend/` **450 passing + 3 opt-in live** (9 suites). All 430 pre-existing
tests still pass; 20 added.

---

## 6h. Integration audit — Modules 4–10 · 2026-08-30 · VERDICT: PASS

Independent auditor, read-only, `ai-service/` confirmed byte-identical afterwards.
**No defect found in the "silently corrupts data across a boundary" class.**

### Conversion factors — INDEPENDENTLY VERIFIED (this was the top risk)

Every factor recomputed from IUPAC atomic weights, not taken from the file's stated basis.
All 9 **MATCH**: glucose ×18.0156 (exact) · creatinine ×0.011312 (exact) ·
haemoglobin ×1.61145 (exact) · vitamin D ×0.400641 (1.5 ppm) · B12 ×1.35537 (13 ppm) ·
cholesterol ×38.6654 (26 ppm) · triglycerides ×88.57 (280 ppm, the universal clinical
convention). Largest residual is 0.04 mg/dL at the 150 mg/dL triglyceride decision point.

**The HbA1c affine transform has exactly ONE arithmetic site** — `UnitConversion.apply()`
= `value*factor + offset`, called once from `feature_engineer.py:283`. There is **no
ratio-only path anywhere** to regress into. A ratio would give 4.391 % for 48 mmol/mol;
the pipeline gives 6.54304 %.

### Also verified end-to-end

- **Warning propagation:** a canary planted in Module 4's `warnings[]` survives
  4→5→6→7→8 and 4→5→6→9/10 with `{stage, module}` origins intact at every hop.
- **Tri-state:** absent `hypertension` never reads as `False` anywhere in the chain.
  `ABSENT` refuses `bool()`, `float()`, `int()`, `len()`, `+`, `<`.
- **Unit-confusion magnitudes** all still rejected: HbA1c 48 (IFCC), Hb 142 (g/L),
  creatinine 884 (µmol/L).
- **Module 6 bounds are now clinically checked** (closing the earlier debt): a
  maximum-abnormality patient (HbA1c 14.9, glucose 485, creatinine 7.2, Hb 5.9, TG 1500)
  had **every value accepted** and correctly tagged `clinically_extreme`.
- **PHI in logs:** 609 bytes logged across all routes plus error paths — **zero PHI**.
- **Module 10 metrics reproduce bit-for-bit** from the committed artifact; the metrics JSON
  is sha256-bound to the shipped joblib.
- **Fusion readiness:** every rule and predictor sources its condition string from
  `conditions.py` constants. No rule/predictor pair would fail to group.

### Correction to a claim previously recorded here

`validation_rules.py` claimed an unconverted mmol/L **cholesterol** (3–8) falls *inside*
the plausible band. **It does not** — `possible_low` is 20.0, so it is rejected as
implausibly low. The argument for unconditional `canonical_unit: false` rejection still
holds, but the real examples are **vitamin D** (25–250 nmol/L inside 0–400 ng/mL) and
**blood glucose** (5.5–30 mmol/L inside 5–3000 mg/dL). Comment corrected in the file.

### Three requirements carried into the Module 15/16 brief

1. **Group by `(condition, source)` in Module 15; de-duplicate `sources`, union evidence
   and recommendations in Module 16.** The rule engine legitimately emits MORE THAN ONE
   decision per condition from the same source (HbA1c rule *and* glucose rule both fire for
   `Diabetes`). That is correct — the unit of a rule decision is one **rule**, not one
   condition, which is what makes per-rule traceability possible. But naive fusion yields
   `sources = ["Clinical Rule Engine", "Clinical Rule Engine"]`, double-weights the
   condition in Module 19, and shows two contradictory dashboard cards. **Fix upstream of
   fusion, not inside Module 8.**
2. **Add a condition-vocabulary validator to `ClinicalDecision`.** `condition="diabetes
   mellitus"` is currently accepted; nothing enforces the canonical list. Every in-repo
   producer is clean, but Modules 15/16 will add producers. Cheap now, invasive later.
3. **Give Module 20 the rejected-feature join.** When Module 6 rejects a value, Module 8's
   evidence says *"this value was not available in the submitted report"* — factually wrong;
   it WAS there and was refused. The rejection reason does reach `all_warnings`; it is just
   not joined to the evidence item.

### Lower-severity, recorded not fixed

- **`Heart Disease` means two things.** The composite rule fires on a *risk-factor count*;
  Module 11 will emit *disease likelihood*. Fusing them under one condition conflates burden
  with probability. Fix in Module 16/17 by surfacing the band label, not just the status.
- **Safety-scanner patterns are thinner than the docstring claims** — misses "diagnosis is
  X", drug names not on its list, dosages without numerals, and "you do not need to see a
  doctor". **Not live today** (176 user-facing strings from a maximum-abnormality run were
  scanned: zero unsafe outputs, and the structural defence holds), but **harden before the
  Module 23/24 LLM layer runs prose through `scan_text`**.
- `ClinicalDecision(source_kind=CLINICAL_RULE, confidence=0.0)` is accepted; the live rule
  engine always emits `None`.

---

## 6i. Modules 11, 12, 15, 16 — built 2026-08-30, NOT independently audited

### Module 11 — Heart Disease · **SUPERSEDED 2026-09-06 by v2, see §6s.**

> **Everything in this subsection describes `heart_rf_v1` (cardio_train), which is no longer
> loaded.** It is kept because the v1 numbers are still quoted in older sections and because
> the reasoning below is the reasoning that v2 disproved. For the shipped model read §6s.
> In particular the "0.800 vs 0.697" blood-pressure comparison below is a cardio_train fact:
> the same measurement on NHANES gives +0.0066, not +0.10.

### Module 11 (v1, HISTORICAL) — Heart Disease · trained, but WEAK.

ROC-AUC **0.697** · PR-AUC 0.684 · accuracy **0.592 vs 0.500 baseline** (n=13,988, ~50/50).
At threshold 0.673: precision 0.747, **recall 0.277**, F1 0.404.
5-fold CV ROC-AUC 0.6960 ± 0.0051 — **the weakness is stable, not split-luck.**

It flags fewer than 3 in 10 true positives and the Low band holds only 12% of the cohort, so
**it almost never rules anything out**. Treat it as a coarse indicator to be fused with Module
8's risk-factor tally, never as a heart-disease predictor.

**Why it is weak — a data gap, not a modelling failure.** `ap_hi`/`ap_lo` (blood pressure)
dominate this dataset, but **Module 2 does not collect BP**, `feature_catalog.py` has no such
feature and Module 4 does not extract it. Training on BP would mean median-imputing the top
input for every real patient and publishing metrics for a model that never actually runs.
The cost was **measured, not hidden**: a BP-inclusive reference model scores **0.800 vs the
shipped 0.697**, recorded in the artifact with `shipped: false`.

Other decisions: **gender 1 = female, 2 = male**, inferred from an 8.6 cm mean height gap and a
12-fold smoking difference both pointing the same way. Cholesterol mg/dL → ordinal band by NCEP
ATP III (`<200→1`, `200–239→2`, `≥240→3`), column named `cholesterol_band` so it can never be
confused with Module 5's mg/dL `cholesterol`. Cleaning removed **60 of 70,000 rows**.
`gluc` deliberately unused — worth +0.003 AUC and its fasting/random basis is undocumented.

### Module 12 — Kidney Disease · excellent numbers, small dataset

ROC-AUC **0.998** · PR-AUC 0.999 · accuracy **0.970 vs 0.630 baseline** (n=100).
5-fold CV ROC-AUC 0.9957 ± 0.0040.

**The numbers are near-perfect because the dataset makes it easy**, not because the model
generalises: 399 rows, single-centre UCI, where creatinine and haemoglobin separate the classes
almost cleanly. The test split is 100 patients — one error moves recall ~1.6 points. **Read the
sufficiency skip, not the accuracy, as this module's contribution.**

**Sufficiency: `required = (creatinine, hemoglobin)`.** All 30 feature subsets were measured;
the pair alone gives 0.9860 CV ROC-AUC vs 0.9957 for all five, so the other three are a 0.010
refinement and are optional — a predictor that skips too eagerly is not safer, only silent.

**Creatinine is required on CLINICAL grounds, not statistical ones**, and the builder said so
plainly: blanking it costs only 0.0073. It is the analyte that *defines* renal function, and
haemoglobin only substitutes because anaemia of CKD is near-universal in this cohort. Without
creatinine this is an anaemia signal wearing a kidney label — which in a screening population
fails quietly in the dangerous direction.

**Malformed CKD row DROPPED, not repaired.** Row 369's whole tail is shifted (`appet`=`no`,
`pe`=`good` — both outside their domains). Repairing means guessing whether that patient had
CKD, i.e. fabricating training data. 399 rows used. Missingness is imputed **inside the
pipeline**; no rows dropped for missing values.

**Thresholds deviate from Module 10's deliberately.** Module 10's 0.90-precision rule is
satisfied here at threshold 0.11 — before the model commits — which would put 79% of the cohort
in INDICATED. Both cut-offs are therefore sensitivity guarantees instead.

### Modules 15/16 — Decision Engine and Fusion

**Status fusion rule:** a fused decision is `INSUFFICIENT_DATA` **only when no contributing
decision actually assessed** the condition; otherwise status is the most severe among those
that *did* assess. This excludes two opposite failures at once: an abstention hiding a real
`Indicated/High` finding, and an empty assessed set presenting as assessed. The abstention is
recorded four ways, including a warning that reaches Module 17's validation warnings.

**Confidence fusion:** the maximum over contributors that actually produced a probability.
`None` is **absent from the maximum** — never read as 0.0, never able to suppress another
source's real number. `0.0` **is** a value and does take part.

**Heart Disease semantic hazard handled.** Not renamed (that would break fusion). Each
contribution carries `assessment_basis` (`risk_factor_count` / `threshold_comparison` /
`model_probability` / `not_assessed`); when a risk-factor burden sits beside a different kind of
claim the fused decision sets `basis_conflict=True` and Module 17 should render them side by
side. Threshold-vs-model is deliberately **not** flagged — those are two methods answering one
question, and flagging it would caveat everything until the caveat stopped being read.

**Verified cross-agent interaction:** the Diabetes predictor predates the `assessment_basis`
convention and leaves it `None` when it skips. Fusion derives `not_assessed` from the **status**
rather than a metadata default, so the unstamped skip is still labelled correctly. Checked
directly.

**Condition-vocabulary validator added to `ClinicalDecision`** — a non-canonical condition
string is now rejected at construction, closing the §6h latent gap. Import ordering verified
across seven orders in fresh interpreters, plus a negative control proving the harness can fail.

### Known gaps carried forward

- `summary.overall_status` is **`null` when nothing was assessed**. Spec Module 18 names three
  outcomes but not that fourth case, and "no abnormal findings ⇒ Healthy" is vacuously true for
  a report whose every test was unreadable. **Module 17 must read it with `any_assessed`.**
- The **rejected-feature join for Module 20** (§6h item 3) is still not implemented.
- **Safety-scanner patterns still need hardening before Modules 23/24** run LLM prose through
  `scan_text`.
- Heart joblib is **21.6 MB** — fine to load, worth knowing before it goes into an image.
- RF `predict_proba` with `n_jobs=-1` can differ in the last float bit between calls; tests
  assert the band exactly and the probability to 1e-12.

---

## 6j. Modules 21–26 — RAG, Knowledge Base, LLM, Safety, Terminology, Guidance

### Module 22 — Knowledge Base
62 documents / 377 paragraphs / 243 chunks in `app/data/knowledge_documents/`. Vocabulary
aligns **byte-for-byte** with `feature_catalog.FEATURES` and `conditions.CONDITIONS`, both
directions, enforced at import. Every document carries its `basis`. An import-time scanner
rejects unsafe content — four planted unsafe documents were all refused.

### Module 21 — RAG
`Documents → chunk → TF-IDF → index → query → similarity`. The index is a **committed
artifact** built by `knowledge/build_index.py`; `--check` verifies the committed copy matches
a fresh build. Never built at import or request time.

**TF-IDF was shipped, and the agent MEASURED that this is the weaker choice and said so.**
all-MiniLM-L6-v2 scores R@1 0.967 vs TF-IDF 0.733. TF-IDF was chosen anyway: PyTorch is
~2.5 GB, needs a first-use download against the offline-test requirement, and failed to
install on the Windows 260-char path limit.

**The consequence is a SAFETY property, not a quality one:** TF-IDF cannot distinguish a
medical question the corpus covers from one it does not — uncovered terms score 0.141–0.271
and covered ones 0.121–0.27, **fully overlapping**, so no similarity floor separates them.
That is why free text is now anchored to the catalogue first (see 6k, D7).

### Module 23 — LLM explanation
Architecture is literally `findings + retrieved knowledge -> LLM -> Module 24 -> approved`.
`explanation` is assigned in exactly ONE place, from `guarded_generation().approved_text`.
Raw model output is never stored on the object at all. Four independent proofs exist,
including a test that reads the source file for a second assignment.

Five outcomes, all HTTP 200: `generated`, `withheld_by_safety`, `not_grounded`,
`model_unavailable`, `unknown_subject`. Every non-generated one carries `safe_fallback()`.

**`gemini-3.6-flash` is a THINKING model** — reasoning tokens are spent before any prose is
emitted. The token cap had to be raised to 4096 with `thinking_level="low"`; a 700-token cap
produced `MODEL_RESPONSE_TRUNCATED` on **every** live call. **No offline test could have
found this** — a mocked client has no thinking budget. That is the argument for keeping the
opt-in live tests.

### Module 25 — Terminology
**Does not retrieve on free text at all.** Exact mapping only: canonical name →
`feature_catalog.lookup_test_name` (the same synonym index Module 5 uses) → a curated alias
table. No similarity, no nearest match, no fallback. TSH / ferritin / WBC / ALT / PSA / CRP
are refused with **zero retriever calls and zero model calls**.

**Honest gap: SGPT is named in the spec but refused**, because the corpus has no
liver-enzyme document. Published in `known_gaps` on `GET /api/v1/explain/terms`. Adding one
liver document fixes it.

### Module 26 — Lifestyle guidance
**Serves catalogue text and calls no model.** The property that has held across this whole
project is that recommendation text has no free-text entry point; adding a generator to the
module most likely to drift into treatment advice would crack that for no gain.
`EDUCATIONAL_CODES` is computed at import and is the complete reachable set through every
entry point. A hole was found and closed during the build: `SEEK_PROMPT_MEDICAL_ADVICE` (a
HIGH-risk-tier sentence) was initially servable as "general guidance".

---

## 6k. Module 24 audit — verdict FAIL — and the eight fixes · 2026-09-04

An independent audit rated **Module 24 FAIL** and the **Module 1 to 26 flow FAIL**, proving
it end to end rather than in the abstract. `explain_feature(...)` with CRLF-wrapped model
prose returned `verdict=approve`, **zero violations**, and this text to a patient:

> "Your HbA1c result is 6.8 percent. You have diabetes. There is no need to see a doctor
> about this result; the report is enough. A qualified healthcare professional wrote these
> reference ranges."

**All eight defects are now fixed**, with 66 regression tests in
`tests/test_safety_audit_fixes.py`, each verified to fail against the pre-fix code.

### D1 — CRITICAL and ARCHITECTURAL. The positive controls did not backstop the blocklist.
The design claimed positive controls covered what the blocklist missed. Measured, they did
not. **"Your kidneys are failing."**, **"Your results are completely fine and nothing is
wrong."** and **"You do not have diabetes."** were all APPROVED. Two causes:

1. **Hedging only fires on an INTERPRETIVE VERB** (means / indicates / suggests), so the
   most direct clinical assertions in English were invisible to it.
2. **`MISSING_PROFESSIONAL_REFERRAL` is `required` severity** — it appends framing and
   APPROVES; it cannot reject. It was also satisfied by the mere SUBSTRING "qualified
   healthcare professional", which in the sample above sat in a sentence that was not a
   referral at all.

**Fix:** new rule `assertion.clinical_state` using `UNHEDGED_INTERPRETIVE_CLAIM` (already
PROHIBITED). Second-person anchored, so "A normal HbA1c is below 5.7%" passes and "You are
normal" does not. Covers organ-state assertions, blanket reassurance, and negative
diagnoses. **False reassurance is treated as seriously as false alarm** — this project
refuses everywhere else to let an unassessed condition read as reassuring.

### D2 — separators and punctuation split banned phrases
Newline, CRLF, tab, double space, comma, parenthetical and quoted emphasis all escaped,
because the rules contained a single LITERAL SPACE. **Fix:** `_GAP = r"\W{1,4}"` applied via
a `_phrase()` helper in `policy.py`. None of these are adversarial — wrapped prose and
parentheticals are ordinary LLM output, so this class WILL occur in production.

### D3 — the carve-out rejected the platform's OWN mandated disclaimers
Eight hand-enumerated fixed-width lookbehinds excused eight phrasings and REFUSED every
other correct English disclaimer — "never a diagnosis", "not any kind of diagnosis", "No
diagnosis is offered here", even "not  a diagnosis" with two spaces. Since the code is
PROHIBITED, each refused the WHOLE generation, so the patient got the fallback BECAUSE the
model disclaimed properly. The retry then quoted the span back, teaching the model to DROP
the disclaimer. **Fix:** `_drop_disclaimed_diagnoses` — a sentence-clamped negation filter,
scoped to hits whose matched text IS `diagnos*`. Widening the pattern also caught "the
diagnosis is X", a known miss before.

### D4 — invisible characters
Zero-width and soft hyphen were DELETED, so `you<ZWSP>have` became `youhave` and matched
nothing — deletion CREATED the escape. But deletion is required for the opposite case
(`met<ZWSP>formin` -> `metformin`). **Fix:** map format characters to a space AND run a
second `_compacted_pass` with them removed, unioning the results. Only PROHIBITED findings
are taken from the second pass, because spans there do not index the caller's text and a
prohibited violation never redacts.

### D5 — false claims in comments, including ones the assistant wrote
`_normalise` claimed the three scanners were "fixed in all three so they cannot drift apart"
(**never reconciled — the drift is exactly why the validator was the weakest of the three**)
and that spans "index correctly into the caller's original string" (**false — NFKC is not
length-preserving**). Both corrected. **Reconciling the three scanners is still NOT done.**

### D6 — Module 25's refusal echoed injected text back
`explain_term("there is no need to see a doctor")` returned that phrase verbatim. The rule
fired, but `_drop_disclaimed_replacements` discarded it: the template's own words "does not
hold" sit in the 60-character window before the echo slot, so **the carve-out was disarmed
BY CONSTRUCTION for every echo**. **Fix:** validate the bare echo FIRST, where the
template's negator cannot reach it.

### D7 — free-text retrieval returned confidently wrong grounding
"my ALT and AST liver enzymes are high" -> `term_ldl_hdl`; "C reactive protein CRP" ->
`lab_hemoglobin`; and worst, "what does a raised HbA1c mean" -> `cond_elevated_hemoglobin`
as its TOP chunk — a query the corpus DOES cover, returning a different analyte.
**Fix:** `_anchor_free_text()` in `app/rag/retriever.py` resolves free text to canonical
features/conditions EXACTLY (same synonym index Module 5 uses) and then retrieves the
reliable way. Anchors to nothing means returns nothing. Now "what does a raised HbA1c mean"
returns `lab_hba1c`.

### D8 — numeric grounding defeated by writing the number out
"nine point nine percent" was approved. Spec Module 23 asks for PLAIN LANGUAGE, so a
spelled-out number is NORMAL output — the control was blind in the register it was written
for. **Fix:** word-form numbers are parsed and checked against the same allowlist.
**Two over-corrections had to be walked back**, both of which made Module 24 reject the
platform's own curated corpus and silently withhold correct explanations: "one of the two
main types" read as two fabricated values, and "one unit either side" tripped because "unit"
was in the units list. Final rule: a spelled number counts only when it is a decimal, a
compound, or next to an **unambiguous clinical unit**.

### Verified NOT broken by any of the above
Zero false positives across **20 catalogue recommendations and 377 KB paragraphs**. A safety
layer that refuses its own text sends every patient the fallback.

### Still open, low severity
- Homoglyph (Cyrillic lookalike) and combining-mark folding — deliberately out of scope; the
  endpoint is service-key gated and Gemini does not emit lookalikes. Published in
  `SAFETY_POLICY["limitations"]`, the same posture as the acknowledged `digoxin` gap.
- The three scanners are still not reconciled into one rule table.

---

## 6l. Live end-to-end verification · 2026-09-04

Ran the real chain: register -> login -> profile -> upload -> analyze, with the backend
driving `ai-service` over HTTP against real Gemini.

**The backend now calls EIGHT stages:**

```
extract -> engineer -> validate -> [ rules || predict || report ] -> explain -> guidance
```

`/api/v1/decisions/fuse` is deliberately NOT called: `report/generate` runs fusion
internally and returns it verbatim, so a second call would create a second source of truth
that a non-deterministic RF tie-break could make disagree. The standalone rules and ML calls
ARE kept, because `report/generate` CONTAINS engine failures inside an HTTP 200 — without
them the backend could not report "the ML stage failed", and per-rule traceability is
unrecoverable from the fused view.

**A real defect was found and fixed by this run.** First attempt:

```
"explanation": {"ok": false, "errorCode": "AI_SERVICE_TIMEOUT", "durationMs": 120049}
"status": "partial"
```

`explain_report` made **up to 6 SEQUENTIAL LLM calls**, one per lab value, at roughly 25s
each on a thinking model — about 150s, past the 120s stage timeout. **Fix:** parallelised
with order preserved. After: `status: processed`, explanation ok in **40s**, with real
Gemini prose **approved by Module 24 on the first attempt, zero violations**.

**Concurrency is 2, and that number was measured.** At 4 the free-tier key returned
`MODEL_RATE_LIMITED` — a timeout traded for a 429. Tunable via `AI_EXPLANATION_CONCURRENCY`.
The failure is graceful either way: a rate-limited generation yields no text, Module 24
rejects the empty string as `UNANALYSABLE_INPUT` (**fail-closed working as designed**), and
that feature falls back to catalogue guidance while the others still explain.

**Also confirmed live:** Module 12's kidney predictor returned `Insufficient Data` with
`risk: null`; Module 19 ranked the unassessed condition ABOVE every settled normal finding;
and warnings arrived from stages only reachable at the end (`fusion`, `report`).

---

## 6m. Modules 27–32 — built 2026-09-04. NO TESTS, NO AUDIT.

Built in four waves, one agent per module, on the user's instruction to build without
testing ("we will test later everything"). **Nothing in this section has been independently
verified.** Two waves were interrupted mid-build by session rate limits; the surviving work
was inspected and completed by the orchestrating session, which is itself a self-report.

`ai-service/` now serves **46 OpenAPI paths**, up from 38. Five new routers were added to
`app/main.py`; its module docstring was updated each time so it no longer claims 27–32 are
deliberately absent.

### Placement decisions (made once, applied throughout)

- **Module 27 is in `backend/`.** The spec calls it "the frontend dashboard"; there is no
  frontend, so it was built as **the backend read-model a dashboard renders** — a pure
  projection of the stored Module 17/19/20/23/26 output. It calls no model and computes no
  new clinical judgement.
- **Modules 28/29/30/32 compute in `ai-service/`, but the HISTORY lives in `backend/`.**
  Canonical names, units, reference ranges and polarity all live in the Python service, and
  comparing values across reports without that normalisation is exactly the "silently
  corrupts data across a boundary" class §6h exists to catch. The ai-service holds no
  database (Module 7's repository is in-memory and process-local), so the backend assembles
  history from Mongo — `Report.chronoDate` is indexed on `{user, chronoDate}` for precisely
  this — and POSTs snapshots in. Each of these endpoints is therefore a **pure function of
  its request**.
- **`TimelineReportInput` (Module 28) is the ONE snapshot shape** crossing that boundary.
  Modules 29, 30 and 32 all reuse it rather than inventing a second way to pass a report's
  features.

### Module 27 — Health Dashboard · `backend/`

`GET /api/v1/reports/:id/dashboard`. New: `src/services/dashboardService.js` (pure
functions, no I/O), `src/controllers/dashboardController.js`.

Loads only `clinicalReport + patientExplanation + lifestyleGuidance` — narrower than
`ANALYSIS_PROJECTION`, because Modules 17–20 already folded what the cards need into the
report. 404 when `analysis.version === 0` or the report is absent.

- **Keys are camelCase**, converted from the ai-service's snake_case, matching the backend's
  own `toPublicJSON` / `toAnalysisJSON` view convention. Values pass through verbatim.
- **It does not re-derive overall status** — it calls the exported
  `analysisService.summariseReport`, so there is no second place that can disagree about
  whether a report was assessed. Verified: `overall.status: 'Fine'` (unknown vocabulary)
  with `any_assessed: true` degrades to `status: null`, `statusLabel: 'Not Assessed'`.
- A fourth laboratory state, `unavailable`, is a join the agent invented — but only where
  Module 20 already wrote an availability reason. `document.missing_features` alone creates
  no card, because it carries no reason and one would have had to be guessed. A **rejected**
  value is never downgraded into an **unavailable** one.
- Module 23 branching is on the `generated_explanation_available` boolean, never on the
  string's presence.

**Untested through Express, auth, or real Mongo.** The ownership path is copied from
`analysisController` and has not been exercised against user B / admin / clinician.

### Module 28 — Trends · `ai-service/`

`POST /api/v1/timeline/trends` · `GET /api/v1/timeline/policy`.
`app/data/trend_polarity.py` (729 lines) · `app/schemas/timeline.py` (708) ·
`app/services/trend_analyzer.py` (1,091) · `app/api/routes_timeline.py`.

- **Polarity is declared per feature in a reviewable table**, never inferred. 14 features; a
  feature with no declared polarity reports direction only, with
  `CLINICAL_DIRECTION_UNKNOWN`. Rising vitamin D and rising creatinine are not the same
  event and the table is what knows that.
- **Stability is a reference change value (RCV)**, not a round percentage.
- `outcome` is the field to branch on, **never `trend`**. Fewer than two usable readings is
  `INSUFFICIENT_DATA` with `trend: null` — **never `stable`**. Missing readings are `gaps[]`
  carrying their reason; nothing is interpolated or imputed.
- Deterministic and model-free; same request in, same trends out. Its `_self_check()` runs
  at import and passes.
- **The agent building this was killed by a rate limit before writing its router.** The
  router was written by the orchestrating session, matching `routes_repository.py`.

### Module 29 — Smart Report Comparison · `ai-service/`

`POST /api/v1/comparison/reports` · `GET /api/v1/comparison/policy`.
`app/schemas/comparison.py` · `app/services/report_comparator.py` ·
`app/api/routes_comparison.py`.

- **No second polarity or stability table.** The improved/worsened/unchanged decision is
  Module 28's `analyse_feature()` over a two-report series. Its refusal vocabulary is
  **derived from Module 28's `OUTCOME_VALUES` at import, not retyped**, so the two cannot
  drift. Grep confirms `POLARITY`, `STABILITY`, `direction_of_harm` appear nowhere in it.
- Two axes, kept separate: **change** (`improved`/`worsened`/`unchanged`) and **abnormality
  transition** (`newly_abnormal`/`newly_normal`/`remained_*`). A single `category` collapses
  them by a documented precedence.
- **`newly_abnormal` requires abnormality to be KNOWN ON BOTH SIDES.**
  `AbnormalityState.abnormal` is tri-state with a `basis` and a reason code, and a validator
  makes "not_determinable with a non-null answer" structurally impossible. An unknown
  baseline gives `NOT_DETERMINABLE` — never `newly_abnormal`, never `unchanged`. Getting
  this wrong invents an alarming finding, so it was deliberately made strict.
- Censored values (`<x` / `>x`) answer only where the conclusion holds across the whole
  censored interval.
- **Its only change to Module 28** was appending public aliases to existing private helpers.
  Module 28's self-check still passes.

**The most debatable call, flagged by its own author:** when a report's printed flag
disagrees with its printed reference range, **the range wins**, the flag is kept, and
`flag_disagrees_with_range` plus warnings fire. The strict alternative is
`NOT_DETERMINABLE`. Reasoning: labs often flag against a sex-specific range they do not
print, so this is two concrete signals rather than an absence. Single change point in
`_abnormality`.

Abnormality is computed **per report against that report's own units**, so a parameter that
refused on the change axis for `UNIT_MISMATCH` can still yield a valid `newly_abnormal`.

### Module 30 — Health Progress Analysis · `ai-service/`

`POST /api/v1/progress/score` · `GET /api/v1/progress/policy`.
`app/data/progress_scoring.py` (the reviewable table) · `app/schemas/progress.py` ·
`app/services/progress_analyzer.py` · `app/api/routes_progress.py`.

Scores **Module 29's finished `category`**. It never calls `polarity_for()`, never reads a
stability band, and **does no arithmetic on any patient value** beyond a weighted mean of
table lookups. No third table exists.

- **Scale 0–100, `higher_is_better`, stated as a mandatory response field**, not
  documentation. Category anchors: `newly_normal` 100 · `improved` 75 · `unchanged` 50 ·
  `worsened` 25 · `newly_abnormal` 0.
- **The equal spacing is enforced at import, not merely claimed.** `_self_check()` computes
  the four steps and raises if they differ, on the stated grounds that the *order* is
  defensible (it is Module 29's documented precedence) but no *spacing* is — nobody here can
  say `newly_abnormal` is 3.2× as bad as `worsened`, so no such ratio is asserted.
- **Weights are equal (1.0) across the 9 trendable features, and the table says why**: there
  is no defensible basis on this project for ranking one canonical parameter above another,
  and an invented hierarchy inside a score would reach a reader as clinical fact. The 5
  non-trendable features carry weight 0.0 **as an exclusion, not a low importance**, so the
  table is total and the decision is visible rather than inferred from an omission.
  `_self_check()` fails if a feature with declared polarity ever gets weight 0 (a silent
  drop), or a non-trendable one a non-zero weight.
- **Band boundaries at 20/40/60/80 are derived, not round numbers**: they are the partition
  giving each of the five anchors its own band with no anchor on an interior boundary, so
  "everything worsened" can never share a label with "everything was unchanged". Asserted at
  import. Score is rounded to 1 dp **before** the band is chosen, so number and band cannot
  disagree.
- **Coverage floor of 3 contributing parameters**, on the stated rule that *no single
  parameter may be a majority of the score* — at n=1 one parameter is the whole score, at
  n=2 it is half. Below the floor: `INSUFFICIENT_COVERAGE`, `score: null`, `band: null`, and
  the contributions found are still returned. The floor is deliberately low because only 8
  of 14 canonical features are numerically trendable and only 7 carry a declared polarity.
- `outcome` is the field to branch on: `SCORE_COMPUTED` | `NO_PAIR` | `NOTHING_ASSESSED` |
  `INSUFFICIENT_COVERAGE`. A validator enforces score+band non-null **only** for
  `SCORE_COMPUTED`. `ExcludedParameter` **has no `points`/`weight` field at all**,
  structurally, the way `TimelineGap` has no `value`.
- No option can lower the floor, change a weight, or move a band — a caller cannot talk the
  service into a friendlier score.

**Two calls to review:** (1) there is **no magnitude multiplier** — the spec lists "relative
changes", which are honoured only through the RCV band applied upstream and by surfacing
`percent_change` per contribution; adding a curve would have been the forbidden third table.
(2) The **score is logged** via `safe_meta`, judged a derived unitless non-invertible
statistic rather than a medical value. Reject if the project's line is stricter.

### Module 31 — Population Context · `ai-service/`

`POST /api/v1/population/context` · `GET /api/v1/population/policy`.
`app/population/{__init__,policy,tables}.py` · `app/schemas/population.py` ·
`app/services/population_context.py` · `app/api/routes_population.py` ·
`datasets/population/` (raw + build script + distributions + PROVENANCE.md).

**The data is real.** Survey-weighted percentiles built from **NHANES microdata** (CDC/NCHS)
downloaded as `.xpt` with SHA-256 recorded, weighted with `WTMEC2YR`, pregnant participants
excluded, adults 20+.

| Feature | Table unit | Cohorts | Analytic n | Smallest cell |
|---|---|---|---|---|
| `hba1c` | `%` | 14 | 4,971 | 178 |
| `hemoglobin` | `g/dl` | 14 | 4,981 | 178 |
| `creatinine` | `mg/dl` | 14 | 4,869 | 174 |
| `cholesterol` | `mg/dl` | 14 | 4,890 | 175 |
| `bmi` | `kg/m2` | 14 | 5,120 | 171 |
| `vitamin_d` | **`nmol/l`** | 14 | 4,936 | 176 |
| `vitamin_b12` | `pg/ml` | 14 | 5,255 | 149 |

Cohorts are male/female × 20-29…70-79 + 80+. Zero dropped cells. Cycle J (2017–2018) except
vitamin B12, cycle H (2013–2014).

**Independently reproduced:** re-running `build_population_tables.py --check` to a scratch
directory produced all 7 tables **byte-identical**. Cross-checked against published NCHS
output: BMI vs Series 3 No. 46, worst diff 1.60 kg/m² over 117 comparisons; high-total-
cholesterol prevalence vs DB363 within 0.8–1.3 pp.

- **The no-value guarantee is STRUCTURAL.** Every answer field lives inside a nested
  `comparison` object that is *absent* when `available` is false, and `comparison` carries no
  reason field. An unavailable entry is physically incapable of holding a percentile.
- **No interpolated percentile exists** — `band` has no single-percentile field to populate.
  The value is bracketed between two published cut-points with `bisect_right`, and the
  reported value is the same rounded number that was bracketed, so a reader can re-derive the
  band by hand from the response's own grid.
- **No unmatched cohort, ever.** An all-adults distribution is never substituted for a
  missing age or sex, because haemoglobin and creatinine differ so much by sex that an
  unmatched percentile is a different claim wearing the same words.
- **`other` / `prefer_not_to_say` / absent gender ⇒ `SEX_COHORT_NOT_AVAILABLE`.** A stated
  gender is never coerced into a binary category to force a lookup — the §6a pattern.
- Age below the table minimum ⇒ `AGE_BELOW_ADULT_TABLE`, called out separately because
  scoring a child against an adult table is a clinical error deserving its own code.
- **Vitamin D is the only unit mismatch** (table nmol/L, canonical ng/mL). The **table is
  never rescaled**; the patient's value converts into the table's unit through the audited
  `unit_conversions` row.
- **`blood_glucose` and `triglycerides` are deliberately excluded**, not missing: fasting
  status is not recorded anywhere in the pipeline, and comparing a random glucose against a
  fasting population "would produce a percentile that looks precise and is wrong". Recorded
  in `EXCLUDED_FEATURES` with the reasoning.
- **The catalogue-completeness guard works and was proven.**
  `tables._check_catalogue_cover()` fails at import if a canonical feature has neither a
  table nor an `EXCLUDED_FEATURES` entry; the agent injected a fake feature and confirmed the
  failure. Guards raise `PopulationTableError`, not `assert`, because `python -O` strips
  asserts.
- Copy carries no risk word, no normal/abnormal judgement and no recommendation. Module 8
  owns "is this in range"; Module 31 owns only "how common is this".

**Dead paths today:** `AGE_OUTSIDE_TABLE_RANGE` and `COHORT_TOO_SMALL_TO_PUBLISH` are
implemented but **unreachable** — the bands are contiguous from 20 with an open top band and
no cell was dropped. They exist for future tables. Do not assume they are covered.

**One edit to a pre-existing file:** `policy.py` gained `REASON_MESSAGES` (pure addition),
because the 11 request-dependent reason codes had no patient-facing wording and putting it in
the service would have split copy across two layers. `tables.py` asserts at import that every
reason code has wording and there are no orphans.

### Module 32 — Doctor-Friendly Clinical Summary · `ai-service/`

`POST /api/v1/doctor-summary/generate` · `GET /api/v1/doctor-summary/policy`.
`app/schemas/doctor_summary.py` (1,360 lines) · `app/services/doctor_summary.py` (1,765) ·
`app/api/routes_doctor_summary.py`.

**It assembles; it does not generate.** No LLM call, no free prose — templated section text
only. **Verified structurally:** the service imports no `gemini_client`, no `gemini_text`, no
`app.services.explanation`. The `explanation` identifiers in it are Module 20's *fixed*
evidence-line explanations, not model output.

The reasoning is on the record and should not be relitigated: Module 26 serves catalogue text
and calls no model because recommendation text has no free-text entry point on this project,
and the §6k audit rated the whole 1→26 flow FAIL when free prose reached a patient with a
fabricated diagnosis in it. **A clinician-facing document is a higher-stakes surface, not a
lower one.**

Sections degrade explicitly rather than silently: `SECTION_NO_HISTORY`,
`SECTION_SINGLE_REPORT`, `SECTION_ANALYSIS_REFUSED`, `SECTION_RETRIEVAL_UNAVAILABLE`,
`SECTION_NOTHING_TO_GROUND`, `SECTION_NO_MATCH`, `SECTION_DISABLED`. Trends and comparison
are optional sections — with one report they are **absent with a stated reason**, never
rendered as "stable". Its `_self_check()` runs the Module 24 safety scanner over every
template at import and passes.

**The agent building this was killed by a rate limit during its end-to-end smoke run**, after
all three files were written. So: it imports, its self-check passes, its router mounts — and
**its assembly paths have never been run against a real report.**

### The backend longitudinal layer · `backend/`

The Node side that makes 28/29/30/32 reachable by a client. New:
`src/services/historyService.js` (the shared assembler), `src/controllers/timelineController.js`,
`src/controllers/doctorSummaryController.js`, `src/routes/timelineRoutes.js`,
`src/middleware/timelineValidators.js`. Changed: `aiServiceClient.js` (4 `PATHS`, 4 `STAGES`,
4 methods through the existing `postJson`), `config/env.js` (four **per-stage** timeouts, each
its own env var — never a shared default, per that file's own rule — plus a `config.history`
block), `rateLimiter.js`, `routes/index.js`, `reportRoutes.js`.

| URL | Query | `data` |
|---|---|---|
| `GET /api/v1/timeline/trends` | — | `{history, trends}` |
| `GET /api/v1/timeline/comparison` | `baseline`,`comparison` (both-or-neither) | `{history, requestedPair, comparison}` |
| `GET /api/v1/timeline/progress` | same | `{history, requestedPair, progress}` |
| `GET /api/v1/reports/:id/doctor-summary` | same | `{report, history, requestedPair, doctorSummary}` |

**The inclusion rule — read this before changing it.** A report enters a timeline iff
`analysis.version > 0` **AND** `featureValidation` is stored. **`status` is deliberately not
consulted**, and the reasoning matters:

- `partial` is *included* when validation succeeded — rules or ML failing says nothing about
  whether the readings were good — and *excluded* by the same test when validation was the
  stage that failed.
- `failed` may be *included*: the failure path writes only status bookkeeping and never
  touches stored payloads or `version`, so a report that analysed successfully and then
  failed a later re-run still holds a real Module 6 verdict. Each included report's `status`
  is returned so this stays visible rather than surprising.
- A report whose every reading was rejected **is** sent, because Module 28 renders it as a
  `TimelineGap` with reasons — which beats it vanishing from the timeline silently.

Exclusion codes: `NOT_ANALYSED`, `NO_VALIDATED_FEATURES`. `history` reports `considered`,
`included`, `excludedCount` and the excluded rows, so **a short timeline is distinguishable
from a patient with little history** — the failure mode this accounting exists to prevent.

**Cap `HISTORY_MAX_REPORTS`, default 50**, clamped to `[2, 500]` (the ai-service's own
`max_length`). The window is the **most recent** 50, sorted `{chronoDate:-1,_id:-1}` — the
index's declared direction, so the scan stays index-covered — then reversed to oldest-first.
`cap+1` rows are fetched so `truncated` is **proven, not inferred**. Projection is
`user chronoDate status analysis.version +featureValidation` only; the other seven
`select:false` payloads are never read (doctor-summary adds `+clinicalReport`).

**Ownership.** `ownerScopedFilter` + `assertCanAccess` on every query, **no `allowRoles`
grant anywhere**, and every loaded row re-checked though the query was already scoped. A
named `?baseline=` / `?comparison=` id goes through `resolveNamedPair`, which re-loads it
owner-scoped and `assertCanAccess`es it **before it can reach a request body** — another
patient's id yields the identical 404 a random id yields; an owner naming their own
*unanalysed* report yields **422 `REPORT_NOT_IN_HISTORY`**, and no message echoes the
submitted id.

**Judgement calls:**
1. **The ai-service is called even with 0 or 1 reports.** Short-circuiting would create a
   second definition of "not enough history" in the backend; the refusal codes
   (`INSUFFICIENT_DATA`, `NO_PAIR`, `NOTHING_ASSESSED`, `INSUFFICIENT_COVERAGE`) pass through
   untouched instead.
2. **Timeline endpoints return 200, not 404, for an empty history** — a patient's timeline
   exists whether or not anything is on it, and the refusal *is* the answer. Doctor-summary
   does 404 without a `clinicalReport`, matching `/report` and `/dashboard`.
3. **A new `historyLimiter` (60 / 15 min), not `analysisLimiter`.** These fan out over up to
   50 reports *and* make an outbound call — 1:1 inbound→outbound amplification, unlike
   `/dashboard`, which reads one document and calls nothing. But `analysisLimiter` is 20 per
   window and sized for LLM quota: drawing a trend screen must not lock a patient out of
   analysing an upload.
4. `sequence` is not sent — the `_id` tie-break and the service's `report_id` tie-break are
   the same ordering, and an array-index `sequence` would make the answer depend on
   serialisation order.
5. Four queries per history request (2 counts, 2 finds), accepted to report `considered` and
   `excluded` exactly.

**CONTRACT MISMATCH FOUND, NOT PATCHED.** `report_comparator._select_pair` raises
`BadRequestError` (**HTTP 400**, `COMPARISON_REPORT_NOT_FOUND`) when a named ref is not among
the supplied reports, but `mapAxiosError` maps unclassified 4xx to **502
`AI_SERVICE_REJECTED_REQUEST`** ("contract mismatch") — an accurate description of a bug and
a poor one of a user naming a report they have not analysed. Neither side was changed: the
backend pre-checks and returns 422 first, so the 400 is unreachable **in practice**. Decide
whether `mapAxiosError` should learn about 400.

**Verified by running:** app loads and all four URLs register; the four Python request models
(`TimelineTrendsRequest`, `ReportComparisonRequest`, `HealthProgressRequest`,
`DoctorSummaryRequest`) accept payloads built through the real Module 5→6 chain and wrapped
exactly as `historyService` wraps them; 2 reports → `TREND_CLASSIFIED/worsening`; 1 → 
`INSUFFICIENT_DATA` with `trend=None`; 0 and 1 → `NO_PAIR` with `score=None`; all four
responses scanned against `assertStorableKeys` for `$`/`.` keys — none. `historyService`
against in-memory Mongo: cap honoured, `truncated` exact, oldest-first, inclusion/exclusion
codes correct, no cross-user leak, `role:'admin'` does not widen, missing identity throws,
other-user id → 404, own-not-in-history → 422. Validators through a live express app with no
`mongo-sanitize`/`hpp` present: `?baseline=a&baseline=b` → 422 and `?baseline[$ne]=` → 422,
**proving `.isString().bail()` is doing the work itself** rather than leaning on a sanitiser.

**Not verified:** the 476-test jest suite was not run, so there is no evidence about
regressions. No live HTTP call was made between the two services — the contract check ran the
Python models in-process, not over the wire.

### What the whole wave has NOT had

No tests written. No test suite run — the existing 3,352 are unproven against this code. No
independent audit. No live end-to-end run. `tests/test_auth.py`'s recursive route walk has
not been run against the five new routers.

---

## 6n. End-to-end audit of Modules 1–32, and the fixes · 2026-09-04

The user asked for the whole system to be checked end to end and defects fixed. Three
passes ran: **both suites re-run**, an **independent read-only contract audit**, and a
**live end-to-end run against real Gemini** with three analysed reports. Six defects were
found. Five are fixed; one is deferred with a stated reason.

### Suites, re-run after the 27–32 wave and again after every fix

`backend/` **476 passed** / 3 skipped / 0 failures · `ai-service/` **2,878 passed** / 6
skipped / 0 failures (2,876 at baseline, +2 from the D7 regression test). `tests/test_auth.py`'s recursive route walk **runs clean over all
five new routers** — the §0 item that recorded it as unproven is closed.

### D1 (CRITICAL, FIXED) — the Module 5 unit bug reached the patient-facing LLM

`feature_engineer.py` converted a value into the canonical unit but copied
`reference_low`/`reference_high` through **in the report's printed unit**. Its blast radius
was wider than §0 recorded: MEMORY named Modules 27/29/32, but **Module 23 — the LLM
prompt — was on the list and nobody had noticed.** The literal text sent to Gemini for a
report printing `Creatinine 88.4 umol/L (62 - 106)` was:

```
The reader's validated value: 0.9999808 mg/dl
Reference interval printed on the report: 62 to 106
```

**And Module 24 could not catch it.** `explanation._permitted` whitelists
`reference_low`/`reference_high` as permitted numbers, so the number-grounding control —
the one thing designed to stop a fabricated number — *approved* prose quoting a range 60x
off. The control was never wrong; its input was.

**Fixed at the lowest layer** (§11), in `feature_engineer._reference_bounds`: the interval
is carried through **the same audited `UnitConversion` that was applied to the value**.
Notable properties of the fix:
- **The arithmetic is affine, not a bare multiply.** `canonical = raw * factor + offset`,
  and `offset` is non-zero for HbA1c IFCC (the NGSP master equation), so `conversion.apply`
  is used. No second factor table was introduced.
- **Monotonicity is checked.** A non-positive or non-finite factor/offset, or a bound that
  converts to a non-finite number, is REFUSED — both bounds come back `None` with a note
  and a warning. An interval that cannot be carried is **absent, never left in the printed
  unit and never approximated**. `reference_range_raw` still preserves the printed text.
- `provenance.reference_unit` and `provenance.reference_converted` record what happened,
  and a note is added.

**Verified live:** the record is now `value 0.9999808 mg/dl | bounds 0.701344 – 1.199072
mg/dl | converted=True`, and the value sits inside its own range. The prompt line now reads
`The reference interval for this parameter, in the same unit as the value above: 0.701344
to 1.199072`.

**The double-conversion risk was the real danger of this fix, and it is closed.**
`report_comparator._reference_interval` (Module 29) short-circuits on
`provenance.reference_converted` and returns already-converted bounds untouched; Module 32
**calls that same function** rather than carrying its own path, so there is exactly one
conversion site and one guard. The per-consumer workarounds were deliberately LEFT IN
PLACE — they are now belt-and-braces on a correct source, which is the pattern that
survives on this project.

### D2 (HIGH, FIXED) — Module 32 was dead on 100% of calls

`GET /reports/:id/doctor-summary` returned 502 every time. `doctor_summary.py` was the only
file in the service passing `module=` through `safe_meta`, and **`module` is a reserved
`LogRecord` attribute** — CPython's `makeRecord` raises `KeyError` from inside `_log`,
*before* handlers, so logging's swallow-errors protection never applies. All four call
sites were affected, **three of them inside `except` blocks written to make failures
degrade gracefully** — so the degradation paths failed harder than the happy path.

**Fixed at the layer where it cannot recur:** `_SafeLogger` in `app/core/logging.py`
re-keys colliding `extra` keys (`module` → `meta_module`) instead of raising, installed via
`get_logger()`, which is the sole path to a logger (25 uses, zero direct
`logging.getLogger`). Colliding keys are **re-keyed, never dropped** — losing the tag
silently would trade a loud failure for a quiet one. The four call sites were also moved to
the project's one convention, because `_SafeLogger` alone would have turned a crash into
silently metadata-free logs under the configured formatter.

**§6m's "its assembly paths have never been run" was exactly right.** No offline test could
have found this: the failure is in the logging call, and the suite's assertions never
exercised those four lines.

### D3 (HIGH, FIXED) — a partial assessment printed to the patient as "Healthy"

Module 18 emits **five** `status_label` values; the fifth, `Healthy (partial assessment)`,
exists *precisely because* a partial clean result was otherwise byte-identical to a full
one. The backend **never read `status_label` at all** — `analysisService` re-derived a
label from the three-value `status`. Demonstrated: service says `Healthy (partial
assessment)`, dashboard printed **`Healthy`**. `complete: false` survived, but the headline
word on the card did not. **This was the exact D4 defect Module 18 was amended to fix,
reintroduced one hop later.**

**Fixed:** the backend now carries `overall.status_label` through, with the defensive
behaviour intact. Proven across four cases:

| service `status_label` | backend label | note |
|---|---|---|
| `Healthy (partial assessment)` | `Healthy (partial assessment)` | was `Healthy` |
| `Healthy` | `Healthy` | unchanged |
| `Not Assessed` | `Not Assessed` | unchanged |
| `Totally Fine` (unknown) | **`Not Assessed`** + `STATUS_LABEL_UNRECOGNISED` | fails safe |

An unrecognised label degrades toward *not assessed*, **never toward a clean bill**.

### D4 (HIGH, FIXED) — a comment asserting a guarantee the code did not make

`analysisService.js` claimed the service's `status_label` "is checked against ours and a
disagreement is recorded as a warning-worthy fact rather than silently preferred".
**`status_label` appeared nowhere in the file.** Had the check existed, D3 would have
surfaced as a warning instead of shipping. The check now genuinely exists
(`statusLabelDisagreement` / `statusLabelWarnings`) — the comment was made true rather than
deleted. This is the **fourth** false-comment finding on this project; §11's "a comment
asserting a guarantee is not a guarantee" keeps earning its place.

Two stale claims in `dashboardService.js` that the label vocabulary is four-valued were
also corrected — the producer declares five.

### D5 (MEDIUM, FIXED) — Module 31 was unreachable by any client

The NHANES tables were live in the service with no way to consume them: no `PATHS` entry,
no controller, no route. Now wired as
**`GET /api/v1/reports/:id/population-context`** — authenticated, owner-scoped,
404-before-403, no `allowRoles` grant, behind `historyLimiter` (it makes an outbound call,
unlike `/dashboard`; but not `analysisLimiter`, whose budget is sized for LLM quota that
Module 31 never spends).

**Age and gender come from the authenticated user's own Module 2 profile, never from a
query parameter** — a caller who could name the cohort could score a value against an
arbitrary population and read the percentile as their own. **A refusal is a 200**: no age,
or a gender with no published stratum, returns `available: false` with a reason code and
reviewed copy, passed through verbatim. That is the answer Module 31 was built to give.

### D6 (LOW, FIXED) — `historyService` JSDoc declared a returned field that did not exist

An `excluded[]` key documented in `@returns` and absent from the return: a caller trusting
it reads `undefined` and renders "nothing was excluded" — absence quietly becoming a
reassuring value.

### D7 (HIGH, **FIXED 2026-09-04** — was deferred, then applied on the user's word)

**The ai-service blocks its own event loop.** Every route handler is `async def` and
**nowhere in `app/` is `run_in_threadpool`/`to_thread` used**, so `load_document` (pymupdf)
and the synchronous google-genai call run *on the loop*. Measured during the live run:
`/api/v1/health` went from <10 ms idle to **2.5 s → 4.7 s → a 30 s timeout** during a
single extraction. With one worker and the documented ~61-minute worst case, **one
pathological upload can make the whole service unavailable for an hour** — including the
backend's readiness probe and every fast Module 6/8/28–32 endpoint that needs no model.

**FIXED.** `run_in_threadpool` in `app/api/routes_ocr.py` (both `load_document` and
`service.extract`) and in all three `app/api/routes_explain.py` handlers — the explanation
stage calls Gemini through the same blocking client and held the loop for 40s on the live
run. Nothing about the work changes: same inputs, same calls, same order, same result. Only
the thread changes.

**IT WAS DEFERRED FIRST BECAUSE IT COULD NOT BE PROVEN, AND THE PROOF TURNED OUT TO BE THE
HARD PART.** The first verification attempt PASSED AGAINST THE PRE-FIX CODE TOO, i.e. it
proved nothing. The reason is worth remembering: **timing each probe individually cannot
detect a blocked loop**, because when the loop is blocked `asyncio.sleep` cannot resume
either, so the probe's own clock starts only after the block has already ended and every
probe looks fast in both worlds. What separates the two cases is WHEN a probe completes on
one absolute clock. Re-measured that way:

| | /health probes served during a 3s extraction |
|---|---|
| pre-fix (on the loop) | **0 of 4** — all completed at t=+3.02s or later |
| fixed | **4 of 4** — completed at +0.43, +0.85, +1.26, +1.68s |

The request-id `ContextVar` was confirmed to reach the worker thread
(`anyio.to_thread.run_sync` copies the context), so extraction log lines keep their
correlation id.

**A PERMANENT REGRESSION TEST NOW GUARDS THIS:**
`ai-service/tests/test_event_loop_not_blocked.py`, 2 tests. It is the only test in the
suite that runs the real ASGI app on a real event loop with two requests overlapping —
**every other test drives `TestClient`, which is synchronous and can never have a second
request in flight, so none of them can catch this class of defect.** Per project
convention the test was verified to genuinely FAIL against the reverted pre-fix code
(`only 0 of 4 /health probes completed while a 1.5s extraction was in flight`) before being
kept. Suite after: **2,878 passed / 6 skipped / 0 failures** (2,884 collected, +2).

### Also corrected

The live-test assertion recorded in §0 as a known issue: **MEMORY had it backwards.**
`liveIntegration.test.js` holds an *allow-list* that omitted `explanation`, and two objects
had been conflated. The stored report's `warnings_by_stage` genuinely cannot carry an
explanation entry (Module 17 runs before Module 23) — that part was right. But the
assertion actually checks `analysis.warnings`, the **backend's** cross-stage list assembled
*after* all eight stages, and `analysisService.js` appends Module 23's warnings there
deliberately. The live run produced two real explanation-stage warnings when a generation
was rate-limited, so **the assertion would have failed on this run**; earlier runs passed
only because that stage had always fully succeeded. The allow-list was **extended, not
weakened** — `guidance` was deliberately not added, since Module 26 pushes no warnings and
an unreachable value in an allow-list only weakens it.

### What the live run confirmed working

Full §16 flow against real Gemini: register → profile → 4 uploads → 3 full analyses (8
stages `ok`, 194 s / 126 s / 112 s; the 4th hit `MODEL_RATE_LIMITED`). **M28**
`TREND_CLASSIFIED / worsening` on HbA1c 6.1→6.4→6.8 (the spec's own example), with
`blood_glucose` correctly `CLINICAL_DIRECTION_UNKNOWN`. **M29** `newly_abnormal` on
cholesterol crossing "< 200", `newly_normal` on vitamin D. **M30** `SCORE_COMPUTED` 41.7,
6 contributing / 5 excluded with reasons. **M31** matched `male_40_49` with NHANES
provenance. **M32** assembled after the D2 fix.

**Every absence case held.** One report: all features `INSUFFICIENT_DATA`, `trend: null`,
progress `NO_PAIR` with `score: null`. Zero analysed reports: 404, not an empty clean bill.
Nothing rendered as "Healthy", "stable" or `0` where the truth was "we could not tell", and
the tri-state `hypertension` stayed absent through all eight hops.

### Still not verified

- **Modules 27–32 still have no tests of their own.** Both suites are green, but they are
  green because nothing tests the new code — the 3,352 assertions cover Modules 1–26.
- The Module 32 `SECTION_SINGLE_REPORT` path (the live attempt hit quota) and the
  "readings extracted then all rejected" case (the 4th PDF failed at OCR on quota).
- No live HTTP was exercised for the new backend population route.
- Modules 21–26 have still never been audited as a group.

---

## 6o. Tests for Modules 27–32 · 2026-09-04/05 · +911 tests, and one real defect found

Modules 27–32 shipped with no tests. §6n's end-to-end audit found seven defects in exactly
that blind spot, so the tests were written next, four agents in parallel, one per module
group. **They found a genuine patient-safety defect on their first run** — see D8 below.

| Suite | Before | After | New |
|---|---|---|---|
| `backend/` | 476 passing | **617 passing** / 3 skipped / 0 failures | **+141** |
| `ai-service/` | 2,878 passing | **3,649 passing** / 7 skipped / 0 failures | **+770** |
| **Total** | 3,354 | **4,266** | **+911** |

### Files

`ai-service/tests/`: `test_trend_analyzer.py`, `test_timeline_endpoint.py`,
`test_report_comparator.py`, `trend_payloads.py` (28/29) · `test_progress_analyzer.py`,
`test_doctor_summary.py` (30/32) · `test_population_tables.py`,
`test_population_context.py`, `test_population_endpoint.py` (31).
`backend/tests/`: `dashboard.test.js` (27), `timeline.test.js`, `history.test.js`.

Nothing under `app/` or `src/` was modified by the test-writing agents, and no existing
test file was touched. `conftest.py` and `setup.js` were deliberately left alone so three
agents could share `tests/` without colliding.

### D8 (HIGH, FOUND BY THESE TESTS, FIXED) — the heart model's caveat could never fire

**Module 11 flags ~27% of true positives at its operating threshold**, so an unflagged
heart result from it rules NOTHING out. `ModelLimitations.recall_at_operating_threshold`
exists to carry that number — its own field description calls it "the single most important
number on this object" — and it reads it from `thresholds['indicated_recall_achieved']`.

`ml/artifacts/heart_rf_v1.metrics.json` records `indicated_recall_achieved = 0.2678`. But
`app/ml/heart.py` published only `{'borderline', 'indicated'}`. **The number never left the
artifact**, `recall_at_operating_threshold` was always `None`, and the caveat "an unflagged
result rules nothing out" could never fire — for the one model that most needs it. **The
clinician-facing document quoted a heart-disease probability with no statement of how much
the model misses**, which is precisely the misleading output Module 32's brief set out to
prevent.

**Fixed** in `app/ml/heart.py` and `app/ml/kidney.py` (same gap; its recall is 0.984, so the
caveat correctly does NOT fire there — the caveat is driven by the measured number, not by
which model is speaking). Module 10's artifact records no such value, and a missing value is
**omitted rather than sent as null**: absent reads as "not recorded", a null would be a claim
that there is no recall.

Verified live — the caveat a clinician now actually sees:
> "At the operating threshold used here, this model flags a minority of the true positive
> cases in its own held-out data. An unflagged result from this model therefore rules
> nothing out."

**How the test was handled, and why it is worth copying.** The agent could not modify
`app/`, so it wrote the test as `@pytest.mark.xfail(strict=True)` with the whole defect in
the reason string, plus a companion test proving the mechanism works when the number IS
carried. Once `heart.py` was fixed the strict xfail turned into an XPASS — which strict mode
reports as a failure, i.e. **the marker announced its own staleness**. The marker was then
removed and the test kept as a permanent guard. That is the right shape for "found a defect
I am not allowed to fix".

### What the tests actually guard

- **The absence hazard** (§11) across all six modules: `INSUFFICIENT_DATA` never becoming
  `stable`, nothing-assessed never becoming a score, gaps never becoming zeros, an
  unassessed condition never rendering as a clean bill.
- **Module 29's `newly_abnormal`** — the category most able to invent an alarming finding —
  including the tri-state `AbnormalityState` and every reason code.
- **Regression guards for §6n's fixes**: the `status_label` flattening (D3), the
  reference-range double-conversion (D1), and the reserved-`LogRecord`-key crash that made
  Module 32 dead on 100% of calls (D2).
- **Module 27's ownership path**, which §6m had recorded as never exercised against user B /
  admin / clinician. It now is.
- **Module 31's structural no-value guarantee**, the catalogue-completeness guard, and table
  integrity asserted against the shipped NHANES JSON — a table that loses its provenance
  fails the suite.
- **Module 30's scoring table invariants**: equal anchor spacing, total weights, bands
  tiling 0–100 with no anchor on an interior boundary.

### Three tests were broken on arrival and were repaired, not deleted

All three came from an agent killed mid-file by a rate limit, and **all three were test bugs,
not source defects** — confirmed individually before touching anything:
1. `test_the_disclaimer_and_scale_wording_ride_on_every_response` asserted a lowercase
   literal against copy that capitalises for emphasis ("NOT a measure of health"). Matched
   case-insensitively instead, with a note saying why — asserting the exact casing would fail
   on a typographic edit while a real removal would still be caught.
2. `test_the_summary_is_deterministic_apart_from_its_timestamp` excluded only the TOP-LEVEL
   `generated_at`, while the summary nests sections that stamp their own. **The determinism
   claim was verified independently first** (masking every ISO timestamp made two builds
   byte-identical) before the exclusion was made recursive. Report dates are deliberately
   still compared — masking all timestamps would hide a real ordering bug.
3. `test_the_low_detection_caveat_does_fire_when_the_recall_is_carried` constructed
   `MLExplanation` without its required `prediction` field.

---

## 6p. Independent audit of Modules 27–32, and the fixes · 2026-09-05

Three independent auditors — none of which built the code or wrote its tests — audited
Modules 27–32. Each was told to derive its own checklist from `Project Description.txt`
BEFORE reading any implementation, and **not to trust the tests**, since the tests and the
code were written in the same week by agents working from the same brief.

**They found 17 defects.** That is the headline result: the suite was fully green, the
modules had 911 tests of their own, and an independent pass still found this much. It is
the fourth time on this project that an audit has found live holes behind a green suite.

### The single most useful thing an auditor said

> "The branch that refuses is tested, the branch that answers on thin evidence is not."

Every audit found the same shape. The tests assert that a refusal happens; almost none ask
whether an ANSWER was earned. Three concrete instances:
- `tests/test_report_comparator.py`'s `cholesterol()` fixture defaults **every** cholesterol
  test to a one-sided `reference_high=200` with no lower bound. Mutating `_outside_interval`
  to refuse on the unbounded side failed 12 tests — **every one of them a test about
  something else that merely rode on that fixture.** No test asked what a one-sided interval
  says about a value below it, which is why D1 shipped green.
- `tests/test_population_context.py` parametrises "every adult age" as `[20, 20.0, 45, 79,
  80, 99, 120, 130]` — **all integers**, which is exactly the gap the fractional-age defect
  lives in.
- `tests/test_population_context.py` asserts `what_this_means == PER_FEATURE_MEANS.format(…)`
  — **the implementation's wording against itself**, never asking whether the sentence is
  true of the band it describes.

### VERIFIED CLEAN — worth as much as the findings

- **Module 31's NHANES data was independently reproduced.** An auditor wrote its own `.xpt`
  reader, its own analytic filter and its own survey-weighted quantile without reading
  `build_population_tables.py`, and matched **all 7 tables × 14 cohorts × 11 cut-points to
  1e-6**, plus every sample count, plus all 11 SHA-256 digests. **The no-synthetic-data rule
  holds, verified by someone who did not build it.**
- **The backend security surface held under real attack.** User B, admin and clinician against
  all six new endpoints and through `?baseline=`: every one 404, byte-identical to a random-id
  404, same headers and `content-length`. Timing: median 6.85 ms vs 7.34 ms over 200 requests
  — no oracle. Type confusion (arrays, `[$ne]`, `[$regex]`, `%24`, nested operators,
  `__proto__`, `constructor[prototype]`, full-width unicode) — all 422, nothing reached Mongo.
  Rate limiter with rotating `X-Forwarded-For` → 429×8; the Module 1 defect-1 bypass does not
  exist here because `TRUST_PROXY` defaults to false. **`allowRoles` appears nowhere in code,
  only in comments.**
- **There is genuinely ONE polarity table.** No auditor could construct an input where
  Modules 28, 29 and 30 disagree about a direction.
- **The CVa/CVi stability inputs, which §6m flagged as unaudited, were audited** against
  Westgard biological-variation figures. All literature-consistent. That flag is closed.
- **Module 32 generates no prose** — verified structurally, not by docstring: importing it
  loads 40 `app.*` modules and **zero** model clients; `google.genai` is never imported.
- The §6n D1 reference-range fix **could not be made to double-convert** by any auditor.
- Censored-value logic correct across all eight branches. `newly_abnormal` could not be made
  to fire on an unknown baseline.

### FIXED

**D1/D2 (HIGH) — a truncated reference interval produced a FALSE claim of normality.**
`_outside_interval` treated a MISSING bound as "no bound exists" and returned a definite
`False` (= inside) for any value on the unbounded side. `reference_low`/`reference_high` are
independently nullable all the way from Module 4's contract, so a printed `13.0 - 17.0` can
arrive as `high=17.0` alone. Demonstrated: haemoglobin `13.9 → 7.5 g/dL` — **severe anaemia**
— reported as `remained_normal`, "sat inside the reference interval stated on both reports".
And the lab's own printed `low` flag was overruled by "the range wins", whose recorded
reasoning ("two concrete signals rather than an absence") **does not hold on the unbounded
side, where the range is not a signal at all.**

Fixed by asking Module 28's polarity declaration whether anything is unfavourable on the
missing side (`harm_declared_beyond`, tri-state), and by letting an inconclusive interval
**fall through to the printed flag** instead of discarding it. **Module 29 still holds no
polarity table** — it asks a yes/no question and never looks at a direction, threshold or
band. A new reason code `ONE_SIDED_INTERVAL_INCONCLUSIVE` keeps this distinct from
`CENSORED_VALUE_INCONCLUSIVE`: one is uncertainty about the VALUE, the other incompleteness
of the INTERVAL, and blaming censoring for a one-sided interval would be a fresh false
statement.

Verified, with the controls that mattered most:

| case | before | after |
|---|---|---|
| Hb 13.9→7.5, truncated interval, `low` flag printed | `remained_normal` | **`newly_abnormal`** via printed flag |
| Creatinine 0.9→6.5, low bound only, no flag | `remained_normal` | **`NOT_DETERMINABLE`** + reason code |
| Cholesterol `< 200` (**genuinely** one-sided) | `newly_abnormal` | **unchanged** — still settles |
| Hb with both bounds printed | `newly_abnormal` | **unchanged** |

**D3 (HIGH) — a risk level survived a status degradation: the card printed "Not Assessed"
beside "Low".** `RISK_VALUES.includes(overall.risk)` is false for an explicit `null`, so the
code fell through to the top-level `report.overall_risk` and substituted `Low` — directly
under a comment reading *"No decisions must never become Low."* Worst case: the producer
wrote `risk: null`, an explicit "there is no risk to state", and it was overridden. Not
dashboard-local — it also reached the persisted copy, `/analysis` and the listing.
**The tests written in §6o had already caught this** and pinned it as
`DEFECT: documents current behaviour`, with an instruction to invert the assertions once
fixed. That is exactly what happened, and the inversion is what made the fix visible rather
than silent — the right shape for "found a defect I am not allowed to fix".

**D4 (MEDIUM) — `considered = included + excludedCount` broke the moment the cap engaged.**
55 eligible + 3 unanalysed returned `considered: 58, included: 50, excludedCount: 3`,
leaving **five reports in neither bucket**, with `truncated: true` the only hint. Fixed with
a third term, `droppedByCap`, derived by subtraction so it cannot disagree with the other
three, plus `excludedListed` so a capped `excluded[]` cannot read as complete. The existing
test called itself "THE ACCOUNTING IDENTITY" but seeded fewer eligible reports than the cap,
so truncation never engaged — the new test does engage it and was **verified to fail against
the two-term version** (`Expected: 2, Received: 0`).

**D5 (MEDIUM-LOW) — an uppercase report id produced a false statement about the caller's own
analysed report.** `snapshotIds.has(id)` compared the *submitted* string against lowercase
hex, so the same id in uppercase returned 422 telling the patient to analyse a report that
was already analysed. Now compares against the id of the document `resolveNamedPair` just
loaded.

**D6 (LOW) — `assembleHistory`'s JSDoc declared an `excluded[]` it never returned.** A caller
trusting it read `undefined` and would render "nothing was excluded" — absence quietly
becoming a reassuring value, in the block built to prevent exactly that.

### FIXED IN THE SECOND PASS

**D7 (HIGH) — the diabetes model's detection numbers never reached the clinician. This was
D8 for the third model, and the reason recorded for closing D8 was MY OWN FALSE COMMENT.**
`heart.py`, `kidney.py` and §6o all said "Module 10's artifact does not record it". It
does: recall 0.7028 and precision 0.9113 at `decision_threshold` 0.7947, IDENTICAL to the
published `indicated` threshold, plus accuracy 0.9678 against a 0.9118 majority-class
baseline. They were simply recorded under `metrics.positive_class` rather than under
`thresholds`. Believing my own comment is why the D8 fix stopped at two models.

**D8 (MEDIUM-HIGH) — `precision_at_operating_threshold` was structurally dead.** The reader
looked for `indicated_precision_achieved`, a key **no model published**. All three returned
None while the artifacts held 0.7496 (heart) and 0.9840 (kidney).

Both fixed by **one shared reader**, `app/ml/operating_metrics.py`, used by all three
predictors — because per-model reasoning about a cross-model question is what caused both
failures. It prefers the explicit `thresholds.indicated_*_achieved` keys and falls back to
`metrics.positive_class.*` **only when `metrics.decision_threshold` equals the published
`indicated` threshold**; when they diverge the numbers describe a different operating point
and are refused, because a precision measured at 0.5 presented as the precision at 0.795
would be a fabricated performance claim. An absent figure is **omitted, never null**.

| model | before | after |
|---|---|---|
| Diabetes | recall/precision/accuracy/baseline all `None` | 0.7028 / 0.9113 / 0.9678 / 0.9118 |
| Heart | recall only | 0.2678 / 0.7496 / 0.5918 / 0.5003 |
| Kidney | recall only | 0.9840 / 0.9840 / 0.97 / 0.63 |

Heart's accuracy 0.5918 against a 0.5003 baseline is the honest "barely better than a coin
flip" a clinician needs and could not previously see.

Also added `METRICS_OPERATING_POINT_INCOMPLETE`: a record with figures but no operating
point is no longer allowed to report `metrics_available: True` with no absent code, which
is exactly the state Module 10 was in with nothing signalling it.

**D9 (LOW) — a skipped model no longer explains a figure it never showed.**
`model_probability_meaning` was seeded unconditionally, so a model that produced no estimate
still carried "The figure shown is the model's own estimated likelihood...".

**D10 (MEDIUM-HIGH) — Module 31's copy overstated how many people are below the patient.**
The band is built with `bisect_right` over cut-points defined as `min{x : P(X <= x) >= p}`,
so it is a statement about the share AT OR BELOW — but the sentence said "the share who had
a **lower** {label} than yours". Lab values cluster hard at one decimal, so for men aged
20-29: HbA1c 5.2 (the modal value) reported 50th-75th when only **40.9%** are strictly
lower; 4.6 reported 5th-10th when **2.4%** are. The banding arithmetic was correct
throughout; the sentence had been written for a point percentile and never revised. Now
reads "the share whose {label} was at or below yours. People whose result equals yours are
counted in that share."

**Two tests that asserted the implementation against itself were corrected, not deleted.**
One required the literal word "lower"; the other extracted the label by splitting the
sentence on `"lower "` and compared the result against that same sentence — circular, and it
broke with an `IndexError` rather than a useful failure. The label now comes from the
service's own label source, and the copy test asserts the semantics ("at or below" present,
"lower than yours" absent).

Suites after this pass: `ai-service` **3,653 passing** / 0 failures (+4) · `backend` **618
passing** / 0 failures. Regression tests were verified to fail against the unfixed code:
the operating-point test fails on `Diabetes`, and the accounting test on `Expected: 2,
Received: 0`.

### FIXED IN THE THIRD PASS

**D11 (HIGH) — a doctor summary could carry trends for a history that did not contain the
report it describes.** Two live routes: a subject excluded by the backend's own inclusion
rule, and a subject dropped by the history cap (with `excludedCount: 0`, so nothing named it
missing). **The backstop went in the ai-service**, at the layer that renders the claim, where
no caller's accounting bug can route around it: `_subject_missing_from_history` refuses both
sections with `SUBJECT_NOT_IN_HISTORY` when `report_ref` is not among the snapshots. The
backend additionally reports `history.subjectInHistory`, and the controller comment claiming
the inclusion rule guaranteed membership — it did not — was replaced with what the code
actually does. Verified: subject present → both sections render; subject absent → both refuse
with the code, **and the clinical findings are untouched** (a missing section never costs the
document its content).

**D12 (MEDIUM) — Module 30 discarded the warnings that qualify its own score.** Only
request-level warnings propagated, so `crossed_without_significant_change` was dropped and a
**0.02 mg/dL** creatinine move (below the declared stability band, across a printed bound)
swung the score 50.0 → 37.5 and changed the headline band with no caveat anywhere. Per-
parameter warnings now travel with the score, de-duplicated, in parameter order. The design
call that a crossing outranks the change axis is Module 29's and was deliberately kept; it
was the silence that was wrong.

**D13 (MEDIUM) — BMI's adult-only guard fired only when an age was present.** With no `age`
feature the WHO adult 18.5-24.9 interval was applied silently, so `bmi 15.0 → 17.5` in a
child read `improving`, while the same series WITH `age=8` was correctly refused. Age-unknown
became age-adult. Now refused with `NOT_COMPARABLE_AGE_CONTEXT` either way — consistent with
how the module already refuses glucose for want of a recorded sample timing.
**A test was asserting the defect**: `mixed_pair()` records no age, so BMI was being scored,
and the test pinned 7 contributors and 450/7 = 64.3. Corrected to 6 contributors and
400/6 = 66.7, with BMI's exclusion asserted explicitly and the reasoning recorded in place.

**D14 (MEDIUM) — a fractional age was refused with a false reason.** `age` is typed
`Optional[float]`, and bands were compared against the raw value, so they were contiguous
over the integers but not over the reals: `29.5` and `79.9` fell through the cracks and were
told they "fall outside every group the survey published". Ages are now compared as
**completed years**, which is how NHANES records them (`RIDAGEYR`) and how the cells were
cut, so no new assumption is introduced. `19.99` still floors to 19 and is still refused as
below the adult table. `DroppedCohort.covers` was given the same treatment so the two cannot
disagree and produce the wrong reason code.

**D15 (LOW) — negative day counts** in prose on an explicitly named reverse-chronological
pair ("(-152 days apart)"). The signed value stays on the data object, where it correctly
records the direction the caller asked for; only the rendering takes the absolute value,
because a separation is a magnitude.

**D16 (LOW) — the policy endpoint published "eight canonical features are numerically
trendable"; it is nine.** Now **derived** from the tables rather than typed, so it cannot go
stale the next time the polarity table gains a row — the adjacent `feature_coverage_note`
was computed and correct the whole time, which was the argument for computing this one too.

**The Module 24 safety scanner caught one of my own fixes.** A new template worded "an
unknown age is not *treated* as an adult one" matched a `treatment_instruction` pattern and
failed the import. Reworded to "not assumed to be". The scanner is doing exactly what it
exists to do, on a string a human would have waved through.

**A reachability test caught another.** `test_every_declared_section_reason_code_is_reachable`
failed the moment `SUBJECT_NOT_IN_HISTORY` was added to the vocabulary without a scenario
producing it. That is a test earning its keep; a scenario was added rather than the
assertion loosened.

Suites after this pass: `ai-service` **3,660 passing** / 0 failures · `backend` **618
passing** / 0 failures.

### FIXED IN THE FOURTH PASS — ALL 17 AUDIT DEFECTS ARE NOW CLOSED

**D17 (LOW-MEDIUM) — physiologically impossible values received a band.** `hba1c = -3` came
back `available: true`, "below the 1st percentile"; `hemoglobin = 1e9` came back "at or above
the 99th". Both statements are true of the published grid and neither makes a clinical claim,
which is what made them dangerous: they laundered an extraction error into something that
reads like a measurement.

**D18 (LOW) — the `snapshot` input path bypassed Module 6**, so `hba1c -1.0 → -2.0`
classified as `improving` while `trend_analyzer.py`'s own docstring asserted a rejected value
"cannot even reach here" (true of the `validated` path, false of this one).

**Both fixed by borrowing Module 6's OWN bounds** — `validation_rules.rule_for`, the same
table Module 6 rejects on — rather than writing a second definition of "physiologically
possible" that could drift from it (§11). Module 31 refuses with
`VALUE_NOT_PHYSIOLOGICALLY_PLAUSIBLE`; Module 28 emits `IMPLAUSIBLE_VALUE` gaps instead of
trend points. The docstring that claimed the guarantee is now true rather than aspirational.

**The bound is compared in the CANONICAL unit, and that detail is load-bearing.** Module 6
states its band in ng/mL for vitamin D while the NHANES table is nmol/L (~2.5x). Checking an
already-table-converted number against canonical bounds would reject real readings near the
top and accept impossible ones, so the conversion direction is asserted by its own test.

**Six existing tests broke, and every one was using an impossible value as a convenient
probe.** They were repaired rather than the guard weakened:
- A zero-first-value probe used `cholesterol = 0` (Module 6's floor is 20). Switched to
  vitamin D, whose possible band genuinely starts at 0.0, so the division-by-zero path is now
  exercised by a value that could actually arrive.
- An exhaustive undeclared-polarity test hard-coded `[10.0, 1000.0]` for every feature —
  1000 g/dL of haemoglobin. The probes are now derived from each feature's own possible band,
  so the test stays exhaustive over the table AND every probe is a real measurement.
- Three population band-edge tests probed `values[0] - 5` and `values[-1] + 1`, i.e. negative
  creatinine. Shared `_just_below` / `_just_above` helpers now step outside the published
  grid while staying inside the possible band — preserving exactly what those tests were
  written to check.

One of my own new tests was wrong and was corrected rather than the code: it asserted a
haemoglobin trend would be `TREND_CLASSIFIED`, but haemoglobin's polarity is deliberately
UNDECLARED, so `CLINICAL_DIRECTION_UNKNOWN` is the honest answer. The test now asserts what it
actually cares about — that both readings were USED — because plausibility and direction are
different questions and conflating them is what the test would otherwise have hidden.

**FINAL STATE: `ai-service` 3,667 passing / 0 failures · `backend` 618 passing / 0 failures.
All 17 defects from the independent audit of Modules 27–32 are fixed.**

### Formerly open, now closed

~~1. **(LOW-MEDIUM) Physiologically impossible values receive a band.**~~ `hba1c = -3` →
   "below the 1st percentile"; `hemoglobin = 1e9` → "at or above the 99th". The service
   checks only `is_finite_number`, and this endpoint takes raw `measurements` rather than a
   validated snapshot, so Module 6's plausibility bounds are never consulted. The statements
   are technically true and carry no clinical claim — this is laundering nonsense rather than
   emitting a wrong number — but a percentile attached to a negative haemoglobin is not
   something this platform should print. Reuse Module 6's bounds; do not write a second
   table.
2. **(LOW) The `snapshot` input path bypasses Module 6.** `TimelineReportInput.snapshot`
   accepts a `FeatureSnapshot` posted directly with no plausibility check, so
   `hba1c -1.0 → -2.0` classifies as `improving` — while `trend_analyzer.py`'s own docstring
   asserts a rejected value "cannot even reach here". Either close the gap or make the
   comment true; a comment asserting a guarantee the code does not make is itself a defect
   here.

### PREVIOUSLY OPEN, NOW SUPERSEDED

The following were listed in the first pass and are fixed above: the doctor-summary subject
(D11), Module 30's dropped warnings (D12), the BMI age guard (D13), the fractional age
(D14), negative days (D15), the trendable count (D16). ~~1. **(HIGH) A doctor summary can
carry trends for a history that does not contain the report it describes.**~~ Two triggers: a subject excluded by the inclusion rule, and the cap
   dropping it (`SUBJECT IN HISTORY? false`, `excludedCount: 0` — nothing names it missing).
   **The ai-service does not backstop it**: `_trend_section` / `_comparison_section` branch
   only on `len(history) < 2` and never check `report_ref ∈ history`. The controller comment
   claims the opposite.
2. **(MEDIUM) Module 30 discards the warnings that qualify its own score.** Only
   request-level warnings propagate, so `crossed_without_significant_change` is dropped and a
   **0.02 mg/dL** creatinine move swings the score 50.0 → 37.5 and changes the headline band
   with no caveat.
6. **(MEDIUM) BMI's adult-only guard fires only when an age is present.** No age ⇒ the WHO
   adult interval is applied silently; `bmi 15.0 → 17.5` in a child reads `improving`.
7. **(MEDIUM) A fractional age is refused with a false reason.** `age=29.5` →
   `AGE_OUTSIDE_TABLE_RANGE` "falls outside every group the survey published", though a
   29.5-year-old is plainly in the published 20–29 cell. **§6m's claim that this code is
   "implemented but unreachable" is falsified.**
8. **(LOW-MEDIUM) Physiologically impossible values receive a band** — `hba1c = -3` →
   "below the 1st percentile". Module 6's plausibility bounds are never consulted.
6. **(LOW) Module 30's policy endpoint publishes "eight canonical features are numerically
    trendable"; it is nine.** §6m repeats the same wrong number.
11. **(LOW) Negative day count** in prose on an explicitly named reverse-chronological pair.
12. **(LOW) The `snapshot` input path bypasses Module 6**, so `hba1c -1.0 → -2.0` classifies
    as `improving`, while the module docstring asserts a rejected value "cannot even reach
    here".

### Corrections to this file

- §6m's "`AGE_OUTSIDE_TABLE_RANGE` is implemented but unreachable" — **false**, see item 7.
- §6m's "CONTRACT MISMATCH FOUND, NOT PATCHED" (400 → 502) — **stale, it is fixed**; 400 now
  joins the 422 branch.
- §6m's claim about duplicated `?baseline=` — wrong; `hpp()` collapses it to the last value
  before the chain sees it.
- §6o's "Module 10's artifact does not record it" — **false**, see item 2.
- §6m's "eight trendable features" — it is nine.

**Six false comments have now been found on this project, three of them written by an
assistant.** §11's "a comment asserting a guarantee is not a guarantee" is the single
most repeatedly-vindicated line in this file.

---

## 6q. The React frontend · 2026-09-05 · spec §15, built in four slices

`frontend/` — Vite + React + react-router, plain CSS, no state library. **44 tests.** Built
in four commits so each slice was independently verifiable, after two sessions of agents
being killed mid-edit by rate limits made large single generations a bad bet.

Every module now has a user-facing surface: auth and profile (1, 2), reports with upload and
analyse (3), the dashboard (27), the timeline (28/29/30), the clinician summary (32) and
population context (31).

### The one thing to read first: `src/lib/absence.js`

Every layer beneath the UI was made careful about absence at real cost — `INSUFFICIENT_DATA`
carries no risk, a gap structurally has no `value` field, fewer than two readings is never
`stable`, a model that declined to predict says so. **All of it can be undone by one line of
JSX.** `{risk ?? 'Low'}` renders a missing risk as reassurance; `{value || 0}` renders a
rejected reading as zero. And a dashboard has to show *something* in every box, which is
exactly the pressure that turns an absence into a value.

So `absence.js` and `components/Absent.jsx` are the only sanctioned way to render a
possibly-absent clinical value, and **not one of them accepts a fallback VALUE — only a
fallback EXPLANATION.** `Risk` has no way to express "missing means Low". `Section` cannot
render an absent section without a reason. There is deliberately no `defaultValue` prop
anywhere, because the whole class of bug is someone reaching for one under deadline.

The rule they encode: **branch on the API's explicit flag** — `available`, `present`,
`any_assessed`, `generated_explanation_available` — **never on the truthiness of the value.**
A real `0`, a real `false` and a real empty string are all falsy and all meaningful.

### Architecture decisions

- **The browser never contacts `ai-service`.** Every call goes through the Node backend,
  where authentication, owner scoping and 404-before-403 live.
- **The dev server proxies `/api` rather than relaxing CORS.** Both services default
  `CORS_ALLOW_ORIGINS` to empty deliberately; proxying keeps that default untouched and keeps
  the browser same-origin, so no relaxation is needed locally and none is tempting to add.
- **Tokens:** access token in memory, refresh token in `localStorage`. A stated trade-off,
  not an oversight — in-memory-only logs a patient out on every reload, which pushes people
  toward staying signed in on shared devices. The mitigation that matters is the backend's
  rotation-on-every-use. **The correct end state is an httpOnly cookie, which needs a backend
  change. Recorded as a known limitation.**
- One shared refresh promise: concurrent 401s share a single rotation, or a dashboard firing
  five requests on load would burn five refresh tokens against a rotating store.
- `checking` is a real auth state, rendered as one. Guessing signed-out bounces a signed-in
  patient on every reload; guessing signed-in flashes a dashboard about to 401.

### Two defects found by checking the contract against a RUNNING backend

A live check (real mongod + backend, 24 assertions) found what the build could not:

1. **The sign-up hint stated only a length rule.** The real policy also demands upper, lower,
   digit and symbol — a patient would have hit a 422 they were never warned about. Found
   because the check's own test password was rejected.
2. **The profile form sent `null` for an unanswered tri-state**, which the validator rejects
   outright. So choosing "Not sure" — the honest answer, and the one the tri-state design
   exists to protect — produced an unactionable 422. **Absence is sent by OMITTING the key**,
   and the form now saves with `PUT`, whose replace semantics are what let a patient move an
   answer back to unknown. A comment asserting the opposite was corrected.

### Tests, and the mutations that prove they can fail

Per project convention every important assertion was verified to FAIL against a plausible
wrong implementation, then restored:

| reverted to | tests that caught it |
|---|---|
| printing `status` instead of `statusLabel` | 1 (the `Healthy (partial assessment)` flattening) |
| defaulting a missing trend to `"stable"` | 2 (incl. `CLINICAL_DIRECTION_UNKNOWN`) |
| dropping the model-limits block | 2 (a bare probability, and the incomplete-record code) |

What the suite holds: a real `0` and a real `false` still print; a rejected reading never
renders as `0` nor as the rejected number; a missing risk never renders as `Low`, and a risk
arriving beside `anyAssessed: false` is refused anyway; `INSUFFICIENT_DATA` never renders as
`stable`; an unavailable population entry carries no percentile at all; every model
probability is rendered with its detection rate and precision; `metrics_absent_code` is
surfaced so a partial record cannot read as complete; a withheld section always states its
reason.

**One test bug caught in myself:** an assertion on `/50/` matched both the included count and
the cap — it would have passed for the wrong reason. Re-asserted on the sentence.

### Not done

- **No browser has driven a full upload → analyse → dashboard flow.** The contract is
  verified against a running backend and every component is unit-tested, but the two have not
  met in a real browser against a real analysis.
- **No accessibility review.** This is a medical tool; that gap is worth closing.
- No loading skeletons, no pagination on the report list, no report deletion in the UI.

---

## 6r. Audit of Modules 21–26 · 2026-09-05 · **TWO VERDICTS OF FAIL. NOTHING FIXED YET.**

> **READ THIS BEFORE TOUCHING MODULES 21–26.** Three independent auditors were sent at the
> last unaudited region — the path where a language model's words reach a patient. Two
> returned **FAIL** with demonstrated, reproducible defects. **None of them has been fixed.**
> The third (Modules 25/26) was killed by a rate limit before finishing and must be re-run.
>
> Both suites are still fully green. That is the point: **408 knowledge tests and 327
> safety tests pass with these holes wide open.**

### Auditor 1 — Modules 21/22 (RAG + Knowledge Base) — **VERDICT: FAIL**

**D1 · CRITICAL · DEMONSTRATED — the §6k D7 fix is bypassed on the public HTTP endpoint.**
`_anchor_free_text` is called from `retrieve()` only (`app/rag/retriever.py:161-166`).
`retrieve_payload()` (`app/rag/retriever.py:178-197`) calls `build_query(...)` directly and
**never anchors**, and `app/api/routes_knowledge.py:104` calls `retrieve_payload`. Every D7
example reproduces verbatim through the API today, HTTP 200, `grounding_available: true`:

| query | chunk returned | score |
|---|---|---|
| `what does a raised HbA1c mean` | `cond_elevated_hemoglobin#0` | 0.152 |
| `my ALT and AST liver enzymes are high` | `term_ldl_hdl#1` | 0.190 |
| `white blood cell count WBC` | `cond_anemia#2` | 0.402 |
| `my blood pressure is 160 over 100` | `ref_glucose_bands#0` | 0.300 |
| `is my cancer chemotherapy working` | `cond_obesity#1` | 0.176 |

**Module 23 is NOT exposed to this** — `explanation.py:290` calls `retrieve()` with canonical
names. But the endpoint is public and its own `/index` policy payload advertises
`"empty_rather_than_irrelevant"`, which is a **false claim about behaviour**, and
`routes_knowledge.py:4-7` claims the HTTP layer "can never drift from the in-process one".
It has drifted. Also: `floor` is caller-controllable to `0.0` (`app/rag/schemas.py:64-73`),
so the last guard is client-defeatable.

**The overlapping-similarity claim in §6j is verified and is WORSE than recorded.** Measured
unanchored top-1 scores: covered queries 0.152–0.444, uncovered 0.168–0.402. They do not
merely overlap, they **invert** — the uncovered WBC query outscores 9 of 10 covered ones. No
similarity floor can separate them.

**D2 · CRITICAL — three tests pass while the endpoint is wrong.**
`tests/test_knowledge_endpoint.py:158` posts `"what does HbA1c measure"` and asserts only
`assert data["results"]` — it asserts that *something* came back, not the right thing. The
only off-domain tests use `"how do I fix my bicycle"` / `"asdfghjkl"`, stopped by the domain
floor rather than by anchoring. **No test anywhere exercises a medical-but-uncovered query
through `retrieve_payload`.**

**D3 · HIGH — both corpus scanners share a dosage blind spot.**
`app/data/knowledge_safety.py:100-104`, `dose_quantity` ends `\b(?!\s*/)` to allow "126
mg/dL"; it excuses **any** slash. `500 mg/day`, `1000 IU/day`, `2.5 mg/tablet` are accepted
by the KB scanner AND approved by Module 24. Latent, not live (no such string is in the 62
documents), but the import gate that should prevent it does not. Also accepted by both:
`This result establishes that the person has diabetes.`, `pathognomonic of…`.

**D4 · MEDIUM — scanner divergence the other way.** `knowledge_safety` accepts second-person
imperatives Module 24 hard-rejects (`You should reduce salt…`, `Eat more leafy greens…`). A
future lifestyle document in that register imports fine and then silently withholds the
patient's whole explanation.

**D5 · MEDIUM** — 19 of 243 chunks are byte-identical boilerplate; the diversity cap is per
document, so one query returns five identical chunks and consumes the whole grounding budget.
**D6 · LOW/MED** — `term_reference_interval`, `interp_missing_value`,
`interp_what_this_platform_is` carry no tags, so anchoring makes them unreachable by the very
questions they exist to answer (`retrieve(text="what is a reference interval")` → `[]`).

**Verified clean (worth as much):** `build_index.py --check` passes, committed index matches a
fresh build, fingerprint check prevents a stale index shipping. All §6j corpus claims exact —
62 docs / 377 paragraphs / 243 chunks, vocabulary aligned both directions at import, every
document carries a real, checkable `basis` (ADA, WHO VMNIS, NCEP ATP III, KDIGO, Endocrine
Society, BCSH); spot-checked numbers against the cited guidelines with **no factual errors**.
**Chunking could not be broken** — no chunk separates a negation or caveat from what it
qualifies. Determinism holds across `PYTHONHASHSEED`. No PHI in logs. All 243 chunks pass
Module 24 with zero real violations.

### Auditor 2 — Modules 23/24 (LLM explanation + safety validator) — **VERDICT: FAIL**

**14 defects. Of §6k's eight fixes: three DO NOT HOLD, four are PARTIAL, one holds.**

| | §6k fix | status |
|---|---|---|
| D1 | positive controls backstop the blocklist | **DOES NOT HOLD** |
| D2 | `_GAP` for separators | PARTIAL |
| D3 | `_drop_disclaimed_diagnoses` | PARTIAL |
| D4 | invisible characters | **DOES NOT HOLD** |
| D5 | false comments corrected | **DOES NOT HOLD** |
| D6 | Module 25 echo | **HOLDS** |
| D7 | `_anchor_free_text` | holds *for Module 23* (see Auditor 1) |
| D8 | spelled-out numbers | PARTIAL |

The most severe, all DEMONSTRATED by driving `validate_text` / `explain_feature` directly:

1. **A diagnosis stated as flat fact reaches the patient.** `assertion.clinical_state`
   (`app/safety/policy.py:461-525`) is an enumeration, not a positive control.
   `'You have cirrhosis of the liver. Discuss with a healthcare professional.'` → **approve,
   zero violations.** Same for chronic liver failure, leukaemia, underactive thyroid, kidney
   failure, "your heart is weak and enlarged". False reassurance too: `'Your results are all
   fine.'`, `'You do not have any diabetes.'` → approved. **`RULES` contains 13 rules and not
   one has `positive_control=True`.** D1's own stated diagnosis is still true: the fix
   replaced one enumeration with another.
2. **One ordinary adverb defeats every multi-word rule.** `_GAP = r"\W{1,4}"`
   (`policy.py:197`) matches only non-word runs. `'Your kidneys are failing.'` → reject;
   `'Your kidneys are, sadly, failing.'` → **approve.**
3. **`MISSING_PROFESSIONAL_REFERRAL` is still satisfied by a bare substring.**
   `validator.py:838-861`. Combining 1 and 3 reproduces the original FAIL audit's headline:
   `'A qualified healthcare professional wrote these reference ranges. Your liver is scarred
   and hardened.'` → approve, no violations, verbatim to the patient.
4. **`_compacted_pass` discards REDACTABLE findings** (`validator.py:487-537`), so one
   zero-width space smuggles `'There is no ne​ed to see a doctor about this result'`
   through to **approve**. **15/15 invisible characters MISS in the redactable class.**
5. **`_ZERO_WIDTH` covers 7 code points**; LRM, RLM, LRI, PDI, LRO, RLO, U+2061 and VS1
   escape even PROHIBITED inside a word — and a **passing test masks it** by only testing the
   between-words direction where `_GAP` catches them for free.
6. **Numeric grounding is set-membership**, so any number in the corpus can be attributed to
   the patient: with the real value 6.8, `'Your HbA1c is 5.7 percent, which is in the normal
   band.'` → approve. A fabricated *and falsely reassuring* value sourced from the model's own
   grounding.
7. **D8 misses the register it was written for**: `'Your level is around fifteen.'`,
   `'Your reading is twelve.'`, `'one in four'`, `'one third'` → all approve. **And it has a
   new false positive**: `_spelled_number('five and seven') == 12.0`, so every spelled range —
   the exact register Module 23 asks for — is read as a fabricated number and rejected.
8. **D3 is regressed on the redaction recheck** (`validator.py:1139-1143`): adding a *correct*
   disclaimer flips approve→reject, and `_feedback_block` then teaches the model to drop it.
9. **Fail-closed runs before normalisation** (`validator.py:971`): `validate_text('​​')`
   → approve, `outcome='generated'`, empty explanation plus disclaimer. A blank rendered as an
   answer.
10. **Nothing checks the output is an explanation.** `'I cannot help with that.'`, `'.'`,
    `'x'` → all approved as `outcome='generated'`. Module 24 is purely subtractive.
11. **Prompt injection via `unit` and `status`** (`explanation.py:341,361`) — `_clean_label`
    is applied only to `interpretation`. Raw newlines land a forged `## NEW RULES` heading
    *before* the absolute-rules block. `unit` is OCR-derived report text, and via
    `/explain/report` the budget is **unbounded**, which falsifies `EXPLANATION_POLICY`'s
    claim that the model never sees raw report text.
12. **The three scanners disagree in both directions** — 12 measured rows. `Acyclovir is an
    antiviral.` is caught by both corpus scanners and **approved by Module 24**
    (`policy.py:576` has `navirs?|ciclovirs?` where siblings have the wider `virs?`). The KB
    scanner misses "no need to contact a doctor", "replaces a consultation", "rest assured",
    "without seeing a clinician" — all rejected by Module 24, so **the corpus gate is
    materially weaker than the output gate it is meant to mirror.**
13. **A false comment asserting the guarantee §6k D5 says was corrected** —
    `app/data/recommendation_catalog.py:461`, *"Fixed in all three so the sibling scanners
    cannot drift apart again."* Corrected in `validator.py` only. **Seventh false comment on
    this project, and the second time this exact sentence has been found.**
14. `guarded_generation` catches `Exception`, not `BaseException` (`app/safety/fallback.py`).
    Fails safe; the docstring is inaccurate.

**Verified clean:** the single-assignment invariant genuinely holds (raw model output is
never stored); all five outcomes reachable with fallbacks; fail-closed on type/encoding/size/
control characters; **no PHI, prompt, span or value in any log line, exception or
patient-facing field**; Module 24 still produces zero false positives on its own corpus.

### Auditor 3 — Modules 25/26 — **NOT COMPLETED**

Killed by a session rate limit after "Now let me instrument and probe rather than read."
**Re-run it.** The brief is in this file's history: independently recompute Module 26's
reachable `EDUCATIONAL_CODES` set (a HIGH-risk-tier sentence was once servable as general
guidance), and confirm "zero model and retriever calls" **by instrumentation, not reading**.
Also cross-check spec-named terms against the vocabulary for gaps not declared in
`known_gaps` — SGPT is declared; an undeclared one would be worse.

### The pattern, now four audits deep

Every audit on this project has found live defects behind a fully green suite. §6p's auditor
named the shape and it holds here exactly:

> **"The branch that refuses is tested, the branch that answers on thin evidence is not."**

And a second pattern is now undeniable: **§6k's fixes were verified once, by the person who
wrote them, and three of eight did not survive re-attack.** A fix is not done when its
author says so.

---

## 6s. Module 11 retrained on NHANES · 2026-09-06 · **0.697 → 0.837, SHIPPED**

`heart_rf_v2` is loaded by `app/ml/heart.py`. v1 is kept on disk, unloaded.

| | v1 (`cardio_train`) | v2 (NHANES 2017–2023) |
|---|---|---|
| Held-out ROC-AUC `with_smoking` | 0.6970 | **0.8374** |
| Held-out ROC-AUC `without_smoking` | 0.6949 | **0.8293** |
| PR-AUC | — | 0.348 (baseline 0.093) |
| Prevalence | 50% (constructed) | **9.3% (a real screening rate)** |
| Outcome | undocumented | physician-diagnosed CHD / MI / angina / CHF |
| Inputs | age, bmi, cholesterol_band, smoking, gender | age, bmi, **cholesterol (mg/dL)**, smoking, gender |
| Rows | 69,940 | 13,152 adults |

Trainer: `ml/train_heart_nhanes.py`. Dataset: `datasets/raw/nhanes_cvd_2017_2023.csv`
(Kaggle `ahiduzzaman28/nhanes-cvd-raw-data-2017-23`), with sex and smoking joined on `SEQN`
from CDC's own `P_DEMO`/`DEMO_L` and `P_SMQ`/`SMQ_L` in `datasets/population/raw/`.

**The prevalence change may matter more than the AUC.** A model fitted at 50% positive emits
probabilities calibrated to a world where every second person has heart disease. v2's
probabilities are calibrated to a population that looks like a real one.

**Why the join was necessary.** The Kaggle extract has no sex and no smoking column. A first
attempt shipped three inputs where v1 used five — better ranking bought by discarding two
answers Module 2 already collects, which is a trade, not an improvement. Joining them back
costs nothing and gains a little: age+bmi+chol 0.8110 → +sex 0.8159 → +smoking 0.8207 (CV).
Sex matched 100% of rows; smoking resolves for 65%, and an unresolved answer still selects
the `without_smoking` variant rather than having a value imputed.

### THE ~0.10 BLOOD-PRESSURE FIGURE IS WRONG. Stop quoting it.

This project has treated "add systolic BP to Module 2" as Module 11's highest-value change,
on the strength of a measured 0.10 ROC-AUC gap. NHANES publishes blood pressure, so v2
fitted the reference model and scored it **on the same test rows** instead of inheriting the
number:

> **BP-inclusive 0.8416 vs shipped 0.8350 → cost of exclusion +0.0066.**

0.10 is a property of `cardio_train`, where BP carried most of the signal and the remaining
features carried little. It does not transfer. BP is still worth having; it is a small gain.

### Two things deliberately NOT used

* **`Vitamin_D` / `Vitamin_B12` in that dataset are DIETARY INTAKE** (medians 3.3 and 3.2
  mcg/day), not the serum levels VaidyaAI's identically-named features hold (~20–50 ng/mL,
  ~200–900 pg/mL). Same word, different quantity. Wiring them together would have produced
  a stronger-looking model built on a unit confusion — the class of bug §6n D1 already cost
  this project once.
* **A 12k-row NHANES CKD set was rejected**, not used. All 5,607 rows staged `Unknown` are
  labelled `ckd_present = 1` — 67% of its positives are unknowns counted as disease. See
  §10's eGFR note for why its clean alternative target is circular.

### Two safety regressions introduced while doing this, both caught by the suite

1. Generated band prose said *"% of patients in this band had a diagnosis"*. That string is
   rendered into the **patient-facing report** and the Module 24 scanner correctly flags it
   as a diagnostic assertion. v1's *"were positive"* was already right.
2. The artifact's `honest_read` said *"SELF-REPORTED physician diagnosis"*, which trips the
   same scanner. The consequence is worse than a flag: `doctor_summary` **withholds the whole
   note**, so a clinician silently loses the model's own statement of its limits. Reworded,
   fact intact.

**Both were introduced by the change and caught by existing tests.** That is the first time
on this project the suite has caught a live safety defect rather than missing one.

### A design fix that outlives the artifact

`app/ml/heart.py` hard-coded facts belonging to whichever artifact is loaded — the band prose
(*"21.1% positive against a cohort prevalence of 50.0%"*), the threshold procedure, and the
NCEP band mapping. Those are cardio_train's numbers, and pointing the file at any other
artifact left them rendering **unchanged and now false beside a patient's result**. They are
read from the artifact now (`threshold_basis`, `band_meaning`), with v1's text as fallback,
and the cholesterol-band block is emitted only when the model actually consumes a band.

`model_artifact` must be `{filename, sha256, bytes}`, not a bare filename — writing a string
leaves every prediction stamped `artifact_integrity_verified: false`, silently downgrading a
shipped integrity check to nothing. That was also introduced and fixed here.

### 20 tests rewritten, none deleted

Each had frozen a cardio_train fact as an invariant: `rows_raw == 70000`, age in days,
cholesterol as a 1/2/3 band, gender *inferred* rather than documented, a 1.5× precision-lift
procedure, `roc_auc < 0.8`, HIGH_RISK reaching INDICATED. The clearest case is
`test_the_heart_model_carries_its_weak_discrimination_caveat`, whose own docstring said the
caveat *"must be SELECTED BY THE NUMBER rather than remembered for this one model"* — and
which then pinned `0.697`. The selection mechanism kept working perfectly and the test failed
anyway. They now assert both branches, or read the expected value from the loaded artifact.

**Lesson, and it is the same one as §6n D1 and the band prose above:** a number that belongs
to a dataset must live in the artifact, never in code and never in an assertion.

`ai-service` 3,676 passed / 7 skipped · `frontend` 44 passed · commits `1cd15c9`, `fcd32fd`.

---

## 6t. First real run · 2026-09-06 · three defects a green suite never saw

The application was started and driven through a browser for the first time. Everything below
was invisible to 4,300 passing tests.

### D1 — CRITICAL: report upload was broken for EVERY file

The client sent the multipart part as `report`; the backend accepts only `file`
(`upload.single(FIELD_NAME)`, `FIELD_NAME = 'file'`). Multer rejected every upload as
`LIMIT_UNEXPECTED_FILE`, surfacing as *"Unexpected file upload. Send exactly one file in the
`file` field"* — wording that blames the user for sending several files when they sent one.
**No report could ever be uploaded through the UI.** Fixed in `frontend/src/pages/Reports.jsx`;
`file` is the contract every backend upload test attaches. **No frontend test covered upload at
all** — zero hits for `FormData` in `frontend/tests/`.

### D2 — every intake refusal read the same

`mapAxiosError` collapsed all 400/422 responses into *"The analysis service could not process
this report"*, discarding an explanation the ai-service had already produced. A 13-page report
over a 10-page limit — fixable by the patient in seconds — was indistinguishable from a corrupt
file. The backend now reads the service's stable error **code** and picks one of its own
messages for the actionable cases (`TOO_MANY_PAGES`, `FILE_TOO_LARGE`, `ENCRYPTED_PDF`, …).
The response **body** is still never echoed, so the guarantee that nothing quoting report
content reaches a patient holds.

### D3 — the dashboard went blank exactly when it had something to say

`dashboard.warnings` is an array of `{stage, module, message}` objects; four screens rendered
each one directly as a React child. React throws `Objects are not valid as a React child` and,
with no error boundary, **unmounts the whole page**. The block is guarded by
`warnings?.length`, so it only ever fired when the analysis had warnings — which is precisely
when it is telling a patient their report was read incompletely. Fixed with one shared
`WarningList` in `frontend/src/components/Absent.jsx`, used by Dashboard, DoctorSummary and
both Timeline sites. The 44 frontend tests only exercised the empty-warnings path.

### Also learned while running it

* **Gemini free tier is 20 requests/day PER MODEL** (`GenerateRequestsPerDayPerProjectPerModel`).
  One 13-page report exhausts it — extraction is one call per page, plus one per feature in the
  explanation stage. The quota is **per model**, so `gemini-3.5-flash` and the lite variants
  each carry their own untouched allowance. The client now **falls back across models on 429**
  (`GEMINI_FALLBACK_MODELS`), and only on 429: a deterministic 4xx fails identically everywhere,
  and a provider safety block is an ANSWER that must never be shopped around until one model
  complies. Concurrency does NOT help here — the ceiling is request count, not wall-clock.
* **`GEMINI_TIMEOUT_SECONDS=45` (the README's recommendation) drops pages.** Real per-page
  latency runs to 38.6s, so 45s sits inside the normal distribution; three pages of a 13-page
  report were skipped with `MODEL_TIMEOUT`. The shipped default of 120 is right.
* **`ai-service/.env.example` cannot be used as shipped.** `CORS_ALLOW_ORIGINS=` (empty) makes
  pydantic-settings JSON-decode fail before the `_split_origins` validator runs, so the service
  refuses to start. Same trap as any `List[str]` settings field — `train_heart_nhanes.py`
  avoids it by using a plain string. Not yet fixed in the example file.
* **Mongo Atlas needs the non-SRV connection string on this machine.** Node's resolver is
  configured with DNS server `127.0.0.1` where nothing listens, so `dns.resolveSrv` fails with
  `ECONNREFUSED` and any `mongodb+srv://` URI dies at startup. Ordinary A-record lookups go
  through the OS resolver and work. The standard multi-host form is in `backend/.env`.

---

## 6u. Making Module 27 readable by a patient · 2026-09-06/07

Everything in this section is FRONTEND + the two backend fields it needed. The
pipeline's clinical behaviour is unchanged. All three suites green:
**ai-service 3,690 · backend 618 · frontend 44.**

### THE ONE THING TO UNDERSTAND FIRST

The dashboard was rendering the pipeline's INTERNAL VOCABULARY at a patient.
"Based on: Clinical Rule Engine, Random Forest". "Model probability: 0.0089
(max_of_model_probabilities)". "Not Indicated". "fusion: Heart Disease: the
analyses contributing to this topic answer different questions...". Every one
of those is true, and none of them is readable by the person whose blood it is.

The split now enforced: **the patient screen speaks English, the clinician
summary (Module 32) speaks statistics.** Nothing was deleted — ROC-AUC,
precision, operating thresholds and the full warning list are all still on the
clinician view, where the reader knows what they mean.

### What the dashboard shows now, in page order

| Section | What it is |
|---|---|
| Overall | unchanged |
| Worth a closer look | full cards, FLAGGED conditions only |
| Everything else that was checked | two one-line round-ups, `clear` and `unchecked` kept strictly apart |
| Your results | lab table; columns appear only if the report can fill them |
| From your profile | age/BMI/sex/smoking, no laboratory columns |
| Also on your report, but not assessed here | **NEW** — see below |
| Topics you could read about | guidance, matched to flagged findings only |
| Worth knowing about this analysis | warnings, methodology stages filtered out |
| What these results mean | **NEW** — Module 23's prose, last |

### TWO THINGS THE PIPELINE ALREADY PRODUCED AND THE UI THREW AWAY

1. **Module 23's plain-language explanations were never rendered.** Six
   paragraphs per report, grounded in retrieved documents, safety-validated,
   persisted — and invisible. They cost a model call each. Now shown, last on
   the page, with the trailing "consult a qualified healthcare professional"
   sentence lifted off each paragraph and stated once for the section (six
   identical closings made the platform look like it had nothing to say).

2. **63 of 67 extracted parameters were dropped in silence.** A real report is
   mostly tests this platform does not know. Worse, `document.unmapped_count`
   read **0** while `fusion.upstream_summary.unmapped_count` read **63** — the
   dashboard was reading the wrong one of two fields that disagree, so the
   screen asserted that nothing had been skipped. **The ai-service defect is
   NOT fixed**: `report_builder` still writes 0. The dashboard now derives the
   count from the real list instead.

### THE LABORATORY'S OWN FLAGS WERE BEING DISCARDED. This was the worst find.

Module 4 extracts each parameter's printed reference interval AND the lab's own
high/low marking — including for tests this platform does not assess. Feature
engineering dropped both along with the parameter. On PK0016 that buried **nine
results the laboratory itself marked abnormal**, including **Blood Urea 53,
Blood Urea Nitrogen 24.77 and Potassium 5.2, all high, alongside the raised
creatinine that DID produce a Kidney Disease card.** The platform flagged the
condition and silently dropped the evidence corroborating it, off the same page.

Now carried through (`dashboardController` passes `features` + `extraction`,
`dashboardService.buildUnanalysedSection` joins them) and shown at the top of
the unassessed section, attributed to the LABORATORY, not to this platform.

### Answering "will it work for unknown parameters?" — NO, and that is deliberate

| | Unknown parameter |
|---|---|
| Read off the report | yes |
| Listed on the dashboard | yes |
| Lab's own high/low shown | yes, if printed |
| Condition assessed / risk / ML | **no** |
| Plain-language description | yes — see 6v |

Making one genuinely assessed needs five pieces in the catalog: feature
definition, synonyms, validation bounds, clinical thresholds, and a knowledge
document for grounding. That is per-analyte clinical work. LDL and HDL are the
obvious first candidates — both are already extracted and already dropped.

### Design rules that came out of the session, all learned from a defect

* **A number that belongs to a dataset must live in the artifact, never in
  code and never in an assertion.** (§6s' band prose; the same lesson again.)
  `threshold_basis` and `band_meaning` are read from the artifact now.
* **Collapse only on positive proof.** Grouping conditions by `flagged` alone
  meant a card with `status: 'Indicated'` and no `flagged` field fell into
  "nothing pointed to this" — an indicated finding reported as clear, one
  missing boolean away. Collapse now requires `Not Indicated` + assessed +
  not flagged; anything unrecognised keeps a full card.
* **Unknown provenance must not become a claim.** Splitting lab rows on
  `source === 'lab_report'` put a row with NO source under "these came from the
  details you entered" — asserting a measured blood value was typed in by the
  patient. Only an explicit `patient_profile` moves a row now.
* **Missing information is not agreement.** The basis-conflict note was
  suppressed when per-source verdicts were absent, silently dropping a note
  Module 16 had stamped. Now suppressed only when two or more sources
  PROVABLY agree.
* **A safety string is data the safety scanner will read.** Two regressions
  introduced and caught here: generated band prose saying "had a diagnosis"
  (flagged as a diagnostic assertion in the patient report), and an artifact
  `honest_read` saying "SELF-REPORTED physician diagnosis" — which does not
  merely get flagged, it makes `doctor_summary` WITHHOLD THE WHOLE NOTE, so the
  clinician silently loses the model's statement of its own limits.
* **Guidance `becauseOfConditions` is the catalog's topic list, NOT a finding.**
  Printing it directly rendered "Shown because of: Diabetes, Obesity,
  Underweight and Heart Disease" under a report with none of them. It is
  intersected with what was actually flagged now.

### Smaller fixes

* `window.open` after `await` is silently blocked by every popup blocker — the
  tab must be claimed synchronously inside the click. And `noopener` in the
  feature string makes `window.open` return **null** by definition, so the
  handle is lost; `opener` is severed on the handle instead.
* Report rows: click the name to open the stored PDF, plus an inline-confirm
  Delete. Both backend routes (`DELETE /reports/:id`, `GET /:id/download`)
  already existed and had never been wired to the UI.
* The blob is rebuilt with an ALLOW-LISTED content type (pdf/jpeg/png) before
  `window.open`, because a `blob:` URL inherits the app's origin and would undo
  the download route's deliberate `Content-Disposition: attachment`.

---

## 6v. Descriptions for tests this platform does not assess · 2026-09-07 · **FINISHED IN §6w**

`ai-service/app/services/parameter_glossary.py` + 14 tests. **Backend wiring
done, dashboard rendering NOT done — see "What is left" below.**

### What it does

Asks the model ONE question about a test NAME: *what does this test measure?*
Then shows the patient's own value beside it, rendered from the extraction.

**Why this is not "letting the LLM interpret unknown parameters"**, which was
asked for and declined:

1. **The prompt contains no patient data.** Not the value, not the range, not
   the flag, not age or sex. A test name. So the answer cannot be about the
   person, and the model is never in a position to interpret anything.
2. **No number may come back**, enforced locally — see the defect below.
3. **Every answer passes the Module 24 validator**, same as Module 23.
4. **Cached by test name** (the answer is identical for every patient) and
   capped at 8 calls per report. The free tier is 20 calls/day; without the
   cache this feature is unusable.

Only tests **the laboratory itself flagged abnormal** are described — nine on
PK0016, not sixty-three. Describing "Urine Colour: Pale Yellow" is what would
burn the quota.

### THE SAFETY DEFECT WORTH REMEMBERING

The obvious assumption — that an empty `permitted_numbers` forbids all numbers
— **is wrong and is the opposite of the truth.** In `app/safety/validator.py`:

```
active = bool(context.grounding_sources) or bool(context.permitted_numbers)
```

A context supplying NEITHER gets **no numeric control at all**. The first
version of this module was approved while returning *"A normal level is 3.5 to
5.1 mmol/L"* — an invented reference range, the single most dangerous output
this feature could produce. Module 23 never hits it because it always supplies
grounding.

The rule is enforced locally instead of loosening a shared safety default. It
then failed twice more, both silently:

* a shell heredoc turned `\b` into `\x08` (a literal **backspace byte**), so the
  regex could never match and every test of it passed for the wrong reason;
* without word boundaries, "one" matches inside **bone** and **hormone**, so a
  correct description of vitamin D or a thyroid test would be discarded.

Tests now assert the patterns fire on known-bad AND stay silent on known-good.
Do not trust a regex here by reading it.

### What was left — **ALL THREE DONE 2026-09-07, see §6w.** Kept for the reasoning.

1. **Render it.** `Dashboard.jsx` → the `Unanalysed` component already lists
   lab-flagged results; it needs to read `dashboard.parameterGlossary` and show
   each description under its test. The backend does NOT yet expose it —
   `dashboardService.buildUnanalysedSection` must merge
   `report.parameterGlossary` entries into `unanalysed.items` by test name, and
   `DASHBOARD_PROJECTION` must add `+parameterGlossary`.
2. **Re-analyse a report to populate it.** The stage only runs during
   `POST /reports/:id/analyze`; existing stored reports have no glossary.
   Costs one model call per new lab-flagged test name, then cached.
3. **No tests yet for the backend stage** (`labFlaggedUnmappedNames`,
   the `describeParameters` client call, persistence). The Python module has 14.

### A live bug this nearly shipped

`runDownstreamStages({ features, requestId })` had no `extraction` in scope, and
the new selector referenced it — an undeclared identifier, so **every analysis
500'd** and 46 backend tests failed. Fixed by threading `extraction` through.
The lesson is only that the backend suite catches this class immediately; run it
after touching `analysisService.js`.

---

## 6w. The glossary finished, then three screens rewritten · 2026-09-07

Two halves. **First**, `parameter_glossary` (§6v) was completed and live-verified
— that is everything down to "Still open". **Second**, and unplanned: the user
read the running screens and found defect after defect in them, which produced
the five subsections from "The closing In short summary" onward. Every one of
those is a RENDERING defect on a correct pipeline. Read them together; the
pattern only shows up across all five.

The three steps in §6v are done and the feature has been driven end to end
against real Gemini. All three suites green: **ai-service 3,697 · backend 634 ·
frontend 50** (+7, +16, +6).

### THE DEFECT THAT MATTERED: THE FEATURE WAS DEAD ON EVERY CALL

`POST /api/v1/explain/glossary` returned a **bare `GlossaryData`** instead of the
`{success, data}` envelope every other route in `routes_explain.py` returns. The
backend's `unwrapEnvelope` requires `success === true` and an object `data`, so
it rejected a perfectly good HTTP 200 as `AI_SERVICE_MALFORMED_RESPONSE`.

The first live run made this visible in the ugliest possible way:

```
ai-service log :  parameter_glossary {'requested': 3, 'generated': 3, 'withheld': 0}
stored analysis:  glossary {"ok": false, "errorCode": "AI_SERVICE_MALFORMED_RESPONSE"}
```

Three descriptions were generated, safety-validated, cached — and thrown away at
the transport boundary. **The module's 14 tests never went through HTTP**, and
`test_every_route_answers_with_the_key` in `tests/test_explain_endpoint.py`
asserts exactly `response.json()["success"] is True` and would have caught it on
the first run. **The route was simply never added to that file's `ROUTES` list.**

Fixed with a `GlossaryResponse` wrapper, the route added to `ROUTES`, and five
dedicated HTTP tests. Verified by mutation: reverting the wrapper fails three
tests, one of them the shared route walk.

> This is the sixth time on this project that a green suite said nothing. The
> shape here is new and worth naming: **the unit tests were excellent and tested
> the wrong layer.** A module can be perfect and unreachable. Anything with a
> route needs one test that goes through the route.

### The three §6v steps, as built

1. **`dashboardService.buildUnanalysedSection`** takes `parameterGlossary` and
   merges entries into `unanalysed.items` by `test_name`.
   `DASHBOARD_PROJECTION` gained `+parameterGlossary`; the controller passes
   `null` (not absent) when the field is missing.

2. **`Dashboard.jsx`** renders each description under its test, in both the
   lab-flagged list and the collapsed groups.

3. **Populated live.** Report 06 (below) analysed against real Gemini: glossary
   stage `ok: true`, 14.4s, 2 described / 1 withheld / 1 never asked.

### THREE STATES, NOT TWO — the design decision the whole feature turns on

Only tests **the laboratory itself flagged** are ever described, so most
unassessed items were never asked about. That is not the same as an entry whose
description was withheld. Collapsing them would render "nobody asked" as "there
is nothing to say about this test" — this codebase's standing failure mode in a
new costume.

| Situation | Item fields | On screen |
|---|---|---|
| Never asked (lab did not flag it) | none | nothing |
| Described | `descriptionAvailable: true` + `description` | the text |
| Withheld (model silent, or Module 24 refused) | `descriptionAvailable: false` + `descriptionNotice` | the producer's notice |

Section level carries `descriptionsPresent` — whether the stage ran for this
report at all, which separates "analysed before this feature existed" from
"described nothing" — plus `describedCount` / `withheldCount` **derived from the
items**, never from the payload's own counters. (§6u: `document.unmapped_count`
said 0 on a report with 63 unmapped parameters and the dashboard repeated it.)

Verified by mutation: collapsing never-asked into withheld fails three backend
tests; ignoring the producer's `available` flag fails one.

### The safety sentence is ON THE SCREEN, not in a comment

> *"Where a description appears below, it explains what the test measures in
> general. It was written from the name of the test only — your result was not
> used and is not interpreted here."*

Shown only when at least one description is present. That sentence is the entire
argument for why this feature is safe, and it sits under a number the laboratory
flagged abnormal — without it the paragraph invites exactly the reading the
architecture forbids.

### A NEW FIXTURE, because none of the five could exercise this

**All five reports that already existed carry only the eight tests the platform assesses,
and none prints a reference interval.** So `unmapped` was empty, the selector
asked for nothing, and analysing any of them would have proved precisely
nothing. Added **`06-lab-flagged-tests-we-do-not-assess.pdf`**:

* 02's assessed panel, **value for value**, so the four extra rows are the only
  difference between the two fixtures — a verdict that differs means an
  unassessed parameter influenced an assessed decision.
* Four rows the platform has no feature for, **with printed intervals and the
  laboratory's own H/L flags**: LDL 160 (H), HDL 44 (in range), Blood Urea 53
  (H), Potassium 5.2 (H).
* Urea and potassium are raised while **creatinine, the one renal marker that IS
  assessed, is 1.1 and correctly produces no kidney finding.** That is the §6u
  defect's exact shape: corroborating evidence on the same page as the verdict.
* HDL is in range on purpose — it must be listed and **not** described. A
  description appearing for it means the selector widened, and a sixty-parameter
  report would then exhaust a day's quota.

**Printing an interval on an unassessed row does not violate the generator's
"no reference intervals" rule — it is the same rule.** An interval on an
assessed test would let a verdict be copied off the page instead of decided by
the service's own thresholds. An unassessed test has no threshold and reaches no
verdict, so the laboratory's marking is the only judgement that will ever exist
for it, and a fixture omitting it cannot exercise the path that carries it.

The generator now also **fails to generate** if the engine assesses a row the
fixture carries as unassessed — so if `blood_urea` is ever added to
`feature_catalog.py`, whoever adds it is told that fixture 06 needs a new
unassessed row, rather than finding out when the section it exercises silently
empties.

### The live run, in full

`06-...pdf` → upload → analyze (85.5s, every stage ok) → dashboard:

| Test | Value | Lab | What the screen shows |
|---|---|---|---|
| LDL Cholesterol, Direct | 160 mg/dL | high | described |
| HDL Cholesterol | 44 mg/dL | — | listed, no description, nothing implying one was tried |
| Blood Urea | 53 mg/dL | high | **withheld** — Module 24 rejected it twice, `UNHEDGED_INTERPRETIVE_CLAIM` |
| Potassium, Serum | 5.2 mmol/L | high | described |

The Blood Urea withholding is the safety layer working, and worth keeping:
an **earlier cached generation for that same name said blood urea "primarily
relates to liver function"**, which is clinically wrong — urea is a renal
marker. Withholding it was the right outcome, reached for a reason
(unhedged interpretive claim) that is not the reason it was wrong. Do not read
this as the validator catching a factual error; it does not check facts.

### Smaller things found on the way

* The withheld line initially printed the platform's own sentence **and** the
  producer's notice, saying the same thing twice. The notice is already a whole
  patient-readable sentence; ours is now only the fallback for a withheld entry
  that arrives with no notice — which must still not render as a blank line.
* `labFlaggedUnmappedNames` is now exported and has 6 tests. It was untested and
  both its failure modes are expensive: too wide burns a day's quota, too narrow
  loses the laboratory's own markings.
* **Windows curl cannot read an MSYS `/c/...` path.** `-F "file=@/c/..."` sends
  nothing at all and prints nothing — the request never leaves. Use `C:/...`.
* Both services had to be restarted before any of this worked: the running
  ai-service predated the glossary route entirely (`/api/v1/explain/glossary`
  was not in its OpenAPI), and the backend predated the read path. **A live run
  against a stale process proves nothing** — check `/openapi.json` for the route
  before believing a live result.

### The closing "In short" summary · added on the user's request

The page had a verdict at the top (`Needs Medical Attention` / `High`) and six
per-feature paragraphs at the bottom, and **nothing that said the whole report
in one breath.** A closing `In short` section now does, as the last thing on the
page — a recap, not a headline, so it is read after the findings rather than
instead of them.

**IT IS COMPOSED, NEVER GENERATED, AND THAT IS THE WHOLE DESIGN.** "Summarise
this report for the patient" is one prompt away and would be the most dangerous
string on this screen: a new patient-facing conclusion with no rule, no
threshold, no model and no evidence chain, rendered under fourteen findings that
have all four and looking more authoritative than any of them. Every sentence is
assembled from a decision some stage already made.

**The counts come from the CARDS, not the counters.** `overall` carries
`abnormalConditionCount`, but the page groups cards with its own predicate
(`Not Indicated` + assessed + not flagged; anything unrecognised stays flagged),
so counter and cards can disagree. The grouped arrays are passed down. A test
feeds `abnormalConditionCount: 99` and asserts 99 never reaches the screen.

Three paragraphs exist ONLY to stop an absence becoming a negative result, and
each is separately mutation-tested (deleting any one fails exactly one test):
topics that could not be checked, tests the laboratory flagged that this
platform does not assess, and pages that could not be read.

Two defects found while building it, both by the tests:

* **An unrecognised status label rendered an empty `<strong>`.** `STATUS_IN_ENGLISH[label]`
  yields `undefined`, and `undefined !== null` is true, so the branch meant to
  say *"this screen has no plain-English wording for that result"* was skipped
  and the summary said nothing at all about the verdict. `?? null` is
  load-bearing. **An unknown label never gets a guessed gloss** — a missing
  gloss is cosmetic, a wrong one is clinical.
* **A comma inside a test name split it into two tests.** Laboratories print
  "LDL Cholesterol, Direct" and "Potassium, Serum", so a comma-joined list of
  three read as five — directly contradicting the "marked 3 results" in the same
  sentence. The separator is now chosen from the data: semicolons only when a
  name actually contains a comma.

Four pre-existing overall-card tests had to be **scoped to the card**. They
asserted page-wide that e.g. `Healthy` appears nowhere, which was right while
the verdict appeared once and is wrong now that the summary legitimately
restates it. The guarantee is unchanged and is about that card. **One assertion
stayed page-wide on purpose:** a missing risk must not become `Low` *anywhere*,
summary included.

Frontend suite **60** (was 50); **65** after the fixes below.

### Two defects a READER found on a real screen, in one glance

The user opened a report whose every laboratory value was in range and whose
only flagged topic was Obesity, and asked two questions. Both were right, and
neither suite had anything to say about either.

**1. "All are shown as in range — then why does the summary say one is out of
range?"** Obesity is decided by `RULE_OBESITY_BMI` from `bmi`, and BMI is
computed from the height and weight the patient typed into the profile form.
Nothing about it was measured in the document. The summary's headline said
*"Something in this report is outside its usual range"* — **false, and it
contradicted the in-range table directly above it.**

The lab table already keeps these apart ("Your results" vs "From your
profile", §6u) and the summary had flattened that distinction back on its very
first line. Fixed twice over: the status wording now claims no location at all
("One of the things this tool checked…"), and the provenance is stated
outright, derived from each evidence line's `sourceStage`.

**Then the SAME mistake one clause further down.** The new sentence ended
*"…that is why it can be flagged while every laboratory result on the page is
in range"* — true on the all-clear report it was written for, false on a mixed
report that also flagged Diabetes from a raised HbA1c. Caught by reading the
finished sentence on a real mixed report, not by a test. That clause is now
conditional on the profile findings being the ONLY findings.

`isProfileDerived` returns **false on empty evidence**, deliberately:
`[].every(...)` is `true`, so without a length check a finding of unknown
provenance would be announced as coming from the form. Unknown provenance must
not become a claim in either direction — and the dangerous direction is telling
a patient a raised blood value was something they typed in.

**2. "Needs Monitoring with risk Low — aren't those contradicting?"** They are
not. Module 18's rule (`report_builder.overall_status`) is:

```
No abnormal findings              -> Healthy
Abnormal findings + no High risk  -> Needs Monitoring     <-- this pairing
Abnormal finding  + High risk     -> Needs Medical Attention
```

So the pairing is the DEFINED output for a mild finding. The status and the
risk are different scales — one says *whether anything was flagged*, the other
*how serious the worst flagged thing is*.

**THE FIRST FIX WAS WRONG AND THE USER SAID SO.** A paragraph was added
explaining that the two answer different questions. The user's reply: *"why
this for a patient — display only what is useful for the patients."* Correct.
That paragraph is a lecture about two internal fields; a patient cannot act on
it, and its existence is an admission that the screen is showing something it
should not.

**The real fix is not to put the reader in front of the pair at all.** Both
explanatory paragraphs are gone, and so is the summary's
`Recorded as <label> · overall risk: <risk>` line, which restated the Overall
card's vocabulary at the foot of the page. The severity is already carried by
the English sentence — *"worth keeping an eye on and worth raising at your next
appointment"* against *"should be looked at by a doctor"* — which is the part a
patient can act on. The labels stay on the Overall card and the clinician
summary, which is exactly the split §6u established and which this had drifted
away from.

> Generalisable: **when a screen needs a paragraph explaining why two of its
> own fields do not contradict each other, the fields are the bug, not the
> missing paragraph.**

Mutation-tested. Frontend suite **65** (three tests replaced by one asserting the vocabulary stays OFF the patient summary).

> The lesson is not about either bug. It is that **a screen nobody has read
> aloud is untested.** 60 passing tests, three mutation rounds and a live
> browser check had all been done, and a reader found two false statements in
> the first paragraph in under a minute. Every prior entry in this file records
> a green suite missing something a person then found. This is the first one
> where the person was the user.

### The clinician summary, read end to end · Module 32's page rewritten

The user asked for the same pass over "Summary for a healthcare professional".
Reading the rendered page against the payload it serves, **the page was showing
a fraction of what it had and burying that fraction in repetition.** Every
finding below is a rendering decision; the pipeline produced all of it
correctly.

**1. THE MEASURED VALUES WERE NOT ON THE PAGE.** `laboratory.rows` carried all
eleven — HbA1c 8.4%, glucose 186 mg/dL, cholesterol 268 — and **none was
rendered.** A clinician was told `RULE_DIABETES_HBA1C` fired and never told
what the HbA1c was. For a document whose own stated purpose is to be read
*alongside the original laboratory report*, that is the one omission it cannot
afford. This was the single worst thing on the page and no test covered it.

**2. TEN RETRIEVED REFERENCE PASSAGES WERE DISCARDED BY A SHAPE BUG.**
`trends` and `comparison` carry `present` at the top level; `knowledge` and
`evidence` carry it under `.status`. `<Section status={summary.knowledge}>`
read `undefined` and printed **"This section is not available"** over a fully
populated section — an absence asserted to the reader that was not an absence,
which is this project's signature failure wearing a new hat. Fixed with a
`statusOf()` accessor that handles both shapes.

**3. A PROBABILITY AT SIXTEEN DECIMAL PLACES** — `probability
0.9509128032443647` from a model with ROC-AUC 0.697. §6u fixed exactly this on
the patient dashboard ("a bare 0.0089 reads as precision this model does not
have") and the clinician page kept it. Now `95%`, with the exact value in the
element's `title` so nothing is lost.

**4. THE SIGNAL WAS BURIED IN BOILERPLATE.** "This source compared measured
laboratory values against fixed thresholds" appeared **ten times**, the
statistical-model sentence three, and seven unflagged topics each got a card
identical to the six flagged ones. Six findings that mattered sat inside
thirteen indistinguishable blocks. The per-source sentence is a property of the
SOURCE, not of the topic, so it is now stated **once** in a legend; flagged
topics come first; assessed-and-clear collapses to one named line.

**5. NEVER RENDERED AT ALL:** `patient` (age/sex/BMI + what was *not*
supplied), `data_quality` (pages, confidence, valid/rejected counts, warnings),
`integrity` (`llm_calls_made: 0` — a claim a clinician is entitled to check),
and `attribution`.

**6. A WITHHELD TRANSCRIPTION WAS INVISIBLE.** `integrity.transcriptions_withheld: 1`
at `laboratory_values[4].original_test_name` — the Module 24 scanner refused to
reproduce the printed name of *Vitamin B12* because it matched `medication_name`.
A clinician would have seen one row with no printed name, every other row with
one, and no way to know why. Now stated on the row and in the integrity block.

#### Two faults introduced during the rewrite and caught by reading the result

* **The boilerplate came back one component lower.** Rendering both laboratory
  columns unconditionally produced **eleven copies** of "The source report
  printed no reference interval for this parameter" — the exact fault being
  removed, reintroduced inside `LabRows`. The dashboard had already solved this
  (§6u: drop a column nothing can fill). Now the columns drop and **the fact is
  stated once beneath the table** — dropping the column must not drop the fact,
  or eleven unqualified numbers read as in range.
* **`printed as "bmi"`, under a caption saying the row was NOT measured in this
  report.** The ai-service stamps `origin: report_transcription` on
  profile-derived rows with the feature key as the text, so the page claimed a
  transcription of something nobody printed. Gated on the same flag the
  laboratory columns use. **This is an ai-service defect, unfixed at source.**
  Alongside it, the catalog's `display_name` for `gender` —
  *"Self-described gender as stored by Module 2."* — was rendering as a table
  row label; §6u caught that identical string leaking onto the dashboard and it
  was still leaking here.

#### One earlier decision reversed

The scope statement (`purpose.is_not`) was moved to the foot of the page as
"eight sentences of negation between the reader and the findings". **Wrong
move:** its first line reads *"No line **below** asserts that any condition is
present"*, and at the bottom of the page "below" points at nothing. These are
the service's own sentences and this file does not get to reword them, so they
go back where they are true. The real complaint was DUPLICATION — a
near-identical copy at the foot — and that copy is what went. Set as a list
rather than a run-on paragraph, which is what made five statements read as a
wall.

`reason_code` chips (`SINGLE_REPORT_ONLY`) were left alone: shown deliberately
by `Absent.jsx`, asserted by tests on three separate pages, and changing that
is a wider decision than this page.

Frontend suite **76**. Four of the fixes mutation-tested (dropping the lab
table fails 2, restoring the shape bug 1, restoring the raw probability 1,
repeating the methodology 1).

> The pattern across all three of this session's screens is one thing: **the
> pipeline's output was fine and the rendering layer was where the lying
> happened** — by omission (values, passages, withheld transcriptions), by
> false precision (sixteen digits), by false provenance (`printed as "bmi"`),
> and by burying six real findings in thirteen identical blocks. None of it was
> visible from a green suite. All of it was visible from reading the page.

### "This website is used by normal users" — and the CRITICAL defect that found

The user's objection to the clinician page: *"why clinical rule engine and random
forest, why all these? this website is used by normal users who don't know
anything about clinical rule engine."*

They are right, and §6u had already ruled on the same words. "Based on: Clinical
Rule Engine, Random Forest" was removed from the patient dashboard because they
are **internal component names, useless to the person whose blood it is** — and
they were moved HERE. **Here turns out to be read by the same person.** The
document is addressed to a clinician and generated *for the patient to hand
over*, so the patient reads it first, every time.

What was on a page a patient opens:

```
Clinical Rule Engine · Random Forest · RULE_OBESITY_BMI · conditions.OBESITY
app/services/doctor_summary.py · feature_catalog.py · clinical_rules.py
laboratory_values[4].original_test_name · Module 24 safety scanner
term-frequency matching · ROC-AUC 0.697 · precision at the operating threshold
```

**Source-file paths and array indices have no defence at either register.** No
reader of a medical document is served by a Python module path.

#### THE CRITICAL FIND: every model was rendered with NO limits at all

Chasing the jargon exposed something far worse. **`limitations` lives at
`basis.ml.limitations`. The page read `basis.limitations`, which is `null` on
every real response.** So `ModelLimits` returned null and **every model
probability on this page was shown with no ROC-AUC, no recall, no caveat and no
author note.**

Including this, from the heart model's own `author_note`, sitting unrendered:

> *"Precision at the Indicated cut-off is about 0.37, so most patients it flags
> will NOT have heart disease — a high score is a reason to discuss testing with
> a clinician, never a finding."*

This file's own docstring records this defect being found and fixed **twice**
(§6o D8, §6p). This is the **third** occurrence, at the render layer.

**The fixtures are why it survived.** `tests/clinical.test.jsx` put
`limitations` at the basis level — where the page looked — so the test asserting
"shows a model probability WITH its detection rate, never alone" passed while
the live page showed the probability alone. **A fixture written against the
consumer's assumption instead of the producer's output cannot catch the
consumer's assumption being wrong.** That is a new entry in this project's
catalogue of green-suite failures, and the most useful one yet.

Now rendered, all of it previously in the payload and unused: the real
`limitations`, `author_note`, `band_meaning` (*"96.9% of patients in this band
were positive"* — what the percentage actually means), and `features_missing`
(*"this model had no value for hypertension, and reached the figure above
without it"*).

#### The two registers, split by AUDIENCE rather than by page

* **Always visible** — what the check was, in words (`Compared against standard
  limits`, `Counted risk factors`, `Statistical pattern model`, mapped from the
  stable `assessment_basis`/`source_kind`, never from the display name); the
  estimate as a percentage; and **every caveat and author note**, because a
  model's limits are the thing a reader can be harmed by not seeing. The
  docstring's rule that caveats are never behind a toggle is unchanged.
* **Behind "Technical details"** — ROC-AUC, precision, accuracy, baseline, rule
  identifiers, the incomplete-metrics code, the knowledge passages' provenance
  line, and the retrieval method. Nothing deleted, still in the DOM, still
  printable.

`source_report_violation_locations` is rendered **nowhere**: an array path
locates a field for someone reading a bug report and has no audience on this
page. The count and the consequence are stated in words.

Reference passages are now grouped **by document**, because two chunks of one
article rendered as two entries put the identical heading on screen twice and
read as a duplication bug.

`readableFeature` deliberately does NOT consult `PROFILE_LABEL`: that table is
for table-row headings, where "Smoking history (reported)" is right, and it is
wrong mid-sentence — *"this model had no value for Smoking history (reported)"*
is not English. Two uses that look interchangeable and are not.

**One "ROC-AUC" remains visible**, inside the kidney model author's own caveat
("a ROC-AUC near 0.99 says the separation was easy, not that this would hold on
a screening population"). Rewriting an author's safety note to remove a term is
not a licence this file has.

Frontend suite **77**. Three mutations checked: the wrong `limitations` path,
caveats behind the toggle, and the author note hidden — each fails a test.

### The clinician page becomes ONE PASSAGE · the user's call, and it was right

*"just a summary for that professional in a simple paragraph based on the
results... it should be professional... don't mention anything unnecessary like
this is for this, this is generated by llm."*

The structured document is gone: purpose statement, scope bullets, a card per
condition, the source legend, "how this document was produced", the ten
retrieved reference passages, the data-quality block, rule identifiers, the
metrics table, every source-file path. **Most of that was the page talking about
ITSELF rather than about the report.** A clinician handed a patient's phone for
thirty seconds does not read a document that explains its own architecture
first.

What replaced it is a handover note — subject, values, what was flagged and by
what, what was not available, one closing line. Professional register: a
clinician reads `HbA1c 8.4 %` and does not need it translated.

**COMPOSED, NOT GENERATED.** "Summarise these results for a doctor" is one
prompt away and would be the worst possible use of one — a clinical narrative
with no rule, no threshold and no evidence chain, in a register that invites
action. The service also publishes `integrity.llm_calls_made: 0` and
`model_generated_text_included: false` ABOUT THIS DOCUMENT; generating the prose
would make both claims false.

#### Four things kept, because cutting them would make the passage lie

1. **WHICH KIND OF CHECK FLAGGED WHAT.** On the live report: creatinine
   1.1 mg/dL does not cross the kidney rule and the model flagged it anyway.
   The passage says *"Kidney Disease was flagged by the statistical model only —
   no measured value crossed a configured threshold for it."* A clinician told
   "kidney disease flagged" without that is being told something the analysis
   did not find. Three groups: flagged by both, by threshold only, by model only.
2. **ONE SENTENCE OF MODEL LIMITATION**, in the model author's own words,
   wherever a model contributed to a flag.
3. **EVERY ABSENCE** — fields not supplied, parameters the report lacked, pages
   unreadable, stages that failed. The rule the codebase is built on, and the
   one a compressed summary is most likely to drop.
4. **ONE closing line**, not the ten-sentence scope statement.

#### Three faults found by reading the finished passage

* **A lowercase list opened a sentence** — *". hypertension, heart disease..."*.
* **The same three fields were named twice** — once as "not supplied" and again
  as "not present in this report". For hypertension, heart disease and smoking
  history those lists hold identical names, so the reader saw it, read a
  paragraph, saw it again. They are different facts, and a field the patient
  never supplied cannot also be a parameter the report failed to carry, so the
  second list now excludes anything already named in the first.
* **A model's caveat appeared under a finding that model DISAGREED with.** The
  notes were collected from every basis of every flagged topic, so the heart
  model's four-sentence note printed beside a Heart Disease flag the heart
  model had returned `Not Indicated` for. A note qualifies an OUTPUT; a model
  that flagged nothing produced no output this passage reports.

Four properties mutation-tested: collapsing the model-only distinction, dropping
the no-intervals sentence, dropping the absences paragraph, and letting a
rejected reading into the values — each fails a test. Frontend suite **71**
(17 Module 32 tests replaced by 11 written against the passage).

> **The pattern, stated once:** three screens, three rewrites, and every defect
> was the rendering layer — lying by omission, by false precision, by false
> provenance, by burial, and finally by talking about itself instead of the
> patient. The pipeline was correct throughout. **A green suite saw none of it;
> a person reading the page found all of it.**

### §6r D1 CLOSED — the RAG anchoring reaches the public endpoint at last

Asked whether the platform uses RAG, checking the answer turned up the open
defect from §6k D7 / §6r D1, still live and still reproducing verbatim.

**What the RAG layer is:** 62 documents → 377 paragraphs → **243 chunks**,
retrieved with **TF-IDF**, no FAISS, no embeddings model. That choice is
measured, not assumed, and `app/rag/embeddings.py` states the cost honestly:
all-MiniLM-L6-v2 scores Recall@1 **0.967 vs 0.733** and MRR **0.971 vs 0.822**.
The argument for the lexical option is narrow and is written as narrow —
Module 23 takes the top 5, so Recall@5 (0.967 vs 0.933, one query in thirty) is
the operative metric, and it holds only because queries here are built from
canonical vocabulary rather than free prose.

#### THE DEFECT: the control existed, was tested, was documented, and was bypassed

There were TWO retrieval entry points and only one was safe:

* `retrieve()` ran `_anchor_free_text` — every word and adjacent pair resolved
  through the same exact synonym index Module 5 uses, returning **nothing** when
  a phrase anchors to nothing.
* `retrieve_payload()` called `build_query` directly and skipped it — and
  `retrieve_payload` is what **`POST /api/v1/knowledge/retrieve`** calls.

So the one path a stranger can reach was the one without the control:

```
'what should I take for my thyroid'  -> 5 chunks about TRIGLYCERIDES
'is my liver enzyme high'            -> 5 chunks about LDL/HDL and vitamin D
'chest pain'                         -> a chunk about when to seek advice
```

**Why no test caught it.** `test_off_domain_query_returns_empty_not_junk`
passed throughout — "how do I fix my bicycle" is far enough off-domain that the
similarity floor catches it. The queries that got through were **medical ones
this corpus does not cover**, and those score 0.141–0.271 against covered terms'
0.121–0.27: the ranges overlap completely, so **no floor can separate them** and
only anchoring can. The test suite proved the easy half of the property.

#### The fix, and why it is shaped this way

Both entry points now build their query through one `_anchored_query()`.
Patching `retrieve_payload` alone would have restored the behaviour and left
the cause — **two paths building the same query independently is why a fix
applied to one looked complete from either end and survived two audits.**

The echo is better for it: a refused query reports `source: "unanchored"` with
empty features, and a covered one reports what it actually resolved to, so a
reader sees the resolution step rather than just the raw text.

**One existing test had to be changed, and it was asserting the defect.**
`test_free_text_retrieval_works` required `query.source == "text"` — i.e. that
this endpoint retrieved on raw words, which is exactly what D7 was about. It now
asserts `findings_and_text` with `features == ["hba1c"]`.

Verified on the live HTTP endpoint after restart: both D7 examples return
`returned=0, grounding_available=false`, and "what does a raised HbA1c mean"
returns 5 chunks anchored to `hba1c`. Reverting the fix fails four of the new
tests. **ai-service 3,721.**

> The Module 23 patient path was never affected — it goes through `retrieve()`.
> The exposure was the public endpoint, which is also where §6r found it.

### A Heart Disease card that named two inputs it did not have

The user pointed at one condition card. Two defects, both in the rendering
layer, both confirmed against the stored payload before anything was changed.

#### 1. ABSENCE RENDERED AS A VALUE, on the worst possible card

> *"Your history of heart disease, history of high blood pressure, smoking
> history, BMI, age and sex were also taken into account."*

Of the six named, **two did not exist**. The stored evidence:

```
heart_disease    availability: not_present_in_report   value: null
hypertension     availability: not_present_in_report   value: null
smoking_history  availability: observed                value: "never"
```

`summariseEvidence` bucketed a cited feature into "context" on the strength of
it having a `PATIENT_LABEL`, **never consulting `availability`** — so a null
became a contribution.

**This is the single worst place on the platform for that sentence to appear.**
The heart model's own author note reads *"Blood pressure, the strongest known
predictor, is still not collected by VaidyaAI."* The card asserted, to the
patient, the exact opposite of the assessment's most important limitation.

Fixed by gating on `availability === 'observed'`. **The absent ones are NOT
dropped** — dropping them is the same failure from the other side, and the
reader would never learn the strongest predictor was missing:

> *"No value was available for your history of heart disease or history of
> high blood pressure, so they could not be taken into account here."*

#### 2. "Close to the usual limit" printed above two values that were over it

The card read *"Close to the usual limit — worth keeping an eye on"* directly
above:

```
Total cholesterol   268 mg/dl   above 240 mg/dl
HbA1c (average...)  8.4 %       above 6.5 %
```

Both statements were true of **different things** and the reader had no way to
know which. Heart Disease here was decided by
`assessment_basis: risk_factor_count` — the COUNT was borderline; the
individual values were plainly over their cut-offs. "Close to the usual limit"
describes a threshold comparison, and no threshold comparison happened.

`PATIENT_STATUS` now has a `RISK_FACTOR_STATUS` sibling, selected when a card
has **positive proof of a count and no threshold comparison at all**. A topic
with both keeps threshold wording: a crossing did happen, and that is the more
concrete thing to say. An unrecognised basis keeps the default — an unfamiliar
basis must not silently acquire a different description.

#### The mutation that survived, and why it mattered

Four mutations were run. Three failed a test immediately. The fourth --
reducing the gate from `counted && !compared` to `counted` -- **passed
everything**, because every fixture had exactly one basis. A card carrying BOTH
is the only shape that distinguishes them, and it is the shape the real Heart
Disease card is one config change away from. Added, and the mutation now fails.

> `counted && !compared` is two conditions, so it needs two tests. One
> assertion per clause, not one per function.

Frontend suite **84**.

### Still open

* **The ai-service stamps `origin: report_transcription` on profile-derived
  laboratory rows**, with the canonical feature key as the "transcribed" text
  (`bmi`, `age`, `gender`). Nothing was printed on any report for those. The
  clinician page now guards against it; the field is still wrong at source.
* **`feature_catalog`'s `display_name` for `gender` is an internal note** —
  "Self-described gender as stored by Module 2." — and it reaches any renderer
  that trusts `display_name`. Two screens now override it locally. It should be
  fixed in the catalog.
* **Module 32's payload nests `present` two different ways.** `trends` and
  `comparison` carry it at the top level; `knowledge` and `evidence` carry it
  under `.status`. A renderer that assumes one shape silently reports the other
  as absent, which is exactly what happened to ten reference passages. The
  frontend now normalises with `statusOf()`; the contract is still inconsistent
  at source and the next consumer will hit it.
* **THE FRONTEND FIXTURES ARE NOT VALIDATED AGAINST REAL RESPONSES**, and that
  is now a demonstrated hazard rather than a theoretical one:
  `tests/clinical.test.jsx` put `limitations` at `basis.limitations` — where the
  page wrongly looked — so a test literally named *"shows a model probability
  WITH its detection rate, never alone"* passed green while the live page showed
  the probability alone, for three recurrences. **A fixture written against the
  consumer's assumption instead of the producer's output cannot catch the
  consumer's assumption being wrong.** Worth generating fixtures from a captured
  real response, or at minimum diffing the two.
* **The clinician page no longer renders the retrieved reference passages,
  `data_quality`, `integrity` or the scope list.** That is a deliberate product
  decision (§6w, final subsection), not an oversight — the page is a handover
  passage now. The data is still in the payload; do not re-add it as a "fix"
  without asking.

* **`app/api/routes_explain.py` was the only place this envelope was missing,
  but nothing enforces it.** `ROUTES` is a hand-maintained list, so the next
  route added there can repeat this exactly. A test that walks the router's own
  routes and asserts every one returns `{success, data}` would close the class;
  it is not written.
* The Python module's own 14 tests still do not touch HTTP. That is fine now
  that the endpoint has its own, but the split is worth keeping in mind.
* `document.unmapped_count` in `report_builder` **still writes 0** (§6u). The
  dashboard derives around it. Unfixed at source.

---

## 6x. The "Instrument" design system · 2026-09-11 · `design.md` implemented

The user wrote `design.md` (option 2c/3a, warm sand + warm brown-black) and
asked for it across the whole app — login and authorisation included — plus a
dark-mode toggle. Frontend suite **44 → 109**.

### THE MOVE THAT MADE IT SAFE: ALIAS, DO NOT RENAME

`styles.css` had 294 lines naming colours by their old roles (`--line`,
`--card`, `--accent`, `--danger`, `--low/medium/high`). The obvious
implementation is a rewrite; the obvious implementation also silently drops a
selector, and on this screen a dropped selector is a dropped absence state.

So the new palette was installed and the OLD NAMES ALIASED ONTO IT:

```css
--line: var(--panel-line);   --accent: var(--brand);
--card: var(--panel);        --low:    var(--green-text);
```

Every existing rule became theme-aware in one move, nothing was deleted, and
the old names still say what each rule MEANT. Three literal hex values outside
`:root` were retired; the file now has none.

**`--on-brand` / `--on-danger` are the tokens that stopped a real defect.**
`button { background: var(--accent); color: #fff }` is fine while the accent is
a dark clay and illegible the moment it is a light gold — which is exactly what
dark mode makes it. "White on the accent" is not a colour, it is an assumption.

### The toggle, added without giving any component a theme

`design.md` §2 ships no toggle and sets `data-theme` once at boot. The user
asked for one; it was added while keeping the spec's actual property intact —
**no component knows the theme exists**. `lib/theme.js` writes `localStorage`
and re-stamps `data-theme` on `<html>`; every colour is already a token, so
nothing else changed. The toggle is in the header AND on the sign-in screen,
because the header only renders when signed in and sign-in is both the first
screen anyone sees and the one most likely to be opened at night.

The theme is stamped by an inline script in `index.html` **before first paint**.
Doing it in React renders one frame of the light palette first, which on a
dark-mode phone is a flash of near-white — the exact thing dark mode exists to
prevent. Every `localStorage` access is wrapped: in a private window the
ACCESSOR throws rather than returning null, and a theme preference must never be
able to take the app down. "Never chosen" is kept as `null`, distinct from
'light', so a dark-mode user is not silently opted out of their own setting.

### The charts, and the one thing each of them could have got wrong

Three hand-authored SVG components taking already-derived data. They hold no
threshold, no condition and no clinical rule — a change to what counts as
flagged happens in one place and cannot make a picture disagree with the words
beside it.

* **`RiskGauge`** — a gauge has a resting position and it is *low*. A report
  where nothing could be assessed would park the needle on "Low" and hand the
  reader "we could not look" rendered as "we looked and it was fine". So
  `assessed === false` draws **no needle and no hub**; there is no angle for
  unknown and the component does not invent one. A risk word arriving with
  `assessed: false` loses — absence is the safer of two contradictory readings.
* **`CoverageRadar`** — a vertex at the centre looks like a bad score and
  usually means the test was never done. Unassessed topics get the app's
  absence treatment (dashed, unfilled, `--mono` label) and are **pinned to
  zero even if a coverage number arrives**.
* **`RangeChart`** — three absences: not on the report, rejected reading, and
  in-range/flagged. A rejected 999 is never plotted: it is not a high result,
  it is not a result.

**The needle's angle is a static inline transform as well as the animation's
end state.** `prefers-reduced-motion` switches every animation off, and a
needle whose angle lived only in a keyframe would rest pointing at "low" on a
high-risk report. A chart that animates to the truth but rests on a lie is
worse than one that never moves.

### FOUR DEFECTS FOUND BY RENDERING IT, NOT BY READING IT

1. **The whole app was on `system-ui`.** `body { font: 16px/1.55 system-ui… }`
   is the `font:` SHORTHAND, which resets the family — and it sat after the new
   typography block. Three webfonts loaded and used by nothing but the wordmark.
   Invisible in the stylesheet, obvious in `getComputedStyle`.
2. **Links were browser-default blue** on a palette whose first principle is
   "no blue anywhere". Anchors outside the header had no colour rule at all and
   fell through to the user agent; on the dark ground it was low-contrast blue
   on near-black.
3. **Every band was drawn as an absence.** The chart had two band states and
   needs THREE: a printed interval (shaded band), *measured with no interval
   printed* (**no band at all**), and value-absent (dashed empty band). On a
   report that prints no intervals — which is most of them — the two-state
   version marked every single row as absent while showing its number beside it.
4. **"NOT USABLE" against three rows nobody had rejected.** Mapping
   `usable === false` to 'rejected' caught `state: 'unavailable'` too, so a
   profile question the patient never answered claimed a reading had been taken
   and refused. The payload's own `state` decides now.

Also caught: radar axis labels clipped to `"olesterol"` at the spec's exact
`viewBox` — on a chart about what was measured, the worst possible thing to
truncate. The pentagon geometry is unchanged; the frame is padded around it.

### How the sweep was done, and why it is worth repeating

Screenshots were unreliable (the browser pane captures below-fold content
mid-paint). So the audit ran **in the page**: walk every text-bearing element,
resolve the token palette to RGB, and flag any computed colour that is not in
it — plus every font family in use.

**12/12 route × theme combinations: zero colour offenders, exactly three font
families.** That is what caught the `system-ui` regression and would have caught
the blue links. A stylesheet cannot be audited by reading it; a rendered page
can be audited by asking it.

Mutation-tested: parking the needle at low when unassessed (3 tests fail),
drawing an unassessed radar topic as a filled dot (2), plotting a rejected
reading (1).

### Open

* The range chart and the results table both show every value. The chart is the
  picture, the table carries what it cannot (printed lab name, profile-derived
  rows, "no range printed"), and the table is the accessible record — the
  chart's bars are `aria-hidden`. If that reads as duplication on a real screen
  it is a one-line change, but it is deliberate.
* `design.md` §4 lists a `/timeline` trend chart in the range chart's vocabulary.
  Timeline has the tokens and typography but no chart yet.

---

### Two things changed after reading the running pages

**The population page was giving a card to every refusal**, including three
that nobody expected an answer for. `FEATURE_NOT_CONTINUOUS` covers age, gender
and smoking history: age and gender are what the cohort is **matched on**, so
asking for their percentile is circular, and smoking history is a word. Three
cards explaining that is the page describing its own mechanics.

Those three are now one line — *"age and gender are not measured values, so no
percentile is offered for them"* — and the cards that stay are the ones a reader
would otherwise wonder about: a glucose of 186 with no comparison beside it is
a real question, and *"fasting status is not recorded, so the comparison would
look precise and be wrong"* is a real answer. **The reason codes are still in
the payload**; only the cards went. Mutation-tested both ways: deleting the
summary line fails a test (an absence that stops being a card must not stop
being mentioned), and filtering out *all* refusals fails three.

**The breadcrumb row was four identical underlined links stacked in two rows**,
so every page opened with a list of equal-looking things and none of them was
the title. Now: the trail is mono micro-type that recedes, the filename is set
as the heading it actually is (19px sans), and the two cross-links are bordered
pills with a chevron — shape carrying "goes somewhere" rather than another
colour. Applied to the dashboard, the clinician summary and the population page.

---

## 6y. STATE AT THE END OF 2026-09-11 — read this before doing anything

**Everything runs. Everything is green. Nothing after commit `e175eb7` is
committed.**

### Suites, counted by running them

| | |
|---|---|
| `backend/` | **634** passing + 3 opt-in live |
| `ai-service/` | **3,739** passing + 7 skipped |
| `frontend/` | **111** passing |
| **Total** | **4,484** |

`cd backend && npm test` · `cd frontend && npx vitest run` ·
`cd ai-service && .venv/Scripts/python.exe -m pytest -q` **with `.env` moved
aside** (still unfixed; see §0).

### Running it

```
cd ai-service && .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
cd backend   && npm start          # :5000, Mongo Atlas, non-SRV URI
cd frontend  && npm run dev        # :5173
```

Health: `curl http://127.0.0.1:5000/api/v1/health`. **Restart the services
after any ai-service or backend change** — a live run against a stale process
proves nothing, and that has cost real time twice.

Test account with an analysed report:
`glossary.check+1788753613@example.com` / `Str0ng!Passw0rd`,
report `6a9e36ced9a53914342f3734`.

### UNCOMMITTED WORK — commit this first

`git status` at the end of the session:

* **frontend** — the whole "Instrument" design system (§6x): `styles.css`
  rewritten around tokens, `index.html` (fonts + pre-paint theme stamp),
  `lib/theme.js`, `components/ThemeToggle.jsx`, `components/RiskGauge.jsx`,
  `components/CoverageRadar.jsx`, `components/RangeChart.jsx`, `App.jsx`,
  `Dashboard.jsx`, `SignIn.jsx`, `Population.jsx`, `DoctorSummary.jsx`,
  `Reports.jsx`, `tests/design.test.jsx`, `tests/reports.test.jsx`,
  `tests/dashboard.test.jsx`, `tests/clinical.test.jsx`
* **ai-service** — the comma-synonym fix (`feature_catalog.py`), the 5xx model
  fallback (`gemini_client.py`), prose fixtures (`tools/make_test_reports.py`)
  and their tests
* **`design.md`** — the user's own spec, untracked
* `ai-service/app/data/trend_polarity.py`, `app/rag/retriever.py`,
  `app/services/trend_analyzer.py` and three test files were **already modified
  when this session started** and were not touched by it. Check what they are
  before committing.

### What to pick up

1. **Commit the above.** It is a session's worth of work sitting in the working
   tree, and `origin/master` has none of it.
2. **`design.md` §4 wants a timeline trend chart** in the range chart's
   vocabulary. Timeline has the tokens and the typography but no chart.
3. **Two ai-service defects, still open at source** (§6w "Still open"): profile
   rows are stamped `origin: report_transcription` with the feature key as the
   "transcribed" text, and `feature_catalog`'s `display_name` for `gender` is an
   internal note that reaches any renderer trusting it. Both are worked around
   in the frontend.
4. **Module 32's payload nests `present` two different ways** — `trends` and
   `comparison` at the top level, `knowledge` and `evidence` under `.status`.
   The frontend normalises with `statusOf()`; the contract is still
   inconsistent and the next consumer will hit it.
5. **The frontend fixtures are not validated against real responses** — a
   demonstrated hazard, not a theoretical one (§6w).

### The one habit worth keeping

Three sessions running, every defect found has been in the **rendering layer of
a correct pipeline**, and none was visible from a green suite. What found them:

* **reading the page aloud** — the user did this and found two false statements
  in the first paragraph of a screen that had 60 passing tests;
* **auditing the rendered DOM rather than the source** — resolving the token
  palette to RGB and flagging any computed colour outside it caught an entire
  app silently running on `system-ui`, which no amount of reading `styles.css`
  would have shown;
* **mutation-testing every guard** — flip the condition, confirm a test dies.

A screen nobody has read aloud is untested.

---

## 7. Module 1 → later modules: inherited obligations

**RESOLVED by Module 2:** `ownership.js` is now wired up and enforced, `ownerScopedFilter` throws
on missing identity, and `allowRoles` denies by default. See §6a.

Still standing:

- Preserve `assertCanAccess`'s **404-before-403** behaviour so a non-owner cannot probe
  whether another patient's record exists. Module 3 verified this holds for addressable ids.
- Keep passing no `allowRoles` grant for any medical resource. `OWNER_ONLY` is exported and
  spread at call sites as intent-declaring belt-and-braces (now identical to the default).
- `express-mongo-sanitize` works on Express 4 but **is incompatible with Express 5** — a pin
  to remember on any future upgrade.

---

## 8. Module 4 output contract (BINDING)

Module 5 consumes this, so it is fixed. `POST /api/v1/ocr/extract` (multipart) returns
`{ success, data: { source, raw_text, pages[], extracted_parameters[], report_metadata,
extraction_confidence, warnings[] } }`, where each extracted parameter is:

```json
{ "test_name": "HbA1c", "value_raw": "6.8", "value_numeric": 6.8, "unit": "%",
  "reference_range_raw": "4.0 - 5.6", "reference_low": 4.0, "reference_high": 5.6,
  "flag": "high", "page_number": 1, "confidence": 0.94 }
```

**Contract rules:**

- `test_name` is **exactly as printed on the report**. Module 4 does **not** normalise;
  canonical mapping (`HbA1c` / `Hb A1c` / `Glycated Hemoglobin` → `hba1c`) is **Module 5's job**.
- `value_numeric` is `null` for non-numeric results ("Negative", "Trace"); `value_raw` always
  preserves what was printed.
- `flag` is `low|normal|high|critical|null`, set **only** when the report says so or the
  reference range makes it unambiguous. **No clinical inference at the OCR stage.**
- Everything except `test_name` and `value_raw` is nullable. **Missing information must be
  `null`, never invented.**
- Module 4's tests must pass **with no API key and no network** (Gemini mocked), with an
  opt-in live test for real-integration confirmation.

---

## 9. Conventions any new module must follow

- **CommonJS** in `backend/`; match the existing file layout and naming.
- Response shapes: `{ success: true, data }` and `{ success: false, error: { code, message } }`.
- Use the existing `asyncHandler`, `ApiError`, `apiResponse`, and `validate` middleware.
  Do not introduce a second way to do something that already has one.
- **Every validator chain starts with `.isString().bail()`** (or the matching type guard)
  before any sanitizer. This is not style — a missing one caused a live authentication
  bypass. **Never let an untyped value reach a Mongo query.**
- Never log file contents, raw report text, medical values, or secrets.
- Never echo unsanitized user input back in error messages.
- New modules must not modify Module 1 auth logic, and **all existing tests must keep passing.**
---

## 10. Suggested next steps

In the order that gives the most value:

0. ~~Apply the D7 fix.~~ **DONE 2026-09-04**, with a regression test that fails against
   the old code (§6n D7). Still worth watching `/health` during a real Gemini extraction
   the next time quota allows — the proof used a synthetic 3s block, not a real 190s one.
1. ~~Write tests for Modules 27-32.~~ **DONE 2026-09-04/05 — +911 tests (§6o).** They
   found a real patient-safety defect (D8) on their first run.
2. ~~Audit Modules 27-32.~~ **DONE 2026-09-05 (§6p).** Three independent auditors found
   **17 defects** in code that had 911 tests and a fully green suite. All 17 are fixed.
   The finding worth carrying forward is one auditor's summary of the test suite's shape:
   *"the branch that refuses is tested, the branch that answers on thin evidence is not."*
3. ~~Decide the Module 5 reference-range unit bug.~~ **FIXED at source 2026-09-04
   (§6n D1).** The interval is now converted with the value; Modules 29/32 short-circuit
   on `provenance.reference_converted` so nothing double-converts.
4. ~~A frontend.~~ **DONE 2026-09-05 (§6q).** Still worth doing on top of it: a real
   end-to-end pass through the browser against a live analysis (the contract was verified
   against a running backend, but no browser has driven a full upload-to-dashboard flow),
   and an accessibility review — this is a medical tool and none has been done.
5. ~~Audit Modules 21-26 as a group.~~ **DONE 2026-09-05 — TWO FAIL VERDICTS (§6r).**
   **THE FIXES ARE THE TOP PRIORITY OF THE NEXT SESSION**, in this order:

   a. **Modules 23/24, 14 defects (§6r).** Start with the positive-control gap: a diagnosis
      stated as flat fact reaches the patient, and `RULES` has 13 rules with
      `positive_control=True` on **none** of them. Then `_GAP` (one adverb defeats every
      multi-word rule), then `_compacted_pass` discarding REDACTABLE findings (15/15
      invisible characters miss), then `MISSING_PROFESSIONAL_REFERRAL` substring
      satisfaction — which §6k D1 named and never actually fixed.
   b. **Module 21's D1**: route `retrieve_payload` through `_anchor_free_text`, or delete the
      unanchored path. Then correct the two false claims the endpoint publishes about itself.
   c. **RE-RUN THE MODULES 25/26 AUDIT.** It never completed.
   d. **Reconcile the three safety scanners.** This is no longer tidiness — §6r has 12
      measured rows where they disagree, including a drug name the corpus scanners catch and
      Module 24 approves.

   Two lessons worth carrying into the fixes themselves: **a fix verified once by its own
   author is not done** (three of §6k's eight did not survive re-attack), and the suite's
   shape is *"the branch that refuses is tested, the branch that answers on thin evidence is
   not"* — so every fix needs a test on the ANSWERING branch.
6. **Reconcile the three safety scanners** into one rule table (see 6k, D5).
7. **One measured data gap left** (the other was re-measured and shrank):
   - ~~adding systolic BP to Module 2 is worth ~0.10 ROC-AUC to Module 11~~ **FALSE.**
     Re-measured on NHANES: **+0.0066**. See §6s. Not a priority.
   - adding `blood_urea` and `albumin` to `feature_catalog.py` is the biggest available
     win for Module 12, which can currently use only 5 of the CKD dataset's 24 attributes.
   - **NEW — compute eGFR instead of learning it.** CKD-EPI is a deterministic function of
     creatinine, age and gender, all three of which VaidyaAI already has. Verified against
     an NHANES CKD set: recomputing CKD-EPI from those columns reproduces the published
     eGFR at correlation **1.00000**, median difference **0.00 mL/min**. Any ML model of
     eGFR<60 is re-deriving a formula — that is why such a model scores 0.9995 and why the
     score is meaningless. If Module 12 wants staging, put the formula in the rule engine.
8. **Add a liver-enzyme KB document** so Module 25 stops refusing SGPT, which the spec names.
9. **A background job queue for `analyze`.** It still blocks on a slow LLM round trip.
   Extraction worst case is bounded but large; the explanation stage is now parallel but
   still synchronous.

## 11. Things that recur — worth knowing before editing

- **Absence must never become a value.** Tri-state booleans (true / false / absent-unknown),
  `INSUFFICIENT_DATA` may not carry a risk, `RiskLevel.highest([])` returns None not LOW,
  Module 18 will not say Healthy when nothing was assessed, and Module 7's `ABSENT`
  sentinel raises on every implicit coercion. This is the single most repeated hazard here.
- **Guarantees belong at the lowest layer.** A validator-only password cap, a call-site-only
  ownership flag and a pattern-only safety control all failed the same way; each was fixed
  by moving the check to where it cannot be bypassed.
- **A comment asserting a guarantee is not a guarantee.** Three separate audits found false
  claims in comments on this project, two of them written by the assistant.
- **Build-agent self-reports are not evidence.** Independent audits repeatedly found live
  holes behind a fully green suite — including a critical one Module 10 had already
  passed.
