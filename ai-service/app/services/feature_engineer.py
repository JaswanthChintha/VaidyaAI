from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from app.data.feature_catalog import (
    FEATURES,
    LAB_FEATURES,
    PROFILE_FEATURES,
    SOURCE_LAB_REPORT,
    SOURCE_PATIENT_PROFILE,
    SOURCE_REPORT_DETAILS,
    UnmappedReason,
    lookup_test_name,
    normalize_gender,
    normalize_smoking_history,
    normalize_tristate_boolean,
)
from app.data.unit_conversions import conversion_for, is_known_unit, normalize_unit
from app.schemas.extraction import ExtractedParameter, coerce_numeric
from app.services.printed_identity import read_age_years, read_sex
from app.services.sex_specific_range import bounds_for_sex
from app.schemas.features import (
    ConversionDetail,
    ConversionRecord,
    DuplicateCandidate,
    DuplicateResolution,
    EngineeredFeature,
    ExtractionInput,
    FeatureEngineeringData,
    FeatureEngineeringSummary,
    FeatureProvenance,
    PatientProfileContext,
    STAGE_EXTRACTION,
    STAGE_FEATURE_ENGINEERING,
    StageWarning,
    UnmappedItem,
    UpstreamExtraction,
    UpstreamPage,
)

_LEFT_CENSORED = ("<", "≤", "<=")
_RIGHT_CENSORED = (">", "≥", ">=")

DUPLICATE_POLICY = (
    "deterministic_rank: "
    "1) higher synonym specificity (e.g. fasting glucose over post-prandial); "
    "2) recognised unit over unrecognised/assumed; "
    "3) uncensored over censored; "
    "4) higher extraction confidence (missing confidence ranks last); "
    "5) earlier page_number (missing page ranks last); "
    "6) earlier position in extracted_parameters[]. "
    "Discarded candidates are preserved in duplicates_resolved[] and unmapped[]."
)


class _Candidate:
    __slots__ = (
        "feature",
        "value",
        "unit",
        "canonical_unit",
        "provenance",
        "conversion_record",
        "specificity",
        "index",
        "test_name",
        "value_raw",
        "warnings",
    )

    def __init__(self, **kw: Any) -> None:
        for slot in self.__slots__:
            setattr(self, slot, kw.get(slot))

    def as_duplicate_candidate(self) -> DuplicateCandidate:
        prov: FeatureProvenance = self.provenance
        return DuplicateCandidate(
            test_name=self.test_name,
            value_raw=self.value_raw,
            canonical_value=self.value,
            unit=self.unit,
            confidence=prov.confidence,
            page_number=prov.page_number,
            parameter_index=self.index,
            specificity=self.specificity,
        )


def _candidate_rank(candidate: _Candidate) -> Tuple:
    prov: FeatureProvenance = candidate.provenance
    return (
        -(candidate.specificity or 0),
        0 if (prov.unit_recognised and not prov.unit_assumed) else 1,
        0 if prov.censored is None else 1,
        -(prov.confidence if prov.confidence is not None else -1.0),
        prov.page_number if prov.page_number is not None else 10**6,
        candidate.index,
    )


def _detect_censoring(value_raw: Optional[str]) -> Optional[str]:
    if not value_raw:
        return None
    text = value_raw.strip()
    if text.startswith(_LEFT_CENSORED):
        return "left"
    if text.startswith(_RIGHT_CENSORED):
        return "right"
    return None


def _resolve_numeric(param: ExtractedParameter) -> Optional[float]:
    if param.value_numeric is not None:
        return param.value_numeric
    text = (param.value_raw or "").strip()
    for comparator in ("≤", "≥", "<=", ">="):
        if text.startswith(comparator):
            text = text[len(comparator):].strip()
            break
    return coerce_numeric(text)


def _reference_bounds(
    param: ExtractedParameter,
    *,
    conversion: Optional[Any],
    value_unit: Optional[str],
    sex: Optional[str],
    notes: List[str],
    warnings: List[str],
    sex_from: str = "the profile",
) -> Tuple[Optional[float], Optional[float], bool, Optional[str]]:
    low = param.reference_low
    high = param.reference_high

    if low is None and high is None and sex:
        chosen = bounds_for_sex(param.reference_range_raw, sex)
        if chosen is not None:
            low, high = chosen
            notes.append(
                f"The report printed a reference interval for each sex "
                f"({param.reference_range_raw!r}); the {sex} interval "
                f"{low}-{high} was used, matching the sex on {sex_from}."
            )

    if low is None and high is None:
        return None, None, False, None

    if conversion is None or conversion.is_identity:
        return low, high, False, value_unit

    def refuse(detail: str) -> Tuple[None, None, bool, None]:
        notes.append(
            f"The printed reference interval could not be carried into "
            f"'{conversion.to_unit}' ({detail}); it was dropped rather than "
            f"left in '{conversion.from_unit}'."
        )
        warnings.append(
            f"'{param.test_name}' printed a reference interval in "
            f"'{conversion.from_unit}' that could not be converted to "
            f"'{conversion.to_unit}' ({detail}). The interval was omitted; the "
            f"printed text is preserved in reference_range_raw."
        )
        return None, None, False, None

    factor = conversion.factor
    offset = conversion.offset
    if not math.isfinite(factor) or factor <= 0.0:
        return refuse("the conversion factor does not preserve the ordering")
    if not math.isfinite(offset):
        return refuse("the conversion offset is not a finite number")

    new_low = None if low is None else conversion.apply(low)
    new_high = None if high is None else conversion.apply(high)
    for converted in (new_low, new_high):
        if converted is not None and not math.isfinite(converted):
            return refuse("a converted bound is not a finite number")

    notes.append(
        f"The printed reference interval was converted with the value "
        f"({conversion.formula})."
    )
    return new_low, new_high, True, conversion.to_unit


def _build_lab_candidate(
    index: int,
    param: ExtractedParameter,
    sex: Optional[str] = None,
    sex_from: str = "the profile",
) -> Tuple[Optional[_Candidate], Optional[UnmappedItem], List[str]]:
    warnings: List[str] = []

    match, reason = lookup_test_name(param.test_name)
    if match is None:
        return (
            None,
            UnmappedItem(
                test_name=param.test_name,
                value_raw=param.value_raw,
                unit=param.unit,
                reason=reason or UnmappedReason.NO_SYNONYM,
                parameter_index=index,
                page_number=param.page_number,
                confidence=param.confidence,
            ),
            warnings,
        )

    feature = match.feature
    definition = FEATURES[feature]

    raw_number = _resolve_numeric(param)
    if raw_number is None:
        return (
            None,
            UnmappedItem(
                test_name=param.test_name,
                value_raw=param.value_raw,
                unit=param.unit,
                reason=UnmappedReason.NON_NUMERIC_VALUE,
                parameter_index=index,
                page_number=param.page_number,
                confidence=param.confidence,
                detail=(
                    f"Recognised as {feature!r} but the result is not numeric; "
                    "no value was invented."
                ),
            ),
            warnings,
        )

    censored = _detect_censoring(param.value_raw)
    if censored is not None:
        warnings.append(
            f"'{param.test_name}' reported a censored result "
            f"('{param.value_raw}'); the value was kept at the stated "
            f"detection limit ({censored}-censored)."
        )

    unit_key = normalize_unit(param.unit)
    canonical_unit = definition.canonical_unit
    conversion = conversion_for(feature, unit_key) if unit_key else None

    unit_assumed = False
    unit_recognised = True
    conversion_detail: Optional[ConversionDetail] = None
    conversion_record: Optional[ConversionRecord] = None
    value = raw_number
    out_unit = canonical_unit
    out_canonical = True
    notes: List[str] = []

    if unit_key is None:
        unit_assumed = True
        notes.append(
            f"No unit printed; assumed the canonical unit '{canonical_unit}'."
        )
        warnings.append(
            f"'{param.test_name}' had no printed unit; the canonical unit "
            f"'{canonical_unit}' was assumed for feature '{feature}'."
        )
    elif conversion is None:
        unit_recognised = False
        out_unit = param.unit
        out_canonical = False
        detail = (
            "not a recognised unit for this feature"
            if is_known_unit(unit_key)
            else "unrecognised unit"
        )
        notes.append(
            f"Unit '{param.unit}' is {detail}; the value was NOT converted and "
            f"is NOT in the canonical unit '{canonical_unit}'."
        )
        warnings.append(
            f"'{param.test_name}' reported unit '{param.unit}', which is not a "
            f"recognised unit for feature '{feature}' (canonical: "
            f"'{canonical_unit}'). The value was left unconverted and flagged "
            f"canonical_unit=false."
        )
    elif not conversion.is_identity:
        value = conversion.apply(raw_number)
        conversion_detail = ConversionDetail(
            from_unit=conversion.from_unit,
            to_unit=conversion.to_unit,
            factor=conversion.factor,
            offset=conversion.offset,
            formula=conversion.formula,
            basis=conversion.basis,
        )
        conversion_record = ConversionRecord(
            feature=feature,
            original_test_name=param.test_name,
            original_value=raw_number,
            original_unit=param.unit or conversion.from_unit,
            canonical_value=value,
            canonical_unit=conversion.to_unit,
            factor=conversion.factor,
            offset=conversion.offset,
            formula=conversion.formula,
        )

    ref_low, ref_high, ref_converted, ref_unit = _reference_bounds(
        param,
        conversion=conversion,
        value_unit=out_unit,
        sex=sex,
        notes=notes,
        warnings=warnings,
        sex_from=sex_from,
    )

    provenance = FeatureProvenance(
        source=SOURCE_LAB_REPORT,
        original_test_name=param.test_name,
        original_value_raw=param.value_raw,
        original_value_numeric=param.value_numeric,
        original_unit=param.unit,
        normalized_unit=unit_key,
        matched_synonym=match.matched_term,
        parameter_index=index,
        page_number=param.page_number,
        confidence=param.confidence,
        reference_range_raw=param.reference_range_raw,
        reference_low=ref_low,
        reference_high=ref_high,
        reference_unit=ref_unit,
        reference_converted=ref_converted,
        flag=param.flag,
        unit_converted=conversion_detail is not None,
        unit_assumed=unit_assumed,
        unit_recognised=unit_recognised,
        conversion=conversion_detail,
        censored=censored,
        notes=notes,
    )

    candidate = _Candidate(
        feature=feature,
        value=float(value),
        unit=out_unit,
        canonical_unit=out_canonical,
        provenance=provenance,
        conversion_record=conversion_record,
        specificity=match.preference,
        index=index,
        test_name=param.test_name,
        value_raw=param.value_raw,
        warnings=warnings,
    )
    return candidate, None, warnings


def _profile_feature(
    name: str,
    value: Any,
    *,
    source_field: str,
    raw: Any,
    derived: Optional[str] = None,
    notes: Optional[List[str]] = None,
) -> EngineeredFeature:
    definition = FEATURES[name]
    return EngineeredFeature(
        name=name,
        value=value,
        unit=definition.canonical_unit,
        canonical_unit=True,
        source=SOURCE_PATIENT_PROFILE,
        provenance=FeatureProvenance(
            source=SOURCE_PATIENT_PROFILE,
            original_test_name=source_field,
            original_value_raw=None if raw is None else str(raw),
            original_value_numeric=(
                float(raw) if isinstance(raw, (int, float)) and not isinstance(raw, bool)
                else None
            ),
            original_unit=definition.canonical_unit,
            normalized_unit=definition.canonical_unit,
            derived=derived,
            notes=notes or [],
        ),
    )


def _printed_details(upstream: Optional[ExtractionInput]) -> Dict[str, Any]:
    meta = upstream.report_metadata if upstream is not None else None
    raw_sex = getattr(meta, "patient_sex", None)
    raw_age = getattr(meta, "patient_age", None)
    sex = read_sex(raw_sex)
    return {
        "gender": normalize_gender(sex) if sex else None,
        "gender_raw": raw_sex,
        "age": read_age_years(raw_age),
        "age_raw": raw_age,
    }


def _merge_report_details(
    printed: Dict[str, Any],
    profile: Optional[PatientProfileContext],
    features: Dict[str, EngineeredFeature],
    warnings: List[str],
) -> set:
    claimed = set()
    profile_values = {
        "gender": normalize_gender(profile.gender) if profile and profile.gender is not None else None,
        "age": int(profile.age) if profile and profile.age is not None else None,
    }
    labels = {"gender": "sex", "age": "age"}
    for name in ("gender", "age"):
        value = printed.get(name)
        if value is None:
            continue
        raw = printed.get(f"{name}_raw")
        from_profile = profile_values[name]
        notes = [f"Printed on the report as {raw!r}; used in place of the profile."]
        if from_profile is not None and from_profile != value:
            notes.append(f"The profile gives {from_profile}.")
            warnings.append(
                f"The report prints the patient's {labels[name]} as {raw!r}; the "
                f"profile gives {from_profile}. The report's value was used for "
                f"this analysis."
            )
        definition = FEATURES[name]
        features[name] = EngineeredFeature(
            name=name,
            value=value,
            unit=definition.canonical_unit,
            canonical_unit=True,
            source=SOURCE_REPORT_DETAILS,
            provenance=FeatureProvenance(
                source=SOURCE_REPORT_DETAILS,
                original_test_name=name,
                original_value_raw=None if raw is None else str(raw),
                original_value_numeric=float(value) if name == "age" else None,
                original_unit=definition.canonical_unit,
                normalized_unit=definition.canonical_unit,
                notes=notes,
            ),
        )
        claimed.add(name)
    return claimed


def _merge_profile(
    profile: PatientProfileContext,
    features: Dict[str, EngineeredFeature],
    unmapped: List[UnmappedItem],
    warnings: List[str],
    skip: Iterable[str] = (),
) -> None:
    skip = set(skip)

    def claim(name: str, feature: EngineeredFeature) -> None:
        if name in skip:
            return
        existing = features.get(name)
        if existing is not None:
            warnings.append(
                f"Feature '{name}' was already set from the "
                f"{existing.source}; the patient-profile value was not applied."
            )
            unmapped.append(
                UnmappedItem(
                    test_name=name,
                    value_raw=str(feature.value),
                    reason=UnmappedReason.DUPLICATE_DISCARDED,
                    source=SOURCE_PATIENT_PROFILE,
                    detail="A lab-report value for this feature already exists.",
                )
            )
            return
        features[name] = feature

    if profile.age is not None:
        claim(
            "age",
            _profile_feature("age", int(profile.age), source_field="age", raw=profile.age),
        )

    if profile.bmi is not None:
        claim(
            "bmi",
            _profile_feature("bmi", float(profile.bmi), source_field="bmi", raw=profile.bmi),
        )
    elif profile.height_cm is not None and profile.weight_kg is not None:
        metres = float(profile.height_cm) / 100.0
        derived_bmi = round(float(profile.weight_kg) / (metres * metres), 2)
        warnings.append(
            "bmi was not supplied; it was derived from heightCm/weightKg "
            "(kg / m^2). Module 2 is the authoritative source for bmi."
        )
        claim(
            "bmi",
            _profile_feature(
                "bmi",
                derived_bmi,
                source_field="heightCm+weightKg",
                raw=None,
                derived="bmi = weightKg / (heightCm/100)^2",
                notes=[
                    f"Derived from heightCm={profile.height_cm}, "
                    f"weightKg={profile.weight_kg}."
                ],
            ),
        )

    for name, raw_value, field_name in (
        ("hypertension", profile.hypertension, "hypertension"),
        ("heart_disease", profile.heart_disease, "heartDisease"),
    ):
        parsed, recognised = normalize_tristate_boolean(raw_value)
        if not recognised:
            warnings.append(
                f"Profile field '{field_name}' had an unrecognised value; it "
                f"was treated as UNKNOWN (not false) and no feature was set."
            )
            unmapped.append(
                UnmappedItem(
                    test_name=field_name,
                    value_raw=str(raw_value),
                    reason=UnmappedReason.UNRECOGNISED_CATEGORY,
                    source=SOURCE_PATIENT_PROFILE,
                    detail="Expected true, false, or absent (unknown).",
                )
            )
            continue
        if parsed is None:
            continue
        claim(
            name,
            _profile_feature(name, bool(parsed), source_field=field_name, raw=raw_value),
        )

    if profile.smoking_history is not None:
        category = normalize_smoking_history(profile.smoking_history)
        if category is None:
            warnings.append(
                "Profile field 'smokingHistory' had an unrecognised value; no "
                "smoking_history feature was set (it was NOT defaulted)."
            )
            unmapped.append(
                UnmappedItem(
                    test_name="smokingHistory",
                    value_raw=str(profile.smoking_history),
                    reason=UnmappedReason.UNRECOGNISED_CATEGORY,
                    source=SOURCE_PATIENT_PROFILE,
                    detail="Expected one of: "
                    + ", ".join(FEATURES["smoking_history"].categories),
                )
            )
        else:
            claim(
                "smoking_history",
                _profile_feature(
                    "smoking_history",
                    category,
                    source_field="smokingHistory",
                    raw=profile.smoking_history,
                ),
            )

    if profile.gender is not None:
        category = normalize_gender(profile.gender)
        if category is None:
            warnings.append(
                "Profile field 'gender' had an unrecognised value; no gender "
                "feature was set."
            )
            unmapped.append(
                UnmappedItem(
                    test_name="gender",
                    value_raw=str(profile.gender),
                    reason=UnmappedReason.UNRECOGNISED_CATEGORY,
                    source=SOURCE_PATIENT_PROFILE,
                    detail="Expected one of: "
                    + ", ".join(FEATURES["gender"].categories),
                )
            )
        else:
            claim(
                "gender",
                _profile_feature(
                    "gender", category, source_field="gender", raw=profile.gender
                ),
            )


def _coerce_parameters(
    parameters: Iterable[Any],
) -> List[ExtractedParameter]:
    out: List[ExtractedParameter] = []
    for item in parameters:
        if isinstance(item, ExtractedParameter):
            out.append(item)
        else:
            out.append(ExtractedParameter.model_validate(item))
    return out


def _build_upstream(extraction: Optional[ExtractionInput]) -> UpstreamExtraction:
    if extraction is None:
        return UpstreamExtraction(provided=False)

    pages = [
        UpstreamPage(
            page_number=page.page_number,
            raw_text_available=page.raw_text is not None,
        )
        for page in extraction.pages
    ]
    return UpstreamExtraction(
        provided=True,
        source=extraction.source,
        report_metadata=extraction.report_metadata,
        extraction_confidence=extraction.extraction_confidence,
        pages=pages,
        pages_unreadable=[p.page_number for p in pages if not p.raw_text_available],
        warning_count=len(extraction.warnings),
    )


def engineer_features(
    extracted_parameters: Optional[Sequence[Any]] = None,
    profile: Optional[Any] = None,
    extraction: Optional[Any] = None,
) -> FeatureEngineeringData:
    upstream_input: Optional[ExtractionInput] = None
    if extraction is not None:
        upstream_input = (
            extraction
            if isinstance(extraction, ExtractionInput)
            else ExtractionInput.model_validate(
                extraction if isinstance(extraction, dict) else extraction.model_dump()
            )
        )
        if extracted_parameters is None:
            extracted_parameters = upstream_input.extracted_parameters

    params = _coerce_parameters(extracted_parameters or [])

    profile_ctx: Optional[PatientProfileContext] = None
    if profile is not None:
        profile_ctx = (
            profile
            if isinstance(profile, PatientProfileContext)
            else PatientProfileContext.model_validate(profile)
        )

    warnings: List[str] = []
    unmapped: List[UnmappedItem] = []
    by_feature: Dict[str, List[_Candidate]] = {}

    printed = _printed_details(upstream_input)
    if printed["gender"] is not None:
        sex, sex_from = printed["gender"], "the report"
    else:
        sex = (
            normalize_gender(profile_ctx.gender)
            if profile_ctx is not None and profile_ctx.gender is not None
            else None
        )
        sex_from = "the profile"

    for index, param in enumerate(params):
        candidate, unmapped_item, row_warnings = _build_lab_candidate(
            index, param, sex, sex_from
        )
        warnings.extend(row_warnings)
        if unmapped_item is not None:
            unmapped.append(unmapped_item)
        if candidate is not None:
            by_feature.setdefault(candidate.feature, []).append(candidate)

    features: Dict[str, EngineeredFeature] = {}
    conversions: List[ConversionRecord] = []
    duplicates: List[DuplicateResolution] = []

    for feature in LAB_FEATURES:
        candidates = by_feature.get(feature)
        if not candidates:
            continue
        ordered = sorted(candidates, key=_candidate_rank)
        winner = ordered[0]
        losers = ordered[1:]

        features[feature] = EngineeredFeature(
            name=feature,
            value=winner.value,
            unit=winner.unit,
            canonical_unit=winner.canonical_unit,
            source=SOURCE_LAB_REPORT,
            provenance=winner.provenance,
        )
        if winner.conversion_record is not None:
            conversions.append(winner.conversion_record)

        if losers:
            duplicates.append(
                DuplicateResolution(
                    feature=feature,
                    policy=DUPLICATE_POLICY,
                    chosen=winner.as_duplicate_candidate(),
                    discarded=[c.as_duplicate_candidate() for c in losers],
                )
            )
            warnings.append(
                f"{len(candidates)} report rows mapped to feature "
                f"'{feature}'; '{winner.test_name}' was kept and "
                + ", ".join(f"'{c.test_name}'" for c in losers)
                + " discarded (see duplicates_resolved)."
            )
            for loser in losers:
                unmapped.append(
                    UnmappedItem(
                        test_name=loser.test_name,
                        value_raw=loser.value_raw,
                        unit=loser.provenance.original_unit,
                        reason=UnmappedReason.DUPLICATE_DISCARDED,
                        parameter_index=loser.index,
                        page_number=loser.provenance.page_number,
                        confidence=loser.provenance.confidence,
                        detail=f"Another row was selected for feature '{feature}'.",
                    )
                )

    from_report = _merge_report_details(printed, profile_ctx, features, warnings)
    if profile_ctx is not None:
        _merge_profile(profile_ctx, features, unmapped, warnings, skip=from_report)

    missing = [name for name in FEATURES if name not in features]

    unmapped.sort(key=lambda u: (u.parameter_index is None, u.parameter_index or 0))

    upstream = _build_upstream(upstream_input)
    upstream_warnings = [
        StageWarning(stage=STAGE_EXTRACTION, module=4, message=message)
        for message in (upstream_input.warnings if upstream_input else [])
    ]
    all_warnings = upstream_warnings + [
        StageWarning(stage=STAGE_FEATURE_ENGINEERING, module=5, message=message)
        for message in warnings
    ]

    summary = FeatureEngineeringSummary(
        feature_count=len(features),
        lab_feature_count=sum(
            1 for f in features.values() if f.source == SOURCE_LAB_REPORT
        ),
        profile_feature_count=sum(
            1 for f in features.values() if f.source == SOURCE_PATIENT_PROFILE
        ),
        report_details_feature_count=sum(
            1 for f in features.values() if f.source == SOURCE_REPORT_DETAILS
        ),
        unmapped_count=len(unmapped),
        conversion_count=len(conversions),
        duplicate_count=len(duplicates),
        parameters_received=len(params),
        profile_provided=profile_ctx is not None,
        upstream_warning_count=len(upstream_warnings),
        pages_unreadable_count=len(upstream.pages_unreadable),
    )

    return FeatureEngineeringData(
        features=features,
        unmapped=unmapped,
        conversions_applied=conversions,
        duplicates_resolved=duplicates,
        missing_features=missing,
        warnings=warnings,
        upstream_warnings=upstream_warnings,
        all_warnings=all_warnings,
        upstream=upstream,
        summary=summary,
    )


def engineer_from_extraction(
    extraction: Any, profile: Optional[Any] = None
) -> FeatureEngineeringData:
    if isinstance(extraction, ExtractionInput):
        payload = extraction
    else:
        payload = ExtractionInput.model_validate(
            extraction if isinstance(extraction, dict) else extraction.model_dump()
        )
    return engineer_features(
        payload.extracted_parameters, profile, extraction=payload
    )


__all__ = [
    "DUPLICATE_POLICY",
    "engineer_features",
    "engineer_from_extraction",
    "LAB_FEATURES",
    "PROFILE_FEATURES",
]
