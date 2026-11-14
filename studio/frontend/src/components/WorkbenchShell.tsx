import { useEffect, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation } from "react-router-dom";
import { fetchExecutionHealth } from "../api/backtests";
import { TAB_PATHS, tabForPath } from "../routes";
import type { WorkbenchTab } from "../types";

const groups = [
  { label: "Research", tabs: ["compose", "screens", "charts", "watchlists", "market", "runs", "optimize"] },
  { label: "Deploy", tabs: ["deploy"] },
  { label: "Monitor", tabs: ["monitor"] },
] as const;

const destinations: Record<WorkbenchTab, [string, string]> = {
  compose: ["Strategies", "St"], screens: ["Screens", "Sc"], charts: ["Charts", "Ch"],
  watchlists: ["Watchlists", "Wl"], market: ["Market", "Mk"], runs: ["Backtests", "Bt"],
  optimize: ["Optimize", "Op"], deploy: ["Deploy", "De"], monitor: ["Monitor", "Mo"],
};

export function WorkbenchShell({ children }: { children: ReactNode }) {
  const location = useLocation();
  const active = tabForPath(location.pathname);
  const address = location.pathname + location.search + location.hash;
  const lastAddress = useRef<Partial<Record<WorkbenchTab, string>>>({});
  const dialog = useRef<HTMLDialogElement>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [compact, setCompact] = useState(() => window.matchMedia("(max-width: 1199px)").matches);
  const health = useQuery({
    queryKey: ["execution-health"], queryFn: fetchExecutionHealth, refetchInterval: 30_000,
  }).data;

  useEffect(() => {
    lastAddress.current[active] = address;
    dialog.current?.close();
  }, [active, address]);

  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 1024px)");
    function closeOnDesktop() {
      if (desktop.matches) dialog.current?.close();
    }
    desktop.addEventListener("change", closeOnDesktop);
    return () => desktop.removeEventListener("change", closeOnDesktop);
  }, []);

  function navigation(collapsed: boolean) {
    return (
      <nav aria-label="Workbench lifecycle" className="workbench-nav">
        {groups.map(group => (
          <div key={group.label} role="group" aria-label={group.label}>
            <h2 className={collapsed ? "sr-only" : "nav-group-label"}>{group.label}</h2>
            {group.tabs.map(tab => {
              const [label, abbreviation] = destinations[tab];
              return (
                <Link key={tab} to={tab === active ? address : lastAddress.current[tab] ?? TAB_PATHS[tab]}
                  aria-current={active === tab ? "page" : undefined}
                  title={collapsed ? label : undefined} aria-label={label}
                  onClick={() => dialog.current?.close()}>
                  {collapsed ? abbreviation : label}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
    );
  }

  return (
    <div className="workbench">
      <header className="workbench-header">
        <button type="button" className="workbench-control lg:hidden" aria-label="Open navigation"
          aria-controls="workbench-menu" aria-haspopup="dialog" aria-expanded={drawerOpen}
          onClick={() => { dialog.current?.showModal(); setDrawerOpen(true); }}>
          <span aria-hidden="true">☰</span> Menu
        </button>
        <h1 className="font-semibold tracking-tight">SigmaRail Studio</h1>
        <span className="truncate text-xs text-ink-muted">{destinations[active][0]}</span>
        {health && (
          <div className="ml-auto hidden items-center gap-2 font-mono text-xs text-ink-muted md:flex" aria-label="Execution health">
            <span className={health.ready ? "text-accent" : "text-warn"}>{health.ready ? "Ready" : "Unavailable"}</span>
            {([["docker", health.docker], ["lean", health.lean_cli], ["ch", health.clickhouse], ["worker", health.worker_recent]] as const).map(
              ([name, ready]) => <span key={name} className={ready ? "text-accent" : "text-ink-muted"} title={ready ? "Available" : "Unavailable"}>{name}</span>
            )}
          </div>
        )}
      </header>
      <div className="flex min-h-0 min-w-0 flex-1">
        <aside className={`workbench-sidebar ${compact ? "w-16" : "w-44"}`}>
          <button type="button" className="workbench-control" aria-label={compact ? "Expand navigation" : "Collapse navigation"}
            aria-expanded={!compact} onClick={() => setCompact(!compact)}>{compact ? "»" : "« Collapse"}</button>
          {navigation(compact)}
        </aside>
        <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-auto">{children}</main>
      </div>
      <dialog id="workbench-menu" ref={dialog} aria-label="Navigation" className="workbench-drawer"
        onClose={() => setDrawerOpen(false)} onClick={event => {
          if (event.target === event.currentTarget && event.clientX >= event.currentTarget.getBoundingClientRect().right) dialog.current?.close();
        }}>
        <button type="button" autoFocus className="workbench-control" onClick={() => dialog.current?.close()}>Close menu</button>
        {navigation(false)}
      </dialog>
    </div>
  );
}
