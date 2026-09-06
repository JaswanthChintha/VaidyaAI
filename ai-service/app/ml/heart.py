"""Module 11 -- the Heart Disease Predictor.

Loads the Random Forest pipelines built by `ml/train_heart.py` and turns one
probability into one `ClinicalDecision`. It does not fit anything, ever.

==========================================================================
THE THING TO READ FIRST: "Heart Disease" MEANS TWO DIFFERENT THINGS
==========================================================================

Module 8's `RULE_HEART_DISEASE_RISK_FACTORS` already emits
`condition="Heart Disease"`, and it is a TALLY OF RISK FACTORS -- "three of the
six things we can check are present". This predictor emits the SAME condition
string and is a DISEASE-LIKELIHOOD estimate -- "the model puts this patient at
p=0.71". Module 16 fuses by condition name, so the two WILL merge, and merging
a burden count with a probability without saying so would let a reader read one
as the other.

The condition string is deliberately NOT changed -- renaming it would break
fusion, which is the one thing Module 16 exists to do. Instead the distinction
is made explicit and machine-readable on every decision this predictor emits::

    metadata["assessment_kind"] = "disease_likelihood"

`ASSESSMENT_KIND_LIKELIHOOD` is the constant. Module 8's rule decisions do not
carry the key at all; Modules 16/17 should read a MISSING `assessment_kind` as
`risk_factor_burden` and surface the difference rather than averaging across
it. `metadata["assessment_kind_note"]` carries the same statement in prose so
it survives into the metrics artifact and into Module 20.

==========================================================================
THE MODEL IS WEAK, AND THE REASON IS BLOOD PRESSURE
==========================================================================

Held-out ROC-AUC is 0.697. The identical model WITH the dataset's systolic and
diastolic blood pressure scores 0.800. VaidyaAI collects neither: Module 2 does
not ask, `feature_catalog.py` has no such feature, and Module 4 does not
extract it from a laboratory report. Training on `ap_hi` would have meant
median-imputing the model's most important input for every real patient, and
publishing a 0.80 ROC-AUC for a model that never runs.

So the shipped model excludes blood pressure, the cost is measured rather than
hidden (`blood_pressure_reference_model` in the metrics artifact), and this
predictor should be read as a COARSE indicator built from age, BMI and a
three-level cholesterol band. `metadata.model_performance_reference` carries
the real numbers onto every decision so Module 20 cannot present it as more
than it is.

==========================================================================
THE CHOLESTEROL TRAP
==========================================================================

The training dataset's `cholesterol` column is an ORDINAL BAND -- 1 normal,
2 above normal, 3 well above normal. VaidyaAI's `cholesterol` feature is TOTAL
cholesterol in mg/dL. Handing a 212 mg/dL value to a forest trained on 1/2/3
would put every real patient beyond the largest split point and silently
flatten the feature to a constant.

`cholesterol_band()` is the mapping layer, and it is the only place the
conversion happens. Cut-offs are NCEP ATP III's total-cholesterol bands, which
is the same reference `app/data/validation_rules.py` and Module 8's cholesterol
rule already use:

    < 200 mg/dL      -> 1  desirable
    200 - 239 mg/dL  -> 2  borderline high
    >= 240 mg/dL     -> 3  high

Those are also the dataset's own three labels in the same order, which is why
this mapping is a translation rather than an invention. Boundary behaviour
(199.9 -> 1, 200.0 -> 2, 239.9 -> 2, 240.0 -> 3) is asserted in
`tests/test_heart_predictor.py`.

==========================================================================
SMOKING IS TRI-STATE HERE TOO
==========================================================================

The dataset has a binary `smoke` (currently smokes / does not). Module 2 has a
six-valued `smoking_history`, one value of which -- `no_info` -- means nobody
asked, and another -- `ever` -- is genuinely ambiguous about the present.

    never, former, not_current  -> 0
    current                     -> 1
    ever, no_info, absent       -> UNKNOWN

An UNKNOWN does not become 0. Following Module 10, the artifact holds TWO
fitted pipelines -- `with_smoking` and `without_smoking` -- and the variant
whose ColumnTransformer lacks the smoking column is used when the answer is
unknown. The matrix handed to the forest never contains a value nobody gave.

The honest footnote: `smoking_current` carries 0.5% of this model's global
importance and the two variants differ by 0.002 ROC-AUC. The machinery is
correctness at no measurable cost; smoking is a spec feature, not a driver, in
THIS model.

==========================================================================
INFORMATION SUFFICIENCY
==========================================================================

`required_features = ("age", "bmi", "cholesterol")`.

Those three carry 98.4% of the model's global importance between them, and
there is nothing else of substance left: blanking one of them at prediction
time costs 0.049 (age), 0.019 (bmi) or 0.027 (cholesterol) ROC-AUC against a
total headroom of 0.197 over chance. A "prediction" made from two of the three
plus two median-imputed stand-ins would be mostly a statement about the
training cohort. So the predictor SKIPS.

`gender` and `smoking_history` are optional: 0.011 and 0.005 importance, and
blanking either moves ROC-AUC by less than 0.001.

==========================================================================
CONFIDENCE SEMANTICS -- READ THIS BEFORE USING THE FIELD
==========================================================================

`ClinicalDecision.confidence` is ALWAYS the model's probability of the POSITIVE
class, exactly as in Module 10 -- never "how sure the model is of whatever it
concluded". A NOT_INDICATED decision therefore carries a LOW number, and that
number means "low probability of cardiovascular disease", i.e. a confident
negative. `metadata.confidence_semantics` records this on every decision.
"""

from __future__ import annotations

import math

from typing import Any, Dict, List, Mapping, Optional, Tuple

from app.data import conditions as C
from app.data.recommendation_catalog import (
    CONFIRM_WITH_REPEAT_TESTING,
    DISCUSS_WITH_CLINICIAN,
    GENERAL_BALANCED_DIET,
    GENERAL_DIETARY_FAT_QUALITY,
    GENERAL_PHYSICAL_ACTIVITY,
    GENERAL_SMOKING_CESSATION_SUPPORT,
    INPUT_QUALITY_CAVEAT,
    MONITOR_OVER_TIME,
    NOTHING_FLAGGED_EDUCATIONAL,
    NOT_A_DIAGNOSIS,
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
from app.schemas.decisions import (
    ClinicalDecision,
    DecisionSourceKind,
    DecisionStatus,
    EvidenceItem,
    RiskLevel,
)
from app.schemas.fusion import BASIS_MODEL_PROBABILITY, BASIS_NOT_ASSESSED

HEART_MODEL_FILE = "heart_rf_v2.joblib"
HEART_METRICS_FILE = "heart_rf_v2.metrics.json"

#: THE key that stops Module 16 conflating a risk-factor tally with a
#: probability. See the module docstring.
ASSESSMENT_KIND_KEY = "assessment_kind"
ASSESSMENT_KIND_LIKELIHOOD = "disease_likelihood"

#: Module 15/16's own vocabulary for the same distinction. Module 16 already
#: DEFAULTS a machine-learning decision to `model_probability`, so fusion works
#: without this -- but a default is an assumption, and this states it. The
#: constants are imported rather than spelled out so a rename in
#: `app/schemas/fusion.py` fails loudly here instead of silently reverting
#: these decisions to the default.
#:
#: On the SKIP path the basis is `not_assessed`: no model ran, so claiming
#: `model_probability` would assert a probability that does not exist.
ASSESSMENT_BASIS_KEY = "assessment_basis"

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
NOTE_CHOLESTEROL_BANDED = (
    "this value was grouped into a normal / above normal / well above normal "
    "band before the model used it"
)
NOTE_QUESTIONABLE = "this value was marked less reliable when the report was read"
NOTE_EXTREME_HIGH = (
    "this value is far above the usual range and was flagged for priority"
)

HEART_NOTE_FRAGMENTS: Tuple[str, ...] = (
    NOTE_MODEL_INPUT,
    NOTE_IMPUTED,
    NOTE_NOT_ASSERTED,
    NOTE_UNRECOGNISED_CATEGORY,
    NOTE_CHOLESTEROL_BANDED,
    NOTE_QUESTIONABLE,
    NOTE_EXTREME_HIGH,
)

#: What an absent categorical becomes: a token the encoder has never seen, so
#: `handle_unknown="ignore"` turns it into an all-zero block ("no category
#: asserted") rather than the most-frequent category.
ABSENT_CATEGORY = "__absent__"

# --------------------------------------------------------------------------
# The mg/dL -> ordinal band mapping. THE one place this conversion happens.
# --------------------------------------------------------------------------

#: NCEP ATP III total-cholesterol cut-offs, in mg/dL. Lower edge of band 2 and
#: lower edge of band 3.
CHOLESTEROL_BAND_CUTOFFS: Tuple[float, float] = (200.0, 240.0)

CHOLESTEROL_BAND_LABELS: Dict[int, str] = {
    1: "normal (< 200 mg/dL)",
    2: "above normal (200-239 mg/dL)",
    3: "well above normal (>= 240 mg/dL)",
}


def cholesterol_band(mg_dl: Any) -> Optional[int]:
    """TOTAL cholesterol in mg/dL -> the dataset's ordinal band 1 / 2 / 3.

    Returns None when the value is absent or unparseable, in which case the
    sufficiency gate has already refused (cholesterol is required) or the
    median imputer takes over.

    The cut-offs are inclusive at the lower edge: exactly 200.0 is band 2 and
    exactly 240.0 is band 3, matching how ATP III states them ("200-239
    borderline high", "240 and above high").
    """
    value = _as_float(mg_dl)
    if value is None:
        return None
    borderline, high = CHOLESTEROL_BAND_CUTOFFS
    if value >= high:
        return 3
    if value >= borderline:
        return 2
    return 1


# --------------------------------------------------------------------------
# Smoking: six Module 2 categories -> binary / unknown
# --------------------------------------------------------------------------

#: Module 2 category -> the dataset's binary `smoke`. Absent from this map
#: means UNKNOWN, which selects the `without_smoking` variant.
SMOKING_TO_CURRENT: Dict[str, int] = {
    "never": 0,
    "former": 0,
    "not_current": 0,
    "current": 1,
}

#: Deliberately unmapped, with the reason, so a future reader does not "fix" it.
SMOKING_UNKNOWN_REASON: Dict[str, str] = {
    "ever": (
        "'ever smoked' covers current and former smokers alike, so it does not "
        "determine the dataset's current-smoker flag"
    ),
    "no_info": "the patient was never asked",
}

TRI_STATE_SMOKING = "smoking_history"

#: THE v2 ARTIFACT SHIPS ONE PIPELINE, so both answers select it.
#:
#: v1 was trained on cardio_train, which carried a smoking column, and shipped
#: `with_smoking` / `without_smoking` so a patient who had answered the question
#: was scored by a model that had actually seen it. v2 is trained on NHANES-CVD,
#: which has no smoking column at all. Keeping two names here would advertise a
#: choice the artifact cannot honour: both would resolve to the same fitted
#: pipeline, and a decision stamped `with_smoking` would claim an input the
#: model never saw. v1's two variants differed by 0.002 ROC-AUC.
#:
#: The MAP IS KEPT rather than deleted because the tri-state smoking answer is
#: still read, still normalised, and still recorded in the decision trace -- as
#: `not_asserted`, which is the truth: the patient may well have answered, and
#: this model does not use it. Restoring real variants means changing only this
#: table and retraining on a cohort that has the column.
VARIANT_BY_AVAILABILITY: Dict[bool, str] = {
    True: "with_smoking",
    False: "without_smoking",
}


def normalise_category(value: Any) -> Optional[str]:
    """Module 2 spelling -> the token the encoder was fitted on.

    `"No Info"` and `"not current"` become `no_info` / `not_current`. Skipping
    this is a SILENT failure: `handle_unknown="ignore"` would quietly zero the
    mismatch and nothing would raise.
    """
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    return text.replace(" ", "_").replace("-", "_")


def smoking_current(value: Any) -> Optional[int]:
    """Module 2 `smoking_history` -> 1 / 0 / None(unknown)."""
    token = normalise_category(value)
    if token is None:
        return None
    return SMOKING_TO_CURRENT.get(token)


class HeartPredictor(Predictor):
    """Spec Module 11. Random Forest, one `ClinicalDecision` per call."""

    name = "heart_rf"
    condition = C.HEART_DISEASE  # byte-for-byte canonical; never spelled out
    source_label = "Random Forest"
    version = "1.0.0"

    #: See "INFORMATION SUFFICIENCY" above. These are CANONICAL feature names,
    #: not model column names -- `cholesterol` arrives in mg/dL and is banded.
    required_features: Tuple[str, ...] = ("age", "bmi", "cholesterol")
    optional_features: Tuple[str, ...] = ("gender", "smoking_history")

    def __init__(self, artifact_filename: str = HEART_MODEL_FILE) -> None:
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
            "synthetic_rows": dataset.get("synthetic_rows"),
            "resampling": dataset.get("resampling"),
            "blood_pressure_excluded": True,
            "blood_pressure_exclusion_reason": (
                "VaidyaAI collects no blood pressure, so training on it would "
                "median-impute the model's strongest input for every patient. "
                "Measured cost of the exclusion: about 0.10 ROC-AUC."
            ),
        }

    # -- variant selection: THE tri-state decision ------------------------

    def select_variant(
        self, features: Mapping[str, Any]
    ) -> Tuple[str, Optional[int], Optional[str]]:
        """Which fitted pipeline matches what this patient actually answered.

        Returns the variant name, the resolved 0/1/None smoking flag, and the
        normalised token that produced it (for the decision's trace).
        """
        token = normalise_category(features.get(TRI_STATE_SMOKING))
        current = SMOKING_TO_CURRENT.get(token) if token is not None else None
        return VARIANT_BY_AVAILABILITY[current is not None], current, token

    # -- the model frame --------------------------------------------------

    def _model_row(
        self, features: Mapping[str, Any], variant_name: str
    ) -> Tuple[Any, Dict[str, Any]]:
        """Build the ONE-ROW frame handed to the pipeline, plus a trace of how.

        The trace is keyed by CANONICAL feature name (`cholesterol`, not
        `cholesterol_band`) so evidence and Module 16's dedup line up with
        every other producer, and it records where each model column's value
        came from. Evidence and metadata are built from the trace, so what the
        decision claims and what the model received cannot drift apart.
        """
        import numpy as np
        import pandas as pd

        bundle = self.artifact
        if bundle is None:  # pragma: no cover - guarded by is_available()
            raise PredictorError("heart model artifact is not loaded")
        spec = bundle.variants.get(variant_name)
        if spec is None:
            raise PredictorError(
                f"the heart artifact has no variant {variant_name!r}; it has "
                f"{sorted(bundle.variants)}"
            )

        numeric: List[str] = list(spec["numeric_features"])
        categorical: List[str] = list(spec["categorical_features"])
        trace: Dict[str, Any] = {}
        row: Dict[str, Any] = {}

        for column in numeric:
            if column == "cholesterol_band":
                raw = features.get("cholesterol")
                band = cholesterol_band(raw)
                if band is None:
                    row[column] = np.nan
                    trace["cholesterol"] = {
                        "status": "imputed",
                        "value": None,
                        "model_column": column,
                    }
                else:
                    row[column] = float(band)
                    trace["cholesterol"] = {
                        "status": "banded",
                        "value": _as_float(raw),
                        "model_column": column,
                        "band": band,
                        "band_label": CHOLESTEROL_BAND_LABELS[band],
                    }
                continue
            if column == "smoking_current":
                # Only reachable in the with_smoking variant, which is only
                # selected when the answer is actually known.
                current = smoking_current(features.get(TRI_STATE_SMOKING))
                row[column] = float(current)  # type: ignore[arg-type]
                trace[TRI_STATE_SMOKING] = {
                    "status": "observed",
                    "value": normalise_category(features.get(TRI_STATE_SMOKING)),
                    "model_column": column,
                }
                continue
            number = _as_float(features.get(column))
            if number is None:
                row[column] = np.nan
                trace[column] = {
                    "status": "imputed",
                    "value": None,
                    "model_column": column,
                }
            else:
                row[column] = number
                trace[column] = {
                    "status": "observed",
                    "value": number,
                    "model_column": column,
                }

        known_levels = _known_levels(bundle)
        for column in categorical:
            token = normalise_category(features.get(column))
            if token is None:
                row[column] = ABSENT_CATEGORY
                trace[column] = {
                    "status": "not_asserted",
                    "value": None,
                    "model_column": column,
                }
            elif token in known_levels.get(column, ()):
                row[column] = token
                trace[column] = {
                    "status": "observed",
                    "value": token,
                    "model_column": column,
                }
            else:
                # e.g. gender="prefer_not_to_say", which Module 2 allows and
                # this dataset has no equivalent for. Passed through unchanged
                # so handle_unknown="ignore" makes it an all-zero block.
                row[column] = token
                trace[column] = {
                    "status": "unrecognised",
                    "value": token,
                    "model_column": column,
                }

        if "smoking_current" not in numeric:
            trace[TRI_STATE_SMOKING] = {
                "status": "not_asserted",
                "value": normalise_category(features.get(TRI_STATE_SMOKING)),
                "model_column": None,
            }

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
        see `ml/train_heart.py`, which also explains why Module 10's absolute
        0.90-precision target is NOT reused here (at 50% prevalence and
        ROC-AUC 0.70 no threshold reaches it, so the rule would degenerate to
        its own fallback branch).

          * `indicated`  = the smallest threshold whose cumulative precision
            reaches 1.5x the cohort's base rate -- "half again as likely as
            average". On the shipped `with_smoking` model that lands at 0.673
            and achieves precision 0.750.
          * `borderline` = the LARGEST threshold whose cumulative recall is
            still >= 0.95, i.e. below that line the model would still have
            caught 95 of every 100 positives. It lands at 0.285.

        Measured band composition on the 13,988-row held-out test split
        (variant `with_smoking`), recorded in the metrics artifact:

            low      1,716 patients,   362 positive (21.1%)
            medium   9,678 patients, 4,691 positive (48.5%)
            high     2,594 patients, 1,937 positive (74.7%)

        Read that honestly. The cohort is 50% positive, so the middle band is
        the base rate and means NOT RULED OUT, not "elevated". The Low band
        holds only 12% of the cohort at a 21% positive rate: this model rarely
        rules heart disease out, and it never says "safe". That is the direct
        consequence of training without blood pressure, and
        `metadata.band_meaning` carries it forward so Module 20 cannot render
        the bands as more discriminating than they are.
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
        variant_name, current, smoking_token = self.select_variant(features)
        frame, trace = self._model_row(features, variant_name)

        pipeline = bundle.pipelines[variant_name]
        probability = float(pipeline.predict_proba(frame)[0][1])

        borderline, indicated = self._thresholds(bundle, variant_name)
        status, risk, band_name = self.band(probability, borderline, indicated)

        # The share of true positives the Indicated threshold actually flags.
        # THIS MODEL'S IS 0.268, and carrying it is the whole point: it is what
        # `ModelLimitations.recall_at_operating_threshold` reads to decide
        # whether to raise "an unflagged result rules nothing out". It was
        # previously dropped between the artifact (which records it) and the
        # published threshold pair (which did not), so that caveat could never
        # fire -- for the one model that most needs it. A clinician reading a
        # low probability from a model that misses ~73% of true positives as
        # reassurance has been misled. Surfaced by tests/test_doctor_summary.py.
        # Read by ONE shared reader that knows every place an artifact may
        # record these, because per-model reasoning about this exact question
        # produced 6o D8 and then 6p. Absent figures stay absent.
        achieved = operating_metrics(bundle.variants[variant_name])
        achieved_performance = performance_figures(bundle.variants[variant_name])

        spec = bundle.variants[variant_name]
        importance = _canonical_importance(
            dict(spec.get("global_feature_importance", {}))
        )

        evidence = self._evidence(trace, importance, context)
        recommendations = self._recommendations(status, context, trace, current)

        metrics = spec.get("metrics", {}) or {}
        metadata: Dict[str, Any] = {
            "predictor": self.name,
            "predictor_version": self.version,
            "skipped": False,
            "model": self.model_provenance(),
            ASSESSMENT_KIND_KEY: ASSESSMENT_KIND_LIKELIHOOD,
            ASSESSMENT_BASIS_KEY: BASIS_MODEL_PROBABILITY,
            "assessment_kind_note": (
                "This decision estimates the LIKELIHOOD of cardiovascular "
                "disease. Module 8's RULE_HEART_DISEASE_RISK_FACTORS emits the "
                "same condition string from a COUNT OF RISK FACTORS. Both are "
                "legitimate and they are not the same quantity. A decision "
                "carrying no assessment_kind key should be read as a "
                "risk-factor burden, not as a probability."
            ),
            "variant": variant_name,
            "variant_reason": (
                (
                    "chosen by whether the patient's smoking history determines "
                    f"CURRENT smoking: smoking_history={smoking_token or 'not recorded'}"
                    + (
                        ""
                        if current is not None
                        else " (does not determine current smoking, so the "
                        "variant fitted WITHOUT a smoking column was used -- no "
                        "value was assumed)"
                    )
                )
                if len(bundle.pipelines) > 1
                # ONE pipeline means there was no choice to make, and saying a
                # smoking answer selected it would credit an input this
                # artifact never saw.
                else (
                    "this artifact ships a single pipeline, so no variant "
                    "selection took place; smoking history was not an input to "
                    "it"
                )
            ),
            "probability_positive": probability,
            "confidence_semantics": "probability_of_positive_class",
            "confidence_note": (
                "confidence is P(positive) and is NOT 'how sure the model is'. "
                "A low value on a Not Indicated decision means a confident "
                "negative."
            ),
            # An achieved figure the artifact does not record is OMITTED rather
            # than sent as null: consumers read a missing value as "not
            # recorded", while a null would be a claim that there is no recall,
            # which is a different statement.
            #
            # This comment previously added "(Module 10's does not)". THAT WAS
            # FALSE and it cost a real defect: Module 10's artifact records
            # recall, precision, accuracy and the majority-class baseline, just
            # under `metrics.positive_class` rather than under `thresholds`.
            # Believing the comment is why the 6o D8 fix stopped at two models
            # and left the third reporting a probability with no statement of
            # what it misses. The lookup now lives in
            # `app/ml/operating_metrics.py`, which knows both shapes, so no
            # comment here has to be right about another model's artifact.
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
            # HOW THE CUT-OFFS WERE CHOSEN IS THE ARTIFACT'S FACT, NOT THIS
            # FILE'S. It was hard-coded here and described v1's
            # precision/recall-curve procedure; v2 chooses percentiles of the
            # out-of-fold distribution, so the sentence became false the moment
            # the artifact changed -- while still being reported on every
            # decision. Anything that varies per artifact is now read FROM the
            # artifact, with a fallback that claims nothing.
            "threshold_basis": spec.get(
                "threshold_basis",
                # v1's procedure, correct for the cardio_train artifact. A newer
                # artifact that chooses its cut-offs differently publishes its
                # own `threshold_basis` and overrides this.
                "indicated = smallest out-of-fold threshold whose cumulative "
                "precision reaches 1.5x the cohort base rate; borderline = "
                "largest out-of-fold threshold holding 0.95 cumulative recall. "
                "Neither is a round number; both are read off the measured "
                "precision-recall curve.",
            ),
            "risk_band": band_name,
            "band_meaning": _band_meaning(spec, band_name),
            # Only meaningful when the model actually consumes a BAND. v2 is
            # trained on continuous mg/dL, so emitting the NCEP mapping would
            # describe a transformation that did not happen.
            **(
                {
                    "cholesterol_band_mapping": {
                        "cutoffs_mg_dl": list(CHOLESTEROL_BAND_CUTOFFS),
                        "basis": (
                            "NCEP ATP III total cholesterol: <200 desirable, "
                            "200-239 borderline high, >=240 high. This "
                            "artifact's cholesterol column is an ORDINAL BAND "
                            "(1/2/3), not mg/dL."
                        ),
                        "band": trace.get("cholesterol", {}).get("band"),
                    }
                }
                if "cholesterol_band" in spec.get("numeric_features", ())
                else {}
            ),
            "features_observed": sorted(
                n for n, t in trace.items() if t["status"] in ("observed", "banded")
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
                "artifact": "ml/artifacts/heart_rf_v2.metrics.json",
                # THIS STRING IS SCANNED BEFORE IT REACHES A CLINICIAN.
                # `doctor_summary` runs `scan_text` over the artifact's honest
                # read and WITHHOLDS the whole note if anything trips, so a
                # careless phrase does not get flagged -- it deletes the
                # model's own statement of its limits from the document that
                # most needs it. An earlier draft said "SELF-REPORTED physician
                # diagnosis", which the Module 24 scanner correctly reads as a
                # diagnostic assertion; the fact is kept, the phrasing is not.
                "honest_read": (
                    "A COARSE discriminator: held-out ROC-AUC about 0.84 at a "
                    "realistic 9% prevalence. Precision at the Indicated "
                    "cut-off is about 0.37, so most patients it flags will NOT "
                    "have heart disease -- a high score is a reason to discuss "
                    "testing with a clinician, never a finding. It learned from "
                    "what respondents said a doctor had told them, so it misses "
                    "people not yet identified. Blood pressure, the strongest "
                    "known predictor, is still not collected by VaidyaAI."
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
        """The base skip, plus the fusion-disambiguating key.

        Module 16 must be able to tell a skipped LIKELIHOOD decision from a
        skipped RISK-COUNT decision too, so `assessment_kind` is stamped on the
        INSUFFICIENT_DATA path as well as the assessed one.
        """
        metadata = {
            ASSESSMENT_KIND_KEY: ASSESSMENT_KIND_LIKELIHOOD,
            ASSESSMENT_BASIS_KEY: BASIS_NOT_ASSESSED,
            "assessment_kind_note": (
                "This predictor estimates the LIKELIHOOD of cardiovascular "
                "disease and did not run. Module 8's "
                "RULE_HEART_DISEASE_RISK_FACTORS emits the same condition "
                "string from a COUNT OF RISK FACTORS. A decision carrying no "
                "assessment_kind key should be read as a risk-factor burden, "
                "not as a probability."
            ),
        }
        metadata.update(extra_metadata or {})
        return super().insufficient_decision(
            report, context, extra_metadata=metadata
        )

    # -- evidence ---------------------------------------------------------

    def _evidence(
        self,
        trace: Dict[str, Any],
        importance: Dict[str, float],
        context: PredictionContext,
    ) -> List[EvidenceItem]:
        """One item per feature the model was given, most important first.

        Absent features are listed too: "the model was not told whether you
        smoke" is exactly the sort of thing spec Module 20 exists to show.
        `threshold` stays None throughout -- `decisions.py` reserves it for
        rule-based producers, and no single threshold explains a forest.
        """
        order = sorted(trace, key=lambda name: (-importance.get(name, 0.0), name))
        items: List[EvidenceItem] = []
        for name in order:
            entry = trace[name]
            status = entry["status"]
            note = {
                "observed": NOTE_MODEL_INPUT,
                "banded": NOTE_CHOLESTEROL_BANDED,
                "imputed": NOTE_IMPUTED,
                "not_asserted": NOTE_NOT_ASSERTED,
                "unrecognised": NOTE_UNRECOGNISED_CATEGORY,
            }[status]
            if status in ("observed", "banded") and name in context.questionable:
                note = NOTE_QUESTIONABLE
            elif status in ("observed", "banded") and name in context.clinically_extreme:
                note = NOTE_EXTREME_HIGH
            items.append(
                EvidenceItem(
                    feature=name,
                    value=entry["value"],
                    unit=(
                        context.unit_for(name)
                        if status in ("observed", "banded")
                        else None
                    ),
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
        current_smoker: Optional[int],
    ):
        """Codes only. No code path here composes text.

        Note what is deliberately NOT here: `SEEK_PROMPT_MEDICAL_ADVICE`.
        Module 10 attaches it to an INDICATED diabetes decision, where the
        model's precision at the cut-off is ~0.91. This model's is 0.75 on a
        50%-prevalence cohort, so an urgency instruction would be unsupported
        certainty -- exactly what spec section 24 forbids. A weak model gets
        `DISCUSS_WITH_CLINICIAN`, not an alarm.
        """
        if status is DecisionStatus.INDICATED:
            codes: Tuple[str, ...] = (
                DISCUSS_WITH_CLINICIAN,
                CONFIRM_WITH_REPEAT_TESTING,
                GENERAL_PHYSICAL_ACTIVITY,
                GENERAL_DIETARY_FAT_QUALITY,
                GENERAL_BALANCED_DIET,
            )
        elif status is DecisionStatus.BORDERLINE:
            codes = (
                DISCUSS_WITH_CLINICIAN,
                MONITOR_OVER_TIME,
                GENERAL_PHYSICAL_ACTIVITY,
                GENERAL_BALANCED_DIET,
            )
        else:
            codes = (NOTHING_FLAGGED_EDUCATIONAL, MONITOR_OVER_TIME)

        # Attached only on a POSITIVELY stated current smoking history, never
        # on an unknown one -- the same rule the rest of this file applies to
        # the tri-state.
        if current_smoker == 1 and status is not DecisionStatus.NOT_INDICATED:
            codes += (GENERAL_SMOKING_CESSATION_SUPPORT,)

        if any(name in context.questionable for name in trace):
            codes += (INPUT_QUALITY_CAVEAT,)
        # Attached to EVERY decision, exactly as Module 8 and Module 10 do.
        return resolve_recommendations(codes + (NOT_A_DIAGNOSIS,))


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _band_meaning(spec, band_name: str) -> str:
    """What this band means FOR THE LOADED ARTIFACT.

    Prefers the figures the artifact measured on its own held-out split. The
    module-level `_BAND_MEANING` below is v1's text and quotes cardio_train's
    50% prevalence; using it for any other artifact states a false rate beside
    a patient's result, which is exactly how it went stale when v2 landed.
    """
    recorded = spec.get("band_meaning") if hasattr(spec, "get") else None
    if isinstance(recorded, dict):
        text = recorded.get(band_name)
        if isinstance(text, str) and text:
            return text
    return _BAND_MEANING.get(
        band_name, "this artifact records no meaning for this band"
    )


#: v1 ONLY. Kept as the fallback for the cardio_train artifact; every figure in
#: it is that dataset's. A new artifact must publish its own `band_meaning`.
_BAND_MEANING = {
    "low": (
        "Below the sensitivity-derived cut-off. On the held-out test split "
        "21.1% of patients in this band were positive, against a cohort "
        "prevalence of 50.0%. This band holds only 12% of the cohort: this "
        "model rarely rules heart disease out."
    ),
    "medium": (
        "Between the two cut-offs: NOT RULED OUT rather than elevated. On the "
        "held-out test split 48.5% of patients in this band were positive, "
        "which is the cohort base rate."
    ),
    "high": (
        "At or above the precision-derived cut-off. On the held-out test split "
        "74.7% of patients in this band were positive, against a cohort "
        "prevalence of 50.0%."
    ),
}

#: model column -> canonical feature name, for importance and evidence keys.
_COLUMN_TO_FEATURE: Dict[str, str] = {
    "cholesterol_band": "cholesterol",
    "smoking_current": "smoking_history",
}


def _canonical_importance(importance: Dict[str, float]) -> Dict[str, float]:
    """Re-key the artifact's model-column importances to canonical features."""
    out: Dict[str, float] = {}
    for column, value in importance.items():
        name = _COLUMN_TO_FEATURE.get(column, column)
        out[name] = out.get(name, 0.0) + float(value)
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


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


def _known_levels(bundle) -> Dict[str, Tuple[str, ...]]:
    """Categories the encoder was actually fitted on, from the artifact."""
    dataset = bundle.get("dataset", {}) or {}
    return {"gender": tuple(dataset.get("gender_levels", ()))}


__all__ = [
    "ABSENT_CATEGORY",
    "ASSESSMENT_BASIS_KEY",
    "ASSESSMENT_KIND_KEY",
    "ASSESSMENT_KIND_LIKELIHOOD",
    "CHOLESTEROL_BAND_CUTOFFS",
    "CHOLESTEROL_BAND_LABELS",
    "HEART_METRICS_FILE",
    "HEART_MODEL_FILE",
    "HEART_NOTE_FRAGMENTS",
    "SMOKING_TO_CURRENT",
    "TRI_STATE_SMOKING",
    "VARIANT_BY_AVAILABILITY",
    "HeartPredictor",
    "cholesterol_band",
    "normalise_category",
    "smoking_current",
]
