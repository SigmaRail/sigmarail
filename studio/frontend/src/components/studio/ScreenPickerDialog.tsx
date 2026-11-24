import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteSavedScreen } from "../../api/screens";
import type { SavedScreen } from "../../types";
import { Button, Dialog, TextInput } from "../ui/primitives";

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
    <Dialog
      open={isOpen}
      title="Load universe screen"
      onClose={onClose}
      className="w-[min(94vw,36rem)] max-h-[84dvh]"
    >
      <div className="mb-3 text-xs text-ink-muted">{screens.length} available</div>

      {/* Filter pills and search */}
      <div className="grid gap-2 border-b border-line pb-3 sm:flex sm:items-center sm:justify-between">
        <div role="group" aria-label="Filter screens" className="flex flex-wrap gap-1">
            <Button
              type="button"
              variant={filter === "all" ? "primary" : "secondary"}
              aria-pressed={filter === "all"}
              onClick={() => setFilter("all")}
              className="min-h-8 px-2.5 text-[11px]"
            >
              All ({screens.length})
            </Button>
            <Button
              type="button"
              variant={filter === "system" ? "primary" : "secondary"}
              aria-pressed={filter === "system"}
              onClick={() => setFilter("system")}
              className="min-h-8 px-2.5 text-[11px]"
            >
              ⭐ System ({systemScreens.length})
            </Button>
            <Button
              type="button"
              variant={filter === "custom" ? "primary" : "secondary"}
              aria-pressed={filter === "custom"}
              onClick={() => setFilter("custom")}
              className="min-h-8 px-2.5 text-[11px]"
            >
              💾 Custom ({customScreens.length})
            </Button>
        </div>

        <TextInput
            type="text"
            placeholder="Search screens…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search screens"
            className="min-h-9 w-full px-2.5 py-1 text-[11px] sm:w-44"
        />
      </div>

      <div className="-mx-2 min-h-0 max-h-[55dvh] divide-y divide-line overflow-y-auto sm:-mx-3">
          {displayedScreens.length === 0 ? (
            <div className="p-8 text-center text-[12px] text-ink-muted">
              No screens found matching your filter or search criteria.
            </div>
          ) : (
            displayedScreens.map((s) => (
              <div
                key={String(s.id)}
                className="flex flex-wrap items-center justify-between gap-2 px-2 py-3 transition-colors hover:bg-slate-50 sm:px-3"
              >
                <button
                  type="button"
                  onClick={() => { onSelectScreen(s); onClose(); }}
                  className="min-w-0 flex-1 text-left flex flex-col gap-0.5 cursor-pointer pr-2"
                >
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-[12px] text-ink hover:text-accent transition-colors">
                      {s.name}
                    </span>
                    {s.is_system ? (
                      <span className="text-[9.5px] font-mono px-1.5 py-0.5 rounded-md border border-sky-600/20 bg-sky-50 text-sky-700 font-semibold">
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
                  <Button
                    type="button"
                    variant="primary"
                    className="min-h-8 px-2.5 text-[11px]"
                    onClick={() => { onSelectScreen(s); onClose(); }}
                  >
                    Load
                  </Button>
                  {!s.is_system && (
                    <Button
                      type="button"
                      variant="ghost"
                      className="min-h-8 min-w-8 px-1.5 text-xs"
                      aria-label={`Delete screen ${s.name}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (confirm(`Delete screen "${s.name}"?`)) {
                          deleteMutation.mutate(s.id);
                        }
                      }}
                      title="Delete screen"
                    >
                      🗑️
                    </Button>
                  )}
                </div>
              </div>
            ))
          )}
      </div>
    </Dialog>
  );
}
