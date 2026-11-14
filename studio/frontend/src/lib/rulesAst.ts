/**
 * Rule/Action AST (Phase 1) — client-side mirror of `vera_lab/ir/rules.py`
 * (C-FW-RULES). Action set: exit, trim, ratchet_stop, cap_weight,
 * arm_cooldown, set_flag. Anything else is a lint error (E205) at save time.
 */

export type ActionTypeId =
  | "exit"
  | "trim"
  | "ratchet_stop"
  | "cap_weight"
  | "arm_cooldown"
  | "set_flag"
  // C-FW-RULES Phase 2 — PCM allocation actions (PortfolioConstruction slot).
  | "enter"
  | "add"
  | "skip"
  | "resize"
  | "displace";

export type OperandAst =
  | { type: "col"; name: string }
  // Runtime position binding (C-VERA-EXPR-V2) — resolves a field of the open
  // position context (entry/r/current_stop/…), not a screener row column.
  // Replaces the legacy `{"type":"col","name":"__position.<field>"}` spelling.
  | { type: "pos"; field: string }
  // Namespaced runtime binding — the general form (cand/hold/acct/pyr/regime
  // inside PCM rules + size_expr; ns="pos" is the same binding as `pos`).
  | { type: "ref"; ns: string; field: string }
  | { type: "lit"; value: number | string | boolean }
  | { type: "formula"; op: "+" | "-" | "*" | "/"; args: OperandAst[] }
  // C-VERA-EXPR-V2: aggregate + piecewise operands (min/max n-ary, abs unary,
  // clamp ternary, cond piecewise over a bool `when`).
  | { type: "min"; args: OperandAst[] }
  | { type: "max"; args: OperandAst[] }
  | { type: "abs"; arg: OperandAst }
  | { type: "clamp"; value: OperandAst; min: OperandAst; max: OperandAst }
  | {
      type: "cond";
      when: Record<string, unknown>;
      then: OperandAst;
      otherwise: OperandAst;
    };

export type RuleAction =
  | ({ type: "exit" } & Partial<{ fraction: number }>)
  | ({ type: "trim" } & Partial<{ fraction: number }>)
  | ({ type: "ratchet_stop" } & Partial<{ to: OperandAst; mode: "max" | "set" }>)
  | ({ type: "cap_weight" } & Partial<{ to: OperandAst }>)
  | ({ type: "arm_cooldown" } & Partial<{ days: number }>)
  | ({ type: "set_flag" } & Partial<{ flag: string }>)
  // PCM actions (C-FW-RULES Phase 2) — PortfolioConstruction slot only.
  | ({ type: "enter" } & Partial<{ size_scale: OperandAst }>)
  | ({ type: "add" } & Partial<{ size_scale: OperandAst }>)
  | ({ type: "skip" })
  | ({ type: "resize" } & Partial<{ to: OperandAst }>)
  | ({ type: "displace" } & Partial<{
      min_incumbent_days: number;
      max_incumbent_r: number;
      immune_rs: number;
      max_per_day: number;
    }>);

export type RuleSpec = {
  name: string;
  priority: number;
  once: boolean;
  when: Record<string, unknown>;
  then: RuleAction[];
  tag?: string | null;
  /** Human-readable intent — display-only, never affects evaluation. */
  description?: string | null;
};

export type ActionMeta = {
  id: ActionTypeId;
  label: string;
  terminal: boolean;
  fields: readonly string[];
  hint: string;
};

/** Phase 1 catalog — mirrors ACTION_TERMINAL in vera_lab/ir/rules.py. */
export const ACTION_CATALOG: readonly ActionMeta[] = [
  {
    id: "exit",
    label: "Exit",
    terminal: true,
    fields: ["fraction"],
    hint: "Liquidate the position (fraction 1.0) and stop evaluating rules.",
  },
  {
    id: "trim",
    label: "Trim",
    terminal: true,
    fields: ["fraction"],
    hint: "Sell `fraction` of the position (keeps the rest) and stop evaluating rules.",
  },
  {
    id: "ratchet_stop",
    label: "Ratchet Stop",
    terminal: false,
    fields: ["to", "mode"],
    hint: "Move the protective stop to the evaluated level (max = never loosen).",
  },
  {
    id: "cap_weight",
    label: "Cap Weight (deprecated)",
    terminal: false,
    fields: ["to"],
    hint: "Deprecated — still evaluated for stored specs. New specs cap position weight in PCM (max_position_weight drift scan).",
  },
  {
    id: "arm_cooldown",
    label: "Arm Cooldown",
    terminal: false,
    fields: ["days"],
    hint: "Block re-entry for N calendar days after this rule fires.",
  },
  {
    id: "set_flag",
    label: "Set Flag",
    terminal: false,
    fields: ["flag"],
    hint: "Raise a named position flag (e.g. tranche1_taken) that later rules can read as pos.<flag>.",
  },
];

export const ACTION_META: Record<string, ActionMeta> = Object.fromEntries(
  ACTION_CATALOG.map((a) => [a.id, a]),
);

/** PCM allocation actions (C-FW-RULES Phase 2) — PortfolioConstruction slot. */
export const PCM_ACTION_CATALOG: readonly ActionMeta[] = [
  {
    id: "enter",
    label: "Enter",
    terminal: true,
    fields: ["size_scale"],
    hint: "Emit a buy target (size_expr × size_scale) and consume a position slot.",
  },
  {
    id: "add",
    label: "Add",
    terminal: true,
    fields: ["size_scale"],
    hint: "Pyramid add — advances the phase state, then emits size_expr × size_scale.",
  },
  {
    id: "skip",
    label: "Skip",
    terminal: true,
    fields: [],
    hint: "Decide this unit with no target — a gate rule.",
  },
  {
    id: "resize",
    label: "Resize",
    terminal: true,
    fields: ["to"],
    hint: "Emit an absolute weight target for the unit's symbol (0 = flatten).",
  },
  {
    id: "displace",
    label: "Displace",
    terminal: false,
    fields: ["min_incumbent_days", "max_incumbent_r", "immune_rs", "max_per_day"],
    hint: "Flatten the weakest qualifying incumbent to free a slot — the rule's `when` qualifies the challenger; these args qualify the incumbent.",
  },
  {
    id: "arm_cooldown",
    label: "Arm Cooldown",
    terminal: false,
    fields: ["days"],
    hint: "Block re-entry for N calendar days after this rule fires.",
  },
  {
    id: "set_flag",
    label: "Set Flag",
    terminal: false,
    fields: ["flag"],
    hint: "Raise a named flag on the unit's symbol — later rules read it as hold.<flag>.",
  },
];

export const PCM_ACTION_META: Record<string, ActionMeta> = Object.fromEntries(
  PCM_ACTION_CATALOG.map((a) => [a.id, a]),
);

/** All actions (risk ∪ pcm) — for `isActionTypeId` lookups. */
const ALL_ACTION_META: Record<string, ActionMeta> = {
  ...PCM_ACTION_META,
  ...ACTION_META,
};

/** Slot-scoped action catalog — a risk action in a PCM rule fails E205. */
export function catalogForSlot(slot: "risk" | "pcm"): readonly ActionMeta[] {
  return slot === "pcm" ? PCM_ACTION_CATALOG : ACTION_CATALOG;
}

export function metaForAction(type: string, slot: "risk" | "pcm"): ActionMeta | undefined {
  return (slot === "pcm" ? PCM_ACTION_META : ACTION_META)[type];
}

export function isActionTypeId(v: unknown): v is ActionTypeId {
  return typeof v === "string" && v in ALL_ACTION_META;
}

/** Format one action for a compact summary chip, e.g. `trim × 33%`. */
export function formatAction(action: RuleAction): string {
  switch (action.type) {
    case "exit":
      return `exit ${(action.fraction ?? 1) * 100}%`;
    case "trim":
      return `trim × ${Math.round((action.fraction ?? 0) * 100)}%`;
    case "ratchet_stop":
      return `stop → ${formulaText(action.to)} (${action.mode ?? "max"})`;
    case "cap_weight":
      return `cap ≤ ${formulaText(action.to)}`;
    case "arm_cooldown":
      return `cooldown ${action.days ?? 0}d`;
    case "enter":
      return `enter × ${formulaText(action.size_scale)}`;
    case "add":
      return `add × ${formulaText(action.size_scale)}`;
    case "skip":
      return "skip";
    case "resize":
      return `→ ${formulaText(action.to)}`;
    case "displace":
      return `displace weakest (≥${action.min_incumbent_days ?? 0}d, <${action.max_incumbent_r ?? 0}R)`;
    default:
      return (action as { type?: string }).type ?? "?";
  }
}

/** Compact infix rendering of an operand AST for display. */
export function formulaText(op: OperandAst | undefined | null): string {
  if (!op) return "?";
  switch (op.type) {
    case "col":
      return op.name;
    case "pos":
      return `pos.${op.field}`;
    case "ref":
      return `${op.ns}.${op.field}`;
    case "lit":
      return String(op.value);
    case "formula": {
      const joiner = ` ${op.op} `;
      const parts = op.args.map((a) =>
        // Parenthesize nested formulas/functions so `a * 1 - min(...)` can't
        // misread as `(a * 1) - min(...)` — display only, not parsed back.
        a && (a.type === "formula" || a.type === "cond")
          ? `(${formulaText(a)})`
          : formulaText(a),
      );
      return parts.length ? parts.join(joiner) : "?";
    }
    case "min":
      return `min(${op.args.map(formulaText).join(", ")})`;
    case "max":
      return `max(${op.args.map(formulaText).join(", ")})`;
    case "abs":
      return `abs(${formulaText(op.arg)})`;
    case "clamp":
      return `clamp(${formulaText(op.value)}, ${formulaText(op.min)}, ${formulaText(op.max)})`;
    case "cond":
      return `${formulaText(op.then)} if ${boolText(op.when)} else ${formulaText(op.otherwise)}`;
    default:
      return "?";
  }
}

const _CMP_TEXT: Record<string, string> = {
  gt: ">",
  gte: "≥",
  lt: "<",
  lte: "≤",
  eq: "=",
  neq: "≠",
};

/** Compact rendering of a BoolExprItem for `cond` summaries (display only). */
export function boolText(node: Record<string, unknown> | undefined | null): string {
  if (!node || typeof node !== "object") return "?";
  const t = node.type as string;
  if (t === "all" || t === "any") {
    const items = (node.items as Record<string, unknown>[] | undefined) ?? [];
    const joiner = t === "all" ? " ∧ " : " ∨ ";
    const inner = items.map(boolText).join(joiner);
    return items.length > 1 ? `(${inner})` : inner || "?";
  }
  if (t === "not") {
    return `¬${boolText(node.item as Record<string, unknown>)}`;
  }
  if (t in _CMP_TEXT) {
    const l = formulaText(node.left as OperandAst);
    const r = formulaText(node.right as OperandAst);
    return `${l} ${_CMP_TEXT[t]} ${r}`;
  }
  return t ?? "?";
}

/** Parse unknown JSON into RuleSpec[]; silently drops invalid entries (best effort). */
export function parseRules(raw: unknown): RuleSpec[] {
  if (!Array.isArray(raw)) return [];
  const out: RuleSpec[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const r = item as Record<string, unknown>;
    if (typeof r.name !== "string" || !r.name) continue;
    if (!r.when || typeof r.when !== "object") continue;
    const then = Array.isArray(r.then) ? (r.then as RuleAction[]) : [];
    if (!then.length) continue;
    out.push({
      name: r.name,
      priority: typeof r.priority === "number" ? r.priority : 0,
      once: r.once === true,
      when: normalizeBoolAst(r.when) as Record<string, unknown>,
      then: then.map((a) => {
        if (!a || typeof a !== "object") return a;
        const next = { ...a } as Record<string, unknown>;
        if ("to" in next) next.to = normalizeOperandAst(next.to);
        if ("size_scale" in next) next.size_scale = normalizeOperandAst(next.size_scale);
        return next as RuleAction;
      }),
      tag: typeof r.tag === "string" ? r.tag : null,
      description: typeof r.description === "string" ? r.description : null,
    });
  }
  return out;
}

/**
 * Canonicalize the legacy `{"type":"col","name":"__position.<f>"}` spelling into
 * `{"type":"pos","field":<f>}` in place — both evaluate identically at runtime;
 * `pos` is the authored form. Stored specs migrate on their next save.
 */
/** PCM decision-unit namespaces (`ref` operands) — `col __<ns>.<f>` migrates the same way as `__position.`. */
const REF_NAMESPACES = ["cand", "hold", "acct", "pyr", "regime"] as const;

export function normalizeOperandAst(node: unknown): unknown {
  if (Array.isArray(node)) return node.map(normalizeOperandAst);
  if (!node || typeof node !== "object") return node;
  const o = node as Record<string, unknown>;
  if (
    o.type === "col" &&
    typeof o.name === "string" &&
    o.name.startsWith("__position.")
  ) {
    return { type: "pos", field: o.name.slice("__position.".length) };
  }
  if (o.type === "col" && typeof o.name === "string" && o.name.startsWith("__")) {
    const rest = o.name.slice(2);
    const dot = rest.indexOf(".");
    const ns = dot > 0 ? rest.slice(0, dot) : "";
    if ((REF_NAMESPACES as readonly string[]).includes(ns)) {
      return { type: "ref", ns, field: rest.slice(dot + 1) };
    }
  }
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(o)) out[k] = normalizeOperandAst(v);
  return out;
}

/** Same normalization for a BoolExpr root (delegates — `pos` lives in operands). */
export function normalizeBoolAst(node: unknown): unknown {
  return normalizeOperandAst(node);
}

export function rulesToJson(rules: RuleSpec[]): Record<string, unknown>[] {
  return rules.map((r) => ({
    name: r.name,
    priority: r.priority ?? 0,
    once: r.once === true,
    when: r.when,
    then: r.then,
    ...(r.tag ? { tag: r.tag } : {}),
    ...(r.description ? { description: r.description } : {}),
  }));
}

/** Stable id for React keys. */
export function ruleKey(rule: RuleSpec, index: number): string {
  return `${rule.name}#${index}`;
}

/**
 * Well-formed default operand for a pill-editor type switch (morph). Every
 * kind produces a valid node so a click never yields a broken AST.
 */
export function defaultOperand(type: string): OperandAst {
  switch (type) {
    case "col":
      return { type: "col", name: "close" };
    case "pos":
      return { type: "pos", field: "r" };
    case "ref":
      return { type: "ref", ns: "cand", field: "price" };
    case "lit":
      return { type: "lit", value: 1 };
    case "formula":
      return {
        type: "formula",
        op: "*",
        args: [
          { type: "lit", value: 1 },
          { type: "lit", value: 1 },
        ],
      };
    case "min":
      return { type: "min", args: [{ type: "lit", value: 0 }] };
    case "max":
      return { type: "max", args: [{ type: "lit", value: 0 }] };
    case "abs":
      return { type: "abs", arg: { type: "lit", value: 1 } };
    case "clamp":
      return {
        type: "clamp",
        value: { type: "lit", value: 0 },
        min: { type: "lit", value: 0 },
        max: { type: "lit", value: 1 },
      };
    case "cond":
      return {
        type: "cond",
        when: defaultBoolNode("gte"),
        then: { type: "lit", value: 1 },
        otherwise: { type: "lit", value: 0 },
      };
    default:
      return { type: "lit", value: 0 };
  }
}

/** Well-formed default BoolExpr node for pill-editor type morphs / "+ condition". */
export function defaultBoolNode(type: string): Record<string, unknown> {
  if (type === "all" || type === "any") return { type, items: [] };
  if (type === "not") return { type: "not", item: defaultBoolNode("gte") };
  return {
    type: type && type !== "cmp" ? type : "gte",
    left: { type: "pos", field: "r" },
    right: { type: "lit", value: 0 },
  };
}

/** New empty rule for "add rule". */
export function emptyRule(index: number, slot: "risk" | "pcm" = "risk"): RuleSpec {
  if (slot === "pcm") {
    return {
      name: `rule_${index + 1}`,
      priority: 0,
      once: false,
      when: {
        type: "neq",
        left: { type: "ref", ns: "cand", field: "is_new" },
        right: { type: "lit", value: 0 },
      },
      then: [{ type: "enter", size_scale: { type: "lit", value: 1 } }],
      tag: null,
      description: null,
    };
  }
  return {
    name: `rule_${index + 1}`,
    priority: 0,
    once: false,
    when: { type: "gte", left: { type: "pos", field: "r" }, right: { type: "lit", value: 1.0 } },
    then: [{ type: "trim", fraction: 0.5 }],
    tag: null,
    description: null,
  };
}
