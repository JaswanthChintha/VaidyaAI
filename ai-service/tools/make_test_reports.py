from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymupdf

HERE = Path(__file__).resolve().parent
SERVICE_ROOT = HERE.parent
OUT_DIR = SERVICE_ROOT.parent / "backend" / "storage" / "samples" / "generated"

LAB_NAME = "MERIDIAN DIAGNOSTICS (SPECIMEN)"
LAB_LINE = "Plot 14, Sector 9 · Test City 500081 · NOT AN ACCREDITED LABORATORY"
SYNTHETIC_BANNER = (
    "SYNTHETIC TEST DOCUMENT — GENERATED DATA, NOT A REAL PATIENT RECORD"
)

Row = Tuple[str, str, str]

UnassessedRow = Tuple[str, str, str, str, str]


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
        unassessed: Optional[List[UnassessedRow]] = None,
        expect_described: Optional[List[str]] = None,
        prose: Optional[List[Tuple[str, str]]] = None,
        paired_with: Optional[str] = None,
    ) -> None:
        self.slug = slug
        self.title = title
        self.patient = patient
        self.age = age
        self.sex = sex
        self.rows = rows
        self.features = features
        self.expect = expect
        self.note = note
        self.unassessed = list(unassessed or [])
        self.expect_described = list(expect_described or [])
        self.prose = list(prose or [])
        self.paired_with = paired_with


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
            "Diabetes": "Borderline",
            "High Cholesterol": "Borderline",
            "High Triglycerides": "Borderline",
            "Vitamin D Deficiency": "Borderline",
            "Vitamin B12 Deficiency": "Borderline",
            "Kidney Disease": "Not Indicated",
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
    Report(
        slug="06-lab-flagged-tests-we-do-not-assess",
        title="Lipid and Renal Panel (extended)",
        patient="Devendra Bhatt",
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
        unassessed=[
            ("LDL Cholesterol, Direct", "160", "mg/dL", "< 100", "H"),
            ("HDL Cholesterol", "44", "mg/dL", "> 40", ""),
            ("Blood Urea", "53", "mg/dL", "15 - 40", "H"),
            ("Potassium, Serum", "5.2", "mmol/L", "3.5 - 5.1", "H"),
        ],
        expect_described=[
            "LDL Cholesterol, Direct",
            "Blood Urea",
            "Potassium, Serum",
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
        note="THE FIXTURE FOR THE UNASSESSED SECTION. 02's assessed panel plus "
        "four tests this platform has no feature for, three of them marked "
        "abnormal BY THE LABORATORY. Blood urea and potassium are raised while "
        "creatinine -- the only renal marker that IS assessed -- is normal, so "
        "the dashboard must show the laboratory's markings without claiming to "
        "have assessed them, and must not let them change any verdict. The "
        "three flagged rows must each carry a plain-language description of "
        "what the test measures; the in-range HDL row must carry none.",
    ),
    Report(
        slug="07-prose-abnormal",
        title="Consultation Note — Metabolic and Lipid Review",
        patient="Rakesh Menon",
        age=58,
        sex="male",
        paired_with="02-diabetes-and-lipids",
        rows=[
            ("Glycosylated Haemoglobin", "8.4", "%"),
            ("Fasting Blood Sugar", "186", "mg/dL"),
            ("Total Cholesterol", "268", "mg/dL"),
            ("Triglycerides", "320", "mg/dL"),
            ("Serum Creatinine", "1.1", "mg/dL"),
            ("Haemoglobin", "14.8", "g/dL"),
            ("Vitamin D (25-Hydroxy)", "34", "ng/mL"),
            ("Vitamin B-12", "420", "pg/mL"),
        ],
        prose=[
            (
                "Reason for review",
                "Mr Menon attended for a fasting metabolic and lipid review "
                "following an earlier abnormal screening result. He reports no "
                "new symptoms. The sample was drawn after a twelve-hour fast "
                "and processed the same morning.",
            ),
            (
                "Glycaemic indices",
                "Glycaemic control remains the principal concern. Glycosylated "
                "haemoglobin measured 8.4 % on this specimen, and the fasting "
                "blood sugar taken from the same draw was 186 mg/dL. Both were "
                "repeated on the analyser and agreed to within the usual "
                "coefficient of variation.",
            ),
            (
                "Lipid profile",
                "The lipid picture is likewise unfavourable. Total cholesterol "
                "returned at 268 mg/dL, with triglycerides of 320 mg/dL. The "
                "specimen was lipaemic on inspection, which is consistent with "
                "the triglyceride result and does not appear to have interfered "
                "with the other assays on the panel.",
            ),
            (
                "Renal and haematological indices",
                "Renal function was unremarkable on this occasion: serum "
                "creatinine measured 1.1 mg/dL. The full blood count was within "
                "the laboratory's usual expectations, with a haemoglobin of "
                "14.8 g/dL and no abnormal cells reported on the film.",
            ),
            (
                "Micronutrient status",
                "Vitamin D (25-hydroxy) was 34 ng/mL and vitamin B-12 was "
                "420 pg/mL. Neither was repeated. No further micronutrient "
                "assays were requested on this sample.",
            ),
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
        note="PROSE, NOT A TABLE. 02's values written into a consultation "
        "note, with each result stated inside a sentence. Verdicts MUST be "
        "identical to 02; any difference is an extraction failure on narrative "
        "text, not a clinical one. A value that is not extracted becomes 'not "
        "measured' on the dashboard, which is indistinguishable from a test "
        "the report never contained.",
    ),
    Report(
        slug="08-prose-all-normal",
        title="Health Check Summary — Narrative Report",
        patient="Aarti Deshpande",
        age=34,
        sex="female",
        paired_with="01-all-normal",
        rows=[
            ("Glycated Haemoglobin", "5.2", "%"),
            ("Fasting Glucose", "88", "mg/dL"),
            ("Haemoglobin", "13.6", "g/dL"),
            ("Serum Creatinine", "0.8", "mg/dL"),
            ("Total Cholesterol", "172", "mg/dL"),
            ("Triglycerides", "118", "mg/dL"),
            ("Vitamin D (25-OH)", "42", "ng/mL"),
            ("Vitamin B12", "512", "pg/mL"),
        ],
        prose=[
            (
                "Summary",
                "Ms Deshpande attended for a routine health check. She is well, "
                "takes nothing regularly, and reports no symptoms. The results "
                "below are given in the body of this note rather than as a "
                "table, as is this laboratory's practice for screening panels.",
            ),
            (
                "Glycaemic indices",
                "Glycated haemoglobin was 5.2 % and the fasting glucose was "
                "88 mg/dL. There is nothing in either figure to suggest a "
                "disturbance of glucose handling at this time.",
            ),
            (
                "Haematology and renal function",
                "Haemoglobin measured 13.6 g/dL. Serum creatinine was "
                "0.8 mg/dL, which is comfortably within what this laboratory "
                "expects for a woman of this age.",
            ),
            (
                "Lipids",
                "Total cholesterol was 172 mg/dL and triglycerides 118 mg/dL. "
                "The specimen was clear and was not lipaemic.",
            ),
            (
                "Micronutrients",
                "Vitamin D (25-OH) was 42 ng/mL and vitamin B12 was 512 pg/mL. "
                "No supplementation was reported at the time of the draw.",
            ),
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
        note="PROSE, AND NOTHING MAY FLAG. 01's values written into a "
        "narrative note. Verdicts MUST be identical to 01. This is the case "
        "07 cannot cover: a number misread out of a sentence, or picked up "
        "from the surrounding words, would invent a condition in a healthy "
        "person -- and a fixture that is expected to flag would never show it.",
    ),
]


W, H = 595, 842
LEFT, RIGHT = 44, W - 44


def _line(page, y: float, colour=(0.72, 0.75, 0.79), width=0.7) -> None:
    page.draw_line((LEFT, y), (RIGHT, y), color=colour, width=width)


def _finish(doc, page, report: Report, text) -> None:
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


def _save(doc, report: Report) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{report.slug}.pdf"
    doc.save(str(path))
    doc.close()
    return path


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

    if report.prose:
        for heading, paragraph in report.prose:
            text(LEFT, y, heading.upper(), size=8.2, bold=True,
                 colour=(0.35, 0.39, 0.45))
            y += 12
            box = pymupdf.Rect(LEFT, y - 9, RIGHT, y + 150)
            used = page.insert_textbox(
                box, paragraph, fontsize=9.6, fontname="helv",
                color=(0.1, 0.12, 0.15), lineheight=1.45, align=0,
            )
            if used < 0:
                raise SystemExit(
                    f"{report.slug}: paragraph {heading!r} does not fit on the "
                    "page. Shorten it rather than letting it clip -- a clipped "
                    "paragraph silently removes a value from the fixture."
                )
            y += (box.height - used) - 9 + 12

        y += 6
        text(LEFT, y, "— END OF REPORT —", size=8.4, bold=True,
             colour=(0.35, 0.39, 0.45))
        y += 26
        text(LEFT, y, "Dr. B. Fictional, MD (Pathology)", size=8.4, bold=True)
        y += 11
        text(LEFT, y, "Consultant Pathologist · Reg. No. SPECIMEN-0000", size=7.8,
             colour=(0.45, 0.49, 0.55))
        _finish(doc, page, report, text)
        return _save(doc, report)

    cols = (
        (LEFT, LEFT + 230, LEFT + 300, LEFT + 380, LEFT + 470)
        if report.unassessed
        else (LEFT, LEFT + 280, LEFT + 390, 0, 0)
    )
    text(cols[0], y, "TEST", size=7.8, bold=True, colour=(0.35, 0.39, 0.45))
    text(cols[1], y, "RESULT", size=7.8, bold=True, colour=(0.35, 0.39, 0.45))
    text(cols[2], y, "UNITS", size=7.8, bold=True, colour=(0.35, 0.39, 0.45))
    if report.unassessed:
        text(cols[3], y, "REF. INTERVAL", size=7.8, bold=True,
             colour=(0.35, 0.39, 0.45))
        text(cols[4], y, "FLAG", size=7.8, bold=True, colour=(0.35, 0.39, 0.45))
    y += 6
    _line(page, y, colour=(0.35, 0.39, 0.45), width=0.9)
    y += 16

    def _row(name, value, unit, interval="", flag=""):
        nonlocal y
        text(cols[0], y, name, size=9.4)
        text(cols[1], y, value, size=9.4, bold=True)
        text(cols[2], y, unit, size=9.4)
        if interval:
            text(cols[3], y, interval, size=9.0, colour=(0.35, 0.39, 0.45))
        if flag:
            text(cols[4], y, flag, size=9.4, bold=True, colour=(0.65, 0.12, 0.12))
        y += 11
        _line(page, y - 3, colour=(0.90, 0.92, 0.94), width=0.5)
        y += 8

    for name, value, unit in report.rows:
        _row(name, value, unit)

    for name, value, unit, interval, flag in report.unassessed:
        _row(name, value, unit, interval, flag)

    y += 8
    text(LEFT, y, "— END OF REPORT —", size=8.4, bold=True,
         colour=(0.35, 0.39, 0.45))
    y += 26
    text(LEFT, y, "Dr. B. Fictional, MD (Pathology)", size=8.4, bold=True)
    y += 11
    text(LEFT, y, "Consultant Pathologist · Reg. No. SPECIMEN-0000", size=7.8,
         colour=(0.45, 0.49, 0.55))

    _finish(doc, page, report, text)
    return _save(doc, report)


def engine_verdicts(report: Report) -> Tuple[Dict[str, str], List[str]]:
    from app.services.feature_engineer import engineer_features
    from app.services.rule_engine import evaluate_rules

    parameters = [
        {
            "test_name": printed_name,
            "value_raw": printed_value,
            "value_numeric": float(printed_value),
            "unit": printed_unit,
            "reference_range_raw": None,
            "page_number": 1,
            "confidence": 0.99,
        }
        for printed_name, printed_value, printed_unit in report.rows
    ]
    parameters += [
        {
            "test_name": printed_name,
            "value_raw": printed_value,
            "value_numeric": float(printed_value),
            "unit": printed_unit,
            "reference_range_raw": printed_interval or None,
            "flag": {"H": "high", "L": "low"}.get(printed_flag),
            "page_number": 1,
            "confidence": 0.99,
        }
        for printed_name, printed_value, printed_unit, printed_interval, printed_flag
        in report.unassessed
    ]
    profile = {"age": report.age, "gender": report.sex}

    engineered = engineer_features(parameters, profile)
    decisions = evaluate_rules(engineered=engineered)

    rank = {"Indicated": 3, "Borderline": 2, "Not Indicated": 1}
    out: Dict[str, str] = {}
    for decision in getattr(decisions, "decisions", decisions):
        status = getattr(decision.status, "value", decision.status)
        condition = decision.condition
        if rank.get(status, 0) >= rank.get(out.get(condition, ""), 0):
            out[condition] = status

    skipped = [
        name for name in (
            getattr(item, "test_name", None) for item in engineered.unmapped
        ) if isinstance(name, str) and name
    ]
    return out, skipped


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
        actual, skipped = engine_verdicts(report)

        mismatches = {
            condition: {"expected": expected, "engine_said": actual.get(condition)}
            for condition, expected in report.expect.items()
            if actual.get(condition) != expected
        }
        if mismatches:
            failures.append(f"{report.slug}: {mismatches}")

        if report.prose:
            body = " ".join(paragraph for _heading, paragraph in report.prose)
            for name, value, unit in report.rows:
                if value not in body:
                    failures.append(
                        f"{report.slug}: {name} = {value} {unit} is in `rows` "
                        "but does not appear in the prose. The page and the "
                        "expectation have drifted apart."
                    )

        not_skipped = [
            name for name, _v, _u, _i, _f in report.unassessed if name not in skipped
        ]
        if not_skipped:
            failures.append(
                f"{report.slug}: the engine ASSESSED {not_skipped}, which this "
                "fixture carries as unassessed rows"
            )

        entry = {
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
            "layout": "prose" if report.prose else "table",
            "expect": report.expect,
        }
        if report.paired_with:
            entry["paired_with"] = report.paired_with
            entry["pairing_rule"] = (
                "Same values as the paired fixture, different layout only. "
                "Verdicts MUST be identical to it; any difference is an "
                "extraction defect and cannot be a clinical one."
            )
        if report.unassessed:
            entry["unassessed_tests"] = {
                name: {
                    "printed": f"{value} {unit}",
                    "reference_interval_printed": interval or None,
                    "laboratory_flag": {"H": "high", "L": "low"}.get(flag),
                }
                for name, value, unit, interval, flag in report.unassessed
            }
            entry["expect_unassessed"] = (
                "Listed under 'Also on your report, but not assessed here'. The "
                "laboratory's own flag and range are shown and attributed to "
                "the laboratory; NO condition, risk or verdict may be derived "
                "from any of them."
            )
            entry["expect_described"] = report.expect_described
        manifest["reports"].append(entry)
        flag = "MISMATCH" if mismatches else "ok"
        extra = (
            f" + {len(report.unassessed)} unassessed" if report.unassessed else ""
        )
        extra += "  [prose]" if report.prose else ""

        print(
            f"  {path.name:40s} {len(report.rows)} tests{extra}  "
            f"engine agrees: {flag}"
        )

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
