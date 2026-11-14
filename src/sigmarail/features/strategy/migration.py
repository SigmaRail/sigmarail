"""PortfolioDocument persistence: decompile legacy specs + persist the source.

The persisted model is the two-column split from the plan (§7, §9):

- ``algorithm_json``  — the compiled VeraLabV1 (run artifact, cached).
- ``portfolio_json``  — the ``PortfolioDocument`` (authoring source of truth).

``decompile_specs`` is the pure, DB-free transform; ``import_from_db`` reads
legacy specs, decompiles them, and (optionally) re-inserts the same rows with
``portfolio_json`` populated (ReplacingMergeTree dedups on ``ir_id`` via FINAL).
"""

from __future__ import annotations

import json
from typing import Any

from .decompiler import decompile_portfolio

# Version stamp recorded alongside the cached algorithm_json so a future
# round-trip can detect when a spec predates a compiler change.
COMPILER_VERSION = "portfolio-v1"


def decompile_specs(specs: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """Decompile legacy VeraLabV1 specs into PortfolioDocuments.

    ``specs`` is a list of ``(ir_id, algorithm_json)``. Returns one result per
    spec: ``{ir_id, ok, portfolio_json, error}``.
    """
    results: list[dict[str, Any]] = []
    for ir_id, algorithm_json in specs:
        try:
            spec = json.loads(algorithm_json)
            doc = decompile_portfolio(spec)
            results.append(
                {
                    "ir_id": ir_id,
                    "ok": True,
                    "portfolio_json": json.dumps(doc.model_dump(), separators=(",", ":")),
                    "error": None,
                }
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                {"ir_id": ir_id, "ok": False, "portfolio_json": None, "error": str(exc)}
            )
    return results


def import_from_db(client: Any, *, persist: bool = True) -> dict[str, Any]:
    """Read all legacy specs, decompile, and (optionally) persist portfolio_json.

    Re-inserts the original ``algorithm_json``/``title``/``notes`` unchanged and
    adds the decompiled ``portfolio_json`` — so the import never changes what
    runs, it only adds the source-of-truth sidecar.
    """
    rows = client.query(
        "SELECT ir_id, spec_schema_version, title, notes, algorithm_json"
        " FROM strategy_algorithm_specs FINAL"
    )
    originals = {r[0]: r for r in rows.result_rows}
    results = decompile_specs([(r[0], r[4]) for r in rows.result_rows])

    if persist:
        ok = [r for r in results if r["ok"]]
        if ok:
            client.insert(
                "strategy_algorithm_specs",
                [
                    [
                        r["ir_id"],
                        originals[r["ir_id"]][1],  # spec_schema_version
                        originals[r["ir_id"]][2],  # title
                        originals[r["ir_id"]][4],  # algorithm_json (preserved)
                        originals[r["ir_id"]][3],  # notes
                        r["portfolio_json"],
                        COMPILER_VERSION,
                    ]
                    for r in ok
                ],
                column_names=[
                    "ir_id",
                    "spec_schema_version",
                    "title",
                    "algorithm_json",
                    "notes",
                    "portfolio_json",
                    "compiler_version",
                ],
            )

    return {
        "total": len(results),
        "ok": sum(1 for r in results if r["ok"]),
        "failed": sum(1 for r in results if not r["ok"]),
        "results": results,
    }
