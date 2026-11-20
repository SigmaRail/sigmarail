# sigmarail-studio — domain catalog

Consolidated domain MCP (strangler-fig over `vera` / `vera-backtest` / `vera-lean-framework`).
Tool count: see `sigmarail_studio_mcp/parity.py`. Canonical mapping: `sigmarail_studio_mcp/parity.py`.

| Domain | Tools |
|---|---|
| catalog | `catalog_list_tables` `catalog_list_columns` `catalog_list_join_paths` `catalog_describe_entity` |
| screen | `screen_stocks` `screen_probe_layers` `screen_probe_asof` `screen_probe_range` `screen_probe_diff` |
| strategy | `strategy_list_factors` `strategy_list_presets` `strategy_list_templates` `strategy_get_template` `strategy_list_columns` `strategy_pipeline_schema` `strategy_validate_pipeline` `strategy_compile_pipeline` `strategy_compile_preset` `strategy_fork` `strategy_compile_portfolio` `strategy_fork_portfolio` `strategy_patch_pipeline` |
| backtest | `backtest_report` `backtest_compare` `backtest_list_runs_by_ir_id` `backtest_wait` `backtest_list_specs` `backtest_get_spec` `backtest_list_runs` `backtest_get_run` `backtest_list_jobs` `backtest_save_spec` `backtest_save_from_template` `backtest_submit` `backtest_submit_from_template` `backtest_job_status` `backtest_cancel` `backtest_investigate` `backtest_list_pending` |
| optimize | `optimize_list_runs` `optimize_policy_scorecard` |
| deploy | `deploy_list_deployments` `deploy_status` `deploy_performance` |
| portfolio | `portfolio_status` `portfolio_household_summary` `portfolio_rvab_position_size` `portfolio_balance_at_risk` `portfolio_accounts` `portfolio_positions` `portfolio_trades` `portfolio_allocation_drift` `portfolio_performance` |
| regime | `regime_market_regime` `regime_explain_allocation` `regime_compare_periods` `regime_entry_gate` `regime_position_management` `regime_rank_candidates` `regime_transition_weight` |
| research | `research_narrative_search` `research_sentiment_timeline` `research_context` `research_anchored` `research_influencer_index_posture` `research_influencer_action_rollups` |
| chart | `chart_tv_embed` `chart_price_embed` |
| studio | `studio_navigate` `studio_run_context` |
| kb | `kb_get_episode` `kb_get_episode_asset` `kb_derivatives_status` `kb_list_extraction_pages` `kb_get_extraction_page` `kb_extraction_schema` `kb_extraction_page_schema` `kb_chunk_embed_schema` `kb_submit_extraction_page` `kb_submit_episode_extraction` `kb_submit_episode_extraction_finalize` `kb_submit_episode_chunks` |
| lean | `lean_discover_types` |

## Data contract

- Join/column surface = `sql/schema/screener_l7_join.yaml` + `l7_from.column_homes()` (screener_* only; no legacy `daily_screener`).
- Raw catalog/query (`query_table_v1`, `describe_table`, `explain_column`, …) stay on `mcp-clickhouse` (dev/escape hatch).
- Envelope: `{data, meta}` / `{error:{code,message}}` (Phase 6).
- **C-SCREEN-PROBE-V1:** `screen_probe_*` tools POST `STUDIO_BASE_URL` `/api/screens/probe` (default `http://127.0.0.1:8001`). Studio must be running. No parallel ClickHouse writes from MCP for probe.
- **Agent patch:** `strategy_patch_pipeline` POSTs `/api/backtests/specs/:ir_id/pipeline-ops` (default `dry_run=true`). Each op needs `annotation.rationale`.

## Parity

`parity.py` maps every old tool (`vera.*`, `vera-backtest.*`, `vera-lean-framework.*`) to its sigmarail-studio
equivalent. Backlog must be empty — enforced by `platform_gate.check_vera_studio_parity`.
