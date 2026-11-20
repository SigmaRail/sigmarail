#!/usr/bin/env python3
"""Backfill PCM rules/size_expr into stored specs (C-FW-RULES Phase 2).

For every ``strategy_algorithm_specs`` row whose PCM is
``RiskBudgetedPortfolioConstructionModel`` and whose ``Parameters`` lack an
authored ``rules`` table or ``size_expr``, injects the generated allocation
table via ``screens.pcm_rules.materialize_pcm_rules`` (the same bridge the save
path uses), then mirrors it into ``pipeline_json.sizing`` and fills rule
descriptions so stored specs self-describe the decision surface that ran.

Write model: ``strategy_algorithm_specs`` is ``ReplacingMergeTree(created_at)``
— the backfill re-INSERTs the full row with the mutated ``algorithm_json`` /
``pipeline_json`` (newest ``created_at`` wins under ``FINAL``). Same ir_id =
in-place patch, not a fork.

Side effect to be aware of: ``strategy_runs.ir_content_hash`` is the sha256 of
the *old* ``algorithm_json``, so runs on touched specs will report "stale
revision" — accurate at the byte level, semantically a no-op (the runtime had
regenerated the identical table internally). Dry-run reports each spec's run
count so the blast radius is visible before applying.

Usage:
    python scripts/backfill_pcm_rules.py              # dry-run report
    python scripts/backfill_pcm_rules.py --apply      # write
    python scripts/backfill_pcm_rules.py --ir-id strat-x --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_PCM_TYPE = "RiskBudgetedPortfolioConstructionModel"
_CHANGELOG = "backfill: materialized PCM rules/size_expr (C-FW-RULES Phase 2)"
_AUTHOR = "backfill-pcm-rules"


def _describe_columns(client: Any) -> list[str]:
    rows = client.query("DESCRIBE TABLE strategy_algorithm_specs").result_rows
    return [r[0] for r in rows]


def _count_runs(client: Any, ir_id: str) -> int:
    rows = client.query(
        "SELECT count() FROM strategy_runs FINAL WHERE ir_id = %(ir_id)s",
        parameters={"ir_id": ir_id},
    ).result_rows
    return int(rows[0][0]) if rows else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write rows (default: dry-run)")
    parser.add_argument("--ir-id", default=None, help="scope to one spec")
    args = parser.parse_args()

    from screens.ch import get_ch_client
    from screens.pcm_rules import (
        hydrate_pcm_rule_descriptions,
        materialize_pcm_rules,
        seed_pipeline_pcm_rules,
    )

    client = get_ch_client()
    try:
        columns = _describe_columns(client)
        selectable = [c for c in columns if c != "created_at"]
        where = " WHERE ir_id = %(ir_id)s" if args.ir_id else ""
        params = {"ir_id": args.ir_id} if args.ir_id else {}
        rows = client.query(
            f"SELECT {', '.join(selectable)} FROM strategy_algorithm_specs FINAL{where}",
            parameters=params,
        )
        idx = {c: i for i, c in enumerate(selectable)}

        scanned = changed = written = 0
        for row in rows.result_rows:
            rec = dict(zip(selectable, row))
            ir_id = rec["ir_id"]
            try:
                spec = json.loads(rec.get("algorithm_json") or "{}")
            except Exception:
                continue
            pcm = (spec.get("Framework") or {}).get("PortfolioConstruction") or {}
            if pcm.get("Type") != _PCM_TYPE:
                continue
            scanned += 1
            p = pcm.get("Parameters") or {}
            needs_rules = p.get("rules") is None
            needs_size = p.get("size_expr") is None

            doc: dict[str, Any] | None = None
            if rec.get("pipeline_json"):
                try:
                    doc = json.loads(rec["pipeline_json"])
                except Exception:
                    doc = None

            spec_changed = materialize_pcm_rules(spec)
            filled = hydrate_pcm_rule_descriptions(spec, doc)
            doc_changed = seed_pipeline_pcm_rules(spec, doc) if doc is not None else False
            if not (spec_changed or filled or doc_changed):
                continue
            changed += 1
            runs = _count_runs(client, ir_id)
            rules_n = len(((spec.get("Framework") or {}).get("PortfolioConstruction") or {})
                          .get("Parameters", {}).get("rules") or [])
            print(
                f"{ir_id}: +rules={needs_rules} +size_expr={needs_size} "
                f"desc_filled={filled} doc_seeded={doc_changed} "
                f"ladder={rules_n} rules — {runs} run(s) will flag stale",
            )

            if not args.apply:
                continue
            rec["algorithm_json"] = json.dumps(spec, separators=(",", ":"), sort_keys=True)
            if doc is not None:
                rec["pipeline_json"] = json.dumps(doc, separators=(",", ":"), sort_keys=True)
            rec["mutation_type"] = "patch"
            rec["changelog_notes"] = _CHANGELOG
            rec["author_agent"] = _AUTHOR
            cols = [c for c in selectable if c in rec]
            client.insert(
                "strategy_algorithm_specs",
                [[rec[c] for c in cols]],
                column_names=cols,
            )
            written += 1

        verb = "written" if args.apply else "would be rewritten"
        print(f"\n{scanned} RiskBudgeted spec(s) scanned, {changed} changed, {written} {verb}.")
        if not args.apply and changed:
            print("dry-run — re-run with --apply to write.")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
