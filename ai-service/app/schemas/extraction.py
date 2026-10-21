from __future__ import annotations

import re
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_COMPARATOR = (
    r"(?:<=|>=|<|>|≤|≥|up\s*to|upto|less\s+than|greater\s+than|more\s+than)"
)
_NUMBER = r"\d+(?:\.\d+)?"
_RANGE_SEP = r"(?:-|–|—|to)"
_UNIT_TOKEN = r"[A-Za-z%µμ][A-Za-z0-9/%^.µμ]*"

_ONLY_AN_INTERVAL = re.compile(
    rf"^\s*(?:{_COMPARATOR}\s*)?{_NUMBER}"
    rf"(?:\s*{_RANGE_SEP}\s*{_NUMBER})?"
    rf"(?:\s*({_UNIT_TOKEN}))?\s*$",
    re.IGNORECASE,
)

_MAX_ALPHABETIC_UNIT = 4


def printed_range_is_only_a_range(raw: object) -> bool:
    if raw is None:
        return True
    if not isinstance(raw, str) or not raw.strip():
        return True
    match = _ONLY_AN_INTERVAL.match(raw)
    if match is None:
        return False
    unit = match.group(1)
    if unit and unit.isalpha() and len(unit) > _MAX_ALPHABETIC_UNIT:
        return False
    return True


class Flag(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


_NUMERIC_RE = re.compile(r"^[<>~=]?\s*[+-]?(\d{1,3}(,\d{3})+|\d*)(\.\d+)?([eE][+-]?\d+)?$")


def coerce_numeric(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        if f != f or f in (float("inf"), float("-inf")):
            return None
        return f
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    if not _NUMERIC_RE.match(s):
        return None
    s = s.lstrip("<>~=").strip().replace(",", "")
    if not s or s in {"+", "-", "."}:
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


class ExtractedParameter(BaseModel):

    model_config = ConfigDict(extra="ignore", use_enum_values=True)

    test_name: str = Field(
        ...,
        min_length=1,
        description="Test name exactly as printed on the report. NOT normalised.",
    )
    value_raw: str = Field(
        ...,
        min_length=1,
        description="The result exactly as printed, numeric or not.",
    )
    value_numeric: Optional[float] = Field(
        default=None,
        description="Numeric form of value_raw, or null when non-numeric.",
    )
    unit: Optional[str] = Field(default=None, description="Unit as printed.")
    reference_range_raw: Optional[str] = Field(
        default=None, description="Reference range exactly as printed."
    )
    reference_low: Optional[float] = Field(default=None)
    reference_high: Optional[float] = Field(default=None)
    flag: Optional[Flag] = Field(
        default=None,
        description="low|normal|high|critical, only when stated or unambiguous.",
    )
    page_number: Optional[int] = Field(default=None, ge=1)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


    @field_validator("test_name", "value_raw", mode="before")
    @classmethod
    def _require_text(cls, v: object) -> object:
        if v is None:
            return v
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return str(v)
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator(
        "unit", "reference_range_raw", mode="before"
    )
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            if s == "" or s.lower() in {"null", "none", "n/a", "na", "-", "--"}:
                return None
            return s
        return v

    @field_validator("value_numeric", "reference_low", "reference_high", mode="before")
    @classmethod
    def _coerce_number(cls, v: object) -> Optional[float]:
        return coerce_numeric(v)

    @field_validator("flag", mode="before")
    @classmethod
    def _normalise_flag(cls, v: object) -> object:
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip().lower()
            if s in {"", "null", "none", "n/a", "na", "-"}:
                return None
            alias = {
                "l": "low",
                "lo": "low",
                "h": "high",
                "hi": "high",
                "n": "normal",
                "wnl": "normal",
                "within normal limits": "normal",
                "abnormal": None,
                "c": "critical",
                "crit": "critical",
                "panic": "critical",
            }
            if s in alias:
                return alias[s]
            if s in {"low", "normal", "high", "critical"}:
                return s
            return None
        return v

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_confidence(cls, v: object) -> Optional[float]:
        f = coerce_numeric(v)
        if f is None:
            return None
        return min(1.0, max(0.0, f))

    @field_validator("page_number", mode="before")
    @classmethod
    def _coerce_page(cls, v: object) -> object:
        f = coerce_numeric(v)
        if f is None:
            return None
        i = int(f)
        return i if i >= 1 else None

    @model_validator(mode="after")
    def _refuse_bounds_from_text_that_is_not_only_a_range(
        self,
    ) -> "ExtractedParameter":
        if printed_range_is_only_a_range(self.reference_range_raw):
            return self
        if self.reference_low is not None or self.reference_high is not None:
            object.__setattr__(self, "reference_low", None)
            object.__setattr__(self, "reference_high", None)
        if self.flag == Flag.NORMAL:
            object.__setattr__(self, "flag", None)
        return self


class SourceInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    filename: Optional[str] = None
    mime_type: Optional[str] = None
    page_count: Optional[int] = Field(default=None, ge=0)
    size_bytes: Optional[int] = Field(default=None, ge=0)


class PageText(BaseModel):
    model_config = ConfigDict(extra="ignore")

    page_number: int = Field(..., ge=1)
    raw_text: Optional[str] = None


class ReportMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    lab_name: Optional[str] = None
    report_date: Optional[str] = Field(
        default=None,
        description="Date exactly as printed. Not parsed or reformatted.",
    )
    patient_name_present: Optional[bool] = Field(
        default=None,
        description="Whether a patient name appears. The name itself is NOT "
        "extracted -- Module 4 does not lift identifiers off the report.",
    )
    patient_sex: Optional[str] = Field(
        default=None,
        description="Patient sex exactly as printed (e.g. 'Male', 'F'). Null if absent.",
    )
    patient_age: Optional[str] = Field(
        default=None,
        description="Patient age exactly as printed (e.g. '63 Years', '34Y 2M'). Null if absent.",
    )

    @field_validator("lab_name", "report_date", "patient_sex", "patient_age", mode="before")
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            if s == "" or s.lower() in {"null", "none", "n/a", "na", "-"}:
                return None
            return s
        return v


class ExtractionData(BaseModel):

    model_config = ConfigDict(extra="ignore")

    source: SourceInfo
    raw_text: str = ""
    pages: List[PageText] = Field(default_factory=list)
    extracted_parameters: List[ExtractedParameter] = Field(default_factory=list)
    report_metadata: ReportMetadata = Field(default_factory=ReportMetadata)
    extraction_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    warnings: List[str] = Field(default_factory=list)


class ExtractionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: bool = True
    data: ExtractionData


class PageExtraction(BaseModel):

    model_config = ConfigDict(extra="ignore")

    raw_text: str = ""
    parameters: List[ExtractedParameter] = Field(default_factory=list)
    lab_name: Optional[str] = None
    report_date: Optional[str] = None
    patient_name_present: Optional[bool] = None
    patient_sex: Optional[str] = None
    patient_age: Optional[str] = None
    page_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    warnings: List[str] = Field(default_factory=list)

    @field_validator("patient_sex", "patient_age", mode="before")
    @classmethod
    def _identity_blank_to_none(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            if s == "" or s.lower() in {"null", "none", "n/a", "na", "-"}:
                return None
            return s[:32]
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return str(v)
        return None

    @field_validator("raw_text", mode="before")
    @classmethod
    def _text_default(cls, v: object) -> object:
        if v is None:
            return ""
        return v

    @field_validator("warnings", mode="before")
    @classmethod
    def _warnings_default(cls, v: object) -> object:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v

    @field_validator("page_confidence", mode="before")
    @classmethod
    def _clamp(cls, v: object) -> Optional[float]:
        f = coerce_numeric(v)
        if f is None:
            return None
        return min(1.0, max(0.0, f))


def gemini_response_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "raw_text": {
                "type": "string",
                "description": "Complete verbatim text of this page.",
            },
            "parameters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "test_name": {"type": "string"},
                        "value_raw": {"type": "string"},
                        "value_numeric": {"type": "number", "nullable": True},
                        "unit": {"type": "string", "nullable": True},
                        "reference_range_raw": {"type": "string", "nullable": True},
                        "reference_low": {"type": "number", "nullable": True},
                        "reference_high": {"type": "number", "nullable": True},
                        "flag": {
                            "type": "string",
                            "nullable": True,
                            "enum": ["low", "normal", "high", "critical"],
                        },
                        "confidence": {"type": "number", "nullable": True},
                    },
                    "required": ["test_name", "value_raw"],
                },
            },
            "lab_name": {"type": "string", "nullable": True},
            "report_date": {"type": "string", "nullable": True},
            "patient_name_present": {"type": "boolean", "nullable": True},
            "patient_sex": {"type": "string", "nullable": True},
            "patient_age": {"type": "string", "nullable": True},
            "page_confidence": {"type": "number", "nullable": True},
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["raw_text", "parameters"],
    }
