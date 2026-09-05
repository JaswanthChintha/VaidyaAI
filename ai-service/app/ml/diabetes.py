"""Module 10 -- the Diabetes Predictor.

Loads the Random Forest pipeline built by `ml/train_diabetes.py` and turns one
probability into one `ClinicalDecision`. It does not fit anything, ever.

==========================================================================
THE TRI-STATE PROBLEM, AND WHAT THIS FILE DOES ABOUT IT
==========================================================================

Module 2 stores `hypertension` and `heart_disease` as TRUE / FALSE / ABSENT,
where absent means "the patient never answered". The training dataset has only
0 and 1 -- it has no way to say "unknown".

Encoding an absent answer as 0 would tell the forest "this patient does not
have hypertension" when nobody ever asked. Median-imputing the column is the
same act with better manners: the median of a 92%-zero column IS 0.

So the artifact contains FOUR fitted pipelines, one per availability pattern:

    both  |  hypertension_only  |  heart_disease_only  |  neither

Each was fitted on the same real rows, and each variant's ColumnTransformer
simply does not contain the column(s) that variant cannot know. `_model_row()`
picks the variant matching what the patient actually answered, and builds a
one-row frame containing ONLY that variant's columns. The matrix handed to the
forest therefore never contains a value that was not observed -- not a zero,
not a median, nothing. `tests/test_diabetes_predictor.py` asserts this against
the real frame, not against the intention.

WHY THIS IS DIFFERENT FROM IMPUTING `bmi` OR `age`. Imputing a continuous
MEASUREMENT substitutes a population value for an unmeasured quantity: a
documented statistical choice, and the one spec section 10 explicitly asks
for. Imputing a boolean CLINICAL FINDING invents a diagnosis the patient never
gave. Those are different acts and this file does not treat them the same way.

The honest footnote, measured and recorded in the metrics artifact: the
`neither` variant scores ROC-AUC 0.9734 against `both`'s 0.9738. Dropping the
tri-state pair costs essentially nothing, because HbA1c and blood glucose carry
almost all of the signal. The variant machinery therefore buys correctness at
no measurable accuracy cost -- which is the best possible outcome, but it also
means nobody should claim these two features are doing much work.

==========================================================================
INFORMATION SUFFICIENCY
==========================================================================

`required_features = ("hba1c", "blood_glucose")`.

Those two carry ~69% of the model's global importance between them. If either
is absent, the median imputer would substitute a population value for THE most
discriminative input, and the resulting probability would be driven mostly by
a number that came from the training set rather than from the patient. Spec
Module 12's principle -- a model trained on several parameters is not equally
reliable on a subset -- applies squarely, so the predictor SKIPS.

That is not a gap in the report. Module 8's rule engine assesses `Diabetes`
from whichever of the two IS present, and `Diabetes` is marked
`always_assessed` in `app/data/conditions.py`, so the topic still reaches the
reader with a deterministic decision attached. Only the ML opinion is withheld.

==========================================================================
CONFIDENCE SEMANTICS -- READ THIS BEFORE USING THE FIELD
==========================================================================

`ClinicalDecision.confidence` is ALWAYS the model's probability of the POSITIVE
class, never "how sure the model is of whatever it concluded". So a
NOT_INDICATED decision carries a LOW number (e.g. 0.03), and that number means
"3% probability of diabetes", i.e. a confident negative -- not a shaky verdict.

`decisions.py` defines the field as "Model probability in [0,1]" and Module 16
fuses on it, so a consistent, single-directional meaning is the only workable
choice; flipping it for negatives would make two decisions about the same
condition incomparable. `metadata.confidence_semantics` records this on every
decision so Module 20 cannot render it wrongly by accident.
"""

from __future__ import annotations

import math

from typing import Any, Dict, List, Mapping, Optional, Tuple

from app.data import conditions as C
from app.data.recommendation_catalog import (
    CONFIRM_WITH_REPEAT_TESTING,
    DISCUSS_WITH_CLINICIAN,
    GENERAL_BALANCED_DIET,
    GENERAL_LIMIT_ADDED_SUGAR,
    GENERAL_PHYSICAL_ACTIVITY,
    INPUT_QUALITY_CAVEAT,
    MONITOR_OVER_TIME,
    NOTHING_FLAGGED_EDUCATIONAL,
    NOT_A_DIAGNOSIS,
    SEEK_PROMPT_MEDICAL_ADVICE,
    recommendations as resolve_recommendations,
)
from app.ml.artifacts import (
    DIABETES_MODEL_FILE,
    load_failure_reason,
    load_model,
)
from app.ml.operating_metrics import (
    operating_metrics,
    performance_figures,
)
from app.ml.base import (
    EMPTY_CONTEXT,
    PredictionContext,
    Predictor,
    PredictorError,
)
from app.schemas.decisions import (
    ClinicalDecision,
    DecisionSourceKind,
    DecisionStatus,
    EvidenceItem,
    RiskLevel,
)

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
NOTE_UNRECOGNISED_CATEGORY = (
    "this answer is not one the model was built on, so no category was "
    "assumed for it"
)
NOTE_QUESTIONABLE = (
    "this value was marked less reliable when the report was read"
)
NOTE_EXTREME_HIGH = (
    "this value is far above the usual range and was flagged for priority"
)
NOTE_EXTREME_LOW = (
    "this value is far below the usual range and was flagged for priority"
)

DIABETES_NOTE_FRAGMENTS: Tuple[str, ...] = (
    NOTE_MODEL_INPUT,
    NOTE_IMPUTED,
    NOTE_NOT_ASSERTED,
    NOTE_UNRECOGNISED_CATEGORY,
    NOTE_QUESTIONABLE,
    NOTE_EXTREME_HIGH,
    NOTE_EXTREME_LOW,
)

#: What a categorical feature becomes when it is absent entirely. Deliberately
#: a token the encoder has never seen, so `handle_unknown="ignore"` turns it
#: into an all-zero block -- "no category asserted". It is NOT handed to the
#: most-frequent imputer, which would assert the majority category instead.
ABSENT_CATEGORY = "__absent__"

#: The tri-state pair, in the order the variant key is built from.
TRI_STATE: Tuple[str, str] = ("hypertension", "heart_disease")

#: (has_hypertension, has_heart_disease) -> artifact variant name.
VARIANT_BY_AVAILABILITY: Dict[Tuple[bool, bool], str] = {
    (True, True): "both",
    (True, False): "hypertension_only",
    (False, True): "heart_disease_only",
    (False, False): "neither",
}


def normalise_category(value: Any) -> Optional[str]:
    """Module 2 / dataset spelling -> the token the encoder was fitted on.

    `"No Info"`, `"NOT CURRENT"` and `"not current"` all become `no_info` /
    `not_current`. Skipping this is a SILENT failure: the profile sends
    `no_info`, the encoder was fitted on whatever the training script produced,
    and `handle_unknown="ignore"` quietly zeroes the mismatch. Nothing raises;
    the feature just stops existing. The training script applies the identical
    transformation to the dataset, and a test asserts both directions.
    """
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    return text.replace(" ", "_").replace("-", "_")


class DiabetesPredictor(Predictor):
    """Spec Module 10. Random Forest, one `ClinicalDecision` per call."""

    name = "diabetes_rf"
    condition = C.DIABETES  # byte-for-byte canonical; never spelled out here
    source_label = "Random Forest"
    version = "1.0.0"

    #: See "INFORMATION SUFFICIENCY" above.
    required_features: Tuple[str, ...] = ("hba1c", "blood_glucose")
    optional_features: Tuple[str, ...] = (
        "age",
        "bmi",
        "gender",
        "smoking_history",
        "hypertension",
        "heart_disease",
    )

    def __init__(self, artifact_filename: str = DIABETES_MODEL_FILE) -> None:
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
        """Trainable-to-prediction traceability, for decision metadata."""
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
            "synthetic_rows": dataset.get("synthetic_rows"),
            "resampling": dataset.get("resampling"),
        }

    # -- variant selection: THE tri-state decision ------------------------

    @staticmethod
    def _tri_state(value: Any) -> Optional[bool]:
        """A tri-state feature's value, or None for 'the patient never said'.

        ONLY a real bool counts. Module 5 preserves the tri-state by ABSENCE
        from the feature map, and Module 6 keeps booleans as booleans, so
        anything that is not a `bool` here (a `None`, a stray `"unknown"`, a
        `0` that arrived as an int from a sloppy caller) is treated as UNKNOWN
        rather than coerced.

        Note what is deliberately NOT done: `bool(value)` would turn the string
        `"false"` into True and `0` into False. Both would fabricate an answer.
        """
        if isinstance(value, bool):
            return value
        return None

    def select_variant(self, features: Mapping[str, Any]) -> Tuple[str, Dict[str, Optional[bool]]]:
        """Which fitted pipeline matches what this patient actually answered."""
        known = {name: self._tri_state(features.get(name)) for name in TRI_STATE}
        key = (known["hypertension"] is not None, known["heart_disease"] is not None)
        return VARIANT_BY_AVAILABILITY[key], known

    # -- the model frame --------------------------------------------------

    def _model_row(
        self, features: Mapping[str, Any], variant_name: str
    ) -> Tuple[Any, Dict[str, Any]]:
        """Build the ONE-ROW frame handed to the pipeline, plus a trace of how.

        The trace records, per feature, whether the value came from the patient
        (`observed`), was left for the median imputer (`imputed`), was an
        unrecognised category (`unrecognised`), or was excluded from the model
        entirely (`not_asserted`). Evidence and metadata are built from the
        trace, so what the decision claims and what the model actually received
        cannot drift apart.
        """
        import numpy as np
        import pandas as pd

        bundle = self.artifact
        if bundle is None:  # pragma: no cover - guarded by is_available()
            raise PredictorError("diabetes model artifact is not loaded")
        spec = bundle.variants.get(variant_name)
        if spec is None:
            raise PredictorError(
                f"the diabetes artifact has no variant {variant_name!r}; it "
                f"has {sorted(bundle.variants)}"
            )

        numeric: List[str] = list(spec["numeric_features"])
        categorical: List[str] = list(spec["categorical_features"])
        trace: Dict[str, Any] = {}
        row: Dict[str, Any] = {}

        for name in numeric:
            if name in TRI_STATE:
                # Only reachable when this variant includes the column, which
                # only happens when the patient supplied a real bool.
                value = self._tri_state(features.get(name))
                row[name] = int(value)  # type: ignore[arg-type]
                trace[name] = {"status": "observed", "value": value}
                continue
            raw = features.get(name)
            number = _as_float(raw)
            if number is None:
                row[name] = np.nan
                trace[name] = {"status": "imputed", "value": None}
            else:
                row[name] = number
                trace[name] = {"status": "observed", "value": number}

        known_levels = _known_levels(bundle, categorical)
        for name in categorical:
            token = normalise_category(features.get(name))
            if token is None:
                row[name] = ABSENT_CATEGORY
                trace[name] = {"status": "not_asserted", "value": None}
            elif token in known_levels.get(name, ()):
                row[name] = token
                trace[name] = {"status": "observed", "value": token}
            else:
                # e.g. gender="prefer_not_to_say", which Module 2 allows and the
                # dataset has no equivalent for. Passed through unchanged so the
                # encoder's handle_unknown="ignore" makes it an all-zero block.
                row[name] = token
                trace[name] = {"status": "unrecognised", "value": token}

        # Excluded from THIS variant because the patient never answered.
        for name in TRI_STATE:
            if name not in numeric:
                trace[name] = {"status": "not_asserted", "value": None}

        frame = pd.DataFrame([row], columns=numeric + categorical)
        return frame, trace

    # -- risk banding -----------------------------------------------------

    @staticmethod
    def _thresholds(bundle, variant_name: str) -> Tuple[float, float]:
        spec = bundle.variants[variant_name]
        thresholds = spec["thresholds"]
        return float(thresholds["borderline"]), float(thresholds["indicated"])

    @staticmethod
    def band(
        probability: float, borderline: float, indicated: float
    ) -> Tuple[DecisionStatus, RiskLevel, str]:
        """probability -> (status, risk, band name).

        Both cut-offs are read off the artifact, and both were derived from the
        measured precision-recall curve of a held-out validation split rather
        than chosen as round numbers. See `ml/train_diabetes.py`:

          * `indicated`  = the smallest threshold whose cumulative precision
            reaches 0.90, so roughly nine in ten people flagged INDICATED in a
            cohort like the training one are truly positive. On the shipped
            model that lands at 0.795; the F1-maximising threshold on the same
            data is 0.793, so the cut-off is insensitive to which criterion is
            used, which is the strongest evidence it is not an artefact of the
            choice.
          * `borderline` = the LARGEST threshold whose cumulative recall is
            still >= 0.99, so "below this line" means the model would still
            have caught 99 of every 100 positives. It lands at 0.117.

        The asymmetry is the point. The upper cut-off is set by precision
        because a false INDICATED costs an unnecessary worry; the lower one is
        set by sensitivity because a false NOT_INDICATED is false reassurance,
        which `app/schemas/decisions.py` calls the most dangerous failure this
        type can have.

        Measured band composition on the 19,230-row held-out test split
        (variant `both`), recorded in the metrics artifact:

            low     11,713 patients,   12 positive  ( 0.10%)
            medium   6,209 patients,  492 positive  ( 7.92%)
            high     1,308 patients, 1192 positive  (91.13%)

        Read that honestly. The middle band means "NOT RULED OUT", not
        "elevated": its own positive rate (7.9%) is a shade BELOW the cohort
        prevalence of 8.8%, because everyone genuinely high-scoring has already
        been pulled out into the high band. It is mapped to
        BORDERLINE/MEDIUM because those are the vocabulary `decisions.py`
        offers, and `metadata.band_meaning` carries the real meaning forward so
        Module 20 can render it without overclaiming.
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
        variant_name, tri_known = self.select_variant(features)
        frame, trace = self._model_row(features, variant_name)

        pipeline = bundle.pipelines[variant_name]
        probability = float(pipeline.predict_proba(frame)[0][1])

        borderline, indicated = self._thresholds(bundle, variant_name)
        status, risk, band_name = self.band(probability, borderline, indicated)

        spec = bundle.variants[variant_name]
        importance: Dict[str, float] = dict(spec.get("global_feature_importance", {}))

        evidence = self._evidence(trace, importance, context)
        recommendations = self._recommendations(status, context, trace)

        metrics = spec.get("metrics", {}) or {}
        metadata: Dict[str, Any] = {
            "predictor": self.name,
            "predictor_version": self.version,
            "skipped": False,
            "model": self.model_provenance(),
            "variant": variant_name,
            "variant_reason": (
                "chosen by which tri-state answers the patient actually gave: "
                f"hypertension={_tri_word(tri_known['hypertension'])}, "
                f"heart_disease={_tri_word(tri_known['heart_disease'])}. A "
                "variant that excludes a column was fitted without it, so no "
                "value was assumed for an unanswered question."
            ),
            "probability_positive": probability,
            "confidence_semantics": "probability_of_positive_class",
            "confidence_note": (
                "confidence is P(positive) and is NOT 'how sure the model is'. "
                "A low value on a Not Indicated decision means a confident "
                "negative."
            ),
            "thresholds": {
                "borderline": borderline,
                "indicated": indicated,
                # ACHIEVED RECALL AND PRECISION AT THIS CUT-OFF. This model
                # published neither until 6p, so a clinician read a probability
                # against a 0.795 threshold with no statement that it catches
                # ~70% of true positives -- and `metrics_available` was True
                # with no absent-code, so nothing signalled the gap. The
                # numbers were in the artifact the whole time, under
                # `metrics.positive_class` rather than under `thresholds`;
                # the shared reader knows both shapes.
                **operating_metrics(spec),
            },
            "threshold_basis": (
                "indicated = smallest validation threshold reaching 0.90 "
                "cumulative precision; borderline = largest validation "
                "threshold holding 0.99 cumulative recall. Both measured on a "
                "held-out split, neither chosen as a round number."
            ),
            "risk_band": band_name,
            "band_meaning": _BAND_MEANING[band_name],
            "features_observed": sorted(
                n for n, t in trace.items() if t["status"] == "observed"
            ),
            "features_imputed": sorted(
                n for n, t in trace.items() if t["status"] == "imputed"
            ),
            "features_not_asserted": sorted(
                n for n, t in trace.items() if t["status"] == "not_asserted"
            ),
            "features_unrecognised_category": sorted(
                n for n, t in trace.items() if t["status"] == "unrecognised"
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
                "measured_on": "held-out test split, see the metrics artifact",
                "variant": variant_name,
                "roc_auc": metrics.get("roc_auc"),
                "pr_auc_average_precision": metrics.get("pr_auc_average_precision"),
                "positive_class": metrics.get("positive_class"),
                # Accuracy WITH its baseline. 0.968 against a 0.912
                # majority-class baseline is a lift of 5.6 points, and the
                # first number alone reads as far stronger than the pair does.
                **performance_figures(spec),
                "artifact": "ml/artifacts/diabetes_rf_v1.metrics.json",
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

    # -- evidence ---------------------------------------------------------

    def _evidence(
        self,
        trace: Dict[str, Any],
        importance: Dict[str, float],
        context: PredictionContext,
    ) -> List[EvidenceItem]:
        """One item per feature the model was given, most important first.

        Every feature is listed, INCLUDING the ones that were absent, because
        "the model was not told whether you have hypertension" is exactly the
        sort of thing spec Module 20 exists to show. `threshold` is None
        throughout: `decisions.py` reserves it for rule-based producers, and no
        single threshold explains a forest.
        """
        order = sorted(
            trace,
            key=lambda name: (-importance.get(name, 0.0), name),
        )
        items: List[EvidenceItem] = []
        for name in order:
            entry = trace[name]
            status = entry["status"]
            note = {
                "observed": NOTE_MODEL_INPUT,
                "imputed": NOTE_IMPUTED,
                "not_asserted": NOTE_NOT_ASSERTED,
                "unrecognised": NOTE_UNRECOGNISED_CATEGORY,
            }[status]
            if status == "observed" and name in context.questionable:
                note = NOTE_QUESTIONABLE
            elif status == "observed" and name in context.clinically_extreme:
                note = NOTE_EXTREME_HIGH
            items.append(
                EvidenceItem(
                    feature=name,
                    value=entry["value"],
                    unit=context.unit_for(name) if status == "observed" else None,
                    threshold=None,
                    comparator=None,
                    note=note,
                    source_stage="model_input" if status != "not_asserted" else "not_available",
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

        `recommendation_catalog.recommendation()` takes a CODE and raises on an
        unknown one, so nothing this predictor can do -- now or after a future
        edit -- can emit unvetted medical wording.
        """
        if status is DecisionStatus.INDICATED:
            codes: Tuple[str, ...] = (
                DISCUSS_WITH_CLINICIAN,
                SEEK_PROMPT_MEDICAL_ADVICE,
                CONFIRM_WITH_REPEAT_TESTING,
                GENERAL_LIMIT_ADDED_SUGAR,
                GENERAL_PHYSICAL_ACTIVITY,
            )
        elif status is DecisionStatus.BORDERLINE:
            codes = (
                DISCUSS_WITH_CLINICIAN,
                CONFIRM_WITH_REPEAT_TESTING,
                MONITOR_OVER_TIME,
                GENERAL_LIMIT_ADDED_SUGAR,
                GENERAL_BALANCED_DIET,
            )
        else:
            codes = (NOTHING_FLAGGED_EDUCATIONAL, MONITOR_OVER_TIME)

        if any(name in context.questionable for name in trace):
            codes += (INPUT_QUALITY_CAVEAT,)
        # NOT_A_DIAGNOSIS is attached to EVERY decision, exactly as Module 8
        # does. This is a decision-support tool, and it says so every time.
        return resolve_recommendations(codes + (NOT_A_DIAGNOSIS,))


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

_BAND_MEANING = {
    "low": (
        "Below the sensitivity-derived cut-off. On the held-out test split "
        "0.10% of patients in this band were positive."
    ),
    "medium": (
        "Between the two cut-offs: NOT RULED OUT rather than elevated. On the "
        "held-out test split 7.9% of patients in this band were positive, "
        "against a cohort prevalence of 8.8%."
    ),
    "high": (
        "At or above the precision-derived cut-off. On the held-out test split "
        "91.1% of patients in this band were positive."
    ),
}


def _as_float(value: Any) -> Optional[float]:
    """A usable number, or None. `bool` is NOT a number here.

    Python makes `isinstance(True, int)` true, so without the explicit guard a
    stray boolean would silently become 1.0 in a numeric column.
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


def _known_levels(bundle, categorical: List[str]) -> Dict[str, Tuple[str, ...]]:
    """Categories the encoder was actually fitted on, from the artifact."""
    dataset = bundle.get("dataset", {}) or {}
    return {
        "gender": tuple(dataset.get("gender_levels", ())),
        "smoking_history": tuple(dataset.get("smoking_history_levels", ())),
    }


__all__ = [
    "ABSENT_CATEGORY",
    "DIABETES_NOTE_FRAGMENTS",
    "NOTE_IMPUTED",
    "NOTE_MODEL_INPUT",
    "NOTE_NOT_ASSERTED",
    "NOTE_UNRECOGNISED_CATEGORY",
    "TRI_STATE",
    "VARIANT_BY_AVAILABILITY",
    "DiabetesPredictor",
    "normalise_category",
]
