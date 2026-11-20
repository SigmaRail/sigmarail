import type { ExitTranche, SlotExpr } from "../strategy/StrategyDocument";
import type { ScreenField } from "../../types";
import type { OperandAst, RuleSpec } from "../../lib/rulesAst";
import { formulaText } from "../../lib/rulesAst";
import { SlotBoolExprRow } from "./SlotBoolExprRow";
import { UnitNumberField } from "./UnitNumberField";
import { RuleListEditor } from "./RuleListEditor";
import { RuleTableTester } from "./RuleTableTester";
import { EditableOperand } from "./ExprPillEditor";
import { usePositionBindings } from "../../lib/slotFieldCatalog";
import { Card } from "@sb/webapp-core/components/ui/card";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Checkbox } from "@sb/webapp-core/components/forms/checkbox";

interface RiskSlotCardProps {
  tranches: ExitTranche[];
  onChangeTranches: (next: ExitTranche[]) => void;
  trailingStopPct: number;
  onChangeTrailingStopPct: (v: number) => void;
  maxHoldDays: number;
  onChangeMaxHoldDays: (v: number) => void;
  atrStopMultiplier: number;
  onChangeAtrStopMultiplier: (v: number) => void;
  maxStopLossPct: number;
  onChangeMaxStopLossPct: (v: number) => void;
  useAtrStops: boolean;
  onChangeUseAtrStops: (v: boolean) => void;
  breakevenTimeStopDays: number;
  onChangeBreakevenTimeStopDays: (v: number) => void;
  breakevenRTrigger: number;
  onChangeBreakevenRTrigger: (v: number) => void;
  stopCooldownDays: number;
  onChangeStopCooldownDays: (v: number) => void;
  slotFields?: ScreenField[];
  skipTimeStopExpr?: SlotExpr | null;
  onChangeSkipTimeStopExpr?: (v: SlotExpr | null) => void;
  /** Ordered rule AST (Phase 1, C-FW-RULES) — compiles to Risk Parameters.rules. */
  rules?: RuleSpec[];
  onChangeRules?: (next: RuleSpec[]) => void;
  /** Initial-stop Operand AST (C-VERA-EXPR-V2) — compiles to Risk Parameters.init_stop. */
  initStop?: Record<string, unknown> | null;
  onChangeInitStop?: (next: Record<string, unknown> | null) => void;
  /** Saved spec id — enables the rule-table preview tester. */
  testIrId?: string | null;
}

export function RiskSlotCard({
  tranches,
  onChangeTranches,
  trailingStopPct,
  onChangeTrailingStopPct,
  maxHoldDays,
  onChangeMaxHoldDays,
  atrStopMultiplier,
  onChangeAtrStopMultiplier,
  maxStopLossPct,
  onChangeMaxStopLossPct,
  useAtrStops,
  onChangeUseAtrStops,
  breakevenTimeStopDays,
  onChangeBreakevenTimeStopDays,
  breakevenRTrigger,
  onChangeBreakevenRTrigger,
  stopCooldownDays,
  onChangeStopCooldownDays,
  slotFields = [],
  skipTimeStopExpr,
  onChangeSkipTimeStopExpr,
  rules = [],
  onChangeRules,
  initStop = null,
  onChangeInitStop,
  testIrId,
}: RiskSlotCardProps) {
  const t1 = tranches[0] ?? { trigger_r: 2.5, sell_pct: 0.2 };
  const t2 = tranches[1] ?? { trigger_r: 4.5, sell_pct: 0.33 };
  const t3 = tranches[2] ?? { trigger_r: 8.0, sell_pct: 0.33 };
  // C-FW-RULES: once the spec carries rules, defaults no longer consume the
  // tranche/time-stop/weight-cap knobs — they are inert and must not fake
  // control. Pre-rule protective layers stay live (ATR stop, trail, cooldown).
  const hasRules = onChangeRules != null && rules.length > 0;
  // C-VERA-EXPR-V2: when the spec carries an init_stop Operand AST the runtime
  // evaluates it at fill — the ATR/max-stop knobs are generation inputs baked
  // into that expression, so they are inert and hidden while the AST exists.
  const hasInitStop = initStop != null;
  const posBindings = usePositionBindings();

  function setTranche(i: number, patch: Partial<ExitTranche>) {
    const next = [t1, t2, t3].map((t, idx) => (idx === i ? { ...t, ...patch } : t));
    onChangeTranches(next);
  }

  return (
    <Card className="space-y-3 p-3.5 shadow-sm">
      {onChangeRules ? (
        <>
          <RuleListEditor
            label="Exit rules"
            rules={rules}
            onChangeRules={onChangeRules}
            fields={slotFields}
          />
          <RuleTableTester slot="risk" irId={testIrId ?? null} rules={rules} />
        </>
      ) : null}

      {!hasRules ? (
        <div className="rounded border border-accent/40 bg-accent/5 p-2.5 space-y-2.5">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            {([t1, t2, t3] as const).map((t, i) => (
              <div key={i} className="space-y-1.5 rounded border border-line/60 bg-surface/50 p-2">
                <span className="text-[10px] font-semibold text-ink">T{i + 1}</span>
                <UnitNumberField
                  layout="card"
                  label="Trigger"
                  hint={`Profit target in R for tranche ${i + 1}.`}
                  value={t.trigger_r}
                  onChange={(v) => setTranche(i, { trigger_r: v })}
                  unit="R"
                  step={0.5}
                  min={i === 0 ? 1.5 : i === 1 ? 3 : 5}
                  max={i === 0 ? 4 : i === 1 ? 7 : 12}
                  inputClassName="w-14"
                />
                <UnitNumberField
                  layout="card"
                  label="Sell"
                  hint={`Share of the full position sold at the T${i + 1} trigger.`}
                  value={t.sell_pct ?? 0}
                  onChange={(v) => setTranche(i, { sell_pct: v })}
                  unit="%"
                  displayScale={100}
                  step={0.01}
                  min={0.05}
                  max={0.5}
                  inputClassName="w-14"
                />
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="rounded border border-accent/40 bg-accent/5 p-2.5 space-y-2.5">
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
          {!hasRules ? (
            <UnitNumberField
              layout="card"
              label="Chandelier trail (under high)"
              hint="Runner stop trails this percent below the highest price since entry — sells into weakness only as a last resort."
              value={trailingStopPct}
              onChange={onChangeTrailingStopPct}
              unit="%"
              displayScale={100}
              step={0.01}
              min={0.08}
              max={0.25}
            />
          ) : null}
          {!hasRules ? (
            <UnitNumberField
              layout="card"
              label="Max hold"
              hint="Hard time exit: any position older than this many trading days is closed regardless of P/L."
              value={maxHoldDays}
              onChange={onChangeMaxHoldDays}
              unit="d"
              step={1}
              min={15}
              max={120}
              inputClassName="w-16"
            />
          ) : null}
          {hasInitStop ? (
            <div className="col-span-full space-y-1 rounded border border-line/60 bg-surface/50 p-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] font-semibold text-ink">
                  Initial stop expression
                </span>
                {onChangeInitStop ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-7 px-2 text-[10px]"
                    title="Clear the init_stop AST so the ATR/max-stop knobs become live again — the next save re-materializes the default expression from them."
                    onClick={() => onChangeInitStop(null)}
                  >
                    Reset to knobs
                  </Button>
                ) : null}
              </div>
              <div className="flex flex-wrap items-center gap-1" title={formulaText(initStop as OperandAst)}>
                <span className="font-mono text-[10px] text-ink-muted">init_stop =</span>
                {onChangeInitStop ? (
                  <EditableOperand
                    value={initStop as OperandAst}
                    onChange={(n) => onChangeInitStop(n as unknown as Record<string, unknown>)}
                    fields={slotFields}
                    posBindings={posBindings}
                    posContext="init"
                  />
                ) : (
                  <code className="text-[10px] text-ink break-all">
                    {formulaText(initStop as OperandAst)}
                  </code>
                )}
              </div>
            </div>
          ) : null}
          {!hasInitStop ? (
            <div className="space-y-1.5 rounded border border-line/60 bg-surface/50 p-2">
              <div title="Place the initial protective stop at ATR × multiplier under entry instead of a fixed percent.">
                <Checkbox
                  checked={useAtrStops}
                  onCheckedChange={(checked) => onChangeUseAtrStops(checked === true)}
                  label="ATR stop after fill"
                  className="text-[10.5px]"
                />
              </div>
            </div>
          ) : null}
          {!hasInitStop ? (
            <UnitNumberField
              layout="card"
              label="Risk ATR"
              hint="Stop distance = this many ATRs below entry (when ATR stop is on)."
              value={atrStopMultiplier}
              onChange={onChangeAtrStopMultiplier}
              unit="×"
              step={0.1}
              min={1}
              max={4}
              inputClassName="w-14"
            />
          ) : null}
          {!hasInitStop ? (
            <UnitNumberField
              layout="card"
              label="Max stop"
              hint="Clamp on the ATR stop distance — no stop wider than this percent, no matter the volatility."
              value={maxStopLossPct}
              onChange={onChangeMaxStopLossPct}
              unit="%"
              displayScale={100}
              step={0.01}
              min={0.02}
              max={0.12}
            />
          ) : null}
          {!hasRules ? (
            <UnitNumberField
              layout="card"
              label="Time-stop days"
              hint="If the trade hasn’t reached the breakeven R trigger within this many days, exit the full position — capital rotation rule."
              value={breakevenTimeStopDays}
              onChange={onChangeBreakevenTimeStopDays}
              unit="d"
              step={1}
              min={3}
              max={21}
              inputClassName="w-16"
            />
          ) : null}
          {!hasRules ? (
            <UnitNumberField
              layout="card"
              label="Breakeven at"
              hint="Once the trade reaches this R-multiple, the stop moves up to the entry price — after that the worst case is roughly scratch."
              value={breakevenRTrigger}
              onChange={onChangeBreakevenRTrigger}
              unit="R"
              step={0.25}
              min={0.5}
              max={3}
              inputClassName="w-14"
            />
          ) : null}
          {!hasRules ? (
            <UnitNumberField
              layout="card"
              label="Stop-out cooldown"
              hint="After a name is stopped out, re-entries are suppressed for this many days (prevents churn on the same setup)."
              value={stopCooldownDays}
              onChange={onChangeStopCooldownDays}
              unit="d"
              step={1}
              min={0}
              max={30}
              inputClassName="w-16"
            />
          ) : null}
        </div>
      </div>


      {!hasRules && onChangeSkipTimeStopExpr && slotFields.length > 0 ? (
        <SlotBoolExprRow
          label="Skip time-stop if"
          hint="Condition (over measures / L7, plus pos.*) under which the breakeven time-stop does not fire. Missing columns fail closed — the time-stop applies."
          fields={slotFields}
          value={skipTimeStopExpr}
          onChange={onChangeSkipTimeStopExpr}
        />
      ) : null}

    </Card>
  );
}
