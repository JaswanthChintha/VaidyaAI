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

MIN_CELL_N = 100


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
    Spec(
        feature="hematocrit",
        table_id="nhanes_2017_2018_hematocrit",
        analyte_file="CBC_J.xpt",
        demo_file="DEMO_J.xpt",
        column="LBXHCT",
        unit="%",
        cycle="2017-2018",
        cycle_label="NHANES 2017-2018 (cycle J)",
        analyte_label="LBXHCT - Hematocrit (%)",
        eligible_ages="examined participants aged 1 year and over",
        weight_variable="WTMEC2YR",
        measurand=(
            "Haematocrit -- the percentage of whole blood volume occupied by "
            "red cells, Sysmex XN-series. PRINTED AS `PCV` (packed cell "
            "volume) on the reports this service reads; the two names are the "
            "same measurement."
        ),
        decimals=1,
        notes=(
            "Strongly sex-dependent, like haemoglobin, which is why an "
            "unmatched cohort is never offered.",
            "Altitude is not adjusted for.",
        ),
    ),
    Spec(
        feature="rbc_count",
        table_id="nhanes_2017_2018_rbc_count",
        analyte_file="CBC_J.xpt",
        demo_file="DEMO_J.xpt",
        column="LBXRBCSI",
        unit="10^6/ul",
        cycle="2017-2018",
        cycle_label="NHANES 2017-2018 (cycle J)",
        analyte_label="LBXRBCSI - Red blood cell count (million cells/uL)",
        eligible_ages="examined participants aged 1 year and over",
        weight_variable="WTMEC2YR",
        measurand="Red blood cell count, Sysmex XN-series automated analyser.",
        decimals=2,
        notes=(
            "Sex-dependent. Harmful at both extremes (anaemia below, "
            "polycythaemia above), so no direction of harm is declared.",
        ),
    ),
    Spec(
        feature="mcv",
        table_id="nhanes_2017_2018_mcv",
        analyte_file="CBC_J.xpt",
        demo_file="DEMO_J.xpt",
        column="LBXMCVSI",
        unit="fl",
        cycle="2017-2018",
        cycle_label="NHANES 2017-2018 (cycle J)",
        analyte_label="LBXMCVSI - Mean cell volume (fL)",
        eligible_ages="examined participants aged 1 year and over",
        weight_variable="WTMEC2YR",
        measurand="Mean corpuscular volume -- average red cell volume, Sysmex XN-series.",
        decimals=1,
        notes=(
            "An INDEX, not a severity measure. A low MCV points toward iron "
            "deficiency or thalassaemia and a high one toward B12/folate "
            "deficiency or alcohol; neither end is 'better'.",
        ),
    ),
    Spec(
        feature="mch",
        table_id="nhanes_2017_2018_mch",
        analyte_file="CBC_J.xpt",
        demo_file="DEMO_J.xpt",
        column="LBXMCHSI",
        unit="pg",
        cycle="2017-2018",
        cycle_label="NHANES 2017-2018 (cycle J)",
        analyte_label="LBXMCHSI - Mean cell hemoglobin (pg)",
        eligible_ages="examined participants aged 1 year and over",
        weight_variable="WTMEC2YR",
        measurand="Mean corpuscular haemoglobin -- average haemoglobin mass per red cell.",
        decimals=1,
        notes=("An index derived from haemoglobin and red cell count.",),
    ),
    Spec(
        feature="mchc",
        table_id="nhanes_2017_2018_mchc",
        analyte_file="CBC_J.xpt",
        demo_file="DEMO_J.xpt",
        column="LBXMC",
        unit="g/dl",
        cycle="2017-2018",
        cycle_label="NHANES 2017-2018 (cycle J)",
        analyte_label="LBXMC - Mean Cell Hgb Conc. (g/dL)",
        eligible_ages="examined participants aged 1 year and over",
        weight_variable="WTMEC2YR",
        measurand=(
            "Mean corpuscular haemoglobin CONCENTRATION. NHANES reports it in "
            "g/dL; some reports print the same quantity as `%`. "
            "backend/src/services/unitEquivalence.js records that equivalence "
            "and the assumptions it rests on."
        ),
        decimals=1,
        notes=(
            "A raised MCHC is more often a measurement artefact (lipaemia, "
            "haemolysis, cold agglutinins) than a physiological finding.",
        ),
    ),
    Spec(
        feature="wbc_count",
        table_id="nhanes_2017_2018_wbc_count",
        analyte_file="CBC_J.xpt",
        demo_file="DEMO_J.xpt",
        column="LBXWBCSI",
        unit="10^3/ul",
        cycle="2017-2018",
        cycle_label="NHANES 2017-2018 (cycle J)",
        analyte_label="LBXWBCSI - White blood cell count (1000 cells/uL)",
        eligible_ages="examined participants aged 1 year and over",
        weight_variable="WTMEC2YR",
        measurand="Total white blood cell count, Sysmex XN-series.",
        decimals=1,
        notes=(
            "Harmful at both extremes: low counts raise infection risk, high "
            "counts accompany infection, inflammation and haematological "
            "disease. The analytic sample includes participants with both.",
        ),
    ),
    Spec(
        feature="neutrophils",
        table_id="nhanes_2017_2018_neutrophils",
        analyte_file="CBC_J.xpt",
        demo_file="DEMO_J.xpt",
        column="LBXNEPCT",
        unit="%",
        cycle="2017-2018",
        cycle_label="NHANES 2017-2018 (cycle J)",
        analyte_label="LBXNEPCT - Segmented neutrophils percent (%)",
        eligible_ages="examined participants aged 1 year and over",
        weight_variable="WTMEC2YR",
        measurand=(
            "Segmented neutrophils as a PERCENTAGE of the white cell count. "
            "The percentage, not the absolute count, because that is what the "
            "reports print."
        ),
        decimals=1,
        notes=(
            "A PROPORTION of a total. It can move because neutrophils changed "
            "or because another population did, so a percentile on it is not "
            "a statement about neutrophil numbers.",
        ),
    ),
    Spec(
        feature="lymphocytes",
        table_id="nhanes_2017_2018_lymphocytes",
        analyte_file="CBC_J.xpt",
        demo_file="DEMO_J.xpt",
        column="LBXLYPCT",
        unit="%",
        cycle="2017-2018",
        cycle_label="NHANES 2017-2018 (cycle J)",
        analyte_label="LBXLYPCT - Lymphocyte percent (%)",
        eligible_ages="examined participants aged 1 year and over",
        weight_variable="WTMEC2YR",
        measurand="Lymphocytes as a PERCENTAGE of the white cell count.",
        decimals=1,
        notes=("A proportion of a total; see the neutrophil note.",),
    ),
    Spec(
        feature="monocytes",
        table_id="nhanes_2017_2018_monocytes",
        analyte_file="CBC_J.xpt",
        demo_file="DEMO_J.xpt",
        column="LBXMOPCT",
        unit="%",
        cycle="2017-2018",
        cycle_label="NHANES 2017-2018 (cycle J)",
        analyte_label="LBXMOPCT - Monocyte percent (%)",
        eligible_ages="examined participants aged 1 year and over",
        weight_variable="WTMEC2YR",
        measurand="Monocytes as a PERCENTAGE of the white cell count.",
        decimals=1,
        notes=("A proportion of a total; see the neutrophil note.",),
    ),
    Spec(
        feature="eosinophils",
        table_id="nhanes_2017_2018_eosinophils",
        analyte_file="CBC_J.xpt",
        demo_file="DEMO_J.xpt",
        column="LBXEOPCT",
        unit="%",
        cycle="2017-2018",
        cycle_label="NHANES 2017-2018 (cycle J)",
        analyte_label="LBXEOPCT - Eosinophils percent (%)",
        eligible_ages="examined participants aged 1 year and over",
        weight_variable="WTMEC2YR",
        measurand="Eosinophils as a PERCENTAGE of the white cell count.",
        decimals=1,
        notes=(
            "A proportion of a total; see the neutrophil note.",
            "Strongly right-skewed and seasonal (allergy, parasitic "
            "exposure), so the upper percentiles are wide.",
        ),
    ),
    Spec(
        feature="basophils",
        table_id="nhanes_2017_2018_basophils",
        analyte_file="CBC_J.xpt",
        demo_file="DEMO_J.xpt",
        column="LBXBAPCT",
        unit="%",
        cycle="2017-2018",
        cycle_label="NHANES 2017-2018 (cycle J)",
        analyte_label="LBXBAPCT - Basophils percent (%)",
        eligible_ages="examined participants aged 1 year and over",
        weight_variable="WTMEC2YR",
        measurand="Basophils as a PERCENTAGE of the white cell count.",
        decimals=1,
        notes=(
            "A proportion of a total; see the neutrophil note.",
            "⚠ REPORTED TO ONE DECIMAL PLACE ON A RANGE OF ROUGHLY 0-2 %. "
            "Adjacent percentiles on the published grid can therefore be the "
            "SAME printed number, and the service brackets between grid "
            "points rather than interpolating, which is the right behaviour "
            "here.",
        ),
    ),
    Spec(
        feature="platelet_count",
        table_id="nhanes_2017_2018_platelet_count",
        analyte_file="CBC_J.xpt",
        demo_file="DEMO_J.xpt",
        column="LBXPLTSI",
        unit="10^3/ul",
        cycle="2017-2018",
        cycle_label="NHANES 2017-2018 (cycle J)",
        analyte_label="LBXPLTSI - Platelet count (1000 cells/uL)",
        eligible_ages="examined participants aged 1 year and over",
        weight_variable="WTMEC2YR",
        measurand="Platelet count, Sysmex XN-series automated analyser.",
        decimals=0,
        notes=(
            "Harmful at both extremes: a low count raises bleeding risk and a "
            "high one accompanies thrombocytosis. No direction of harm is "
            "declared.",
        ),
    ),
)


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
            urllib.request.urlretrieve(meta["url"], target)
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
