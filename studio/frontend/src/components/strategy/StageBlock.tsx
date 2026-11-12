import { useState } from "react";
import type { IrOperand, ScreenField } from "../../types";
import { formatOperandToString, parseArithmeticTokens, tokenize } from "../../lib/formulaParser";
import { FilterTreeSlotEditor } from "../studio/FilterTreeSlotEditor";
import type {
  EntryTriggerType,
  FilterGroup,
  FilterNode,
  FilterTree,
  Stage,
  StageMode,
} from "./StrategyDocument";
import { isFilterNot } from "./StrategyDocument";

export const STAGE_MODE_LABELS: Record<StageMode, string> = {
  filter: "Filter",
  score: "Score",
  signal: "Signal",
  confirm: "Confirm",
  watch: "Watch",
  pyramid: "Pyramid",
  hedge: "Hedge",
  exit: "Exit",
};

export const STAGE_MODE_COLORS: Record<StageMode, string> = {
  filter: "border-sky-500/50 bg-sky-500/5 text-sky-300",
  score: "border-violet-500/50 bg-violet-500/5 text-violet-300",
  signal: "border-amber-500/50 bg-amber-500/5 text-amber-300",
  confirm: "border-indigo-500/50 bg-indigo-500/5 text-indigo-300",
  watch: "border-teal-500/50 bg-teal-500/5 text-teal-300",
  pyramid: "border-emerald-500/50 bg-emerald-500/5 text-emerald-300",
  hedge: "border-rose-500/50 bg-rose-500/5 text-rose-300",
  exit: "border-orange-500/50 bg-orange-500/5 text-orange-300",
};

export const STAGE_MODE_DESCRIPTIONS: Record<StageMode, string> = {
  filter: "Legacy Alpha filter — Trend Template belongs on Universe",
  score: "Boolean gate (where) and/or rank by weighted factors",
  signal: "Entry setup AST (setup_where) — gates Insights, not membership",
  confirm: "Meta-labeling secondary gate over entry signals",
  watch: "Build a watchlist without auto-entering",
  pyramid: "Scale positions in progressively",
  hedge: "Deploy inverse ETFs in risk-off regimes",
  exit: "Take profits in tranches + trail stops",
};

const FILTER_OPS = ["gt", "gte", "lt", "lte", "eq", "neq"] as const;
type FilterOp = (typeof FILTER_OPS)[number];

const OP_DISPLAY: Record<FilterOp, string> = {
  gt: ">",
  gte: ">=",
  lt: "<",
  lte: "<=",
  eq: "=",
  neq: "≠",
};

const isIrOperand = (value: unknown): value is IrOperand => {
  if (!value || typeof value !== "object") return false;
  const type = (value as { type?: unknown }).type;
  return type === "col" || type === "lit" || type === "formula";
};

const operandToText = (operand: string | IrOperand): string => {
  if (typeof operand === "string") return operand;
  if (operand.type === "col") return operand.name;
  if (operand.type === "lit") return String(operand.value);
  return formatOperandToString(operand);
};

const parseOperandExpression = (raw: string): IrOperand | null => {
  const { operand, error } = parseArithmeticTokens(tokenize(raw));
  return error || !operand ? null : operand;
};

interface FilterEditorProps {
  tree: FilterTree;
  fields: ScreenField[];
  onChange: (tree: FilterTree) => void;
  onDelete?: () => void;
  depth?: number;
}

function FilterNodeEditor({
  node,
  fields,
  onChange,
  onDelete,
}: {
  node: FilterNode;
  fields: ScreenField[];
  onChange: (n: FilterNode) => void;
  onDelete?: () => void;
}) {
  if ("logic" in node) {
    return <FilterGroupEditor group={node} fields={fields} onChange={onChange} onDelete={onDelete} />;
  }
  if (isFilterNot(node)) {
    // A negated subtree has no comparison row: render a NOT box around its child instead of
    // reading `.left` off a node that has no operands.
    return (
      <div className="rounded border border-rose-500/40 bg-rose-500/5 p-1">
        <div className="flex items-center justify-between px-1">
          <span className="text-[9.5px] font-bold uppercase tracking-wide text-rose-300">NOT</span>
          <button type="button" onClick={onDelete} className="text-[10px] text-danger" title="Remove">
            ×
          </button>
        </div>
        <FilterNodeEditor node={node.item} fields={fields} onChange={(item) => onChange({ item })} onDelete={onDelete} />
      </div>
    );
  }

  const fieldNames = fields.map((f) => f.name);
  const availableFields = fieldNames.length > 0;
  const leftText = typeof node.left === "string" ? node.left : operandToText(node.left);
  const rightKind = node.right_kind ?? (isIrOperand(node.right) ? node.right.type : "lit");
  const rightText =
    typeof node.right === "string"
      ? node.right
      : isIrOperand(node.right)
        ? operandToText(node.right)
        : String(node.right ?? "");
  const formulaText = rightKind === "formula"
    ? node.expr ?? rightText
    : rightText;

  return (
    <div className="flex flex-wrap items-center gap-1 font-mono text-[11px]">
      <select
        value={leftText}
        onChange={(e) => onChange({ ...node, left: e.target.value })}
        className="rounded border border-line bg-surface-sunk px-1 py-0.5 text-[11px] text-ink"
        title="Left operand"
      >
        {availableFields ? (
          <>
            <option value="">Select field…</option>
            {fieldNames.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
            {!fieldNames.includes(leftText) && leftText && (
              <option value={leftText}>{leftText}</option>
            )}
          </>
        ) : (
          <option value={leftText}>{leftText}</option>
        )}
      </select>

      <select
        value={node.op}
          onChange={(e) =>
          onChange({ ...node, op: e.target.value as FilterOp })
        }
        className="rounded border border-line bg-surface-sunk px-1 py-0.5 text-[11px] text-ink"
        title="Operator"
      >
        {FILTER_OPS.map((op) => (
          <option key={op} value={op}>
            {OP_DISPLAY[op]}
          </option>
        ))}
      </select>

      <input
        type="text"
        value={rightKind === "formula" ? formulaText : rightText}
        onChange={(e) => {
          const raw = e.target.value;
          if (rightKind === "col") {
            onChange({ ...node, right: raw, right_kind: "col", expr: undefined });
            return;
          }
          if (rightKind === "formula") {
            const operand = parseOperandExpression(raw);
            if (operand) {
              onChange({ ...node, right: operand, right_kind: "formula", expr: raw });
            } else {
              onChange({ ...node, expr: raw || undefined });
            }
            return;
          }
          let val: number | string | boolean = raw;
          if (raw === "true") val = true;
          else if (raw === "false") val = false;
          else if (!isNaN(Number(raw)) && raw !== "") val = Number(raw);
          onChange({ ...node, right: val, right_kind: "lit", expr: undefined });
        }}
        placeholder={rightKind === "formula" ? "e.g. high_52w * 0.75" : "value"}
        className={rightKind === "formula" ? "w-48" : "w-24"}
        title={rightKind === "formula" ? "Right operand formula" : "Right operand"}
      />

      <select
        value={rightKind}
        onChange={(e) =>
          onChange({
            ...node,
            right_kind: e.target.value as "lit" | "col" | "formula",
          })
        }
        className="rounded border border-line bg-surface-sunk px-1 py-0.5 text-[10px] text-ink"
        title="Right operand kind"
      >
        <option value="lit">lit</option>
        <option value="col">col</option>
        <option value="formula">formula</option>
      </select>

      {onDelete && (
        <button
          type="button"
          onClick={onDelete}
          className="rounded border border-line px-1.5 text-[10px] hover:bg-danger/10 text-danger"
          title="Remove condition"
        >
          ✕
        </button>
      )}
    </div>
  );
}

function FilterGroupEditor({
  group,
  fields,
  onChange,
  onDelete,
  depth = 0,
}: {
  group: FilterGroup;
  fields: ScreenField[];
  onChange: (g: FilterGroup) => void;
  onDelete?: () => void;
  depth?: number;
}) {
  const indent = depth > 0 ? "ml-4 border-l border-line pl-2" : "";

  return (
    <div className={`space-y-1 ${indent}`}>
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => onChange({ ...group, logic: group.logic === "and" ? "or" : "and" })}
          className={`rounded px-2 py-0.5 text-[10px] font-bold uppercase ${
            group.logic === "and"
              ? "bg-sky-500/20 text-sky-300"
              : "bg-amber-500/20 text-amber-300"
          }`}
          title="Toggle AND/OR"
        >
          {group.logic.toUpperCase()}
        </button>

        <button
          type="button"
          onClick={() =>
            onChange({
              ...group,
              conditions: [
                ...group.conditions,
                { op: "gte", left: "", right: "", right_kind: "lit" },
              ],
            })
          }
          className="rounded border border-line px-1.5 py-0.5 text-[10px] hover:bg-surface-sunk"
        >
          + Condition
        </button>

        <button
          type="button"
          onClick={() =>
            onChange({
              ...group,
              conditions: [
                ...group.conditions,
                {
                  logic: group.logic === "and" ? "or" : "and",
                  conditions: [{ op: "gte", left: "", right: "", right_kind: "lit" }],
                },
              ],
            })
          }
          className="rounded border border-line px-1.5 py-0.5 text-[10px] hover:bg-surface-sunk"
        >
          + Group
        </button>

        {onDelete && (
          <button
            type="button"
            onClick={onDelete}
            className="rounded border border-line px-1.5 text-[10px] hover:bg-danger/10 text-danger"
          >
            ✕
          </button>
        )}
      </div>

      <div className={`space-y-1 ${indent}`}>
        {group.conditions.map((item, i) => (
          <FilterTreeEditor
            key={i}
            tree={item}
            fields={fields}
            onChange={(updated) => {
              const next = [...group.conditions];
              next[i] = updated;
              onChange({ ...group, conditions: next });
            }}
            onDelete={() => {
              const next = group.conditions.filter((_, idx) => idx !== i);
              onChange({ ...group, conditions: next });
            }}
            depth={depth + 1}
          />
        ))}
        {group.conditions.length === 0 && (
          <span className="text-[10px] opacity-50 ml-4">No conditions</span>
        )}
      </div>
    </div>
  );
}

export function FilterTreeEditor({
  tree,
  fields,
  onChange,
  onDelete,
  depth = 0,
}: FilterEditorProps) {
  if ("logic" in tree) {
    return (
      <FilterGroupEditor
        group={tree}
        fields={fields}
        onChange={onChange}
        onDelete={onDelete}
        depth={depth}
      />
    );
  }
  return (
    <FilterNodeEditor
      node={tree}
      fields={fields}
      onChange={onChange}
      onDelete={onDelete}
    />
  );
}

interface StageBlockProps {
  stage: Stage;
  index: number;
  onRemove: (index: number) => void;
  onMoveUp: (index: number) => void;
  onMoveDown: (index: number) => void;
  onChange: (index: number, stage: Stage) => void;
  fields?: ScreenField[];
  freezeScoreRanking?: boolean;
  /** Hide optional-score boxes when gate_combine=count (Champion). */
  hideOptionalScores?: boolean;
  /** Setup filters live in AlphaMeasuresPanel — hide duplicate chrome. */
  hideSetupFilters?: boolean;
  /** Exit SSOT is Risk Defense — collapse tranche editors to a link. */
  exitSsotOnly?: boolean;
}

export function StageBlock({
  stage,
  index,
  onRemove,
  onMoveUp,
  onMoveDown,
  onChange,
  fields = [],
  freezeScoreRanking = false,
  hideOptionalScores = false,
  hideSetupFilters = false,
  exitSsotOnly = false,
}: StageBlockProps) {
  const mode = stage.mode;
  const isSecondaryBlend =
    freezeScoreRanking && mode === "score" && !Boolean(stage.as_gate);
  const [showFrozenFactors, setShowFrozenFactors] = useState(false);
  const hasSetupFilters = (stage.filters?.length ?? 0) > 0;
  const hasEntryTriggers = (stage.entry_triggers?.length ?? 0) > 0;

  const updateFilters = (next: FilterTree[]) => {
    onChange(index, { ...stage, filters: next });
  };

  const purpose = stage.documentation?.purpose ?? "";

  return (
    <div className={`rounded border p-3 ${STAGE_MODE_COLORS[mode]}`}>
      {isSecondaryBlend ? (
        <div className="mb-2 rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1.5 text-[10px] text-amber-100/90 leading-tight">
          Secondary blend — does not drive Champion shortlist. Rank is{" "}
          <code className="font-mono">screens_hit</code> → tie-break (ORDER BY from Measures Insight ✓).
          Factors frozen under <code className="font-mono">gate_combine=count</code>.
        </div>
      ) : null}      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono uppercase font-bold opacity-80">
            Stage {index + 1}
          </span>
          <span className="text-[10px] font-mono uppercase font-bold">
            {STAGE_MODE_LABELS[mode]}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => onMoveUp(index)}
            disabled={index === 0}
            className="rounded border border-line px-1.5 text-[10px] hover:bg-surface-sunk disabled:opacity-30"
            title="Move up"
          >
            ↑
          </button>
          <button
            type="button"
            onClick={() => onMoveDown(index)}
            className="rounded border border-line px-1.5 text-[10px] hover:bg-surface-sunk"
            title="Move down"
          >
            ↓
          </button>
          <button
            type="button"
            onClick={() => onRemove(index)}
            className="rounded border border-line px-1.5 text-[10px] hover:bg-surface-sunk"
            title="Remove stage"
          >
            ✕
          </button>
        </div>
      </div>

      <input
        type="text"
        value={stage.name}
        onChange={(e) => onChange(index, { ...stage, name: e.target.value })}
        className="mt-1 w-full rounded border border-line bg-surface-sunk px-2 py-1 text-[12px] text-ink"
        placeholder="Stage name"
      />

      <label className="mt-1 block text-[10px] text-ink-muted">
        Binding id (SQL alias)
        <input
          type="text"
          value={stage.id ?? ""}
          onChange={(e) =>
            onChange(index, {
              ...stage,
              id: e.target.value || null,
            })
          }
          onBlur={(e) => {
            const trimmed = e.target.value.trim();
            if (trimmed !== (stage.id ?? "")) {
              onChange(index, {
                ...stage,
                id: trimmed || null,
              });
            }
          }}
          placeholder="screen_1"
          className="mt-0.5 w-full rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-ink"
        />
      </label>

      <label className="mt-1 block text-[10px] text-ink-muted">
        Purpose / notes
        <textarea
          value={purpose}
          onChange={(e) =>
            onChange(index, {
              ...stage,
              documentation: {
                ...(stage.documentation ?? {}),
                purpose: e.target.value || undefined,
              },
            })
          }
          rows={2}
          placeholder="What this stage measures"
          className="mt-0.5 w-full rounded border border-line bg-surface px-1.5 py-0.5 text-[11px] text-ink"
        />
      </label>

      <p className="mt-1 text-[10px] opacity-70">{STAGE_MODE_DESCRIPTIONS[mode]}</p>

      {/* Filter tree: Universe-style AST only when the stage has filters (Champion screens / setup). Hide empty rank-only gates. */}
      {!hideSetupFilters &&
        (mode === "filter" ||
          mode === "confirm" ||
          (mode === "signal" && hasSetupFilters) ||
          (mode === "score" && Boolean(stage.as_gate) && (stage.filters?.length ?? 0) > 0)) && (
        <div className="mt-2">
          <FilterTreeSlotEditor
            filters={stage.filters}
            fields={fields}
            onChange={updateFilters}
          />
        </div>
      )}
      {!hideSetupFilters && mode === "signal" && !hasSetupFilters ? (
        <div className="mt-2">
          <button
            type="button"
            onClick={() => updateFilters([{ logic: "and", conditions: [] }])}
            className="rounded border border-dashed border-line px-2 py-0.5 text-[10px] text-ink-muted hover:border-accent hover:text-accent"
          >
            + Add setup filters
          </button>
        </div>
      ) : null}
      {hideSetupFilters && mode === "signal" ? (
        <p className="mt-1 text-[10px] text-ink-faint">
          Setup filters → Measures panel above. Entry triggers below.
        </p>
      ) : null}
      {/* Score/watch stage: factor weights + selection rule */}
      {(mode === "score" || mode === "watch") && (
        <div className="mt-2 space-y-2">
          {mode === "score" && (
            <label className="flex items-center gap-1.5 text-[10px] text-ink-muted">
              <input
                type="checkbox"
                checked={Boolean(stage.as_gate)}
                onChange={(e) => onChange(index, { ...stage, as_gate: e.target.checked })}
              />
              Parallel Alpha gate (boolean where and/or score; Champion uses where + screens_hit)
            </label>
          )}
          {mode === "score" && Boolean(stage.as_gate) && (
            <p className="text-[10px] text-ink-faint">
              Count gates with an expression measure (e.g. screen_1 + screen_2). Insight ✓ = ORDER BY.
            </p>
          )}
          {mode === "score" && Boolean(stage.as_gate) && (stage.filters?.length ?? 0) === 0 && (
            <button
              type="button"
              onClick={() => updateFilters([{ logic: "and", conditions: [] }])}
              className="mt-1 rounded border border-dashed border-violet-400/60 px-2 py-0.5 text-[10px] font-semibold text-violet-300 hover:bg-violet-500/10"
            >
              + Add boolean where
            </button>
          )}
          {mode === "score" && Boolean(stage.as_gate) && !hideOptionalScores && (
            <div className="space-y-1.5 rounded border border-line/70 bg-surface-sunk/30 p-2">
              <label className="block text-[10px] text-ink-muted">
                Optional score fields (comma-separated L7 cols; nulls skip)
                <input
                  type="text"
                  value={(stage.optional_score_fields ?? []).join(", ")}
                  onChange={(e) =>
                    onChange(index, {
                      ...stage,
                      optional_score_fields: e.target.value
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    })
                  }
                  placeholder="eps_ny_rev_pct_90d, eps_last_surprise_pct"
                  className="mt-0.5 w-full rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-ink"
                />
              </label>
              <label className="block text-[10px] text-ink-muted">
                optional_min (field=threshold, comma-separated)
                <input
                  type="text"
                  value={Object.entries(stage.optional_min ?? {})
                    .map(([k, v]) => `${k}=${v}`)
                    .join(", ")}
                  onChange={(e) => {
                    const next: Record<string, number> = {};
                    for (const part of e.target.value.split(",")) {
                      const [k, raw] = part.split("=").map((s) => s.trim());
                      if (!k || raw === undefined) continue;
                      const n = Number(raw);
                      if (!Number.isNaN(n)) next[k] = n;
                    }
                    onChange(index, { ...stage, optional_min: next });
                  }}
                  placeholder="eps_ny_rev_pct_90d=0.08"
                  className="mt-0.5 w-full rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-ink"
                />
              </label>
            </div>
          )}
          {mode === "score" && Boolean(stage.as_gate) && hideOptionalScores && (
            <p className="text-[10px] text-ink-muted">
              Count combinator: optional score fields hidden (screens_hit from bool columns).
            </p>
          )}
          {freezeScoreRanking && mode === "score" ? (
            isSecondaryBlend ? (
              <div className="space-y-1.5">
                <button
                  type="button"
                  onClick={() => setShowFrozenFactors((v) => !v)}
                  className="rounded border border-line px-1.5 py-0.5 text-[10px] text-ink-muted hover:bg-surface-sunk"
                >
                  {showFrozenFactors ? "Hide frozen factors" : "Show frozen factors"}
                </button>
                {showFrozenFactors ? (
                  <p className="text-[10px] text-ink-faint">
                    {(stage.factors ?? [])
                      .map((f) => `${f.name}:${(f.weight * 100).toFixed(0)}%`)
                      .join(" · ") || "No factors"}
                  </p>
                ) : null}
              </div>
            ) : (
              <p className="text-[10px] text-ink-muted">
                Champion count ranking uses screens_hit. Factor weights and top_n selection stay
                frozen.
              </p>
            )
          ) : (
          <>
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-[10px] font-semibold text-ink-muted">
              <span>Factor Weights</span>
              <button
                type="button"
                onClick={() => {
                  const current = stage.factors ?? [];
                  onChange(index, {
                    ...stage,
                    factors: [...current, { name: "momentum", weight: 0.2 }],
                  });
                }}
                className="rounded border border-dashed border-accent/50 bg-accent/5 px-1.5 py-0.5 text-[10px] text-accent-ink hover:bg-accent/10"
              >
                + Factor
              </button>
            </div>
            {(stage.factors ?? []).map((fw, fi) => (
              <div key={fi} className="flex items-center gap-2 rounded border border-line/60 bg-surface-sunk/50 px-2 py-1 text-[11px]">
                <input
                  type="text"
                  value={fw.name}
                  onChange={(e) => {
                    const next = [...(stage.factors ?? [])];
                    next[fi] = { ...fw, name: e.target.value };
                    onChange(index, { ...stage, factors: next });
                  }}
                  placeholder="Factor name (e.g. momentum, value)"
                  className="flex-1 rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-ink focus:border-accent focus:outline-none"
                />
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    step="0.05"
                    min="0"
                    max="1"
                    value={fw.weight}
                    onChange={(e) => {
                      const next = [...(stage.factors ?? [])];
                      next[fi] = { ...fw, weight: parseFloat(e.target.value) || 0 };
                      onChange(index, { ...stage, factors: next });
                    }}
                    className="w-16 rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-ink focus:border-accent focus:outline-none text-right"
                  />
                  <span className="font-mono text-[10px] text-ink-muted">({(fw.weight * 100).toFixed(0)}%)</span>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    const next = (stage.factors ?? []).filter((_, idx) => idx !== fi);
                    onChange(index, { ...stage, factors: next });
                  }}
                  className="text-[12px] text-ink-faint hover:text-danger"
                  title="Remove factor"
                >
                  ✕
                </button>
              </div>
            ))}
            {(stage.factors ?? []).length === 0 && (
              <span className="text-[10px] opacity-50">No factors configured yet</span>
            )}
          </div>

          {/* Selection rule */}
          <div className="rounded border border-line/70 bg-surface-sunk/30 p-2 text-[11px]">
            <span className="block font-semibold text-[10px] text-ink-muted mb-1">Selection Method</span>
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={stage.selection?.method ?? "top_n"}
                onChange={(e) => {
                  const m = e.target.value as "top_n" | "top_n_per_sector" | "threshold";
                  onChange(index, {
                    ...stage,
                    selection: {
                      method: m,
                      n: m === "top_n" ? stage.selection?.n ?? 20 : undefined,
                      sectors: m === "top_n_per_sector" ? stage.selection?.sectors ?? 5 : undefined,
                      per_sector: m === "top_n_per_sector" ? stage.selection?.per_sector ?? 3 : undefined,
                      min_score: m === "threshold" ? stage.selection?.min_score ?? 70 : undefined,
                    },
                  });
                }}
                className="rounded border border-line bg-surface px-1.5 py-0.5 text-[11px] text-ink"
              >
                <option value="top_n">Top N Overall</option>
                <option value="top_n_per_sector">Top N Per Sector</option>
                <option value="threshold">Score Threshold</option>
              </select>
              {stage.selection?.method !== "threshold" && stage.selection?.method !== "top_n_per_sector" && (
                <label className="flex items-center gap-1 text-[10.5px]">
                  <span>N:</span>
                  <input
                    type="number"
                    min="1"
                    value={stage.selection?.n ?? 20}
                    onChange={(e) =>
                      onChange(index, {
                        ...stage,
                        selection: { ...(stage.selection ?? { method: "top_n" }), n: parseInt(e.target.value) || 1 },
                      })
                    }
                    className="w-14 rounded border border-line bg-surface px-1 py-0.5 font-mono text-[11px] text-ink"
                  />
                </label>
              )}
              {stage.selection?.method === "top_n_per_sector" && (
                <>
                  <label className="flex items-center gap-1 text-[10.5px]">
                    <span>Sectors:</span>
                    <input
                      type="number"
                      min="1"
                      value={stage.selection?.sectors ?? 5}
                      onChange={(e) =>
                        onChange(index, {
                          ...stage,
                          selection: { ...(stage.selection ?? { method: "top_n_per_sector" }), sectors: parseInt(e.target.value) || 1 },
                        })
                      }
                      className="w-12 rounded border border-line bg-surface px-1 py-0.5 font-mono text-[11px] text-ink"
                    />
                  </label>
                  <label className="flex items-center gap-1 text-[10.5px]">
                    <span>Per Sector:</span>
                    <input
                      type="number"
                      min="1"
                      value={stage.selection?.per_sector ?? 3}
                      onChange={(e) =>
                        onChange(index, {
                          ...stage,
                          selection: { ...(stage.selection ?? { method: "top_n_per_sector" }), per_sector: parseInt(e.target.value) || 1 },
                        })
                      }
                      className="w-12 rounded border border-line bg-surface px-1 py-0.5 font-mono text-[11px] text-ink"
                    />
                  </label>
                </>
              )}
              {stage.selection?.method === "threshold" && (
                <label className="flex items-center gap-1 text-[10.5px]">
                  <span>Min Score:</span>
                  <input
                    type="number"
                    value={stage.selection?.min_score ?? 70}
                    onChange={(e) =>
                      onChange(index, {
                        ...stage,
                        selection: { ...(stage.selection ?? { method: "threshold" }), min_score: parseFloat(e.target.value) || 0 },
                      })
                    }
                    className="w-16 rounded border border-line bg-surface px-1 py-0.5 font-mono text-[11px] text-ink"
                  />
                </label>
              )}
            </div>
          </div>
          </>
          )}
        </div>
      )}

      {/* Signal stage: Entry triggers + Stop-loss rule */}
      {mode === "signal" && (
        <div className="mt-2 space-y-2.5">
          <div className="rounded border border-line/70 bg-surface-sunk/40 px-2 py-1.5 text-[10px] text-ink-muted leading-tight">
            {hasSetupFilters && !hasEntryTriggers ? (
              <>
                <span className="font-semibold text-ink">Role: Setup gate</span>
                {" "}
                (<code className="font-mono">setup_where</code>
                {stage.id ? (
                  <>
                    {" "}
                    / <code className="font-mono">{stage.id}</code>
                  </>
                ) : null}
                ). Gates Insights — not universe membership, not hit count.
              </>
            ) : hasEntryTriggers && !hasSetupFilters ? (
              <>
                <span className="font-semibold text-ink">Role: Entry signal (legacy triggers)</span>
                . Prefer timing as a bool measure. Triggers below are Vera glue, not Lean.
              </>
            ) : (
              <>
                <span className="font-semibold text-ink">Role: Signal</span>
                . Setup filters → Measures / <code className="font-mono">setup_pass</code>. Timing
                belongs in measures, not Alpha trigger lists.
              </>
            )}
          </div>
          <div className="space-y-1.5">
            <div className="rounded border border-warn/40 bg-warn-soft/40 px-2 py-1.5 text-[10px] text-warn leading-tight">
              <span className="font-semibold">Legacy.</span>{" "}
              <code className="font-mono">entry_triggers</code> are Vera Alpha glue, not Lean.
              Prefer a <span className="font-semibold">bool measure</span> (Insight ✓ → WHERE /
              setup) for timing. Do not add new triggers here.
            </div>
            <div className="flex items-center justify-between text-[10px] font-semibold text-ink-muted">
              <span>Entry Triggers (legacy)</span>
              <button
                type="button"
                onClick={() => {
                  const current = stage.entry_triggers ?? [];
                  onChange(index, {
                    ...stage,
                    entry_triggers: [
                      ...current,
                      { type: "pivot_breakout", lookback_days: 5, volume_multiplier: 1.5 },
                    ],
                  });
                }}
                className="rounded border border-dashed border-amber-500/50 bg-amber-500/5 px-1.5 py-0.5 text-[10px] text-amber-300 hover:bg-amber-500/10"
              >
                + Entry Trigger
              </button>
            </div>
            {(stage.entry_triggers ?? []).map((trig, ti) => (
              <div key={ti} className="rounded border border-line/60 bg-surface-sunk/50 p-2 text-[11px] space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-ink-muted font-semibold">Type:</span>
                    <select
                      value={trig.type}
                      onChange={(e) => {
                        const next = [...(stage.entry_triggers ?? [])];
                        next[ti] = { type: e.target.value as EntryTriggerType };
                        onChange(index, { ...stage, entry_triggers: next });
                      }}
                      className="rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-ink"
                    >
                      <option value="pivot_breakout">Pivot Breakout</option>
                      <option value="breakout">Swing Breakout</option>
                      <option value="vcp_complete">VCP Complete</option>
                      <option value="pullback_to_sma">Pullback to SMA</option>
                      <option value="rsi_cross">RSI Cross</option>
                      <option value="macd">MACD Cross</option>
                      <option value="ema_cross">EMA Cross</option>
                    </select>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      const next = (stage.entry_triggers ?? []).filter((_, idx) => idx !== ti);
                      onChange(index, { ...stage, entry_triggers: next });
                    }}
                    className="text-[12px] text-ink-faint hover:text-danger"
                    title="Remove trigger"
                  >
                    ✕
                  </button>
                </div>

                {/* Specific trigger parameters */}
                <div className="flex flex-wrap items-center gap-2 text-[10.5px]">
                  {(trig.type === "pivot_breakout" || trig.type === "breakout") && (
                    <>
                      <label className="flex items-center gap-1">
                        <span className="text-ink-muted">Lookback (days):</span>
                        <input
                          type="number"
                          value={trig.lookback_days ?? 5}
                          onChange={(e) => {
                            const next = [...(stage.entry_triggers ?? [])];
                            next[ti] = { ...trig, lookback_days: parseInt(e.target.value) || 1 };
                            onChange(index, { ...stage, entry_triggers: next });
                          }}
                          className="w-14 rounded border border-line bg-surface px-1 py-0.5 font-mono text-[11px] text-ink"
                        />
                      </label>
                      <label className="flex items-center gap-1">
                        <span className="text-ink-muted">Vol Multiplier:</span>
                        <input
                          type="number"
                          step="0.1"
                          value={trig.volume_multiplier ?? 1.5}
                          onChange={(e) => {
                            const next = [...(stage.entry_triggers ?? [])];
                            next[ti] = { ...trig, volume_multiplier: parseFloat(e.target.value) || 1 };
                            onChange(index, { ...stage, entry_triggers: next });
                          }}
                          className="w-14 rounded border border-line bg-surface px-1 py-0.5 font-mono text-[11px] text-ink"
                        />
                      </label>
                    </>
                  )}
                  {trig.type === "vcp_complete" && (
                    <>
                      <label className="flex items-center gap-1">
                        <span className="text-ink-muted">Contractions:</span>
                        <input
                          type="number"
                          value={trig.contraction_count ?? 3}
                          onChange={(e) => {
                            const next = [...(stage.entry_triggers ?? [])];
                            next[ti] = { ...trig, contraction_count: parseInt(e.target.value) || 1 };
                            onChange(index, { ...stage, entry_triggers: next });
                          }}
                          className="w-12 rounded border border-line bg-surface px-1 py-0.5 font-mono text-[11px] text-ink"
                        />
                      </label>
                      <label className="flex items-center gap-1">
                        <span className="text-ink-muted">Consolidation Days:</span>
                        <input
                          type="number"
                          value={trig.consolidation_days ?? 5}
                          onChange={(e) => {
                            const next = [...(stage.entry_triggers ?? [])];
                            next[ti] = { ...trig, consolidation_days: parseInt(e.target.value) || 1 };
                            onChange(index, { ...stage, entry_triggers: next });
                          }}
                          className="w-12 rounded border border-line bg-surface px-1 py-0.5 font-mono text-[11px] text-ink"
                        />
                      </label>
                    </>
                  )}
                  {trig.type === "pullback_to_sma" && (
                    <>
                      <label className="flex items-center gap-1">
                        <span className="text-ink-muted">SMA Period:</span>
                        <input
                          type="number"
                          value={trig.sma_period ?? 50}
                          onChange={(e) => {
                            const next = [...(stage.entry_triggers ?? [])];
                            next[ti] = { ...trig, sma_period: parseInt(e.target.value) || 1 };
                            onChange(index, { ...stage, entry_triggers: next });
                          }}
                          className="w-14 rounded border border-line bg-surface px-1 py-0.5 font-mono text-[11px] text-ink"
                        />
                      </label>
                      <label className="flex items-center gap-1">
                        <span className="text-ink-muted">Max Deviation %:</span>
                        <input
                          type="number"
                          step="0.01"
                          value={trig.max_deviation_pct ?? 0.03}
                          onChange={(e) => {
                            const next = [...(stage.entry_triggers ?? [])];
                            next[ti] = { ...trig, max_deviation_pct: parseFloat(e.target.value) || 0 };
                            onChange(index, { ...stage, entry_triggers: next });
                          }}
                          className="w-14 rounded border border-line bg-surface px-1 py-0.5 font-mono text-[11px] text-ink"
                        />
                      </label>
                    </>
                  )}
                  {trig.type === "rsi_cross" && (
                    <>
                      <label className="flex items-center gap-1">
                        <span className="text-ink-muted">Period:</span>
                        <input
                          type="number"
                          value={trig.period ?? 14}
                          onChange={(e) => {
                            const next = [...(stage.entry_triggers ?? [])];
                            next[ti] = { ...trig, period: parseInt(e.target.value) || 1 };
                            onChange(index, { ...stage, entry_triggers: next });
                          }}
                          className="w-12 rounded border border-line bg-surface px-1 py-0.5 font-mono text-[11px] text-ink"
                        />
                      </label>
                      <label className="flex items-center gap-1">
                        <span className="text-ink-muted">Oversold:</span>
                        <input
                          type="number"
                          value={trig.oversold ?? 30}
                          onChange={(e) => {
                            const next = [...(stage.entry_triggers ?? [])];
                            next[ti] = { ...trig, oversold: parseFloat(e.target.value) || 0 };
                            onChange(index, { ...stage, entry_triggers: next });
                          }}
                          className="w-12 rounded border border-line bg-surface px-1 py-0.5 font-mono text-[11px] text-ink"
                        />
                      </label>
                    </>
                  )}
                  {(trig.type === "macd" || trig.type === "ema_cross") && (
                    <>
                      <label className="flex items-center gap-1">
                        <span className="text-ink-muted">Fast:</span>
                        <input
                          type="number"
                          value={trig.fast_period ?? 12}
                          onChange={(e) => {
                            const next = [...(stage.entry_triggers ?? [])];
                            next[ti] = { ...trig, fast_period: parseInt(e.target.value) || 1 };
                            onChange(index, { ...stage, entry_triggers: next });
                          }}
                          className="w-12 rounded border border-line bg-surface px-1 py-0.5 font-mono text-[11px] text-ink"
                        />
                      </label>
                      <label className="flex items-center gap-1">
                        <span className="text-ink-muted">Slow:</span>
                        <input
                          type="number"
                          value={trig.slow_period ?? 26}
                          onChange={(e) => {
                            const next = [...(stage.entry_triggers ?? [])];
                            next[ti] = { ...trig, slow_period: parseInt(e.target.value) || 1 };
                            onChange(index, { ...stage, entry_triggers: next });
                          }}
                          className="w-12 rounded border border-line bg-surface px-1 py-0.5 font-mono text-[11px] text-ink"
                        />
                      </label>
                    </>
                  )}
                </div>
              </div>
            ))}
            {(stage.entry_triggers ?? []).length === 0 && (
              <span className="text-[10px] opacity-50">No entry triggers specified</span>
            )}
          </div>

          {/* Stop-loss rule */}
          <div className="rounded border border-line/70 bg-surface-sunk/30 p-2 text-[11px]">
            <span className="block font-semibold text-[10px] text-ink-muted mb-1">
              Alpha ATR (share count, not post-fill stop)
            </span>
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={stage.stop_loss?.type ?? "atr"}
                onChange={(e) => {
                  const t = e.target.value as "atr" | "fixed_pct";
                  onChange(index, {
                    ...stage,
                    stop_loss: {
                      type: t,
                      multiplier: t === "atr" ? stage.stop_loss?.multiplier ?? 2.0 : undefined,
                      pct: t === "fixed_pct" ? stage.stop_loss?.pct ?? 0.05 : undefined,
                    },
                  });
                }}
                className="rounded border border-line bg-surface px-1.5 py-0.5 text-[11px] text-ink"
              >
                <option value="atr">ATR Multiple</option>
                <option value="fixed_pct">Fixed Percentage</option>
              </select>
              {stage.stop_loss?.type === "fixed_pct" ? (
                <label className="flex items-center gap-1 text-[10.5px]">
                  <span>Stop %:</span>
                  <input
                    type="number"
                    step="0.01"
                    value={stage.stop_loss?.pct ?? 0.05}
                    onChange={(e) =>
                      onChange(index, {
                        ...stage,
                        stop_loss: { ...(stage.stop_loss ?? { type: "fixed_pct" }), pct: parseFloat(e.target.value) || 0.05 },
                      })
                    }
                    className="w-16 rounded border border-line bg-surface px-1 py-0.5 font-mono text-[11px] text-ink"
                  />
                </label>
              ) : (
                <label className="flex items-center gap-1 text-[10.5px]">
                  <span>ATR Mult:</span>
                  <input
                    type="number"
                    step="0.1"
                    value={stage.stop_loss?.multiplier ?? 2.0}
                    onChange={(e) =>
                      onChange(index, {
                        ...stage,
                        stop_loss: { ...(stage.stop_loss ?? { type: "atr" }), multiplier: parseFloat(e.target.value) || 2.0 },
                      })
                    }
                    className="w-14 rounded border border-line bg-surface px-1 py-0.5 font-mono text-[11px] text-ink"
                  />
                </label>
              )}
              <span className="text-[9.5px] text-ink-faint">
                Cooldown after stop-out is edited on the Risk card.
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Pyramid stage: progressive scaling phases */}
      {mode === "pyramid" && (
        <div className="mt-2 space-y-1.5">
          <label className="flex items-center gap-1 text-[10.5px]">
            <span className="text-ink-muted">Add trigger (gain vs entry):</span>
            <input
              type="number"
              step="0.005"
              min="0"
              max="0.2"
              value={stage.add_trigger_pct ?? 0.02}
              onChange={(e) =>
                onChange(index, {
                  ...stage,
                  add_trigger_pct: parseFloat(e.target.value) || 0,
                })
              }
              className="w-16 rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-ink text-right"
            />
            <span className="font-mono text-[10px] text-ink-muted">
              ({(((stage.add_trigger_pct ?? 0.02) * 100).toFixed(1))}%)
            </span>
          </label>
          <div className="flex items-center justify-between text-[10px] font-semibold text-ink-muted">
            <span>Scaling Phases</span>
            <button
              type="button"
              onClick={() => {
                const current = stage.phases ?? [];
                onChange(index, {
                  ...stage,
                  phases: [...current, { name: `phase_${current.length + 1}`, size_pct: 0.25 }],
                });
              }}
              className="rounded border border-dashed border-emerald-500/50 bg-emerald-500/5 px-1.5 py-0.5 text-[10px] text-emerald-300 hover:bg-emerald-500/10"
            >
              + Phase
            </button>
          </div>
          {(stage.phases ?? []).map((p, fi) => (
            <div key={fi} className="flex items-center gap-2 rounded border border-line/60 bg-surface-sunk/50 px-2 py-1 text-[11px]">
              <input
                type="text"
                value={p.name}
                onChange={(e) => {
                  const next = [...(stage.phases ?? [])];
                  next[fi] = { ...p, name: e.target.value };
                  onChange(index, { ...stage, phases: next });
                }}
                placeholder="Phase name"
                className="w-24 rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-ink focus:border-accent focus:outline-none"
              />
              <label className="flex items-center gap-1 text-[10.5px]">
                <span className="text-ink-muted">Size:</span>
                <input
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  value={p.size_pct}
                  onChange={(e) => {
                    const next = [...(stage.phases ?? [])];
                    next[fi] = { ...p, size_pct: parseFloat(e.target.value) || 0 };
                    onChange(index, { ...stage, phases: next });
                  }}
                  className="w-16 rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-ink text-right"
                />
                <span className="font-mono text-[10px] text-ink-muted">({(p.size_pct * 100).toFixed(0)}%)</span>
              </label>
              <button
                type="button"
                onClick={() => {
                  const next = (stage.phases ?? []).filter((_, idx) => idx !== fi);
                  onChange(index, { ...stage, phases: next });
                }}
                className="text-[12px] text-ink-faint hover:text-danger ml-auto"
                title="Remove phase"
              >
                ✕
              </button>
            </div>
          ))}
          {(stage.phases ?? []).length === 0 && (
            <span className="text-[10px] opacity-50">No pyramid phases configured</span>
          )}
        </div>
      )}

      {/* Exit stage: Risk Defense is SSOT when exitSsotOnly */}
      {mode === "exit" && exitSsotOnly ? (
        <p className="mt-2 text-[10.5px] text-ink-muted leading-tight">
          Exit schedule SSOT → <span className="font-semibold text-ink">Risk Defense</span>{" "}
          (tranches, trail, hold, ATR). Edit knobs there — not in Alpha.
        </p>
      ) : null}
      {mode === "exit" && !exitSsotOnly && (
        <div className="mt-2 space-y-1.5">
          <p className="text-[10px] text-ink-muted leading-tight">
            Same fields as Risk Defense panel (one SSOT) — tranches / trail / hold sync via
            progressive risk.
          </p>
          <div className="flex items-center justify-between text-[10px] font-semibold text-ink-muted">
            <span>Profit Tranches (Sell into Strength)</span>
            <button
              type="button"
              onClick={() => {
                const current = stage.tranches ?? [];
                onChange(index, {
                  ...stage,
                  tranches: [...current, { trigger_r: 2.5, sell_pct: 0.25 }],
                });
              }}
              className="rounded border border-dashed border-orange-500/50 bg-orange-500/5 px-1.5 py-0.5 text-[10px] text-orange-300 hover:bg-orange-500/10"
            >
              + Tranche
            </button>
          </div>
          {(stage.tranches ?? []).map((t, fi) => (
            <div key={fi} className="flex items-center gap-2 rounded border border-line/60 bg-surface-sunk/50 px-2 py-1 text-[11px]">
              <label className="flex items-center gap-1 text-[10.5px]">
                <span className="text-ink-muted">Trigger:</span>
                <input
                  type="number"
                  step="0.5"
                  value={t.trigger_r}
                  onChange={(e) => {
                    const next = [...(stage.tranches ?? [])];
                    next[fi] = { ...t, trigger_r: parseFloat(e.target.value) || 0 };
                    onChange(index, { ...stage, tranches: next });
                  }}
                  className="w-16 rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-ink text-right"
                />
                <span className="font-mono text-[10px] text-ink-muted">R</span>
              </label>
              <label className="flex items-center gap-1 text-[10.5px]">
                <span className="text-ink-muted">Sell:</span>
                <input
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  value={t.sell_pct}
                  onChange={(e) => {
                    const next = [...(stage.tranches ?? [])];
                    next[fi] = { ...t, sell_pct: parseFloat(e.target.value) || 0 };
                    onChange(index, { ...stage, tranches: next });
                  }}
                  className="w-16 rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-ink text-right"
                />
                <span className="font-mono text-[10px] text-ink-muted">({(t.sell_pct * 100).toFixed(0)}%)</span>
              </label>
              <button
                type="button"
                onClick={() => {
                  const next = (stage.tranches ?? []).filter((_, idx) => idx !== fi);
                  onChange(index, { ...stage, tranches: next });
                }}
                className="text-[12px] text-ink-faint hover:text-danger ml-auto"
                title="Remove tranche"
              >
                ✕
              </button>
            </div>
          ))}
          {(stage.tranches ?? []).length === 0 && (
            <span className="text-[10px] opacity-50">No exit tranches configured</span>
          )}
        </div>
      )}

      {/* Hedge stage: instruments */}
      {mode === "hedge" && (
        <div className="mt-2 space-y-1.5">
          <div className="flex items-center justify-between text-[10px] font-semibold text-ink-muted">
            <span>Inverse Hedge Instruments</span>
            <button
              type="button"
              onClick={() => {
                const current = stage.instruments ?? [];
                onChange(index, {
                  ...stage,
                  instruments: [...current, { ticker: "SH", max_allocation: 0.25 }],
                });
              }}
              className="rounded border border-dashed border-rose-500/50 bg-rose-500/5 px-1.5 py-0.5 text-[10px] text-rose-300 hover:bg-rose-500/10"
            >
              + Hedge Instrument
            </button>
          </div>
          {(stage.instruments ?? []).map((inst, fi) => (
            <div key={fi} className="flex items-center gap-2 rounded border border-line/60 bg-surface-sunk/50 px-2 py-1 text-[11px]">
              <input
                type="text"
                value={inst.ticker}
                onChange={(e) => {
                  const next = [...(stage.instruments ?? [])];
                  next[fi] = { ...inst, ticker: e.target.value.toUpperCase() };
                  onChange(index, { ...stage, instruments: next });
                }}
                placeholder="Ticker (e.g. SH, PSQ)"
                className="w-24 rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-ink uppercase focus:border-accent focus:outline-none"
              />
              <label className="flex items-center gap-1 text-[10.5px]">
                <span className="text-ink-muted">Max Alloc:</span>
                <input
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  value={inst.max_allocation}
                  onChange={(e) => {
                    const next = [...(stage.instruments ?? [])];
                    next[fi] = { ...inst, max_allocation: parseFloat(e.target.value) || 0 };
                    onChange(index, { ...stage, instruments: next });
                  }}
                  className="w-16 rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-ink text-right"
                />
                <span className="font-mono text-[10px] text-ink-muted">({(inst.max_allocation * 100).toFixed(0)}%)</span>
              </label>
              <button
                type="button"
                onClick={() => {
                  const next = (stage.instruments ?? []).filter((_, idx) => idx !== fi);
                  onChange(index, { ...stage, instruments: next });
                }}
                className="text-[12px] text-ink-faint hover:text-danger ml-auto"
                title="Remove instrument"
              >
                ✕
              </button>
            </div>
          ))}
          {(stage.instruments ?? []).length === 0 && (
            <span className="text-[10px] opacity-50">No hedge instruments configured</span>
          )}
        </div>
      )}
    </div>
  );
}
