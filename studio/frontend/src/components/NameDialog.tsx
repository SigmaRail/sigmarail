import { useEffect, useId, useRef, useState } from "react";

/** In-app name dialog — replaces window.prompt (often blocked in embedded browsers). */
export function NameDialog({
  open,
  title,
  label = "Name",
  initialValue = "",
  confirmLabel = "Save",
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  label?: string;
  initialValue?: string;
  confirmLabel?: string;
  onConfirm: (value: string) => void;
  onCancel: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();
  const [value, setValue] = useState(initialValue);

  useEffect(() => {
    if (!open) return;
    setValue(initialValue);
    const t = window.setTimeout(() => {
      inputRef.current?.focus();
      inputRef.current?.select();
    }, 0);
    return () => window.clearTimeout(t);
  }, [open, initialValue]);

  if (!open) return null;

  const trimmed = value.trim();

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onCancel();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${inputId}-title`}
        className="w-full max-w-sm rounded border border-line bg-surface-raised p-4 shadow-panel"
      >
        <h2
          id={`${inputId}-title`}
          className="text-sm font-semibold text-ink"
        >
          {title}
        </h2>
        <label
          htmlFor={inputId}
          className="mt-3 block text-[11px] font-semibold uppercase tracking-wider text-ink-faint"
        >
          {label}
        </label>
        <input
          ref={inputRef}
          id={inputId}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && trimmed) {
              e.preventDefault();
              onConfirm(trimmed);
            }
            if (e.key === "Escape") {
              e.preventDefault();
              onCancel();
            }
          }}
          className="mt-1 w-full rounded border border-line bg-surface-sunk px-2.5 py-1.5 text-[13px] text-ink outline-none focus:border-accent"
        />
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded border border-line bg-surface-sunk px-3 py-1.5 text-[12px] font-medium text-ink hover:border-accent"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!trimmed}
            onClick={() => onConfirm(trimmed)}
            className="rounded bg-ink px-3 py-1.5 text-[12px] font-medium text-white hover:bg-ink/90 disabled:opacity-50"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
