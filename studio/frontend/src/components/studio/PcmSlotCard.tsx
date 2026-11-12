import type { ScreenField } from "../../types";
import type { PyramidPhase } from "../strategy/StrategyDocument";
import type { OperandAst, RuleSpec } from "../../lib/rulesAst";
import type { PcmBookExprKey } from "../../lib/pipelineSlotBindings";
import { usePcmBindings } from "../../lib/slotFieldCatalog";
import { EditableOperand } from "./ExprPillEditor";
import { RuleListEditor } from "./RuleListEditor";
import { RuleTableTester } from "./RuleTableTester";
import { UnitNumberField } from "./UnitNumberField";

interface PcmSlotCardProps {
  /** Pyramid phase geometry — the state machine definition (pyr.entry_frac/add_frac). */
  phases: PyramidPhase[];
  onChangePhases: (phases: PyramidPhase[]) => void;
  slotFields?: ScreenField[];
  /** Regime thermostat — cross-slot regime policy (doc.regime_gate); wires the
      DataSource uses[] that decide which regime rule rows generate. */
  regimeOn?: boolean;
  onToggleRegime?: (v: boolean) => void;
  regimeUses?: string[];
  onChangeRegimeUses?: (uses: string[]) => void;
  enableSurrogates?: boolean;
  onChangeEnableSurrogates?: (v: boolean) => void;
  surrogateSizingMode?: "dollar_risk_parity" | "full_notional";
  onChangeSurrogateSizingMode?: (v: "dollar_risk_parity" | "full_notional") => void;
  minSurrogateAdv?: number;
  onChangeMinSurrogateAdv?: (v: number) => void;
  /** Unified allocation rules (doc.sizing.rules → PCM Parameters.rules). */
  rules?: RuleSpec[];
  onChangeRules?: (rules: RuleSpec[]) => void;
  /** Saved spec id — enables the rule-table preview tester (row source = stored universe). */
  testIrId?: string | null;
  /** Base sizing Operand AST (doc.sizing.size_expr → PCM Parameters.size_expr). */
  sizeExpr?: Record<string, unknown> | null;
  onChangeSizeExpr?: (v: Record<string, unknown> | null) => void;
  /** Book-level ASTs evaluated once per pass (Phase 3, C-FW-RULES):
      scale_expr → regime.scale, slots_expr → acct.scaled_max_positions,
      order_expr → unit ordering key. */
  bookExprs?: Partial<Record<PcmBookExprKey, Record<string, unknown> | null>>;
  onChangeBookExpr?: (key: PcmBookExprKey, v: Record<string, unknown> | null) => void;
}

/** PCM is a pure decision surface: book-level exprs (once per pass), the base
    sizing expr, and the ordered allocation table. Magnitudes live *inside* the
    ASTs as literals — edit them in place, or reset an expr to regenerate from
    the doc's parameters at save. The only non-expression controls left are the
    engine's structural plumbing (pyramid geometry, surrogate routing, regime
    DataSource wiring) in the drawer at the bottom. */
export function PcmSlotCard({
  phases,
  onChangePhases,
  slotFields = [],
  regimeOn = false,
  onToggleRegime,
  regimeUses = [],
  onChangeRegimeUses,
  enableSurrogates = false,
  onChangeEnableSurrogates,
  surrogateSizingMode = "dollar_risk_parity",
  onChangeSurrogateSizingMode,
  minSurrogateAdv = 5_000_000,
  onChangeMinSurrogateAdv,
  rules,
  onChangeRules,
  testIrId,
  sizeExpr,
  onChangeSizeExpr,
  bookExprs,
  onChangeBookExpr,
}: PcmSlotCardProps) {
  const pcmBindings = usePcmBindings();

  return (
    <div className="space-y-3 rounded-lg border border-line bg-surface p-3.5 shadow-sm">
      <div className="flex items-center justify-between border-b border-line pb-2">
        <h4 className="text-[12.5px] font-bold text-ink">3. Portfolio (PCM)</h4>
        <span className="font-mono text-[10px] text-ink-muted">
          RiskBudgetedPortfolioConstructionModel
        </span>
      </div>

      <p className="text-[10.5px] text-ink-muted leading-tight">
        Every allocation decision is an expression below: the book policy computes scale,
        capacity, and ordering once per pass; the rules table decides each unit;{" "}
        <code className="text-[10px]">size_expr</code> prices it. Numbers are literals
        inside the ASTs — edit in place, or reset an expr to regenerate from the doc.
      </p>

      {onChangeBookExpr ? (
        <div className="space-y-2 rounded border border-line p-2">
          <span className="text-[10.5px] font-semibold text-ink">
            Book policy{" "}
            <span className="font-normal text-ink-faint">
              evaluated once per pass, before the rules table
            </span>
          </span>
          {(
            [
              ["scale_expr", "Exposure scale → regime.scale", ["acct", "regime"]],
              ["slots_expr", "Position capacity → acct.scaled_max_positions", ["acct", "regime"]],
              ["order_expr", "Fill-order key per unit", ["cand", "hold"]],
            ] as [PcmBookExprKey, string, string[]][]
          ).map(([key, label, nss]) => {
            const expr = bookExprs?.[key] ?? null;
            const exprBindings = pcmBindings.filter((b) => nss.includes(b.ns));
            return (
              <div key={key} className="space-y-1 rounded border border-line/60 bg-surface/50 p-1.5">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[10px] text-ink">
                    {key}{" "}
                    <span className="font-sans text-ink-faint">{label}</span>
                  </span>
                  {expr ? (
                    <button
                      type="button"
                      onClick={() => onChangeBookExpr(key, null)}
                      className="rounded border border-line px-1.5 py-0.5 text-[9px] text-ink-muted hover:bg-surface-sunk"
                      title="Remove the authored expression — the generated default is materialized on save"
                    >
                      reset
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() =>
                        onChangeBookExpr(key, {
                          type: "ref",
                          ns: nss[0],
                          field: key === "order_expr" ? "rank" : "fraction",
                        } as unknown as Record<string, unknown>)
                      }
                      className="rounded border border-line px-1.5 py-0.5 text-[9px] text-ink-muted hover:bg-surface-sunk"
                    >
                      + expr
                    </button>
                  )}
                </div>
                {expr ? (
                  <EditableOperand
                    value={expr as OperandAst}
                    onChange={(n) => onChangeBookExpr(key, n as unknown as Record<string, unknown>)}
                    fields={slotFields}
                    pcmBindings={exprBindings}
                  />
                ) : (
                  <p className="text-[9px] text-ink-faint">
                    none — the generated default is materialized on save.
                  </p>
                )}
              </div>
            );
          })}
        </div>
      ) : null}

      {onChangeSizeExpr ? (
        <div className="space-y-1 rounded border border-line p-2">
          <div className="flex items-center justify-between">
            <span className="text-[10.5px] font-semibold text-ink">
              Base size expression{" "}
              <span className="font-normal text-ink-faint">
                target weight = size_expr × action scale (enter/add)
              </span>
            </span>
            {sizeExpr ? (
              <button
                type="button"
                onClick={() => onChangeSizeExpr(null)}
                className="rounded border border-line px-1.5 py-0.5 text-[9px] text-ink-muted hover:bg-surface-sunk"
                title="Remove the authored size expression — the generated default is materialized on save"
              >
                reset
              </button>
            ) : null}
          </div>
          {sizeExpr ? (
            <EditableOperand
              value={sizeExpr as OperandAst}
              onChange={(n) => onChangeSizeExpr(n as unknown as Record<string, unknown>)}
              fields={slotFields}
              pcmBindings={pcmBindings}
            />
          ) : (
            <div className="flex items-center justify-between">
              <span className="text-[10.5px] text-ink-faint">
                none — the generated risk-budget expression is materialized on save.
              </span>
              <button
                type="button"
                onClick={() =>
                  onChangeSizeExpr({ type: "ref", ns: "acct", field: "portfolio_value" } as unknown as Record<string, unknown>)
                }
                className="rounded border border-line px-1.5 py-0.5 text-[10px] text-ink-muted hover:bg-surface-sunk"
              >
                + size expr
              </button>
            </div>
          )}
        </div>
      ) : null}

      {onChangeRules ? (
        <div>
          <RuleListEditor
            rules={rules ?? []}
            onChangeRules={onChangeRules}
            label="Allocation rules"
            fields={slotFields}
            slot="pcm"
          />
          <RuleTableTester slot="pcm" irId={testIrId ?? null} rules={rules ?? []} />
        </div>
      ) : null}

      <details className="rounded border border-line bg-surface-raised/40">
        <summary className="cursor-pointer px-2.5 py-1.5 text-[10px] font-semibold text-ink-muted select-none">
          Engine plumbing — pyramid geometry, surrogates, regime wiring (not allocation decisions)
        </summary>
        <div className="space-y-2.5 border-t border-line p-2.5">
          {onToggleRegime && onChangeRegimeUses ? (
            <div className="space-y-1.5">
              <label
                className="flex items-center gap-1.5 cursor-pointer"
                title="Wire the weekly CH regime signal into position sizing and scale-in."
              >
                <input
                  type="checkbox"
                  checked={regimeOn}
                  onChange={(e) => onToggleRegime(e.target.checked)}
                  className="rounded border-line"
                />
                <span className="text-[11px] font-semibold text-ink">Regime thermostat</span>
              </label>
              <p className="text-[9px] leading-snug text-ink-faint">
                Data wiring only — the uses select which regime rule rows and scale_expr
                shape generate at save; the thermostat's arithmetic lives in the exprs above.
              </p>
              {regimeOn ? (
                <div className="flex flex-wrap gap-1.5">
                  {(
                    [
                      ["scale_exposure", "PCM scale"],
                      ["skip_pyramid_adds", "Skip pyramid adds"],
                    ] as const
                  ).map(([use, label]) => {
                    const on = regimeUses.includes(use);
                    return (
                      <button
                        key={use}
                        type="button"
                        title={
                          use === "scale_exposure"
                            ? "Generate a regime-scaled scale_expr (else scale_expr is the constant 1.0)"
                            : "Generate the regime_skip_pyramid_adds rule row"
                        }
                        onClick={() =>
                          onChangeRegimeUses(
                            on ? regimeUses.filter((u) => u !== use) : [...regimeUses, use],
                          )
                        }
                        className={
                          on
                            ? "rounded border border-accent bg-accent/10 px-1.5 py-0.5 text-[9.5px] font-semibold text-accent-ink"
                            : "rounded border border-line px-1.5 py-0.5 text-[9.5px] text-ink-muted"
                        }
                      >
                        {label}
                      </button>
                    );
                  })}
                </div>
              ) : null}
            </div>
          ) : null}

          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-[10px] font-semibold text-ink-muted">
              <span>
                Phases{" "}
                <span className="font-normal text-ink-faint">
                  — live: pyr.entry_frac / add_frac read these at runtime
                </span>
              </span>
              <button
                type="button"
                onClick={() =>
                  onChangePhases([
                    ...phases,
                    { name: `phase_${phases.length + 1}`, size_pct: 0.25 },
                  ])
                }
                className="rounded border border-dashed border-emerald-500/50 bg-emerald-500/5 px-1.5 py-0.5 text-[10px] text-emerald-300"
              >
                + Phase
              </button>
            </div>
            <p className="text-[9px] leading-snug text-ink-faint">
              Pyramid state machine — each phase is a fraction of the full risk size
              added at its turn (starter → add → full).
            </p>
            {phases.map((p, fi) => (
              <div
                key={fi}
                className="flex items-center gap-2 rounded border border-line/60 bg-surface-sunk/50 px-2 py-1 text-[11px]"
              >
                <input
                  type="text"
                  value={p.name}
                  onChange={(e) => {
                    const next = [...phases];
                    next[fi] = { ...p, name: e.target.value };
                    onChangePhases(next);
                  }}
                  className="w-24 rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-ink"
                />
                <label className="flex items-center gap-1 text-[10.5px]">
                  <span className="text-ink-muted">Size</span>
                  <input
                    type="number"
                    step="0.05"
                    min="0"
                    max="1"
                    value={p.size_pct}
                    onChange={(e) => {
                      const next = [...phases];
                      next[fi] = { ...p, size_pct: parseFloat(e.target.value) || 0 };
                      onChangePhases(next);
                    }}
                    className="w-16 rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-ink text-right"
                  />
                </label>
                <button
                  type="button"
                  onClick={() => onChangePhases(phases.filter((_, i) => i !== fi))}
                  className="ml-auto text-[12px] text-ink-faint hover:text-danger"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-1.5 cursor-pointer text-[11px] font-bold text-ink">
                <input
                  type="checkbox"
                  checked={enableSurrogates}
                  onChange={(e) => onChangeEnableSurrogates?.(e.target.checked)}
                  className="rounded border-line"
                />
                <span>Route Eligible Stocks to Leveraged ETF Surrogates</span>
              </label>
              <span className="rounded bg-accent/10 px-1.5 py-0.5 text-[9.5px] font-mono text-accent-ink">
                Capital-Efficiency Layer
              </span>
            </div>
            <p className="text-[10px] text-ink-faint leading-tight">
              Execution routing, not a decision — an insight on an underlying routes
              execution to its leveraged ETF surrogate (NVDL 2x, TSLL 2x, SOXL 3x).
            </p>
            {enableSurrogates && (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2 pt-1 border-t border-line/50">
                <div className="space-y-1 rounded border border-line/60 bg-surface/50 p-2">
                  <span className="block text-[10px] font-semibold text-ink">Sizing mode</span>
                  <select
                    value={surrogateSizingMode}
                    onChange={(e) =>
                      onChangeSurrogateSizingMode?.(
                        e.target.value as "dollar_risk_parity" | "full_notional",
                      )
                    }
                    className="block w-full rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[10.5px] text-ink"
                  >
                    <option value="dollar_risk_parity">Dollar Risk Parity (1/L Weight - Recommended)</option>
                    <option value="full_notional">Full Notional (Equal Nominal Capital)</option>
                  </select>
                  <p className="text-[9px] leading-snug text-ink-faint">
                    Dollar Risk Parity halves 2x surrogate weight to maintain identical 1R dollar risk while freeing up 50% cash.
                  </p>
                </div>
                <UnitNumberField
                  layout="card"
                  label="Min Surrogate ADV ($)"
                  hint="Minimum 20-day Average Daily Volume required for surrogate execution. If surrogate ADV is below this, fallback to underlying stock."
                  value={minSurrogateAdv}
                  onChange={onChangeMinSurrogateAdv ?? (() => {})}
                  unit="$"
                  displayScale={1}
                  step={1000000}
                  min={1000000}
                  max={50000000}
                />
              </div>
            )}
          </div>
        </div>
      </details>
    </div>
  );
}
