"""PRELOAD_ON_STARTUP (2026-10-06).

On Render's free plan the first analysis loaded the ML models mid-request,
took ~30 s, and the backend's stage timeout turned the report "partial". With
the setting on, the models and the knowledge index are loaded during startup
-- before the port opens -- and nothing is loaded lazily on a patient's time.
"""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main
from app.ml import artifacts
from app.rag import retriever


def _start(monkeypatch, preload: bool) -> None:
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(preload_on_startup=preload))
    artifacts.reset_cache()
    retriever.reset_index_cache()
    with TestClient(main.app):
        pass


def test_preload_on_loads_every_model_before_serving(monkeypatch):
    _start(monkeypatch, preload=True)
    loaded = {key for key, value in artifacts._CACHE.items() if value is not None}
    names = {k.replace("\\", "/").rsplit("/", 1)[-1] for k in loaded}
    assert {"diabetes_rf_v1.joblib", "kidney_rf_v1.joblib"} <= names
    assert any(n.startswith("heart_rf_") for n in names)
    assert retriever._INDEX is not None


def test_preload_off_loads_nothing_at_startup(monkeypatch):
    _start(monkeypatch, preload=False)
    assert artifacts._CACHE == {}


def test_a_preload_failure_does_not_stop_the_service(monkeypatch):
    def boom():
        raise RuntimeError("index missing")

    monkeypatch.setattr(retriever, "get_index", lambda *a, **k: boom())
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(preload_on_startup=True))
    with TestClient(main.app) as client:
        assert client.get("/api/v1/health").status_code == 200


def test_the_setting_defaults_to_off():
    from app.config import Settings

    assert Settings.model_fields["preload_on_startup"].default is False
