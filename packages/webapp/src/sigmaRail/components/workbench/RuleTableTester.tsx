import { useState } from "react";
import type { RuleSpec } from "../../lib/rulesAst";
import { Badge } from "@sb/webapp-core/components/ui/badge";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Card } from "@sb/webapp-core/components/ui/card";
import { Input } from "@sb/webapp-core/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@sb/webapp-core/components/ui/select";
import { Textarea } from "@sb/webapp-core/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@sb/webapp-core/components/ui/dialog";
import { authenticatedFetch } from "../../api/authenticatedFetch";

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

/** Unit-shape presets represent runtime contexts a local preview cannot infer. */
const PCM_PRESETS: { label: string; contexts: Record<string, Record<string, number>> }[] = [
  {
    label: "New candidate",
    contexts: {
      cand: { is_new: 1, has_insight: 1, rs: 92, confidence: 1 },
      acct: { slots_remaining: 2 },
      pyr: { entry_frac: 1 },
      regime: { on: 1, scaling_on: 0, fraction: 1 },
    },
  },
  {
    label: "Pyramid add",
    contexts: {
      cand: { is_add: 1, has_insight: 1, confirm_price: 110, price: 106 },
      hold: { invested: 1, days_held: 5, entry: 100, weight: 0.1 },
      pyr: { add_frac: 0.5, entry_price: 100 },
      regime: { on: 1, scaling_on: 0, fraction: 1 },
    },
  },
  {
    label: "Down insight",
    contexts: { cand: { is_down: 1, has_insight: 1 }, hold: { invested: 1, weight: 0.1 } },
  },
  {
    label: "Quiet holding",
    contexts: { cand: { has_insight: 0 }, hold: { invested: 1, weight: 0.15 } },
  },
  {
    label: "Quiet holding over cap",
    contexts: { cand: { has_insight: 0 }, hold: { invested: 1, weight: 0.3 } },
  },
];

const RISK_PRESETS: { label: string; contexts: Record<string, Record<string, number>> }[] = [
  {
    label: "Profitable holding",
    contexts: {
      pos: { invested: 1, entry: 100, price: 115, r: 1.5, days_held: 10, initial_stop: 95 },
    },
  },
  {
    label: "Losing holding",
    contexts: {
      pos: { invested: 1, entry: 100, price: 94, r: -0.6, days_held: 10, initial_stop: 95 },
    },
  },
  {
    label: "Aged holding",
    contexts: {
      pos: { invested: 1, entry: 100, price: 101, r: 0.1, days_held: 60, initial_stop: 95 },
    },
  },
];

export function RuleTableTester({
  slot,
  irId,
  rules,
}: {
  slot: RuleSlot;
  /** Saved spec id — the ticker row comes from its stored universe. */
  irId: string | null;
  /** Current rules, including unsaved edits, are sent to the evaluator. */
  rules: RuleSpec[];
}) {
  const presets = slot === "risk" ? RISK_PRESETS : PCM_PRESETS;
  const [open, setOpen] = useState(false);
  const [ticker, setTicker] = useState("NVDA");
  const [asOf, setAsOf] = useState("");
  const [selectedPreset, setSelectedPreset] = useState(presets[0].label);
  const [ctxText, setCtxText] = useState(JSON.stringify(presets[0].contexts, null, 2));
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
      setErr("Context JSON is invalid.");
      setBusy(false);
      return;
    }
    try {
      const response = await authenticatedFetch("/api/strategy/eval-rules", {
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
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail || `HTTP ${response.status}`);
      setResult(data as EvalResult);
      setShowRow(false);
    } catch (error) {
      setErr(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        disabled={!irId}
        title={irId ? "Evaluate these rules using a real universe row" : "Save the spec first; test rows come from its stored universe"}
        aria-haspopup="dialog"
        className="h-8 px-2 text-xs"
      >
        Test rules
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent size="lg" className="flex max-h-[90dvh] flex-col overflow-hidden p-0">
          <DialogHeader className="border-b px-4 py-3 pr-12 sm:px-5">
            <DialogTitle>Test {slot === "risk" ? "risk" : "portfolio"} rules</DialogTitle>
            <DialogDescription>
              Evaluate the current rule draft against a saved universe row and an explicit runtime context.
            </DialogDescription>
          </DialogHeader>

          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 sm:p-5">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <label htmlFor="rule-test-ticker" className="text-sm font-medium">Ticker</label>
                <Input
                  id="rule-test-ticker"
                  value={ticker}
                  onChange={(event) => setTicker(event.target.value.toUpperCase())}
                  placeholder="NVDA"
                  autoCapitalize="characters"
                  className="font-mono uppercase"
                />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="rule-test-as-of" className="text-sm font-medium">As-of date</label>
                <Input
                  id="rule-test-as-of"
                  type="date"
                  value={asOf}
                  onChange={(event) => setAsOf(event.target.value)}
                />
                <p className="text-xs text-muted-foreground">Leave blank to use the latest available row.</p>
              </div>
            </div>

            <div className="space-y-1.5">
              <label htmlFor="rule-test-context-preset" className="text-sm font-medium">Runtime context preset</label>
              <Select
                value={selectedPreset}
                onValueChange={(value) => {
                  setSelectedPreset(value);
                  const preset = presets.find((item) => item.label === value);
                  if (preset) setCtxText(JSON.stringify(preset.contexts, null, 2));
                }}
              >
                <SelectTrigger id="rule-test-context-preset" aria-label="Runtime context preset">
                  <SelectValue placeholder="Choose a context" />
                </SelectTrigger>
                <SelectContent>
                  {presets.map((preset) => (
                    <SelectItem key={preset.label} value={preset.label}>{preset.label}</SelectItem>
                  ))}
                  <SelectItem value="custom">Custom JSON</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <label htmlFor="rule-test-context-json" className="text-sm font-medium">Runtime context JSON</label>
              <Textarea
                id="rule-test-context-json"
                value={ctxText}
                onChange={(event) => {
                  setCtxText(event.target.value);
                  setSelectedPreset("custom");
                }}
                rows={Math.max(8, Math.min(16, ctxText.split("\n").length + 1))}
                spellCheck={false}
                className="resize-y font-mono text-xs"
              />
            </div>

            {err ? (
              <div role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {err}
              </div>
            ) : null}

            {result ? (
              <section aria-label="Rule evaluation results" className="space-y-3 border-t pt-4">
                {result.in_universe === false ? (
                  <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-300">
                    {result.detail || `${result.ticker} is outside the saved universe for ${result.date}.`}
                  </div>
                ) : null}

                <div className="space-y-2">
                  <h3 className="text-sm font-semibold">Rule matches</h3>
                  {result.per_rule.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No rules are configured in this slot.</p>
                  ) : result.per_rule.map((rule) => (
                    <Card key={`${rule.priority}-${rule.name}`} className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center sm:justify-between">
                      <div className="flex min-w-0 items-start gap-2">
                        <Badge variant={rule.error ? "destructive" : rule.matched ? "success" : "muted"} className="shrink-0">
                          {rule.error ? "Error" : rule.matched ? "Matched" : "No match"}
                        </Badge>
                        <span className="min-w-0 break-words text-sm font-medium">{rule.name}</span>
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                        {rule.actions?.map((action, index) => (
                          <Badge key={index} variant="outline">{String(action.type)}</Badge>
                        ))}
                        {rule.error ? <span className="break-words text-destructive">{rule.error}</span> : null}
                      </div>
                    </Card>
                  ))}
                </div>

                <Card className="space-y-2 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-semibold">
                      Decision: <span className="font-mono">{result.decision.rule ?? "No rule"}</span>
                    </p>
                    {result.decision.actions.length ? (
                      <div className="flex flex-wrap gap-1.5">
                        {result.decision.actions.map((action, index) => (
                          <Badge key={index} variant="secondary">{String(action.type)}</Badge>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  {result.row ? (
                    <>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        aria-expanded={showRow}
                        onClick={() => setShowRow((value) => !value)}
                        className="px-0 text-xs"
                      >
                        {showRow ? "Hide universe row" : "Show universe row"}
                      </Button>
                      {showRow ? (
                        <pre className="max-h-64 overflow-auto rounded-md bg-muted/60 p-3 text-xs text-muted-foreground">
                          {JSON.stringify(result.row, null, 2)}
                        </pre>
                      ) : null}
                    </>
                  ) : null}
                </Card>
              </section>
            ) : null}
          </div>

          <div className="flex flex-col-reverse gap-2 border-t px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>Close</Button>
            <Button type="button" onClick={run} disabled={busy || !ticker.trim()}>
              {busy ? "Evaluating…" : "Evaluate rules"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
