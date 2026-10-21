from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.index import SIMILARITY_FLOOR, KnowledgeIndex
from app.rag.query import build_query


@dataclass(frozen=True)
class EvalQuery:
    label: str
    kind: str
    expect: Tuple[str, ...] = ()
    conditions: Tuple[str, ...] = ()
    features: Tuple[str, ...] = ()
    text: Optional[str] = None


EVAL_QUERIES: Tuple[EvalQuery, ...] = (
    EvalQuery(
        "spec example: Diabetes + HbA1c + glucose",
        "finding",
        conditions=("Diabetes",),
        features=("hba1c", "blood_glucose"),
        expect=("cond_diabetes", "lab_hba1c", "ref_hba1c_bands",
                "lab_blood_glucose", "ref_glucose_bands"),
    ),
    EvalQuery(
        "HbA1c alone",
        "finding",
        features=("hba1c",),
        expect=("lab_hba1c", "ref_hba1c_bands", "cond_diabetes"),
    ),
    EvalQuery(
        "Anemia + haemoglobin",
        "finding",
        conditions=("Anemia",),
        features=("hemoglobin",),
        expect=("cond_anemia", "lab_hemoglobin", "ref_hemoglobin_bands"),
    ),
    EvalQuery(
        "Kidney Disease + creatinine",
        "finding",
        conditions=("Kidney Disease",),
        features=("creatinine",),
        expect=("cond_kidney_disease", "lab_creatinine", "ref_creatinine_bands",
                "term_egfr"),
    ),
    EvalQuery(
        "Vitamin D Deficiency",
        "finding",
        conditions=("Vitamin D Deficiency",),
        features=("vitamin_d",),
        expect=("cond_vitamin_d_deficiency", "lab_vitamin_d",
                "ref_vitamin_d_bands", "life_vitamin_d_sources"),
    ),
    EvalQuery(
        "Vitamin B12 Deficiency",
        "finding",
        conditions=("Vitamin B12 Deficiency",),
        features=("vitamin_b12",),
        expect=("cond_vitamin_b12_deficiency", "lab_vitamin_b12",
                "ref_vitamin_b12_bands", "life_vitamin_b12_sources"),
    ),
    EvalQuery(
        "High Cholesterol + cholesterol",
        "finding",
        conditions=("High Cholesterol",),
        features=("cholesterol",),
        expect=("cond_high_cholesterol", "lab_cholesterol",
                "ref_cholesterol_bands", "term_ldl_hdl"),
    ),
    EvalQuery(
        "High Triglycerides",
        "finding",
        conditions=("High Triglycerides",),
        features=("triglycerides",),
        expect=("cond_high_triglycerides", "lab_triglycerides",
                "ref_triglycerides_bands"),
    ),
    EvalQuery(
        "Obesity + BMI",
        "finding",
        conditions=("Obesity",),
        features=("bmi",),
        expect=("cond_obesity", "ref_bmi_bands", "term_bmi_word",
                "profile_bmi_derived"),
    ),
    EvalQuery(
        "Heart Disease risk-factor context",
        "finding",
        conditions=("Heart Disease",),
        features=("cholesterol", "smoking_history", "hypertension", "age"),
        expect=("cond_heart_disease", "term_risk_factor",
                "profile_smoking_history", "profile_hypertension"),
    ),
    EvalQuery(
        "Hypoglycemia",
        "finding",
        conditions=("Hypoglycemia",),
        features=("blood_glucose",),
        expect=("cond_hypoglycemia", "ref_glucose_bands", "lab_blood_glucose"),
    ),
    EvalQuery(
        "Elevated Hemoglobin",
        "finding",
        conditions=("Elevated Hemoglobin",),
        features=("hemoglobin",),
        expect=("cond_elevated_hemoglobin", "lab_hemoglobin",
                "ref_hemoglobin_bands"),
    ),
    EvalQuery(
        "Underweight",
        "finding",
        conditions=("Underweight",),
        features=("bmi",),
        expect=("cond_underweight", "ref_bmi_bands", "life_weight_discussion"),
    ),
    EvalQuery(
        "Elevated Vitamin D",
        "finding",
        conditions=("Elevated Vitamin D",),
        features=("vitamin_d",),
        expect=("cond_elevated_vitamin_d", "ref_vitamin_d_bands", "lab_vitamin_d"),
    ),
    EvalQuery(
        "lay: what is HbA1c",
        "text",
        text="what does my HbA1c number actually mean",
        expect=("lab_hba1c", "ref_hba1c_bands"),
    ),
    EvalQuery(
        "lay: sugar disease",
        "text",
        text="I was told I might have sugar disease, what is it",
        expect=("cond_diabetes", "lab_blood_glucose", "lab_hba1c"),
    ),
    EvalQuery(
        "lay: always tired and pale",
        "text",
        text="why am I always tired and pale, is my blood low",
        expect=("cond_anemia", "lab_hemoglobin"),
    ),
    EvalQuery(
        "lay: thick blood",
        "text",
        text="my report says high haemoglobin, is my blood too thick",
        expect=("cond_elevated_hemoglobin", "lab_hemoglobin"),
    ),
    EvalQuery(
        "lay: good and bad cholesterol",
        "text",
        text="what is the difference between good and bad cholesterol",
        expect=("term_ldl_hdl", "lab_cholesterol"),
    ),
    EvalQuery(
        "lay: fasting needed",
        "text",
        text="do I need to fast before a blood sugar test",
        expect=("term_fasting_sample", "lab_blood_glucose"),
    ),
    EvalQuery(
        "lay: normal range meaning",
        "text",
        text="what does the normal range on a lab report mean",
        expect=("term_reference_interval",),
    ),
    EvalQuery(
        "lay: mmol vs mg",
        "text",
        text="my old report used mmol/L and this one uses mg/dL",
        expect=("term_units_mgdl_mmoll",),
    ),
    EvalQuery(
        "lay: kidney number egfr",
        "text",
        text="what is eGFR and how is it different from creatinine",
        expect=("term_egfr", "lab_creatinine"),
    ),
    EvalQuery(
        "lay: how much exercise",
        "text",
        text="how much exercise should an adult get each week",
        expect=("life_physical_activity",),
    ),
    EvalQuery(
        "lay: foods with iron",
        "text",
        text="which foods are high in iron",
        expect=("life_iron_rich_foods",),
    ),
    EvalQuery(
        "lay: is this a diagnosis",
        "text",
        text="is this automated report a diagnosis, can I rely on it",
        expect=("interp_what_this_platform_is",),
    ),
    EvalQuery(
        "lay: result changed since last time",
        "text",
        text="why is my result different from my last report",
        expect=("interp_why_values_vary", "interp_single_result"),
    ),
    EvalQuery(
        "lay: slightly out of range",
        "text",
        text="my value is only slightly above the range, should I worry",
        expect=("interp_borderline", "interp_when_to_seek_advice"),
    ),
    EvalQuery(
        "lay: test missing from report",
        "text",
        text="one of my tests could not be read from the report",
        expect=("interp_missing_value",),
    ),
    EvalQuery(
        "lay: vitamin d from sun",
        "text",
        text="can I get enough vitamin D from sunlight in winter",
        expect=("life_vitamin_d_sources", "cond_vitamin_d_deficiency"),
    ),
    EvalQuery("negative: bicycle", "negative",
              text="how do I fix a puncture on my bicycle tyre"),
    EvalQuery("negative: keyboard mash", "negative", text="asdfghjkl qwertyuiop"),
    EvalQuery("negative: python bug", "negative",
              text="why does my python script raise a KeyError on line 40"),
    EvalQuery("negative: weather", "negative",
              text="what is the weather forecast for tomorrow afternoon"),
    EvalQuery("negative: empty", "negative", text="   "),
)


def _ranked_doc_ids(results) -> List[str]:
    seen: List[str] = []
    for r in results:
        if r.chunk.doc_id not in seen:
            seen.append(r.chunk.doc_id)
    return seen


@dataclass
class Report:
    name: str
    recall_at_1: float = 0.0
    recall_at_3: float = 0.0
    recall_at_5: float = 0.0
    mrr: float = 0.0
    precision_at_3: float = 0.0
    negatives_correct: int = 0
    negatives_total: int = 0
    failures: List[str] = field(default_factory=list)


def evaluate(
    search: Callable[[EvalQuery, int], List[str]], name: str, verbose: bool = False
) -> Report:
    report = Report(name=name)
    positives = [q for q in EVAL_QUERIES if q.kind != "negative"]
    negatives = [q for q in EVAL_QUERIES if q.kind == "negative"]

    r1 = r3 = r5 = mrr = p3 = 0.0
    for q in positives:
        ranked = search(q, 10)
        expected = set(q.expect)
        r1 += bool(set(ranked[:1]) & expected)
        hit3 = bool(set(ranked[:3]) & expected)
        r3 += hit3
        r5 += bool(set(ranked[:5]) & expected)
        p3 += len(set(ranked[:3]) & expected) / 3.0
        rank = next((i + 1 for i, d in enumerate(ranked) if d in expected), None)
        mrr += (1.0 / rank) if rank else 0.0
        if not hit3:
            report.failures.append(f"{q.label}: got {ranked[:3]}, wanted {q.expect}")
        if verbose:
            mark = "ok " if hit3 else "MISS"
            print(f"    {mark} {q.label:44s} -> {ranked[:3]}")

    n = len(positives)
    report.recall_at_1 = r1 / n
    report.recall_at_3 = r3 / n
    report.recall_at_5 = r5 / n
    report.mrr = mrr / n
    report.precision_at_3 = p3 / n

    for q in negatives:
        ranked = search(q, 10)
        ok = not ranked
        report.negatives_correct += ok
        if verbose and not ok:
            print(f"    LEAK {q.label:44s} -> {ranked[:3]}")
    report.negatives_total = len(negatives)
    return report


def lexical_search(index: KnowledgeIndex, floor: float = SIMILARITY_FLOOR):
    def _search(q: EvalQuery, top_k: int) -> List[str]:
        query = build_query(
            conditions=q.conditions, features=q.features, text=q.text
        )
        if query.is_empty:
            return []
        return _ranked_doc_ids(index.search(query, top_k=top_k, floor=floor))

    return _search


def print_report(r: Report) -> None:
    print(f"\n  {r.name}")
    print(f"    Recall@1      {r.recall_at_1:.3f}")
    print(f"    Recall@3      {r.recall_at_3:.3f}")
    print(f"    Recall@5      {r.recall_at_5:.3f}")
    print(f"    MRR           {r.mrr:.3f}")
    print(f"    Precision@3   {r.precision_at_3:.3f}")
    print(
        f"    negatives     {r.negatives_correct}/{r.negatives_total} "
        "correctly returned nothing"
    )
    for f in r.failures:
        print(f"    MISS  {f}")


def sweep_floor(index: KnowledgeIndex) -> None:
    print("\n  similarity floor sweep")
    print(
        f"    {'floor':>7}  {'Recall@3':>8}  {'Prec@3':>7}  "
        f"{'negatives kept out':>19}"
    )
    for floor in (0.0, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25, 0.30):
        r = evaluate(lexical_search(index, floor), f"floor={floor}")
        print(
            f"    {floor:7.2f}  {r.recall_at_3:8.3f}  {r.precision_at_3:7.3f}  "
            f"{r.negatives_correct:>10}/{r.negatives_total}"
        )


def main() -> int:
    index = KnowledgeIndex.build()
    print(f"corpus: {len(index.chunks)} chunks, "
          f"{len(index.vocabulary.idf)} vocabulary terms")
    print(f"eval set: {len([q for q in EVAL_QUERIES if q.kind != 'negative'])} "
          f"positive, {len([q for q in EVAL_QUERIES if q.kind == 'negative'])} negative")

    report = evaluate(
        lexical_search(index), "LEXICAL TF-IDF (shipped)", verbose="-v" in sys.argv
    )
    print_report(report)
    sweep_floor(index)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
