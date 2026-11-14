import type { IrWhereNode } from "../types";
import type { PipelineDocument, SlotExpr, Stage } from "../components/strategy/StrategyDocument";
import { extractAppliedFilters, rowsToWhere } from "./irFilters";

export type MeasureInPlay = {
  alias: string;
  stageIndex: number;
  kind: "gate" | "setup";
  /** Gate counts toward screens_hit. */
  shortlist: boolean;
  /** Referenced in alpha_eligibility (gate) or alpha_setup (setup). */
  emit: boolean;
  /** Referenced in alpha_confidence number expr. */
  confidence: boolean;
};

/** Bool payload → Insight = WHERE; number/field expr → Insight = ORDER BY. */
export type MeasurePayloadKind = "bool" | "rank";

export function measurePayloadKind(stage: Stage): MeasurePayloadKind {
  if (stage.mode === "signal") return "bool";
  if (stage.computed_expr) return "rank";
  return "bool";
}

function stageAlias(s: Stage, fallback: string): string {
  const id = (s.id || "").trim();
  return id || fallback;
}

function walkExprCols(node: unknown, out: Set<string>): void {
  if (!node || typeof node !== "object") return;
  const n = node as Record<string, unknown>;
  if (n.type === "col" && typeof n.name === "string") {
    out.add(n.name);
    return;
  }
  if (Array.isArray(n.args)) {
    for (const a of n.args) walkExprCols(a, out);
  }
  if (n.left) walkExprCols(n.left, out);
  if (n.right) walkExprCols(n.right, out);
  if (Array.isArray(n.items)) {
    for (const a of n.items) walkExprCols(a, out);
  }
}

/** Column names referenced by a SlotExpr (bool where or number expr). */
export function slotExprCols(slot: SlotExpr | null | undefined): Set<string> {
  const out = new Set<string>();
  if (!slot) return out;
  if (slot.kind === "bool" && slot.where) walkExprCols(slot.where, out);
  if (slot.kind === "number" && slot.expr) walkExprCols(slot.expr, out);
  return out;
}

/** True when eligibility/setup has an explicit ``alias = 1`` Insight filter clause. */
export function isInsightFilterAlias(
  doc: PipelineDocument,
  alias: string,
  slotKey: "alpha_eligibility" | "alpha_setup" = "alpha_eligibility",
): boolean {
  const slot = doc.bindings?.[slotKey];
  if (!slot || slot.kind !== "bool" || !slot.where) return false;
  const { rows } = extractAppliedFilters(slot.where as IrWhereNode);
  return rows.some((r) => {
    const left = r.left as { type?: string; name?: string } | undefined;
    const right = r.right as { type?: string; value?: unknown } | undefined;
    return (
      r.op === "eq" &&
      left?.type === "col" &&
      left.name === alias &&
      right?.type === "lit" &&
      (right.value === 1 || right.value === true)
    );
  });
}

export function isInsightActive(doc: PipelineDocument, stage: Stage): boolean {
  const alias = stageAlias(stage, "");
  if (!alias) return false;
  if (measurePayloadKind(stage) === "bool") {
    if (stage.mode === "signal") {
      return (
        isInsightFilterAlias(doc, alias, "alpha_setup") ||
        isInsightFilterAlias(doc, "setup_pass", "alpha_setup")
      );
    }
    return isInsightFilterAlias(doc, alias, "alpha_eligibility");
  }
  return isInsightRankAlias(doc, alias);
}

export function listMeasuresInPlay(doc: PipelineDocument): MeasureInPlay[] {
  const stages = doc.stages ?? [];
  const eligCols = slotExprCols(doc.bindings?.alpha_eligibility);
  const setupCols = slotExprCols(doc.bindings?.alpha_setup);
  const confCols = slotExprCols(doc.bindings?.alpha_confidence);
  const out: MeasureInPlay[] = [];
  let gateI = 0;
  for (let i = 0; i < stages.length; i++) {
    const s = stages[i]!;
    if (s.mode === "score" && Boolean(s.as_gate)) {
      const alias = stageAlias(s, `gate_${gateI}`);
      gateI += 1;
      out.push({
        alias,
        stageIndex: i,
        kind: "gate",
        shortlist: s.count_as_signal !== false,
        emit: eligCols.has(alias),
        confidence: confCols.has(alias) || confCols.has("screens_hit") || confCols.has("screens_hit_w"),
      });
    }
  }
  const setupIdx = stages.findIndex(
    (s) =>
      s.mode === "signal" &&
      ((s.id || "") === "setup_pass" || (s.filters?.length ?? 0) > 0),
  );
  if (setupIdx >= 0) {
    const s = stages[setupIdx]!;
    const alias = stageAlias(s, "setup_pass");
    out.push({
      alias,
      stageIndex: setupIdx,
      kind: "setup",
      shortlist: false,
      emit: setupCols.has(alias) || setupCols.has("setup_pass"),
      confidence: confCols.has(alias),
    });
  }
  return out;
}

function toggleColInBoolSlot(
  slot: SlotExpr | null | undefined,
  col: string,
  enable: boolean,
): SlotExpr | null {
  const rows =
    slot?.kind === "bool" && slot.where
      ? extractAppliedFilters(slot.where as IrWhereNode).rows
      : [];
  const filtered = rows.filter((r) => {
    const left = r.left as { type?: string; name?: string } | undefined;
    return !(left?.type === "col" && left.name === col);
  });
  if (!enable) {
    if (!filtered.length) return null;
    return { kind: "bool", where: rowsToWhere(filtered) as Record<string, unknown> };
  }
  const already = rows.some((r) => {
    const left = r.left as { type?: string; name?: string } | undefined;
    return left?.type === "col" && left.name === col;
  });
  if (already) {
    return slot?.kind === "bool" ? slot : { kind: "bool", where: rowsToWhere(rows) as Record<string, unknown> };
  }
  const nextRows = [
    ...filtered,
    {
      id: `mip_${col}`,
      op: "eq" as const,
      left: { type: "col" as const, name: col },
      right: { type: "lit" as const, value: 1 },
    },
  ];
  return { kind: "bool", where: rowsToWhere(nextRows) as Record<string, unknown> };
}

function removeFromAlphaRank(doc: PipelineDocument, alias: string): PipelineDocument {
  const rank = (doc.bindings?.alpha_rank ?? []).filter((a) => a !== alias);
  const dirs = { ...(doc.bindings?.alpha_rank_directions ?? {}) };
  delete dirs[alias];
  return {
    ...doc,
    bindings: {
      ...(doc.bindings ?? {}),
      alpha_rank: rank.length ? rank : null,
      alpha_rank_directions: Object.keys(dirs).length ? dirs : null,
    },
  };
}

/**
 * Insight ✓ by payload type:
 * - bool (filters / setup) → ``alias = 1`` in eligibility/setup (SQL WHERE, drop falses)
 * - rank (number expr / field) → ``alpha_rank`` (SQL ORDER BY)
 */
export function toggleInsightMeasure(
  doc: PipelineDocument,
  stage: Stage,
): PipelineDocument {
  const alias = stageAlias(stage, stage.mode === "signal" ? "setup_pass" : "");
  if (!alias) return doc;
  const kind = measurePayloadKind(stage);

  if (kind === "bool") {
    let next = removeFromAlphaRank(doc, alias);
    if (stage.mode === "signal") {
      const on = isInsightFilterAlias(next, alias, "alpha_setup");
      const slot = toggleColInBoolSlot(next.bindings?.alpha_setup, alias, !on);
      return {
        ...next,
        bindings: { ...(next.bindings ?? {}), alpha_setup: slot },
      };
    }
    const on = isInsightFilterAlias(next, alias, "alpha_eligibility");
    const slot = toggleColInBoolSlot(next.bindings?.alpha_eligibility, alias, !on);
    return {
      ...next,
      bindings: { ...(next.bindings ?? {}), alpha_eligibility: slot },
    };
  }

  let next = doc;
  if (isInsightFilterAlias(doc, alias, "alpha_eligibility")) {
    next = {
      ...doc,
      bindings: {
        ...(doc.bindings ?? {}),
        alpha_eligibility: toggleColInBoolSlot(doc.bindings?.alpha_eligibility, alias, false),
      },
    };
  }
  return toggleInsightRankAlias(next, alias);
}

export function toggleShortlist(
  doc: PipelineDocument,
  stageIndex: number,
): PipelineDocument {
  const stages = doc.stages ?? [];
  const stage = stages[stageIndex];
  if (!stage || stage.mode !== "score" || !stage.as_gate) return doc;
  const nextCount = stage.count_as_signal === false;
  const nextStages = stages.map((st, i) =>
    i === stageIndex ? { ...st, count_as_signal: nextCount } : st,
  );
  return {
    ...doc,
    gate_combine: "count",
    stages: nextStages,
  };
}

export function toggleEmitRole(
  doc: PipelineDocument,
  measure: MeasureInPlay,
): PipelineDocument {
  const enable = !measure.emit;
  if (measure.kind === "setup") {
    const next = toggleColInBoolSlot(doc.bindings?.alpha_setup, measure.alias, enable);
    const setupSlot =
      measure.alias !== "setup_pass" && enable
        ? toggleColInBoolSlot(next, "setup_pass", true)
        : next;
    return {
      ...doc,
      bindings: { ...(doc.bindings ?? {}), alpha_setup: setupSlot },
    };
  }
  const next = toggleColInBoolSlot(doc.bindings?.alpha_eligibility, measure.alias, enable);
  return {
    ...doc,
    bindings: { ...(doc.bindings ?? {}), alpha_eligibility: next },
  };
}

export function confidenceExprForCol(col: string, denom = 5): SlotExpr {
  return {
    kind: "number",
    expr: {
      type: "formula",
      op: "/",
      args: [
        { type: "col", name: col },
        { type: "lit", value: denom },
      ],
    },
  };
}

export function confidenceColRef(col: string): SlotExpr {
  return { kind: "number", expr: { type: "col", name: col } };
}

export function confidencePrimaryCol(slot: SlotExpr | null | undefined): string | null {
  if (!slot || slot.kind !== "number" || !slot.expr) return null;
  const e = slot.expr as Record<string, unknown>;
  if (e.type === "col" && typeof e.name === "string") return e.name;
  if (e.type === "formula" && Array.isArray(e.args)) {
    const a = e.args[0] as Record<string, unknown> | undefined;
    if (a?.type === "col" && typeof a.name === "string") return a.name;
  }
  return null;
}

/** Number / field Insight ✓ → Universe ORDER BY (list order = priority). */
export function toggleInsightRankAlias(
  doc: PipelineDocument,
  alias: string,
): PipelineDocument {
  const stageOrder = (doc.stages ?? [])
    .map((s) => (s.id || "").trim())
    .filter(Boolean);
  let rank = [...(doc.bindings?.alpha_rank ?? [])];
  if (rank.includes(alias)) {
    rank = rank.filter((a) => a !== alias);
  } else {
    rank.push(alias);
  }
  rank.sort((a, b) => {
    const ia = stageOrder.indexOf(a);
    const ib = stageOrder.indexOf(b);
    const sa = ia < 0 ? 10_000 + rank.indexOf(a) : ia;
    const sb = ib < 0 ? 10_000 + rank.indexOf(b) : ib;
    return sa - sb;
  });
  return {
    ...doc,
    gate_combine: "count",
    bindings: {
      ...(doc.bindings ?? {}),
      alpha_rank: rank.length ? rank : null,
    },
  };
}

export function isInsightRankAlias(doc: PipelineDocument, alias: string): boolean {
  return (doc.bindings?.alpha_rank ?? []).includes(alias);
}

export function rankDirection(
  doc: PipelineDocument,
  alias: string,
): "asc" | "desc" {
  const d = doc.bindings?.alpha_rank_directions?.[alias];
  return d === "asc" ? "asc" : "desc";
}

export function toggleRankDirection(
  doc: PipelineDocument,
  alias: string,
): PipelineDocument {
  if (!isInsightRankAlias(doc, alias)) return doc;
  const cur = rankDirection(doc, alias);
  const nextDir = cur === "desc" ? "asc" : "desc";
  const dirs = { ...(doc.bindings?.alpha_rank_directions ?? {}) };
  if (nextDir === "desc") {
    delete dirs[alias];
  } else {
    dirs[alias] = "asc";
  }
  return {
    ...doc,
    bindings: {
      ...(doc.bindings ?? {}),
      alpha_rank_directions: Object.keys(dirs).length ? dirs : null,
    },
  };
}

export function setMeasureFilter(
  doc: PipelineDocument,
  stageIndex: number,
  filter: {
    op: "gt" | "gte" | "lt" | "lte" | "eq" | "neq";
    value: number;
  } | null,
): PipelineDocument {
  const stages = [...(doc.stages ?? [])];
  const stage = stages[stageIndex];
  if (!stage) return doc;
  const alias = (stage.id || "").trim();
  if (!alias) return doc;
  stages[stageIndex] = {
    ...stage,
    measure_filter: filter
      ? {
          op: filter.op,
          left: alias,
          right: filter.value,
          right_kind: "lit",
        }
      : null,
  };
  return { ...doc, stages };
}

export function toggleInsightConfidenceAlias(
  doc: PipelineDocument,
  alias: string,
): PipelineDocument {
  const confOn = confidencePrimaryCol(doc.bindings?.alpha_confidence) === alias;
  if (confOn) {
    return {
      ...doc,
      bindings: {
        ...(doc.bindings ?? {}),
        alpha_confidence: null,
      },
    };
  }
  const next = isInsightRankAlias(doc, alias) ? doc : toggleInsightRankAlias(doc, alias);
  return {
    ...next,
    bindings: {
      ...(next.bindings ?? {}),
      alpha_confidence: confidenceColRef(alias),
    },
  };
}

export function isInsightConfidenceAlias(
  doc: PipelineDocument,
  alias: string,
): boolean {
  const primary = confidencePrimaryCol(doc.bindings?.alpha_confidence);
  return primary === alias || isInsightRankAlias(doc, alias);
}

export function setShortlistFloor(
  doc: PipelineDocument,
  minScreens: number,
): PipelineDocument {
  return {
    ...doc,
    gate_combine: "count",
    min_screens: Math.max(1, Math.round(minScreens)),
  };
}

export function setTieBreak(doc: PipelineDocument, tie: string): PipelineDocument {
  const rank = [...(doc.bindings?.alpha_rank ?? [])];
  const primary = rank[0];
  if (!primary) {
    return {
      ...doc,
      gate_combine: "count",
      bindings: {
        ...(doc.bindings ?? {}),
        alpha_rank: [tie],
      },
    };
  }
  const rest = rank.slice(2);
  return {
    ...doc,
    gate_combine: "count",
    bindings: {
      ...(doc.bindings ?? {}),
      alpha_rank: [primary, tie, ...rest.filter((a) => a !== tie && a !== primary)],
    },
  };
}

export function toggleConfidenceRole(
  doc: PipelineDocument,
  measure: MeasureInPlay,
): PipelineDocument {
  return toggleInsightConfidenceAlias(doc, measure.alias);
}

export function formatNumberSlotExpr(slot: SlotExpr | null | undefined): string {
  if (!slot || slot.kind !== "number" || !slot.expr) return "default (unbound)";
  return formatOperand(slot.expr as Record<string, unknown>);
}

function formatOperand(e: Record<string, unknown> | null | undefined): string {
  if (!e || typeof e !== "object") return "?";
  if (e.type === "col" && typeof e.name === "string") return e.name;
  if (e.type === "lit") return String(e.value);
  if (e.type === "formula" && Array.isArray(e.args) && e.args.length >= 1) {
    const op = typeof e.op === "string" ? e.op : "?";
    const parts = (e.args as Record<string, unknown>[]).map((a) => formatOperand(a));
    if (parts.length === 1) return parts[0]!;
    if (op === "+" || op === "*") {
      return parts.join(` ${op} `);
    }
    if (parts.length === 2) {
      return `${parts[0]} ${op} ${parts[1]}`;
    }
    return `(${parts.join(` ${op} `)})`;
  }
  return JSON.stringify(e);
}

export function formatStopSummary(stop: {
  type?: string;
  multiplier?: number;
  pct?: number;
} | null | undefined): string {
  if (!stop) return "ATR × 2";
  if (stop.type === "fixed_pct") return `fixed ${(stop.pct ?? 0.05) * 100}%`;
  return `ATR × ${stop.multiplier ?? 2}`;
}

/** Number SlotExpr that is a bare column ref (Insights property ← measure). */
export function colRefSlotExpr(col: string): SlotExpr {
  return { kind: "number", expr: { type: "col", name: col } };
}

/** Primary column name from a number SlotExpr (col or formula first arg). */
export function primaryColFromSlot(slot: SlotExpr | null | undefined): string | null {
  if (!slot || slot.kind !== "number" || !slot.expr) return null;
  const e = slot.expr as Record<string, unknown>;
  if (e.type === "col" && typeof e.name === "string") return e.name;
  if (e.type === "formula" && Array.isArray(e.args)) {
    const a = e.args[0] as Record<string, unknown> | undefined;
    if (a?.type === "col" && typeof a.name === "string") return a.name;
  }
  return null;
}

/**
 * Measure aliases for Insight property lookup (not the full L7 catalog).
 * Includes score gates and expr/field measures with a binding id.
 */
export function measureAliasesForLookup(stages: Stage[]): string[] {
  const out: string[] = [];
  for (const s of stages) {
    const id = (s.id || "").trim();
    if (!id) continue;
    if (s.mode === "score" && (Boolean(s.as_gate) || Boolean(s.computed_expr))) {
      out.push(id);
    }
  }
  return [...new Set(out)];
}

/**
 * @deprecated Prefer {@link measureAliasesForLookup}. Ignores ``fieldNames`` —
 * property lookup is measure-gated (not raw Universe.select / L7 dump).
 */
export function insightPropertyAliases(
  stages: Stage[],
  _fieldNames: string[] = [],
): string[] {
  return measureAliasesForLookup(stages);
}

/**
 * ORDER BY columns shown on Insights: ``alpha_rank`` entries that are measures.
 * Bare L7 harvest (e.g. unbound overall_score) is excluded.
 */
export function orderByMeasureAliases(doc: PipelineDocument): string[] {
  const measures = new Set(measureAliasesForLookup(doc.stages ?? []));
  return (doc.bindings?.alpha_rank ?? []).filter((a) => measures.has(a));
}

/**
 * Bool Insight ✓ aliases: setup (``alpha_setup``) then eligibility (``alpha_eligibility``).
 * These are SQL WHERE / emit keep-true — not ORDER BY.
 */
export function whereMeasureAliases(doc: PipelineDocument): {
  setup: string[];
  eligibility: string[];
} {
  const measureIds = new Set(
    (doc.stages ?? [])
      .map((s) => (s.id || "").trim())
      .filter(Boolean),
  );
  // setup_pass may be the default id even when stage.id was blank historically
  measureIds.add("setup_pass");

  const setup: string[] = [];
  const eligibility: string[] = [];
  for (const id of measureIds) {
    if (isInsightFilterAlias(doc, id, "alpha_setup")) setup.push(id);
    if (isInsightFilterAlias(doc, id, "alpha_eligibility")) eligibility.push(id);
  }
  // Prefer authored stage order
  const order = (doc.stages ?? []).map((s) => (s.id || "").trim()).filter(Boolean);
  const byStage = (a: string, b: string) => {
    const ia = order.indexOf(a);
    const ib = order.indexOf(b);
    return (ia < 0 ? 9999 : ia) - (ib < 0 ? 9999 : ib);
  };
  return {
    setup: [...new Set(setup)].sort(byStage),
    eligibility: [...new Set(eligibility)].sort(byStage),
  };
}

/**
 * @deprecated No-op. Hit-count ranking is whatever measure aliases have Insight ✓ —
 * there is no reserved ``screens_hit`` name.
 */
export function repairHitRankBindings(doc: PipelineDocument): PipelineDocument {
  return doc;
}

function remapColNameInNode(node: unknown, from: string, to: string): unknown {
  if (!node || typeof node !== "object") return node;
  if (Array.isArray(node)) {
    return node.map((x) => remapColNameInNode(x, from, to));
  }
  const n = node as Record<string, unknown>;
  if (n.type === "col" && n.name === from) {
    return { ...n, name: to };
  }
  const out: Record<string, unknown> = { ...n };
  for (const key of ["args", "left", "right", "items", "where", "expr"]) {
    if (key in out) out[key] = remapColNameInNode(out[key], from, to);
  }
  return out;
}

function remapSlotCol(
  slot: SlotExpr | null | undefined,
  from: string,
  to: string,
): SlotExpr | null | undefined {
  if (!slot) return slot;
  if (slot.kind === "bool" && slot.where) {
    return { ...slot, where: remapColNameInNode(slot.where, from, to) as typeof slot.where };
  }
  if (slot.kind === "number" && slot.expr) {
    return {
      ...slot,
      expr: remapColNameInNode(slot.expr, from, to) as Record<string, unknown>,
    };
  }
  return slot;
}

/**
 * Rename a measure binding id and remape rank / Insight property / expr refs.
 * Clearing the id drops it from ``alpha_rank`` only (stage remains).
 */
export function renameMeasureAlias(
  doc: PipelineDocument,
  stageIndex: number,
  nextId: string | null,
): PipelineDocument {
  const stages = [...(doc.stages ?? [])];
  const stage = stages[stageIndex];
  if (!stage) return doc;
  const prev = (stage.id || "").trim();
  const next = (nextId || "").trim();
  if (prev === next) {
    return {
      ...doc,
      stages: stages.map((s, i) =>
        i === stageIndex ? { ...s, id: next || null } : s,
      ),
    };
  }

  stages[stageIndex] = { ...stage, id: next || null };

  // Remap col refs in other stage formulas (e.g. hit_count := screen_1 + …).
  if (prev && next) {
    for (let i = 0; i < stages.length; i++) {
      if (i === stageIndex) continue;
      const s = stages[i]!;
      if (s.computed_expr) {
        stages[i] = {
          ...s,
          computed_expr: remapColNameInNode(s.computed_expr, prev, next) as Record<
            string,
            unknown
          >,
        };
      }
    }
  }

  const b = doc.bindings ?? {};
  let alpha_rank = [...(b.alpha_rank ?? [])];
  const dirs = { ...(b.alpha_rank_directions ?? {}) };

  if (prev && next) {
    alpha_rank = alpha_rank.map((a) => (a === prev ? next : a));
    if (dirs[prev] !== undefined) {
      dirs[next] = dirs[prev]!;
      delete dirs[prev];
    }
  } else if (prev && !next) {
    alpha_rank = alpha_rank.filter((a) => a !== prev);
    delete dirs[prev];
  }

  const remapIf = (slot: SlotExpr | null | undefined) =>
    prev && next ? remapSlotCol(slot, prev, next) ?? null : slot ?? null;

  return {
    ...doc,
    stages,
    bindings: {
      ...b,
      alpha_rank,
      alpha_rank_directions: dirs,
      alpha_direction: remapIf(b.alpha_direction),
      alpha_magnitude: remapIf(b.alpha_magnitude),
      alpha_weight: remapIf(b.alpha_weight),
      alpha_confidence: remapIf(b.alpha_confidence),
      alpha_eligibility: remapIf(b.alpha_eligibility),
      alpha_setup: remapIf(b.alpha_setup),
      pcm_allow_entry: remapIf(b.pcm_allow_entry),
      pcm_scale: remapIf(b.pcm_scale),
      risk_allow_pyramid_add: remapIf(b.risk_allow_pyramid_add),
      risk_skip_time_stop: remapIf(b.risk_skip_time_stop),
    },
  };
}

/** Patch bindings for Insight property ← alias (null clears). */
export function patchInsightPropertyAlias(
  bindings: PipelineDocument["bindings"] | null | undefined,
  key: "alpha_direction" | "alpha_magnitude" | "alpha_weight" | "alpha_confidence",
  alias: string | null,
): NonNullable<PipelineDocument["bindings"]> {
  return {
    ...(bindings ?? {}),
    [key]: alias ? colRefSlotExpr(alias) : null,
  };
}

/** Patch ``pcm_scale`` ← measure alias (null clears; honor Insight confidence). */
export function patchPcmScaleAlias(
  bindings: PipelineDocument["bindings"] | null | undefined,
  alias: string | null,
): NonNullable<PipelineDocument["bindings"]> {
  return {
    ...(bindings ?? {}),
    pcm_scale: alias ? colRefSlotExpr(alias) : null,
  };
}

/**
 * Minervini SEPA Insight.Price ← measure map (Champion preset aliases).
 * Weight/confidence prefer scaled conviction measures (hit_count/5), not raw counts.
 */
const SEPA_INSIGHT_PICKS: Record<
  "alpha_direction" | "alpha_magnitude" | "alpha_weight" | "alpha_confidence",
  string[]
> = {
  alpha_direction: ["insight_dir"],
  alpha_magnitude: ["mag_thrust"],
  alpha_weight: ["w_conviction"],
  alpha_confidence: ["conf_scale", "w_conviction"],
};

export type SepaInsightApplyResult = {
  bindings: NonNullable<PipelineDocument["bindings"]>;
  used: Partial<
    Record<
      "alpha_direction" | "alpha_magnitude" | "alpha_weight" | "alpha_confidence",
      string
    >
  >;
  missing: string[];
};

/** Bind Insight.Price slots to Champion SEPA measure aliases when present. */
export function applySepaInsightPropertyBindings(
  doc: PipelineDocument,
): SepaInsightApplyResult {
  const available = new Set(measureAliasesForLookup(doc.stages ?? []));
  const used: SepaInsightApplyResult["used"] = {};
  const missing: string[] = [];
  let bindings: NonNullable<PipelineDocument["bindings"]> = {
    ...(doc.bindings ?? {}),
  };

  for (const key of Object.keys(SEPA_INSIGHT_PICKS) as Array<
    keyof typeof SEPA_INSIGHT_PICKS
  >) {
    const pick = SEPA_INSIGHT_PICKS[key].find((a) => available.has(a));
    if (pick) {
      used[key] = pick;
      bindings = patchInsightPropertyAlias(bindings, key, pick);
    } else {
      missing.push(...SEPA_INSIGHT_PICKS[key].slice(0, 1));
    }
  }

  bindings = {
    ...bindings,
    alpha_insight_period_days: doc.bindings?.alpha_insight_period_days ?? 1,
  };

  return { bindings, used, missing: [...new Set(missing)] };
}
