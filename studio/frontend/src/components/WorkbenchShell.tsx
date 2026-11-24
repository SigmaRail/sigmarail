import { useEffect, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useLocation } from "react-router-dom";
import { fetchExecutionHealth } from "../api/backtests";
import { TAB_PATHS, tabForPath } from "../routes";
import type { WorkbenchTab } from "../types";
import { Button } from "./ui/primitives";

const groups = [
  { label: "Research", tabs: ["compose", "screens", "charts", "watchlists", "market"] },
  { label: "Backtests", tabs: ["runs", "optimize"] },
  { label: "Deploy", tabs: ["deploy"] },
  { label: "Monitor", tabs: ["monitor"] },
  { label: "Settings", tabs: ["settings"] },
  { label: "Profile", tabs: ["profile"] },
] as const;

const destinations: Record<WorkbenchTab, [string, string]> = {
  compose: ["Strategies", "St"], screens: ["Screens", "Sc"], charts: ["Charts", "Ch"],
  watchlists: ["Watchlists", "Wl"], market: ["Market", "Mk"], runs: ["Backtests", "Bt"],
  optimize: ["Optimize", "Op"], deploy: ["Deploy", "De"], monitor: ["Monitor", "Mo"],
  settings: ["Settings", "Se"], profile: ["Profile", "Pr"],
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
        <Button type="button" variant="ghost" className="workbench-control" aria-label="Open navigation"
          aria-controls="workbench-menu" aria-haspopup="dialog" aria-expanded={drawerOpen}
          onClick={() => { dialog.current?.showModal(); setDrawerOpen(true); }}>
          <span aria-hidden="true">☰</span><span className="hidden sm:inline">Menu</span>
        </Button>
        <Link to={TAB_PATHS.screens} className="workbench-brand"><span className="workbench-brand-mark" aria-hidden="true">S</span><span>SigmaRail</span></Link>
        <span className="hidden text-ink-faint sm:inline" aria-hidden="true">/</span>
        <span className="truncate text-sm font-medium text-ink-muted">{destinations[active][0]}</span>
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
          <Button type="button" variant="ghost" className="workbench-collapse" aria-label={compact ? "Expand navigation" : "Collapse navigation"}
            aria-expanded={!compact} onClick={() => setCompact(!compact)}>{compact ? "»" : "Collapse"}</Button>
          {navigation(compact)}
        </aside>
        <main className="flex min-h-0 min-w-0 flex-1 flex-col overflow-auto">{children}</main>
      </div>
      <dialog id="workbench-menu" ref={dialog} aria-label="Navigation" className="workbench-drawer"
        onClose={() => setDrawerOpen(false)} onClick={event => {
          if (event.target === event.currentTarget && event.clientX >= event.currentTarget.getBoundingClientRect().right) dialog.current?.close();
        }}>
        <div className="workbench-drawer-heading"><strong>Workspace</strong><Button type="button" variant="ghost" onClick={() => dialog.current?.close()}>Close</Button></div>
        {navigation(false)}
      </dialog>
    </div>
  );
}
