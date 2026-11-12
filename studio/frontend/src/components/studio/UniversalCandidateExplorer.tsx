import { useState, useMemo } from "react";
import { cn } from "../../lib/utils";
import { VeraCandidateChart } from "./VeraCandidateChart";
import type { RankedRow } from "../../types";

export interface CandidateItem {
  ticker: string;
  price?: number;
  rs_rating?: number;
  technical_rating?: number;
  setup_quality_rating?: number;
  atr_pct?: number;
  market_cap?: number;
  sector?: string;
  // Execution status flags for historical/live modes
  decision?: "bought" | "rejected_risk" | "passed_rank" | "holding" | "none";
  target_weight?: number;
  notes?: string;
}

interface UniversalCandidateExplorerProps {
  candidates: CandidateItem[] | RankedRow[];
  mode?: "interactive" | "historical" | "live";
  asOfDate?: string;
  selectedTicker?: string | null;
  onSelectTicker?: (ticker: string) => void;
  title?: string;
  subtitle?: string;
  loading?: boolean;
  onOpenUniverseLab?: () => void;
}

export function UniversalCandidateExplorer({
  candidates = [],
  mode = "interactive",
  asOfDate,
  selectedTicker,
  onSelectTicker,
  title,
  subtitle,
  loading = false,
  onOpenUniverseLab,
}: UniversalCandidateExplorerProps) {
  const [internalSelectedTicker, setInternalSelectedTicker] = useState<string | null>(null);
  const [filterText, setFilterText] = useState("");

  const activeSelectedTicker = selectedTicker !== undefined ? selectedTicker : internalSelectedTicker;

  const handleSelect = (ticker: string) => {
    setInternalSelectedTicker(ticker);
    onSelectTicker?.(ticker);
  };

  // Normalize candidate rows
  const normalizedCandidates = useMemo<CandidateItem[]>(() => {
    return (candidates as any[]).map((c) => {
      if ("rs_rating" in c || "technical_rating" in c) {
        return {
          ticker: c.ticker,
          price: c.close ?? c.price,
          rs_rating: c.rs_rating,
          technical_rating: c.technical_rating,
          setup_quality_rating: c.setup_quality_rating,
          atr_pct: c.atr_pct ?? (c.atr_14 && c.close ? (c.atr_14 / c.close) * 100 : undefined),
          market_cap: c.market_cap,
          sector: c.sector ?? c.gics_sector,
          decision: c.decision ?? "none",
          target_weight: c.target_weight,
          notes: c.notes,
        };
      }
      return c as CandidateItem;
    });
  }, [candidates]);

  // Filter candidates
  const filteredCandidates = useMemo(() => {
    if (!filterText.trim()) return normalizedCandidates;
    const q = filterText.toLowerCase();
    return normalizedCandidates.filter(
      (c) =>
        c.ticker.toLowerCase().includes(q) ||
        (c.sector && c.sector.toLowerCase().includes(q))
    );
  }, [normalizedCandidates, filterText]);

  const effectiveSelectedTicker =
    activeSelectedTicker || filteredCandidates[0]?.ticker || null;

  return (
    <div className="flex flex-col rounded-lg border border-line bg-surface shadow-sm overflow-hidden">
      {/* Header Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-surface-raised px-3.5 py-2.5">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-bold text-ink">
              {title || (mode === "historical" ? "Point-in-Time Candidates" : mode === "live" ? "Live Candidate Feed" : "Universe Candidates")}
            </span>
            <span className="rounded bg-surface-sunk px-2 py-0.5 font-mono text-[10.5px] font-bold text-accent">
              {filteredCandidates.length} names
            </span>
            {asOfDate ? (
              <span className="font-mono text-[11px] text-ink-muted">
                as of {asOfDate}
              </span>
            ) : null}
          </div>
          {subtitle ? (
            <p className="text-[11px] text-ink-faint">{subtitle}</p>
          ) : null}
        </div>

        <div className="flex items-center gap-2">
          <input
            type="search"
            placeholder="Search ticker/sector…"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            className="rounded border border-line bg-surface px-2.5 py-1 text-[11px] text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none"
          />
          {onOpenUniverseLab ? (
            <button
              type="button"
              onClick={onOpenUniverseLab}
              className="rounded bg-accent px-2.5 py-1 text-[11px] font-semibold text-accent-ink hover:opacity-90 transition-opacity"
            >
              Open Universe Lab
            </button>
          ) : null}
        </div>
      </div>

      {/* Decision Legend for Historical Mode */}
      {mode === "historical" ? (
        <div className="flex flex-wrap items-center gap-3 border-b border-line/60 bg-surface-sunk/40 px-3.5 py-1.5 text-[10px] text-ink-muted">
          <span className="font-semibold text-ink">Historical Model Decisions:</span>
          <span className="flex items-center gap-1">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400"></span> Bought / Active
          </span>
          <span className="flex items-center gap-1">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400"></span> Rejected (Risk / Cap)
          </span>
          <span className="flex items-center gap-1">
            <span className="h-1.5 w-1.5 rounded-full bg-ink-faint"></span> Passed Rank
          </span>
        </div>
      ) : null}

      {/* 2-Pane Side-by-Side Workbench Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 min-h-[380px] divide-y lg:divide-y-0 lg:divide-x divide-line">
        {/* Left Pane (5 Cols): Candidate Table */}
        <div className="lg:col-span-5 max-h-[420px] overflow-y-auto bg-surface">
          {loading ? (
            <div className="flex h-48 items-center justify-center text-[12px] text-ink-muted">
              Loading universe candidates…
            </div>
          ) : filteredCandidates.length === 0 ? (
            <div className="flex h-48 items-center justify-center text-[12px] text-ink-muted">
              No universe candidates matching criteria.
            </div>
          ) : (
            <table className="w-full text-left text-[11px]">
              <thead className="sticky top-0 z-10 border-b border-line bg-surface-sunk text-ink-faint">
                <tr>
                  <th className="px-3 py-1.5">Ticker</th>
                  <th className="px-2 py-1.5">Price</th>
                  <th className="px-2 py-1.5">RS</th>
                  <th className="px-2 py-1.5">TA</th>
                  <th className="px-2 py-1.5">Sector</th>
                  {mode === "historical" && <th className="px-2 py-1.5">Decision</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-line/60">
                {filteredCandidates.map((c, idx) => {
                  const isSelected = c.ticker === effectiveSelectedTicker;
                  return (
                    <tr
                      key={`${c.ticker}-${idx}`}
                      onClick={() => handleSelect(c.ticker)}
                      className={cn(
                        "cursor-pointer transition-colors hover:bg-surface-sunk/60",
                        isSelected && "bg-accent/15 font-semibold"
                      )}
                    >
                      <td className={cn(
                        "px-3 py-1.5 font-mono font-bold text-ink",
                        isSelected && "text-accent font-extrabold"
                      )}>
                        {c.ticker}
                      </td>
                      <td className="px-2 py-1.5 font-mono tabular-nums text-ink">
                        {c.price != null ? `$${c.price.toFixed(2)}` : "—"}
                      </td>
                      <td className="px-2 py-1.5 font-mono tabular-nums text-emerald-400 font-bold">
                        {c.rs_rating != null ? Math.round(c.rs_rating) : "—"}
                      </td>
                      <td className="px-2 py-1.5 font-mono tabular-nums text-ink">
                        {c.technical_rating != null ? Math.round(c.technical_rating) : "—"}
                      </td>
                      <td className="px-2 py-1.5 text-[10px] text-ink-muted truncate max-w-[100px]">
                        {c.sector || "—"}
                      </td>
                      {mode === "historical" && (
                        <td className="px-2 py-1.5">
                          {c.decision === "bought" ? (
                            <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 text-[9.5px] font-bold text-emerald-400">
                              BOUGHT
                            </span>
                          ) : c.decision === "rejected_risk" ? (
                            <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-[9.5px] font-bold text-amber-400">
                              REJECTED
                            </span>
                          ) : (
                            <span className="font-mono text-[9.5px] text-ink-faint">
                              passed
                            </span>
                          )}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Right Pane (7 Cols): Native ClickHouse Candlestick Chart */}
        <div className="lg:col-span-7 flex flex-col bg-surface min-h-[380px] overflow-hidden">
          {effectiveSelectedTicker ? (
            <VeraCandidateChart
              ticker={effectiveSelectedTicker}
              asOfDate={asOfDate}
              height={390}
            />
          ) : (
            <div className="flex h-full items-center justify-center text-[12px] text-ink-muted">
              Select a candidate ticker to inspect historical candlestick chart.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
