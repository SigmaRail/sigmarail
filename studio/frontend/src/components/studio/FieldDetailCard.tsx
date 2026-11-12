import React, { useState, useEffect, useMemo } from "react";
import { cn } from "../../lib/utils";
import type { ScreenField, FieldLineageResponse } from "../../types";
import MathFormulaCard from "../common/MathFormulaCard";
import FieldEvaluatorDrawer from "./FieldEvaluatorDrawer";

/** Shared field-info content card with LaTeX math, caveats, and live evaluator. */
export function FieldDetailCard({
  field,
  className,
}: {
  field: ScreenField | null;
  className?: string;
}) {
  const [activeTab, setActiveTab] = useState<"formula" | "example" | "lineage">("formula");
  const [lineageData, setLineageData] = useState<FieldLineageResponse | null>(null);
  const [, setLoadingLineage] = useState(false);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);

  useEffect(() => {
    setSelectedStepId(null);
    if (!field) {
      setLineageData(null);
      return;
    }
    let isMounted = true;
    setLoadingLineage(true);
    const tbl = field.table || "";
    fetch(`/api/screens/fields/${encodeURIComponent(field.name)}/lineage?table=${encodeURIComponent(tbl)}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data: FieldLineageResponse | null) => {
        if (isMounted) setLineageData(data);
      })
      .catch(() => {
        if (isMounted) setLineageData(null);
      })
      .finally(() => {
        if (isMounted) setLoadingLineage(false);
      });
    return () => {
      isMounted = false;
    };
  }, [field?.name, field?.table]);

  const caveats = lineageData?.caveats || field?.caveats || [];
  const math = lineageData?.math || field?.math;
  const edges = lineageData?.graph?.edges || [];
  const nodes = lineageData?.graph?.nodes || [];

  // Build breadcrumb lineage path from edges
  const lineageChain: string[] = [];
  if (field?.table) lineageChain.push(field.table.replace("screener_", ""));
  edges.forEach((e: any) => {
    const targetTbl = e.to.split(".")[0];
    if (targetTbl && !lineageChain.includes(targetTbl)) {
      lineageChain.push(targetTbl);
    }
  });

  // useMemo must be called unconditionally before early returns
  const selectedNode = useMemo(() => {
    if (!selectedStepId) return null;
    return nodes.find(
      (n: any) =>
        n.table === selectedStepId ||
        n.table?.replace("screener_", "") === selectedStepId
    );
  }, [nodes, selectedStepId]);

  if (!field) return null;

  return (
    <div className={cn("w-80 text-xs flex flex-col max-h-[600px] overflow-hidden", className)}>
      {/* Header */}
      <div className="flex items-start justify-between gap-2 border-b border-line px-3 py-2 flex-shrink-0 bg-surface">
        <div className="min-w-0">
          <h4 className="truncate text-[12px] font-bold text-ink">{field.label}</h4>
          <p className="truncate font-mono text-[10px] text-ink-muted">
            {field.prefixed_name || (field.prefix ? `${field.prefix}.${field.name}` : field.sql_expr || field.name)}
          </p>
        </div>
        <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded bg-accent/15 text-accent text-[10px] font-bold">
          S
        </span>
      </div>

      {/* Category & type pills */}
      <div className="flex flex-wrap items-center gap-1 px-3 pt-2 flex-shrink-0">
        {field.category_label || field.category ? (
          <span className="rounded-full bg-accent/10 border border-accent/25 px-1.5 py-0.5 text-[9.5px] font-semibold text-accent">
            {field.category_label || field.category}
          </span>
        ) : null}
        {field.type ? (
          <span className="rounded-full bg-surface-sunk border border-line px-1.5 py-0.5 font-mono text-[9.5px] text-ink-muted">
            {field.type}
          </span>
        ) : null}
        {field.table ? (
          <span
            className="truncate rounded-full bg-surface-sunk border border-line px-1.5 py-0.5 font-mono text-[9px] text-ink-muted max-w-[140px]"
            title={field.table}
          >
            {field.table.replace("screener_", "")}
          </span>
        ) : null}
      </div>

      {/* Limitations / Caveats Badges */}
      {caveats.length > 0 && (
        <div className="px-3 pt-2 space-y-1 flex-shrink-0">
          <div className="flex flex-wrap gap-1">
            {caveats.map((c: any, i: number) => {
              const isWarning = c.severity === "warning" || c.severity === "caution";
              return (
                <div
                  key={i}
                  title={c.description}
                  className={cn(
                    "flex items-center gap-1 rounded px-1.5 py-0.5 text-[9px] font-medium border",
                    isWarning
                      ? "border-amber-500/30 bg-amber-500/10 text-amber-300"
                      : "border-line bg-surface-sunk text-ink-muted"
                  )}
                >
                  <span>{isWarning ? "!" : "i"}</span>
                  <span className="truncate max-w-[200px]">{c.title}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-line px-3 pt-2.5 flex-shrink-0 gap-3 text-[10.5px]">
        <button
          type="button"
          onClick={() => setActiveTab("formula")}
          className={cn(
            "pb-1 border-b-2 font-medium transition-colors",
            activeTab === "formula" ? "border-accent text-accent font-bold" : "border-transparent text-ink-muted hover:text-ink"
          )}
        >
          Formula
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("example")}
          className={cn(
            "pb-1 border-b-2 font-medium transition-colors",
            activeTab === "example" ? "border-accent text-accent font-bold" : "border-transparent text-ink-muted hover:text-ink"
          )}
        >
          Live Example
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("lineage")}
          className={cn(
            "pb-1 border-b-2 font-medium transition-colors",
            activeTab === "lineage" ? "border-accent text-accent font-bold" : "border-transparent text-ink-muted hover:text-ink"
          )}
        >
          Lineage Chain
        </button>
      </div>

      {/* Content Body */}
      <div className="overflow-y-auto p-3 space-y-2.5 flex-1">
        {activeTab === "formula" && (
          <div className="space-y-2.5">
            {/* KaTeX Formula */}
            {math && <MathFormulaCard math={math} />}

            {/* Description */}
            <div className="space-y-1">
              <label className="text-[9px] font-bold uppercase tracking-wider text-ink-muted">
                Definition
              </label>
              <p className="rounded-lg border border-line bg-surface p-2 text-[10.5px] leading-relaxed text-ink">
                {field.description || "Database screener metric available for universe filtering and sorting."}
              </p>
            </div>

            {/* AST projection mapping */}
            <div className="space-y-1">
              <label className="text-[9px] font-bold uppercase tracking-wider text-ink-muted">
                Projection Mapping
              </label>
              <div className="space-y-0.5 rounded border border-line bg-surface-sunk p-2 font-mono text-[9.5px] text-ink-muted">
                <div className="flex justify-between gap-2">
                  <span className="text-ink-muted/70">Column:</span>
                  <span className="font-semibold text-ink">{field.name}</span>
                </div>
                {field.table && (
                  <div className="flex justify-between gap-2">
                    <span className="text-ink-muted/70">Table:</span>
                    <span className="truncate text-ink">{field.table}</span>
                  </div>
                )}
                {field.sql_expr && (
                  <div className="flex justify-between gap-2">
                    <span className="text-ink-muted/70">Expr:</span>
                    <span className="truncate font-semibold text-accent">{field.sql_expr}</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === "example" && (
          <FieldEvaluatorDrawer fieldName={field.name} table={field.table} />
        )}

        {activeTab === "lineage" && (
          <div className="space-y-2 text-[10.5px]">
            <label className="text-[9px] font-bold uppercase tracking-wider text-ink-muted">
              Source Transformation Path
            </label>
            {lineageChain.length > 0 ? (
              <div className="space-y-1.5 rounded-lg border border-line bg-surface p-2.5">
                <div className="flex flex-wrap items-center gap-1.5 font-mono text-[10px]">
                  {lineageChain.map((step, idx) => {
                    const isSelected = selectedStepId === step;
                    return (
                      <React.Fragment key={idx}>
                        <button
                          type="button"
                          onClick={() => setSelectedStepId(isSelected ? null : step)}
                          className={cn(
                            "flex items-center gap-1.5 rounded px-1.5 py-0.5 transition-all text-left border",
                            isSelected
                              ? "bg-accent text-white font-bold border-accent shadow-sm"
                              : "bg-surface-sunk border-line hover:border-accent/40 text-ink"
                          )}
                          title={`Click to inspect transform step ${idx + 1}: ${step}`}
                        >
                          <span
                            className={cn(
                              "flex h-3.5 w-3.5 items-center justify-center rounded text-[8.5px] font-bold",
                              isSelected ? "bg-white/20 text-white" : "bg-accent/15 text-accent"
                            )}
                          >
                            {idx + 1}
                          </span>
                          <span>{step}</span>
                        </button>
                        {idx < lineageChain.length - 1 && (
                          <span className="text-ink-muted/50 text-[9px]">-</span>
                        )}
                      </React.Fragment>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="rounded border border-line bg-surface p-2 text-ink-muted">
                Direct table column; no multi-table transform chain.
              </div>
            )}

            {/* Upstream Step Inspection Drawer */}
            {selectedNode && (
              <div className="rounded-lg border border-accent/40 bg-surface p-2.5 space-y-2 animate-in fade-in duration-150">
                <div className="flex items-center justify-between border-b border-line pb-1.5">
                  <div className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full bg-accent" />
                    <span className="font-bold text-ink text-[10.5px] font-mono">
                      {selectedNode.table}.{selectedNode.column}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelectedStepId(null)}
                    className="text-ink-muted hover:text-ink text-[11px] px-1 rounded hover:bg-surface-sunk"
                  >
                    x
                  </button>
                </div>

                {selectedNode.lineage?.expression && (
                  <div className="space-y-1">
                    <span className="text-[9px] font-bold uppercase tracking-wider text-ink-muted">
                      Transform SQL Expression
                    </span>
                    <pre className="rounded bg-surface-sunk p-2 font-mono text-[9px] text-accent overflow-x-auto whitespace-pre-wrap break-all border border-line/60">
                      {selectedNode.lineage.expression}
                    </pre>
                  </div>
                )}

                {selectedNode.math && (
                  <MathFormulaCard
                    math={selectedNode.math}
                    title="Step Equation"
                    className="border-line/60"
                  />
                )}

                {selectedNode.caveats && selectedNode.caveats.length > 0 && (
                  <div className="space-y-1">
                    <span className="text-[9px] font-bold uppercase tracking-wider text-ink-muted">
                      Step Caveats
                    </span>
                    <div className="space-y-1">
                      {selectedNode.caveats.map((c: any, i: number) => (
                        <div key={i} className="text-[9.5px] text-ink-muted bg-surface-sunk p-1.5 rounded border border-line/40">
                          <span className="font-semibold text-ink">{c.title}:</span> {c.description}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Detailed Caveats list */}
            {caveats.length > 0 && (
              <div className="space-y-1 pt-1">
                <label className="text-[9px] font-bold uppercase tracking-wider text-ink-muted">
                  Detected Quantitative Caveats
                </label>
                <div className="space-y-1.5">
                  {caveats.map((c: any, idx: number) => (
                    <div
                      key={idx}
                      className="rounded border border-line bg-surface p-2 text-[10px] space-y-0.5"
                    >
                      <div className="font-semibold text-ink flex items-center gap-1.5">
                        <span>{c.severity === "warning" ? "!" : "i"}</span>
                        <span>{c.title}</span>
                      </div>
                      <p className="text-ink-muted leading-relaxed">{c.description}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default FieldDetailCard;
