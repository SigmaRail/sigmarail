"""Old-MCP → sigmarail-studio tool parity catalog.

Single source of truth for the Phase 4 parity gate and Phase 5 cutover. ``MAPPING``
maps ``server.tool`` → ``vera_studio_tool``; tools absent from ``MAPPING`` are gaps.
"""
from __future__ import annotations

# server.tool -> sigmarail-studio domain_verb tool
MAPPING: dict[str, str] = {
    # --- vera (read: regime / optimizer / portfolio / deploy / research / kb / chart / backtest) ---
    "vera.get_market_regime": "regime_market_regime",
    "vera.explain_regime_allocation": "regime_explain_allocation",
    "vera.compare_regime_periods": "regime_compare_periods",
    "vera.evaluate_entry_gate": "regime_entry_gate",
    "vera.evaluate_position_management": "regime_position_management",
    "vera.rank_candidates_for_selection": "regime_rank_candidates",
    "vera.regime_transition_weight": "regime_transition_weight",
    "vera.list_optimizer_runs": "optimize_list_runs",
    "vera.get_policy_scorecard": "optimize_policy_scorecard",
    "vera.get_portfolio_status": "portfolio_status",
    "vera.get_household_broker_summary": "portfolio_household_summary",
    "vera.compute_rvab_position_size": "portfolio_rvab_position_size",
    "vera.compute_balance_at_risk": "portfolio_balance_at_risk",
    "vera.get_broker_accounts": "portfolio_accounts",
    "vera.get_broker_positions": "portfolio_positions",
    "vera.get_broker_trades": "portfolio_trades",
    "vera.get_broker_allocation_drift": "portfolio_allocation_drift",
    "vera.get_broker_performance": "portfolio_performance",
    "vera.list_live_deployments": "deploy_list_deployments",
    "vera.get_live_status": "deploy_status",
    "vera.get_live_performance": "deploy_performance",
    "vera.kb_narrative_search": "research_narrative_search",
    "vera.kb_ticker_sentiment_timeline": "research_sentiment_timeline",
    "vera.research_context": "research_context",
    "vera.timeseries_anchored_research": "research_anchored",
    "vera.get_influencer_index_posture": "research_influencer_index_posture",
    "vera.get_influencer_action_rollups": "research_influencer_action_rollups",
    "vera.tv_chart_embed": "chart_tv_embed",
    "vera.vera_price_chart_embed": "chart_price_embed",
    "vera.get_backtest_report": "backtest_report",
    "vera.list_runs_by_ir_id": "backtest_list_runs_by_ir_id",
    "vera.wait_for_backtest": "backtest_wait",
    "vera.describe_adm_entity": "catalog_describe_entity",
    "vera.list_adm_join_paths": "catalog_list_join_paths",
    "vera.kb_get_episode": "kb_get_episode",
    "vera.kb_get_episode_asset": "kb_get_episode_asset",
    "vera.kb_derivatives_status": "kb_derivatives_status",
    "vera.kb_list_extraction_pages": "kb_list_extraction_pages",
    "vera.kb_get_extraction_page": "kb_get_extraction_page",
    "vera.get_extraction_schema": "kb_extraction_schema",
    "vera.get_extraction_page_schema": "kb_extraction_page_schema",
    "vera.get_chunk_embed_schema": "kb_chunk_embed_schema",
    "vera.submit_extraction_page": "kb_submit_extraction_page",
    "vera.submit_episode_extraction": "kb_submit_episode_extraction",
    "vera.submit_episode_extraction_finalize": "kb_submit_episode_extraction_finalize",
    "vera.submit_episode_chunks": "kb_submit_episode_chunks",
    "vera.screen_stocks": "screen_stocks",
    "vera.list_templates": "strategy_list_templates",
    "vera.get_template": "strategy_get_template",
    "vera.list_specs": "backtest_list_specs",
    "vera.get_spec": "backtest_get_spec",
    "vera.list_runs": "backtest_list_runs",
    "vera.get_run": "backtest_get_run",
    "vera.list_backtest_jobs": "backtest_list_jobs",
    "vera-backtest.save_spec": "backtest_save_spec",
    "vera-backtest.submit_backtest": "backtest_submit",
    "vera-backtest.get_backtest_status": "backtest_job_status",
    "vera-backtest.cancel_backtest": "backtest_cancel",
    "vera-backtest.list_pending_jobs": "backtest_list_pending",
    "vera-lean-framework.lean_framework_discover_types": "lean_discover_types",
    # --- vera-backtest ---
    "vera-backtest.list_strategy_factors": "strategy_list_factors",
    "vera-backtest.list_strategy_presets": "strategy_list_presets",
    "vera-backtest.compile_strategy_pipeline": "strategy_compile_pipeline",
    "vera-backtest.compile_strategy_preset": "strategy_compile_preset",
    "vera-backtest.decompile_strategy_spec": "strategy_fork",
    "vera-backtest.list_templates": "strategy_list_templates",
    "vera-backtest.get_template": "strategy_get_template",
    "vera-backtest.create_spec_from_strategy_template": "backtest_save_from_template",
    "vera-backtest.submit_backtest_from_template": "backtest_submit_from_template",
}

# Old tools that are intentionally out of scope for the domain MCP (dev/escape hatch: mcp-clickhouse).
OUT_OF_SCOPE = {
    "vera.list_database_tables",
    "vera.describe_table",
    "vera.query_table_v1",
    "vera.query_table_v1_spec_schema",
    "vera.explain_column",
    "vera.explain_column_graph",
    "vera.describe_entity",
    "vera.canon_entity",
    "vera.canon_registry",
}

# Old tools still to port (Phase 4 backlog). Empty once lean_framework_discover_types is mapped.
BACKLOG: set[str] = set()

# MCP app / resource helpers (not domain tools; handled by the embed layer).
APP_RESOURCES = {
    "vera.tv_chart_mcp_app",
    "vera.vera_price_chart_mcp_app",
    "vera.kb_extraction_schema_resource",
    "vera.kb_extraction_page_schema_resource",
    "vera.kb_chunk_embed_schema_resource",
    "vera._tv_chart_mcp_app_resource",
}


def gaps() -> list[str]:
    """Old tools that have no sigmarail-studio equivalent yet (Phase 4 backlog)."""
    return sorted(BACKLOG)


def coverage() -> dict[str, int]:
    return {
        "mapped": len(MAPPING),
        "out_of_scope": len(OUT_OF_SCOPE),
        "backlog": len(BACKLOG),
        "app_resources": len(APP_RESOURCES),
    }
