import { useEffect, useState } from "react";

export type UnitKind = "%" | "R" | "×" | "d" | "$" | "";

type Props = {
  label: string;
  /** What this knob controls at runtime (shown under the field). */
  hint?: string;
  /** Storage value (e.g. 0.008 for 0.8%). */
  value: number;
  onChange: (storage: number) => void;
  unit?: UnitKind;
  /**
   * Multiply storage → display (e.g. 100 for fraction↔percent).
   * Display is edited; stored as display / displayScale.
   */
  displayScale?: number;
  step?: number;
  min?: number;
  max?: number;
  /** Preset values in *display* units (after scale). */
  presets?: number[];
  className?: string;
  inputClassName?: string;
  /** Disable the editor while keeping the value visible (dependent knob). */
  disabled?: boolean;
  /** Why the field is disabled (shown when disabled). */
  disabledReason?: string;
  /** "row" = label left / input right; "card" = self-contained cell for grid layouts. */
  layout?: "row" | "card";
};

function clamp(n: number, min?: number, max?: number): number {
  let v = n;
  if (min != null && Number.isFinite(min)) v = Math.max(min, v);
  if (max != null && Number.isFinite(max)) v = Math.min(max, v);
  return v;
}

/** Compact mono number + unit; optional Champion-style preset chips. */
export function UnitNumberField({
  label,
  hint,
  value,
  onChange,
  unit = "",
  displayScale = 1,
  step = 1,
  min,
  max,
  presets,
  className = "",
  inputClassName = "w-20",
  disabled = false,
  disabledReason,
  layout = "row",
}: Props) {
  const scale = displayScale || 1;
  const toDisplay = (storage: number) => storage * scale;
  const toStorage = (display: number) => display / scale;
  const EPS = 1e-9;
  const outOfRange =
    (min != null && Number.isFinite(min) && value < min - EPS) ||
    (max != null && Number.isFinite(max) && value > max + EPS);
  const rangeLabel =
    min != null && max != null
      ? `outside ${toDisplay(min)}–${toDisplay(max)}`
      : min != null
        ? `below ${toDisplay(min)}`
        : max != null
          ? `above ${toDisplay(max)}`
          : "";

  const [text, setText] = useState(() => String(toDisplay(value)));

  useEffect(() => {
    const d = toDisplay(value);
    const rounded =
      Math.abs(d) >= 10 || Number.isInteger(step)
        ? String(Math.round(d * 1e6) / 1e6)
        : String(Math.round(d * 1e4) / 1e4);
    setText(rounded);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- sync from external value only
  }, [value, scale]);

  function commit(raw: string) {
    const parsed = parseFloat(raw);
    if (!Number.isFinite(parsed)) {
      setText(String(toDisplay(value)));
      return;
    }
    const storage = clamp(toStorage(parsed), min, max);
    onChange(storage);
    setText(String(toDisplay(storage)));
  }

  const inputEl = (
    <span className="inline-flex items-center gap-0.5">
      <input
        type="number"
        step={step * (scale !== 1 ? scale : 1)}
        value={text}
        disabled={disabled}
        title={disabled ? disabledReason : undefined}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => commit(text)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.currentTarget.blur();
          }
        }}
        className={`rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[11px] text-ink text-right disabled:opacity-40 ${inputClassName}`}
      />
      {unit ? (
        <span className="font-mono text-[10px] text-ink-muted w-4">{unit}</span>
      ) : null}
    </span>
  );

  const warnBadge = outOfRange ? (
    <span
      className="ml-1 rounded border border-amber-500/60 bg-amber-500/10 px-1 py-px align-middle font-mono text-[8.5px] font-semibold text-amber-300"
      title={`Value sits ${rangeLabel} (editor range). The runtime still uses this value as authored.`}
    >
      ⚠ {rangeLabel}
    </span>
  ) : null;

  if (layout === "card") {
    return (
      <div
        className={`space-y-1 rounded border border-line/60 bg-surface/50 p-2 ${className} ${disabled ? "opacity-70" : ""}`}
        title={disabled ? disabledReason : undefined}
      >
        <div className="flex items-center justify-between gap-1.5">
          <span className="min-w-0 truncate text-[10px] font-semibold text-ink">
            {label}
            {warnBadge}
          </span>
          {inputEl}
        </div>
        {hint ? <p className="text-[9px] leading-snug text-ink-faint">{hint}</p> : null}
        {presets && presets.length > 0 && !disabled ? (
          <div className="flex flex-wrap gap-1">
            {presets.map((p) => {
              const storage = toStorage(p);
              const active = Math.abs(value - storage) < 1e-9;
              return (
                <button
                  key={p}
                  type="button"
                  onClick={() => {
                    const next = clamp(storage, min, max);
                    onChange(next);
                    setText(String(toDisplay(next)));
                  }}
                  className={
                    active
                      ? "rounded border border-accent bg-accent/10 px-1.5 py-0.5 font-mono text-[9.5px] font-semibold text-accent-ink"
                      : "rounded border border-line px-1.5 py-0.5 font-mono text-[9.5px] text-ink-muted hover:bg-surface-sunk"
                  }
                >
                  {p}
                  {unit}
                </button>
              );
            })}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className={`space-y-1 ${className}`}>
      <label className="flex flex-wrap items-center gap-1.5 text-[10.5px] text-ink-faint">
        <span className="min-w-0 flex-1">
          {label}
          {warnBadge}
        </span>
        {inputEl}
      </label>
      {hint ? (
        <p className="text-[9px] leading-snug text-ink-faint">{hint}</p>
      ) : null}
      {presets && presets.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {presets.map((p) => {
            const storage = toStorage(p);
            const active = Math.abs(value - storage) < 1e-9;
            return (
                <button
                  key={p}
                  type="button"
                  disabled={disabled}
                  onClick={() => {
                    const next = clamp(storage, min, max);
                    onChange(next);
                    setText(String(toDisplay(next)));
                  }}
                  className={
                    active
                      ? "rounded border border-accent bg-accent/10 px-1.5 py-0.5 font-mono text-[9.5px] font-semibold text-accent-ink"
                      : "rounded border border-line px-1.5 py-0.5 font-mono text-[9.5px] text-ink-muted hover:bg-surface-sunk disabled:opacity-40"
                  }
                >
                {p}
                {unit}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
