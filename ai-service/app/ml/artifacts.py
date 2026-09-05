"""Loading persisted model artifacts. NEVER trains anything.

Spec section 15 names joblib for model persistence. `ml/train_diabetes.py`
writes two files per model:

    ml/artifacts/<model>.joblib        the whole sklearn Pipeline(s) + provenance
    ml/artifacts/<model>.metrics.json  every evaluation number, auditable

The joblib file holds the COMPLETE pipeline -- imputers, encoder and forest in
one object -- so a prediction can never be made with preprocessing that does
not match the model that was fitted alongside it.

==========================================================================
LOADING POLICY
==========================================================================

* LAZY. The artifact is read on first use, not at import. Importing
  `app.ml` must not cost 15 MB of RAM in a process that never predicts.
* CACHED per path. Four Random Forests deserialise once per process.
* NEVER FATAL. A missing or unreadable artifact does not raise out of
  `load_model()`; it returns None with the reason recorded. `Predictor.
  is_available()` then reports False and every decision becomes
  INSUFFICIENT_DATA with `skipped_reason="model_unavailable"`. A deployment
  that forgot to ship the model produces visibly unassessed topics, not
  fabricated predictions and not a 500 on every report.

`ML_ARTIFACT_DIR` overrides the location (deployment, or a test pointing at a
fixture directory).
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.logging import get_logger, safe_meta

logger = get_logger(__name__)

#: `app/ml/artifacts.py` -> `app/ml` -> `app` -> the service root.
SERVICE_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_ARTIFACT_DIR = SERVICE_ROOT / "ml" / "artifacts"

DIABETES_MODEL_FILE = "diabetes_rf_v1.joblib"
DIABETES_METRICS_FILE = "diabetes_rf_v1.metrics.json"


def artifact_dir() -> Path:
    override = os.environ.get("ML_ARTIFACT_DIR", "").strip()
    return Path(override) if override else DEFAULT_ARTIFACT_DIR


def artifact_path(filename: str) -> Path:
    return artifact_dir() / filename


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------
# Artifact <-> metrics integrity (integration audit D3)
# --------------------------------------------------------------------------
#
# The training scripts write the sha256 of the joblib they produced into the
# metrics document beside it, under `model_artifact.sha256`. That digest is
# what BINDS the two files: every threshold a predictor bands with, every
# `global_feature_importance` it orders its evidence by, and every performance
# number it publishes are read from the metrics document and attributed to the
# model in the joblib. `ML_ARTIFACT_DIR` is env-overridable, so a substituted
# or retrained joblib would otherwise load in silence and be served with the
# previous model's thresholds and metrics.
#
# WHY A LOUD FLAG AND NOT A REFUSAL TO START
# ------------------------------------------
# Refusing to start was considered and rejected, for three reasons.
#
#   1. It contradicts the loading policy this module already commits to and
#      that the rest of the service is built on: NEVER FATAL. A missing or
#      corrupt artifact today produces visibly unassessed topics, not a 500 on
#      every request. Making a MISMATCHED artifact more fatal than an ABSENT
#      one would be backwards.
#   2. The blast radius is wrong. One bad joblib would take down OCR,
#      validation, Module 8's deterministic rules and the other two models --
#      all of which are unaffected by it. A patient who would have received a
#      correct rule-based anaemia finding instead receives nothing.
#   3. The failure is not silent under this design. The mismatch is logged as
#      an error, `describe()` reports it on the introspection endpoint, and
#      `integrity` rides in `model_provenance()` -- so it appears in the
#      metadata of EVERY decision the affected model produces, and Module 20
#      carries that metadata into the report. An operator sees it; an auditor
#      reading a single stored decision sees it too.
#
# The deliberate cost: a mismatched artifact still predicts. That is the right
# trade only because the flag travels WITH each decision rather than only to a
# log an operator may never read. If that ever stops being true, revisit this.

INTEGRITY_VERIFIED = "verified"
INTEGRITY_MISMATCH = "mismatch"
INTEGRITY_UNRECORDED = "no_recorded_digest"
INTEGRITY_UNCHECKED = "not_checked"

INTEGRITY_MISMATCH_CAVEAT = (
    "The model file on disk is not the one these thresholds, feature "
    "importances and performance numbers were measured on. The prediction was "
    "produced, but everything published alongside it about how the model "
    "performs may describe a different model."
)


def metrics_filename_for(model_filename: str) -> str:
    """`x_v1.joblib` -> `x_v1.metrics.json`, the naming the trainers use."""
    stem = model_filename[: -len(".joblib")] if model_filename.endswith(
        ".joblib"
    ) else model_filename
    return f"{stem}.metrics.json"


def verify_artifact_integrity(filename: str) -> Dict[str, Any]:
    """Compare the joblib on disk with the digest its metrics document records.

    Never raises and never blocks a load -- see the note above. Returns a small
    dict that is safe to embed in decision metadata: filenames and digests
    only, never a path and never anything patient-derived.
    """
    path = artifact_path(filename)
    metrics_name = metrics_filename_for(filename)
    result: Dict[str, Any] = {
        "artifact_file": filename,
        "metrics_file": metrics_name,
        "status": INTEGRITY_UNCHECKED,
        "verified": False,
        "recorded_sha256": None,
        "actual_sha256": None,
        "caveat": None,
    }

    metrics = load_metrics(metrics_name)
    recorded = None
    if isinstance(metrics, dict):
        block = metrics.get("model_artifact")
        if isinstance(block, dict):
            recorded = block.get("sha256")
    result["recorded_sha256"] = recorded

    try:
        actual = sha256_of(path)
    except OSError:
        return result
    result["actual_sha256"] = actual

    if not recorded:
        result["status"] = INTEGRITY_UNRECORDED
        return result
    if str(recorded).lower() == actual.lower():
        result["status"] = INTEGRITY_VERIFIED
        result["verified"] = True
        return result

    result["status"] = INTEGRITY_MISMATCH
    result["caveat"] = INTEGRITY_MISMATCH_CAVEAT
    return result


@dataclass(frozen=True)
class LoadedArtifact:
    """A deserialised model bundle plus where it came from."""

    path: Path
    bundle: Dict[str, Any]
    #: The artifact<->metrics sha256 check, run once at load time.
    integrity: Dict[str, Any] = field(default_factory=dict)

    @property
    def pipelines(self) -> Dict[str, Any]:
        return self.bundle.get("pipelines", {})

    @property
    def variants(self) -> Dict[str, Any]:
        return self.bundle.get("variants", {})

    def get(self, key: str, default: Any = None) -> Any:
        return self.bundle.get(key, default)


_CACHE: Dict[str, Optional[LoadedArtifact]] = {}
_REASONS: Dict[str, Optional[str]] = {}
_LOCK = threading.RLock()


def load_model(filename: str = DIABETES_MODEL_FILE) -> Optional[LoadedArtifact]:
    """Load and cache a joblib bundle. Returns None if it cannot be loaded.

    The failure path is deliberately non-fatal -- see the module docstring.
    The reason is logged once and is retrievable via `load_failure_reason()`
    for the introspection endpoint.
    """
    key = str(artifact_path(filename))
    with _LOCK:
        if key in _CACHE:
            return _CACHE[key]

        path = Path(key)
        reason: Optional[str] = None
        loaded: Optional[LoadedArtifact] = None
        if not path.exists():
            reason = (
                f"model artifact {filename!r} not found in {artifact_dir()}. Run "
                "`python ml/train_diabetes.py` to build it; it is never trained "
                "at request time."
            )
        else:
            try:
                import joblib  # imported here so `app.ml` imports without sklearn

                bundle = joblib.load(path)
                if not isinstance(bundle, dict) or "pipelines" not in bundle:
                    reason = (
                        f"model artifact {filename!r} does not have the expected "
                        "shape (a dict carrying 'pipelines')"
                    )
                else:
                    integrity = verify_artifact_integrity(filename)
                    if integrity.get("status") == INTEGRITY_MISMATCH:
                        # LOUD. The only place this can be caught, and the
                        # operator-facing half of the D3 policy above.
                        logger.error(
                            "ml_artifact_digest_mismatch %s",
                            safe_meta(
                                artifact=filename,
                                metrics=integrity.get("metrics_file"),
                                recorded_sha256=integrity.get("recorded_sha256"),
                                actual_sha256=integrity.get("actual_sha256"),
                            ),
                        )
                    elif integrity.get("status") == INTEGRITY_UNRECORDED:
                        logger.warning(
                            "ml_artifact_digest_unrecorded %s",
                            safe_meta(artifact=filename),
                        )
                    loaded = LoadedArtifact(
                        path=path, bundle=bundle, integrity=integrity
                    )
            except Exception as exc:  # noqa: BLE001 - reported, never re-raised
                # Type only. A deserialisation error message can embed paths and
                # library internals; it must not carry anything else into logs.
                reason = (
                    f"model artifact {filename!r} could not be deserialised "
                    f"({type(exc).__name__}). It may have been written by an "
                    "incompatible scikit-learn version -- retrain with "
                    "`python ml/train_diabetes.py`."
                )

        if reason:
            logger.error("ml_artifact_unavailable %s", safe_meta(artifact=filename))
        _CACHE[key] = loaded
        _REASONS[key] = reason
        return loaded


def load_failure_reason(filename: str = DIABETES_MODEL_FILE) -> Optional[str]:
    key = str(artifact_path(filename))
    if key not in _CACHE:
        load_model(filename)
    return _REASONS.get(key)


def load_metrics(filename: str = DIABETES_METRICS_FILE) -> Optional[Dict[str, Any]]:
    """The evaluation document written beside the model. None if absent."""
    path = artifact_path(filename)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        logger.error("ml_metrics_unreadable %s", safe_meta(artifact=filename))
        return None


def reset_cache() -> None:
    """Drop the process cache. For tests that repoint `ML_ARTIFACT_DIR`."""
    with _LOCK:
        _CACHE.clear()
        _REASONS.clear()


def artifact_integrity(filename: str = DIABETES_MODEL_FILE) -> Dict[str, Any]:
    """The integrity record for a loaded artifact, loading it if necessary."""
    loaded = load_model(filename)
    if loaded is None:
        return {
            "artifact_file": filename,
            "metrics_file": metrics_filename_for(filename),
            "status": INTEGRITY_UNCHECKED,
            "verified": False,
            "recorded_sha256": None,
            "actual_sha256": None,
            "caveat": None,
        }
    return dict(loaded.integrity)


__all__ = [
    "DEFAULT_ARTIFACT_DIR",
    "INTEGRITY_MISMATCH",
    "INTEGRITY_MISMATCH_CAVEAT",
    "INTEGRITY_UNCHECKED",
    "INTEGRITY_UNRECORDED",
    "INTEGRITY_VERIFIED",
    "artifact_integrity",
    "metrics_filename_for",
    "verify_artifact_integrity",
    "DIABETES_METRICS_FILE",
    "DIABETES_MODEL_FILE",
    "LoadedArtifact",
    "artifact_dir",
    "artifact_path",
    "load_failure_reason",
    "load_metrics",
    "load_model",
    "reset_cache",
    "sha256_of",
]
