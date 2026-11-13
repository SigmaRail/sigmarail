"""SigmaRail Studio MCP server (domain_verb tool naming)."""
from __future__ import annotations

import json
import importlib.util
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from sigmarail_studio_mcp.spec_resources import register_spec_resources

from sigmarail_studio_mcp.domains import (
    backtest,
    catalog,
    chart,
    core,
    deploy,
    kb,
    lean,
    optimize,
    portfolio,
    regime,
    research,
    screen,
    strategy,
    studio,
)


_MODULE_CATALOG = json.loads(
    (Path(__file__).parent / "data" / "module-catalog.json").read_text(encoding="utf-8")
)
_MODULES_BY_NAME = {row["name"]: row for row in _MODULE_CATALOG["modules"]}


def _enabled_modules() -> set[str]:
    configured = os.environ.get("SIGMARAIL_STUDIO_MODULES", "").strip()
    enabled = (
        {part.strip().lower() for part in configured.split(",") if part.strip()}
        if configured else set(_MODULE_CATALOG["default_enabled"])
    )
    enabled.update(_MODULE_CATALOG["always_enabled"])
    unknown = enabled - _MODULES_BY_NAME.keys()
    if unknown:
        raise ValueError(f"unknown SigmaRail Studio modules: {', '.join(sorted(unknown))}")
    # The catalog records current and target dependencies separately during
    # migration. Fail at activation with an actionable message instead of
    # registering tools that can only fail when first called.
    unavailable: dict[str, list[str]] = {}
    for name in sorted(enabled):
        missing = [
            package for package in _MODULES_BY_NAME[name].get("requires", [])
            if importlib.util.find_spec(package) is None
        ]
        if missing:
            unavailable[name] = missing
    if unavailable:
        details = "; ".join(
            f"{name}: {', '.join(packages)}" for name, packages in unavailable.items()
        )
        raise RuntimeError(
            "Requested SigmaRail Studio modules have unmet current runtime dependencies: "
            f"{details}. Core and Studio modules remain available by default."
        )
    return enabled


def _build() -> FastMCP:
    enabled_modules = _enabled_modules()

    def _tool(module: str):
        """Register tools only when their Studio module is explicitly enabled."""
        def decorate(function):
            if module not in enabled_modules:
                return function
            return mcp.tool()(function)
        return decorate

    mcp = FastMCP(
        name="sigmarail-studio",
        instructions=(
            "SigmaRail Studio MCP. Read the versioned SigmaRail Spec Resources first. "
            "The core module is always available; additional SigmaRail capabilities are "
            "enabled through SIGMARAIL_STUDIO_MODULES.\n\n"
            "core_*     — SQL-backed SigmaRail dataset catalog and bounded read-only queries.\n"
            "screening, strategy, backtesting, portfolio, deployment, knowledge — optional modules.\n"
        ),
    )
    register_spec_resources(mcp)

    # --- core data domain ---------------------------------------------------
    @_tool("core")
    def core_list_datasets() -> dict[str, Any]:
        """List SigmaRail core datasets with IDs, grains, and Sharadar lineage roots."""
        return core.list_datasets()

    @_tool("core")
    def core_describe_dataset(dataset_id: str) -> dict[str, Any]:
        """Describe one registered core dataset, its fields, lineage, and time semantics."""
        return core.describe_dataset(dataset_id)

    @_tool("core")
    def core_query_dataset(query: core.DataQueryV1) -> dict[str, Any]:
        """Run a bounded read-only query with allowlisted field IDs and declared joins."""
        return core.query_dataset(query)

    # --- catalog domain -----------------------------------------------------
    @_tool("screening")
    def catalog_list_tables() -> dict[str, Any]:
        """List the L7 screener tables and join metadata (spine/grain/prefix)."""
        return catalog.list_tables()

    @_tool("screening")
    def catalog_list_columns() -> dict[str, Any]:
        """List the screener column surface (name -> owning table / physical column)."""
        return catalog.list_columns()

    @_tool("screening")
    def catalog_list_join_paths(
        from_entity: str | None = None,
        to_entity: str | None = None,
    ) -> dict[str, Any]:
        """Join paths: L7 spine star + cross-entity ADM paths."""
        return catalog.list_join_paths(from_entity=from_entity, to_entity=to_entity)

    @_tool("screening")
    def catalog_describe_entity(entity: str) -> dict[str, Any]:
        """Static ADM entity metadata (tables/keys/anchors)."""
        try:
            return catalog.describe_entity(entity)
        except ValueError as exc:
            return {"error": str(exc), "code": "unknown_entity"}

    # --- screen domain ------------------------------------------------------
    @_tool("screening")
    def screen_stocks(date: str, preset: str = "leaders", limit: int = 25) -> dict[str, Any]:
        """Run an L7 screener preset (leaders / minervini_tt / vcp_tight / high_rs / …)."""
        return screen.stocks(date, preset=preset, limit=limit)

    @_tool("screening")
    def screen_probe_layers(
        preset_id: str | None = None,
        through_binding_id: str | None = None,
        through_stage_index: int | None = None,
        probe_mode: str = "measures",
        pipeline: dict[str, Any] | None = None,
        spec: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """List stage-prefix layers / computed aliases (HTTP → Studio; no ClickHouse)."""
        return screen.probe_layers(
            preset_id=preset_id,
            pipeline=pipeline,
            spec=spec,
            through_binding_id=through_binding_id,
            through_stage_index=through_stage_index,
            probe_mode=probe_mode,
        )

    @_tool("screening")
    def screen_probe_asof(
        as_of: str,
        preset_id: str | None = None,
        through_binding_id: str | None = None,
        through_stage_index: int | None = None,
        probe_mode: str = "measures",
        limit: int = 25,
        pipeline: dict[str, Any] | None = None,
        spec: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Single-day ranked sample of prefix columns (HTTP → Studio probe)."""
        return screen.probe_asof(
            as_of=as_of,
            preset_id=preset_id,
            pipeline=pipeline,
            spec=spec,
            through_binding_id=through_binding_id,
            through_stage_index=through_stage_index,
            probe_mode=probe_mode,
            limit=limit,
        )

    @_tool("screening")
    def screen_probe_range(
        end_date: str,
        start_date: str | None = None,
        preset_id: str | None = None,
        through_binding_id: str | None = None,
        through_stage_index: int | None = None,
        probe_mode: str = "measures",
        pipeline: dict[str, Any] | None = None,
        spec: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Per-day member counts + measure averages (HTTP → Studio probe)."""
        return screen.probe_range(
            end_date=end_date,
            start_date=start_date,
            preset_id=preset_id,
            pipeline=pipeline,
            spec=spec,
            through_binding_id=through_binding_id,
            through_stage_index=through_stage_index,
            probe_mode=probe_mode,
        )

    @_tool("screening")
    def screen_probe_diff(
        as_of: str,
        preset_id: str | None = None,
        through_binding_id: str | None = None,
        through_stage_index: int | None = None,
        through_b_binding_id: str | None = None,
        through_b_stage_index: int | None = None,
        probe_mode: str = "members",
        pipeline: dict[str, Any] | None = None,
        spec: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Compare prefix layers A vs B (HTTP → Studio probe)."""
        return screen.probe_diff(
            as_of=as_of,
            preset_id=preset_id,
            pipeline=pipeline,
            spec=spec,
            through_binding_id=through_binding_id,
            through_stage_index=through_stage_index,
            through_b_binding_id=through_b_binding_id,
            through_b_stage_index=through_b_stage_index,
            probe_mode=probe_mode,
        )

    # --- strategy domain ----------------------------------------------------
    @_tool("strategy")
    def strategy_list_factors() -> dict[str, Any]:
        """Semantic factor registry (name -> L7 column/table/direction)."""
        return strategy.list_factors()

    @_tool("strategy")
    def strategy_list_presets() -> dict[str, Any]:
        """Named strategy presets."""
        return strategy.list_presets()

    @_tool("strategy")
    def strategy_list_templates(kind: str | None = None, status: str | None = "active") -> dict[str, Any]:
        """List screener and strategy templates (C-TEMPLATE-CATALOG-V1). Default status=active."""
        return strategy.list_templates(kind=kind, status=status)

    @_tool("strategy")
    def strategy_get_template(template_id: str) -> dict[str, Any]:
        """Load one catalog template (screener IR or strategy PipelineDocument)."""
        return strategy.get_template(template_id)

    @_tool("strategy")
    def strategy_list_columns() -> dict[str, Any]:
        """Screener column surface for authoring (screener_*, never the legacy view)."""
        return strategy.list_columns()

    @_tool("strategy")
    def strategy_pipeline_schema() -> dict[str, Any]:
        """JSON schema for a staged PipelineDocument."""
        return strategy.pipeline_schema()

    @_tool("strategy")
    def strategy_validate_pipeline(pipeline_json: str) -> dict[str, Any]:
        """Validate a staged PipelineDocument JSON without compiling it."""
        return strategy.validate_pipeline(pipeline_json)

    @_tool("strategy")
    def strategy_compile_pipeline(pipeline_json: str) -> dict[str, Any]:
        """Compile a staged PipelineDocument JSON into a VeraLabV1 spec dict."""
        return strategy.compile_pipeline(pipeline_json)

    @_tool("strategy")
    def strategy_compile_preset(preset_id: str) -> dict[str, Any]:
        """Compile a named strategy preset into a VeraLabV1 spec dict."""
        return strategy.compile_preset(preset_id)

    @_tool("strategy")
    def strategy_fork(spec_json: str) -> dict[str, Any]:
        """Decompile a VeraLabV1 spec JSON back into a PipelineDocument."""
        return strategy.fork(spec_json)

    @_tool("strategy")
    def strategy_compile_portfolio(portfolio_json: str) -> dict[str, Any]:
        """Compile a PortfolioDocument JSON (legs + allocation) into a VeraLabV1 spec."""
        return strategy.compile_portfolio(portfolio_json)

    @_tool("strategy")
    def strategy_fork_portfolio(spec_json: str) -> dict[str, Any]:
        """Decompile a VeraLabV1 spec JSON back into a PortfolioDocument."""
        return strategy.fork_portfolio(spec_json)

    @_tool("strategy")
    def strategy_diff(spec_a_json: str, spec_b_json: str) -> dict[str, Any]:
        """Semantic slot-level diff between two VeraLabV1 specs."""
        return strategy.strategy_diff(spec_a_json, spec_b_json)

    @_tool("strategy")
    def strategy_lint(pipeline_json: str) -> dict[str, Any]:
        """Validate a PipelineDocument AST + flag runtime-contract conflicts."""
        return strategy.strategy_lint(pipeline_json)

    @_tool("strategy")
    def strategy_list_setup_recipes() -> dict[str, Any]:
        """Named setup expression packs (SSOT for composed setup trees).

        Use these recipe ids with strategy_compose_document instead of hand-typing expression trees.
        ``champion_setup_or`` = volume_thrust_breakout OR vcp_compression OR pocket_pivot.
        """
        return strategy.list_setup_recipes()

    @_tool("strategy")
    def strategy_compose_document(
        preset_id: str = "minervini_sepa",
        setup_recipe_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Compose an authored PipelineDocument from a preset + setup recipe packs (semantic authoring).

        ``setup_recipe_ids`` defaults to ``["champion_setup_or"]``.
        """
        return strategy.compose_document(preset_id, setup_recipe_ids)

    @_tool("strategy")
    def strategy_save_pipeline(
        ir_id: str,
        title: str,
        pipeline_json: str,
        notes: str = "",
        changelog_notes: str = "",
        author_agent: str = "agent",
        force_new_version: bool = False,
    ) -> dict[str, Any]:
        """Validate + compile an authored PipelineDocument and save it (forks when runs exist).

        Use this to persist the output of ``strategy_compose_document`` / ``strategy_fork`` — no raw
        VeraLabV1 JSON needed. Check ``forked`` and use the returned ``ir_id`` for follow-up calls.
        """
        return strategy.save_pipeline(
            ir_id,
            title,
            pipeline_json,
            notes,
            changelog_notes=changelog_notes,
            author_agent=author_agent,
            force_new_version=force_new_version,
        )

    @_tool("strategy")
    def strategy_patch_pipeline(
        ir_id: str,
        ops: list[dict[str, Any]],
        dry_run: bool = True,
        expected_hash: str | None = None,
        retest: bool = False,
        through_binding_id: str | None = None,
        probe_mode: str = "measures",
    ) -> dict[str, Any]:
        """Patch authored PipelineDocument via Studio REST (HTTP; requires rationale per op)."""
        return strategy.patch_pipeline(
            ir_id,
            ops,
            dry_run=dry_run,
            expected_hash=expected_hash,
            retest=retest,
            through_binding_id=through_binding_id,
            probe_mode=probe_mode,
        )

    # --- backtest domain ----------------------------------------------------
    @_tool("backtesting")
    def backtest_report(run_id: str) -> dict[str, Any]:
        """Agent-friendly digest for one backtest run (metrics/highlights/warnings)."""
        return backtest.report(run_id)

    @_tool("backtesting")
    def backtest_compare(run_id_a: str, run_id_b: str) -> dict[str, Any]:
        """Diff the key metrics of two backtest runs (delta = B - A)."""
        return backtest.compare(run_id_a, run_id_b)

    @_tool("backtesting")
    def backtest_list_runs_by_ir_id(ir_id: str, limit: int = 20) -> dict[str, Any]:
        """List backtest runs for a VeraLab ir_id (most-recent first)."""
        return backtest.list_runs_by_ir_id(ir_id, limit=limit)

    @_tool("backtesting")
    def backtest_wait(job_id: str, timeout_sec: int = 3600, poll_interval_sec: float = 5) -> dict[str, Any]:
        """Poll a backtest job until done/failed; returns the report digest on success."""
        return backtest.wait(job_id, timeout_sec=timeout_sec, poll_interval_sec=poll_interval_sec)

    @_tool("backtesting")
    def backtest_list_specs(limit: int = 20) -> dict[str, Any]:
        """List stored VeraLab algorithm specs (most-recent first, no algorithm_json blob)."""
        return backtest.list_specs(limit=limit)

    @_tool("backtesting")
    def backtest_get_spec(ir_id: str) -> dict[str, Any]:
        """Fetch a single VeraLab algorithm spec by ir_id (includes full algorithm_json)."""
        return backtest.get_spec(ir_id)

    @_tool("backtesting")
    def backtest_list_runs(strategy_id: str | None = None, limit: int = 20) -> dict[str, Any]:
        """List backtest runs (most-recent first; optional strategy_id filter)."""
        return backtest.list_runs(strategy_id=strategy_id, limit=limit)

    @_tool("backtesting")
    def backtest_get_run(run_id: str) -> dict[str, Any]:
        """Fetch a single run by run_id including all artifacts (debug/advanced)."""
        return backtest.get_run(run_id)

    @_tool("backtesting")
    def backtest_list_jobs(status: str | None = None, limit: int = 20) -> dict[str, Any]:
        """List backtest jobs from the queue (optional status filter)."""
        return backtest.list_jobs(status=status, limit=limit)

    @_tool("backtesting")
    def backtest_save_spec(
        ir_id: str,
        title: str,
        spec_json: str,
        notes: str = "",
        spec_schema_version: int | None = None,
        force_new_version: bool = False,
        changelog_notes: str = "",
        author_agent: str = "agent",
    ) -> dict[str, Any]:
        """Store a VeraLab algorithm spec in strategy_algorithm_specs.

        Forks automatically when `ir_id` already has backtest runs: the spec is
        saved under a NEW ir_id with parent_ir_id + mutation_type="fork", so
        existing runs are never re-pointed at changed content. Check `forked` in
        the response and use the returned `ir_id` for follow-up calls.
        """
        return backtest.save_spec(
            ir_id,
            title,
            spec_json,
            notes=notes,
            spec_schema_version=spec_schema_version,
            force_new_version=force_new_version,
            changelog_notes=changelog_notes,
            author_agent=author_agent,
        )

    @_tool("backtesting")
    def backtest_save_from_template(
        template_id: str,
        ir_id: str | None = None,
        title: str | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        """Compile a strategy catalog template and save_spec it."""
        return backtest.save_from_template(template_id, ir_id=ir_id, title=title, notes=notes)

    @_tool("backtesting")
    def backtest_submit(
        ir_id: str,
        start_date: str,
        end_date: str,
        job_id: str | None = None,
        immediate: bool = False,
        extra_env: dict[str, str] | None = None,
        lean_project: str | None = None,
    ) -> dict[str, Any]:
        """Submit a backtest job (pending, or immediately via lean backtest)."""
        return backtest.submit(ir_id, start_date, end_date, job_id=job_id, immediate=immediate, extra_env=extra_env, lean_project=lean_project)

    @_tool("backtesting")
    def backtest_submit_from_template(
        template_id: str,
        start_date: str,
        end_date: str,
        ir_id: str | None = None,
        immediate: bool = False,
        extra_env: dict[str, str] | None = None,
        lean_project: str | None = None,
    ) -> dict[str, Any]:
        """Compile + save a strategy catalog template, then enqueue (or run) a backtest."""
        return backtest.submit_from_template(
            template_id,
            start_date,
            end_date,
            ir_id=ir_id,
            immediate=immediate,
            extra_env=extra_env,
            lean_project=lean_project,
        )

    @_tool("backtesting")
    def backtest_job_status(job_id: str) -> dict[str, Any]:
        """Current backtest job state from backtest_jobs (incl. telemetry columns)."""
        return backtest.job_status(job_id)

    @_tool("backtesting")
    def backtest_cancel(job_id: str) -> dict[str, Any]:
        """Cancel an active/queued backtest job."""
        return backtest.cancel(job_id)

    @_tool("backtesting")
    def backtest_investigate(
        job_id: str,
        heartbeat_stale_seconds: int = 180,
        log_stale_seconds: int = 600,
        tail_lines: int = 40,
    ) -> dict[str, Any]:
        """Hang/failure forensics for one backtest job.

        Verdict ``running``/``pending``/``hung``/``orphaned``/``done``/``failed``/
        ``cancelled`` with heartbeat age, log age, live progress re-parse,
        'Analysis Complete' detection, strategy_runs presence, log tail and
        next-step hints. Use when a job seems stuck, failed, or unreported.
        """
        return backtest.investigate(
            job_id,
            heartbeat_stale_seconds=heartbeat_stale_seconds,
            log_stale_seconds=log_stale_seconds,
            tail_lines=tail_lines,
        )

    @_tool("backtesting")
    def backtest_list_pending(limit: int = 50) -> dict[str, Any]:
        """Pending backtest jobs ordered by submission time (oldest first)."""
        return backtest.list_pending(limit=limit)

    @_tool("backtesting")
    def backtest_run_attribution(run_id: str) -> dict[str, Any]:
        """Per-trade loss-cause attribution for one run."""
        return backtest.run_attribution(run_id)

    # --- regime domain ------------------------------------------------------
    @_tool("backtesting")
    def regime_market_regime(date: str) -> dict[str, Any]:
        """Market regime row for a session date."""
        return regime.market_regime(date)

    @_tool("backtesting")
    def regime_explain_allocation(date: str, policy_name: str | None = None, ticker: str = "SPY") -> dict[str, Any]:
        """Explain the regime allocation (v1 daily row or composed policy)."""
        return regime.explain_allocation(date, policy_name=policy_name, ticker=ticker)

    @_tool("backtesting")
    def regime_compare_periods(
        focus_start: str,
        focus_end: str,
        reference_start: str,
        reference_end: str,
    ) -> dict[str, Any]:
        """Compare breadth/allocation aggregates between two date windows."""
        return regime.compare_periods(focus_start, focus_end, reference_start, reference_end)

    @_tool("backtesting")
    def regime_entry_gate(as_of_date: str) -> dict[str, Any]:
        """HARD entry gate (rules 1-7) — mandatory session-open check."""
        return regime.entry_gate(as_of_date)

    @_tool("backtesting")
    def regime_position_management(
        ticker: str,
        entry: float,
        stop: float,
        targets: list[float],
        as_of_date: str | None = None,
        action: str = "new",
        earnings_date: str | None = None,
    ) -> dict[str, Any]:
        """Gate 2.5b pass/fail: R:R >= 3:1, BAR budget, earnings window, regime slots."""
        return regime.position_management(ticker, entry, stop, targets, as_of_date=as_of_date, action=action, earnings_date=earnings_date)

    @_tool("backtesting")
    def regime_rank_candidates(passing_tickers: list[str], as_of_date: str) -> dict[str, Any]:
        """Rank tickers that already passed the HARD gates (refuses when entry gate closed)."""
        return regime.rank_candidates(passing_tickers, as_of_date)

    @_tool("backtesting")
    def regime_transition_weight(as_of_date: str, base_weight: float = 1.0) -> dict[str, Any]:
        """Direction-split regime-transition weighting (de-risk only)."""
        return regime.transition_weight(as_of_date, base_weight=base_weight)

    # --- optimize domain ----------------------------------------------------
    @_tool("backtesting")
    def optimize_list_runs(limit: int = 50, policy_source: str | None = "search") -> dict[str, Any]:
        """List regime optimizer/search policies."""
        return optimize.list_runs(limit=limit, policy_source=policy_source)

    @_tool("backtesting")
    def optimize_policy_scorecard(policy_name: str, asset_ticker: str = "SPY", window: str | None = None) -> dict[str, Any]:
        """Policy scorecard (pooled/train/val/test)."""
        return optimize.policy_scorecard(policy_name, asset_ticker=asset_ticker, window=window)

    @_tool("backtesting")
    def optimize_list_sessions(limit: int = 20, base_ir_id: str | None = None) -> dict[str, Any]:
        """List recent hyperparameter sweep sessions (Studio optimizer)."""
        return optimize.list_sessions(limit=limit, base_ir_id=base_ir_id)

    @_tool("backtesting")
    def optimize_launch_sweep(
        base_ir_id: str,
        param_x_name: str,
        param_x_values: list[float],
        param_y_name: str | None = None,
        param_y_values: list[float] | None = None,
        start_date: str = "",
        end_date: str = "",
        strategy_type: str = "euler",
        oos_days: int = 60,
        objective: str = "sharpe_ratio",
        title: str | None = None,
        max_concurrent: int = 4,
    ) -> dict[str, Any]:
        """Launch a 1D or 2D hyperparameter sweep session."""
        return optimize.launch_sweep(
            base_ir_id, param_x_name, param_x_values,
            param_y_name=param_y_name, param_y_values=param_y_values,
            start_date=start_date, end_date=end_date, strategy_type=strategy_type,
            oos_days=oos_days, objective=objective, title=title, max_concurrent=max_concurrent,
        )

    @_tool("backtesting")
    def optimize_get_session_heatmap(session_id: str) -> dict[str, Any]:
        """Response surface: heatmap grid, Pareto frontier, completed points."""
        return optimize.get_session_heatmap(session_id)

    @_tool("backtesting")
    def optimize_get_pareto_frontier(session_id: str) -> dict[str, Any]:
        """Non-dominated Pareto optimal runs for a sweep session."""
        return optimize.get_pareto_frontier(session_id)

    @_tool("backtesting")
    def optimize_cancel_session(session_id: str) -> dict[str, Any]:
        """Cancel a sweep session and its pending backtest jobs."""
        return optimize.cancel_session(session_id)

    @_tool("backtesting")
    def optimize_promote_optimal_run(
        session_id: str, run_id: str, new_ir_id: str, title: str, changelog: str = ""
    ) -> dict[str, Any]:
        """Promote a sweep winner to a new spec version (sweep_promotion lineage)."""
        return optimize.promote_optimal_run(session_id, run_id, new_ir_id, title, changelog=changelog)

    # --- portfolio domain ---------------------------------------------------
    @_tool("portfolio")
    def portfolio_status(
        scope: str = "household_yaml",
        account_id: str | None = None,
        book: str | None = None,
        include_cash_equivalents: bool = False,
        include_performance: bool = True,
        include_drift: bool = False,
    ) -> dict[str, Any]:
        """Unified household portfolio status (accounts/holdings/BAR/RVAB/SP)."""
        return portfolio.status(
            scope=scope,
            account_id=account_id,
            book=book,
            include_cash_equivalents=include_cash_equivalents,
            include_performance=include_performance,
            include_drift=include_drift,
        )

    @_tool("portfolio")
    def portfolio_household_summary() -> dict[str, Any]:
        """Household broker totals (all_snaptrade vs yaml_book)."""
        return portfolio.household_summary()

    @_tool("portfolio")
    def portfolio_rvab_position_size(
        ticker: str,
        as_of_date: str | None = None,
        slot_weight: float | None = None,
        reference_rvab: float | None = None,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        """RVAB-adjusted position size for the Schwab swing book."""
        return portfolio.rvab_position_size(
            ticker,
            as_of_date=as_of_date,
            slot_weight=slot_weight,
            reference_rvab=reference_rvab,
            account_id=account_id,
        )

    @_tool("portfolio")
    def portfolio_balance_at_risk(account_id: str | None = None, bar_budget_pct: float | None = None) -> dict[str, Any]:
        """Balance at risk for Schwab swing open positions (ATR stops)."""
        return portfolio.balance_at_risk(account_id=account_id, bar_budget_pct=bar_budget_pct)

    @_tool("portfolio")
    def portfolio_accounts(include_paper: bool = False, include_simulated: bool = False, execution_tier: str | None = None) -> dict[str, Any]:
        """Production broker accounts from broker_accounts_current."""
        return portfolio.accounts(include_paper=include_paper, include_simulated=include_simulated, execution_tier=execution_tier)

    @_tool("portfolio")
    def portfolio_positions(
        account_id: str | None = None,
        include_paper: bool = False,
        include_simulated: bool = False,
        execution_tier: str | None = None,
        include_cash_equivalents: bool = False,
        limit: int = 500,
    ) -> dict[str, Any]:
        """Latest holdings from broker_positions_flat."""
        return portfolio.positions(account_id=account_id, include_paper=include_paper, include_simulated=include_simulated, execution_tier=execution_tier, include_cash_equivalents=include_cash_equivalents, limit=limit)

    @_tool("portfolio")
    def portfolio_trades(
        account_id: str | None = None,
        ticker: str | None = None,
        status: str = "closed",
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Filtered round-trip trades (closed/open)."""
        return portfolio.trades(account_id=account_id, ticker=ticker, status=status, date_from=date_from, date_to=date_to, limit=limit)

    @_tool("portfolio")
    def portfolio_allocation_drift() -> dict[str, Any]:
        """Latest sector/stock drift vs Vera targets and household deployment vs regime."""
        return portfolio.allocation_drift()

    @_tool("portfolio")
    def portfolio_performance(account_id: str | None = None) -> dict[str, Any]:
        """Trade performance summary and equity returns by account."""
        return portfolio.performance(account_id=account_id)

    # --- deploy domain ------------------------------------------------------
    @_tool("deployment")
    def deploy_list_deployments(status: str | None = None, limit: int = 20) -> dict[str, Any]:
        """List live trading deployments."""
        return deploy.list_deployments(status=status, limit=limit)

    @_tool("deployment")
    def deploy_status(deployment_id: str) -> dict[str, Any]:
        """Deployment registry row + latest account snapshot + spec summary."""
        return deploy.status(deployment_id)

    @_tool("deployment")
    def deploy_performance(deployment_id: str, days: int = 30) -> dict[str, Any]:
        """Equity snapshot time series for a live deployment."""
        return deploy.performance(deployment_id, days=days)

    @_tool("deployment")
    def deploy_evaluate_promotion_gate(ir_id: str, run_id: str) -> dict[str, Any]:
        """Pre-flight eligibility checks for paper promotion (Sharpe/DD/job/IR)."""
        return deploy.evaluate_promotion_gate(ir_id, run_id)

    @_tool("deployment")
    def deploy_register_paper_deployment(
        ir_id: str,
        run_id: str,
        deployment_id: str | None = None,
        lean_environment: str = "live-alpaca",
        brokerage: str = "AlpacaBrokerage",
    ) -> dict[str, Any]:
        """Gate-then-register a paper deployment in live_deployments."""
        return deploy.register_paper_deployment(
            ir_id, run_id, deployment_id=deployment_id,
            lean_environment=lean_environment, brokerage=brokerage,
        )

    # --- research domain ----------------------------------------------------
    @_tool("knowledge")
    def research_narrative_search(
        query: str,
        ticker: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Full-text search over KB episode bodies (optional ticker/date filters)."""
        return research.narrative_search(query, ticker=ticker, date_from=date_from, date_to=date_to, limit=limit)

    @_tool("knowledge")
    def research_sentiment_timeline(ticker: str, date_from: str | None = None, date_to: str | None = None, limit: int = 50) -> dict[str, Any]:
        """Ticker mention timeline joined to KB documents."""
        return research.sentiment_timeline(ticker, date_from=date_from, date_to=date_to, limit=limit)

    @_tool("knowledge")
    def research_context(ticker: str, as_of_date: str | None = None, narrative_query: str | None = None, narrative_limit: int = 5) -> dict[str, Any]:
        """Composite: L7 screener row + KB mention timeline + narrative search."""
        return research.context(ticker, as_of_date=as_of_date, narrative_query=narrative_query, narrative_limit=narrative_limit)

    @_tool("knowledge")
    def research_anchored(
        ticker: str,
        as_of_date: str,
        narrative_query: str | None = None,
        narrative_lookback_days: int = 90,
        narrative_limit: int = 5,
        include_regime: bool = True,
    ) -> dict[str, Any]:
        """Screener + KB timeline + windowed narrative + optional regime for an as_of date."""
        return research.anchored_research(
            ticker,
            as_of_date=as_of_date,
            narrative_query=narrative_query,
            narrative_lookback_days=narrative_lookback_days,
            narrative_limit=narrative_limit,
            include_regime=include_regime,
        )

    @_tool("knowledge")
    def research_influencer_index_posture(as_of_date: str, lookback_days: int = 2) -> dict[str, Any]:
        """Influencer de-risking posture on indexes/Mag7."""
        return research.influencer_index_posture(as_of_date, lookback_days=lookback_days)

    @_tool("knowledge")
    def research_influencer_action_rollups(
        as_of_date: str,
        lookback_days: int = 2,
        action_types: list[str] | None = None,
        channel_slugs: list[str] | None = None,
        min_confidence: float = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Unified influencer watch/trade/model lists with citations."""
        return research.influencer_action_rollups(
            as_of_date,
            lookback_days=lookback_days,
            action_types=action_types,
            channel_slugs=channel_slugs,
            min_confidence=min_confidence,
            limit=limit,
        )

    # --- chart domain -------------------------------------------------------
    @_tool("screening")
    def chart_tv_embed(symbol: str, interval: str = "D", theme: str = "dark", height: int = 480, studies: list[str] | None = None) -> dict[str, Any]:
        """TradingView advanced-chart embed payload."""
        return chart.tv_embed(symbol, interval=interval, theme=theme, height=height, studies=studies)

    @_tool("screening")
    def chart_price_embed(ticker: str, lookback_days: int = 252, theme: str = "dark", height: int = 520, show_rsi: bool = True) -> dict[str, Any]:
        """Vera daily OHLCV Chart.js embed (from screener_price_tech_daily)."""
        return chart.price_embed(ticker, lookback_days=lookback_days, theme=theme, height=height, show_rsi=show_rsi)

    # --- studio domain ------------------------------------------------------
    @_tool("studio")
    def studio_navigate(
        section: str,
        run_id: str | None = None,
        section_view: str | None = None,
        ticker: str | None = None,
        as_of: str | None = None,
    ) -> dict[str, Any]:
        """Canonical Studio React-Router URL for a section/subview (LLM-shareable)."""
        try:
            return studio.navigate(section, run_id=run_id, section_view=section_view, ticker=ticker, as_of=as_of)
        except ValueError as exc:
            return {"error": str(exc), "code": "invalid_argument"}

    @_tool("backtesting")
    def studio_run_context(run_id: str, trades_limit: int = 50) -> dict[str, Any]:
        """Context-pack for one backtest run (report/trades/equity/spec/warnings)."""
        return studio.run_context(run_id, trades_limit=trades_limit)

    # --- lean domain --------------------------------------------------------
    @_tool("deployment")
    def lean_discover_types(
        slot: str | None = None,
        include_unwired: bool = True,
        lean_root: str | None = None,
        include_vera_screener_ids: bool = True,
    ) -> dict[str, Any]:
        """List Lean framework `Type` ids, slots, init parameters, and vera_lab flags."""
        return lean.discover_types(slot=slot, include_unwired=include_unwired, lean_root=lean_root, include_vera_screener_ids=include_vera_screener_ids)

    # --- kb domain ----------------------------------------------------------
    @_tool("knowledge")
    def kb_get_episode(
        doc_id: str | None = None,
        vault_relative_path: str | None = None,
        include_derivatives_status: bool = True,
    ) -> dict[str, Any]:
        """Full KB episode: kb_documents metadata + body (+ optional derivatives_status)."""
        return kb.get_episode(doc_id=doc_id, vault_relative_path=vault_relative_path, include_derivatives_status=include_derivatives_status)

    @_tool("knowledge")
    def kb_get_episode_asset(doc_id: str, asset: str, include_content: bool = False) -> dict[str, Any]:
        """Resolve one KB episode bundle asset (srt/mp4/md/image); optional base64 inline."""
        return kb.get_episode_asset(doc_id, asset, include_content=include_content)

    @_tool("knowledge")
    def kb_derivatives_status(doc_id: str) -> dict[str, Any]:
        """Per-doc KB derivative coverage (mentions/sentiment/chunks + agent guidance)."""
        return kb.derivatives_status(doc_id)

    @_tool("knowledge")
    def kb_list_extraction_pages(doc_id: str) -> dict[str, Any]:
        """List timed extraction pages for an episode (MCP paging workflow)."""
        return kb.list_extraction_pages(doc_id)

    @_tool("knowledge")
    def kb_get_extraction_page(doc_id: str, page_index: int) -> dict[str, Any]:
        """Fetch one extraction page (transcript window + aligned OCR segments)."""
        return kb.get_extraction_page(doc_id, page_index)

    @_tool("knowledge")
    def kb_extraction_schema() -> dict[str, Any]:
        """JSON schema for manual episode extraction."""
        return kb.extraction_schema()

    @_tool("knowledge")
    def kb_extraction_page_schema() -> dict[str, Any]:
        """JSON schema for one MCP extraction page partial."""
        return kb.extraction_page_schema()

    @_tool("knowledge")
    def kb_chunk_embed_schema() -> dict[str, Any]:
        """JSON schema for optional RAG chunks with agent-submitted embedding[]."""
        return kb.chunk_embed_schema()

    @_tool("knowledge")
    def kb_submit_extraction_page(doc_id: str, page_index: int, partial_json: dict[str, Any]) -> dict[str, Any]:
        """Stage one page extraction partial in kb_extraction_partials."""
        return kb.submit_extraction_page(doc_id, page_index, partial_json)

    @_tool("knowledge")
    def kb_submit_episode_extraction(
        doc_id: str,
        extraction_json: dict[str, Any],
        rewrite_transcript: bool = True,
        write_manual_sidecar: bool = False,
    ) -> dict[str, Any]:
        """Publish session-LLM extraction JSON to ClickHouse (mentions + sentiment)."""
        return kb.submit_episode_extraction(doc_id, extraction_json, rewrite_transcript=rewrite_transcript, write_manual_sidecar=write_manual_sidecar)

    @_tool("knowledge")
    def kb_submit_episode_extraction_finalize(
        doc_id: str,
        synthesis_json: dict[str, Any] | None = None,
        rewrite_transcript: bool = True,
        write_manual_sidecar: bool = False,
    ) -> dict[str, Any]:
        """Merge staged page partials + publish to ClickHouse."""
        return kb.submit_episode_extraction_finalize(doc_id, synthesis_json=synthesis_json, rewrite_transcript=rewrite_transcript, write_manual_sidecar=write_manual_sidecar)

    @_tool("knowledge")
    def kb_submit_episode_chunks(doc_id: str, chunks: list[dict[str, Any]]) -> dict[str, Any]:
        """Upsert optional RAG chunks with agent-submitted embedding[] vectors."""
        return kb.submit_episode_chunks(doc_id, chunks)

    return mcp


def main() -> None:
    mcp = _build()
    mcp.run(transport=os.environ.get("MCP_TRANSPORT", "stdio"))


if __name__ == "__main__":
    main()
