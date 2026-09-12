"""Module 12 -- the Kidney Disease Predictor.

Loads the Random Forest pipelines built by `ml/train_kidney.py` and turns one
probability into one `ClinicalDecision`. It does not fit anything, ever.

==========================================================================
THE HEADLINE FEATURE IS THE SKIP, NOT THE ACCURACY
==========================================================================

Spec Module 12:

    "If insufficient kidney-related information is available, the predictor
     can skip the prediction rather than blindly producing a result... a
     machine-learning model trained using multiple kidney-related parameters
     should not automatically be interpreted as equally reliable when only a
     small subset of those parameters is available."

`required_features = ("creatinine", "hemoglobin")`. Without BOTH, the base
class's template method returns an `INSUFFICIENT_DATA` decision with
`risk=None` and `confidence=None`, and `_predict` is never reached.

WHY THOSE TWO, AND WHY NOT MORE OR FEWER. The training script measures every
one of the 30 usable feature subsets and writes them into
`ml/artifacts/kidney_rf_v1.metrics.json` under `sufficiency_evidence`. The
numbers (5-fold CV ROC-AUC on the training portion):

    creatinine + hemoglobin ............................ 0.9860
    all five features .................................. 0.9957
    hemoglobin alone ................................... 0.9611
    creatinine alone ................................... 0.9095
    blood_glucose alone ................................ 0.7380
    age alone .......................................... 0.5860

So the pair carries essentially the whole model and the other three are a
0.010 refinement -- which is why `blood_glucose`, `age` and `hypertension` are
OPTIONAL. Making them required would turn a good prediction into a skip for no
benefit, and a predictor that skips too eagerly is not safer, it is just
silent.

THE HONEST PART. Blanking one input on the shipped pipeline at prediction time
costs, on the held-out split: hemoglobin -0.0360, creatinine -0.0073,
blood_glucose -0.0051, age -0.0017, hypertension -0.0004 ROC-AUC. Haemoglobin's
case is therefore made by the numbers. **Creatinine's is not**, and pretending
otherwise would be dishonest: on THIS cohort the model barely misses it.

Creatinine is required anyway, for a reason that is clinical rather than
statistical. Serum creatinine is the analyte that DEFINES renal function; the
reason haemoglobin can stand in for it here is that anaemia of chronic kidney
disease is near-universal in this single-centre 399-patient cohort. A "kidney
prediction" produced without creatinine would in practice be an anaemia signal
wearing a kidney label, and in a screening population -- where anaemia has many
other causes -- that substitution would fail quietly and in the dangerous
direction. Requiring the defining analyte is a deliberate refusal to let a
correlate stand in for it. The cost of that refusal is a SKIP, which the reader
sees, rather than a wrong answer, which they would not.

That is not a hole in the report. `app/data/conditions.py` marks
`Kidney Disease` `always_assessed`, and Module 8's creatinine rule still
produces a deterministic decision. Only the ML opinion is withheld.

==========================================================================
THE TRI-STATE PROBLEM: ABSENT MUST NEVER BECOME "no"
==========================================================================

Module 2 stores `hypertension` as TRUE / FALSE / ABSENT, where absent means
"the patient never answered". The UCI dataset has only `yes` / `no`.

Encoding an absent answer as `no` would tell the forest "this patient does not
have hypertension" when nobody ever asked, and most-frequent imputation is the
same act with better manners -- the majority value IS `no`. So, following
Module 10, the artifact holds TWO fitted pipelines::

    with_hypertension  |  without_hypertension

Each was fitted on the same real rows, and the `without_hypertension` variant's
ColumnTransformer has no hypertension column at all -- not even an encoder.
`select_variant()` picks by whether the patient supplied an actual `bool`, and
`_model_row()` builds a frame containing ONLY that variant's columns, so the
matrix handed to the forest never contains a value that was not observed.
`tests/test_kidney_predictor.py` asserts this against the real frame, not
against the intention.

Note the asymmetry with imputing `blood_glucose` or `age`. Imputing a
continuous MEASUREMENT substitutes a population value for an unmeasured
quantity -- a documented statistical choice, and the one spec Module 12
explicitly asks for. Imputing a boolean CLINICAL FINDING invents a diagnosis
the patient never gave. Different acts, treated differently.

==========================================================================
WHAT THE NUMBERS DO AND DO NOT MEAN
==========================================================================

Held-out ROC-AUC 0.998, accuracy 0.97 against a 0.63 majority-class baseline.
Those numbers are real and they are also not as impressive as they look: the
test split is 100 patients, so a single misclassification moves recall by 1.6
points, and this UCI cohort separates almost cleanly on creatinine and
haemoglobin. `metadata.model_performance_reference.honest_read` carries that
caveat onto every decision so Module 20 cannot render 0.998 as clinical-grade
certainty.

Only five of the dataset's 24 attributes are used, because those five are the
only kidney-related ones `app/data/feature_catalog.py` can supply at prediction
time. Blood urea, albumin and specific gravity would very likely improve the
model and are a REPORTED GAP, not an oversight.

==========================================================================
CONFIDENCE SEMANTICS
==========================================================================

`ClinicalDecision.confidence` is ALWAYS P(positive), exactly as in Modules 10
and 11 -- never "how sure the model is". A NOT_INDICATED decision carries a low
number meaning a confident negative. `metadata.confidence_semantics` records it.
"""

from __future__ import annotations

import math

from typing import Any, Dict, List, Mapping, Optional, Tuple

from app.data import conditions as C
from app.data.recommendation_catalog import (
    CONFIRM_WITH_REPEAT_TESTING,
    DISCUSS_WITH_CLINICIAN,
    GENERAL_HYDRATION,
    INPUT_QUALITY_CAVEAT,
    MONITOR_OVER_TIME,
    NOTHING_FLAGGED_EDUCATIONAL,
    NOT_A_DIAGNOSIS,
    SEEK_PROMPT_MEDICAL_ADVICE,
    recommendations as resolve_recommendations,
)
from app.ml.artifacts import load_failure_reason, load_model
from app.ml.operating_metrics import (
    operating_metrics,
    performance_figures,
)
from app.ml.base import (
    PredictionContext,
    Predictor,
    PredictorError,
)
from app.ml.heart import (
    ASSESSMENT_BASIS_KEY,
    ASSESSMENT_KIND_KEY,
    ASSESSMENT_KIND_LIKELIHOOD,
)
from app.schemas.decisions import (
    ClinicalDecision,
    DecisionSourceKind,
    DecisionStatus,
    EvidenceItem,
    RiskLevel,
)
from app.schemas.fusion import BASIS_MODEL_PROBABILITY, BASIS_NOT_ASSESSED

KIDNEY_MODEL_FILE = "kidney_rf_v1.joblib"
KIDNEY_METRICS_FILE = "kidney_rf_v1.metrics.json"

# --------------------------------------------------------------------------
# Fixed, user-facing note fragments (scanned by the safety scanner in tests)
# --------------------------------------------------------------------------

NOTE_MODEL_INPUT = "this value was given to the model"
NOTE_IMPUTED = (
    "this value was not available, so the model used the median of its "
    "training data in its place"
)
NOTE_NOT_ASSERTED = (
    "this was not recorded, and the model used for this report was built "
    "without it rather than assuming an answer"
)
NOTE_QUESTIONABLE = "this value was marked less reliable when the report was read"
NOTE_EXTREME_HIGH = (
    "this value is far above the usual range and was flagged for priority"
)
NOTE_EXTREME_LOW = (
    "this value is far below the usual range and was flagged for priority"
)

KIDNEY_NOTE_FRAGMENTS: Tuple[str, ...] = (
    NOTE_MODEL_INPUT,
    NOTE_IMPUTED,
    NOTE_NOT_ASSERTED,
    NOTE_QUESTIONABLE,
    NOTE_EXTREME_HIGH,
    NOTE_EXTREME_LOW,
)

#: The tri-state feature, handled by variant selection rather than imputation.
TRI_STATE_HYPERTENSION = "hypertension"

#: hypertension answered? -> artifact variant name.
VARIANT_BY_AVAILABILITY: Dict[bool, str] = {
    True: "with_hypertension",
    False: "without_hypertension",
}

#: The dataset's own spelling of the two answers. A bool becomes one of these
#: and NOTHING else ever does.
HYPERTENSION_LEVELS: Dict[bool, str] = {True: "yes", False: "no"}

#: Features whose EXTREME direction is LOW rather than high, for note wording.
_EXTREME_LOW_FEATURES = ("hemoglobin",)


class KidneyPredictor(Predictor):
    """Spec Module 12. Random Forest, one `ClinicalDecision` per call."""

    name = "kidney_rf"
    condition = C.KIDNEY_DISEASE  # byte-for-byte canonical; never spelled out
    source_label = "Random Forest"
    version = "1.0.0"

    #: See "THE HEADLINE FEATURE IS THE SKIP" above.
    required_features: Tuple[str, ...] = ("creatinine", "hemoglobin")
    optional_features: Tuple[str, ...] = ("blood_glucose", "age", "hypertension")

    def __init__(self, artifact_filename: str = KIDNEY_MODEL_FILE) -> None:
        self._artifact_filename = artifact_filename
        super().__init__()

    # -- artifact ---------------------------------------------------------

    @property
    def artifact(self):
        """The loaded bundle, or None. Lazy and cached in `app.ml.artifacts`."""
        return load_model(self._artifact_filename)

    def is_available(self) -> bool:
        return self.artifact is not None

    def unavailable_reason(self) -> Optional[str]:
        return load_failure_reason(self._artifact_filename)

    def artifact_integrity(self) -> Dict[str, Any]:
        """The load-time artifact<->metrics sha256 check (integration audit D3)."""
        bundle = self.artifact
        return dict(bundle.integrity or {}) if bundle is not None else {}

    def model_provenance(self) -> Dict[str, Any]:
        bundle = self.artifact
        if bundle is None:
            return {"available": False, "reason": self.unavailable_reason()}
        dataset = bundle.get("dataset", {}) or {}
        integrity = dict(bundle.integrity or {})
        return {
            "available": True,
            "artifact_file": self._artifact_filename,
            # Integration audit D3. The artifact<->metrics sha256 binding,
            # checked at load time and carried on EVERY decision this model
            # produces -- the thresholds, importances and performance numbers
            # published beside the prediction all come from the metrics
            # document this digest binds to the joblib.
            "artifact_integrity": integrity,
            "artifact_integrity_verified": bool(integrity.get("verified")),
            "artifact_version": bundle.get("artifact_version"),
            "model_id": bundle.get("model_id"),
            "algorithm": bundle.get("algorithm"),
            "trained_at": bundle.get("trained_at"),
            "sklearn_version": bundle.get("sklearn_version"),
            "hyperparameters": bundle.get("hyperparameters"),
            "dataset_sha256": dataset.get("sha256"),
            "dataset_rows_used": dataset.get("rows_used"),
            "dataset_prevalence": dataset.get("prevalence"),
            "malformed_label_rows_dropped": dataset.get(
                "malformed_label_rows_dropped"
            ),
            "synthetic_rows": dataset.get("synthetic_rows"),
            "resampling": dataset.get("resampling"),
            "kidney_parameters_unavailable_to_vaidyaai": dataset.get(
                "columns_available_but_unused"
            ),
        }

    # -- variant selection: THE tri-state decision ------------------------

    @staticmethod
    def _tri_state(value: Any) -> Optional[bool]:
        """A tri-state value, or None for 'the patient never said'.

        ONLY a real `bool` counts. Module 5 preserves the tri-state by ABSENCE
        from the feature map and Module 6 keeps booleans as booleans, so
        anything that is not a `bool` here -- a `None`, a stray `"unknown"`, a
        `0` from a sloppy caller -- is treated as UNKNOWN rather than coerced.

        What is deliberately NOT done: `bool(value)` would turn the string
        `"false"` into True and `0` into False. Both fabricate an answer.
        """
        if isinstance(value, bool):
            return value
        return None

    def select_variant(
        self, features: Mapping[str, Any]
    ) -> Tuple[str, Optional[bool]]:
        """Which fitted pipeline matches what this patient actually answered."""
        known = self._tri_state(features.get(TRI_STATE_HYPERTENSION))
        return VARIANT_BY_AVAILABILITY[known is not None], known

    # -- the model frame --------------------------------------------------

    def _model_row(
        self, features: Mapping[str, Any], variant_name: str
    ) -> Tuple[Any, Dict[str, Any]]:
        """Build the ONE-ROW frame handed to the pipeline, plus a trace of how.

        The trace records, per feature, whether the value came from the patient
        (`observed`), was left to the median imputer (`imputed`), or was
        excluded from the model entirely (`not_asserted`). Evidence and
        metadata are built from the trace, so what the decision claims and what
        the model actually received cannot drift apart.

        Every model column here already carries its canonical VaidyaAI name --
        the training script renames `sc`/`hemo`/`bgr`/`htn` -- so no mapping
        layer is needed and none is hidden here.
        """
        import numpy as np
        import pandas as pd

        bundle = self.artifact
        if bundle is None:  # pragma: no cover - guarded by is_available()
            raise PredictorError("kidney model artifact is not loaded")
        spec = bundle.variants.get(variant_name)
        if spec is None:
            raise PredictorError(
                f"the kidney artifact has no variant {variant_name!r}; it has "
                f"{sorted(bundle.variants)}"
            )

        numeric: List[str] = list(spec["numeric_features"])
        categorical: List[str] = list(spec["categorical_features"])
        trace: Dict[str, Any] = {}
        row: Dict[str, Any] = {}

        for column in numeric:
            number = _as_float(features.get(column))
            if number is None:
                row[column] = np.nan
                trace[column] = {"status": "imputed", "value": None}
            else:
                row[column] = number
                trace[column] = {"status": "observed", "value": number}

        for column in categorical:
            # Only `hypertension`, and only in the with_hypertension variant,
            # which is only selected when a real bool was supplied.
            known = self._tri_state(features.get(column))
            if known is None:  # pragma: no cover - unreachable via select_variant
                raise PredictorError(
                    f"variant {variant_name!r} requires {column!r} but the "
                    "patient did not supply it; select_variant() should have "
                    "chosen the variant fitted without it"
                )
            row[column] = HYPERTENSION_LEVELS[known]
            trace[column] = {"status": "observed", "value": known}

        if TRI_STATE_HYPERTENSION not in categorical:
            trace[TRI_STATE_HYPERTENSION] = {"status": "not_asserted", "value": None}

        frame = pd.DataFrame([row], columns=numeric + categorical)
        return frame, trace

    # -- risk banding -----------------------------------------------------

    @staticmethod
    def _thresholds(bundle, variant_name: str) -> Tuple[float, float]:
        thresholds = bundle.variants[variant_name]["thresholds"]
        return float(thresholds["borderline"]), float(thresholds["indicated"])

    @staticmethod
    def band(
        probability: float, borderline: float, indicated: float
    ) -> Tuple[DecisionStatus, RiskLevel, str]:
        """probability -> (status, risk, band name).

        Both cut-offs are read off the artifact and both were derived from the
        measured precision-recall curve of OUT-OF-FOLD training predictions --
        a holdout slice of ~60 patients would have made them noise. See
        `ml/train_kidney.py` for why Module 10's absolute 0.90-precision rule
        is recorded but not applied: this model reaches 0.90 precision at a
        threshold of 0.11, before it has committed to anything, which would
        have put 79% of the cohort in the INDICATED band and left BORDERLINE
        empty.

          * `indicated`  = the MOST PRECISE out-of-fold threshold still
            catching 98 of every 100 positives. On the shipped
            `with_hypertension` model that is 0.411, achieving precision 0.984.
          * `borderline` = the LARGEST out-of-fold threshold still catching 99
            of every 100. It lands at 0.180.

        Both cut-offs are stated as sensitivity guarantees because a missed
        case of kidney disease is this condition's dangerous failure, and
        `app/schemas/decisions.py` calls false reassurance the worst failure
        the decision type can have.

        Measured band composition on the 100-patient held-out test split
        (variant `with_hypertension`), recorded in the metrics artifact:

            low      35 patients,  1 positive ( 2.9%)
            medium    1 patient,   0 positive ( 0.0%)
            high     64 patients, 62 positive (96.9%)

        Read that honestly. The middle band holds ONE patient, because this
        cohort's scores are strongly bimodal -- the model is rarely uncertain
        about a UCI CKD patient. On a screening population it would be
        uncertain far more often, and the middle band exists for exactly that
        case. Do not read a near-empty BORDERLINE band as evidence that
        borderline patients do not exist.
        """
        if probability >= indicated:
            return DecisionStatus.INDICATED, RiskLevel.HIGH, "high"
        if probability >= borderline:
            return DecisionStatus.BORDERLINE, RiskLevel.MEDIUM, "medium"
        return DecisionStatus.NOT_INDICATED, RiskLevel.LOW, "low"

    # -- prediction -------------------------------------------------------

    def _predict(
        self, features: Mapping[str, Any], context: PredictionContext
    ) -> ClinicalDecision:
        bundle = self.artifact
        variant_name, known_hypertension = self.select_variant(features)
        frame, trace = self._model_row(features, variant_name)

        pipeline = bundle.pipelines[variant_name]
        probability = float(pipeline.predict_proba(frame)[0][1])

        borderline, indicated = self._thresholds(bundle, variant_name)
        status, risk, band_name = self.band(probability, borderline, indicated)

        # The share of true positives the Indicated threshold actually flags,
        # read by `ModelLimitations.recall_at_operating_threshold`. Carried for
        # the same reason as in Module 11, where it was found to be dropped:
        # a consumer must be able to see how much a model misses. This model's
        # is 0.984, so the low-detection caveat will NOT fire here -- which is
        # the point. The caveat has to be driven by the measured number, not by
        # which model happens to be speaking.
        # Read by ONE shared reader that knows every place an artifact may
        # record these, because per-model reasoning about this exact question
        # produced 6o D8 and then 6p. Absent figures stay absent.
        achieved = operating_metrics(bundle.variants[variant_name])
        achieved_performance = performance_figures(bundle.variants[variant_name])

        spec = bundle.variants[variant_name]
        importance: Dict[str, float] = dict(spec.get("global_feature_importance", {}))

        evidence = self._evidence(trace, importance, context)
        recommendations = self._recommendations(status, context, trace)

        metrics = spec.get("metrics", {}) or {}
        sufficiency = bundle.get("sufficiency_evidence", {}) or {}
        metadata: Dict[str, Any] = {
            "predictor": self.name,
            "predictor_version": self.version,
            "skipped": False,
            "model": self.model_provenance(),
            ASSESSMENT_KIND_KEY: ASSESSMENT_KIND_LIKELIHOOD,
            ASSESSMENT_BASIS_KEY: BASIS_MODEL_PROBABILITY,
            "assessment_kind_note": (
                "This decision estimates the LIKELIHOOD of chronic kidney "
                "disease. Module 8's creatinine rule assesses the same "
                "condition string from a threshold on one analyte. A decision "
                "carrying no assessment_kind key should not be read as a "
                "probability."
            ),
            "variant": variant_name,
            "variant_reason": (
                "chosen by whether the patient actually answered the "
                f"hypertension question: hypertension="
                f"{_tri_word(known_hypertension)}"
                + (
                    ""
                    if known_hypertension is not None
                    else ". The variant fitted WITHOUT a hypertension column "
                    "was used, so an unanswered question was never encoded as "
                    "'no'."
                )
            ),
            "probability_positive": probability,
            "confidence_semantics": "probability_of_positive_class",
            "confidence_note": (
                "confidence is P(positive) and is NOT 'how sure the model is'. "
                "A low value on a Not Indicated decision means a confident "
                "negative."
            ),
            # Omitted rather than sent as null when the artifact does not
            # record it: a missing value reads as "not recorded", a null would
            # be a claim that there is no recall.
            "thresholds": {
                "borderline": borderline,
                "indicated": indicated,
                # Recall AND precision at this cut-off, where the artifact
                # records them. Precision is what tells a clinician what an
                # "Indicated" flag is actually worth; it was structurally
                # unreachable until 6p because the reader looked for a key no
                # model published.
                **achieved,
            },
            "threshold_basis": (
                "indicated = most precise out-of-fold threshold still holding "
                "0.98 cumulative recall; borderline = largest out-of-fold "
                "threshold still holding 0.99 cumulative recall. Both are read "
                "off the measured precision-recall curve, neither is a round "
                "number, and both are stated as sensitivity guarantees because "
                "a missed case is the dangerous failure here."
            ),
            "risk_band": band_name,
            "band_meaning": _BAND_MEANING[band_name],
            "sufficiency_rule": {
                "required_features": list(self.required_features),
                "optional_features": list(self.optional_features),
                "basis": (
                    "creatinine + hemoglobin alone reach 0.986 cross-validated "
                    "ROC-AUC against the full model's 0.996, so the other "
                    "three inputs are a refinement rather than load-bearing. "
                    "Creatinine is required on clinical rather than "
                    "statistical grounds: it is the analyte that defines renal "
                    "function, and without it this model leans on haemoglobin, "
                    "which is a correlate in this cohort and would not be one "
                    "in a screening population."
                ),
                "measured": sufficiency.get("imputed_at_prediction_time", {}).get(
                    "blanked"
                ),
            },
            "features_observed": sorted(
                n for n, t in trace.items() if t["status"] == "observed"
            ),
            "features_imputed": sorted(
                n for n, t in trace.items() if t["status"] == "imputed"
            ),
            "features_not_asserted": sorted(
                n for n, t in trace.items() if t["status"] == "not_asserted"
            ),
            "model_input_columns": list(frame.columns),
            "questionable_features_used": sorted(
                n for n in trace if n in context.questionable
            ),
            "clinically_extreme_features_used": sorted(
                n for n in trace if n in context.clinically_extreme
            ),
            "partial_document": context.partial_document,
            "global_feature_importance": importance,
            "feature_importance_scope": "global_model_level",
            "feature_importance_caveat": (
                "Mean impurity decrease over the whole training set. It ranks "
                "features FOR THE MODEL and orders the evidence below. It is "
                "NOT a per-patient explanation and must never be presented as "
                "the reason THIS prediction came out as it did."
            ),
            "evidence_ordering": "global_feature_importance_descending",
            "model_performance_reference": {
                # Accuracy read WITH its majority-class baseline: accuracy alone
                # on an imbalanced set is close to meaningless, and reporting
                # one without the other invites exactly that misreading.
                **achieved_performance,
                "measured_on": "held-out test split, see the metrics artifact",
                "variant": variant_name,
                "roc_auc": metrics.get("roc_auc"),
                "pr_auc_average_precision": metrics.get("pr_auc_average_precision"),
                "accuracy": metrics.get("accuracy"),
                "majority_class_baseline_accuracy": metrics.get(
                    "majority_class_baseline_accuracy"
                ),
                "positive_class": metrics.get("positive_class"),
                "artifact": "ml/artifacts/kidney_rf_v1.metrics.json",
                # WRITTEN FOR THE CLINICIAN WHO READS IT, not for a model
                # reviewer. This string is rendered verbatim on the doctor
                # summary (Module 32), and the earlier wording -- "399 rows",
                # "a single UCI cohort", "a ROC-AUC near 0.99", "moves recall
                # by about 1.6 points" -- is the vocabulary of whoever trained
                # the thing. A clinician handed a patient's phone reads past
                # it, and the caveat is the part they most need.
                #
                # EVERY FACT IS KEPT and only the register changed: the small
                # single-source dataset, the two analytes that made the split
                # easy, that the accuracy reflects the dataset rather than
                # expected screening performance, and the fragility of a
                # 100-record test set. The ML reading of the same facts is
                # untouched in `ml/artifacts/kidney_rf_v1.metrics.json`, whose
                # audience really is a model reviewer.
                # SHORTENED AGAIN 2026-09-11, on the reader's objection: the
                # dataset arithmetic is the EVIDENCE for the caveat, not the
                # caveat. "399 records to learn from and 100 to check against"
                # and "1.6 percentage points" tell a clinician how the model
                # was built; what they can act on is that the flag came from a
                # pattern, that its accuracy figure flatters it, and what the
                # flag is therefore worth. The counts remain in
                # `ml/artifacts/kidney_rf_v1.metrics.json`, whose audience is a
                # model reviewer.
                #
                # WHAT MAY NOT GO IS THE CAVEAT ITSELF. This platform has found
                # it MISSING three separate times (MEMORY.md 6o D8, 6p, 6w),
                # each time leaving a model's flag on screen with nothing
                # qualifying it, and each time it was recorded as the most
                # serious thing on the page.
                "honest_read": (
                    "This came from a pattern model, not from a measurement. "
                    "It was developed on one small dataset in which the two "
                    "groups separated unusually cleanly, so its accuracy there "
                    "flatters it and nothing shows it holds in a screening "
                    "population where kidney disease is far less common. It is "
                    "a reason to consider further assessment, never a finding "
                    "in itself."
                ),
            },
        }

        return ClinicalDecision(
            condition=self.condition,
            status=status,
            risk=risk,
            confidence=probability,
            source=self.source_label,
            source_kind=DecisionSourceKind.MACHINE_LEARNING,
            evidence=evidence,
            recommendations=recommendations,
            metadata=metadata,
        )

    # -- the skip ---------------------------------------------------------

    def insufficient_decision(self, report, context=None, *, extra_metadata=None):
        """The base skip, plus this module's own explanation of it.

        The base class already produces the right SHAPE -- INSUFFICIENT_DATA,
        `risk=None`, `confidence=None`, an evidence item per missing input.
        What is added here is WHY these particular inputs are the ones that can
        force a skip, because "the model needed creatinine" is a claim a reader
        is entitled to see the basis for.
        """
        metadata: Dict[str, Any] = {
            ASSESSMENT_KIND_KEY: ASSESSMENT_KIND_LIKELIHOOD,
            ASSESSMENT_BASIS_KEY: BASIS_NOT_ASSESSED,
            "sufficiency_rule": {
                "required_features": list(self.required_features),
                "optional_features": list(self.optional_features),
                "basis": (
                    "Serum creatinine defines renal function and haemoglobin "
                    "carries the largest measured share of this model's "
                    "discrimination. Without both, a probability would rest on "
                    "median values taken from the training cohort rather than "
                    "on this patient. Module 8's creatinine rule still "
                    "assesses this condition."
                ),
            },
        }
        metadata.update(extra_metadata or {})
        return super().insufficient_decision(report, context, extra_metadata=metadata)

    # -- evidence ---------------------------------------------------------

    def _evidence(
        self,
        trace: Dict[str, Any],
        importance: Dict[str, float],
        context: PredictionContext,
    ) -> List[EvidenceItem]:
        """One item per feature the model was given, most important first.

        Absent features are listed too -- "the model was not told whether you
        have hypertension" is exactly what spec Module 20 exists to show.
        `threshold` stays None: `decisions.py` reserves it for rule-based
        producers, and no single threshold explains a forest.
        """
        order = sorted(trace, key=lambda name: (-importance.get(name, 0.0), name))
        items: List[EvidenceItem] = []
        for name in order:
            entry = trace[name]
            status = entry["status"]
            note = {
                "observed": NOTE_MODEL_INPUT,
                "imputed": NOTE_IMPUTED,
                "not_asserted": NOTE_NOT_ASSERTED,
            }[status]
            if status == "observed" and name in context.questionable:
                note = NOTE_QUESTIONABLE
            elif status == "observed" and name in context.clinically_extreme:
                note = (
                    NOTE_EXTREME_LOW
                    if name in _EXTREME_LOW_FEATURES
                    else NOTE_EXTREME_HIGH
                )
            items.append(
                EvidenceItem(
                    feature=name,
                    value=entry["value"],
                    unit=context.unit_for(name) if status == "observed" else None,
                    threshold=None,
                    comparator=None,
                    note=note,
                    source_stage=(
                        "not_available" if status == "not_asserted" else "model_input"
                    ),
                )
            )
        return items

    # -- recommendations: catalogue codes only ----------------------------

    def _recommendations(
        self,
        status: DecisionStatus,
        context: PredictionContext,
        trace: Dict[str, Any],
    ):
        """Codes only. There is no code path here that composes text.

        `SEEK_PROMPT_MEDICAL_ADVICE` IS attached to an INDICATED decision here,
        unlike Module 11's. The difference is measured, not stylistic: this
        model's precision at its INDICATED cut-off is 0.97 on held-out data
        (0.98 out-of-fold), comfortably above the ~0.90 at which Module 10
        attaches the same code, whereas Module 11's is 0.75.
        """
        if status is DecisionStatus.INDICATED:
            codes: Tuple[str, ...] = (
                DISCUSS_WITH_CLINICIAN,
                SEEK_PROMPT_MEDICAL_ADVICE,
                CONFIRM_WITH_REPEAT_TESTING,
                GENERAL_HYDRATION,
            )
        elif status is DecisionStatus.BORDERLINE:
            codes = (
                DISCUSS_WITH_CLINICIAN,
                CONFIRM_WITH_REPEAT_TESTING,
                MONITOR_OVER_TIME,
                GENERAL_HYDRATION,
            )
        else:
            codes = (NOTHING_FLAGGED_EDUCATIONAL, MONITOR_OVER_TIME)

        if any(name in context.questionable for name in trace):
            codes += (INPUT_QUALITY_CAVEAT,)
        # Attached to EVERY decision, exactly as Modules 8, 10 and 11 do.
        return resolve_recommendations(codes + (NOT_A_DIAGNOSIS,))


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

_BAND_MEANING = {
    "low": (
        "Below the sensitivity-derived cut-off. On the held-out test split "
        "2.9% of patients in this band were positive, against a cohort "
        "prevalence of 63.0%."
    ),
    "medium": (
        "Between the two cut-offs: NOT RULED OUT rather than elevated. It held "
        "one patient of 100 on the held-out split, because this cohort's "
        "scores are strongly bimodal. A near-empty band here is a property of "
        "the test cohort, not evidence that borderline patients do not exist."
    ),
    "high": (
        "At or above the precision-derived cut-off. On the held-out test split "
        "96.9% of patients in this band were positive, against a cohort "
        "prevalence of 63.0%."
    ),
}


def _as_float(value: Any) -> Optional[float]:
    """A usable number, or None. `bool` is NOT a number here.

    Python makes `isinstance(True, int)` true, so without the explicit guard a
    stray boolean would silently become 1.0 in a numeric column -- which for
    this predictor would mean a tri-state answer leaking into a measurement.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        try:
            number = float(str(value).strip())
        except (TypeError, ValueError):
            return None
    # NaN and inf are not measurements. NaN matters most: it is the exact value
    # the pipeline's imputer replaces, so admitting it here would record the
    # feature as `observed` while the model actually received a cohort median
    # -- the one substitution that would leave no trace (integration audit D1).
    return number if math.isfinite(number) else None


def _tri_word(value: Optional[bool]) -> str:
    return "not recorded" if value is None else str(value).lower()


__all__ = [
    "HYPERTENSION_LEVELS",
    "KIDNEY_METRICS_FILE",
    "KIDNEY_MODEL_FILE",
    "KIDNEY_NOTE_FRAGMENTS",
    "TRI_STATE_HYPERTENSION",
    "VARIANT_BY_AVAILABILITY",
    "KidneyPredictor",
]
