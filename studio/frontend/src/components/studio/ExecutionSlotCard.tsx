import type { FillSession } from "../../lib/pipelineSlotBindings";

interface ExecutionSlotCardProps {
  fillSession: FillSession;
  onChangeFillSession: (v: FillSession) => void;
}

export function ExecutionSlotCard({
  fillSession,
  onChangeFillSession,
}: ExecutionSlotCardProps) {
  return (
    <div className="space-y-2 rounded-lg border border-line bg-surface p-3.5 shadow-sm">
      <div className="flex items-center justify-between border-b border-line pb-2">
        <h4 className="text-[12.5px] font-bold text-ink">5. Execution</h4>
        <span className="font-mono text-[10px] text-ink-muted">VeraScreenerExecutionModel</span>
      </div>
      <p className="text-[10.5px] text-ink-muted leading-tight">
        MOO schedules BeforeMarketOpen and fills MarketOnOpen. MOC schedules BeforeMarketClose
        and fills MarketOnClose. Signal as-of stays T-1 either way. This tape has no minute history.
      </p>
      <div className="flex gap-2">
        {(["moo", "moc"] as const).map((session) => (
          <button
            key={session}
            type="button"
            title={
              session === "moo"
                ? "Evaluate signals on T-1 close, fill at the T open — classic overnight-gap swing entry"
                : "Evaluate signals on T close data, fill at that same close — no overnight gap between decision and fill"
            }
            onClick={() => onChangeFillSession(session)}
            className={
              fillSession === session
                ? "rounded border border-accent bg-accent/10 px-2 py-1 text-[11px] font-semibold text-accent-ink"
                : "rounded border border-line px-2 py-1 text-[11px] text-ink-muted"
            }
          >
            {session === "moo" ? "MOO (open of T)" : "MOC (close of T)"}
          </button>
        ))}
      </div>
      <p className="text-[9px] leading-snug text-ink-faint">
        Choice affects fill price only — sizing (1R), scale-in phases, and exits are unchanged.
        MOC is the more conservative backtest fill because the decision and the fill share a
        bar; MOO implicitly trades the overnight gap.
      </p>
    </div>
  );
}
