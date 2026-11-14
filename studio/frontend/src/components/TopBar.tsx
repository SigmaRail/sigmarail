import { cn } from "../lib/utils";
import type { WorkbenchTab } from "../types";
import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";
import { fetchExecutionHealth } from "../api/backtests";
import { TAB_PATHS } from "../routes";

export const WORKBENCH_TABS: { id: WorkbenchTab; label: string; icon: string }[] = [
  { id: "screens", label: "Screens", icon: "🔍" },
  { id: "charts", label: "Charts", icon: "📈" },
  { id: "watchlists", label: "Watchlists", icon: "📑" },
  { id: "market", label: "Market", icon: "🌐" },
  { id: "compose", label: "Strategies", icon: "🎛️" },
  { id: "runs", label: "Backtests", icon: "📊" },
  { id: "optimize", label: "Optimize", icon: "⚡" },
  { id: "deploy", label: "Deploy", icon: "🚀" },
  { id: "monitor", label: "Monitor", icon: "🛡️" },
];

export function TopBar({
  showSave,
  dirty,
  saving,
  onSave,
  onSaveAs,
}: {
  showSave?: boolean;
  dirty?: boolean;
  saving?: boolean;
  onSave?: () => void;
  onSaveAs?: () => void;
}) {
  const healthQuery = useQuery({
    queryKey: ["execution-health"],
    queryFn: fetchExecutionHealth,
    refetchInterval: 30_000,
  });

  const h = healthQuery.data;

  return (
    <header className="flex min-h-[46px] shrink-0 flex-wrap items-center justify-between gap-3 border-b border-line bg-surface-raised px-3 sm:px-4 py-1.5 shadow-panel">
      {/* Brand & Unified Lifecycle Navigation */}
      <div className="flex items-center gap-4 sm:gap-6">
        <div className="flex items-baseline gap-1.5 shrink-0">
          <h1 className="text-[14px] sm:text-[15px] font-bold tracking-tight text-ink">
            Screening Studio
          </h1>
          <span className="hidden sm:inline font-mono text-[9px] uppercase tracking-wider text-ink-faint">
            Workbench
          </span>
        </div>

        {/* Single Full-Lifecycle Pipeline Bar */}
        <nav className="inline-flex rounded-lg border border-line bg-surface-sunk p-0.5" aria-label="Workbench Lifecycle">
          {WORKBENCH_TABS.map((t) => (
            <NavLink
              key={t.id}
              to={TAB_PATHS[t.id]}
              className={({ isActive }) =>
                cn(
                  "rounded-md px-3 py-1 text-xs font-semibold transition-all flex items-center gap-1.5 shrink-0 cursor-pointer",
                  isActive
                    ? "bg-ink text-white shadow-xs font-bold"
                    : "text-ink-muted hover:text-ink hover:bg-surface/50"
                )
              }
            >
              <span>{t.icon}</span>
              <span>{t.label}</span>
            </NavLink>
          ))}
        </nav>
      </div>

      {/* Right Side: Health Status Badges & Actions */}
      <div className="flex items-center gap-2 shrink-0">
        {h && (
          <div className="hidden md:flex items-center gap-1.5 rounded border border-line bg-surface px-2 py-0.5 text-[10.5px] font-mono text-ink-muted">
            <span className={cn("inline-block h-2 w-2 rounded-full", h.ready ? "bg-emerald-500" : "bg-warn")} />
            <span className={h.docker ? "text-emerald-400" : "text-ink-faint"}>docker</span>
            <span>·</span>
            <span className={h.lean_cli ? "text-emerald-400" : "text-ink-faint"}>lean</span>
            <span>·</span>
            <span className={h.clickhouse ? "text-emerald-400" : "text-ink-faint"}>ch</span>
            <span>·</span>
            <span className={h.worker_recent ? "text-emerald-400" : "text-ink-faint"}>worker</span>
          </div>
        )}

        {showSave ? (
          <div className="flex items-center gap-1.5 shrink-0">
            {dirty ? (
              <span className="mr-1 font-mono text-[9.5px] uppercase tracking-wider text-warn font-bold">
                Unsaved
              </span>
            ) : null}
            <button
              type="button"
              disabled={saving || !onSave}
              onClick={() => onSave?.()}
              className="rounded border border-line bg-surface-sunk px-2.5 py-1 text-[11.5px] font-semibold text-ink hover:border-accent hover:bg-accent-soft disabled:opacity-50 transition-colors cursor-pointer"
            >
              {saving ? "Saving…" : "Save"}
            </button>
            <button
              type="button"
              disabled={saving || !onSaveAs}
              onClick={() => onSaveAs?.()}
              className="rounded border border-line bg-surface-sunk px-2.5 py-1 text-[11.5px] font-semibold text-ink hover:border-accent hover:bg-accent-soft disabled:opacity-50 transition-colors cursor-pointer"
            >
              Save As
            </button>
          </div>
        ) : null}
      </div>
    </header>
  );
}
