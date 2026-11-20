import { useMemo } from "react";
import { buildBacktestRecommendations } from "../lib/recommendations";
import type { RecommendationSeverity } from "../lib/recommendations";
import type { BacktestReport } from "../types";

const SEVERITY_LABEL: Record<RecommendationSeverity, string> = {
  action: "Action",
  watch: "Watch",
  info: "Info",
};

const SEVERITY_CLASS: Record<RecommendationSeverity, string> = {
  action: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  watch: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  info: "bg-sky-500/15 text-sky-300 border-sky-500/30",
};

export function RecommendationsPanel({ report }: { report: BacktestReport }) {
  const recommendations = useMemo(() => buildBacktestRecommendations(report), [report]);

  if (recommendations.length === 0) return null;

  return (
    <section className="mb-4">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-ink-faint">
        Recommendations
      </h3>
      <ul className="mt-2 space-y-1.5">
        {recommendations.map((r) => (
          <li
            key={r.id}
            className="rounded border border-line bg-surface px-2.5 py-2"
          >
            <div className="flex flex-wrap items-center gap-1.5">
              <span
                className={`rounded border px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase ${SEVERITY_CLASS[r.severity]}`}
              >
                {SEVERITY_LABEL[r.severity]}
              </span>
              <span className="rounded bg-surface-sunk px-1.5 py-0.5 font-mono text-[9px] text-ink-muted border border-line">
                {r.slot}
              </span>
              <span className="text-[12px] font-semibold text-ink">{r.title}</span>
            </div>
            <p className="mt-1 text-[11.5px] leading-relaxed text-ink-muted">
              {r.body}
            </p>
            <p className="mt-1.5 rounded bg-surface-sunk px-2 py-1 font-mono text-[10.5px] text-accent-ink">
              {r.action}
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}