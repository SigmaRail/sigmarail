import { useState, useRef, useEffect } from "react";
import { cn } from "../../lib/utils";
import type { ScreenField } from "../../types";
import type { FieldPick } from "../../lib/fieldPick";
import { FieldDetailCard } from "./FieldDetailCard";
import { useFieldPicker } from "./FieldPickerProvider";

export { FieldDetailCard };

interface FieldInfoPopoverProps {
  /** The field whose details to show (pass null to render nothing) */
  field: ScreenField | null;
  /** Optional override catalog (if omitted the shared provider catalog is used) */
  fields?: ScreenField[];
  /** Called when the user picks a field in the browser modal. */
  onPickField?: (field: ScreenField) => void;
  /** Called with the full pick result (field / expr / predicate). Takes precedence over onPickField. */
  onPick?: (pick: FieldPick) => void;
  /** Primary action label for the browser (e.g. "Add Filter", "Sort by") */
  actionLabel?: string;
  /** Restrict the browser to a single mode */
  mode?: "fields" | "expressions";
  /** Optional controlled open state */
  show?: boolean;
  className?: string;
  /** Render a custom trigger instead of the default ℹ glyph */
  trigger?: (props: { onClick: () => void; open: boolean }) => React.ReactNode;
  /** Small glyph only (default trigger) */
  glyphClassName?: string;
}

/**
 * Reusable "what is this field?" ℹ glyph. Clicking opens the SINGLE app-wide
 * field/expression browser (via FieldPickerProvider), so there is exactly one
 * modal implementation for field selection anywhere in the app.
 */
export function FieldInfoPopover({
  field,
  fields: propFields,
  onPickField,
  onPick,
  actionLabel,
  mode,
  show: controlledShow,
  className,
  trigger,
  glyphClassName,
}: FieldInfoPopoverProps) {
  const [popoverOpen, setPopoverOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const { fields: sharedFields, openPicker } = useFieldPicker();
  const fields = propFields && propFields.length > 0 ? propFields : sharedFields;

  // Close hover-popover on outside click (only used in fallback mode)
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setPopoverOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  if (!field) return null;

  const hasCatalog = !!fields && fields.length > 0;
  const open = controlledShow ?? popoverOpen;

  const handleClick = () => {
    if (!hasCatalog) {
      setPopoverOpen((o) => !o);
      return;
    }
    openPicker({
      use: "info",
      fields,
      initialFieldName: field.name,
      mode,
      actionLabel: actionLabel ?? "Select",
      onPick: (pick) => {
        if (onPick) onPick(pick);
        else if (pick.kind === "field" && onPickField) onPickField(pick.field);
      },
    });
  };

  return (
    <span ref={ref} className={cn("relative inline-flex items-center", className)}>
      {trigger ? (
        trigger({ onClick: handleClick, open })
      ) : (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            handleClick();
          }}
          onMouseEnter={() => {
            if (!hasCatalog && !controlledShow) setPopoverOpen(true);
          }}
          onMouseLeave={() => {
            if (!hasCatalog && !controlledShow) setPopoverOpen(false);
          }}
          className={cn(
            "inline-flex h-4 w-4 flex-shrink-0 cursor-help items-center justify-center rounded-full text-[9px] font-bold transition-colors",
            open ? "bg-accent/25 text-accent" : "bg-surface-sunk text-ink-muted hover:bg-accent/20 hover:text-accent",
            glyphClassName,
          )}
          title={
            hasCatalog
              ? `Browse & inspect field: ${field.label}`
              : `${field.label}: ${field.description || "Metric from ClickHouse screener catalog"}`
          }
          aria-label={`Field info: ${field.label}`}
        >
          ℹ
        </button>
      )}

      {/* Fallback: lightweight single-field popover (no full catalog available) */}
      {!hasCatalog && open && (
        <div
          className="absolute left-full top-0 z-[60] ml-2 rounded-lg border border-line bg-surface-raised shadow-2xl ring-1 ring-black/10 overflow-hidden"
          onClick={(e) => e.stopPropagation()}
        >
          <FieldDetailCard field={field} />
        </div>
      )}
    </span>
  );
}

/** Compact inline "label + info glyph" used in option rows. */
export function FieldLabelWithInfo({
  field,
  fields,
  onPickField,
  actionLabel,
  label,
  monospace = false,
}: {
  field: ScreenField;
  fields?: ScreenField[];
  onPickField?: (field: ScreenField) => void;
  actionLabel?: string;
  label?: string;
  monospace?: boolean;
}) {
  return (
    <span className="inline-flex items-center gap-1 min-w-0">
      <span className={cn("truncate", monospace && "font-mono")}>{label ?? field.label}</span>
      <FieldInfoPopover field={field} fields={fields} onPickField={onPickField} actionLabel={actionLabel} />
    </span>
  );
}

export default FieldInfoPopover;