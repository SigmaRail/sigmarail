import { useCallback, useState } from "react";
import { compilePortfolio } from "../../api/strategy";
import type { AllocationPolicy, PipelineDocument, PortfolioDocument } from "./StrategyDocument";
import { StrategyEditorView } from "./StrategyEditorView";

const BASE_OPTIONS: Array<NonNullable<AllocationPolicy["base"]>> = [
  "weights",
  "risk_parity",
  "hrp",
  "black_litterman",
];

function emptyLeg(name: string): PipelineDocument {
  return { strategy_name: name, stages: [] };
}

/**
 * Portfolio authoring canvas: N pipeline legs + an allocation policy.
 * Each leg is a full staged pipeline editor; the portfolio compiles to a
 * CompositeAlphaModel ensemble (or a single-leg spec) via the REST API.
 */
export function PortfolioEditorView() {
  const [portfolio, setPortfolio] = useState<PortfolioDocument>({
    name: "Untitled Portfolio",
    legs: [emptyLeg("leg_1")],
    allocation: { base: "weights", weights: {} },
  });
  const [compiled, setCompiled] = useState<Record<string, unknown> | null>(null);
  const [compileError, setCompileError] = useState<string | null>(null);

  const updateLeg = useCallback((i: number, doc: PipelineDocument) => {
    setPortfolio((p) => {
      const legs = [...p.legs];
      legs[i] = doc;
      return { ...p, legs };
    });
  }, []);

  const addLeg = useCallback(() => {
    setPortfolio((p) => ({
      ...p,
      legs: [...p.legs, emptyLeg(`leg_${p.legs.length + 1}`)],
    }));
  }, []);

  const removeLeg = useCallback((i: number) => {
    setPortfolio((p) => ({ ...p, legs: p.legs.filter((_, j) => j !== i) }));
  }, []);

  const doCompile = useCallback(async () => {
    setCompileError(null);
    try {
      const spec = await compilePortfolio(portfolio as unknown as Record<string, unknown>);
      setCompiled(spec);
    } catch (e) {
      setCompiled(null);
      setCompileError(e instanceof Error ? e.message : String(e));
    }
  }, [portfolio]);

  return (
    <div className="space-y-4">
      {/* Portfolio name */}
      <div className="rounded border border-line bg-surface px-3 py-3">
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">Portfolio</h3>
        <input
          value={portfolio.name}
          onChange={(e) => setPortfolio((p) => ({ ...p, name: e.target.value }))}
          className="mt-2 w-full rounded border border-line bg-surface-sunk px-2 py-1 text-sm text-ink"
        />
      </div>

      {/* Legs */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
            Legs ({portfolio.legs.length})
          </h3>
          <button
            type="button"
            onClick={addLeg}
            className="rounded border border-line bg-surface-sunk px-2 py-1 text-[11px] text-ink hover:border-accent/50"
          >
            + Add Leg
          </button>
        </div>
        {portfolio.legs.map((leg, i) => (
          <div key={i} className="rounded border border-line bg-surface px-3 py-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-ink">Leg {i + 1}</span>
              {portfolio.legs.length > 1 && (
                <button
                  type="button"
                  onClick={() => removeLeg(i)}
                  className="text-[11px] text-danger hover:underline"
                >
                  Remove
                </button>
              )}
            </div>
            <div className="mt-2">
              <StrategyEditorView initialDocument={leg} onChangeDocument={(d) => updateLeg(i, d)} />
            </div>
          </div>
        ))}
      </div>

      {/* Allocation policy */}
      <div className="rounded border border-line bg-surface px-3 py-3">
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">Allocation</h3>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {BASE_OPTIONS.map((b) => (
            <button
              key={b}
              type="button"
              onClick={() =>
                setPortfolio((p) => ({ ...p, allocation: { ...p.allocation, base: b } }))
              }
              className={`rounded border px-2 py-1 text-[11px] ${
                portfolio.allocation?.base === b
                  ? "border-accent bg-accent-soft text-ink"
                  : "border-line bg-surface-sunk text-ink-muted hover:border-accent/50"
              }`}
            >
              {b}
            </button>
          ))}
        </div>
        {portfolio.allocation?.base === "weights" && (
          <div className="mt-2">
            <p className="text-[10px] text-ink-faint">
              Weights (leg strategy_name → weight; blank = equal)
            </p>
            <textarea
              value={JSON.stringify(portfolio.allocation?.weights ?? {}, null, 2)}
              onChange={(e) => {
                try {
                  const weights = JSON.parse(e.target.value) as Record<string, number>;
                  setPortfolio((p) => ({ ...p, allocation: { ...p.allocation, weights } }));
                } catch {
                  // ignore partial JSON while typing
                }
              }}
              className="mt-1 w-full rounded border border-line bg-surface-sunk p-2 font-mono text-[11px] text-ink"
              rows={4}
            />
          </div>
        )}
      </div>

      {/* Compile */}
      <div className="rounded border border-line bg-surface px-3 py-3">
        <button
          type="button"
          onClick={() => void doCompile()}
          className="rounded-lg bg-accent px-4 py-2 text-xs font-bold text-accent-fg hover:opacity-90"
        >
          Compile Portfolio
        </button>
        {compileError && <p className="mt-2 text-[11px] text-danger">{compileError}</p>}
        {compiled && (
          <div className="mt-2">
            <p className="text-[11px] text-ink-muted">
              ✓ Compiled →{" "}
              {String(
                (compiled as { Framework?: { Alpha?: { Type?: string } } }).Framework?.Alpha?.Type ??
                  "VeraLabV1",
              )}
            </p>
            <pre className="mt-2 max-h-80 overflow-auto rounded border border-line bg-surface-sunk p-2 font-mono text-[10px] text-ink-muted">
              {JSON.stringify(compiled, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}