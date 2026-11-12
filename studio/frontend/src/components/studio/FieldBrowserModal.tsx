import { useMemo, useState, useEffect, useRef, useCallback } from "react";
import { createPortal } from "react-dom";
import { useQuery } from "@tanstack/react-query";
import { cn } from "../../lib/utils";
import { fetchFieldValues } from "../../api/screens";
import type { ScreenField } from "../../types";
import type { ExpressionRecipe, FieldPick } from "../../lib/fieldPick";
import {
  expressionNeedsJoin,
  isStringishFieldType,
  parseArithmeticTokens,
  tokenize,
  validateArithmeticExpression,
  validateFilterExpression,
  valueCompletionContext,
} from "../../lib/formulaParser";
import { FieldDetailCard } from "./FieldDetailCard";

type AcItem =
  | { kind: "field"; field: ScreenField }
  | { kind: "value"; value: string };

export type BrowserMode = "fields" | "expressions";
export type BrowserPurpose = "filter" | "sort" | "column" | "number";

interface ApiFormulaPreset {
  id: string;
  label: string;
  expr: string;
  description: string;
  category?: string;
  is_active?: number;
}

interface FieldBrowserModalProps {
  /** Catalog fields to browse (reused by Fields tab) */
  fields: ScreenField[];
  /** Named expression recipes — the purpose-tagged expression knowledgebase */
  recipes?: ExpressionRecipe[];
  /** Initially selected field name (optional) */
  initialFieldName?: string | null;
  /** Initially pre-fill the expression editor text (filter mode) */
  initialExpression?: string;
  /** Open state */
  isOpen: boolean;
  onClose: () => void;
  /** Callback with what the user picked (field OR expression). */
  onPick: (pick: FieldPick) => void;
  /** Primary action label (e.g. "Sort by", "Use") */
  actionLabel?: string;
  /** Restrict to a single tab: force mode */
  mode?: BrowserMode;
  /** Purpose driving which expression recipes are highlighted/relevant */
  purpose?: BrowserPurpose;
  /** Title suffix used in header */
  title?: string;
  /** If true, expression editor is shown and picks return parsed text (filter/sort) */
  expressionLinked?: boolean;
}

/** Operators the expression parser supports — offered as quick-insert chips. */
const COMPARISON_OPS = [">=", ">", "<=", "<", "=="];
const ARITH_OPS = ["+", "-", "*", "/", "(", ")"];

function recipePurposeFlags(r: ExpressionRecipe): Set<BrowserPurpose> {
  const flags = new Set<BrowserPurpose>();
  if (r.purposes?.length) {
    r.purposes.forEach((p) => flags.add(p));
    return flags;
  }
  const hasCmp = /[><=]/.test(r.expr);
  const isFlag = /^(is_|has_|breakout|stage)/.test(r.expr.split(" ")[0] ?? "");
  if (hasCmp || isFlag) flags.add("filter");
  if (!hasCmp) {
    flags.add("sort");
    flags.add("number");
  }
  if (isFlag) flags.add("column");
  return flags;
}

/** Logical name of a field as it appears in expressions (drop prefix). */
function fieldToken(f: ScreenField): string {
  return f.name.includes(".") ? f.name.split(".").slice(1).join(".") : f.name;
}

/**
 * Unified single-app picker. Preview-first:
 *   - Clicking a field/recipe ONLY previews its definition in the right pane.
 *   - Use the row "+ Insert" button, the detail-pane action, or double-click to
 *     add it to the expression / confirm.
 * Expression editor (filter/sort) has field autocomplete + operator quick-insert.
 */
export function FieldBrowserModal({
  fields,
  recipes = [],
  initialFieldName,
  initialExpression,
  isOpen,
  onClose,
  onPick,
  actionLabel = "Select",
  mode,
  purpose,
  title,
  expressionLinked = false,
}: FieldBrowserModalProps) {
  const [activeMode, setActiveMode] = useState<BrowserMode>(mode ?? "fields");
  const [query, setQuery] = useState("");
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [selectedRecipe, setSelectedRecipe] = useState<ExpressionRecipe | null>(null);
  const [freeText, setFreeText] = useState("");
  const [freeError, setFreeError] = useState<string | null>(null);
  const [showManageDialog, setShowManageDialog] = useState(false);
  const [editingRecipe, setEditingRecipe] = useState<ExpressionRecipe | null>(null);
  const [newRecipe, setNewRecipe] = useState({ label: "", expr: "", description: "", category: "Custom", purposes: ["filter"] as BrowserPurpose[] });
  const [savingRecipe, setSavingRecipe] = useState(false);
  const [managedRecipes, setManagedRecipes] = useState<ApiFormulaPreset[] | null>(null);

  useEffect(() => {
    if (!showManageDialog) return;
    let active = true;
    void (async () => {
      try {
        const res = await fetch("/api/screens/formula-presets?active_only=false");
        if (!res.ok || !active) return;
        const payload = (await res.json()) as { presets?: ApiFormulaPreset[] };
        if (active) setManagedRecipes(payload.presets ?? []);
      } catch {
        if (active) setManagedRecipes([]);
      }
    })();
    return () => { active = false; };
  }, [showManageDialog]);

  // Expression editor: caret + autocomplete + default join operator
  const editorRef = useRef<HTMLInputElement>(null);
  const [caret, setCaret] = useState(0);
  // Tracks whether the caret was actually placed by user interaction (typing/clicking/
  // if false, the insertion helpers fall back to the end of the expression.
// This avoids
  // jamming a term into the middle of a pre-filled expression when the user never
  // clicked into the text field first.
  const caretSetRef = useRef(false);
  const [acOpen, setAcOpen] = useState(false);
  const [acIndex, setAcIndex] = useState(0);
  const [joinOp, setJoinOp] = useState<string>("and");

  useEffect(() => {
    if (mode) setActiveMode(mode);
  }, [mode]);

  useEffect(() => {
    if (isOpen) {
      setSelectedName(initialFieldName ?? null);
      setSelectedRecipe(null);
      setQuery("");
      setFreeText(initialExpression ?? "");
      setFreeError(null);
      setAcOpen(false);
      setJoinOp(purpose === "sort" || purpose === "number" ? "+" : "and");
      // Fresh session: nobody has clicked into the editor yet — insertions append.

      caretSetRef.current = false;
    }
  }, [isOpen, initialFieldName, initialExpression, purpose]);

  useEffect(() => {
    if (!isOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, onClose]);

  const hasModes = !mode;
  const isNumericPurpose = purpose === "number" || purpose === "sort";

  // ---- Field list (grouped, searchable) ----
  const filteredGroups = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = fields;
    if (purpose === "number") {
      // Prefer measure aliases / computed / bool gates when authoring Σ expressions.
      const measures = fields.filter(
        (f) =>
          f.category === "measures" ||
          f.origin === "computed" ||
          f.type === "bool" ||
          f.type === "number",
      );
      if (measures.length > 0) list = measures;
    }
    if (q) {
      list = list.filter((f) =>
        [f.name, f.label, f.category, f.category_label, f.description, f.table, f.prefixed_name, f.prefix ? `${f.prefix}.${f.name}` : ""]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(q),
      );
    }
    const groups: { label: string; fields: ScreenField[] }[] = [];
    const map = new Map<string, ScreenField[]>();
    for (const f of list) {
      const cat = f.category_label || f.category || "Other";
      (map.get(cat) ?? map.set(cat, []).get(cat)!).push(f);
    }
    map.forEach((arr, label) => groups.push({ label, fields: arr.sort((a, b) => a.label.localeCompare(b.label)) }));
    return groups.sort((a, b) => a.label.localeCompare(b.label));
  }, [fields, query, purpose]);

  // ---- Expression knowledgebase (purpose-filtered, grouped) ----
  const staticRecipeIds = useMemo(
    () => new Set(recipes.map((r) => r.id)),
    [recipes],
  );
  const availableRecipes = useMemo(() => {
    if (managedRecipes === null) return recipes;
    const managed = managedRecipes
      .filter((p) => !staticRecipeIds.has(p.id))
      .map((p) => {
        const recipe: ExpressionRecipe = {
          id: p.id,
          label: p.label,
          expr: p.expr,
          desc: p.description,
          category: p.category ?? "Custom",
        };
        recipe.purposes = Array.from(recipePurposeFlags(recipe)) as BrowserPurpose[];
        return recipe;
      });
    return [...recipes, ...managed];
  }, [managedRecipes, recipes, staticRecipeIds]);

  const filteredRecipes = useMemo(() => {
    const q = query.trim().toLowerCase();

    let list = availableRecipes;
    if (purpose) list = list.filter((r) => recipePurposeFlags(r).has(purpose));
    if (q) {
      list = list.filter((r) =>
        [r.label, r.expr, r.desc, r.category, ...(r.purposes ?? [])].filter(Boolean).join(" ").toLowerCase().includes(q),
      );
    }
    const groups: { purpose: BrowserPurpose; recipes: ExpressionRecipe[] }[] = [];
    for (const p of ["filter", "sort", "number", "column"] as BrowserPurpose[]) {
      const arr = list.filter((r) => recipePurposeFlags(r).has(p));
      if (arr.length) groups.push({ purpose: p, recipes: arr });
    }
    return groups;
  }, [availableRecipes, query, purpose]);

  const selectedField = useMemo(
    () => (activeMode === "fields" ? fields.find((f) => f.name === selectedName) ?? null : null),
    [fields, selectedName, activeMode],
  );

  const freeValidation = useMemo(() => {
    if (!freeText.trim()) return { valid: false, error: null as string | null };
    if (isNumericPurpose) {
      const v = validateArithmeticExpression(freeText, fields);
      return { valid: v.valid, error: v.error ?? null };
    }
    const v = validateFilterExpression(freeText, fields);
    return { valid: v.valid, error: v.error ?? null };
  }, [freeText, fields, isNumericPurpose]);

  const valueCtx = useMemo(() => {
    const ctx = valueCompletionContext(freeText, caret);
    if (!ctx) return null;
    const field = fields.find((f) => f.name === ctx.fieldName || f.prefixed_name === ctx.fieldName);
    if (!field || !isStringishFieldType(field.type)) return null;
    return { ...ctx, field };
  }, [freeText, caret, fields]);

  const valuesQuery = useQuery({
    queryKey: ["field-values", valueCtx?.field.name, valueCtx?.prefix ?? ""],
    queryFn: () => fetchFieldValues(valueCtx!.field.name, valueCtx!.prefix),
    enabled: !!valueCtx,
    staleTime: 30_000,
  });

  // ---- Autocomplete: value after `field=` (from CH) or field name token ----
  const acSuggestions = useMemo((): AcItem[] => {
    if (valueCtx) {
      return (valuesQuery.data ?? []).map((value) => ({ kind: "value" as const, value }));
    }
    const before = freeText.slice(0, caret);
    const m = before.match(/([A-Za-z_][A-Za-z0-9_]*)$/);
    if (!m) return [];
    const tok = m[1].toLowerCase();
    if (!tok) return [];
    return fields
      .filter((f) => {
        const t = fieldToken(f).toLowerCase();
        const l = (f.label || "").toLowerCase();
        return t.includes(tok) || l.includes(tok) || t.startsWith(tok);
      })
      .slice(0, 10)
      .map((field) => ({ kind: "field" as const, field }));
  }, [valueCtx, valuesQuery.data, freeText, caret, fields]);

  // Keep ac open when suggestions exist (only show after an identifier char typed)
  useEffect(() => {
    setAcOpen(acSuggestions.length > 0);
    setAcIndex(0);
  }, [acSuggestions]);

  const updateCaret = () => {
    if (editorRef.current) {
      caretSetRef.current = true;
      setCaret(editorRef.current.selectionStart ?? freeText.length);
    }
  };

  const insertAtCaret = useCallback(
    (snippet: string) => {
      setFreeText((prev) => {
        // Insert at the user-placed caret; if none was placed this session, append
        // at the end of the expression instead of the initial (0) position.

        const pos = caretSetRef.current ? caret : prev.length;
        const next = prev.slice(0, pos) + snippet + prev.slice(pos);
        const newPos = pos + snippet.length;
        caretSetRef.current = true;
        requestAnimationFrame(() => {
          editorRef.current?.focus();
          editorRef.current?.setSelectionRange(newPos, newPos);
          setCaret(newPos);
        });
        return next;
      });
      setAcOpen(false);
      setFreeError(null);
    },
    [],
  );

  // Insert a new term, auto-joining with the chosen operator when the expression
  // already ends in an operand (field/literal/RPAREN) that would need a connector.
  const insertTerm = useCallback(
    (term: string) => {
      // Judge join-eligibility against the effective insertion point: user caret,
      // otherwise end of expression (so a fresh/pre-filled form appends rather than
      // jamming the term into the middle).
      const before = freeText.slice(0, caretSetRef.current ? caret : freeText.length);
      const snippet = expressionNeedsJoin(before) ? ` ${joinOp} ${term}` : term;
      insertAtCaret(snippet);
    },
    [freeText, caret, caretSetRef, joinOp, insertAtCaret],
  );

  const insertFieldToken = useCallback(
    (f: ScreenField) => {
      // Replace the current incomplete token at the effective insertion point: user caret, otherwise end of expression.
      const before = freeText.slice(0, caretSetRef.current ? caret : freeText.length);
      const m = before.match(/([A-Za-z_][A-Za-z0-9_]*)$/);
      const tok = m?.[1];
      const base = caretSetRef.current ? caret : freeText.length;
      if (tok) {
        setFreeText(prev => prev.slice(0, base - tok.length) + fieldToken(f) + prev.slice(base));
        const newPos = base - tok.length + fieldToken(f).length;
        requestAnimationFrame(() => {
          editorRef.current?.focus();
          editorRef.current?.setSelectionRange(newPos, newPos);
          setCaret(newPos);
        });
      } else {
        insertAtCaret(fieldToken(f));
      }
      setAcOpen(false);
    },
    [freeText, caret, caretSetRef, insertAtCaret],
  );

  const insertValueToken = useCallback(
    (value: string) => {
      const ctx = valueCompletionContext(freeText, caretSetRef.current ? caret : freeText.length);
      const quoted = JSON.stringify(value);
      if (!ctx) {
        insertAtCaret(quoted);
        return;
      }
      const base = caretSetRef.current ? caret : freeText.length;
      setFreeText((prev) => prev.slice(0, ctx.replaceFrom) + quoted + prev.slice(base));
      const newPos = ctx.replaceFrom + quoted.length;
      requestAnimationFrame(() => {
        editorRef.current?.focus();
        editorRef.current?.setSelectionRange(newPos, newPos);
        setCaret(newPos);
      });
      setAcOpen(false);
    },
    [freeText, caret, insertAtCaret],
  );

  const applyAcItem = useCallback(
    (item: AcItem) => {
      if (item.kind === "value") insertValueToken(item.value);
      else insertFieldToken(item.field);
    },
    [insertValueToken, insertFieldToken],
  );

  const canApply = expressionLinked || isNumericPurpose
    ? freeText.trim().length > 0
    : freeText.trim().length > 0 || !!selectedField || !!selectedRecipe;

  const confirmPick = () => {
    if (isNumericPurpose) {
      if (!freeText.trim()) {
        setFreeError("Type a numeric expression (insert measure aliases, then + − * /)");
        return;
      }
      const valid = validateArithmeticExpression(freeText, fields);
      if (!valid.valid) {
        setFreeError(valid.error || "Invalid expression");
        return;
      }
      onPick({
        kind: "expr",
        text: freeText.trim(),
        operand: valid.operand ?? null,
      });
      return;
    }
    if (expressionLinked) {
      if (!freeText.trim()) {
        setFreeError("Type an expression (or insert a field / pick a recipe)");
        return;
      }
      const valid = validateFilterExpression(freeText, fields);
      if (!valid.valid) {
        setFreeError(valid.error || "Invalid expression");
        return;
      }
      const tokens = tokenize(freeText);
      const hasCmp = tokens.some((t) => t.type === "CMP");
      if (hasCmp) onPick({ kind: "predicate", text: freeText.trim() });
      else {
        const parsed = parseArithmeticTokens(tokens.filter((t) => t.type !== "CMP"));
        onPick({ kind: "expr", text: freeText.trim(), operand: parsed.operand });
      }
      return;
    }
    if (freeText.trim() && freeValidation.valid) {
      if (isNumericPurpose) {
        const valid = validateArithmeticExpression(freeText, fields);
        onPick({
          kind: "expr",
          text: freeText.trim(),
          operand: valid.operand ?? null,
        });
        return;
      }
      const tokens = tokenize(freeText);
      const hasCmp = tokens.some((t) => t.type === "CMP");
      if (hasCmp) onPick({ kind: "predicate", text: freeText.trim() });
      else {
        const parsed = parseArithmeticTokens(tokens.filter((t) => t.type !== "CMP"));
        onPick({ kind: "expr", text: freeText.trim(), operand: parsed.operand });
      }
      return;
    }
    if (selectedRecipe) {
      const hasCmp = /[><=]/.test(selectedRecipe.expr);
      if (!hasCmp || isNumericPurpose) {
        const valid = validateArithmeticExpression(selectedRecipe.expr, fields);
        onPick({
          kind: "expr",
          text: selectedRecipe.expr,
          operand: valid.operand ?? null,
          source: selectedRecipe,
        });
        return;
      }
      onPick(
        hasCmp
          ? { kind: "predicate", text: selectedRecipe.expr, source: selectedRecipe }
          : { kind: "expr", text: selectedRecipe.expr, source: selectedRecipe },
      );
      return;
    }
    if (selectedField) onPick({ kind: "field", field: selectedField });
  };

  // Critical: only render (and mount the portal) while the picker is open.
  if (!isOpen) return null;

  const purposeLabel = purpose
    ? { filter: "Filter", sort: "Sort", column: "Column", number: "Number" }[purpose]
    : null;
  const editorActive = expressionLinked || purpose === "sort" || purpose === "number";

  return createPortal(
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 p-6 backdrop-blur-[2px]" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex h-[86vh] w-[min(1240px,96vw)] flex-col overflow-hidden rounded-xl border border-line bg-surface-raised shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-line bg-surface px-4 py-2.5">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded bg-accent/15 text-accent text-xs font-bold">
              {purpose === "filter" ? "ƒ" : purpose === "sort" ? "⇅" : purpose === "number" ? "Σ" : "ℹ"}
            </span>
            <h3 className="text-sm font-bold text-ink">{title ?? "Field & Expression Browser"}</h3>
            {purposeLabel && (
              <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[9.5px] font-bold uppercase tracking-wider text-accent">
                {purposeLabel}
              </span>
            )}
            <span className="rounded bg-surface-sunk px-2 py-0.5 font-mono text-[10px] text-ink-muted">
              {fields.length} fields · {recipes.length} expressions
            </span>
          </div>
          <button type="button" onClick={onClose} className="rounded p-1 text-ink-muted hover:bg-surface-sunk hover:text-ink transition-colors" title="Close">
            ✕
          </button>
        </div>

        {/* 1. Expression editor (top) — authoring uses only */}
        {editorActive && (
          <div className="border-b border-line bg-surface px-4 py-2.5">
            <div className="flex items-center justify-between">
              <label className="text-[9.5px] font-bold uppercase tracking-wider text-ink-muted">
                {purpose === "number"
                  ? "Build numeric expression — insert measure aliases, then + − * /"
                  : expressionLinked
                    ? "Build Expression — insert fields below, then add operators"
                    : "Sort Expression / Value"}
              </label>
              {freeText.trim() && (
                <span
                  className={cn(
                    "rounded px-1.5 py-0.5 font-mono text-[9.5px] font-bold",
                    freeValidation.valid ? "bg-emerald-500/10 text-emerald-500" : "bg-amber-500/10 text-amber-500",
                  )}
                >
                  {freeValidation.valid ? "✓ valid" : "incomplete"}
                </span>
              )}
            </div>

            <div className="relative mt-1">
              <input
                ref={editorRef}
                type="text"
                value={freeText}
                onChange={(e) => {
                  setFreeText(e.target.value);
                  caretSetRef.current = true;
                  setCaret(e.target.selectionStart ?? e.target.value.length);
                  setFreeError(null);
                }}
                onClick={updateCaret}
                onKeyUp={updateCaret}
                onKeyDown={(e) => {
                  if (acOpen && acSuggestions.length) {
                    if (e.key === "ArrowDown") { e.preventDefault(); setAcIndex((i) => (i + 1) % acSuggestions.length); return; }
                    if (e.key === "ArrowUp") { e.preventDefault(); setAcIndex((i) => (i - 1 + acSuggestions.length) % acSuggestions.length); return; }
                    if (e.key === "Tab" || e.key === "Enter") { e.preventDefault(); applyAcItem(acSuggestions[acIndex]); return; }
                    if (e.key === "Escape") { setAcOpen(false); return; }
                  }
                  if (e.key === "Enter") { e.preventDefault(); confirmPick(); }
                }}
                placeholder={
                  purpose === "number"
                    ? "e.g. screen_1 + screen_2 + screen_3 + screen_4 + code_33"
                    : expressionLinked
                      ? "e.g. rs_rating >= 80 and close >= sma50d"
                      : "e.g. (close - sma50d) / atr_14"
                }
                className="w-full rounded-lg border border-line bg-surface-sunk px-3 py-1.5 font-mono text-[12px] text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/40"
              />

              {/* Autocomplete dropdown */}
              {acOpen && acSuggestions.length > 0 && (
                <div className="absolute left-0 right-0 top-full z-[70] mt-1 overflow-hidden rounded-lg border border-accent/40 bg-surface-raised shadow-2xl ring-1 ring-black/10">
                  {acSuggestions.map((item, i) => (
                    <button
                      key={item.kind === "value" ? `v:${item.value}` : item.field.name}
                      type="button"
                      onMouseDown={(e) => { e.preventDefault(); applyAcItem(item); }}
                      onMouseEnter={() => setAcIndex(i)}
                      className={cn(
                        "flex w-full items-center justify-between gap-2 px-3 py-1 text-left text-[11px] transition-colors",
                        i === acIndex ? "bg-accent/15 text-ink" : "hover:bg-surface-sunk text-ink",
                      )}
                    >
                      {item.kind === "value" ? (
                        <>
                          <span className="truncate font-mono text-accent font-bold">{JSON.stringify(item.value)}</span>
                          <span className="truncate text-ink-muted">{valueCtx?.field.label ?? "value"}</span>
                        </>
                      ) : (
                        <>
                          <span className="truncate font-mono text-accent font-bold">{fieldToken(item.field)}</span>
                          <span className="truncate text-ink-muted">{item.field.label}</span>
                        </>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {freeError ? (
              <p className="mt-1 text-[10px] font-semibold text-rose-500">{freeError}</p>
            ) : freeText.trim() && !freeValidation.valid ? (
              <p className="mt-1 text-[10px] text-amber-500">{freeValidation.error || "Incomplete expression"}</p>
            ) : null}

            {/* Default join operator + quick-insert chips */}
            <div className="mt-2 flex flex-wrap items-center gap-1">
              {purpose === "number" ? (
                <>
                  <span className="mr-0.5 text-[9px] font-bold uppercase tracking-wider text-ink-faint">
                    join aliases with
                  </span>
                  {["+", "-", "*", "/"].map((op) => (
                    <button
                      key={op}
                      type="button"
                      onClick={() => setJoinOp(op)}
                      title={`Arithmetic ${op}`}
                      className={cn(
                        "rounded border px-1.5 py-0.5 font-mono text-[10px] font-semibold transition-colors",
                        joinOp === op
                          ? "border-accent bg-accent/15 text-accent"
                          : "border-line bg-surface-sunk text-ink-muted hover:border-accent/60 hover:text-accent",
                      )}
                    >
                      {op}
                    </button>
                  ))}
                  <span className="mx-1 h-4 w-px bg-line" />
                  <span className="mr-0.5 text-[9px] font-bold uppercase tracking-wider text-ink-faint">math</span>
                  {ARITH_OPS.map((op) => (
                    <OpChip key={op} op={op} title={`Arithmetic ${op}`} onClick={() => insertAtCaret(` ${op} `)} />
                  ))}
                </>
              ) : (
                <>
                  <span className="mr-0.5 text-[9px] font-bold uppercase tracking-wider text-ink-faint">join new terms with</span>
                  {["and", "or", "+", "-", "*", "/"].map((op) => (
                    <button
                      key={op}
                      type="button"
                      onClick={() => setJoinOp(op)}
                      title={op === "and" || op === "or" ? `Combine with ${op}` : `Arithmetic ${op}`}
                      className={cn(
                        "rounded border px-1.5 py-0.5 font-mono text-[10px] font-semibold transition-colors",
                        joinOp === op
                          ? "border-accent bg-accent/15 text-accent"
                          : "border-line bg-surface-sunk text-ink-muted hover:border-accent/60 hover:text-accent",
                      )}
                    >
                      {op}
                    </button>
                  ))}
                  <span className="mx-1 h-4 w-px bg-line" />
                  <span className="mr-0.5 text-[9px] font-bold uppercase tracking-wider text-ink-faint">compare</span>
                  {COMPARISON_OPS.map((op) => (
                    <OpChip key={op} op={op} title={`Compare ${op}`} onClick={() => insertAtCaret(` ${op} `)} />
                  ))}
                  <span className="ml-2 mr-0.5 text-[9px] font-bold uppercase tracking-wider text-ink-faint">math</span>
                  {ARITH_OPS.map((op) => (
                    <OpChip key={op} op={op} title={`Arithmetic ${op}`} onClick={() => insertAtCaret(` ${op} `)} />
                  ))}
                </>
              )}
            </div>
          </div>
        )}

        {/* 2. Tabs */}
        <div className="flex items-center justify-between border-b border-line bg-surface-raised/60 px-4 py-1.5">
          {hasModes ? (
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => setActiveMode("fields")}
                className={cn("rounded px-2.5 py-1 text-[11px] font-bold transition-colors", activeMode === "fields" ? "bg-accent/20 text-accent" : "text-ink-muted hover:text-ink")}
              >
                Fields
              </button>
              <button
                type="button"
                onClick={() => setActiveMode("expressions")}
                className={cn("rounded px-2.5 py-1 text-[11px] font-bold transition-colors", activeMode === "expressions" ? "bg-accent/20 text-accent" : "text-ink-muted hover:text-ink")}
              >
                Expressions
              </button>
            </div>
          ) : null}
          <span className="text-[10px] text-ink-faint">
            {activeMode === "fields" ? "ClickHouse table columns — click to preview" : "Expression knowledgebase — grouped by purpose"}
          </span>
          {activeMode === "expressions" && (
            <button
              type="button"
              onClick={() => setShowManageDialog(true)}
              className="ml-auto rounded border border-line bg-surface px-1.5 py-0.5 text-[9px] font-mono text-ink-muted hover:border-accent hover:text-accent hover:bg-accent/5 transition-colors"
              title="Manage expressions"
            >
              Manage
            </button>
          )}
        </div>

        {/* 3. Search */}
        <div className="border-b border-line px-4 py-2">
          <div className="relative">
            <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-faint text-[11px]">🔍</span>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={activeMode === "fields" ? "Search fields by name, label, category, description…" : "Search expressions by label, formula, or purpose…"}
              className="w-full rounded-lg border border-line bg-surface-sunk py-1.5 pl-8 pr-3 font-mono text-[12px] text-ink placeholder:text-ink-faint focus:border-accent focus:outline-none"
            />
          </div>
        </div>

        {/* 4. Master / Detail */}
        <div className="flex min-h-0 flex-1">
          {/* Master list */}
          <div className="w-[46%] min-w-[320px] flex-shrink-0 overflow-y-auto border-r border-line bg-surface/40">
            {activeMode === "fields" ? (
              filteredGroups.length === 0 ? (
                <div className="px-4 py-8 text-center text-[12px] text-ink-muted">No fields match “{query}”</div>
              ) : (
                filteredGroups.map((group) => (
                  <div key={group.label}>
                    <div className="sticky top-0 z-[5] border-b border-line/50 bg-surface/95 px-3 py-1 text-[9.5px] font-bold uppercase tracking-wider text-ink-muted backdrop-blur">
                      {group.label} · {group.fields.length}
                    </div>
                    {group.fields.map((f) => {
                      const isSel = f.name === selectedName;
                      return (
                        <div
                          key={f.name}
                          onClick={() => { setSelectedName(f.name); setSelectedRecipe(null); }}
                          className={cn(
                            "group flex w-full cursor-pointer items-start justify-between gap-2 border-b border-line/30 px-3 py-1.5 transition-colors",
                            isSel ? "bg-accent/10" : "hover:bg-surface-sunk",
                          )}
                        >
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center justify-between gap-2">
                              <span className={cn("truncate text-[12px] font-semibold", isSel ? "text-accent" : "text-ink")}>{f.label}</span>
                              <span className="shrink-0 rounded bg-surface-sunk px-1.5 py-0.5 font-mono text-[9px] text-ink-muted">{fieldToken(f)}</span>
                            </div>
                            <p className="mt-0.5 line-clamp-2 text-[10px] leading-snug text-ink-muted">
                              {f.description || "Database screener metric for universe filtering and sorting."}
                            </p>
                          </div>
                          {/* Insert into expression button (editor uses) */}
                          {editorActive && (
                            <button
                              type="button"
                              title={`Insert ${fieldToken(f)} into expression`}
                              onClick={(e) => { e.stopPropagation(); insertTerm(fieldToken(f)); }}
                              className="mt-1 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-surface-sunk text-[10px] font-bold text-ink-muted opacity-0 transition-opacity hover:bg-accent/20 hover:text-accent group-hover:opacity-100"
                            >
                              +
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ))
              )
            ) : filteredRecipes.length === 0 ? (
              <div className="px-4 py-8 text-center text-[12px] text-ink-muted">No matching expressions{purpose ? ` for ${purpose}` : ""}</div>
            ) : (
              filteredRecipes.map((grp) => (
                <div key={grp.purpose}>
                  <div className="sticky top-0 z-[5] border-b border-line/50 bg-surface/95 px-3 py-1 text-[9.5px] font-bold uppercase tracking-wider backdrop-blur" style={{ color: purposeColor(grp.purpose) }}>
                    {grp.purpose} · {grp.recipes.length}
                  </div>
                  {grp.recipes.map((r) => {
                    const isSel = selectedRecipe?.id === r.id;
                    return (
                      <div
                        key={r.id}
                        onClick={() => { setSelectedRecipe(r); setSelectedName(null); }}
                        className={cn(
                          "group flex w-full cursor-pointer items-start justify-between gap-2 border-b border-line/30 px-3 py-1.5 transition-colors",
                          isSel ? "bg-accent/10" : "hover:bg-surface-sunk",
                        )}
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center justify-between gap-2">
                            <span className={cn("truncate text-[12px] font-semibold", isSel ? "text-accent" : "text-ink")}>{r.label}</span>
                            <span className="shrink-0 rounded bg-surface-sunk px-1.5 py-0.5 font-mono text-[9px] text-ink-muted">{r.category || grp.purpose}</span>
                          </div>
                          <code className="mt-0.5 block truncate font-mono text-[10px] text-accent">{r.expr}</code>
                          <p className="mt-0.5 line-clamp-2 text-[10px] leading-snug text-ink-muted">{r.desc}</p>
                        </div>
                        {editorActive && (
                          <button
                            type="button"
                            title={`Insert ${r.expr}`}
                            onClick={(e) => { e.stopPropagation(); insertTerm(r.expr); setSelectedRecipe(r); }}
                            className="mt-1 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-surface-sunk text-[10px] font-bold text-ink-muted opacity-0 transition-opacity hover:bg-accent/20 hover:text-accent group-hover:opacity-100"
                          >
                            +
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              ))
            )}
          </div>

          {/* Detail pane */}
          <div className="flex min-w-0 flex-1 flex-col">
            <div className="min-h-0 flex-1 overflow-y-auto">
              {activeMode === "fields" ? (
                selectedField ? (
                  <div className="p-4">
                    <FieldDetailCard field={selectedField} className="w-full" />
                    {editorActive && (
                      <button
                        type="button"
                        onClick={() => insertTerm(fieldToken(selectedField))}
                        className="mt-2 w-full rounded-lg border border-accent/40 bg-accent/10 px-3 py-2 text-[11px] font-bold text-accent hover:bg-accent/20"
                      >
                        + Insert "{fieldToken(selectedField)}" into expression
                      </button>
                    )}
                  </div>
                ) : (
                  <div className="flex h-full items-center justify-center px-6 text-center text-[12px] text-ink-muted">
                    Select a field to preview its definition & AST details
                  </div>
                )
              ) : selectedRecipe ? (
                <div className="p-4">
                  <div className="rounded-lg border border-accent/30 bg-surface p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-[12px] font-bold text-ink">{selectedRecipe.label}</span>
                      <span className="rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider" style={{ color: purposeColor(grpPurposeOf(selectedRecipe)) }}>
                        {selectedRecipe.category || grpPurposeOf(selectedRecipe)}
                      </span>
                    </div>
                    <code className="mt-2 block rounded bg-surface-sunk px-2 py-1.5 font-mono text-[11px] text-accent">{selectedRecipe.expr}</code>
                    <p className="mt-2 text-[11px] leading-relaxed text-ink">{selectedRecipe.desc}</p>
                  </div>
                  {editorActive && (
                    <button
                      type="button"
                      onClick={() => insertTerm(selectedRecipe.expr)}
                      className="mt-2 w-full rounded-lg border border-accent/40 bg-accent/10 px-3 py-2 text-[11px] font-bold text-accent hover:bg-accent/20"
                    >
                      + Insert recipe into expression
                    </button>
                  )}
                </div>
              ) : (
                <div className="flex h-full items-center justify-center px-6 text-center text-[12px] text-ink-muted">
                  Select a field / expression to preview, or author one above
                </div>
              )}
            </div>

            {/* Action footer */}
            {canApply && (
              <div className="flex items-center justify-end gap-2 border-t border-line px-4 py-2.5">
                <button type="button" onClick={onClose} className="rounded border border-line bg-surface px-3 py-1.5 text-[11px] font-semibold text-ink-muted hover:text-ink transition-colors">
                  Cancel
                </button>
                <button type="button" onClick={confirmPick} className="rounded-lg bg-accent px-3.5 py-1.5 text-[11.5px] font-bold text-white hover:opacity-90 transition-opacity">
                  {actionLabel}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
      {showManageDialog && (
      <div className="fixed inset-0 z-[300] flex items-center justify-center bg-black/50 p-4">
        <div className="w-full max-w-2xl max-h-[85vh] overflow-hidden rounded-xl border border-line bg-surface-sunk flex flex-col">
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <h3 className="text-[12px] font-bold text-ink">Manage Expressions</h3>
            <button
              type="button"
              onClick={() => { setShowManageDialog(false); setEditingRecipe(null); }}
              className="rounded border border-line bg-surface p-1 text-ink-muted hover:bg-accent/5 hover:text-accent transition-colors"
            >
              ✕
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {/* Add/Edit Form */}
            <div className="border border-line/60 rounded-lg p-4 space-y-3">
              <h4 className="text-[11px] font-bold text-ink">{editingRecipe ? "Edit Expression" : "Add New Expression"}</h4>
              <div className="space-y-2">
                <div>
                  <label className="block text-[10px] font-bold text-ink-muted mb-1">Label</label>
                  <input
                    type="text"
                    value={editingRecipe ? editingRecipe.label : newRecipe.label}
                    onChange={(e) => setNewRecipe({ ...newRecipe, label: e.target.value })}
                    placeholder="e.g. My Custom Breakout"
                    className="w-full rounded border border-line bg-surface px-2 py-1.5 text-[11px] font-mono text-ink"
                    disabled={savingRecipe}
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-ink-muted mb-1">Expression</label>
                  <input
                    type="text"
                    value={editingRecipe ? editingRecipe.expr : newRecipe.expr}
                    onChange={(e) => setNewRecipe({ ...newRecipe, expr: e.target.value })}
                    placeholder="e.g. close > high[-1]"
                    className="w-full rounded border border-line bg-surface px-2 py-1.5 text-[11px] font-mono text-ink"
                    disabled={savingRecipe}
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-ink-muted mb-1">Description</label>
                  <input
                    type="text"
                    value={editingRecipe ? editingRecipe.desc : newRecipe.description}
                    onChange={(e) => setNewRecipe({ ...newRecipe, description: e.target.value })}
                    placeholder="Optional tooltip text"
                    className="w-full rounded border border-line bg-surface px-2 py-1.5 text-[11px] font-mono text-ink"
                    disabled={savingRecipe}
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-ink-muted mb-1">Category</label>
                  <input
                    type="text"
                    value={editingRecipe ? editingRecipe.category : newRecipe.category}
                    onChange={(e) => setNewRecipe({ ...newRecipe, category: e.target.value })}
                    placeholder="e.g. Breakout, Momentum, Multi-bar"
                    className="w-full rounded border border-line bg-surface px-2 py-1.5 text-[11px] font-mono text-ink"
                    disabled={savingRecipe}
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-ink-muted mb-1">Purposes</label>
                  <div className="flex gap-2">
                    {(["filter", "sort", "number", "column"] as const).map((p) => (
                      <label key={p} className="flex items-center gap-1.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={newRecipe.purposes.includes(p)}
                          onChange={(e) => setNewRecipe({ ...newRecipe, purposes: e.target.checked ? [...newRecipe.purposes, p] : newRecipe.purposes.filter((pur) => pur !== p) })}
                          className="rounded border border-line bg-surface"
                        />
                        <span className="text-[10px] font-medium capitalize">{p}</span>
                      </label>
                    ))}
                  </div>
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-2 border-t border-line/40">
                <button
                  type="button"
                  onClick={() => { setEditingRecipe(null); setNewRecipe({ label: "", expr: "", description: "", category: "Custom", purposes: ["filter"] }); }}
                  className="rounded border border-line bg-surface px-3 py-1.5 text-[11px] font-semibold text-ink-muted hover:bg-accent/5"
                  disabled={savingRecipe}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={async () => {
                    const payload = editingRecipe
                      ? { ...newRecipe }
                      : { ...newRecipe, id: crypto.randomUUID() };
                    setSavingRecipe(true);
                    try {
                      const res = await fetch(editingRecipe ? `/api/screens/formula-presets/${editingRecipe.id}` : "/api/screens/formula-presets", {
                        method: editingRecipe ? "PATCH" : "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(payload),
                      });
                      if (res.ok) {
                          const saved = (await res.json()) as ApiFormulaPreset;
                          setManagedRecipes((prev) => {
                            const current = prev ?? [];
                            if (editingRecipe) {
                              return current.map((p) => p.id === saved.id ? saved : p);
                            }
                            return [...current, saved];
                          });
                        setEditingRecipe(null);
                        setNewRecipe({ label: "", expr: "", description: "", category: "Custom", purposes: ["filter"] });
                      }
                    } catch (e) {
                      console.error("Failed to save expression:", e);
                    } finally {
                      setSavingRecipe(false);
                    }
                  }}
                  className="rounded bg-accent px-3.5 py-1.5 text-[11px] font-bold text-white hover:opacity-90 transition-opacity"
                  disabled={savingRecipe || !newRecipe.label || !newRecipe.expr}
                >
                  {savingRecipe ? "Saving…" : (editingRecipe ? "Save Changes" : "Add Expression")}
                </button>
              </div>
            </div>

            {/* Presets List */}
            <div className="space-y-2">
              <h4 className="text-[11px] font-bold text-ink-muted uppercase tracking-wider">Your Expressions</h4>
              <div className="divide-y divide-line/40">
                {availableRecipes.map((r) => {
                  const isStaticRecipe = staticRecipeIds.has(r.id);
                  return (
                  <div
                    key={r.id}
                    className="flex items-center justify-between gap-2 p-2 rounded-lg bg-surface-sunk/50 hover:bg-surface-sunk transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-[11px] text-ink font-semibold">{r.label}</span>
                        {isStaticRecipe && (
                          <span className="rounded px-1.5 py-0.5 text-[8px] font-mono text-ink-faint bg-line/30">Built-in</span>
                        )}
                        {!isStaticRecipe && (
                          <span className="rounded px-1.5 py-0.5 text-[8px] font-mono text-accent bg-accent/10">Custom</span>
                        )}
                      </div>
                      <div className="text-[10px] text-ink-muted truncate font-mono">{r.expr}</div>
                      <p className="text-[9px] text-ink-faint line-clamp-1">{r.desc}</p>
                      <span className="rounded px-1.5 py-0.5 text-[8px] font-mono text-ink-muted bg-surface-sunk">{r.category}</span>
                    </div>
                    {!isStaticRecipe && (
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => { setEditingRecipe(r); setNewRecipe({ label: r.label, expr: r.expr, description: r.desc ?? "", category: r.category ?? "Custom", purposes: r.purposes || ["filter"] }); }}
                        className="rounded border border-line bg-surface p-1.5 text-[10px] text-ink-muted hover:bg-accent/5 hover:text-accent"
                        title="Edit"
                      >
                        ✏️
                      </button>
                      <button
                        type="button"
                        onClick={async () => {
                          if (!confirm(`Delete "${r.label}"?`)) return;
                          try {
                            const res = await fetch(`/api/screens/formula-presets/${r.id}`, { method: "DELETE" });
                            if (res.ok) {
                              setManagedRecipes((prev) => (prev ?? []).filter((p) => p.id !== r.id));
                            }
                          } catch (e) {
                            console.error("Failed to delete expression:", e);
                          }
                        }}
                        className="rounded border border-amber-500/50 bg-surface p-1.5 text-[10px] text-amber-500 hover:bg-amber-500/10"
                        title="Delete"
                      >
                        🗑️
                      </button>
                    </div>
                    )}
                  </div>
                  );
                })}
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
    </div>,
    document.body,
  );
}

function OpChip({ op, title, onClick }: { op: string; title: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className="rounded border border-line bg-surface-sunk px-1.5 py-0.5 font-mono text-[10px] font-semibold text-ink-muted transition-colors hover:border-accent/60 hover:text-accent"
    >
      {op}
    </button>
  );
}

function purposeColor(p: string): string {
  switch (p) {
    case "filter": return "#0b6e4f";
    case "sort": return "#1d4ed8";
    case "column": return "#6d28d9";
    default: return "#5a6577";
  }
}

function grpPurposeOf(r: ExpressionRecipe): string {
  return r.purposes?.[0] ?? (recipePurposeFlags(r).values().next().value as string) ?? "Expression";
}

export default FieldBrowserModal;