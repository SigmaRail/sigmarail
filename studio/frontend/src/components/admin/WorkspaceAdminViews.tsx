import { useQuery } from "@tanstack/react-query";
import { fetchExecutionHealth } from "../../api/backtests";
import { PageHeader, Panel } from "../ui/primitives";

function ServiceStatus({ label, ready }: { label: string; ready: boolean }) {
  return (
    <div className="admin-status-row">
      <span>{label}</span>
      <span className={`admin-status ${ready ? "admin-status-ready" : "admin-status-down"}`}>
        <i aria-hidden="true" />{ready ? "Available" : "Unavailable"}
      </span>
    </div>
  );
}

export function WorkspaceSettingsView() {
  const health = useQuery({ queryKey: ["execution-health"], queryFn: fetchExecutionHealth, refetchInterval: 30_000 }).data;

  return (
    <div className="admin-page">
      <PageHeader title="Settings" description="Workspace configuration and service status." />
      <div className="admin-grid">
        <Panel>
          <div className="admin-panel-heading"><div><h2>Workspace</h2><p>Application and data context for this Studio.</p></div></div>
          <dl className="admin-settings-list">
            <div><dt>Product</dt><dd>SigmaRail Studio</dd></div>
            <div><dt>Strategy format</dt><dd>Five-slot pipeline</dd></div>
            <div><dt>Market data</dt><dd>SigmaRail data services</dd></div>
          </dl>
        </Panel>
        <Panel>
          <div className="admin-panel-heading"><div><h2>Services</h2><p>Live availability reported by the connected Studio API.</p></div></div>
          {health ? <div className="admin-status-list">
            <ServiceStatus label="Execution" ready={health.ready} />
            <ServiceStatus label="ClickHouse" ready={health.clickhouse} />
            <ServiceStatus label="LEAN CLI" ready={health.lean_cli} />
            <ServiceStatus label="Worker" ready={health.worker_recent} />
          </div> : <p className="admin-empty-state">Service status is unavailable. Check the Studio API connection.</p>}
        </Panel>
      </div>
    </div>
  );
}

export function WorkspaceProfileView() {
  return (
    <div className="admin-page">
      <PageHeader title="Profile" description="Account and personal workspace details." />
      <Panel className="admin-profile-panel">
        <div className="admin-avatar" aria-hidden="true">SR</div>
        <div className="min-w-0"><h2>Local workspace</h2><p>This Studio deployment does not currently expose signed-in profile data.</p></div>
      </Panel>
      <p className="admin-note">Profile editing will be available when SigmaRail account authentication is connected to this deployment.</p>
    </div>
  );
}
