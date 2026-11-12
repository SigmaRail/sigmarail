import { useMemo, useState, type ReactNode } from "react";
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
import { cn, swapIndex } from "../../lib/utils";

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
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={cn(
        "rounded border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide",
        active
          ? "border-accent/60 bg-accent/20 text-accent-ink"
          : "border-line text-ink-faint hover:bg-surface-sunk",
      )}
    >
      Insight{active ? " ✓" : ""}
    </button>
  );
}

/** Shared measure card chrome (gates + expression measures). */
function MeasureCard({ children }: { children: ReactNode }) {
  return (
    <div className="rounded border border-violet-500/30 bg-violet-500/5 p-2 space-y-1.5">
      {children}
    </div>
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
      <label className="flex items-center gap-1">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => {
            if (e.target.checked) {
              commit(setMeasureFilter(document, stageIndex, { op: "gte", value: 1 }));
            } else {
              commit(setMeasureFilter(document, stageIndex, null));
            }
          }}
        />
        Floor (post_where)
      </label>
      {enabled ? (
        <>
          <span className="font-mono text-ink-faint">{alias}</span>
          <select
            value={op}
            onChange={(e) =>
              commit(
                setMeasureFilter(document, stageIndex, {
                  op: e.target.value as typeof op,
                  value,
                }),
              )
            }
            className="rounded border border-line bg-surface px-1 py-0.5 font-mono text-[11px] text-ink"
          >
            <option value="gte">≥</option>
            <option value="gt">&gt;</option>
            <option value="lte">≤</option>
            <option value="lt">&lt;</option>
            <option value="eq">=</option>
            <option value="neq">≠</option>
          </select>
          <input
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
            className="w-16 rounded border border-line bg-surface px-1 py-0.5 font-mono text-[11px] text-ink"
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
      <div className="border-b border-line/60 pb-2">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted">
          Measures
        </span>
        <p className="mt-0.5 text-[10px] text-ink-faint leading-tight">
          Named SELECT columns (filter → 0/1, expr, or L7 field). Insight ✓ → WHERE / shortlist
          or ORDER BY (field measures required for L7 ties like rs_rating). Timing and setup
          belong here as bool measures — not Alpha entry_triggers. Bind Direction / Magnitude /
          Weight / Confidence on Insights.
        </p>
      </div>

      <div className="space-y-2">
        {rows.map((row, rowIndex) => {
          if (row.kind === "setup") {
            const { stage, stageIndex } = row;
            const alias = (stage.id || "").trim() || "setup_pass";
            const insightOn = isInsightActive(document, stage);
            return (
              <MeasureCard key={`setup-${stageIndex}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <input
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
                    className="w-36 rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-ink"
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
                  <button
                    type="button"
                    onClick={() => removeStageAt(stageIndex)}
                    className="text-[12px] text-ink-faint hover:text-danger"
                    title="Remove measure"
                  >
                    ✕
                  </button>
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
          const insightOn = Boolean(alias) && isInsightActive(document, stage);
          const isFieldCol =
            isExpr &&
            (stage.computed_expr as { type?: string } | null)?.type === "col";
          return (
            <MeasureCard key={`m-${stageIndex}`}>
              <div className="flex flex-wrap items-center gap-2">
                <input
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
                  className="w-36 rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-ink"
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
                    <button
                      type="button"
                      title="Toggle ASC/DESC"
                      onClick={() => commit(toggleRankDirection(document, alias))}
                      className="rounded border border-line px-1.5 py-0.5 font-mono text-[9px] text-ink-muted hover:bg-surface-sunk"
                    >
                      {rankDirection(document, alias).toUpperCase()}
                    </button>
                  </>
                ) : null}
                <ReorderButtons
                  className="ml-auto"
                  canUp={rowIndex > 0}
                  canDown={rowIndex < rows.length - 1}
                  onUp={() => moveMeasureRow(rowIndex, -1)}
                  onDown={() => moveMeasureRow(rowIndex, 1)}
                />
                <button
                  type="button"
                  onClick={() => removeStageAt(stageIndex)}
                  className="text-[12px] text-ink-faint hover:text-danger"
                  title="Remove measure"
                >
                  ✕
                </button>
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
            <button
              type="button"
              onClick={() => setAddOpen(true)}
              className="w-full rounded border border-dashed border-accent/50 bg-accent/5 py-1.5 text-[11px] font-semibold text-accent-ink hover:bg-accent/10"
            >
              + Add measure
            </button>
          ) : (
            <div className="rounded border border-accent/40 bg-surface p-2 space-y-1.5 shadow-sm">
              <div className="text-[10px] font-semibold text-ink-muted">Measure definition</div>
              <p className="text-[9px] text-ink-faint leading-tight">
                Filters → WHERE · Expr / Field / Shortlist sum → ORDER BY (Insight ✓ on)
              </p>
              <div className="flex flex-wrap gap-1.5">
                <button
                  type="button"
                  onClick={() => {
                    setAddOpen(false);
                    addFilterMeasure();
                  }}
                  className="flex-1 rounded border border-line bg-surface-raised px-2 py-1 text-[10px] font-semibold text-ink hover:bg-surface-sunk"
                >
                  Filters (WHERE)
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setAddOpen(false);
                    addExprMeasure();
                  }}
                  className="flex-1 rounded border border-line bg-surface-raised px-2 py-1 text-[10px] font-semibold text-ink hover:bg-surface-sunk"
                >
                  Expr (ORDER BY)
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setAddOpen(false);
                    addFieldMeasure();
                  }}
                  className="flex-1 rounded border border-line bg-surface-raised px-2 py-1 text-[10px] font-semibold text-ink hover:bg-surface-sunk"
                >
                  Field (ORDER BY)
                </button>
                <button
                  type="button"
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
                  className="flex-1 rounded border border-line bg-surface-raised px-2 py-1 text-[10px] font-semibold text-ink hover:bg-surface-sunk disabled:opacity-40 disabled:hover:bg-surface-raised"
                >
                  Shortlist sum (ORDER BY)
                </button>
                <button
                  type="button"
                  onClick={() => setAddOpen(false)}
                  className="rounded border border-line px-2 py-1 text-[10px] text-ink-faint hover:text-ink"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
