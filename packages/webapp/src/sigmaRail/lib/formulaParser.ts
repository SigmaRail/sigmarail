/**
 * Mathematical Infix Formula Tokenizer & Shunting-Yard AST Parser
 * Converts text expressions like:
 *   "(px.close - px.sma50d) / px.atr_14 >= 2.0"
 *   "px.close >= px.low_52w * 1.30"
 *   "rt.rs_rating >= 70"
 * into recursive UniverseQueryV1 AST operand trees and vice-versa.
 */

import type { AppliedFilterRow, ComparisonOp, IrOperand, ScreenField } from "../types";

export type TokenType = "IDENT" | "STRING" | "NUM" | "OP" | "CMP" | "AND" | "OR" | "LPAREN" | "RPAREN";

export interface Token {
  type: TokenType;
  value: string;
  offset?: number;
}

const COMPARISON_OPS: Record<string, ComparisonOp> = {
  ">=": "gte",
  "≥": "gte",
  "<=": "lte",
  "≤": "lte",
  ">": "gt",
  "<": "lt",
  "==": "eq",
  "=": "eq",
  "!=": "neq",
  "<>": "neq",
  "≠": "neq",
};

const OP_PRECEDENCE: Record<string, number> = {
  "+": 1,
  "-": 1,
  "*": 2,
  "/": 2,
  "%": 2,
};

export function tokenize(input: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;
  const str = input.trim();

  while (i < str.length) {
    const ch = str[i];

    // Skip whitespace
    if (/\s/.test(ch)) {
      i++;
      continue;
    }

    // Two-character comparators: >=, <=, ==, !=, <>
    if (i + 1 < str.length) {
      const twoChar = str.slice(i, i + 2);
      if (COMPARISON_OPS[twoChar]) {
        tokens.push({ type: "CMP", value: twoChar });
        i += 2;
        continue;
      }
    }

    // Single-character comparators: >, <, =, ≥, ≤
    if (COMPARISON_OPS[ch]) {
      tokens.push({ type: "CMP", value: ch });
      i++;
      continue;
    }

    // Parentheses
    if (ch === "(") {
      tokens.push({ type: "LPAREN", value: "(" });
      i++;
      continue;
    }
    if (ch === ")") {
      tokens.push({ type: "RPAREN", value: ")" });
      i++;
      continue;
    }

    // Negative number (e.g. -100, -0.5) when '-' precedes a digit after CMP, OP, LPAREN, or at start
    if (
      ch === "-" &&
      i + 1 < str.length &&
      (/[0-9]/.test(str[i + 1]) || str[i + 1] === ".") &&
      (tokens.length === 0 || ["CMP", "OP", "LPAREN"].includes(tokens[tokens.length - 1].type))
    ) {
      let numStr = "-";
      i++;
      while (i < str.length && /[0-9.]/.test(str[i])) {
        numStr += str[i];
        i++;
      }
      tokens.push({ type: "NUM", value: numStr });
      continue;
    }

    // Arithmetic operators: +, -, *, /, % (also ×, ÷)
    if (["+", "-", "*", "/", "%", "×", "÷"].includes(ch)) {
      const normalizedOp = ch === "×" ? "*" : ch === "÷" ? "/" : ch;
      tokens.push({ type: "OP", value: normalizedOp });
      i++;
      continue;
    }

    // Numbers (e.g. 70, 1.30, 0.05)
    if (/[0-9]/.test(ch) || (ch === "." && i + 1 < str.length && /[0-9]/.test(str[i + 1]))) {
      let numStr = "";
      while (i < str.length && /[0-9.]/.test(str[i])) {
        numStr += str[i];
        i++;
      }
      tokens.push({ type: "NUM", value: numStr });
      continue;
    }

    // Quoted string literals (e.g. "NYSE", 'Technology')
    if (ch === '"' || ch === "'") {
      const quote = ch;
      i++;
      let s = "";
      while (i < str.length && str[i] !== quote) {
        if (str[i] === "\\" && i + 1 < str.length) {
          s += str[i + 1];
          i += 2;
          continue;
        }
        s += str[i];
        i++;
      }
      if (i < str.length) i++;
      tokens.push({ type: "STRING", value: s });
      continue;
    }

    // Identifiers & Prefixed column names (e.g. px.close, rt.rs_rating, sma50d, true, false)
    if (/[a-zA-Z_]/.test(ch)) {
      let identStr = "";
      while (i < str.length && /[a-zA-Z0-9_.]/.test(str[i])) {
        identStr += str[i];
        i++;
      }
      const low = identStr.toLowerCase();
      if (low === "and" || low === "or") {
        tokens.push({ type: low === "and" ? "AND" : "OR", value: low });
        continue;
      }
      const token: Token = { type: "IDENT", value: identStr };
      // Optional bar offset suffix: [-N] for previous bars, [+N] for future bars
      if (i < str.length && str[i] === "[") {
        const bracketEnd = str.indexOf("]", i);
        if (bracketEnd !== -1) {
          const raw = str.slice(i + 1, bracketEnd).trim();
          const parsed = parseInt(raw, 10);
          if (!isNaN(parsed)) {
            token.offset = parsed;
            i = bracketEnd + 1;
          }
        }
      }
      tokens.push(token);
      continue;
    }

    // Unknown char, step forward
    i++;
  }

  return tokens;
}

/**
 * Parses a sequence of arithmetic tokens into an IrOperand tree using Shunting-Yard algorithm.
 * Returns { operand, error } with precise validation for operators and balance.
 */
export function parseArithmeticTokens(tokens: Token[]): {
  operand: IrOperand | null;
  error: string | null;
} {
  if (tokens.length === 0) {
    return { operand: null, error: "Empty operand expression" };
  }

  // Check for trailing or leading operators
  if (tokens[tokens.length - 1].type === "OP") {
    return {
      operand: null,
      error: `Trailing operator '${tokens[tokens.length - 1].value}' is missing a right-hand value or field`,
    };
  }
  if (tokens[0].type === "OP") {
    return {
      operand: null,
      error: `Expression cannot start with operator '${tokens[0].value}'`,
    };
  }

  // Check for consecutive operators or consecutive operands
  for (let i = 0; i < tokens.length - 1; i++) {
    const cur = tokens[i];
    const next = tokens[i + 1];
    if (cur.type === "OP" && next.type === "OP") {
      return { operand: null, error: `Consecutive operators '${cur.value} ${next.value}' are invalid` };
    }
    if (
      (cur.type === "IDENT" || cur.type === "NUM" || cur.type === "STRING") &&
      (next.type === "IDENT" || next.type === "NUM" || next.type === "STRING")
    ) {
      return { operand: null, error: `Missing operator between '${cur.value}' and '${next.value}'` };
    }
  }

  const outputQueue: IrOperand[] = [];
  const operatorStack: Token[] = [];

  for (const token of tokens) {
    if (token.type === "NUM") {
      outputQueue.push({ type: "lit", value: Number(token.value) });
    } else if (token.type === "STRING") {
      outputQueue.push({ type: "lit", value: token.value });
    } else if (token.type === "IDENT") {
      if (token.value.toLowerCase() === "true") {
        outputQueue.push({ type: "lit", value: true });
      } else if (token.value.toLowerCase() === "false") {
        outputQueue.push({ type: "lit", value: false });
      } else {
        const colName = token.value.includes(".") ? token.value.split(".").slice(1).join(".") : token.value;
        outputQueue.push({ type: "col", name: colName, offset: token.offset });
      }
    } else if (token.type === "OP") {
      const prec = OP_PRECEDENCE[token.value] || 0;
      while (
        operatorStack.length > 0 &&
        operatorStack[operatorStack.length - 1].type === "OP" &&
        (OP_PRECEDENCE[operatorStack[operatorStack.length - 1].value] || 0) >= prec
      ) {
        const topOp = operatorStack.pop()!;
        const right = outputQueue.pop();
        const left = outputQueue.pop();
        if (!left || !right) {
          return { operand: null, error: `Operator '${topOp.value}' is missing an operand` };
        }
        outputQueue.push({
          type: "formula",
          op: topOp.value,
          args: [left, right],
        });
      }
      operatorStack.push(token);
    } else if (token.type === "LPAREN") {
      operatorStack.push(token);
    } else if (token.type === "RPAREN") {
      let foundLparen = false;
      while (operatorStack.length > 0) {
        const topOp = operatorStack.pop()!;
        if (topOp.type === "LPAREN") {
          foundLparen = true;
          break;
        }
        const right = outputQueue.pop();
        const left = outputQueue.pop();
        if (!left || !right) {
          return { operand: null, error: `Operator '${topOp.value}' is missing an operand` };
        }
        outputQueue.push({
          type: "formula",
          op: topOp.value,
          args: [left, right],
        });
      }
      if (!foundLparen) {
        return { operand: null, error: "Unmatched closing parenthesis ')'" };
      }
    }
  }

  while (operatorStack.length > 0) {
    const topOp = operatorStack.pop()!;
    if (topOp.type === "LPAREN") {
      return { operand: null, error: "Unclosed parenthesis '('" };
    }
    if (topOp.type === "OP") {
      const right = outputQueue.pop();
      const left = outputQueue.pop();
      if (!left || !right) {
        return { operand: null, error: `Operator '${topOp.value}' is missing an operand` };
      }
      outputQueue.push({
        type: "formula",
        op: topOp.value,
        args: [left, right],
      });
    }
  }

  if (outputQueue.length !== 1) {
    return { operand: null, error: "Incomplete arithmetic expression" };
  }

  return { operand: outputQueue[0], error: null };
}

/**
 * Parses a full text expression into an AppliedFilterRow (LeftOperand CmpOp RightOperand).
 */
function parseSingleComparison(
  tokens: Token[],
  id: string,
): { row: AppliedFilterRow | null; error: string | null } {
  const cmpIndices = tokens
    .map((t, idx) => (t.type === "CMP" ? idx : -1))
    .filter((idx) => idx !== -1);

  if (cmpIndices.length > 1) {
    return { row: null, error: "Only one comparison operator (>=, <=, >, <, =) is allowed per clause" };
  }

  if (cmpIndices.length === 0) {
    // If no comparator provided, parse as single operand (e.g. boolean flag)
    const { operand, error } = parseArithmeticTokens(tokens);
    if (error || !operand) {
      return { row: null, error: error || "Invalid expression" };
    }
    return {
      row: {
        id,
        op: "gte",
        left: operand,
        right: { type: "lit", value: 1 },
      },
      error: null,
    };
  }

  const cmpIndex = cmpIndices[0];
  const cmpToken = tokens[cmpIndex];
  const cmpOp = COMPARISON_OPS[cmpToken.value] || "gte";

  const leftTokens = tokens.slice(0, cmpIndex);
  const rightTokens = tokens.slice(cmpIndex + 1);

  if (leftTokens.length === 0) {
    return { row: null, error: `Missing expression before comparison operator '${cmpToken.value}'` };
  }
  if (rightTokens.length === 0) {
    return { row: null, error: `Missing right-hand value or field after '${cmpToken.value}'` };
  }

  const leftResult = parseArithmeticTokens(leftTokens);
  if (leftResult.error || !leftResult.operand) {
    return { row: null, error: leftResult.error || "Invalid left-side expression" };
  }

  const rightResult = parseArithmeticTokens(rightTokens);
  if (rightResult.error || !rightResult.operand) {
    return { row: null, error: rightResult.error || "Invalid right-side expression" };
  }

  return {
    row: {
      id,
      op: cmpOp,
      left: leftResult.operand,
      right: rightResult.operand,
    },
    error: null,
  };
}

export function parseExpressionToFilterRows(
  rawInput: string,
  firstId?: string,
): { rows: AppliedFilterRow[]; join: "and" | "or"; error: string | null } {
  const tokens = tokenize(rawInput);
  if (tokens.length === 0) {
    return { rows: [], join: "and", error: "Empty expression" };
  }

  const joins = tokens.filter((t) => t.type === "AND" || t.type === "OR");
  const joinTypes = new Set(joins.map((t) => t.type));
  if (joinTypes.size > 1) {
    return {
      rows: [],
      join: "and",
      error: "Mix of and/or is not allowed in one expression — use a nested group",
    };
  }
  const join: "and" | "or" = joinTypes.has("OR") ? "or" : "and";

  const clauses: Token[][] = [[]];
  for (const token of tokens) {
    if (token.type === "AND" || token.type === "OR") {
      clauses.push([]);
    } else {
      clauses[clauses.length - 1].push(token);
    }
  }
  if (clauses.some((c) => c.length === 0)) {
    return { rows: [], join, error: "Empty clause next to and/or" };
  }

  const rows: AppliedFilterRow[] = [];
  for (let i = 0; i < clauses.length; i++) {
    const id = i === 0 && firstId ? firstId : `filter-${Date.now()}-${i}`;
    const parsed = parseSingleComparison(clauses[i], id);
    if (parsed.error || !parsed.row) {
      return { rows: [], join, error: parsed.error || "Invalid clause" };
    }
    rows.push(parsed.row);
  }
  return { rows, join, error: null };
}

/**
 * Parses a full text expression into an AppliedFilterRow (LeftOperand CmpOp RightOperand).
 * Compound `and`/`or` expressions return the first clause only; use parseExpressionToFilterRows.
 */
export function parseExpressionToFilterRow(
  rawInput: string,
  id: string = `filter-${Date.now()}`
): { row: AppliedFilterRow | null; error: string | null } {
  const parsed = parseExpressionToFilterRows(rawInput, id);
  if (parsed.error || parsed.rows.length === 0) {
    return { row: null, error: parsed.error };
  }
  return { row: parsed.rows[0], error: null };
}

/**
 * Formats an IrOperand back to human-readable math string with optimal parentheses.
 */
export function formatOperandToString(op: IrOperand, parentPrec: number = 0): string {
  if (!op) return "";
  if (op.type === "col") return op.offset != null ? `${op.name}[${op.offset}]` : op.name;
  if (op.type === "lit") {
    return typeof op.value === "string" ? JSON.stringify(op.value) : String(op.value);
  }
  if (op.type === "formula") {
    const prec = OP_PRECEDENCE[op.op] || 0;
    const leftStr = op.args && op.args[0] ? formatOperandToString(op.args[0], prec) : "";
    const rightStr = op.args && op.args[1] ? formatOperandToString(op.args[1], prec + 1) : "";
    const res = `${leftStr} ${op.op} ${rightStr}`;
    return prec < parentPrec ? `(${res})` : res;
  }
  return "…";
}

const CMP_DISPLAY: Record<ComparisonOp, string> = {
  gte: ">=",
  gt: ">",
  lte: "<=",
  lt: "<",
  eq: "=",
  neq: "!=",
};

/**
 * Formats an AppliedFilterRow back to a complete text expression.
 */
export function formatFilterRowToExpression(row: AppliedFilterRow): string {
  if (row.readOnly) return "Custom Preset Condition";
  const left = formatOperandToString(row.left);
  const cmp = CMP_DISPLAY[row.op] || ">=";
  const right = formatOperandToString(row.right);
  return `${left} ${cmp} ${right}`;
}

function allowedColumnNames(fields: ScreenField[]): Set<string> {
  const allowedNames = new Set<string>();
  for (const f of fields) {
    allowedNames.add(f.name.toLowerCase());
    if (f.prefixed_name) allowedNames.add(f.prefixed_name.toLowerCase());
    if (f.sql_expr) allowedNames.add(f.sql_expr.toLowerCase());
  }
  return allowedNames;
}

function checkOperandColumns(op: IrOperand, allowedNames: Set<string>): string | null {
  if (op.type === "col") {
    const nameLower = op.name.toLowerCase();
    const isKnown =
      allowedNames.size === 0 ||
      allowedNames.has(nameLower) ||
      /^(px|rt|st|fd|ow|fa|kb|mx|tf|rv)\.[a-z0-9_]+$/i.test(op.name);
    if (!isKnown) {
      return `Unknown column "${op.name}"`;
    }
  }
  if (op.type === "formula" && op.args) {
    for (const a of op.args) {
      const err = checkOperandColumns(a, allowedNames);
      if (err) return err;
    }
  }
  return null;
}

/**
 * Validates a raw expression string against the catalog of fields.
 * Expects a boolean filter (comparison / flag → true|false).
 */
export function validateFilterExpression(
  input: string,
  fields: ScreenField[] = []
): { valid: boolean; error?: string; row?: AppliedFilterRow } {
  const trimmed = input.trim();
  if (!trimmed) {
    return { valid: false, error: "Expression is empty" };
  }

  const parsed = parseExpressionToFilterRows(trimmed);
  if (parsed.error || parsed.rows.length === 0) {
    return { valid: false, error: parsed.error || "Invalid syntax" };
  }

  const allowedNames = allowedColumnNames(fields);

  for (const row of parsed.rows) {
    const leftErr = checkOperandColumns(row.left, allowedNames);
    if (leftErr) return { valid: false, error: leftErr, row };
    const rightErr = checkOperandColumns(row.right, allowedNames);
    if (rightErr) return { valid: false, error: rightErr, row };
  }

  return { valid: true, row: parsed.rows[0] };
}

/**
 * Validates a numeric / sort expression (cols, lits, + − * /).
 * Does not require a comparison — returns a number operand, not true|false.
 * `fields` may include measure aliases (screen_1, screens_hit, …).
 */
export function validateArithmeticExpression(
  input: string,
  fields: ScreenField[] = [],
): { valid: boolean; error?: string; operand?: IrOperand | null } {
  const trimmed = input.trim();
  if (!trimmed) {
    return { valid: false, error: "Expression is empty" };
  }

  const tokens = tokenize(trimmed);
  if (tokens.some((t) => t.type === "CMP" || t.type === "AND" || t.type === "OR")) {
    return {
      valid: false,
      error: "Numeric expressions use + − * / only (no comparisons / and / or)",
    };
  }

  const { operand, error } = parseArithmeticTokens(tokens);
  if (error || !operand) {
    return { valid: false, error: error || "Invalid arithmetic expression" };
  }

  const colErr = checkOperandColumns(operand, allowedColumnNames(fields));
  if (colErr) return { valid: false, error: colErr, operand };

  return { valid: true, operand };
}

export type ValueCompletionContext = {
  fieldName: string;
  prefix: string;
  replaceFrom: number;
};

function indexInsideQuotes(text: string, index: number): boolean {
  let inQuote: '"' | "'" | null = null;
  for (let i = 0; i < index && i < text.length; i++) {
    const ch = text[i];
    if (inQuote) {
      if (ch === "\\") {
        i++;
        continue;
      }
      if (ch === inQuote) inQuote = null;
    } else if (ch === '"' || ch === "'") {
      inQuote = ch;
    }
  }
  return inQuote !== null;
}

/** After the last `field =` / `field ==` before the caret (quoted or bare value). */
export function valueCompletionContext(
  text: string,
  caret: number,
): ValueCompletionContext | null {
  const before = text.slice(0, caret);
  const re = /([A-Za-z_][A-Za-z0-9_]*)\s*(!=|<>|==|=)\s*/g;
  let last: { fieldName: string; valueStart: number } | null = null;
  let m: RegExpExecArray | null;
  while ((m = re.exec(before)) !== null) {
    if (indexInsideQuotes(before, m.index)) continue;
    last = { fieldName: m[1], valueStart: m.index + m[0].length };
  }
  if (!last) return null;
  const rawVal = before.slice(last.valueStart);
  if (/^[0-9.]/.test(rawVal)) return null;
  const quote = rawVal.startsWith('"') || rawVal.startsWith("'") ? rawVal[0] : "";
  const prefix = quote ? rawVal.slice(1) : rawVal;
  if (!quote && /[\s(),]/.test(prefix)) return null;
  return {
    fieldName: last.fieldName,
    prefix,
    replaceFrom: last.valueStart,
  };
}

/** True when inserting another field/term needs `and`/`or` (or arithmetic) before it. */
export function expressionNeedsJoin(before: string): boolean {
  const tail = before.trimEnd();
  if (!tail) return false;
  if (/\b(and|or|not)$/i.test(tail)) return false;
  if (/[<>=+\-*/()%]$/.test(tail)) return false;
  return /[A-Za-z0-9_)\]%"']$/.test(tail);
}

export function isStringishFieldType(colType: string | undefined): boolean {
  if (!colType) return false;
  const t = colType.toLowerCase();
  return t.includes("string") || t.startsWith("enum");
}
