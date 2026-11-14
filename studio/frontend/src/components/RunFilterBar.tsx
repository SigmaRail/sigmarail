import { useMemo } from "react";
import type { BacktestRunSummary } from "../types";

export type RunFilters = {
  search: string;
  status: string; // 'all' | 'done' | 'running' | 'failed'
  irId?: string; // specific ir_id filter
  alphaType: string; // 'all' or specific alpha type
  universeType: string;
  minSharpe: string; // 'all' | '0' | '0.5' | '1.0' | '1.5'
  returnTier: string; // 'all' | 'positive' | 'high' | 'negative'
  maxDd: string; // 'all' | '0.05' | '0.10' | '0.20'
  minOrders: boolean;
};

export const INITIAL_RUN_FILTERS: RunFilters = {
  search: "",
  status: "all",
  irId: undefined,
  alphaType: "all",
  universeType: "all",
  minSharpe: "all",
  returnTier: "all",
  maxDd: "all",
  minOrders: false,
};

export function RunFilterBar({
  filters,
  onChange,
  runs,
  filteredCount,
}: {
  filters: RunFilters;
  onChange: (filters: RunFilters) => void;
  runs: BacktestRunSummary[];
  filteredCount: number;
}) {
  // Extract unique alpha types and universe types from current runs
  const uniqueAlphas = useMemo(() => {
    const set = new Set<string>();
    for (const r of runs) {
      if (r.alpha_type) set.add(r.alpha_type);
    }
    return Array.from(set).sort();
  }, [runs]);

  const uniqueUniverses = useMemo(() => {
    const set = new Set<string>();
    for (const r of runs) {
      if (r.universe_type) set.add(r.universe_type);
    }
    return Array.from(set).sort();
  }, [runs]);

  const uniqueSpecs = useMemo(() => {
    const map = new Map<string, string>();
    for (const r of runs) {
      if (r.ir_id) {
        map.set(r.ir_id, r.spec_title || r.ir_id);
      }
    }
    return Array.from(map.entries()).map(([id, title]) => ({ id, title }));
  }, [runs]);

  const isFiltered =
    filters.search.trim() !== "" ||
    filters.status !== "all" ||
    (filters.irId != null && filters.irId !== "all") ||
    filters.alphaType !== "all" ||
    filters.universeType !== "all" ||
    filters.minSharpe !== "all" ||
    filters.returnTier !== "all" ||
    filters.maxDd !== "all" ||
    filters.minOrders;

  const handleReset = () => onChange(INITIAL_RUN_FILTERS);

  return (
    <div className="flex flex-col gap-2.5 rounded-lg border border-line bg-surface-raised p-3 text-xs">
      {/* Top Search & Status Strip */}
      <div className="flex flex-wrap items-center justify-between gap-2.5">
        <div className="relative flex-1 min-w-[200px]">
          <span className="absolute inset-y-0 left-2.5 flex items-center text-ink-faint pointer-events-none">
            🔍
          </span>
          <input
            type="text"
            value={filters.search}
            onChange={(e) => onChange({ ...filters, search: e.target.value })}
            placeholder="Search run_id, IR model, strategy title, alpha model, symbols…"
            className="w-full rounded border border-line bg-surface py-1.5 pl-8 pr-8 text-[12px] text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none"
          />
          {filters.search ? (
            <button
              type="button"
              onClick={() => onChange({ ...filters, search: "" })}
              className="absolute inset-y-0 right-2 flex items-center text-ink-muted hover:text-ink"
            >
              ✕
            </button>
          ) : null}
        </div>

        {/* Status Pill Toggles */}
        <div className="flex items-center rounded border border-line bg-surface p-0.5 text-[11px] font-medium">
          {[
            { id: "all", label: "All Status" },
            { id: "done", label: "Done", dot: "bg-emerald-400" },
            { id: "running", label: "Running", dot: "bg-sky-400 animate-pulse" },
            { id: "failed", label: "Failed", dot: "bg-rose-400" },
          ].map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => onChange({ ...filters, status: s.id })}
              className={`flex items-center gap-1.5 rounded px-2.5 py-1 transition-colors ${
                filters.status === s.id
                  ? "bg-surface-raised font-bold text-accent shadow-xs"
                  : "text-ink-muted hover:text-ink"
              }`}
            >
              {s.dot ? <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} /> : null}
              {s.label}
            </button>
          ))}
        </div>

        {/* Filter Count & Reset */}
        <div className="flex items-center gap-2">
          <span className="rounded bg-surface-sunk px-2 py-1 font-mono text-[11px] font-semibold text-ink-muted">
            {filteredCount} / {runs.length} runs
          </span>
          {isFiltered ? (
            <button
              type="button"
              onClick={handleReset}
              className="rounded border border-line/60 bg-surface px-2 py-1 text-[11px] font-medium text-ink-muted hover:bg-surface-sunk hover:text-ink transition-colors"
            >
              Reset Filters
            </button>
          ) : null}
        </div>
      </div>

      {/* Bottom Dropdowns & Performance Thresholds */}
      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        {/* Strategy Spec Dropdown */}
        {uniqueSpecs.length > 0 ? (
          <div className="flex items-center gap-1">
            <span className="text-ink-faint">Strategy:</span>
            <select
              value={filters.irId ?? "all"}
              onChange={(e) =>
                onChange({
                  ...filters,
                  irId: e.target.value === "all" ? undefined : e.target.value,
                })
              }
              className="rounded border border-line bg-surface px-2 py-1 text-ink focus:border-accent focus:outline-none max-w-[200px] truncate"
            >
              <option value="all">All Strategies ({uniqueSpecs.length})</option>
              {uniqueSpecs.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        {/* Alpha Model Dropdown */}
        {uniqueAlphas.length > 0 ? (
          <div className="flex items-center gap-1">
            <span className="text-ink-faint">Alpha:</span>
            <select
              value={filters.alphaType}
              onChange={(e) => onChange({ ...filters, alphaType: e.target.value })}
              className="rounded border border-line bg-surface px-2 py-1 text-ink focus:border-accent focus:outline-none"
            >
              <option value="all">All Alphas ({uniqueAlphas.length})</option>
              {uniqueAlphas.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        {/* Universe Model Dropdown */}
        {uniqueUniverses.length > 0 ? (
          <div className="flex items-center gap-1">
            <span className="text-ink-faint">Universe:</span>
            <select
              value={filters.universeType}
              onChange={(e) => onChange({ ...filters, universeType: e.target.value })}
              className="rounded border border-line bg-surface px-2 py-1 text-ink focus:border-accent focus:outline-none"
            >
              <option value="all">All Universes</option>
              {uniqueUniverses.map((u) => (
                <option key={u} value={u}>
                  {u}
                </option>
              ))}
            </select>
          </div>
        ) : null}

        {/* Min Sharpe Filter */}
        <div className="flex items-center gap-1">
          <span className="text-ink-faint">Min Sharpe:</span>
          <select
            value={filters.minSharpe}
            onChange={(e) => onChange({ ...filters, minSharpe: e.target.value })}
            className="rounded border border-line bg-surface px-2 py-1 text-ink focus:border-accent focus:outline-none"
          >
            <option value="all">Any Sharpe</option>
            <option value="0">&gt; 0.0</option>
            <option value="0.5">&gt; 0.5</option>
            <option value="1.0">&gt; 1.0 (Strong)</option>
            <option value="1.5">&gt; 1.5 (Elite)</option>
          </select>
        </div>

        {/* Return Tier Filter */}
        <div className="flex items-center gap-1">
          <span className="text-ink-faint">Return:</span>
          <select
            value={filters.returnTier}
            onChange={(e) => onChange({ ...filters, returnTier: e.target.value })}
            className="rounded border border-line bg-surface px-2 py-1 text-ink focus:border-accent focus:outline-none"
          >
            <option value="all">All Returns</option>
            <option value="positive">Profitable (&gt; 0%)</option>
            <option value="high">High Return (&gt; 10%)</option>
            <option value="negative">Losses (&lt; 0%)</option>
          </select>
        </div>

        {/* Max DD Filter */}
        <div className="flex items-center gap-1">
          <span className="text-ink-faint">Max DD:</span>
          <select
            value={filters.maxDd}
            onChange={(e) => onChange({ ...filters, maxDd: e.target.value })}
            className="rounded border border-line bg-surface px-2 py-1 text-ink focus:border-accent focus:outline-none"
          >
            <option value="all">Any Drawdown</option>
            <option value="0.05">&lt; 5% DD</option>
            <option value="0.10">&lt; 10% DD</option>
            <option value="0.20">&lt; 20% DD</option>
          </select>
        </div>

        {/* Min Orders Toggle */}
        <label className="flex items-center gap-1.5 cursor-pointer ml-auto text-ink-muted hover:text-ink">
          <input
            type="checkbox"
            checked={filters.minOrders}
            onChange={(e) => onChange({ ...filters, minOrders: e.target.checked })}
            className="rounded border-line bg-surface text-accent focus:ring-accent"
          />
          <span>Active Trades Only (&gt;0 orders)</span>
        </label>
      </div>
    </div>
  );
}
