import { useState, useRef, useEffect, useMemo, useCallback } from "react";
import { cn } from "../../lib/utils";
import type { ScreenField, AppliedFilterRow } from "../../types";
import {
  validateFilterExpression,
  formatFilterRowToExpression,
} from "../../lib/formulaParser";
import { FieldInfoPopover } from "./FieldInfoPopover";

interface FormulaPreset {
  id: string;
  label: string;
  expr: string;
  description: string;
  category: string;
  is_active: number;
}

interface TextFormulaInputProps {
  initialRow?: AppliedFilterRow | null;
  fields: ScreenField[];
  onSave: (row: AppliedFilterRow) => void;
  onCancel: () => void;
  onFocusField?: (field: ScreenField | null) => void;
  title?: string;
}

const DEFAULT_PRESETS: FormulaPreset[] = [
  { id: "builtin-1", label: "Exclude Recent IPOs (2Y+ History)", expr: "growth_rate_pct > -100", description: "Excludes recent IPOs by requiring 2+ years of historical financial reports", category: "Quality", is_active: 1 },
  { id: "builtin-2", label: "Exclude Recent IPOs (200d+ SMA)", expr: "sma200d > 0", description: "Excludes recent IPOs by requiring an established 200-day moving average", category: "Quality", is_active: 1 },
  { id: "builtin-3", label: "ATR Breakout", expr: "(close - sma50d) / atr_14 >= 2.0", description: "Price expands 2+ ATRs above 50-day SMA", category: "Breakout", is_active: 1 },
  { id: "builtin-4", label: "+30% from 52W Low", expr: "close >= low_52w * 1.30", description: "Stage 2 criterion: at least 30% above 52-week low", category: "Momentum", is_active: 1 },
  { id: "builtin-5", label: "Within 25% of 52W High", expr: "close >= high_52w * 0.75", description: "Near all-time/annual highs (Minervini rule)", category: "Momentum", is_active: 1 },
  { id: "builtin-6", label: "Golden Cross Spread", expr: "(sma50d - sma200d) / sma200d >= 0.05", description: "50-day SMA is 5%+ above 200-day SMA", category: "Trend", is_active: 1 },
  { id: "builtin-7", label: "Volume Surge (2x)", expr: "volume / avg_vol_20d >= 2.0", description: "Volume is double the 20-day average", category: "Volume", is_active: 1 },
  { id: "builtin-8", label: "RS Leader (≥70)", expr: "rs_rating >= 70", description: "Relative Strength in top 30% of market", category: "Relative Strength", is_active: 1 },
  { id: "builtin-9", label: "Stage 2 Advancing", expr: "is_stage_2_advancing == 1", description: "Stan Weinstein Stage 2 markup phase", category: "Trend", is_active: 1 },
  // Minervini Trend Template — individual conditions (AST, not pre-calc)
  { id: "builtin-10", label: "MTT 1: Price above SMA150 & SMA200", expr: "close > sma150d AND close > sma200d", description: "Price trades above both intermediate and long-term trend baselines", category: "Minervini TT", is_active: 1 },
  { id: "builtin-11", label: "MTT 2: SMA150 above SMA200", expr: "sma150d > sma200d", description: "Intermediate trend baseline is above the primary long-term baseline", category: "Minervini TT", is_active: 1 },
  { id: "builtin-12", label: "MTT 3: SMA200 rising (30d)", expr: "sma200d > sma200d[-30]", description: "200-day SMA is higher today than it was 30 trading days ago (uptrending)", category: "Minervini TT", is_active: 1 },
  { id: "builtin-13", label: "MTT 4: SMA50 above long SMAs", expr: "sma50d > sma150d AND sma50d > sma200d", description: "Short-term trend leads both intermediate and long-term baselines", category: "Minervini TT", is_active: 1 },
  { id: "builtin-14", label: "MTT 5: Price above SMA50", expr: "close > sma50d", description: "Price trades above the 50-day institutional support level", category: "Minervini TT", is_active: 1 },
  // Multi-bar patterns (bar offset)
  { id: "builtin-15", label: "Close above previous high", expr: "close > high[-1]", description: "Today's close exceeds yesterday's high — three-bar breakout confirmation", category: "Multi-bar", is_active: 1 },
  { id: "builtin-16", label: "Outside day reversal", expr: "low < low[-1] AND close > close[-1]", description: "Lower low with higher close — capitulation reversal", category: "Multi-bar", is_active: 1 },
  { id: "builtin-17", label: "Two-day downtrend reversal", expr: "close[-1] < close[-2] AND close > close[-1]", description: "Price declined yesterday then reversed higher today", category: "Multi-bar", is_active: 1 },
];

export function TextFormulaInput({
  initialRow,
  fields,
  onSave,
  onCancel,
  onFocusField,
  title = "Filter & Formula Builder",
}: TextFormulaInputProps) {
  const [expression, setExpression] = useState(() => {
    return initialRow ? formatFilterRowToExpression(initialRow) : "px.close > px.sma50d";
  });

  const [activeSuggestionIdx, setActiveSuggestionIdx] = useState(0);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [cursorPos, setCursorPos] = useState(0);
  const [presets, setPresets] = useState<FormulaPreset[]>(DEFAULT_PRESETS);
  const [presetsLoading, setPresetsLoading] = useState(true);
  const [showManageDialog, setShowManageDialog] = useState(false);
  const [editingPreset, setEditingPreset] = useState<FormulaPreset | null>(null);
  const [newPreset, setNewPreset] = useState({ label: "", expr: "", description: "", category: "Custom" });
  const [savingPreset, setSavingPreset] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const suggestionsRef = useRef<HTMLDivElement>(null);

  // Load presets from API on mount
  useEffect(() => {
    let cancelled = false;
    const loadPresets = async () => {
      try {
        const res = await fetch("/api/screens/formula-presets?active_only=true");
        if (res.ok) {
          const data = await res.json();
          if (!cancelled) {
            setPresets(data.presets || []);
          }
        }
        } catch (e) {
          console.warn("Failed to load formula presets:", e);
        } finally {
          if (!cancelled) setPresetsLoading(false);
        }
      }
      loadPresets();
      return () => { cancelled = true; };
    }, []);

  // Save presets to localStorage as fallback (optional)
  useEffect(() => {
    if (!presetsLoading) {
      try {
        localStorage.setItem("formulaPresets", JSON.stringify(presets));
      } catch {}
    }
  }, [presets, presetsLoading]);

  // Validate expression on the fly
  const validation = useMemo(() => {
    return validateFilterExpression(expression, fields);
  }, [expression, fields]);

  // Filter matching suggestions
  const currentToken =
    expression.slice(0, cursorPos).match(/([a-zA-Z0-9_.]+)$/)?.[1] ?? "";
  const matchingSuggestions = useMemo(() => {
    if (!currentToken || currentToken.length < 1) return [];
    const q = currentToken.toLowerCase();
    return fields
      .filter((f) => {
        const pName = (f.prefixed_name || `${f.prefix || "px"}.${f.name}`).toLowerCase();
        const bName = f.name.toLowerCase();
        const lbl = (f.label || "").toLowerCase();
        return pName.includes(q) || bName.includes(q) || lbl.includes(q);
      })
      .slice(0, 7);
  }, [currentToken, fields]);

  useEffect(() => {
    setShowSuggestions(matchingSuggestions.length > 0);
    setActiveSuggestionIdx(0);
  }, [matchingSuggestions]);

  // Notify inspector of active field
  useEffect(() => {
    if (matchingSuggestions.length > 0 && onFocusField) {
      const activeField = matchingSuggestions[activeSuggestionIdx] || matchingSuggestions[0];
      onFocusField(activeField);
    }
  }, [matchingSuggestions, activeSuggestionIdx, onFocusField]);

  const insertSuggestion = useCallback(
    (field: ScreenField) => {
      const pName = field.prefixed_name || `${field.prefix || "px"}.${field.name}`;
      const textBeforeCursor = expression.slice(0, cursorPos);
      const textAfterCursor = expression.slice(cursorPos);
      const tokenMatch = textBeforeCursor.match(/([a-zA-Z0-9_.]+)$/);
      const replaceLen = tokenMatch ? tokenMatch[1].length : 0;
      const newBefore = textBeforeCursor.slice(0, textBeforeCursor.length - replaceLen) + pName;
      const newExpr = newBefore + " " + textAfterCursor;
      setExpression(newExpr);
      setShowSuggestions(false);

      setTimeout(() => {
        if (inputRef.current) {
          const newPos = newBefore.length + 1;
          inputRef.current.setSelectionRange(newPos, newPos);
          inputRef.current.focus();
        }
      }, 10);
    },
    [expression, cursorPos]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (showSuggestions && matchingSuggestions.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveSuggestionIdx((prev) => (prev + 1) % matchingSuggestions.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveSuggestionIdx((prev) => (prev - 1 + matchingSuggestions.length) % matchingSuggestions.length);
        return;
      }
      if (e.key === "Tab" || (e.key === "Enter" && showSuggestions)) {
        e.preventDefault();
        insertSuggestion(matchingSuggestions[activeSuggestionIdx]);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setShowSuggestions(false);
        return;
      }
    }

    if (e.key === "Enter" && !showSuggestions) {
      if (validation.valid && validation.row) {
        onSave(validation.row);
      }
    }
    if (e.key === "Escape") {
      onCancel();
    }
  };

  const handleSave = () => {
    if (validation.valid && validation.row) {
      onSave(validation.row);
    }
  };

  return (
    <div className="flex flex-col gap-3 min-w-[340px] max-w-[460px] text-[11px]">
      <div className="flex items-center justify-between border-b border-line pb-1.5">
        <span className="text-[10.5px] font-bold uppercase tracking-wider text-accent">{title}</span>
        <span className="text-[10px] text-ink-muted">Infix Math & Comparisons</span>
      </div>

      {/* Text Expression Bar */}
      <div className="relative">
        <label className="block text-[10px] font-bold uppercase tracking-wider text-ink-muted mb-1">
          Expression Formula:
        </label>
        <input
          ref={inputRef}
          type="text"
          value={expression}
          onChange={(e) => {
            setExpression(e.target.value);
            setCursorPos(e.target.selectionStart || 0);
          }}
          onClick={(e) => setCursorPos((e.target as HTMLInputElement).selectionStart || 0)}
          onKeyUp={(e) => setCursorPos((e.target as HTMLInputElement).selectionStart || 0)}
          onKeyDown={handleKeyDown}
          placeholder="e.g. (px.close - px.sma50d) / px.atr_14 >= 2.0"
          className="w-full rounded border border-line bg-surface-sunk px-3 py-1.5 font-mono text-[11.5px] text-ink focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/40"
          autoFocus
        />

        {/* Term Completion Floating Popup */}
        {showSuggestions && matchingSuggestions.length > 0 && (
          <div
            ref={suggestionsRef}
            className="absolute left-0 top-full z-50 mt-1 w-full rounded-lg border border-accent/40 bg-surface shadow-2xl overflow-hidden ring-1 ring-black/10"
          >
            <div className="bg-surface-raised px-2.5 py-1 text-[9.5px] font-bold uppercase tracking-wider text-ink-muted border-b border-line flex items-center justify-between">
              <span>Matching Fields</span>
              <span className="text-[9px] font-mono lowercase">Tab or Enter to insert</span>
            </div>
            <div className="max-h-48 overflow-y-auto divide-y divide-line/40">
              {matchingSuggestions.map((item, idx) => {
                const pName = item.prefixed_name || `${item.prefix || "px"}.${item.name}`;
                const isSelected = idx === activeSuggestionIdx;
                return (
                  <div
                    key={item.name}
                    role="option"
                    aria-selected={isSelected}
                    onClick={() => insertSuggestion(item)}
                    onMouseEnter={() => {
                      setActiveSuggestionIdx(idx);
                      if (onFocusField) onFocusField(item);
                    }}
                    className={cn(
                      "w-full text-left px-2.5 py-1.5 flex items-center justify-between gap-2 transition-colors cursor-pointer",
                      isSelected ? "bg-accent/15 text-ink font-semibold" : "hover:bg-surface-sunk text-ink-muted"
                    )}
                  >
                    <div className="flex items-center gap-2 truncate">
                      <span className="font-mono text-accent text-[11px] font-bold">{pName}</span>
                      <span className="text-[10.5px] text-ink truncate">{item.label}</span>
                      {/* Info glyph → opens shared field browser (center modal); pick inserts field */}
                      <FieldInfoPopover
                        field={item}
                        fields={fields}
                        onPickField={insertSuggestion}
                        actionLabel="Insert Field"
                      />
                    </div>
                    <span className="rounded bg-surface px-1.5 py-0.5 text-[9px] font-mono text-ink-muted flex-shrink-0">
                      {item.category_label || item.category}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Formula Presets */}
      <div>
        <div className="text-[9.5px] font-bold uppercase tracking-wider text-ink-muted mb-1 flex items-center justify-between">
          <span>Formula Recipes</span>
          <div className="flex items-center gap-1">
            {presetsLoading && <span className="text-[9px] text-ink-faint animate-pulse">Loading…</span>}
            <button
              type="button"
              onClick={() => setShowManageDialog(true)}
              className="rounded border border-line bg-surface px-1.5 py-0.5 text-[9px] font-mono text-ink-muted hover:border-accent hover:text-accent hover:bg-accent/5 transition-colors"
              title="Manage presets"
            >
              Manage
            </button>
          </div>
        </div>
        <div className="flex flex-wrap gap-1">
          {presets.filter(p => p.is_active).map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => {
                setExpression(p.expr);
                if (inputRef.current) inputRef.current.focus();
              }}
              title={p.description}
              className="rounded border border-line bg-surface px-2 py-0.5 text-[10px] font-mono text-ink-muted hover:border-accent hover:text-accent hover:bg-accent/5 transition-colors"
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Manage Presets Dialog */}
      {showManageDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-2xl max-h-[85vh] overflow-hidden rounded-xl border border-line bg-surface-sunk flex flex-col">
            <div className="flex items-center justify-between border-b border-line px-4 py-3">
              <h3 className="text-[12px] font-bold text-ink">Manage Formula Presets</h3>
              <button
                type="button"
                onClick={() => { setShowManageDialog(false); setEditingPreset(null); }}
                className="rounded border border-line bg-surface p-1 text-ink-muted hover:bg-accent/5 hover:text-accent transition-colors"
              >
                ✕
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {/* Add/Edit Form */}
              <div className="border border-line/60 rounded-lg p-4 space-y-3">
                <h4 className="text-[11px] font-bold text-ink">{editingPreset ? "Edit Preset" : "Add New Preset"}</h4>
                <div className="space-y-2">
                  <div>
                    <label className="block text-[10px] font-bold text-ink-muted mb-1">Label</label>
                    <input
                      type="text"
                      value={editingPreset ? editingPreset.label : newPreset.label}
                      onChange={(e) => setNewPreset({ ...newPreset, label: e.target.value })}
                      placeholder="e.g. My Custom Breakout"
                      className="w-full rounded border border-line bg-surface px-2 py-1.5 text-[11px] font-mono text-ink"
                      disabled={savingPreset}
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold text-ink-muted mb-1">Expression</label>
                    <input
                      type="text"
                      value={editingPreset ? editingPreset.expr : newPreset.expr}
                      onChange={(e) => setNewPreset({ ...newPreset, expr: e.target.value })}
                      placeholder="e.g. close > high[-1]"
                      className="w-full rounded border border-line bg-surface px-2 py-1.5 text-[11px] font-mono text-ink"
                      disabled={savingPreset}
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold text-ink-muted mb-1">Description</label>
                    <input
                      type="text"
                      value={editingPreset ? editingPreset.description : newPreset.description}
                      onChange={(e) => setNewPreset({ ...newPreset, description: e.target.value })}
                      placeholder="Optional tooltip text"
                      className="w-full rounded border border-line bg-surface px-2 py-1.5 text-[11px] font-mono text-ink"
                      disabled={savingPreset}
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-bold text-ink-muted mb-1">Category</label>
                    <input
                      type="text"
                      value={editingPreset ? editingPreset.category : newPreset.category}
                      onChange={(e) => setNewPreset({ ...newPreset, category: e.target.value })}
                      placeholder="e.g. Breakout, Momentum, Multi-bar"
                      className="w-full rounded border border-line bg-surface px-2 py-1.5 text-[11px] font-mono text-ink"
                      disabled={savingPreset}
                    />
                  </div>
                </div>
                <div className="flex justify-end gap-2 pt-2 border-t border-line/40">
                  <button
                    type="button"
                    onClick={() => { setEditingPreset(null); setNewPreset({ label: "", expr: "", description: "", category: "Custom" }); }}
                    className="rounded border border-line bg-surface px-3 py-1.5 text-[11px] font-semibold text-ink-muted hover:bg-accent/5"
                    disabled={savingPreset}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={async () => {
                      const payload = editingPreset
                        ? { ...newPreset }
                        : { ...newPreset, id: crypto.randomUUID() };
                      setSavingPreset(true);
                      try {
                        const res = await fetch(editingPreset ? `/api/screens/formula-presets/${editingPreset.id}` : "/api/screens/formula-presets", {
                          method: editingPreset ? "PATCH" : "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify(payload),
                        });
                        if (res.ok) {
                          const updated = await res.json();
                          setPresets(prev => {
                            if (editingPreset) {
                              return prev.map(p => p.id === editingPreset.id ? { ...p, ...updated } : p);
                            }
                            return [...prev, updated];
                          });
                          setEditingPreset(null);
                          setNewPreset({ label: "", expr: "", description: "", category: "Custom" });
                        }
                      } catch (e) {
                        console.error("Failed to save preset:", e);
                      } finally {
                        setSavingPreset(false);
                      }
                    }}
                    className="rounded bg-accent px-3.5 py-1.5 text-[11px] font-bold text-accent-ink disabled:opacity-40 hover:opacity-90 transition-opacity"
                    disabled={savingPreset || !newPreset.label || !newPreset.expr}
                  >
                    {savingPreset ? "Saving…" : (editingPreset ? "Save Changes" : "Add Preset")}
                  </button>
                </div>
              </div>

              {/* Presets List */}
              <div className="space-y-2">
                <h4 className="text-[11px] font-bold text-ink-muted uppercase tracking-wider">Your Presets</h4>
                <div className="divide-y divide-line/40">
                  {presets.map((p) => (
                    <div
                      key={p.id}
                      className="flex items-center justify-between gap-2 p-2 rounded-lg bg-surface-sunk/50 hover:bg-surface-sunk transition-colors"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-[11px] text-ink font-semibold">{p.label}</span>
                          {p.id.startsWith("builtin-") && (
                            <span className="rounded px-1.5 py-0.5 text-[8px] font-mono text-ink-faint bg-line/30">Built-in</span>
                          )}
                          {!p.id.startsWith("builtin-") && p.id !== "new" && (
                            <span className="rounded px-1.5 py-0.5 text-[8px] font-mono text-accent bg-accent/10">Custom</span>
                          )}
                        </div>
                        <div className="text-[10px] text-ink-muted truncate font-mono">{p.expr}</div>
                        <p className="text-[9px] text-ink-faint line-clamp-1">{p.description}</p>
                        <span className="rounded px-1.5 py-0.5 text-[8px] font-mono text-ink-muted bg-surface-sunk">{p.category}</span>
                      </div>
                      <div className="flex items-center gap-1">
                        {!p.id.startsWith("builtin-") && (
                          <>
                            <button
                              type="button"
                              onClick={() => { setEditingPreset(p); setNewPreset({ label: p.label, expr: p.expr, description: p.description, category: p.category }); }}
                              className="rounded border border-line bg-surface p-1.5 text-[10px] text-ink-muted hover:bg-accent/5 hover:text-accent"
                              title="Edit"
                            >
                              ✏️
                            </button>
                            <button
                              type="button"
                              onClick={async () => {
                                if (!confirm(`Delete "${p.label}"?`)) return;
                                try {
                                  await fetch(`/api/screens/formula-presets/${p.id}`, { method: "DELETE" });
                                  setPresets(prev => prev.filter(x => x.id !== p.id));
        } catch (e) {
                                  console.error("Failed to delete preset:", e);
                                }
                              }}
                              className="rounded border border-amber-500/50 bg-surface p-1.5 text-[10px] text-amber-500 hover:bg-amber-500/10"
                              title="Delete"
                            >
                              🗑️
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className="border-t border-line p-4 flex justify-end">
              <button
                type="button"
                onClick={() => setShowManageDialog(false)}
                className="rounded border border-line bg-surface px-4 py-2 text-[11px] font-semibold text-ink-muted hover:bg-accent/5"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Live AST Validation & Status */}
      <div
        className={cn(
          "rounded border px-2.5 py-1.5 text-[10.5px] font-mono flex items-center justify-between gap-2 transition-all",
          validation.valid
            ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-500"
            : "border-amber-500/30 bg-amber-500/5 text-amber-500"
        )}
      >
        <div className="truncate">
          {validation.valid ? (
            <span>
              <strong className="font-bold">AST: </strong>
              {expression}
            </span>
          ) : (
            <span>
              <strong className="font-bold">Syntax: </strong>
              {validation.error || "Invalid expression"}
            </span>
          )}
        </div>
        <span className="font-sans text-[10px] font-bold flex-shrink-0">
          {validation.valid ? "✓ Valid AST" : "⚠ Incomplete"}
        </span>
      </div>

      {/* Actions */}
      <div className="flex items-center justify-end gap-2 pt-1 border-t border-line/60">
        <button
          type="button"
          onClick={onCancel}
          className="rounded border border-line bg-surface px-3 py-1 text-[11px] font-semibold text-ink-muted hover:text-ink transition-colors"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={handleSave}
          disabled={!validation.valid}
          className="rounded bg-accent px-3.5 py-1 text-[11px] font-bold text-accent-ink disabled:opacity-40 hover:opacity-90 transition-opacity"
        >
          Apply Filter
        </button>
      </div>
    </div>
  );
}
