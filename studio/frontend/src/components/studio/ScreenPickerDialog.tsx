import { useState, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { cn } from "../../lib/utils";
import { deleteSavedScreen } from "../../api/screens";
import type { SavedScreen } from "../../types";

interface ScreenPickerDialogProps {
  isOpen: boolean;
  onClose: () => void;
  screens: SavedScreen[];
  onSelectScreen: (screen: SavedScreen) => void;
}

type FilterCategory = "all" | "system" | "custom";

export function ScreenPickerDialog({
  isOpen,
  onClose,
  screens,
  onSelectScreen,
}: ScreenPickerDialogProps) {
  const [filter, setFilter] = useState<FilterCategory>("all");
  const [search, setSearch] = useState("");
  const queryClient = useQueryClient();

  const deleteMutation = useMutation({
    mutationFn: (id: string | number) => deleteSavedScreen(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["saved-screens"] });
      queryClient.invalidateQueries({ queryKey: ["saved-screens-dialog"] });
    },
  });

  useEffect(() => {
    if (!isOpen) return;
    function handler(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const systemScreens = screens.filter((s) => s.is_system);
  const customScreens = screens.filter((s) => !s.is_system);

  const displayedScreens = screens.filter((s) => {
    if (filter === "system" && !s.is_system) return false;
    if (filter === "custom" && s.is_system) return false;
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      s.name.toLowerCase().includes(q) ||
      (s.description && s.description.toLowerCase().includes(q)) ||
      String(s.id).toLowerCase().includes(q)
    );
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className="flex w-[min(580px,94vw)] flex-col rounded-xl border border-line bg-surface shadow-2xl overflow-hidden max-h-[78vh]">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-line bg-surface-raised px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-bold text-ink">📂 Load Universe Screen</span>
            <span className="text-[11px] font-mono text-ink-muted">({screens.length} available)</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-line bg-surface-sunk px-2.5 py-1 text-[11px] font-semibold text-ink-muted hover:text-ink transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Filter Pills + Search */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-surface-raised px-4 py-2">
          <div className="inline-flex rounded border border-line bg-surface-sunk p-0.5">
            <button
              type="button"
              onClick={() => setFilter("all")}
              className={cn(
                "rounded px-2.5 py-1 text-[11px] font-semibold transition-colors",
                filter === "all" ? "bg-accent text-surface-canvas font-bold shadow-sm" : "text-ink-muted hover:text-ink"
              )}
            >
              All ({screens.length})
            </button>
            <button
              type="button"
              onClick={() => setFilter("system")}
              className={cn(
                "rounded px-2.5 py-1 text-[11px] font-semibold transition-colors",
                filter === "system" ? "bg-accent text-surface-canvas font-bold shadow-sm" : "text-ink-muted hover:text-ink"
              )}
            >
              ⭐ System ({systemScreens.length})
            </button>
            <button
              type="button"
              onClick={() => setFilter("custom")}
              className={cn(
                "rounded px-2.5 py-1 text-[11px] font-semibold transition-colors",
                filter === "custom" ? "bg-accent text-surface-canvas font-bold shadow-sm" : "text-ink-muted hover:text-ink"
              )}
            >
              💾 Custom ({customScreens.length})
            </button>
          </div>

          <input
            type="text"
            placeholder="Search screens…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-44 rounded border border-line bg-surface px-2.5 py-1 text-[11px] text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none"
          />
        </div>

        {/* Unified Screen List */}
        <div className="flex-1 overflow-y-auto min-h-0 divide-y divide-line">
          {displayedScreens.length === 0 ? (
            <div className="p-8 text-center text-[12px] text-ink-muted">
              No screens found matching your filter or search criteria.
            </div>
          ) : (
            displayedScreens.map((s) => (
              <div
                key={String(s.id)}
                className="flex items-center justify-between px-4 py-3 hover:bg-surface-sunk transition-colors group"
              >
                <button
                  type="button"
                  onClick={() => { onSelectScreen(s); onClose(); }}
                  className="flex-1 text-left flex flex-col gap-0.5 cursor-pointer pr-3"
                >
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-[12px] text-ink group-hover:text-accent transition-colors">
                      {s.name}
                    </span>
                    {s.is_system ? (
                      <span className="text-[9.5px] font-mono px-1.5 py-0.2 rounded border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 font-semibold">
                        ⭐ System
                      </span>
                    ) : (
                      <span className="text-[9.5px] font-mono px-1.5 py-0.2 rounded border border-line bg-surface-raised text-ink-muted font-semibold">
                        💾 Custom
                      </span>
                    )}
                  </div>

                  {s.description ? (
                    <span className="font-mono text-[10.5px] text-ink-faint leading-tight">
                      {s.description}
                    </span>
                  ) : s.created_at ? (
                    <span className="font-mono text-[10px] text-ink-faint">
                      Saved {new Date(s.created_at).toLocaleDateString()}
                    </span>
                  ) : null}
                </button>

                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => { onSelectScreen(s); onClose(); }}
                    className="rounded border border-accent/30 bg-accent/10 px-2.5 py-1 text-[11px] font-bold text-accent hover:bg-accent hover:text-surface-canvas transition-colors"
                  >
                    Load
                  </button>
                  {!s.is_system && (
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (confirm(`Delete screen "${s.name}"?`)) {
                          deleteMutation.mutate(s.id);
                        }
                      }}
                      className="rounded border border-line bg-surface px-2 py-1 text-[11px] text-ink-muted hover:text-rose-400 hover:border-rose-500/40 transition-colors opacity-0 group-hover:opacity-100"
                      title="Delete screen"
                    >
                      🗑️
                    </button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
