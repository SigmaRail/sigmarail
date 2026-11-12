import { useState } from "react";
import type { RuleSpec } from "../../lib/rulesAst";
import { cn } from "../../lib/utils";

type RuleSlot = "risk" | "pcm";

interface EvalResult {
  ticker: string;
  date: string;
  in_universe: boolean;
  row: Record<string, unknown> | null;
  per_rule: {
    name: string;
    priority: number;
    matched: boolean;
    error: string | null;
    actions?: Record<string, unknown>[];
  }[];
  decision: { rule: string | null; actions: Record<string, unknown>[] };
  detail?: string;
}

/** Unit-shape presets — the contexts the runtime builds that a preview can't
    know (portfolio state, pyramid phase, direction). */
const PCM_PRESETS: { label: string; contexts: Record<string, Record<string, number>> }[] = [
  {
    label: "new candidate",
    contexts: {
      cand: { is_new: 1, has_insight: 1, rs: 92, confidence: 1 },
      acct: { slots_remaining: 2 },
      pyr: { entry_frac: 1 },
      regime: { on: 1, scaling_on: 0, fraction: 1 },
    },
  },
  {
    label: "pyramid add",
    contexts: {
      cand: { is_add: 1, has_insight: 1, confirm_price: 110, price: 106 },
      hold: { invested: 1, days_held: 5, entry: 100, weight: 0.1 },
      pyr: { add_frac: 0.5, entry_price: 100 },
      regime: { on: 1, scaling_on: 0, fraction: 1 },
    },
  },
  {
    label: "down insight",
    contexts: { cand: { is_down: 1, has_insight: 1 }, hold: { invested: 1, weight: 0.1 } },
  },
  {
    label: "quiet holding",
    contexts: { cand: { has_insight: 0 }, hold: { invested: 1, weight: 0.15 } },
  },
  {
    label: "quiet holding (over cap)",
    contexts: { cand: { has_insight: 0 }, hold: { invested: 1, weight: 0.3 } },
  },
];

const RISK_PRESETS: { label: string; contexts: Record<string, Record<string, number>> }[] = [
  {
    label: "profitable holding",
    contexts: {
      pos: { invested: 1, entry: 100, price: 115, r: 1.5, days_held: 10, initial_stop: 95 },
    },
  },
  {
    label: "losing holding",
    contexts: {
      pos: { invested: 1, entry: 100, price: 94, r: -0.6, days_held: 10, initial_stop: 95 },
    },
  },
  {
    label: "aged holding",
    contexts: {
      pos: { invested: 1, entry: 100, price: 101, r: 0.1, days_held: 60, initial_stop: 95 },
    },
  },
];

const inputCls =
  "rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[10px] text-ink";

export function RuleTableTester({
  slot,
  irId,
  rules,
}: {
  slot: RuleSlot;
  /** Saved spec id — the ticker row comes from its stored universe. */
  irId: string | null;
  /** Current (possibly draft-edited) rules — sent to the server, so unsaved edits preview. */
  rules: RuleSpec[];
}) {
  const presets = slot === "risk" ? RISK_PRESETS : PCM_PRESETS;
  const [open, setOpen] = useState(false);
  const [ticker, setTicker] = useState("NVDA");
  const [asOf, setAsOf] = useState("");
  const [ctxText, setCtxText] = useState(JSON.stringify(presets[0].contexts, null, 1));
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<EvalResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [showRow, setShowRow] = useState(false);

  const run = async () => {
    setBusy(true);
    setErr(null);
    let contexts: Record<string, unknown>;
    try {
      contexts = JSON.parse(ctxText || "{}");
    } catch {
      setErr("contexts JSON is invalid");
      setBusy(false);
      return;
    }
    try {
      const res = await fetch("/api/strategy/eval-rules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ir_id: irId,
          slot,
          ticker,
          as_of_date: asOf || undefined,
          contexts,
          rules,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
      setResult(data as EvalResult);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        disabled={!irId}
        title={irId ? "Evaluate this table against a real universe row" : "Save the spec first — the test row comes from its stored universe"}
        className="rounded border border-line px-1.5 py-0.5 text-[10px] text-ink-faint hover:text-ink disabled:opacity-40"
      >
        test
      </button>
    );
  }

  return (
    <div className="mt-1 rounded border border-line/70 bg-surface-raised/40 p-1.5 text-[10px] font-mono">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-ink-faint">test unit</span>
        <input className={cn(inputCls, "w-16")} value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} placeholder="NVDA" />
        <input className={cn(inputCls, "w-24")} value={asOf} onChange={(e) => setAsOf(e.target.value)} placeholder="as-of (latest)" />
        {presets.map((p) => (
          <button
            key={p.label}
            type="button"
            onClick={() => setCtxText(JSON.stringify(p.contexts, null, 1))}
            className="rounded border border-line/70 px-1 py-0.5 text-ink-faint hover:text-ink"
          >
            {p.label}
          </button>
        ))}
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="rounded border border-accent bg-accent/10 px-2 py-0.5 text-accent hover:bg-accent/20 disabled:opacity-50"
        >
          {busy ? "evaluating…" : "evaluate"}
        </button>
        <button type="button" onClick={() => setOpen(false)} className="ml-auto text-ink-faint hover:text-ink">close</button>
      </div>
      <textarea
        value={ctxText}
        onChange={(e) => setCtxText(e.target.value)}
        rows={Math.min(10, ctxText.split("\n").length + 1)}
        className="mt-1 w-full rounded border border-line bg-surface p-1 font-mono text-[10px] text-ink"
        spellCheck={false}
      />
      {err && <div className="mt-1 text-red-400">{err}</div>}
      {result && (
        <div className="mt-1 space-y-0.5">
          {result.in_universe === false && (
            <div className="text-amber-400">{result.detail}</div>
          )}
          {result.per_rule.map((r) => (
            <div key={r.name} className="flex items-center gap-1.5">
              <span className={r.error ? "text-red-400" : r.matched ? "text-emerald-400" : "text-ink-faint"}>
                {r.error ? "!" : r.matched ? "✓" : "·"}
              </span>
              <span className={cn("w-40 truncate", r.matched && "font-semibold text-ink")}>{r.name}</span>
              {r.matched && r.actions?.map((a, i) => (
                <span key={i} className="rounded border border-line/70 px-1 text-ink-faint">{String(a.type)}</span>
              ))}
              {r.error && <span className="text-red-400/80">{r.error}</span>}
            </div>
          ))}
          <div className="pt-0.5 text-ink-faint">
            → decision: <span className="text-ink font-semibold">{result.decision.rule ?? "none"}</span>
            {result.decision.actions.length > 0 &&
              ` (${result.decision.actions.map((a) => String(a.type)).join(", ")})`}
            {result.row && (
              <button type="button" onClick={() => setShowRow((v) => !v)} className="ml-2 underline">
                {showRow ? "hide row" : "show row"}
              </button>
            )}
          </div>
          {showRow && result.row && (
            <pre className="max-h-40 overflow-auto rounded bg-surface p-1 text-ink-faint">
              {JSON.stringify(result.row, null, 1)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
