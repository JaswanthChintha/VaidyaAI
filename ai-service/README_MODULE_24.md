# Module 24 — Medical Safety and Validation Layer

> To be merged into `ai-service/README.md`. Written separately because the
> RAG/KB agent owns `README.md`.

Spec §14 fixes the pipeline as

```
LLM Output  ->  Safety Validation  ->  Approved Educational Response
```

and **not**

```
LLM Output  ->  Directly shown to patient
```

This module is the middle box. Module 23 will call it in-process on every
generation and act on the verdict it returns.

---

## What was added

| File | What it is |
| --- | --- |
| `app/safety/policy.py` | Violation codes, severities, the rule table, the published policy including its **limitations** |
| `app/safety/validator.py` | `validate_text()` — the fail-closed engine, the positive controls, the modification logic |
| `app/safety/fallback.py` | `safe_fallback()` and `guarded_generation()` — what a patient sees when a generation is refused |
| `app/safety/schemas.py` | The HTTP request/response contract, pydantic v2 |
| `app/safety/__init__.py` | The small import surface Module 23 needs |
| `app/api/routes_safety.py` | `POST /api/v1/safety/validate`, `GET /api/v1/safety/policy`, `GET /api/v1/safety/rules` |
| `tests/test_safety_validator.py` | 177 framework-independent tests |
| `tests/test_safety_endpoint.py` | 20 HTTP-contract tests |

Nothing existing was modified. `pytest`: **2218 passed, 2 skipped** —
2218 − 197 = the 2021 pre-existing tests, all still passing.

### Mount line for `app/main.py`

Add the import to the existing `from app.api import (...)` block and this line
beside the other `include_router` calls:

```python
app.include_router(routes_safety.router)
```

Verified by simulation: after the mount, `test_auth.py`'s recursive walker
reports **zero** unprotected `/api/v1` routes.

---

## How Module 23 uses it

```python
from app.safety import SafetyContext, guarded_generation, validate_text

context = SafetyContext(
    grounding_sources=retrieved_chunks,   # Modules 21/22
    permitted_numbers=patient_values,     # Module 6's validated values
    require_grounding=True,
)

result = guarded_generation(lambda **kw: llm(prompt, **kw), context=context, attempts=2)
if result.approved_text is not None:
    show(result.approved_text)
else:
    show(result.fallback)                 # never an empty screen
```

Or directly, when the caller wants to drive the retry itself:

```python
verdict = validate_text(text, context)
verdict.verdict          # "approve" | "approve_with_modification" | "reject"
verdict.approved_text    # the ONLY string that may be shown; None on reject
verdict.violations       # code, rule_id, severity, reason, span, excerpt
```

`validate_text` **never raises**. Every failure is a rejection.

---

## Architecture: two kinds of check

### 1. Prohibition checks — a blocklist, honestly labelled

Patterns for the six classes spec Module 24 names: unsupported diagnosis,
medication, dosage, unsafe treatment instruction, certainty claims, and
presenting the system as a replacement for professional care. Plus clinician
first-person voice.

**A blocklist cannot be complete**, and this one does not claim to be. Every
rule carries `positive_control = False`, and `GET /api/v1/safety/rules`
publishes the blocklist / positive-control / fail-closed split so a reader can
see for themselves how much of the layer is an enumeration of things somebody
thought of.

### 2. Permission checks — positive controls

These do not ask *"does this contain something bad?"* but *"is this the kind of
statement we permit at all?"*

| Control | What it requires |
| --- | --- |
| `REQUIRED_PROFESSIONAL_REFERRAL` | The text must name a qualified healthcare professional. Missing ⇒ **append** the catalogue disclaimer. |
| `REQUIRED_HEDGING` | An interpretive claim about someone's clinical state must carry a hedge. `"this means you have kidney disease"` ⇒ reject; `"this may indicate…"` ⇒ fine. |
| `DIRECTIVE_VERB_ALLOWLIST` | `you should <verb>` — the verb must be on a short permitted list (*discuss, ask, consult, …*). Everything else is refused **without the layer knowing what the instruction was**. |
| `NUMERIC_GROUNDING` | Every number in the output must appear in the retrieved knowledge or among the patient's validated values. |

The hedging control fires only when the sentence is **about someone's clinical
state** (second person, a result/finding cue, or a condition name from
`app/data/conditions.py`). A definitional gloss is not an interpretation:
`"HbA1c means glycated haemoglobin"` is Module 25's whole job and passes
untouched, as does the service's own `"confidence=None, which means no
probability is produced"`.

---

## Fail closed

Every path that cannot complete an analysis returns **REJECT**. There is no
`return APPROVE` reachable from an error.

| Input | Code |
| --- | --- |
| non-`str` (`None`, `int`, `bytes`, `dict`, …) | `UNANALYSABLE_INPUT` |
| lone surrogate / not UTF-8 encodable | `UNANALYSABLE_INPUT` |
| C0/C1 control characters | `UNANALYSABLE_INPUT` |
| > 20 000 characters | `INPUT_TOO_LARGE` |
| empty / whitespace only | `EMPTY_OUTPUT` |
| **any internal exception** (`except BaseException`) | `VALIDATOR_ERROR` |
| grounding required but absent | `GROUNDING_REQUIRED_BUT_ABSENT` |
| redaction would gut the text | `REDACTION_NOT_POSSIBLE` |

An empty generation is a **failure**, not an approval — that distinction is the
one a naive implementation gets wrong.

---

## What "approve with modification" may change

**Exactly two actions, neither of which touches the words of a finding.**

1. **`append_safety_framing`** — appends the `NOT_A_DIAGNOSIS` text *verbatim
   from the reviewed catalogue*. Nothing existing is altered.
2. **`redact_sentence`** — removes a whole offending sentence and replaces it
   with a fixed notice. Permitted **only** for
   `REPLACES_PROFESSIONAL_CONSULTATION` and `UNPERMITTED_DIRECTIVE`, whose
   constructions are *instructions*, never findings. A statement about a value
   can never carry one of those codes, so **softening an abnormality into
   reassurance is structurally unreachable**.

Explicitly forbidden: paraphrasing, rewording, softening, editing inside a
sentence, salvaging text with a PROHIBITED violation.

Post-conditions: the modified text is **re-validated in full** (a modification
cannot launder text into approval); redaction is refused if it would remove more
than half the sentences or leave under 40 characters of original prose.

---

## Fallback

A rejection never produces an empty screen. `safe_fallback()` returns:

- `generated_explanation_available: False`
- a fixed notice saying the plain-language explanation could not be prepared,
  that **the structured findings are unaffected**, and that a professional can
  go through them;
- the catalogue recommendations `NOT_A_DIAGNOSIS`, `DISCUSS_WITH_CLINICIAN`,
  `INFORMATION_INCOMPLETE`, resolved through `recommendation()`;
- `use_structured_report: True` — the Module 17–20 report, whose safety is
  *structural* rather than inspected, is the fallback content;
- the violation **codes** only.

It never echoes, summarises or hints at the refused text.

---

## Privacy

The text under validation is never logged at any level. The log line is:

```
safety_validation {'request_id': ..., 'verdict': 'reject', 'violation_count': 3,
                   'modification_count': 0, 'codes': 'MEDICATION_DOSAGE,...', 'module': 24}
```

Offending spans travel in the **return value**, where the caller who already has
the text can audit them.

---

## What this layer can and cannot guarantee

**It can**, deterministically and with zero false positives on the system's own
output: catch the six named classes in their common phrasings; refuse an
unhedged interpretation of someone's clinical state; refuse any instruction
whose verb is not on the permitted list; refuse a number that is not in the
grounding; require the mandated referral framing; and fail closed on anything it
cannot analyse.

**It cannot**:

- **Enumerate everything an LLM might say.** The prohibition half is a
  blocklist. A drug with no recognisable class stem (`digoxin`) is not matched
  by the medication rules — `tests/test_safety_validator.py::test_the_known_gap_is_recorded_rather_than_hidden`
  asserts that gap so it is visible in the suite rather than only in prose.
- **Understand meaning.** The positive controls are lexical. They constrain the
  *register* of a statement and the *provenance* of its numbers; they cannot
  tell that a clinically true statement is inappropriate for this reader.
- **Verify facts.** A grounded, hedged, referral-carrying sentence can still be
  wrong.
- **Resist deliberate paraphrase.** *"The sugar-control number over three
  months"* avoids every drug and dosage pattern. Only the hedging and directive
  controls would catch an unsafe use of it.
- **Know whether the explanation matches the report.** That depends on Module 23
  passing real grounding.

These are published verbatim at `GET /api/v1/safety/policy` under
`policy.limitations`, so the limitation is stated by the running service rather
than implied away.

---

## Interaction with Module 22's knowledge base

Module 22 ships its own scanner (`app/data/knowledge_safety.py::scan_text`).
Running **this** layer over all 1 140 strings in `knowledge_base.DOCUMENTS`
found 43 that Module 24 would reject; five classes of those were genuine false
positives in *my* rules and are now fixed, each pinned from both sides by a
test:

| Fixed | Why it was wrong |
| --- | --- |
| `milligrams per decilitre` | A spelled-out **concentration**, not a dose — the same distinction as `126 mg/dL` vs `500 mg`. |
| `insulin` (the hormone) | "the body makes too little insulin" is unavoidable diabetes education. Administration uses still match. |
| `nothing in it replaces an assessment` | A **disclaimer**, not a replacement claim. Negation guard added, clamped to the sentence. |
| `what a result means … is a question for a professional` | Naming an interpretation is not making one. |
| `is not\na diagnosis` (hard-wrapped) | A fixed-width lookbehind cannot span a newline; character classes fix it. |

**23 of 1 140 still fail**, and I did **not** weaken the rules further to clear
them. They break down as:

- `prescribed` (10) — descriptive use, e.g. "some prescribed preparations".
- `insulin` (4), `dialysis`, `treated as context` — remaining strict-rule hits.
- `apply` / `take` / `drink` / `reduce` / `stop` (6) — clause-initial
  imperatives, several of them **topic keys** ("reduce sugar", "stop smoking")
  rather than prose.
- `means` (2), `reflects` (1) — including an internal provenance field.

**This matters for Module 23**: if the LLM quotes an affected KB sentence
verbatim, the output is rejected. Somebody has to decide between (a) Module 22
rewording those documents, or (b) Module 24 exempting the descriptive passive
(`prescribed by …`, `treated as …`). **I recommend (a)** — widening a
treatment-instruction rule to make a corpus pass is how safety rules acquire
holes, and the KB is the easier of the two to edit.

### Should the two scanners be reconciled?

**Yes — into one, and Module 24's should win**, with one qualification.

They answer different questions today: `knowledge_safety` gates *corpus intake*
(is this document fit to ground an LLM?), Module 24 gates *model output*. But
they enforce overlapping rules with independently-maintained pattern lists, and
two lists drift — the measurement above is that drift, already visible on day
one.

The suggested shape: Module 24's `RULES` + severities become the single rule
table; `knowledge_safety` keeps its **intake-specific** additions (alarm
language, `scan_administration`) as extra rules registered against the same
codes, and calls `validate_text` with a corpus-appropriate `SafetyContext`
(`require_referral=False`, no numeric grounding). That keeps one reviewed
vocabulary while preserving the stricter intake bar. I have **not** made this
change — `knowledge_safety.py` is the other agent's file.

---

**The structural defence remains the stronger one.** Catalogue text cannot be
injected because `recommendation(code)` has no text parameter. Module 23's prose
has no such guarantee and never will — this layer is an inspection with a
verdict attached, and the fallback exists because inspections fail.
