from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from app.data.feature_catalog import (
    CANONICAL_FEATURES,
    LAB_FEATURES,
    PROFILE_FEATURES,
    SOURCE_LAB_REPORT,
    SOURCE_PATIENT_PROFILE,
)
from app.schemas.extraction import (
    ExtractedParameter,
    Flag,
    PageText,
    ReportMetadata,
    SourceInfo,
)

STAGE_EXTRACTION = "extraction"
STAGE_FEATURE_ENGINEERING = "feature_engineering"

STAGE_MODULE = {STAGE_EXTRACTION: 4, STAGE_FEATURE_ENGINEERING: 5}

FeatureValue = Union[StrictBool, StrictInt, StrictFloat, StrictStr]


class ExtractionInput(BaseModel):

    model_config = ConfigDict(extra="ignore")

    source: Optional[SourceInfo] = None
    pages: List[PageText] = Field(default_factory=list)
    extracted_parameters: List[ExtractedParameter] = Field(default_factory=list)
    report_metadata: Optional[ReportMetadata] = None
    extraction_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    warnings: List[str] = Field(default_factory=list)

    @field_validator("warnings", mode="before")
    @classmethod
    def _warnings_list(cls, v: object) -> object:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v


class PatientProfileContext(BaseModel):

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    age: Optional[int] = Field(default=None, ge=0, description="Whole years.")
    gender: Optional[str] = None
    bmi: Optional[float] = Field(
        default=None,
        gt=0,
        description="kg/m2, derived server-side by Module 2 from height/weight.",
    )
    height_cm: Optional[float] = Field(default=None, gt=0, alias="heightCm")
    weight_kg: Optional[float] = Field(default=None, gt=0, alias="weightKg")
    hypertension: Optional[Union[StrictBool, StrictStr]] = None
    heart_disease: Optional[Union[StrictBool, StrictStr]] = Field(
        default=None, alias="heartDisease"
    )
    smoking_history: Optional[str] = Field(default=None, alias="smokingHistory")

    @field_validator("gender", "smoking_history", mode="before")
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v


class FeatureEngineeringRequest(BaseModel):

    model_config = ConfigDict(extra="ignore")

    extraction: ExtractionInput = Field(default_factory=ExtractionInput)
    profile: Optional[PatientProfileContext] = None

    @model_validator(mode="before")
    @classmethod
    def _unwrap_module_4_envelope(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        if "extraction" in value:
            return value

        envelope = value.get("data")
        has_envelope = isinstance(envelope, dict)
        has_bare = "extracted_parameters" in value

        if has_envelope and has_bare:
            raise ValueError(
                "Ambiguous request: send the extraction under 'extraction', or "
                "relay Module 4's response envelope, but not both."
            )
        if has_envelope:
            unwrapped = dict(value)
            unwrapped["extraction"] = envelope
            return unwrapped
        if has_bare:
            return {"extraction": value, "profile": value.get("profile")}
        return value


class ConversionDetail(BaseModel):

    model_config = ConfigDict(extra="forbid")

    from_unit: str
    to_unit: str
    factor: float
    offset: float = 0.0
    formula: str
    basis: str = ""


class FeatureProvenance(BaseModel):

    model_config = ConfigDict(extra="forbid")

    source: str = Field(
        description=f"{SOURCE_LAB_REPORT} | {SOURCE_PATIENT_PROFILE} | report_details"
    )
    original_test_name: Optional[str] = Field(
        default=None, description="Test name exactly as printed, or profile field."
    )
    original_value_raw: Optional[str] = None
    original_value_numeric: Optional[float] = None
    original_unit: Optional[str] = None
    normalized_unit: Optional[str] = None
    matched_synonym: Optional[str] = Field(
        default=None, description="The synonym-table entry that matched."
    )
    parameter_index: Optional[int] = Field(
        default=None,
        ge=0,
        description="Index into the submitted extracted_parameters[] array.",
    )
    page_number: Optional[int] = Field(default=None, ge=1)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    reference_range_raw: Optional[str] = Field(
        default=None,
        description="The reference range EXACTLY as printed, never converted.",
    )
    reference_low: Optional[float] = Field(
        default=None,
        description="Lower reference bound IN THE SAME UNIT AS THE FEATURE'S "
        "`value` -- i.e. the canonical unit whenever the value is canonical. "
        "Converted with the value by the same audited transform when "
        "`reference_converted` is true. None when no bound was printed OR when "
        "the printed bound could not be carried into the value's unit; the "
        "unconvertible case is never passed through in the printed unit and "
        "is recorded in `notes`. `reference_range_raw` keeps the printed text.",
    )
    reference_high: Optional[float] = Field(
        default=None,
        description="Upper reference bound, in the same unit as `reference_low` "
        "and as the feature's `value`. Same conversion and same refusal rule.",
    )
    reference_unit: Optional[str] = Field(
        default=None,
        description="The unit `reference_low`/`reference_high` are expressed "
        "in. Equal to the feature's `unit` whenever bounds are present.",
    )
    reference_converted: bool = Field(
        default=False,
        description="True when the printed bounds were carried through the "
        "SAME conversion applied to the value (`conversion`). False when no "
        "conversion was needed, when no bounds were printed, or when the "
        "bounds were refused. A consumer must NOT re-apply `conversion` to "
        "these bounds when this is true.",
    )
    flag: Optional[Flag] = None
    unit_converted: bool = Field(
        default=False,
        description="True when the VALUE was converted to the canonical unit.",
    )
    unit_assumed: bool = Field(
        default=False,
        description="True when no unit was printed and the canonical unit was assumed.",
    )
    unit_recognised: bool = True
    conversion: Optional[ConversionDetail] = None
    censored: Optional[str] = Field(
        default=None,
        description="'left' for '<x' results, 'right' for '>x'. Value kept at "
        "the stated detection limit.",
    )
    derived: Optional[str] = Field(
        default=None, description="How a value was derived, when not read directly."
    )
    notes: List[str] = Field(default_factory=list)


class EngineeredFeature(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    name: str
    value: FeatureValue
    unit: Optional[str] = Field(
        default=None,
        description="Canonical unit, OR the original unit when it was not "
        "recognised (in which case canonical_unit is false).",
    )
    canonical_unit: bool = Field(
        default=True,
        description="False means `value` is NOT in the canonical unit. "
        "Consumers must not use `value` numerically without checking this.",
    )
    source: str
    provenance: FeatureProvenance


class UnmappedItem(BaseModel):

    model_config = ConfigDict(extra="forbid")

    test_name: str
    value_raw: Optional[str] = None
    unit: Optional[str] = None
    reason: str
    source: str = SOURCE_LAB_REPORT
    parameter_index: Optional[int] = Field(default=None, ge=0)
    page_number: Optional[int] = Field(default=None, ge=1)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    detail: Optional[str] = None


class ConversionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature: str
    original_test_name: Optional[str] = None
    original_value: float
    original_unit: str
    canonical_value: float
    canonical_unit: str
    factor: float
    offset: float = 0.0
    formula: str


class DuplicateCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_name: str
    value_raw: Optional[str] = None
    canonical_value: Optional[float] = None
    unit: Optional[str] = None
    confidence: Optional[float] = None
    page_number: Optional[int] = None
    parameter_index: Optional[int] = None
    specificity: Optional[int] = None


class DuplicateResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature: str
    policy: str
    chosen: DuplicateCandidate
    discarded: List[DuplicateCandidate] = Field(default_factory=list)


class StageWarning(BaseModel):

    model_config = ConfigDict(extra="forbid")

    stage: str = Field(
        description=f"{STAGE_EXTRACTION} (Module 4) | "
        f"{STAGE_FEATURE_ENGINEERING} (Module 5)"
    )
    module: int = Field(description="Spec module number that raised it: 4 or 5.")
    message: str


class UpstreamPage(BaseModel):

    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1)
    raw_text_available: bool


class UpstreamExtraction(BaseModel):

    model_config = ConfigDict(extra="forbid")

    stage: str = STAGE_EXTRACTION
    module: int = 4
    provided: bool = False
    source: Optional[SourceInfo] = None
    report_metadata: Optional[ReportMetadata] = None
    extraction_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    pages: List[UpstreamPage] = Field(default_factory=list)
    pages_unreadable: List[int] = Field(
        default_factory=list,
        description="Page numbers Module 4 could not read. Non-empty means the "
        "feature set is built from a PARTIALLY UNREADABLE document.",
    )
    warning_count: int = 0


class FeatureEngineeringSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature_count: int = 0
    lab_feature_count: int = 0
    profile_feature_count: int = 0
    report_details_feature_count: int = 0
    unmapped_count: int = 0
    conversion_count: int = 0
    duplicate_count: int = 0
    parameters_received: int = 0
    profile_provided: bool = False
    upstream_warning_count: int = 0
    pages_unreadable_count: int = 0


class FeatureEngineeringData(BaseModel):

    model_config = ConfigDict(extra="forbid")

    features: Dict[str, EngineeredFeature] = Field(default_factory=dict)
    unmapped: List[UnmappedItem] = Field(default_factory=list)
    conversions_applied: List[ConversionRecord] = Field(default_factory=list)
    duplicates_resolved: List[DuplicateResolution] = Field(default_factory=list)
    missing_features: List[str] = Field(
        default_factory=list,
        description="Canonical features with no value. For hypertension / "
        "heart_disease this means UNKNOWN, not false.",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings raised by MODULE 5 ITSELF. Upstream warnings are "
        "NOT merged in here -- see `upstream_warnings` / `all_warnings`.",
    )
    upstream_warnings: List[StageWarning] = Field(
        default_factory=list,
        description="Warnings received from Module 4 and carried forward "
        "unchanged. Module 5 never edits, filters or drops these.",
    )
    all_warnings: List[StageWarning] = Field(
        default_factory=list,
        description="Every warning from both stages, upstream first, each "
        "tagged with the stage that raised it. THIS is the list Module 6 and "
        "the final clinical report (spec Module 17) should consume.",
    )
    upstream: UpstreamExtraction = Field(
        default_factory=UpstreamExtraction,
        description="Module 4 context carried forward: source, report "
        "metadata, extraction confidence and per-page readability.",
    )
    summary: FeatureEngineeringSummary = Field(
        default_factory=FeatureEngineeringSummary
    )

    @field_validator("features")
    @classmethod
    def _keys_are_canonical(
        cls, v: Dict[str, EngineeredFeature]
    ) -> Dict[str, EngineeredFeature]:
        for key, feat in v.items():
            if key not in CANONICAL_FEATURES:
                raise ValueError(f"{key!r} is not a canonical feature")
            if feat.name != key:
                raise ValueError(f"feature key {key!r} != feature.name {feat.name!r}")
        return v


class FeatureEngineeringResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: bool = True
    data: FeatureEngineeringData


def catalog_document() -> Dict[str, Any]:
    from app.data.feature_catalog import FEATURES
    from app.data.unit_conversions import accepted_units

    return {
        "canonical_features": list(CANONICAL_FEATURES),
        "lab_features": list(LAB_FEATURES),
        "profile_features": list(PROFILE_FEATURES),
        "features": {
            name: {
                "canonical_unit": d.canonical_unit,
                "value_type": d.value_type,
                "source": d.source,
                "description": d.description,
                "categories": list(d.categories),
                "accepted_units": sorted(accepted_units(name)),
            }
            for name, d in FEATURES.items()
        },
    }
