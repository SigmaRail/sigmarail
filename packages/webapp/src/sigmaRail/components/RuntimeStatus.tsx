import { useEffect, useState } from "react";
import { Button } from "@sb/webapp-core/components/ui/button";
import { authenticatedFetch } from "../api/authenticatedFetch";

type BuildIdentity = { revision: string; branch: string; source_tree: string };
type UiRuntimeIdentity = BuildIdentity & {
  dirty: boolean;
  process: { pid: number; cwd: string; port: number | null };
  browser_origin: string | null;
  tailscale: unknown;
};
type ApiIdentity = BuildIdentity & {
  container: string;
  image: string;
  ports: { container: string; published: string };
  tailscale: { host: string; port: string; target: string };
};

declare const __SIGMARAIL_BUILD__: BuildIdentity;

export function RuntimeStatus() {
  const [open, setOpen] = useState(false);
  const [api, setApi] = useState<ApiIdentity | null>(null);
  const [ui, setUi] = useState<UiRuntimeIdentity | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let current = true;
    const fetchIdentity = async <T,>(url: string) => {
      const response = await authenticatedFetch(url, { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`${url} returned HTTP ${response.status}`);
      return response.json() as Promise<T>;
    };
    Promise.all([
      fetchIdentity<ApiIdentity>("/api/runtime/identity"),
      fetchIdentity<UiRuntimeIdentity>("/runtime/identity"),
    ])
      .then(([apiIdentity, uiIdentity]) => {
        if (current) { setApi(apiIdentity); setUi(uiIdentity); setError(null); }
      })
      .catch((reason: unknown) => { if (current) setError(reason instanceof Error ? reason.message : "Runtime identity unavailable"); });
    return () => { current = false; };
  }, [open]);

  const aligned = Boolean(api && api.revision !== "unknown" && api.revision === __SIGMARAIL_BUILD__.revision);
  return (
    <div className="relative ml-auto">
      <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-[11px]" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        Runtime: {api ? (aligned ? "aligned" : "mismatch") : "check"}
      </Button>
      {open ? (
        <section className="absolute right-0 top-8 z-50 w-[min(92vw,28rem)] rounded-md border border-line bg-surface p-3 text-xs shadow-xl" aria-label="Runtime identity">
          <h2 className="mb-2 font-semibold">Running build identity</h2>
          <dl className="grid grid-cols-[6rem_1fr] gap-x-2 gap-y-1">
            <dt>UI revision</dt><dd className="break-all">{__SIGMARAIL_BUILD__.revision}</dd>
            <dt>UI branch</dt><dd className="break-all">{__SIGMARAIL_BUILD__.branch}</dd>
            <dt>UI source</dt><dd className="break-all">{ui?.source_tree ?? __SIGMARAIL_BUILD__.source_tree}</dd>
            <dt>UI process</dt><dd className="break-all">{ui ? `PID ${ui.process.pid} · port ${ui.process.port ?? "unknown"}` : "—"}</dd>
            <dt>UI cwd</dt><dd className="break-all">{ui?.process.cwd ?? "—"}</dd>
            <dt>Browser URL</dt><dd className="break-all">{ui?.browser_origin ?? window.location.origin}</dd>
            <dt>UI dirty</dt><dd>{ui ? (ui.dirty ? "yes (tracked source changes)" : "no") : "—"}</dd>
            <dt>API revision</dt><dd className="break-all">{api?.revision ?? error ?? "Checking…"}</dd>
            <dt>API branch</dt><dd className="break-all">{api?.branch ?? "—"}</dd>
            <dt>API source</dt><dd className="break-all">{api?.source_tree ?? "—"}</dd>
            <dt>API container</dt><dd className="break-all">{api?.container ?? "—"}</dd>
            <dt>API image</dt><dd className="break-all">{api?.image ?? "—"}</dd>
            <dt>API ports</dt><dd>{api ? `${api.ports.published} → ${api.ports.container}` : "—"}</dd>
            <dt>Tailscale</dt><dd className="break-all">{api ? `${api.tailscale.host}:${api.tailscale.port} → ${api.tailscale.target}` : "—"}</dd>
            {ui ? <><dt>Serve config</dt><dd className="break-all"><pre className="max-h-24 overflow-auto whitespace-pre-wrap">{JSON.stringify(ui.tailscale, null, 2)}</pre></dd></> : null}
            <dt>Status</dt><dd>{error ? "API identity unavailable" : !api ? "Checking API" : aligned ? "UI and API revisions match" : "UI and API revisions differ or API metadata is unknown"}</dd>
          </dl>
        </section>
      ) : null}
    </div>
  );
}
