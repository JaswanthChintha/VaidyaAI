from __future__ import annotations

import threading
from typing import Dict, Iterator, List, Optional, Tuple

from app.data import conditions as C
from app.ml.base import Predictor, PredictorError


class DuplicatePredictorError(PredictorError):
    pass


class UnknownPredictorError(PredictorError, KeyError):
    pass


class PredictorRegistry:

    def __init__(self) -> None:
        self._predictors: Dict[str, Predictor] = {}
        self._lock = threading.RLock()


    def register(self, predictor: Predictor, *, replace: bool = False) -> Predictor:
        if not isinstance(predictor, Predictor):
            raise PredictorError(
                f"{type(predictor).__name__} is not a Predictor subclass. The "
                "registry only accepts app.ml.base.Predictor instances, which "
                "is what guarantees every registered predictor inherits the "
                "information-sufficiency gate."
            )
        name = predictor.name
        with self._lock:
            if name in self._predictors and not replace:
                raise DuplicatePredictorError(
                    f"a predictor named {name!r} is already registered "
                    f"({type(self._predictors[name]).__name__}). Pass "
                    "replace=True to substitute it deliberately."
                )
            self._predictors[name] = predictor
        return predictor

    def unregister(self, name: str) -> Predictor:
        with self._lock:
            try:
                return self._predictors.pop(name)
            except KeyError:
                raise UnknownPredictorError(
                    f"no predictor named {name!r} is registered"
                ) from None

    def clear(self) -> None:
        with self._lock:
            self._predictors.clear()


    def get(self, name: str) -> Predictor:
        try:
            return self._predictors[name]
        except KeyError:
            raise UnknownPredictorError(
                f"no predictor named {name!r} is registered. Registered: "
                f"{sorted(self._predictors)}"
            ) from None

    def find(self, name: str) -> Optional[Predictor]:
        return self._predictors.get(name)

    def for_condition(self, condition: str) -> List[Predictor]:
        return [p for p in self._predictors.values() if p.condition == condition]

    def conditions(self) -> Tuple[str, ...]:
        seen: Dict[str, None] = {}
        for predictor in self._predictors.values():
            seen.setdefault(predictor.condition, None)
        return tuple(sorted(seen, key=C.condition_rank))

    def names(self) -> Tuple[str, ...]:
        return tuple(self._predictors)


    def __iter__(self) -> Iterator[Predictor]:
        return iter(list(self._predictors.values()))

    def __len__(self) -> int:
        return len(self._predictors)

    def __contains__(self, item: object) -> bool:
        if isinstance(item, Predictor):
            return self._predictors.get(item.name) is item
        return item in self._predictors


    def describe(self) -> dict:
        return {
            "predictor_count": len(self._predictors),
            "conditions_covered": list(self.conditions()),
            "predictors": [p.describe() for p in self._predictors.values()],
            "extensibility": (
                "Predictors are registered dynamically (spec Module 13). A new "
                "condition-specific predictor is added by subclassing "
                "app.ml.base.Predictor and registering it; the engine iterates "
                "the registry and needs no change."
            ),
        }

    def __repr__(self) -> str:
        return f"<PredictorRegistry {list(self._predictors)}>"


def build_default_registry() -> PredictorRegistry:
    registry = PredictorRegistry()
    _register_defaults(registry)
    return registry


def _register_defaults(registry: PredictorRegistry) -> None:
    from app.ml.diabetes import DiabetesPredictor
    from app.ml.heart import HeartPredictor
    from app.ml.kidney import KidneyPredictor

    registry.register(DiabetesPredictor())
    registry.register(HeartPredictor())
    registry.register(KidneyPredictor())


_DEFAULT_REGISTRY: Optional[PredictorRegistry] = None
_DEFAULT_LOCK = threading.Lock()


def default_registry() -> PredictorRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        with _DEFAULT_LOCK:
            if _DEFAULT_REGISTRY is None:
                _DEFAULT_REGISTRY = build_default_registry()
    return _DEFAULT_REGISTRY


__all__ = [
    "DuplicatePredictorError",
    "PredictorRegistry",
    "UnknownPredictorError",
    "build_default_registry",
    "default_registry",
]
