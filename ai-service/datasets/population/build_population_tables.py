"""Build Module 31's population distribution tables from REAL NHANES microdata.

RUN THIS TO REPRODUCE `distributions/*.json` FROM SOURCE. Nothing in Module 31
is hand-written, estimated, interpolated or "reasonably approximated": every
number in every shipped table is a survey-weighted quantile of the public
NHANES microdata files whose sha256 digests are recorded in `PROVENANCE.md`.

    cd ai-service
    .venv/Scripts/python.exe datasets/population/build_population_tables.py \
        --raw datasets/population/raw \
        --out datasets/population/distributions

The raw `.xpt` files are NOT committed (they are ~15 MB and are permanently
published by CDC). `--download` fetches them from the CDC URLs recorded below
and verifies the sha256 of each against the digest recorded here, so a silently
changed upstream file fails the build instead of quietly changing a percentile.

--------------------------------------------------------------------------
WHY MICRODATA AND NOT A PUBLISHED PERCENTILE TABLE
--------------------------------------------------------------------------

CDC/NCHS publishes summary tables for some of these analytes, but not for all
of them, not on a single consistent set of age bands, and not at the percentile
grid this module needs. Transcribing numbers out of PDFs by hand is exactly the
kind of step where a wrong digit becomes a false clinical claim.

The NHANES public-use microdata file IS the primary published source. Computing
a weighted quantile from it is measurement, not invention: it is deterministic,
it is reproducible by anyone from the same public files, and the method is
written down below. The shipped tables therefore say
`"derivation": "computed_by_vaidyaai_from_published_microdata"` and never claim
to be a CDC-published percentile table.

Two published NCHS summary statistics are recomputed as a CROSS-CHECK and
printed by this script (see `--check`); the agreement is recorded in
`PROVENANCE.md`.

--------------------------------------------------------------------------
METHOD (this is the whole method; there is nothing else)
--------------------------------------------------------------------------

Analytic sample
    * `RIDSTATR == 2`  -- interviewed AND MEC-examined (the exam weight is only
      valid for these).
    * `WTMEC2YR > 0`   -- a zero exam weight represents nobody.
    * `RIDAGEYR >= 20` -- ADULTS ONLY. Paediatric reference distributions are
      age-in-months sensitive and are not derivable at this band width; a child
      scored against an adult table is a clinical error, so children are simply
      not covered (the service returns `available: false`).
    * `RIDEXPRG != 1`  -- pregnant participants excluded. Pregnancy shifts
      haemoglobin, creatinine and lipids materially. Recorded as a limitation:
      a pregnant patient is therefore compared against a non-pregnant cohort.
    * the analyte value is present (item non-response dropped; NHANES notes
      that no re-weighting for item non-response is applied here).

Strata
    * sex from `RIAGENDR` (1 = Male, 2 = Female -- NHANES codebook).
    * ten-year age bands 20-29 .. 70-79 plus "80 and over" (NHANES top-codes
      age at 80, so the top band cannot be split).
    * A stratum with fewer than MIN_CELL_N = 100 unweighted observations is
      DROPPED, not published. A noisy percentile is worse than no percentile.

Weighted quantile estimator
    Sort the stratum's values ascending. Let W be the cumulative sum of
    `WTMEC2YR` and T the stratum's total weight. The p-th percentile is the
    smallest observed value x_i with W_i / T >= p/100 -- the inverse of the
    weighted empirical CDF (the "type 1" / lower estimator). No interpolation
    between observations, no distributional assumption. Every published number
    is therefore a value that a real NHANES participant actually had.

    Variance is NOT estimated. NHANES is a complex multistage design and a
    correct standard error needs `SDMVPSU`/`SDMVSTRA` with Taylor-series
    linearisation. The module reports a percentile BAND rather than a point
    estimate precisely because it cannot report an interval, and PROVENANCE.md
    records this as a limitation.

Percentile grid
    1, 2.5, 5, 10, 25, 50, 75, 90, 95, 97.5, 99.
    The service brackets a patient's value BETWEEN two adjacent grid points and
    never interpolates a single percentile number out of them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Source files. sha256 recorded 2026-09-04 from the CDC URLs below.
# --------------------------------------------------------------------------

CDC_BASE = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public"

SOURCE_FILES: Dict[str, Dict[str, str]] = {
    "DEMO_J.xpt": {
        "url": f"{CDC_BASE}/2017/DataFiles/DEMO_J.xpt",
        "sha256": "c0b46e0345ea19404928656277c8b0d10b0cca348a9b2fe4fc3c67e8b7ee73ec",
        "bytes": "3412720",
    },
    "BMX_J.xpt": {
        "url": f"{CDC_BASE}/2017/DataFiles/BMX_J.xpt",
        "sha256": "8d675e42d8826ac98714b2c3dd4c5138a5e353fb4424f7eff5e6db4a01ce838a",
        "bytes": "1466000",
    },
    "TCHOL_J.xpt": {
        "url": f"{CDC_BASE}/2017/DataFiles/TCHOL_J.xpt",
        "sha256": "0291a6a4f6d82dac8392c8c992b519946824dfeda01647935520cf506ed9f4ab",
        "bytes": "179680",
    },
    "GHB_J.xpt": {
        "url": f"{CDC_BASE}/2017/DataFiles/GHB_J.xpt",
        "sha256": "35f07094573a0061a03ed609a5a363b34eb1b1c7065d1623b43d72e132a8a654",
        "bytes": "103520",
    },
    "CBC_J.xpt": {
        "url": f"{CDC_BASE}/2017/DataFiles/CBC_J.xpt",
        "sha256": "00f964098dc91272e415344554cbf1b627ecaeb2eda201518527446a7d81e742",
        "bytes": "1476320",
    },
    "BIOPRO_J.xpt": {
        "url": f"{CDC_BASE}/2017/DataFiles/BIOPRO_J.xpt",
        "sha256": "5bcd5722c1892883b96a9d7fed0befadabacae313f800fadc0133cd5dd00c4c6",
        "bytes": "2106080",
    },
    "VID_J.xpt": {
        "url": f"{CDC_BASE}/2017/DataFiles/VID_J.xpt",
        "sha256": "5a688e2107758b9344a222823fbdce4838928bbec70e1fd2f34e3ef5c45a95ac",
        "bytes": "604400",
    },
    "DEMO_H.xpt": {
        "url": f"{CDC_BASE}/2013/DataFiles/DEMO_H.xpt",
        "sha256": "f8f0cbb3085a323d4cde22349b164878fea1e64dbc404e65b5815c7816b547d7",
        "bytes": "3833200",
    },
    "VITB12_H.xpt": {
        "url": f"{CDC_BASE}/2013/DataFiles/VITB12_H.xpt",
        "sha256": "6d280479d279379a1f67278722e3b6a1f1a3566c06dfc3a1f02c9713975633ae",
        "bytes": "138880",
    },
}

# --------------------------------------------------------------------------
# Strata
# --------------------------------------------------------------------------

PERCENTILE_GRID: Tuple[float, ...] = (
    1.0,
    2.5,
    5.0,
    10.0,
    25.0,
    50.0,
    75.0,
    90.0,
    95.0,
    97.5,
    99.0,
)

#: (age_min, age_max_inclusive). 80 is NHANES' top-code, so the last band is open.
AGE_BANDS: Tuple[Tuple[int, Optional[int]], ...] = (
    (20, 29),
    (30, 39),
    (40, 49),
    (50, 59),
    (60, 69),
    (70, 79),
    (80, None),
)

SEXES = {1: "male", 2: "female"}

#: Below this many unweighted observations a stratum is dropped, not published.
MIN_CELL_N = 100


# --------------------------------------------------------------------------
# Feature specifications -- one per canonical VaidyaAI feature that has a
# real, verified NHANES distribution.
# --------------------------------------------------------------------------


class Spec:
    def __init__(
        self,
        *,
        feature: str,
        table_id: str,
        analyte_file: str,
        demo_file: str,
        column: str,
        unit: str,
        cycle: str,
        cycle_label: str,
        analyte_label: str,
        eligible_ages: str,
        weight_variable: str,
        measurand: str,
        llod: Optional[str] = None,
        llod_flag_column: Optional[str] = None,
        decimals: int = 2,
        notes: Tuple[str, ...] = (),
    ) -> None:
        self.feature = feature
        self.table_id = table_id
        self.analyte_file = analyte_file
        self.demo_file = demo_file
        self.column = column
        self.unit = unit
        self.cycle = cycle
        self.cycle_label = cycle_label
        self.analyte_label = analyte_label
        self.eligible_ages = eligible_ages
        self.weight_variable = weight_variable
        self.measurand = measurand
        self.llod = llod
        self.llod_flag_column = llod_flag_column
        self.decimals = decimals
        self.notes = notes


SPECS: Tuple[Spec, ...] = (
    Spec(
        feature="bmi",
        table_id="nhanes_2017_2018_bmi",
        analyte_file="BMX_J.xpt",
        demo_file="DEMO_J.xpt",
        column="BMXBMI",
        unit="kg/m2",
        cycle="2017-2018",
        cycle_label="NHANES 2017-2018 (cycle J)",
        analyte_label="BMXBMI - Body Mass Index (kg/m**2)",
        eligible_ages="all examined participants (body measures component)",
        weight_variable="WTMEC2YR",
        measurand="Body mass index computed by NCHS from measured standing height and measured weight.",
        decimals=1,
        notes=(
            "Height and weight are MEASURED by trained examiners in the Mobile "
            "Examination Center, not self-reported.",
        ),
    ),
    Spec(
        feature="cholesterol",
        table_id="nhanes_2017_2018_total_cholesterol",
        analyte_file="TCHOL_J.xpt",
        demo_file="DEMO_J.xpt",
        column="LBXTC",
        unit="mg/dl",
        cycle="2017-2018",
        cycle_label="NHANES 2017-2018 (cycle J)",
        analyte_label="LBXTC - Total Cholesterol (mg/dL)",
        eligible_ages="examined participants aged 6 years and older",
        weight_variable="WTMEC2YR",
        measurand=(
            "Serum TOTAL cholesterol, enzymatic assay. Matches VaidyaAI's "
            "`cholesterol` feature, which is explicitly TOTAL cholesterol "
            "(HDL/LDL/VLDL are separate analytes in feature_catalog.py)."
        ),
        llod="4 mg/dL",
        decimals=0,
        notes=(
            "Measured regardless of fasting status, so the cohort is "
            "fasting-mixed in the same way an arbitrary patient sample is. "
            "Total cholesterol is only minimally fasting-dependent.",
            "Includes participants on lipid-lowering therapy. This is a "
            "distribution of the US adult population as it is, NOT of "
            "untreated people.",
        ),
    ),
    Spec(
        feature="hba1c",
        table_id="nhanes_2017_2018_hba1c",
        analyte_file="GHB_J.xpt",
        demo_file="DEMO_J.xpt",
        column="LBXGH",
        unit="%",
        cycle="2017-2018",
        cycle_label="NHANES 2017-2018 (cycle J)",
        analyte_label="LBXGH - Glycohemoglobin (%)",
        eligible_ages="examined participants aged 12 years and older",
        weight_variable="WTMEC2YR",
        measurand=(
            "Glycohaemoglobin (HbA1c) as a percentage, Tosoh HLC-723 HPLC, "
            "NGSP-certified. Matches VaidyaAI's `hba1c` canonical unit '%' "
            "(NGSP), NOT IFCC mmol/mol."
        ),
        decimals=1,
        notes=(
            "Includes people with diagnosed diabetes and people on glucose-"
            "lowering treatment. The upper percentiles of this distribution "
            "are therefore populated by treated and untreated diabetes.",
        ),
    ),
    Spec(
        feature="hemoglobin",
        table_id="nhanes_2017_2018_hemoglobin",
        analyte_file="CBC_J.xpt",
        demo_file="DEMO_J.xpt",
        column="LBXHGB",
        unit="g/dl",
        cycle="2017-2018",
        cycle_label="NHANES 2017-2018 (cycle J)",
        analyte_label="LBXHGB - Hemoglobin (g/dL)",
        eligible_ages="examined participants aged 1 year and over",
        weight_variable="WTMEC2YR",
        measurand="Whole-blood haemoglobin concentration, Sysmex XN-series automated analyser.",
        decimals=1,
        notes=(
            "Haemoglobin distribution differs markedly by sex, which is why "
            "an unmatched cohort is never offered for this feature.",
            "Altitude is not adjusted for. NHANES examines at sea-level and "
            "high-altitude locations alike.",
        ),
    ),
    Spec(
        feature="creatinine",
        table_id="nhanes_2017_2018_creatinine",
        analyte_file="BIOPRO_J.xpt",
        demo_file="DEMO_J.xpt",
        column="LBXSCR",
        unit="mg/dl",
        cycle="2017-2018",
        cycle_label="NHANES 2017-2018 (cycle J)",
        analyte_label="LBXSCR - Creatinine, refrigerated serum (mg/dL)",
        eligible_ages="examined participants aged 12 years and older",
        weight_variable="WTMEC2YR",
        measurand=(
            "SERUM creatinine (Roche Cobas 6000, enzymatic, IDMS-traceable). "
            "Matches VaidyaAI's `creatinine` feature, which is serum "
            "creatinine; urine creatinine is a different analyte and is "
            "refused upstream by NON_BLOOD_SPECIMEN_TOKENS."
        ),
        decimals=2,
        notes=(
            "Serum creatinine tracks muscle mass as well as kidney function. "
            "A high percentile is not by itself a kidney finding.",
        ),
    ),
    Spec(
        feature="vitamin_d",
        table_id="nhanes_2017_2018_vitamin_d",
        analyte_file="VID_J.xpt",
        demo_file="DEMO_J.xpt",
        column="LBXVIDMS",
        unit="nmol/l",
        cycle="2017-2018",
        cycle_label="NHANES 2017-2018 (cycle J)",
        analyte_label="LBXVIDMS - 25OHD2+25OHD3 (nmol/L)",
        eligible_ages="examined participants aged 1 year and older",
        weight_variable="WTMEC2YR",
        measurand=(
            "Total serum 25-hydroxyvitamin D (25OHD2 + 25OHD3) by HPLC-MS/MS, "
            "standardised to the Vitamin D Standardization Program. "
            "PUBLISHED IN nmol/L. VaidyaAI's canonical unit is ng/mL, so the "
            "SERVICE converts the patient's value into nmol/L before lookup "
            "using app.data.unit_conversions -- the table itself is never "
            "rescaled."
        ),
        llod_flag_column="LBDVIDLC",
        decimals=1,
        notes=(
            "Serum 25OHD has a strong seasonal cycle. NHANES releases only a "
            "six-month examination period indicator (RIDEXMON) and the "
            "distribution here is pooled across the whole year, so a summer "
            "and a winter draw are compared against the same cohort.",
            "Values below the limit of detection are stored by NCHS as "
            "LLOD/sqrt(2); the count of such records is recorded below.",
        ),
    ),
    Spec(
        feature="vitamin_b12",
        table_id="nhanes_2013_2014_vitamin_b12",
        analyte_file="VITB12_H.xpt",
        demo_file="DEMO_H.xpt",
        column="LBDB12",
        unit="pg/ml",
        cycle="2013-2014",
        cycle_label="NHANES 2013-2014 (cycle H)",
        analyte_label="LBDB12 - Vitamin B12 (pg/mL)",
        eligible_ages="examined participants aged 19 years and older",
        weight_variable="WTMEC2YR",
        measurand="Serum vitamin B12 (cobalamin), Roche Elecsys electrochemiluminescence immunoassay.",
        llod="30 pg/mL",
        decimals=0,
        notes=(
            "DIFFERENT SURVEY CYCLE from every other table here. Serum B12 was "
            "not measured in NHANES 2017-2018; 2013-2014 is the most recent "
            "cycle in which it was. The cohort is therefore US adults in "
            "2013-2014, and the table records that.",
            "Serum B12 does not distinguish B12 bound to haptocorrin from "
            "metabolically available B12, and is raised by supplementation, "
            "which is common. A high percentile frequently reflects "
            "supplement use.",
        ),
    ),
)


# --------------------------------------------------------------------------
# Machinery
# --------------------------------------------------------------------------


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_sources(raw_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    for name, meta in SOURCE_FILES.items():
        target = raw_dir / name
        if not target.exists():
            print(f"downloading {name} <- {meta['url']}")
            urllib.request.urlretrieve(meta["url"], target)  # noqa: S310
        digest = sha256_of(target)
        status = "OK" if digest == meta["sha256"] else "MISMATCH"
        print(f"  {name}: {digest} [{status}]")
        if status == "MISMATCH":
            raise SystemExit(
                f"sha256 mismatch for {name}. The upstream file changed, or the "
                f"download is corrupt. REFUSING to build tables from it."
            )


def verify_sources(raw_dir: Path) -> Dict[str, str]:
    digests: Dict[str, str] = {}
    for name, meta in SOURCE_FILES.items():
        target = raw_dir / name
        if not target.exists():
            raise SystemExit(
                f"missing {target}. Run with --download to fetch the public "
                f"CDC files first."
            )
        digest = sha256_of(target)
        if digest != meta["sha256"]:
            raise SystemExit(f"sha256 mismatch for {name}: {digest}")
        digests[name] = digest
    return digests


def weighted_quantiles(
    values: np.ndarray, weights: np.ndarray, percentiles: Tuple[float, ...]
) -> List[float]:
    """Inverse of the weighted empirical CDF -- see the module docstring.

    Returns, for each requested percentile p, the smallest OBSERVED value whose
    cumulative weight fraction reaches p/100. No interpolation: every returned
    number is a value some participant actually had.
    """
    order = np.argsort(values, kind="mergesort")
    v = values[order]
    w = weights[order]
    cum = np.cumsum(w)
    total = cum[-1]
    out: List[float] = []
    for p in percentiles:
        idx = int(np.searchsorted(cum, (p / 100.0) * total, side="left"))
        idx = min(idx, len(v) - 1)
        out.append(float(v[idx]))
    return out


def weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    return float(np.sum(values * weights) / np.sum(weights))


def load_frame(raw_dir: Path, spec: Spec) -> pd.DataFrame:
    demo = pd.read_sas(raw_dir / spec.demo_file, format="xport")
    lab = pd.read_sas(raw_dir / spec.analyte_file, format="xport")
    keep_demo = ["SEQN", "RIAGENDR", "RIDAGEYR", "RIDSTATR", "WTMEC2YR"]
    if "RIDEXPRG" in demo.columns:
        keep_demo.append("RIDEXPRG")
    keep_lab = ["SEQN", spec.column]
    if spec.llod_flag_column and spec.llod_flag_column in lab.columns:
        keep_lab.append(spec.llod_flag_column)
    df = demo[keep_demo].merge(lab[keep_lab], on="SEQN", how="inner")
    return df


def build_table(raw_dir: Path, spec: Spec, digests: Dict[str, str]) -> dict:
    df = load_frame(raw_dir, spec)
    n_merged = len(df)

    df = df[df["RIDSTATR"] == 2]
    df = df[df["WTMEC2YR"] > 0]
    df = df[df["RIDAGEYR"] >= 20]
    if "RIDEXPRG" in df.columns:
        n_preg = int((df["RIDEXPRG"] == 1).sum())
        df = df[df["RIDEXPRG"] != 1]
    else:
        n_preg = 0
    df = df[df[spec.column].notna()]

    n_below_llod: Optional[int] = None
    if spec.llod_flag_column and spec.llod_flag_column in df.columns:
        n_below_llod = int((df[spec.llod_flag_column] == 1).sum())

    cohorts = []
    dropped = []
    for sex_code, sex_name in SEXES.items():
        for age_min, age_max in AGE_BANDS:
            sel = (df["RIAGENDR"] == sex_code) & (df["RIDAGEYR"] >= age_min)
            if age_max is not None:
                sel &= df["RIDAGEYR"] <= age_max
            cell = df[sel]
            n = len(cell)
            label = f"{age_min}-{age_max}" if age_max is not None else f"{age_min}+"
            if n < MIN_CELL_N:
                dropped.append(
                    {"sex": sex_name, "age_band": label, "n_unweighted": n}
                )
                continue
            values = cell[spec.column].to_numpy(dtype=float)
            weights = cell["WTMEC2YR"].to_numpy(dtype=float)
            cohorts.append(
                {
                    "cohort_id": f"{sex_name}_{age_min}_{age_max or 'plus'}",
                    "sex": sex_name,
                    "age_min": age_min,
                    "age_max": age_max,
                    "age_band_label": (
                        f"{age_min}-{age_max} years"
                        if age_max is not None
                        else f"{age_min} years and over"
                    ),
                    "n_unweighted": n,
                    "weighted_population": round(float(weights.sum()), 1),
                    "percentile_values": [
                        round(x, spec.decimals)
                        for x in weighted_quantiles(values, weights, PERCENTILE_GRID)
                    ],
                    "weighted_mean": round(weighted_mean(values, weights), spec.decimals),
                }
            )

    return {
        "table_id": spec.table_id,
        "schema_version": 1,
        "feature": spec.feature,
        "unit": spec.unit,
        "measurand": spec.measurand,
        "derivation": "computed_by_vaidyaai_from_published_microdata",
        "built_on": date.today().isoformat(),
        "percentile_grid": list(PERCENTILE_GRID),
        "source": {
            "name": "National Health and Nutrition Examination Survey (NHANES)",
            "publisher": (
                "National Center for Health Statistics, Centers for Disease "
                "Control and Prevention (US)"
            ),
            "cycle": spec.cycle,
            "cycle_label": spec.cycle_label,
            "data_file": spec.analyte_file,
            "data_file_url": SOURCE_FILES[spec.analyte_file]["url"],
            "data_file_sha256": digests[spec.analyte_file],
            "demographics_file": spec.demo_file,
            "demographics_file_url": SOURCE_FILES[spec.demo_file]["url"],
            "demographics_file_sha256": digests[spec.demo_file],
            "variable": spec.column,
            "variable_label": spec.analyte_label,
            "eligible_sample": spec.eligible_ages,
            "analytic_weight": spec.weight_variable,
            "retrieved_on": "2026-09-04",
            "citation": (
                f"Centers for Disease Control and Prevention (CDC). National "
                f"Center for Health Statistics (NCHS). National Health and "
                f"Nutrition Examination Survey Data, {spec.cycle}. Hyattsville, "
                f"MD: U.S. Department of Health and Human Services, CDC. "
                f"File {spec.analyte_file}, variable {spec.column}."
            ),
        },
        "population": {
            "description": (
                f"Civilian non-institutionalised United States population, "
                f"adults aged 20 and over, {spec.cycle}, excluding pregnant "
                f"participants."
            ),
            "country": "United States",
            "adults_only": True,
            "min_age": 20,
            "pregnant_excluded": True,
        },
        "method": {
            "estimator": (
                "survey-weighted empirical CDF inverse (type 1 / lower); no "
                "interpolation between observations"
            ),
            "weight_variable": spec.weight_variable,
            "min_cell_unweighted_n": MIN_CELL_N,
            "variance_estimated": False,
            "variance_note": (
                "No standard errors. A correct NHANES variance needs "
                "SDMVPSU/SDMVSTRA Taylor linearisation; the service reports a "
                "percentile BAND, never a point percentile, partly for this "
                "reason."
            ),
        },
        "counts": {
            "merged_records": n_merged,
            "analytic_sample": int(len(df)),
            "pregnant_excluded": n_preg,
            "below_llod": n_below_llod,
            "llod": spec.llod,
        },
        "notes": list(spec.notes),
        "cohorts": cohorts,
        "dropped_cohorts": dropped,
    }


# --------------------------------------------------------------------------
# Independent cross-check against PUBLISHED NCHS summary statistics.
# --------------------------------------------------------------------------

# The estimator below is validated against numbers CDC/NCHS ACTUALLY PUBLISHED.
# Both reference PDFs are committed under `reference/` so the transcription can
# be re-checked without a network.
#
# NOTE ON CYCLES: both published references pool NHANES 2015-2018 (two cycles);
# the tables built here use 2017-2018 (one cycle) so that a single, dated cohort
# is described. The comparison is therefore a METHOD check, not an identity
# check -- close agreement shows the sample definition, the exam weights and the
# quantile estimator are right; exact equality is not expected and would in fact
# be suspicious.

#: NCHS Series 3 No. 46, Table 15 (adult males) and Table 14 (adult females),
#: "Body mass index values ... selected percentiles ... United States,
#: 2015-2018", All race and Hispanic-origin groups rows. Transcribed from
#: `reference/sr03-046-508.pdf`, PDF pages 25 and 24.
#: Published percentile columns: 5th, 10th, 15th, 25th, 50th, 75th, 85th, 90th, 95th.
NCHS_SR3_46_BMI_PERCENTILES = {
    "male": {
        "20-29": [18.7, 20.0, 21.0, 22.6, 26.5, 31.6, 34.4, 36.8, 39.5],
        "30-39": [21.6, 23.0, 23.8, 25.4, 28.9, 33.7, 36.4, 38.3, 43.4],
        "40-49": [22.1, 23.5, 24.7, 26.2, 29.1, 32.8, 35.5, 38.1, 41.8],
        "50-59": [21.8, 22.6, 24.0, 25.2, 29.1, 32.8, 35.5, 37.4, 41.7],
        "60-69": [22.2, 23.2, 23.9, 25.8, 28.9, 33.3, 35.3, 37.1, 40.3],
        "70-79": [20.9, 22.9, 24.1, 25.9, 28.2, 32.8, 34.5, 35.6, 37.2],
    },
    "female": {
        "20-29": [18.6, 19.6, 20.4, 21.9, 26.2, 32.9, 37.4, 39.6, 43.3],
        "30-39": [19.8, 21.2, 22.0, 23.6, 28.3, 34.2, 38.2, 41.1, 46.1],
        "40-49": [20.6, 22.0, 22.8, 24.4, 28.6, 34.8, 39.3, 43.1, 46.6],
        "50-59": [19.6, 21.5, 22.5, 24.3, 29.1, 34.2, 37.7, 41.5, 45.7],
        "60-69": [20.4, 22.2, 23.2, 24.9, 29.2, 34.7, 37.2, 39.5, 42.9],
        "70-79": [20.8, 22.0, 23.3, 25.3, 28.8, 33.3, 35.7, 37.9, 42.1],
        "80+": [19.9, 20.8, 22.2, 23.8, 27.5, 30.8, 33.5, 35.5, 39.3],
    },
}
NCHS_SR3_46_GRID = (5.0, 10.0, 15.0, 25.0, 50.0, 75.0, 85.0, 90.0, 95.0)

#: NCHS Data Brief No. 363, April 2020, Figure 1 notes: "Crude estimates are
#: 11.5% for total, 10.3% for men, and 12.6% for women" -- prevalence of HIGH
#: total cholesterol (>= 240 mg/dL) among US adults aged 20 and over,
#: 2015-2018. Transcribed from `reference/db363-h.pdf`, page 1.
DB363_HIGH_TC_CRUDE = {"total": 11.5, "male": 10.3, "female": 12.6}


def run_cross_checks(raw_dir: Path) -> None:
    by_feature = {s.feature: s for s in SPECS}

    print("\n--- cross-check 1: BMI percentiles vs NCHS Series 3 No. 46 ---")
    print("    (published 2015-2018; computed 2017-2018 -- method check)")
    spec = by_feature["bmi"]
    df = load_frame(raw_dir, spec)
    df = df[(df["RIDSTATR"] == 2) & (df["WTMEC2YR"] > 0) & (df["RIDAGEYR"] >= 20)]
    df = df[df["RIDEXPRG"] != 1]
    df = df[df[spec.column].notna()]
    worst = 0.0
    for sex_name, bands in NCHS_SR3_46_BMI_PERCENTILES.items():
        sex_code = 1 if sex_name == "male" else 2
        for band, published in bands.items():
            if band.endswith("+"):
                lo, hi = int(band[:-1]), 200
            else:
                lo, hi = (int(x) for x in band.split("-"))
            cell = df[
                (df["RIAGENDR"] == sex_code)
                & (df["RIDAGEYR"] >= lo)
                & (df["RIDAGEYR"] <= hi)
            ]
            got = weighted_quantiles(
                cell[spec.column].to_numpy(dtype=float),
                cell["WTMEC2YR"].to_numpy(dtype=float),
                NCHS_SR3_46_GRID,
            )
            diffs = [abs(a - b) for a, b in zip(got, published)]
            worst = max(worst, max(diffs))
            print(
                f"  {sex_name:>6} {band:>6}  n={len(cell):>4}  "
                f"max|diff|={max(diffs):.2f}  median: computed {got[4]:.1f} "
                f"vs published {published[4]:.1f}"
            )
    print(f"  WORST absolute difference across all 13 cohorts x 9 percentiles: {worst:.2f} kg/m2")

    print("\n--- cross-check 2: high total cholesterol prevalence vs NCHS DB363 ---")
    spec = by_feature["cholesterol"]
    df = load_frame(raw_dir, spec)
    df = df[(df["RIDSTATR"] == 2) & (df["WTMEC2YR"] > 0) & (df["RIDAGEYR"] >= 20)]
    df = df[df["RIDEXPRG"] != 1]
    df = df[df[spec.column].notna()]
    for label, published in DB363_HIGH_TC_CRUDE.items():
        cell = df if label == "total" else df[df["RIAGENDR"] == (1 if label == "male" else 2)]
        w = cell["WTMEC2YR"].to_numpy(dtype=float)
        high = (cell[spec.column].to_numpy(dtype=float) >= 240.0).astype(float)
        pct = 100.0 * float(np.sum(high * w) / np.sum(w))
        print(
            f"  {label:>6}: computed {pct:.1f}%  vs published crude "
            f"{published}%  (|d|={abs(pct - published):.1f} pp)"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    here = Path(__file__).resolve().parent
    parser.add_argument("--raw", default=str(here / "raw"))
    parser.add_argument("--out", default=str(here / "distributions"))
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    raw_dir = Path(args.raw)
    out_dir = Path(args.out)

    if args.download:
        download_sources(raw_dir)
    digests = verify_sources(raw_dir)

    out_dir.mkdir(parents=True, exist_ok=True)
    for spec in SPECS:
        table = build_table(raw_dir, spec, digests)
        path = out_dir / f"{spec.feature}.json"
        path.write_text(json.dumps(table, indent=2) + "\n", encoding="utf-8")
        print(
            f"{spec.feature:>14}: {len(table['cohorts'])} cohorts, "
            f"n={table['counts']['analytic_sample']}, "
            f"dropped={len(table['dropped_cohorts'])} -> {path.name}"
        )

    if args.check:
        run_cross_checks(raw_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
