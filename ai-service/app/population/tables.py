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

DISTRIBUTIONS_DIR: Path = (
    Path(__file__).resolve().parents[2] / "datasets" / "population" / "distributions"
)

SUPPORTED_SCHEMA_VERSION = 1

TABLE_SEXES: Tuple[str, ...] = ("male", "female")


class PopulationTableError(RuntimeError):
    pass


@dataclass(frozen=True)
class Cohort:

    cohort_id: str
    sex: str
    age_min: int
    age_max: Optional[int]
    age_band_label: str
    n_unweighted: int
    weighted_population: float
    percentile_values: Tuple[float, ...]
    weighted_mean: float

    def covers(self, age: float) -> bool:
        completed_years = math.floor(age)
        if completed_years < self.age_min:
            return False
        return self.age_max is None or completed_years <= self.age_max


@dataclass(frozen=True)
class DroppedCohort:

    sex: str
    age_band: str
    age_min: int
    age_max: Optional[int]
    n_unweighted: int

    def covers(self, age: float) -> bool:
        completed_years = math.floor(age)
        if completed_years < self.age_min:
            return False
        return self.age_max is None or completed_years <= self.age_max


_AGE_BAND_RE = re.compile(r"^(\d{1,3})(?:-(\d{1,3})|\+)$")


@dataclass(frozen=True)
class PopulationTable:

    feature: str
    table_id: str
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
        return min(c.age_min for c in self.cohorts)

    @property
    def max_age(self) -> Optional[int]:
        if any(c.age_max is None for c in self.cohorts):
            return None
        return max(c.age_max for c in self.cohorts)

    @property
    def age_band_labels(self) -> Tuple[str, ...]:
        seen: List[str] = []
        for cohort in self.cohorts:
            if cohort.age_band_label not in seen:
                seen.append(cohort.age_band_label)
        return tuple(seen)

    def cohort_for(self, sex: str, age: float) -> Optional[Cohort]:
        for cohort in self.cohorts:
            if cohort.sex == sex and cohort.covers(age):
                return cohort
        return None

    def dropped_for(self, sex: str, age: float) -> Optional[DroppedCohort]:
        for dropped in self.dropped_cohorts:
            if dropped.sex == sex and dropped.covers(age):
                return dropped
        return None

    def reference(self) -> Dict[str, object]:
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
    assert match is not None
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
    numeric = tuple(float(v) for v in values)
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
        age_min=int(raw["age_min"]),
        age_max=None if age_max is None else int(age_max),
        age_band_label=str(raw["age_band_label"]),
        n_unweighted=int(raw["n_unweighted"]),
        weighted_population=float(raw["weighted_population"]),
        percentile_values=numeric,
        weighted_mean=float(raw["weighted_mean"]),
    )


def _check_bands_disjoint(feature: str, cells: Sequence[Cohort]) -> None:
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
    except (OSError, ValueError) as exc:
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


TABLES: Dict[str, PopulationTable] = _load_all()

COVERED_FEATURES: Tuple[str, ...] = tuple(
    name for name in CANONICAL_FEATURES if name in TABLES
)


def _check_catalogue_cover() -> None:
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


def table_for(feature: str) -> Optional[PopulationTable]:
    return TABLES.get(feature)


def has_table(feature: str) -> bool:
    return feature in TABLES


def excluded_reason(feature: str) -> Optional[Tuple[str, str]]:
    entry = EXCLUDED_FEATURES.get(feature)
    if entry is None:
        return None
    return str(entry["reason_code"]), str(entry["message"])


def reason_message(reason_code: str) -> str:
    try:
        return REASON_MESSAGES[reason_code]
    except KeyError as exc:
        raise PopulationTableError(
            f"no patient-facing message for reason code {reason_code!r}"
        ) from exc


def inventory() -> Dict[str, object]:
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
