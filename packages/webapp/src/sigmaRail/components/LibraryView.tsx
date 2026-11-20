import { useMemo, useState } from "react";
import type { ScreenPreset } from "../types";

export function LibraryView({
  presets,
  selectedId,
  onSelect,
}: {
  presets: ScreenPreset[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  const [q, setQ] = useState("");
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return presets;
    return presets.filter(
      (p) =>
        p.id.toLowerCase().includes(needle) ||
        p.label.toLowerCase().includes(needle),
    );
  }, [presets, q]);

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-surface-raised">
      <div className="border-b border-line px-4 py-3">
        <h2 className="text-sm font-semibold text-ink">Preset library</h2>
        <p className="mt-0.5 text-[12px] text-ink-muted">
          Search named screen_stocks presets. Selecting one opens Screen mode.
        </p>
        <input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Filter by id or label…"
          className="mt-2 w-full max-w-md rounded border border-line bg-white px-2.5 py-1.5 text-[13px] outline-none focus:border-highlight"
        />
      </div>
      <ul className="flex-1 overflow-y-auto divide-y divide-line">
        {filtered.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              onClick={() => onSelect(p.id)}
              className="flex w-full items-center justify-between px-4 py-2.5 text-left hover:bg-surface-sunk"
            >
              <div>
                <div className="text-[13px] font-medium text-ink">
                  {p.label}
                </div>
                <div className="font-mono text-[11px] text-ink-faint">
                  {p.id}
                </div>
              </div>
              {p.id === selectedId ? (
                <span className="rounded bg-accent-soft px-1.5 py-0.5 text-[10px] font-semibold uppercase text-accent">
                  active
                </span>
              ) : null}
            </button>
          </li>
        ))}
        {filtered.length === 0 ? (
          <li className="px-4 py-8 text-center text-sm text-ink-muted">
            No presets match
          </li>
        ) : null}
      </ul>
    </div>
  );
}
