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
    stem = model_filename[: -len(".joblib")] if model_filename.endswith(
        ".joblib"
    ) else model_filename
    return f"{stem}.metrics.json"


def verify_artifact_integrity(filename: str) -> Dict[str, Any]:
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

    path: Path
    bundle: Dict[str, Any]
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
                import joblib

                bundle = joblib.load(path)
                if not isinstance(bundle, dict) or "pipelines" not in bundle:
                    reason = (
                        f"model artifact {filename!r} does not have the expected "
                        "shape (a dict carrying 'pipelines')"
                    )
                else:
                    integrity = verify_artifact_integrity(filename)
                    if integrity.get("status") == INTEGRITY_MISMATCH:
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
            except Exception as exc:
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
    path = artifact_path(filename)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.error("ml_metrics_unreadable %s", safe_meta(artifact=filename))
        return None


def reset_cache() -> None:
    with _LOCK:
        _CACHE.clear()
        _REASONS.clear()


def artifact_integrity(filename: str = DIABETES_MODEL_FILE) -> Dict[str, Any]:
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
