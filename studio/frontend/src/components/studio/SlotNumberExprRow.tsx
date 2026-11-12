import { useEffect, useState } from "react";
import type { ScreenField } from "../../types";
import type { IrOperand } from "../../types";
import type { SlotExpr } from "../strategy/StrategyDocument";
import {
  formatOperandToString,
  parseArithmeticTokens,
  tokenize,
} from "../../lib/formulaParser";

type Props = {
  fields: ScreenField[];
  value: SlotExpr | null | undefined;
  onChange: (next: SlotExpr | null) => void;
  presets?: { label: string; expr: SlotExpr }[];
  placeholder?: string;
};

function exprToText(expr: Record<string, unknown> | null | undefined): string {
  if (!expr) return "";
  try {
    return formatOperandToString(expr as IrOperand);
  } catch {
    return "";
  }
}

function textToExpr(raw: string): { expr: Record<string, unknown> | null; error: string | null } {
  const trimmed = raw.trim();
  if (!trimmed) return { expr: null, error: null };
  const { operand, error } = parseArithmeticTokens(tokenize(trimmed));
  if (error || !operand) return { expr: null, error: error || "Invalid expression" };
  return { expr: operand as unknown as Record<string, unknown>, error: null };
}

/** Number / field measure body: formula text to AST Operand (col / lit / + - * /). */
export function SlotNumberExprRow({
  fields: _fields,
  value,
  onChange,
  presets = [],
  placeholder = "e.g. screen_1 + screen_2 + code_33",
}: Props) {
  const committed =
    value?.kind === "number" ? exprToText(value.expr as Record<string, unknown>) : "";
  const [text, setText] = useState(committed);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setText(committed);
    setError(null);
  }, [committed]);

  function commitText(next: string) {
    setText(next);
    const { expr, error: err } = textToExpr(next);
    setError(err);
    if (err) return;
    if (!expr) {
      onChange(null);
      return;
    }
    onChange({ kind: "number", expr });
  }

  return (
    <div className="space-y-1">
      <input
        type="text"
        value={text}
        onChange={(e) => commitText(e.target.value)}
        onBlur={() => commitText(text)}
        placeholder={placeholder}
        spellCheck={false}
        className="w-full rounded border border-line bg-surface px-1.5 py-1 font-mono text-[11px] text-ink"
      />
      {error ? <p className="text-[10px] text-danger">{error}</p> : null}
      {presets.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {presets.map((p) => (
            <button
              key={p.label}
              type="button"
              onClick={() => {
                const t = exprToText(p.expr.expr as Record<string, unknown>);
                setText(t);
                setError(null);
                onChange(p.expr);
              }}
              className="rounded border border-line px-1.5 py-0.5 text-[10px] text-ink hover:bg-surface-sunk"
            >
              {p.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
