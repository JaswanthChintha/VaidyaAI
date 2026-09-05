"""Module 31 -- Population Context and Percentile Analysis. The data layer.

Two files, split the same way `app/data/` is split from `app/services/`:

* `policy.py` -- reason codes, the deliberate exclusions, and every string a
  patient can be shown. Tables and text, no control flow, so a clinician can
  review what will be said without reading Python.
* `tables.py` -- loads `datasets/population/distributions/*.json` at import
  time and validates them, then exposes read-only lookups over them.

The arithmetic lives in `app/services/population_context.py`; nothing in this
package computes a percentile.

This package is deliberately NOT under `app/data/`. `app/data/` holds
hand-written reviewable constants; the distribution tables here are computed
from public NHANES microdata by `datasets/population/build_population_tables.py`
and are shipped as data files with recorded sha256 digests, which is a
different provenance story and deserves a different home.
"""

from __future__ import annotations

__all__: list = []
