import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useGenerateLocalePath } from "@sb/webapp-core/hooks";
import { fetchBacktestSpecDetail, fetchBacktestSpecs } from "../../api/backtests";
import { fetchCatalogTemplates } from "../../api/strategy";
import type { BacktestSpecSummary } from "../../types";
import { CopyIdBadge } from "../CopyIdBadge";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Input } from "@sb/webapp-core/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@sb/webapp-core/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@sb/webapp-core/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@sb/webapp-core/components/ui/dialog";

/** Studio compose only lists AST templates that compile against the current pipeline. */
const STUDIO_STRATEGY_TEMPLATE_IDS = [
  "minervini_sepa",
  "minervini_sepa_eps_beat",
  "minervini_sepa_eps_beat_override",
  "minervini_sepa_weighted",
] as const;

interface SpecLibraryModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** Open: load into compose (navigate to ir_id). */
  onSelectSpec: (spec: BacktestSpecSummary) => void;
  /** Clone: copy to a new ir_id and open. */
  onDuplicateSpec: (spec: BacktestSpecSummary) => void;
}

export function SpecLibraryModal({
  isOpen,
  onClose,
  onSelectSpec,
  onDuplicateSpec,
}: SpecLibraryModalProps) {
  const navigate = useNavigate();
  const generateLocalePath = useGenerateLocalePath();
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [schemaFilter, setSchemaFilter] = useState<"all" | "modern" | "legacy">("all");
  const [alphaFilter, setAlphaFilter] = useState<string>("all");
  const [inspectingJsonSpec, setInspectingJsonSpec] = useState<BacktestSpecSummary | null>(null);

  const catalogQuery = useQuery({
    queryKey: ["catalog-templates", "strategy", "studio-working"],
    queryFn: () => fetchCatalogTemplates({ kind: "strategy", status: "active" }),
    enabled: isOpen,
  });

  const chSpecsQuery = useQuery({
    queryKey: ["strategy-specs-library"],
    queryFn: () => fetchBacktestSpecs({ limit: 200 }),
    enabled: isOpen,
    staleTime: 15_000,
  });

  const catalogSpecs: BacktestSpecSummary[] = useMemo(
    () =>
      (catalogQuery.data ?? [])
        .filter((row) =>
          (STUDIO_STRATEGY_TEMPLATE_IDS as readonly string[]).includes(row.id),
        )
        .map((row) => ({
          ir_id: `catalog:${row.id}`,
          title: row.label,
          notes: [row.description, row.why, row.how].filter(Boolean).join(" "),
          category: "catalog",
          is_system: true,
          is_template: true,
          alpha_type: "VeraPyramidAlphaModel",
          universe_type: "VeraScreenerUniverseSelectionModel",
          catalog_template_id: row.id,
          has_pipeline: true,
          schema_status: "modern",
        })),
    [catalogQuery.data],
  );

  const allSpecs = useMemo(() => {
    const ch = (chSpecsQuery.data ?? []).filter(
      // Drop legacy is_system builtins if any still appear; catalog seed is separate.
      (s) => !s.is_system,
    );
    const seen = new Set(ch.map((s) => s.ir_id));
    const merged = [...ch];
    for (const c of catalogSpecs) {
      if (!seen.has(c.ir_id)) merged.push(c);
    }
    return merged;
  }, [chSpecsQuery.data, catalogSpecs]);

  // Extract unique alpha models for filtering
  const alphaModels = useMemo(() => {
    const s = new Set<string>();
    for (const spec of allSpecs) {
      if (spec.alpha_type) s.add(spec.alpha_type);
    }
    return Array.from(s).sort();
  }, [allSpecs]);

  // Counts for tabs
  const counts = useMemo(() => {
    let catalog = 0;
    let templates = 0;
    let strategies = 0;
    let modern = 0;
    let legacy = 0;

    for (const s of allSpecs) {
      if (s.is_system || s.catalog_template_id) {
        catalog++;
      } else if (s.is_template) {
        templates++;
      } else {
        strategies++;
      }

      if (s.schema_status === "modern" || s.has_pipeline || s.catalog_template_id) {
        modern++;
      } else {
        legacy++;
      }
    }

    return { total: allSpecs.length, catalog, templates, strategies, modern, legacy };
  }, [allSpecs]);

  // Filtered specs list
  const filteredSpecs = useMemo(() => {
    return allSpecs.filter((s) => {
      if (selectedCategory === "catalog" && !(s.is_system || s.catalog_template_id)) return false;
      if (selectedCategory === "templates" && (!s.is_template || s.is_system)) return false;
      if (selectedCategory === "strategies" && (s.is_system || s.is_template)) return false;

      const isModern = Boolean(s.schema_status === "modern" || s.has_pipeline || s.catalog_template_id);
      if (schemaFilter === "modern" && !isModern) return false;
      if (schemaFilter === "legacy" && isModern) return false;

      if (alphaFilter !== "all" && s.alpha_type !== alphaFilter) return false;

      if (searchTerm.trim()) {
        const query = searchTerm.toLowerCase();
        const matchable = [
          s.title,
          s.ir_id,
          s.notes,
          s.category,
          s.alpha_type,
          s.universe_type,
          ...(s.symbols ?? []),
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();

        if (!matchable.includes(query)) return false;
      }

      return true;
    });
  }, [allSpecs, selectedCategory, schemaFilter, alphaFilter, searchTerm]);

  if (!isOpen) return null;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        size="full"
        className="flex h-[calc(100dvh-1rem)] max-h-[calc(100dvh-1rem)] w-[calc(100vw-1rem)] max-w-6xl flex-col gap-0 overflow-hidden rounded-xl p-0 sm:h-[92dvh] sm:max-h-[92dvh]"
      >
        {/* Modal Header */}
        <DialogHeader className="flex flex-row items-start justify-between gap-3 border-b border-line bg-surface-raised px-4 py-3 pr-12 sm:px-6 sm:py-4">
          <div className="flex min-w-0 items-start gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/15 border border-accent/30 text-accent font-bold">
              📚
            </div>
            <div className="min-w-0">
              <DialogTitle className="flex flex-wrap items-center gap-2 text-base font-bold text-ink">
                Strategy Spec & Template Library
                <span className="rounded-full bg-surface-sunk border border-line px-2 py-0.5 text-[10px] font-mono text-ink-muted">
                  {filteredSpecs.length} / {allSpecs.length}
                </span>
              </DialogTitle>
              <DialogDescription className="mt-1 text-[11.5px] text-ink-muted">
                Open a Strategy or Template in compose, or Clone a copy. Template is a filter tag.
              </DialogDescription>
            </div>
          </div>

          <div className="hidden items-center gap-2 sm:flex">
            <Button
              type="button"
              onClick={onClose}
              variant="outline"
              className="rounded-lg border border-line bg-surface-sunk px-3 py-1.5 text-xs font-semibold text-ink hover:bg-surface-raised hover:border-accent/40 transition-colors"
            >
              Close (Esc)
            </Button>
          </div>
        </DialogHeader>

        {/* Filter & Search Bar */}
        <div className="flex flex-col gap-3 border-b border-line/60 bg-surface-sunk/60 px-3 py-3 sm:px-6">
          {/* Category Tabs & Schema Filter */}
          <div className="grid min-w-0 gap-2 xl:grid-cols-[minmax(0,1fr)_auto]">
            <Tabs value={selectedCategory} onValueChange={(value) => setSelectedCategory(value)}>
              <TabsList className="grid h-auto w-full grid-cols-4 p-1">
                <TabsTrigger value="all" className="min-w-0 px-2 py-1.5 text-xs">All ({counts.total})</TabsTrigger>
                <TabsTrigger value="strategies" className="min-w-0 px-2 py-1.5 text-xs">Strategies ({counts.strategies})</TabsTrigger>
                <TabsTrigger value="templates" className="min-w-0 px-2 py-1.5 text-xs">Templates ({counts.templates})</TabsTrigger>
                <TabsTrigger value="catalog" className="min-w-0 px-2 py-1.5 text-xs">Catalog ({counts.catalog})</TabsTrigger>
              </TabsList>
            </Tabs>

            <Tabs value={schemaFilter} onValueChange={(value) => setSchemaFilter(value as "all" | "modern" | "legacy")}>
              <TabsList className="grid h-auto w-full grid-cols-3 p-1 xl:w-auto">
                <TabsTrigger value="all" className="px-2 py-1.5 text-xs">Any schema</TabsTrigger>
                <TabsTrigger value="modern" title="Specs with modern multi-stage pipeline documents" className="px-2 py-1.5 text-xs">Modern ({counts.modern})</TabsTrigger>
                <TabsTrigger value="legacy" title="Legacy AST specs (upgradeable via pipeline decompiler)" className="px-2 py-1.5 text-xs">Legacy ({counts.legacy})</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>

          {/* Search & Alpha Dropdown */}
          <div className="flex w-full min-w-0 flex-col gap-2 sm:flex-row sm:items-center">
            <div className="relative flex-1">
              <Input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                aria-label="Search strategy specs"
                placeholder="Search title, ir_id, models, symbols…"
                className="h-10 w-full pl-8 font-mono text-xs"
              />
              <span aria-hidden="true" className="pointer-events-none absolute left-2.5 top-3 text-xs text-muted-foreground">🔍</span>
              {searchTerm ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => setSearchTerm("")}
                  aria-label="Clear spec search"
                  className="absolute right-1 top-1 h-8 w-8"
                >
                  ✕
                </Button>
              ) : null}
            </div>

            <Select
              value={alphaFilter}
              onValueChange={setAlphaFilter}
            >
              <SelectTrigger aria-label="Alpha model" className="h-10 w-full text-xs sm:w-[260px]">
                <SelectValue placeholder="All Alpha Models" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Alpha Models ({alphaModels.length})</SelectItem>
              {alphaModels.map((m) => (
                <SelectItem key={m} value={m}>
                  {m}
                </SelectItem>
              ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Spec Grid / Card List */}
        <div className="min-h-0 flex-1 overflow-y-auto bg-surface/50 p-3 sm:p-6">
          {catalogQuery.isLoading || chSpecsQuery.isLoading ? (
            <div className="flex h-64 flex-col items-center justify-center gap-2 text-ink-muted">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
              <p className="text-xs">Loading strategy specifications & templates…</p>
            </div>
          ) : filteredSpecs.length === 0 ? (
            <div className="flex h-64 flex-col items-center justify-center gap-3 text-center border border-dashed border-line rounded-xl bg-surface-raised/40 p-8">
              <span className="text-3xl">🔍</span>
              <p className="text-sm font-semibold text-ink">No matching strategy specs found</p>
              <p className="text-xs text-ink-muted max-w-md">
                Try adjusting your search query or switching categories. You can save any current 5-slot composition as a template anytime.
              </p>
              {searchTerm || selectedCategory !== "all" || alphaFilter !== "all" ? (
                <Button
                  type="button"
                  onClick={() => {
                    setSearchTerm("");
                    setSelectedCategory("all");
                    setAlphaFilter("all");
                  }}
                variant="outline"
                  className="rounded-md border border-line bg-surface px-3 py-1.5 text-xs font-semibold text-ink hover:bg-surface-raised"
                >
                  Reset Filters
                </Button>
              ) : null}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
              {filteredSpecs.map((spec) => {
                return (
                  <div
                    key={spec.ir_id}
                    className="flex flex-col justify-between rounded-xl border border-line bg-surface-raised/80 p-3 transition-all hover:border-accent/50 hover:shadow-lg sm:p-4 group"
                  >
                    <div>
                      {/* Top Badges & Title */}
                      <div className="flex items-start justify-between gap-2 mb-2">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5 flex-wrap mb-1">
                            {spec.is_system ? (
                              <span className="rounded bg-sky-500/15 border border-sky-500/30 px-1.5 py-0.5 text-[9.5px] font-semibold text-sky-400 uppercase tracking-wide">
                                🌟 System Template
                              </span>
                            ) : spec.is_template ? (
                              <span className="rounded bg-emerald-500/15 border border-emerald-500/30 px-1.5 py-0.5 text-[9.5px] font-semibold text-emerald-400 uppercase tracking-wide">
                                💾 Saved Template
                              </span>
                            ) : (
                              <span className="rounded bg-surface-sunk border border-line px-1.5 py-0.5 text-[9.5px] font-semibold text-ink-muted uppercase tracking-wide">
                                ⚙️ Custom Spec
                              </span>
                            )}
                            {spec.is_shared ? (
                              <span className="rounded bg-muted px-1.5 py-0.5 text-[9.5px] font-semibold uppercase tracking-wide text-muted-foreground">
                                Shared · fork to edit
                              </span>
                            ) : null}

                            {/* Schema Version Badge */}
                            {spec.catalog_template_id || spec.has_pipeline || spec.schema_status === "modern" ? (
                              <span className="rounded bg-emerald-500/10 border border-emerald-500/25 px-1.5 py-0.5 text-[9.5px] font-medium text-emerald-400">
                                v2 Pipeline
                              </span>
                            ) : (
                              <span
                                className="rounded bg-amber-500/10 border border-amber-500/25 px-1.5 py-0.5 text-[9.5px] font-medium text-amber-400"
                                title="Legacy AST spec (lacks pipeline_json stage definitions)"
                              >
                                v1 Legacy AST
                              </span>
                            )}

                            {spec.category ? (
                              <span className="rounded bg-purple-500/10 border border-purple-500/20 px-1.5 py-0.5 text-[9.5px] font-medium text-purple-300">
                                {spec.category}
                              </span>
                            ) : null}
                          </div>

                          <h3 className="font-semibold text-[13.5px] text-ink group-hover:text-accent transition-colors truncate">
                            {spec.title}
                          </h3>

                          {/* Metadata row: Hash & Date */}
                          <div className="flex items-center gap-2 mt-0.5 mb-1 text-[10px] text-ink-muted font-mono">
                            {spec.ir_content_hash ? (
                              <span
                                className="rounded bg-surface-sunk border border-line px-1.5 py-0.2 text-[9.5px] text-ink-muted"
                                title={`Immutable Content Hash: ${spec.ir_content_hash}`}
                              >
                                #{spec.ir_content_hash.slice(0, 8)}
                              </span>
                            ) : null}
                            {spec.created_at ? (
                              <span className="text-ink-faint text-[9.5px]">
                                {spec.created_at.slice(0, 10)}
                              </span>
                            ) : null}
                          </div>
                        </div>

                        <CopyIdBadge
                          id={spec.ir_id}
                          label="IR"
                          head={6}
                          tail={4}
                          sqlQuery={`SELECT * FROM strategy_algorithm_specs FINAL WHERE ir_id = '${spec.ir_id}'`}
                        />
                      </div>

                      {/* Notes / Description */}
                      <p className="text-[11.5px] text-ink-muted line-clamp-2 mb-3 min-h-[32px]">
                        {spec.notes || "Standard 5-slot QuantConnect algorithmic specification."}
                      </p>

                      {/* 5-Slot Pipeline Mini-Tags */}
                      <div className="space-y-1.5 rounded-lg border border-line/60 bg-surface-sunk/60 p-2.5 text-[11px] mb-3">
                        <div className="flex items-center justify-between text-ink-muted">
                          <span className="text-[10px] text-ink-faint font-semibold uppercase">Alpha</span>
                          <span className="font-mono text-ink font-medium truncate max-w-[170px]">
                            {spec.alpha_type || "—"}
                          </span>
                        </div>

                        <div className="flex items-center justify-between text-ink-muted">
                          <span className="text-[10px] text-ink-faint font-semibold uppercase">Universe</span>
                          <span className="font-mono text-ink font-medium truncate max-w-[170px]">
                            {spec.universe_type || "—"}
                          </span>
                        </div>

                        <div className="flex items-center justify-between text-ink-muted">
                          <span className="text-[10px] text-ink-faint font-semibold uppercase">Risk</span>
                          <span className="font-mono text-ink font-medium truncate max-w-[170px]">
                            {spec.risk_type || "—"}
                          </span>
                        </div>

                        {spec.screener_summary?.has_screener ? (
                          <div className="mt-1 pt-1 border-t border-line/40 flex items-center justify-between text-[10.5px] text-accent">
                            <span className="font-medium">🎯 Embedded Screener:</span>
                            <span className="font-mono">
                              {spec.screener_summary.rules_count} rules · Top {spec.screener_summary.limit_per_day || 50}
                            </span>
                          </div>
                        ) : null}
                      </div>
                    </div>

                    {/* Action Buttons */}
                    <div className="pt-2 border-t border-line/60 flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5">
                        <Button
                          type="button"
                          onClick={() => {
                            if (spec.algorithm_json) {
                              setInspectingJsonSpec(spec);
                            } else if (spec.ir_id && !spec.catalog_template_id) {
                              void fetchBacktestSpecDetail(spec.ir_id)
                                .then((detail) =>
                                  setInspectingJsonSpec(detail as unknown as BacktestSpecSummary),
                                )
                                .catch(() => setInspectingJsonSpec(spec));
                            } else {
                              setInspectingJsonSpec(spec);
                            }
                          }}
                          variant="outline"
                          className="rounded border border-line bg-surface-sunk px-2 py-1 text-[11px] font-medium text-ink hover:bg-surface hover:border-accent/40 transition-colors"
                          title="View JSON AST"
                        >
                          JSON
                        </Button>

                        <Button
                          type="button"
                          onClick={() => {
                            onDuplicateSpec(spec);
                            onClose();
                          }}
                          variant="outline"
                          className="rounded border border-line bg-surface-sunk px-2 py-1 text-[11px] font-medium text-ink hover:bg-surface hover:border-accent/40 transition-colors"
                          title="Clone a copy and open it"
                        >
                          Clone
                        </Button>

                        {!spec.catalog_template_id && (
                          <Button
                            type="button"
                            onClick={() => {
                              navigate(generateLocalePath(`backtests?ir_id=${encodeURIComponent(spec.ir_id)}`));
                              onClose();
                            }}
                            variant="outline"
                            className="rounded border border-line bg-surface-sunk px-2 py-1 text-[11px] font-medium text-ink hover:bg-surface hover:border-accent/40 transition-colors flex items-center gap-1"
                            title="Filter Backtest Runs on this Strategy Spec"
                          >
                            <span>📊</span> Runs
                          </Button>
                        )}
                      </div>

                      <Button
                        type="button"
                        onClick={() => {
                          onSelectSpec(spec);
                          onClose();
                        }}
                        variant="default"
                        className="rounded-lg bg-accent text-accent-fg px-3.5 py-1.5 text-xs font-semibold hover:opacity-90 shadow-sm transition-all"
                      >
                        Open
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </DialogContent>

      {/* JSON Inspector Slide-over / Modal */}
      {inspectingJsonSpec ? (
        <Dialog open onOpenChange={(open) => !open && setInspectingJsonSpec(null)}>
          <DialogContent size="lg" className="flex max-h-[88dvh] flex-col overflow-hidden p-0">
            <DialogHeader className="border-b px-4 py-3 sm:px-5">
              <DialogTitle className="break-all font-mono text-sm">
                {inspectingJsonSpec.title}
              </DialogTitle>
              <DialogDescription className="break-all font-mono text-xs">
                {inspectingJsonSpec.ir_id}
              </DialogDescription>
            </DialogHeader>

            <div className="min-h-0 flex-1 overflow-auto bg-muted/40 p-4 font-mono text-xs leading-relaxed">
              <pre className="whitespace-pre-wrap break-words">
                {inspectingJsonSpec.algorithm_json
                  ? JSON.stringify(JSON.parse(inspectingJsonSpec.algorithm_json), null, 2)
                  : "// No JSON payload stored for this spec"}
              </pre>
            </div>

            <DialogFooter className="flex-col-reverse items-stretch gap-2 border-t px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
              <CopyIdBadge
                id={inspectingJsonSpec.algorithm_json || ""}
                label="Copy Full Spec JSON"
                truncate={false}
              />
              <Button
                type="button"
                onClick={() => {
                  onSelectSpec(inspectingJsonSpec);
                  setInspectingJsonSpec(null);
                  onClose();
                }}
                variant="default"
                className="rounded-lg bg-accent text-accent-fg px-4 py-1.5 text-xs font-semibold hover:opacity-90"
              >
                📥 Load This Spec into Composer
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      ) : null}
    </Dialog>
  );
}
