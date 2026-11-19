import { useState, useMemo } from "react";
import { cn } from "../../lib/utils";
import { CandidatePriceChart } from "./CandidatePriceChart";
import type { RankedRow } from "../../types";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Input } from "@sb/webapp-core/components/ui/input";
import { Badge } from "@sb/webapp-core/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@sb/webapp-core/components/ui/table";

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
          <Input
            type="search"
            placeholder="Search ticker/sector…"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            aria-label="Search candidates by ticker or sector"
            className="h-9 w-full sm:w-56 px-2.5 py-1 text-[11px]"
          />
          {onOpenUniverseLab ? (
            <Button
              type="button"
              onClick={onOpenUniverseLab}
              variant="default"
              size="sm"
              className="h-9 shrink-0 text-[11px]"
            >
              Open Universe Lab
            </Button>
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
            <>
              <Table containerClassName="max-h-[420px] overflow-auto" className="min-w-[520px]">
                <TableHeader className="sticky top-0 z-10 bg-surface-sunk text-ink-faint">
                  <TableRow>
                    <TableHead className="h-auto px-3 py-1.5 text-[10px]">Ticker</TableHead>
                    <TableHead className="h-auto px-2 py-1.5 text-[10px]">Price</TableHead>
                    <TableHead className="h-auto px-2 py-1.5 text-[10px]">RS</TableHead>
                    <TableHead className="h-auto px-2 py-1.5 text-[10px]">TA</TableHead>
                    <TableHead className="h-auto px-2 py-1.5 text-[10px]">Sector</TableHead>
                    {mode === "historical" && <TableHead className="h-auto px-2 py-1.5 text-[10px]">Decision</TableHead>}
                  </TableRow>
                </TableHeader>
                <TableBody className="divide-y divide-line/60">
                  {filteredCandidates.map((candidate, idx) => {
                    const isSelected = candidate.ticker === effectiveSelectedTicker;
                    return (
                      <TableRow
                        key={`${candidate.ticker}-${idx}`}
                        data-state={isSelected ? "selected" : undefined}
                        className={cn("text-[11px]", isSelected && "bg-accent/15 font-semibold")}
                      >
                        <TableCell className={cn("px-3 py-1.5", isSelected && "text-accent")}>
                          <Button type="button" variant="link" size="sm" aria-pressed={isSelected} onClick={() => handleSelect(candidate.ticker)} className="h-auto min-w-0 justify-start p-0 font-mono text-[11px] font-bold">
                            {candidate.ticker}
                          </Button>
                        </TableCell>
                        <TableCell className="px-2 py-1.5 font-mono tabular-nums">{candidate.price != null ? `$${candidate.price.toFixed(2)}` : "—"}</TableCell>
                        <TableCell className="px-2 py-1.5 font-mono font-bold tabular-nums text-emerald-500">{candidate.rs_rating != null ? Math.round(candidate.rs_rating) : "—"}</TableCell>
                        <TableCell className="px-2 py-1.5 font-mono tabular-nums">{candidate.technical_rating != null ? Math.round(candidate.technical_rating) : "—"}</TableCell>
                        <TableCell className="max-w-[100px] truncate px-2 py-1.5 text-[10px] text-ink-muted">{candidate.sector || "—"}</TableCell>
                        {mode === "historical" && (
                          <TableCell className="px-2 py-1.5">
                            <Badge variant={candidate.decision === "bought" ? "default" : "secondary"}>
                              {candidate.decision === "bought" ? "Bought" : candidate.decision === "rejected_risk" ? "Rejected" : "Passed"}
                            </Badge>
                          </TableCell>
                        )}
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </>
          )}
        </div>

        {/* Candidate price chart uses the shared stock chart engine. */}
        <div className="lg:col-span-7 flex min-h-[420px] min-w-0 flex-col overflow-hidden bg-surface">
          {effectiveSelectedTicker ? (
            <CandidatePriceChart
              ticker={effectiveSelectedTicker}
              asOfDate={asOfDate}
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
