import type { StrategyDecisionEvent, StrategyDecisionStage } from "../../types";

const STAGE_LABELS: Record<StrategyDecisionStage, string> = {
  universe: "Universe",
  alpha: "Alpha",
  portfolio: "Portfolio",
  risk: "Risk",
  execution: "Execution",
};

function display(value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

export function StrategyDecisionTimeline({
  events,
  asOf,
  startAt,
  endAt,
  strategyHash,
  sourceLabel = "Recorded strategy decisions",
}: {
  events: StrategyDecisionEvent[];
  asOf?: string;
  startAt?: string;
  endAt?: string;
  strategyHash?: string | null;
  sourceLabel?: string;
}) {
  const filtered = [...events]
    .filter((event) => {
      const date = event.as_of.slice(0, 10);
      if (startAt && date < startAt.slice(0, 10)) return false;
      if (endAt && date > endAt.slice(0, 10)) return false;
      return !asOf || startAt || endAt || date === asOf.slice(0, 10);
    })
    .sort((a, b) => a.observed_at.localeCompare(b.observed_at));

  return (
    <section className="border-b border-line bg-surface px-3 py-3 sm:px-4" aria-label="Strategy decision timeline">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-xs font-semibold text-ink">Strategy decisions</h2>
        <div className="font-mono text-[9px] text-ink-muted">
          {sourceLabel}{strategyHash ? ` · spec ${strategyHash.slice(0, 12)}` : " · strategy hash unavailable"}
        </div>
      </div>
      {filtered.length ? (
        <ol className="mt-2 space-y-2">
          {filtered.map((event, index) => (
            <li key={event.event_id ?? `${event.stage}-${event.observed_at}-${index}`} className="grid min-w-0 grid-cols-[5.5rem_minmax(0,1fr)] gap-x-3 rounded border border-line/70 px-2.5 py-2 text-[10px] sm:grid-cols-[6.5rem_minmax(0,1fr)]">
              <div>
                <div className="font-semibold text-ink">{STAGE_LABELS[event.stage] ?? event.stage}</div>
                <time className="font-mono text-[9px] text-ink-muted" dateTime={event.observed_at}>{event.observed_at.replace("T", " ").slice(0, 16)}</time>
              </div>
              <div className="min-w-0">
                <div className="font-semibold text-ink">{event.outcome}{event.rule_name ? ` · ${event.rule_name}` : ""}</div>
                {event.reason ? <p className="mt-0.5 break-words text-ink-muted">{event.reason}</p> : null}
                {(event.inputs || event.outputs) ? (
                  <dl className="mt-1 grid grid-cols-[auto_minmax(0,1fr)] gap-x-2 gap-y-0.5 font-mono text-[9px] text-ink-muted">
                    {Object.entries(event.inputs ?? {}).map(([key, value]) => <div key={`in-${key}`} className="contents"><dt>{key}</dt><dd className="truncate text-right" title={display(value)}>{display(value)}</dd></div>)}
                    {Object.entries(event.outputs ?? {}).map(([key, value]) => <div key={`out-${key}`} className="contents"><dt>{key}</dt><dd className="truncate text-right" title={display(value)}>{display(value)}</dd></div>)}
                  </dl>
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-2 rounded border border-dashed border-line px-2.5 py-3 text-[10px] text-ink-muted">
          {events.length
            ? `No recorded decisions match this symbol and selection${startAt || endAt ? ` from ${startAt ?? "start"} through ${endAt ?? "now"}` : asOf ? ` for ${asOf}` : ""}. Other strategy evidence exists outside this selection.`
            : `No recorded decision events are available${startAt || endAt ? ` from ${startAt ?? "start"} through ${endAt ?? "now"}` : asOf ? ` for ${asOf}` : ""}. This record may predate decision evidence capture.`}
        </p>
      )}
    </section>
  );
}
