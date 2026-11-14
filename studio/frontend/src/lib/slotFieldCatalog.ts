import { useEffect, useState } from "react";
import type { ScreenField } from "../types";
import type { Stage } from "../components/strategy/StrategyDocument";

const L7_SLOT_COLS: { name: string; label: string }[] = [
  { name: "atr_14_pct", label: "ATR 14%" },
  { name: "close", label: "Close" },
  { name: "rs_rating", label: "RS rating" },
  { name: "overall_score", label: "Overall score" },
  { name: "high_90d", label: "High 90d" },
  { name: "high_5d", label: "High 5d" },
];

/**
 * One runtime position binding — served from VeraLab
 * (`vera_lab/ir/position_bindings.py`, via `GET /api/strategy/position-fields`).
 * These populate `pos` operands; they are **not** screener `col` names, so they
 * never appear in the FieldPicker catalog below.
 */
export type PositionBinding = {
  field: string;
  label: string;
  description: string;
  type: string; // "number" | "bool"
  contexts: string[]; // subset of ("init" | "live")
};

let _posBindingsPromise: Promise<PositionBinding[]> | null = null;

/** Fetch + cache the served position-binding registry (module scope). */
export function fetchPositionBindings(): Promise<PositionBinding[]> {
  if (!_posBindingsPromise) {
    _posBindingsPromise = fetch("/api/strategy/position-fields")
      .then((r) => (r.ok ? r.json() : { fields: [] }))
      .then((d) => (Array.isArray(d?.fields) ? (d.fields as PositionBinding[]) : []))
      .catch(() => [] as PositionBinding[]);
  }
  return _posBindingsPromise;
}

/** React hook over the cached fetch — re-renders when bindings arrive. */
export function usePositionBindings(): PositionBinding[] {
  const [bindings, setBindings] = useState<PositionBinding[]>([]);
  useEffect(() => {
    let live = true;
    void fetchPositionBindings().then((b) => {
      if (live) setBindings(b);
    });
    return () => {
      live = false;
    };
  }, []);
  return bindings;
}

/**
 * One PCM runtime binding — served from VeraLab
 * (`vera_lab/ir/pcm_bindings.py`, via `GET /api/strategy/pcm-fields`).
 * These populate `ref` operands inside PCM rules / size_expr — the
 * decision-unit namespaces (cand/hold/acct/pyr/regime).
 */
export type PcmBinding = {
  ns: string;
  field: string;
  label: string;
  description: string;
  type: string; // "number" | "bool"
};

let _pcmBindingsPromise: Promise<PcmBinding[]> | null = null;

/** Fetch + cache the PCM binding registry, flattened to {ns, field, …} rows. */
export function fetchPcmBindings(): Promise<PcmBinding[]> {
  if (!_pcmBindingsPromise) {
    _pcmBindingsPromise = fetch("/api/strategy/pcm-fields")
      .then((r) => (r.ok ? r.json() : { namespaces: {} }))
      .then((d) => {
        const ns = (d?.namespaces ?? {}) as Record<
          string,
          Array<{ field: string; label: string; description: string; type: string }>
        >;
        const out: PcmBinding[] = [];
        for (const [name, items] of Object.entries(ns)) {
          for (const b of items) out.push({ ns: name, ...b });
        }
        return out;
      })
      .catch(() => [] as PcmBinding[]);
  }
  return _pcmBindingsPromise;
}

/** React hook over the cached PCM bindings fetch. */
export function usePcmBindings(): PcmBinding[] {
  const [bindings, setBindings] = useState<PcmBinding[]>([]);
  useEffect(() => {
    let live = true;
    void fetchPcmBindings().then((b) => {
      if (live) setBindings(b);
    });
    return () => {
      live = false;
    };
  }, []);
  return bindings;
}

/** PCM `ref` namespaces, in registry order. */
export function pcmNamespaces(bindings: PcmBinding[]): string[] {
  const seen = new Set<string>();
  for (const b of bindings) seen.add(b.ns);
  return [...seen];
}

/**
 * FieldPicker catalog: authored measure aliases, then L7 columns.
 * Does not invent phantom combinator columns (e.g. screens_hit) — those appear
 * only when authored as measure stages. Position bindings are `pos` operands,
 * selected through `usePositionBindings`, not offered as `col` names.
 */
export function slotFieldCatalog(
  stages: Stage[],
  opts?: { combinator?: string | null },
): ScreenField[] {
  const out: ScreenField[] = [];
  const seen = new Set<string>();
  for (const s of stages) {
    const id = (s.id || "").trim();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    const isNumber =
      Boolean(s.computed_expr) ||
      (s.mode === "score" && !s.as_gate && (s.factors?.length ?? 0) > 0);
    out.push({
      name: id,
      label: s.name || id,
      category: "measures",
      category_label: "This spec’s measures",
      type: s.computed_expr ? "number" : isNumber && !s.as_gate ? "number" : "bool",
      origin: "computed",
    });
  }
  // `combinator` is accepted for call-site compat but ignored — no phantom aliases.
  void opts?.combinator;
  for (const c of L7_SLOT_COLS) {
    if (seen.has(c.name)) continue;
    seen.add(c.name);
    out.push({
      name: c.name,
      label: c.label,
      category: "l7",
      category_label: "L7 columns",
      type: "number",
      origin: "l7",
    });
  }
  return out;
}
