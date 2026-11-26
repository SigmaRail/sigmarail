"""Store-backed daily loop: Alpha → PCM → Risk.ManageRisk → Execution.

Champion (and other SigmaRailScreenerExecutionModel books) do not use Lean's default
insight pipeline. This helper is the single place that must call ManageRisk so
tranches, time-stop, ATR stops, and hedge actually run.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sigmarail_lab.runtime.decision_evidence import record_decision


def fill_session_time_rule_kind(fill_session: str | None) -> str:
    """Schedule kind for store-backed rebalance. ``moo`` must not be AfterMarketOpen."""
    session = str(fill_session or "moo").strip().lower()
    if session == "moc":
        return "before_market_close"
    return "before_market_open"


def fill_session_minutes_before(fill_session: str | None) -> int:
    """Minutes before the open/close bell.

    ``TimeRules.BeforeMarketOpen(symbol, 0)`` is 09:30 — the open — which rejects
    Python ``market_on_open_order``. Same for ``BeforeMarketClose(0)`` and
    ``market_on_close_order``.
    """
    session = str(fill_session or "moo").strip().lower()
    if session == "moc":
        return 10
    return 30


def _symbol_key(symbol: Any) -> str:
    return str(getattr(symbol, "Value", symbol))


def _portfolio_items(algorithm: Any) -> list[tuple[Any, Any]]:
    portfolio = getattr(algorithm, "Portfolio", None)
    items = getattr(portfolio, "items", None)
    if callable(items):
        try:
            return list(items())
        except Exception:
            pass
    result = []
    try:
        for item in portfolio:
            result.append((item.Key, item.Value))
    except Exception:
        pass
    return result


def merge_pcm_and_risk_targets(pcm_targets: list[Any] | None, risk_targets: list[Any] | None) -> list[Any]:
    """Union by ticker; risk overrides PCM for the same symbol."""
    by_sym: dict[str, Any] = {}
    for t in pcm_targets or []:
        if t is None:
            continue
        by_sym[_symbol_key(getattr(t, "Symbol", None))] = t
    for t in risk_targets or []:
        if t is None:
            continue
        by_sym[_symbol_key(getattr(t, "Symbol", None))] = t
    return list(by_sym.values())


def run_store_backed_rebalance(
    algorithm: Any,
    alpha: Any,
    pcm: Any,
    risk: Any,
    execution: Any,
) -> list[Any] | None:
    """One Alpha/PCM/Risk/Execute pass per calendar date.

    Runs ManageRisk even when Alpha emits no insights so open-position defense
    still fires. Returns merged targets (may be empty).
    """
    as_of_date = algorithm.Time.date()
    last = getattr(algorithm, "_sigmarail_store_loop_date", None)
    if last == as_of_date:
        return None
    algorithm._sigmarail_store_loop_date = as_of_date

    insights = []
    if alpha is not None:
        insights = alpha.Update(algorithm, None) or []
    as_of = (as_of_date - timedelta(days=1)).isoformat()
    universe_rows = getattr(algorithm, "_decision_universe_rows", {})
    selected_tickers = set(universe_rows) if isinstance(universe_rows, dict) else set()
    held_tickers = {
        _symbol_key(symbol) for symbol, holding in _portfolio_items(algorithm)
        if getattr(holding, "Invested", False)
    }
    # Long/short candidates can only come from the compiled SigmaRail query. Retain
    # insights for existing holdings so Alpha can close positions after they leave.
    insights = [
        insight for insight in insights
        if _symbol_key(getattr(insight, "Symbol", "")) in selected_tickers | held_tickers
    ]
    qualified = list(universe_rows.items())[:100] if isinstance(universe_rows, dict) else []
    insight_by_ticker = {}
    for insight in insights:
        symbol = getattr(insight, "Symbol", None)
        ticker = _symbol_key(symbol) if symbol is not None else ""
        if ticker:
            insight_by_ticker[ticker] = insight
    for rank, (ticker, row) in enumerate(qualified, start=1):
        record_decision(
            algorithm,
            ticker=ticker,
            as_of=as_of,
            stage="universe",
            outcome="qualified",
            reason="Returned by the compiled universe query; this event records membership, not a replay of every predicate.",
            inputs={key: row.get(key) for key in ("overall_score", "rs_rating", "technical_rating", "close") if isinstance(row, dict) and key in row},
            outputs={"rank": rank},
        )
        insight = insight_by_ticker.get(ticker)
        if insight is None:
            record_decision(
                algorithm,
                ticker=ticker,
                as_of=as_of,
                stage="alpha",
                outcome="no prediction emitted",
                reason="The Alpha model returned no prediction for this qualified candidate on this evaluation.",
            )
            continue
        direction = str(getattr(insight, "Direction", "unknown"))
        inputs = {"direction": direction}
        for attr in ("Confidence", "Magnitude", "Weight", "Period"):
            value = getattr(insight, attr, None)
            if value is not None:
                inputs[attr.lower()] = str(value)[:120]
        record_decision(
            algorithm,
            ticker=ticker,
            as_of=as_of,
            stage="alpha",
            outcome="prediction emitted",
            reason="Prediction emitted by the configured Alpha model.",
            inputs=inputs,
        )
    targets = []
    if pcm is not None:
        targets = pcm.CreateTargets(algorithm, insights) or []
    target_by_ticker = {
        _symbol_key(getattr(target, "Symbol", None)): target
        for target in targets if target is not None
    }
    held_tickers = {
        _symbol_key(symbol) for symbol, holding in _portfolio_items(algorithm)
        if getattr(holding, "Invested", False)
    }
    portfolio_tickers = {str(ticker) for ticker, _ in qualified}
    portfolio_tickers.update(target_by_ticker)
    portfolio_tickers.update(held_tickers)
    tags = getattr(algorithm, "_sigmarail_order_tags", {})
    pcm_matches = getattr(pcm, "_decision_rule_matches_by_ticker", {}) if pcm is not None else {}
    for ticker in sorted(portfolio_tickers):
        target = target_by_ticker.get(ticker)
        quantity = getattr(target, "Quantity", None) if target is not None else None
        rule_name = tags.get(ticker) if isinstance(tags, dict) else None
        matched_rules = pcm_matches.get(ticker, []) if isinstance(pcm_matches, dict) else []
        matched_rule = matched_rules[-1] if matched_rules else None
        record_decision(
            algorithm,
            ticker=ticker,
            as_of=as_of,
            stage="portfolio",
            outcome="target emitted" if target is not None else "no target emitted",
            reason=(f"Portfolio rule {matched_rule.get('rule')} matched." if matched_rule else
                    f"Portfolio target tagged by {rule_name}." if rule_name else
                    "No Portfolio target was emitted for this candidate or holding."),
            rule_name=matched_rule.get("rule") if matched_rule else rule_name,
            inputs={"matched_rules": matched_rules[:12]},
            outputs={"quantity": quantity} if quantity is not None else {},
        )
    risk_targets = []
    if risk is not None and hasattr(risk, "ManageRisk"):
        risk_targets = risk.ManageRisk(algorithm, targets) or []
    risk_by_ticker = {
        _symbol_key(getattr(target, "Symbol", None)): target
        for target in risk_targets if target is not None
    }
    traces = getattr(risk, "_decision_rule_trace_by_ticker", {}) if risk is not None else {}
    risk_tickers = set(risk_by_ticker) | held_tickers | portfolio_tickers
    for ticker in sorted(risk_tickers):
        target = risk_by_ticker.get(ticker)
        trace = traces.get(ticker, []) if isinstance(traces, dict) else []
        matches = [item for item in trace if item.get("matched") is True]
        matched = matches[-1] if matches else None
        record_decision(
            algorithm,
            ticker=ticker,
            as_of=as_of,
            stage="risk",
            outcome=("risk target emitted" if target is not None else
                     "no risk adjustment" if ticker in held_tickers else "not applicable (no open position)"),
            reason=(f"Risk rule {matched.get('rule')} matched." if matched else
                    "No Risk rule changed this open holding." if ticker in held_tickers else
                    "Risk management evaluates open holdings; this candidate had no open position."),
            rule_name=matched.get("rule") if matched else None,
            inputs={"rule_checks": trace[:12]},
            outputs={"quantity": getattr(target, "Quantity", None)} if target is not None else {},
        )
    merged = merge_pcm_and_risk_targets(targets, risk_targets)
    if execution is not None and hasattr(execution, "Execute"):
        merged_tickers = set()
        for target in merged:
            if target is None:
                continue
            ticker = _symbol_key(getattr(target, "Symbol", None))
            merged_tickers.add(ticker)
            record_decision(
                algorithm,
                ticker=ticker,
                as_of=as_of,
                stage="execution",
                outcome="target passed to execution model",
                reason="The strategy target was passed to the configured Execution model; this does not assert an order fill.",
                outputs={"quantity": getattr(target, "Quantity", None)},
            )
        for ticker in sorted(portfolio_tickers - merged_tickers):
            record_decision(
                algorithm,
                ticker=ticker,
                as_of=as_of,
                stage="execution",
                outcome="no execution target",
                reason="No merged Portfolio or Risk target was available to pass to Execution.",
            )
        execution.Execute(algorithm, merged)
    return merged
