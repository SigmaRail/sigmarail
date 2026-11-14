"""CI baseline VeraLabV1 JSON duplicated for LEAN Docker local runs.

QuantConnect Lean CLI only copies ``.py``, ``.cs``, ``.ipynb``, ``.css``, and ``.html``
into the engine container, so ``tests/fixtures/ir/baseline.json`` is never mounted at
``/project``. When ``SIGMARAIL_STRATEGY_PATH`` points at that fixture and the resolved file is
missing, ``resolve_sigmarail_lab`` loads this string instead.

Must stay byte-identical to ``tests/fixtures/ir/baseline.json`` (see
``tests/test_resolver_kinds.py``).
"""

from __future__ import annotations

from pathlib import Path

_FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "ir" / "baseline.json"
RAW_JSON = _FIXTURE.read_text(encoding="utf-8")
