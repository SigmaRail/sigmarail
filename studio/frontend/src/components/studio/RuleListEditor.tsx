import { useState } from "react";
import type { RuleSpec, RuleAction, ActionMeta, ActionTypeId, OperandAst } from "../../lib/rulesAst";
import type { ScreenField } from "../../types";
import { usePcmBindings, usePositionBindings } from "../../lib/slotFieldCatalog";
import {
  ACTION_META,
  boolText,
  catalogForSlot,
  emptyRule,
  formatAction,
  isActionTypeId,
  metaForAction,
  ruleKey,
} from "../../lib/rulesAst";
import { cn } from "../../lib/utils";
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
      <select
        value={action.type}
        onChange={(e) => onChange(defaultAction(e.target.value as ActionTypeId, slot))}
        className="rounded border border-line bg-surface px-1 py-0.5 text-[10px] font-semibold text-ink"
        title={meta?.hint}
      >
        {catalog.map((a: ActionMeta) => (
          <option key={a.id} value={a.id}>
            {a.label}
            {a.terminal ? " ■" : " ▫"}
          </option>
        ))}
        {/* Stored foreign-slot actions still render selectable (can't be picked anew). */}
        {!catalog.some((a) => a.id === action.type) ? (
          <option value={action.type}>{action.type} (foreign)</option>
        ) : null}
      </select>
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
          <input
            type="number"
            min={0.01}
            max={1}
            step={0.01}
            value={action.fraction ?? 1}
            onChange={(e) =>
              onChange({ ...action, fraction: Number(e.target.value) } as RuleAction)
            }
            className="w-14 rounded border border-line bg-surface px-1 py-0.5 text-[10px] text-ink"
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
              <input
                type="number"
                step="any"
                value={(action as Record<string, unknown>)[key] as number | undefined ?? 0}
                onChange={(e) =>
                  onChange({ ...action, [key]: Number(e.target.value) } as RuleAction)
                }
                className="w-14 rounded border border-line bg-surface px-1 py-0.5 text-[10px] text-ink"
              />
            </label>
          ))}
        </>
      ) : null}
      {action.type === "ratchet_stop" ? (
        <select
          value={action.mode ?? "max"}
          onChange={(e) => onChange({ ...action, mode: e.target.value as "max" | "set" })}
          className="rounded border border-line bg-surface px-1 py-0.5 text-[10px] text-ink"
        >
          <option value="max">max</option>
          <option value="set">set</option>
        </select>
      ) : null}
      {action.type === "arm_cooldown" ? (
        <label className="flex items-center gap-1 text-[10px] text-ink-muted">
          days
          <input
            type="number"
            min={0}
            step={1}
            value={action.days ?? 0}
            onChange={(e) => onChange({ ...action, days: Number(e.target.value) } as RuleAction)}
            className="w-14 rounded border border-line bg-surface px-1 py-0.5 text-[10px] text-ink"
          />
        </label>
      ) : null}
      {action.type === "set_flag" ? (
        <label className="flex items-center gap-1 text-[10px] text-ink-muted">
          flag
          <input
            type="text"
            value={action.flag ?? ""}
            onChange={(e) => onChange({ ...action, flag: e.target.value } as RuleAction)}
            placeholder="tranche1_taken"
            className="w-36 rounded border border-line bg-surface px-1 py-0.5 font-mono text-[10px] text-ink"
          />
        </label>
      ) : null}
      <button
        type="button"
        onClick={onRemove}
        title="Remove action"
        className="ml-auto rounded border border-line px-1 py-0.5 text-[9px] text-ink-muted hover:bg-surface-sunk"
      >
        ✕
      </button>
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
      <div className={cn("rounded border border-dashed border-line p-2", className)}>
        <div className="flex items-center justify-between">
          <span className="text-[10.5px] text-ink-faint">
            {label}: none — the generated ladder is materialized into the spec on save.
          </span>
          <button
            type="button"
            onClick={() => onChangeRules([emptyRule(0, slot)])}
            className="rounded border border-line px-1.5 py-0.5 text-[10px] text-ink-muted hover:bg-surface-sunk"
          >
            + rule
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={cn("space-y-1.5 rounded border border-line p-2", className)}>
      <div className="flex items-center justify-between">
        <span className="text-[10.5px] font-semibold text-ink">
          {label}{" "}
          <span className="font-normal text-ink-faint">
            (first match wins · ■ terminal)
          </span>
        </span>
        <div className="flex items-center gap-1">
          {jsonEdit !== null ? (
            <>
              <button
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
                className="rounded border border-line px-1.5 py-0.5 text-[10px] text-ink hover:bg-surface-sunk"
              >
                apply
              </button>
              <button
                type="button"
                onClick={() => setJsonEdit(null)}
                className="rounded border border-line px-1.5 py-0.5 text-[10px] text-ink-muted hover:bg-surface-sunk"
              >
                cancel
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={() =>
                  setExpanded(
                    expanded.size === rules.length
                      ? new Set()
                      : new Set(rules.map((_, i) => i)),
                  )
                }
                className="rounded border border-line px-1.5 py-0.5 text-[10px] text-ink-muted hover:bg-surface-sunk"
                title={expanded.size === rules.length ? "Collapse all rules" : "Expand all rules"}
              >
                {expanded.size === rules.length ? "collapse" : "expand"}
              </button>
              <button
                type="button"
                onClick={() => setJsonEdit(JSON.stringify(rules, null, 2))}
                className="rounded border border-line px-1.5 py-0.5 text-[10px] text-ink-muted hover:bg-surface-sunk"
                title="Edit raw rule JSON"
              >
                json
              </button>
              <button
                type="button"
                onClick={addRule}
                className="rounded border border-line px-1.5 py-0.5 text-[10px] text-ink-muted hover:bg-surface-sunk"
              >
                + rule
              </button>
            </>
          )}
        </div>
      </div>

      {jsonEdit !== null ? (
        <textarea
          value={jsonEdit}
          onChange={(e) => setJsonEdit(e.target.value)}
          rows={Math.min(20, jsonEdit.split("\n").length + 1)}
          className="w-full rounded border border-line bg-surface-sunk p-1.5 font-mono text-[10px] text-ink"
          spellCheck={false}
        />
      ) : (
        rules.map((rule, i) => {
          const isOpen = expanded.has(i);
          const fireSummary = rule.then
            .map((a) => formatAction(a as RuleAction))
            .join(" → ");
          if (!isOpen) {
            return (
              <div
                key={ruleKey(rule, i)}
                className="flex items-center gap-1.5 rounded border border-line bg-surface-raised/40 px-1.5 py-1"
              >
                <button
                  type="button"
                  onClick={() => toggleExpanded(i)}
                  className="text-[10px] text-ink-muted hover:text-ink"
                  title="Expand rule"
                  aria-label={`expand ${rule.name}`}
                >
                  ▸
                </button>
                <span className="w-6 text-right font-mono text-[9px] text-ink-faint">
                  {rule.priority ?? 0}
                </span>
                <span
                  className="truncate font-mono text-[10px] font-semibold text-ink"
                  title={rule.description ?? undefined}
                >
                  {rule.name}
                </span>
                <span className="truncate text-[10px] text-ink-muted" title={boolText(rule.when)}>
                  {boolText(rule.when)}
                </span>
                <span className="ml-auto shrink-0 text-[10px] text-info">
                  → {fireSummary || "—"}
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
              <button
                type="button"
                onClick={() => toggleExpanded(i)}
                className="text-[10px] text-ink-muted hover:text-ink"
                title="Collapse rule"
                aria-label={`collapse ${rule.name}`}
              >
                ▾
              </button>
              <ReorderButtons
                canUp={i > 0}
                canDown={i < rules.length - 1}
                onUp={() => move(i, -1)}
                onDown={() => move(i, 1)}
              />
              <input
                type="text"
                value={rule.name}
                onChange={(e) => patchRule(i, { name: e.target.value })}
                className="w-32 rounded border border-line bg-surface px-1 py-0.5 font-mono text-[10px] font-semibold text-ink"
                placeholder="name"
              />
              {showPriority && (
                <label className="flex items-center gap-1 text-[10px] text-ink-muted">
                  pri
                  <input
                    type="number"
                    step={1}
                    value={rule.priority ?? 0}
                    onChange={(e) => patchRule(i, { priority: Number(e.target.value) })}
                    className="w-12 rounded border border-line bg-surface px-1 py-0.5 text-[10px] text-ink"
                  />
                </label>
              )}
              <label
                className="flex items-center gap-1 text-[10px] text-ink-muted"
                title="Fire at most once per position (tracked via __rule.<name>.fired)"
              >
                <input
                  type="checkbox"
                  checked={rule.once}
                  onChange={(e) => patchRule(i, { once: e.target.checked })}
                  className="rounded border-line"
                />
                once
              </label>
              <input
                type="text"
                value={rule.tag ?? ""}
                onChange={(e) => patchRule(i, { tag: e.target.value || null })}
                className="w-24 rounded border border-line bg-surface px-1 py-0.5 text-[10px] text-ink-muted"
                placeholder="tag"
              />
              <button
                type="button"
                onClick={() => onChangeRules(rules.filter((_, idx) => idx !== i))}
                className="ml-auto rounded border border-line px-1 py-0.5 text-[9px] text-ink-muted hover:bg-surface-sunk"
                title="Remove rule"
              >
                ✕
              </button>
            </div>
            <input
              type="text"
              value={rule.description ?? ""}
              onChange={(e) => patchRule(i, { description: e.target.value || null })}
              placeholder="what this rule is for…"
              title="Rule intent — display-only; never affects evaluation"
              aria-label="rule description"
              spellCheck={false}
              className="w-full rounded border border-transparent bg-transparent px-1 py-0.5 text-[10px] italic text-ink-muted placeholder:text-ink-faint hover:border-line focus:border-line focus:bg-surface"
            />
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
              <button
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
                className="rounded border border-dashed border-line px-1.5 py-0.5 text-[10px] text-ink-muted hover:bg-surface-sunk"
              >
                + action
              </button>
            </div>
            <p className="text-[9.5px] text-ink-faint">
              on fire: {fireSummary || "—"}
            </p>
          </div>
          );
        })
      )}
    </div>
  );
}
