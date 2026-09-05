"""Module 31's population distribution tables: load, VALIDATE, and look up.

WHAT THIS FILE IS
-----------------
`datasets/population/distributions/*.json` holds survey-weighted percentile
tables computed from public NHANES microdata by
`datasets/population/build_population_tables.py`. Those JSON files are the only
source of every number Module 31 will ever report. This file reads them once,
at import, checks them against everything that can be checked without the raw
microdata, and freezes them into read-only objects.

WHY THE CHECKS RUN AT IMPORT AND RAISE
--------------------------------------
Every failure mode below is one that produces a WRONG NUMBER rather than an
error: a grid that has drifted out of step with a cohort's values silently
shifts every reported band; a unit typo silently compares a value against a
distribution of something else. A table this file cannot vouch for must not be
served, so a bad table stops the process from starting rather than degrading
the answer. `app/core/auth.py` fails closed at import for the same reason.

The checks raise `PopulationTableError` rather than using `assert`, because
`python -O` removes assertions and these guarantees must survive it.

THE CATALOGUE COMPLETENESS CHECK
--------------------------------
`policy.py` promises that every canonical feature is either backed by a table
here or listed in `EXCLUDED_FEATURES` with a reason. `_check_catalogue_cover()`
enforces exactly that. Adding a feature to `app/data/feature_catalog.py`
without deciding what Module 31 does about it therefore fails at import,
instead of the feature quietly never appearing in a population response --
which is indistinguishable, from the outside, from having been forgotten.

NO FALLBACKS LIVE HERE
----------------------
`cohort_for()` returns the (sex, age band) cell or `None`. There is no
"nearest band", no all-adults cell, and no interpolation between cells. The
absence of a cell is an answer, and `app/services/population_context.py` turns
it into a reason code.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from app.data.feature_catalog import CANONICAL_FEATURES, FEATURES
from app.data.unit_conversions import conversion_for, is_known_unit, normalize_unit
from app.population.policy import (
    EXCLUDED_FEATURES,
    REASON_CODES,
    REASON_MESSAGES,
    PopulationReason,
)

#: `ai-service/datasets/population/distributions`. Resolved from this file so
#: the service works from any working directory.
DISTRIBUTIONS_DIR: Path = (
    Path(__file__).resolve().parents[2] / "datasets" / "population" / "distributions"
)

#: The only table schema this loader understands. A future rebuild that
#: changes the JSON shape must bump this and update the loader together.
SUPPORTED_SCHEMA_VERSION = 1

#: The two sexes the published tables stratify on. NOT a statement about
#: gender: see `POLICY["matching"]["gender_handling"]`.
TABLE_SEXES: Tuple[str, ...] = ("male", "female")


class PopulationTableError(RuntimeError):
    """A shipped table is missing, malformed, or not self-consistent."""


# --------------------------------------------------------------------------
# Frozen views over one table
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Cohort:
    """One published (sex, age band) cell.

    `percentile_values[i]` is the value at `percentile_grid[i]` of the parent
    table -- the two are index-aligned, and `_check_table()` refuses a table
    where they are not. Every value is a real observation from a real NHANES
    participant (the build script uses the lower/"type 1" weighted quantile,
    which never averages two observations together).
    """

    cohort_id: str
    sex: str
    age_min: int
    #: `None` for the open-ended top band. NHANES top-codes age at 80, so the
    #: last band genuinely has no upper edge in the source data.
    age_max: Optional[int]
    age_band_label: str
    n_unweighted: int
    weighted_population: float
    percentile_values: Tuple[float, ...]
    weighted_mean: float

    def covers(self, age: float) -> bool:
        """Inclusive on both edges; the top band is open above.

        AGE IS COMPARED AS COMPLETED YEARS, which is how the bands were built
        and how the survey records it. NHANES publishes `RIDAGEYR`, an integer
        count of completed years, and the cells were cut on that -- so "20-29"
        means "everyone whose completed age is 20 through 29", i.e. the real
        interval [20, 30).

        Comparing a fractional age directly against the printed edges made the
        bands contiguous over the INTEGERS but not over the reals, so a
        29.5-year-old fell through the crack between "20-29" and "30-39" and
        was refused with `AGE_OUTSIDE_TABLE_RANGE` -- whose message says the
        age "falls outside every group the survey published". That was a false
        statement about a person the survey plainly covers, and the refusal
        was wrong as well as wrongly explained.

        Truncating is the demographic convention (a person aged 29.5 is 29,
        not 30) and it is the same operation the survey itself performed, so
        this introduces no assumption the tables do not already embody. It
        cannot let a child into an adult band: floor(19.99) is 19, still below
        20.
        """
        completed_years = math.floor(age)
        if completed_years < self.age_min:
            return False
        return self.age_max is None or completed_years <= self.age_max


@dataclass(frozen=True)
class DroppedCohort:
    """A (sex, age band) cell the build REFUSED to publish, and its size.

    A cell with fewer than the build's `min_cell_unweighted_n` observations is
    dropped rather than published, because a percentile estimated from a
    handful of people is worse than no percentile. It is recorded here (rather
    than merely absent) so the service can say `COHORT_TOO_SMALL_TO_PUBLISH`
    instead of the vaguer `AGE_OUTSIDE_TABLE_RANGE`.
    """

    sex: str
    age_band: str
    age_min: int
    age_max: Optional[int]
    n_unweighted: int

    def covers(self, age: float) -> bool:
        # Completed years, for the same reason as `Cohort.covers` -- and the
        # two must agree, or a fractional age could fall outside every
        # published cell AND outside every dropped one, and be refused with
        # the wrong code.
        completed_years = math.floor(age)
        if completed_years < self.age_min:
            return False
        return self.age_max is None or completed_years <= self.age_max


#: The build script writes dropped bands as "20-29" or "80+". Parsed with a
#: strict pattern so a future format change raises here rather than silently
#: making every dropped band uncoverable -- which would downgrade an honest
#: COHORT_TOO_SMALL_TO_PUBLISH into AGE_OUTSIDE_TABLE_RANGE.
_AGE_BAND_RE = re.compile(r"^(\d{1,3})(?:-(\d{1,3})|\+)$")


@dataclass(frozen=True)
class PopulationTable:
    """One canonical feature's published distribution, whole and read-only."""

    feature: str
    table_id: str
    #: The unit the TABLE's numbers are in. NOT necessarily the feature's
    #: canonical unit -- NHANES publishes 25-hydroxyvitamin D in nmol/L while
    #: VaidyaAI's canonical unit is ng/mL. The service converts the patient's
    #: value into this unit; the table is never rescaled.
    unit: str
    measurand: str
    derivation: str
    built_on: str
    percentile_grid: Tuple[float, ...]
    source: Dict[str, object]
    population: Dict[str, object]
    method: Dict[str, object]
    counts: Dict[str, object]
    notes: Tuple[str, ...]
    cohorts: Tuple[Cohort, ...]
    dropped_cohorts: Tuple[DroppedCohort, ...]

    @property
    def min_age(self) -> int:
        """The youngest age any published cell covers."""
        return min(c.age_min for c in self.cohorts)

    @property
    def max_age(self) -> Optional[int]:
        """The oldest age covered, or `None` when the top band is open."""
        if any(c.age_max is None for c in self.cohorts):
            return None
        return max(c.age_max for c in self.cohorts)  # type: ignore[type-var]

    @property
    def age_band_labels(self) -> Tuple[str, ...]:
        seen: List[str] = []
        for cohort in self.cohorts:
            if cohort.age_band_label not in seen:
                seen.append(cohort.age_band_label)
        return tuple(seen)

    def cohort_for(self, sex: str, age: float) -> Optional[Cohort]:
        """The one published cell for this (sex, age), or `None`.

        No nearest-band fallback and no unmatched cell: `None` means the
        service must report why, not reach for a different population.
        `_check_table()` guarantees the bands within one sex do not overlap,
        so at most one cell can match.
        """
        for cohort in self.cohorts:
            if cohort.sex == sex and cohort.covers(age):
                return cohort
        return None

    def dropped_for(self, sex: str, age: float) -> Optional[DroppedCohort]:
        """The dropped cell covering this (sex, age), if the build dropped one."""
        for dropped in self.dropped_cohorts:
            if dropped.sex == sex and dropped.covers(age):
                return dropped
        return None

    def reference(self) -> Dict[str, object]:
        """Provenance, flat enough to put in a response. No patient data."""
        source = self.source
        return {
            "table_id": self.table_id,
            "feature": self.feature,
            "unit": self.unit,
            "measurand": self.measurand,
            "derivation": self.derivation,
            "built_on": self.built_on,
            "survey": source.get("name"),
            "publisher": source.get("publisher"),
            "cycle": source.get("cycle_label") or source.get("cycle"),
            "data_file": source.get("data_file"),
            "data_file_url": source.get("data_file_url"),
            "data_file_sha256": source.get("data_file_sha256"),
            "variable": source.get("variable"),
            "variable_label": source.get("variable_label"),
            "analytic_weight": source.get("analytic_weight"),
            "citation": source.get("citation"),
            "population": self.population.get("description"),
            "estimator": self.method.get("estimator"),
            "notes": list(self.notes),
        }

    def inventory(self) -> Dict[str, object]:
        """What this table covers, for the policy endpoint. No patient data."""
        return {
            "feature": self.feature,
            "table_id": self.table_id,
            "unit": self.unit,
            "canonical_unit": FEATURES[self.feature].canonical_unit,
            "measurand": self.measurand,
            "derivation": self.derivation,
            "built_on": self.built_on,
            "percentile_grid": list(self.percentile_grid),
            "cohort_count": len(self.cohorts),
            "age_band_labels": list(self.age_band_labels),
            "sexes": list(TABLE_SEXES),
            "min_age": self.min_age,
            "max_age": self.max_age,
            "analytic_sample": self.counts.get("analytic_sample"),
            "cohort_sample_sizes": {
                c.cohort_id: c.n_unweighted for c in self.cohorts
            },
            "dropped_cohorts": [
                {
                    "sex": d.sex,
                    "age_band": d.age_band,
                    "n_unweighted": d.n_unweighted,
                }
                for d in self.dropped_cohorts
            ],
            "source": self.reference(),
            "method": dict(self.method),
            "counts": dict(self.counts),
            "population": dict(self.population),
        }


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PopulationTableError(message)


def _parse_age_band(label: str) -> Tuple[int, Optional[int]]:
    match = _AGE_BAND_RE.match(label.strip())
    _require(
        match is not None,
        f"dropped-cohort age band {label!r} does not match the build script's "
        "'20-29' / '80+' format. Parsing it is not guessed at.",
    )
    assert match is not None  # narrowed by _require; kept for type checkers
    low = int(match.group(1))
    high = match.group(2)
    return low, (int(high) if high is not None else None)


def _load_cohort(feature: str, raw: Dict[str, object], grid_size: int) -> Cohort:
    values = raw.get("percentile_values")
    _require(
        isinstance(values, list) and len(values) == grid_size,
        f"{feature}: cohort {raw.get('cohort_id')!r} has "
        f"{len(values) if isinstance(values, list) else 'no'} percentile values "
        f"but the grid has {grid_size} cut-points. An index-misaligned table "
        "would report a wrong band for every value.",
    )
    numeric = tuple(float(v) for v in values)  # type: ignore[union-attr]
    _require(
        all(b >= a for a, b in zip(numeric, numeric[1:])),
        f"{feature}: cohort {raw.get('cohort_id')!r} percentile values are not "
        "monotone non-decreasing. A quantile function cannot decrease, so the "
        "table is wrong.",
    )
    age_max = raw.get("age_max")
    return Cohort(
        cohort_id=str(raw["cohort_id"]),
        sex=str(raw["sex"]),
        age_min=int(raw["age_min"]),  # type: ignore[arg-type]
        age_max=None if age_max is None else int(age_max),  # type: ignore[arg-type]
        age_band_label=str(raw["age_band_label"]),
        n_unweighted=int(raw["n_unweighted"]),  # type: ignore[arg-type]
        weighted_population=float(raw["weighted_population"]),  # type: ignore[arg-type]
        percentile_values=numeric,
        weighted_mean=float(raw["weighted_mean"]),  # type: ignore[arg-type]
    )


def _check_bands_disjoint(feature: str, cells: Sequence[Cohort]) -> None:
    """Within one sex, no age may fall in two bands, and none may be inverted.

    Overlapping bands would make `cohort_for()` depend on the order the JSON
    happens to list them in -- i.e. two runs could compare the same patient
    against two different populations.
    """
    for sex in TABLE_SEXES:
        bands = sorted(
            ((c.age_min, c.age_max, c.cohort_id) for c in cells if c.sex == sex),
            key=lambda b: b[0],
        )
        previous_max: Optional[int] = None
        previous_id: Optional[str] = None
        for age_min, age_max, cohort_id in bands:
            _require(
                age_max is None or age_max >= age_min,
                f"{feature}: cohort {cohort_id!r} has age_max < age_min.",
            )
            if previous_max is None and previous_id is not None:
                raise PopulationTableError(
                    f"{feature}: cohort {previous_id!r} is open-ended above but "
                    f"is followed by {cohort_id!r}. Only the last band may be "
                    "open, or ages would fall in two cells."
                )
            if previous_max is not None:
                _require(
                    age_min > previous_max,
                    f"{feature}: cohorts {previous_id!r} and {cohort_id!r} "
                    "cover overlapping ages.",
                )
            previous_max, previous_id = age_max, cohort_id


def _check_table(table: PopulationTable) -> None:
    """Everything checkable about one table without the raw microdata."""
    feature = table.feature
    _require(
        feature in CANONICAL_FEATURES,
        f"table {table.table_id!r} declares feature {feature!r}, which is not "
        "in app/data/feature_catalog.py.",
    )
    _require(
        feature not in EXCLUDED_FEATURES,
        f"{feature!r} has a distribution table AND an EXCLUDED_FEATURES entry. "
        "One of the two is a mistake and it is not this file's job to pick.",
    )

    grid = table.percentile_grid
    _require(len(grid) >= 2, f"{feature}: a percentile grid needs at least two "
             "cut-points to bracket anything between.")
    _require(
        all(b > a for a, b in zip(grid, grid[1:])),
        f"{feature}: percentile_grid is not strictly increasing.",
    )
    _require(
        0.0 < grid[0] and grid[-1] < 100.0,
        f"{feature}: percentile_grid must lie strictly inside 0-100; the 0th "
        "and 100th percentiles are the sample's extremes, not population "
        "cut-points.",
    )

    # The unit the table publishes must be a unit this service can actually
    # convert a patient's value INTO -- otherwise the table is unusable and
    # every lookup against it would be UNIT_NOT_CONVERTIBLE at runtime.
    unit_key = normalize_unit(table.unit)
    _require(
        unit_key == table.unit,
        f"{feature}: table unit {table.unit!r} is not written in the "
        f"normalised spelling app/data/unit_conversions.py uses "
        f"({unit_key!r}).",
    )
    _require(
        is_known_unit(unit_key),
        f"{feature}: table unit {table.unit!r} is not a unit "
        "app/data/unit_conversions.py recognises.",
    )
    _require(
        conversion_for(feature, unit_key) is not None,
        f"{feature}: no audited conversion exists between {table.unit!r} and "
        f"the canonical unit {FEATURES[feature].canonical_unit!r}, so a "
        "patient's value could never be placed in this table honestly.",
    )
    _require(
        FEATURES[feature].value_type in ("number", "integer"),
        f"{feature}: has a distribution table but is declared "
        f"{FEATURES[feature].value_type!r} in the feature catalogue. Only a "
        "measured number has a distribution.",
    )

    _require(bool(table.cohorts), f"{feature}: table publishes no cohorts.")
    for cohort in table.cohorts:
        _require(
            cohort.sex in TABLE_SEXES,
            f"{feature}: cohort {cohort.cohort_id!r} has sex {cohort.sex!r}, "
            f"which is not one of {TABLE_SEXES}.",
        )
        _require(
            cohort.n_unweighted > 0 and cohort.weighted_population > 0,
            f"{feature}: cohort {cohort.cohort_id!r} represents nobody.",
        )
    _check_bands_disjoint(feature, table.cohorts)

    # A dropped band must not also be published, or `dropped_for()` and
    # `cohort_for()` would both answer and the service would have to choose.
    for dropped in table.dropped_cohorts:
        for cohort in table.cohorts:
            if cohort.sex != dropped.sex:
                continue
            overlap_low = max(cohort.age_min, dropped.age_min)
            highs = [h for h in (cohort.age_max, dropped.age_max) if h is not None]
            overlap_high = min(highs) if highs else overlap_low
            _require(
                overlap_low > overlap_high,
                f"{feature}: dropped band {dropped.sex} {dropped.age_band} "
                f"overlaps published cohort {cohort.cohort_id!r}.",
            )


def _load_table(path: Path) -> PopulationTable:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # unreadable or not JSON
        raise PopulationTableError(f"{path.name}: could not be read: {exc}") from exc

    _require(isinstance(raw, dict), f"{path.name}: top level is not an object.")
    _require(
        int(raw.get("schema_version", -1)) == SUPPORTED_SCHEMA_VERSION,
        f"{path.name}: schema_version is "
        f"{raw.get('schema_version')!r}, this loader understands only "
        f"{SUPPORTED_SCHEMA_VERSION}.",
    )
    feature = str(raw.get("feature", ""))
    _require(
        feature == path.stem,
        f"{path.name}: declares feature {feature!r}. The file name is the key "
        "the service looks tables up by, so the two must agree.",
    )

    grid = tuple(float(p) for p in raw["percentile_grid"])
    cohorts = tuple(
        _load_cohort(feature, cell, len(grid)) for cell in raw.get("cohorts", [])
    )
    dropped: List[DroppedCohort] = []
    for cell in raw.get("dropped_cohorts", []):
        age_min, age_max = _parse_age_band(str(cell["age_band"]))
        dropped.append(
            DroppedCohort(
                sex=str(cell["sex"]),
                age_band=str(cell["age_band"]),
                age_min=age_min,
                age_max=age_max,
                n_unweighted=int(cell["n_unweighted"]),
            )
        )

    table = PopulationTable(
        feature=feature,
        table_id=str(raw["table_id"]),
        unit=str(raw["unit"]),
        measurand=str(raw["measurand"]),
        derivation=str(raw["derivation"]),
        built_on=str(raw["built_on"]),
        percentile_grid=grid,
        source=dict(raw.get("source", {})),
        population=dict(raw.get("population", {})),
        method=dict(raw.get("method", {})),
        counts=dict(raw.get("counts", {})),
        notes=tuple(str(n) for n in raw.get("notes", [])),
        cohorts=cohorts,
        dropped_cohorts=tuple(dropped),
    )
    _check_table(table)
    return table


def _load_all() -> Dict[str, PopulationTable]:
    _require(
        DISTRIBUTIONS_DIR.is_dir(),
        f"population distributions directory not found at {DISTRIBUTIONS_DIR}. "
        "Rebuild it with datasets/population/build_population_tables.py.",
    )
    tables: Dict[str, PopulationTable] = {}
    for path in sorted(DISTRIBUTIONS_DIR.glob("*.json")):
        table = _load_table(path)
        tables[table.feature] = table
    _require(bool(tables), f"no distribution tables found in {DISTRIBUTIONS_DIR}.")
    return tables


# --------------------------------------------------------------------------
# Import-time enforcement
# --------------------------------------------------------------------------

TABLES: Dict[str, PopulationTable] = _load_all()

#: Canonical features backed by a real published distribution, catalogue order.
COVERED_FEATURES: Tuple[str, ...] = tuple(
    name for name in CANONICAL_FEATURES if name in TABLES
)


def _check_catalogue_cover() -> None:
    """Every canonical feature is table-backed OR deliberately excluded.

    This is the promise `policy.py` makes in the comment above
    `EXCLUDED_FEATURES`, enforced. A feature added to the catalogue and to
    neither list would simply never appear in a population response, which
    looks exactly like having forgotten it.
    """
    undecided = [
        name
        for name in CANONICAL_FEATURES
        if name not in TABLES and name not in EXCLUDED_FEATURES
    ]
    _require(
        not undecided,
        f"canonical feature(s) {undecided!r} have neither a population "
        "distribution table nor an app/population/policy.py EXCLUDED_FEATURES "
        "entry. Module 31 will not silently omit a feature: either ship a "
        "verified table for it, or record why there is none.",
    )

    unknown = [name for name in EXCLUDED_FEATURES if name not in CANONICAL_FEATURES]
    _require(
        not unknown,
        f"EXCLUDED_FEATURES names {unknown!r}, which are not in "
        "app/data/feature_catalog.py. A stale exclusion hides the fact that "
        "nothing is being excluded.",
    )

    for name, entry in EXCLUDED_FEATURES.items():
        _require(
            entry.get("reason_code") in REASON_CODES,
            f"EXCLUDED_FEATURES[{name!r}] carries reason_code "
            f"{entry.get('reason_code')!r}, which is not a PopulationReason.",
        )
        _require(
            bool(str(entry.get("message", "")).strip()),
            f"EXCLUDED_FEATURES[{name!r}] has no message. A refusal a patient "
            "cannot read is not a refusal.",
        )


def _check_reason_messages() -> None:
    """Every reason code the service can emit has patient-readable wording.

    `UNKNOWN_FEATURE` and the two per-feature codes are covered by
    `REASON_MESSAGES` as well, because they are also reachable for a feature
    that has no `EXCLUDED_FEATURES` entry to speak for it.
    """
    missing = [code for code in REASON_CODES if code not in REASON_MESSAGES]
    _require(
        not missing,
        f"reason code(s) {missing!r} have no entry in "
        "app/population/policy.py REASON_MESSAGES. A code with no wording "
        "would reach a patient as a bare identifier.",
    )
    unknown = [code for code in REASON_MESSAGES if code not in REASON_CODES]
    _require(
        not unknown,
        f"REASON_MESSAGES has wording for {unknown!r}, which are not "
        "PopulationReason codes.",
    )


_check_catalogue_cover()
_check_reason_messages()


# --------------------------------------------------------------------------
# Public lookups
# --------------------------------------------------------------------------


def table_for(feature: str) -> Optional[PopulationTable]:
    """The published table for a canonical feature, or `None` if there is none."""
    return TABLES.get(feature)


def has_table(feature: str) -> bool:
    return feature in TABLES


def excluded_reason(feature: str) -> Optional[Tuple[str, str]]:
    """`(reason_code, message)` for a deliberately excluded feature, or `None`."""
    entry = EXCLUDED_FEATURES.get(feature)
    if entry is None:
        return None
    return str(entry["reason_code"]), str(entry["message"])


def reason_message(reason_code: str) -> str:
    """The patient-facing sentence for a reason code.

    Every code in `REASON_CODES` is present -- `_check_reason_messages()`
    enforced that at import -- so this cannot invent wording for an unknown
    code; it raises instead.
    """
    try:
        return REASON_MESSAGES[reason_code]
    except KeyError as exc:  # pragma: no cover - prevented at import
        raise PopulationTableError(
            f"no patient-facing message for reason code {reason_code!r}"
        ) from exc


def inventory() -> Dict[str, object]:
    """The whole shipped table set, machine-readable. No patient data.

    Served by `GET /api/v1/population/policy` so a reviewer can see exactly
    which parameters are covered, from which survey file, at which digest --
    and which canonical features are not covered, and why.
    """
    return {
        "distributions_dir": str(DISTRIBUTIONS_DIR),
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "covered_features": list(COVERED_FEATURES),
        "excluded_features": {
            name: {
                "reason_code": entry["reason_code"],
                "message": entry["message"],
            }
            for name, entry in EXCLUDED_FEATURES.items()
        },
        "tables": {name: TABLES[name].inventory() for name in COVERED_FEATURES},
    }


__all__ = [
    "COVERED_FEATURES",
    "DISTRIBUTIONS_DIR",
    "SUPPORTED_SCHEMA_VERSION",
    "TABLES",
    "TABLE_SEXES",
    "Cohort",
    "DroppedCohort",
    "PopulationReason",
    "PopulationTable",
    "PopulationTableError",
    "excluded_reason",
    "has_table",
    "inventory",
    "reason_message",
    "table_for",
]
