import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchBacktestSpecDetail, fetchBacktestSpecs } from "../../api/backtests";
import { fetchCatalogTemplates } from "../../api/strategy";
import type { BacktestSpecSummary } from "../../types";
import { CopyIdBadge } from "../CopyIdBadge";

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
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [schemaFilter, setSchemaFilter] = useState<"all" | "modern" | "legacy">("all");
  const [alphaFilter, setAlphaFilter] = useState<string>("all");
  const [inspectingJsonSpec, setInspectingJsonSpec] = useState<BacktestSpecSummary | null>(null);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (inspectingJsonSpec) {
          setInspectingJsonSpec(null);
        } else {
          onClose();
        }
      }
    };
    if (isOpen) {
      window.addEventListener("keydown", handleKeyDown);
      return () => window.removeEventListener("keydown", handleKeyDown);
    }
  }, [isOpen, inspectingJsonSpec, onClose]);

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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="flex h-[92vh] w-full max-w-6xl flex-col rounded-xl border border-line bg-surface shadow-2xl overflow-hidden">
        {/* Modal Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-surface-raised px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent/15 border border-accent/30 text-accent font-bold">
              📚
            </div>
            <div>
              <h2 className="text-base font-bold text-ink flex items-center gap-2">
                Strategy Spec & Template Library
                <span className="rounded-full bg-surface-sunk border border-line px-2 py-0.5 text-[10px] font-mono text-ink-muted">
                  {filteredSpecs.length} / {allSpecs.length}
                </span>
              </h2>
              <p className="text-[11.5px] text-ink-muted">
                Open a Strategy or Template in compose, or Clone a copy. Template is a filter tag.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-line bg-surface-sunk px-3 py-1.5 text-xs font-semibold text-ink hover:bg-surface-raised hover:border-accent/40 transition-colors"
            >
              Close (Esc)
            </button>
          </div>
        </div>

        {/* Filter & Search Bar */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line/60 bg-surface-sunk/60 px-6 py-3">
          {/* Category Tabs & Schema Filter */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex flex-wrap items-center gap-1.5">
              <button
                type="button"
                onClick={() => setSelectedCategory("all")}
                className={`rounded-md px-3 py-1 text-xs font-medium transition-all ${
                  selectedCategory === "all"
                    ? "bg-accent text-accent-fg shadow-sm font-semibold"
                    : "bg-surface-raised border border-line text-ink-muted hover:text-ink hover:border-accent/30"
                }`}
              >
                All ({counts.total})
              </button>

              <button
                type="button"
                onClick={() => setSelectedCategory("strategies")}
                className={`rounded-md px-3 py-1 text-xs font-medium transition-all ${
                  selectedCategory === "strategies"
                    ? "bg-accent text-accent-fg shadow-sm font-semibold"
                    : "bg-surface-raised border border-line text-ink-muted hover:text-ink hover:border-accent/30"
                }`}
              >
                Strategies ({counts.strategies})
              </button>

              <button
                type="button"
                onClick={() => setSelectedCategory("templates")}
                className={`rounded-md px-3 py-1 text-xs font-medium transition-all ${
                  selectedCategory === "templates"
                    ? "bg-accent text-accent-fg shadow-sm font-semibold"
                    : "bg-surface-raised border border-line text-ink-muted hover:text-ink hover:border-accent/30"
                }`}
              >
                Templates ({counts.templates})
              </button>

              <button
                type="button"
                onClick={() => setSelectedCategory("catalog")}
                className={`rounded-md px-3 py-1 text-xs font-medium transition-all ${
                  selectedCategory === "catalog"
                    ? "bg-accent text-accent-fg shadow-sm font-semibold"
                    : "bg-surface-raised border border-line text-ink-muted hover:text-ink hover:border-accent/30"
                }`}
              >
                Catalog ({counts.catalog})
              </button>
            </div>

            <div className="h-4 w-px bg-line/80 mx-1 hidden sm:block" />

            <div className="flex items-center gap-1 rounded-md border border-line bg-surface p-0.5 text-xs">
              <button
                type="button"
                onClick={() => setSchemaFilter("all")}
                className={`rounded px-2 py-0.5 text-[11px] font-medium transition-colors ${
                  schemaFilter === "all"
                    ? "bg-accent text-accent-fg font-semibold shadow-xs"
                    : "text-ink-muted hover:text-ink"
                }`}
              >
                All Schemas
              </button>
              <button
                type="button"
                onClick={() => setSchemaFilter("modern")}
                className={`rounded px-2 py-0.5 text-[11px] font-medium flex items-center gap-1.5 transition-colors ${
                  schemaFilter === "modern"
                    ? "bg-accent text-accent-fg font-semibold shadow-xs"
                    : "text-ink-muted hover:text-ink"
                }`}
                title="Specs with modern multi-stage pipeline documents"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                Modern ({counts.modern})
              </button>
              <button
                type="button"
                onClick={() => setSchemaFilter("legacy")}
                className={`rounded px-2 py-0.5 text-[11px] font-medium flex items-center gap-1.5 transition-colors ${
                  schemaFilter === "legacy"
                    ? "bg-accent text-accent-fg font-semibold shadow-xs"
                    : "text-ink-muted hover:text-ink"
                }`}
                title="Legacy AST specs (upgradeable via pipeline decompiler)"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                Legacy ({counts.legacy})
              </button>
            </div>
          </div>

          {/* Search & Alpha Dropdown */}
          <div className="flex items-center gap-2.5 flex-1 min-w-[280px] max-w-md">
            <div className="relative flex-1">
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search title, ir_id, models, symbols…"
                className="w-full rounded-md border border-line bg-surface px-3 py-1.5 pl-8 text-xs font-mono text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none"
              />
              <span className="absolute left-2.5 top-1.5 text-xs text-ink-faint">🔍</span>
              {searchTerm ? (
                <button
                  type="button"
                  onClick={() => setSearchTerm("")}
                  className="absolute right-2 top-1.5 text-xs text-ink-muted hover:text-ink"
                >
                  ✕
                </button>
              ) : null}
            </div>

            <select
              value={alphaFilter}
              onChange={(e) => setAlphaFilter(e.target.value)}
              className="rounded-md border border-line bg-surface px-2.5 py-1.5 text-xs text-ink focus:border-accent focus:outline-none"
            >
              <option value="all">All Alpha Models ({alphaModels.length})</option>
              {alphaModels.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Spec Grid / Card List */}
        <div className="flex-1 overflow-y-auto p-6 bg-surface/50">
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
                <button
                  type="button"
                  onClick={() => {
                    setSearchTerm("");
                    setSelectedCategory("all");
                    setAlphaFilter("all");
                  }}
                  className="rounded-md border border-line bg-surface px-3 py-1.5 text-xs font-semibold text-ink hover:bg-surface-raised"
                >
                  Reset Filters
                </button>
              ) : null}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
              {filteredSpecs.map((spec) => {
                return (
                  <div
                    key={spec.ir_id}
                    className="flex flex-col justify-between rounded-xl border border-line bg-surface-raised/80 hover:border-accent/50 hover:shadow-lg transition-all p-4.5 group"
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
                        <button
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
                          className="rounded border border-line bg-surface-sunk px-2 py-1 text-[11px] font-medium text-ink hover:bg-surface hover:border-accent/40 transition-colors"
                          title="View JSON AST"
                        >
                          JSON
                        </button>

                        <button
                          type="button"
                          onClick={() => {
                            onDuplicateSpec(spec);
                            onClose();
                          }}
                          className="rounded border border-line bg-surface-sunk px-2 py-1 text-[11px] font-medium text-ink hover:bg-surface hover:border-accent/40 transition-colors"
                          title="Clone a copy and open it"
                        >
                          Clone
                        </button>

                        {!spec.catalog_template_id && (
                          <button
                            type="button"
                            onClick={() => {
                              navigate(`/backtests?ir_id=${encodeURIComponent(spec.ir_id)}`);
                              onClose();
                            }}
                            className="rounded border border-line bg-surface-sunk px-2 py-1 text-[11px] font-medium text-ink hover:bg-surface hover:border-accent/40 transition-colors flex items-center gap-1"
                            title="Filter Backtest Runs on this Strategy Spec"
                          >
                            <span>📊</span> Runs
                          </button>
                        )}
                      </div>

                      <button
                        type="button"
                        onClick={() => {
                          onSelectSpec(spec);
                          onClose();
                        }}
                        className="rounded-lg bg-accent text-accent-fg px-3.5 py-1.5 text-xs font-semibold hover:opacity-90 shadow-sm transition-all"
                      >
                        Open
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* JSON Inspector Slide-over / Modal */}
      {inspectingJsonSpec ? (
        <div className="fixed inset-0 z-60 flex items-center justify-center bg-black/80 p-4 backdrop-blur-md">
          <div className="flex h-[85vh] w-full max-w-3xl flex-col rounded-xl border border-line bg-surface shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between border-b border-line bg-surface-raised px-5 py-3.5">
              <div>
                <h3 className="font-mono text-sm font-bold text-ink flex items-center gap-2">
                  <span>📄 {inspectingJsonSpec.title}</span>
                  <span className="text-xs text-ink-muted">({inspectingJsonSpec.ir_id})</span>
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setInspectingJsonSpec(null)}
                className="rounded border border-line bg-surface-sunk px-2.5 py-1 text-xs font-semibold text-ink hover:bg-surface-raised"
              >
                ✕ Close
              </button>
            </div>

            <div className="flex-1 overflow-auto p-4 bg-surface-sunk font-mono text-[11.5px] leading-relaxed text-ink">
              <pre className="whitespace-pre-wrap break-words">
                {inspectingJsonSpec.algorithm_json
                  ? JSON.stringify(JSON.parse(inspectingJsonSpec.algorithm_json), null, 2)
                  : "// No JSON payload stored for this spec"}
              </pre>
            </div>

            <div className="flex items-center justify-between border-t border-line bg-surface-raised px-5 py-3">
              <CopyIdBadge
                id={inspectingJsonSpec.algorithm_json || ""}
                label="Copy Full Spec JSON"
                truncate={false}
              />
              <button
                type="button"
                onClick={() => {
                  onSelectSpec(inspectingJsonSpec);
                  setInspectingJsonSpec(null);
                  onClose();
                }}
                className="rounded-lg bg-accent text-accent-fg px-4 py-1.5 text-xs font-semibold hover:opacity-90"
              >
                📥 Load This Spec into Composer
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
