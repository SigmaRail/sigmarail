import type { FilterCondition, FilterNode, FilterTree } from "../components/strategy/StrategyDocument";
import { isFilterGroup, isFilterNot } from "../components/strategy/StrategyDocument";
import type { IrOperand, ScreenField } from "../types";

const OPERATOR_WORDS: Record<FilterCondition["op"], string> = {
  gt: "is above",
  gte: "is at least",
  lt: "is below",
  lte: "is at most",
  eq: "equals",
  neq: "is not",
};

const NAMESPACE_LABELS: Record<string, string> = {
  acct: "account",
  cand: "candidate",
  hold: "holding",
  pos: "position",
  pyr: "pyramid",
  regime: "market regime",
};

function fieldFor(name: string, fields: ScreenField[]): ScreenField | undefined {
  return fields.find((field) =>
    [field.name, field.prefixed_name].some((candidate) => candidate?.toLowerCase() === name.toLowerCase()),
  );
}

function humanizeName(name: string): string {
  const prefixes: Record<string, string> = {
    arq: "Quarterly",
    ary: "Annual",
    mrt: "Most recent year",
    mrq: "Most recent quarter",
  };
  const match = /^(arq|ary|mrt|mrq)_(.+)$/i.exec(name);
  const prefix = match ? `${prefixes[match[1]!.toLowerCase()]} ` : "";
  const body = (match ? match[2]! : name)
    .replace(/_/g, " ")
    .replace(/\b3y\b/gi, "3-year")
    .replace(/\bqoq\b/gi, "quarter over quarter")
    .replace(/\byoy\b/gi, "year over year")
    .replace(/\bfy\b/gi, "fiscal year");
  return `${prefix}${body}`.replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function fieldLabel(name: string, fields: ScreenField[]): string {
  return fieldFor(name, fields)?.label || humanizeName(name);
}

function isBooleanField(name: string, fields: ScreenField[]): boolean {
  const field = fieldFor(name, fields);
  return field?.type === "bool" || /^screen_/i.test(name) || /(_flag|acceleration)/i.test(name);
}

function isPercentField(name: string): boolean {
  return /(growth|pct|percent|margin|return|yield|surprise)/i.test(name);
}

function displayLiteral(value: unknown, fieldName: string, fields: ScreenField[]): string {
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (isBooleanField(fieldName, fields) && (value === 0 || value === 1)) {
      return value === 1 ? "true" : "false";
    }
    if (isPercentField(fieldName) && value > -1 && value < 1) {
      return `${Number((value * 100).toFixed(1))}%`;
    }
    return new Intl.NumberFormat("en-US", { maximumFractionDigits: 3 }).format(value);
  }
  return String(value ?? "—");
}

function operandText(operand: unknown, fields: ScreenField[]): string {
  if (typeof operand === "string") return fieldLabel(operand, fields);
  if (operand == null || typeof operand !== "object") return String(operand ?? "—");

  const node = operand as Record<string, unknown>;
  if (node.type === "col" && typeof node.name === "string") return fieldLabel(node.name, fields);
  if (node.type === "ref" && typeof node.field === "string") {
    const namespace = typeof node.ns === "string" ? NAMESPACE_LABELS[node.ns] ?? node.ns : "";
    const label = fieldLabel(node.field, fields);
    return namespace ? `${namespace} ${label}` : label;
  }
  if (node.type === "pos" && typeof node.field === "string") return `position ${humanizeName(node.field)}`;
  if (node.type === "lit") return displayLiteral(node.value, "", fields);
  if (node.type === "formula" && Array.isArray(node.args)) {
    const operator = String(node.op ?? "?");
    const args = node.args.map((arg) => operandText(arg, fields));
    if (args.length === 2) return `${args[0]} ${operator} ${args[1]}`;
    return args.join(` ${operator} `);
  }
  if ((node.type === "min" || node.type === "max") && Array.isArray(node.args)) {
    return `${node.type} of ${node.args.map((arg) => operandText(arg, fields)).join(", ")}`;
  }
  if (node.type === "abs") return `absolute value of ${operandText(node.arg, fields)}`;
  if (node.type === "clamp") {
    return `${operandText(node.value, fields)} clamped from ${operandText(node.min, fields)} to ${operandText(node.max, fields)}`;
  }

  return "Expression";
}

function conditionText(condition: FilterCondition, fields: ScreenField[]): string {
  const left = typeof condition.left === "string"
    ? condition.left
    : condition.left && typeof condition.left === "object" && "type" in condition.left && condition.left.type === "col"
      ? String((condition.left as Extract<IrOperand, { type: "col" }>).name)
      : "";
  const leftText = operandText(condition.left, fields);
  const rawRight = condition.right && typeof condition.right === "object" && "type" in condition.right
    ? condition.right as IrOperand
    : condition.right;
  const rightText = rawRight && typeof rawRight === "object" && "type" in rawRight
    ? operandText(rawRight, fields)
    : displayLiteral(rawRight, left, fields);

  if (condition.op === "eq" && isBooleanField(left, fields) && rightText === "true") return `${leftText} is active`;
  if (condition.op === "eq" && isBooleanField(left, fields) && rightText === "false") return `${leftText} is inactive`;
  return `${leftText} ${OPERATOR_WORDS[condition.op]} ${rightText}`;
}

function filterNodeText(node: FilterNode, fields: ScreenField[]): string {
  if (isFilterNot(node)) return `not (${filterNodeText(node.item, fields)})`;
  if (isFilterGroup(node)) {
    const parts = node.conditions.map((condition) => filterNodeText(condition, fields));
    const joiner = node.logic === "or" ? " or " : " and ";
    const joined = parts.join(joiner);
    return node.logic === "or" && parts.length > 1 ? `(${joined})` : joined;
  }
  return conditionText(node, fields);
}

export function summarizeMeasureFilters(filters: FilterTree[] | undefined, fields: ScreenField[]): string {
  return (filters ?? [])
    .map((filter) => filterNodeText(filter, fields))
    .filter(Boolean)
    .join(" and ");
}

export function summarizeMeasureExpression(expression: Record<string, unknown> | null | undefined, fields: ScreenField[]): string {
  return expression ? operandText(expression, fields) : "";
}
