import type { ScreenField } from "../../types";
import type {
  PipelineBindings,
  PolicyRule,
  PolicyRuleRole,
  SlotExpr,
} from "../strategy/StrategyDocument";
import { SlotBoolExprRow } from "./SlotBoolExprRow";

/** Live roles for Studio (all compile + runtime-backed slots). */
export const LIVE_POLICY_ROLES: { role: PolicyRuleRole; label: string; kind: "bool" | "number" }[] =
  [
    { role: "alpha_eligibility", label: "Eligible to shortlist", kind: "bool" },
    { role: "alpha_setup", label: "Setup required for entry", kind: "bool" },
    { role: "alpha_confidence", label: "Confidence ← measure", kind: "number" },
    { role: "pcm_allow_entry", label: "Allow new entry if", kind: "bool" },
    { role: "pcm_scale", label: "PCM size scale", kind: "number" },
    { role: "risk_skip_time_stop", label: "Skip time-stop if", kind: "bool" },
    { role: "risk_allow_pyramid_add", label: "Allow pyramid add if", kind: "bool" },
  ];
const ROLE_LABEL: Record<string, string> = Object.fromEntries(
  LIVE_POLICY_ROLES.map((r) => [r.role, r.label]),
);

/** Sync binding slot fields from policy_rules (bool AND last number wins — UI shows last). */
export function bindingsFromPolicyRules(
  rules: PolicyRule[],
  base?: PipelineBindings | null,
): PipelineBindings {
  const next: PipelineBindings = { ...(base ?? {}) };
  const byRole = new Map<PolicyRuleRole, PolicyRule[]>();
  for (const r of rules) {
    const list = byRole.get(r.role) ?? [];
    list.push(r);
    byRole.set(r.role, list);
  }
  for (const [role, group] of byRole) {
    const last = group[group.length - 1]!;
    const slot = last.slot;
    if (role === "alpha_eligibility") next.alpha_eligibility = slot;
    else if (role === "alpha_setup") next.alpha_setup = slot;
    else if (role === "alpha_confidence") next.alpha_confidence = slot;
    else if (role === "pcm_allow_entry") next.pcm_allow_entry = slot;
    else if (role === "pcm_scale") next.pcm_scale = slot;
    else if (role === "risk_skip_time_stop") next.risk_skip_time_stop = slot;
    else if (role === "risk_allow_pyramid_add") next.risk_allow_pyramid_add = slot;
  }
  // Clear roles with no rules
  const roles = new Set(byRole.keys());
  if (!roles.has("pcm_allow_entry")) next.pcm_allow_entry = null;
  if (!roles.has("pcm_scale")) next.pcm_scale = null;
  if (!roles.has("risk_skip_time_stop")) next.risk_skip_time_stop = null;
  if (!roles.has("risk_allow_pyramid_add")) next.risk_allow_pyramid_add = null;
  return next;
}

/** Upsert a single binding role into policy_rules (keeps other rules). */
export function upsertPolicyRuleForBinding(
  rules: PolicyRule[],
  role: PolicyRuleRole,
  slot: SlotExpr | null,
): PolicyRule[] {
  const without = rules.filter((r) => r.role !== role);
  if (!slot) return without;
  const meta = LIVE_POLICY_ROLES.find((r) => r.role === role);
  return [
    ...without,
    {
      id: role,
      label: meta?.label ?? role,
      role,
      slot,
    },
  ];
}

type Props = {
  rules: PolicyRule[];
  fields: ScreenField[];
  onChange: (next: PolicyRule[]) => void;
};

export function PolicyRulesPanel({ rules, fields, onChange }: Props) {
  function updateRule(index: number, patch: Partial<PolicyRule>) {
    const next = rules.map((r, i) => (i === index ? { ...r, ...patch } : r));
    onChange(next);
  }

  function removeRule(index: number) {
    onChange(rules.filter((_, i) => i !== index));
  }

  function addRule() {
    const used = new Set(rules.map((r) => r.role));
    const pick =
      LIVE_POLICY_ROLES.find((r) => r.kind === "bool" && !used.has(r.role)) ??
      LIVE_POLICY_ROLES[0]!;
    const id = `${pick.role}_${rules.length + 1}`;
    const slot: SlotExpr =
      pick.kind === "bool"
        ? { kind: "bool", where: { type: "eq", left: { type: "col", name: "setup_pass" }, right: { type: "lit", value: 1 } } }
        : {
            kind: "number",
            expr: {
              type: "col",
              name: "conf_scale",
            },
          };
    onChange([
      ...rules,
      { id, label: pick.label, role: pick.role, slot },
    ]);
  }

  return (
    <div className="space-y-3 rounded-lg border border-line bg-surface p-3.5 shadow-sm">
      <div className="flex items-center justify-between border-b border-line pb-2">
        <h4 className="text-[12.5px] font-bold text-ink">Gates &amp; scale</h4>
        <span className="font-mono text-[10px] text-ink-muted">policy_rules SSOT</span>
      </div>
      <p className="text-[10px] text-ink-muted leading-tight">
        Same roles as chips on PCM / Risk above — edit either place. Bool roles AND-merge at
        compile; number roles last-wins. Knobs stay on the cards.
      </p>

      <div className="space-y-2">
        {rules.map((rule, i) => {
          const meta = LIVE_POLICY_ROLES.find((r) => r.role === rule.role);
          const kind = meta?.kind ?? rule.slot.kind;
          return (
            <div
              key={rule.id || `${rule.role}-${i}`}
              className="rounded border border-line bg-surface-raised/30 p-2 space-y-1.5"
            >
              <div className="flex items-center gap-2">
                <span className="font-mono text-[10px] text-ink-faint">{i + 1}.</span>
                <select
                  value={rule.role}
                  onChange={(e) => {
                    const role = e.target.value as PolicyRuleRole;
                    const m = LIVE_POLICY_ROLES.find((r) => r.role === role);
                    updateRule(i, {
                      role,
                      label: m?.label ?? role,
                      slot:
                        m?.kind === "number"
                          ? {
                              kind: "number",
                              expr: rule.slot.expr ?? {
                                type: "col",
                                name: "conf_scale",
                              },
                            }
                          : {
                              kind: "bool",
                              where:
                                rule.slot.where ?? {
                                  type: "eq",
                                  left: { type: "col", name: "setup_pass" },
                                  right: { type: "lit", value: 1 },
                                },
                            },
                    });
                  }}
                  className="flex-1 rounded border border-line bg-surface px-1.5 py-0.5 text-[11px] text-ink"
                >
                  {LIVE_POLICY_ROLES.map((r) => (
                    <option key={r.role} value={r.role}>
                      {r.label}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => removeRule(i)}
                  className="text-[12px] text-ink-faint hover:text-danger"
                  title="Remove rule"
                >
                  ✕
                </button>
              </div>
              {kind === "bool" ? (
                <SlotBoolExprRow
                  label={ROLE_LABEL[rule.role] ?? rule.role}
                  hint="Bool over computed / L7 (+ pos.* for Risk skip)."
                  fields={fields}
                  value={rule.slot.kind === "bool" ? rule.slot : null}
                  onChange={(slot) => {
                    if (!slot) {
                      removeRule(i);
                      return;
                    }
                    updateRule(i, { slot });
                  }}
                />
              ) : (
                <p className="font-mono text-[10px] text-ink-muted break-all">
                  number expr: {JSON.stringify(rule.slot.expr ?? {})}
                </p>
              )}
            </div>
          );
        })}
        {rules.length === 0 ? (
          <p className="text-[10px] text-ink-faint">No policy rules — Champion may use bindings defaults at compile.</p>
        ) : null}
      </div>

      <button
        type="button"
        onClick={addRule}
        className="w-full rounded border border-dashed border-accent/50 bg-accent/5 py-1.5 text-[11px] font-semibold text-accent-ink hover:bg-accent/10"
      >
        + Add rule
      </button>
    </div>
  );
}
