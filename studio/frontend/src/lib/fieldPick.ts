import type { ScreenField, IrOperand } from "../types";

/** A reusable named expression recipe shown in the unified field/expression browser. */
export interface ExpressionRecipe {
  /** Unique id (slug) */
  id: string;
  /** Human label, e.g. "ATR Breakout" */
  label: string;
  /** Infix formula text shown in the picker, e.g. "(close - sma50d) / atr_14 >= 2.0" */
  expr: string;
  /** Short description of what the expression selects/ranks */
  desc: string;
  /** Category grouping (default "Expression") */
  category?: string;
  /** Purpose(s) this recipe is relevant for — filter/sort/column/number */
  purposes?: Array<"filter" | "sort" | "column" | "number">;
}

/**
 * What the user picked in the unified browser. Exactly one of:
 *  - field: a catalog field
 *  - expr: a free-form / recipe arithmetic formula (as text + parsed operand, when value-only)
 *  - predicate: a full boolean expression recipe (e.g. used to build a filter)
 */
export type FieldPick =
  | { kind: "field"; field: ScreenField }
  | { kind: "expr"; text: string; operand?: IrOperand | null; source?: ExpressionRecipe }
  | { kind: "predicate"; text: string; source?: ExpressionRecipe };
