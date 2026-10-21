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

MAX_PER_REQUEST = 16

CV_PERMITTED: Tuple[float, float] = (0.1, 50.0)

_CACHE: Dict[str, "PolarityFact"] = {}
_CACHE_LOCK = threading.Lock()

_POLARITY_WORDS = {
    "higher_is_worse": (POLARITY_MONOTONE, HARM_INCREASE),
    "higher_is_better": (POLARITY_MONOTONE, HARM_DECREASE),
    "best_within_range": (POLARITY_TOWARD_REFERENCE, None),
    "unknown": (POLARITY_UNDECLARED, None),
}


class PolarityFact(BaseModel):

    model_config = ConfigDict(extra="forbid")

    test_name: str
    kind: str = POLARITY_UNDECLARED
    direction_of_harm: Optional[str] = None
    analytical_cv_pct: Optional[float] = None
    within_subject_cv_pct: Optional[float] = None
    significant_change_pct: Optional[float] = None
    available: bool = False
    notice: Optional[str] = None
    variation_source: Optional[str] = None
    variation_verified: bool = False
    variation_reference: Optional[str] = None

    @property
    def usable(self) -> bool:
        return (
            self.available
            and self.kind != POLARITY_UNDECLARED
            and self.significant_change_pct is not None
        )


class LabSeriesInput(BaseModel):

    model_config = ConfigDict(extra="forbid")

    test_name: str
    first_value: float
    last_value: float
    unit: Optional[str] = None
    reference_low: Optional[float] = None
    reference_high: Optional[float] = None


class LabSeriesVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_name: str
    outcome: str
    trend: Optional[str] = None
    reason_key: Optional[str] = None
    basis: Optional[str] = None
    significant_change_pct: Optional[float] = None
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
    match = _JSON_OBJECT.search(text or "")
    if match is None:
        return None
    try:
        parsed = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _cv(raw: Any) -> Optional[float]:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = float(raw)
    low, high = CV_PERMITTED
    if not (low <= value <= high):
        return None
    return value


def _fact_from_table(test_name: str) -> Optional[PolarityFact]:
    row = variation_for(test_name)
    if row is None:
        return None

    word = _POLARITY_WORDS.get(row.polarity)
    if word is None:
        logger.warning(
            "lab_variation_unknown_polarity %s",
            safe_meta(test=row.test, polarity=row.polarity),
        )
        return None
    kind, harm = word

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
        return PolarityFact(
            test_name=test_name,
            kind=POLARITY_UNDECLARED,
            available=True,
            notice="No direction of benefit is established for this test.",
        )

    cva = _cv(parsed.get("analytical_cv_pct"))
    cvi = _cv(parsed.get("within_subject_cv_pct"))
    if cva is None or cvi is None:
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
        variation_source="model",
        variation_verified=False,
    )


def _cache_key(test_name: str) -> str:
    return re.sub(r"\s+", " ", str(test_name or "")).strip().lower()


def classify_lab_series(
    series: Sequence[LabSeriesInput],
    client: Any,
    *,
    max_calls: int = MAX_PER_REQUEST,
) -> LabPolarityData:
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
    polarity = TrendPolarity(
        feature=item.test_name,
        kind=fact.kind,
        basis="Polarity supplied by Module 35 from the test name alone.",
        direction_of_harm=fact.direction_of_harm,
        optimal_low=item.reference_low,
        optimal_high=item.reference_high,
    )
    band = StabilityBand(
        feature=item.test_name,
        significant_change_pct=float(fact.significant_change_pct or 0.0),
        min_absolute_change=0.0,
        basis="RCV from model-supplied CVa/CVi; see Module 35.",
        analytical_cv_pct=fact.analytical_cv_pct,
        within_subject_cv_pct=fact.within_subject_cv_pct,
    )

    change = _Change(first_value=item.first_value, last_value=item.last_value)
    significant = _is_significant(item.first_value, item.last_value, band)

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

    __slots__ = ("first_value", "last_value", "absolute_change")

    def __init__(self, first_value: float, last_value: float) -> None:
        self.first_value = first_value
        self.last_value = last_value
        self.absolute_change = last_value - first_value


def reset_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()
