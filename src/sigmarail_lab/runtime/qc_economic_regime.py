"""Economic-environment regime source (Dalio 4-quadrant classification).

Maps growth/inflation deltas to the four All-Weather environments. The pure
core is ``classify_environment``; a ``EconomicEnvironmentRegimeSource`` wraps it
for the runtime and can be backed by a macro dataset later.
"""

from __future__ import annotations

from typing import Any


def classify_environment(
    growth: float,
    inflation: float,
    *,
    growth_threshold: float = 0.0,
    inflation_threshold: float = 0.0,
) -> str:
    """Classify the economic environment from growth/inflation deltas.

    Returns one of:
      - ``reflation``    (growth up,   inflation up)
      - ``goldilocks``   (growth up,   inflation down)
      - ``stagflation``  (growth down, inflation up)
      - ``deflation``    (growth down, inflation down)
    """
    g_up = growth >= growth_threshold
    i_up = inflation >= inflation_threshold
    if g_up and i_up:
        return "reflation"
    if g_up and not i_up:
        return "goldilocks"
    if not g_up and i_up:
        return "stagflation"
    return "deflation"


class EconomicEnvironmentRegimeSource:
    """Runtime regime source: returns the current quadrant for a given date.

    The default implementation reads growth/inflation deltas from the store
    (``growth_delta`` / ``inflation_delta``) when available; otherwise it is
    neutral. A macro dataset can be wired later without changing callers.
    """

    def __init__(self, store: Any = None):
        self._store = store

    def classify(self, as_of: str) -> str:
        if self._store is not None:
            quadrant = getattr(self._store, "economic_quadrant", lambda d: "")(as_of)
            if quadrant:
                return str(quadrant)
            growth = float(getattr(self._store, "growth_delta", lambda d: 0.0)(as_of) or 0.0)
            inflation = float(getattr(self._store, "inflation_delta", lambda d: 0.0)(as_of) or 0.0)
            return classify_environment(growth, inflation)
        return classify_environment(0.0, 0.0)
