"""Generate realistic one-page lab-report PDFs with KNOWN expected outcomes.

WHY THIS EXISTS. Uploading a real report tells you the app did not crash. It
does not tell you the app was RIGHT, because nobody knows what the answer
should have been. These fixtures carry their answer with them: every value is
chosen against the thresholds in `app/data/clinical_rules.py`, and the expected
status for each condition is written out by hand next to it.

THE HAND-WRITTEN EXPECTATION IS THE POINT. This script also runs the same
values through the real rule engine and REFUSES TO GENERATE if the two
disagree. That makes the fixtures useful in both directions:

  * if the engine changes behaviour, generation fails and you find out here;
  * if extraction misreads a PDF, the end-to-end result stops matching the
    expectation file and you find out there.

Deriving the expectations from the engine instead would have been easier and
worthless -- a fixture that agrees with the code by construction cannot catch
the code being wrong.

EVERY DOCUMENT IS MARKED SYNTHETIC, on the page and in its metadata. These are
test fixtures, not medical records; the laboratory, the patients, the doctors
and the identifiers are all invented. Nothing here describes a real person.

    python tools/make_test_reports.py

Writes PDFs and `expected.json` to `backend/storage/samples/generated/`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pymupdf

HERE = Path(__file__).resolve().parent
SERVICE_ROOT = HERE.parent
OUT_DIR = SERVICE_ROOT.parent / "backend" / "storage" / "samples" / "generated"

LAB_NAME = "MERIDIAN DIAGNOSTICS (SPECIMEN)"
LAB_LINE = "Plot 14, Sector 9 · Test City 500081 · NOT AN ACCREDITED LABORATORY"
SYNTHETIC_BANNER = (
    "SYNTHETIC TEST DOCUMENT — GENERATED DATA, NOT A REAL PATIENT RECORD"
)

#: One row of the printed table: (printed test name, value, printed unit).
#:
#: NO REFERENCE INTERVAL IS PRINTED, deliberately.
#:
#: Many real reports do print one, and when they do the pipeline reads it. But
#: a fixture that supplies the interval cannot tell you whether the verdict came
#: from the service's OWN clinical thresholds or was simply copied off the page.
#: Withholding it forces the rule engine to decide on its own authority, which
#: is the thing under test -- and it exercises the "no range printed" path that
#: real reports genuinely hit.
#:
#: The printed name is deliberately NOT the canonical feature key: matching a
#: lab's wording to a feature is Module 4's job and these fixtures exercise it.
Row = Tuple[str, str, str]


class Report:
    def __init__(
        self,
        slug: str,
        title: str,
        patient: str,
        age: int,
        sex: str,
        rows: List[Row],
        features: Dict[str, Tuple[float, str]],
        expect: Dict[str, str],
        note: str,
    ) -> None:
        self.slug = slug
        self.title = title
        self.patient = patient
        self.age = age
        self.sex = sex
        self.rows = rows
        #: canonical feature key -> (value, unit) AS PRINTED. Used for the
        #: engine cross-check; the pipeline gets these from OCR instead.
        self.features = features
        #: condition -> expected DecisionStatus value, written by hand.
        self.expect = expect
        self.note = note


REPORTS: List[Report] = [
    Report(
        slug="01-all-normal",
        title="Health Check Panel",
        patient="Aarti Deshpande",
        age=34,
        sex="female",
        rows=[
            ("Glycated Haemoglobin (HbA1c)", "5.2", "%"),
            ("Glucose, Fasting", "88", "mg/dL"),
            ("Haemoglobin", "13.6", "g/dL"),
            ("Creatinine, Serum", "0.8", "mg/dL"),
            ("Cholesterol, Total", "172", "mg/dL"),
            ("Triglycerides", "118", "mg/dL"),
            ("Vitamin D (25-OH)", "42", "ng/mL"),
            ("Vitamin B12", "512", "pg/mL"),
        ],
        features={
            "hba1c": (5.2, "%"),
            "blood_glucose": (88.0, "mg/dl"),
            "hemoglobin": (13.6, "g/dl"),
            "creatinine": (0.8, "mg/dl"),
            "cholesterol": (172.0, "mg/dl"),
            "triglycerides": (118.0, "mg/dl"),
            "vitamin_d": (42.0, "ng/ml"),
            "vitamin_b12": (512.0, "pg/ml"),
        },
        expect={
            "Diabetes": "Not Indicated",
            "Anemia": "Not Indicated",
            "Kidney Disease": "Not Indicated",
            "High Cholesterol": "Not Indicated",
            "High Triglycerides": "Not Indicated",
            "Vitamin D Deficiency": "Not Indicated",
            "Vitamin B12 Deficiency": "Not Indicated",
        },
        note="Everything comfortably in range. Nothing should flag. If this "
        "report produces a flagged condition, a threshold is inverted.",
    ),
    Report(
        slug="02-diabetes-and-lipids",
        title="Diabetic Profile with Lipids",
        patient="Rakesh Menon",
        age=58,
        sex="male",
        rows=[
            ("HbA1C (Glycosylated Haemoglobin)", "8.4", "%"),
            ("Fasting Blood Sugar", "186", "mg/dL"),
            ("Total Cholesterol", "268", "mg/dL"),
            ("Triglyceride", "320", "mg/dL"),
            ("Serum Creatinine", "1.1", "mg/dL"),
            ("Haemoglobin", "14.8", "g/dL"),
            ("25-Hydroxy Vitamin D", "34", "ng/mL"),
            ("Vitamin B-12 (Cyanocobalamin)", "420", "pg/mL"),
        ],
        features={
            "hba1c": (8.4, "%"),
            "blood_glucose": (186.0, "mg/dl"),
            "cholesterol": (268.0, "mg/dl"),
            "triglycerides": (320.0, "mg/dl"),
            "creatinine": (1.1, "mg/dl"),
            "hemoglobin": (14.8, "g/dl"),
            "vitamin_d": (34.0, "ng/ml"),
            "vitamin_b12": (420.0, "pg/ml"),
        },
        expect={
            "Diabetes": "Indicated",
            "High Cholesterol": "Indicated",
            "High Triglycerides": "Indicated",
            "Kidney Disease": "Not Indicated",
            "Anemia": "Not Indicated",
            "Vitamin D Deficiency": "Not Indicated",
            "Vitamin B12 Deficiency": "Not Indicated",
        },
        note="Three conditions must flag together. Also the paired case for "
        "05-si-units, which carries the SAME patient in SI units.",
    ),
    Report(
        slug="03-renal-anaemia-deficiency",
        title="Renal and Nutritional Panel",
        patient="Suresh Iyer",
        age=63,
        sex="male",
        rows=[
            ("Serum Creatinine", "2.4", "mg/dL"),
            ("Haemoglobin", "9.2", "g/dL"),
            ("Vitamin D, 25-Hydroxy", "12", "ng/mL"),
            ("Vitamin B12", "140", "pg/mL"),
            ("HbA1c", "5.4", "%"),
            ("Glucose, Fasting", "92", "mg/dL"),
            ("Cholesterol, Total", "186", "mg/dL"),
            ("Triglycerides", "132", "mg/dL"),
        ],
        features={
            "creatinine": (2.4, "mg/dl"),
            "hemoglobin": (9.2, "g/dl"),
            "vitamin_d": (12.0, "ng/ml"),
            "vitamin_b12": (140.0, "pg/ml"),
            "hba1c": (5.4, "%"),
            "blood_glucose": (92.0, "mg/dl"),
            "cholesterol": (186.0, "mg/dl"),
            "triglycerides": (132.0, "mg/dl"),
        },
        expect={
            "Kidney Disease": "Indicated",
            "Anemia": "Indicated",
            "Vitamin D Deficiency": "Indicated",
            "Vitamin B12 Deficiency": "Indicated",
            "Diabetes": "Not Indicated",
            "High Cholesterol": "Not Indicated",
            "High Triglycerides": "Not Indicated",
        },
        note="Four flags at once, and the metabolic panel must stay quiet. "
        "Tests that one abnormal system does not colour the others.",
    ),
    Report(
        slug="04-exactly-on-the-boundary",
        title="Routine Screen",
        patient="Vikram Rao",
        age=45,
        sex="male",
        rows=[
            ("HbA1c", "5.7", "%"),
            ("Glucose, Fasting", "100", "mg/dL"),
            ("Cholesterol, Total", "200", "mg/dL"),
            ("Triglycerides", "150", "mg/dL"),
            ("Vitamin D (25-OH)", "29", "ng/mL"),
            ("Vitamin B12", "250", "pg/mL"),
            ("Serum Creatinine", "1.35", "mg/dL"),
            ("Haemoglobin", "13.0", "g/dL"),
        ],
        features={
            "hba1c": (5.7, "%"),
            "blood_glucose": (100.0, "mg/dl"),
            "cholesterol": (200.0, "mg/dl"),
            "triglycerides": (150.0, "mg/dl"),
            "vitamin_d": (29.0, "ng/ml"),
            "vitamin_b12": (250.0, "pg/ml"),
            "creatinine": (1.35, "mg/dl"),
            "hemoglobin": (13.0, "g/dl"),
        },
        expect={
            # `>=` bands: the value sits exactly ON the boundary and MUST fire.
            "Diabetes": "Borderline",
            "High Cholesterol": "Borderline",
            "High Triglycerides": "Borderline",
            # `<` bands: 29 < 30 and 250 < 300, so both are borderline.
            "Vitamin D Deficiency": "Borderline",
            "Vitamin B12 Deficiency": "Borderline",
            # STRICT `>` for creatinine: 1.35 is NOT > 1.35, so this must stay
            # quiet. An off-by-one here would tell a healthy man his kidneys
            # are failing.
            "Kidney Disease": "Not Indicated",
            # STRICT `<` for anaemia: 13.0 is NOT < 13.0 (male cut-off).
            "Anemia": "Not Indicated",
        },
        note="THE MOST VALUABLE FIXTURE. Every value sits exactly on a "
        "threshold, so `>=` and `>` cannot be confused without this failing. "
        "Creatinine and haemoglobin must NOT flag; the rest must.",
    ),
    Report(
        slug="05-si-units",
        title="Diabetic Profile with Lipids (SI units)",
        patient="Rakesh Menon",
        age=58,
        sex="male",
        rows=[
            ("HbA1c (IFCC)", "68", "mmol/mol"),
            ("Glucose, Fasting", "10.3", "mmol/L"),
            ("Total Cholesterol", "6.94", "mmol/L"),
            ("Triglycerides", "3.62", "mmol/L"),
            ("Creatinine, Serum", "97", "umol/L"),
            ("Haemoglobin", "148", "g/L"),
            ("Vitamin D (25-OH)", "85", "nmol/L"),
            ("Vitamin B12", "310", "pmol/L"),
        ],
        features={
            "hba1c": (68.0, "mmol/mol"),
            "blood_glucose": (10.3, "mmol/l"),
            "cholesterol": (6.94, "mmol/l"),
            "triglycerides": (3.62, "mmol/l"),
            "creatinine": (97.0, "umol/l"),
            "hemoglobin": (148.0, "g/l"),
            "vitamin_d": (85.0, "nmol/l"),
            "vitamin_b12": (310.0, "pmol/l"),
        },
        expect={
            # THE SAME PATIENT AS 02, in the units a European lab would print.
            # Every verdict must match 02 exactly. If they differ, unit
            # conversion is wrong -- and MEMORY.md already records one
            # unit-handling defect that reached the patient-facing prompt.
            "Diabetes": "Indicated",
            "High Cholesterol": "Indicated",
            "High Triglycerides": "Indicated",
            "Kidney Disease": "Not Indicated",
            "Anemia": "Not Indicated",
            "Vitamin D Deficiency": "Not Indicated",
            "Vitamin B12 Deficiency": "Not Indicated",
        },
        note="Same values as 02 in SI units. Verdicts MUST be identical to 02; "
        "any difference is a unit-conversion defect.",
    ),
]


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

W, H = 595, 842  # A4 points
LEFT, RIGHT = 44, W - 44


def _line(page, y: float, colour=(0.72, 0.75, 0.79), width=0.7) -> None:
    page.draw_line((LEFT, y), (RIGHT, y), color=colour, width=width)


def render(report: Report) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=W, height=H)

    def text(x, y, s, size=9.2, bold=False, colour=(0.1, 0.12, 0.15)):
        page.insert_text(
            (x, y), s, fontsize=size,
            fontname="hebo" if bold else "helv", color=colour,
        )

    y = 52
    text(LEFT, y, LAB_NAME, size=15, bold=True, colour=(0.05, 0.25, 0.42))
    y += 14
    text(LEFT, y, LAB_LINE, size=7.6, colour=(0.42, 0.46, 0.52))
    y += 10
    text(LEFT, y, "Laboratory Investigation Report", size=7.6,
         colour=(0.42, 0.46, 0.52))

    # The synthetic marker stays -- these must never be mistakable for a real
    # record -- but it lives in the footer and the metadata rather than in a
    # banner across the top, so the page reads as a report.
    y += 14
    _line(page, y)
    y += 15

    left_col = [
        ("Patient Name", report.patient),
        ("Age / Sex", f"{report.age} Years / {report.sex.title()}"),
        ("Patient ID", f"SPEC-{report.slug.split('-')[0]}-0000"),
    ]
    right_col = [
        ("Referred By", "Dr. A. Specimen (not a real practitioner)"),
        ("Collected On", "05-Sep-2026 08:15"),
        ("Reported On", "05-Sep-2026 17:40"),
    ]
    start = y
    for label, value in left_col:
        text(LEFT, y, f"{label}", size=8, colour=(0.45, 0.49, 0.55))
        text(LEFT + 78, y, value, size=8.6, bold=True)
        y += 13
    y2 = start
    for label, value in right_col:
        text(LEFT + 290, y2, f"{label}", size=8, colour=(0.45, 0.49, 0.55))
        text(LEFT + 360, y2, value, size=8.6)
        y2 += 13

    y = max(y, y2) + 6
    _line(page, y)
    y += 18
    text(LEFT, y, report.title.upper(), size=10, bold=True,
         colour=(0.05, 0.25, 0.42))
    y += 16

    cols = (LEFT, LEFT + 280, LEFT + 390)
    text(cols[0], y, "TEST", size=7.8, bold=True, colour=(0.35, 0.39, 0.45))
    text(cols[1], y, "RESULT", size=7.8, bold=True, colour=(0.35, 0.39, 0.45))
    text(cols[2], y, "UNITS", size=7.8, bold=True, colour=(0.35, 0.39, 0.45))
    y += 6
    _line(page, y, colour=(0.35, 0.39, 0.45), width=0.9)
    y += 16

    for name, value, unit in report.rows:
        text(cols[0], y, name, size=9.4)
        text(cols[1], y, value, size=9.4, bold=True)
        text(cols[2], y, unit, size=9.4)
        y += 11
        _line(page, y - 3, colour=(0.90, 0.92, 0.94), width=0.5)
        y += 8

    y += 8
    text(LEFT, y, "— END OF REPORT —", size=8.4, bold=True,
         colour=(0.35, 0.39, 0.45))
    y += 26
    text(LEFT, y, "Dr. B. Fictional, MD (Pathology)", size=8.4, bold=True)
    y += 11
    text(LEFT, y, "Consultant Pathologist · Reg. No. SPECIMEN-0000", size=7.8,
         colour=(0.45, 0.49, 0.55))

    text(LEFT, H - 46,
         "Results relate only to the specimen tested. This is a generated "
         "document for software testing.",
         size=7.2, colour=(0.5, 0.54, 0.6))
    text(LEFT, H - 34, SYNTHETIC_BANNER, size=7.2, bold=True,
         colour=(0.65, 0.12, 0.12))

    doc.set_metadata({
        "title": f"{report.title} - SYNTHETIC TEST DOCUMENT",
        "author": "VaidyaAI test fixture generator",
        "subject": SYNTHETIC_BANNER,
        "keywords": "synthetic, test fixture, not a medical record",
    })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{report.slug}.pdf"
    doc.save(str(path))
    doc.close()
    return path


# --------------------------------------------------------------------------
# Cross-check: the hand-written expectation vs the real rule engine
# --------------------------------------------------------------------------


def engine_verdicts(report: Report) -> Dict[str, str]:
    """Run the shipped pipeline over this report's PRINTED rows.

    The rows are fed in as Module 4 extraction output -- printed test name,
    printed value, printed unit -- rather than as canonical features. That is
    deliberate: it exercises the synonym lookup and the unit conversion, which
    is exactly what fixture 05 exists to test. Handing the engine clean
    canonical keys would skip both.
    """
    from app.services.feature_engineer import engineer_features
    from app.services.rule_engine import evaluate_rules

    parameters = [
        {
            "test_name": printed_name,
            "value_raw": printed_value,
            "value_numeric": float(printed_value),
            "unit": printed_unit,
            # No reference interval: the page does not print one, so neither
            # does the extraction. The verdict must come from the service's own
            # thresholds.
            "reference_range_raw": None,
            "page_number": 1,
            "confidence": 0.99,
        }
        for printed_name, printed_value, printed_unit in report.rows
    ]
    profile = {"age": report.age, "gender": report.sex}

    engineered = engineer_features(parameters, profile)
    decisions = evaluate_rules(engineered=engineered)

    rank = {"Indicated": 3, "Borderline": 2, "Not Indicated": 1}
    out: Dict[str, str] = {}
    for decision in getattr(decisions, "decisions", decisions):
        status = getattr(decision.status, "value", decision.status)
        condition = decision.condition
        # Several rules can name one condition (HbA1c and glucose both say
        # Diabetes). The strongest verdict is the one the dashboard shows.
        if rank.get(status, 0) >= rank.get(out.get(condition, ""), 0):
            out[condition] = status
    return out


def main() -> int:
    manifest: Dict[str, Any] = {
        "generated_by": "ai-service/tools/make_test_reports.py",
        "warning": SYNTHETIC_BANNER,
        "how_to_use": (
            "Upload a PDF, run Analyse, then compare the dashboard's condition "
            "cards against `expect` below. Every value was chosen against the "
            "thresholds in app/data/clinical_rules.py."
        ),
        "reports": [],
    }

    failures: List[str] = []
    for report in REPORTS:
        path = render(report)
        actual = engine_verdicts(report)

        mismatches = {
            condition: {"expected": expected, "engine_said": actual.get(condition)}
            for condition, expected in report.expect.items()
            if actual.get(condition) != expected
        }
        if mismatches:
            failures.append(f"{report.slug}: {mismatches}")

        manifest["reports"].append({
            "file": path.name,
            "title": report.title,
            "patient": report.patient,
            "age": report.age,
            "sex": report.sex,
            "note": report.note,
            "printed_values": {
                name: f"{value} {unit}" for name, value, unit in report.rows
            },
            "reference_intervals_printed": False,
            "expect": report.expect,
        })
        flag = "MISMATCH" if mismatches else "ok"
        print(f"  {path.name:34s} {len(report.rows)} tests  engine agrees: {flag}")

    (OUT_DIR / "expected.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    if failures:
        print("\nTHE HAND-WRITTEN EXPECTATIONS AND THE ENGINE DISAGREE:")
        for line in failures:
            print("   " + line)
        print(
            "\nOne of the two is wrong. Do not 'fix' this by copying the "
            "engine's answer into `expect` -- that is how a fixture stops "
            "being able to catch anything."
        )
        return 1

    print(f"\n  wrote {len(REPORTS)} PDFs + expected.json to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(SERVICE_ROOT))
    raise SystemExit(main())
