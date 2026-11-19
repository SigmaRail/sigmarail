import { useState } from "react";
import type { RuleSpec, RuleAction, ActionMeta, ActionTypeId, OperandAst } from "../../lib/rulesAst";
import type { ScreenField } from "../../types";
import { usePcmBindings, usePositionBindings } from "../../lib/slotFieldCatalog";
import {
  ACTION_META,
  boolText,
  catalogForSlot,
  emptyRule,
  isActionTypeId,
  metaForAction,
  ruleKey,
  summarizeRule,
} from "../../lib/rulesAst";
import { cn } from "../../lib/utils";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Checkbox } from "@sb/webapp-core/components/forms/checkbox";
import { Input } from "@sb/webapp-core/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@sb/webapp-core/components/ui/select";
import { Textarea } from "@sb/webapp-core/components/ui/textarea";
import { ReorderButtons } from "./ReorderButtons";
import { BoolExprEditor, OperandEditor } from "./ExprPillEditor";

type RuleSlot = "risk" | "pcm";

interface RuleListEditorProps {
  rules: RuleSpec[];
  onChangeRules: (next: RuleSpec[]) => void;
  /** Slot label shown in the header, e.g. "Risk rules". */
  label?: string;
  /** Show priorities? (slots that sort by priority — all of them — do). */
  showPriority?: boolean;
  /** Field catalog for screener-column lookup pills (measures + L7). */
  fields?: ScreenField[];
  /** Position context for `pos` operand pickers (risk rules eval live). */
  posContext?: "init" | "live";
  /** Owning slot — scopes the action vocabulary + `ref` bindings (E205). */
  slot?: RuleSlot;
  className?: string;
}

/** Well-formed default for an action-type morph (stale fields never leak — E206). */
function defaultAction(t: ActionTypeId, slot: RuleSlot): RuleAction {
  if (t === "exit" || t === "trim") return { type: t, fraction: 0.5 } as RuleAction;
  if (t === "ratchet_stop")
    return { type: t, to: { type: "pos", field: "entry" }, mode: "max" } as RuleAction;
  if (t === "cap_weight") return { type: t, to: { type: "lit", value: 0.15 } } as RuleAction;
  if (t === "set_flag")
    return { type: t, flag: slot === "pcm" ? "block_listed" : "tranche1_taken" } as RuleAction;
  if (t === "arm_cooldown") return { type: t, days: 10 } as RuleAction;
  if (t === "enter")
    return {
      type: t,
      size_scale: { type: "ref", ns: "pyr", field: "entry_frac" },
    } as RuleAction;
  if (t === "add")
    return {
      type: t,
      size_scale: { type: "ref", ns: "pyr", field: "add_frac" },
    } as RuleAction;
  if (t === "resize") return { type: t, to: { type: "lit", value: 0.1 } } as RuleAction;
  if (t === "displace")
    return {
      type: t,
      min_incumbent_days: 5,
      max_incumbent_r: 1.0,
      immune_rs: 95,
      max_per_day: 2,
    } as RuleAction;
  return { type: "skip" } as RuleAction;
}

function ActionRow({
  action,
  index,
  onChange,
  onRemove,
  fields,
  posBindings,
  posContext,
  pcmBindings,
  slot,
}: {
  action: RuleAction;
  index: number;
  onChange: (next: RuleAction) => void;
  onRemove: () => void;
  fields?: ScreenField[];
  posBindings?: ReturnType<typeof usePositionBindings>;
  posContext?: "init" | "live";
  pcmBindings?: ReturnType<typeof usePcmBindings>;
  slot: RuleSlot;
}) {
  const catalog = catalogForSlot(slot);
  const meta = isActionTypeId(action.type) ? metaForAction(action.type, slot) ?? ACTION_META[action.type] : undefined;
  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded border border-line bg-surface-sunk px-1.5 py-1">
      <span className="font-mono text-[10px] text-ink-muted">{index + 1}.</span>
      <Select
        value={action.type}
        onValueChange={(value) => onChange(defaultAction(value as ActionTypeId, slot))}
      >
        <SelectTrigger aria-label="Action" title={meta?.hint} className="h-8 w-auto min-w-32 px-2 text-xs font-semibold">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {catalog.map((a: ActionMeta) => (
            <SelectItem key={a.id} value={a.id}>
              {a.label}{a.terminal ? " ■" : " ▫"}
            </SelectItem>
          ))}
          {/* Stored foreign-slot actions still render selectable (can't be picked anew). */}
          {!catalog.some((a) => a.id === action.type) ? (
            <SelectItem value={action.type}>{action.type} (foreign)</SelectItem>
          ) : null}
        </SelectContent>
      </Select>
      {meta && (
        <span
          className={cn(
            "rounded px-1 text-[9px] font-semibold",
            meta.terminal ? "bg-danger/10 text-danger" : "bg-info/10 text-info",
          )}
          title={meta.terminal ? "Terminal — ends rule evaluation" : "Non-terminal"}
        >
          {meta.terminal ? "T" : "n"}
        </span>
      )}
      {action.type === "exit" || action.type === "trim" ? (
        <label className="flex items-center gap-1 text-[10px] text-ink-muted">
          frac
          <Input
            type="number"
            min={0.01}
            max={1}
            step={0.01}
            value={action.fraction ?? 1}
            onChange={(e) =>
              onChange({ ...action, fraction: Number(e.target.value) } as RuleAction)
            }
            aria-label="Action fraction"
            className="h-8 w-16 px-2 py-1 text-xs"
          />
        </label>
      ) : null}
      {action.type === "ratchet_stop" || action.type === "cap_weight" || action.type === "resize" ? (
        <span className="inline-flex items-center gap-1 text-[10px] text-ink-muted">
          to
          <OperandEditor
            value={(action.to ?? null) as OperandAst | null}
            onChange={(to) => onChange({ ...action, to } as RuleAction)}
            fields={fields}
            posBindings={posBindings}
            posContext={posContext}
            pcmBindings={pcmBindings}
          />
        </span>
      ) : null}
      {action.type === "enter" || action.type === "add" ? (
        <span className="inline-flex items-center gap-1 text-[10px] text-ink-muted">
          ×scale
          <OperandEditor
            value={(action.size_scale ?? null) as OperandAst | null}
            onChange={(size_scale) => onChange({ ...action, size_scale } as RuleAction)}
            fields={fields}
            posBindings={posBindings}
            posContext={posContext}
            pcmBindings={pcmBindings}
          />
        </span>
      ) : null}
      {action.type === "displace" ? (
        <>
          {(
            [
              ["min_incumbent_days", "min days"],
              ["max_incumbent_r", "max open R"],
              ["immune_rs", "immune rs"],
              ["max_per_day", "max/day"],
            ] as const
          ).map(([key, lab]) => (
            <label key={key} className="flex items-center gap-1 text-[10px] text-ink-muted">
              {lab}
              <Input
                type="number"
                step="any"
                value={(action as Record<string, unknown>)[key] as number | undefined ?? 0}
                onChange={(e) =>
                  onChange({ ...action, [key]: Number(e.target.value) } as RuleAction)
                }
                aria-label={lab}
                className="h-8 w-16 px-2 py-1 text-xs"
              />
            </label>
          ))}
        </>
      ) : null}
      {action.type === "ratchet_stop" ? (
        <Select
          value={action.mode ?? "max"}
          onValueChange={(value) => onChange({ ...action, mode: value as "max" | "set" })}
        >
          <SelectTrigger aria-label="Stop update mode" className="h-8 w-24 px-2 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="max">max</SelectItem>
            <SelectItem value="set">set</SelectItem>
          </SelectContent>
        </Select>
      ) : null}
      {action.type === "arm_cooldown" ? (
        <label className="flex items-center gap-1 text-[10px] text-ink-muted">
          days
          <Input
            type="number"
            min={0}
            step={1}
            value={action.days ?? 0}
            onChange={(e) => onChange({ ...action, days: Number(e.target.value) } as RuleAction)}
            aria-label="Cooldown days"
            className="h-8 w-16 px-2 py-1 text-xs"
          />
        </label>
      ) : null}
      {action.type === "set_flag" ? (
        <label className="flex items-center gap-1 text-[10px] text-ink-muted">
          flag
          <Input
            type="text"
            value={action.flag ?? ""}
            onChange={(e) => onChange({ ...action, flag: e.target.value } as RuleAction)}
            placeholder="tranche1_taken"
            aria-label="Flag name"
            className="h-8 w-36 px-2 py-1 font-mono text-xs"
          />
        </label>
      ) : null}
      <Button
        type="button"
        onClick={onRemove}
        variant="ghost"
        size="icon"
        title="Remove action"
        aria-label="Remove action"
        className="ml-auto h-8 w-8 text-ink-muted"
      >
        ✕
      </Button>
    </div>
  );
}

export function RuleListEditor({
  rules,
  onChangeRules,
  label = "Ordered rules",
  showPriority = true,
  fields,
  posContext = "live",
  slot = "risk",
  className,
}: RuleListEditorProps) {
  const [jsonEdit, setJsonEdit] = useState<string | null>(null);
  // Rules render collapsed by default — a one-line summary per rule; click ▸
  // to expand into the full pill editor. New rules open expanded.
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const posBindings = usePositionBindings();
  const pcmBindings = usePcmBindings();

  function toggleExpanded(i: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  }

  function addRule() {
    setExpanded((prev) => new Set(prev).add(rules.length));
    onChangeRules([...rules, emptyRule(rules.length, slot)]);
  }

  function patchRule(i: number, patch: Partial<RuleSpec>) {
    onChangeRules(rules.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }

  function move(i: number, dir: -1 | 1) {
    const j = i + dir;
    if (j < 0 || j >= rules.length) return;
    const next = [...rules];
    [next[i], next[j]] = [next[j], next[i]];
    onChangeRules(next);
  }

  if (!rules.length) {
    return (
      <div className={cn("flex items-center justify-between py-1", className)}>
        <span className="text-[10.5px] text-ink-faint">{label}</span>
        <Button
          type="button"
          onClick={addRule}
          variant="outline"
          size="sm"
          className="h-8 px-2 text-xs text-ink-muted"
        >
          + rule
        </Button>
      </div>
    );
  }

  return (
    <div className={cn("space-y-0.5", className)}>
      <div className="flex min-h-8 items-center justify-between gap-2 border-b border-line/60 pb-1">
        <span className="text-[10.5px] font-semibold text-ink">{label}</span>
        <div className="flex items-center gap-1">
          {jsonEdit !== null ? (
            <>
              <Button
                type="button"
                onClick={() => {
                  try {
                    const parsed = JSON.parse(jsonEdit) as RuleSpec[];
                    onChangeRules(parsed);
                  } catch {
                    /* invalid JSON — keep editing */
                  }
                  setJsonEdit(null);
                }}
                variant="outline"
                size="sm"
                className="h-8 px-2 text-xs"
              >
                apply
              </Button>
              <Button
                type="button"
                onClick={() => setJsonEdit(null)}
                variant="ghost"
                size="sm"
                className="h-8 px-2 text-xs text-ink-muted"
              >
                cancel
              </Button>
            </>
          ) : (
            <>
              <Button
                type="button"
                onClick={() =>
                  setExpanded(
                    expanded.size === rules.length
                      ? new Set()
                      : new Set(rules.map((_, i) => i)),
                  )
                }
                variant="outline"
                size="sm"
                className="h-8 px-2 text-xs text-ink-muted"
                title={expanded.size === rules.length ? "Collapse all rules" : "Expand all rules"}
              >
                {expanded.size === rules.length ? "collapse" : "expand"}
              </Button>
              <Button
                type="button"
                onClick={() => setJsonEdit(JSON.stringify(rules, null, 2))}
                variant="outline"
                size="sm"
                className="h-8 px-2 text-xs text-ink-muted"
                title="Edit raw rule JSON"
              >
                json
              </Button>
              <Button
                type="button"
                onClick={addRule}
                variant="outline"
                size="sm"
                className="h-8 px-2 text-xs text-ink-muted"
              >
                + rule
              </Button>
            </>
          )}
        </div>
      </div>

      {jsonEdit !== null ? (
        <Textarea
          value={jsonEdit}
          onChange={(e) => setJsonEdit(e.target.value)}
          rows={Math.min(20, jsonEdit.split("\n").length + 1)}
          className="min-h-32 w-full bg-surface-sunk p-2 font-mono text-xs text-ink"
          spellCheck={false}
        />
      ) : (
        rules.map((rule, i) => {
          const isOpen = expanded.has(i);
          if (!isOpen) {
            return (
              <div
                key={ruleKey(rule, i)}
                className="flex min-w-0 items-center gap-1.5 rounded border border-line bg-surface-raised/40 px-1.5 py-1"
              >
                <Button
                  type="button"
                  onClick={() => toggleExpanded(i)}
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 shrink-0 text-ink-muted"
                  title="Expand rule"
                  aria-label={`expand ${rule.name}`}
                >
                  ▸
                </Button>
                <span className="w-5 shrink-0 text-right font-mono text-[9px] text-ink-faint">
                  {rule.priority ?? 0}
                </span>
                <span className="max-w-36 shrink-0 truncate font-mono text-[10px] font-semibold text-ink">
                  {rule.name}
                </span>
                <span className="min-w-0 flex-1 truncate text-[11px] text-muted-foreground" title={summarizeRule(rule)}>
                  {summarizeRule(rule)}
                </span>
              </div>
            );
          }
          return (
          <div
            key={ruleKey(rule, i)}
            className="space-y-1 rounded border border-line bg-surface-raised/40 p-1.5"
          >
            <div className="flex flex-wrap items-center gap-1.5">
              <Button
                type="button"
                onClick={() => toggleExpanded(i)}
                variant="ghost"
                size="icon"
                className="h-8 w-8 shrink-0 text-ink-muted"
                title="Collapse rule"
                aria-label={`collapse ${rule.name}`}
              >
                ▾
              </Button>
              <ReorderButtons
                canUp={i > 0}
                canDown={i < rules.length - 1}
                onUp={() => move(i, -1)}
                onDown={() => move(i, 1)}
              />
              <Input
                type="text"
                value={rule.name}
                onChange={(e) => patchRule(i, { name: e.target.value })}
                aria-label="Rule name"
                className="h-8 w-32 px-2 py-1 font-mono text-xs font-semibold"
                placeholder="name"
              />
              {showPriority && (
                <label className="flex items-center gap-1 text-[10px] text-ink-muted">
                  pri
                  <Input
                    type="number"
                    step={1}
                    value={rule.priority ?? 0}
                    onChange={(e) => patchRule(i, { priority: Number(e.target.value) })}
                    aria-label="Rule priority"
                    className="h-8 w-16 px-2 py-1 text-xs"
                  />
                </label>
              )}
              <span title="Fire at most once per position (tracked via __rule.<name>.fired)">
                <Checkbox
                  checked={rule.once}
                  onCheckedChange={(checked) => patchRule(i, { once: checked === true })}
                  label="Once"
                  className="min-h-8 px-1 text-ink-muted"
                />
              </span>
              <Input
                type="text"
                value={rule.tag ?? ""}
                onChange={(e) => patchRule(i, { tag: e.target.value || null })}
                aria-label="Rule tag"
                className="h-8 w-28 px-2 py-1 text-xs text-ink-muted"
                placeholder="tag"
              />
              <Button
                type="button"
                onClick={() => onChangeRules(rules.filter((_, idx) => idx !== i))}
                variant="ghost"
                size="icon"
                className="ml-auto h-8 w-8 text-ink-muted"
                title="Remove rule"
                aria-label={`Remove ${rule.name}`}
              >
                ✕
              </Button>
            </div>
            <div className="flex items-start gap-1.5">
              <span className="pt-0.5 text-[10px] text-ink-muted" title={boolText(rule.when)}>
                when:
              </span>
              <BoolExprEditor
                value={rule.when}
                onChange={(when) => patchRule(i, { when })}
                fields={fields}
                posBindings={posBindings}
                posContext={posContext}
                pcmBindings={slot === "pcm" ? pcmBindings : undefined}
              />
            </div>
            <div className="space-y-1">
              {rule.then.map((a, ai) => (
                <ActionRow
                  key={ai}
                  action={a}
                  index={ai}
                  fields={fields}
                  posBindings={posBindings}
                  posContext={posContext}
                  pcmBindings={pcmBindings}
                  slot={slot}
                  onChange={(next) =>
                    patchRule(i, { then: rule.then.map((x, xi) => (xi === ai ? next : x)) })
                  }
                  onRemove={() =>
                    patchRule(i, { then: rule.then.filter((_, xi) => xi !== ai) })
                  }
                />
              ))}
              <Button
                type="button"
                onClick={() =>
                  patchRule(i, {
                    then: [
                      ...rule.then,
                      (slot === "pcm"
                        ? { type: "skip" }
                        : { type: "trim", fraction: 0.5 }) as RuleAction,
                    ],
                  })
                }
                variant="outline"
                size="sm"
                className="h-8 border-dashed px-2 text-xs text-ink-muted"
              >
                + action
              </Button>
            </div>
          </div>
          );
        })
      )}
    </div>
  );
}
