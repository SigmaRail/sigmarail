import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchRunBenchmarkComparison } from "../../api/backtests";
import { fetchBenchmarkPreferences, saveBenchmarkPreferences } from "../../api/preferences";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Input } from "@sb/webapp-core/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@sb/webapp-core/components/ui/select";
import { ChartContainer, ChartTooltip, Area, AreaChart, CartesianGrid, Line, ResponsiveContainer, XAxis, YAxis, axisDefaults, gridDefaults } from "@sb/webapp-core/components/ui/chart";

export interface BenchmarkOption {
  symbol: string;
  name: string;
  category: "Broad Market" | "Leveraged Index" | "CAN SLIM & Breakouts" | "Momentum & Trend" | "Custom";
  description: string;
}

export const BENCHMARK_OPTIONS: BenchmarkOption[] = [
  { symbol: "SPY", name: "S&P 500", category: "Broad Market", description: "SPDR S&P 500 ETF Trust" },
  { symbol: "QQQ", name: "Nasdaq 100", category: "Broad Market", description: "Invesco QQQ Trust (Tech / Growth)" },
  { symbol: "IWM", name: "Russell 2000", category: "Broad Market", description: "iShares Russell 2000 ETF (Small-Cap)" },
  { symbol: "TQQQ", name: "3x QQQ", category: "Leveraged Index", description: "ProShares UltraPro QQQ (3x Daily Leveraged Nasdaq 100)" },
  { symbol: "QLD", name: "2x QQQ", category: "Leveraged Index", description: "ProShares Ultra QQQ (2x Daily Leveraged Nasdaq 100)" },
  { symbol: "UPRO", name: "3x SPY", category: "Leveraged Index", description: "ProShares UltraPro S&P 500 (3x Daily Leveraged S&P 500)" },
  { symbol: "SSO", name: "2x SPY", category: "Leveraged Index", description: "ProShares Ultra S&P 500 (2x Daily Leveraged S&P 500)" },
  { symbol: "FFTY", name: "IBD 50", category: "CAN SLIM & Breakouts", description: "CapForce IBD 50 ETF (CAN SLIM Fundamental & Technical Leaders)" },
  { symbol: "BOUT", name: "IBD Breakout", category: "CAN SLIM & Breakouts", description: "CapForce IBD Breakout Opportunities (Cup-with-Handle & Base Breakouts)" },
  { symbol: "QMOM", name: "Quant Momentum", category: "Momentum & Trend", description: "Alpha Architect US Quant Momentum" },
  { symbol: "PDP", name: "DWA Momentum", category: "Momentum & Trend", description: "Invesco DWA Momentum" },
  { symbol: "SPMO", name: "S&P Momentum", category: "Momentum & Trend", description: "Invesco S&P 500 Momentum Factor" },
  { symbol: "PTLC", name: "Trendpilot 200d", category: "Momentum & Trend", description: "Pacer Trendpilot US Large Cap" },
];

const BENCHMARK_GROUPS = [
  "Broad Market",
  "Leveraged Index",
  "CAN SLIM & Breakouts",
  "Momentum & Trend",
] as const;
const LEGACY_BENCHMARK_KEYS = ["sigmarail_custom_benchmarks", "vera_custom_benchmarks"] as const;

function accountBenchmarkKey(userId: string): string {
  return `sigmarail-studio.user.${encodeURIComponent(userId)}.custom-benchmarks`;
}

function readAccountBenchmarkPreferences(userId: string): string[] {
  try {
    const scoped = localStorage.getItem(accountBenchmarkKey(userId));
    if (scoped) {
      const parsed: unknown = JSON.parse(scoped);
      if (Array.isArray(parsed) && parsed.every((item) => typeof item === "string")) {
        return parsed.map((item) => item.trim().toUpperCase()).filter(Boolean).slice(0, 6);
      }
    }

    for (const key of LEGACY_BENCHMARK_KEYS) {
      const legacy = localStorage.getItem(key);
      if (!legacy) continue;
      const parsed: unknown = JSON.parse(legacy);
      const normalized = Array.isArray(parsed) && parsed.every((item) => typeof item === "string")
        ? parsed.map((item) => item.trim().toUpperCase()).filter(Boolean).slice(0, 6)
        : null;
      if (normalized) {
        localStorage.setItem(accountBenchmarkKey(userId), JSON.stringify(normalized));
        for (const legacyKey of LEGACY_BENCHMARK_KEYS) localStorage.removeItem(legacyKey);
        return normalized;
      }
    }
  } catch {
    // Invalid or unavailable browser storage must not block the profile preference.
  }
  return ["SMH", "NVDA"];
}

function formatDateTick(value: string): string {
  const date = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(date.getTime())
    ? value
    : new Intl.DateTimeFormat("en", { month: "short", year: "2-digit", timeZone: "UTC" }).format(date);
}

export function BenchmarkComparisonPanel({ runId }: { runId: string }) {
  const [benchmark, setBenchmark] = useState("SPY");
  const [customInput, setCustomInput] = useState("");
  const [customTickers, setCustomTickers] = useState<string[]>(["SMH", "NVDA"]);
  const [profileUserId, setProfileUserId] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void fetchBenchmarkPreferences()
      .then(({ userId, preferences }) => {
        if (!active) return;
        setProfileUserId(userId);
        if (preferences !== null) {
          setCustomTickers(preferences);
          if (userId) {
            try {
              localStorage.setItem(accountBenchmarkKey(userId), JSON.stringify(preferences));
            } catch {
              // The profile is the durable preference store.
            }
          }
          return;
        }
        if (!userId) return;
        // Import the account-scoped or previous browser-only list once.
        const accountPreferences = readAccountBenchmarkPreferences(userId);
        setCustomTickers(accountPreferences);
        void saveBenchmarkPreferences(accountPreferences).catch(() => {});
      })
      .catch(() => {
        // Keep the browser copy available while the profile API is unavailable.
      });
    return () => {
      active = false;
    };
  }, []);

  const saveCustomTickers = (tickers: string[]) => {
    setCustomTickers(tickers);
    if (profileUserId) {
      try {
        localStorage.setItem(accountBenchmarkKey(profileUserId), JSON.stringify(tickers));
      } catch {
        // Keep the selection usable for the current session if storage is unavailable.
      }
      void saveBenchmarkPreferences(tickers).catch(() => {
      // The browser-scoped copy remains available as an offline fallback.
      });
    }
  };

  const handleApplyCustom = (event: React.FormEvent) => {
    event.preventDefault();
    const symbol = customInput.trim().toUpperCase();
    if (!/^[A-Z0-9.-]{1,12}$/.test(symbol)) return;
    setBenchmark(symbol);
    if (!BENCHMARK_OPTIONS.some((option) => option.symbol === symbol) && !customTickers.includes(symbol)) {
      saveCustomTickers([symbol, ...customTickers].slice(0, 6));
    }
    setCustomInput("");
  };

  const handleRemoveCustom = (symbol: string) => {
    saveCustomTickers(customTickers.filter((ticker) => ticker !== symbol));
    if (benchmark === symbol) setBenchmark("SPY");
  };

  const currentOption = useMemo(() => {
    const found = BENCHMARK_OPTIONS.find((option) => option.symbol === benchmark);
    return found ?? {
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

  return (
    <section className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
      <header className="space-y-3 border-b border-border px-3 py-3 sm:px-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-foreground">Benchmark comparison &amp; active risk</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              $100 normalized starting value · comparing {currentOption.symbol} ({currentOption.name})
            </p>
          </div>
          <div className="grid w-full gap-2 sm:w-auto sm:grid-cols-[minmax(12rem,16rem)_auto]">
            <Select value={benchmark} onValueChange={setBenchmark}>
              <SelectTrigger aria-label="Benchmark" className="h-9 w-full text-xs sm:w-64">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {BENCHMARK_GROUPS.map((group) => (
                  <SelectGroup key={group}>
                    <SelectLabel>{group}</SelectLabel>
                    {BENCHMARK_OPTIONS.filter((option) => option.category === group).map((option) => (
                      <SelectItem key={option.symbol} value={option.symbol}>
                        {option.symbol} · {option.name}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                ))}
                {customTickers.some((symbol) => !BENCHMARK_OPTIONS.some((option) => option.symbol === symbol)) && (
                  <SelectGroup>
                    <SelectLabel>Custom</SelectLabel>
                    {customTickers
                      .filter((symbol) => !BENCHMARK_OPTIONS.some((option) => option.symbol === symbol))
                      .map((symbol) => <SelectItem key={symbol} value={symbol}>{symbol}</SelectItem>)}
                  </SelectGroup>
                )}
              </SelectContent>
            </Select>
            <form onSubmit={handleApplyCustom} className="flex min-w-0 gap-2">
              <Input
                value={customInput}
                onChange={(event) => setCustomInput(event.target.value.toUpperCase())}
                aria-label="Custom benchmark ticker"
                placeholder="Add ticker"
                maxLength={12}
                className="h-9 min-w-0 font-mono text-xs sm:w-36"
              />
              <Button type="submit" size="sm" className="h-9 shrink-0" disabled={!customInput.trim()}>
                Add
              </Button>
            </form>
          </div>
        </div>
        {customTickers.length > 0 ? (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">Saved benchmarks</span>
            {customTickers.map((symbol) => (
              <span key={symbol} className="inline-flex items-center rounded-md border border-border bg-muted/40">
                <Button
                  type="button"
                  variant={benchmark === symbol ? "secondary" : "ghost"}
                  size="sm"
                  className="h-7 rounded-r-none px-2 font-mono text-[11px]"
                  onClick={() => setBenchmark(symbol)}
                  aria-pressed={benchmark === symbol}
                >
                  {symbol}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 rounded-l-none text-muted-foreground"
                  onClick={() => handleRemoveCustom(symbol)}
                  aria-label={`Remove ${symbol} from saved benchmarks`}
                  title={`Remove ${symbol}`}
                >
                  ×
                </Button>
              </span>
            ))}
          </div>
        ) : null}
      </header>

      {metrics ? (
        <div className="grid grid-cols-2 gap-2 border-b border-border bg-muted/20 p-3 sm:grid-cols-4 xl:grid-cols-7">
          <Metric label="Strategy return" value={`${metrics.strategy_total_return >= 0 ? "+" : ""}${(metrics.strategy_total_return * 100).toFixed(2)}%`} positive={metrics.strategy_total_return >= 0} />
          <Metric label={`${currentOption.symbol} return`} value={`${metrics.benchmark_total_return >= 0 ? "+" : ""}${(metrics.benchmark_total_return * 100).toFixed(2)}%`} positive={metrics.benchmark_total_return >= 0} />
          <Metric label="Beta / correlation" value={`${metrics.beta.toFixed(2)} / ${metrics.correlation.toFixed(2)}`} />
          <Metric label="Up-market capture" value={`${metrics.up_market_capture.toFixed(1)}%`} />
          <Metric label="Down-market capture" value={`${metrics.down_market_capture.toFixed(1)}%`} positive={metrics.down_market_capture < 100} />
          <Metric label="Annualized alpha" value={`${metrics.alpha_annualized >= 0 ? "+" : ""}${(metrics.alpha_annualized * 100).toFixed(1)}%`} positive={metrics.alpha_annualized >= 0} />
          <Metric label="Information ratio" value={metrics.information_ratio.toFixed(2)} />
        </div>
      ) : null}

      <div className="p-3 sm:p-4">
        {query.isLoading ? (
          <div className="flex h-56 items-center justify-center text-sm text-muted-foreground">Loading benchmark series for {benchmark}…</div>
        ) : query.isError ? (
          <div role="alert" className="flex h-56 items-center justify-center text-sm text-destructive">{(query.error as Error).message}</div>
        ) : series.length === 0 ? (
          <div className="flex h-56 flex-col items-center justify-center px-4 text-center text-sm text-muted-foreground">
            <p className="font-medium text-foreground">{query.data?.error || `No comparative equity data for ${benchmark}.`}</p>
            <p className="mt-1 max-w-md text-xs">Check that the symbol has price history during this backtest window.</p>
          </div>
        ) : (
          <ChartContainer
            title="Growth of $100"
            description="Strategy and benchmark performance, normalized to the same starting value."
            className="rounded-md border-0 bg-transparent shadow-none [&>div:last-child]:p-0"
          >
            <div className="h-56 min-w-0 sm:h-72">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={series} margin={{ top: 8, right: 8, bottom: 4, left: -16 }}>
                  <CartesianGrid vertical={false} {...gridDefaults} />
                  <XAxis dataKey="date" tickFormatter={formatDateTick} minTickGap={28} {...axisDefaults} />
                  <YAxis domain={["auto", "auto"]} width={48} tickFormatter={(value: number) => value.toFixed(0)} {...axisDefaults} />
                  <ChartTooltip
                    title="Portfolio value"
                    labelFormatter={formatDateTick}
                    formatter={(value, name) => `${Number(value ?? 0).toFixed(2)} · ${name === "Strategy" ? "strategy" : currentOption.symbol}`}
                  />
                  <Area
                    type="monotone"
                    dataKey="strategy_normalized"
                    name="Strategy"
                    stroke="#2563eb"
                    fill="#2563eb"
                    fillOpacity={0.1}
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4, strokeWidth: 2, fill: "#2563eb", stroke: "white" }}
                  />
                  <Line
                    type="monotone"
                    dataKey="benchmark_normalized"
                    name={currentOption.symbol}
                    stroke="#64748b"
                    strokeWidth={2}
                    dot={false}
                    activeDot={{ r: 4, strokeWidth: 2, fill: "#64748b", stroke: "white" }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </ChartContainer>
        )}
      </div>
    </section>
  );
}

function Metric({
  label,
  value,
  positive,
}: {
  label: string;
  value: string;
  positive?: boolean;
}) {
  return (
    <div className="min-w-0 rounded-md border border-border/70 bg-card px-2.5 py-2">
      <div className="truncate text-[10px] text-muted-foreground" title={label}>{label}</div>
      <div className={`mt-1 font-mono text-xs font-semibold tabular-nums ${positive === undefined ? "text-foreground" : positive ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
        {value}
      </div>
    </div>
  );
}
