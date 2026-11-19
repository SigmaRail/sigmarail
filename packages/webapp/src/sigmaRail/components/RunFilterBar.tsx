import { useEffect, useMemo, useState } from "react";
import type { BacktestRunSummary } from "../types";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Input } from "@sb/webapp-core/components/ui/input";
import { Checkbox } from "@sb/webapp-core/components/forms/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@sb/webapp-core/components/ui/select";

function FilterSelect({
  label,
  value,
  onValueChange,
  options,
}: {
  label: string;
  value: string;
  onValueChange: (value: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
      <span className="shrink-0">{label}</span>
      <Select value={value} onValueChange={onValueChange}>
        <SelectTrigger className="h-8 min-w-[8rem] max-w-[14rem] px-2 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}
        </SelectContent>
      </Select>
    </label>
  );
}

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
  const [advancedFiltersOpen, setAdvancedFiltersOpen] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(min-width: 768px)").matches,
  );

  useEffect(() => {
    const media = window.matchMedia("(min-width: 768px)");
    const syncToViewport = (event: MediaQueryListEvent) => setAdvancedFiltersOpen(event.matches);
    media.addEventListener("change", syncToViewport);
    return () => media.removeEventListener("change", syncToViewport);
  }, []);

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

  const advancedFilterCount = [
    filters.irId != null && filters.irId !== "all",
    filters.alphaType !== "all",
    filters.universeType !== "all",
    filters.minSharpe !== "all",
    filters.returnTier !== "all",
    filters.maxDd !== "all",
    filters.minOrders,
  ].filter(Boolean).length;

  const handleReset = () => onChange(INITIAL_RUN_FILTERS);

  return (
    <div className="flex flex-col gap-3 rounded-lg border bg-card p-3 text-xs">
      {/* Top Search & Status Strip */}
      <div className="flex flex-wrap items-center justify-between gap-2.5">
        <div className="relative min-w-0 flex-1 sm:min-w-[200px]">
          <Input
            type="text"
            value={filters.search}
            onChange={(e) => onChange({ ...filters, search: e.target.value })}
            placeholder="Search runs, strategies, or symbols"
            aria-label="Search backtest runs"
            className="h-9 w-full pr-8 text-sm"
          />
          {filters.search ? (
            <Button
              type="button"
              onClick={() => onChange({ ...filters, search: "" })}
              variant="ghost"
              size="icon"
              aria-label="Clear search"
              className="absolute right-0 top-0 h-9 w-9"
            >
              ✕
            </Button>
          ) : null}
        </div>

        {/* Status Pill Toggles */}
        <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Filter by run status">
          {[
            { id: "all", label: "All Status" },
            { id: "done", label: "Done", dot: "bg-emerald-400" },
            { id: "running", label: "Running", dot: "bg-sky-400 animate-pulse" },
            { id: "failed", label: "Failed", dot: "bg-rose-400" },
          ].map((s) => (
            <Button
              key={s.id}
              type="button"
              onClick={() => onChange({ ...filters, status: s.id })}
              variant={filters.status === s.id ? "secondary" : "ghost"}
              size="sm"
              className="h-8 px-2.5 text-xs"
            >
              {s.label}
            </Button>
          ))}
        </div>

        {/* Filter Count & Reset */}
        <div className="flex items-center gap-2">
            <span className="whitespace-nowrap text-xs text-muted-foreground">
            {filteredCount} / {runs.length} runs
          </span>
          {isFiltered ? (
              <Button
              type="button"
              onClick={handleReset}
                variant="ghost"
                size="sm"
                className="h-8 px-2 text-xs"
            >
                Reset
              </Button>
          ) : null}
        </div>
      </div>

      {/* Secondary facets stay out of the way on phones, while remaining visible on desktop. */}
      <details
        className="group md:contents"
        open={advancedFiltersOpen}
        onToggle={(event) => setAdvancedFiltersOpen(event.currentTarget.open)}
      >
        <summary
          aria-label="Additional backtest filters"
          className="flex min-h-9 cursor-pointer list-none items-center justify-between rounded-md border px-3 text-sm font-medium text-foreground marker:hidden md:hidden"
        >
          <span>More filters{advancedFilterCount ? ` · ${advancedFilterCount} active` : ""}</span>
          <span aria-hidden="true" className="text-muted-foreground transition-transform group-open:rotate-180">⌄</span>
        </summary>
        <div className="mt-2 hidden flex-wrap items-center gap-2 group-open:flex md:mt-0 md:flex">
        {/* Strategy Spec Dropdown */}
        {uniqueSpecs.length > 0 ? (
          <FilterSelect
            label="Strategy"
            value={filters.irId ?? "all"}
            onValueChange={(value) =>
                onChange({
                  ...filters,
                  irId: value === "all" ? undefined : value,
                })
            }
            options={[{ value: "all", label: `All strategies (${uniqueSpecs.length})` }, ...uniqueSpecs.map((s) => ({ value: s.id, label: s.title }))]}
          />
        ) : null}

        {/* Alpha Model Dropdown */}
        {uniqueAlphas.length > 0 ? (
          <FilterSelect
            label="Alpha"
            value={filters.alphaType}
            onValueChange={(alphaType) => onChange({ ...filters, alphaType })}
            options={[{ value: "all", label: `All alphas (${uniqueAlphas.length})` }, ...uniqueAlphas.map((alpha) => ({ value: alpha, label: alpha }))]}
          />
        ) : null}

        {/* Universe Model Dropdown */}
        {uniqueUniverses.length > 0 ? (
          <FilterSelect
            label="Universe"
            value={filters.universeType}
            onValueChange={(universeType) => onChange({ ...filters, universeType })}
            options={[{ value: "all", label: "All universes" }, ...uniqueUniverses.map((universe) => ({ value: universe, label: universe }))]}
          />
        ) : null}

        {/* Min Sharpe Filter */}
        <FilterSelect label="Min Sharpe" value={filters.minSharpe} onValueChange={(minSharpe) => onChange({ ...filters, minSharpe })} options={[
          { value: "all", label: "Any" }, { value: "0", label: "> 0.0" }, { value: "0.5", label: "> 0.5" }, { value: "1.0", label: "> 1.0 (Strong)" }, { value: "1.5", label: "> 1.5 (Elite)" },
        ]} />

        {/* Return Tier Filter */}
        <FilterSelect label="Return" value={filters.returnTier} onValueChange={(returnTier) => onChange({ ...filters, returnTier })} options={[
          { value: "all", label: "All returns" }, { value: "positive", label: "Profitable (> 0%)" }, { value: "high", label: "High (> 10%)" }, { value: "negative", label: "Losses (< 0%)" },
        ]} />

        {/* Max DD Filter */}
        <FilterSelect label="Max drawdown" value={filters.maxDd} onValueChange={(maxDd) => onChange({ ...filters, maxDd })} options={[
          { value: "all", label: "Any" }, { value: "0.05", label: "< 5%" }, { value: "0.10", label: "< 10%" }, { value: "0.20", label: "< 20%" },
        ]} />

        {/* Min Orders Toggle */}
        <Checkbox
          className="ml-auto"
          label="Active trades only (> 0 orders)"
          checked={filters.minOrders}
          onCheckedChange={(checked) => onChange({ ...filters, minOrders: checked === true })}
        />
        </div>
      </details>
    </div>
  );
}
