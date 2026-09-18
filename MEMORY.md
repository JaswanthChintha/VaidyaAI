# VaidyaAI — Project Memory

> Living context file for the VaidyaAI build. Keep this in the project folder so the
> project's history, decisions, and state survive independently of any chat session.
>
> **Last updated:** 2026-09-18 (§6aw) · **All 32 modules + frontend built, plus 33, 34, 35 and 36**
>
> The build history is §1–§6w. The recent design and safety work is:
> the "Instrument" design system (§6x) · the timeline trend chart (§6z) · five
> patient-facing screens reworked on a reader's objections (§6aa–§6af) · the
> clinician summary WRITTEN BY GEMINI behind four gates (§6ag) · a report
> picker for the comparison (§6ah) · and a third session of design, WCAG AA
> and internal-vocabulary work (§6aj–§6ao).
>
> **⚠ READ §6aw FIRST, THEN §6av, THEN §6au.** Those are the current
> handovers. §6aw is the newest: Module 36 (test-name joining), a hand-written
> variation table that takes precedence over the model, a zero-change defect
> in the SHARED significance test, and the comparison card brought to the same
> coverage as the timeline. §6av documents Module 35 and supersedes §6au's
> conclusion that improving/worsening/stable could not be produced for an
> unassessed test. §6at is the long one and still holds except where the later
> sections correct it. §6as is older again and its test counts are off by 7.
>
> The line that stood here — "nothing since `6dc3409` is committed, 45 files,
> three sessions deep, read §6ap first" — **is history.** Everything is
> committed and the tree is clean. §6ap and §6ai are stale handovers and §6ap
> opens with that same uncommitted-work warning; do not act on it.

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
| `backend/` (Node/Express) | **762** passing + 3 skipped (15 suites, 0 failed) |
| `ai-service/` (Python/FastAPI) | **4,022** passing + 7 skipped (4,029 collected, 0 failures, 0 errors) |
| `frontend/` (React/Vitest) | **384** passing, 0 suites failed |
| **Total** | **5,168** -- ALL THREE green 2026-09-18 |

> **⚠ THE 4,852 IN EVERY EARLIER SECTION WAS 7 TOO HIGH.** §6as recorded
> ai-service's COLLECTED total (3,865) as its PASSED count; that day's real
> figure was 3,858 passed + 7 skipped. The row above is a true count, taken
> from the junit XML. See §6at.

> ### ✅ EVERYTHING IS COMMITTED AND PUSHED. TREE CLEAN, ONE BRANCH
>
> Verified 2026-09-18: `main` == `origin/main` at **`351b693`**, working tree
> clean, `origin/main` the only remote branch. **The 14-path uncommitted
> warning that stood here for two sessions is history.**
>
> **SIX COMMITS ON 2026-09-18**, newest first — the whole of §6av and §6aw:
>
> ```
> 351b693  docs: the stored bounds are repaired, and the gate was the judge
> 6b60a8d  the printed range must be only a range
> e15c184  a silent unit is not a different one -- and one change is not two verdicts
> a865f75  two labels for one scale, declared where a reviewer can read it
> f772bc0  one unit spelled two ways is one unit
> 5142acd  two names for one test, and a threshold you can go and check
> 0c4930d  the model says which way is worse; this service decides whether it moved
> ```
>
> **Verified at `351b693`, all three suites, nothing taken on trust:** backend
> **762** + 3 skipped (15 suites, 0 failed), ai-service **4,022** + 7 skipped
> (4,029 collected, 0 failures, 0 errors), frontend **384** (0 suites failed,
> no file reporting zero assertions). **5,168.**
>
> **NOTHING CARRIES A CO-AUTHOR TRAILER.** Checked by grep on every commit.
> Do not add one.
>
> **STILL DO `git status` FIRST IN A NEW SESSION.** It cost this project a
> whole session's work being one bad `git checkout` away from gone, and the
> habit is the only reason it wasn't.

> ### ▶ WHAT TO DO NEXT, IN ORDER
>
> All four are named in §6aw's KNOWN AND OPEN with the evidence.
>
> 1. **VERIFY THE VARIATION TABLE.** `ai-service/app/data/lab_variation.py`,
>    16 rows, **every one `verified: false`** — literature-typical CVa/CVi
>    recorded with the source to check them against, never read off it. Every
>    `stable` on the timeline rests on these. `test_no_row_claims_to_be_verified`
>    fails loudly if a row is flipped without someone doing the comparison.
>    Take **ESR** (the 62 % threshold that makes `ESR 35 -> 45` read `stable`),
>    then **EOSINOPHILS**, then **BASOPHILS** — each says so in its own
>    `source` field.
> 2. **VERIFY THE TWO UNIT EQUIVALENCES.** `U/L == IU/L` globally, and
>    `g/dL == %` for MCHC only, in
>    `backend/src/services/unitEquivalence.js`. Both `verified: false`.
>    `SGPT 101.9 -> 13 improving` rests entirely on the first.
> 3. **DECIDE eAG's `flag: "normal"`.** The last piece of the interpretation-band
>    defect. Almost certainly inferred against the band now refused, but it
>    cannot be told from a genuine printed marking by looking at the stored
>    row, so the panel still shows `In range` for 154 mg/dL. **Open Test 3 and
>    look at whether that row carries its own H/L marking.**
> 4. **READ THE CLINICIAN PAGE ALOUD.** Every screen-reading session on this
>    project has found something no suite did — eight times now. The timeline
>    and comparison cards were read this session; the clinician page was not.

> ### ▶ RUN AND TEST, IN ONE PLACE
>
> ```
> cd ai-service && .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
> cd backend   && npm start        # :5000, Mongo Atlas, non-SRV URI
> cd frontend  && npm run dev      # :5173
> ```
>
> * **Frontend is `http://localhost:5173`, NOT `127.0.0.1:5173`** — Vite binds
>   `::1` only.
> * **`curl http://127.0.0.1:5000/api/v1/health`** before believing anything;
>   it reports `database` and `aiService.reachable`.
> * **RESTART backend/ai-service after changing them, and restart BEFORE
>   believing the browser.** A background task reporting "exit 127" usually
>   means the wrapper died while the server is still serving —
>   `Get-NetTCPConnection -LocalPort 5000` then `Stop-Process`.
> * **⚠ HISTORY ENDPOINTS ALLOW 60 REQUESTS PER 15 MINUTES.** Repeated reloads
>   while checking a render exhaust it and the page goes blank with `429`,
>   which looks exactly like a broken feature. The limiter is in-memory, so
>   **restarting the backend clears it** — faster than waiting.
>
> ```
> backend      npm test                      # or: npx jest --json --outputFile=<f>
> frontend     npx vitest run --reporter=json --outputFile=<f>      FROM frontend/
> ai-service   pytest --junitxml=<f>         ONLY passes with ai-service/.env moved aside
> ```
>
> **Read `numFailedTestSuites` and PER-FILE assertion counts, never the failure
> line** — a file that fails to compile reports zero failures. pytest's summary
> does not survive to tail; parse the junit XML. Vitest's JSON reporter is the
> reliable one.


> ### ▶ NEW CHAT? START AT §6aw, THEN §6av, THEN §6au.
>
> **§6aw is the current handover and it is long because the reader drove two
> real screens for a whole session.** Read its opening list and its KNOWN AND
> OPEN block first; the rest is evidence for those.
>
> Between them they have the run commands, the state of the repository, what
> `Test 2.pdf` and `Test 3.pdf` are and why they matter, and what is open.
> **§6at opens with a ten-line list of what that session did and a KNOWN AND
> OPEN list naming four things it raised and did NOT fix.** Read those two
> blocks before anything else in it — the section is long because the reader
> drove the real pages for a whole session, not because it all matters equally.
>
> **⚠ GEMINI WAS EXHAUSTED ON 2026-09-16.** All three models in the chain hit
> their daily limits. Every refusal path renders nothing, which is designed
> behaviour and looks exactly like a bug — check the ai-service log before
> concluding anything is broken.
> **NO DECISION IS WAITING. §6as's two open questions were BOTH defects, and
> both were framed as decisions because nobody had probed them.** The
> six-finding ceiling was already dropping a raised CRP on Test 3; the certainty
> gate's `indicate` gap was a plural subject evading the gate in every verb,
> seven of seven flat assertions passing. §6at is both, with the measurements.
>
> **THE TRANSFERABLE PART: a "wording decision" in a handover is a claim about
> a gate that someone described without running.** Probe it first — both probes
> took two minutes and both said something other than what was written down.
>
> **§6at is verified live on BOTH real reports, through the real page to
> Mongo** — Test 3's seven findings with the CRP that was being dropped, and
> Test 2's twelve, six of which had never been described on any report. 19
> descriptions, 19 Module 24 approvals, zero gate refusals, zero skipped.
> Nothing on Module 34's ceiling is outstanding.
>
> **§6ap and §6ai are PREVIOUS handovers and both are stale in the way that
> matters most: §6ap opens with "45 files uncommitted, no recovery point", and
> that is history.** Everything is committed and pushed; the tree is clean.
>
> **THE REPOSITORY IS ONE BRANCH NOW.** `origin/main` and `origin/master` were
> two UNRELATED histories — separate roots, no merge base — with the real work
> on `master` and a squashed snapshot on GitHub's default. They were
> consolidated onto `main`, and the commit messages were then rewritten to
> carry no co-author trailer. **Nothing carries one; do not add one.**
>
> All 4,934 tests pass and all three suites ran 2026-09-16. §6x is the design
> system; §6z–§6ah and §6aj–§6ao are the earlier sessions; **§6aq, §6ar, §6as
> and §6at are the recent ones** — two real laboratory reports driven through
> the app, the three lookup defects they exposed (a parenthetical, a
> misspelling and a unit spelled out in words), Modules 33 and 34, a page
> stripped of its own commentary, every parameter finally described, and
> **Module 34's ceiling caught silently dropping a finding (§6at)**.
>
> **§6ar carries the runner fault worth reading before you trust any suite
> here:** a frontend run reported 288 passed / 0 failed when a whole file had
> failed to compile and its 32 tests did not exist.

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

* ~~The range chart and the results table both show every value... If that
  reads as duplication on a real screen it is a one-line change, but it is
  deliberate.~~ **IT READ AS DUPLICATION, to the person the screen is for.
  CLOSED 2026-09-11 — see §6ab.** The chart is drawn only when at least one row
  carries a real reference interval; on a report that prints none, the panel
  does not appear at all. The table is unchanged and remains the record.
* ~~`design.md` §4 lists a `/timeline` trend chart in the range chart's
  vocabulary.~~ **BUILT 2026-09-11 — see §6z.**

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

## 6y. STATE AFTER THE FIRST 2026-09-11 SESSION — **SUPERSEDED BY §6ai**

> Its uncommitted list was never committed and is still in the working tree,
> underneath this session's. The run commands and the test account here are
> still correct; §6ai has the current state.

**Everything runs. Everything is green. Nothing after commit `e175eb7` is
committed.**

### Suites, counted by running them

| | |
|---|---|
| `backend/` | **636** passing + 3 opt-in live |
| `ai-service/` | **3,765** passing + 7 skipped |
| `frontend/` | **213** passing |
| **Total** | **4,614** |

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
2. ~~**`design.md` §4 wants a timeline trend chart.**~~ **BUILT 2026-09-11 —
   see §6z.** `components/TrendChart.jsx`, wired into the Trends section of
   `/timeline` only; the rest of that page is untouched, by design.
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

## 6z. The timeline trend chart · 2026-09-11 · `design.md` §4 closed

`components/TrendChart.jsx`, wired into the Trends section of `/timeline` and
nowhere else — the comparison and progress sections were deliberately left
alone. Hand-authored SVG, already-derived props, **no threshold, polarity,
condition or stability band inside it**, same contract as `RangeChart` and
`CoverageRadar`. Frontend suite **111 → 147**.

### THE FOUR STATES, WHICH ARE THE ENTIRE POINT

A flat line and "we have no data" look identical if you let them. Module 28's
payload already keeps these apart, and the chart's only job is not to collapse
them:

| Situation | Drawn as | The thing it must not be |
|---|---|---|
| >=2 readings, `TREND_CLASSIFIED` | solid line, direction colour | — |
| **<2 readings** (`INSUFFICIENT_DATA`) | **no line at all**; one dot + a sentence | a flat line, or the word "stable" |
| **a gap** | the line **BREAKS**; dashed unfilled marker in a lane *below the axis* | a line drawn through a period nobody measured |
| **a rejected reading** | same lane, `NOT USABLE` + the service's reason | a plotted value — a rejected 999 is not a high result |
| >=2 readings, any other outcome | line in neutral ink, no trend word | a risk colour the service did not classify |

A gap has **no y position** and is never given one: `TimelineGap` structurally
has no `value` field, and the lane sits outside the plot so the rendering
cannot quietly invent one.

### TWO RULES THE CHART DECIDES ITSELF, AND THEY ARE PRESENTATION

Both are the same class as the range chart's display domain, and both are
documented as such in the file:

* **Readings in two units are never placed on one axis** — and withholding
  only the LINE is not enough. Two dots positioned by one shared scale make
  the comparison just as firmly; 7.2 mmol/L would sit at the floor and
  100 mg/dL at the ceiling, which reads as a collapse and is the same
  measurement twice. So mixed units render no plot at all, and say why.
* **Every number printed on the chart is a reading somebody took.** Labelling
  the axis with the *domain* printed the padding: readings of 8.4 and 5.2 came
  out as "8.78" and "4.82" — two numbers that appear on a medical chart, look
  like measurements, and are neither. The labels are now the highest and
  lowest actual readings, at their own heights, deduplicated so a flat line
  prints its one value once rather than twice or never.

### FOUR THINGS FOUND BY RUNNING IT, NOT BY READING IT

A second fixture (`01-all-normal.pdf`) was uploaded and analysed against real
Gemini so that a real two-report timeline existed. All four of these came from
the live payload or the rendered page; the suite was green throughout.

1. **`age` arrives `NOT_TRENDABLE` with two perfectly good points** — and on
   the live data those are 58 and 34, because the two synthetic fixtures carry
   different patients. Charted, that is a person getting 24 years younger,
   drawn beside a sentence refusing to describe a trend. **A picture that
   disagrees with the words next to it is the thing these components exist to
   prevent.** The page now skips `NOT_TRENDABLE` / `NOT_NUMERIC` outright.
2. **`gender` is the same shape from the other end** — `NOT_NUMERIC`, zero
   readings, two gaps. That rendered an axis with nothing on it. A chart needs
   at least one real reading; the table row beside it already carries the
   service's own refusal sentence.
3. **`186 mg/dl` rendered as `16 mg/dl`.** The y-axis label is right-anchored
   8 units left of the plot, and adding the unit pushed it off the viewBox.
   **A clipped axis label does not look broken — it looks like a smaller
   number.** This is §6x's `"olesterol"` defect recurring, and the fix is the
   same one: pad the frame, move no geometry. Now guarded by a test on the
   gutter width, and verified in-page with `getBBox()` across all 35 labels.
4. **`vitamin_b12` declares `optimal_low: 200` and no ceiling.** A one-sided
   optimum drawn as a band runs to the top of the frame and asserts a ceiling
   nobody declared. The both-ends rule fires on live data, not just in a test.

### MUTATION-TESTED: 17 GUARDS FLIPPED, 17 KILLED A TEST

Run as a script: apply the mutation, run the two files, revert. **Four
survived the first pass**, and each named a missing test rather than a
harmless guard:

* `classified && trend === 'worsening'` — dropping `classified` SURVIVED,
  because every fixture with no classification also had `trend: null`, so the
  second clause was false anyway. **Two conditions need two tests**, the
  §6w `counted && !compared` lesson hit again. The distinguishing shape is a
  payload where `classified` and `trend` CONTRADICT each other.
* Testing that shape exposed a real defect: **`classified: true` with
  `trend: null` rendered the string "null" as the direction** in the chart's
  own aria-label. Now one `declared` flag checks both halves — the same shape
  as the gauge's `assessed && known risk` — and absence wins the contradiction.
* Two page-level mutations survived because the component enforces the same
  rule underneath. One had a distinguishing shape (a non-classified outcome
  carrying a trend word) and got a test. The other — the band's both-ends
  rule, copied into the page — had none, because it changed nothing
  observable. **That is exactly what a comment pretending to be a guarantee
  looks like**, so the duplicate was deleted and the rule now lives in one
  place, at the layer that cannot be bypassed.

### Also

* `PATIENT_LABEL` moved out of `Dashboard.jsx` into **`src/lib/labels.js`**.
  Nine chart headings name the same features the dashboard names, and a second
  copy of that table is how one of them ends up saying `blood_glucose` to a
  patient. It is still table-row/subject wording and still wrong mid-sentence
  — `readableFeature`'s split (§6w) is unchanged.
* The in-page palette sweep was re-run over the new elements: **zero colour
  offenders, exactly two font families, both themes.** Reduced-motion rest
  state checked the same way — the line rests at `stroke-dashoffset: 0`, fully
  drawn, because `pathLength="1"` makes the drawn state the default rather
  than the end of a keyframe.
* `improving` takes `--green`, matching the page's existing `.trend--improving`
  rule. Worth knowing that this stretches green from "in range" to "in range or
  moving favourably": **a green line does NOT mean the values are normal.** It
  is paired with the word "improving" in the title and the table, so colour is
  never the only signal — but if that reading ever bites, this is where it is.

### NOT VERIFIED LIVE

**The gap and rejected paths were never produced by real data.** All six
single-page fixtures carry the same eight mapped tests, so no report is
missing a parameter and nothing was rejected — `history` came back
`considered: 2, included: 2, excludedCount: 0`, with gaps only on `gender`.
Those two paths were exercised by patching the response at the transport layer
in a live browser (the line breaks into 0 paths, two dashed markers sit below
the axis at `cy=166`, and `NO READING` / `NOT USABLE` are distinguished with
their own reasons) — a real render of synthetic data, which is not the same as
a real report missing a real parameter. **A fixture with a parameter absent
from one report would close this**, and it would be the first fixture on this
project able to exercise a timeline gap at all.


---

## 6aa. The condition card, read aloud again · 2026-09-11 · two sentences cut

The user looked at the Heart Disease card and said: *"make sure visible only
required sentences which are understandable for users."* The card carried four
sentences under its values. Two went.

### CUT: the basis-conflict paragraph — **the SECOND removal of this shape**

> *"Two checks were made and they did not agree. One counts risk factors from
> your profile; the other is a statistical estimate. They answer different
> questions, so neither settles the other — this is worth raising with a
> doctor."*

§6w removed the paragraph explaining that "Needs Monitoring" and "risk Low"
do not contradict each other, on this user's own instruction — *"why this for
a patient"* — and recorded the generalisation: **when a screen needs a
paragraph explaining why two of its own fields do not contradict each other,
the fields are the bug, not the missing paragraph.** A risk-factor tally
versus a model probability is that same paragraph, on a different card, and it
survived that pass because nobody read this card aloud.

A patient cannot adjudicate between the two; the decision engine already did,
and the fused verdict is what the card shows. The sentence ended on "worth
raising with a doctor", which the status line above it says already.

**Nothing is hidden.** `basisConflict` and `basisNote` stay in the payload, and
the clinician passage still states which kind of check flagged what —
including the model-only case, which is the one a reader can genuinely be
misled by (§6w, "Four things kept", item 1). `shouldShowBasisNote` was deleted
rather than left as an unreachable branch; its reasoning is preserved as a
comment where it stood, because it was good reasoning (`basisConflict` does not
mean "they disagreed", and the test was "can we PROVE they agreed", never "did
they disagree" — missing per-source verdicts are not agreement).

### CONDITIONALLY CUT: "Checked against standard clinical thresholds..."

Above a row reading `268 mg/dl — above 240 mg/dl`, that sentence is the screen
narrating its own mechanics. §6u removed *"Based on: Clinical Rule Engine,
Random Forest"* from this very card for exactly that reason, and this is the
same sentence in friendlier words.

**But it could not go unconditionally, and the live page is why.** On the
analysed report:

```
High Cholesterol  268 mg/dl  above 240 mg/dl        -> no sentence. The row IS the explanation.
Kidney Disease    1.1 mg/dl  (crosses nothing)      -> sentence KEPT.
```

Creatinine 1.1 does not cross the kidney threshold; the topic is flagged
anyway. Strip the sentence there and a patient sees a normal-looking value
under a **High** verdict with nothing on the card connecting them — a verdict
with no reason, which is a thing to be believed or not. So it is stated exactly
where the card does not already explain itself, and nowhere else.

### KEPT, both of them

* *"No value was available for your history of heart disease and history of
  high blood pressure, so they could not be taken into account here."* — the
  §6w fix. The heart model's own author note says blood pressure is the
  strongest known predictor and is not collected here; dropping this hides the
  assessment's single biggest limitation.
* *"Your smoking history, BMI, age and sex were also taken into account."* —
  plain English, one line, and the other half of the sentence above it. Keeping
  only the absence would make the assessment look thinner than it was; keeping
  only this was the original §6w defect.

### THE GATE WAS WRONG ON ITS FIRST WRITING, AND A MUTATION SAID SO

First version: `card.flagged === true && !measured.some(crossing)`. The
`flagged` clause **survived mutation**, and chasing why found two faults:

1. **It is unreachable.** `ConditionCard` renders only for the flagged group,
   so the clause can never be false — an unkillable mutation, and the test
   written for it passed **without asserting anything**. A vacuous green is
   worse than no test, and this file has a whole catalogue of them.
2. **It was also incorrect.** `isClear` requires the exact status
   `Not Indicated`, so a **`Borderline`** topic lands in the flagged group with
   `flagged` NOT true. Gating on it would have stripped the explanation from
   precisely the cards least able to speak for themselves.

Now `!measured.some(crossing)` alone, with the caller's guarantee named in a
comment at the point that relies on it. Seven mutations run over the final
version, **7 killed** — including putting the lecture back, and cutting the
methodology line unconditionally.


### THEN: what the three ML models actually contributed, and the sentence it earned

The user asked whether the Diabetes, Heart and Kidney models were included in
the result. They are — those three topics are hybrid, the other ten on this
report are rule-only — but "included" means something different in each, and
the per-source verdicts are the thing worth keeping:

| Topic | Clinical Rule Engine | Random Forest | Shown |
|---|---|---|---|
| Diabetes | Indicated / High | Indicated / High (p 0.95) | High — both agree |
| Heart Disease | Indicated / High (`risk_factor_count`) | **Not Indicated / Low** (p 0.46) | High — **the rule's verdict; the model said no** |
| Kidney Disease | **Not Indicated / Low** (creatinine 1.1, in range) | Indicated / High (p 0.70) | High — **the model's verdict; nothing crossed** |

So Heart Disease is the `basisConflict: true` card, and **Kidney is its mirror
image**: a normal-looking number under a serious word, with nothing on the card
joining them. Cutting the generic methods line above had left that card saying
only "Checked against standard clinical thresholds, and also assessed by a
statistical model" — true, and it does not tell the reader that the threshold
check came back CLEAR and the model is the entire reason the topic is there.

`flaggedByModelAlone()` now states it, in the model author's own framing
(§6w: *"a high score is a reason to discuss testing with a clinician, never a
finding"*), and REPLACES the generic line rather than joining it:

> *"No measured value crossed a standard limit for this. It was flagged by a
> statistical model that compares your results with patterns in population
> data — that is a reason to discuss it with a doctor, not a finding in
> itself."*

**PROOF IN BOTH DIRECTIONS, OR SILENCE.** It never infers "nothing crossed"
from the absence of a crossing on screen — that is a clinical claim and the
render layer does not get to make it. It reads the producer's own per-source
verdicts and stays silent unless both are present AND assessed. A finding is an
explicit status (`Indicated` / `Borderline`), never "not `Not Indicated`", so
`Insufficient Data` and any unrecognised status cannot become one.

Nine mutations, **9 killed** — two only after the first pass exposed missing
tests: a card carrying only ONE of the two sources (which also read
`undefined.status` and would have taken the page down), and a source marked
`assessed: false` whose `Not Indicated` is a check that did not run, not a
check that came back clear.

### A THIRD STATUS VOCABULARY, because the headline then contradicted the fix

Reading the fixed card caught it immediately: the headline still said *"These
results point to this"* directly above *"No measured value crossed a standard
limit for this."* "These results point to this" describes a comparison of
measured values, and no comparison found anything here. That is the identical
shape as §6w's *"Close to the usual limit"* printed above two values that were
over it — the fault `RISK_FACTOR_STATUS` was created to fix, appearing in a
third basis. **The contradiction was always latent on this card; the new
sentence is what made it visible.**

So `MODEL_STATUS` joins `PATIENT_STATUS` and `RISK_FACTOR_STATUS`:

```
Kidney Disease                                            High
A statistical model flagged this — worth discussing with a doctor
Creatinine (kidney marker)   1.1 mg/dl
No value was available for your history of high blood pressure, ...
Your Haemoglobin, Blood sugar and age were also taken into account.
No measured value crossed a standard limit for this. The model compares your
results with patterns in population data — it cannot confirm a condition.
```

**Only the two statuses that differ are defined**; `statusText` falls back to
`PATIENT_STATUS` for the rest, so the three lines all three tables would
otherwise hold identically cannot drift apart in three places. And the caveat
was rewritten once the headline carried the attribution — the first version
said "flagged by a statistical model" and "a reason to discuss it with a
doctor" immediately below a headline saying both, which is §6w's repetition
defect arriving by the back door.

**THE MODEL BASIS OUTRANKS THE RISK-FACTOR BASIS, and that ordering needed its
own test.** A rule that counts risk factors and finds NONE returns
`Not Indicated` with no threshold comparison anywhere — so `countsRiskFactors`
and `flaggedByModelAlone` are true at the same time, and taking the
risk-factor wording there would announce "several things here are known to
raise this risk" about a count that came back empty. Whichever analysis
actually produced the verdict names it.

Six mutations on the wording, **6 killed** — including reversing that
precedence.

### Two more things the rendered page said out loud

* **`|| status` had no test.** Mutating the final fallback into a guessed gloss
  survived everything: an unrecognised status would have been described as
  "These results point to this". That is §6w's rule (*a missing gloss is
  cosmetic, a wrong one is clinical*) with no assertion behind it, and three
  tables now share the fallback. Tested.
* **"Your BMI were also taken into account."** Read off the live Obesity card,
  which cites exactly one feature. The sentence directly above it already
  switches `it`/`they` on the same count; this one never learned to.

> The habit that found all of this is the same one as the last three sessions:
> **a screen nobody has read aloud is untested.** The suite was green before
> and after; the user reading one card is what moved it.


---

## 6ab. The range chart, on a report that prints no intervals · 2026-09-11

The user looked at the range chart on the live dashboard: *"in this all are at
same, only colour difference, and i can't see any shaded band — and also
remove the sentence 'this report printed no reference intervals'."*

All three observations are the same defect.

### EIGHT ROWS, EIGHT DOTS, ALL IN THE SAME PLACE

`domainFor` builds a per-row display domain from `[low, high, value]` and pads
it to `ceiling * 1.35`. With no printed interval, the only number in that list
is the value itself — so **every row's marker lands at exactly 1/1.35 = 74% of
its own track, whatever the value is.** HbA1c 8.4, glucose 186, cholesterol
268: three identical positions, separated only by colour.

That is not a weak chart. It is **a picture that looks like a measurement and
encodes nothing**, under a panel titled *"Where each result sits against its
reference range"* on a report with no reference ranges in it, above a legend
(`SHADED BAND = USUAL RANGE`) pointing at a band that is not on screen. A
reader comparing two dots is reading an artefact of a multiplication.

### THE FIX IS NOT TO REMOVE THE SENTENCE

The sentence the user asked to delete — *"This report printed no reference
intervals, so no result below is placed against a usual range"* — was doing
real work: §6x added it because eleven bandless tracks with nothing explaining
them read as "everything is in range". Deleting only the sentence leaves the
meaningless picture AND removes its only caveat, which is strictly worse than
before.

**So the chart itself goes, on a report where nothing can be compared**, and
the sentence goes with it because there is no longer anything to explain.
`hasComparableRange(rows)` is exported from `RangeChart` and used by BOTH the
component (the layer that cannot be bypassed) and `Dashboard` (which must not
draw the bordered panel around a chart that has decided to render nothing —
otherwise the result is an empty box with a heading). One rule, one definition,
two callers — not two copies, which is the trap this session already hit twice.

**NOTHING IS LOST, and this was checked against the live DOM before the change,
not assumed.** The results table below carries every value with its verdict
(`High` / `In range`), the laboratory's own printed name, and all three
absences with their reasons under "From your profile". The lab-flagged footnote
the chart used to carry is separately stated by the "Also on your report, but
not assessed here" section. Verified after the change: no `.range` panel, no
empty card, and "laboratory marked ..." still on the page.

This closes §6x's own open question, in §6x's own words: *"If that reads as
duplication on a real screen it is a one-line change, but it is deliberate."*
It read as duplication, to the person the screen is for.

### Mutation-tested, and the two that survived the first pass

Four mutations, all four killed after the gaps were closed:

* drawing the chart with no comparable range — killed;
* refusing it when a band DOES exist — killed (9 tests);
* **`low && high` weakened to `low || high`** — survived. A one-sided interval
  draws no band (`hasBand` needs both), so a chart admitted on the strength of
  one is a chart with no bands in it: the refused state reached sideways. Real
  gap, now tested — and the same both-ends rule the trend chart needed (§6z).
* **the page-level guard removed** — survived, because nothing asserted that
  the empty bordered panel does not render. The component returning null is not
  the same as the section not existing. Now tested on the page.

Five existing single-row chart tests were rewritten to place their row NEXT TO
a banded one rather than alone. That is not a concession to the new rule — it
is the only arrangement in which a reader ever sees those rows, so the tests
describe the product more accurately than they did before.


---

## 6ac. The coverage radar said the opposite of its own title · 2026-09-11

The user asked what the radar panel meant. Answering it against the live DOM
found three defects, one of them serious.

### THE SERIOUS ONE: the radius was the VERDICT, under the word "Coverage"

```js
coverage: isUnassessed(card) ? 0 : isClear(card) ? 0.55 : 0.95
```

A flagged topic sat at the rim, a clear one well inside it. So **the more
topics a report flagged, the fuller and more reassuring the pentagon looked**,
under a panel titled *"Coverage of the topics checked"* and a caption about
things not being measured. A big shape reads as thorough; here it meant
"everything on this chart is abnormal". The code comment even said *"Coverage
is how much of this topic the report could speak to"* — which is not what
`isClear ? 0.55 : 0.95` computes. **A comment asserting a guarantee is not a
guarantee**, for the fourth time in this file.

It now measures what the title says: **of the inputs each assessment cites,
how many the report actually carried**, from the evidence lines'
`availability`. On the live report that is Diabetes 5 of 8, Heart 5 of 8,
Kidney 4 of 5, Cholesterol 1 of 1, Triglycerides 1 of 1 — an irregular shape
that finally says something, and says the flagged multi-input topics were
assessed on partial information, which is the one question the condition cards
below do NOT answer.

Two absence rules in the derivation:

* **an unassessed topic keeps its spoke** and its dashed point at zero — that
  is the chart's entire reason for existing;
* **an assessed topic whose coverage cannot be computed is left OFF** rather
  than given a radius. There is no number for "we do not know how much we saw".

And **a feature counts once, however many rules cite it**, available if ANY
line observed it — double-counting would inflate exactly the topics that have
several rules, and "first line wins" made it an accident of ordering.

### The two smaller ones

* **`.glycerides`.** Measured, not guessed: the label box started at x=-74.1
  against a viewBox starting at -56. §6x widened this frame once for
  `"olesterol"` on the RIGHT; the left was still too narrow for the longest
  name. Now -104, with a test on the gutter.
  **Widening a frame is only half the fix**: the element was still
  `width="278"`, so the whole chart rendered scaled DOWN to fit the gutter
  inside it — the pentagon shrinks every time a label needs more room. The
  element now matches the frame and `max-width: 100%` keeps it in the panel.
* **A caption for a mark that was not on the chart.** "A dotted point sits at
  zero because nothing was measured" sat under a chart whose own title said
  *"All 5 topics were assessed"*. Same fault as a "shaded band = usual range"
  legend above a chart with no band (§6ab, the same afternoon). The prop is
  now `absenceCaption` and the component shows it only when a dotted point
  exists — named so the contract cannot be misread by the next caller.

Also: the SVG title now speaks the fractions (*"Inputs available for each
topic: Diabetes 5 of 8..."*). A radius is not readable by a screen reader and
is not precise to anyone else either.

### TEN MUTATIONS, and the two that survived were the whole point

* **Reverting the radius to the verdict SURVIVED the first pass.** Every new
  test asserted the spoken fractions, which come from the counts — so the
  geometry could go back to being the verdict and still pass. **Asserting what
  a chart SAYS is not asserting what it DRAWS.** Both are tested now, at the
  component and through the page.
* **Un-pinning an unassessed topic from zero SURVIVED**, and that exposed a
  latent inconsistency rather than a missing test: **the polygon and the
  vertices computed each point's radius independently.** §6x's rule — "the
  polygon must pass through the centre on that axis" — was enforced twice and
  tested once, so the filled shape could reach out to a topic whose own point
  was drawn at the centre as an absence. One radius, computed once, used by
  both; and the pinning test now asserts the polygon too.

Third and fourth passes: 10/10 killed, including double-counted features and
an observed line losing to a later absent one.


---

## 6ad. Two results with no explanation, and nothing saying so · 2026-09-11

The user, reading "What these results mean": *"in this section few parameters
are missing which are there in the report."*

Correct. Eight results on the report, **six explanation cards**, and nothing on
the page about the other two.

### THE FACT WAS PRODUCED, STORED, AND DROPPED AT THE LAST HOP

Module 23 explains up to `max_explanations` usable values — capped at **6**,
in `config/env.js` (`Math.min(6, ...)`) and enforced by the service's own
`ge=0, le=6`, because every explanation is a model call. **And it already
records every value it passed over.** Straight from the stored analysis:

```
/data/analysis/explanation/skipped:
  cholesterol    explanation_limit_reached
  triglycerides  explanation_limit_reached
  bmi | age | gender   explanation_limit_reached
```

`ReportExplanationSet.skipped` crosses HTTP, `normaliseExplanationSet` spreads
it through to storage, `+patientExplanation` selects it — and
`buildRecommendationsSection` never read it. **Four layers carried the fact and
the fifth threw it away**, which is this project's signature failure for the
fourth session running.

**The frontend could not have caught this.** `Explanations` already refuses to
skip a withheld paragraph — its docstring says *"silently omitting the second
would make a partial set look complete"* — but it guards `available !== true`
on the ENTRIES array, and **an explanation that was never requested has no
entry to be absent in.** The guard was real, tested, and structurally unable to
fire. Worth remembering: a guard over a list cannot see what never entered the
list.

### What it says now

`explanations.notExplained` carries `{feature, reason}` verbatim, reason codes
included — the same split as the population page's refusal codes, which stayed
in the payload after the cards went. The page states it:

> *"Total cholesterol and Triglycerides have no explanation above. Only a set
> number of explanations is written for each report, and this one has more
> results than that — nothing was wrong with these results, and their values
> are in the table above."*

**Its own sentence, not the withheld one.** "Never attempted" is not
"withheld": the withheld line blames the writing step, and using it here would
tell a reader their result was refused when it was simply not reached. Third
time this three-state distinction has had to be drawn on this project (§6w's
glossary: never asked / described / withheld).

**Profile answers are filtered out.** `skipped` also names `age`, `gender` and
`bmi`; "no explanation was prepared for your age" is the screen describing its
own mechanics, and nobody was waiting to be told what age measures. Only
features shown as results on this page are named.

### THE BUG IN MY OWN FIX, caught by a mutation

The first version rendered the section whenever anything was skipped — so with
no explanation on screen at all, the page would have said *"...have no
explanation **above**"* pointing at nothing. That is §6w's scope-statement
fault exactly (*"No line BELOW asserts..."* moved to the foot of a page). With
zero explanations shown there is no partial set to mistake for a complete one,
so the section stays absent.

Seven mutations, 7 killed. The last survivor was not a missing test but a
DUPLICATED RULE: `andList` and `nameList` each computed the comma-safe
separator (§6w: a laboratory prints "LDL Cholesterol, Direct", and a
comma-joined list of two reads as four). One `commaSafeSeparator` now, used by
both — and the existing "In short" comma test kills the mutation.

Also read off the live page and fixed: *"Total cholesterol, Triglycerides are
not explained above"* is not a sentence. `andList` gives the final "and";
`contextPhrase` was rewritten to use it rather than keep its own copy.

### THE CAP WAS THEN RAISED, ON THE USER'S WORD: 6 -> 10

`DEFAULT_MAX_EXPLANATIONS` 6 → 10 in `app/services/explanation.py`, and
`config/env.js` 6 → 10 to match. The route bound is `le=DEFAULT_MAX_EXPLANATIONS`
so it follows on its own — but **the Node clamp is a separate constant in a
separate language and nothing links the two.** Raising only the Node side turns
every analyse into a 422; that warning is now in the comment beside it.

**Raising the number alone would have spent the new budget on the wrong rows.**
`laboratory_values` carries the age, sex and BMI the assessment used alongside
the printed results, and all three were candidates — at a cap of 10, three
model calls would go to writing "this test measures your age". Two changes
made the budget mean what it says:

* **A profile answer is not a result.** Rows are excluded on
  `source != "lab_report"`, with the new reason `not_a_laboratory_value`.
  **`source`, NOT `origin`** — the ai-service stamps `report_transcription` on
  profile-derived rows (§6w, still open at source), so `origin` says the
  opposite of the truth here.
* **Positive proof only.** `LaboratoryValue.source` is `Optional[str] = None`,
  so a row can genuinely arrive without one — an older stored report, a
  hand-built row, and **every fixture in `test_explanation.py`**. Requiring the
  field to EQUAL "lab_report" skips every such row and explains nothing at all.
  A missing field is not evidence that a value came from the profile. Caught by
  the existing tests the moment the strict version ran, which is the
  fixture-vs-producer hazard (§6w) arriving from the other direction: here the
  FIXTURE was the honest one and the new code assumed a field it does not
  always get.

**Eligibility is now decided before the budget.** With the limit checked first,
every row past the cap came back as `explanation_limit_reached` — including
rows that were never eligible at all — so a rejected value was blamed on the
budget and a caller could not tell "we ran out" from "there was nothing here to
explain". Three reasons answering three different questions, flattened into one
by the order of two `if`s.

**Live, after restarting both services** (the OpenAPI now advertises
`maximum: 10`), the same report re-analysed:

```
generatedCount: 8   withheldCount: 0
explained:     hba1c, blood_glucose, hemoglobin, vitamin_d,
               vitamin_b12, creatinine, cholesterol, triglycerides
notExplained:  bmi, age, gender  -- not_a_laboratory_value
```

Eight cards on the page, and the "no explanation above" sentence correctly
absent because nothing is missing. It stays as the safety net for a report
that ever does exceed 10.


### AND STILL NOT ALL OF THEM — the section is not the whole report

*"still this section didn't contain all parameters listed in the report."* Also
correct, and a different fact again. The report prints **twelve** parameters:

* **8** the platform assesses → explained here, with the reader's own value;
* **4** it has no feature for (LDL Direct, HDL, Blood Urea, Potassium) → the
  `parameter_glossary` section, higher up, under "Also on your report, but not
  assessed here". Three carry a description; HDL is not lab-flagged so nobody
  asked (§6w's three states).

Nothing was lost — but a section headed *"What these results mean"* showing
eight of twelve reads as the complete list, which is the same
partial-set-looks-complete fault in a third costume. It now says so and points
at the section that has the rest, and the test asserts the named heading
ACTUALLY EXISTS on the page: a signpost to a section that is not there is worse
than none.

**NOT MERGED, and this is the architecture rather than a layout preference.**
Those four are described from the test NAME ONLY, with no patient data in the
prompt (§6v) — that is the entire argument for why the feature is safe. Moving
them into a list whose other entries interpret the reader's own values invites
exactly the inference the design forbids. Four mutations, 4 killed.


### A word set in the figures face

Seen on the running page while checking the above: **From your profile** read

```
BMI    26.42 kg/m2
Age    58 years
Sex    male
```

all three in `IBM Plex Mono` with tabular numerals, because `.lab-table td`
sets every cell that way. That treatment is right for the reason design.md §3
gives — figures align down the column, which is what makes a results table
scannable — and **a word aligns with nothing**, so the only thing it carries
there is the LOOK of a measured value, directly under two real figures and a
heading about results.

Non-numeric cells now take the body face (`.lab__word`), and a string value is
capitalised on its first letter only: NOT `text-transform: capitalize`, which
renders an absence sentence as "Not Measured", and not a rewording — "male"
and "Male" are the same answer. Absence sentences in that column get the body
face too, which is what they always should have had. Four mutations, 4 killed.

Live: BMI and Age stay mono, Sex is "Male" in sans.

### The cost, stated plainly

**Every explanation is a Gemini call.** An eight-value report now spends 8
where it spent 6, and the free tier is 20 per model per day with a fallback
chain across models. Two full analyses of an ordinary report is most of a
day's quota on the first model. `AI_SERVICE_MAX_EXPLANATIONS` lowers it
without a code change if that bites.


---

## 6ae. The clinician's caveat, written for a clinician · 2026-09-11

*"this summary is for the healthcare professional. he does not know what is ml
model and roc and all."*

The **On the model output** paragraph read:

> *"Trained on 399 rows and measured on 100, from a single UCI cohort in which
> creatinine and haemoglobin separate the classes almost cleanly. A ROC-AUC
> near 0.99 says the separation was easy, not that this would hold on a
> screening population. One misclassification moves recall by about 1.6
> points."*

Every word of that is true and it is addressed to whoever trained the model.
§6w had ruled that this page *"does not get to reword an author's safety
note"* — correct as a rule about the RENDERING layer, and it left the note
unreadable by its actual audience. **The fix is to rewrite it where it is
authored**, not to paraphrase it downstream where two statements of the same
fact would drift.

`honest_read` in `app/ml/kidney.py` and `app/ml/heart.py` is now written for
the reader of the document. **Every fact kept, only the register changed** —
dataset size, the two analytes that made the split easy, that the accuracy
reflects the dataset rather than screening performance, the fragility of a
100-record test set; and for heart, what a flag is actually worth, the
self-report limitation and the missing blood pressure. The ML reading of the
same numbers is untouched in `ml/artifacts/*.metrics.json`, whose audience
really is a model reviewer.

### THE SAFETY SCANNER REFUSED THE FIRST TWO DRAFTS, AND WAS RIGHT BOTH TIMES

Module 24 **withholds the whole note** if any phrase trips it — it deletes the
model's statement of its own limits from the document that most needs it.

1. *"about 37 of every 100 people it flags turn out to have heart disease"* →
   `diagnostic_assertion`. The original said *"most patients it flags will NOT
   have heart disease"*, and **that direction was not an accident**: the same
   fact stated as a negation passes. Now "roughly two out of every three people
   it flags do NOT have heart disease" — which is precision 0.37 in the only
   form the scanner allows, and the more useful form for a clinician anyway.
2. *"so it misses people not yet **diagnosed**"* → `diagnostic_assertion` on
   the word itself. The original used "identified", and the comment beside it
   already recorded an earlier draft failing this exact way. It happened again
   on the first rewrite. **Found by bisecting the sentence through
   `_transcribe` directly**, which took one command and no guessing.

### THE GUARD BELONGS AT THE PRODUCER, and a mutation proved it

A frontend test asserting "no ROC-AUC in the passage" runs against a FIXTURE
and cannot see `app/ml/kidney.py`. Putting `ROC-AUC` back into the note
survived the frontend suite completely. `test_the_honest_read_is_written_for_a
_clinician` now checks the string where it is authored, in both predictors.

Three further mutations were needed after the first sweep:

* the frontend jargon list did not include **this page's own lead-in**
  (*"a likelihood derived from patterns in training data"*) — a list that
  polices only the upstream note lets the local copy of the same register
  straight through;
* a diagnostic claim smuggled into the note survived until
  `test_doctor_summary.py` was in the run — the safety scan lives there, not
  in the predictor tests;
* **inverting the caveat survived**: `"nothing shows it holds in a screening
  population"` → `"it holds in a screening population"` still contained the
  phrase the test asserted. An assertion that a phrase APPEARS says nothing
  about which way round the claim points, and on this sentence the direction is
  the whole content. Now pinned as a negation, with several phrasings allowed.

### Frozen in storage, like the explanations

`honest_read` is captured into the decision metadata at analysis time, so
**every already-analysed report keeps the old wording until it is re-analysed.**
Same shape as the explanation cap (§6ad): changing a generator does not rewrite
what a past run stored.


---

## 6af. "How many times should I tell you" · 2026-09-11 · the same lesson, third screen

The user, with reason: *"this application will be used by normal users, they
don't know anything about the models — only show useful things."* The same
instruction §6u and §6w already recorded, arriving a third time because each
fix was applied to the SCREEN in front of us rather than to the class of fault.
**Worth stating as a standing rule: when a fix is "remove this system's own
vocabulary from a reader-facing surface", it is never one surface.**

Three things went.

### 1. "Worth knowing about this analysis" — DELETED from the dashboard

It printed the pipeline's stage warnings verbatim at a patient:

> *"'25-Hydroxy Vitamin D' reported unit 'ng/dL', which is not a recognised
> unit for feature 'vitamin_d' (canonical: 'ng/ml'). The value was left
> unconverted and flagged canonical_unit=false."*

That is a bug report. Nothing in it is actionable by the person whose blood it
is, and the facts they CAN act on are already on the page in their own words:
a value that could not be used says so on its own row, an unreadable page is
stated in the summary, a failed stage is stated there too. **Relocated, not
deleted** — every warning is in the stored analysis and on
`GET /reports/:id/analysis`, which is where a maintainer looks. `readerWarnings`
and its methodology filter went with it; a filter whose only consumer is gone
is an unreachable branch.

### 2. The validator's rejection message — off the patient page

`rejectionReason` is written for whoever fixes the unit. The row and the range
chart both printed it. One sentence now, `REJECTED_FOR_READER`, defined once
and used by both: *"This result could not be used, so nothing on this page is
based on it."* **The chart mutation SURVIVED the first sweep** — the fixture
had no reference interval, so no chart rendered and only the table was ever
asserted. A banded row was added to the fixture; 3/3 killed after that.

### 3. The clinician passage — this system's component names removed

*"Threshold comparison against the platform's configured cut-offs flagged..."*
is how the software describes itself. A clinician reads a handover note. Now:

> *Diabetes was flagged two ways: a measured value crossed one of this tool's
> cut-offs, and the statistical model agreed. ... Kidney Disease was flagged by
> the statistical model alone — no measured value crossed a cut-off for it.*

The three-group distinction §6w insisted on is intact; only the vocabulary
changed. The frontend jargon list grew to cover component names as well as ML
metrics, and two mutations confirm both the wording and the distinction are
held by tests.

### STILL OPEN: the user asked for the clinician summary to be GENERATED by Gemini

Not done, and it is not a wording change. The document publishes
`integrity.llm_calls_made: 0` and `model_generated_text_included: false`
**about itself**, and §6w's decision to compose rather than generate rests on
that. Generating it means: those two claims become false unless updated
honestly; the output must pass Module 24 like every other model text; and it
needs a fact check against the composed version so an LLM cannot quietly drop
one of the four things §6w kept (which kind of check flagged what, the model
limitation, every absence, the closing line). The safe shape is
generate → validate → verify-facts → **fall back to the composed passage**, so
the worst case is today's behaviour. Awaiting the user's word because it flips
a published safety claim, not because the work is unclear.


---

## 6ag. The clinician summary, written by the model · 2026-09-11 · Module 32b

On the user's instruction. §6w's decision to COMPOSE rather than generate is
not overturned lightly — it argues, correctly, that "summarise these results
for a doctor" is the worst possible use of a model. What changed is that the
composed prose kept reaching for this system's own vocabulary, three times in
one session, and prose written for a reader is better prose.

**`app/services/clinician_narrative.py`, and the worst case is exactly the
composed passage.** Four gates, each discarding the text outright:

1. **no model** → `model_unavailable`, no network touched. This is what makes
   the caller's fallback the NORMAL path rather than an error path;
2. **Module 24**, the same `guarded_generation` every other model text goes
   through;
3. **the fact check**, this module's own contribution: every value, flagged
   name, unassessed name, unsupplied profile answer, the no-intervals fact and
   the model-only distinction must be in the output or it is thrown away;
4. **no silent substitution** — `text` is None on every refusal and `outcome`
   says which gate stopped it.

Each refusal gets ONE retry that says what went wrong: the safety layer quotes
its codes back, a fact failure names what was dropped. "Try again" is not
feedback.

### THE MODEL NEVER HANDLES THE SAFETY-CRITICAL SENTENCES

The limitation note and the closing line are APPENDED after approval; the model
is told not to write them. The first version told it to copy them and verified
the copy, which **could never succeed**: the kidney model's own note is judged
`UNHEDGED_INTERPRETIVE_CLAIM` by this module's safety context — it passes
Module 32's transcription check, which applies different controls — so a
narrative REQUIRED to contain it was unapprovable. Three live runs were refused
and **the refusing paragraph was the safety note itself**, found by bisecting
the output through the validator paragraph by paragraph.

Appending is also simply stronger: a sentence the model retypes is one it can
mistype.

### FIVE DEFECTS IN MY OWN WORK, ALL FOUND BY RUNNING IT

The offline suite was green before any of these. Every one came from reading a
live response.

1. **Bare numbers.** `_value_strings` passed values without test names, so the
   narrative read "the reported values are 8.4 %, 186 mg/dl, 14.8 g/dl..." — a
   list of quantities of nothing, worse than the passage it replaced.
2. **Profile answers as laboratory results**, including the catalog's internal
   note: *"a patient with Age in whole years recorded as 58 years and
   Self-described gender as stored by Module 2 as male"*. The filter looked for
   a top-level `source`; the producer carries it at `provenance.source`.
3. **A flagged topic with no assessment entry vanished from the prompt** — the
   fallback only fired when ALL THREE flag groups were empty. `_missing` then
   required a name the model was never given, refusing every narrative forever.
   A fallback that only fires when nothing else did is not a fallback.
4. **`_missing` checked the test NAME instead of the number**, because
   `value.split(" ")[0]` started returning "Glucose" once names were added.
5. **`not_supplied` was read from a field that does not exist.** There is no
   such list on the payload; the signal is `null` on the three tri-state keys.
   The check fed by it could never fire, and a live narrative dropped "were not
   supplied" while the gate reported nothing missing. **Second time in one file
   that a guessed field name produced a check protecting nothing.**

Two more absences were lost on a run that passed every other gate — the
unsupplied answers and the no-intervals sentence — because the fact check did
not list them. **A fact check that does not name a fact does not protect it.**

### Also worth keeping

* **`require_referral` is off, and the reason was MEASURED rather than
  assumed.** With it on, the validator records `MISSING_PROFESSIONAL_REFERRAL`
  and **approves anyway** — §6r's finding, named in §6k D1 and never fixed. It
  is not a blocking control, so leaving it on would stamp a code on every
  narrative while refusing nothing. A mutation flipping it is equivalent.
* **The narrative is cached on the report, keyed to `analysis.version`.** The
  doctor summary is built per request, so generating inline would spend a model
  call every time someone opened the page. A re-analysis invalidates it,
  because prose describing the previous run is worse than no prose.
* `model_unavailable` is the one outcome NOT cached: a key outage is a
  configuration state, not an answer about this report.
* The page says a model wrote the wording AND that the findings were not
  produced by one. The distinction is the whole reason the composed version
  existed.
* The route is in `tests/test_explain_endpoint.py::ROUTES` from the day it was
  written, not after it shipped dead (§6w).


### THEN THE CAVEAT ITSELF WAS TOO LONG · the user again, and again right

*"why this part in the summary?? show only required part to the healthcare
professionals."* — pointing at four sentences of dataset arithmetic: 399
records to learn from, 100 to check against, 1.6 percentage points.

**The caveat stays; the arithmetic goes.** Those counts are the EVIDENCE for
the caveat, not the caveat. What a clinician acts on is that the flag came from
a pattern rather than a measurement, that the accuracy figure flatters it, and
what the flag is therefore worth. The kidney `honest_read` is now three
sentences:

> *"This came from a pattern model, not from a measurement. It was developed on
> one small dataset in which the two groups separated unusually cleanly, so its
> accuracy there flatters it and nothing shows it holds in a screening
> population where kidney disease is far less common. It is a reason to
> consider further assessment, never a finding in itself."*

**WHAT MAY NEVER GO IS THE CAVEAT.** This platform has found it MISSING three
separate times (§6o D8, §6p, §6w), each time leaving a model's flag on screen
with nothing qualifying it, and each time it was recorded as the worst thing on
the page. Shortening it is not the same decision as dropping it.

The test that pinned "399" was changed to assert what the count was a PROXY
for — a smallness word plus the non-transfer negation. That is the same
invariant ("a near-perfect metric must never appear without the fact that the
dataset was small and the accuracy does not transfer"), stated without pinning
a figure the document deliberately no longer shows. **Twice now a test here has
been rewritten to follow this note; the guard against that is that the
invariant, not the wording, is what each version asserts.**

### Three prose defects the live runs showed, none visible offline

Each was found by reading a generated narrative, and each is a known fault of
this project arriving through a new door:

1. **Lowercase sentence starts** — "hypertension, heart disease, smoking
   history were not supplied" opening a sentence, because the facts block hands
   the model lower-case keys. §6w's ". hypertension, heart disease..." exactly.
2. **The same sentence four times** — "This tool flagged Heart Disease because
   a measured value crossed a cut-off", once per topic. §6w's burial fault,
   which the clinician page was rewritten to remove in the first place.
3. **The old note kept appearing after it was changed** — `honest_read` is
   captured into the decision metadata at analysis time, so every stored report
   keeps the previous wording until re-analysed. Same as the explanations
   (§6ad). **Worth knowing as a standing property: changing a generator does
   not rewrite what a past run stored, and on this project that has now
   surprised three separate changes.**

Both prose faults are prompt rules now. Neither is enforced by a gate — the
gates guarantee facts and safety, not style, and a style gate would refuse
prose for being ugly while the fallback was uglier still.


### The page around it · a box two-thirds full is not a document

The passage card took the app's full 880px column while its paragraphs wrapped
at a 68ch measure, so a third of every line's width was empty inside the box
and the panel read as a half-filled container. **The container follows the
measure**: the card is `min(100%, 74ch)`, and the whole route — trail, heading
and article — shares that width, because this page is a document with one
article on it and nothing to put beside it. Verified at 1230px and at 375px;
no horizontal overflow at either.

**And the prose arrived as one ten-line block.** The model separates its
sentence groups with a DOUBLE SPACE after a full stop, not with a blank line,
however the prompt asks — two live runs confirmed it. The renderer now treats
both as a break: it reflows already-approved text and changes not one character
of it, which is the cheap half of a choice whose other half was another round
of prompt-tuning at a model call each. Seven paragraphs instead of one.

### Live, after four rounds of fixes

```
outcome: generated   calls: 1   missing: []
```

Values named, absences stated, the three flag groups intact including "Kidney
Disease was flagged by the statistical model alone, and no measured value
crossed a cut-off for it", the limitation note verbatim, the closing line last.

**Cost, measured:** one model call per ANALYSIS, not per page view -- the
narrative is cached on the report and keyed to `analysis.version`. A refusal is
cached too, deliberately: retrying a safety rejection on every page view would
spend a day's quota on one reader.


---

## 6ah. Comparing any two reports · 2026-09-11 · a picker, not an endpoint

The timeline compared the first report with the latest and offered no way to
choose. **The backend already took `?baseline=&comparison=` on both
`/timeline/comparison` and `/timeline/progress`** — the capability was there
from the day those routes were written and nothing exposed it. This was a
frontend control, not a feature.

### The decisions worth keeping

* **BOTH SECTIONS ARE RE-ASKED, the trends section is not.** The progress score
  is computed from the same two reports as the table; a score describing one
  pair beside a table describing another is two answers to different questions
  presented as one screen. Trends describes EVERY report on the account, so
  refetching it would redraw an unrelated section under the reader's hands.
* **The old table is cleared before the new one arrives.** Leaving the previous
  numbers under a changed picker states that they are the comparison the
  control now names.
* **The selects are seeded from the pair that came BACK, not the one
  requested.** With no explicit choice the service picks first-vs-latest;
  reading its answer is what stops the control describing a comparison the
  table is not showing.
* **Report names come from `listReports` and their failure costs the labels
  only.** An account with four reports from one week is four identical options
  otherwise. The picker still renders with dates alone.
* **Both or neither.** `pairQuery` sends a pair only when both ids are present:
  the backend refuses exactly one rather than guessing, so a half-made choice
  would become an error under a table the reader was mid-way through changing.

### TWO DEFECTS FOUND BY DRIVING IT, both invisible to the suite

1. **The control did nothing when clicked.** On an account with TWO reports the
   only available change is choosing the other report as the baseline — which
   necessarily equals the current comparison, and the identical-pair guard
   silently refused it. **A control that visibly does nothing is worse than no
   control.** It now SWAPS: naming the later report as the baseline asks for
   the comparison the other way round, which Module 29 supports and reports as
   `chronological: false`. Verified live: the table recomputed, HbA1c went from
   `8.4 → 5.2 improved` to `5.2 → 8.4 worsened`.
   The symmetric branch (colliding from the SECOND select) was written, found
   unreachable — that list excludes the current baseline — and deleted with
   its test rather than kept as a branch nobody can find out is wrong.
2. **"…the direction of every change is reversed.."** The conditional clause
   carried its own full stop and another was printed after it regardless.
   Latent since the sentence was written, and **invisible until the picker made
   an out-of-order comparison reachable for the first time**. A feature's first
   real use is when its neighbours get tested.

Seven mutations on the control and the query builder, all killed — including
sending half a pair and pasting an unescaped id into the URL, which needed a
test at the API layer because the picker can no longer produce either.


### THE MIDDLE READING WAS NOWHERE · found on a three-report chart

The user, pointing at the middle dot of a three-point series: *"when i click on
that it is showing 7th to 11th for every dot, but that dot belongs to the 9th
September report."*

Correct, and it was worse than a tooltip bug. **That reading appeared nowhere
on the page at all:**

* the x axis is deliberately two dates rather than a ruler (the readings are
  irregular and evenly spaced ticks would imply a cadence nobody kept), so the
  middle date is not labelled;
* the chart's `<title>` — the only sentence describing the series — named the
  FIRST and the LAST and said "across 3 readings";
* and because only the SVG carried a title, **every dot showed that same
  whole-series summary**, which reads as though the dot under the pointer is
  the 7th-to-11th span.

So the one thing a reader was pointing at was the one thing nothing said.

**Two fixes, and the second is the one that matters for a screen reader.**
Each marker now carries its own `<title>` (a child title takes precedence over
the parent's for the element under the pointer), and the summary names EVERY
reading while the list stays readable — above six it falls back to the two ends
and the count, because a sentence naming fourteen dates is not a summary. The
gap markers got titles on the same reasoning: that lane sits below the axis
with no date of its own either.

Four mutations, all killed — including one that survived the first pass because
the gap reason is deliberately printed twice (tooltip and list) and the test
counted occurrences rather than looking at the marker's own title.

**Verification boundary, stated:** the three-point case is covered by tests
(the middle dot's tooltip is asserted by position); the live check ran on a
two-report account. The reporter's own account has three.


---

## 6ai. STATE AT THE END OF THE SECOND 2026-09-11 SESSION — **SUPERSEDED BY §6ap**

> Its run commands are still correct; its **test-account description is not**
> (the reports on that account have changed), and its uncommitted list is now
> a subset of §6ap's. Read §6ap.

**Everything runs. All 4,614 tests pass. NOTHING IS COMMITTED.**

### ⚠ THE WORKING TREE IS TWO SESSIONS DEEP AND `origin/master` IS AT `6dc3409`

§6y's uncommitted list was never committed, and this session's work sits on
top of it. **Commit before building anything new.** `git status` right now:

```
 M MEMORY.md
 M ai-service/app/api/routes_explain.py          new clinician-summary route
 M ai-service/app/ml/heart.py                    honest_read rewritten for a clinician
 M ai-service/app/ml/kidney.py                   honest_read rewritten, then shortened
 M ai-service/app/services/explanation.py        eligibility before budget; profile rows excluded
 M ai-service/tests/test_explain_endpoint.py     new route added to ROUTES
 M ai-service/tests/test_explanation.py
 M ai-service/tests/test_heart_predictor.py      jargon guard at the producer
 M ai-service/tests/test_kidney_predictor.py     jargon guard; smallness not the count
 M backend/src/config/env.js                     maxExplanations 6 -> 10
 M backend/src/controllers/doctorSummaryController.js  narrative, cached per analysis
 M backend/src/models/Report.js                  +doctorNarrative
 M backend/src/services/aiServiceClient.js       +writeClinicianSummary
 M backend/src/services/dashboardService.js      +explanations.notExplained
 M backend/tests/dashboard.test.js
 M frontend/src/components/CoverageRadar.jsx     real coverage, frame, caption
 M frontend/src/components/RangeChart.jsx        hasComparableRange
 M frontend/src/lib/api.js                       pair query for comparison/progress
 M frontend/src/pages/Dashboard.jsx              cards, warnings, explanations, labels
 M frontend/src/pages/DoctorSummary.jsx          narrative render + fallback, layout
 M frontend/src/pages/Timeline.jsx               trend charts + the report picker
 M frontend/src/styles.css
 M frontend/tests/clinical.test.jsx
 M frontend/tests/dashboard.test.jsx
 M frontend/tests/design.test.jsx
 M frontend/tests/timeline.test.jsx
?? ai-service/app/services/clinician_narrative.py      NEW MODULE (32b)
?? ai-service/tests/test_clinician_narrative.py        19 tests
?? frontend/src/components/TrendChart.jsx              NEW COMPONENT
?? frontend/src/lib/labels.js                          PATIENT_LABEL, shared
?? frontend/tests/api.test.jsx                         NEW
?? frontend/tests/trendchart.test.jsx                  NEW, 33 tests
```

A sensible split, if committing in parts: (1) the timeline trend chart
§6z; (2) the dashboard card and chart work §6aa–§6ac; (3) the explanation cap
and the model notes §6ad–§6af; (4) the Gemini clinician summary §6ag; (5) the
comparison picker §6ah.

### Running it (unchanged)

```
cd ai-service && .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
cd backend   && npm start          # :5000, Mongo Atlas, non-SRV URI
cd frontend  && npm run dev        # :5173, or :5174 if that is taken
```

Health: `curl http://127.0.0.1:5000/api/v1/health`. **Restart after any
backend or ai-service change** — and this session hit the stale-process trap
twice more, once on the OpenAPI route and once on a model note.

Tests: `cd backend && npm test` · `cd frontend && npx vitest run` ·
`cd ai-service && .venv/Scripts/python.exe -m pytest -q` **with `.env` moved
aside** (still unfixed; see §0).

Test account: `glossary.check+1788753613@example.com` / `Str0ng!Passw0rd`.
It has TWO analysed reports — `06-lab-flagged...pdf` (2026-09-07) and
`01-all-normal.pdf` (2026-09-11) — both re-analysed on the current code.

### What this session did, in one line each

| § | |
|---|---|
| **6z** | the timeline trend chart: a real change, <2 readings, a gap, a rejected reading — kept apart |
| **6aa** | the condition card: the two-checks lecture removed; "how it was checked" only where the values do not say |
| **6ab** | the range chart is not drawn when nothing has a reference interval |
| **6ac** | the coverage radar measured the VERDICT under the word "Coverage"; now real coverage |
| **6ad** | two results had no explanation and nothing said so; the cap raised 6 → 10 |
| **6ae** | the model notes rewritten for a clinician, guarded at the producer |
| **6af** | pipeline warnings and validator messages off the patient page |
| **6ag** | **the clinician summary is now written by Gemini**, behind four gates, falling back to the composed passage |
| **6ah** | a picker for comparing any two reports; per-dot tooltips on the trend chart |

### KNOWN AND OPEN, carried forward

* **The Gemini narrative is cached per analysis** (`report.doctorNarrative`,
  keyed to `analysis.version`). A refusal is cached too, deliberately.
  `model_unavailable` is not. **Changing the prompt or a model note does not
  affect stored reports** — clear `doctorNarrative` or re-analyse.
* **`honest_read` is captured at analysis time**, so changing a model note
  needs a re-analysis to show. This surprised three separate changes today.
* **Two ai-service defects still open at source** (§6w "Still open"): profile
  rows stamped `origin: report_transcription`, and `feature_catalog`'s
  `display_name` for `gender` being an internal note. Both worked around in
  three places now, including the new narrative module.
* **Module 32's payload still nests `present` two ways** (§6w).
* **`MISSING_PROFESSIONAL_REFERRAL` does not block** — measured this session:
  the validator records the code and approves anyway (§6r, §6k D1).
* **Frontend fixtures are still not generated from real responses.** This
  session hit it twice inside one new module: a guessed `source` field and a
  guessed `not_supplied` field each produced a check that protected nothing.
* Gemini free tier is 20/day/model with a fallback chain. Today spent roughly
  five analyses plus a dozen narrative calls.

### The habit, after two sessions of this

Every defect this session was found by **running it and reading the result** —
never by the suite, which was green before and after each one. The user found
most of them. What worked:

* **mutation-testing every guard**, and treating a SURVIVOR as information:
  four times it meant a missing test, twice it meant an unreachable branch to
  delete, and twice it exposed a real bug (a `null` printed as a direction, a
  fact check that could never fire);
* **reading the producer's actual response before writing a consumer**, which
  this session proved the hard way three times;
* **asking what a sentence is FOR** — most of the removals were text that
  described the software rather than the patient.

---

## 6aj. The round-up and the guidance list, read aloud · 2026-09-12

The user, on the two plainest panels on the dashboard: *"these are looking
somewhat normal or simple make it as a good design."* Both were redesigned —
and as usual the redesign is not where the value was. **Auditing the two
sections against the spec found a defect that had been live since §6x**, and
the design work is the smaller half of this entry.

Frontend suite **213 → 224**. Both sections had ONE test between them before
this (`/Not enough information to check/`, asserting the wording only).

### THE DEFECT: the absence group was separated by a tint

```css
.condition__roundup            { color: var(--ink); }
.condition__roundup--unassessed{ color: var(--muted); }
```

Two comma-runs, `--ink` versus `--muted`. **One step of grey carrying the
single distinction this whole screen exists to preserve** — CHECKED AND CLEAR
is not COULD NOT CHECK — and `styles.css`'s own file header says in as many
words why that can never work: *"a grey number still reads as a number; a
dashed empty outline cannot."* `design.md` §6 mandates the treatment
(`NOT CHECKED` in `--mono`, dashed `--band-line`, **no fill**) and this panel
had never implemented it.

It was invisible on both stored reports, because neither has an unassessed
topic — `01-all-normal.pdf` renders twelve clear and zero unchecked. **The
group that was wrong is the group the data cannot produce.**

Now: chips. Cleared topics are filled, bordered solid, ticked. Unchecked
topics have **no fill**, a dashed `--band-line` border, and the words
`NOT CHECKED` in mono. The charts already speak this language, so the page has
one absence vocabulary instead of three.

### THE FILL IS NOT THE SIGNAL, AND THE FIRST COMMENT SAID IT WAS

The CSS comment claimed *"Fill is the signal; colour only agrees with it."*
Measured in the page: `--panel` on `--bg` is **1.14:1 in light, 1.06:1 in
dark**. The fill is very nearly invisible and carries almost nothing. That is
**a comment asserting a guarantee the code does not make — the fifth time in
this file** — written, this time, by the person who had just finished quoting
the rule about it.

What a reader actually sees is SOLID vs DASHED, a tick vs no tick, and the
literal words. Three signals, none of them colour alone. The comment says that
now, with the measurement in it.

### A CONTRAST REGRESSION, INTRODUCED AND THEN CAUGHT BY MEASURING

Putting the unchecked topic NAMES in `--mono` — the obvious reading of
design.md §6 — scored **3.37:1** on `--bg`. Below AA, and **dimmer than the
`--muted` comma-run it replaced (4.04:1)**. Wrong twice: these are the topics
a reader most needs to take to a doctor, and the file's own principle is that
the OUTLINE carries the absence *precisely so the text does not have to be
degraded to carry it.*

Names are `--body` now: **6.6:1 light, 8.73:1 dark.** `--mono` is spent on the
tag, which is where design.md actually puts it.

> **~~STILL OPEN, APP-WIDE~~ — FIXED THE SAME DAY, see §6am.** `--mono` at 11px
> measured **3.37:1** here and **3.04:1** in the header — below AA, and it is the
> `NOT CHECKED` / `NOT ON REPORT` / `NOT USABLE` tag in every component.
>
> Recorded at the time as app-wide and therefore not to be diverged from
> locally. That judgement was right and the conclusion drawn from it was
> wrong: app-wide is a reason to fix it AT THE TOKEN, not a reason to leave
> it. §6am changed the token, which fixed every component at once — and
> found two more failing tokens on the way, one of them far worse.

### The guidance list: one attribution, not one per row

Three bullets, each ending `Related to: Obesity.` — §6ag's repetition fault
and §6w's burial fault, in a list. `sharedBecausePhrase` hoists it to one line
**only when every row's set is identical**, compared set-wise because the
catalog's order is incidental.

**Hoisting a set that is not shared is the failure mode, and it is the bad
direction:** one line saying "Obesity" above a bullet that is there because of
Diabetes announces a condition the bullet never claimed — the exact hazard
`matchedConditions` exists to prevent. Unlike sets keep their per-row spans.

The list also stopped being browser bullets (`list-style` discs at
`padding-left: 20px` gave the most reader-facing list on the page less
structure than a form label). Rows with a left rule — and **the rule's token
was measured, not picked**: `--hairline` was the first try and drew literally
nothing at **1.064:1** against `--bg`, an element present in the stylesheet and
absent from the screen. `--band-line` is the most visible and is exactly wrong,
because it is the dashed-absence token and spending it on decoration teaches
the eye that it means nothing. `--panel-line`, 1.225:1.

### A NUL BYTE IN THE SOURCE

`grep` started reporting `Binary file src/pages/Dashboard.jsx matches`. An edit
had written `.join('\0')` where `.join(' ')` was intended — a literal NUL
inside a string literal. It **worked**, which is why nothing caught it: as a
join separator a NUL is as unique as a space, every test passed, and the page
rendered correctly.

What it broke was the tooling. `grep -n` refused to print matches, and the
mutation runner reported **"pattern not found"** for the one mutation aimed at
that line — a guard silently exempted from mutation testing by an invisible
character. Found by debugging the skip rather than shrugging at it. Scanned the
whole of `src/` and `tests/`: this was the only one.

**Worth carrying: a mutation reported as SKIPPED is not a mutation that
passed.** The runner prints KILLED / SURVIVED / SKIP, and SKIP is the row that
looks like nothing happening and means the guard was never tested at all.

### MUTATION-TESTED: 11 GUARDS, 10 KILLED, 1 DELETED

Run as a script (mutate, run `dashboard.test.jsx`, revert). The survivor:

* **`if (!first) return null;` SURVIVED** — the guard against hoisting when a
  row has no reason. Unreachable: `groupGuidance` pushes an item only when
  `matchedConditions` returned a non-empty list, so every row that arrives has
  one. Deleted rather than kept, on §6aa's precedent, with the caller's
  guarantee named in a comment at the point that relies on it. It is also
  unreachable a second way — `becausePhrase` returns null for an empty list, so
  a future unfiltered caller falls through to the per-row spans, which is the
  safe direction.

The ten killed include rendering an unchecked chip as a clear one (2 tests),
dropping `NOT CHECKED` (1), cutting the "open question, not a negative result"
sentence (1), hoisting without comparing the sets (1), making the comparison
order-sensitive (1), keeping the per-row spans beside the hoisted line (2),
forcing the plural (1), printing a count the chips do not match (2), never
hoisting (3), and drawing the unchecked group when it is empty (1).

**The CSS carries guarantees vitest cannot see.** jsdom loads no stylesheet, so
"no fill" and "dashed" are unkillable from the suite. They are held by the
in-page audit below instead, and that asymmetry is worth knowing before
trusting a green run on anything in this file.

### Verified in the page, both themes

* **Zero colour offenders, 36 elements scanned, light and dark.** Every
  computed colour resolves to a declared token.
* Fill / no-fill, solid / dashed, and the mono tag confirmed by
  `getComputedStyle` rather than by screenshot.
* **The unchecked group was forced onto the live page by patching `fetch` at
  the transport layer** — same technique as §6z's gap markers — because
  neither stored report has an unassessed topic. Two injected topics rendered
  as dashed outlines with `NOT CHECKED` and the correct plural. Nothing was
  written anywhere; the patch was removed and the page reloaded before the
  final sweep.
* No horizontal overflow from either section at 375px; twelve chips wrap to
  twelve rows, widest 188px.

### FOUND IN PASSING, NOT FIXED — the header does not fit a phone

At 375px the page scrolls horizontally to **558px**, and none of it is these
two sections. The offenders are all in the header: `nav__user`, `theme-toggle`
and the sign-out `link` button do not wrap, putting sign-out at x=535 on a
screen 375 wide. Pre-existing, unrelated to this change, and reported rather
than folded into it. **This is a patient-facing screen and a phone is the most
likely thing it is opened on.**

### Also

* **`.guidance, .warnings { padding-left: 20px }` was split.** The new
  `.guidance` rule overrides it by order, and leaving the dead declaration in
  place is the unreachable-branch smell this project keeps deleting.
* Neither section had real coverage before this. The clear round-up and the
  entire guidance list had **no test at all**; the one test that existed
  asserted a wording. Eleven now, and they assert the markup — a test reading
  only the text passes with both groups rendered identically, which is the bug.

---

## 6ak. The header on a phone · 2026-09-12 · and the design system's dead `.nav`

Raised by §6aj's closing note: at 375px the page scrolled horizontally to
558px and `Sign out` sat at **x=535** — 160px off the right edge, on the
control that ends a session. Frontend suite **224 → 232**.

### FIXING THE PHONE AND LEAVING THE TABLET IS THE SAME DEFECT

The first fix scoped everything to `@media (max-width: 560px)`, measured at
375px, and looked complete. **It was measured against the wrong string.** The
browser happened to be signed in as `jaswanth` — eight characters. With the
project's own test-account email (`glossary.check+1788753613@example.com`, 37
characters) the header still overflowed **from 561px to about 890px**, with
`Sign out` at x=811 on an 800px window.

The signed-in identity is the ONLY variable-length item in a fixed row, so
truncation belongs at every width and not inside a breakpoint. It is declared
once in the base rule now; the phone query keeps only the row-two sizing.

`min-width: 0` is the load-bearing half and is easy to omit: a flex item
defaults to `min-width: auto` and **refuses to shrink below its content**, so
`overflow: hidden` on its own does nothing and the row grows instead.

> **The lesson, and it is not about CSS.** A responsive check run against
> whatever the session happened to be signed in as is a check against one
> string. The fixture that mattered was sitting in §6ai the whole time. **Test
> the longest value the system can actually produce, not the one on screen.**

Swept 320 / 375 / 414 / 560 / 561 / 640 / 720 / 800 / 900 / 1024 / 1280 with
the long email, driven in an offscreen iframe so the pane never had to be
resized eleven times: **zero overflow, sign-out and toggle on screen at every
width.** Ellipsis engages below 1024 and stops being needed above it.

### THE DESIGN SYSTEM'S HEADER RULES HAVE BEEN DEAD SINCE §6x

Found while reading `.nav`, and NOT FIXED — it changes the desktop header's
appearance and is the user's call. `styles.css` has **two** `.nav` blocks: §6x's
at ~206, and the pre-existing one at ~307. The later one wins on every shared
property:

| | §6x intended | Actually renders |
|---|---|---|
| background | `--header` | `--panel` |
| border-bottom | `--header-line` | `--panel-line` |
| padding | `18px 30px` | `12px 24px` |
| gap | `18px` | `16px` |
| `.nav__user` | 11px `--mono` | 14px `--muted` |
| `.nav a` | `--body` | `--ink` |

So §6x's *"distinct warm band so the page body reads as the working surface and
the chrome recedes"* is not on screen, and `.nav__user` is a hybrid — it kept
`font-family: mono` and `uppercase` from the older block's non-overridden
neighbours while losing the size and colour.

**§6x's own in-page palette sweep passed it.** Both rules use legitimate
tokens, so there were zero colour offenders. **A palette sweep proves no colour
is foreign; it cannot prove a rule won.** That is a real limit of the technique
§6x introduced and should be read alongside it.

This is also §6x's "ALIAS, DO NOT RENAME" discipline landing exactly one step
short: nothing was deleted, which was right, but the new block was added
*above* the old one, where it loses.

### THE SAME TRAP NEARLY ATE THE FIX

A media query adds **no specificity**. `@media (...) { .nav { ... } }` placed
earlier in the file loses to a later plain `.nav` on every shared property —
`flex-wrap` included. The phone block therefore has to sit BELOW the rule at
~307, and moving it up would be a silent revert with the code still present and
still looking correct.

That invariant is now a test rather than a comment: `design.test.jsx` reads
`styles.css` as source and asserts the phone block appears after every plain
`.nav {`. Mutating it to hoist the block kills that test.

### CSS IS INVISIBLE TO EVERY OTHER TEST IN THE SUITE

jsdom applies no stylesheet and evaluates no media query, so the round-up's
"no fill"/"dashed" absence treatment and all of the header behaviour were
**unkillable from a render test** — §6aj said so and left it to the in-page
audit, which is a one-off and does not run in CI.

`design.test.jsx` now reads `styles.css` as text and pins the invariants that
have an absence or an overflow behind them (+8 tests). Source-level assertions
are weaker than a rendered check and they are not nothing: they are the only
thing in the suite that can fail when one of these rules is quietly reverted.

### MUTATION-TESTED: 19 RUN, 19 KILLED — AFTER THE RUNNER WAS FIXED THREE TIMES

11 CSS guards, then 3 scoped re-runs, then 5 on the relocated rule.
**Every survivor on the first pass turned out to be a bug in the runner, not a
gap in the tests** — and each one had reported something false about a guard:

1. **A NUL byte** (§6aj) made one mutation report `pattern not found`.
2. **CRLF vs LF** made four more report `pattern not found` — every multi-line
   pattern, against a CRLF file.
3. **A non-unique pattern**: the two `.chip--clear` mutations SURVIVED because
   `background: var(--panel); border: 1px solid var(--panel-line);` also
   appears in `.card, .passage, .roundup, .lab-table` **earlier in the file**,
   so `replace(..., 1)` mutated that rule instead and never touched the chip.
   Scoped to the named rule, both die.

> **Three different ways for a mutation runner to lie in one task.** SKIP and
> SURVIVED are both claims about the runner before they are claims about the
> code. §6aj recorded "a SKIP is not a pass"; the `.chip--clear` pair extends
> it: **a SURVIVOR is not a gap until you have proved the mutation landed.**

One genuine gap did surface once the runner was honest: **dimming the cleared
chip's text off `--ink` survived everything.** The unchecked chip's colour was
pinned and this one was not, so the two could drift into the same ink while
fill and border still differed — quietly spending one of the three signals
that keep them apart. Tested.

### Still open

* ~~**§6x's `.nav` block is still dead.**~~ **FIXED on the user's word the same
  day — see §6al.** The two rules are merged into one, the older block is
  deleted, and `.nav` being declared exactly once is now a test.
* ~~`--mono` at 11px is **3.37:1** in light mode, below AA.~~ **FIXED §6am**
  — and it was worse than reported: `--muted` failed too, and `--amber` as
  text measured 2.28:1. All three fixed at the token.
* **A raw feature key reaches a patient**: the stored Vitamin B12 explanation
  reads *"Your vitamin_b12 test measures…"*. It is LLM text frozen at analysis
  time (§6ad/§6ag: changing a generator does not rewrite what a past run
  stored), so it needs a re-analysis to confirm any fix. Same family as the
  `PATIENT_LABEL` work in §6z, one layer further up.

---

## 6al. The design system's header, finally on screen · 2026-09-12

On the user's word, closing §6ak's open item. `styles.css` had **two `.nav`
blocks**; §6x's was above the pre-existing one and lost every property they
shared, so the header specified in `design.md` §4 had never rendered. Frontend
suite **232 → 236**.

Now live and measured in the page: `--header` ground, `--header-line` bottom,
18px/30px padding, 18px gap, the serif wordmark at 24px/400 in `--ink` with
only the italic `AI` in `--brand`, links 13px `--body`, the identity mono 11px
uppercase.

### THE MERGE'S REAL RISK WAS THE DELETED BLOCK, NOT THE KEPT ONE

§6x's rule was written as an ADDITION — it carried only the properties it
meant to change and relied on the block below for the rest. So deleting that
block naively would have taken three load-bearing declarations with it:

| Declaration | Lived only in the deleted block | If lost |
|---|---|---|
| `display: flex` / `align-items: center` | yes | the header stops being a row |
| `.nav__spacer { flex: 1 }` | yes | controls collapse left against the links |
| `.nav a { text-decoration: none }` | yes | **every header link gets the browser default underline** |

The third is the one worth remembering: §6x already had to fix
browser-default anchors once (its defect 2), and this would have reintroduced
them on every page, from a rule nobody would think to look at. All three are
folded into the surviving rule, each named in a comment at the point that
needs it, and each has a mutation.

**The old block is DELETED, not left in place.** Keeping it "just in case" is
precisely what made the design system's header dead for a month.

### §6x's OWN PADDING THEN BROKE THE ROW, AND NO TEST COULD HAVE SAID SO

18px/30px and an 18px gap leave the row tighter than the 12/24 they replaced.
The first thing a squeezed flex row does is wrap its own children's text:
**"Your details" and "Sign out" each split over two lines** from about 780px
down. That is not an overflow — no scrollbar, no offscreen element, nothing
for the width sweep to report — **it just looks broken**, and it was visible
only in a screenshot.

The header's labels are short and fixed, so they stay whole (`white-space:
nowrap`); the identity beside them is the one item that may shrink and it
already truncates rather than wrapping. **Shrink pressure now lands on the
only item designed to absorb it.**

Verified by counting rendered LINE BOXES per item (`Range.getClientRects()`),
not by element height: the first attempt used height ÷ line-height and
reported the theme toggle as wrapped at every width, because that button
contains an icon and padding. **A proxy measurement produces a defect that
isn't there just as readily as it misses one that is.**

### Widths and themes

Swept 320 / 375 / 560 / 561 / 640 / 720 / 781 / 800 / 900 / 1024 / 1280 with
the 37-character test-account email, in an offscreen iframe: **no overflow, no
wrapped label, sign-out and toggle on screen at every width.** Header palette
sweep: **zero colour offenders, both themes**, three font families (sans,
serif for the wordmark, mono for the identity) — which is itself the evidence
the serif wordmark is finally rendering.

### Contrast, measured on the new ground — one number fails

| | light | dark |
|---|---|---|
| wordmark | 11.49 | 15.00 |
| links / toggle | 5.97 | 8.12 |
| sign out | 4.78 | 8.13 |
| **identity, 11px** | **3.04** | 4.97 |

**The identity label fails AA in light mode at 3.04:1**, and restoring §6x
made it worse rather than better — it was 14px `--muted` before and is now
11px `--mono` on the darker `--header` band.

**Deliberately not changed.** `--mono` is §6x's own choice and `design.md` §4
asks for "metadata (mono, right)"; deviating silently would be editing the
user's design system while claiming to restore it. It is one token away from
fixed (`--body` measures 5.97 on the same ground) and belongs with the other
`--mono` finding in §6ak — both are the same app-wide question, and the
accessibility review §10 item 4 still calls for is where it should be settled,
once, rather than per-element.

### MUTATION-TESTED: 7 GUARDS, 7 KILLED

Including putting the deleted block back below (the exact regression), the
band reverting to `--panel`, the border to `--panel-line`, and each of the
three fold-ins dropped individually. `design.test.jsx` also now asserts
**`.nav` is declared exactly once** — two rules for one element is the shape
of the original fault, so the count is the guarantee.

> **What this one is really about.** The defect was not a wrong value; every
> value in both blocks was a legitimate token, which is why the palette sweep
> passed for a month. It was a rule that never applied. **Source-level
> invariants — how many times is this declared, does this come before that —
> catch a class of fault that neither a rendered audit nor a green suite can
> see**, and they are cheap. That is the lasting output of §6aj–§6al, more
> than any of the individual fixes.

---

## 6am. Text contrast · 2026-09-12 · three tokens, and the worst one never rendered

On the user's word, closing §6ak and §6aj's open contrast items. What began as
one token ended as three, because measuring the whole screen found more than
the thing that had been reported. Frontend suite **236 → 242**.

### THE ABSENCE LABELS WERE THE LEAST READABLE TEXT IN THE APP

Auditing every text node against its **effective** background (walking up for
the first non-transparent ancestor, not assuming) found **17 failures on one
screen**, all from two tokens:

| token | was | worst measured | now | worst |
|---|---|---|---|---|
| `--mono` | `#8a7c69` | **3.04:1** | `#655b4d` | 4.98 |
| `--muted` | `#7d6f5d` | **3.66:1** | `#6c6050` | 4.59 |

The text they carry is *"Not measured"*, *"not checked"*, and the reasons
underneath them. **On a screen whose entire purpose is that an absence must
not be mistaken for a result, the absence labels were the hardest thing on it
to read.** Fixed at the token, not on 17 elements — guarantees belong at the
lowest layer. Hue and chroma are unchanged (each is the original scaled toward
black), so the palette still reads as one family.

`--mono` is deliberately set DARKER than `--muted`: it carries 11px tracked
uppercase, which is harder to read than 13–14px prose at the same ratio. Dark
mode was already compliant on the same grounds (4.97–5.34) and is untouched.

> Worth knowing: dark has ALWAYS set `--muted` and `--mono` to one value, so
> the two converging in light would have been the system's own precedent, not
> a new problem. The gap was kept anyway, for the reason above.

### THE WORST DEFECT IN THE APP NEVER RENDERED DURING THE SWEEP

`--amber` measured **2.28:1 as text** — far worse than anything reported — and
it is the colour of `.flag--low`, `.verdict--low`, `.risk--medium`,
`.status--partial` and `.caveat`: patient-facing words in the results table.

**The route sweep passed it clean.** Neither stored report has a borderline
finding or a low-flagged value, so that text never rendered on any of the 12
route × theme combinations. It was found by computing the token table
directly, then confirmed by **forcing a `Borderline` topic and a low-flagged
row through the transport layer** so the text existed to be audited.

> **A rendered audit only covers the states your data can reach.** This is the
> §6z gap/rejected lesson and the §6aj unchecked-chip lesson arriving a third
> time: the fixtures do not produce every branch, so an in-page sweep is a
> lower bound on the defects, never a clean bill. Computing from the tokens
> covers the states the data cannot reach.

The fix is the pattern the palette had already invented and applied exactly
once: `--green-text` exists because *"--green does not pass 4.5:1 as text"*.
`--amber` had the identical problem and no such pair. Now `--amber-text:
#775200` (5.26:1), with `--amber` unchanged and still painting the gauge's
middle arc — geometry, not text.

### DARKENING A HUE TO PASS AA DRAGS IT INTO ITS NEIGHBOUR'S LUMINANCE

`--amber-text` and `--rust` differ by only **1.05:1** in luminance. The
stylesheet's header requires the three risk colours stay *distinguishable from
each other*, so luminance could not be the thing that separates them and the
first candidate had to be checked another way.

Chosen on **CIE Lab ΔE**, not luminance: `#775200` sits ΔE 28 from rust and 32
from green-text (a just-noticeable difference is ~2). Both are tested, because
a value that passes AA and collapses into rust would satisfy every other
assertion here.

### THE MUTATION THAT MATTERED: THE FIX WAS BYPASSABLE BY ONE ALIAS

8 token mutations. **T4 SURVIVED**: repointing `--medium` from
`var(--amber-text)` back to `var(--amber)`.

That restores the 2.28:1 defect in full, and every contrast test still passed
— because they check token VALUES, and **no stylesheet rule names
`--amber-text`; they all name `--medium`.** A guard over a list cannot see
what never entered the list (§6ad), in a stylesheet.

Now tested: `--low` → `--green-text`, `--medium` → `--amber-text`, `--high` →
`--rust`, `--absent` → `--mono`, asserted as the alias mapping rather than as
values. 8/8 killed after that, including inverting the mono/muted hierarchy
(both still AA, so only the hierarchy test catches it) and darkening
`--amber-text` into rust.

### The test, and what it deliberately does NOT check

`design.test.jsx` computes WCAG ratios from the hex values as written, for
both themes. jsdom has no colours and the in-page palette sweep only asks
whether a colour is *in* the palette — **a token that is in the palette and
too light passes that check every time**, which is how this survived §6x.

The token × ground pairs are a **measured table, not a cartesian product**.
The first version used the product and failed on `--green-text` over
`--header` at 4.11:1 — a pairing that does not exist, because the header holds
a wordmark, links, an identity and two controls and no verdict word. Tuning a
colour to satisfy a combination nothing renders is the same error as tuning
`--mono` against `--track`, which backs chart geometry and no text.
**Adding a pairing now means adding a row, deliberately, with a number.**

### Verified

* **0 AA failures across 6 routes × 2 themes**, re-run after the change with
  the transport patch removed.
* The forced borderline state: 0 failures in both themes, and the gauge's
  middle arc still resolves to the bright `--amber` — the chart vocabulary is
  untouched while the words are legible.
* Both `--mono` findings from §6aj and §6ak are now closed. `--ink`, `--ink-2`,
  `--body`, `--brand`, `--rust` and `--green-text` were already compliant on
  the grounds they are used on and were not changed.

### Still open

* `--rust` measures 4.38:1 on `--header` — below AA, but no verdict word is
  ever painted in the header, so it is not in the pair table. If a risk word
  ever moves into the header, that row has to be added and the colour
  revisited.
* ~~`/signin` was never audited.~~ **MEASURED, CLEAN — see below.**

### §6am-b. `/signin`, the route a signed-in session cannot reach

It had never been audited by anything, because every sweep runs from a live
session and `/signin` redirects. "Same tokens, therefore fine" was the
inference on offer and it is exactly the kind this project keeps being wrong
about, so it was measured instead.

**Reached without risking the session.** `AuthProvider` starts `signedOut`
when `hasSession()` is false and only calls `refreshSession()` when it is
true - so removing `localStorage['vaidyaai.refresh']` for the length of one
script renders the real sign-in page with **no logout call and no server-side
change**. The value is captured first, restored in a `finally`, and the
parent tab keeps its in-memory session throughout. Verified afterwards by a
full reload: still signed in, same token.

**Three states, both themes, zero AA failures:** the sign-in form, the form
carrying an `.error` paragraph, and the register view (Name / Email /
Password). The error was INJECTED with its real class rather than produced by
submitting bad credentials - a real failed login would spend an attempt
against the user's own account and could trip rate limiting. `.error`
resolves to `--rust`, which is 5.52:1 on the card.

**And it found one more alias gap.** `--danger` -> `--rust` was not in the
alias table, so repointing it was the T4 defect again with a different name:
`.error`, `.status--failed` and `.report__confirm-text` would all have
followed it anywhere. Now pinned; two mutations, both killed.

> The habit worth keeping: **a route your session cannot reach is a route
> nothing has ever checked.** Auditing from a signed-in browser silently
> excludes sign-in, registration and every error state on them - and those
> are the first screens a new patient sees.

---

## 6an. The long sections, put behind disclosures · 2026-09-12

The user: *"for the sections topics you could read about, what these results
mean give like hyperlinks ... when the user wants then only he can click
those, otherwise it is looking too long."* Frontend suite **242 → 248**.

Measured: the dashboard was **4,950px** and is now **3,745px** — **24%
shorter**, all of it from eight explanation paragraphs and one guidance list.

### WHAT MAY CLOSE IS A CLINICAL DECISION, NOT A LAYOUT ONE

The explanations section holds two different kinds of thing, and only one of
them may be hidden behind a toggle:

| | Treatment |
|---|---|
| the eight explanation paragraphs | `<details>`, closed, subject in the summary |
| *"…have no explanation above"* (§6ad) | **stays on the page** |
| *"No plain-language explanation could be prepared for…"* | **stays on the page** |
| *"your report lists N other tests it does not check"* | **stays on the page** |
| *"Written by a language model…"* | **stays on the page** |

**A reader who never opens a disclosure never learns what is inside it.** For
prose that is a saving; for a sentence reporting that something is MISSING it
turns the absence into silence — the one failure this page exists to prevent,
arriving through a layout change. The three absence sentences and the
provenance line are therefore outside every `<details>`, and each has a
mutation proving it.

The guidance section is the opposite case and closes **as a whole**: nothing
in it is an absence, the rows are a line each, and six toggles for six short
lines is more chrome than content. Its *"not personalised treatment advice"*
qualifier travels INSIDE with the items — it has nothing to qualify while the
group is shut. The count sits on the summary so opening it is an informed
choice.

Native `<details>`/`<summary>`, not a button and a state hook: keyboard
operable, correct role for a screen reader, and it still opens with no
JavaScript. The chevron is a CSS border rotated on `[open]`, so it cannot pick
up a font that lacks the glyph, and the global `prefers-reduced-motion` block
already switches its transition off.

### THE SUITE WENT GREEN ON THIS CHANGE AND COULD NOT HAVE TOLD ANYONE

All 242 tests passed on the commit that collapsed the section. **jsdom renders
the children of a closed `<details>` like any others**, so every existing
`getByText` still found text no reader could see.

That is not a small gap — it means the entire "is this sentence on the page"
style of assertion in `dashboard.test.jsx`, which is most of it, is blind to
whether the sentence is reachable. The new tests therefore assert DOM SHAPE:
`expect(said.closest('details')).toBeNull()` for each absence notice. Asking
*is this text present* cannot answer *can the reader see it*; asking *what is
it nested inside* can.

8 mutations, 8 killed — including moving each of the three absence notices
and the provenance line inside a disclosure, opening the explanations by
default, and emptying the summaries so the list becomes blank toggles.

### I REPORTED THIS BROKEN WHEN IT WAS NOT — THE PROBE WAS WRONG

Worth recording as a measurement failure, because it nearly shipped as a
false statement to the user.

`getBoundingClientRect().height` on the collapsed paragraph returns **100**,
and `offsetHeight` returns 100. On that evidence the conclusion was that the
browser pane does not implement `<details>` at all, and a "clean document with
no CSS" control was built to confirm it — **which used the same bad probe and
therefore agreed**. A control that shares the instrument's fault confirms the
error instead of catching it.

The screenshot disproved it: eight neatly collapsed rows. `checkVisibility()`
returns **false** for the same element. Chromium keeps the last-known layout
box for rect queries on content hidden by a closed `<details>`
(`content-visibility` semantics); `checkVisibility()` is the only probe that
answers the question asked.

> **Two rules from this.** A control has to differ from the thing it is
> checking in the way that matters, or it is a second run of the same mistake.
> And when a measurement and a screenshot disagree on this project, the
> screenshot has now won twice — once here and once on the wrapped nav labels
> (§6al), where a height-based probe invented a defect that was not there.

A second, smaller version of the same fault: the chevron's rotation was read
200ms after a 180ms transition and came back inverted. Re-read from explicit
`open` state with a longer settle, it is correct (45° closed, −135° open).
Nothing was wrong with the CSS.

### Verified

* Page height 4,950 → 3,745px; reopening everything restores 4,950 exactly.
* Both themes: all closed on arrival, content `checkVisibility() === false`,
  every summary and subject visible, **every absence notice visible**.
* Disclosure chrome: zero colour offenders across 54 elements, zero AA
  failures, `cursor: pointer`, default marker suppressed.
* Click opens, clicks closed again, summary is focusable.

### Known, and accepted

* **Find-in-page does not reach closed content** in browsers without
  `hidden=until-found` behaviour for `<details>`. The subject of every
  explanation is in its summary and stays searchable; the paragraph body is
  not. Accepted as the cost of the thing that was asked for.
* Closed content is not announced to a screen reader until expanded — which
  is the correct behaviour for a disclosure, and the reason the absence
  notices were kept outside one.
### §6an-b. The opened panel, read aloud — three faults in the reveal

The user circled the section OPEN: *"add some good design to this part also,
it is looking very odd and simple."* Measured against the live DOM, three
separate faults, all in the revealed state rather than the collapsed one —
**the state that had not been looked at.** Frontend suite **248 → 251**.

1. **The count was 680px from the heading it counted.** `.disclosure__summary
   > h2` is `flex: 1`, so the heading stretched to 672px and parked the badge
   at x=710, hard against the chevron, where it read as a second control
   rather than "there are three of these". A `__spacer` does the pushing now
   and the heading sizes to its text; the gap is 10px. Adjacency is the whole
   content of that badge, and it had none.
2. **The revealed content had no edge.** Three blocks landed straight on the
   page ground, so nothing said where the disclosure ended — the closing
   "not personalised treatment advice" qualifier in particular read as page
   text that merely followed the list. One panel now holds the attribution,
   the topics and the qualifier: opening the toggle produces ONE object.
3. **The rows were a pale left rule at 1.2:1** — the §6aj `--hairline`
   fault again, in the place it was moved to. Inside the panel they are
   bullet rows separated by hairlines, which read against `--panel`.

### THE ROWS ARE STILL NOT LINKS, AND THAT IS DELIBERATE

The section was asked for as "hyperlinks". The SUMMARY became a real control
and looks like one; the rows did not, because **there is nowhere for them to
go** — the catalog supplies a sentence, not a document. A row styled as a
link that does nothing when clicked is a worse answer than a plain row, and
on a page about someone's blood it invites the reader to believe there is more
to read about their result than there is.

So the marker is a bullet, not a chevron; the rows carry no hover state and
`cursor: auto`; and a test asserts the list contains **no anchor, button,
role=link, role=button or tabindex**. Mutation: turning the rows into `<a>`
elements is killed.

> If these topics ever gain real destinations, that test is the thing to
> change, and changing it should be a deliberate act — which is the point of
> writing the affordance down rather than leaving it as a styling accident.

### Verified

* Badge 10px from the heading; chevron still pinned right.
* Panel: `--panel` on `--bg`, 12px radius, qualifier divided by a hairline.
* Both themes: zero colour offenders across 16 elements, zero AA failures.
* 4 mutations, 4 killed: fake links, the badge moved back beside the chevron,
  the panel removed, and the qualifier moved out of it.

> **The pattern worth naming.** §6an collapsed the section and verified the
> COLLAPSED state carefully — heights, visibility, absence notices — and never
> looked at the open one. A disclosure has two states and shipping it means
> reading both. Every fault above was in the half nobody opened.
### §6an-c. The population page's method notes — panelled, NOT collapsed

Same complaint, circled on the population page: three stacked `.hint` blocks
(browser bullets, no container, one flat grey) ending the page in a wall, with
the closing disclaimer reading as text that merely followed the list.
Frontend suite **251 → 257**.

### THE ANSWER THAT WORKED ON THE DASHBOARD IS THE WRONG ONE HERE

The obvious move — and the consistent-looking one — is the disclosure from
§6an. **It must not be used.** These bullets are the CAVEATS on the comparison
above them, and §6ag is explicit: what may never go is the caveat. This
platform has found it missing three separate times and recorded it each time
as the worst thing on the page. **A caveat behind a toggle is a caveat most
readers never open — the same outcome as deleting it, reached more slowly.**

Length was the complaint; hiding is not the only answer to it. So: one panel,
a heading, the shared bullet rows, and the disclaimer divided off by a rule as
the conclusion OF the bullets rather than a remark after them — the same
shape as `.passage__close` on the clinician page, which solved this exact
problem for that document.

A component test now asserts `.notes` is **not** a `<details>` and contains
none. If it ever becomes one, that assertion has to be deleted first, by
someone who has read why it is there.

### ONE ROW RULE, TWO CALLERS — NOT A SECOND COPY

The limitations wanted exactly the treatment the guidance topics had got an
hour earlier. Copying it would have been **the third duplicated rule this
stylesheet has had to reverse** (§6z's band rule, §6al's two `.nav` blocks — the
second of which cost a month of the header being dead).

So `.guidance > li`'s styling was promoted to a shared **`.bullets`**, the
in-panel override was deleted, and both pages now point at it. Two tests hold
it: the invariant it always carried (no risk colour on a decorative mark,
asserted on the row AND the `::before` dot) and a new one — **`.bullets` is
defined exactly once, with no page-scoped override** — which is the `.nav`
lesson written down as a guard rather than as a paragraph.

The existing test that pinned `.guidance > li`'s left rule was rewritten to
follow the rule to its new home. Worth noting honestly: that is the third
time on this project a test has been edited to match a refactor, and the
protection against that is exactly what was done here — the INVARIANT was
kept identical and only the selector moved.

### Verified

* Both themes, both pages: zero colour offenders, zero AA failures.
* Rows `cursor: auto`, panel is a `<section>`, close rule present, no
  horizontal overflow.
* The dashboard's guidance panel re-checked after the refactor: 3 rows, dot
  `rgb(123,88,54)` = `--brand`, hairline separators intact.
* **6 mutations, 6 killed** — the panel turned into a disclosure, the
  disclaimer moved out, the panel gated on limitations alone (which silently
  loses the disclaimer), the population list dropped off `.bullets`, a second
  copy of the row rule reintroduced, and a risk colour spent on the dot.

> **A `[no tests]` result is a PARSE ERROR, not a kill.** Two mutations this
> session reported it, both because the JSX I generated was unbalanced — the
> compiler caught them, no test did. Re-run well-formed, both genuinely died.
> This is the SKIP rule from §6aj in a third costume: KILLED, SURVIVED, SKIP
> and `[no tests]` are all claims about the RUNNER before they are claims
> about the code.
### §6an-d. Twenty-one lines saying three things — the population cards

The user circled the repeated prose on the comparison cards: *"see all are
repeating sentences ... do the need innovatively."* Frontend suite
**257 → 269**, plus a new component.

**Measured on the live payload first, not assumed.** Seven comparison cards,
each carrying three lines:

| line | unique values across 7 cards |
|---|---|
| `Compared with: 20-29 years, male` | **1** — byte-identical |
| `what_this_means` | 7, differing ONLY by the interpolated parameter name |
| `what_this_does_not_mean` | 7, same |

So: twenty-one lines saying three things. The cohort is chosen from the
patient's own age and sex, so it cannot differ between parameters on one
report; the other two are one sentence template each.

### THE FIX IS NOT DELETION, IT IS RELOCATION AND A PICTURE

**One method statement above the list**, carrying the cohort and both
sentences. For the caveat this is BETTER placement, not merely less of it:
it is now read BEFORE the first band rather than after each one. It is a
`.method` panel in body ink, deliberately **not** a `.hint` — demoting the
only surviving copy of a caveat to the page's quietest type is how a caveat
stops being read, and a mutation doing exactly that is killed.

**And each card gained `PercentileBar`** — the 0-100 scale with the published
band drawn on it. That is the innovation the repetition was hiding: the cards
needed something ABOUT THEIR OWN RESULT, and "between the 50th and the 75th"
is the one thing on the card a reader has to do arithmetic to picture.

Three rules inside it, all of them this project's existing ones:

* **No risk colour, ever.** The page says a percentile "does not say whether
  a result is normal, high, or low" — a green or rust segment two inches
  below that sentence contradicts it. The fill is `--brand`.
* **A band, not a point.** Module 31 publishes cut-points and interpolates
  nothing; its own limitations list says a band is reported precisely because
  the estimates carry sampling uncertainty. A single marker would invent the
  precision the service refuses.
* **An open end runs to the frame and is not capped.** "Below the 5th
  percentile" has no published floor, and a closed segment from 0 asserts a
  bound nobody published — the one-sided-interval fault of §6ab and §6z, third
  appearance.

### READING THE PRODUCER PAID FOR ITSELF IMMEDIATELY

`band.position` is **`"between_published_percentiles"`**, not `"between"` —
the Python constant is `POSITION_BETWEEN` and its VALUE is the long string.
Guessing from the constant name would have produced a component that matched
nothing and rendered no bar at all, on every card, silently. That is §6ag's
guessed-field-name defect exactly, and it was avoided only by fetching the
real response and printing `Object.keys(band)`.

### The hoist is guarded, and the guard is clinical

`sharedCohortLabel` hoists ONLY when every available comparison agrees.
Module 31 matches on (sex, age band) and refuses rather than falling back, so
a table with different age bands per parameter is possible — and one line
above the list saying "20-29 years" over a card compared against 30-39 would
**misstate which population the reader is being measured against**. Unequal
cohorts put the line back on every card. Same shape as the dashboard's
`sharedBecausePhrase`.

### MUTATION-TESTED: 9 GUARDS, 9 KILLED

Hoisting unequal cohorts, demoting the method statement to `.hint`, dropping
the caveat clause, showing the statement with no bars on the page (§6ac's
legend-for-a-mark-that-is-not-there), printing both the hoisted and per-card
cohort lines, a risk colour on the band, drawing an unrecognised position,
capping an open end, and drawing a `between` band missing one end.

### Verified, and one boundary stated

* 21 repeated lines → **0**; one method statement; 7 bars; no overflow.
* Both themes: zero colour offenders, zero AA failures, band fill resolves to
  `--brand` in each.
* **NOT LIVE-VERIFIED: both open-ended positions.** Every value on both
  stored reports lands `between_published_percentiles`, so `below_lowest` and
  `at_or_above_highest` have never been rendered from real data. They are
  covered by tests and are reachable the moment a value falls outside the
  published grid — the same boundary §6z recorded for timeline gaps.

> **A third probe error, and the pattern is now unmistakable.** The palette
> sweep reported ~60 offenders: every one was `fill: rgb(0,0,0)` on a `<line>`
> or on an HTML `<p>`, where `fill` is a UA default that paints nothing. Like
> the `getBoundingClientRect` reading of a closed `<details>` (§6an) and the
> height-based wrap check (§6al), **the instrument invented a defect that was
> not there.** Scope `fill` to elements that actually fill.
### §6an-e. The progress card, in plain English — and the FIRST ai-service edit

The user asked what the score shows, then asked for the card in simple
English with nothing unnecessary. Frontend **269 → 279**; ai-service
**3,765 pass, 7 skipped** — the exact baseline, re-run in full because shared
strings moved.

**The jargon was authored in the SERVICE, so it was fixed there** (§6ae's rule:
rewrite where it is written, never paraphrase downstream where two statements
of one fact drift apart).

| was | now |
|---|---|
| "...the direction the polarity table records as favourable" | "...moved in the better direction" |
| "against the stability band declared for that parameter" | "A change has to be big enough to count at all." |
| "take no part in the classification and appear only in the returned series" | "...not included, though it still appears on the chart above" |
| caveat, 5 sentences / ~90 words | 2 sentences, **every claim kept** |

`polarity table` and `stability band` are FILES IN THIS REPOSITORY. Naming
them on a patient's results page is this platform's most repeated defect —
§6u, §6w, §6af, and now a fourth time in a fourth place.

### THE CARD SAID "HIGHER IS BETTER" TWICE IN ONE BREATH

`Timeline.jsx` rendered the literal `"Higher is better. "` immediately in
front of `direction_text`, which itself opened *"The scale runs from 0 to 100
and HIGHER IS BETTER"*. Not a wording preference — a duplication in the
markup. And the band DESCRIPTION restated its own label in longer words, so
it is no longer rendered (the field is untouched on the API).

### WHAT WAS KEPT, AND WHY IT IS NOT NEGOTIABLE

* **The caveat.** Shorter, never weaker: not a health score, not a risk
  score, not a diagnosis; nothing about what to do; only movement between two
  reports; cannot see what was not measured on both; ask a professional. All
  six claims survive in two sentences. §6ag: shortening is not the same
  decision as dropping, and this class of sentence has gone MISSING three
  times on this project.
* **The coverage line** — an absence. "8 of your 12 results ... the other 4
  could not be compared this way". `parameter(s)` is gone; the counts choose
  the wording.
* **The floor** ("at least 3 are needed") now appears ONLY when it is the
  reason there is no score. Under a score built from 8 it answered a question
  nobody asked.

### `ScoreScale`, and the colour it may not use

A bare "62.5 / 100" makes the reader place the number themselves. The marker
is `--brand`: **the card's own text says this is not a risk score**, and a
green marker at 80 with a rust one at 20 would contradict that sentence two
inches below it. No band boundaries are drawn either — four gridlines at
20/40/60/80 would invite a reader to treat the nearest as a threshold, and
they are labels for reading the number, not clinical cut-offs.

### A REPETITION THE REDESIGN EXPOSED: Module 30 inherits Module 29's warnings

Measured in the live DOM after the rewrite: *"This comparison uses two of your
reports..."* printed on the comparison card AND the progress card, because
the progress payload carries Module 29's warnings too. The progress card now
renders only the warnings the comparison card did not — filtered by **exact
text against what was actually rendered**, never by index, so a warning unique
to progress still appears. Both directions are tested.

### MUTATION-TESTED: 9 GUARDS, and the survivor was a WEAK TEST

**P1 SURVIVED**: putting the `"Higher is better."` literal back. The test
counted occurrences of the phrase and allowed one — and since the REWRITTEN
service sentence no longer contains that phrase, the prefix was the only copy
and the count was still 1. **Counting a phrase cannot catch a page prepending
its own words to an author's sentence; equality can.** The assertion is now
`meaning.textContent === data.scale.direction_text`, and P1 dies.

Also killed: the band description restored, the caveat dropped, the coverage
line dropped, the excluded-count clause dropped (an absence going silent), a
risk colour on the marker, an out-of-range score drawn anyway, the warning
filter removed, and the filter swallowing everything.

### THREE AI-SERVICE TESTS PINNED THE OLD WORDING

Each was rewritten to assert the INVARIANT rather than the sentence — §6ag's
warning about editing a test to follow a note, which has now happened four
times here. The three denials in the caveat, the size-does-not-scale claim,
and "the middle report is in the series and contributes nothing" are each
asserted in whichever words carry them, with the old phrasing still accepted.

### Process notes

* **`assert_safe` guards this text** and passed first time — then was PROVED
  live by feeding it two known-bad strings and watching it refuse. A guard
  that has not been seen to fail has not been seen to work.
* **The ai-service was restarted before any live check**, and the new strings
  confirmed on `/progress/policy` before touching the browser.
* **A `[no tests]` result is a parse error, not a kill** — third and fourth
  occurrences this session. One was my own test file: an escaped apostrophe
  did not survive the edit and broke the transform.
* **The backend rate-limited me** (history: 60 requests / 15 min; the timeline
  costs 4 per load). Not a defect — my own reloading. The limiter is
  in-memory, so restarting the backend clears it, which is faster and more
  honest than waiting out a window.
### §6an-f. "Save changes did nothing" — it did. The page never said what it does.

The user, on the profile page: the two diagnosis questions *"after clicking
save changes also are like that only, not changed ... looks something odd"*.
Frontend **279 → 286**.

### THE SAVE IS NOT BROKEN, AND THAT WAS WORTH PROVING FIRST

Driven end to end in the browser: selected **No**, the PUT sent
`{"hypertension":false}`, the server returned `hypertension: false` with 200,
and the answer **survived a full reload still showing No**. The tri-state
control, the payload builder, the validator and PUT's replace semantics are
all correct. The profile was restored to exactly the state it was found in
(both unanswered) once the check was done.

**So the report was right and the diagnosis was wrong.** What is odd is not
the saving; it is that saving VISIBLY ACHIEVES NOTHING:

### THE REAL CAUSE: the answers do not reach a report already analysed

`analysisService.buildProfilePayload()` reads the profile **at analysis
time** and the result is stored on the report. So a reader who answers these
two questions BECAUSE the dashboard told them *"no value was available for
your history of heart disease and history of high blood pressure"* goes back
to the dashboard, sees the identical sentence, and concludes the form is
broken.

Nothing on the page said so. It does now, next to "Saved.", where the
expectation actually forms:

> *These answers are used the next time a report is analysed. Reports you
> have already analysed keep what was known when they ran, so their results
> do not change.*

**This is the fourth appearance of one standing property** — the explanation
cap (§6ad), the clinician narrative (§6ag), the model notes (§6ae), and now the
profile answers: *changing an input does not rewrite what a past run stored.*
The first three were recorded as facts for a developer. This is the first
time it has been said to the person it actually surprises.

### AND A RAW DOCUMENT KEY AT A PATIENT

The completeness line read **"Still blank: heartDisease"** — a Mongo field
name shown to the person whose heart it is. Same defect as `vitamin_b12`
reaching a reader (§6ak), one layer up. Now "diagnosed heart disease",
matching the question the form asks above it so a reader can find the thing
they are told is missing.

`PROFILE_FIELD_LABEL` is kept SEPARATE from `PATIENT_LABEL` deliberately:
that table is keyed by Module 5's snake_case feature names
(`heart_disease`), these are Module 2's camelCase document keys
(`heartDisease`). One table answering to two key styles is exactly how a
lookup misses and prints the raw key — the defect being fixed.

### The two questions no longer look unfinished

A bare `<fieldset>` draws its border THROUGH its own legend and has no
ground of its own, which is why these two read as unstyled next to the
inputs above them. They now sit on `--bg` inside the card with the legend as
an ordinary heading, and each option is a full-width row with a hit area —
the labels always wrapped their inputs, so the whole row was already
clickable; it just did not look like it, and on a phone a 7px radio was
otherwise the entire target. No risk colour: "yes, I was diagnosed" is an
ANSWER, not a finding, and tinting it would make the form look like it was
judging the reply.

### THE PROFILE PAGE HAD NO TESTS AT ALL

None. On the page holding the two answers the heart model names as its
single biggest limitation. Its own comments stated three guarantees that
nothing checked — and **a comment asserting a guarantee is not a
guarantee**, which this file has now caught four times:

1. a stored `false` round-trips as "No", never as "Not sure";
2. "Not sure" is sent by OMITTING the key, because the validator rejects an
   explicit null with a 422 the patient cannot act on;
3. `false` IS sent, because it is a real answer.

`tests/profile.test.jsx`, 7 tests. **7 mutations, 7 killed** — including
reading a stored `false` as unknown, defaulting an absent answer to No
(an absence becoming a value, on the page where it would originate),
sending the null that 422s, dropping a real "No" from the payload, removing
the note, and printing the raw keys again.

> **Worth carrying:** the bug report was accurate and the cause was not the
> one it named. Proving the save worked BEFORE changing anything is what
> stopped a correct payload builder being "fixed".
### §6an-g. The two diagnosis questions, collapsed — and the legend that never fitted

The user: the boxes are *"placed"* wrongly, and after Save they should CLOSE,
reopening only when the reader wants to change something — *"don't make open
those 2 every time"*. Frontend **286 → 294**.

### THE PLACEMENT FAULT WAS `<legend>`, AND IT HAS NO CSS FIX

A user agent paints a `<legend>` **over its fieldset's top border**. That is
invisible while the box has no background and unmissable once it does — which
is what §6an-f's restyle had just given it, so the heading sat half on the
border with the line running through the text. Every fix for it is a float
hack.

`<details>` has no such element and no such problem, and the change was
already wanted for the collapse. **One change answered both halves of the
request.**

THE GROUPING IS NOT OPTIONAL AND WAS NOT DROPPED. `<fieldset>` is what tells
a screen reader three radios belong to one question; `role="radiogroup"` plus
`aria-label` carries it, and is tested. A bonus: the question is now announced
ONCE, where a summary plus a legend would have said the same words twice.

### CLOSING IS ONLY SAFE BECAUSE THE ANSWER IS ON THE SUMMARY

The condition attached to the whole request. Each row reads
**"Diagnosed heart disease — Not sure / prefer not to say"** while shut, so:

* nothing is hidden that a reader would otherwise have to open both boxes to
  find;
* an UNANSWERED question stays visible as unanswered — the one thing this
  form exists to prevent going quiet.

A collapsed question that concealed its own answer would be more work than
the open version, not less.

### THE STATE IS NOT DERIVED FROM THE ANSWER, DELIBERATELY

Opening the boxes that are still blank is the obvious "helpful" move and it
is wrong twice: it nags someone who deliberately chose *prefer not to say* on
every single visit, and it springs both boxes open again the instant a save
completes — which is precisely the behaviour being removed. Closed on
arrival, closed after save, opened only by the reader. A mutation deriving
the state from the answers kills three tests.

### MUTATION-TESTED: 15 GUARDS, and the survivor was the dangerous one

**R4 SURVIVED**: flipping `answerLabel`'s fallback from *Not sure* to **No**.
That renders an unanswered question as an ANSWERED one — an absence turned
into a value, on the form where that would originate, and the single worst
thing this page could do.

It survived because `null` matches the third option, so the fallback is only
reached by a value that is none of true/false/null — and the form normalises
to those three with `?? null`, so **no rendering test can produce the shape**.
Reaching it needs the exported function. `answerLabel` is now tested directly
against `undefined`, `'yes'`, `1`, `0` and `{}`, and both R4 and "delete the
fallback entirely" die.

> **The pattern, third time this session.** A guard that only fires on a shape
> the UI cannot construct is invisible to every UI test — §6ad's "a guard over
> a list cannot see what never entered the list", §6am's alias that no value
> test touched, and now a fallback no render can reach. When a mutation
> survives, ask WHICH INPUT would reach the mutated line, and test at the
> layer that accepts it.

Also killed: boxes open by default, boxes not closed after save, the answer
removed from the summary, the radiogroup role dropped, and the boxes
re-opening because an answer is missing.

### Verified

* Live: clicking one summary opens THAT one only; choosing No and saving
  leaves both shut with the summary reading "No". Profile restored to
  unanswered afterwards, as found.
* Both themes: zero colour offenders; question 12.7:1 / 16.1:1, answer
  5.08:1 / 5.34:1 against the box.

> **Not a defect, but worth stating:** these two questions are the heart
> model's single biggest declared gap, and they are now one click further
> away. The summary keeps the absence visible and the completeness line still
> names them, so nothing is concealed — but if answer rates matter, this is
> the change that would move them.
### §6an-h. "Clumsy" was two blocks in contact, on four screens

The user circled the top and bottom of the profile page: *"these look clumsy,
add some space between them."* Frontend **294 → 295**.

Measured before touching anything, and it was not a padding judgement:

| pair | gap |
|---|---|
| profile intro → the form card | **0px** |
| "used the next time a report is analysed" → Save changes | **0px** |

**Two elements literally touching.** Cause: `.hint { margin: 4px 0 0 }` — no
bottom margin at all, so anything following it that sets no top margin of its
own sits flush against it.

### IT WAS NEVER ONE SURFACE, AND THE SWEEP SAID SO BEFORE THE FIX

Walked every `.hint` on four routes looking for a following sibling within
4px. **Four collisions on two routes**, all the same rule:

* `/profile` — intro against the form;
* `/timeline` — intro against the first panel, the trend summary against its
  chart block, and the comparison lead against the results table.

So the fix went to the rule, not the page (§6am's lesson: app-wide is a reason
to fix it at the lowest layer, not a reason to patch one screen). The 4px TOP
is deliberately kept — a hint belongs to the thing above it, and pushing it
away would attach it to the wrong subject. A mutation doing that is killed
alongside the one that removes the bottom.

**The bottom margin is a FLOOR, not an addition.** Adjacent margins collapse
to the larger of the two, so every place that already set more spacing keeps
exactly what it had — nothing that was correct became looser. Re-measured
across all four routes afterwards: zero collisions.

### A FIFTH PROBE ERROR, AND THE SAME SHAPE AS THE OTHER FOUR

The re-sweep reported eight fresh "collisions" on the dashboard at **-18px**
— the explanation summaries' heading against their chevron. They are FLEX
SIBLINGS ON ONE ROW, 9px apart horizontally; my probe compared vertical gaps
and read a neighbour as an overlap.

> That is the fifth measurement this session that invented a defect: the
> `getBoundingClientRect` reading of a closed `<details>` (§6an), the
> height-based wrap check (§6al), `fill` on a `<line>` (§6an-d), the
> mid-transition chevron (§6al), and now a vertical gap between horizontal
> siblings. **Every one was disproved by looking at the screen.** The probes
> are still worth having — they found the four real 0px gaps that no
> screenshot would have measured — but a probe's output is a claim about the
> probe until a second, different observation agrees with it.

### Also

The profile's closing block was three touching lines under the last question.
"Saved." and its note are ONE thing and are grouped as one (4px apart); the
button is the next thing and is separated (20px), as is the block from the
questions above it (20px).

A mistyped command also ran `vitest` from the REPO ROOT rather than
`frontend/`, which collected the backend's Jest files and reported 225
failures. Nothing was wrong and nothing had been written — the python step
before it had already failed on a missing path. Worth knowing because the
output looks catastrophic: **a suite run from the wrong directory fails
everything, and says nothing about the code.**
### §6an-i. "Why is Module 2 here?" — the leak was in four labels, then eleven more

The user, on the comparison table: **"Self-described gender as stored by
Module 2."** — *"y module 2 came here?"*. ai-service **3,765 → 3,768**,
frontend **295 → 297**.

### IT WAS A KNOWN, OPEN DEFECT — AND IT WAS FOUR, NOT ONE

§6ai listed it: *"`feature_catalog`'s `display_name` for `gender` being an
internal note"*, worked around in three places and never fixed at source.
Reading the catalog, **four** of the fourteen entries put a maintainer's note
in the field the nine laboratory entries use as a LABEL:

```
gender           Self-described gender as stored by Module 2.
smoking_history  Smoking history, diabetes-dataset categories.
hypertension     Known hypertension. TRI-STATE: true / false / absent(unknown).
heart_disease    Known heart disease. TRI-STATE: ...
```

Two of those were on the screen the user photographed. The other two would
have printed an implementation contract the moment they appeared. And the
field is not only rendered — `rag/query.py` feeds it to the retriever as a
**search term**, so "as stored by Module 2" was also polluting retrieval.

Fixed at source. The facts the notes carried are real and are kept, as
comments, which is where a note to a maintainer belongs. "Self-described" is
deliberately retained in the label: it is the patient's own answer rather
than a clinical determination, and only the module number goes.

### THEN THE SAME AUDIT FOUND THE TABLE ABOVE IT, AND A THIRD MODULE

Sweeping the page for the same class:

* **The trends table printed RAW FEATURE KEYS** — `hba1c`, `blood_glucose`,
  `vitamin_b12`, `smoking_history` — while `PATIENT_LABEL`, already imported
  in that very file, titled the charts above them "HbA1c (average blood
  sugar)". One screen, both vocabularies, twelve rows apart.
* **`trend_analyzer.py` interpolated the raw key into eleven reader-facing
  sentences**: *"blood_glucose went from 186 to 88"*, *"smoking_history is a
  category feature"*. All eleven now route through the catalog label.
* Two more sentences named files: *"declared not trendable in the polarity
  table"* and *"Reason recorded in the polarity table"*. The reason itself is
  useful and is kept verbatim; only the filing cabinet goes.

**That is the fifth and sixth surface.** §6af's standing rule was *when a fix
is "remove this system's vocabulary from a reader-facing surface", it is never
one surface.* The corollary this adds: **finding one is a reason to sweep the
whole screen it is on, and then the producer behind it.**

### THE GUARD IS AT THE CATALOG, WHERE NO RENDER TEST COULD SUBSTITUTE

Three tests in `test_feature_catalog.py` scan the table itself: no label may
contain "module", "tri-state", "dataset", "true / false"; **no label may end
in a full stop** (a label is a noun phrase — the full stop was the tell that
a sentence had crept in, and both offenders had one); and no label may be
empty. 4 mutations, 4 killed.

### TWO RUNNER FAULTS, AND ONE OF THEM CORRUPTED A FILE

1. **All four catalog mutations first reported SURVIVED.** The runner passed
   a LIST argv with `shell=True`, which on Windows executes only the first
   element — pytest never ran, produced no output, and "no failure" was read
   as "survived". Re-run with `shell=False`: 4/4 killed. **Sixth runner fault
   this session**, and the first that inverted a result rather than skipping
   it.
2. **A regex insertion put a new function INSIDE the module docstring**,
   splitting a sentence, because the first match for `_TEMPLATES` was a
   mention in that docstring rather than the assignment. Caught by reading
   the file after writing it. Anchor on the DEFINITION
   (`^_TEMPLATES\s*=\s*\{`), never on the first mention of a name.

### Verified

* ai-service **3,768 pass, 7 skipped**, run in full twice (shared strings).
  Frontend **297**. ai-service restarted before every live check.
* Live page sweep for `hba1c`, `blood_glucose`, `vitamin_b12`,
  `smoking_history`, `heart_disease`, `vitamin_d`, "polarity table",
  "Module 2", "diabetes-dataset", "TRI-STATE": **all gone**.
* Both tables read properly: trends as "HbA1c (average blood sugar) / Blood
  sugar / Sex", comparison as "Glycated haemoglobin, NGSP % / Self-described
  gender".

### STILL OPEN

* **"stability band"** survives in the trend sentence (*"That clears the
  declared stability band for this feature (17 % and 5 mg/dl)"*). Left
  deliberately: unlike a module number it is a real concept shown WITH its
  own numbers, so replacing it is a wording decision rather than a leak fix.
* `origin: report_transcription` on profile rows (§6w) is still open at
  source — the other half of §6ai's pair.
### §6an-j. The nine trend charts, collapsed — and a contract I broke on the way

The user: give the trend charts the same disclosure as "What these results
mean", *"these are taking too long space in the page"*. Frontend
**297 → 300**, ai-service **3,768 → 3,770**.

Nine charts at ~200px each. Page **6,156 → 4,298px, 30% shorter**.

**Closing is safe only because the summary states the DIRECTION** —
"HbA1c (average blood sugar) — improving". A shut list that hid its own
directions would make a reader open nine boxes to learn what the open list
told them at a glance. Same condition as the profile questions (§6an-g).

The direction comes from `outcome === 'TREND_CLASSIFIED' && isPresent(trend)`,
the SAME two-part predicate the table uses — never `trend.trend` alone.
§6z: a payload carrying a direction without a classification printed the
string "null" as a direction once already. 4 mutations, 4 killed.

### I BROKE THE API CONTRACT, AND 3,768 TESTS DID NOT NOTICE

The worst thing in this entry, and it was mine.

§6an-i routed eleven `feature=feature` occurrences through a label helper with
a blanket regex. **Ten were message templates. The eleventh was the response
object:**

```python
return FeatureTrend(
    feature=_label(feature),   # <- the canonical key, replaced by a label
```

So `GET /trends` began returning `feature: "Glycated haemoglobin, NGSP %"`
where `hba1c` belongs. Every consumer keys off that field: the frontend's
`PATIENT_LABEL[trend.feature]` lookup missed, fell through to the raw value,
and the chart headings silently reverted to the clinical register.

**The full suite passed.** 3,768 tests, and not one asserted that the field a
dozen consumers index by is the key they index with. It was found by reading
the rendered page — noticing that the chart said "Glycated haemoglobin,
NGSP %" while the table under it said "HbA1c (average blood sugar)".

> **Two names for one parameter on one screen is a symptom, not a style
> issue.** It was the only visible trace of a broken contract.

Two tests now hold both halves, and both are needed: pinning only the key
lets the messages regress to raw keys, and pinning only the messages is what
let the key become a label. 5 mutations, 5 killed.

### THE TEST FOR THE MESSAGES TOOK THREE ATTEMPTS, EACH WRONG DIFFERENTLY

1. **One fixture** — a healthy three-reading series only ever produced the
   `change_line` template, so reverting any OTHER message survived. Four
   scenarios now drive four templates.
2. **Plain substring** — flagged the CORRECT "Serum creatinine" for
   containing "creatinine". A false positive from the test, on working code.
3. **Snake_case only** — caught `blood_glucose` but not single-word keys
   like `hba1c`, so two mutations still survived.

The signal that actually works: **every one of these templates OPENS with the
feature name**, so a raw key appears as the first token. `startswith(key)`
separates the key from a label that merely contains the same word.

### AND I HIT THE STALE-PROCESS TRAP THE NOTES WARN ABOUT

After reverting the contract break I ran the suite, wrote tests, ran
mutations — and checked the browser **without restarting the ai-service**.
The page still showed the old labels, and for a moment that looked like the
revert had failed. It had not; the process was three edits old.

MEMORY has warned about this since §0 and it has now cost time six times on
this project. **The rule is not "restart after changing the service" — it is
"restart before BELIEVING the browser".** The two are different: I had
restarted after the earlier edits in this same session and still got caught,
because the check came after a LATER edit.

### Verified

* 9 charts closed on arrival, each summary naming its parameter and
  direction; page 30% shorter; reopening restores the full height.
* **Chart headings and table rows now agree** — asserted in the live DOM,
  not assumed.
* ai-service **3,770 pass / 7 skipped**; frontend **300**.
### §6ao. The parameters this tool does not assess, given the laboratory's own limits

The user asked whether an out-of-catalogue parameter could be assessed by
Gemini, was told why not, and then specified the safe version himself: **use
the reference ranges printed in the report, diagnose nothing new, and show
these parameters in "Your results" and "What these results mean" like the
rest.** Frontend **300 → 312**. No backend or ai-service change.

### WHAT WAS REFUSED, AND WHY IT MATTERED

The original proposal was *"compared with usual limits **using Gemini**"*.
A model-supplied reference range is not wording — it is an invented clinical
threshold, and **this platform has shipped that defect once already** (§6v: an
empty `permitted_numbers` turned the validator's numeric control OFF and let
an invented range through). The limits here are the LABORATORY'S, already
extracted by Module 4 and already in the dashboard payload
(`labReferenceLow/High`, `labFlag`). The comparison is arithmetic.

**Nothing needed to be built in either service.** The whole feature was a
rendering change over data the backend had carried for sessions.

### A RECORDED DECISION WAS REVERSED, DELIBERATELY AND NOT QUIETLY

`Dashboard.jsx` said, in the code: *"NOT MERGED, deliberately: those four are
described from the test NAME ONLY ... Putting them in a list whose other
entries interpret the reader's own values would invite the inference the
whole architecture exists to prevent."*

That reasoning is correct **about the list**, and it is why these are a
SEPARATE GROUP with its own heading, its own verdict vocabulary and an
explicit "your result was not used and is not interpreted here" — not
interleaved rows. What changed is the judgement that burying a laboratory's
own abnormal marking at the foot of the page was the safer of the two errors.
It is not. The old comment's reasoning is preserved where the new group is
defined.

### THREE SEPARATIONS, EACH ONE TEST AWAY FROM COLLAPSING

1. **The limit is the laboratory's**, never invented, and attributed IN THE
   CELL rather than only in a heading far above.
2. **The marking never borrows the verdict palette.** `--green/--amber/--rust`
   mean THIS TOOL crossed a threshold it holds; nothing here was assessed by
   this tool. The group contains zero `.verdict` elements, asserted.
3. **The description is about the TEST, not the value**, and is labelled as
   such where it sits. That label is what makes inclusion safe, so it is not
   decoration and has its own test.

### I SHIPPED A BUG INTO THE CELL ADDED TO SURFACE REAL FINDINGS

The first version printed the comparison only when a range existed, so a
result **the laboratory had marked abnormal with no printed interval** fell
through to "no range printed" and **lost the marking entirely**. An absence
swallowing a real finding, in the one cell built to stop exactly that.

Laboratories routinely flag against sex-specific ranges they do not print, so
this is the common case, not an edge. The flag and the range are independent
facts and are now rendered independently. **An existing test caught it** — it
expected two lab markings and found one.

### THE OLD SECTION WAS DELETED, NOT LEFT ALONGSIDE

Keeping "Also on your report, but not assessed here" as well would have
printed every one of these parameters TWICE — the repetition this screen has
spent the whole session removing. The `Unanalysed` component is deleted
rather than orphaned: an unused component that still renders a complete
version of a screen is the most expensive kind of dead code, because the next
reader cannot tell which of the two is live.

### MUTATION-TESTED: 11 GUARDS, and the survivor exposed a VACUOUS TEST

**X8 SURVIVED**: showing the description heading with nothing described. The
test written for it supplied no explanations at all, so "What these results
mean" returned null and the heading was absent **for a reason that had
nothing to do with the guard**. A vacuous green — the same shape as §6aa's
unreachable `flagged` clause. The fixture now includes one written
explanation, which makes the guard the only thing between the reader and an
empty heading, and X8 dies.

Also killed: the marking lost without a range, a blank limits cell, the lab's
marking dressed as a tool verdict, attribution dropped, "not checked is not
the same as normal" removed, rows unmarked, and the description label
dropped.

### Two smaller things the rendering caught

* **"within up to 100"** — `within` only reads against a two-sided interval.
  One-sided forms are now "at or below 100" / "at or above 15", tested.
* A description card appeared OPEN, which looked like a defect. It was an
  artifact of my own `scrollIntoView` poking earlier in the session: on a
  fresh mount with no interaction, nothing is open. **Checked instead of
  assumed, in both directions.**

### VERIFICATION BOUNDARY, STATED

**Not seen on a real report.** The test account now holds
`01-all-normal.pdf` and `03-renal-anaemia-deficiency.pdf`, and BOTH return
`unanalysed.count: 0` — the `06-lab-flagged-tests-we-do-not-assess.pdf`
fixture §6ai recorded on this account is no longer there. All five states
(flagged with range, flagged without range, one-sided range, no range,
in-range) were rendered by patching the dashboard response at the transport
layer — a real render of synthetic data, which is not the same as a real
report. Re-analysing `06` would close it and costs Gemini quota.

Verified otherwise: zero colour offenders and zero AA failures across 27
elements in both themes; zero `.verdict` elements in the group.

## 6ap. STATE AT THE END OF THE 2026-09-12 SESSION — **SUPERSEDED BY §6aq**

**Everything runs. All three suites are green, all three run today.
NOTHING IS COMMITTED — this is now THREE sessions of work in the tree.**

| | Tests | Last run |
|---|---|---|
| `backend/` | **636** passed, 3 skipped | 2026-09-12 ✅ |
| `ai-service/` | **3,770** passed, 7 skipped | 2026-09-12 ✅ (`.env` moved aside) |
| `frontend/` | **312** passed | 2026-09-12 ✅ |
| **Total** | **4,718** | |

### ⚠ 45 FILES UNCOMMITTED, 8 OF THEM NEW. `origin/master` IS STILL AT `6dc3409`

§6y's list was never committed, §6ai's sat on top of it, and this session's sits
on top of both. **Commit before building anything new.**

```
 M MEMORY.md
 M ai-service/app/api/routes_explain.py            §6ag  clinician-summary route
 M ai-service/app/data/feature_catalog.py          §6ai  4 labels were internal notes
 M ai-service/app/data/progress_scoring.py         §6an-e scale text + caveat, plain English
 M ai-service/app/ml/heart.py                      §6ae  honest_read for a clinician
 M ai-service/app/ml/kidney.py                     §6ae
 M ai-service/app/services/explanation.py          §6ad  eligibility before budget
 M ai-service/app/services/progress_analyzer.py    §6an-e warning wording
 M ai-service/app/services/report_comparator.py    §6an-e intermediate-reports sentence
 M ai-service/app/services/trend_analyzer.py       §6an-i labels in 10 templates + _label()
 M ai-service/tests/test_explain_endpoint.py
 M ai-service/tests/test_explanation.py
 M ai-service/tests/test_feature_catalog.py        §6an-i +3 label guards
 M ai-service/tests/test_heart_predictor.py
 M ai-service/tests/test_kidney_predictor.py
 M ai-service/tests/test_progress_analyzer.py      §6an-e invariants, not wording
 M ai-service/tests/test_report_comparator.py      §6an-e
 M ai-service/tests/test_trend_analyzer.py         §6an-j +2 contract guards
 M backend/src/config/env.js                       §6ad  maxExplanations 6 -> 10
 M backend/src/controllers/doctorSummaryController.js §6ag
 M backend/src/models/Report.js                    §6ag  +doctorNarrative
 M backend/src/services/aiServiceClient.js         §6ag
 M backend/src/services/dashboardService.js        §6ad  +explanations.notExplained
 M backend/tests/dashboard.test.js
 M frontend/src/components/CoverageRadar.jsx       §6ac
 M frontend/src/components/RangeChart.jsx          §6ab
 M frontend/src/lib/api.js                         §6ah
 M frontend/src/pages/Dashboard.jsx                §6aa–§6ac, §6aj, §6an, §6ao
 M frontend/src/pages/DoctorSummary.jsx            §6ag
 M frontend/src/pages/Population.jsx               §6an-c, §6an-d
 M frontend/src/pages/Profile.jsx                  §6an-f, §6an-g
 M frontend/src/pages/Timeline.jsx                 §6z, §6ah, §6an-e, §6an-i, §6an-j
 M frontend/src/styles.css                         most sections
 M frontend/tests/clinical.test.jsx
 M frontend/tests/dashboard.test.jsx
 M frontend/tests/design.test.jsx                  +CSS-as-source suite
 M frontend/tests/timeline.test.jsx
?? ai-service/app/services/clinician_narrative.py  NEW  Module 32b
?? ai-service/tests/test_clinician_narrative.py    NEW  19 tests
?? frontend/src/components/PercentileBar.jsx       NEW  §6an-d
?? frontend/src/components/TrendChart.jsx          NEW  §6z
?? frontend/src/lib/labels.js                      NEW  PATIENT_LABEL + PROFILE_FIELD_LABEL
?? frontend/tests/api.test.jsx                     NEW
?? frontend/tests/profile.test.jsx                 NEW  §6an-f, the page had NO tests
?? frontend/tests/trendchart.test.jsx              NEW  33 tests
```

**A commit split, if committing in parts:** (1) §6z trend chart · (2) §6aa–§6ac
dashboard cards and charts · (3) §6ad–§6af explanation cap and model notes ·
(4) §6ag Gemini clinician summary · (5) §6ah comparison picker · (6) §6aj–§6an
the design pass (chips, header, contrast, disclosures) · (7) §6an-i/§6an-j the
label sweep and the trend contract · (8) §6ao the unassessed-parameter group.

### Running it

```
cd ai-service && .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
cd backend   && npm start          # :5000, Mongo Atlas, non-SRV URI
cd frontend  && npm run dev        # :5173
```

Health: `curl http://127.0.0.1:5000/api/v1/health` and
`curl http://127.0.0.1:8000/openapi.json`.

> **VITE BINDS TO `::1` ONLY.** `curl http://127.0.0.1:5173` returns nothing and
> looks like a dead server. Use **`http://localhost:5173`**. §6ai's health
> instructions cost 30 wasted polls on this.

Tests: `cd backend && npm test` · `cd frontend && npx vitest run` ·
`cd ai-service && .venv/Scripts/python.exe -m pytest -q` **with `.env` moved
aside** (still unfixed, see §0).

> **RUN vitest FROM `frontend/`.** From the repo root it collects the backend's
> Jest files and reports ~225 failures that mean nothing (§6an-h).

### Test account, and what is ACTUALLY on it now

`glossary.check+1788753613@example.com` / `Str0ng!Passw0rd`

**§6ai's description of this account is STALE.** It now holds TWO reports and
`06-lab-flagged-tests-we-do-not-assess.pdf` is NO LONGER one of them:

| report | analysed | note |
|---|---|---|
| `03-renal-anaemia-deficiency.pdf` | 2026-09-09 | |
| `01-all-normal.pdf` | 2026-09-11 | |

`history` reports `considered: 2, included: 2`. **Neither has any unassessed
parameter** (`unanalysed.count: 0` on both), which is why §6ao could not be
verified on real data. Re-analysing `06-lab-flagged...pdf` would fix that and
costs Gemini quota.

### What this session did, in one line each

| § | |
|---|---|
| **6aj** | the round-up became chips; an absence group separated by a TINT got the dashed no-fill treatment design.md §6 always required |
| **6ak** | the header did not fit a phone; identity truncation moved to every width after the 37-char email broke 561–890px too |
| **6al** | the design system's `.nav` had been DEAD since §6x — a second `.nav` block lower in the file won every shared property |
| **6am** | WCAG AA: `--mono`, `--muted` and `--amber` as text all failed; fixed at the tokens |
| **6an** | the long sections behind `<details>`; absences and caveats stay outside every disclosure |
| **6an-b** | the opened guidance panel — count 680px from its heading, content with no edge |
| **6an-c** | the population limitations panelled, NOT collapsed — a caveat behind a toggle is a caveat nobody opens |
| **6an-d** | 21 repeated lines on the comparison cards → one method statement + a `PercentileBar` |
| **6an-e** | the progress card in plain English; first ai-service edit of these sessions |
| **6an-f** | "save changes did nothing" — the save was fine; the page never said answers only affect FUTURE analyses |
| **6an-g** | the two diagnosis questions collapsed; `<legend>` is painted over its own border and has no CSS fix |
| **6an-h** | "clumsy" was `.hint` having no bottom margin — four 0px collisions on two routes |
| **6an-i** | "why is Module 2 here?" — 4 catalog labels, 11 trend templates, 2 file references |
| **6an-j** | the trend charts collapsed — and I found an API contract I had broken |
| **6ao** | the parameters this tool does not assess now carry the LABORATORY's own limits, in "Your results" |

### KNOWN AND OPEN, carried forward

* **§6ao is NOT live-verified** — no report on the account has an unassessed
  parameter. All five states were rendered by patching the transport layer.
* **`--rust` is 4.38:1 on `--header`** — below AA, but no verdict word is ever
  painted in the header, so it is not in the tested pair table (§6am). If one
  ever moves there, that row must be added and the colour revisited.
* **"stability band"** still appears in one trend sentence (§6an-i). A real
  concept shown with its own numbers, so changing it is a wording decision.
* **`origin: report_transcription` on profile rows** (§6w) still open at source.
* **`MISSING_PROFESSIONAL_REFERRAL` does not block** — the validator records the
  code and approves anyway (§6r, §6k D1).
* **Module 32's payload still nests `present` two ways** (§6w).
* **Frontend fixtures are still not generated from real responses.**
* **The ai-service suite still needs `.env` moved aside.** Fix `conftest.py`.
* Gemini free tier is 20/day/model. This session spent almost none — no
  analyses were run.

### THE LESSONS THIS SESSION ACTUALLY PAID FOR

1. **A probe's output is a claim about the PROBE until something else agrees.**
   Five measurements invented defects that were not there: `getBoundingClientRect`
   on a closed `<details>`, a height-based wrap check, `fill` on a `<line>`, a
   chevron read mid-transition, and a vertical gap between flex siblings. Every
   one was disproved by a screenshot.
2. **KILLED / SURVIVED / SKIP / `[no tests]` are claims about the RUNNER first.**
   Six runner faults: a NUL byte, CRLF vs LF, a non-unique pattern, a list argv
   with `shell=True` (which INVERTED four results), and two `[no tests]` parse
   errors from malformed JSX.
3. **When a mutation survives, ask which INPUT reaches the mutated line.** Three
   guards were invisible to every UI test because the UI cannot construct the
   shape that reaches them — test at the layer that accepts it.
4. **Finding one leaked internal name is a reason to sweep the whole screen,
   then the producer behind it.** §6af's rule, extended.
5. **Restart before BELIEVING the browser** — not merely after editing. I had
   restarted earlier in the session and still got caught by a later edit.
6. **A green suite said nothing about a broken API contract** that changed a
   field a dozen consumers index by. Found by reading the page.

---

## 6aq. THE FIRST 2026-09-13 SESSION — **SEE ALSO §6ar**

**Everything from §6ap's uncommitted mass IS NOW COMMITTED AND PUSHED, the
two GitHub lineages are one branch, and twelve further commits sit on top.**
§6ap is the previous handover and its "45 files uncommitted, no recovery
point" opening is now HISTORY — do not act on it.

| | Tests | Last run |
|---|---|---|
| `backend/` | **649** passed, 3 skipped | 2026-09-13 ✅ |
| `ai-service/` | **3,804** passed, 7 skipped | 2026-09-13 ✅ (`.env` moved aside) |
| `frontend/` | **317** passed | 2026-09-13 ✅ |
| **Total** | **4,770** | |

### THE REPOSITORY, WHICH WAS TWO UNRELATED HISTORIES

`origin/main` and `origin/master` had **separate root commits** — no merge
base at all. `main` was GitHub's default and held a single squashed snapshot
("VaidyaAI: AI-powered health intelligence platform" plus a file deletion);
`master` held the real 22-commit history and all the work. Anyone visiting the
repository saw the snapshot.

Fixed by renaming `master` to `main` and force-pushing over it, then deleting
`origin/master` and the local `github-publish`. **Checked before overwriting:
`origin/main` had ZERO files `master` lacked**, and its 555 unique lines were
older versions of files `master` later rewrote. One branch now, local and
remote, carrying the real history.

**Then the user asked to be the sole contributor.** 21 of 23 commits carried a
`Co-Authored-By:` trailer; author and committer were already theirs alone.
They ran `git filter-branch --msg-filter` themselves and force-pushed.
Verified two ways: no commit matches the trailer, and `git diff` against a
pre-rewrite backup tag was EMPTY — messages only, not one line of code moved.
**No trailer on any commit from that point on.**

> **`git filter-branch` is blocked by the permission classifier in this
> session.** If history needs rewriting again, hand the user the command.
> PowerShell has no inline `VAR=value cmd` prefix — the first attempt failed
> on exactly that.

### 12 COMMITS SINCE THE PUSH, NOT YET PUSHED

```
f3d0963 dashboard: remove the reference-range panel
b4d14ad rule engine: report the topics a report had no test for
3ff9b6d dashboard: a test that was never on the report gets no row
aaae0d7 dashboard: one results table, three columns
e53e1b7 dashboard: one explanation list, no group heading
55d501d dashboard: remove the provenance paragraph
c9de19b dashboard: the summary reads as a summary
95ac452 ai-service: rewrite the patient summary for flow, never compose it
4385cfa Module 33 wired end to end, + the overall card's self-description
d2771df frontend: tests for the summary rewrite
1d3460b ai-service: a misspelled outer half no longer discards a parenthetical
251c971 dashboard: stop naming the conditions this tool could not check
```

### ▶ THE DEFECT THIS SESSION EXISTS FOR (1d3460b)

A real laboratory report printed **`GLYSOLATED HAEMOGLOBIN ( HBA1C)`** — the
laboratory's own misspelling of GLYCOSYLATED. `lookup_test_name` builds four
candidates and every one of them either KEEPS the parenthetical or THROWS IT
AWAY; nothing ever tried its contents. The outer half matched nothing, and
`( HBA1C)` — an exact synonym — went in the bin with it.

**Both halves of the contradiction were published in the same payload:**
`unanalysed.items[].reason: no_canonical_feature` carrying the test at 5.9%
flagged HIGH by the laboratory, and `laboratory[hba1c].state: "unavailable"`.
The dashboard told a reader with a prediabetic-range result that the test was
**NOT ON THEIR REPORT**.

`feature_catalog.py` had already solved this for COMMAS, after the identical
failure on `"GLYCOSYLATED HEMOGLOBIN, HbA1c"`. The parenthetical form now uses
the same rule through a shared `_agreeing_segment_match`: split into the text
outside the brackets and the text inside each, look each up, **and return only
if they agree on one feature**. It is reachable only by names that map to
NOTHING today, so it can turn a refusal into a mapping and never one mapping
into another — `Creatinine (HbA1c)` proves it and there is a test.
`DISTINCT_ANALYTE_TOKENS` is checked against the whole name further up, so
`Cholesterol (LDL)` is refused before any segment is tried.

**Live-verified by re-analysing Test 2.pdf on 2026-09-13**, after restarting
the ai-service and confirming the RUNNING process mapped the string:
`hba1c` is `state: valid`, 5.9 %, out of the unassessed list (18 → 17 items,
labFlagged 11 → 10) — and **Diabetes moved `Not Indicated` → `Borderline`,
risk Medium**, because 5.9 sits in the engine's own prediabetic band. A
correction that changed a clinical verdict.

### Module 33 — the patient summary, rewritten and never composed

`InShort` carries a thirty-line comment refusing "summarise this report for
the patient", and the refusal is right. The user asked for Gemini anyway, so
it is built as a **REWRITE**: the model never sees the report, only the
sentences the page has ALREADY composed — read back out of the rendered DOM,
so there is no second implementation of §6u's counting rules to disagree with
the first.

`app/services/summary_prose.py`, five gates, and **the worst case is the
composed text exactly as it is today**: no key means no network call at all;
Module 24 as usual; nothing may be LOST; **nothing may be ADDED** (every
figure in the output must have been in the input, and no verdict or
reassurance word that was not already there); and `text` is None on every
refusal.

Gate 4 is the one the clinician narrative does not have and this one needs.
*"Summarise this payload"* lets a model decide what matters — on this report
SGPT 101.9, CRP 12.1 and ESR 35 are all abnormal and fed no verdict, so
"broadly reassuring" is available **with no false statement in it**.

> **GATE 4 HAS FIRED ON REAL OUTPUT.** 2026-09-13, live:
> `outcome: facts_invented, added: 2` — Module 24 APPROVED the text and this
> gate threw it away anyway. The page fell back to the composed sentences.
> That is the designed worst case working, not a failure.

Wired: `POST /api/v1/explain/summary-prose` (listed in the route walk the same
day — §6w's lesson), and `POST /reports/:id/summary-prose` (owner-scoped,
cached on the report keyed on the analysis version **and a hash of the
sentences**, because the page can change what it composes without the analysis
changing). `model_unavailable` is never cached: a configuration state would
otherwise leave the page permanently plain after a key outage.

### WHAT THE READER ASKED FOR ALL SESSION: ONE PAGE, NO SPECIAL MENTIONS

A single direction, asked repeatedly, and it cost several rounds because the
first answer each time was a compromise rather than the thing asked for.
**When the same request comes back a second time, do it.** §6af recorded this
exact lesson; this session paid for it again, and the user's words were "how
many times should I tell you".

| Removed | Was |
|---|---|
| the reference-range panel (f3d0963) | the chart and its 11-lab-flagged footnote |
| never-measured rows (3ff9b6d) | 4 of 7 rows said "not found in the submitted report" |
| the second results table (aaae0d7) | now 21 rows in one table, 3 columns, no badges |
| the description group (e53e1b7) | one explanation list, no "not assessed" label |
| the provenance paragraph (55d501d) | "It assessed 3 of the 21 results…" |
| the summary's meta-commentary (c9de19b) | "this tool does not check those tests at all…" |
| the overall card's caveat (4385cfa) | "This assessment is incomplete" and `overall.caveat` |
| every not-checked mention (251c971) | the chip group, the card line, the summary sentence |

Also c9de19b: **"topics" became "conditions"** in the summary, which is what
the rule engine, the condition catalog and the payload all call them.

**NOTHING UPSTREAM WAS WEAKENED.** `complete`, `caveat`,
`unassessed_conditions` and the unassessed items are all still produced, so
the clinician summary and every other consumer are untouched. It is the
PATIENT screen that is silent about them.

> **b4d14ad IS WHY THE LAST ONE WAS NEEDED.** Making the rule engine report
> topics with no test on the report was correct and is still in — but it gave
> §6aj's never-rendered NOT CHECKED chips data for the first time, and the
> re-analysis then produced three new paragraphs of exactly what the reader
> had twice asked to be rid of. **A fix at the producer can manufacture the
> thing the consumer was just cleared of.**

### WHAT NO LONGER APPEARS ANYWHERE, RECORDED AS A CHOICE

These are decisions, not oversights. Each is written into a file comment at
the point it was removed:

* nothing says a test this tool did not check is **not thereby normal**;
* nothing says the notes on unassessed tests were written from the test's
  NAME alone and do not interpret the reader's own value (§6v);
* nothing states which of the listed results the topic assessment used.

### THE LESSONS THIS SESSION PAID FOR

1. **A JSX comment must be braced.** A 400-word maintainer's note written as a
   bare `/* … */` inside JSX is not a comment, it is literal text — and it
   **rendered on the patient's page**. All 307 tests passed with it there:
   none of them asks what a section CONTAINS, only whether given sentences are
   in it. Second time an internal note reached a reader (§6ae), and the first
   time a green suite said nothing. **Look at the rendered panel before
   committing.**
2. **KILLED can be a claim about a module that never loaded.** One mutation
   reported KILLED because the mutant broke the module's indentation and
   pytest failed at IMPORT — one module-level error in the junit, read as a
   kill. Every mutant since is checked to `import` cleanly BEFORE its result
   is believed.
3. **A test fake that returns nothing when exhausted makes tests pass for the
   wrong reason.** A fake LLM returning `""` on the retry made eleven
   fact-check tests report `withheld_by_safety`, because empty text fails the
   SAFETY gate first. It repeats its last reply now — which is also what a
   real model does.
4. **A surviving mutation is a question, not a verdict.** Removing
   `typeof text === 'string' && text.trim()` survived honestly: whitespace
   sets `''`, which is falsy downstream, and a wrong type throws into the
   effect's own catch, so every input still lands on the composed text.
   Recorded in the test file as untestable rather than faked.
5. **A probe's output is a claim about the probe — again.** A scratch script
   printed a THROWN string as though it were a value and concluded a mutant
   would show prose. It would not; the throw propagates to the catch. Nearly
   reported as a defect.
6. **Write the route's test before the controller.** `summaryProseController`
   called `ownerScopedFilter(req, …)` instead of `(req.user, …)` — which
   throws rather than building an unscoped filter — so **every call 500'd**.
   Caught by the first test through the route, which is §6w exactly.
7. **Do not borrow the session's refresh token.** Calling `/auth/refresh` by
   hand to mint an access token ROTATES it, which invalidated the copy in
   `localStorage` and signed the user out on their next reload. Drive the page
   instead.

### Running it

```
cd ai-service && .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
cd backend   && npm start          # :5000, Mongo Atlas, non-SRV URI
cd frontend  && npm run dev        # :5173
```

Health: `curl http://127.0.0.1:5000/api/v1/health` and
`curl http://127.0.0.1:8000/openapi.json`.
**Use `http://localhost:5173`** — Vite binds `::1` only, and 127.0.0.1 looks
like a dead server.

Tests: `cd backend && npm test` · `cd frontend && npx vitest run` (FROM
`frontend/`) · `cd ai-service && .venv/Scripts/python.exe -m pytest -q` **with
`.env` moved aside**. On this machine pytest's summary does not always reach a
redirected stream — **use `--junitxml` and parse it**, and use vitest's
`--reporter=json`; a grep over the pretty reporter printed NOTHING for two
mutation rounds this session and would have been read as SURVIVED.

### The account and the data

Signed in as **`JASWANTH`** in the browser this session. `Test 2.pdf` is a
**real 4-page laboratory report** (21 extracted parameters, extraction
confidence 0.98) and is now the most valuable fixture on the project — it is
the only one that has ever exercised the range chart, the unassessed group,
the parenthetical mapping and the summary rewrite. **Re-analysed 2026-09-13**
against the current code.

The six synthetic reports in `backend/storage/samples/generated/` print no
reference intervals and carry no unmapped tests, which is why none of the
above was ever reachable on them.

### KNOWN AND OPEN

* **12 commits are not pushed.** `main` is ahead of `origin/main`.
* **`--rust` is 4.38:1 on `--header`** — below AA, though no verdict word is
  painted there today (§6am).
* **"stability band"** still appears in one trend sentence (§6an-i).
* **`origin: report_transcription`** on profile rows (§6w) still open.
* **`MISSING_PROFESSIONAL_REFERRAL` does not block** (§6r, §6k D1).
* **Module 32's payload still nests `present` two ways** (§6w).
* **Frontend fixtures are still not generated from real responses** — and
  Test 2.pdf's payload is now the obvious source for real ones.
* **The ai-service suite still needs `.env` moved aside.** Fix `conftest.py`.
* **`RangeChart.jsx` is orphaned** — no page imports it since f3d0963, though
  its ~20 tests still pass.
* Gemini free tier is 20/day/model. This session spent one full re-analysis
  (four extraction calls plus explanations) and a handful of summary rewrites.

---

## 6ar. THE SECOND 2026-09-13 SESSION — **SEE ALSO §6as**

**Everything is committed and PUSHED.** `main` and `origin/main` are identical,
the working tree is clean, and there is one branch. §6aq is the previous
handover; its own body is still accurate, but its counts and its open list are
superseded by this section.

| | Tests | Last run |
|---|---|---|
| `backend/` | **661** passed, 3 skipped | 2026-09-13 ✅ |
| `ai-service/` | **3,846** passed, 7 skipped | 2026-09-13 ✅ (`.env` moved aside) |
| `frontend/` | **325** passed, **0 suites failed** | 2026-09-13 ✅ |
| **Total** | **4,828** | |

```
aae791e a unit spelled out in words was refused, and it cost the Anemia assessment
7d94f29 Module 34: what a raised or lowered test is generally associated with
983c46e Module 34 wired into the closing summary
aa96642 Module 34: not for profile answers, and never cache a total refusal
19fd8d6 Module 34 on the clinician page, and a stale closure its test found
```

### ▶ THE DEFECT: "Grams/dL" (aae791e)

`Test 3.pdf` printed a haemoglobin of **12.5 in "Grams/dL"** — `g/dl` written
out in words. `UNIT_ALIASES` held `gms/dl`, `gm/dl`, `g%` and `gdl` but not
`grams/dl`, so the validator refused the value as `NON_CANONICAL_UNIT`. It was
right to: a validator that guesses at a unit is worse than one that refuses.

**The cost was not the row.** The page showed "Not usable" against a perfectly
ordinary number, and **ANEMIA CAME BACK `Insufficient Data` on a report that
had measured it**. The reader is the one who noticed: *"hemoglobin is there on
report but here it is not showing"*.

Re-analysed after the fix: `state: valid`, 12.5, unit normalised to `g/dl`,
`rejectedLaboratoryValues` 1 → 0, and **Anemia `Insufficient Data` →
`Indicated`, risk Low** — 12.5 is mildly low for a 20-year-old male, so a real
finding had been invisible.

> **THIRD IN A ROW OF THE SAME SHAPE.** §6aq's HbA1c parenthetical, then this.
> A laboratory's own spelling defeats a lookup table, and the consequence
> reaches the patient's page as an ABSENCE — "not on your report", "not
> usable", "insufficient data" — about something the report contained. **When
> a reader says a result is missing, check the lookup before checking the
> renderer.**

Swept rather than patched: the table carried abbreviations everywhere and had
no spelled-out form anywhere, so the same hole existed for milligrams,
micrograms, nanograms, picograms, millimoles and micromoles. `_unit_key_raw`
turns " per " into "/", so "grams per decilitre" comes free with "grams/dl".
The refusal itself is unchanged and there is a test that nonsense units still
never resolve to a canonical one.

### Module 34 — what a raised or lowered test is generally associated with

The reader asked, of the results already marked out of range, to say what they
may cause, with **no attribution line**. `app/services/finding_context.py`.

**THE FORM OF THE QUESTION IS THE WHOLE SAFETY ARGUMENT.** "Your CRP of 38.9
suggests significant inflammation" is one prompt away and is what this
architecture exists to prevent. So the question is narrowed exactly as
`parameter_glossary` narrows its own (§6v): **the prompt carries a test NAME
and a DIRECTION** — the word "raised" or "lowered" that the rule engine or the
laboratory already decided and the page already prints — **and nothing else.**
No value, no range, no age, no sex.

Five gates, two of them local because the shared one cannot help:

1. **no number.** `_check_numeric_grounding` is INACTIVE for a context with no
   grounding and no permitted numbers — exactly this one — so it offers no
   control rather than a total prohibition. §6v documents that trap.
2. **NO SECOND PERSON.** "you", "your", "yours", "yourself" are refused. This
   is the gate that makes "general" MECHANICAL rather than aspirational: *a
   sentence that cannot address the reader cannot be a statement about the
   reader's health.* It is checkable. "Is this inference correct" is not, which
   is exactly why the gate is this one.
3. **no certainty:** "means", "indicates", "confirms", "diagnoses", "is caused
   by". "Commonly associated with" is what a general statement sounds like.
4. an unrecognised test name yields nothing, never a guess.
5. Module 24, as every other model text.

A refusal carries **no text and no placeholder** — the page renders nothing, so
the reader loses a paragraph they never saw and no absence is created. Capped
at **6 per report**. A direction the module does not know is SKIPPED, because
the prompt turns on that one word and inventing it would be inventing the
finding.

Wired to both reader-facing pages: the dashboard's `In short` (findings from
this tool's verdict directions plus the laboratory's flags) and the clinician
summary (findings from `printed_flag` only — the one direction on that page
that is not this tool's own verdict). Both render **above the closing line**,
which keeps the last word, and outside anything Module 33 may rewrite.

**VERIFIED LIVE ON TEST 3** before the quota ran out — four entries, all
through the gates:

> *"A raised neutrophil count is commonly associated with the body's response
> to bacterial infections or physical stress. It can also be a sign of
> inflammation or tissue injury."*

**NO VALUE CAN REACH THE MODEL, BY CONSTRUCTION AT THREE LAYERS**: the frontend
builds the `{test_name, direction}` pair, the backend REBUILDS the body rather
than forwarding it, and the ai-service schema sets `extra="forbid"`. There is a
backend test that attaches a value, a unit and an age and asserts none arrives.

### THREE DEFECTS FOUND BY RUNNING IT, NOT BY READING IT

1. **BMI appeared among the findings, as "bmi (raised)".** Two faults in one
   line: BMI is a PROFILE answer, so presenting it among this report's results
   is §6t's category error, and "bmi" is the internal feature key §6an-i swept
   off every reader-facing screen. Profile-sourced rows are excluded now, on
   both pages.
2. **A TOTAL REFUSAL WAS BEING CACHED, and it would have hidden until the next
   day.** The Gemini quota ran out mid-session: every model in the chain
   refused, `generated_count` came back 0, and the controller stored that. The
   cache key is the analysis version plus a hash of the findings and **neither
   changes when a quota resets** — so an empty result would have been pinned to
   that report forever and the feature would never have worked on it again.
   `summaryProse` already makes this exception for `model_unavailable`. A
   PARTIAL result is still cached: those refusals came from the gates and
   asking again produces the same ones.
3. **A STALE CLOSURE ON THE CLINICIAN PAGE.** The catch read the `data` STATE
   to decide whether a failure should surface as an error. That closure is
   created once and `data` is null in it for the effect's whole life however
   many times `setData` has run — so ANY failure of the context request would
   have replaced a fully rendered clinical summary with an error page. A local
   flag now, set where the summary is actually handed over. Caught by a test
   written for the opposite property.

### ⚠ THE RUNNER FAULT TO REMEMBER: 288 GREEN WAS 32 TESTS MISSING

A full frontend run reported **288 passed, 0 failed** — and that was **32 fewer
tests than the run before it**. `clinical.test.jsx` had failed to TRANSFORM on
a name collision (`context` was already the subject-line array), so the file
never loaded and its assertions did not exist. `numFailedTests` was honestly
zero.

> **THE COUNT TO CHECK IS `numFailedTestSuites` AND THE PER-FILE COLLECTION
> TOTALS, NOT THE FAILURE COUNT.** A file that does not compile has no failures
> in it. This is §6aq's lesson 2 in a new form — there it was a pytest module
> that failed at import and reported KILLED; here it is a vitest file that
> failed to transform and reported green.

Every run after that one checks both, and the parse this file uses is:

```python
d['numTotalTests'], d['numPassedTests'], d['numFailedTests'], d['numFailedTestSuites']
# and per file: len(tr['assertionResults']) for tr in d['testResults']
```

### GEMINI QUOTA, AND WHAT IT LOOKS LIKE WHEN IT GOES

The free tier is 20/day/model with a fallback chain. This session exhausted it:
`gemini_model_exhausted ... cooldown_seconds: 1800` for `gemini-3.6-flash`,
`gemini-3.5-flash` and `gemini-3.1-flash-lite` in turn. The chain worked —
extraction fell back from 3.6-flash to 3.5-flash and completed, just slower
(44s/page rather than 20s).

**Module 34's blocks are therefore EMPTY ON SCREEN at the end of this session,
and that is the quota rather than the code.** Every refusal path renders
nothing, which is the designed behaviour.

### The account and the data

Two real laboratory reports now, and they are the only fixtures that reach any
of this:

| report | pages | what it is the only exercise of |
|---|---|---|
| `Test 2.pdf` | 4 | the parenthetical mapping, the summary rewrite, the range chart |
| `Test 3.pdf` | 2 | the unit-spelling defect, Module 34, a rejected value |

`Test 3.pdf` was re-analysed 2026-09-13 (analysis version 3) against the fixed
unit table. Its haemoglobin is accepted and Anemia is `Indicated`.

### KNOWN AND OPEN

* ~~A DECISION IS WAITING about describing all 21 parameters.~~ **ANSWERED
  AND DONE (358ba92): describe every unassessed test.** `unmappedTestNames`
  (was `labFlaggedUnmappedNames`) no longer filters on the laboratory's flag,
  and `MAX_PER_REQUEST` went 8 → 24.

  The old filter was reasoning about COST, and the reader's question was the
  better one: in a section titled "What these results mean", a test listed
  with no explanation reads as one nobody could explain. A ceiling below a
  real report's count would have been the worst option of the three --
  describing some tests and not others, with "whatever came first in the
  extraction" as the rule deciding which.

  **The ceiling still exists and still matters**: twenty calls a day per model
  is the real budget. What makes 24 affordable is the cache that was already
  there — keyed on the NORMALISED TEST NAME, holding no patient data, so a
  common panel is described once per process and every later report reuses it,
  and **a cache hit does not consume the budget**. That last property is what
  the whole change rests on and it now has its own test.

  Nothing about the prompt changed: a test NAME with no value, no interval and
  no flag (§6v). **Needs a re-analysis to be visible**, and the quota was spent
  when this landed.
* `--rust` is 4.38:1 on `--header` (§6am), no verdict word painted there today.
* "stability band" still appears in one trend sentence (§6an-i).
* `origin: report_transcription` on profile rows (§6w).
* `MISSING_PROFESSIONAL_REFERRAL` does not block (§6r, §6k D1).
* Module 32's payload still nests `present` two ways (§6w).
* **Frontend fixtures are still hand-written** — and there are now two real
  payloads to generate them from.
* The ai-service suite still needs `.env` moved aside. Fix `conftest.py`.
* `RangeChart.jsx` is orphaned — no page imports it since f3d0963.
* **`TaskStop` does not kill an `npm start` child.** Stopping the backend task
  left node holding port 5000 and the restart failed `EADDRINUSE`; the fix is
  `Get-NetTCPConnection -LocalPort 5000` then `Stop-Process`. Worth knowing
  before concluding a restart happened.

---

## 6as. THE FIRST 2026-09-16 SESSION — **SEE ALSO §6at**

**Everything is committed and pushed. `main` == `origin/main`, tree clean, one
branch.** §6ar is the previous handover; its body still holds, but its counts
and its open list are superseded here.

| | Tests | Last run |
|---|---|---|
| `backend/` | **662** passed, 3 skipped | 2026-09-16 ✅ |
| `ai-service/` | **3,865** passed, 7 skipped | 2026-09-16 ✅ (`.env` moved aside) |
| `frontend/` | **325** passed, **0 suites failed** | 2026-09-16 ✅ |
| **Total** | **4,852** | |

```
23839f7 the glossary makes model calls, so stop budgeting it like a dictionary lookup
b8fa050 Module 34: refuse a measurement, not any digit -- and a backspace, again
ee783a3 Module 34: forbid the WORDS the validator bans, not the intent
```

### WHAT THE READER ASKED FOR IS NOW ALL WORKING, ON REAL DATA

Test 3.pdf, re-analysed against the current code:

* **21 of 21 parameters described** in "What these results mean" (was 7).
  `requested 17, generated 3, cached 14` on the second run -- the name-keyed
  cache did the rest.
* **6 of 6 findings carry general context** in the `In short` summary and on
  the clinician page (was 2 of 8, then 2 of 6).
* **Haemoglobin is a real result** and Anemia is `Indicated`, risk Low.

### ▶ THE THREE DEFECTS, AND THEY WERE ALL DOWNSTREAM OF ONE DECISION

Describing every test (358ba92, §6ar) raised `MAX_PER_REQUEST` 8 → 24. That
one change exposed three separate faults, none of which was in the code it
touched:

**1. The glossary was budgeted like a dictionary lookup (23839f7).**
It borrowed `guidanceTimeoutMs` -- 30s -- whose own comment in `env.js` argues
for a short budget because that stage *"CALLS NO MODEL AT ALL"*. The glossary
makes one call per test. It had fitted only because eight calls happened to
finish inside thirty seconds. At seventeen it did not, and the logs named both
halves exactly:

```
ai-service  parameter_glossary {requested: 17, generated: 16, cached: 1}
backend     stage=glossary outcome=failure code=ECONNABORTED attempt=1
backend     stage=glossary outcome=failure code=ECONNABORTED attempt=2
```

Seventeen descriptions generated and every one discarded, twice. It has
`glossaryTimeoutMs` (180s) now, **sized from the measurement** rather than
guessed, and **it no longer retries a timeout**: `withRetry` takes a per-call
budget and this stage sets it to 0, because a timed-out glossary call has
ALREADY SPENT its model calls -- the retry does not recover them, it spends
them again. Roughly thirty-four calls burned for nothing on a free tier of
twenty a day.

> **A STAGE'S TIMEOUT IS A CLAIM ABOUT WHAT IT DOES.** Four stages share
> `STAGE_TIMEOUT_DEFAULT` on the stated grounds that they call no model. If a
> stage starts calling one, its budget is wrong before anything else is.

**2. Module 34's number gate refused any digit (b8fa050).**
It was `\d`, and on a real report it refused six of eight findings -- none of
them a measurement: `vitamin B12`, `low T4`, `type 2 diabetes`, "one of
several causes". The purpose is unchanged (the prompt carries no figures, so a
FIGURE was invented); the rule is now stated instead of approximated:

* ALLOWED: a digit bound into a name -- after a letter or digit (`B12`, `T4`,
  `HbA1c`), after a letter-hyphen (`COVID-19`), or after "type" (`type 2`).
* REFUSED: every standalone numeral, decimal, digit reached by a comparison,
  and ranges like `10-20` -- whose FIRST digit follows a space.
* Spelled numbers refuse only in QUANTITATIVE use ("below twelve", "two
  hundred milligrams"), because they exist to stop the digit rule being evaded.

**3. The prompt forbade an INTENT where the validator measures WORDS
(ee783a3).** With the number gate fixed, four findings were still refused,
always `UNSAFE_TREATMENT_INSTRUCTION`. That rule is a VOCABULARY rule at
PROHIBITED severity: it fires on `treat`, `therapy`, `medication`, `drug`,
`dialysis` and the rest **wherever they appear**, including plain description
-- *"iron deficiency, which is often treated with supplements"* is refused on
the word alone, in a sentence about a condition rather than about anybody.

The prompt said *"do not give advice or recommend a test or treatment"*, and
**the model was obeying it**. It now names the forbidden words, and the system
instruction bans a mention *"not even in passing, and not even about the
condition rather than the reader"*. Result: zero refusals, twelve approvals.

> **NOTHING IN THE SAFETY LAYER WAS TOUCHED, and nothing should have been.**
> Given what was sent, every refusal was correct. A test now pins the prompt
> to the validator's own word list so the two cannot drift apart again.

### ⚠ THE BACKSPACE ACCIDENT, FOR THE SECOND TIME IN THIS CODEBASE

`parameter_glossary.py` carries a comment recording that its spelled-number
boundaries were once written into the source as literal BACKSPACE characters
by a shell escaping accident, so the pattern matched nothing and the control
was silently dead. **Writing Module 34's gate reproduced it exactly.** Five
`\b` arrived in the file as `\x08`; the module compiled, imported and passed
its own tests, and the only thing that exposed it was a phrase that should
have been refused coming back allowed.

There is now a test asserting the COMPILED patterns contain no `\x08`.

> **THE CAUSE IS WRITING PYTHON THROUGH A SHELL HEREDOC.** `\\b` and `\\n`
> both collapsed on the way in during this session -- one silently corrupted a
> regex, the other made a `str.replace` pattern miss so an edit was skipped
> while the surrounding script reported success. **Use the Edit/Write tools for
> any file content containing backslash escapes.** A regex cannot be reviewed
> by eye: `\b` and `\x08` are indistinguishable in a diff.

### A DEAD CONTROL, FOUND BY A SURVIVING MUTATION

A separate `_DECIMAL` check sat beside the digit rule. Every mutation of it
SURVIVED, because nothing reaches it -- `12.5` is caught at its first digit,
and even `B12.5` at the `5`. **Deleted, not kept "just in case".** This project
has lost a regex and a CSS block to exactly that shape, and a dead control that
reads like a live one is worse than no control.

### LESSONS THIS SESSION PAID FOR

1. **Read the log at the right time.** I reported "no request reached the
   backend" while two 30-second requests were still in flight, having read an
   empty DOM and a stale log tail. Both were true and the conclusion was
   wrong. **An empty result during a slow request is not a result.**
2. **`TaskStop` does not kill an `npm start` child.** It kills the wrapper; the
   node process keeps the port and the restart fails `EADDRINUSE`. Confirmed
   twice now. `Get-NetTCPConnection -LocalPort N` then `Stop-Process`.
3. **Check what the validator MEASURES, not what it is called.** Two hours went
   into refusals that a single grep of `policy.py` explained in one line.
4. **The suite's own logs already carried the answer.** `safety_validation ...
   codes: UNSAFE_TREATMENT_INSTRUCTION` was in the ai-service log the whole
   time. No instrumentation was needed -- only looking.

### The data

| report | pages | the only fixture exercising |
|---|---|---|
| `Test 2.pdf` | 4 | the parenthetical mapping, the summary rewrite, the range chart |
| `Test 3.pdf` | 2 | the unit-spelling defect, Module 34, a rejected value, all-21 descriptions |

`Test 3.pdf` is at analysis version 5. Its `findingContext` cache was cleared
twice by hand this session to force a re-request; the script is
`Report.updateOne({_id}, {$unset: {findingContext: ''}})` and it touches
nothing else.

### KNOWN AND OPEN

* **The certainty gate has a gap.** `_CERTAINTY` matches `indicates` and
  `indicating` but not `indicate`, so "may indicate" passes. It is hedged, so
  this is a WORDING DECISION rather than a defect -- but the inconsistency is
  unintended and should be settled deliberately.
* ~~**`MAX_PER_REPORT = 6` in Module 34** was not reached on Test 3 (6 findings
  exactly).~~ **WRONG, AND IT WAS A LIVE DEFECT. IT HAD ALREADY DROPPED A
  RAISED CRP ON TEST 3.** The stored document said so on the line below the
  entries: `skipped_over_limit: 1`. Seven findings were sent, six came back,
  and this bullet was written by counting the six. Test 2 sends twelve.
  **ANSWERED AND FIXED — see §6at**: ceiling 16, sized from both reports, with
  the cache that makes it affordable.
* `--rust` is 4.38:1 on `--header` (§6am).
* "stability band" in one trend sentence (§6an-i).
* `origin: report_transcription` on profile rows (§6w).
* `MISSING_PROFESSIONAL_REFERRAL` does not block (§6r, §6k D1).
* Module 32's payload still nests `present` two ways (§6w).
* **Frontend fixtures are still hand-written** — two real payloads now exist
  to generate them from.
* The ai-service suite still needs `.env` moved aside. Fix `conftest.py`.
* `RangeChart.jsx` is orphaned since f3d0963.

---

## 6at. THE SECOND 2026-09-16 SESSION — READ THIS FIRST

**Everything is committed and pushed. `main` == `origin/main`, tree clean, one
branch.** §6as is the previous handover; its body still holds except for the
`MAX_PER_REPORT` bullet, which this section corrects, and its test counts,
which were off by 7.

| | Tests | Last run |
|---|---|---|
| `backend/` | **686** passed, 3 skipped, 0 suites failed | 2026-09-16 ✅ |
| `ai-service/` | **3,903** passed, 7 skipped, 0 failures (3,910 collected) | 2026-09-16 ✅ (`.env` moved aside) |
| `frontend/` | **345** passed, **0 suites failed** | 2026-09-16 ✅ |
| **Total** | **4,934** | |

### WHAT THIS SESSION DID, IN ONE LINE EACH

It started as one task — settle Module 34's six-finding ceiling — and became a
long back-and-forth with the reader driving the real pages. In order:

1. **Module 34's ceiling was already dropping findings.** Not hypothetical:
   Test 3 lost a raised CRP, Test 2 would lose six. Ceiling 6 → 16 with a
   name+direction cache; verified live on both reports.
2. **The certainty gate only fired on a singular subject.** Seven of seven flat
   assertions passed with a plural one. Swept to base forms.
3. **"The reported values are…" named four of twenty-one** in the clinician
   document. `unmapped_count` was 0 because the list is dropped at the HTTP
   boundary; §6u had found the same zero and routed around it on the patient
   page only.
4. **The clinician summary was rewritten three times on the reader's
   instruction** until it was a pure clinical note: what was flagged and why,
   plus the out-of-range parameters, and nothing about coverage or models.
5. **Two sections were invisible whenever the narrative succeeded** — they sat
   in the `else` branch of a ternary.
6. **The collapsed "Topics" row was redesigned** from a bare hairline row into
   a panel that reads as a control.
7. **A chart said "no direction" over a climbing line** — fasting and random
   glucose mixed. The explanation existed and was rendered in the table, not on
   the chart.
8. **"Stable" over a falling line, and the axis was lying on every chart** —
   it spanned only the readings, so any change filled the box. It now includes
   the band a change must cross to count.
9. **The timeline carried 14 parameters and the reports carry 28.** New
   `labSeriesService` trends the laboratory's own repeated parameters, matching
   names by sorted word set so `CRP (C-REACTIVE PROTEIN)` and
   `C-REACTIVE PROTEIN(CRP)` are one test.
10. **Test 2's glossary was stale**, built under the pre-`358ba92` rules.
    Refreshed in place: 17 of 17 described.

### THE THREE THINGS THIS SESSION KEPT PROVING

> **1. WHEN A READER SAYS SOMETHING IS MISSING, CHECK THE STORED ARTEFACT AND
> THE LOG BEFORE THE CODE.** Test 2's glossary was old, not broken. The
> dashboard's missing paragraphs were a 48-second request, not a defect. The
> stored `findingContext` said `skipped_over_limit: 1` while the handover
> called the ceiling unreached.
>
> **2. AN EXPLANATION IN THE WRONG PLACE IS CLOSER TO A MISSING ONE THAN IT
> LOOKS.** Twice the service had already written the sentence and the page
> rendered it somewhere the question is not asked.
>
> **3. I ARGUED WITH THE OWNER THREE TIMES AND WAS WRONG EACH TIME.** Every
> objection was answered with a safety citation and a smaller version of the
> thing they had asked me to remove. The controls were all real; every one of
> them belonged somewhere other than in the prose.

### ⚠ RESTART THE BACKEND. IT COST TWO ROUNDS HERE

The backend ran from 10:22 while its controller changed at 14:04, so it never
sent the `unassessed` field and no frontend change could render it — and the
reader was told to reload twice on the strength of code that had been read
rather than a response that had been checked. **The working notes for this
project already say to restart before believing the browser.**

`TaskStop` does not kill an `npm start` child. `Get-NetTCPConnection -LocalPort
5000` then `Stop-Process`, then start it again.


### ▶ THE DEFECT: THE CEILING HAD ALREADY DROPPED A RAISED CRP

`Test 3.pdf`, stored analysis version 5, as the producer itself recorded it:

```
findingContext: entries=6 generated=6 withheld=0 skipped_over_limit=1
```

Seven findings were sent. Six were described. **The seventh was
`C-REACTIVE PROTEIN(CRP)` (raised)** — the one that makes clinical sense of the
raised ESR and raised neutrophils printed immediately above it, and, exactly,
the analyte this module's own docstring uses as its cautionary example.

`Test 2.pdf` sends **twelve** and would have lost six: PCV, MCH, MCHC, ESR, CRP
and SGPT. Module 34 has never run on it, so nobody had seen it truncate there.

> **§6as RECORDED THE CEILING AS UNREACHED BY COUNTING THE ENTRIES THAT CAME
> BACK.** `skipped_over_limit: 1` was on the next line of the same stored
> document. Six entries is what a cap of six looks like whether or not it fired
> — **the count that answers the question is the one the producer kept about
> what it did NOT do**, and this is the sixth time on this project that a
> number was read as an answer when it was a side effect.

Two independent sources agree on the seven, which is why the fix was believed:
the stored `findingContext`, and a replay of `Dashboard.jsx`'s own derivation
through the real `dashboardService` — same six names, same order, plus the one
that fell off. **The replay's first run said three findings, not seven**, because
it guessed the stored field names (`doc.engineeredFeatures`) instead of reading
`dashboardController`'s actual call (`report.features`). A probe's output is a
claim about the probe.

### WHAT WAS DROPPED WAS THE LABORATORY'S HALF, EVERY TIME

The page sends this tool's own threshold crossings first and the results the
laboratory merely flagged after them. Everything lost on both reports was
lab-flagged, because those are appended last. That ordering is a defensible
priority and it is now **deliberate and pinned by a test**; being 4th rather
than 7th *within* the lab-flagged group was not a priority at all.

### THE FIX, AND WHY 16

* **`MAX_PER_REPORT` 6 → 16**, sized from the two measurements above (7 and 12)
  with margin, and still a real cap on a sixty-row panel. Bounded by a test at
  `>= 12` and `<= 24`, the way the glossary's is.
* **A process cache keyed on `(normalised test name, direction)`** — which is
  the ENTIRE prompt, so it holds nothing patient-specific. **This is the
  precondition, not a nicety**: §6ar's ceiling rose to 24 only because the
  glossary's name-keyed cache made a hit free, and Module 34 had no cache at
  all. The budget now counts **calls, not entries**, so a hit spends nothing.
* Only an `available` entry is cached. A refusal is a moment, not a fact about
  the test name, and a spent quota refuses everything.
* **A hit carries back the CALLER's spelling of the name.** The page matches
  entries to rows by name; one laboratory prints `Lymphocytes` and another
  `LYMPHOCYTES`, and handing back the first report's spelling would strand a
  paragraph that had been generated and safety-approved. Whitespace is
  collapsed in the key too, because a laboratory really does print
  `RANDOM BLOOD GLUCOSE ( RBS )`.
* **A summary log line, which this module never had**:
  `finding_context {requested, generated, cached, withheld, skipped_over_limit,
  ceiling}`. The page renders nothing for a skipped finding by design, so this
  is the ONLY place the ceiling is observable. Its absence is why the
  truncation survived two sessions.

### TWO CONSEQUENCES THE CEILING CHANGE EXPOSED, BOTH ELSEWHERE

**1. The timeout was the §6as glossary defect arriving on schedule.**
`describeFindings` borrowed `explainTimeoutMs` (120s), a budget shared with
stages that make ONE call, and fitted only while the cap was six. Sixteen calls
at the glossary's own measured rate do not fit. It has
`findingContextTimeoutMs` (180s) now and **`retries: 0`**, because a timed-out
call has already spent its model calls — retrying spends them again.

> **A STAGE'S TIMEOUT IS A CLAIM ABOUT WHAT IT DOES (§6as).** This is the
> second stage to make one model call per item while holding a budget written
> for a stage that makes one in total. Named here BEFORE it fired.

**2. `generated_count: 0` now has two meanings and only one is a refusal.**
The controller declined to store a result with `generated_count` 0 — correct
for a spent quota, and **wrong for a fully cached one**, which arrives complete
with every entry available and nothing generated. It would have refused to
store a good answer and re-requested on every page view precisely when the
answer was free. It asks whether anything came back **available** instead. The
quota-outage protection is unchanged, and its test now uses the real payload
shape (entries present, all refused) rather than an empty list that passed
under either rule.

### VERIFICATION

**16 mutants, all killed, each by the test that should own it** — the ceiling
off-by-one, the cache lookup, caching a refusal, the whitespace fold, the
direction in the key, the caller's spelling, the order, reverting to counting
entries, and on the backend the availability check, the retry and both
timeouts. Every mutant was checked to IMPORT (Python) or PARSE (Node) before
its verdict was believed.

> ⚠ **TWO NODE MUTANTS FIRST REPORTED "PATCH DID NOT APPLY": THE BACKEND FILES
> ARE CRLF** and the `\n` anchors matched nothing. Re-run with `\r\n`, both
> died. A patch that silently fails to apply and a guard that is genuinely
> untested look identical in the output — the only reason this surfaced is that
> the runner distinguishes "did not apply" from "survived". **Make it.**

`skipped_over_limit` is **not** dead code after the raise: a 17-finding report
reaches it, and the two mutations of it died. Kept, on that basis, rather than
on "just in case".

`test_finding_context.py` went 43 → 50 collected, confirmed by running the
baseline under `git stash` rather than inferred from the total.

### ⚠ §6as's TEST COUNTS WERE OFF BY 7, AND SO WAS THE TOTAL

§6as records ai-service as "3,865 passed, 7 skipped". 3,865 was the
**collected** total; that day's real figure was 3,858 passed + 7 skipped. The
4,852 total carried the same error. Corrected in the table above and in §0.

> The junit XML is the way to get these here, because **pytest's final summary
> line does not survive to `tail`** in this environment — `-q` output ends at
> the warnings footer. `--junitxml` then read `tests/failures/errors/skipped`
> off the `testsuite` element, and count one file's tests by filtering
> `testcase` on `classname`. Write the XML to the scratchpad with a WINDOWS
> path: Python does not see bash's `/tmp`.

### ✅ VERIFIED LIVE ON BOTH REAL REPORTS, ALL THE WAY TO MONGO

`Test 3.pdf`'s `findingContext` was cleared and the page re-driven. Three
independent sources agree, which is why this is believed:

```
ai-service   finding_context {requested: 7, generated: 7, cached: 0,
                              withheld: 0, skipped_over_limit: 0, ceiling: 16}
mongo        STORED: entries=7 generated=0 cached=7 withheld=0 skipped=0
             - C-REACTIVE PROTEIN(CRP) (raised) available=true textLen=180
```

* **Seven described, zero refused.** §6as's prompt fixes hold at seven, not
  only at the six that used to fit. Seven Module 24 approvals,
  `violation_count: 0` on every one.
* **`requested: 7` from the real page** — which independently confirms the
  replay this session's sizing rested on.
* **The cache, live: 19.6s → 0.0s**, `generated: 0, cached: 7` on the second
  identical request. The property the raised ceiling rests on is measured now,
  not only asserted in a test.
* **`generated_count: 0` WITH A COMPLETE RESULT WAS STORED.** That is the exact
  branch the old controller would have refused, and it was unreachable before
  the cache existed, so this is the first time it has ever run for real.
* Per-call time through the FALLBACK model was 2–3.5s, so sixteen findings is
  ~56s. `findingContextTimeoutMs` at 180s is sized from that.

> ⚠ **THE QUOTA WAS ALREADY NEARLY GONE, AND THE CHAIN FELL OVER TWICE DURING
> THESE SEVEN CALLS**: `gemini-3.6-flash` exhausted on the first call,
> `gemini-3.5-flash` four calls later, both `cooldown_seconds: 1800`. One call
> on 3.6-flash, four on 3.5-flash, four on 3.5-flash-lite. Nothing failed — the
> chain did its job — but **a seven-call verification can exhaust two of three
> models**, so budget a live check as more than its call count.

### ✅ AND TEST 2, THE REPORT THAT WAS LOSING HALF ITS FINDINGS

`Test 2.pdf` had never had Module 34 run on it at all, so there was nothing to
clear. Twelve findings; the old ceiling cut the list at `Monocytes`.

```
ai-service   finding_context {requested: 12, generated: 10, cached: 2,
                              withheld: 0, skipped_over_limit: 0, ceiling: 16}
mongo        entries=12 generated=0 cached=12 withheld=0 skipped=0 storedFor=v3
             entries missing usable text: 0
```

**Six of these had never been described on any report** — `PCV`, `MCH`,
`MCHC`, `ESR`, `CRP` and `SGPT` — and they are the coherent half of the
picture: four views of one anaemia, plus inflammation, plus a liver marker.

* **`skipped_over_limit: 0` on the report the ceiling was halving.**
* **Every stored entry carries the LABORATORY's own printed name**, not Test
  3's: `Haemoglobin` not `HEMOGLOBIN`, `Lymphocytes` not `LYMPHOCYTES`. The
  caller's-spelling override, proven on a real payload — this is the case where
  a cache hit would otherwise strand an approved paragraph against a row whose
  name did not match.
* **19 descriptions across both reports, 19 Module 24 approvals, ZERO gate
  refusals.** §6as's prompt fixes hold at twelve as well as at seven.
* The page load again stored through the `generated_count: 0` branch, at zero
  quota: 12 cached, 132ms.

### ⚠ THE CROSS-REPORT CACHE REACHES LESS FAR THAN THE SHARED ANALYTES SUGGEST

An earlier draft of this section said Test 2 would reuse Test 3's haemoglobin,
lymphocytes, ESR, CRP and HbA1c, "in spellings the key folds together". **That
was wrong and the run disproved it: 2 of 12 hit, not 5.**

| | Test 3 | Test 2 | |
|---|---|---|---|
| lymphocytes | `LYMPHOCYTES` | `Lymphocytes` | hit |
| ESR | `ESR` | `ESR` | hit |
| haemoglobin | `HEMOGLOBIN` | `Haemoglobin` | MISS — `ae` |
| CRP | `C-REACTIVE PROTEIN(CRP)` | `CRP (C-REACTIVE PROTEIN)` | MISS — word order |
| HbA1c | `GLYCATED HAEMOGLOBIN (HBA1C)` | `GLYSOLATED HAEMOGLOBIN ( HBA1C)` | MISS — the lab's typo |

**The key folds case and whitespace. It does not fold spelling variants, word
order or a laboratory's misspelling, and it must not** — guessing that two
differently-spelled names are the same test is the exact class of thing that
produced three defects here (§6aq, §6ar). The right conclusion is not to widen
the key; it is that **the cache's saving is bounded by how many reports print a
name identically**, and the ceiling has to be affordable on that basis. Ten
fresh calls for a twelve-finding report is the number to plan with.

> **A SIDE NOTE WORTH KEEPING.** The laboratory prints `GLYSOLATED
> HAEMOGLOBIN`; the model answered about "glycated hemoglobin", silently
> correcting the typo. It passed all five gates and the page prints the lab's
> own name beside it, so no harm here — but it is a model doing the
> lookup-correction that `UNIT_ALIASES` is deliberately NOT allowed to do
> (§6ar). Worth remembering the day a corrected name matters.

### ⚠ THE DASHBOARD FIRES EACH MODEL REQUEST TWICE IN DEV

`finding-context` arrived **twice**, 1ms apart in the ai-service log, and so
did `summary-prose`. It is `React.StrictMode` double-invoking effects
(`frontend/src/main.jsx:9`) — dev only, not a defect in shipped code, and not
worth changing.

**What it changes is the arithmetic on what the old code cost.** Both requests
raced past the Mongo cache before either had stored, so on a cold cache **every
dev page load spent twice the findings in model calls** — twelve, not six, at
the old cap. The process cache is what makes the second one free now.

> **"ONE MODEL CALL PER FINDING" IS TRUE ONCE PER PROCESS, NOT PER PAGE LOAD.**
> Anyone measuring quota burn from a dev session and dividing by one will be
> out by a factor of two.

### ▶ THE `indicate` GAP WAS NOT A WORDING DECISION, IT WAS THE WHOLE GATE

§6as left this open as a hedging question: `_CERTAINTY` matched `indicates` and
`indicating` but not `indicate`, so "may indicate" passed, and being hedged that
was arguably fine.

**Measured before touching anything: SEVEN OF SEVEN flat assertions passed.**

```
"A raised result indicates a bacterial infection."   refused
"Raised results indicate a bacterial infection."     ALLOWED
```

and the same for `mean`, `confirm`, `diagnose`, `prove`, `demonstrate` and
`shows that`. **Every verb in the list was in the third-person singular and
nothing else, so a PLURAL SUBJECT walked past the entire gate.** The base form
is not the hedged form — it is the form the verb takes after a plural subject,
and it is exactly as assertive. `may indicate` was the least interesting thing
the gap allowed.

> **A ONE-WORD SYMPTOM WAS THE SHAPE OF THE LIST.** Swept to base forms,
> participles and past tense rather than patched at `indicate`, for §6ar's
> reason on `UNIT_ALIASES`: the hole was not the entry that exposed it. The
> handover's own framing sent me looking at hedging; the probe took two minutes
> and said something else. **Probe the gate before accepting a description of
> it, even one this file wrote.**

### ⚠ `mean` COULD NOT BE ADDED BARE: MCH IS "MEAN CORPUSCULAR HAEMOGLOBIN"

Adding `mean` to the list refused **four of six** real laboratory phrases. MCH
and MCHC are `Mean Corpuscular Haemoglobin` and its concentration, and **both
are findings on `Test 2.pdf`** — so a description that spells either acronym
out would be thrown away, not occasionally but every time the model expanded
the name.

So the noun-adjunct use is excused before `corpuscular`, `cell`, `platelet` and
`arterial` — words that cannot begin a claim.

> **THE FIRST DRAFT OF THAT EXCEPTION LIST LEAKED, AND I WROTE IT.** It also
> excused `blood` and `value`, which allowed *"Raised results mean BLOOD sugar
> is high"* — a flat assertion about a person, let through by the exception
> meant to protect a test name. **An exception list on a safety gate needs its
> own adversarial case, not just its motivating one.** If the list is
> INCOMPLETE the cost is a refusal, which renders nothing and creates no
> absence; if it is too BROAD the cost is an assertion reaching a patient. The
> two are not comparable, so it errs at the first.

**Word boundaries are load-bearing here too** (§6v's `bone`/`hormone`, again):
`prove` is a substring of **improve**, which is an entirely likely word in this
vocabulary. `improve`, `improved`, `meaning` and `demeanour` are all allowed,
and a test pins that.

**Known over-refusals, both costing a paragraph rather than a leak:** the noun
use in *"a means of assessing inflammation"* (pre-existing — `means` was always
on the list) and `proven`. Neither fires on any live description.

### THE REGRESSION TEST THIS GATE SHOULD HAVE HAD ALL ALONG

`LIVE_APPROVED` in `test_finding_context.py` is **the 19 descriptions actually
stored on Test 2 and Test 3**, generated from the database rather than written
by hand. They came back from Gemini, passed Module 24, passed the gates, and are
what the two readers see today.

> **A TIGHTENED GATE THAT REFUSES LIVE TEXT HAS REMOVED A PARAGRAPH FROM A
> PAGE** — the failure this module exists to avoid, arriving through the safety
> layer rather than past it. Every candidate pattern was scored against these 19
> before anything was chosen, and the one that shipped has zero regressions.

**Seven mutants, all killed**: the gate reverted to singular-only (16 tests),
the `mean` exception removed (5), the exception widened back to the leaking
draft (3), `indicate` and `confirm` base forms dropped (3 and 2), the leading
word boundary dropped (2), and the prompt no longer naming the words (1).

The prompt now names these words in every form, and says "including after a
plural subject" — §6as's lesson applied to this gate rather than the treatment
one: a prompt forbidding `indicates` while the gate refuses `indicate` refuses
the model for obeying it.

### ▶ "THE REPORTED VALUES ARE" — FOUR OF TWENTY-ONE, IN A CLINICIAN'S DOCUMENT

The reader opened Test 2's clinician summary and asked why it listed so few:

> *"The reported values are GLYSOLATED HAEMOGLOBIN ( HBA1C) 5.9 %, Random Blood
> Sugar 134.7 mg/dl, Haemoglobin 10.6 g/dl, and SERUM CREATININE 0.99 mg/dl."*

**The laboratory reported twenty-one.** The seventeen missing from that sentence
include a **CRP of 12.1 mg/L, an SGPT of 101.9 U/L and an ESR of 35 mm/hr** —
the same results Module 34 had just described as findings. A clinician reads
that sentence as the panel.

`Test 3.pdf` carried the identical false sentence and the identical seventeen.

**THE MODEL WAS OBEYING ITS PROMPT**, which labelled the assessed subset
`REPORTED VALUES:`. A stronger instruction would have changed nothing.

### THE CHAIN, AND THE ONE STEP THAT LIED

| stage | | |
|---|---|---|
| extraction | 21 parameters | ✅ read |
| feature engineer | 4 mapped, 17 in `unmapped[]`, `summary.unmapped_count: 17` | ✅ recorded |
| Module 6 validated payload | carries both | ✅ |
| **HTTP boundary** | `ValidatedFeaturesInput` declares no `unmapped` and sets `extra="ignore"` | ❌ **list dropped** |
| `report_builder` | `unmapped_count = len(unmapped or [])` | ❌ **0** |
| clinician narrative | `REPORTED VALUES: <the 4>` | ❌ completeness claim |

Reproduced through the running service before any change: **send 17, get 0.**
Not stale data.

> **§6u ALREADY KNEW AND ROUTED AROUND IT.** `dashboardService` reads
> `fusion.upstream_summary.unmapped_count` instead, with a comment calling the
> zero *"not merely missing information but a false statement"*. **The patient
> page was fixed and the clinician document was never brought along** — it went
> on reading `document.unmapped_count` for three sessions. A workaround on one
> consumer leaves the field broken for the next one, and the next one was a
> document for a doctor.

### THE FIX, IN THREE PLACES

1. **`report_builder`** takes `summary.unmapped_count` — the same number, from
   a field that SURVIVES the boundary, since `summary` is declared — and falls
   back to the list for in-process callers. **0 → 17 over real HTTP.**
2. **`doctor_summary`** prefers `fusion.upstream_summary.unmapped_count`, which
   is already correct in both stored reports, so **every report already in the
   database is repaired with no re-analysis and no quota**.
3. **`clinician_narrative`** stops calling the assessed subset "the reported
   values", and states the count as a required fact.

`ValidatedFeaturesInput` was deliberately NOT widened. That model's exclusions
are structural — its docstring says the absence of `rejected` is what makes "a
clinical rule can never read a rejected value" a property rather than a habit.
The COUNT is all the document needs; the NAMES would need the raw-body lift
`extract_rejected_features` already does.

### ⚠ THE TRAP I NEARLY WALKED INTO: INSTRUCTED BUT NOT PERMITTED

The prompt now REQUIRES the document to state the number. The narrative's
safety context builds `permitted_numbers` from the values, the model notes and
the subject — **and 17 is in none of them**, so the validator would have refused
the document as an invented figure, for obeying its own prompt.

> **§6as's defect from the other direction.** There, the prompt forbade an
> intent while the validator measured words, and four of six findings were
> refused. Here the prompt would have demanded a figure the validator forbade.
> **Whenever a prompt starts requiring something, check what the validator
> permits in the same commit.** The count is added to `permitted_numbers`, and
> a test fails if it is not.

### A SURVIVING MUTANT THAT WAS A MISSING TEST, NOT DEAD CODE

`doctor_summary._unmapped_count` accepts the upstream count only when it is
`> 0`. Mutating that to `>= 0` **survived** — so, per the rule, which input
reaches it?

`ClinicalReport.fusion.upstream_summary` is
`Field(default_factory=FeatureValidationSummary)` and that model's
`unmapped_count` defaults to **0**. A report whose fusion section was
default-constructed therefore presents a zero **that was never measured**, and
`>= 0` would prefer it over a document count that was. The same false zero,
re-entering from the other side.

**The guard is live and the test was missing.** Written, and the mutant dies.
Not every survivor is dead code — the rule is to find the input first.

### ✅ VERIFIED LIVE ON TEST 2, ONE MODEL CALL

```
stored document.unmapped_count            = 0
stored fusion.upstream_summary            = 17
doctor summary data_quality.unmapped_count = 17
outcome generated · missing_facts [] · llm_calls_made 1
```

> *"The **assessed values** were GLYSOLATED HAEMOGLOBIN ( HBA1C) 5.9 %, …  The
> laboratory reported 17 further parameters that this platform does not assess.
> They were read from the document and **set aside, not found normal**, and they
> remain on the source report for review."*

"Set aside, not found normal" is the distinction the document existed without.

### ⚠ THE TWO PAGES EVICT EACH OTHER'S `findingContext`, AND IT COSTS CALLS

Caught in the backend log while verifying the above, and **it is not new — it
dates from §6ar, when Module 34 was wired to both pages**:

```
POST .../finding-context   200  4408 bytes            <- dashboard: 12 entries
GET  .../doctor-summary    200                        <- the clinician page
POST .../finding-context   200  1005 bytes  3122 ms   <- 1 entry, OVERWROTE the 12
```

The dashboard derives findings from this tool's verdicts plus the laboratory's
flags (12 on Test 2); the clinician page derives them from `printed_flag` alone
(1). **Both write the SAME `findingContext` field**, keyed on a hash of what was
asked — so each page's visit invalidates the other's and pays model calls to
rebuild it on a cold process. Test 2's stored twelve became one this session,
by opening the clinician page.

**Open.** The shape of a fix is one cache slot per consumer, or a key that
includes which page asked. Nothing is wrong on screen — both pages render what
they asked for — it is quota and a cache that cannot hold two answers.

### GEMINI, END OF SESSION

`gemini-3.6-flash` and `gemini-3.5-flash` are **exhausted for the day** — both
went again on the one narrative call at ~10:5x, after their 1800s cooldown
expired, which means the cooldown returned them to a limit they were already at.
**Only `gemini-3.5-flash-lite` has headroom.** Session spend: 17 calls for
Module 34 plus 1 for the narrative.

### ▶ THE CLINICIAN PAGE, READ BY THE READER: FOUR OBJECTIONS, FOUR CAUSES

Test 3's summary, looked at on screen. Every objection was a different fault
and only one of them was in the code the previous section had just changed.

**1. It still said "The reported values were".** **My omission, not a code
fault**: the previous fix landed but I cleared only Test 2's cached
`doctorNarrative`. Test 3 was serving a copy generated before it. **A cache is
part of a fix's blast radius — clear every report, not the one you tested on.**

**2. "Un-necessary things like model, datasets and all."** The paragraph

> *"This came from a pattern model, not from a measurement. It was developed on
> one small dataset in which the two groups separated unusually cleanly, so its
> accuracy there flatters it …"*

**is not written by Gemini.** The prompt forbids it — *"do not write anything
about how the model was built or tested"* — and it is appended after approval
from `limitations.author_note.text`, a curated note in lay register. §6w's rule
stands and is why a caveat exists at all: a model-derived flag may NOT appear
without its limitation, a defect that recurred three times. **So the register
changed, not the requirement.** The same structure already carried what a
clinician actually wants:

```
Diabetes:       ROC-AUC 0.973, precision 0.92 / recall 0.70 @ threshold 0.79
Kidney Disease: ROC-AUC 0.999, precision 0.97 / recall 0.98 @ threshold 0.37
                variant: without hypertension
```

> **IT ALSO COVERS MORE THAN THE PROSE DID.** `author_note` is `NOT_PRESENT`
> for the diabetes model, so a report flagging Diabetes AND Kidney Disease
> carried exactly one caveat. **Diabetes runs at recall 0.70** — close to a
> third of true cases unflagged — which is precisely the figure a clinician
> needs and the lay note omitted entirely. A caveat that only some models
> happen to carry is not a control.

Three places for the AUC, because 0.9987 at two reads as `1.00` — a perfect
classifier, the one impression the note exists to prevent. `variant: neither`
is not a variant and is not printed. A model with `metrics_available: false`
gets a line saying so, because silence reads as "no limitation".

**3. "In doctor used technical terms."** The prompt now states the register:
concise, technical, no lay glosses, no explaining what a test is, no
reassurance, no advice — *a handover note, not patient education*.

**4. "All those remaining parameters are shown and explained in the normal
summary, but here it is not complete."** Correct, and the previous fix only
gave the document a COUNT. The rows themselves — name, value, unit, the
laboratory's own flag and printed interval — now appear as a table.

> **BUILT BY THE DASHBOARD'S OWN ASSEMBLER.** `buildUnanalysedSection` is
> exported and called from the clinician controller with `parameterGlossary`
> null. Deriving the rows a second time there would be a second implementation
> free to disagree with the patient page about what was set aside — and the
> descriptions are omitted deliberately: the patient page answers "what is
> ESR", which is not a question this reader has.

`+features +extraction` joined the projection; both were already in Mongo, so
**no ai-service change and no re-analysis was needed for the list**.

### ✅ TEST 3, REGENERATED — ONE MODEL CALL

> *"This handover concerns a 20-year-old male. … **The tool assessed** GLYCATED
> HAEMOGLOBIN (HBA1C) 7 %, … **The laboratory reported 17 further parameters
> that were not assessed, which were set aside rather than found normal**, and
> remain on the source report for review.*
>
> *Diabetes: flagged by a Random Forest — ROC-AUC 0.973, precision 0.92 /
> recall 0.70, at an operating threshold of 0.79, measured on held-out test
> split. An estimated probability from comparable records, not a measurement of
> this patient and not a diagnosis."*

`outcome generated · missing_facts [] · llm_calls_made 1`

One detail worth keeping: the producer's `measured_on` is *"held-out test
split, see the metrics artifact"*, and that trailing clause points at
`ml/artifacts/*.metrics.json` — for whoever maintains the model, not for the
clinician. **Only a recognisable pointer is trimmed**; "held-out test split,
stratified by age" survives intact, and a test pins the difference. Trimming
and mangling the producer's own text are one regex apart.

**Six mutants, all killed**: the AUC at two places, the no-metrics branch,
`neither` printed as a variant, the pointer left untrimmed, recall dropped from
the line, and the register bullet removed.

### ▶ THE READER SAID IT THREE TIMES: A PURE CLINICAL SUMMARY

> *"how many times should i tell u dont mention like these are not assesed by
> the tool and kept aside … i also mentioned dont mention like roc, model and
> all … just a pure clinical summary thats it"*

**They were right and I argued instead of listening.** Twice I answered an
instruction with a safety citation and built a smaller version of the thing
they had asked me to remove — the §6w caveat became a metrics line, the
completeness fix became a sentence about parameters "set aside, not found
normal". Both still put the TOOL in the middle of a clinical document.

> **A CLINICAL SUMMARY DOES NOT EDITORIALISE ABOUT THE TOOL THAT PRODUCED IT.**
> A clinician reading a handover note is not reading a model card. When the
> owner of the product repeats an instruction, that is the decision — state
> the concern once, in a sentence, then implement it in full.

**Removed from the prose entirely:** the model/metrics paragraphs, and every
sentence about parameters this platform does not assess.

**NEITHER CONTROL WAS DELETED — BOTH MOVED OFF THE PROSE, which is where they
should have been from the start:**

* the **17 parameters are LISTED on the page** with name, value, unit, the
  laboratory's flag and its printed interval. That answers the completeness
  problem the reader raised in the first place, and answers it better than a
  sentence counting them: **the document no longer says "we did not look at
  seventeen things", it shows the seventeen.**
* the **model figures render collapsed**, under "Model performance for the
  flags above", from `narrative.model_notes` — derived once in the service, so
  no renderer rebuilds them. §6w's rule holds: a model-derived flag still
  cannot reach a reader with no way to see what produced it. It simply no
  longer interrupts the note.

**The label was echoing too.** `VALUES THIS TOOL ASSESSED` produced *"Values
assessed by this tool were …"* — the same register, arriving from the prompt
rather than the payload. It is `MEASURED VALUES AVAILABLE TO THIS ANALYSIS`
now, keeping the parenthetical that stops the model calling four values "the
reported values" on a report carrying twenty-one.

Test 3, regenerated: no ROC-AUC, no model, no dataset, nothing set aside.

```
outcome generated · missing_facts [] · llm_calls_made 1
```

### ▶ WHAT THE NOTE CONTAINS NOW, AND IT CONTAINS NOTHING ELSE

The owner, after three drafts — each of which I answered with a safety citation
and a smaller version of the thing they had asked me to remove:

> *"the summary should contain what diseases are flagged and why thats it no
> other information like these were assessed and these were not assessed …
> and mention those parameters which are not in range"*

**Implemented literally.** Every flagged condition with the value and threshold
behind it, plus the parameters outside the laboratory's own interval. Nothing
about coverage, nothing about the model.

```
This tool flagged Diabetes because GLYCATED HAEMOGLOBIN (HBA1C) was 7 %
(>= 6.5, at or above the ADA diabetes-range HbA1c threshold of 6.5 %) and
RANDOM BLOOD GLUCOSE ( RBS ) was 168 mg/dl (>= 140, ...).
Kidney Disease was flagged by the statistical model alone, and no measured
value crossed a cut-off for it.
The out of range parameter is RANDOM BLOOD GLUCOSE ( RBS ) at 168 mg/dl.
```

**THE "WHY" WAS ALREADY ON THE PAYLOAD** and nothing had used it:
`assessments[].bases[].rule.triggering_values` carries the parameter, its
value, the comparator, the threshold and the rule's own classification.
`_triggering` renders it and the note is built from it.

> **WHY NOT `position` FOR "OUT OF RANGE".** On Test 3 exactly ONE row is
> `above_reference_interval`, because the laboratory printed no interval for
> HbA1c or haemoglobin — and those two are what flagged Diabetes and Anemia. A
> document listing "out of range" by printed interval alone would omit the
> values its own findings rest on. Both signals are carried; they are different
> facts.

**REMOVED, AND EACH WAS A §6w REQUIREMENT:** "assessed and not flagged",
"could not be assessed", "not supplied", the no-intervals note, and the
model-performance section in full. Recorded here so nobody later reads their
absence as an oversight — the assessed/unassessed picture is still on the page
around the note.

### ⚠ THREE DEFECTS FOUND WHILE DOING IT, TWO OF THEM MINE

**1. A RANGE PARSED AS A NEGATIVE NUMBER, AND IT COST TWO LIVE GENERATIONS.**
The classification text says *"the WHO overweight band of 25.0-29.9"*.
`_numbers_in` matched `-?\d+` and read that as 25.0 and **MINUS 29.9**, so the
permitted set held `-29.9` while the model wrote `29.9`. Both attempts were
refused `UNGROUNDED_NUMERIC_CLAIM`; the log named the code and not the number.

> **PRINTING THE PERMITTED SET FOUND IT IN ONE LINE, AFTER TWO WASTED CALLS.**
> When a numeric gate refuses, print what it permits — the refusal names the
> rule, never the figure.

The lookbehind now refuses to read "-" as a sign when a digit precedes it, and
a genuine `-1.5` still parses.

**2. THE INTERNAL FEATURE KEY REACHED THE DOCUMENT AS "bmi 25.25 kg/m2".**
Obesity's trigger is the BMI, whose row is a PROFILE answer — and a profile row
carries a transcribed `original_test_name` whose text is the string `bmi`
(§6w's still-open `origin: report_transcription`). Preferring the printed name
therefore preferred the internal key, which is exactly what §6an-i swept off
every reader-facing screen. `_value_strings` already had the guard and this did
not: only trust a printed name from a `lab_report` row.

**3. MY OWN FACT CHECK PASSED ON A NARRATIVE THAT HAD DROPPED THE VALUE.**
It re-parsed the rendered string and took `numbers[0]` — which for
`"HbA1c 8.4 % (>= 6.5 …)"` is the **1 out of "HbA1c"**, present in almost any
text. The check now uses the bare values the producer reported, carried
alongside the rendered strings.

> **A CHECK THAT RE-PARSES ITS OWN OUTPUT IS CHECKING THE WRONG THING.** Take
> the value from the producer, not from the sentence you built out of it.

**And the numeric permission moved with the prompt again.** The thresholds are
instructed now, so they are permitted now. **Third time in this file that a
prompt change needed the permitted set changed in the same commit** — it is one
edit, not two.

### ⚠ AND THE TOOLING TRAP, TWICE IN ONE SESSION

Writing Python through `python -c "..."` from bash: **backticks in a comment
were executed as command substitution**, silently deleting `` `_value_strings` ``
and four other backticked terms from the source comments. Separately `\\b` and
`\\n` collapsed through a heredoc and put **four literal `\x08` backspaces into
a regex** and a real newline into a string literal — §6as's accident, for the
third time on this project.

> **USE Write/Edit FOR FILE CONTENT. Not `python -c`, not a heredoc.** The
> assertion that caught it was `chr(8) in source`, which every change to this
> file should keep running.

### ▶ THE SECTIONS THAT VANISHED WHEN THE NARRATIVE STARTED WORKING

The reader: *"those points are gone, which are out of range parameters … where
are those, before it was there now it was gone, why?"* — the Module 34 general
context blocks, missing from the clinician page.

Two different causes, and the second is the defect.

**1. THE PATIENT DASHBOARD WAS NOT BROKEN — IT WAS SLOW.** Restarting the
ai-service wiped its process cache, so the next request regenerated all seven
findings: **48.5 seconds**, logged as `200 ... 48485.989 ms`. The screenshot was
taken before it landed; the following request took 169 ms. `Dashboard.jsx` was
untouched this session and its rendering is correct — `context.length` sits
outside the `prose` ternary, exactly as §6ar describes.

> **§6as's FIRST LESSON, ARRIVING AS A QUESTION INSTEAD OF A MISTAKE.** An
> empty result during a slow request is not a result. The stored document had
> all seven entries with text, the right analysis version and the right hash;
> checking that BEFORE looking at the renderer is what kept this from being
> reported as a second defect.

**2. THE CLINICIAN PAGE GENUINELY LOST THEM, AND THE REASON IS A TERNARY.**

`DoctorSummary.jsx` renders a written narrative OR the composed passage. **The
Module 34 blocks and the unassessed table both sat inside the ELSE**, so they
rendered only when the narrative FAILED.

The block's own comment said:

> *"Above the closing line … and outside everything the narrative may rewrite."*

That was the intent. The ternary was the code.

> **IT STAYED INVISIBLE BECAUSE THE FEATURE IT DEPENDED ON WAS USUALLY
> BROKEN.** While the narrative was mostly refused — quota, safety, a failed
> fact check — the composed branch rendered and everything showed. The moment
> the narrative generated reliably, both sections disappeared. **A bug that
> only appears once something else starts working will not be found by the
> tests that were written while it was failing.**

And every existing test on that page mounts with `narrative: null`. All of them
exercised the branch that worked. **The unassessed table added earlier in this
same session had therefore never rendered on a page with a narrative at all** —
it was built, tested, verified against the payload, and placed where the reader
could not see it.

Both sections are lifted out of the ternary now. Three tests, and a mutant that
re-hides them is killed by exactly the two written for it.

### THE TABLE IS "OUT OF RANGE", NOT "NOT ASSESSED"

> *"just mention these are out of ranges for those unassessed parameters that
> it and dont mention like these are unassessed parameters like that"*

The section listed all seventeen skipped parameters under **"Reported, not
assessed by this tool"**, with a paragraph about their being *"set aside …
not found normal"*. Both are statements about this platform's coverage in a
document that is supposed to carry findings.

It is now **ONE PARAGRAPH**, listing only the rows the LABORATORY marked
outside its own interval:

> **Marked outside the reference interval by the laboratory:** NEUTROPHILS 82 %
> (40-70, high); LYMPHOCYTES 14 % (20-40, low); ESR 45 mm/hr (0-20, high);
> C-REACTIVE PROTEIN(CRP) 38.9 mg/L (<= 5, high).

**No heading, no table, no section of its own** -- the reader asked for these as
ordinary prose, and they are right: a handover note is paragraphs, and a
bordered grid under its own heading reads as a separate document stapled to
it.

| | skipped | shown |
|---|---|---|
| `Test 3.pdf` | 17 | **4** — NEUTROPHILS 82 %, LYMPHOCYTES 14 %, ESR 45 mm/hr, CRP 38.9 mg/L |
| `Test 2.pdf` | 17 | **10** — T.RBC, Polymorphs, Lymphocytes, Monocytes, PCV, MCH, MCHC, ESR, CRP, SGPT |

Four is the same four the patient page reports as *"your laboratory marked 4
further results outside its own range"*, which is the check that the two pages
agree: both filter on `labFlaggedAbnormal`, the producer's own boolean, and
neither re-derives it.

> **THE PAYLOAD STILL CARRIES ALL SEVENTEEN.** The filter is in the renderer,
> not the controller, so nothing was thrown away at the source — a later reader
> of that endpoint still gets the full list. **A section headed "Out of range"
> must not appear over an empty table**, so a report whose skipped parameters
> are all in range renders nothing at all; that has its own test, as does a
> parameter flagged `normal` being left out.

### MODULE 34 LEAVES THE CLINICIAN PAGE, AND THE LINE MOVES INSIDE THE DOCUMENT

> *"remove that random glucose bottom one why it came? and add the below ones
> also in those white box only not as separate"*

**Both done.** The general-context block — *"a raised random blood glucose
result is commonly associated with diabetes or prediabetes…"* — is gone from
this page, and the out-of-range sentence now renders INSIDE the passage rather
than as a sibling of it, which is what was drawing its own box.

The context blocks are patient-facing writing: a clinician does not need to be
told what a raised glucose is associated with. They remain on the patient
dashboard, which is where they were asked for.

> **AND IT CLOSES AN OPEN DEFECT FOR FREE.** §6at recorded that the two pages
> evicted each other's `findingContext`: the dashboard asks about 12 findings
> on Test 2, the clinician page about 1, both write the same field, and each
> visit invalidated the other and paid model calls to rebuild. **The clinician
> page no longer makes the request at all**, so there is only one writer left
> and nothing to evict. A feature removed on taste turned out to be the fix for
> a defect logged on quota.

`outOfRangeLine` is built once and rendered in BOTH branches of the passage
rather than after them. One constant, two call sites — duplicating the markup
would let the two copies drift.

### ⚠ TWO SELF-INFLICTED FAULTS IN THAT ONE EDIT, BOTH CAUGHT BY THE RUNNER

**1. A JSX COMMENT INSIDE A TERNARY, AND THE SUITE REPORTED NO TESTS AT ALL.**
Moving the block carried its `{/* … */}` with it into an expression position,
where it is not valid. Vitest reported:

```
Test Files 1 failed · Tests no tests
{ total: 0, passed: 0, failed: 0, failedSuites: 1 }
```

> **§6ar'S RUNNER FAULT, ARRIVING FOR THE THIRD TIME AND CAUGHT IMMEDIATELY.**
> `numFailedTests` was honestly zero because the file never compiled. The check
> that caught it is the one §6ar wrote down: **assertion count per file, and
> `numFailedTestSuites` — never the failure count.**

**2. A `const` IN THE TEMPORAL DEAD ZONE.** `outOfRangeLine` reads
`outOfRange`, which is derived from `data`, which only exists past the early
returns. Declared above them it threw *"Cannot access 'outOfRange' before
initialization"* on every render — 32 of 47 tests, all with the same message,
which is what a single structural fault looks like as opposed to 32 problems.

### ⚠ TEST 2'S GLOSSARY WAS STALE, NOT BROKEN — A STORED RESULT FROM OLD RULES

The reader: not all parameters are covered in "What these results mean" on
Test 2. Correct, and the code was right — the stored result was old.

```
Test 2  analysis v3   entries=8   skipped_over_limit=2   9 names never asked
Test 3  analysis v5   entries=17  skipped_over_limit=0   0 missing
```

Test 2 was analysed BEFORE §6ar's `358ba92`, which stopped filtering to the
tests the laboratory had flagged and raised `MAX_PER_REQUEST` 8 → 24. Under the
old rules it got:

* **8 described** — lab-flagged, up to the old cap of 8;
* **2 flagged and cut by the cap** — `CRP`, `SGPT`;
* **7 never requested** — `WBC Count`, `Platelet count`, `Eosinophils`,
  `Basophils`, `MCV`, `Estimated Average Glucose`, `TSH`, all unflagged.

**The arithmetic is the proof, and it came from a separate count:** Test 2 has
exactly **10** lab-flagged out-of-range parameters, and 8 + 2 = 10.

> **A STORED RESULT IS AS OLD AS THE RULES THAT MADE IT.** Every report
> analysed before `358ba92` carries a glossary built by the filter and the cap
> of that day, and nothing about the current code will repair it. When a reader
> says a feature is incomplete on ONE report, check the stored artefact's age
> before the code — the same way a missing result means checking the lookup
> before the renderer.

### REFRESHING ONE STAGE WITHOUT RE-ANALYSING

A full re-analysis would re-run extraction over four pages and every downstream
stage, produce a new analysis version, and invalidate the `findingContext` and
narrative caches with it. The glossary was regenerated ALONE instead: 17 names
to `/explain/glossary`, the result written to `parameterGlossary`.

**The names came from the pipeline's own `unmappedTestNames`**, imported rather
than re-derived — it orders them by the extraction and filters to the rows the
feature stage actually skipped, and a second implementation here would be free
to disagree about what to describe.

Two guards on the write, because this touches the database directly:

* a `--dry` pass that prints the names and writes nothing, run first;
* **a refusal to write a result with FEWER descriptions than the one stored.**
  A partial regeneration replacing a fuller stored result would remove
  descriptions a reader is seeing today — the failure this whole section is
  about, arriving through the repair.

Result: `requested 17, generated 17, cached 0, withheld 0, skipped 0`, 82.9s.
**Both reports now have 17 of 17 described.**

> **GEMINI IS SPENT FOR THE DAY.** All three models in the chain — 3.6-flash,
> 3.5-flash and 3.5-flash-lite — hit their daily limits during this session.

### ▶ "NO DIRECTION" OVER A LINE THAT CLIMBS — AND THE REFUSAL WAS RIGHT

The reader, of their own blood-sugar chart: *"why no direction as the graph is
changing?"* The line runs 88 → 168. Module 28's actual answer:

```
blood_glucose   NOT_COMPARABLE_SAMPLE_TIMING   trend: null
   92    mg/dl  fasting    9 Sept
   88    mg/dl  fasting   11 Sept
  134.7  mg/dl  random    12 Sept
  168    mg/dl  random    13 Sept
```

**The first two readings are FASTING and the last two are RANDOM.** Most of the
climb is the change of test, not a change in the reader — so the refusal is
correct, and naming a direction there would have been the invention this
project exists to avoid.

> **THE SERVICE HAD ALREADY EXPLAINED ITSELF AND THE PAGE PUT IT SOMEWHERE
> ELSE.** `trend.reason` carried the whole sentence — *"Blood glucose readings
> were taken under different sample timings (fasting, random). Those are not
> comparable quantities, so no trend is reported."* — and `Timeline.jsx`
> rendered it **in the table below the charts**. Which is no use to somebody
> looking at the picture: the panel said "no direction", the chart drew a
> rising line, and the two contradicted each other with the reconciliation a
> scroll away.

The sentence is now on the panel it belongs to. Nothing was generated and
nothing was reworded — it was in the payload the whole time, rendered in the
wrong place.

> **AN EXPLANATION IN THE WRONG PLACE IS CLOSER TO A MISSING ONE THAN IT
> LOOKS.** Every check this project runs said this was working: the payload had
> the reason, the page rendered the reason, a test asserted the reason. It took
> a reader looking at a picture to find that none of that put it where the
> question is asked.

### STILL OPEN ON THAT CHART

**The line is still drawn across all four points.** If two of them are fasting
and two are random, connecting them asserts a continuous series that the panel
immediately refuses to characterise. The text now resolves the contradiction;
the picture still states it. Not comparable readings arguably should not be
joined by one stroke at all — that is a chart change and it was not made here.

### WHAT MODULE 28 ANSWERS FOR THIS ACCOUNT, IN FULL

```
hba1c            TREND_CLASSIFIED               worsening
vitamin_d        TREND_CLASSIFIED               improving
vitamin_b12      TREND_CLASSIFIED               improving
creatinine       TREND_CLASSIFIED               improving
cholesterol      TREND_CLASSIFIED               stable
triglycerides    TREND_CLASSIFIED               stable
bmi              TREND_CLASSIFIED               stable
blood_glucose    NOT_COMPARABLE_SAMPLE_TIMING   --
hemoglobin       CLINICAL_DIRECTION_UNKNOWN     --
age              NOT_TRENDABLE                  --
smoking_history  NOT_NUMERIC                    --
gender           NOT_NUMERIC                    --
```

### AND WHAT POPULATION CONTEXT COVERS, CHECKED AT THE SAME TIME

Seven features have a published distribution — `bmi`, `cholesterol`,
`creatinine`, `hba1c`, `hemoglobin`, `vitamin_b12`, `vitamin_d`. On Test 3 that
is **8 examined, 4 banded, 4 refused**, and the page accounts for every one:
four cards, a card for `blood_glucose` carrying its full message, and the three
non-measurements named in a single line. **Nothing is dropped**, and the
backend deliberately forwards uncovered features rather than filtering them, so
a second coverage table cannot drift from the service's.

> ⚠ **BUT THE GLUCOSE EXCLUSION MESSAGE IS WRONG ABOUT WHY.** It says *"neither
> this service nor the uploaded report reliably records fasting status"* —
> and `clinical_rules.sample_timing()` recovers exactly that from the printed
> name (`RANDOM BLOOD GLUCOSE ( RBS )` → `random`), which is how Module 20 knew
> to use the 140 post-load boundary instead of the 126 fasting one, and how the
> trend refusal above was reached.
>
> The OUTCOME is still right for two other reasons: no glucose distribution is
> shipped at all, and the backend sends Module 31 only `feature/value/unit`, so
> the timing never reaches it. But *"the information does not exist"* forecloses
> the option, while *"we ship no table and do not forward the timing"* is a
> choice someone could revisit. **The same wording appears in three places**
> (`policy.py`'s message, `populationController.js:122`, `Population.jsx:178`)
> and is unfixed.

### ▶ "STABLE" OVER A LINE THAT FALLS FROM CEILING TO FLOOR

The same reader, on the next chart down. Cholesterol 186 → 172, drawn as a
cliff, labelled **stable**. Both were true:

```
cholesterol   TREND_CLASSIFIED   trend: stable   direction: falling
  186 -> 172 mg/dl   =  -14 mg/dl,  -7.53 %
  stability band: 17 %  (floor 5 mg/dl)   exceeded: false
  basis: RCV = sqrt(2) * 1.96 * sqrt(CVa^2 + CVi^2)
         CVa 2.5 %, CVi 5.7 % -> 17.3 % -> 17 %
```

**A 7.5 % fall is smaller than the test's own variation** — two draws from an
unchanged person can differ by that much — so `stable` is the right word, and
the service records `direction: falling` separately rather than pretending
nothing moved. Nothing was wrong with the classification.

### THE AXIS WAS THE LIE, AND IT IS A LIE EVERY CHART TOLD

`domainFor()` spanned the readings and nothing else. **So every change filled
the box, whatever its size.** A 7.5 % move and a 70 % move drew the same
picture, and the only thing distinguishing them was a word in the corner that
the picture contradicted.

The domain now includes **the span a change would have to cross to count** —
the service's own `significant_change_pct` and `min_absolute_change`, measured
from the baseline the change is measured from. Inside the band the line is
visibly shallow; a trend that exceeds the band still runs past it. Measured:
the same two readings now occupy **less than half** the height they did.

> **NOTHING IS DRAWN FOR THE SPAN AND NOTHING NEW IS LABELLED.** It sets the
> scale only. The axis numbers are still the highest and lowest actual
> readings -- 186 and 172 -- because every number printed on that chart is a
> reading somebody took. A test asserts 154 and 218 never appear.

### AND THE PANEL NOW SAYS WHAT STABLE MEANS

The `reason` field already carried it. The panel explanation added earlier
showed only when there was NO direction, so "stable" -- the other case where
the words and the picture disagree -- still said nothing. It shows for both
now, and for neither when the service gave no sentence.

> **TWO FIXES FOR ONE COMPLAINT, AND THEY ARE NOT ALTERNATIVES.** The sentence
> explains the contradiction; the axis removes it. Text that talks a reader out
> of what they can see is the weaker half -- **a chart whose steepness means
> nothing should not be argued with, it should be rescaled.**

Four mutants, all killed: the span dropped from the domain, the percentage
ignored in favour of the absolute floor, stable panels silenced, and a reason
invented when the service gave none.

### ▶ THE TIMELINE SHOWED 14 PARAMETERS AND THE REPORTS CARRY 28

The reader: the timeline only covers the fixed parameters, not all of them.
Correct, and the reason was structural rather than a bug — Module 28 trends
CANONICAL features, and a canonical feature is one the pipeline can identify
across two reports and express in one unit. Everything this platform does not
assess has neither, so **CRP 12.1 → 38.9 mg/L, a tripling across two reports,
was nowhere on the timeline.** Not refused, not explained: absent.

### THE DIFFICULTY IS NAMES, AND IT IS THE SAME DEFECT A THIRD TIME

On this account: **28 distinct printed names across 4 reports, of which SIX
repeat as exact strings.** Five more are the same test in a different case.
And the one that matters most matches by neither route:

```
"CRP (C-REACTIVE PROTEIN)"   vs   "C-REACTIVE PROTEIN(CRP)"
```

Same test, same words, different order — §6aq's parenthetical and §6ar's
"Grams/dL" again, with the consequence reaching the reader as an absence.

**So the key is the SET OF WORDS, sorted.** `crp` + `creactive` + `protein` in
either arrangement is one key. That took the account from 6 matched to
**22 considered, 10 plotted, 2 blocked, 10 seen only once** — and CRP is on the
timeline.

> **SET EQUALITY, NOT SIMILARITY, AND THE LINE IS DELIBERATE.** Two names match
> only when built from exactly the same words. Nothing is fuzzy and nothing is
> scored: `Free Frimbulator` does not match `Frimbulator`, and there is a test
> for it. A similarity threshold here would be the file guessing that two tests
> are the same — the class of guess this codebase refuses everywhere else.
> Duplicate words are kept too, so `total total protein` cannot collapse into
> `total protein`.

### THREE THINGS IT IS NOT ALLOWED TO DO

1. **NO DIRECTION, EVER.** There is no polarity for these parameters and no
   stability band — nothing knows whether a rising ESR is better or worse, or
   how much movement is noise. Module 28 refuses to classify without both, and
   so does this. A test asserts no panel carries a direction element.
2. **NO UNIT IS ASSUMED.** Reports disagreeing about a unit BLOCK the series.
   `U/L` and `IU/L` are the same to a clinician, and `g/dL` and `%` for MCHC are
   numerically close — and this file treats none of that as known, because two
   scales on one axis is the failure §6z caught once. **A blocked series still
   shows its readings**; it just draws no line. On this account that is MCHC and
   SGPT.
3. **NOTHING IS DROPPED SILENTLY.** Ten parameters appeared on only one report;
   the page says so rather than showing nine panels and letting the reader
   assume nine was the total.

### ⚠ THE SCALE CAVEAT, STATED RATHER THAN DESIGNED AROUND

The assessed charts are now drawn against the band a change must cross to
count. **These have no such band and no reference interval reaches this page**,
so their vertical scale spans only the readings — which makes any change fill
the box, the very thing fixed one section above. The page says so in a line.
That is the honest option available today; the fix is to carry the
laboratory's own printed interval into the history snapshot, which would mean
changing what Module 28 receives and was not done here.

### BUILT WHERE IT CANNOT DISAGREE

`labSeriesService` reads `historyService`'s own snapshots — the same objects
Module 28 receives — so the two cannot differ about which reports are in the
history or in what order. `featureValidation.unmapped` was already on them; no
projection changed and no query was added.

**EVERY TEST FIXTURE IS INVENTED** — `Zorblex`, `Quibblease`, `Frimbulator`.
There is no list of known tests in the service and there must be none in its
tests, or the suite would pass by recognising the fixtures instead of the rule
working. The reader asked for exactly this: *"this should work for any report
which contains any unknown parameters, don't rely only on these."*

Seven mutants, all killed: words unsorted, duplicates collapsed, units never
compared, one report accepted, one numeric reading accepted, the chronological
sort dropped, and the unit case not folded.

### STILL TO DO ON THIS

Nothing on Module 34's ceiling. Both real reports are described, stored and
rendering.

To force a re-request on a report that already has one, the script is §6as's
and it touches nothing else:
`Report.updateOne({_id}, {$unset: {findingContext: ''}})` — verified this
session to leave the analysis version, `clinicalReport`, `summaryProse` and
`parameterGlossary` intact.

> ⚠ **DRIVE A COLD REPORT THROUGH THE AI-SERVICE FIRST, NOT THROUGH THE PAGE.**
> The controller caches a PARTIAL result — §6ar's reasoning was that partial
> refusals come from the gates and would recur. **Quota exhaustion mid-batch is
> a second cause of a partial and that reasoning does not cover it**: a spent
> quota halfway through twelve findings would pin an incomplete result to the
> report until someone cleared it by hand. Warming the ai-service's process
> cache directly writes nothing to Mongo on failure, and the page load that
> follows is then free and complete. Both reports were done that way.

### KNOWN AND OPEN

**Raised this session and NOT fixed:**

* **The glucose exclusion message is wrong about why.** `policy.py`'s
  `EXCLUDED_FEATURES['blood_glucose']`, `populationController.js:122` and
  `Population.jsx:178` all say fasting status is not recorded. It IS —
  `clinical_rules.sample_timing()` recovers it from the printed name, which is
  how Module 20 chose the 140 post-load boundary and how the glucose TREND
  refusal was reached. The outcome is right for other reasons (no glucose
  distribution is shipped, and the timing is not forwarded to Module 31), but
  the stated reason is stronger than the truth in three places.
* **The trend chart still draws one line across non-comparable points.** The
  glucose panel now explains that fasting and random readings are not
  comparable, and then joins all four with a single stroke. The text resolves
  the contradiction; the picture still states it.
* **`labSeries` charts have no scale to judge against.** No stability band and
  no reference interval reaches that page, so their axis spans only the
  readings — the exact thing fixed for the assessed charts. The page says so.
  The fix is carrying the laboratory's printed interval into the history
  snapshot, which changes what Module 28 receives.
* **Ten of Test 2/3's unassessed parameters appear on only one report**, so
  they can never form a series. Nothing to do about it here; stated on the page.

**Carried forward, unchanged:**

* `--rust` is 4.38:1 on `--header` (§6am).
* "stability band" in one trend sentence (§6an-i).
* `origin: report_transcription` on profile rows (§6w) — this is what put the
  internal key `bmi` into a clinician's document this session.
* `MISSING_PROFESSIONAL_REFERRAL` does not block (§6r, §6k D1).
* Module 32's payload still nests `present` two ways (§6w).
* **Frontend fixtures are still hand-written** — two real payloads to generate
  them from.
* The ai-service suite still needs `.env` moved aside. Fix `conftest.py`.
* `RangeChart.jsx` is orphaned since f3d0963.

**Closed this session:**

* ~~The certainty gate's `indicate` gap~~ — was a plural subject evading the
  whole gate, in every verb. Swept to base forms.
* ~~Module 34's six-finding ceiling~~ — was already dropping a raised CRP.
  Ceiling 16, with the cache that makes it affordable.
* ~~The two pages evict each other's `findingContext`~~ — the clinician page no
  longer requests it at all.

### ⚠ GEMINI IS SPENT FOR 2026-09-16

All three models in the chain — `gemini-3.6-flash`, `gemini-3.5-flash`,
`gemini-3.5-flash-lite` — hit their daily limits during this session. Roughly
45 calls went on Module 34 across both reports, two clinician narratives, and
Test 2's 17 glossary descriptions. **Anything needing a model will refuse until
the quota resets**; every refusal path renders nothing, which is the designed
behaviour and looks identical to a bug if you do not check the log.

### THE DATA, AND WHAT IS CURRENT ON IT

| | |
|---|---|
| `Test 2.pdf` | analysis v3 · glossary refreshed to 17/17 · `findingContext` 12 entries · narrative CLEARED |
| `Test 3.pdf` | analysis v5 · glossary 17/17 · `findingContext` 7 entries incl. CRP · narrative CLEARED |

Both narratives were cleared deliberately, so the clinician page regenerates
against the current code on the next visit — one model call each, and the
quota is gone, so expect the composed passage until it resets.
---

## 6au. THE THIRD 2026-09-16 SESSION — READ THIS FIRST

**Two things, both on the timeline's `labSeries` section.** First, taken from
§6at's KNOWN AND OPEN: the charts had no scale to judge against. Closed.
Then the reader said the page still showed only the fixed parameters — **it
was showing 12 of the 22 on their reports**, and the other ten were counted
and never displayed. Also closed. Everything else in §6at still holds.

| | Tests | Last run |
|---|---|---|
| `backend/` | **722** passed, 3 skipped, 0 suites failed | 2026-09-17 ✅ |
| `ai-service/` | **3,903** passed, 7 skipped | **NOT RE-RUN — nothing in it changed** |
| `frontend/` | **363** passed, 0 suites failed | 2026-09-17 ✅ |
| **Total** | **5,016** | |

### THE HANDOVER'S OWN DESCRIPTION OF THE FIX WAS WRONG, AND CHEAPLY SO

§6at said the fix "is carrying the laboratory's printed interval into the
history snapshot, which changes what Module 28 receives." **It does not.**
`dashboardService.buildUnanalysedSection` already reunites an unmapped row
with its printed interval by joining `extraction.extracted_parameters` on the
exact `test_name`, per report, in this backend at read time. The same join
serves the timeline. `TimelineReportInput`, `UnmappedItem` and the ai-service
are untouched; **no Python file changed.**

> **A HANDOVER'S ESTIMATE OF A FIX IS A CLAIM ABOUT A DESIGN NOBODY PROBED —
> the same lesson §6at recorded about "wording decisions", one layer up.** Two
> minutes of reading the dashboard's own join replaced a schema change across
> a service boundary.

### ▶ WHAT THE PROBE FOUND, AND WHY IT CHANGED THE DESIGN

Before writing anything, the real `buildLabSeries` was run over the real
snapshots and each point joined back to its own report's stored extraction.
**The intervals are all there** — 23 of 24 point-rows carry a numeric bound.
**But the two reports disagree about the range on NINE of the ten plotted
parameters:**

```
ESR           0-20    and  0-20      <- the ONLY agreement
LYMPHOCYTES   22-45   and  20-40
MCV           78-100  and  80-97
MONOCYTES     5-7     and  1-8
CRP           < 6     and  < 5.0     <- one-sided: low is null
PCV           35-48   and  "F: 36 - 46 M: 40 - 50"  <- NEITHER bound
```

So there is no single interval, and **a drawn band would be asserting that one
laboratory's assay applies to the other's reading.** Two further shapes any
consumer must survive: a one-sided interval (`< 6`, `UP TO 40`), and a
sex-specific range the extraction correctly refused to reduce to one pair.

### THE DESIGN: IT SETS THE SCALE AND IS NEVER DRAWN

Exactly §6at's move for the significance span, one section up. A scale asserts
nothing about which interval applies; a rectangle does. **And `band` in
`TrendChart` is THIS PLATFORM's declared `polarity.optimal_low/high`** —
drawing a laboratory's interval in the same ink would merge two different
authors' claims into one shape, which is what `labFlag` / `labReferenceLow`
exist to keep apart.

* **`historyService.loadPrintedParameters`** — new. A SEPARATE, optional,
  owner-scoped query, the same construction as `describeExcluded`, because
  `assembleHistory` is shared by four endpoints and three have no use for
  this. Projects **four fields out of the array**, not the payload.
* **`buildLabSeries(snapshots, printed)`** — second argument optional, still a
  pure function. Points gain `labReferenceLow/High/Raw`; series gain
  `referenceScale` (the UNION, each bound taken independently),
  `referenceAgreement` (`agree`/`differ`/`none`) and `referenceCoverage`.
  Omit the argument and every series comes back unscaled — an older caller
  degrades to the old behaviour, never to a wrong one.
* **`TrendChart`** gains `scaleOnly`, which enters `domainFor` and is drawn
  and labelled nowhere. Axis numbers are still only readings.
* **The page's caveat was FALSE once this landed** — it said "There is no
  reference range here to judge one against". It now says the scale includes
  the printed range, that no range is drawn, and why: the reader's own reports
  do not all print the same one.

### ⚠ THE `+` PREFIX SILENTLY RETURNED NOTHING

`PRINTED_PROJECTION` was first written as
`'+extraction.extracted_parameters.test_name'`. **mongoose returned
`extraction: undefined`** — no error, no warning, and every chart quietly back
to spanning its own readings. `+path` re-includes a deselected path BY ITS OWN
NAME; on a SUBPATH of one it is not that. Naming the subpath plainly works.
Caught only because a test asserted on the loaded value, and confirmed by
running all four projection spellings side by side against the real schema.

### VERIFICATION

**15 mutants: 12 killed, 3 SURVIVED — and the survivors were the useful part.**
Every mutant was confirmed to apply (by grep count) and to parse before its
verdict was believed.

* **Two survivors were guards that no input could reach, and both were
  deleted.** An explicit `some(shape === null) -> 'differ'` branch in
  `referenceAgreementOf`: a null beside a non-null already makes the set size
  2, and a set of size 1 containing null is the all-null case answered one
  line above. And `!s.blocked &&` in `scaledCount`: `referenceScale` is
  already null for every blocked series. **Both read like they were doing
  work.**
* **The third survivor was KEPT, after a control proved the pattern.** The
  per-row `assertCanAccess` in `loadPrintedParameters` cannot fire — the query
  is already owner-scoped. So the SAME mutation was applied to the
  PRE-EXISTING re-check in `assembleHistory`: **it survives too, with 143
  tests passing.** This is the file's documented belt-and-braces convention
  for a filter someone widens later, not dead code introduced here. Deleting
  it would have made this one function the only unguarded one in the backend.

> **A SURVIVING MUTANT IS A QUESTION, NOT A VERDICT: "is this guard dead, or
> is it a convention?" The control mutant is what tells them apart**, and it
> took one run. Two guards were deleted and one kept on the strength of it.

### LIVE, ON THE REAL REPORTS

The production path itself — `assembleHistory` → `loadPrintedParameters` →
`buildLabSeries`, composed as `getTrends` composes them — run against Atlas
after restarting the backend. **10 of 10 plotted series scaled.** The measured
effect, as a fraction of the plot box the readings occupy:

```
LYMPHOCYTES     15 -> 14        81%  ->   3%
PLATELET COUNT  2.6 -> 3.03     81%  ->  12%
MCV             85.1 -> 88.6    81%  ->  13%
ESR             35 -> 45        81%  ->  18%
CRP             12.1 -> 38.9    81%  ->  66%   <- now the steepest on the page
```

**Every chart filled 81% of the box before, whatever the change meant.** CRP's
tripling past the upper bound and a one-point lymphocyte wobble inside a
25-point range drew the same picture. They no longer do.

### ▶ THEN THE READER SAID THE TIMELINE STILL SHOWED ONLY THE FIXED ONES

And they were right, in a way the section above had not addressed. **The
reports carry 22 unassessed parameters; the page showed 12** — ten charts and
two blocked. The other ten were counted (`singleReportCount`) and never
displayed, because a parameter on one report cannot make a series.

**A COUNT OF WHAT WAS LOOKED AT IS NOT AN ANSWER ABOUT WHAT WAS FOUND.**
"22 parameters considered" answers a question nobody asked while the ten they
were asking about were not on the page at all. Same failure mode as §6at's
`skipped_over_limit`, one layer out.

Fixed by listing them: `buildLabSeries` now returns `readings[]` beside
`series[]`, carrying the value AS PRINTED, the unit and the date — **no line,
no direction, no scale, and deliberately not in `series` so nothing downstream
can draw a trend through one point.** Non-numeric results (`Pale Yellow`,
`Negative`) are shown as text rather than rendered blank. Live: **22
considered, 22 visible.**

### ⚠ FIVE OF THOSE TEN ARE THE SAME FIVE TESTS, TWICE

The stored data, not a guess:

```
AVERAGE BLOOD GLUCOSE  154 mg/dL   |  Estimated Average Glucose  121.94
TOTAL WBC COUNT        9,300       |  WBC Count                  7,290
RBC COUNT              4.2         |  T.RBC                      4.04
TSH                    1.81 µIU/mL |  TSH (Thyroid Stim Hormone) 3.51 ulU/mL
NEUTROPHILS            82 %        |  Polymorphs                 77 %
```

Each pair is one test on both reports under names `nameKey` will not join —
extra words, or different words entirely. **They are listed as ten separate
readings and are NOT joined.** The owner was asked and chose set-equality:
joining them means either subset-matching (which would make `Free
Frimbulator` match `Frimbulator`, and free vs total hormone are different
tests) or a hand-written synonym table, which is clinical knowledge entering a
file that deliberately has none. **The option is open and the data above is
the evidence for it; nothing was inferred.**

Six more mutants, all killed: a trended series also listed as a reading,
`valueRaw` dropped, `readings` collected but not returned, the block not
rendered, the section hiding itself when there are readings but no charts, and
the unit dropped from a listed reading.

### ▶ THEN THE READER LOOKED AT IT AND ASKED FOR THE COMMENTARY TO GO

They sent a screenshot. The section was headed **"Other parameters on your
reports"**, described them as values *"this tool does not assess"*, and
carried three paragraphs: that nothing here is interpreted and no condition is
derived, that the scale includes the printed reference range, and that no
range is drawn because the reports disagree. Then a fourth line counting what
was considered, and a sub-heading "Reported once, or not as a number".

*"dont make as separate and dont mention separately... add those also on
normal like things... dont mention any unnecessary things."*

**All of it is gone.** The panels now sit in the `Trends over time` card with
the assessed parameters, as ordinary disclosure rows.

> **THIS IS §6at's LESSON A FOURTH TIME, AND IT WAS RIGHT A FOURTH TIME. Every
> control those paragraphs described is still enforced — none of them was ever
> enforced BY the paragraph.** No direction is emitted because
> `labSeriesService` produces none; no band is drawn because `scaleOnly` never
> reaches `hasBand`; two units are never joined because `TrendChart` refuses.
> **Removing a description of a guarantee is not removing the guarantee** —
> and a panel carrying no direction badge asserts nothing, so nothing had to
> be said to make it safe.

A blocked series is now listed rather than charted, in the same shape as a
one-report reading: **a unit disagreement is a result, not a reason to
withhold the numbers**, and it no longer needs its own prose block to say so.
`.lab-series__blocked` was deleted and `.trend-chart__readings` replaces it.

**Live: 22 panels in one card — 10 with a chart, 12 as readings.** Three more
mutants killed: a blocked series charted instead of listed, the panels not
rendered into the card, and the card's "No parameters could be followed"
empty state returning beside ten real panels.

**Four tests were DELETED, not adapted** — they asserted the wording of
paragraphs that no longer exist. A test that pins removed prose is a test that
will be made to pass by putting the prose back. **One test replaces them and
pins the removal**, listing every phrase that must not reappear.

### ▶ "THE STATUS IS NOT SHOWING WHETHER STABLE OR IMPROVING OR WORSENING"

The reader, on the merged panels. **Those three words cannot be produced for
these parameters and were not.** Each needs something no part of this pipeline
has for a test it does not assess:

> **⚠ SUPERSEDED BY §6av — AND THE ANALYSIS BELOW IS STILL WHY.** Module 35
> now produces all three, by obtaining the two missing inputs named below from
> the model FROM A TEST NAME ALONE and handing the classification to Module
> 28's own classifier. **What was wrong here was "cannot", not the reasoning.**
> The two things the words need were identified correctly; the section simply
> concluded that nothing could supply them without asking what could be asked
> for safely. Read the list below as the specification Module 35 was built
> against, then read §6av.

* `improving` / `worsening` need **POLARITY** — whether a rising ESR is better
  or worse for this person. Module 28 itself refuses that with
  `CLINICAL_DIRECTION_UNKNOWN` rather than guess.
* `stable` needs a **STABILITY BAND**. Without one, a 7 % move called "stable"
  states something nobody measured — the hazard `Timeline.jsx`'s own header is
  about, and the most repeated one on this project.

**Two TRUE statuses are shown instead, and together they answer what was
actually being asked:**

1. **`rose` / `fell` / `no change`** — arithmetic on the reader's own first and
   latest readings, claiming nothing about meaning. **Deliberately
   uncoloured**: green and rust on this page mean better and worse, and that
   is precisely the judgement not being made. Module 28 keeps the same
   separation — cholesterol came back `trend: stable` with
   `direction: falling`, both true.
2. **`High` / `Low` / `In range`** — **the laboratory's own marking** of the
   latest reading, from `extraction.flag`. Same three words and the same
   wording `Dashboard.jsx`'s `labFlagVerdict` uses, so one laboratory verdict
   cannot appear differently on two screens. Carries a `title` attributing it
   to the laboratory in the markup, not only in a comment.

**A NULL FLAG RENDERS NO CHIP AT ALL.** "Not checked" is not "In range", and
on real data that distinction is load-bearing: **PCV's older report marked it
low and the newer marked nothing**, so `latestFlag` is strictly the last row's
flag and never the last row that happened to carry one. Reaching back would
present a stale verdict as the reader's current status. `Estimated Average
Glucose` is the other one, and both come back blank.

A **blocked** series gets no movement word either: 101.9 U/L and 13 IU/L may
be the same measurement twice, and "fell" would assert a change the same file
refused to draw a line through.

Live, all 22 panels:

```
C-REACTIVE PROTEIN(CRP)   12.1 -> 38.9   rose       High
ESR                       35 -> 45       rose       High
LYMPHOCYTES               15 -> 14       fell       Low
BASOPHILS                 0 -> 0         no change  In range
PCV                       34.4 -> 37.9   rose       (none - latest marked nothing)
SGPT (blocked)            101.9 -> 13    (none)     In range
NEUTROPHILS               82             --         High
```

Seven more mutants killed: movement on a blocked series, `latestFlag` reaching
back to an older marking, an unmarked value reported as `normal`, the
movement comparison inverted, a null marking rendered as "In range", the
movement word borrowing `trend--worsening`, and the marking losing its
attribution.

### KNOWN AND OPEN

**Not verified here:** the rendered page. All three services are up and the
backend was restarted onto this code, but signing in needs the owner's
credentials. The data is proven at the service boundary and the rendering is
pinned by 9 new frontend tests (including one asserting no band rectangle
appears); **nobody has read the screen aloud**, which on this project is the
step that has found what green suites did not, six times.

**Raised and NOT fixed:**

* **`referenceAgreement` is computed and never shown per panel.** The section
  says once that the reports disagree; a reader looking at ESR — the one
  parameter where they AGREE — is told the general thing. The field is there
  to make that fixable.
* **PCV is scaled from ONE report's interval** (`referenceCoverage 1/2`) and
  the panel does not say so. It is not wrong, but it is one laboratory's range
  presented with the same confidence as a series where both agree.

**Carried forward from §6at, unchanged:** the glucose exclusion message wrong
about why (three places); the trend chart drawing one line across
non-comparable glucose points; ten unassessed parameters appearing on only one
report; `--rust` at 4.38:1; `origin: report_transcription`;
`MISSING_PROFESSIONAL_REFERRAL` not blocking; Module 32's two-way `present`;
hand-written frontend fixtures; **the ai-service suite still needing `.env`
moved aside**; `RangeChart.jsx` orphaned.

**Closed this session:** ~~`labSeries` charts have no scale to judge against~~.

### ⚠ GEMINI WAS STILL SPENT — AND NOTHING HERE NEEDED IT

No stage in this change calls a model. The quota state was irrelevant to it,
which is worth knowing: a task picked off the open list that needs no model is
the one to take on a spent day.

---

## 6av. THE 2026-09-17 SESSION — READ THIS FIRST

**Three things, and the first one was already built when the session opened.**
Module 35 was sitting in an uncommitted working tree with no handover; the
other two came from the reader driving the timeline. Everything is committed
now, one commit, tree clean.

| | Tests | Last run |
|---|---|---|
| `backend/` | **725** passed, 3 skipped, 15 suites, 0 failed | 2026-09-17 ✅ |
| `ai-service/` | **3,931** passed, 7 skipped (3,938 collected, 0 failures, 0 errors) | 2026-09-17 ✅ (`.env` moved aside) |
| `frontend/` | **368** passed, 0 suites failed | 2026-09-17 ✅ |
| **Total** | **5,024** | |

### ▶ THE SESSION OPENED ON 14 UNCOMMITTED PATHS AND NO RECORD OF THEM

`git status` first, per §0. It found what §0 promised — and two things §0 had
wrong, both because §0 was written before the last commit rather than after:

* **`main` was at `5ba63a6`, not `5fb20f9`.** A commit had landed after that
  warning was written and had already saved part of what the warning listed.
* **The 14 dirty paths were NEWER work than the warning described** — a whole
  feature, Module 35, that no section of this file mentioned. §6au does not
  name it. Its only trace was a filename in §0's list.

> **A HANDOVER IS WRITTEN AT A MOMENT AND THE TREE MOVES AFTER IT.** §0's
> warning was accurate when written and wrong in two particulars by the time
> it was read, in the direction that matters least (work was safer than
> described) but by the same mechanism that could have made it worse. The
> `git status` is what closes that gap, and it is why it is the first action.

### MODULE 35 — improving / worsening / stable FOR A TEST THIS PLATFORM DOES NOT ASSESS

Found uncommitted, read from the source rather than from a description, and
committed as it stood. It closes §6au's "the status is not showing whether
stable or improving or worsening", which §6au had concluded was impossible.

**THE PROMPT CONTAINS A TEST NAME AND NOTHING ELSE.** Not the value, not the
change, not the range, not the flag, not the age or sex. So the answer is a
property of the TEST -- true for anyone who ever takes it -- and the model is
never in a position to interpret this person's result. Same narrowing as
Module 27b (`parameter_glossary`), and for the same reason.

**THE MODEL DOES NOT CLASSIFY.** It supplies a polarity and two variation
figures (CVa, CVi). The service computes
`RCV = 2**0.5 * 1.96 * sqrt(CVa**2 + CVi**2)` with
`trend_polarity.reference_change_value` — the same function that produced
every row of the hand-written STABILITY table — and the classification is made
by `trend_analyzer._classify` and `_is_significant`, the SAME two functions
Module 28 uses for assessed features. **There is one trend classifier in this
service and Module 35 did not become a second one.**

* **The model never supplies a reference range.** When the polarity is
  `best_within_range`, the interval is the one the PATIENT'S OWN LABORATORY
  printed, passed in by the caller. §6v records an invented range reaching a
  patient already.
* **A CV outside `CV_PERMITTED` refuses the WHOLE entry rather than being
  clamped.** A clamped hallucination is still a hallucination wearing a
  plausible value.
* **An entry needs both halves.** Polarity without a band would call a 0.1 %
  wobble "worsening"; a band without polarity cannot say which way is better.
* **`basis` carries the arithmetic and its inputs**, labelled `PENDING
  INDEPENDENT VERIFICATION`, so a reviewer can recompute it.
* **It cannot break the timeline.** `timelineController` catches every failure
  — spent quota, unconfigured key, timeout, service down — and passes the
  built series through unchanged, which is what the page rendered before this
  existed. The failure is logged with a stage name, a code and a count, no
  PHI.
* **`labPolarityTimeoutMs` is its own budget**, not the trends one. The
  comment names the §6as borrow-the-wrong-budget defect before it can fire.
* **`attachVerdicts` branches on `outcome`, never on `trend`**, and matches by
  the exact name that was sent. A fuzzy match would put one test's verdict on
  another's panel, which is the worst failure this feature can have.

Tests: **22 in `test_lab_polarity.py` plus 6 through the HTTP route** in
`test_explain_endpoint.py`. The route tests exist because of §6w — a module
can be perfect and unreachable, and anything with a route needs one test that
goes through the route.

**LIVE, ON THE REAL REPORTS.** Gemini's quota had reset. One probe first, to
learn whether the feature could run at all before concluding anything from a
blank screen:

```
ESR   35 -> 45   TREND_CLASSIFIED   stable   threshold 62.0 %
```

Then through the page, all 10 trended laboratory series classified. CRP
`worsening` (118 % threshold, 12.1 -> 38.9), MCV / LYMPHOCYTES / MONOCYTES /
PLATELET COUNT / ESR `stable`, PCV `improving`.

### ⚠ ESR READS `stable` AND `High` OVER A RISE FROM 35 TO 45, AND IT IS RAISED FOR THE OWNER

Not a defect. The model returned CVa 10.0 % and CVi 20.2 %, giving a reference
change value of **62 %**; a 28.6 % rise does not cross it, so `stable` is the
honest answer to the question asked. The panel still shows `rose` and the
laboratory's `High` beside it, so nothing tells the reader they are fine.

**But a 62 % threshold calls almost any ESR movement stable, and the figures
behind it are labelled pending verification.** Raised with the owner and NOT
resolved. This is the one thing on Module 35 that wants a human decision
rather than a test.

### ▶ THE READER ASKED FOR THE TRENDS TABLE TO GO

A screenshot, circling the `Parameter / Direction / First → latest / Readings`
table under the charts: *"i dont need this part as already above trends parts
are there."*

**Checked before cutting, and the check changed the scope.** Of its 12 rows,
**nine were pure duplication** — the chart above each one carried the same
direction word and the same refusal sentence. **Three were not:** `age`,
`sex` and `smoking_history` get no chart, so the table was their only row on
that card. The owner was asked and chose to drop them; they are still named
for a reader in the comparison table below.

Deleted with it: `TrendRow`, and `rowHeading` — which existed only because
that table once printed `trend.feature` raw and put `hba1c` and
`smoking_history` on a patient's screen. **The chart headings use
`PATIENT_LABEL` and always did, so the fix did not leave with the function.**

**The empty-state condition had to move.** It hung off `features.length`,
which was safe only while a table printed a row per feature. A payload of
nothing but unchartable features would now have left the card blank — no
panels, no line, nothing said. It now hangs off `charted`, computed once and
shared with the map, because a second copy is how the two come to disagree.

**SIX FIXTURES WERE LYING ABOUT THE PAYLOAD AND THE SUITE HAD NEVER MINDED.**
They declared `usable_point_count: 1` or `: 2` and then carried no `points`
array — a shape Module 28 does not produce. They passed because the table
printed a row whether or not there was anything to plot. With the table gone
those features render nothing and the tests failed. **They were given their
real points rather than having their assertions weakened.** One test asserted
prose that no longer exists anywhere and was deleted; one new test pins the
removal by listing the four column headings and the row phrasings that must
not reappear.

### ▶ THEN THE NUMBERS WERE MISSING FROM THE SHUT ROW, AND THAT WAS REAL

Removing the table took its `First → latest` column with it, so a reader
scanning closed panels saw `HbA1c ... worsening` and had to open a panel to
learn from what to what. Raised, and the owner asked for it back.

`ChangePair` puts it on the collapsed row of both kinds of panel. **It selects
nothing and computes nothing:** Module 28's own `change.first_value` /
`change.last_value` for an assessed feature, and `movementFrom` /
`movementTo` for a laboratory one — added to `labSeriesService` for this.

**A PAIR IS SHOWN ONLY WHERE A CHANGE WAS ESTABLISHED.** 18 of 31 rows carry
one, and every row without one is a case where a pair would assert something:

```
MCHC, SGPT    blocked (g/dL vs %, U/L vs IU/L) -- an arrow would claim the
              comparison the service refused to draw a line through
Blood sugar   Module 28 supplies no `change`: four readings mixing fasting
              and random. Haemoglobin, by contrast, shows 9.2 -> 12.5 g/dl
              beside `no direction` -- change known, meaning not.
10 readings   one report only; one reading is not a change
```

**Uncoloured, deliberately.** Green and rust mean better and worse on that
page, and two readings mean neither — the same separation §6au made for the
movement word. **The unit prints once, at the end** (`2.6 → 3.03 Lakhs/cumm`,
34 characters down to 21). Printing it once ASSERTS both readings are in it,
and that holds exactly where the pair renders: `blocked` is the test that the
units agree, and a blocked series gets no pair.

### ⚠ I WROTE A FALSE JUSTIFICATION INTO TWO FILES AND CAUGHT IT ONE STEP LATER

`movementOf` was changed to return the two values with the word, and the
comment explaining why said a point could carry a null value at either end,
so a consumer reaching for `points[0]` would print numbers the word did not
describe. **That shape does not exist.** `points` is built from `numeric`,
which is already `entries.filter((e) => e.value !== null)`, so the filter
inside `movementOf` can remove nothing and `points[0]` would have been safe.

Publishing the pair from the service is still right — one comparison, one
place, so the word and the numbers cannot drift if the rule for WHICH readings
are compared ever changes. **But that is a different reason, and the comment
now says that one.** The filter is kept as this file's belt-and-braces
convention, on §6au's precedent for the re-check in `assembleHistory`.

> **A JUSTIFICATION IS A CLAIM ABOUT THE PRODUCER AND HAS TO BE READ THERE.**
> §6au's lesson was that a handover's description of a fix is a claim nobody
> probed. This is the same error one layer smaller and self-inflicted, in a
> comment written while making the change it describes. Two minutes reading
> `buildLabSeries` replaced an invented hazard with the real reason.

The lab-series test fixture had the matching fault: it did not set the new
fields at all, which would have exercised a no-pair path the backend never
returns. It now derives them the way the producer does. **That is the
`basis.limitations` trap from §6w — a fixture written to the consumer's
assumption cannot catch the assumption being wrong.**

### KNOWN AND OPEN

**Raised this session and NOT resolved:**

* **ESR's 62 % stability threshold**, above. The one Module 35 question that
  needs a person.
* **Module 35's CVa/CVi figures are unverified across the board.** Every
  `basis` string says so. Nobody has checked one against a published table.
* **`5.4 → 7 %` prints `7`, not `7.0`.** `formatValue` does not pad, so a
  pair can look like it has different precision on each end.
* The unknown-key chart heading prints the raw key as it stands
  (`some_new_marker`); the capitalisation the deleted table applied went with
  `rowHeading`. Pinned by a test either way.

**Carried forward from §6au and §6at, unchanged:** the glucose exclusion
message wrong about why (three places); the trend chart drawing one line
across non-comparable glucose points; `referenceAgreement` computed and never
shown per panel; PCV scaled from one report's interval without saying so; ten
unassessed parameters on only one report; `--rust` at 4.38:1;
`origin: report_transcription`; `MISSING_PROFESSIONAL_REFERRAL` not blocking;
Module 32's two-way `present`; **the ai-service suite still needing `.env`
moved aside** (fix `conftest.py`); `RangeChart.jsx` orphaned.

**Closed this session:** ~~Module 35 uncommitted and undocumented~~ ·
~~§6au's "those three words cannot be produced"~~ · ~~the trends table
repeating every chart~~ · ~~no numbers on a collapsed row~~.

### ⚠ GEMINI'S QUOTA HAD RESET, AND ONE PROBE IS HOW THAT WAS LEARNED

§6at and §6au both ended with all three models spent. On 2026-09-17 the chain
was available again. **One call to `/lab-polarity` established that before any
conclusion was drawn from a page** — the alternative is reading a blank panel
and debugging code that is working exactly as designed. Cost: one of twenty.

---

## 6aw. THE 2026-09-18 SESSION — READ THIS FIRST

**Driven entirely by the reader looking at two screens and counting.** Four
things, in the order they were found:

1. **A change of ZERO was being called significant** in the SHARED
   significance test. Reachable only through Module 35.
2. **MODULE 36** — which printed test names are the same test, from names
   alone. Ten stranded readings became five trended parameters.
3. **A HAND-WRITTEN VARIATION TABLE** takes precedence over the model, so a
   threshold stops moving between page loads and can be reviewed.
4. **The comparison card** brought to the same coverage as the timeline: 12
   rows → 25.

| | Tests | Last run |
|---|---|---|
| `backend/` | **762** passed, 3 skipped, 15 suites, 0 failed | 2026-09-18 ✅ |
| `ai-service/` | **4,022** passed, 7 skipped (4,029 collected, 0 failures, 0 errors) | 2026-09-18 ✅ (`.env` moved aside) |
| `frontend/` | **384** passed, 0 suites failed | 2026-09-18 ✅ |
| **Total** | **5,168** | |

**NINE things, not four.** Five were taken off this section's own open list
later the same day, three of them about units: the TSH OCR artefact, then
SGPT and MCHC, then the silent unit on eAG -- **and that last one exposed a
false `improving` on a rising blood sugar, which is the most serious thing
this session found.** The unit subsections are below the comparison one.

### ⚠ A CHANGE OF ZERO WAS SIGNIFICANT, IN THE FUNCTION EVERY MODULE SHARES

`trend_analyzer._is_significant`:

```python
absolute = abs(last - first)            # 0
if absolute < band.min_absolute_change: # 0 < 0.0 is False -- not caught
    return False
if first == 0:
    return True                         # <- a zero change, called significant
```

**Reachable ONLY through Module 35**, which passes `min_absolute_change=0.0`
because it has no canonical unit to set a floor in and documents that choice.
Every band in `trend_polarity.py` declares a positive floor (0.1 to 25.0), so
no assessed feature can reach the branch with a zero change. Checked before
touching shared code.

The symptom the reader saw: **BASOPHILS is 0 % on both reports**, so the zero
change was handed to `_classify` as a real one, which then refused to direct it
— and the panel showed "no change" with no trend word while every neighbour had
one. *"why some are showing stable even though there are changes in the
values?"* was the question about the OTHER rows; this was the row that had the
opposite problem.

Fixed with `if absolute == 0: return False`. **Mutation-tested**: the mutant
(`absolute < 0`, never true) was confirmed by grep to apply and by `ast.parse`
to parse, then KILLED by the test written for it. Reverted and re-checked.

### ▶ MODULE 36 — WHICH PRINTED NAMES ARE THE SAME TEST

`app/services/lab_name_match.py`. Ten of the reader's unassessed parameters
were five tests printed twice under names `nameKey` cannot join:

```
AVERAGE BLOOD GLUCOSE  ·  Estimated Average Glucose
TOTAL WBC COUNT        ·  WBC Count
RBC COUNT              ·  T.RBC
TSH                    ·  TSH (Thyroid Stim Hormone)
NEUTROPHILS            ·  Polymorphs
```

A parameter seen once has no first and no latest, so it can carry no direction
at all — not because anything refused, but because a change needs two numbers.
**Joining them is the only way those rows get one.**

* **THE PROMPT IS NAMES AND NOTHING ELSE**, and the request model has NO FIELD
  for a value — a stronger guarantee than Module 35's, which carries the
  readings and keeps them from the prompt by construction.
* **ONE CALL FOR THE WHOLE SET**, because "are these the same test" is a
  question about the set. Cached against the folded name set.
* **FIVE LOCAL GATES**: echo validation (a name not sent is dropped with its
  group), group-of-one, **a name in two groups invalidates BOTH** (there is no
  basis for preferring the one emitted first), the qualifier guard below, and
  a reported ceiling.
* **`joinedFrom` reaches the screen.** A reader whose report says `Polymorphs`
  is looking at a panel headed `NEUTROPHILS`; a join nobody can see is the page
  rewriting their report rather than regrouping it.
* **A WRONG JOIN CANNOT DRAW A LINE.** If two joined names disagree about
  units, `blocked` catches it and the series gets no scale, no movement and no
  pair — the safety net was already there.

**Backend:** `buildLabSeries(snapshots, printed, aliases)` — optional third
argument, same degradation pattern as `printed`; `unjoinedNames` and
`aliasMap`; a two-pass controller (build, ask, rebuild) where every failure
keeps the first pass.

**SERIES ARE NOT OFFERED FOR JOINING, only readings.** Merging two existing
series would silently redraw charts the reader has already looked at on the
strength of a model call. The case exists — a third spelling of an
already-trended test — and is left alone deliberately.

### ⚠ THE QUALIFIER GUARD, AND THE VERSION OF IT THAT WAS TOO WEAK

First version: contrast SETS, refused only when BOTH names carried a different
member. It caught `Free Frimbulator` vs `Total Frimbulator` and **let
`Free T3` vs `T3` straight through**, because the bare name carries no member
at all. Free and total are different tests, and §6au names that exact pair as
the reason not to subset-match.

Now: **the qualifiers present on each side must be the SAME SET.**

```
_QUALIFIERS = free bound direct indirect fasting random postprandial pp
              pre post left right
```

**`total` IS DELIBERATELY ABSENT** — it is a clarifier, not a qualifier.
`TOTAL WBC COUNT` and `WBC Count` are one test, and that is the join the module
was built for. The asymmetry is real: adding `free` selects a different
analyte, adding `total` names the whole of the one already meant. 12 of 12
cases correct, including `Free T3` vs `Free Triiodothyronine` → JOIN.

> **A CONTROL IN A PROMPT IS NOT A CONTROL.** The prompt already said free and
> total are different. That is an instruction, and the guard is what makes it
> true — this project's own repeated lesson, applied to a model's output for
> the first time.

### ▶ THE VARIATION FIGURES MOVED BETWEEN PAGE LOADS, SO THEY MOVED INTO A TABLE

`app/data/lab_variation.py`, 16 rows. The reader asked for the wobble limits to
be *verified*, after EOSINOPHILS was refused on one request and read `stable`
on the next **with the data unchanged** — the model had returned a different
CVi (63 % vs under 60 %).

* **THE TABLE IS CONSULTED FIRST.** A listed test costs NO model call at all:
  the row carries the polarity as well as the two figures, so the quota stops
  being a factor for the tests that matter most, and the verdict is
  reproducible.
* **A MISS FALLS THROUGH TO THE MODEL**, which is the previous behaviour.
* **THE TABLE IS NOT EXEMPT FROM THE CV GATE.** A typo here would reach a
  patient carrying the authority of having been reviewed.
* **EVERY ROW IS `verified=False`.**

> **⚠ THE NUMBERS ARE NOT VERIFIED AND THE FILE SAYS SO IN THREE PLACES.**
> They are literature-typical figures recorded WITH the source they should be
> checked against (EFLM Biological Variation Database; Ricós et al. 1999).
> **They were not read off that source.** `verified=True` may only be set by a
> human who has compared a row to its `source` — not by a model, not by the
> file's author, and not because the number looks reasonable.
> `test_no_row_claims_to_be_verified` fails loudly if one is flipped.
>
> What changed is not that the figures became trustworthy. It is that they
> became **stable, reviewable and attributable** instead of invisible.

**THREE SENTENCES, NOT ONE.** The old `basis` said "PENDING INDEPENDENT
VERIFICATION" on every verdict, which was honest and useless — there was no
table to go to, so it named a task nobody could start. Now it names the source
to check, or says plainly that there is none. The panel says which, in words:
*"That figure is from this tool's variation table and has not yet been checked
against its published source"* versus *"...produced by a language model from
the test name and comes from no reviewable source."*

**Rows a reviewer should take first**, and each says so in its own `source`:
**ESR** (sparse published data; the 62 % threshold is what made
`ESR 35 → 45 stable` possible), **EOSINOPHILS** (figures vary widely),
**BASOPHILS** (small, noisy counts).

### ⚠ THE SUMMARY LINE WAS COUNTING A SET THAT NO LONGER EXISTED

The reader circled it. `3 improving · 1 worsening · 3 stable · 5 not
determinable` over a card showing **twenty-six panels**. Both halves wrong:

* it was Module 28's tally of its **twelve assessed features** and counted
  none of the fourteen laboratory panels beside them, which now carry verdicts;
* three of the twelve it DID count — `age`, `sex`, `smoking_history` — are no
  longer rendered anywhere, because §6av's commit removed the table they lived
  in. **A count of rows the reader cannot see.**

Now `26 parameters · 4 improving · 2 worsening · 13 stable · 7 with no
direction stated`, computed from the same array that becomes the panels
(`labPanelsOf` was split out of `LabPanels` for exactly this), and `LabStatus`
shares the one `panelTrendWord` predicate instead of keeping its own copy.

> **A COUNT THAT CANNOT BE RECONCILED WITH THE ROWS UNDER IT IS WORSE THAN NO
> COUNT.** A reader who checks it and fails stops trusting the numbers that are
> right. The total is now stated so the four parts can be checked against it.

### ▶ THE CHART CONTRADICTED ITS OWN ROW, AND ONLY THE SCREEN SAID SO

`NEUTROPHILS` read `stable` on its row while the chart inside the same panel
said **"No direction was classified for them"** — `classified` and `trend` were
never passed to `TrendChart` from `LabPanels`. Correct before Module 35 existed
and wrong the moment it did. Passing them also earns the line its colour: a
classified `worsening` takes rust exactly as it does on an assessed chart.

**No test caught this. Reading the expanded panel did.** Seventh time on this
project.

### ▶ THE COMPARISON CARD CARRIED 12 OF 28 PARAMETERS

*"similarly for this comparison part also... i want all parameters to be there
which are in those 2 reports."* Same gap, same card-by-card discovery.

**`buildLabComparison` IS A TRANSFORM OVER `buildLabSeries`, NOT A SECOND
COMPARATOR.** Run that over only the two chosen reports and it already answers
everything a comparison row needs. A second grouping would mean two files
deciding that `Polymorphs` and `NEUTROPHILS` are one test, and eventually
disagreeing — in the same page.

* **MODULE 29's OWN CATEGORY VOCABULARY**, chosen by that module's documented
  precedence rather than translated: `improved` / `worsened` / `unchanged`
  from a Module 35 verdict, `changed_direction_only` when it moved and nothing
  will call that better, `newly_abnormal` / `newly_normal` from the
  LABORATORY's own marking — **and those outrank the change axis**, which is
  Module 29's rule, not a new one. `MCH 26.2 → 29.2 pg` reads `newly normal`
  live because the lab marked it low then normal.
* **A CROSSING IS CLAIMED ONLY WHEN BOTH REPORTS CARRY A MARKING.** PCV is
  marked low then unmarked; reading the absence as normal would invent a
  recovery the laboratory never stated.
* **PREVIOUS AND CURRENT ARE THE REQUESTED PAIR, NOT THE DATE ORDER** — keyed
  off `ComparisonPair.baseline_report_id` / `comparison_report_id`, read off
  the schema. The picker allows an out-of-order pair and Module 29 honours it,
  so one table must not have two ideas of which column is "previous".
* **A BLOCKED ROW SHOWS BOTH UNITS.** `101.9 U/L` against `13 IU/L` is the
  reason it cannot be classified; hiding one unit hides the reason.
* `labComparison` is a **separate response field** — `comparison` stays Module
  29's payload verbatim.

The two-model-call pipeline was **pulled out of `getTrends` into `labAliases`
and `labWithVerdicts`**, shared by both endpoints. Aliases are asked over the
WHOLE history so both cards join the same names and the second call is a cache
hit.

### ▶ TSH WAS ONE UNIT SPELLED TWO WAYS, AND `unitKey` NOW FOLDS OCR CONFUSABLES

Taken off this section's own open list. TSH is printed `1.81 µIU/mL` on one
report and `3.51 ulU/mL` on the other. **That is the same unit** — the
extraction read the micro sign as a `u` and the capital I as a lowercase l,
the two classic OCR confusions in one short string. Lowercasing left `µiu/ml`
against `ulu/ml`, so the series was blocked and the panel told the reader
their two reports disagreed about the unit. They do not; one was misread.

`unitKey` folds **two character classes and only two**:

* the micro sign — `µ` (U+00B5), Greek `μ` (U+03BC) and ASCII `u` — which was
  never only an OCR repair: `ug/dL` is how a laboratory prints µg/dL when the
  character set will not carry the sign;
* `i` and `l`, the same glyph to an OCR engine once case is gone.

**CHECKED AGAINST EVERY DISTINCT UNIT STRING IN THE REAL DATA BEFORE BEING
WRITTEN** — 20 of them, pulled off the rendered page. It merges exactly two
pairs, `ulU/mL`+`µIU/mL` and `umol/L`+`µmol/L`, both genuinely one unit. The
half that matters more is what stays apart:

```
mg/L    -> mg/i      vs  mg/dL   -> mg/di
U/L     -> u/i       vs  IU/L    -> iu/i
mmol/L  -> mmoi/i    vs  µmol/L  -> umoi/i
10^3/µL -> 10^3/ui   vs  10^6/µL -> 10^6/ui
```

**`SGPT` (U/L vs IU/L) AND `MCHC` (g/dL vs %) ARE LEFT BLOCKED ON PURPOSE.**
Enzyme activity is conventionally the same number in U/L and IU/L, and g/dL
and % are numerically equal for MCHC — but those are CLINICAL EQUIVALENCE
CLAIMS, not spelling repairs, and a unit conversion belongs in Module 5
upstream of storage. **DIGITS ARE NEVER FOLDED**, so `10^3/µL` can never merge
with `10^6/µL`.

**FOR COMPARISON ONLY.** `points[].unit` is untouched and the key never
reaches a screen; the panel shows `µIU/mL` because that is the newest report's
spelling. Live: `TSH 3.51 -> 1.81 µIU/mL stable`, and the timeline tally moved
with it — 14 stable, 6 undirected, from 13 and 7.

**Mutated in BOTH directions.** Removing the `i`/`l` fold was killed by the
TSH test; over-folding (adding `1` and `d` to the class) was killed by the
never-fold-a-digit test. Each mutant was confirmed by grep to apply and by
`node --check` to parse before its verdict was believed.

### ⚠ A MISSING UNIT WAS BEING REPORTED AS A DIFFERENT ONE

Found while fixing the above, and a separate defect. `AVERAGE BLOOD GLUCOSE`
is `154 mg/dL` on one report and `121.94` with **no unit** on the other, and
the row said the two reports gave it in different units. They do not: one gave
none. `blocked.units` could name only one of the two it claimed differed.

`blocked.reason` is now `unit_missing` when the only disagreement is an
absence, with its own sentence. **The outcome is unchanged** — an absent unit
cannot be confirmed to match a present one, so the readings are still not
compared — but the stated reason was false, which is this project's standing
failure mode in miniature.

> **⚠ AND MY FIRST FIX FOR IT SILENTLY DID NOTHING.** The branch read
> `blocked?.reason` where `blocked` was a `Boolean` a few lines above, so it
> was always `undefined` and every row fell through to the wrong sentence. The
> backend had been producing `unit_missing` correctly the whole time and its
> test passed. **Reading the row on screen caught it; no test would have** —
> the eighth time on this project that the screen found what the suite did
> not. There are now two frontend tests pinning both sentences.

### ▶ SGPT AND MCHC: A DECLARED EQUIVALENCE, NOT A SPELLING REPAIR

Also taken off this section's open list. `unitKey`'s folding is enough for one
unit misspelled; it is not enough for two different unit STRINGS that denote
the same scale:

```
SGPT   101.9 U/L   and  13 IU/L
MCHC   30.8 g/dL   and  33 %
```

Saying those are the same scale is a CLINICAL CLAIM, so it is written down in
`backend/src/services/unitEquivalence.js` where a reviewer can find it, not
folded into a regular expression. Each entry carries a `label`, a `basis` that
argues for it and names what to check it against, and `verified: false`.

**THERE IS NO CONVERSION FACTOR IN THAT FILE AND THERE STRUCTURALLY CANNOT
BE.** Every entry declares units whose numbers are ALREADY the same: 101.9 U/L
is 101.9 IU/L, and 33 % MCHC is 33 g/dL. Nothing is multiplied and no reading
is altered — the entries only decide whether two readings may share an axis. A
pair needing a multiplier IS a conversion and belongs in Module 5
(`unit_conversions.py`, whose own header calls itself safety-critical and
records the molar mass behind every factor). A test asserts no entry carries
any numeric field at all.

> **⚠ THE SCOPING IS THE LOAD-BEARING PART, AND IT IS WHY THIS COULD NOT GO IN
> MODULE 5's `UNIT_ALIASES`.** That table is a flat global string map. `%` is a
> MASS CONCENTRATION on MCHC and a PROPORTION OF THE WHITE CELL COUNT on the
> differential — so `g/dL == %` is true for MCHC and false everywhere else.
> Declared globally it would have made every haemoglobin in g/dL
> interchangeable with a percentage, which is the worst defect available in
> this area. `tests: ['MCHC', ...]` is what prevents it; `tests: null` is
> reserved for pairs where the unit strings are synonymous whatever the
> analyte, and the enzyme entry argues for that in its own `basis`.

Applied at the BLOCKING decision rather than inside `unitKey`, because that is
where the test name is known. The series records which declaration it relied
on, and the panel says so: *"Your reports label this test two ways, both
meaning units of enzyme activity per litre... That equivalence is a standard
convention and has not yet been checked against a published standard."*

**Mutation-tested on the scope guard** — making the MCHC entry global was
killed by THREE tests, one of them pre-existing. Live: `SGPT 101.9 -> 13 IU/L
improving`, `MCHC 30.8 -> 33 % improving`, and the tally moved to 6 improving
/ 2 worsening / 14 stable / 4 undirected.

> **⚠ EIGHT PRE-EXISTING TESTS USED `U/L` AGAINST `IU/L` AS THEIR EXAMPLE OF
> "TWO DIFFERENT UNITS".** Declaring the pair equal invalidated all of them at
> once — a useful signal that this codebase had been treating them as
> different. They were re-pointed at `U/L` against `U/mL`, which differ by a
> factor of 1000 and are not declared equivalent, so each fixture keeps its
> intent and is now a truer example than it was.

**`SGPT 101.9 -> 13 improving` is a substantial new clinical statement resting
entirely on the U/L == IU/L declaration.** It is labelled unchecked on the
page. It is the row to verify first.

### ▶ A SILENT UNIT IS NOT A DIFFERENT UNIT

`Estimated Average Glucose` is stored with **no unit at all** — read out of the
extraction, not inferred — while the other report gives `154 mg/dL`. The
series was blocked and the reader was told their reports disagreed about the
unit. They do not; one is silent.

**THE BEHAVIOUR WAS ALREADY INCONSISTENT.** A series where NO reading carries
a unit plots without complaint, because every key folds to the empty string
and nothing differs. **Only the MIXED case blocked.** Taking the silent
reading to be in the one unit the series does print removes an inconsistency
rather than adding an assumption. Two different printed units still block
whatever else is missing — an absence can fail to create a disagreement, never
settle one. Disclosed on the panel, because a reader must not be shown a unit
their own document does not carry without being told where it came from.

> **⚠ TWO OF MY OWN GUARDS DID NOT SURVIVE THE MUTATION ROUND.**
>
> The condition written AS the safety check — `presentKeys.length === 1` —
> changed nothing when mutated to `>= 1`, because when two printed units exist
> `units` becomes those two and the pre-existing `units.length > 1` check
> blocks regardless. **It was documentation wearing a guard's clothes.**
> Deleted, and the name now says what is true (`someReadingIsSilent`).
>
> And `unit_missing`, added ONE COMMIT EARLIER, became unreachable. Every
> shape was enumerated against the real function: all-silent is not blocked,
> one-silent-one-printed is adopted, and anything with two printed units is
> `units_differ` and truthfully so. **The branch, its reader-facing sentence
> and the two tests pinning it are deleted** — a test that pins a state the
> producer can no longer reach is a test that will be satisfied by
> reintroducing it. The term that IS load-bearing, `!blocked`, is verified
> killed by a test.

### ⚠ AND UNBLOCKING IT EXPOSED A FALSE `improving` ON A RISING BLOOD SUGAR

**The most serious thing this session found, and it was one page-read from
reaching a reader.** With the series plottable, the card was about to show:

```
HbA1c (average blood sugar)   5.9 % -> 7 %           worsening
AVERAGE BLOOD GLUCOSE         121.94 -> 154 mg/dL    improving
```

**Those are the same change.** eAG is a fixed restatement of HbA1c —
`28.7 x HbA1c - 46.7` gives 122.6 and 154.2, which is what the reports carry.
One card, one measurement, two opposite verdicts, **and the reassuring one was
the false one.**

The cause, read out of the stored extraction:

```
AVERAGE BLOOD GLUCOSE  154 mg/dL
    reference_range_raw = "151 - 180 - Average Control"   low=151 high=180
```

That is a band from an **HbA1c interpretation table**, not this patient's
reference interval, and Module 4's parser accepted it as one. Module 35's
polarity for the test is `best_within_range`, so judged against a target of
151-180 a rise INTO that range reads as an improvement — when an average
glucose of 154 is HbA1c around 7 %, which is worse control. Module 35 itself
behaves correctly: probed with no interval it returns
`CLINICAL_DIRECTION_UNKNOWN`. **The bad interval did the damage.**

**Fixed by not trending a row that restates an ASSESSED feature.** Declared in
`backend/src/services/labRestatements.js`, with the fixed relationship and how
it was checked. Only a restatement by a FIXED relationship may go in — not a
test that is merely related, which is why fasting and random glucose stay on
the page in their own right.

**EXCLUDED FROM TRENDING, NOT FROM THE PAGE.** The row keeps its readings and
dates, gains no chart, no direction and no scale, and names the feature that
carries the same measurement so a reader can go to the verdict that was
actually reviewed. 6au's lesson: a row a reader can find on their document and
not on the screen reads as missing whatever the reason. The count of rows
declined is reported rather than silent. Live: 26 panels, nothing blocked.

> **THE PARSER DEFECT UNDERNEATH IS GATED NOW** — see the next subsection —
> **but the already-stored bounds are not cleaned.** This entry removed the
> contradiction on one row; the gate stops the class recurring on new uploads.

### ▶ AND THE "PARSER" TURNED OUT NOT TO EXIST — SO THE GATE WENT AT THE BOUNDARY

**THERE IS NO INTERVAL PARSER IN MODULE 4 AND THERE NEVER WAS.**
`reference_low` and `reference_high` are emitted BY THE MODEL; `coerce_numeric`
only coerces them. So "fix the parser" meant: gate the model's answer after it
arrives, which is where every other model boundary in this codebase puts its
control. `extraction.py` now carries
`printed_range_is_only_a_range` plus a `model_validator`.

**THE RULE.** The printed text must be ONLY an interval — an optional
comparator, one or two numbers, at most a unit — and anything else refuses the
numbers while KEEPING `reference_range_raw` exactly as printed. The reader's
document is not wrong; only this service's reduction of it to two numbers was.

**VALIDATED AGAINST ALL 46 DISTINCT PRINTED RANGES IN THE STORED DATA** before
being written, pulled out of Mongo rather than imagined, plus four
labelled-band shapes that do not appear and must also be refused. **50 of 50.**

What the model already refused on its own, and the gate agrees with: both
multi-line HbA1c interpretation tables, and the sex-specific
`"F: 36 - 46 M: 40 - 50"`. It accepted exactly ONE shape — a single band row
with a label after it.

* A unit token carries **no whitespace** (`g/dL`, `pg`, `%`, `cells/cumm`,
  `mill/cu.mm`, `fL`); a category label is words.
* **A purely alphabetic remainder longer than 4 characters is prose, not a
  unit.** Without that cap `"151 - 180 Normal"` — the same defect with the
  dash omitted — passes, because one word fills the unit slot. Mutating the
  cap to 99 was **killed by four tests**.
* **`flag` IS LEFT ALONE.** It is the laboratory's own marking when the report
  states one, and this gate is about a range the service misread. A flag the
  model inferred FROM a refused range is a separate question, deliberately not
  settled here — eAG still carries `flag: "normal"` against that band.
* The extraction PROMPT now names the hazard too, with examples. That is
  belt-and-braces: the gate is the control.

### ✅ AND THE STORED ROW WAS REPAIRED, WITH THE GATE ITSELF AS THE JUDGE

The gate runs at extraction time, so it protected new uploads and left the
already-stored bounds dirty: `AVERAGE BLOOD GLUCOSE` still held
`low=151 high=180`. Repaired on the owner's instruction, in three steps, and
**the method matters more than the one row it changed**:

1. **Node collected** every stored parameter holding a bound — 91 parameters
   scanned, 46 with bounds, 42 distinct printed strings — and decided nothing.
2. **Python judged them by importing `printed_range_is_only_a_range` from the
   shipped schema**, NOT by restating its rule. A repair that re-implemented
   the regex could leave the database in a state the live code would never
   produce, and the two would drift apart silently. **41 accepted, 1 refused.**
3. **Node applied that verdict**, dry run first, with the whole before-state
   written to a JSON backup.

**What changed:** `reference_low` and `reference_high` to null, on ONE row.
**What was kept:** `reference_range_raw` exactly as printed — the reader's
document is not wrong — and the value, the unit and the flag.

**THE VERIFICATION THAT MATTERS:** re-running the audit over the whole
database afterwards refuses NOTHING. 91 parameters, 45 with bounds, 41
distinct strings, 0 refused. **The stored data now matches what the live gate
would produce**, which is a stronger statement than "the row we knew about is
fixed".

> **THE FALSE `improving` NOW HAS TWO INDEPENDENT PROTECTIONS.** eAG is
> excluded from trending by `labRestatements.js`, AND its bounds are gone — so
> even if that exclusion were removed, Module 35 returns
> `CLINICAL_DIRECTION_UNKNOWN` for a `best_within_range` polarity with no
> interval, which was verified by probing it directly.

**The mutation script was deliberately NOT added to the repository.** A
re-runnable database rewrite sitting in `src/` is a footgun; the method above
is the record, and it is reproducible from it.

### ⚠ A UNICODE ESCAPE PUT TWO REAL NUL BYTES IN A SOURCE FILE

Worth knowing because it is silent and it is not the heredoc trap the working
notes already warn about. A map key was built by joining two strings with a
U+0000 separator, written in the source as a backslash-u unicode escape, and
**the file received two actual NUL bytes** rather than the six characters of
the escape. Git immediately treated `labSeriesService.js` as BINARY and
dropped its diff entirely; `grep` reported "Binary file matches" instead of
line numbers, which is how it was noticed.

**IT THEN HAPPENED A SECOND TIME, IN THIS FILE, WHILE WRITING THIS PARAGRAPH**
— quoting the escape inside a code span put a NUL byte into MEMORY.md and
turned the handover binary. So: **do not write that escape in any file here,
not even inside backticks.** Name the code point as U+0000 in prose, as this
paragraph now does.

Replaced with nested Maps, which need no separator at all — and there is no
character safe for that job anyway, since a unit key can hold `/`, `%`, `^`
and `.`.

> **CHECK FOR NUL BYTES WHEN GIT OR GREP STARTS CALLING A SOURCE FILE BINARY.**
> `[System.IO.File]::ReadAllBytes($p)` and count zeros — and note that .NET
> resolves a RELATIVE path against the process working directory, not
> PowerShell's location, so use an absolute one or it reports `bytes: 0`.

### ⚠ "unchanged" BESIDE AN ARROW AND TWO DIFFERENT NUMBERS

```
EOSINOPHILS   5 %       ->  2 %        ↓ unchanged
ESR           35 mm/hr  ->  45 mm/hr   ↑ unchanged
```

Mapping Module 35's `stable` onto Module 29's `unchanged` produced a row
contradicting itself: the arrow says it moved, the numbers say it moved, the
word says it did not. What the category means is "it moved less than this
test's own variation" — a much weaker claim.

**The display word is now "no real change", applied to MODULE 29's ASSESSED
ROWS TOO.** One table must not use one word for the assessed half and another
for the rest. The category, the payload and `category--unchanged` are all
untouched; this is display only.

### KNOWN AND OPEN

**Raised this session and NOT resolved:**

* **NOT ONE ROW OF THE VARIATION TABLE HAS BEEN VERIFIED.** This is the single
  biggest outstanding item: 16 rows, each naming its source, none checked.
  Until then every threshold on the page is labelled as unchecked — correctly.
* **`stable` on the timeline and `no real change` on the comparison** are two
  phrasings of one verdict on one page. Both honest; not settled.
* **⚠ eAG STILL CARRIES `flag: "normal"`, AND THIS IS THE LAST PIECE OF THAT
  DEFECT.** Almost certainly inferred by the model against the band that has
  now been refused — the extraction prompt sets a flag either from a marking
  the report shows OR from an unambiguous numeric comparison, and here only
  the second was available. But **this cannot be told apart from a genuine
  printed marking by looking at the stored row**, which is why neither the
  gate nor the repair touched it. The panel therefore still shows `In range`
  for 154 mg/dL. Deciding it needs the report in front of a human.
* **eAG is shown but not trended**, which is deliberate, and the extraction
  still stores no unit for it. The unit is now taken from the reader's other
  report; the upstream fix is still that extraction should carry it.
* **The two unit equivalences are DECLARED BUT UNCHECKED.** `U/L == IU/L` and,
  for MCHC only, `g/dL == %`. Both are standard conventions and both say
  `verified: false`. `SGPT 101.9 -> 13 improving` rests entirely on the first
  one, which makes it the row to verify first — the page says it is unchecked,
  but it is now making a clinical statement it was not making before.
* **THE OCR CONFUSION IS REPAIRED AT THE COMPARISON KEY, NOT AT SOURCE.** The
  stored extraction still says `ulU/mL`, so every consumer that folds units
  itself would hit the same defect. **A Module 4/5 normalisation is still the
  right long-term home**; `unitKey` just stopped this one card lying about it.
* **`5.4 → 7 %` prints `7`, not `7.0`** — `formatValue` does not pad, so a pair
  can look like it has different precision on each end.
* Module 35's polarity for a table hit is now the table's; a row whose polarity
  word the module does not recognise falls through and is logged.

**Carried forward, unchanged:** the glucose exclusion message wrong about why
(three places); the trend chart drawing one line across non-comparable glucose
points; `referenceAgreement` computed and never shown per panel; PCV scaled
from one report's interval without saying so; `--rust` at 4.38:1;
`origin: report_transcription`; `MISSING_PROFESSIONAL_REFERRAL` not blocking;
Module 32's two-way `present`; **the ai-service suite still needing `.env`
moved aside** (fix `conftest.py`); `RangeChart.jsx` orphaned.

**Closed this session:** ~~a zero change called significant~~ · ~~ten
parameters stranded as single readings~~ · ~~a threshold that moved between
page loads~~ · ~~the summary line counting a set that no longer existed~~ ·
~~the chart contradicting its own row~~ · ~~the comparison card carrying 12 of
28 parameters~~ · ~~"unchanged" over a change~~ · ~~TSH blocked by one unit
spelled two ways~~ · ~~a missing unit reported as a different one~~ · ~~SGPT
and MCHC blocked for want of a declared equivalence~~ · ~~a silent unit
treated as a disagreement~~ · ~~one change given two opposite verdicts~~ ·
~~an interpretation-table band accepted as a reference interval~~ ·
~~the stored `151 - 180` bounds~~ (gated at extraction AND repaired in the
database; the whole stored set now re-audits clean).

### ⚠ THE RATE LIMITER WILL STOP A DEBUG SESSION BEFORE THE QUOTA DOES

History endpoints allow **60 requests per 15 minutes**
(`HISTORY_RATE_LIMIT_MAX`), and each timeline load fires three, doubled in dev.
Repeated reloads while checking a render exhausted it and the page went blank
with `429` — which looks exactly like a broken feature. **The limiter is
in-memory, so restarting the backend clears it**; that is faster than waiting
out the window. Check the console for `429` before debugging a blank card.

**Also on stale state:** a `ReferenceError: tally is not defined` in the
console was HMR holding an intermediate save, and its line numbers did not
match the file. **Compare the error's line numbers to the current file before
believing it.**

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
