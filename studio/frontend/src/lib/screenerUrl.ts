/**
 * The `/screens` address carries the screen in the **AST's own terms**.
 *
 * Rule (agreed): an unaltered screen is shared by **reference** (`template` / `preset` /
 * `screen`); once altered, the address carries the tree itself.
 *
 *   /screens?screen=7&g=all:hygiene&f.0=close>=5&f.1=not(industry='Biotechnology')
 *            &g.2=any&f.2.0=exchange='NYSE'&f.2.1=exchange='NASDAQ'&view=list
 *
 *   g.<path>=all|any[:name]   a group; the path is its position in the tree (root is bare)
 *   f.<path>=<condition>      a comparison, or `not(<condition>)`
 *
 * Encoded from the AST directly — no reduced "chips" model, so `not`, all four arithmetic
 * operators and any nesting depth survive. Ids never travel. If a node cannot be written
 * this way (or the result would be absurdly long), the address falls back to the raw node
 * as `where={…}` rather than dropping anything.
 */

import { extractAppliedFilterGroups, groupsToWhere, nextFilterId } from "./irFilters";
import {
  astToWhere,
  isGroupNode,
  normalizeAst,
  operandLabel,
  whereToAst,
  withIds,
  type AstNode,
} from "./screenAst";
import type { AppliedFilterGroup, IrWhereNode } from "../types";

export const LEGACY_FILTERS_PARAM = "filters";
const LEGACY_CODEC = "v1";
const RAW_PARAM = "where";
/** Guard against absurd URLs: a shared link must stay mailable. */
export const FILTERS_MAX_ENCODED = 8000;

export type ScreenerUrlState = {
  /** Spec reference — exactly one of template / preset / screen is meaningful. */
  template: string | null;
  preset: string | null;
  screen: string | null;
  asOf: string | null;
  view: "list" | "grid" | null;
  universe: string | null;
  deprecated: boolean;
  /** The screen's tree, when the address carries it (the authoritative form). */
  where: AstNode | null;
  /** The same tree as editable chips, for the editor's display model. */
  filters: AppliedFilterGroup[] | null;
};

export const EMPTY_SCREENER_URL_STATE: ScreenerUrlState = {
  template: null,
  preset: null,
  screen: null,
  asOf: null,
  view: null,
  universe: null,
  deprecated: false,
  where: null,
  filters: null,
};

const OPS: Record<string, string> = { gt: ">", gte: ">=", lt: "<", lte: "<=", eq: "=" };
const CODE_TO_OP: Record<string, "gt" | "gte" | "lt" | "lte" | "eq"> = {
  ">": "gt",
  ">=": "gte",
  "<": "lt",
  "<=": "lte",
  "=": "eq",
};
const OP_CODES = [">=", "<=", ">", "<", "="] as const;

// --- AST -> params -----------------------------------------------------------

/**
 * Serialisation is not display: `operandLabel` renders a string bare (fine on screen) and
 * that would read back as a *column* here, so strings are quoted and escaped explicitly.
 */
function operandText(op: Parameters<typeof operandLabel>[0]): string {
  if (op.type === "formula") return `(${op.args.map(operandText).join(op.op)})`;
  if (op.type === "lit") {
    if (typeof op.value === "string") return `'${op.value.replace(/'/g, "\\'")}'`;
    return String(op.value);
  }
  return op.offset ? `${op.name}[${op.offset}]` : op.name;
}

/** `not(eq(a,b))` is written `not(a=b)`; a `not` over a group has no readable form. */
function conditionText(node: AstNode): string | null {
  if (node.type === "not") {
    if (isGroupNode(node.item)) return null;
    const inner = conditionText(node.item);
    return inner ? `not(${inner})` : null;
  }
  if (isGroupNode(node)) return null;
  const code = OPS[node.type];
  if (!code) return null;
  return `${operandText(node.left)}${code}${operandText(node.right)}`;
}

function encodeNode(node: AstNode, path: number[], out: Array<[string, string]>): boolean {
  const suffix = path.length ? `.${path.join(".")}` : "";
  if (isGroupNode(node)) {
    out.push([`g${suffix}`, node.name ? `${node.type}:${node.name}` : node.type]);
    for (const [i, child] of node.items.entries()) {
      if (!encodeNode(child, [...path, i], out)) return false;
    }
    return true;
  }
  const text = conditionText(node);
  if (text === null) return false;
  out.push([`f${suffix}`, text]);
  return true;
}

/** Readable params for a tree, or `[]` when it needs the raw fallback. */
export function astParams(node: AstNode | null | undefined): Array<[string, string]> {
  if (!node) return [];
  const out: Array<[string, string]> = [];
  if (!encodeNode(node, [], out)) return [];
  const total = out.reduce((n, [k, v]) => n + k.length + v.length + 2, 0);
  return total > FILTERS_MAX_ENCODED ? [] : out;
}

// --- params -> AST -----------------------------------------------------------

function parseOperand(raw: string): Parameters<typeof operandLabel>[0] | null {
  const text = raw.trim();
  if (!text) return null;
  if (text.startsWith("(") && text.endsWith(")")) {
    const inner = text.slice(1, -1);
    // split on the first top-level arithmetic operator
    const m = inner.match(/^(.+?)\s*([+\-*/])\s*(.+)$/);
    if (!m) return parseOperand(inner);
    const left = parseOperand(m[1]!);
    const right = parseOperand(m[3]!);
    if (!left || !right) return null;
    return { type: "formula", op: m[2] as "+" | "-" | "*" | "/", args: [left, right] };
  }
  if (text.startsWith("'") && text.endsWith("'")) {
    return { type: "lit", value: text.slice(1, -1).replace(/\\'/g, "'") };
  }
  if (text === "true" || text === "false") return { type: "lit", value: text === "true" };
  if (/^-?\d+(\.\d+)?$/.test(text)) return { type: "lit", value: Number(text) };
  const offset = text.match(/^([A-Za-z_][\w.]*)\[(-?\d+)\]$/);
  if (offset) return { type: "col", name: offset[1]!, offset: Number(offset[2]) };
  if (/^[A-Za-z_][\w.]*$/.test(text)) return { type: "col", name: text };
  return null;
}

function parseCondition(raw: string): AstNode | null {
  const text = raw.trim();
  const not = text.match(/^not\((.*)\)$/);
  if (not) {
    const inner = parseCondition(not[1]!);
    return inner ? { type: "not", item: inner } : null;
  }
  for (const code of OP_CODES) {
    const at = text.indexOf(code);
    if (at > 0) {
      const left = parseOperand(text.slice(0, at));
      const right = parseOperand(text.slice(at + code.length));
      const type = CODE_TO_OP[code];
      if (left && right && type) return { type, left, right };
    }
  }
  return null;
}

const KEY = /^([gf])((?:\.\d+)*)$/;

/**
 * The interim chips form (`f=…&g=all&f2=…&g2=…`) shares the depth-0 keys with the AST
 * form, so the two must be told apart rather than one silently shadowing the other:
 *  - any dotted path (`f.0`, `g.1.2`) => the AST form — the chips form never emits those;
 *  - `f2`/`g2`, or more than one depth-0 `f` => the chips form (whose conditions all sit at
 *    depth 0); the AST only ever writes a bare `f` for a single root comparison.
 */
function looksLikeLegacyChips(params: URLSearchParams): boolean {
  let depthZeroF = 0;
  for (const key of params.keys()) {
    if (key === "f") depthZeroF += 1;
    if (key === "f2" || key === "g2") return true;
  }
  return depthZeroF > 1;
}

/** A path is a dotted key everywhere: `[]` -> "", `[3,2]` -> "3.2". Never bare `join()`,
 *  which inserts commas and silently fails to match for depth >= 2. */
function pathKey(path: number[]): string {
  return path.join(".");
}

function buildNode(path: number[], entries: Map<string, [string, string]>): AstNode | null {
  const suffix = pathKey(path);
  const group = entries.get(`g:${suffix}`);
  if (group) {
    const [rawLogic, ...rest] = group[1].split(":");
    const name = rest.join(":") || undefined;
    const childIdx = new Set<number>();
    for (const key of entries.keys()) {
      const [kind, p] = key.split(":");
      const segs = p!.length ? p!.split(".").map(Number) : [];
      if (kind !== "f" && kind !== "g") continue;
      if (segs.length !== path.length + 1) continue;
      if (pathKey(segs.slice(0, path.length)) !== suffix) continue;
      childIdx.add(segs[segs.length - 1]!);
    }
    const items: AstNode[] = [];
    for (const i of [...childIdx].sort((a, b) => a - b)) {
      const child = buildNode([...path, i], entries);
      if (!child) return null; // never emit a group with a child quietly missing
      items.push(child);
    }
    // zero children is a legitimate, just-added group — not a failure
    return normalizeAst({ type: rawLogic === "any" ? "any" : "all", ...(name ? { name } : {}), items });
  }
  const pred = entries.get(`f:${suffix}`);
  return pred ? parseCondition(pred[1]) : null;
}

function astFromParams(params: URLSearchParams): AstNode | null {
  const entries = new Map<string, [string, string]>();
  for (const [key, value] of params.entries()) {
    const m = key.match(KEY);
    if (!m) continue;
    entries.set(`${m[1]}:${(m[2] ?? "").replace(/^\./, "")}`, [m[1]!, value]);
  }
  if (!entries.has("g:") && !entries.has("f:")) return null;
  return buildNode([], entries);
}

// --- legacy decoders (older links keep working) ------------------------------

/** The chips form this codec emitted before it spoke the AST (links live for a short
 *  while). Rebuilt into proper chip groups, then converted like any other tree. */
function astFromLegacyChips(params: URLSearchParams): AstNode | null {
  type Row = { id: string; op: string; left: unknown; right: unknown };
  type Group = { id: string; logic: "all" | "any"; name?: string; rows: Row[] };
  const groups: Group[] = [];
  let current: Group | null = null;
  for (const [key, value] of params.entries()) {
    if (key === "g" || key === "g2") {
      const [rawLogic, ...rest] = value.split(":");
      current = {
        id: `legacy_${groups.length}_${key}`,
        logic: rawLogic === "any" ? "any" : "all",
        ...(rest.length ? { name: rest.join(":") } : {}),
        rows: [],
      };
      groups.push(current);
      continue;
    }
    if (key !== "f" && key !== "f2") continue;
    const node = parseCondition(value);
    if (!node || node.type === "not" || isGroupNode(node)) continue;
    if (!current) {
      current = { id: "legacy_root", logic: "all", rows: [] };
      groups.push(current);
    }
    current.rows.push({
      id: `legacy_r${groups.length}_${current.rows.length}`,
      op: node.type,
      left: node.left,
      right: node.right,
    });
  }
  const usable = groups.filter((g) => g.rows.length > 0);
  if (usable.length === 0) return null;
  const where = groupsToWhere(usable as never);
  return whereToAst(where);
}

function astFromLegacyBlob(raw: string | null | undefined): AstNode | null {
  if (!raw) return null;
  const dot = raw.indexOf(".");
  if (dot < 0 || raw.slice(0, dot) !== LEGACY_CODEC) return null;
  const body = raw.slice(dot + 1);
  try {
    const padded = body.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (body.length % 4)) % 4);
    const bytes = Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
    const parsed: unknown = JSON.parse(new TextDecoder().decode(bytes));
    // the old blob held chips; convert to the tree via the same chips path the UI used
    const groups = Array.isArray(parsed) ? (parsed as AppliedFilterGroup[]) : null;
    if (!groups) return null;
    return whereToAst(groupsToWhere(groups as never));
  } catch {
    return null;
  }
}

// --- public API --------------------------------------------------------------

function firstParam(params: URLSearchParams, keys: string[]): string | null {
  for (const key of keys) {
    const value = params.get(key);
    if (value) return value;
  }
  return null;
}

export function readScreenerState(search: string): ScreenerUrlState {
  const params = new URLSearchParams(search.startsWith("?") ? search : `?${search}`);
  const view = params.get("view");

  let where: AstNode | null = null;
  const raw = params.get(RAW_PARAM);
  if (raw) {
    try {
      where = whereToAst(JSON.parse(raw));
    } catch {
      where = null;
    }
  }
  if (!where) {
    where = looksLikeLegacyChips(params)
      ? astFromLegacyChips(params) ?? astFromParams(params)
      : astFromParams(params) ?? astFromLegacyChips(params);
  }
  where = where ?? astFromLegacyBlob(params.get(LEGACY_FILTERS_PARAM));

  return {
    template: firstParam(params, ["template"]),
    preset: firstParam(params, ["preset"]),
    screen: firstParam(params, ["screen", "saved"]),
    asOf: firstParam(params, ["as_of", "asOf"]),
    view: view === "list" || view === "grid" ? view : null,
    universe: firstParam(params, ["universe"]),
    deprecated: params.get("deprecated") === "1" || params.get("deprecated") === "true",
    where,
    filters: where ? extractAppliedFilterGroups(astToWhere(where) as IrWhereNode) : null,
  };
}

/** Escape only what would break the query — keeps `>` `<` `:` `'` `(` `)` readable. */
function escapeValue(value: string): string {
  return value
    .replace(/%/g, "%25")
    .replace(/&/g, "%26")
    .replace(/\+/g, "%2B")
    .replace(/#/g, "%23")
    .replace(/ /g, "%20");
}

/**
 * Build the `/screens` search string. Defaults are omitted so a plain screener stays a
 * plain `/screens` link: `today` drops `as_of`. The reference is kept alongside the tree
 * as provenance — the tree is what defines the screen once it has been altered.
 *
 * Accepts the tree (`where`) or the editor's chips (`filters`, converted) so callers can
 * migrate one at a time without the address losing the screen in between.
 */
export function buildScreenerSearch(
  state: Partial<ScreenerUrlState>,
  opts: { today?: string } = {},
): string {
  const parts: string[] = [];
  const add = (key: string, value: string) => parts.push(`${key}=${escapeValue(value)}`);

  if (state.template) add("template", state.template);
  else if (state.preset) add("preset", state.preset);
  else if (state.screen) add("screen", String(state.screen));

  const node =
    state.where ?? (state.filters && state.filters.length ? whereToAst(groupsToWhere(state.filters as never)) : null);
  const pairs = astParams(node);
  if (node && pairs.length === 0) {
    add(RAW_PARAM, JSON.stringify(astToWhere(node))); // unrepresentable or oversized: raw node
  } else {
    for (const [key, value] of pairs) add(key, value);
  }

  if (state.asOf && state.asOf !== opts.today) add("as_of", state.asOf);
  if (state.view) add("view", state.view);
  if (state.universe && state.universe !== "all") add("universe", state.universe);
  if (state.deprecated) add("deprecated", "1");

  return parts.join("&");
}

/** `/screens?...` — the canonical screener URL for a state. */
export function screenerHref(state: Partial<ScreenerUrlState>, opts: { today?: string } = {}): string {
  const search = buildScreenerSearch(state, opts);
  return search ? `/screens?${search}` : "/screens";
}

/** The chips that describe an existing spec's where-AST (editor display model). */
export function whereToFilterGroups(where: IrWhereNode | undefined): AppliedFilterGroup[] {
  return extractAppliedFilterGroups(where);
}

/** Give a tree render ids (the editor needs them; they never reach the URL). */
export function withRenderIds(node: AstNode): ReturnType<typeof withIds> {
  return withIds(node, nextFilterId);
}
