"""The Module 31 (Population Context and Percentile Analysis) contract, pydantic v2.

Module 31 answers ONE question, for one canonical feature at a time:

    among people of the same sex and a similar age in a real, published health
    survey, how common is a value like this one?

That is a DESCRIPTIVE question about a population. It is not "is this normal",
it is not "is this a risk", and it is not "what should be done". Module 8 owns
the reference range; Module 31 owns only how common a number is.

--------------------------------------------------------------------------
THE ONE STRUCTURAL GUARANTEE
--------------------------------------------------------------------------

`PopulationFeatureContext.available` is the field a consumer branches on, and
everything the comparison produced lives inside `comparison`, a nested model
that is `None` when `available` is false. There is therefore exactly ONE place
in the response where a value or a percentile can live, and when the answer is
"we cannot say", that place is absent -- not a null, not a zero, not an empty
band that a template would render as "0th percentile".

`PopulationComparison` in turn has NO `reason_code` and NO `message` field, and
`PopulationFeatureContext` carries no value fields of its own, so the two
halves cannot be filled in at the same time by accident. A model validator
closes the remaining combinations.

--------------------------------------------------------------------------
BANDS, NOT NUMBERS
--------------------------------------------------------------------------

`PercentileBand` reports the two ADJACENT PUBLISHED cut-points a value falls
between -- "between the 75th and the 90th percentile". There is no field for a
single percentile number, because none is computed: the tables publish eleven
cut-points per cohort and an interpolated percentile between them would be an
arithmetic invention wearing the same units as a measurement. See
`POLICY["percentile_reporting"]`.

The two edges are `Optional` for the two real open cases -- below the lowest
published cut-point, and at or above the highest -- and `position` says which
case it is, so a consumer never has to infer meaning from a null.

--------------------------------------------------------------------------
NO CLINICAL CLAIM, NO MODEL
--------------------------------------------------------------------------

Every string in a response comes from `app/population/policy.py` or from the
provenance recorded in the shipped table. No LLM is called, nothing is
generated, and no caller-supplied text is echoed into patient-facing copy.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.population.policy import MODULE, REASON_CODES, VERSION
from app.schemas.repository import FeatureSnapshot

POPULATION_MODULE = MODULE

#: Where a value sits relative to the published grid. Always present on a band.
POSITION_BELOW_LOWEST = "below_lowest_published_percentile"
POSITION_BETWEEN = "between_published_percentiles"
POSITION_AT_OR_ABOVE_HIGHEST = "at_or_above_highest_published_percentile"

POSITION_VALUES = (
    POSITION_BELOW_LOWEST,
    POSITION_BETWEEN,
    POSITION_AT_OR_ABOVE_HIGHEST,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Request
# --------------------------------------------------------------------------


class PopulationMeasurementInput(BaseModel):
    """One measured value to place in a population.

    `unit` is REQUIRED to be supplied by the caller as a string or left out
    entirely; leaving it out is answered with `UNIT_NOT_PROVIDED` rather than
    being treated as "the canonical unit". A value whose unit nobody stated is
    a number without a meaning, and Module 31 will not pick one for it.

    `value` is typed `Any` on purpose: a caller relaying a report row may hold
    "Not Detected" or an empty string there, and the honest answer to that is
    `VALUE_NOT_NUMERIC` from the service, not a 422 that discards the whole
    request. Numeric admission uses the catalogue's own `is_finite_number`.
    """

    model_config = ConfigDict(extra="ignore")

    feature: str = Field(
        min_length=1,
        max_length=64,
        description="A canonical VaidyaAI feature name. An unrecognised name "
        "is answered with UNKNOWN_FEATURE, not rejected -- see the service.",
    )
    value: Any = Field(
        default=None, description="The measured value. Not coerced here."
    )
    unit: Optional[str] = Field(
        default=None,
        max_length=32,
        description="The unit as printed. Normalised and converted through "
        "app/data/unit_conversions.py. Never assumed when absent.",
    )


class PopulationOptions(BaseModel):
    """Options. Every one of them narrows or pads; none of them invents."""

    model_config = ConfigDict(extra="ignore")

    include_all_canonical: bool = Field(
        default=False,
        description="Return an entry for EVERY canonical feature, including "
        "ones with no submitted value (they come back available=false with "
        "VALUE_NOT_NUMERIC or the feature's exclusion reason). Off by default "
        "so the response is not padded with refusals nobody asked for.",
    )


class PopulationContextRequest(BaseModel):
    """Place one patient's values in an age- and sex-matched population.

    The values arrive EITHER as `measurements` (an explicit list) OR as
    `snapshot` (a Module 7 `FeatureSnapshot`, the same object Module 28 takes).
    Sending both is a 422: two sources for the same feature would make the
    answer depend on which one this file happened to read first.

    `age` and `gender` may be given directly. When they are not, and a snapshot
    was supplied, they are read from the snapshot's own `age` and `gender`
    features -- Module 2 stores both and Module 7 carries them through. Nothing
    else is consulted, and neither is ever defaulted.
    """

    model_config = ConfigDict(extra="ignore")

    patient_ref: Optional[str] = Field(
        default=None,
        max_length=128,
        description="Opaque patient identifier. Never a name. Echoed back only.",
    )
    age: Optional[float] = Field(
        default=None,
        ge=0,
        le=130,
        description="Age in years. Absent means AGE_NOT_PROVIDED for every "
        "feature -- it is never inferred and never defaulted.",
    )
    gender: Optional[str] = Field(
        default=None,
        max_length=32,
        description="As Module 2 stores it: male | female | other | "
        "prefer_not_to_say. `other`, `prefer_not_to_say`, an absent value and "
        "an unrecognised value ALL yield SEX_COHORT_NOT_AVAILABLE. A stated "
        "gender is never coerced into a binary category.",
    )
    measurements: List[PopulationMeasurementInput] = Field(
        default_factory=list,
        max_length=64,
        description="One entry per feature to place; at most one entry per "
        "feature. The cap is above the canonical feature count on purpose -- a "
        "caller may also send names this service does not know, and each of "
        "those gets an UNKNOWN_FEATURE answer rather than making the whole "
        "request a 422.",
    )
    snapshot: Optional[FeatureSnapshot] = Field(
        default=None,
        description="A Module 7 FeatureSnapshot, used instead of "
        "`measurements`. Only its usable `features` are read; its "
        "`unavailable` entries have no value by construction and stay absent.",
    )
    options: PopulationOptions = Field(default_factory=PopulationOptions)

    @model_validator(mode="before")
    @classmethod
    def _unwrap(cls, value: Any) -> Any:
        """Accept `{"data": {...}}` so a relayed envelope is not an empty run."""
        if not isinstance(value, dict):
            return value
        if "measurements" in value or "snapshot" in value:
            return value
        inner = value.get("data")
        if isinstance(inner, dict) and (
            "measurements" in inner or "snapshot" in inner
        ):
            merged = dict(inner)
            for key in ("patient_ref", "age", "gender", "options"):
                if key in value and key not in merged:
                    merged[key] = value[key]
            return merged
        return value

    @model_validator(mode="after")
    def _one_value_source(self) -> "PopulationContextRequest":
        if self.measurements and self.snapshot is not None:
            raise ValueError(
                "send the values as 'measurements' OR as 'snapshot' (Module "
                "7), not both."
            )
        if not self.measurements and self.snapshot is None:
            raise ValueError(
                "no values were supplied. Send 'measurements' or a Module 7 "
                "'snapshot'; an empty request would return an empty answer "
                "that looks like a service fault."
            )
        seen = [m.feature for m in self.measurements]
        duplicates = sorted({f for f in seen if seen.count(f) > 1})
        if duplicates:
            raise ValueError(
                f"duplicate feature(s) in one request: {duplicates}. Which "
                "value to place would be ambiguous, and picking one silently "
                "would hide the disagreement."
            )
        return self


# --------------------------------------------------------------------------
# Response -- the comparison
# --------------------------------------------------------------------------


class PercentileBand(BaseModel):
    """The two adjacent PUBLISHED cut-points a value falls between.

    There is deliberately no single-percentile field. `lower_percentile` is
    `None` only when the value is below the lowest published cut-point, and
    `upper_percentile` is `None` only when it is at or above the highest;
    `position` names which of the three cases this is, so no consumer has to
    read meaning into a null.
    """

    model_config = ConfigDict(extra="forbid")

    position: str = Field(description=f"One of {POSITION_VALUES}.")
    lower_percentile: Optional[float] = Field(
        default=None,
        description="The highest published cut-point at or below the value.",
    )
    upper_percentile: Optional[float] = Field(
        default=None,
        description="The lowest published cut-point strictly above the value.",
    )
    lower_value: Optional[float] = Field(
        default=None,
        description="The published value AT `lower_percentile`, in the table's "
        "unit, so the band can be checked by eye.",
    )
    upper_value: Optional[float] = Field(
        default=None, description="The published value at `upper_percentile`."
    )
    label: str = Field(
        description="Fixed-format wording for the band. Assembled from the "
        "cut-points; no model wrote it."
    )

    @field_validator("position")
    @classmethod
    def _known_position(cls, v: str) -> str:
        if v not in POSITION_VALUES:
            raise ValueError(f"position must be one of {POSITION_VALUES}")
        return v

    @model_validator(mode="after")
    def _edges_match_position(self) -> "PercentileBand":
        if self.position == POSITION_BELOW_LOWEST and self.lower_percentile is not None:
            raise ValueError("below the lowest cut-point has no lower edge")
        if (
            self.position == POSITION_AT_OR_ABOVE_HIGHEST
            and self.upper_percentile is not None
        ):
            raise ValueError("at or above the highest cut-point has no upper edge")
        if self.position == POSITION_BETWEEN and (
            self.lower_percentile is None or self.upper_percentile is None
        ):
            raise ValueError("a band between cut-points needs both edges")
        return self


class MatchedCohort(BaseModel):
    """The published (sex, age band) cell the value was compared against.

    Echoed in full because a percentile is meaningless without the group it
    describes, and because `n_unweighted` lets a reader judge how many people
    the statement actually rests on.
    """

    model_config = ConfigDict(extra="forbid")

    cohort_id: str
    sex: str = Field(description="male | female, as the survey recorded it.")
    age_band_label: str
    age_min: int
    age_max: Optional[int] = Field(
        default=None, description="None for the open top band (age is top-coded)."
    )
    n_unweighted: int = Field(
        description="People actually measured in this cell. Not a population "
        "estimate -- a sample size."
    )
    weighted_population: float = Field(
        description="The number of people in the country this cell represents "
        "once survey weights are applied."
    )
    weighted_mean: float = Field(description="The cell's weighted mean value.")


class SubmittedValue(BaseModel):
    """What the caller sent, when a unit conversion changed the number.

    Present ONLY when the submitted unit differed from the table's unit, so a
    reader can see both sides of the conversion instead of wondering why the
    number in the response is not the number on the report.
    """

    model_config = ConfigDict(extra="forbid")

    value: float
    unit: str = Field(description="The caller's unit, normalised.")


class PopulationComparison(BaseModel):
    """Everything the comparison produced. Absent entirely when unavailable.

    HAS NO `reason_code` AND NO `message` FIELD. This object exists only when
    there is a real answer, and the refusal fields live on the parent -- so no
    single object can carry both a percentile and a reason it has none.
    """

    model_config = ConfigDict(extra="forbid")

    value: float = Field(
        description="The value that was compared, in `unit`. This is the "
        "number bracketed against the grid, so the band can be reproduced by "
        "hand from `cohort_percentile_values`."
    )
    unit: str = Field(
        description="The TABLE's unit, which is not always the feature's "
        "canonical unit (NHANES publishes vitamin D in nmol/L)."
    )
    submitted: Optional[SubmittedValue] = Field(
        default=None,
        description="The caller's value and unit, when a conversion was "
        "applied. Absent when the value was already in the table's unit.",
    )
    band: PercentileBand
    cohort: MatchedCohort
    percentile_grid: List[float] = Field(
        description="The published cut-points, index-aligned with "
        "`cohort_percentile_values`."
    )
    cohort_percentile_values: List[float] = Field(
        description="This cohort's published values at each cut-point, in "
        "`unit`. Shipped so a consumer can draw the distribution, and so the "
        "band above is checkable rather than trusted."
    )
    what_this_means: str = Field(
        description="Fixed per-feature copy from app/population/policy.py."
    )
    what_this_does_not_mean: str = Field(
        description="Fixed per-feature copy from app/population/policy.py."
    )
    table: Dict[str, Any] = Field(
        default_factory=dict,
        description="The source table's provenance: survey, cycle, file, "
        "sha256, NHANES variable and citation.",
    )
    table_notes: List[str] = Field(
        default_factory=list,
        description="The table's own recorded caveats (treatment, fasting, "
        "season, altitude), carried verbatim from the shipped JSON.",
    )


class PopulationFeatureContext(BaseModel):
    """The full answer for ONE feature. Branch on `available`.

    When `available` is false, `comparison` is absent and there is no value, no
    percentile and no band anywhere in this object; `reason_code` and `message`
    say why instead. When it is true, `reason_code` and `message` are absent --
    an answer does not also carry an excuse.
    """

    model_config = ConfigDict(extra="forbid")

    feature: str
    available: bool = Field(
        description="THE field to branch on. False means no comparison exists."
    )
    comparison: Optional[PopulationComparison] = Field(
        default=None,
        description="Present if and only if `available` is true. The only "
        "place in this object where a value or a percentile can live.",
    )
    reason_code: Optional[str] = Field(
        default=None,
        description="Present if and only if `available` is false. One of "
        "app/population/policy.py's PopulationReason codes.",
    )
    message: Optional[str] = Field(
        default=None,
        description="Present if and only if `available` is false. Reviewed "
        "copy from app/population/policy.py.",
    )

    @field_validator("reason_code")
    @classmethod
    def _known_reason(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in REASON_CODES:
            raise ValueError(f"reason_code must be one of {REASON_CODES} or null")
        return v

    @model_validator(mode="after")
    def _available_xor_reason(self) -> "PopulationFeatureContext":
        """The half of the no-value guarantee that nesting cannot express.

        Nesting already makes it impossible to carry a value alongside a
        refusal. This closes the two remaining contradictions: an `available`
        entry with nothing in it, and an unavailable entry that forgot to say
        why.
        """
        if self.available:
            if self.comparison is None:
                raise ValueError(f"{self.feature}: available=true with no comparison")
            if self.reason_code is not None or self.message is not None:
                raise ValueError(
                    f"{self.feature}: an available comparison must not also "
                    "carry a reason for having none"
                )
        else:
            if self.comparison is not None:
                raise ValueError(
                    f"{self.feature}: available=false must carry NO comparison "
                    "-- not an empty one"
                )
            if not self.reason_code or not self.message:
                raise ValueError(
                    f"{self.feature}: available=false requires both a "
                    "reason_code and a message"
                )
        return self


# --------------------------------------------------------------------------
# Response -- subject echo, summary and envelope
# --------------------------------------------------------------------------


class SubjectContext(BaseModel):
    """How the request's age and gender were read. No value is repeated here.

    `sex_cohort` is the survey stratum that was used, or `None` when none
    could be. It is derived from `gender` ONLY when Module 2's vocabulary maps
    it onto a stratum the tables actually publish; `other`,
    `prefer_not_to_say`, an absent and an unrecognised gender all leave it
    `None`, and `sex_cohort_available` says so explicitly.
    """

    model_config = ConfigDict(extra="forbid")

    age: Optional[float] = None
    age_source: Optional[str] = Field(
        default=None, description="request | snapshot. Absent when no age was found."
    )
    gender: Optional[str] = Field(
        default=None,
        description="The normalised Module 2 category, when it was recognised.",
    )
    gender_source: Optional[str] = Field(
        default=None, description="request | snapshot."
    )
    gender_recognised: bool = Field(
        default=False,
        description="Whether the supplied gender matched Module 2's "
        "vocabulary at all. Distinct from whether a cohort exists for it.",
    )
    sex_cohort: Optional[str] = Field(
        default=None, description="male | female | null. The stratum used."
    )
    sex_cohort_available: bool = Field(
        default=False,
        description="False whenever no published stratum matches. A stated "
        "gender is never coerced to make this true.",
    )


class PopulationSummary(BaseModel):
    """Counts only -- no values, no percentiles. Safe to render as a headline."""

    model_config = ConfigDict(extra="forbid")

    features_examined: int = 0
    available: int = 0
    unavailable: int = 0
    reason_codes: Dict[str, int] = Field(
        default_factory=dict, description="Count per reason code."
    )


class PopulationContextData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_ref: Optional[str] = None
    module: int = POPULATION_MODULE
    policy_version: str = VERSION
    generated_at: datetime = Field(default_factory=utcnow)
    subject: SubjectContext = Field(default_factory=SubjectContext)
    features: Dict[str, PopulationFeatureContext] = Field(default_factory=dict)
    summary: PopulationSummary = Field(default_factory=PopulationSummary)
    what_this_means: str = ""
    what_this_does_not_mean: str = ""
    limitations: List[str] = Field(default_factory=list)
    disclaimer: str = Field(
        default="",
        description="Fixed, reviewed text. Module 31 describes how common a "
        "value is; it does not assess, interpret or diagnose.",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Warnings raised by MODULE 31 ITSELF about the request as "
        "a whole (for example: no age was supplied, so nothing could match).",
    )


class PopulationContextResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: bool = True
    data: PopulationContextData


__all__ = [
    "POPULATION_MODULE",
    "POSITION_AT_OR_ABOVE_HIGHEST",
    "POSITION_BELOW_LOWEST",
    "POSITION_BETWEEN",
    "POSITION_VALUES",
    "MatchedCohort",
    "PercentileBand",
    "PopulationComparison",
    "PopulationContextData",
    "PopulationContextRequest",
    "PopulationContextResponse",
    "PopulationFeatureContext",
    "PopulationMeasurementInput",
    "PopulationOptions",
    "PopulationSummary",
    "SubjectContext",
    "SubmittedValue",
    "utcnow",
]
