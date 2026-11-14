import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchRunBenchmarkComparison } from "../../api/backtests";

export interface BenchmarkOption {
  symbol: string;
  name: string;
  category: "Broad Market" | "Leveraged Index" | "CAN SLIM & Breakouts" | "Momentum & Trend" | "Custom";
  description: string;
}

export const BENCHMARK_OPTIONS: BenchmarkOption[] = [
  // Broad Market
  { symbol: "SPY", name: "S&P 500", category: "Broad Market", description: "SPDR S&P 500 ETF Trust" },
  { symbol: "QQQ", name: "Nasdaq 100", category: "Broad Market", description: "Invesco QQQ Trust (Tech / Growth)" },
  { symbol: "IWM", name: "Russell 2000", category: "Broad Market", description: "iShares Russell 2000 ETF (Small-Cap)" },

  // Leveraged Index
  { symbol: "TQQQ", name: "3x QQQ", category: "Leveraged Index", description: "ProShares UltraPro QQQ (3x Daily Leveraged Nasdaq 100)" },
  { symbol: "QLD", name: "2x QQQ", category: "Leveraged Index", description: "ProShares Ultra QQQ (2x Daily Leveraged Nasdaq 100)" },
  { symbol: "UPRO", name: "3x SPY", category: "Leveraged Index", description: "ProShares UltraPro S&P 500 (3x Daily Leveraged S&P 500)" },
  { symbol: "SSO", name: "2x SPY", category: "Leveraged Index", description: "ProShares Ultra S&P 500 (2x Daily Leveraged S&P 500)" },

  // CAN SLIM & Breakouts
  { symbol: "FFTY", name: "IBD 50", category: "CAN SLIM & Breakouts", description: "CapForce IBD 50 ETF (CAN SLIM Fundamental & Technical Leaders)" },
  { symbol: "BOUT", name: "IBD Breakout", category: "CAN SLIM & Breakouts", description: "CapForce IBD Breakout Opportunities (Cup-with-Handle & Base Breakouts)" },

  // Momentum & Trend
  { symbol: "QMOM", name: "Quant Momentum", category: "Momentum & Trend", description: "Alpha Architect US Quant Momentum (200d Trend Filter + Smooth Momentum)" },
  { symbol: "PDP", name: "DWA Momentum", category: "Momentum & Trend", description: "Invesco DWA Momentum (Point & Figure Relative Strength)" },
  { symbol: "SPMO", name: "S&P Momentum", category: "Momentum & Trend", description: "Invesco S&P 500 Momentum Factor (Top RS Deciles)" },
  { symbol: "PTLC", name: "Trendpilot 200d", category: "Momentum & Trend", description: "Pacer Trendpilot US Large Cap (200d SMA Macro Equity/Cash Switching)" },
];

export function BenchmarkComparisonPanel({ runId }: { runId: string }) {
  const [benchmark, setBenchmark] = useState<string>("SPY");
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [customInput, setCustomInput] = useState<string>("");
  const [customTickers, setCustomTickers] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem("vera_custom_benchmarks");
      return saved ? JSON.parse(saved) : ["SMH", "NVDA"];
    } catch {
      return ["SMH", "NVDA"];
    }
  });

  const handleApplyCustom = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const sym = customInput.trim().toUpperCase();
    if (!sym) return;
    setBenchmark(sym);
    if (!BENCHMARK_OPTIONS.some((o) => o.symbol === sym) && !customTickers.includes(sym)) {
      const next = [sym, ...customTickers.filter((t) => t !== sym).slice(0, 5)];
      setCustomTickers(next);
      try {
        localStorage.setItem("vera_custom_benchmarks", JSON.stringify(next));
      } catch {}
    }
    setCustomInput("");
  };

  const handleRemoveCustom = (sym: string) => {
    const next = customTickers.filter((t) => t !== sym);
    setCustomTickers(next);
    try {
      localStorage.setItem("vera_custom_benchmarks", JSON.stringify(next));
    } catch {}
    if (benchmark === sym) {
      setBenchmark("SPY");
    }
  };

  const currentOption = useMemo(() => {
    const found = BENCHMARK_OPTIONS.find((o) => o.symbol === benchmark);
    if (found) return found;
    return {
      symbol: benchmark,
      name: "Custom Ticker",
      category: "Custom" as const,
      description: `Custom benchmark ticker: ${benchmark}`,
    };
  }, [benchmark]);

  const query = useQuery({
    queryKey: ["benchmark-comparison", runId, benchmark],
    queryFn: () => fetchRunBenchmarkComparison(runId, benchmark),
    enabled: Boolean(runId),
  });

  const series = query.data?.series ?? [];
  const metrics = query.data?.metrics;

  const chartData = useMemo(() => {
    if (series.length === 0) return null;

    let minVal = Infinity;
    let maxVal = -Infinity;

    for (const p of series) {
      if (p.strategy_normalized < minVal) minVal = p.strategy_normalized;
      if (p.strategy_normalized > maxVal) maxVal = p.strategy_normalized;
      if (p.benchmark_normalized < minVal) minVal = p.benchmark_normalized;
      if (p.benchmark_normalized > maxVal) maxVal = p.benchmark_normalized;
    }

    const padding = (maxVal - minVal) * 0.1 || 2.0;
    minVal = Math.floor(minVal - padding);
    maxVal = Math.ceil(maxVal + padding);

    const width = 800;
    const height = 220;
    const pad = { top: 20, right: 55, bottom: 25, left: 15 };
    const chartW = width - pad.left - pad.right;
    const chartH = height - pad.top - pad.bottom;

    const scaleX = (idx: number) => pad.left + (idx / (series.length - 1 || 1)) * chartW;
    const scaleY = (val: number) => pad.top + chartH - ((val - minVal) / (maxVal - minVal || 1)) * chartH;

    const stratPoints = series.map((p, i) => `${scaleX(i)},${scaleY(p.strategy_normalized)}`).join(" ");
    const benchPoints = series.map((p, i) => `${scaleX(i)},${scaleY(p.benchmark_normalized)}`).join(" ");

    const stratArea = `${scaleX(0)},${pad.top + chartH} ` + stratPoints + ` ${scaleX(series.length - 1)},${pad.top + chartH}`;

    return {
      width,
      height,
      minVal,
      maxVal,
      pad,
      chartW,
      chartH,
      scaleX,
      scaleY,
      stratPoints,
      benchPoints,
      stratArea,
    };
  }, [series]);

  const activeIdx = hoverIndex !== null ? hoverIndex : (series.length > 0 ? series.length - 1 : null);
  const activePt = activeIdx !== null ? series[activeIdx] : null;

  return (
    <div className="flex flex-col rounded-lg border border-line bg-surface shadow-sm overflow-hidden">
      {/* Header Bar */}
      <div className="flex flex-col gap-2.5 border-b border-line bg-surface-raised px-4 py-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[13px] font-bold text-ink">
              Benchmark Comparison &amp; Active Risk
            </span>
            <span className="rounded bg-surface-sunk px-2 py-0.5 font-mono text-[10px] text-ink-muted">
              Base $100.0
            </span>
            <span className="rounded bg-accent/10 border border-accent/25 px-2 py-0.5 text-[10px] font-medium text-accent">
              Comparing vs <strong className="font-bold">{currentOption.symbol}</strong> ({currentOption.name}) — {currentOption.description}
            </span>
          </div>

          {/* Custom Ticker Search Input Form */}
          <form onSubmit={handleApplyCustom} className="flex items-center gap-1.5">
            <div className="relative flex items-center">
              <span className="absolute left-2 text-[10.5px] text-ink-faint pointer-events-none">🎯</span>
              <input
                type="text"
                value={customInput}
                onChange={(e) => setCustomInput(e.target.value.toUpperCase())}
                placeholder="Ticker (e.g. SMH, NVDA)..."
                className="w-40 rounded border border-line bg-surface py-0.5 pl-6 pr-2 text-[11px] font-mono text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none"
              />
            </div>
            <button
              type="submit"
              disabled={!customInput.trim()}
              className="rounded bg-accent px-2.5 py-0.5 text-[10.5px] font-semibold text-accent-ink hover:opacity-90 disabled:opacity-40 transition-opacity"
            >
              Compare
            </button>
          </form>
        </div>

        {/* Grouped Benchmark Selector Tabs */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[11px]">
          {(["Broad Market", "Leveraged Index", "CAN SLIM & Breakouts", "Momentum & Trend"] as const).map((cat) => {
            const items = BENCHMARK_OPTIONS.filter((o) => o.category === cat);
            return (
              <div key={cat} className="flex items-center gap-1 rounded bg-surface p-0.5 border border-line">
                <span className="px-1.5 text-[9px] font-bold uppercase tracking-wider text-ink-faint">
                  {cat === "Broad Market"
                    ? "Index"
                    : cat === "Leveraged Index"
                      ? "Leveraged"
                      : cat === "CAN SLIM & Breakouts"
                        ? "CAN SLIM"
                        : "Momentum"}
                </span>
                {items.map((opt) => (
                  <button
                    key={opt.symbol}
                    type="button"
                    onClick={() => setBenchmark(opt.symbol)}
                    title={`${opt.symbol} (${opt.name}): ${opt.description}`}
                    className={`rounded px-2 py-0.5 text-[10.5px] font-semibold transition-colors flex items-center gap-1 ${
                      benchmark === opt.symbol
                        ? "bg-accent text-accent-ink shadow-xs"
                        : "text-ink-muted hover:bg-surface-sunk hover:text-ink"
                    }`}
                  >
                    <span>{opt.symbol}</span>
                    <span className="text-[9px] opacity-75 font-normal">({opt.name})</span>
                  </button>
                ))}
              </div>
            );
          })}

          {/* User Custom Picked Tickers */}
          {customTickers.length > 0 ? (
            <div className="flex items-center gap-1 rounded bg-surface p-0.5 border border-line">
              <span className="px-1.5 text-[9px] font-bold uppercase tracking-wider text-ink-faint">
                Custom
              </span>
              {customTickers.map((sym) => (
                <div
                  key={sym}
                  className={`flex items-center rounded px-1.5 py-0.5 text-[10.5px] font-semibold transition-colors gap-1 ${
                    benchmark === sym
                      ? "bg-accent text-accent-ink shadow-xs"
                      : "text-ink-muted hover:bg-surface-sunk hover:text-ink"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => setBenchmark(sym)}
                    className="font-mono"
                    title={`Compare vs ${sym}`}
                  >
                    {sym}
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRemoveCustom(sym);
                    }}
                    className="text-[9px] opacity-60 hover:opacity-100 hover:text-rose-400"
                    title={`Remove ${sym} from list`}
                  >
                    ✕
                  </button>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </div>

      {/* Metrics Scorecard */}
      {metrics ? (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2 border-b border-line bg-surface-sunk/40 p-3">
          <div className="rounded border border-line/60 bg-surface px-2.5 py-1.5">
            <div className="text-[10px] text-ink-muted font-medium">Strategy Return</div>
            <div className={`font-mono text-[13px] font-bold ${metrics.strategy_total_return >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {metrics.strategy_total_return >= 0 ? "+" : ""}
              {(metrics.strategy_total_return * 100).toFixed(2)}%
            </div>
          </div>

          <div className="rounded border border-line/60 bg-surface px-2.5 py-1.5">
            <div className="text-[10px] text-ink-muted font-medium truncate" title={`${currentOption.symbol} (${currentOption.name})`}>
              {currentOption.symbol} ({currentOption.name})
            </div>
            <div className={`font-mono text-[13px] font-bold ${metrics.benchmark_total_return >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {metrics.benchmark_total_return >= 0 ? "+" : ""}
              {(metrics.benchmark_total_return * 100).toFixed(2)}%
            </div>
          </div>

          <div className="rounded border border-line/60 bg-surface px-2.5 py-1.5">
            <div className="text-[10px] text-ink-muted font-medium">Beta (β) / Corr</div>
            <div className="font-mono text-[13px] font-bold text-ink">
              {metrics.beta.toFixed(2)} <span className="text-[10px] text-ink-faint">({metrics.correlation.toFixed(2)})</span>
            </div>
          </div>

          <div className="rounded border border-line/60 bg-surface px-2.5 py-1.5">
            <div className="text-[10px] text-ink-muted font-medium">Up-Market Capture</div>
            <div className="font-mono text-[13px] font-bold text-emerald-400">
              {metrics.up_market_capture.toFixed(1)}%
            </div>
          </div>

          <div className="rounded border border-line/60 bg-surface px-2.5 py-1.5">
            <div className="text-[10px] text-ink-muted font-medium">Down-Market Capture</div>
            <div className={`font-mono text-[13px] font-bold ${metrics.down_market_capture < 100 ? "text-emerald-400" : "text-amber-400"}`}>
              {metrics.down_market_capture.toFixed(1)}%
            </div>
          </div>

          <div className="rounded border border-line/60 bg-surface px-2.5 py-1.5">
            <div className="text-[10px] text-ink-muted font-medium">Alpha (Ann.)</div>
            <div className={`font-mono text-[13px] font-bold ${metrics.alpha_annualized >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {metrics.alpha_annualized >= 0 ? "+" : ""}
              {(metrics.alpha_annualized * 100).toFixed(1)}%
            </div>
          </div>

          <div className="rounded border border-line/60 bg-surface px-2.5 py-1.5">
            <div className="text-[10px] text-ink-muted font-medium">Information Ratio</div>
            <div className="font-mono text-[13px] font-bold text-accent">
              {metrics.information_ratio.toFixed(2)}
            </div>
          </div>
        </div>
      ) : null}

      {/* Chart Canvas */}
      <div className="p-3">
        {query.isLoading ? (
          <div className="flex h-48 items-center justify-center text-[12px] text-ink-muted">
            Loading benchmark series for {benchmark}…
          </div>
        ) : query.isError ? (
          <div className="flex h-48 items-center justify-center text-[12px] text-danger">
            {(query.error as Error).message}
          </div>
        ) : !chartData || series.length === 0 ? (
          <div className="flex h-48 flex-col items-center justify-center text-[12px] text-ink-muted px-4 text-center">
            <p className="font-semibold text-ink">
              {query.data?.error || `No comparative equity data found for benchmark '${benchmark}'.`}
            </p>
            <p className="mt-1 text-[11px] text-ink-faint max-w-md">
              Verify that '{benchmark}' is a valid symbol and has price history in ClickHouse during the backtest window.
            </p>
          </div>
        ) : (
          <div className="relative">
            {/* Hover Legend Line */}
            {activePt ? (
              <div className="flex flex-wrap items-center gap-4 pb-2 text-[11px] font-mono">
                <span className="font-bold text-ink">{activePt.date}</span>
                <span className="flex items-center gap-1 text-emerald-400 font-bold">
                  <span className="inline-block h-2 w-2 rounded-full bg-emerald-400"></span>
                  Strategy: ${activePt.strategy_equity.toLocaleString()} ({activePt.strategy_normalized.toFixed(2)})
                </span>
                <span className="flex items-center gap-1 text-slate-400">
                  <span className="inline-block h-2 w-2 rounded-full bg-slate-400"></span>
                  {currentOption.symbol} ({currentOption.name}): ${activePt.benchmark_price.toFixed(2)} ({activePt.benchmark_normalized.toFixed(2)})
                </span>
                <span className="font-semibold text-accent">
                  Spread: {(activePt.strategy_normalized - activePt.benchmark_normalized >= 0 ? "+" : "")}
                  {(activePt.strategy_normalized - activePt.benchmark_normalized).toFixed(2)} pts
                </span>
              </div>
            ) : null}

            <svg
              viewBox={`0 0 ${chartData.width} ${chartData.height}`}
              className="w-full h-48 select-none"
              onMouseLeave={() => setHoverIndex(null)}
            >
              <defs>
                <linearGradient id="stratGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#10b981" stopOpacity="0.25" />
                  <stop offset="100%" stopColor="#10b981" stopOpacity="0.0" />
                </linearGradient>
              </defs>

              {/* Grid Lines */}
              {[0, 0.25, 0.5, 0.75, 1.0].map((ratio) => {
                const y = chartData.pad.top + ratio * chartData.chartH;
                const val = chartData.maxVal - ratio * (chartData.maxVal - chartData.minVal);
                return (
                  <g key={ratio}>
                    <line
                      x1={chartData.pad.left}
                      y1={y}
                      x2={chartData.width - chartData.pad.right}
                      y2={y}
                      stroke="#27272a"
                      strokeWidth="1"
                      strokeDasharray="3 3"
                    />
                    <text
                      x={chartData.width - chartData.pad.right + 6}
                      y={y + 3}
                      fill="#71717a"
                      fontSize="9.5"
                      fontFamily="monospace"
                    >
                      {val.toFixed(1)}
                    </text>
                  </g>
                );
              })}

              {/* Baseline $100.0 line */}
              {chartData.minVal <= 100 && chartData.maxVal >= 100 ? (
                <line
                  x1={chartData.pad.left}
                  y1={chartData.scaleY(100)}
                  x2={chartData.width - chartData.pad.right}
                  y2={chartData.scaleY(100)}
                  stroke="#52525b"
                  strokeWidth="1"
                />
              ) : null}

              {/* Strategy Equity Area */}
              <polygon points={chartData.stratArea} fill="url(#stratGradient)" />

              {/* Benchmark Polyline (Dashed Slate) */}
              <polyline
                points={chartData.benchPoints}
                fill="none"
                stroke="#94a3b8"
                strokeWidth="1.6"
                strokeDasharray="4 3"
              />

              {/* Strategy Polyline (Emerald) */}
              <polyline
                points={chartData.stratPoints}
                fill="none"
                stroke="#10b981"
                strokeWidth="2.2"
                strokeLinecap="round"
              />

              {/* Interactive Hover Vertical Column */}
              {series.map((p, i) => {
                const x = chartData.scaleX(i);
                const colW = chartData.chartW / (series.length || 1);
                return (
                  <g key={`${p.date}-${i}`} onMouseEnter={() => setHoverIndex(i)} className="cursor-pointer">
                    <rect
                      x={x - colW / 2}
                      y={chartData.pad.top}
                      width={colW}
                      height={chartData.chartH}
                      fill="transparent"
                    />
                    {hoverIndex === i ? (
                      <g>
                        <line
                          x1={x}
                          y1={chartData.pad.top}
                          x2={x}
                          y2={chartData.pad.top + chartData.chartH}
                          stroke="#38bdf8"
                          strokeWidth="1"
                          strokeDasharray="2 2"
                        />
                        <circle cx={x} cy={chartData.scaleY(p.strategy_normalized)} r="4" fill="#10b981" />
                        <circle cx={x} cy={chartData.scaleY(p.benchmark_normalized)} r="4" fill="#94a3b8" />
                      </g>
                    ) : null}
                  </g>
                );
              })}
            </svg>
          </div>
        )}
      </div>
    </div>
  );
}
