"""Module 13 -- the Predictor Registry.

    PredictorRegistry
           |
           +-- DiabetesPredictor      (Module 10)
           +-- HeartPredictor         (Module 11 -- add one line below)
           +-- KidneyPredictor        (Module 12 -- add one line below)

Spec Module 13: "Instead of hard-coding every model inside the analysis
process, predictors are registered dynamically... The AI Engine can then
iterate over registered predictors. This creates a plugin-like architecture
where future predictors can be added with minimal changes to the main system."

==========================================================================
WHAT "MINIMAL CHANGES" MEANS CONCRETELY HERE
==========================================================================

To add Module 11's heart predictor, an author writes `app/ml/heart.py` with a
`Predictor` subclass and adds ONE line to `_register_defaults()` below.

Nothing else changes. Not `predict_all()`, not `routes_ml.py`, not the response
schema, not the summary code, not a single test of the engine. The engine only
ever does `for predictor in registry:` -- it has no knowledge of which
predictors exist, and `tests/test_ml_registry.py` proves that by running the
whole engine over a fake predictor for a different condition and asserting its
decision comes out the other end untouched.

==========================================================================
ORDERING
==========================================================================

Registration order is preserved (`dict` insertion order) and the engine sorts
its output by `condition_rank()` afterwards, so output is stable across runs
regardless of import order. Two predictors MAY share a condition -- e.g. two
models for Diabetes -- and Module 16 will fuse them; the registry key is the
predictor NAME, not the condition, precisely so that stays possible.
"""

from __future__ import annotations

import threading
from typing import Dict, Iterator, List, Optional, Tuple

from app.data import conditions as C
from app.ml.base import Predictor, PredictorError


class DuplicatePredictorError(PredictorError):
    """A second predictor was registered under a name already in use.

    Not a silent overwrite. Silently replacing a registered predictor would
    make the analysis depend on import order, which is the kind of bug that
    only shows up in production.
    """


class UnknownPredictorError(PredictorError, KeyError):
    """Lookup by a name that was never registered."""


class PredictorRegistry:
    """A mutable, iterable collection of predictors keyed by name.

    Thread-safe for registration because the default registry is a module-level
    singleton that FastAPI workers may touch concurrently at import time.
    Iteration returns a snapshot list, so a registration during a run cannot
    mutate a sequence being walked.
    """

    def __init__(self) -> None:
        self._predictors: Dict[str, Predictor] = {}
        self._lock = threading.RLock()

    # -- mutation ---------------------------------------------------------

    def register(self, predictor: Predictor, *, replace: bool = False) -> Predictor:
        """Add a predictor. Returns it, so it can be used as an expression."""
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

    # -- lookup -----------------------------------------------------------

    def get(self, name: str) -> Predictor:
        try:
            return self._predictors[name]
        except KeyError:
            raise UnknownPredictorError(
                f"no predictor named {name!r} is registered. Registered: "
                f"{sorted(self._predictors)}"
            ) from None

    def find(self, name: str) -> Optional[Predictor]:
        """Like `get`, but returns None instead of raising."""
        return self._predictors.get(name)

    def for_condition(self, condition: str) -> List[Predictor]:
        """Every predictor registered for one canonical condition."""
        return [p for p in self._predictors.values() if p.condition == condition]

    def conditions(self) -> Tuple[str, ...]:
        """Canonical conditions covered, in canonical order, without repeats."""
        seen: Dict[str, None] = {}
        for predictor in self._predictors.values():
            seen.setdefault(predictor.condition, None)
        return tuple(sorted(seen, key=C.condition_rank))

    def names(self) -> Tuple[str, ...]:
        return tuple(self._predictors)

    # -- iteration --------------------------------------------------------

    def __iter__(self) -> Iterator[Predictor]:
        # Snapshot: a registration mid-run must not mutate what is being walked.
        return iter(list(self._predictors.values()))

    def __len__(self) -> int:
        return len(self._predictors)

    def __contains__(self, item: object) -> bool:
        if isinstance(item, Predictor):
            return self._predictors.get(item.name) is item
        return item in self._predictors

    # -- introspection ----------------------------------------------------

    def describe(self) -> dict:
        """Payload for `GET /api/v1/ml/predictors`. No PHI, shape only."""
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

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<PredictorRegistry {list(self._predictors)}>"


# --------------------------------------------------------------------------
# The default registry
# --------------------------------------------------------------------------


def build_default_registry() -> PredictorRegistry:
    """A FRESH registry populated with the shipped predictors.

    Tests use this to get an isolated registry rather than mutating the
    singleton, so one test cannot leak a fake predictor into another.
    """
    registry = PredictorRegistry()
    _register_defaults(registry)
    return registry


def _register_defaults(registry: PredictorRegistry) -> None:
    """THE ONE PLACE Modules 11 and 12 touch.

    Adding a predictor is a single line here plus its own module::

        from app.ml.heart import HeartPredictor      # Module 11
        registry.register(HeartPredictor())

        from app.ml.kidney import KidneyPredictor    # Module 12
        registry.register(KidneyPredictor())

    Imported inside the function rather than at module scope so that importing
    the registry never drags a model artifact into memory as a side effect.
    """
    from app.ml.diabetes import DiabetesPredictor  # Module 10
    from app.ml.heart import HeartPredictor  # Module 11
    from app.ml.kidney import KidneyPredictor  # Module 12

    registry.register(DiabetesPredictor())
    registry.register(HeartPredictor())
    registry.register(KidneyPredictor())


_DEFAULT_REGISTRY: Optional[PredictorRegistry] = None
_DEFAULT_LOCK = threading.Lock()


def default_registry() -> PredictorRegistry:
    """The process-wide registry the HTTP layer uses. Built once, lazily."""
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
