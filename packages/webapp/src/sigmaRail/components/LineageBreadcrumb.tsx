import type { ReactNode } from "react";

function truncateId(id: string, head = 8, tail = 4): string {
  if (id.length <= head + tail + 1) return id;
  return `${id.slice(0, head)}…${id.slice(-tail)}`;
}

function Crumb({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <span className="inline-flex items-baseline gap-1">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
        {label}
      </span>
      <span
        className={
          mono
            ? "font-mono text-[11px] text-ink"
            : "text-[11px] font-medium text-ink"
        }
        title={value}
      >
        {mono ? truncateId(value) : value}
      </span>
    </span>
  );
}

export function LineageBreadcrumb({
  screenName,
  irId,
  runId,
  deploymentId,
}: {
  screenName?: string | null;
  irId?: string | null;
  runId?: string | null;
  deploymentId?: string | null;
}) {
  const crumbs: ReactNode[] = [];

  if (screenName?.trim()) {
    crumbs.push(
      <Crumb key="screen" label="Screen" value={screenName.trim()} />,
    );
  }
  if (irId?.trim()) {
    crumbs.push(<Crumb key="ir" label="IR" value={irId.trim()} mono />);
  }
  if (runId?.trim()) {
    crumbs.push(<Crumb key="run" label="Run" value={runId.trim()} mono />);
  }
  if (deploymentId?.trim()) {
    crumbs.push(
      <Crumb key="deploy" label="Deploy" value={deploymentId.trim()} mono />,
    );
  }

  if (crumbs.length === 0) return null;

  return (
    <nav
      className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px]"
      aria-label="Lineage"
    >
      {crumbs.map((crumb, i) => (
        <span key={i} className="inline-flex items-center gap-2">
          {i > 0 ? (
            <span className="text-ink-faint" aria-hidden="true">
              /
            </span>
          ) : null}
          {crumb}
        </span>
      ))}
    </nav>
  );
}
