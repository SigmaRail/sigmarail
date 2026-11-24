import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useGenerateLocalePath } from "@sb/webapp-core/hooks";
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
import { BacktestRunSetupDialog } from "./BacktestRunSetupDialog";
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
import { UniversalCandidateExplorer, type CandidateItem } from "./workbench/UniversalCandidateExplorer";
import { BenchmarkComparisonPanel } from "./workbench/BenchmarkComparisonPanel";
import { DayZeroShiftedTimelinePanel } from "./workbench/DayZeroShiftedTimelinePanel";
import { RecommendationsPanel } from "./RecommendationsPanel";
import { UnderwaterDrawdownPanel } from "./workbench/UnderwaterDrawdownPanel";
import { AssetAllocationTreemap } from "./workbench/AssetAllocationTreemap";
import { PortfolioExposurePanel } from "./workbench/PortfolioExposurePanel";
import { RollingStatsMatrix } from "./workbench/RollingStatsMatrix";
import { CopyIdBadge } from "./CopyIdBadge";
import { RunFilterBar, type RunFilters, INITIAL_RUN_FILTERS } from "./RunFilterBar";
import { RunScreenerTable } from "./RunScreenerTable";
import { PageHeadline } from "@sb/webapp-core/components/pageHeadline";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Card } from "@sb/webapp-core/components/ui/card";
import { Badge } from "@sb/webapp-core/components/ui/badge";
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from "@sb/webapp-core/components/ui/alert";
import { Checkbox } from "@sb/webapp-core/components/forms/checkbox";
import { Tabs, TabsList, TabsTrigger } from "@sb/webapp-core/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@sb/webapp-core/components/ui/select";
import { Slider } from "@sb/webapp-core/components/ui/slider";
import {
  Table as WorkspaceTable,
  TableBody as WorkspaceTableBody,
  TableCell as WorkspaceTableCell,
  TableHead as WorkspaceTableHead,
  TableHeader as WorkspaceTableHeader,
  TableRow as WorkspaceTableRow,
} from "@sb/webapp-core/components/ui/table";

function truncateId(id: string, head = 8, tail = 6): string {
  if (id.length <= head + tail + 1) return id;
  return `${id.slice(0, head)}…${id.slice(-tail)}`;
}

function localePath(generateLocalePath: (path: string) => string, path: string) {
  return generateLocalePath(path.replace(/^\/+/, ""));
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
        <Checkbox
          checked={checked}
          disabled={!isDone}
          onCheckedChange={() => onToggleCheck?.()}
          title="Select for comparison"
          aria-label="Select for comparison"
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
          <Button
              type="button"
            variant="ghost"
            size="icon"
              onClick={(e) => {
                e.stopPropagation();
                onViewLog(run.run_id, run.ir_id, run.status);
              }}
            className="h-7 w-7"
              title="View error log"
            aria-label="View error log"
            >
            Log
          </Button>
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

  const selectOrder = (
    row: Record<string, unknown>,
    idx: number,
    timeStr: string,
    dir: string,
    sym: string,
  ) => {
    if (!sym || sym === "—") return;
    const allTrades = [
      ...(closedTradesQuery.data?.trades ?? []),
      ...(closedTradesQuery.data?.open_trades ?? []),
    ];
    const match = allTrades.find(
      (trade) => trade.symbol.toUpperCase() === sym.toUpperCase(),
    );
    if (match) {
      handleSelectTrade(match);
      return;
    }
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
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col p-4">
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
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={onEditInComposer}
              >
                <span>✏️</span>
                <span>Open in Composer</span>
              </Button>
            )}
            {onPromote && report.ir_id ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={onPromote}
              >
                Promote to paper
              </Button>
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

      {/* Section navigation stays compact on phones and keeps full labels on desktop. */}
      <div className="mb-4 min-w-0 pb-1">
        <div className="md:hidden">
          <Select value={runSubTab} onValueChange={(value) => onRunSubTabChange(value as BacktestSection)}>
            <SelectTrigger aria-label="Report section" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="overview">Overview</SelectItem>
              <SelectItem value="trades">Trades &amp; Excursions</SelectItem>
              <SelectItem value="attribution">Attribution &amp; Macro</SelectItem>
              <SelectItem value="scrubber">Day Scrubber</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="hidden md:block">
        <Tabs value={runSubTab} onValueChange={(value) => onRunSubTabChange(value as BacktestSection)}>
          <TabsList className="h-10 w-full justify-start rounded-none border-b bg-transparent p-0">
            <TabsTrigger value="overview" className="h-9 rounded-none px-3 text-xs">Overview</TabsTrigger>
            <TabsTrigger value="trades" className="h-9 rounded-none px-3 text-xs">
              Trades & Excursions{closedTradesQuery.data?.total ? ` (${closedTradesQuery.data.total})` : ""}
            </TabsTrigger>
            <TabsTrigger value="attribution" className="h-9 rounded-none px-3 text-xs">Attribution & Macro</TabsTrigger>
            <TabsTrigger value="scrubber" className="h-9 rounded-none px-3 text-xs">
              Day Scrubber{snapshots.length > 0 ? ` (${snapshots.length}d)` : ""}
            </TabsTrigger>
          </TabsList>
        </Tabs>
        </div>
      </div>

      {zeroOrders ? (
        <Card className="mb-4 space-y-1 border-amber-500/30 bg-amber-50/50 px-3 py-2.5 shadow-none dark:bg-amber-950/20">
          <Badge variant="warning" className="w-fit">No orders recorded</Badge>
          <p className="mt-1 text-[11px] text-warn/90">
            Check that the market data service is available and the universe returned rows for the backtest window.
          </p>
        </Card>
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

          {/* Execution Orders */}
          {ordersQuery.data && ordersQuery.data.count > 0 ? (
            <section className="mb-4">
              <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
                Execution Orders Log ({ordersQuery.data.total})
              </h3>
              <div className="mt-2 md:hidden max-h-56 space-y-2 overflow-auto rounded border border-line bg-surface p-2">
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
                    <Card key={String(row.id ?? idx)} className="space-y-2 p-3 shadow-none">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="font-mono text-sm font-semibold text-ink">{sym}</div>
                          <div className="text-xs text-muted-foreground">{timeStr}</div>
                        </div>
                        <Badge variant={dir === "buy" ? "success" : dir === "sell" ? "destructive" : "muted"} className="shrink-0 uppercase">
                          {dir}
                        </Badge>
                      </div>
                      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                        <span className="text-muted-foreground">Quantity</span><span className="text-right tabular-nums">{qty}</span>
                        <span className="text-muted-foreground">Fill price</span><span className="text-right tabular-nums">{fillPx}</span>
                        <span className="text-muted-foreground">Status</span><span className="text-right">{String(row.status ?? row.Status ?? "—")}</span>
                      </div>
                      <Button type="button" variant="outline" size="sm" onClick={() => selectOrder(row, idx, timeStr, dir, sym)}>
                        View chart
                      </Button>
                    </Card>
                  );
                })}
              </div>
              <div className="mt-2 hidden max-h-56 overflow-auto rounded border border-line bg-surface md:block">
                <WorkspaceTable className="w-full text-left text-[11px]">
                  <WorkspaceTableHeader className="sticky top-0 bg-surface-sunk text-ink-faint">
                    <WorkspaceTableRow>
                      <WorkspaceTableHead className="px-2 py-1">Time</WorkspaceTableHead>
                      <WorkspaceTableHead className="px-2 py-1">Symbol</WorkspaceTableHead>
                      <WorkspaceTableHead className="px-2 py-1">Direction</WorkspaceTableHead>
                      <WorkspaceTableHead className="px-2 py-1">Quantity</WorkspaceTableHead>
                      <WorkspaceTableHead className="px-2 py-1">Fill Price</WorkspaceTableHead>
                      <WorkspaceTableHead className="px-2 py-1">Status</WorkspaceTableHead>
                    </WorkspaceTableRow>
                  </WorkspaceTableHeader>
                  <WorkspaceTableBody>
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
                        <WorkspaceTableRow
                          key={idx}
                          onClick={() => selectOrder(row, idx, timeStr, dir, sym)}
                          className="border-t border-line hover:bg-surface-sunk/60 cursor-pointer transition-colors"
                          title={`Click to view ${sym} candlestick chart & campaign`}
                        >
                          <WorkspaceTableCell className="px-2 py-1 font-mono text-[10px] text-ink-muted">{timeStr}</WorkspaceTableCell>
                          <WorkspaceTableCell className="px-2 py-1 font-mono font-medium text-ink">
                            {sym}
                          </WorkspaceTableCell>
                          <WorkspaceTableCell className="px-2 py-1">
                            <span className={`inline-block font-semibold ${dir === "buy" ? "text-emerald-500" : dir === "sell" ? "text-rose-500" : "text-ink"}`}>
                              {dir.toUpperCase()}
                            </span>
                          </WorkspaceTableCell>
                          <WorkspaceTableCell className="px-2 py-1 tabular-nums text-ink">{qty}</WorkspaceTableCell>
                          <WorkspaceTableCell className="px-2 py-1 tabular-nums text-ink">{fillPx}</WorkspaceTableCell>
                          <WorkspaceTableCell className="px-2 py-1 text-ink-muted">{String(row.status ?? row.Status ?? "—")}</WorkspaceTableCell>
                        </WorkspaceTableRow>
                      );
                    })}
                  </WorkspaceTableBody>
                </WorkspaceTable>
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
            <Card className="space-y-3.5 p-3.5 shadow-none">
              <div className="flex items-center justify-between">
                <h3 className="text-[12px] font-bold text-ink">
                  Point-in-Time Day Scrubber
                </h3>
                <span className="font-mono text-[11px] text-accent font-semibold">
                  Snapshot {snapshotIndex + 1} of {snapshots.length}
                </span>
              </div>
              <Slider
                min={0}
                max={Math.max(0, snapshots.length - 1)}
                step={1}
                value={[Math.min(snapshotIndex, snapshots.length - 1)]}
                onValueChange={([index]) => setSnapshotIndex(index ?? 0)}
                aria-label="Select historical snapshot"
                className="mt-3"
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
            </Card>

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
                  <Button
                    type="button"
                    className="flex h-auto w-full items-baseline justify-between gap-2 rounded-none px-2.5 py-1.5 text-left font-mono text-[11px]"
                    variant="ghost"
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
                  </Button>
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
          decisionEvents={snapshotsQuery.data?.decision_events ?? []}
          strategyHash={report.provenance?.ir_content_hash}
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
  const visibleJobs = jobs.slice(0, 5);

  if (jobsQuery.isLoading && jobs.length === 0) {
    return (
      <div className="border-b border-line px-3 py-2 text-[11px] text-ink-muted">
        Loading jobs…
      </div>
    );
  }
  if (jobsQuery.isError) {
    return (
      <div className="border-b border-line p-2">
        <Alert variant="destructive" className="p-2">
          <AlertTitle className="text-[11px]">Job status is unavailable</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center justify-between gap-2 text-[10px]">
            <span>{(jobsQuery.error as Error).message}</span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7"
              onClick={() => void jobsQuery.refetch()}
              disabled={jobsQuery.isFetching}
            >
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      </div>
    );
  }
  if (visibleJobs.length === 0) return null;

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
        {visibleJobs.map((j) => {
          const isRunning = j.status === "running";
          const pct = Math.min(100, Math.max(0, Math.round((j.progress_pct ?? 0) * 100)));
          const isSelected = j.job_id === selectedRunId;
          const summary = j.result_summary ?? {};
          const metrics: string[] = [];
          if (typeof summary.total_return === "number") {
            metrics.push(`Return ${(summary.total_return * 100).toFixed(1)}%`);
          }
          if (typeof summary.sharpe_ratio === "number") {
            metrics.push(`Sharpe ${summary.sharpe_ratio.toFixed(2)}`);
          }
          if (typeof summary.max_drawdown === "number") {
            metrics.push(`Drawdown ${(summary.max_drawdown * 100).toFixed(1)}%`);
          }
          if (metrics.length === 0 && typeof summary.total_orders === "number") {
            metrics.push(`${summary.total_orders} orders`);
          }
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
                    <Button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onViewLog(j.job_id, j.ir_id, j.status);
                      }}
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      title="View live log"
                      aria-label="View live log"
                    >
                      Log
                    </Button>
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
              {metrics.length > 0 ? (
                <div className="mt-1 truncate text-[9px] text-ink-muted" title={metrics.join(" · ")}>
                  {metrics.join(" · ")}
                </div>
              ) : null}
              {j.status === "failed" && j.error_message ? (
                <div className="mt-1 truncate text-[9px] text-danger" title={j.error_message}>
                  {j.error_message}
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
  compareRunIds = [],
}: {
  onPromoteRun?: (runId: string) => void;
  onEditInComposer?: (run: BacktestRunSummary) => void;
  compareRunIds?: string[];
}) {
  const location = useLocation();
  const navigate = useNavigate();
  const generateLocalePath = useGenerateLocalePath();
  const { runId: selectedRunId, section } = backtestRunFromPath(location.pathname);

  const setSelectedRunId = useCallback(
    (id: string | null) => {
      navigate(localePath(generateLocalePath, id ? backtestRunPath(id) : "/backtests"));
    },
    [navigate, generateLocalePath],
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

  const [checkedRunIds, setCheckedRunIds] = useState<string[]>(
    compareRunIds.length >= 2 ? compareRunIds : initialCompareRunIds,
  );
  const [isCompareMode, setIsCompareMode] = useState<boolean>(
    compareRunIds.length >= 2 || initialCompareRunIds.length >= 2 || new URLSearchParams(window.location.search).get("view") === "compare",
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
  const [newBacktestOpen, setNewBacktestOpen] = useState(false);

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
      navigate(localePath(generateLocalePath, backtestRunPath(filteredRuns[0].run_id)), { replace: true });
    }
  }, [selectedRunId, isCompareMode, filteredRuns, navigate, generateLocalePath]);

  // Canonicalize /backtests/:runId (no section) -> /overview.
  useEffect(() => {
    if (!selectedRunId) return;
    if (location.pathname.endsWith(`/${selectedRunId}`)) {
      navigate(localePath(generateLocalePath, backtestRunPath(selectedRunId, "overview")), { replace: true });
    }
  }, [selectedRunId, location.pathname, navigate, generateLocalePath]);

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
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-background">
      <header className="space-y-3 border-b bg-background p-3 sm:p-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <PageHeadline
            header="Backtest runs"
            subheader="Review results, compare runs, and continue a strategy into deployment."
            className="space-y-1"
          />

          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" size="sm" onClick={() => setNewBacktestOpen(true)}>
              New backtest
            </Button>
            <div className="flex items-center gap-1" role="group" aria-label="Run layout">
              <Button
                type="button"
                onClick={() => setViewMode("split")}
                variant={viewMode === "split" ? "secondary" : "outline"}
                size="sm"
                title="Split view: sidebar list + active run inspector"
              >
                Run details
              </Button>
              <Button
                type="button"
                onClick={() => setViewMode("table")}
                variant={viewMode === "table" ? "secondary" : "outline"}
                size="sm"
                title="Full-width strategy run screener table"
              >
                Table
              </Button>
            </div>

            {checkedRunIds.length >= 2 ? (
              <Button
                type="button"
                onClick={() => {
                  setViewMode("split");
                  setIsCompareMode(true);
                }}
                size="sm"
              >
                Compare ({checkedRunIds.length})
              </Button>
            ) : null}

            {checkedRunIds.length > 0 ? (
              <Button
                type="button"
                onClick={() => {
                  setCheckedRunIds([]);
                  setIsCompareMode(false);
                }}
                variant="ghost"
                size="sm"
              >
                Clear ({checkedRunIds.length})
              </Button>
            ) : null}
          </div>
        </div>

        <RunFilterBar filters={filters} onChange={setFilters} runs={runs} filteredCount={filteredRuns.length} />
      </header>

      {/* Main Body: Full Table Mode vs Split Inspector Mode */}
      {viewMode === "table" ? (
        <div className="min-h-0 flex-1 overflow-auto p-3 sm:p-4">
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
        <div className="flex min-h-0 flex-1 flex-col bg-background lg:flex-row">
          {/* Left Filtered Runs Sidebar */}
          <aside className="flex h-36 w-full shrink-0 flex-col border-b bg-background lg:h-auto lg:w-80 lg:border-b-0 lg:border-r">
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
                <div className="p-2">
                  <Alert variant="destructive" className="p-2">
                    <AlertTitle className="text-[11px]">Backtest runs are unavailable</AlertTitle>
                    <AlertDescription className="flex flex-wrap items-center justify-between gap-2 text-[10px]">
                      <span>{(runsQuery.error as Error).message}</span>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7"
                        onClick={() => void runsQuery.refetch()}
                        disabled={runsQuery.isFetching}
                      >
                        Retry
                      </Button>
                    </AlertDescription>
                  </Alert>
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
          <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto bg-surface-raised">
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
            ) : runsQuery.isError ? (
              <div className="flex flex-1 items-center justify-center p-8 text-center text-sm text-destructive" role="alert">
                Run details are unavailable until the run list loads successfully.
              </div>
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
                <Card className="max-w-lg space-y-3 p-6 text-left shadow-none">
                  <div className="flex items-center justify-center gap-2">
                    <Badge variant="destructive">Failed</Badge>
                    <h3 className="text-base font-semibold text-foreground">Backtest run</h3>
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
                    <Button
                      type="button"
                      onClick={() => {
                        const r = runs.find((item) => item.run_id === selectedRunId);
                        setLogModalJob({
                          jobId: selectedRunId,
                          irId: r?.ir_id,
                          status: r?.status,
                        });
                      }}
                      variant="outline"
                      size="sm"
                    >
                      View execution log
                    </Button>
                  </div>
                </Card>
              </div>
            ) : runs.find((r) => r.run_id === selectedRunId)?.status === "running" ? (
              <div className="flex flex-1 flex-col items-center justify-center p-8 text-center">
                <Card className="max-w-lg space-y-3 p-6 text-left shadow-none">
                  <div className="flex items-center justify-center gap-2">
                    <Badge variant="info">Running</Badge>
                    <h3 className="text-base font-semibold text-foreground">Backtest run</h3>
                  </div>
                  <p className="mt-2 text-xs text-ink-muted">
                    The execution engine is processing this simulation.
                  </p>
                  <div className="mt-4 flex justify-center gap-2">
                    <Button
                      type="button"
                      onClick={() => {
                        const r = runs.find((item) => item.run_id === selectedRunId);
                        setLogModalJob({
                          jobId: selectedRunId,
                          irId: r?.ir_id,
                          status: r?.status,
                        });
                      }}
                      variant="outline"
                      size="sm"
                    >
                      View run logs
                    </Button>
                  </div>
                </Card>
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
                  if (selectedRunId) navigate(localePath(generateLocalePath, backtestRunPath(selectedRunId, s)));
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
      <BacktestRunSetupDialog
        open={newBacktestOpen}
        onOpenChange={setNewBacktestOpen}
        initialIrId={filters.irId === "all" ? undefined : filters.irId}
        onQueued={(irId) => setFilters((current) => ({ ...current, irId }))}
      />
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
  const generateLocalePath = useGenerateLocalePath();
  const [paperRunId, setPaperRunId] = useState<string | null>(null);
  const [optimizerCompareRunIds, setOptimizerCompareRunIds] = useState<string[]>([]);
  const [loadedComposeSpec, setLoadedComposeSpec] = useState<BacktestSpecSummary | null>(null);

  const handlePromoteRun = useCallback((runId: string) => {
    setPaperRunId(runId);
    onTabChange("deploy");
  }, [onTabChange]);

  const handleJumpToRun = useCallback((runId: string) => {
    navigate(localePath(generateLocalePath, backtestRunPath(runId)));
  }, [navigate, generateLocalePath]);

  const handleCompareRuns = useCallback((runIds: string[]) => {
    setOptimizerCompareRunIds(runIds);
    onTabChange("runs");
  }, [onTabChange]);

  const navigateToStrategy = useCallback(
    (irId: string | null) => {
      navigate(localePath(generateLocalePath, strategyPath(irId)));
    },
    [navigate, generateLocalePath],
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
    navigate(localePath(generateLocalePath, strategyPath(id)));
  }, [navigate, generateLocalePath]);

  const handleEditOptimizedInComposer = useCallback((irId: string, runPoint: any) => {
    setLoadedComposeSpec({
      ir_id: irId,
      title: `Optimized Variant (${runPoint.run_id.slice(0, 8)})`,
      notes: `Optimal variant from sweep. Sharpe: ${runPoint.sharpe_ratio?.toFixed(2)}, Return: ${((runPoint.total_return || 0) * 100).toFixed(1)}%`,
      algorithm_json: null,
      is_template: false,
    });
    navigate(localePath(generateLocalePath, strategyPath(irId)));
  }, [navigate, generateLocalePath]);

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
        />
      ) : activeTab === "runs" ? (
        <RunsTab
          onPromoteRun={handlePromoteRun}
          onEditInComposer={handleEditInComposer}
          compareRunIds={optimizerCompareRunIds}
        />
      ) : activeTab === "optimize" ? (
        <div className="flex-1 overflow-y-auto p-2.5 sm:p-4">
          <OptimizerView
            onJumpToRun={handleJumpToRun}
            onPromoteRun={handlePromoteRun}
            onEditInComposer={handleEditOptimizedInComposer}
            onCompareRuns={handleCompareRuns}
          />
        </div>
      ) : activeTab === "deploy" ? (
        <PromotePanel initialRunId={paperRunId} />
      ) : null}
    </div>
  );
}
