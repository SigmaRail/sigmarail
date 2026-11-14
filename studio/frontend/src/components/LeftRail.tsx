import { useMemo, useState, type MouseEvent as ReactMouseEvent, type ReactNode } from "react";
import { cn } from "../lib/utils";
import type { SavedScreen, ScreenPreset, ScreenTemplateSummary } from "../types";

const FEATURED_PRESETS = new Set(["minervini_tt", "canslim", "julian_komar"]);

/** Prefer short IR template aliases in the Templates section. */
const PREFERRED_TEMPLATE_IDS = [
  "minervini",
  "vcp_triad_coiling",
  "canslim",
  "komar",
  "komar_growth",
];

export function LeftRail({
  presets,
  templates,
  savedScreens,
  source,
  selectedPresetId,
  selectedTemplateId,
  selectedSavedScreenId,
  onSelectPreset,
  onSelectTemplate,
  onSelectSaved,
  onRenameSaved,
  onDeleteSaved,
  loading,
  savedLoading,
}: {
  presets: ScreenPreset[];
  templates: ScreenTemplateSummary[];
  savedScreens: SavedScreen[];
  source: "preset" | "ir";
  selectedPresetId: string;
  selectedTemplateId: string | null;
  selectedSavedScreenId: number | string | null;
  onSelectPreset: (id: string) => void;
  onSelectTemplate: (id: string) => void;
  onSelectSaved: (screen: SavedScreen) => void;
  onRenameSaved?: (screen: SavedScreen) => void;
  onDeleteSaved?: (screen: SavedScreen) => void;
  loading?: boolean;
  savedLoading?: boolean;
}) {
  const [showDeprecated, setShowDeprecated] = useState(false);
  const templateList = useMemo(
    () =>
      orderTemplates(
        showDeprecated
          ? templates
          : templates.filter((t) => t.status !== "deprecated" || t.id === selectedTemplateId),
      ),
    [templates, showDeprecated, selectedTemplateId],
  );

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-line bg-surface-raised">
      <div className="border-b border-line px-3 py-2">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
          Screen library
        </div>
        <div className="mt-0.5 text-[11px] text-ink-muted">
          Templates + L7 presets
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-1.5">
        <SectionLabel>Templates</SectionLabel>
        <label className="mb-1 flex cursor-pointer items-center gap-1.5 px-2 text-[10px] text-ink-muted hover:text-ink">
          <input
            type="checkbox"
            checked={showDeprecated}
            onChange={(e) => setShowDeprecated(e.target.checked)}
            className="rounded border-line"
          />
          Show deprecated
        </label>
        {loading && templateList.length === 0 ? (
          <p className="px-2 py-2 text-xs text-ink-muted">Loading…</p>
        ) : null}
        {!loading && templateList.length === 0 ? (
          <p className="px-2 py-2 text-xs text-ink-muted">No IR templates</p>
        ) : null}
        <ul className="mb-3 space-y-0.5">
          {templateList.map((t) => {
            const active = source === "ir" && t.id === selectedTemplateId;
            return (
              <li key={`tpl-${t.id}`}>
                <button
                  type="button"
                  onClick={() => onSelectTemplate(t.id)}
                  title={templateHoverTitle(t)}
                  className={cn(
                    "flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-[13px] transition-colors",
                    active
                      ? "bg-accent text-white"
                      : "bg-highlight-soft/70 text-ink hover:bg-highlight-soft",
                  )}
                >
                  <span className="truncate font-medium">
                    {t.label}
                    {t.status === "deprecated" ? " (deprecated)" : ""}
                  </span>
                  <span
                    className={cn(
                      "ml-2 shrink-0 rounded px-1 py-0.5 font-mono text-[9px] uppercase tracking-wide",
                      active
                        ? "bg-white/20 text-white"
                        : "bg-highlight/10 text-highlight",
                    )}
                  >
                    IR
                  </span>
                </button>
              </li>
            );
          })}
        </ul>

        <SectionLabel>Saved</SectionLabel>
        {savedLoading && savedScreens.length === 0 ? (
          <p className="px-2 py-2 text-xs text-ink-muted">Loading…</p>
        ) : null}
        {!savedLoading && savedScreens.length === 0 ? (
          <p className="px-2 py-2 text-xs text-ink-muted">
            No saved screens — use Save in top bar
          </p>
        ) : null}
        <ul className="mb-3 space-y-0.5">
          {savedScreens.map((s) => {
            const active =
              source === "ir" && s.id === selectedSavedScreenId;
            return (
              <li key={`saved-${s.id}`}>
                <div
                  className={cn(
                    "group flex w-full items-center rounded transition-colors",
                    active
                      ? "bg-accent text-white"
                      : "bg-highlight-soft/70 text-ink hover:bg-highlight-soft",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => onSelectSaved(s)}
                    onDoubleClick={(e) => {
                      e.preventDefault();
                      onRenameSaved?.(s);
                    }}
                    title={s.name}
                    className={cn(
                      "flex min-w-0 flex-1 items-center justify-between px-2 py-1.5 text-left text-[13px]",
                      active ? "text-white" : "text-ink",
                    )}
                  >
                    <span className="truncate font-medium">{s.name}</span>
                    <span
                      className={cn(
                        "ml-2 shrink-0 rounded px-1 py-0.5 font-mono text-[9px] uppercase tracking-wide",
                        active
                          ? "bg-white/20 text-white"
                          : "bg-highlight/10 text-highlight",
                      )}
                    >
                      saved
                    </span>
                  </button>
                  {onRenameSaved || onDeleteSaved ? (
                    <div
                      className={cn(
                        "flex shrink-0 items-center gap-0.5 pr-1 opacity-0 transition-opacity group-hover:opacity-100",
                        active && "opacity-100",
                      )}
                    >
                      {onRenameSaved ? (
                        <IconButton
                          label="Rename"
                          active={active}
                          onClick={(e) => {
                            e.stopPropagation();
                            onRenameSaved(s);
                          }}
                        >
                          ✎
                        </IconButton>
                      ) : null}
                      {onDeleteSaved ? (
                        <IconButton
                          label="Delete"
                          active={active}
                          onClick={(e) => {
                            e.stopPropagation();
                            onDeleteSaved(s);
                          }}
                        >
                          ×
                        </IconButton>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>

        <SectionLabel>Presets</SectionLabel>
        {loading && presets.length === 0 ? (
          <p className="px-2 py-2 text-xs text-ink-muted">Loading presets…</p>
        ) : null}
        {!loading && presets.length === 0 ? (
          <p className="px-2 py-2 text-xs text-ink-muted">No presets from API</p>
        ) : null}
        <ul className="space-y-0.5">
          {presets.map((p) => {
            const featured = FEATURED_PRESETS.has(p.id);
            const active = source === "preset" && p.id === selectedPresetId;
            return (
              <li key={p.id}>
                <button
                  type="button"
                  onClick={() => onSelectPreset(p.id)}
                  className={cn(
                    "flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-[13px] transition-colors",
                    active
                      ? "bg-accent text-white"
                      : featured
                        ? "bg-accent-soft/60 text-ink hover:bg-accent-soft"
                        : "text-ink hover:bg-surface-sunk",
                  )}
                >
                  <span className="truncate font-medium">{p.label}</span>
                  {featured ? (
                    <span
                      className={cn(
                        "ml-2 shrink-0 rounded px-1 py-0.5 font-mono text-[9px] uppercase tracking-wide",
                        active
                          ? "bg-white/20 text-white"
                          : "bg-accent/10 text-accent",
                      )}
                    >
                      key
                    </span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </aside>
  );
}

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div className="px-2 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
      {children}
    </div>
  );
}

function IconButton({
  label,
  active,
  onClick,
  children,
}: {
  label: string;
  active: boolean;
  onClick: (e: ReactMouseEvent<HTMLButtonElement>) => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className={cn(
        "flex h-5 w-5 items-center justify-center rounded text-[12px] leading-none",
        active
          ? "text-white/80 hover:bg-white/20 hover:text-white"
          : "text-ink-muted hover:bg-surface-sunk hover:text-ink",
      )}
    >
      {children}
    </button>
  );
}

function templateHoverTitle(t: ScreenTemplateSummary): string | undefined {
  const parts = [t.why?.trim(), t.description?.trim()].filter(Boolean);
  return parts.length ? parts.join(" — ") : undefined;
}

function orderTemplates(
  templates: ScreenTemplateSummary[],
): ScreenTemplateSummary[] {
  const preferred = PREFERRED_TEMPLATE_IDS.map((id) =>
    templates.find((t) => t.id === id),
  ).filter((t): t is ScreenTemplateSummary => Boolean(t));
  const preferredIds = new Set(preferred.map((t) => t.id));
  const hideStems = new Set<string>();
  for (const t of preferred) {
    if (t.id === "minervini") hideStems.add("minervini_trend_template");
    if (t.id === "canslim") hideStems.add("canslim_template");
    if (t.id === "komar") hideStems.add("julian_komar_best_winners");
    if (t.id === "komar_growth") hideStems.add("julian_komar_growth_leaders");
  }
  const rest = templates.filter(
    (t) => !preferredIds.has(t.id) && !hideStems.has(t.id),
  );
  return [...preferred, ...rest];
}
