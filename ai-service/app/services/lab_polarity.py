"""Module 35 -- improving / worsening / stable for tests this platform does NOT assess.

WHAT THIS IS FOR. `labSeriesService` builds trends for the parameters a report
carries that the pipeline has no canonical feature for -- CRP, ESR, MCV,
lymphocytes. Those panels could show readings and a scale but no status, while
every assessed panel beside them says improving, worsening or stable. A reader
asked why, and the answer was that all three words need something the pipeline
does not hold for an unassessed test.

This module obtains the two missing inputs from the model, and NOTHING ELSE.

==========================================================================
WHY THIS IS NOT "LETTING THE LLM CLASSIFY A TREND"
==========================================================================

The obvious version -- hand the model two values and ask whether the patient is
getting better -- would produce a clinical verdict with no rule, no threshold
and no evidence chain, rendered beside verdicts that have all three. So the
question is narrowed, exactly as Module 27b (`parameter_glossary`) narrows its
own, until what is asked is safe to ask:

  1. THE PROMPT CONTAINS NO PATIENT DATA. Not the values, not the change, not
     the reference range, not the flag, not the age or sex. It contains a test
     NAME. The answer is therefore a property of the TEST -- true for everyone
     who ever has it -- and the model is not in a position to interpret this
     person's result.

  2. THE MODEL DOES NOT CLASSIFY. It supplies a POLARITY (which direction is
     unfavourable) and two VARIATION PERCENTAGES. The classification itself is
     done by `trend_analyzer._classify` and `_is_significant` -- the SAME two
     functions Module 28 uses for assessed features, called with the same
     dataclasses. There is exactly one trend classifier in this service and
     this module does not become a second one.

  3. THE MODEL NEVER SUPPLIES A REFERENCE RANGE. That is the most damaging
     hallucination available to this feature and §6v records one already
     reaching a patient. When the answer is `best_within_range`, the interval
     used is the one the PATIENT'S OWN LABORATORY PRINTED on the report,
     passed in by the caller. The model says which SHAPE the polarity has; the
     laboratory says where the bounds are.

  4. THE ARITHMETIC IS OURS. The model gives CVa and CVi -- published,
     test-specific, widely tabulated figures -- and this service computes
          RCV = 2**0.5 * 1.96 * sqrt(CVa**2 + CVi**2)
     with `trend_polarity.reference_change_value`, the same function that
     produced every row of the hand-written STABILITY table. That table's own
     header describes its inputs as "literature-typical values recorded with
     their arithmetic so a reviewer can check them"; these are the same kind of
     value from a different source, and they are recorded the same way, in
     `basis`, so a reviewer can recompute them.

  5. EVERY NUMBER IS GATED. A CV outside `CV_PERMITTED` refuses the WHOLE
     entry rather than being clamped -- a clamped hallucination is still a
     hallucination, wearing a plausible value. An entry missing either half
     classifies nothing at all.

  6. AN ENTRY NEEDS BOTH HALVES. Polarity without a stability band would label
     a 0.1 % wobble "worsening"; a band without polarity cannot say which way
     is better. Either missing means the panel keeps the movement word it
     already had and gains no clinical one.

Because the prompt holds only a test name, the answer is identical for every
patient who ever has that test -- so it is cached by name, as the glossary is.
On a free-tier key that is not an optimisation but the precondition for the
feature existing at all.
"""

from __future__ import annotations

import json
import re
import threading
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.core.logging import get_logger, safe_meta
from app.data.trend_polarity import (
    HARM_DECREASE,
    HARM_INCREASE,
    POLARITY_MONOTONE,
    POLARITY_TOWARD_REFERENCE,
    POLARITY_UNDECLARED,
    StabilityBand,
    TrendPolarity,
    reference_change_value,
)
from app.data.lab_variation import variation_for
from app.safety.fallback import guarded_generation
from app.safety.validator import SafetyContext
from app.services.trend_analyzer import _classify, _is_significant

logger = get_logger(__name__)

LAB_POLARITY_VERSION = "1.0.0"

#: Model calls per request. Sized like Module 34's: a real panel is tens of
#: rows, a cache hit costs nothing, and the ceiling is observable in the log
#: rather than silently truncating.
MAX_PER_REQUEST = 16

#: WHAT A COEFFICIENT OF VARIATION MAY PLAUSIBLY BE, as a percentage.
#:
#: Not a clamp. A figure outside this refuses the entry, because a model that
#: returns CVa = 300 has not made a small error about a real quantity -- it has
#: produced something that is not a CV, and the honest response to that is to
#: decline rather than to substitute a number nobody measured. The bounds are
#: deliberately wide: the hand-written table's own rows run from CVa 1.5 % to
#: CVi 30 %, so anything inside this window is at least the right kind of
#: quantity.
CV_PERMITTED: Tuple[float, float] = (0.1, 50.0)

#: A description is about a TEST, not a patient, so one answer serves everyone.
_CACHE: Dict[str, "PolarityFact"] = {}
_CACHE_LOCK = threading.Lock()

_POLARITY_WORDS = {
    "higher_is_worse": (POLARITY_MONOTONE, HARM_INCREASE),
    "higher_is_better": (POLARITY_MONOTONE, HARM_DECREASE),
    "best_within_range": (POLARITY_TOWARD_REFERENCE, None),
    "unknown": (POLARITY_UNDECLARED, None),
}


class PolarityFact(BaseModel):
    """What the model said about one TEST. Never about one patient."""

    model_config = ConfigDict(extra="forbid")

    test_name: str
    kind: str = POLARITY_UNDECLARED
    direction_of_harm: Optional[str] = None
    analytical_cv_pct: Optional[float] = None
    within_subject_cv_pct: Optional[float] = None
    significant_change_pct: Optional[float] = None
    available: bool = False
    notice: Optional[str] = None
    #: WHERE THE VARIATION FIGURES CAME FROM: "table" or "model".
    #:
    #: A reader must never be told a reviewable threshold and a model-supplied
    #: one in the same words, so this travels all the way to the screen. It is
    #: the same separation `labFlag` keeps between the laboratory's verdict and
    #: this platform's.
    variation_source: Optional[str] = None
    #: True ONLY when the table row was marked verified by a human who compared
    #: it to its cited source. A model-supplied figure is never verified.
    variation_verified: bool = False
    #: The publication a reviewer should check this row against. None for a
    #: model-supplied figure, because there is nothing to check it against --
    #: which is the point.
    variation_reference: Optional[str] = None

    @property
    def usable(self) -> bool:
        """BOTH halves, or this classifies nothing. See rule 6."""
        return (
            self.available
            and self.kind != POLARITY_UNDECLARED
            and self.significant_change_pct is not None
        )


class LabSeriesInput(BaseModel):
    """One series to classify. Values are the caller's; the prompt sees none."""

    model_config = ConfigDict(extra="forbid")

    test_name: str
    first_value: float
    last_value: float
    unit: Optional[str] = None
    #: THE LABORATORY'S OWN printed interval, when it printed one. Used only
    #: for a `best_within_range` polarity, and never obtained from the model.
    reference_low: Optional[float] = None
    reference_high: Optional[float] = None


class LabSeriesVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_name: str
    outcome: str
    trend: Optional[str] = None
    reason_key: Optional[str] = None
    #: The arithmetic, recorded so a reviewer can recompute it rather than
    #: trust it -- the same discipline the hand-written table applies.
    basis: Optional[str] = None
    significant_change_pct: Optional[float] = None
    #: "table" or "model" -- see `PolarityFact`. Carried to the screen so a
    #: reviewable threshold and a model-supplied one are never described in
    #: the same words.
    variation_source: Optional[str] = None
    variation_verified: bool = False
    variation_reference: Optional[str] = None


class LabPolarityData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdicts: List[LabSeriesVerdict] = Field(default_factory=list)
    requested: int = 0
    generated: int = 0
    cached: int = 0
    withheld: int = 0
    skipped_over_limit: int = 0
    version: str = LAB_POLARITY_VERSION
    policy: str = Field(
        default=(
            "The model is asked, from the test NAME alone, which direction of "
            "change is unfavourable and what this test's analytical and "
            "within-subject variation are. No patient value, reference range "
            "or flag is sent to it. The reference change value is computed by "
            "this service from those two figures; the classification is made "
            "by the same function Module 28 uses for assessed features. A "
            "test whose polarity or variation could not be obtained is not "
            "classified at all."
        )
    )


SYSTEM_INSTRUCTION = (
    "You are a clinical laboratory reference. You are given ONLY the name of a "
    "laboratory test. You state general, published properties of that TEST -- "
    "never anything about any patient, any result, or any person's health. You "
    "never give a reference range, a diagnostic threshold or a cut-off. You "
    "answer with JSON only."
)


def _prompt(test_name: str) -> str:
    return (
        "For the laboratory test named below, state two general properties of "
        "the test itself.\n\n"
        f"Test name as printed on a report: {test_name}\n\n"
        "Reply with JSON only, in exactly this form:\n"
        '{"polarity": "...", "analytical_cv_pct": 0.0, '
        '"within_subject_cv_pct": 0.0}\n\n'
        '"polarity" must be exactly one of:\n'
        '  "higher_is_worse"    a higher result is generally the less '
        "favourable direction\n"
        '  "higher_is_better"   a lower result is generally the less '
        "favourable direction\n"
        '  "best_within_range"  both extremes are unfavourable\n'
        '  "unknown"            you do not recognise the test, or its '
        "direction of benefit is genuinely not established\n\n"
        '"analytical_cv_pct" is the typical published analytical coefficient '
        "of variation for this assay, as a percentage.\n"
        '"within_subject_cv_pct" is the typical published within-subject '
        "biological coefficient of variation, as a percentage.\n\n"
        "Rules you must follow:\n"
        "- Do NOT give a reference range, a normal range or any threshold.\n"
        "- Do NOT mention any patient, result or value.\n"
        "- Do NOT name or imply a diagnosis.\n"
        '- If you do not recognise the test, use "unknown" and set both '
        "percentages to 0.\n"
        "- Output the JSON object and nothing else."
    )


_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def _parse(text: str) -> Optional[dict]:
    """The JSON object in the answer, or None.

    A model asked for JSON returns JSON in a fence often enough that refusing
    a fenced object would refuse mostly-correct answers; anything that is not
    an object with the three expected keys is still refused.
    """
    match = _JSON_OBJECT.search(text or "")
    if match is None:
        return None
    try:
        parsed = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _cv(raw: Any) -> Optional[float]:
    """A coefficient of variation, or None. NEVER clamped -- see CV_PERMITTED."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = float(raw)
    low, high = CV_PERMITTED
    if not (low <= value <= high):
        return None
    return value


def _fact_from_table(test_name: str) -> Optional[PolarityFact]:
    """The hand-written row for this test, or None to ask the model.

    ==========================================================================
    THE TABLE IS CONSULTED FIRST, AND THAT IS THE WHOLE POINT
    ==========================================================================

    A row is reproducible, reviewable and diffable. A per-call answer is none
    of those, and the reader found out the hard way: EOSINOPHILS was refused
    on one request and called `stable` on the next, same data, because the
    model returned a different CVi. A threshold that decides whether someone
    is shown "stable" cannot move between page loads.

    A HIT COSTS NO MODEL CALL AT ALL. The row carries the polarity as well as
    the two figures, so a listed test never reaches the model -- which also
    means the daily quota stops being a factor for the tests that matter most.

    A MISS FALLS THROUGH TO THE MODEL, which is the previous behaviour exactly.
    Adding a row is how a test stops depending on it.
    """
    row = variation_for(test_name)
    if row is None:
        return None

    word = _POLARITY_WORDS.get(row.polarity)
    if word is None:
        # A row whose polarity word this module does not know is a bug in the
        # table, not a reason to invent one. Fall through rather than guess.
        logger.warning(
            "lab_variation_unknown_polarity %s",
            safe_meta(test=row.test, polarity=row.polarity),
        )
        return None
    kind, harm = word

    # THE SAME GATE THE MODEL'S FIGURES PASS THROUGH. A hand-written table is
    # not exempt from the check that a CV is the right kind of quantity -- a
    # typo in this file would otherwise reach a patient with more authority
    # than a hallucination, because it would be labelled as reviewed.
    cva = _cv(row.analytical_cv_pct)
    cvi = _cv(row.within_subject_cv_pct)
    if cva is None or cvi is None:
        logger.warning("lab_variation_cv_refused %s", safe_meta(test=row.test))
        return None

    return PolarityFact(
        test_name=test_name,
        kind=kind,
        direction_of_harm=harm,
        analytical_cv_pct=cva,
        within_subject_cv_pct=cvi,
        significant_change_pct=round(reference_change_value(cva, cvi)),
        available=True,
        variation_source="table",
        variation_verified=bool(row.verified),
        variation_reference=row.source,
    )


def _fact_for(test_name: str, client: Any) -> PolarityFact:
    # THE TABLE, BEFORE ANYTHING ELSE AND BEFORE ANY CALL.
    from_table = _fact_from_table(test_name)
    if from_table is not None:
        return from_table

    def generate(feedback: Any = None) -> str:
        prompt = _prompt(test_name)
        if feedback is not None:
            prompt += (
                "\n\nA previous attempt was rejected by a safety check. "
                "Answer again, following the rules above exactly."
            )
        return client.generate_text(prompt, system_instruction=SYSTEM_INSTRUCTION)

    result = guarded_generation(
        generate,
        context=SafetyContext(
            # Nothing is grounded. The prompt carried no figures, so every
            # number in the answer was supplied by the model -- which is why
            # `_cv` gates each one rather than trusting the validator, whose
            # numeric control is inactive for a context like this one (§6v).
            grounding_sources=(),
            permitted_numbers=(),
            require_grounding=False,
            require_referral=False,
        ),
        attempts=2,
    )

    text = getattr(result, "approved_text", None)
    if not isinstance(text, str) or not text.strip():
        return PolarityFact(
            test_name=test_name,
            notice="No direction of benefit could be established for this test.",
        )

    parsed = _parse(text)
    if parsed is None:
        logger.warning(
            "lab_polarity_unparsable %s", safe_meta(test_name_length=len(test_name))
        )
        return PolarityFact(
            test_name=test_name,
            notice="No direction of benefit could be established for this test.",
        )

    word = parsed.get("polarity")
    if not isinstance(word, str) or word.strip().lower() not in _POLARITY_WORDS:
        return PolarityFact(
            test_name=test_name,
            notice="No direction of benefit could be established for this test.",
        )
    kind, harm = _POLARITY_WORDS[word.strip().lower()]

    if kind == POLARITY_UNDECLARED:
        # A RECOGNISED REFUSAL, and it is cached like any other fact: the model
        # not knowing which way is better for a test is a property of the test
        # as far as this service is concerned, and asking again tomorrow spends
        # a call to be told the same thing.
        return PolarityFact(
            test_name=test_name,
            kind=POLARITY_UNDECLARED,
            available=True,
            notice="No direction of benefit is established for this test.",
        )

    cva = _cv(parsed.get("analytical_cv_pct"))
    cvi = _cv(parsed.get("within_subject_cv_pct"))
    if cva is None or cvi is None:
        # REFUSED, NOT CLAMPED. Without a defensible band there is no way to
        # tell a real change from laboratory noise, and calling noise
        # "worsening" is the failure this module exists to avoid.
        logger.warning(
            "lab_polarity_cv_refused %s",
            safe_meta(test_name_length=len(test_name), kind=kind),
        )
        return PolarityFact(
            test_name=test_name,
            kind=kind,
            direction_of_harm=harm,
            available=True,
            notice=(
                "No reliable measure of this test's own variation was "
                "available, so no change could be called significant."
            ),
        )

    return PolarityFact(
        test_name=test_name,
        kind=kind,
        direction_of_harm=harm,
        analytical_cv_pct=cva,
        within_subject_cv_pct=cvi,
        significant_change_pct=round(reference_change_value(cva, cvi)),
        available=True,
        # MODEL-SUPPLIED, AND NEVER VERIFIED. There is no source to check it
        # against, which is exactly what `variation_reference=None` says.
        variation_source="model",
        variation_verified=False,
    )


def _cache_key(test_name: str) -> str:
    """The WHOLE prompt, folded. Holds nothing patient-specific by construction."""
    return re.sub(r"\s+", " ", str(test_name or "")).strip().lower()


def classify_lab_series(
    series: Sequence[LabSeriesInput],
    client: Any,
    *,
    max_calls: int = MAX_PER_REQUEST,
) -> LabPolarityData:
    """Classify each series, using the cache, the safety validator and Module 28.

    `client` is a Module 23 text client. Injected, so this module has no
    transport of its own and the caller controls the model.
    """
    verdicts: List[LabSeriesVerdict] = []
    generated = cached = withheld = skipped = 0
    calls_left = max(0, int(max_calls))

    for item in series:
        key = _cache_key(item.test_name)
        if not key:
            continue

        with _CACHE_LOCK:
            fact = _CACHE.get(key)

        if fact is not None:
            cached += 1
        elif calls_left <= 0:
            skipped += 1
            continue
        else:
            calls_left -= 1
            fact = _fact_for(item.test_name, client)
            generated += 1
            # ONLY AN ANSWER IS CACHED. A refusal is a moment -- a spent quota
            # refuses everything -- and pinning one would make an outage look
            # like a fact about the test for as long as the process lives.
            if fact.available:
                with _CACHE_LOCK:
                    _CACHE.setdefault(key, fact)

        if not fact.usable:
            withheld += 1
            verdicts.append(
                LabSeriesVerdict(
                    test_name=item.test_name,
                    outcome="CLINICAL_DIRECTION_UNKNOWN",
                    reason_key="direction_unknown",
                    basis=fact.notice,
                )
            )
            continue

        verdicts.append(_verdict_for(item, fact))

    logger.info(
        "lab_polarity_context %s",
        safe_meta(
            requested=len(series),
            generated=generated,
            cached=cached,
            withheld=withheld,
            skipped_over_limit=skipped,
            ceiling=max_calls,
        ),
    )

    return LabPolarityData(
        verdicts=verdicts,
        requested=len(series),
        generated=generated,
        cached=cached,
        withheld=withheld,
        skipped_over_limit=skipped,
    )


def _verdict_for(item: LabSeriesInput, fact: PolarityFact) -> LabSeriesVerdict:
    """Module 28's own classifier, called with a polarity from the model.

    `_classify` and `_is_significant` are imported rather than reimplemented so
    that there is one trend classifier in this service. Every branch of the
    better/worse decision is therefore the branch an assessed feature takes.
    """
    polarity = TrendPolarity(
        feature=item.test_name,
        kind=fact.kind,
        basis="Polarity supplied by Module 35 from the test name alone.",
        direction_of_harm=fact.direction_of_harm,
        # THE LABORATORY'S BOUNDS, NEVER THE MODEL'S. None on either side means
        # "no harm threshold declared there", which is what `_classify` already
        # expects and what a one-sided printed interval actually is.
        optimal_low=item.reference_low,
        optimal_high=item.reference_high,
    )
    band = StabilityBand(
        feature=item.test_name,
        significant_change_pct=float(fact.significant_change_pct or 0.0),
        # NO ABSOLUTE FLOOR IS AVAILABLE and none is invented. The hand-written
        # table sets one per feature in its canonical unit; there is no
        # canonical unit here, so the percentage alone decides. `_is_significant`
        # treats a floor of 0 as "always cleared", which is the correct
        # degradation: it leaves the percentage test doing the work rather
        # than adding a threshold nobody measured.
        min_absolute_change=0.0,
        basis="RCV from model-supplied CVa/CVi; see Module 35.",
        analytical_cv_pct=fact.analytical_cv_pct,
        within_subject_cv_pct=fact.within_subject_cv_pct,
    )

    change = _Change(first_value=item.first_value, last_value=item.last_value)
    significant = _is_significant(item.first_value, item.last_value, band)

    # A TOWARD_REFERENCE polarity with NO bounds cannot be judged: `_classify`
    # would measure distance to an interval that does not exist and call every
    # move equidistant. The laboratory printed no range for this test, so the
    # shape is known and the position is not.
    if fact.kind == POLARITY_TOWARD_REFERENCE and (
        item.reference_low is None and item.reference_high is None
    ):
        return LabSeriesVerdict(
            test_name=item.test_name,
            outcome="CLINICAL_DIRECTION_UNKNOWN",
            reason_key="no_reference_interval",
            basis=(
                "Both extremes of this test are unfavourable, and the report "
                "printed no range to measure against."
            ),
            significant_change_pct=fact.significant_change_pct,
        )

    outcome, trend, reason_key = _classify(polarity, change, significant)

    # THE PROVENANCE SENTENCE, AND IT SAYS WHICH OF THREE THINGS IS TRUE.
    #
    # It used to say "PENDING INDEPENDENT VERIFICATION" on every verdict,
    # which was honest and useless: there was no table for a reviewer to go
    # to, so the sentence named a task nobody could start. Now it names the
    # source to check, or says plainly that there is none.
    arithmetic = (
        "RCV = 2**0.5 * 1.96 * sqrt(CVa^2 + CVi^2) = "
        f"sqrt(2) * 1.96 * sqrt({fact.analytical_cv_pct}^2 + "
        f"{fact.within_subject_cv_pct}^2) -> {fact.significant_change_pct} %. "
    )
    if fact.variation_source == "table" and fact.variation_verified:
        provenance = (
            "CVa/CVi are from this service's reviewed variation table, checked "
            f"against: {fact.variation_reference}"
        )
    elif fact.variation_source == "table":
        provenance = (
            "CVa/CVi are from this service's hand-written variation table and "
            "are NOT YET CHECKED against their cited source, which is: "
            f"{fact.variation_reference}"
        )
    else:
        provenance = (
            "CVa/CVi were supplied by the model from the test name alone. They "
            "are NOT from a reviewable source and there is nothing to check "
            "them against."
        )

    return LabSeriesVerdict(
        test_name=item.test_name,
        outcome=outcome,
        trend=trend,
        reason_key=reason_key,
        basis=arithmetic + provenance,
        significant_change_pct=fact.significant_change_pct,
        variation_source=fact.variation_source,
        variation_verified=fact.variation_verified,
        variation_reference=fact.variation_reference,
    )


class _Change:
    """The two fields `_classify` reads from a `TrendChange`.

    Module 28's own `TrendChange` requires report ids and dates that mean
    nothing here. Passing the two fields the classifier actually touches keeps
    this module from fabricating identifiers to satisfy a model it does not use.
    """

    __slots__ = ("first_value", "last_value", "absolute_change")

    def __init__(self, first_value: float, last_value: float) -> None:
        self.first_value = first_value
        self.last_value = last_value
        self.absolute_change = last_value - first_value


def reset_cache() -> None:
    """Test hook. Never called by the service."""
    with _CACHE_LOCK:
        _CACHE.clear()
