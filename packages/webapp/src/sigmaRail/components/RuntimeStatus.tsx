import { useEffect, useState } from "react";
import { Button } from "@sb/webapp-core/components/ui/button";
import { authenticatedFetch } from "../api/authenticatedFetch";

type BuildIdentity = { revision: string; branch: string; source_tree: string };
type ApiIdentity = { revision: string; branch: string; source_tree: string; image: string };

declare const __SIGMARAIL_BUILD__: BuildIdentity;

export function RuntimeStatus() {
  const [open, setOpen] = useState(false);
  const [api, setApi] = useState<ApiIdentity | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let current = true;
    authenticatedFetch("/api/runtime/identity", { headers: { Accept: "application/json" } })
      .then(async (response) => {
        if (!response.ok) throw new Error(`API returned HTTP ${response.status}`);
        return response.json() as Promise<ApiIdentity>;
      })
      .then((identity) => { if (current) { setApi(identity); setError(null); } })
      .catch((reason: unknown) => { if (current) setError(reason instanceof Error ? reason.message : "API identity unavailable"); });
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
            <dt>UI source</dt><dd className="break-all">{__SIGMARAIL_BUILD__.source_tree}</dd>
            <dt>API revision</dt><dd className="break-all">{api?.revision ?? error ?? "Checking…"}</dd>
            <dt>API branch</dt><dd className="break-all">{api?.branch ?? "—"}</dd>
            <dt>API source</dt><dd className="break-all">{api?.source_tree ?? "—"}</dd>
            <dt>API image</dt><dd className="break-all">{api?.image ?? "—"}</dd>
            <dt>Status</dt><dd>{error ? "API identity unavailable" : !api ? "Checking API" : aligned ? "UI and API revisions match" : "UI and API revisions differ or API metadata is unknown"}</dd>
          </dl>
        </section>
      ) : null}
    </div>
  );
}
