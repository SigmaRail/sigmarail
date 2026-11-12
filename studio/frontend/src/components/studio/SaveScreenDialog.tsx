import { useState, useEffect } from "react";
import { cn } from "../../lib/utils";

interface SaveScreenDialogProps {
  open: boolean;
  /** Default name to prefill */
  defaultName: string;
  /** Whether we are updating an existing screen (vs creating new) */
  isUpdate?: boolean;
  /** Show description field */
  showDescription?: boolean;
  /** Optional error message to display above the action buttons */
  error?: string | null;
  onCancel: () => void;
  onConfirm: (payload: { name: string; description?: string }) => void;
}

export function SaveScreenDialog({
  open,
  defaultName,
  isUpdate = false,
  showDescription = false,
  onCancel,
  onConfirm,
  error,
}: SaveScreenDialogProps) {
  const [name, setName] = useState(defaultName);
  const [description, setDescription] = useState("");

  useEffect(() => {
    if (open) {
      setName(defaultName);
      setDescription("");
    }
  }, [open, defaultName]);

  useEffect(() => {
    if (!open) return;
    function handler(e: KeyboardEvent) {
      if (e.key === "Escape") onCancel();
      if (e.key === "Enter" && name.trim()) {
        e.preventDefault();
        onConfirm({ name: name.trim(), description: description.trim() || undefined });
      }
    }
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, name, description, onCancel, onConfirm]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[120] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div className="flex w-[min(440px,94vw)] flex-col rounded-xl border border-line bg-surface shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between border-b border-line bg-surface-raised px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="text-[13px] font-bold text-ink">💾 Save Universe Screen</span>
            <span
              className={cn(
                "rounded px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-wider",
                isUpdate ? "bg-amber-500/15 text-amber-500" : "bg-emerald-500/15 text-emerald-600",
              )}
            >
              {isUpdate ? "Update Existing" : "New Screen"}
            </span>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="rounded border border-line bg-surface-sunk px-2 py-1 text-[11px] font-semibold text-ink-muted hover:text-ink transition-colors"
          >
            ✕
          </button>
        </div>

        <div className="space-y-3 px-4 py-4">
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-ink-muted">
              Screen Name
            </label>
            <input
              autoFocus
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. My Momentum Screen"
              className="w-full rounded-lg border border-line bg-surface-sunk px-3 py-2 text-[12px] text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none"
            />
          </div>

          {showDescription && (
            <div>
              <label className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-ink-muted">
                Description (optional)
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                placeholder="What does this screen select?"
                className="w-full resize-none rounded-lg border border-line bg-surface-sunk px-3 py-2 text-[12px] text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none"
              />
            </div>
          )}

          {isUpdate && (
            <p className="rounded bg-surface-sunk px-2.5 py-1.5 text-[10.5px] text-ink-muted">
              Saving will overwrite the currently loaded screen. Rename above to save as a copy instead.
            </p>
          )}
        </div>

        {error && (
          <p className="px-4 pb-1 text-[11px] font-semibold text-red-500" role="alert">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2 border-t border-line bg-surface-raised px-4 py-3">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-line bg-surface px-3.5 py-1.5 text-[11.5px] font-semibold text-ink-muted hover:text-ink transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!name.trim()}
            onClick={() => onConfirm({ name: name.trim(), description: description.trim() || undefined })}
            className="rounded-lg bg-accent px-4 py-1.5 text-[11.5px] font-bold text-white hover:opacity-90 transition-opacity disabled:opacity-40"
          >
            {isUpdate ? "Update Screen" : "Save Screen"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default SaveScreenDialog;