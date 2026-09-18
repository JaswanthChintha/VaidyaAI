"""The Module 4 output contract, enforced by pydantic v2.

This schema is BINDING: Module 5 (Medical Feature Engineering) consumes it.
Do not rename or retype fields without coordinating with Module 5.

Contract rules encoded here:
  * `test_name` is the name EXACTLY as printed on the report. Module 4 does
    not normalise to canonical feature names -- that is Module 5's job.
  * `value_numeric` is None for non-numeric results ("Negative", "Trace").
    `value_raw` always preserves what was printed.
  * `flag` is one of low | normal | high | critical | None, and is only set
    when the report states it or the reference range makes it unambiguous.
    No clinical inference happens here.
  * Every field is nullable except `test_name` and `value_raw`.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# --------------------------------------------------------------------------
# THE PRINTED RANGE MUST BE ONLY A RANGE
# --------------------------------------------------------------------------
#
# `reference_low` and `reference_high` are emitted BY THE MODEL. There is no
# parser here and never was: the model reads the report and returns two
# numbers, and `coerce_numeric` only coerces them. So the only place this
# service can refuse a reading of the printed text is here, after the answer
# arrives -- the same shape as every other model boundary in this codebase.
#
# WHAT WENT WRONG. One of the reader's reports prints, against average blood
# glucose:
#
#     "151 - 180 - Average Control"
#
# That is a row from an HbA1c INTERPRETATION TABLE -- a band mapped to a
# control category -- and the model returned `low=151, high=180` as though it
# were this patient's reference interval. Everything downstream then judged
# the reading against a target of 151-180, so a RISE in average glucose read
# as an improvement toward the healthy range. An average glucose of 154 mg/dL
# is an HbA1c around 7 %, which is worse control, and the timeline was one
# page-read away from telling a reader their diabetes had improved while the
# HbA1c row beside it said worsening.
#
# THE MODEL ALREADY REFUSES THE FULL TABLES. Both multi-line HbA1c
# interpretation blocks on these reports come back `null/null`, and so do the
# sex-specific ranges -- `"F: 36 - 46 M: 40 - 50"` -- which cannot be reduced
# to one pair without knowing whose report it is. It accepted exactly one
# shape: a SINGLE band row with a label after it.
#
# THE RULE. The printed text must be ONLY an interval: an optional comparator,
# one or two numbers, and at most a unit. Anything else and the numbers are
# refused -- `reference_range_raw` is kept exactly as printed, because the
# reader's own document is not wrong, and only this service's reduction of it
# to two numbers was.
#
# VALIDATED AGAINST EVERY DISTINCT PRINTED RANGE ON THE REAL REPORTS, 46 of
# them, before being written -- plus four labelled-band shapes that do not
# appear in the data and must also be refused. 50 of 50.
#
# REFUSING IS THE SAFE DIRECTION. A range this gate does not recognise loses
# its bounds and keeps its text; the parameter is still shown, still carries
# its value, and simply is not judged against an interval nobody could parse.
# That is what already happens for the sex-specific ranges.

_COMPARATOR = (
    r"(?:<=|>=|<|>|≤|≥|up\s*to|upto|less\s+than|greater\s+than|more\s+than)"
)
_NUMBER = r"\d+(?:\.\d+)?"
_RANGE_SEP = r"(?:-|–|—|to)"
#: A unit token carries NO WHITESPACE. Every unit printed beside a range on
#: the real reports is one token -- `g/dL`, `pg`, `%`, `cells/cumm`,
#: `mill/cu.mm`, `fL` -- while a category label is words.
_UNIT_TOKEN = r"[A-Za-z%µμ][A-Za-z0-9/%^.µμ]*"

_ONLY_AN_INTERVAL = re.compile(
    rf"^\s*(?:{_COMPARATOR}\s*)?{_NUMBER}"
    rf"(?:\s*{_RANGE_SEP}\s*{_NUMBER})?"
    rf"(?:\s*({_UNIT_TOKEN}))?\s*$",
    re.IGNORECASE,
)

#: A purely alphabetic trailing token longer than this is prose, not a unit.
#:
#: Every alphabetic-only unit printed beside a range on the real reports is two
#: characters (`pg`, `fL`); every longer alphabetic remainder seen or imagined
#: is a category label (`Average`, `Control`, `Normal`, `Desirable`). Without
#: this, `"151 - 180 Normal"` -- the same defect with the dash omitted -- would
#: pass, because a single word fills the unit slot.
_MAX_ALPHABETIC_UNIT = 4


def printed_range_is_only_a_range(raw: object) -> bool:
    """Is this printed text an interval and nothing else?

    True when there is nothing printed -- the gate has no evidence and no
    opinion, and a model that supplied bounds without text is not made wrong
    by this function.
    """
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


# Accepts "6.8", "-1.2", "1.5e3", "1,234.5", and leading comparators/symbols
# that labs print such as "<0.01", ">120", "~5.0".
_NUMERIC_RE = re.compile(r"^[<>~=]?\s*[+-]?(\d{1,3}(,\d{3})+|\d*)(\.\d+)?([eE][+-]?\d+)?$")


def coerce_numeric(value: object) -> Optional[float]:
    """Best-effort numeric coercion. Returns None when not cleanly numeric.

    Deliberately conservative: anything ambiguous becomes None rather than a
    guessed number, per the contract's "never invent" rule.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        # NaN / inf are not valid JSON numbers and are not real lab values.
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
    """One test row read off the report."""

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

    # --- normalisation of model output ---

    @field_validator("test_name", "value_raw", mode="before")
    @classmethod
    def _require_text(cls, v: object) -> object:
        # The model may emit a bare number for value_raw; stringify it so the
        # required-field contract holds rather than failing the whole row.
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
            # Models like to write these instead of emitting null.
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
            # Common lab shorthand -> contract vocabulary.
            alias = {
                "l": "low",
                "lo": "low",
                "h": "high",
                "hi": "high",
                "n": "normal",
                "wnl": "normal",
                "within normal limits": "normal",
                "abnormal": None,  # not specific enough to place
                "c": "critical",
                "crit": "critical",
                "panic": "critical",
            }
            if s in alias:
                return alias[s]
            if s in {"low", "normal", "high", "critical"}:
                return s
            # Unrecognised -> do not guess.
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
        """Drop `reference_low`/`high` when the printed text says more.

        See `printed_range_is_only_a_range` above for what went wrong and what
        was validated against. THE RAW TEXT IS KEPT: the reader's document is
        not wrong, only this service's reduction of it to two numbers was, and
        a consumer that wants to show what was printed still can.

        `flag` IS LEFT ALONE. It is the laboratory's own marking when the
        report states one, and this gate is about a range the service misread,
        not about the laboratory's verdict. A flag the model inferred FROM a
        refused range is a separate question and is not settled here.
        """
        if printed_range_is_only_a_range(self.reference_range_raw):
            return self
        if self.reference_low is None and self.reference_high is None:
            return self
        object.__setattr__(self, "reference_low", None)
        object.__setattr__(self, "reference_high", None)
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

    @field_validator("lab_name", "report_date", mode="before")
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        if isinstance(v, str):
            s = v.strip()
            if s == "" or s.lower() in {"null", "none", "n/a", "na", "-"}:
                return None
            return s
        return v


class ExtractionData(BaseModel):
    """The `data` object of a successful extraction response."""

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


# --------------------------------------------------------------------------
# Model-facing schema
# --------------------------------------------------------------------------
# What we ask Gemini to return for a single page. Kept separate from the
# response contract on purpose: the model is asked for a per-page payload, and
# the service assembles the final document-level contract. That keeps the
# model's job small and keeps assembly logic (page offsets, confidence
# aggregation) in Python where it is testable.


class PageExtraction(BaseModel):
    """Per-page payload as returned by the vision model."""

    model_config = ConfigDict(extra="ignore")

    raw_text: str = ""
    parameters: List[ExtractedParameter] = Field(default_factory=list)
    lab_name: Optional[str] = None
    report_date: Optional[str] = None
    patient_name_present: Optional[bool] = None
    page_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    warnings: List[str] = Field(default_factory=list)

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
    """JSON schema handed to Gemini for structured output.

    Hand-written rather than derived from `PageExtraction.model_json_schema()`
    because the Gemini schema dialect is a restricted subset of OpenAPI: it
    rejects `$defs`/`$ref`, `anyOf`-with-null nullability, and most of what
    pydantic emits. Keep this in sync with `PageExtraction`.
    """
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
            "page_confidence": {"type": "number", "nullable": True},
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["raw_text", "parameters"],
    }
