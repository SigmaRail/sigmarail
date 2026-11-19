import { useId, useState } from "react";
import type { ScreenField } from "../../types";
import type { OperandAst } from "../../lib/rulesAst";
import type { PcmBinding, PositionBinding } from "../../lib/slotFieldCatalog";
import { pcmNamespaces } from "../../lib/slotFieldCatalog";
import { boolText, defaultBoolNode, defaultOperand, formulaText } from "../../lib/rulesAst";
import { cn } from "../../lib/utils";
import { Button } from "@sb/webapp-core/components/ui/button";
import { Input } from "@sb/webapp-core/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@sb/webapp-core/components/ui/select";

/**
 * Pill-based AST editors for C-VERA-EXPR operands and BoolExpr conditions.
 * The AST stays authoritative — pills render it, buttons/selects mutate it,
 * unknown/domain nodes degrade to read-only chips instead of silently
 * disappearing (edit those via the parent JSON view).
 */

type BoolNode = Record<string, unknown>;

const CMP_OPS = ["gt", "gte", "lt", "lte", "eq", "neq"] as const;
const CMP_LABELS: Record<string, string> = {
  gt: ">",
  gte: "≥",
  lt: "<",
  lte: "≤",
  eq: "=",
  neq: "≠",
};
const OPERAND_TYPES = [
  "col",
  "pos",
  "ref",
  "lit",
  "formula",
  "min",
  "max",
  "abs",
  "clamp",
  "cond",
] as const;
const FORMULA_OPS = ["+", "-", "*", "/"] as const;

const pillCls =
  "inline-flex items-center gap-1 rounded-full border border-line bg-surface-raised px-2 py-0.5 font-mono text-[10px] text-ink";
/** Compound nodes (formula/min/max/abs/clamp/cond, cmp rows) get a flat box —
 *  nested rounded-full ovals are unreadable as containers. */
const groupCls =
  "inline-flex items-center gap-1 rounded border border-line/70 bg-surface-raised/60 px-1.5 py-0.5 font-mono text-[10px] text-ink";
const pillInputCls = "h-6 rounded-md px-1.5 py-0 font-mono text-[10px]";

function InlineSelect({
  value,
  onValueChange,
  options,
  label,
  title,
  className,
}: {
  value: string;
  onValueChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
  label: string;
  title?: string;
  className?: string;
}) {
  const safeValue = value || "__none";
  return (
    <Select value={safeValue} onValueChange={(next) => next !== "__none" && onValueChange(next)}>
      <SelectTrigger
        aria-label={label}
        title={title}
        className={cn("h-6 w-auto min-w-9 gap-1 px-1.5 py-0 text-[10px]", className)}
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent align="start" className="min-w-0">
        {safeValue === "__none" ? <SelectItem value="__none" className="py-1 pl-7 pr-2 text-[10px]">?</SelectItem> : null}
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value} className="py-1 pl-7 pr-2 text-[10px]">
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

const tinyBtnCls = "h-6 min-w-6 px-1 py-0 text-[9px]";

function isCmpNode(n: BoolNode): boolean {
  return CMP_OPS.includes(n.type as (typeof CMP_OPS)[number]);
}

function OperandTypeSwitch({
  node,
  onChange,
}: {
  node: OperandAst;
  onChange: (n: OperandAst) => void;
}) {
  const current = OPERAND_TYPES.includes(node?.type as never) ? node.type : "";
  return (
    <InlineSelect
      value={current}
      onValueChange={(value) => onChange(defaultOperand(value))}
      options={OPERAND_TYPES.map((type) => ({ value: type, label: type }))}
      className="font-mono"
      title="Operand kind"
      label="Operand kind"
    />
  );
}

function ColInput({
  name,
  fields,
  onChange,
}: {
  name: string;
  fields: ScreenField[];
  onChange: (name: string) => void;
}) {
  const listId = useId();
  const known = fields.some(
    (f) => f.name === name || f.prefixed_name === name,
  );
  return (
    <>
      <Input
        type="text"
        list={listId}
        value={name}
        onChange={(e) => onChange(e.target.value)}
        className={cn(pillInputCls, "w-36", !known && name && "border-amber-500/50")}
        title={
          known
            ? "Column"
            : `${name || "column"} — not in the field catalog (position flags and runtime cols are still valid)`
        }
        aria-label="column name"
        spellCheck={false}
      />
      <datalist id={listId}>
        {fields.map((f) => (
          <option key={f.name} value={f.name}>
            {f.label}
          </option>
        ))}
      </datalist>
    </>
  );
}

/** Position-binding picker: `pos` operand's field, scoped to the eval context. */
function PosInput({
  field,
  bindings,
  context,
  onChange,
}: {
  field: string;
  bindings: PositionBinding[];
  context?: "init" | "live";
  onChange: (field: string) => void;
}) {
  const listId = useId();
  const scoped = context
    ? bindings.filter((b) => b.contexts.includes(context))
    : bindings;
  const known = scoped.some((b) => b.field === field);
  const doc = scoped.find((b) => b.field === field)?.description;
  return (
    <>
      <Input
        type="text"
        list={listId}
        value={field}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          pillInputCls,
          "w-28",
          !known && field && "border-amber-500/50",
        )}
        title={
          doc ??
          (field
            ? `${field} — not in the ${context ?? "position"} binding registry (set_flag names are still valid)`
            : "position field")
        }
        aria-label="position field"
        spellCheck={false}
      />
      <datalist id={listId}>
        {scoped.map((b) => (
          <option key={b.field} value={b.field}>
            {b.label} — {b.description}
          </option>
        ))}
      </datalist>
    </>
  );
}

/** Namespaced binding picker: `ref` operand's ns + field (PCM decision-unit context). */
function RefInput({
  ns,
  field,
  bindings,
  onChange,
}: {
  ns: string;
  field: string;
  bindings: PcmBinding[];
  onChange: (next: { ns: string; field: string }) => void;
}) {
  const listId = useId();
  const namespaces = pcmNamespaces(bindings);
  const scoped = bindings.filter((b) => b.ns === ns);
  const known = scoped.some((b) => b.field === field);
  const doc = scoped.find((b) => b.field === field)?.description;
  const nsKnown = namespaces.includes(ns);
  return (
    <>
      <InlineSelect
        value={ns}
        onValueChange={(value) => onChange({ ns: value, field })}
        options={[
          ...(!nsKnown ? [{ value: ns, label: ns }] : []),
          ...namespaces.map((namespace) => ({ value: namespace, label: namespace })),
        ]}
        title="Binding namespace (cand/hold/acct/pyr/regime inside PCM rules)"
        label="Binding namespace"
      />
      <span className="text-ink-faint">.</span>
      <Input
        type="text"
        list={listId}
        value={field}
        onChange={(e) => onChange({ ns, field: e.target.value })}
        className={cn(
          pillInputCls,
          "w-28",
          !known && field && "border-amber-500/50",
        )}
        title={
          doc ??
          (field
            ? `${field} — not in the ${ns} binding registry (set_flag names are still valid)`
            : `${ns} field`)
        }
        aria-label="binding field"
        spellCheck={false}
      />
      <datalist id={listId}>
        {scoped.map((b) => (
          <option key={b.field} value={b.field}>
            {b.label} — {b.description}
          </option>
        ))}
      </datalist>
    </>
  );
}

function LitInput({
  node,
  onChange,
}: {
  node: Extract<OperandAst, { type: "lit" }>;
  onChange: (n: OperandAst) => void;
}) {
  const v = node.value;
  if (typeof v === "boolean") {
    return (
      <InlineSelect
        value={String(v)}
        onValueChange={(value) => onChange({ ...node, value: value === "true" })}
        options={[{ value: "true", label: "true" }, { value: "false", label: "false" }]}
        label="literal value"
      />
    );
  }
  if (typeof v === "number") {
    return (
      <Input
        type="number"
        step="any"
        value={v}
        onChange={(e) =>
          onChange({ ...node, value: Number(e.target.value) })
        }
        className={cn(pillInputCls, "w-16")}
        aria-label="literal value"
      />
    );
  }
  return (
    <Input
      type="text"
      value={String(v ?? "")}
      onChange={(e) => onChange({ ...node, value: e.target.value })}
      className={cn(pillInputCls, "w-24")}
      aria-label="literal value"
      spellCheck={false}
    />
  );
}

/** Recursive operand editor — each node is a pill row of editable fragments. */
export function OperandEditor({
  value,
  onChange,
  fields,
  posBindings,
  posContext,
  pcmBindings,
  showTypeSwitch = true,
}: {
  value: OperandAst | null | undefined;
  onChange: (n: OperandAst) => void;
  fields?: ScreenField[];
  posBindings?: PositionBinding[];
  posContext?: "init" | "live";
  /** PCM `ref` namespaces (cand/hold/acct/pyr/regime) — populated on the PCM card. */
  pcmBindings?: PcmBinding[];
  showTypeSwitch?: boolean;
}) {
  const node = value as OperandAst | null | undefined;
  if (!node || typeof node !== "object") {
    return (
      <span className="inline-flex items-center gap-1">
        <span className={cn(pillCls, "text-ink-faint")}>∅</span>
        {showTypeSwitch ? (
          <InlineSelect
            value=""
            onValueChange={(type) => onChange(defaultOperand(type))}
            options={OPERAND_TYPES.map((type) => ({ value: type, label: type }))}
            label="Operand kind"
          />
        ) : null}
      </span>
    );
  }

  const sw = showTypeSwitch ? (
    <OperandTypeSwitch node={node} onChange={onChange} />
  ) : null;

  switch (node.type) {
    case "col":
      return (
        <span className={pillCls}>
          {sw}
          <ColInput
            name={node.name}
            fields={fields ?? []}
            onChange={(name) => onChange({ ...node, name })}
          />
        </span>
      );
    case "pos":
      return (
        <span className={cn(pillCls, "border-accent/40")} title="Position binding — resolves a field of the open position at eval time">
          {sw}
          <span className="text-ink-faint">pos.</span>
          <PosInput
            field={node.field}
            bindings={posBindings ?? []}
            context={posContext}
            onChange={(field) => onChange({ ...node, field })}
          />
        </span>
      );
    case "ref":
      return (
        <span className={cn(pillCls, "border-accent/40")} title="Runtime binding — resolves a namespaced field of the slot's decision context at eval time">
          {sw}
          <RefInput
            ns={node.ns}
            field={node.field}
            bindings={
              node.ns === "pos"
                ? (posBindings ?? []).map((b) => ({
                    ns: "pos",
                    field: b.field,
                    label: b.label,
                    description: b.description,
                    type: b.type,
                  }))
                : (pcmBindings ?? [])
            }
            onChange={({ ns, field }) => onChange({ ...node, ns, field })}
          />
        </span>
      );
    case "lit":
      return (
        <span className={pillCls}>
          {sw}
          <LitInput node={node} onChange={onChange} />
        </span>
      );
    case "formula": {
      const args = node.args ?? [];
      return (
        <span className={cn(groupCls, "flex-wrap")}>
          {sw}
          {args.map((a, i) => (
            <span key={i} className="inline-flex items-center gap-0.5">
              {i > 0 ? (
                <InlineSelect
                  value={node.op}
                  onValueChange={(operator) =>
                    onChange({
                      ...node,
                      op: operator as "+" | "-" | "*" | "/",
                    })
                  }
                  options={FORMULA_OPS.map((operator) => ({ value: operator, label: operator }))}
                  label="Operator"
                />
              ) : null}
              <OperandEditor
                value={a}
                onChange={(n) =>
                  onChange({ ...node, args: args.map((x, xi) => (xi === i ? n : x)) })
                }
                fields={fields} posBindings={posBindings} posContext={posContext} pcmBindings={pcmBindings}
              />
              {args.length > 2 ? (
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  className={tinyBtnCls}
                  title="Remove operand"
                  aria-label="Remove operand"
                  onClick={() =>
                    onChange({ ...node, args: args.filter((_, xi) => xi !== i) })
                  }
                >
                  ✕
                </Button>
              ) : null}
            </span>
          ))}
          <Button
            type="button"
            variant="outline"
            size="icon"
            className={tinyBtnCls}
            title="Add operand"
            aria-label="Add operand"
            onClick={() =>
              onChange({ ...node, args: [...args, { type: "lit", value: 1 }] })
            }
          >
            +
          </Button>
        </span>
      );
    }
    case "min":
    case "max": {
      const args = node.args ?? [];
      return (
        <span className={cn(groupCls, "flex-wrap")}>
          {sw}
          <span className="font-semibold">{node.type}(</span>
          {args.map((a, i) => (
            <span key={i} className="inline-flex items-center gap-0.5">
              {i > 0 ? <span className="text-ink-faint">,</span> : null}
              <OperandEditor
                value={a}
                onChange={(n) =>
                  onChange({ ...node, args: args.map((x, xi) => (xi === i ? n : x)) })
                }
                fields={fields} posBindings={posBindings} posContext={posContext} pcmBindings={pcmBindings}
              />
              {args.length > 1 ? (
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  className={tinyBtnCls}
                  title="Remove argument"
                  aria-label="Remove argument"
                  onClick={() =>
                    onChange({ ...node, args: args.filter((_, xi) => xi !== i) })
                  }
                >
                  ✕
                </Button>
              ) : null}
            </span>
          ))}
          <Button
            type="button"
            variant="outline"
            size="icon"
            className={tinyBtnCls}
            title="Add argument"
            aria-label="Add argument"
            onClick={() =>
              onChange({ ...node, args: [...args, { type: "lit", value: 0 }] })
            }
          >
            +
          </Button>
          <span className="font-semibold">)</span>
        </span>
      );
    }
    case "abs":
      return (
        <span className={groupCls}>
          {sw}
          <span className="font-semibold">abs(</span>
          <OperandEditor
            value={node.arg}
            onChange={(arg) => onChange({ ...node, arg })}
            fields={fields} posBindings={posBindings} posContext={posContext} pcmBindings={pcmBindings}
          />
          <span className="font-semibold">)</span>
        </span>
      );
    case "clamp":
      return (
        <span className={cn(groupCls, "flex-wrap")}>
          {sw}
          <span className="font-semibold">clamp(</span>
          <OperandEditor
            value={node.value}
            onChange={(v) => onChange({ ...node, value: v })}
            fields={fields} posBindings={posBindings} posContext={posContext} pcmBindings={pcmBindings}
          />
          <span className="text-ink-faint">,</span>
          <OperandEditor
            value={node.min}
            onChange={(v) => onChange({ ...node, min: v })}
            fields={fields} posBindings={posBindings} posContext={posContext} pcmBindings={pcmBindings}
          />
          <span className="text-ink-faint">,</span>
          <OperandEditor
            value={node.max}
            onChange={(v) => onChange({ ...node, max: v })}
            fields={fields} posBindings={posBindings} posContext={posContext} pcmBindings={pcmBindings}
          />
          <span className="font-semibold">)</span>
        </span>
      );
    case "cond":
      return (
        <span className="inline-flex flex-col gap-1 rounded border border-line/70 bg-surface-raised/60 p-1.5">
          <span className={cn(groupCls, "self-start flex-wrap")}>
            {sw}
            <span className="font-semibold">cond</span>
            <span className="text-ink-faint">then</span>
            <OperandEditor
              value={node.then}
              onChange={(v) => onChange({ ...node, then: v })}
              fields={fields} posBindings={posBindings} posContext={posContext} pcmBindings={pcmBindings}
            />
            <span className="text-ink-faint">else</span>
            <OperandEditor
              value={node.otherwise}
              onChange={(v) => onChange({ ...node, otherwise: v })}
              fields={fields} posBindings={posBindings} posContext={posContext} pcmBindings={pcmBindings}
            />
          </span>
          <span className="pl-3 border-l-2 border-line/60">
            <BoolExprEditor
              value={node.when as BoolNode}
              onChange={(w) => onChange({ ...node, when: w })}
              fields={fields} posBindings={posBindings} posContext={posContext} pcmBindings={pcmBindings}
            />
          </span>
        </span>
      );
    default:
      // Unknown operand node — render verbatim; editable via parent JSON view.
      return (
        <span className="inline-flex items-center gap-1">
          <span
            className={cn(pillCls, "border-amber-500/50 text-amber-300")}
            title={`Unsupported operand node "${String((node as { type?: unknown }).type)}" — edit via the JSON view`}
          >
            {formulaText(node)}
          </span>
          {sw}
        </span>
      );
  }
}

/**
 * Recursive BoolExpr editor: comparison nodes render as
 * `[operand] [op] [operand]` pills; all/any render as bordered groups with
 * add/remove; not renders as a `¬` prefix; domain/unknown nodes render as
 * read-only chips (still preserved in the AST).
 */
export function BoolExprEditor({
  value,
  onChange,
  fields,
  posBindings,
  posContext,
  pcmBindings,
  onRemove,
}: {
  value: BoolNode | null | undefined;
  onChange: (n: BoolNode) => void;
  fields?: ScreenField[];
  posBindings?: PositionBinding[];
  posContext?: "init" | "live";
  pcmBindings?: PcmBinding[];
  onRemove?: () => void;
}) {
  const node = (value ?? null) as BoolNode | null;
  // PCM context seeds `ref cand.*` (not `pos.*`) for new comparisons.
  const cmpDefault = (): Record<string, unknown> =>
    pcmBindings?.length
      ? {
          type: "gte",
          left: { type: "ref", ns: "cand", field: "price" },
          right: { type: "lit", value: 0 },
        }
      : defaultBoolNode("gte");

  if (!node || typeof node !== "object" || typeof node.type !== "string") {
    return (
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="h-6 rounded-full border-dashed border-accent/60 bg-accent/5 px-2.5 py-0.5 text-[10px] font-semibold text-accent hover:bg-accent/15"
        onClick={() => onChange(cmpDefault())}
      >
        + condition
      </Button>
    );
  }

  const typeSwitch = (
    <InlineSelect
      value={isCmpNode(node) ? "cmp" : (node.type as string)}
      onValueChange={(t) => {
        if (t === "cmp") {
          onChange({
            type: "gte",
            left: pcmBindings?.length
              ? { type: "ref", ns: "cand", field: "price" }
              : { type: "pos", field: "r" },
            right: { type: "lit", value: 0 },
          });
        } else if (t === "all" || t === "any") {
          onChange({ type: t, items: [node] });
        } else if (t === "not") {
          onChange({ type: "not", item: node });
        }
      }}
      title="Node kind"
      label="Condition kind"
      options={[
        ...(!isCmpNode(node) && node.type !== "all" && node.type !== "any" && node.type !== "not"
          ? [{ value: node.type as string, label: node.type as string }]
          : []),
        { value: "cmp", label: "cmp" },
        { value: "all", label: "all" },
        { value: "any", label: "any" },
        { value: "not", label: "not" },
      ]}
    />
  );

  const removeBtn = onRemove ? (
    <Button
      type="button"
      variant="outline"
      size="icon"
      className={tinyBtnCls}
      title="Remove condition"
      aria-label="Remove condition"
      onClick={onRemove}
    >
      ✕
    </Button>
  ) : null;

  if (isCmpNode(node)) {
    return (
      <span className={cn(groupCls, "flex-wrap")}>
        {typeSwitch}
        <OperandEditor
          value={node.left as OperandAst}
          onChange={(left) => onChange({ ...node, left })}
          fields={fields} posBindings={posBindings} posContext={posContext} pcmBindings={pcmBindings}
        />
        <InlineSelect
          value={node.type as string}
          onValueChange={(operator) => onChange({ ...node, type: operator })}
          options={CMP_OPS.map((operator) => ({ value: operator, label: CMP_LABELS[operator] }))}
          label="Comparison operator"
        />
        <OperandEditor
          value={node.right as OperandAst}
          onChange={(right) => onChange({ ...node, right })}
          fields={fields} posBindings={posBindings} posContext={posContext} pcmBindings={pcmBindings}
        />
        {removeBtn}
      </span>
    );
  }

  if (node.type === "all" || node.type === "any") {
    const items = (node.items as BoolNode[] | undefined) ?? [];
    return (
      <span className="inline-flex flex-col gap-1 rounded border border-line/70 bg-surface-raised/40 p-1.5">
        <span className="inline-flex items-center gap-1">
          {typeSwitch}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className={cn(
              "h-6 rounded-full px-2 py-0 text-[10px] font-mono font-semibold uppercase",
              node.type === "all" ? "text-accent-ink" : "text-info",
            )}
            title="Toggle conjunction"
            onClick={() =>
              onChange({ type: node.type === "all" ? "any" : "all", items })
            }
          >
            {node.type === "all" ? "all" : "any"}
          </Button>
          <span className="text-[9px] text-ink-faint">
            {node.type === "all" ? "every condition must hold" : "at least one must hold"}
          </span>
          {removeBtn}
        </span>
        <span className="flex flex-col gap-1 pl-3 border-l-2 border-line/60">
          {items.map((item, i) => (
            <BoolExprEditor
              key={i}
              value={item}
              fields={fields} posBindings={posBindings} posContext={posContext} pcmBindings={pcmBindings}
              onChange={(n) =>
                onChange({
                  ...node,
                  items: items.map((x, xi) => (xi === i ? n : x)),
                })
              }
              onRemove={() =>
                onChange({ ...node, items: items.filter((_, xi) => xi !== i) })
              }
            />
          ))}
          <span className="inline-flex gap-1">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className={tinyBtnCls}
              onClick={() =>
                onChange({ ...node, items: [...items, cmpDefault()] })
              }
            >
              + condition
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className={tinyBtnCls}
              title="Add nested group"
              onClick={() =>
                onChange({ ...node, items: [...items, defaultBoolNode("any")] })
              }
            >
              + group
            </Button>
          </span>
        </span>
      </span>
    );
  }

  if (node.type === "not") {
    return (
      <span className="inline-flex items-start gap-1">
        <span className={pillCls}>
          {typeSwitch}
          <span className="font-semibold">¬</span>
        </span>
        <BoolExprEditor
          value={node.item as BoolNode}
          onChange={(item) => onChange({ ...node, item })}
          fields={fields} posBindings={posBindings} posContext={posContext} pcmBindings={pcmBindings}
        />
        {removeBtn}
      </span>
    );
  }

  // Domain/unknown node (signal, regime, col_gte shorthand …) — keep verbatim.
  return (
    <span className="inline-flex items-center gap-1">
      <span
        className={cn(pillCls, "border-amber-500/50")}
        title={`"${node.type}" is a domain predicate — edit via the JSON view`}
      >
        {typeSwitch}
        <span className="font-mono">{boolText(node)}</span>
      </span>
      {removeBtn}
    </span>
  );
}

/**
 * Compact-then-edit operand display: renders `formulaText` as a single
 * monospace expression by default (deeply nested generated ASTs stay readable),
 * with an "edit" toggle that opens the full pill editor. Use for materialized
 * expressions (init_stop, size_expr) where the pill tree is too tall to scan.
 */
export function EditableOperand({
  value,
  onChange,
  fields,
  posBindings,
  posContext,
  pcmBindings,
}: {
  value: OperandAst | null | undefined;
  onChange: (n: OperandAst) => void;
  fields?: ScreenField[];
  posBindings?: PositionBinding[];
  posContext?: "init" | "live";
  pcmBindings?: PcmBinding[];
}) {
  const [editing, setEditing] = useState(false);
  if (!editing) {
    return (
      <span className="inline-flex flex-wrap items-center gap-1">
        <code className="text-[10px] leading-snug text-ink break-all">
          {formulaText(value as OperandAst)}
        </code>
        <Button
          type="button"
          onClick={() => setEditing(true)}
          variant="outline"
          size="sm"
          className={cn(tinyBtnCls, "min-w-0 px-1.5")}
          title="Open the pill editor for this expression"
        >
          edit
        </Button>
      </span>
    );
  }
  return (
    <span className="inline-flex flex-wrap items-start gap-1">
      <OperandEditor
        value={value}
        onChange={onChange}
        fields={fields}
        posBindings={posBindings}
        posContext={posContext}
        pcmBindings={pcmBindings}
      />
      <Button
        type="button"
        onClick={() => setEditing(false)}
        variant="outline"
        size="sm"
        className={cn(tinyBtnCls, "min-w-0 self-center px-1.5")}
        title="Back to the compact view"
      >
        done
      </Button>
    </span>
  );
}
