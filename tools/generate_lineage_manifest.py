#!/usr/bin/env python3
"""Generate the SigmaRail table-and-column inventory from packaged ClickHouse SQL."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "src" / "sigmarail" / "sql" / "schema"
SCHEMA_MANIFEST = ROOT / "src" / "sigmarail" / "sql" / "schema-manifest.json"
OUTPUT = ROOT / "spec" / "lineage-manifest.json"
PACKAGE_OUTPUT = ROOT / "src" / "sigmarail" / "spec" / "lineage-manifest.json"
MODULE_OUTPUT = ROOT / "spec" / "module-manifest.json"
PACKAGE_MODULE_OUTPUT = ROOT / "src" / "sigmarail" / "spec" / "module-manifest.json"
RAW_SCHEMA_FILE = "01-schema-data-tables.sql"

CORE_OUTPUTS = [
    "screener_price_tech_daily",
    "screener_fundamentals_daily",
    "screener_ratings_daily",
    "screener_stage_weekly_daily",
    "screener_ownership_daily",
]
ADDITIONAL_SHARADAR_OUTPUTS = [
    "asset_returns_daily",
    "factor_residuals",
    "group_strength_daily",
    "sata_score",
    "screener_factor_daily",
    "screener_forecast_models_daily",
    "screener_forward_returns_daily",
    "screener_vcp_pivot_daily",
    "sector_factor_residuals_daily",
    "ticker_rvab_daily",
    "market_context_daily",
    "regime_signals_canonical",
    "symbol_technical_features_daily",
]
EXCLUDED_FIELDS = {
    "ticker_classification_daily": {
        "gic_sector": "reserved for an external GICS overlay; excluded from the Sharadar-only model",
        "gic_group": "reserved for an external GICS overlay; excluded from the Sharadar-only model",
        "gic_industry": "reserved for an external GICS overlay; excluded from the Sharadar-only model",
        "gic_subindustry": "reserved for an external GICS overlay; excluded from the Sharadar-only model",
    }
}
ESTIMATE_METRIC_COLUMNS = [
    "eps_cq_mean", "eps_nq_mean", "eps_cy_mean", "eps_ny_mean",
    "eps_cq_median", "eps_nq_median", "eps_cy_median", "eps_ny_median",
    "eps_cq_n", "eps_nq_n", "eps_cy_n", "eps_ny_n",
    "eps_cq_high", "eps_nq_high", "eps_cy_high", "eps_ny_high",
    "eps_cq_low", "eps_nq_low", "eps_cy_low", "eps_ny_low",
    "sales_cq_mean", "sales_nq_mean", "sales_cy_mean", "sales_ny_mean",
    "sales_cq_median", "sales_nq_median", "sales_cy_median", "sales_ny_median",
    "sales_cq_n", "sales_nq_n", "sales_cy_n", "sales_ny_n",
    "sales_cq_high", "sales_nq_high", "sales_cy_high", "sales_ny_high",
    "sales_cq_low", "sales_nq_low", "sales_cy_low", "sales_ny_low",
    "eps_cq_rev_pct_90d", "eps_nq_rev_pct_90d", "eps_cy_rev_pct_90d",
    "eps_ny_rev_pct_90d", "sales_nq_rev_pct_90d", "sales_ny_rev_pct_90d",
    "eps_last_reported", "eps_last_estimate", "eps_last_surprise_pct",
    "eps_beat_flag", "sales_last_reported", "sales_last_estimate",
    "sales_last_surprise_pct", "sales_beat_flag", "est_vendor", "eps_basis",
]
DEFERRED_EXTERNAL = [
    {
        "table": "screener_kb_daily",
        "direct_inputs": ["kb_daily_ticker_sentiment"],
        "included_sharadar_columns": [],
        "excluded_columns": {
            "ticker": "key is sourced from the KB ticker-sentiment extension",
            "date": "key is sourced from the KB ticker-sentiment extension",
            "lastupdated": "operational metadata for a deferred extension",
            "kb_mentions": "Knowledge Base sentiment input",
            "kb_confidence_avg": "Knowledge Base sentiment input",
            "kb_sentiment_score": "Knowledge Base sentiment input",
        },
        "reason": "Knowledge Base sentiment is deferred pending source review.",
    },
    {
        "table": "screener_estimates_daily",
        "direct_inputs": [
            "analyst_consensus_asof",
            "analyst_actuals",
            "screener_price_tech_daily",
        ],
        "included_sharadar_columns": [],
        "excluded_columns": {
            "ticker": "mixed-source spine; only emitted for analyst-covered tickers",
            "date": "mixed-source spine; only emitted for analyst-covered tickers",
            "lastupdated": "operational metadata for a deferred extension",
            **{name: "analyst consensus or actuals input" for name in ESTIMATE_METRIC_COLUMNS},
        },
        "reason": "Analyst consensus and actuals are deferred third-party inputs.",
    },
]
DEFERRED_SHARADAR_FEATURES = [
    {"table": "stock_allocation_daily", "reason": "portfolio allocation layer"},
    {"table": "sector_etf_allocation_daily", "reason": "portfolio allocation layer"},
]
DEFERRED_APPLICATION_LAYERS = [
    {"table": "regime_composed_daily", "reason": "policy-composed regime application layer"},
    {"table": "regime_backtest_generic", "reason": "regime backtest and evaluation layer"},
    {"table": "regime_backtest_enriched", "reason": "regime backtest and evaluation layer"},
    {"table": "regime_model_output_daily", "reason": "experimental regime model output"},
    {"table": "regime_model_backtest", "reason": "regime backtest and evaluation layer"},
    {"table": "regime_model_backtest_enriched", "reason": "regime backtest and evaluation layer"},
    {"table": "regime_model_scorecard_pooled", "reason": "regime backtest and evaluation layer"},
    {"table": "regime_scorecard_by_env", "reason": "regime backtest and evaluation layer"},
    {"table": "regime_scorecard_by_window", "reason": "regime backtest and evaluation layer"},
    {"table": "regime_scorecard_pooled", "reason": "regime backtest and evaluation layer"},
]


def _balanced_block(text: str, open_index: int) -> tuple[str, int]:
    depth = 0
    quote: str | None = None
    i = open_index
    while i < len(text):
        char = text[i]
        if quote:
            if char == "\\" and quote == "'":
                i += 2
                continue
            if char == quote:
                if i + 1 < len(text) and text[i + 1] == quote:
                    i += 2
                    continue
                quote = None
        elif char in "'\"`":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[open_index + 1 : i], i + 1
        i += 1
    raise ValueError("unclosed ClickHouse schema parentheses")


def _split_top_level(block: str) -> list[str]:
    items: list[str] = []
    quote: str | None = None
    depth = 0
    start = 0
    i = 0
    while i < len(block):
        char = block[i]
        if quote:
            if char == "\\" and quote == "'":
                i += 2
                continue
            if char == quote:
                if i + 1 < len(block) and block[i + 1] == quote:
                    i += 2
                    continue
                quote = None
        elif char in "'\"`":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            items.append(block[start:i].strip())
            start = i + 1
        i += 1
    tail = block[start:].strip()
    if tail:
        items.append(tail)
    return items


def _strip_sql_comments_and_literals(sql: str) -> str:
    """Keep SQL structure while removing comments and single-quoted values."""
    out: list[str] = []
    quote: str | None = None
    line_comment = False
    block_comment = False
    i = 0
    while i < len(sql):
        char = sql[i]
        following = sql[i + 1] if i + 1 < len(sql) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
                out.append(char)
            else:
                out.append(" ")
            i += 1
            continue
        if block_comment:
            if char == "*" and following == "/":
                block_comment = False
                out.extend("  ")
                i += 2
            else:
                out.append("\n" if char == "\n" else " ")
                i += 1
            continue
        if quote == "'":
            if char == "'" and following == "'":
                out.extend("  ")
                i += 2
                continue
            if char == "'":
                quote = None
            out.append(" ")
            i += 1
            continue
        if quote:
            out.append(char)
            if char == quote:
                quote = None
            i += 1
            continue
        if char == "-" and following == "-":
            line_comment = True
            out.extend("  ")
            i += 2
            continue
        if char == "/" and following == "*":
            block_comment = True
            out.extend("  ")
            i += 2
            continue
        if char in "'\"`":
            quote = char
            out.append(" " if char == "'" else char)
            i += 1
            continue
        out.append(char)
        i += 1
    return "".join(out)


def _actual_table_inputs(query: str, known: set[str]) -> tuple[list[str], list[str]]:
    """Return physical table inputs and any unresolved relation names."""
    clean = _strip_sql_comments_and_literals(query)
    clean = re.sub(r"\bARRAY\s+JOIN\b", "ARRAY_JOIN", clean, flags=re.I)
    ctes = {
        name.lower()
        for name in re.findall(
            r"(?:\bWITH(?:\s+RECURSIVE)?|,)\s*`?([A-Za-z_][\w]*)`?\s+AS\s*\(",
            clean,
            re.I,
        )
    }
    table_names = {name.lower(): name for name in known}
    safe_table_functions = {"numbers", "numbers_mt", "zeros", "zeros_mt", "values"}
    actual: list[str] = []
    unresolved: list[str] = []
    relation = re.compile(
        r"\b(?:FROM|JOIN)\s+(`?[A-Za-z_][\w]*`?(?:\s*\.\s*`?[A-Za-z_][\w]*`?)?)",
        re.I,
    )
    for match in relation.finditer(clean):
        raw = match.group(1).replace("`", "")
        source = raw.rsplit(".", 1)[-1].strip().lower()
        if source in table_names:
            name = table_names[source]
            if name not in actual:
                actual.append(name)
            continue
        if source in ctes:
            continue
        trailing = clean[match.end() :].lstrip()
        if source in safe_table_functions and trailing.startswith("("):
            continue
        if source not in unresolved:
            unresolved.append(source)
    return actual, unresolved


def _columns_from_create(sql: str, table: str) -> list[dict[str, str]]:
    match = re.search(
        rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+`?{re.escape(table)}`?\s*\(",
        sql,
        re.I,
    )
    if not match:
        return []
    open_index = match.end() - 1
    block, _ = _balanced_block(sql, open_index)
    columns: list[dict[str, str]] = []
    for definition in _split_top_level(block):
        field = re.match(r"\s*(?:`([^`]+)`|([A-Za-z_][\w]*))\s+(.+)$", definition, re.S)
        if not field:
            continue
        name = field.group(1) or field.group(2)
        remainder = field.group(3).strip()
        type_match = re.match(
            r"(.+?)(?=\s+(?:COMMENT|DEFAULT|CODEC|ALIAS|MATERIALIZED|TTL)\b|$)",
            remainder,
            re.I | re.S,
        )
        comment_match = re.search(r"\bCOMMENT\s+'((?:''|[^'])*)'", remainder, re.I | re.S)
        columns.append({
            "name": name,
            "type": (type_match.group(1) if type_match else remainder).strip(),
            "comment": comment_match.group(1).replace("''", "'") if comment_match else "",
        })
    return columns


def _core_module_manifest(tables: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the built-in core module catalog from SQL lineage plus reviewed query metadata."""
    daily_query_tables = set(CORE_OUTPUTS) | {"daily_prices"}
    by_name = {table["name"]: table for table in tables}
    datasets: list[dict[str, Any]] = []
    for name in sorted(by_name):
        table = by_name[name]
        column_names = {column["name"] for column in table["columns"]}
        daily = name in daily_query_tables
        datasets.append(
            {
                "dataset_id": f"sigmarail.core.{name}",
                "table": name,
                "frequency": "daily" if daily else "unspecified",
                "entity_grain": ["ticker", "date"] if daily else [],
                "time_key": "date" if "date" in column_names else None,
                "as_of_semantics": "observation_time" if daily else "unspecified",
                "completion": "completed" if daily else "unspecified",
                "source_ids": table["sharadar_roots"],
                "schema_ref": "sigmarail-spec://v1/data/schema",
            }
        )

    spine = "sigmarail.core.screener_price_tech_daily"
    joins = [
        {
            "id": f"sigmarail.core.join.screener_price_tech_daily_to_{table}",
            "from_dataset": spine,
            "to_dataset": f"sigmarail.core.{table}",
            "keys": [{"from": "ticker", "to": "ticker"}, {"from": "date", "to": "date"}],
            "cardinality": "one_to_one",
            "temporal_alignment": "exact",
            "max_staleness": None,
        }
        for table in CORE_OUTPUTS
        if table != "screener_price_tech_daily"
    ]
    return {
        "contract_version": 1,
        "module_id": "sigmarail.core",
        "version": "0.1.0",
        "kind": "core_data",
        "package": {"distribution": "sigmarail"},
        "dependencies": [],
        "datasets": datasets,
        "joins": joins,
        "capabilities": [
            {
                "id": "core.data.query",
                "kind": "query",
                "contract_ref": "sigmarail-spec://v1/data/query/v1",
                "mcp_resource_uris": [
                    "sigmarail-spec://v1/data/schema",
                    "sigmarail-spec://v1/data/fields",
                ],
                "mcp_tool_names": ["core_list_datasets", "core_describe_dataset", "core_query_dataset"],
            }
        ],
        "settings": [],
    }


def _load_objects() -> tuple[set[str], dict[str, dict[str, Any]], dict[str, Path]]:
    known: set[str] = set()
    tables: dict[str, dict[str, Any]] = {}
    transforms: dict[str, dict[str, Any]] = {}
    transform_paths: dict[str, Path] = {}
    schema_files = json.loads(SCHEMA_MANIFEST.read_text(encoding="utf-8"))["files"]
    sql_by_path = {
        SCHEMA_DIR / filename: (SCHEMA_DIR / filename).read_text(encoding="utf-8")
        for filename in schema_files
    }

    # Resolve names across the complete packaged schema first. Transforms may
    # read a table whose DDL appears in a later-numbered file.
    for sql in sql_by_path.values():
        for match in re.finditer(
            r"CREATE\s+(?:TABLE|VIEW)\s+IF\s+NOT\s+EXISTS\s+`?([A-Za-z_][\w]*)`?",
            sql,
            re.I,
        ):
            known.add(match.group(1))

    for path, sql in sql_by_path.items():
        for match in re.finditer(r"COMMENT\s+'((?:[^']|'')*)'", sql, re.I):
            comment = match.group(1).replace("''", "'")
            if not comment.lstrip().startswith("{"):
                continue
            try:
                config = json.loads(comment)
            except json.JSONDecodeError:
                continue
            target = config.get("target")
            if target:
                after_comment = sql[match.end() :]
                as_match = re.search(
                    r"\bAS\b(?:(?:\s+)|(?:--[^\n]*(?:\n|$))|(?:/\*.*?\*/))*?(?=(?:WITH|SELECT)\b)",
                    after_comment,
                    re.I | re.S,
                )
                if not as_match:
                    raise ValueError(f"Transform has no SELECT body: {path.name}:{target}")
                body = after_comment[as_match.end() :]
                actual_sources, unresolved = _actual_table_inputs(body, known)
                if unresolved:
                    raise ValueError(
                        f"Transform contains unresolved table inputs for {target}: "
                        f"{sorted(unresolved)}"
                    )
                actual_sources = [source for source in actual_sources if source != target]
                declared_sources = list(config.get("sources") or [])
                if set(actual_sources) != set(declared_sources):
                    raise ValueError(
                        f"Transform source metadata differs from SQL for {target}: "
                        f"SQL={sorted(actual_sources)}, COMMENT={sorted(declared_sources)}"
                    )
                transforms[target] = config
                transform_paths[target] = path
    raw_sql = (SCHEMA_DIR / RAW_SCHEMA_FILE).read_text(encoding="utf-8")
    raw_tables = {
        match.group(1)
        for match in re.finditer(
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+`?([A-Za-z_][\w]*)`?",
            raw_sql,
            re.I,
        )
    }
    for table in raw_tables:
        tables[table] = {
            "kind": "sharadar_source",
            "direct_inputs": [],
            "sharadar_roots": [table],
            "path": SCHEMA_DIR / RAW_SCHEMA_FILE,
        }
    for target, config in transforms.items():
        tables[target] = {
            "kind": "derived",
            "direct_inputs": list(config.get("sources") or []),
            "sharadar_roots": [],
            "path": transform_paths[target],
        }
    return raw_tables, tables, transform_paths


def main() -> int:
    raw_tables, tables, _ = _load_objects()
    pending = True
    while pending:
        pending = False
        for name, entry in tables.items():
            if entry["kind"] == "sharadar_source" or entry["sharadar_roots"]:
                continue
            sources = entry["direct_inputs"]
            if not sources or any(source not in tables for source in sources):
                continue
            if all(tables[source]["sharadar_roots"] for source in sources):
                roots = sorted({root for source in sources for root in tables[source]["sharadar_roots"]})
                entry["sharadar_roots"] = roots
                pending = True

    output_names = [name for name in CORE_OUTPUTS if name in tables]
    included = set(raw_tables)
    additional_output_names = [name for name in ADDITIONAL_SHARADAR_OUTPUTS if name in tables]
    todo = list(output_names + additional_output_names + ["daily_prices"])
    while todo:
        name = todo.pop()
        if name in included:
            continue
        entry = tables.get(name)
        if not entry:
            raise ValueError(f"Core lineage references an absent schema object: {name}")
        if not entry["sharadar_roots"]:
            raise ValueError(f"Core object does not resolve to Sharadar roots: {name}")
        included.add(name)
        todo.extend(entry["direct_inputs"])

    object_sql = {
        filename: (SCHEMA_DIR / filename).read_text(encoding="utf-8")
        for filename in json.loads(SCHEMA_MANIFEST.read_text(encoding="utf-8"))["files"]
    }

    manifest_tables = []
    for name in sorted(included):
        entry = tables[name]
        path = entry["path"]
        columns = _columns_from_create(object_sql[path.name], name)
        if not columns:
            raise ValueError(f"No CREATE TABLE columns parsed for {name} in {path.name}")
        for column in columns:
            column["id"] = f"sigmarail.field.{name}.{column['name']}.{column['name']}"
            if column["name"] == "lastupdated":
                column["classification"] = "operational_metadata"
                column["lineage_roots"] = []
                column["lineage_method"] = "generated by the transform at load time"
            elif entry["kind"] == "sharadar_source":
                column["classification"] = "sharadar_source"
                column["lineage_roots"] = [name]
                column["lineage_method"] = "provider source-table column"
            else:
                column["classification"] = "sharadar_derived"
                column["lineage_roots"] = entry["sharadar_roots"]
                column["lineage_method"] = (
                    "transitive SQL table-input closure; exact expression-level source columns are not asserted"
                )
        manifest_tables.append(
            {
                "name": name,
                "kind": entry["kind"],
                "schema_file": str(path.relative_to(ROOT)),
                "direct_inputs": entry["direct_inputs"],
                "sharadar_roots": entry["sharadar_roots"],
                "column_lineage_basis": "Each column records the table-level source roots of its defining table or transform. Exact expression-level source-column mapping is not asserted.",
                "columns": columns,
            }
        )

    support_view = {
        "name": "recalculation_events_view",
        "kind": "operational_view",
        "schema_file": "src/sigmarail/sql/schema/92-schema-recalculation-events-view.sql",
        "direct_inputs": ["actions", "sep", "sfp", "sp500"],
        "sharadar_roots": ["actions", "sep", "sfp", "sp500"],
        "purpose": "Sharadar corporate-action and membership events used for price-recalculation awareness.",
    }
    result = {
        "manifest_version": 1,
        "project": "SigmaRail",
        "database": "sigmarail",
        "schema_files": json.loads(SCHEMA_MANIFEST.read_text(encoding="utf-8"))["files"],
        "lineage_rule": "Every included derived table and column resolves through SQL inputs only to one or more Sharadar source tables.",
        "source_metadata_check": "Every included transform COMMENT source list matches physical SQL table references; unresolved relations block manifest generation.",
        "core_screener_outputs": output_names,
        "additional_sharadar_outputs": additional_output_names,
        "raw_sharadar_tables": sorted(raw_tables),
        "tables": manifest_tables,
        "support_views": [support_view],
        "excluded_fields": EXCLUDED_FIELDS,
        "deferred_external_tables": DEFERRED_EXTERNAL,
        "deferred_sharadar_features": DEFERRED_SHARADAR_FEATURES,
        "deferred_application_layers": DEFERRED_APPLICATION_LAYERS,
    }
    module_manifest = _core_module_manifest(manifest_tables)
    rendered = json.dumps(result, indent=2, sort_keys=False) + "\n"
    for output in (OUTPUT, PACKAGE_OUTPUT):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    module_rendered = json.dumps(module_manifest, indent=2, sort_keys=False) + "\n"
    for output in (MODULE_OUTPUT, PACKAGE_MODULE_OUTPUT):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(module_rendered, encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}: {len(manifest_tables)} tables, {sum(len(t['columns']) for t in manifest_tables)} columns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
