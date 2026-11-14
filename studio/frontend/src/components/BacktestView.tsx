import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { backtestRunFromPath, backtestRunPath, strategyPath, type BacktestSection } from "../routes";
import {
  fetchBacktestReport,
  fetchBacktestRuns,
  fetchBacktestJobs,
  fetchRunArtifactPreview,
  fetchRunArtifacts,
  fetchRunClosedTrades,
  fetchRunDaySnapshots,
  fetchRunMonthlyReturns,
  fetchRunOrders,
  fetchRunTradeAnalytics,
} from "../api/backtests";
import type {
  BacktestJobListItem,
  BacktestPrefill,
  BacktestReport,
  BacktestRunSummary,
  BacktestSpecSummary,
  ClosedTradeItem,
  SavedScreen,
  ScreenPreset,
  UniverseQueryV1,
  WorkbenchTab,
} from "../types";
import { BacktestComposePanel } from "./BacktestComposePanel";
import { MonthlyReturnsHeatmap } from "./MonthlyReturnsHeatmap";
import { TradeAnalyticsPanel } from "./TradeAnalyticsPanel";
import { ClosedTradesTable } from "./ClosedTradesTable";
import { TradeCandlestickModal } from "./TradeCandlestickModal";
import { RegimeSectorAttribution } from "./RegimeSectorAttribution";
import { MultiRunCompareView } from "./MultiRunCompareView";
import { ActiveBacktestBanner } from "./ActiveBacktestBanner";
import { LiveLogDrawer } from "./LiveLogDrawer";
import { PromotePanel } from "./PromotePanel";
import { OptimizerView } from "./OptimizerView";
import { UniversalCandidateExplorer, type CandidateItem } from "./studio/UniversalCandidateExplorer";
import { BenchmarkComparisonPanel } from "./studio/BenchmarkComparisonPanel";
import { DayZeroShiftedTimelinePanel } from "./studio/DayZeroShiftedTimelinePanel";
import { RecommendationsPanel } from "./RecommendationsPanel";
import { UnderwaterDrawdownPanel } from "./studio/UnderwaterDrawdownPanel";
import { AssetAllocationTreemap } from "./studio/AssetAllocationTreemap";
import { PortfolioExposurePanel } from "./studio/PortfolioExposurePanel";
import { RollingStatsMatrix } from "./studio/RollingStatsMatrix";
import { CopyIdBadge } from "./CopyIdBadge";
import { RunFilterBar, type RunFilters, INITIAL_RUN_FILTERS } from "./RunFilterBar";
import { RunScreenerTable } from "./RunScreenerTable";

function truncateId(id: string, head = 8, tail = 6): string {
  if (id.length <= head + tail + 1) return id;
  return `${id.slice(0, head)}…${id.slice(-tail)}`;
}

function formatPct(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(2)}%`;
}

function formatNum(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

function formatPeriod(run: BacktestRunSummary): string {
  const start = run.period_start ?? "";
  const end = run.period_end ?? "";
  if (!start && !end) return "—";
  if (start && end) return `${start} → ${end}`;
  return start || end;
}

function metricLabel(key: string): string {
  const labels: Record<string, string> = {
    total_return: "Total return",
    annual_return: "Annual return",
    sharpe_ratio: "Sharpe",
    sortino_ratio: "Sortino",
    max_drawdown: "Max drawdown",
    win_rate: "Win rate",
    profit_factor: "Profit factor",
    total_orders: "Orders",
    total_fees: "Fees",
    start_equity: "Start equity",
    end_equity: "End equity",
  };
  return labels[key] ?? key.replace(/_/g, " ");
}

function formatMetricValue(key: string, value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  if (
    key.includes("return") ||
    key.includes("drawdown") ||
    key === "win_rate"
  ) {
    return formatPct(value);
  }
  if (key.includes("equity") || key === "total_fees") {
    return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  }
  if (key === "total_orders") return String(Math.round(value));
  return formatNum(value);
}

function RunListItem({
  run,
  selected,
  checked,
  onSelect,
  onToggleCheck,
  onViewLog,
}: {
  run: BacktestRunSummary;
  selected: boolean;
  checked?: boolean;
  onSelect: () => void;
  onToggleCheck?: () => void;
  onViewLog?: (jobId: string, irId?: string | null, status?: string) => void;
}) {
  const isDone = run.status === "done";
  const isRunning = run.status === "running";
  const isFailed = run.status === "failed";
  const isProfit = (run.total_return ?? 0) >= 0;

  return (
    <div
      onClick={onSelect}
      className={`group relative flex w-full cursor-pointer items-start gap-2.5 border-b border-line px-3 py-2.5 text-left transition-colors ${
        selected
          ? "border-l-2 border-l-accent bg-accent-soft/60"
          : "border-l-2 border-l-transparent hover:bg-surface-sunk"
      }`}
    >
      <div className="pt-0.5" onClick={(e) => e.stopPropagation()}>
        <input
          type="checkbox"
          checked={checked}
          disabled={!isDone}
          onChange={() => onToggleCheck && onToggleCheck()}
          className="rounded border-line bg-surface text-accent focus:ring-accent disabled:opacity-30"
          title="Select for comparison"
        />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-1">
          <div className="flex items-center gap-1.5 min-w-0">
            {isDone ? (
              <span className="h-2 w-2 shrink-0 rounded-full bg-emerald-400" title="Completed run" />
            ) : isRunning ? (
              <span className="h-2 w-2 shrink-0 rounded-full bg-sky-400 animate-pulse" title="Running backtest" />
            ) : isFailed ? (
              <span className="h-2 w-2 shrink-0 rounded-full bg-rose-400" title={run.error_message || "Failed"} />
            ) : (
              <span className="h-2 w-2 shrink-0 rounded-full bg-amber-400" />
            )}
            <span className="font-mono text-[11px] font-semibold text-ink truncate">
              {truncateId(run.run_id)}
            </span>
          </div>

          {isFailed && onViewLog ? (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onViewLog(run.run_id, run.ir_id, run.status);
              }}
              className="text-[10px] text-ink-muted hover:text-ink"
              title="View error log"
            >
              📜
            </button>
          ) : isRunning && run.progress_pct ? (
            <span className="font-mono text-[9px] font-bold text-sky-400">
              {Math.round(run.progress_pct * 100)}%
            </span>
          ) : null}
        </div>

        {run.spec_title ? (
          <div className="mt-0.5 truncate text-[11px] font-medium text-ink" title={run.spec_title}>
            {run.spec_title}
          </div>
        ) : null}

        <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[9.5px] text-ink-muted font-mono">
          {run.alpha_type ? (
            <span className="rounded bg-surface-sunk px-1.5 py-0.2 text-[9px] text-accent-ink border border-line/60">
              {run.alpha_type}
            </span>
          ) : null}
          {run.ir_schema_version ? (
            <span className="rounded bg-surface px-1 py-0.2 text-[8.5px] text-ink-muted border border-line" title={`Spec Schema v${run.ir_schema_version}`}>
              v{run.ir_schema_version}
            </span>
          ) : null}
          {run.ir_content_hash ? (
            <span className="rounded bg-surface px-1 py-0.2 text-[8.5px] text-ink-faint border border-line" title={`Immutable Content Hash: ${run.ir_content_hash}`}>
              #{run.ir_content_hash.slice(0, 8)}
            </span>
          ) : null}
          {run.revision_stale ? (
            <span
              className="rounded bg-amber-500/15 px-1 py-0.2 text-[8.5px] text-amber-400 border border-amber-500/30"
              title={`Produced from an earlier revision — ran #${String(run.ir_content_hash ?? "").slice(0, 8)}, spec is now #${String(run.spec_ir_content_hash ?? "").slice(0, 8)}`}
            >
              ⚠ older revision
            </span>
          ) : null}
          <span>{formatPeriod(run)}</span>
        </div>

        {isDone ? (
          <div className="mt-1.5 flex flex-wrap gap-x-2.5 gap-y-0.5 text-[10px] font-mono">
            <span className="text-ink-muted">
              ret{" "}
              <span className={`font-semibold ${isProfit ? "text-emerald-400" : "text-rose-400"}`}>
                {isProfit ? "+" : ""}{formatPct(run.total_return)}
              </span>
            </span>
            <span className="text-ink-muted">
              sharpe{" "}
              <span className="font-semibold text-ink">
                {formatNum(run.sharpe_ratio)}
              </span>
            </span>
            <span className="text-ink-muted">
              dd{" "}
              <span className="font-semibold text-rose-400/90">
                {formatPct(run.max_drawdown)}
              </span>
            </span>
          </div>
        ) : isFailed ? (
          <div className="mt-1 text-[9.5px] text-rose-400 truncate" title={run.error_message || "Failed"}>
            {run.error_message || "Execution failed"}
          </div>
        ) : null}

        {run.run_timestamp ? (
          <div className="mt-1 font-mono text-[9px] text-ink-faint">
            {run.run_timestamp.slice(0, 16)}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function ReportPanel({
  report,
  runSubTab,
  onRunSubTabChange,
  onPromote,
  onEditInComposer,
}: {
  report: BacktestReport;
  runSubTab: BacktestSection;
  onRunSubTabChange: (section: BacktestSection) => void;
  onPromote?: () => void;
  onEditInComposer?: () => void;
}) {
  const metricEntries = useMemo(() => {
    const metrics = report.metrics ?? {};
    return Object.entries(metrics).filter(([, v]) => v != null);
  }, [report.metrics]);

  const [expandedArtifact, setExpandedArtifact] = useState<string | null>(null);
  const [snapshotIndex, setSnapshotIndex] = useState(0);
  const [selectedTradeModal, setSelectedTradeModal] = useState<ClosedTradeItem | null>(null);

  const handleSelectTrade = useCallback((trade: ClosedTradeItem | null) => {
    setSelectedTradeModal(trade);
    const url = new URL(window.location.href);
    if (trade) {
      url.searchParams.set("trade", trade.id);
      url.searchParams.set("campaign", trade.symbol);
    } else {
      url.searchParams.delete("trade");
      url.searchParams.delete("campaign");
      url.searchParams.delete("symbol");
    }
    window.history.replaceState({}, "", url.toString());
  }, []);

  const monthlyReturnsQuery = useQuery({
    queryKey: ["backtest-monthly-returns", report.run_id],
    queryFn: () => fetchRunMonthlyReturns(report.run_id),
    enabled: Boolean(report.run_id),
  });

  const tradeAnalyticsQuery = useQuery({
    queryKey: ["backtest-trade-analytics", report.run_id],
    queryFn: () => fetchRunTradeAnalytics(report.run_id),
    enabled: Boolean(report.run_id),
  });

  const artifactsQuery = useQuery({
    queryKey: ["backtest-artifacts", report.run_id],
    queryFn: () => fetchRunArtifacts(report.run_id),
    enabled: Boolean(report.run_id),
  });

  const artifactPreviewQuery = useQuery({
    queryKey: ["backtest-artifact-preview", report.run_id, expandedArtifact],
    queryFn: () => fetchRunArtifactPreview(report.run_id, expandedArtifact!),
    enabled: Boolean(report.run_id && expandedArtifact),
  });

  const ordersQuery = useQuery({
    queryKey: ["backtest-orders", report.run_id],
    queryFn: () => fetchRunOrders(report.run_id, 100),
    enabled: Boolean(report.run_id),
  });

  const closedTradesQuery = useQuery({
    queryKey: ["backtest-closed-trades", report.run_id],
    queryFn: () => fetchRunClosedTrades(report.run_id, 500),
    enabled: Boolean(report.run_id),
  });

  // Deep-linking: sync URL ?trade=<id> and ?campaign=<symbol> to modal on load / data arrival
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const tradeParam = params.get("trade");
    const campaignParam = params.get("campaign") || params.get("symbol");
    if (!tradeParam && !campaignParam) return;
    if (selectedTradeModal) return;

    const allTrades = [
      ...(closedTradesQuery.data?.trades ?? []),
      ...(closedTradesQuery.data?.open_trades ?? []),
    ];
    if (allTrades.length === 0) return;

    if (tradeParam) {
      const match = allTrades.find((t) => t.id === tradeParam);
      if (match) {
        setSelectedTradeModal(match);
        return;
      }
    }
    if (campaignParam) {
      const match = allTrades.find(
        (t) => t.symbol.toUpperCase() === campaignParam.toUpperCase(),
      );
      if (match) {
        setSelectedTradeModal(match);
      }
    }
  }, [closedTradesQuery.data, selectedTradeModal]);

  const snapshotsQuery = useQuery({
    queryKey: ["backtest-day-snapshots", report.run_id],
    queryFn: () => fetchRunDaySnapshots(report.run_id),
    enabled: Boolean(report.run_id),
  });

  const snapshots = snapshotsQuery.data?.snapshots ?? [];
  const activeSnapshot =
    snapshots.length > 0
      ? snapshots[Math.min(snapshotIndex, snapshots.length - 1)]
      : null;

  const zeroOrders =
    report.metrics?.total_orders === 0 ||
    (ordersQuery.data?.total === 0 && ordersQuery.isSuccess);

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4">
      {/* Header Info */}
      <div className="mb-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <CopyIdBadge
              id={report.run_id}
              label="Run ID"
              truncate={false}
              sqlQuery={`SELECT * FROM strategy_runs FINAL WHERE run_id = '${report.run_id}'`}
            />
            {report.ir_id ? (
              <CopyIdBadge
                id={report.ir_id}
                label="IR Spec"
                head={12}
                tail={8}
                sqlQuery={`SELECT * FROM strategy_algorithm_specs FINAL WHERE ir_id = '${report.ir_id}'`}
              />
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            {onEditInComposer && (
              <button
                type="button"
                onClick={onEditInComposer}
                className="rounded border border-line bg-surface-sunk px-3 py-1.5 text-[12px] font-semibold text-accent hover:bg-surface hover:border-accent/40 flex items-center gap-1.5"
              >
                <span>✏️</span>
                <span>Open in Composer</span>
              </button>
            )}
            {onPromote && report.ir_id ? (
              <button
                type="button"
                onClick={onPromote}
                className="rounded border border-line bg-surface-sunk px-3 py-1.5 text-[12px] font-medium text-ink hover:bg-surface"
              >
                Promote to paper
              </button>
            ) : null}
          </div>
        </div>
        {report.period ? (
          <div className="mt-1 text-[12px] text-ink-muted">
            Period:{" "}
            <span className="font-medium text-ink">
              {report.period.start || "—"} → {report.period.end || "—"}
            </span>
            {report.run_timestamp ? (
              <span className="ml-3 font-mono text-[11px] text-ink-faint">
                · {report.run_timestamp}
              </span>
            ) : null}
          </div>
        ) : null}
      </div>

      {/* Subtab Navigation Bar */}
      <div className="mb-4 flex gap-1 border-b border-line pb-2">
        <button
          type="button"
          onClick={() => onRunSubTabChange("overview")}
          className={`rounded px-3 py-1.5 text-[12px] font-medium transition-colors ${
            runSubTab === "overview"
              ? "bg-accent text-accent-ink font-semibold"
              : "text-ink-muted hover:bg-surface-sunk hover:text-ink"
          }`}
        >
          Overview & Heatmap
        </button>
        <button
          type="button"
          onClick={() => onRunSubTabChange("trades")}
          className={`rounded px-3 py-1.5 text-[12px] font-medium transition-colors ${
            runSubTab === "trades"
              ? "bg-accent text-accent-ink font-semibold"
              : "text-ink-muted hover:bg-surface-sunk hover:text-ink"
          }`}
        >
          Trades & Excursions {closedTradesQuery.data?.total ? `(${closedTradesQuery.data.total})` : ""}
        </button>
        <button
          type="button"
          onClick={() => onRunSubTabChange("attribution")}
          className={`rounded px-3 py-1.5 text-[12px] font-medium transition-colors ${
            runSubTab === "attribution"
              ? "bg-accent text-accent-ink font-semibold"
              : "text-ink-muted hover:bg-surface-sunk hover:text-ink"
          }`}
        >
          Attribution & Macro
        </button>
        <button
          type="button"
          onClick={() => onRunSubTabChange("scrubber")}
          className={`rounded px-3 py-1.5 text-[12px] font-medium transition-colors ${
            runSubTab === "scrubber"
              ? "bg-accent text-accent-ink font-semibold"
              : "text-ink-muted hover:bg-surface-sunk hover:text-ink"
          }`}
        >
          Day Scrubber {snapshots.length > 0 ? `(${snapshots.length}d)` : ""}
        </button>
      </div>

      {zeroOrders ? (
        <section className="mb-4 rounded border border-warn/30 bg-warn-soft px-3 py-2">
          <p className="text-[12px] font-medium text-warn">No orders recorded</p>
          <p className="mt-1 text-[11px] text-warn/90">
            Check that <span className="font-mono">vera_query_service</span> is
            running (<span className="font-mono">VERA_QUERY_URL</span>) and the
            universe returned rows for the backtest window.
          </p>
        </section>
      ) : null}

      {/* OVERVIEW SUBTAB */}
      {runSubTab === "overview" ? (
        <>
          {/* 0. Actionable Recommendations */}
          <RecommendationsPanel report={report} />

          {/* 1. Benchmark Comparison & Active Risk Card */}
          <section className="mb-4">
            <BenchmarkComparisonPanel runId={report.run_id} />
          </section>

          {/* 1b. Shifted Timeline Matrix (Day 0 Baseline) */}
          <section className="mb-4">
            <DayZeroShiftedTimelinePanel runId={report.run_id} />
          </section>

          {/* 2. Underwater Drawdown & Recovery Analysis */}
          <section className="mb-4">
            <UnderwaterDrawdownPanel runId={report.run_id} />
          </section>

          {/* 3. QuantConnect-Style Asset Volume Treemap & Capital Concentration */}
          <section className="mb-4">
            <AssetAllocationTreemap runId={report.run_id} />
          </section>

          {/* 4. Portfolio Exposure Ribbon & Strategy Capacity */}
          <section className="mb-4">
            <PortfolioExposurePanel runId={report.run_id} />
          </section>

          {/* 5. Rolling Performance Statistics Matrix */}
          <section className="mb-4">
            <RollingStatsMatrix runId={report.run_id} />
          </section>

          {/* Monthly Returns Heatmap */}
          <MonthlyReturnsHeatmap
            data={monthlyReturnsQuery.data}
            isLoading={monthlyReturnsQuery.isLoading}
          />

          {/* Core Metrics Grid */}
          {metricEntries.length > 0 ? (
            <section className="mb-4">
              <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
                Metrics
              </h3>
              <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
                {metricEntries.map(([key, value]) => (
                  <div
                    key={key}
                    className="rounded border border-line bg-surface px-2.5 py-2"
                  >
                    <div className="text-[10px] text-ink-muted">
                      {metricLabel(key)}
                    </div>
                    <div className="mt-0.5 text-[13px] font-semibold tabular-nums text-ink">
                      {formatMetricValue(key, value)}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ) : null}
        </>
      ) : null}

      {/* TRADES & EXCURSIONS SUBTAB */}
      {runSubTab === "trades" ? (
        <>
          {/* Trade Quality Scorecards & MAE/MFE Scatter */}
          <TradeAnalyticsPanel
            data={tradeAnalyticsQuery.data}
            isLoading={tradeAnalyticsQuery.isLoading}
          />

          {/* Closed & Open Trades DataGrid */}
          <ClosedTradesTable
            trades={closedTradesQuery.data?.trades ?? []}
            openTrades={closedTradesQuery.data?.open_trades ?? []}
            total={closedTradesQuery.data?.total}
            openTotal={closedTradesQuery.data?.open_count}
            isLoading={closedTradesQuery.isLoading}
            onSelectTrade={(t) => handleSelectTrade(t)}
          />

          {/* Raw Orders Table */}
          {ordersQuery.data && ordersQuery.data.count > 0 ? (
            <section className="mb-4">
              <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
                Execution Orders Log ({ordersQuery.data.total})
              </h3>
              <div className="mt-2 max-h-56 overflow-auto rounded border border-line bg-surface">
                <table className="w-full text-left text-[11px]">
                  <thead className="sticky top-0 bg-surface-sunk text-ink-faint">
                    <tr>
                      <th className="px-2 py-1">Time</th>
                      <th className="px-2 py-1">Symbol</th>
                      <th className="px-2 py-1">Direction</th>
                      <th className="px-2 py-1">Quantity</th>
                      <th className="px-2 py-1">Fill Price</th>
                      <th className="px-2 py-1">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ordersQuery.data.orders.map((o, idx) => {
                      const row = o as Record<string, unknown>;
                      const timeNum = typeof row.time === "number" ? row.time : Number(row.time);
                      const timeStr = !Number.isNaN(timeNum) && timeNum > 0
                        ? new Date(timeNum > 1e12 ? timeNum : timeNum * 1000).toISOString().slice(0, 10)
                        : "—";
                      const dir = String(row.direction ?? row.Direction ?? "—").toLowerCase();
                      const qty = row.quantity != null ? Number(row.quantity).toLocaleString() : "—";
                      const fillPx = row.fillPrice != null && Number(row.fillPrice) > 0 ? `$${Number(row.fillPrice).toFixed(2)}` : "—";
                      const sym = String(row.symbolValue ?? row.Symbol ?? row.symbol ?? "—");
                      return (
                        <tr
                          key={idx}
                          onClick={() => {
                            if (!sym || sym === "—") return;
                            const allTrades = [
                              ...(closedTradesQuery.data?.trades ?? []),
                              ...(closedTradesQuery.data?.open_trades ?? []),
                            ];
                            const match = allTrades.find(
                              (t) => t.symbol.toUpperCase() === sym.toUpperCase(),
                            );
                            if (match) {
                              handleSelectTrade(match);
                            } else {
                              handleSelectTrade({
                                id: String(row.id ?? `order_${idx}`),
                                symbol: sym,
                                entry_time: timeStr !== "—" ? timeStr : new Date().toISOString().slice(0, 10),
                                entry_price: row.fillPrice != null && Number(row.fillPrice) > 0 ? Number(row.fillPrice) : 0,
                                direction: dir,
                                quantity: row.quantity != null ? Number(row.quantity) : 0,
                                profit_loss: 0,
                                return_pct: 0,
                                is_win: true,
                                status: "OPEN",
                              });
                            }
                          }}
                          className="border-t border-line hover:bg-surface-sunk/60 cursor-pointer transition-colors"
                          title={`Click to view ${sym} candlestick chart & campaign`}
                        >
                          <td className="px-2 py-1 font-mono text-[10px] text-ink-muted">{timeStr}</td>
                          <td className="px-2 py-1 font-mono font-medium text-ink">
                            {sym}
                          </td>
                          <td className="px-2 py-1">
                            <span className={`inline-block font-semibold ${dir === "buy" ? "text-emerald-500" : dir === "sell" ? "text-rose-500" : "text-ink"}`}>
                              {dir.toUpperCase()}
                            </span>
                          </td>
                          <td className="px-2 py-1 tabular-nums text-ink">{qty}</td>
                          <td className="px-2 py-1 tabular-nums text-ink">{fillPx}</td>
                          <td className="px-2 py-1 text-ink-muted">{String(row.status ?? row.Status ?? "—")}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}
        </>
      ) : null}

      {/* ATTRIBUTION & MACRO SUBTAB */}
      {runSubTab === "attribution" ? (
        <RegimeSectorAttribution runId={report.run_id} />
      ) : null}

      {/* DAY SCRUBBER SUBTAB */}
      {runSubTab === "scrubber" ? (
        snapshots.length > 0 ? (
          <section className="mb-4 space-y-3">
            <div className="rounded-lg border border-line bg-surface p-3.5 shadow-sm">
              <div className="flex items-center justify-between">
                <h3 className="text-[12px] font-bold text-ink">
                  Point-in-Time Day Scrubber
                </h3>
                <span className="font-mono text-[11px] text-accent font-semibold">
                  Snapshot {snapshotIndex + 1} of {snapshots.length}
                </span>
              </div>
              <input
                type="range"
                min={0}
                max={Math.max(0, snapshots.length - 1)}
                value={Math.min(snapshotIndex, snapshots.length - 1)}
                onChange={(e) => setSnapshotIndex(Number(e.target.value))}
                className="mt-3 w-full"
              />
              {activeSnapshot ? (
                <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2 rounded border border-line bg-surface-sunk p-2.5 text-[11px]">
                  <div>
                    <span className="text-[9.5px] text-ink-faint block uppercase font-bold">Session Date</span>
                    <span className="font-mono font-bold text-ink">{String(activeSnapshot.date ?? "—")}</span>
                  </div>
                  <div>
                    <span className="text-[9.5px] text-ink-faint block uppercase font-bold">Universe As-Of</span>
                    <span className="font-mono font-bold text-ink">{String(activeSnapshot.as_of ?? "—")}</span>
                  </div>
                  <div>
                    <span className="text-[9.5px] text-ink-faint block uppercase font-bold">Portfolio Equity</span>
                    <span className="font-mono font-bold text-emerald-400">
                      {activeSnapshot.equity != null ? `$${Number(activeSnapshot.equity).toLocaleString()}` : "—"}
                    </span>
                  </div>
                  <div>
                    <span className="text-[9.5px] text-ink-faint block uppercase font-bold">Active Holdings</span>
                    <span className="font-mono font-bold text-ink">
                      {Array.isArray(activeSnapshot.holdings) ? `${activeSnapshot.holdings.length} positions` : "0 positions"}
                    </span>
                  </div>
                </div>
              ) : null}
            </div>

            {activeSnapshot && (
              <UniversalCandidateExplorer
                candidates={(() => {
                  const holdingTickers = new Set(
                    (activeSnapshot.holdings || []).map((h: any) =>
                      typeof h === "string" ? h : h.ticker || h.symbol
                    )
                  );
                  return (activeSnapshot.candidates || []).map((c: any) => {
                    const ticker = typeof c === "string" ? c : c.ticker;
                    const isHolding = holdingTickers.has(ticker);
                    return {
                      ticker,
                      price: c.price ?? c.close,
                      rs_rating: c.rs_rating,
                      technical_rating: c.technical_rating,
                      setup_quality_rating: c.setup_quality_rating,
                      atr_pct: c.atr_pct,
                      sector: c.sector,
                      decision: isHolding ? "bought" : "passed_rank",
                      target_weight: isHolding ? 0.08 : undefined,
                    } as CandidateItem;
                  });
                })()}
                mode="historical"
                asOfDate={String(activeSnapshot.date ?? activeSnapshot.as_of ?? "")}
                title="Point-in-Time Universe & Attribution"
                subtitle={`Candidates evaluated by strategy on ${activeSnapshot.date}`}
              />
            )}
          </section>
        ) : (
          <div className="rounded border border-line bg-surface p-4 text-center text-[12px] text-ink-muted">
            No daily snapshots recorded for this run.
          </div>
        )
      ) : null}

      {artifactsQuery.data && artifactsQuery.data.count > 0 ? (
        <section className="mb-4">
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
            Artifacts
          </h3>
          <ul className="mt-2 space-y-1">
            {artifactsQuery.data.artifacts.map((a) => {
              const atype = String(a.artifact_type ?? "");
              const open = expandedArtifact === atype;
              return (
                <li key={atype} className="rounded border border-line bg-surface">
                  <button
                    type="button"
                    className="flex w-full items-baseline justify-between gap-2 px-2.5 py-1.5 font-mono text-[11px] hover:bg-surface-sunk"
                    onClick={() =>
                      setExpandedArtifact((prev) => (prev === atype ? null : atype))
                    }
                  >
                    <span className="text-ink">{atype}</span>
                    <span className="text-ink-faint">
                      {a.json_bytes != null
                        ? `${a.json_bytes.toLocaleString()} B`
                        : "—"}{" "}
                      · {open ? "Collapse" : "Expand"}
                    </span>
                  </button>
                  {open ? (
                    <div className="border-t border-line px-2.5 py-2">
                      {artifactPreviewQuery.isLoading ? (
                        <p className="text-[11px] text-ink-muted">Loading…</p>
                      ) : artifactPreviewQuery.isError ? (
                        <p className="text-[11px] text-danger">
                          {(artifactPreviewQuery.error as Error).message}
                        </p>
                      ) : artifactPreviewQuery.data?.error ? (
                        <p className="text-[11px] text-warn">
                          {artifactPreviewQuery.data.error}
                        </p>
                      ) : (
                        <pre className="max-h-64 overflow-auto font-mono text-[10px] text-ink-muted whitespace-pre-wrap">
                          {artifactPreviewQuery.data?.preview ?? "—"}
                        </pre>
                      )}
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      {report.highlights && report.highlights.length > 0 ? (
        <section className="mb-4">
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
            Highlights
          </h3>
          <ul className="mt-2 space-y-1">
            {report.highlights.map((h) => (
              <li
                key={h}
                className="rounded border border-line bg-surface px-2.5 py-1.5 text-[12px] text-ink"
              >
                {h}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {report.warnings && report.warnings.length > 0 ? (
        <section className="mb-4">
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-warn">
            Warnings
          </h3>
          <ul className="mt-2 space-y-1">
            {report.warnings.map((w) => (
              <li
                key={w}
                className="rounded border border-warn/30 bg-warn-soft px-2.5 py-1.5 text-[12px] text-warn"
              >
                {w}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {report.provenance ? (
        <section>
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
            Provenance
          </h3>
          <dl className="mt-2 grid grid-cols-1 gap-1.5 text-[12px] sm:grid-cols-2">
            {Object.entries(report.provenance)
              .filter(([, v]) => v != null && v !== "")
              .map(([key, value]) => (
                <div key={key} className="flex gap-2">
                  <dt className="font-mono text-[10px] text-ink-faint">{key}</dt>
                  <dd className="font-mono text-ink-muted break-all">{String(value)}</dd>
                </div>
              ))}
          </dl>
        </section>
      ) : null}

      {selectedTradeModal ? (
        <TradeCandlestickModal
          trade={selectedTradeModal}
          runId={report.run_id}
          onClose={() => handleSelectTrade(null)}
        />
      ) : null}
    </div>
  );
}

function JobsStrip({
  onViewLog,
  onSelectRun,
  selectedRunId,
}: {
  onViewLog?: (jobId: string, irId?: string | null, status?: string) => void;
  onSelectRun?: (runId: string) => void;
  selectedRunId?: string | null;
}) {
  const jobsQuery = useQuery({
    queryKey: ["backtest-jobs", "recent"],
    queryFn: () => fetchBacktestJobs(15),
    refetchInterval: (query) => {
      const jobs = query.state.data ?? [];
      const live = jobs.some(
        (j) => j.status === "pending" || j.status === "running",
      );
      return live ? 2500 : 20_000;
    },
  });
  const jobs: BacktestJobListItem[] = jobsQuery.data ?? [];
  const liveJobs = jobs.filter(
    (j) => j.status === "pending" || j.status === "running",
  );
  const recent = liveJobs.length > 0 ? liveJobs : jobs.slice(0, 5);

  if (jobsQuery.isLoading && jobs.length === 0) {
    return (
      <div className="border-b border-line px-3 py-2 text-[11px] text-ink-muted">
        Loading jobs…
      </div>
    );
  }
  if (jobs.length === 0) return null;

  return (
    <div className="border-b border-line bg-surface px-3 py-2">
      <div className="flex items-center justify-between text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
        <span>Queue / jobs</span>
        {liveJobs.length > 0 ? (
          <span className="flex items-center gap-1 text-accent-ink font-bold">
            <span className="inline-block h-1.5 w-1.5 rounded-full bg-accent animate-pulse" />
            {liveJobs.length} active
          </span>
        ) : null}
      </div>
      <ul className="mt-1.5 max-h-36 space-y-1.5 overflow-y-auto">
        {recent.map((j) => {
          const isRunning = j.status === "running";
          const pct = Math.min(100, Math.max(0, Math.round((j.progress_pct ?? 0) * 100)));
          const isSelected = j.job_id === selectedRunId;
          return (
            <li
              key={j.job_id}
              onClick={() => onSelectRun?.(j.job_id)}
              className={`cursor-pointer rounded border p-1.5 font-mono text-[10px] transition-colors ${
                isSelected
                  ? "border-accent/40 bg-accent/15"
                  : "border-line/50 bg-surface-sunk/60 hover:bg-surface-sunk"
              }`}
            >
              <div className="flex items-baseline justify-between gap-1">
                <span className="min-w-0 truncate font-semibold text-ink" title={j.job_id}>
                  {truncateId(j.job_id, 6, 4)}
                </span>
                <div className="flex items-center gap-1.5">
                  {onViewLog ? (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onViewLog(j.job_id, j.ir_id, j.status);
                      }}
                      className="text-[10px] text-ink-muted hover:text-ink"
                      title="View live log"
                    >
                      📜
                    </button>
                  ) : null}
                  <span
                    className={
                      j.status === "done"
                        ? "text-accent font-semibold"
                        : j.status === "failed"
                          ? "text-danger font-semibold"
                          : j.status === "cancelled"
                            ? "text-ink-muted"
                            : "text-accent-ink font-bold"
                    }
                  >
                    {isRunning && pct > 0 ? `${pct}%` : j.status}
                  </span>
                </div>
              </div>
              {isRunning ? (
                <div className="mt-1 space-y-0.5">
                  <div className="h-1 w-full overflow-hidden rounded-full bg-surface-raised">
                    <div
                      className="h-full bg-accent transition-all duration-300"
                      style={{ width: `${Math.max(pct, 5)}%` }}
                    />
                  </div>
                  {j.current_sim_date ? (
                    <div className="text-[8.5px] text-ink-muted truncate">
                      sim: {j.current_sim_date}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function RunsTab({
  onPromoteRun,
  onEditInComposer,
}: {
  onPromoteRun?: (runId: string) => void;
  onEditInComposer?: (run: BacktestRunSummary) => void;
}) {
  const location = useLocation();
  const navigate = useNavigate();
  const { runId: selectedRunId, section } = backtestRunFromPath(location.pathname);

  const setSelectedRunId = useCallback(
    (id: string | null) => {
      navigate(id ? backtestRunPath(id) : "/backtests");
    },
    [navigate],
  );

  const initialCompareRunIds = useMemo(() => {
    const p = new URLSearchParams(window.location.search);
    const cr = p.get("compare_runs") || p.get("compare");
    if (!cr) return [];
    return cr
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }, []);

  const initialIrId = useMemo(() => {
    const p = new URLSearchParams(window.location.search);
    return p.get("ir_id") || p.get("spec") || undefined;
  }, []);

  const [checkedRunIds, setCheckedRunIds] = useState<string[]>(initialCompareRunIds);
  const [isCompareMode, setIsCompareMode] = useState<boolean>(
    initialCompareRunIds.length >= 2 || new URLSearchParams(window.location.search).get("view") === "compare",
  );
  const [viewMode, setViewMode] = useState<"split" | "table">("split");
  const [filters, setFilters] = useState<RunFilters>(() => ({
    ...INITIAL_RUN_FILTERS,
    irId: initialIrId,
  }));
  const [logModalJob, setLogModalJob] = useState<{
    jobId: string;
    irId?: string | null;
    status?: string;
  } | null>(null);

  // Synchronize comparison run IDs, ir_id filter, and view mode to the address bar
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (checkedRunIds.length > 0) {
      params.set("compare_runs", checkedRunIds.join(","));
    } else {
      params.delete("compare_runs");
      params.delete("compare");
    }
    if (filters.irId && filters.irId !== "all") {
      params.set("ir_id", filters.irId);
    } else {
      params.delete("ir_id");
      params.delete("spec");
    }
    if (isCompareMode) {
      params.set("view", "compare");
    } else {
      params.delete("view");
    }
    const newUrl = `${window.location.pathname}?${params.toString()}`;
    window.history.replaceState(null, "", newUrl);
  }, [checkedRunIds, filters.irId, isCompareMode]);

  const jobsQuery = useQuery({
    queryKey: ["backtest-jobs", "recent", filters.irId],
    queryFn: () => fetchBacktestJobs(15),
    refetchInterval: (query) => {
      const jobs = query.state.data ?? [];
      const live = jobs.some(
        (j) => j.status === "pending" || j.status === "running",
      );
      return live ? 2500 : 20_000;
    },
  });

  const runsQuery = useQuery({
    queryKey: [
      "backtest-runs",
      filters.status,
      filters.irId,
      filters.minSharpe,
      filters.returnTier,
      filters.maxDd,
      filters.search,
    ],
    queryFn: () =>
      fetchBacktestRuns({
        limit: 100,
        status: filters.status,
        irId: filters.irId && filters.irId !== "all" ? filters.irId : undefined,
        minSharpe:
          filters.minSharpe !== "all"
            ? parseFloat(filters.minSharpe)
            : undefined,
        minReturn:
          filters.returnTier === "positive"
            ? 0.0001
            : filters.returnTier === "high"
              ? 0.1
              : undefined,
        maxDd:
          filters.maxDd !== "all" ? parseFloat(filters.maxDd) : undefined,
        search: filters.search.trim() || undefined,
        includeJobs: true,
      }),
  });

  const runs = runsQuery.data ?? [];
  const jobs = jobsQuery.data ?? [];

  // Client-side additional facet filtering
  const filteredRuns = useMemo(() => {
    return runs.filter((r) => {
      if (filters.irId && filters.irId !== "all" && r.ir_id !== filters.irId) {
        return false;
      }
      if (filters.alphaType !== "all" && r.alpha_type !== filters.alphaType) {
        return false;
      }
      if (
        filters.universeType !== "all" &&
        r.universe_type !== filters.universeType
      ) {
        return false;
      }
      if (
        filters.returnTier === "negative" &&
        (r.total_return == null || r.total_return >= 0)
      ) {
        return false;
      }
      if (filters.minOrders && (!r.total_orders || r.total_orders <= 0)) {
        return false;
      }
      return true;
    });
  }, [runs, filters]);

  // Auto-select the first run when on the bare /backtests list (no runId in the path).
  useEffect(() => {
    if (selectedRunId || isCompareMode) return;
    if (filteredRuns.length > 0) {
      navigate(backtestRunPath(filteredRuns[0].run_id), { replace: true });
    }
  }, [selectedRunId, isCompareMode, filteredRuns, navigate]);

  // Canonicalize /backtests/:runId (no section) -> /overview.
  useEffect(() => {
    if (!selectedRunId) return;
    const segs = location.pathname.split("/").filter(Boolean);
    if (segs[0] === "backtests" && segs.length === 2) {
      navigate(backtestRunPath(selectedRunId, "overview"), { replace: true });
    }
  }, [selectedRunId, location.pathname, navigate]);

  const handleToggleCheck = (runId: string) => {
    setCheckedRunIds((prev) => {
      const next = prev.includes(runId)
        ? prev.filter((id) => id !== runId)
        : prev.length < 6
          ? [...prev, runId]
          : prev;
      return next;
    });
  };

  const reportQuery = useQuery({
    queryKey: ["backtest-report", selectedRunId],
    queryFn: () => fetchBacktestReport(selectedRunId!),
    enabled: Boolean(selectedRunId && !isCompareMode && viewMode === "split"),
  });

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-surface overflow-hidden">
      {/* Top Filter & View Mode Bar */}
      <div className="border-b border-line bg-surface-raised p-2.5">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-2.5">
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-bold text-ink">Strategy Runs Lab</h2>
            <span className="rounded bg-surface px-2 py-0.5 font-mono text-[10.5px] text-ink-muted border border-line">
              ClickHouse strategy_runs &amp; backtest_jobs
            </span>
          </div>

          <div className="flex items-center gap-2">
            {/* View Mode Toggle */}
            <div className="flex items-center rounded border border-line bg-surface p-0.5 text-[11px] font-medium">
              <button
                type="button"
                onClick={() => setViewMode("split")}
                className={`flex items-center gap-1.5 rounded px-2.5 py-1 transition-colors ${
                  viewMode === "split"
                    ? "bg-surface-raised font-bold text-accent shadow-xs"
                    : "text-ink-muted hover:text-ink"
                }`}
                title="Split view: sidebar list + active run inspector"
              >
                <span>⊞</span> Split Inspector
              </button>
              <button
                type="button"
                onClick={() => setViewMode("table")}
                className={`flex items-center gap-1.5 rounded px-2.5 py-1 transition-colors ${
                  viewMode === "table"
                    ? "bg-surface-raised font-bold text-accent shadow-xs"
                    : "text-ink-muted hover:text-ink"
                }`}
                title="Full-width strategy run screener table"
              >
                <span>☰</span> Screener Table
              </button>
            </div>

            {/* Compare Button */}
            {checkedRunIds.length >= 2 ? (
              <button
                type="button"
                onClick={() => {
                  setViewMode("split");
                  setIsCompareMode(true);
                }}
                className="rounded bg-accent px-3 py-1 text-[11px] font-semibold text-accent-ink shadow-sm hover:opacity-90 transition-opacity"
              >
                Compare ({checkedRunIds.length})
              </button>
            ) : null}

            {checkedRunIds.length > 0 ? (
              <button
                type="button"
                onClick={() => {
                  setCheckedRunIds([]);
                  setIsCompareMode(false);
                }}
                className="rounded border border-line bg-surface px-2 py-1 text-[11px] font-medium text-ink-muted hover:bg-surface-sunk hover:text-ink"
              >
                Clear ({checkedRunIds.length})
              </button>
            ) : null}
          </div>
        </div>

        {/* Universal Run Filter Bar */}
        <RunFilterBar
          filters={filters}
          onChange={setFilters}
          runs={runs}
          filteredCount={filteredRuns.length}
        />
      </div>

      {/* Main Body: Full Table Mode vs Split Inspector Mode */}
      {viewMode === "table" ? (
        <div className="flex-1 overflow-auto p-4 bg-surface">
          <RunScreenerTable
            runs={filteredRuns}
            selectedRunId={selectedRunId}
            onSelectRun={(rid) => {
              setSelectedRunId(rid);
              setViewMode("split");
              setIsCompareMode(false);
            }}
            checkedRunIds={checkedRunIds}
            onToggleCheck={handleToggleCheck}
            onPromoteRun={onPromoteRun}
            onEditInComposer={onEditInComposer}
            onViewLog={(jobId, irId, status) =>
              setLogModalJob({ jobId, irId, status })
            }
          />
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 bg-surface">
          {/* Left Filtered Runs Sidebar */}
          <aside className="flex w-80 shrink-0 flex-col border-r border-line bg-surface-raised">
            <JobsStrip
              onSelectRun={setSelectedRunId}
              selectedRunId={selectedRunId}
              onViewLog={(jobId, irId, status) =>
                setLogModalJob({ jobId, irId, status })
              }
            />
            <div className="min-h-0 flex-1 overflow-y-auto divide-y divide-line/60">
              {runsQuery.isLoading ? (
                <div className="px-3 py-6 text-[12px] text-ink-muted">Loading runs…</div>
              ) : runsQuery.isError ? (
                <div className="px-3 py-6 text-[12px] text-danger">
                  {(runsQuery.error as Error).message}
                </div>
              ) : filteredRuns.length === 0 ? (
                <div className="px-3 py-8 text-center">
                  <p className="text-[13px] font-medium text-ink">No matching runs</p>
                  <p className="mt-1 text-[11px] leading-relaxed text-ink-muted">
                    Adjust or reset filters in the top toolbar to reveal backtest runs.
                  </p>
                </div>
              ) : (
                filteredRuns.map((run) => (
                  <RunListItem
                    key={run.run_id}
                    run={run}
                    selected={run.run_id === selectedRunId && !isCompareMode}
                    checked={checkedRunIds.includes(run.run_id)}
                    onSelect={() => {
                      setSelectedRunId(run.run_id);
                      setIsCompareMode(false);
                    }}
                    onToggleCheck={() => handleToggleCheck(run.run_id)}
                    onViewLog={(jobId, irId, status) =>
                      setLogModalJob({ jobId, irId, status })
                    }
                  />
                ))
              )}
            </div>
          </aside>

          {/* Right Active Run Inspector / Compare Pane */}
          <main className="flex min-w-0 flex-1 flex-col bg-surface-raised overflow-y-auto">
            <ActiveBacktestBanner
              jobs={jobs}
              onViewLog={(jobId, irId, status) =>
                setLogModalJob({ jobId, irId, status })
              }
            />

            {isCompareMode && checkedRunIds.length >= 2 ? (
              <MultiRunCompareView
                runIds={checkedRunIds}
                onClose={() => setIsCompareMode(false)}
                onSelectRun={(rid) => {
                  setSelectedRunId(rid);
                  setIsCompareMode(false);
                }}
              />
            ) : !selectedRunId ? (
              <div className="flex flex-1 items-center justify-center p-8 text-[13px] text-ink-muted">
                {runsQuery.isLoading
                  ? "Loading…"
                  : filteredRuns.length === 0
                    ? "No runs match filters. Adjust filters above to inspect runs."
                    : "Select a run from the list."}
              </div>
            ) : runs.find((r) => r.run_id === selectedRunId)?.status === "failed" ? (
              <div className="flex flex-1 flex-col items-center justify-center p-8 text-center">
                <div className="max-w-lg rounded-lg border border-rose-500/30 bg-rose-500/10 p-6 shadow-sm">
                  <div className="flex items-center justify-center gap-2 text-rose-400">
                    <span className="text-xl">⚠️</span>
                    <h3 className="text-base font-bold">Backtest Job Failed</h3>
                  </div>
                  <p className="mt-2 text-xs text-ink-muted">
                    This run encountered an execution error and did not produce completed performance records in ClickHouse.
                  </p>
                  <div className="mt-4 rounded bg-surface p-3 text-left font-mono text-[11px] text-rose-300 border border-line">
                    <div className="font-semibold text-ink-faint">
                      Job ID: {selectedRunId}
                    </div>
                    <div className="mt-1">
                      Error: {runs.find((r) => r.run_id === selectedRunId)?.error_message || "Non-zero exit code"}
                    </div>
                    {runs.find((r) => r.run_id === selectedRunId)?.spec_title ? (
                      <div className="mt-1 text-ink-muted">
                        Spec: {runs.find((r) => r.run_id === selectedRunId)?.spec_title}
                      </div>
                    ) : null}
                  </div>
                  <div className="mt-4 flex justify-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        const r = runs.find((item) => item.run_id === selectedRunId);
                        setLogModalJob({
                          jobId: selectedRunId,
                          irId: r?.ir_id,
                          status: r?.status,
                        });
                      }}
                      className="rounded bg-rose-500 px-4 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-rose-600 transition-colors"
                    >
                      📜 Open Execution Log &amp; Stderr
                    </button>
                  </div>
                </div>
              </div>
            ) : runs.find((r) => r.run_id === selectedRunId)?.status === "running" ? (
              <div className="flex flex-1 flex-col items-center justify-center p-8 text-center">
                <div className="max-w-lg rounded-lg border border-sky-500/30 bg-sky-500/10 p-6 shadow-sm">
                  <div className="flex items-center justify-center gap-2 text-sky-400">
                    <span className="h-3 w-3 rounded-full bg-sky-400 animate-pulse" />
                    <h3 className="text-base font-bold">Backtest Running</h3>
                  </div>
                  <p className="mt-2 text-xs text-ink-muted">
                    The LEAN backtest engine is actively executing simulated trades.
                  </p>
                  <div className="mt-4 flex justify-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        const r = runs.find((item) => item.run_id === selectedRunId);
                        setLogModalJob({
                          jobId: selectedRunId,
                          irId: r?.ir_id,
                          status: r?.status,
                        });
                      }}
                      className="rounded bg-sky-500 px-4 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-sky-600 transition-colors"
                    >
                      📜 View Live Telemetry Stream
                    </button>
                  </div>
                </div>
              </div>
            ) : reportQuery.isLoading ? (
              <div className="flex flex-1 items-center justify-center text-[13px] text-ink-muted">
                Loading report…
              </div>
            ) : reportQuery.isError ? (
              <div className="flex flex-1 items-center justify-center p-8">
                <div className="max-w-md rounded border border-danger/30 bg-danger-soft px-4 py-3 text-[12px] text-danger">
                  {(reportQuery.error as Error).message}
                </div>
              </div>
            ) : reportQuery.data ? (
              <ReportPanel
                report={reportQuery.data}
                runSubTab={section}
                onRunSubTabChange={(s) => {
                  if (selectedRunId) navigate(backtestRunPath(selectedRunId, s));
                }}
                onPromote={
                  onPromoteRun && selectedRunId
                    ? () => onPromoteRun(selectedRunId)
                    : undefined
                }
                onEditInComposer={
                  onEditInComposer
                    ? () => {
                        const r = runs.find((item) => item.run_id === selectedRunId);
                        if (r) onEditInComposer(r);
                      }
                    : undefined
                }
              />
            ) : null}
          </main>
        </div>
      )}

      {logModalJob ? (
        <LiveLogDrawer
          jobId={logModalJob.jobId}
          irId={logModalJob.irId}
          status={logModalJob.status}
          onClose={() => setLogModalJob(null)}
        />
      ) : null}
    </div>
  );
}

export function BacktestView({
  activeTab,
  onTabChange,
  savedScreens,
  savedScreenId,
  liveSpec,
  backtestPrefill,
  presets = [],
  routeStrategyIrId = null,
}: {
  activeTab: WorkbenchTab;
  onTabChange: (tab: WorkbenchTab) => void;
  savedScreens: SavedScreen[];
  savedScreenId: number | string | null;
  liveSpec: UniverseQueryV1 | null;
  backtestPrefill?: BacktestPrefill | null;
  presets?: ScreenPreset[];
  /** From `/strategies/:irId` — null when untitled draft. */
  routeStrategyIrId?: string | null;
}) {
  const navigate = useNavigate();
  const [paperRunId, setPaperRunId] = useState<string | null>(null);
  const [loadedComposeSpec, setLoadedComposeSpec] = useState<BacktestSpecSummary | null>(null);

  const handlePromoteRun = useCallback((runId: string) => {
    setPaperRunId(runId);
    onTabChange("deploy");
  }, [onTabChange]);

  const handleJumpToRun = useCallback((runId: string) => {
    navigate(backtestRunPath(runId));
  }, [navigate]);

  const navigateToStrategy = useCallback(
    (irId: string | null) => {
      navigate(strategyPath(irId));
    },
    [navigate],
  );

  const handleEditInComposer = useCallback((run: BacktestRunSummary) => {
    const id = run.ir_id || run.run_id;
    setLoadedComposeSpec({
      ir_id: id,
      title: run.spec_title || `Strategy (${run.run_id.slice(0, 8)})`,
      alpha_type: run.alpha_type,
      universe_type: run.universe_type,
      risk_type: run.risk_type,
      portfolio_type: run.portfolio_type,
      execution_type: run.execution_type,
      symbols: run.symbols,
      is_template: false,
    });
    navigate(strategyPath(id));
  }, [navigate]);

  const handleEditOptimizedInComposer = useCallback((irId: string, runPoint: any) => {
    setLoadedComposeSpec({
      ir_id: irId,
      title: `Optimized Variant (${runPoint.run_id.slice(0, 8)})`,
      notes: `Optimal variant from sweep. Sharpe: ${runPoint.sharpe_ratio?.toFixed(2)}, Return: ${((runPoint.total_return || 0) * 100).toFixed(1)}%`,
      algorithm_json: null,
      is_template: false,
    });
    navigate(strategyPath(irId));
  }, [navigate]);

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-surface">
      {activeTab === "compose" ? (
        <BacktestComposePanel
          savedScreens={savedScreens}
          savedScreenId={savedScreenId}
          liveSpec={liveSpec}
          backtestPrefill={backtestPrefill}
          presets={presets}
          initialSpec={loadedComposeSpec}
          routeStrategyIrId={routeStrategyIrId}
          onNavigateStrategy={navigateToStrategy}
          onNavigateToRuns={() => onTabChange("runs")}
          onNavigateToOptimize={() => onTabChange("optimize")}
        />
      ) : activeTab === "runs" ? (
        <RunsTab
          onPromoteRun={handlePromoteRun}
          onEditInComposer={handleEditInComposer}
        />
      ) : activeTab === "optimize" ? (
        <div className="flex-1 overflow-y-auto p-2.5 sm:p-4">
          <OptimizerView
            onJumpToRun={handleJumpToRun}
            onPromoteRun={handlePromoteRun}
            onEditInComposer={handleEditOptimizedInComposer}
          />
        </div>
      ) : activeTab === "deploy" ? (
        <PromotePanel initialRunId={paperRunId} />
      ) : null}
    </div>
  );
}
