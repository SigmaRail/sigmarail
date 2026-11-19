import { useMemo, useState, type ReactNode } from "react";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Input } from "@sb/webapp-core/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@sb/webapp-core/components/ui/select";
import { Switch } from "@sb/webapp-core/components/ui/switch";
import { Card } from "@sb/webapp-core/components/ui/card";
import type { ScreenField } from "../../types";
import type { FilterTree, PipelineDocument, Stage } from "../strategy/StrategyDocument";
import { FilterTreeSlotEditor } from "./FilterTreeSlotEditor";
import { SlotNumberExprRow } from "./SlotNumberExprRow";
import {
  isInsightActive,
  measurePayloadKind,
  rankDirection,
  renameMeasureAlias,
  setMeasureFilter,
  toggleInsightMeasure,
  toggleRankDirection,
} from "../../lib/insightMeasureBindings";
import { countAsSignalAliases, sumColsExpr } from "../../lib/screensHitMeasure";
import { useFieldPicker } from "./FieldPickerProvider";
import { ReorderButtons } from "./ReorderButtons";
import { swapIndex } from "../../lib/utils";
import { summarizeMeasureExpression, summarizeMeasureFilters } from "../../lib/measureSummary";

type Props = {
  document: PipelineDocument;
  onChange: (doc: PipelineDocument) => void;
  fields: ScreenField[];
};

function patchStageAt(
  doc: PipelineDocument,
  index: number,
  patch: Partial<Stage>,
): PipelineDocument {
  return {
    ...doc,
    stages: doc.stages.map((s, i) => (i === index ? { ...s, ...patch } : s)),
  };
}

type Row =
  | { kind: "gate" | "setup"; stage: Stage; stageIndex: number }
  | { kind: "expr"; stage: Stage; stageIndex: number };

function InsightToggle({
  active,
  title,
  onClick,
}: {
  active: boolean;
  title: string;
  onClick: () => void;
}) {
  return (
    <Button
      type="button"
      variant={active ? "secondary" : "outline"}
      size="sm"
      title={title}
      onClick={onClick}
      className="h-7 px-2 text-[9px] font-semibold uppercase tracking-wide"
    >
      Insight{active ? " ✓" : ""}
    </Button>
  );
}

/** Compact AST summary stays visible while the full editor is collapsed. */
function MeasureCard({ alias, summary, children }: { alias: string; summary: string; children: ReactNode }) {
  return (
    <Card className="p-0 shadow-none">
      <details className="[&[open]>summary>span:first-child]:rotate-90">
        <summary className="flex min-h-10 cursor-pointer list-none items-center gap-2 px-3 py-2 marker:hidden [&::-webkit-details-marker]:hidden">
          <span aria-hidden="true" className="text-[10px] text-ink-faint transition-transform">▸</span>
          <code className="shrink-0 text-[10px] font-semibold text-ink">{alias}</code>
          <span className="min-w-0 flex-1 truncate text-[11px] text-ink-muted" title={summary || "No rule defined"}>
            {summary || "No rule defined"}
          </span>
        </summary>
        <div className="space-y-2 border-t border-line/60 p-2">
          {children}
        </div>
      </details>
    </Card>
  );
}

function MeasureFilterRow({
  alias,
  stage,
  stageIndex,
  document,
  commit,
}: {
  alias: string;
  stage: Stage;
  stageIndex: number;
  document: PipelineDocument;
  commit: (doc: PipelineDocument) => void;
}) {
  const mf = stage.measure_filter;
  const enabled = Boolean(mf);
  const op = (mf?.op as "gt" | "gte" | "lt" | "lte" | "eq" | "neq") || "gte";
  const rawRight = mf?.right;
  const value =
    typeof rawRight === "number"
      ? rawRight
      : typeof rawRight === "string" && rawRight !== "" && !Number.isNaN(Number(rawRight))
        ? Number(rawRight)
        : 0;

  return (
    <div className="flex flex-wrap items-center gap-2 text-[10px] text-ink-muted">
      <label className="flex items-center gap-2">
        <Switch
          checked={enabled}
          onCheckedChange={(checked) => {
            if (checked) {
              commit(setMeasureFilter(document, stageIndex, { op: "gte", value: 1 }));
            } else {
              commit(setMeasureFilter(document, stageIndex, null));
            }
          }}
          aria-label="Floor (post_where)"
        />
        Floor (post_where)
      </label>
      {enabled ? (
        <>
          <span className="font-mono text-ink-faint">{alias}</span>
          <Select
            value={op}
            onValueChange={(nextOp) =>
              commit(
                setMeasureFilter(document, stageIndex, {
                  op: nextOp as typeof op,
                  value,
                }),
              )
            }
          >
            <SelectTrigger className="h-7 w-16 px-1.5 py-0.5 font-mono text-[11px]"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="gte">≥</SelectItem>
              <SelectItem value="gt">&gt;</SelectItem>
              <SelectItem value="lte">≤</SelectItem>
              <SelectItem value="lt">&lt;</SelectItem>
              <SelectItem value="eq">=</SelectItem>
              <SelectItem value="neq">≠</SelectItem>
            </SelectContent>
          </Select>
          <Input
            type="number"
            value={value}
            onChange={(e) => {
              const n = parseFloat(e.target.value);
              commit(
                setMeasureFilter(document, stageIndex, {
                  op,
                  value: Number.isFinite(n) ? n : 0,
                }),
              );
            }}
            className="h-7 w-20 px-1.5 py-0.5 font-mono text-[11px]"
          />
        </>
      ) : null}
    </div>
  );
}

/** Measures: named SELECT columns; Insight ✓ → WHERE / ORDER BY. */
export function AlphaMeasuresPanel({ document, onChange, fields }: Props) {
  const { openPicker } = useFieldPicker();
  const [addOpen, setAddOpen] = useState(false);
  const stages = document.stages ?? [];
  const setupStage =
    stages.find(
      (s) =>
        s.mode === "signal" &&
        !s.computed_expr &&
        ((s.filters?.length ?? 0) > 0 || (s.id || "") === "setup_pass"),
    ) ?? null;

  const rows: Row[] = stages
    .map((stage, stageIndex): Row | null => {
      if (stage.mode === "score" && (Boolean(stage.as_gate) || Boolean(stage.computed_expr))) {
        return {
          kind: stage.computed_expr ? "expr" : "gate",
          stage,
          stageIndex,
        };
      }
      if (setupStage && stage === setupStage && stage.mode === "signal") {
        return { kind: "setup", stage, stageIndex };
      }
      return null;
    })
    .filter((r): r is Row => r !== null);

  const exprFields: ScreenField[] = useMemo(() => {
    const fromCatalog = fields.filter(
      (f) => f.origin === "computed" || f.origin === "l7" || f.type === "bool",
    );
    const seen = new Set(fromCatalog.map((f) => f.name));
    const extras: ScreenField[] = [];
    for (const s of stages) {
      const id = (s.id || "").trim();
      if (!id || seen.has(id)) continue;
      if (s.mode === "score" && (Boolean(s.as_gate) || Boolean(s.computed_expr))) {
        seen.add(id);
        extras.push({
          name: id,
          label: s.name || id,
          category: "measures",
          category_label: "Measures",
          type: s.computed_expr ? "number" : "bool",
          origin: "computed",
        });
      }
    }
    return [...fromCatalog, ...extras];
  }, [fields, stages]);

  function commit(doc: PipelineDocument) {
    // Expression payloads stay gates (as_gate) — coerce any legacy as_gate:false exprs.
    // Setup signal without id defaults to setup_pass (compiler / Insight ✓ contract).
    const stages = (doc.stages ?? []).map((s) => {
      let next = s;
      if (s.mode === "score" && s.computed_expr && !s.as_gate) {
        next = { ...next, as_gate: true };
      }
      if (
        next.mode === "signal" &&
        !(next.id || "").trim() &&
        ((next.filters?.length ?? 0) > 0 || (next.name || "").toLowerCase().includes("setup"))
      ) {
        next = { ...next, id: "setup_pass" };
      }
      return next;
    });
    onChange({ ...doc, stages });
  }

  function addFilterMeasure() {
    const n =
      stages.filter((s) => s.mode === "score" && (s.as_gate || s.computed_expr)).length + 1;
    const id = `measure_${n}`;
    const stage: Stage = {
      mode: "score",
      name: `Measure ${n}`,
      id,
      as_gate: true,
      filters: [],
      factors: [],
      selection: { method: "top_n", n: 10 },
    };
    commit({ ...document, stages: [...stages, stage] });
  }

  function addExprMeasure() {
    const n =
      stages.filter((s) => s.mode === "score" && (s.as_gate || s.computed_expr)).length + 1;
    const id = `measure_${n}`;
    const stage: Stage = {
      mode: "score",
      name: `Measure ${n}`,
      id,
      as_gate: true,
      computed_expr: { type: "lit", value: 0 },
      filters: [],
      factors: [],
    };
    const withStage = { ...document, stages: [...stages, stage] };
    // Number measures → ORDER BY when Insight ✓ is on.
    commit(toggleInsightMeasure(withStage, stage));
  }

  /** Authored Σ of count_as_signal gates — Insight ✓ → ORDER BY (not a reserved name). */
  function addShortlistSumMeasure() {
    const aliases = countAsSignalAliases(stages);
    if (aliases.length === 0) return;
    const used = new Set(
      stages.map((s) => (s.id || "").trim()).filter(Boolean),
    );
    let id = "hit_count";
    if (used.has(id)) {
      let n = 2;
      while (used.has(`hit_count_${n}`)) n += 1;
      id = `hit_count_${n}`;
    }
    const stage: Stage = {
      mode: "score",
      name: "Shortlist sum",
      id,
      as_gate: true,
      count_as_signal: false,
      computed_expr: sumColsExpr(aliases),
      filters: [],
      factors: [],
    };
    const withStage = { ...document, stages: [...stages, stage] };
    commit(toggleInsightMeasure(withStage, stage));
  }

  function addFieldMeasure() {
    openPicker({
      use: "column",
      fields,
      title: "Add field as Insight sort key",
      actionLabel: "Add field measure",
      mode: "fields",
      onPick: (pick) => {
        if (pick.kind !== "field") return;
        const name = pick.field.name.includes(".")
          ? pick.field.name.split(".").slice(1).join(".")
          : pick.field.name;
        if ((document.stages ?? []).some((s) => (s.id || "").trim() === name)) return;
        const stage: Stage = {
          mode: "score",
          name: pick.field.label || name,
          id: name,
          as_gate: true,
          computed_expr: { type: "col", name },
          filters: [],
          factors: [],
        };
        const withStage = { ...document, stages: [...(document.stages ?? []), stage] };
        commit(toggleInsightMeasure(withStage, stage));
      },
    });
  }

  function removeStageAt(index: number) {
    commit({ ...document, stages: stages.filter((_, i) => i !== index) });
  }

  /** Reorder among measure rows (swap stage slots so list order changes). */
  function moveMeasureRow(rowIndex: number, dir: -1 | 1) {
    const toRow = rowIndex + dir;
    if (toRow < 0 || toRow >= rows.length) return;
    const fromStage = rows[rowIndex]!.stageIndex;
    const toStage = rows[toRow]!.stageIndex;
    commit({
      ...document,
      stages: swapIndex(stages, fromStage, toStage),
    });
  }

  function setFilters(stageIndex: number, filters: FilterTree[]) {
    commit(patchStageAt(document, stageIndex, { filters, computed_expr: null, as_gate: true }));
  }

  return (
    <div className="space-y-3 rounded-lg border border-line bg-surface p-3">
      <h3 className="border-b border-line/60 pb-2 text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
        Measures
      </h3>

      <div className="space-y-2">
        {rows.map((row, rowIndex) => {
          if (row.kind === "setup") {
            const { stage, stageIndex } = row;
            const alias = (stage.id || "").trim() || "setup_pass";
            const summary = summarizeMeasureFilters(stage.filters, fields);
            const insightOn = isInsightActive(document, stage);
            return (
              <MeasureCard key={`setup-${stageIndex}`} alias={alias} summary={summary}>
                <div className="flex flex-wrap items-center gap-2">
                  <Input
                    type="text"
                    value={alias}
                    onChange={(e) =>
                      commit(
                        renameMeasureAlias(
                          document,
                          stageIndex,
                          e.target.value.trim() === "" ? "setup_pass" : e.target.value.trim(),
                        ),
                      )
                    }
                    placeholder="setup_pass"
                    className="h-7 w-36 px-1.5 py-0.5 font-mono text-[11px]"
                  />
                  <span className="font-mono text-[10px] text-ink-faint">:= setup</span>
                  <InsightToggle
                    active={insightOn}
                    title={`WHERE ${alias} (keep true)`}
                    onClick={() =>
                      commit(
                        toggleInsightMeasure(document, {
                          ...stage,
                          id: alias,
                        }),
                      )
                    }
                  />
                  {insightOn ? (
                    <span className="font-mono text-[9px] text-ink-faint">WHERE</span>
                  ) : null}
                  <ReorderButtons
                    className="ml-auto"
                    canUp={rowIndex > 0}
                    canDown={rowIndex < rows.length - 1}
                    onUp={() => moveMeasureRow(rowIndex, -1)}
                    onDown={() => moveMeasureRow(rowIndex, 1)}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => removeStageAt(stageIndex)}
                    className="h-7 w-7 px-1 text-[12px] text-ink-faint hover:text-danger"
                    title="Remove measure"
                  >
                    ✕
                  </Button>
                </div>
                <FilterTreeSlotEditor
                  filters={stage.filters}
                  fields={fields}
                  onChange={(next) => setFilters(stageIndex, next)}
                />
              </MeasureCard>
            );
          }

          const { stage, stageIndex } = row;
          const alias = (stage.id || "").trim();
          const isExpr = Boolean(stage.computed_expr);
          const payloadKind = measurePayloadKind(stage);
          const filterSummary = summarizeMeasureFilters(stage.filters, fields);
          const expressionSummary = summarizeMeasureExpression(stage.computed_expr, fields);
          const floorSummary = stage.measure_filter
            ? `; ${summarizeMeasureFilters([stage.measure_filter], fields)}`
            : "";
          const summary = `${isExpr ? expressionSummary : filterSummary}${floorSummary}`;
          const insightOn = Boolean(alias) && isInsightActive(document, stage);
          const isFieldCol =
            isExpr &&
            (stage.computed_expr as { type?: string } | null)?.type === "col";
          return (
            <MeasureCard key={`m-${stageIndex}`} alias={alias || "unnamed measure"} summary={summary}>
              <div className="flex flex-wrap items-center gap-2">
                <Input
                  type="text"
                  value={stage.id ?? ""}
                  onChange={(e) =>
                    commit(
                      renameMeasureAlias(
                        document,
                        stageIndex,
                        e.target.value === "" ? null : e.target.value,
                      ),
                    )
                  }
                  placeholder="alias"
                  className="h-7 w-36 px-1.5 py-0.5 font-mono text-[11px]"
                />
                <span className="font-mono text-[10px] text-ink-faint">
                  := {isFieldCol ? "field" : isExpr ? "expr" : "filters"}
                </span>
                {alias ? (
                  <InsightToggle
                    active={insightOn}
                    title={
                      payloadKind === "bool"
                        ? `WHERE ${alias} (keep true)`
                        : `ORDER BY ${alias}`
                    }
                    onClick={() => commit(toggleInsightMeasure(document, stage))}
                  />
                ) : null}
                {insightOn && payloadKind === "bool" ? (
                  <span className="font-mono text-[9px] text-ink-faint">WHERE</span>
                ) : null}
                {insightOn && payloadKind === "rank" ? (
                  <>
                    <span className="font-mono text-[9px] text-ink-faint">
                      ORDER #{(document.bindings?.alpha_rank ?? []).indexOf(alias) + 1}
                    </span>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      title="Toggle ASC/DESC"
                      onClick={() => commit(toggleRankDirection(document, alias))}
                      className="h-7 px-2 font-mono text-[9px]"
                    >
                      {rankDirection(document, alias).toUpperCase()}
                    </Button>
                  </>
                ) : null}
                <ReorderButtons
                  className="ml-auto"
                  canUp={rowIndex > 0}
                  canDown={rowIndex < rows.length - 1}
                  onUp={() => moveMeasureRow(rowIndex, -1)}
                  onDown={() => moveMeasureRow(rowIndex, 1)}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => removeStageAt(stageIndex)}
                  className="h-7 w-7 px-1 text-[12px] text-ink-faint hover:text-danger"
                  title="Remove measure"
                >
                  ✕
                </Button>
              </div>
              {!isExpr ? (
                <FilterTreeSlotEditor
                  filters={stage.filters}
                  fields={fields}
                  onChange={(next) => setFilters(stageIndex, next)}
                />
              ) : (
                <>
                  <SlotNumberExprRow
                    fields={exprFields.filter((f) => f.name !== alias)}
                    value={
                      stage.computed_expr
                        ? { kind: "number", expr: stage.computed_expr }
                        : null
                    }
                    onChange={(v) => {
                      if (v?.kind === "number" && v.expr) {
                        commit(
                          patchStageAt(document, stageIndex, {
                            as_gate: true,
                            computed_expr: v.expr as Record<string, unknown>,
                            filters: [],
                          }),
                        );
                        return;
                      }
                      commit(
                        patchStageAt(document, stageIndex, {
                          as_gate: true,
                          computed_expr: null,
                          filters: stage.filters?.length ? stage.filters : [],
                        }),
                      );
                    }}
                    placeholder={
                      isFieldCol
                        ? "field name (e.g. rs_rating)"
                        : "e.g. screen_1 + screen_2 + code_33"
                    }
                  />
                  {alias ? (
                    <MeasureFilterRow
                      alias={alias}
                      stage={stage}
                      stageIndex={stageIndex}
                      document={document}
                      commit={commit}
                    />
                  ) : null}
                </>
              )}
            </MeasureCard>
          );
        })}

        {rows.length === 0 ? (
          <p className="text-[10px] text-ink-faint italic">No measures yet.</p>
        ) : null}

        <div className="relative">
          {!addOpen ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setAddOpen(true)}
              className="h-8 w-full border-dashed border-accent/50 bg-accent/5 py-1.5 text-[11px] font-semibold text-accent-ink hover:bg-accent/10"
            >
              + Add measure
            </Button>
          ) : (
            <div className="rounded border border-accent/40 bg-surface p-2 space-y-1.5 shadow-sm">
              <div className="flex flex-wrap gap-1.5">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setAddOpen(false);
                    addFilterMeasure();
                  }}
                  className="h-8 flex-1 px-2 py-1 text-[10px] font-semibold"
                >
                  Filters (WHERE)
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setAddOpen(false);
                    addExprMeasure();
                  }}
                  className="h-8 flex-1 px-2 py-1 text-[10px] font-semibold"
                >
                  Expr (ORDER BY)
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setAddOpen(false);
                    addFieldMeasure();
                  }}
                  className="h-8 flex-1 px-2 py-1 text-[10px] font-semibold"
                >
                  Field (ORDER BY)
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={countAsSignalAliases(stages).length === 0}
                  title={
                    countAsSignalAliases(stages).length === 0
                      ? "Need at least one shortlist (count_as_signal) filter measure"
                      : "Σ of shortlist gates → ORDER BY"
                  }
                  onClick={() => {
                    setAddOpen(false);
                    addShortlistSumMeasure();
                  }}
                  className="h-8 flex-1 px-2 py-1 text-[10px] font-semibold"
                >
                  Shortlist sum (ORDER BY)
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setAddOpen(false)}
                  className="h-8 px-2 py-1 text-[10px] text-ink-faint hover:text-ink"
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
