import { useState, type ReactNode } from "react";
import { Button } from "@sb/webapp-core/components/ui/button";

/** Same position and compact disclosure for point-in-time history in both screener surfaces. */
export function ScreenerMembershipHistory({
  children,
  defaultOpen = true,
}: {
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="min-w-0 border-b border-line bg-surface">
      <Button
        type="button"
        onClick={() => setOpen((value) => !value)}
        variant="ghost"
        className="h-auto w-full justify-between rounded-none px-3 py-2 text-left"
        aria-expanded={open}
      >
        <span className="text-[10px] font-semibold uppercase tracking-wide text-ink-muted">Membership history</span>
        <span className="font-mono text-[10px] text-ink-muted" aria-hidden="true">{open ? "⌄" : "›"}</span>
      </Button>
      {open ? <div className="border-t border-line px-3 py-2">{children}</div> : null}
    </section>
  );
}
