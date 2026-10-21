from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

POLARITY_HIGHER_IS_WORSE = "higher_is_worse"
POLARITY_HIGHER_IS_BETTER = "higher_is_better"
POLARITY_BEST_WITHIN_RANGE = "best_within_range"

_READ_ON = "2026-09-19"


def _eflm(analyte: str, page: int, median: float, low: float, high: float) -> str:
    return (
        f"EFLM Biological Variation Database, meta-analysis for {analyte}: "
        f"CVi median {median} % (CI {low}-{high} %). "
        f"biologicalvariation.eu/meta_by_analyte/{page}, read {_READ_ON} and "
        f"NOT YET CONFIRMED against that page by a human. "
        f"CVa IS NOT FROM THIS SOURCE -- EFLM publishes no analytical CV."
    )

_WORD = re.compile(r"[a-z0-9]+")


def fold(name: object) -> str:
    return " ".join(sorted(_WORD.findall(str(name or "").lower())))


@dataclass(frozen=True)
class LabVariation:

    test: str
    polarity: str
    analytical_cv_pct: float
    within_subject_cv_pct: float
    source: str
    verified: bool = False
    aliases: Tuple[str, ...] = field(default_factory=tuple)


TABLE: Tuple[LabVariation, ...] = (
    LabVariation(
        test="c_reactive_protein",
        polarity=POLARITY_HIGHER_IS_WORSE,
        analytical_cv_pct=5.0,
        within_subject_cv_pct=34.7,
        source=_eflm("C-reactive protein (CRP)", 1635, 34.7, 29.4, 74.4),
        aliases=("CRP", "C-REACTIVE PROTEIN", "C-REACTIVE PROTEIN(CRP)", "CRP (C-REACTIVE PROTEIN)"),
    ),
    LabVariation(
        test="esr",
        polarity=POLARITY_HIGHER_IS_WORSE,
        analytical_cv_pct=10.0,
        within_subject_cv_pct=20.2,
        source=(
            "NO SOURCE. The EFLM Biological Variation Database has NO ENTRY "
            "for ESR -- searched 2026-09-19 for both `ESR` and "
            "`sedimentation`, no result. The figures here are "
            "literature-typical and cite nothing. Published work reports "
            "sex-specific variances (Scand J Clin Lab Invest 1996;56:191-8), "
            "not one CV, and the analytical CV varies with the value itself, "
            "so a single percentage threshold for ESR is questionable in "
            "principle. THIS IS THE ROW TO SETTLE FIRST."
        ),
        aliases=("ESR", "ERYTHROCYTE SEDIMENTATION RATE"),
    ),
    LabVariation(
        test="haemoglobin_a_note",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=1.5,
        within_subject_cv_pct=2.8,
        source=_eflm("Haematocrit (Hct)", 1524, 2.8, 2.2, 3.1),
        aliases=("PCV", "HCT", "HAEMATOCRIT", "HEMATOCRIT", "PACKED CELL VOLUME"),
    ),
    LabVariation(
        test="mcv",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=1.0,
        within_subject_cv_pct=0.8,
        source=_eflm("Mean corpuscular volume (MCV)", 1527, 0.8, 0.7, 1.1),
        aliases=("MCV", "MEAN CORPUSCULAR VOLUME", "MEAN CELL VOLUME"),
    ),
    LabVariation(
        test="mch",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=1.0,
        within_subject_cv_pct=0.8,
        source=_eflm("Mean corpuscular haemoglobin (MCH)", 1525, 0.8, 0.3, 1.7),
        aliases=("MCH", "MEAN CORPUSCULAR HAEMOGLOBIN", "MEAN CORPUSCULAR HEMOGLOBIN"),
    ),
    LabVariation(
        test="mchc",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=1.0,
        within_subject_cv_pct=1.0,
        source=_eflm(
            "Mean corpuscular haemoglobin concentration (MCHC)", 1526, 1.0, 0.8, 1.0
        ),
        aliases=("MCHC", "MEAN CORPUSCULAR HAEMOGLOBIN CONCENTRATION"),
    ),
    LabVariation(
        test="platelet_count",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=4.0,
        within_subject_cv_pct=7.3,
        source=_eflm("Thrombocytes", 1538, 7.3, 6.6, 10.2),
        aliases=("PLATELET COUNT", "PLATELETS", "PLT"),
    ),
    LabVariation(
        test="rbc_count",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=1.5,
        within_subject_cv_pct=2.6,
        source=_eflm("Erythrocytes", 1523, 2.6, 1.4, 4.0),
        aliases=("RBC COUNT", "T.RBC", "TOTAL RBC COUNT", "RBC", "ERYTHROCYTE COUNT"),
    ),
    LabVariation(
        test="wbc_count",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=3.0,
        within_subject_cv_pct=11.1,
        source=_eflm("Leukocytes", 1532, 11.1, 8.1, 12.8),
        aliases=("WBC COUNT", "TOTAL WBC COUNT", "WBC", "TLC", "LEUCOCYTE COUNT"),
    ),
    LabVariation(
        test="neutrophils",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=4.0,
        within_subject_cv_pct=12.5,
        source=_eflm("Neutrophils", 1533, 12.5, 6.3, 26.9),
        aliases=("NEUTROPHILS", "POLYMORPHS", "POLYMORPHONUCLEAR CELLS"),
    ),
    LabVariation(
        test="lymphocytes",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        within_subject_cv_pct=10.5,
        analytical_cv_pct=3.0,
        source=_eflm("Lymphocytes", 1534, 10.5, 9.8, 14.7),
        aliases=("LYMPHOCYTES", "LYMPHS"),
    ),
    LabVariation(
        test="monocytes",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=5.0,
        within_subject_cv_pct=14.0,
        source=_eflm("Monocytes", 1535, 14.0, 11.1, 19.3),
        aliases=("MONOCYTES",),
    ),
    LabVariation(
        test="eosinophils",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=5.0,
        within_subject_cv_pct=15.1,
        source=_eflm("Eosinophils", 1536, 15.1, 10.1, 26.9),
        aliases=("EOSINOPHILS", "EOS"),
    ),
    LabVariation(
        test="basophils",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=10.0,
        within_subject_cv_pct=12.6,
        source=_eflm("Basophils", 1537, 12.6, 11.4, 32.0),
        aliases=("BASOPHILS", "BASO"),
    ),
    LabVariation(
        test="tsh",
        polarity=POLARITY_BEST_WITHIN_RANGE,
        analytical_cv_pct=5.0,
        within_subject_cv_pct=17.8,
        source=_eflm("Thyroid stimulating hormone (TSH)", 1065, 17.8, 12.0, 29.3),
        aliases=(
            "TSH",
            "TSH (THYROID STIMULATING HORMONE)",
            "TSH (THYROID STIM HORMONE)",
            "THYROID STIMULATING HORMONE",
        ),
    ),
    LabVariation(
        test="alanine_aminotransferase",
        polarity=POLARITY_HIGHER_IS_WORSE,
        analytical_cv_pct=5.0,
        within_subject_cv_pct=12.6,
        source=_eflm("Alanine transaminase (ALT)", 1495, 12.6, 9.3, 17.3),
        aliases=("SGPT", "ALT", "SGPT (ALT)", "ALANINE AMINOTRANSFERASE"),
    ),
)


def _build_index() -> Dict[str, LabVariation]:
    index: Dict[str, LabVariation] = {}
    for entry in TABLE:
        for alias in entry.aliases:
            key = fold(alias)
            if not key:
                continue
            index.setdefault(key, entry)
    return index


_INDEX: Dict[str, LabVariation] = _build_index()


_METHOD_WORDS = frozenset(
    {
        "westgard",
        "westergren",
        "photometric",
        "spectrophotometric",
        "colorimetric",
        "immunoturbidimetric",
        "immunoturbidometric",
        "turbidimetric",
        "nephelometric",
        "hplc",
        "elisa",
        "clia",
        "eclia",
        "cmia",
        "chemiluminescence",
        "enzymatic",
        "impedance",
        "cytometry",
    }
)


def _without_method(name: object) -> str:
    words = [w for w in _WORD.findall(str(name or "").lower()) if w not in _METHOD_WORDS]
    return " ".join(sorted(words))


def variation_for(test_name: object) -> Optional[LabVariation]:
    row = _INDEX.get(fold(test_name))
    if row is not None:
        return row
    stripped = _without_method(test_name)
    if not stripped:
        return None
    return _INDEX.get(stripped)


def duplicate_aliases() -> Tuple[str, ...]:
    seen: Dict[str, str] = {}
    clashes = []
    for entry in TABLE:
        for alias in entry.aliases:
            key = fold(alias)
            if key in seen and seen[key] != entry.test:
                clashes.append(key)
            seen.setdefault(key, entry.test)
    return tuple(sorted(set(clashes)))
