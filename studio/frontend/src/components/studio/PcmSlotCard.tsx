import type { ScreenField } from "../../types";
import type { PyramidPhase } from "../strategy/StrategyDocument";
import type { OperandAst, RuleSpec } from "../../lib/rulesAst";
import type { PcmBookExprKey } from "../../lib/pipelineSlotBindings";
import { usePcmBindings } from "../../lib/slotFieldCatalog";
import { EditableOperand } from "./ExprPillEditor";
import { RuleListEditor } from "./RuleListEditor";
import { RuleTableTester } from "./RuleTableTester";
import { UnitNumberField } from "./UnitNumberField";
import { Card } from "@sb/webapp-core/components/ui/card";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Input } from "@sb/webapp-core/components/ui/input";
import { Checkbox } from "@sb/webapp-core/components/forms/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@sb/webapp-core/components/ui/select";

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
    <Card className="space-y-3 p-3.5 shadow-sm">
      {onChangeBookExpr ? (
        <div className="space-y-2 rounded border border-line p-2">
          <span className="text-[10.5px] font-semibold text-ink">
            Book policy
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
                    <Button
                      type="button"
                      onClick={() => onChangeBookExpr(key, null)}
                      variant="ghost"
                      size="sm"
                      className="h-6 px-1.5 text-[10px]"
                      title="Remove the authored expression — the generated default is materialized on save"
                    >
                      reset
                    </Button>
                  ) : (
                    <Button
                      type="button"
                      onClick={() =>
                        onChangeBookExpr(key, {
                          type: "ref",
                          ns: nss[0],
                          field: key === "order_expr" ? "rank" : "fraction",
                        } as unknown as Record<string, unknown>)
                      }
                      variant="outline"
                      size="sm"
                      className="h-6 px-1.5 text-[10px]"
                    >
                      + expr
                    </Button>
                  )}
                </div>
                {expr ? (
                  <EditableOperand
                    value={expr as OperandAst}
                    onChange={(n) => onChangeBookExpr(key, n as unknown as Record<string, unknown>)}
                    fields={slotFields}
                    pcmBindings={exprBindings}
                  />
                ) : null}
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
              <Button
                type="button"
                onClick={() => onChangeSizeExpr(null)}
                variant="ghost"
                size="sm"
                className="h-6 px-1.5 text-[10px]"
                title="Remove the authored size expression — the generated default is materialized on save"
              >
                reset
              </Button>
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
              <Button
                type="button"
                onClick={() =>
                  onChangeSizeExpr({ type: "ref", ns: "acct", field: "portfolio_value" } as unknown as Record<string, unknown>)
                }
                variant="outline"
                size="sm"
                className="h-7 px-2 text-[10px]"
              >
                + size expr
              </Button>
            </div>
          )}
        </div>
      ) : null}

      {onChangeRules ? (
        <>
          <RuleListEditor
            rules={rules ?? []}
            onChangeRules={onChangeRules}
            label="Allocation rules"
            fields={slotFields}
            slot="pcm"
          />
          <RuleTableTester slot="pcm" irId={testIrId ?? null} rules={rules ?? []} />
        </>
      ) : null}

      <details className="rounded border border-line bg-surface-raised/40">
        <summary className="cursor-pointer px-2.5 py-1.5 text-[10px] font-semibold text-ink-muted select-none">
          Advanced settings
        </summary>
        <div className="space-y-2.5 border-t border-line p-2.5">
          {onToggleRegime && onChangeRegimeUses ? (
            <div className="space-y-1.5">
              <div title="Wire the weekly CH regime signal into position sizing and scale-in.">
                <Checkbox
                  checked={regimeOn}
                  onCheckedChange={(checked) => onToggleRegime(checked === true)}
                  label="Regime thermostat"
                  className="text-[11px] font-semibold"
                />
              </div>
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
                      <Button
                        key={use}
                        type="button"
                        variant={on ? "secondary" : "outline"}
                        size="sm"
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
                        className="h-7 px-2 text-[10px]"
                        aria-pressed={on}
                      >
                        {label}
                      </Button>
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
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 border-dashed px-2 text-[10px]"
                onClick={() =>
                  onChangePhases([
                    ...phases,
                    { name: `phase_${phases.length + 1}`, size_pct: 0.25 },
                  ])
                }
              >
                + Phase
              </Button>
            </div>
            {phases.map((p, fi) => (
              <div
                key={fi}
                className="flex items-center gap-2 rounded border border-line/60 bg-surface-sunk/50 px-2 py-1 text-[11px]"
              >
                <Input
                  type="text"
                  value={p.name}
                  onChange={(e) => {
                    const next = [...phases];
                    next[fi] = { ...p, name: e.target.value };
                    onChangePhases(next);
                  }}
                  className="h-8 w-24 px-2 py-1 font-mono text-xs"
                />
                <label className="flex items-center gap-1 text-[10.5px]">
                  <span className="text-ink-muted">Size</span>
                  <Input
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
                    className="h-8 w-20 px-2 py-1 text-right font-mono text-xs"
                  />
                </label>
                <Button
                  type="button"
                  onClick={() => onChangePhases(phases.filter((_, i) => i !== fi))}
                  variant="ghost"
                  size="sm"
                  className="ml-auto h-8 w-8 p-0 text-muted-foreground"
                  aria-label={`Remove phase ${p.name}`}
                >
                  ✕
                </Button>
              </div>
            ))}
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Checkbox
                checked={enableSurrogates}
                onCheckedChange={(checked) => onChangeEnableSurrogates?.(checked === true)}
                label="Route eligible stocks to leveraged ETF surrogates"
                className="text-[11px] font-bold"
              />
            </div>
            {enableSurrogates && (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2 pt-1 border-t border-line/50">
                <div className="space-y-1 rounded border border-line/60 bg-surface/50 p-2">
                  <span className="block text-[10px] font-semibold text-ink">Sizing mode</span>
                  <Select value={surrogateSizingMode} onValueChange={(value) => onChangeSurrogateSizingMode?.(value as "dollar_risk_parity" | "full_notional")}>
                    <SelectTrigger className="h-9 w-full text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="dollar_risk_parity">Dollar Risk Parity (1/L Weight - Recommended)</SelectItem>
                      <SelectItem value="full_notional">Full Notional (Equal Nominal Capital)</SelectItem>
                    </SelectContent>
                  </Select>
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
    </Card>
  );
}
