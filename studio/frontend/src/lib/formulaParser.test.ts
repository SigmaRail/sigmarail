import { describe, it, expect } from "vitest";
import {
  tokenize,
  parseExpressionToFilterRow,
  parseExpressionToFilterRows,
  formatFilterRowToExpression,
  validateFilterExpression,
  valueCompletionContext,
  expressionNeedsJoin,
} from "./formulaParser";

describe("bar offset tokenizer", () => {
  it("parses [-1] suffix on column", () => {
    const tokens = tokenize("px.close[-1]");
    expect(tokens).toHaveLength(1);
    expect(tokens[0].type).toBe("IDENT");
    expect(tokens[0].value).toBe("px.close");
    expect(tokens[0].offset).toBe(-1);
  });

  it("parses [+3] suffix on column", () => {
    const tokens = tokenize("px.high[+3]");
    expect(tokens[0].offset).toBe(3);
  });

  it("parses offset within arithmetic expression", () => {
    const tokens = tokenize("px.close[-1] > px.high[-1]");
    expect(tokens).toHaveLength(3);
    expect(tokens[0].offset).toBe(-1);
    expect(tokens[2].offset).toBe(-1);
  });

  it("parses offset with multiplication", () => {
    const tokens = tokenize("px.close >= px.high_52w * 0.90");
    expect(tokens[0].offset).toBeUndefined();
  });

  it("no offset when brackets absent", () => {
    const tokens = tokenize("px.close > px.sma50d");
    expect(tokens[0].offset).toBeUndefined();
    expect(tokens[2].offset).toBeUndefined();
  });

  it("round-trips expression with offset", () => {
    const expr = "px.close[-1] < px.lower_bb[-1]";
    const { row, error } = parseExpressionToFilterRow(expr);
    expect(error).toBeNull();
    expect(row).not.toBeNull();
    expect(row!.left.type).toBe("col");
    expect((row!.left as any).offset).toBe(-1);
    expect(row!.right.type).toBe("col");
    expect((row!.right as any).offset).toBe(-1);
    // formatOperandToString strips the px. prefix (AST stores bare column name)
    const formatted = formatFilterRowToExpression(row!);
    expect(formatted).toBe("close[-1] < lower_bb[-1]");
  });
});

describe("validateFilterExpression with offset", () => {
  const fields: any[] = [
    { name: "close", prefixed_name: "px.close" },
    { name: "high", prefixed_name: "px.high" },
    { name: "high_52w", prefixed_name: "px.high_52w" },
  ];

  it("accepts valid offset expression", () => {
    const result = validateFilterExpression("px.close[-1] > px.high[-1]", fields);
    expect(result.valid).toBe(true);
  });

  it("rejects unknown column with offset", () => {
    const result = validateFilterExpression("px.foo[-1] > 0", fields);
    expect(result.valid).toBe(false);
  });
});

describe("quoted string literals", () => {
  const fields: any[] = [{ name: "exchange", prefixed_name: "px.exchange", type: "LowCardinality(String)" }];

  it("parses industry != \"Biotechnology\" as neq", () => {
    const { row, error } = parseExpressionToFilterRow('industry != "Biotechnology"');
    expect(error).toBeNull();
    expect(row?.op).toBe("neq");
    expect(row?.right).toEqual({ type: "lit", value: "Biotechnology" });
    expect(formatFilterRowToExpression(row!)).toBe('industry != "Biotechnology"');
  });

  it("parses exchange = \"NYSE\" as a string literal", () => {
    const { row, error } = parseExpressionToFilterRow('exchange = "NYSE"');
    expect(error).toBeNull();
    expect(row?.op).toBe("eq");
    expect(row?.right).toEqual({ type: "lit", value: "NYSE" });
    expect(validateFilterExpression('exchange = "NYSE"', fields).valid).toBe(true);
  });

  it("detects value completion after =", () => {
    const typed = "exchange=ny";
    const ctx = valueCompletionContext(typed, typed.length);
    expect(ctx).toEqual({ fieldName: "exchange", prefix: "ny", replaceFrom: typed.length - 2 });
  });

  it("detects value completion with opening quote", () => {
    const text = 'sector = "Tech';
    const ctx = valueCompletionContext(text, text.length);
    expect(ctx?.fieldName).toBe("sector");
    expect(ctx?.prefix).toBe("Tech");
  });

  it("completes the last field= clause when the field is repeated", () => {
    const text = 'exchange="NYSE" or exchange=n';
    const ctx = valueCompletionContext(text, text.length);
    expect(ctx?.fieldName).toBe("exchange");
    expect(ctx?.prefix).toBe("n");
  });
});

describe("repeated field / and-or expressions", () => {
  const fields: any[] = [
    { name: "exchange", prefixed_name: "px.exchange", type: "LowCardinality(String)" },
    { name: "sector", prefixed_name: "px.sector", type: "String" },
  ];

  it("parses exchange = \"NYSE\" or exchange = \"NASDAQ\" as two rows", () => {
    const parsed = parseExpressionToFilterRows(
      'exchange = "NYSE" or exchange = "NASDAQ"',
    );
    expect(parsed.error).toBeNull();
    expect(parsed.join).toBe("or");
    expect(parsed.rows).toHaveLength(2);
    expect(parsed.rows[0]?.right).toEqual({ type: "lit", value: "NYSE" });
    expect(parsed.rows[1]?.right).toEqual({ type: "lit", value: "NASDAQ" });
    expect(validateFilterExpression('exchange = "NYSE" or exchange = "NASDAQ"', fields).valid).toBe(true);
  });

  it("joins a second field insert after a quoted value", () => {
    expect(expressionNeedsJoin('exchange="NYSE"')).toBe(true);
    expect(expressionNeedsJoin('exchange="NYSE" or')).toBe(false);
    expect(expressionNeedsJoin("rs_rating >= 80")).toBe(true);
  });
});