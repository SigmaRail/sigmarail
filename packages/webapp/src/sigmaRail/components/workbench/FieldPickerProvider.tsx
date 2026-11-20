import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchFields } from "../../api/screens";
import type { ScreenField } from "../../types";
import type { ExpressionRecipe, FieldPick } from "../../lib/fieldPick";
import { studioAgentBridge, getPathValue } from "../../lib/studioAgentBridge";
import {
  formatOperandToString,
  parseArithmeticTokens,
  parseExpressionToFilterRows,
  tokenize,
} from "../../lib/formulaParser";
import { rowsToWhere } from "../../lib/irFilters";
import { FieldBrowserModal, type BrowserMode } from "./FieldBrowserModal";
import { EXPRESSION_RECIPES } from "./expressionRecipes";

/** Which action the picker result will drive. */
export type PickerUse = "filter" | "sort" | "column" | "number" | "info";

export interface OpenPickerOptions {
  use: PickerUse;
  /** Optional catalog override (caller already has fields loaded) */
  fields?: ScreenField[];
  /** title override */
  title?: string;
  /** action button label */
  actionLabel?: string;
  /** pre-select a field */
  initialFieldName?: string | null;
  /** pre-fill free-form expression text (filter / number mode) */
  initialExpression?: string;
  /** force a single mode */
  mode?: BrowserMode;
  /** on result */
  onPick?: (pick: FieldPick) => void;
  /**
   * Bridge target path (e.g. "bindings.pcm_allow_entry.where"). When set, the
   * dialog is mirrored to webmcp (`field_browser_*` tools) and an agent can
   * apply an expression to it directly.
   */
  target?: string;
  /** Current value at the bridge target (for webmcp state). */
  current?: unknown;
}

interface FieldPickerContextValue {
  openPicker: (opts: OpenPickerOptions) => void;
  closePicker: () => void;
  /** catalog fields (shared query) */
  fields: ScreenField[];
  /** whether catalog is still loading */
  loading: boolean;
}

const FieldPickerContext = createContext<FieldPickerContextValue | null>(null);

export function useFieldPicker(): FieldPickerContextValue {
  const ctx = useContext(FieldPickerContext);
  if (!ctx) throw new Error("useFieldPicker must be used within <FieldPickerProvider>");
  return ctx;
}

/**
 * Single app-wide field/expression browser modal. Mount near the app root.
 * Any control (filter chips, sort, add column, ℹ glyphs) opens it through
 * `useFieldPicker().openPicker(...)` so the whole app shares one picker UI.
 */
export function FieldPickerProvider({
  children,
  recipes = EXPRESSION_RECIPES,
}: {
  children: ReactNode;
  recipes?: ExpressionRecipe[];
}) {
  const fieldsQuery = useQuery({
    queryKey: ["field-catalog"],
    queryFn: fetchFields,
    staleTime: 5 * 60_000,
  });
  const fields = fieldsQuery.data ?? [];

  const [open, setOpen] = useState(false);
  const [opts, setOpts] = useState<OpenPickerOptions | null>(null);
  const optsRef = useRef<OpenPickerOptions | null>(null);

  const openPicker = useCallback((o: OpenPickerOptions) => {
    optsRef.current = o;
    setOpts(o);
    setOpen(true);
  }, []);
  const closePicker = useCallback(() => {
    optsRef.current = null;
    setOpen(false);
    setOpts(null);
  }, []);

  // Mirror dialog state + register agent actions on the StudioAgentBridge.
  useEffect(() => {
    studioAgentBridge.updateState({
      fieldBrowser: {
        open,
        target: opts?.target ?? null,
        mode: opts?.mode ?? null,
        current: opts?.current ?? null,
        fields: (opts?.fields && opts.fields.length > 0 ? opts.fields : fields) as unknown,
      },
    });
  }, [open, opts, fields]);

  useEffect(() => {
    const offOpen = studioAgentBridge.registerAction("fieldBrowserOpen", (args: { target?: string; mode?: string }) => {
      const doc = studioAgentBridge.getState().strategyDoc;
      const target = args.target || optsRef.current?.target || null;
      const current = target && doc ? getPathValue(doc, target) : null;
      let initialExpression: string | undefined;
      if (current && typeof current === "object") {
        const cur = current as Record<string, unknown>;
        if (cur.kind === "number" && cur.expr) {
          initialExpression = formatOperandToString(cur.expr as never);
        } else if (cur.kind === "bool" && cur.where) {
          initialExpression = undefined; // AST shown as chips inside the dialog
        }
      } else if (typeof current === "number" || typeof current === "string") {
        initialExpression = String(current);
      }
      const use: PickerUse = args.mode === "number" ? "number" : "filter";
      openPicker({
        use,
        mode: (args.mode as BrowserMode | undefined) ?? undefined,
        target: target ?? undefined,
        current,
        initialExpression,
        title: target ? `Field & Expression Browser — ${target}` : undefined,
      });
      return { open: true, target, mode: args.mode ?? null, current: current ?? null };
    });

    const offApply = studioAgentBridge.registerAction("fieldBrowserApply", (args: { expr: unknown }) => {
      const target = optsRef.current?.target;
      if (!target) throw new Error("No field-browser target is open; call field_browser_open first.");
      const doc = studioAgentBridge.getState().strategyDoc;
      const cur = target && doc ? getPathValue(doc, target) : null;
      let value: unknown;
      if (args.expr !== null && typeof args.expr === "object") {
        // Raw AST: treat as a where-node for bool slots, operand for number slots.
        const isNumberSlot = (cur as Record<string, unknown> | null)?.kind === "number" || /(^|\.)expr$/.test(target);
        value = isNumberSlot ? { kind: "number", expr: args.expr } : { kind: "bool", where: args.expr };
      } else if (typeof args.expr === "string" && args.expr.trim()) {
        const text = args.expr.trim();
        const isNumberSlot = (cur as Record<string, unknown> | null)?.kind === "number" || /(^|\.)expr$/.test(target);
        if (isNumberSlot) {
          const { expr, error } = textToNumberExpr(text);
          if (error || !expr) throw new Error(`Invalid expression: ${error ?? "empty"}`);
          value = { kind: "number", expr };
        } else {
          const parsed = parseExpressionToFilterRows(text, "agent");
          if (parsed.error || !parsed.rows.length) {
            throw new Error(`Could not parse expression: ${parsed.error ?? text}`);
          }
          value = { kind: "bool", where: rowsToWhere(parsed.rows) as Record<string, unknown> };
        }
      } else {
        value = null;
      }
      closePicker();
      return studioAgentBridge.dispatch("setStrategyField", { path: target, value });
    });

    return () => {
      offOpen();
      offApply();
    };
  }, [openPicker, closePicker]);

  const value = useMemo<FieldPickerContextValue>(
    () => ({ openPicker, closePicker, fields, loading: fieldsQuery.isLoading }),
    [openPicker, closePicker, fields, fieldsQuery.isLoading],
  );

  return (
    <FieldPickerContext.Provider value={value}>
      {children}
      <FieldBrowserModal
        isOpen={open}
        fields={opts?.fields && opts.fields.length > 0 ? opts.fields : fields}
        recipes={recipes}
        initialFieldName={opts?.initialFieldName ?? null}
        initialExpression={opts?.initialExpression}
        mode={opts?.mode}
        purpose={useToPurpose(opts?.use)}
        expressionLinked={opts?.use === "filter" || opts?.use === "number"}
        title={opts?.title ?? defaultTitle(opts?.use)}
        actionLabel={opts?.actionLabel ?? defaultAction(opts?.use)}
        onClose={closePicker}
        onPick={(pick) => {
          const cb = opts?.onPick;
          closePicker();
          cb?.(pick);
        }}
      />
    </FieldPickerContext.Provider>
  );
}

function textToNumberExpr(raw: string): { expr: Record<string, unknown> | null; error: string | null } {
  try {
    const tokens = tokenize(raw);
    const parsed = parseArithmeticTokens(tokens);
    if (parsed.error) return { expr: null, error: parsed.error };
    return { expr: parsed.operand as unknown as Record<string, unknown>, error: null };
  } catch (err) {
    return { expr: null, error: err instanceof Error ? err.message : String(err) };
  }
}

function useToPurpose(use?: PickerUse): "filter" | "sort" | "column" | "number" | undefined {
  switch (use) {
    case "filter":
      return "filter";
    case "sort":
      return "sort";
    case "column":
      return "column";
    case "number":
      return "number";
    default:
      return undefined;
  }
}

function defaultTitle(use?: PickerUse): string {
  switch (use) {
    case "filter":
      return "Add / Edit Filter (Field or Expression)";
    case "sort":
      return "Choose Sort Key (Field or Expression)";
    case "column":
      return "Add Column (Catalog Field)";
    case "number":
      return "Numeric Expression (Measure Aliases + Math)";
    default:
      return "Field & Expression Browser";
  }
}

function defaultAction(use?: PickerUse): string {
  switch (use) {
    case "filter":
      return "Apply Filter";
    case "sort":
      return "Sort by this";
    case "column":
      return "Add Column";
    case "number":
      return "Use Expression";
    default:
      return "Select";
  }
}

export default FieldPickerProvider;