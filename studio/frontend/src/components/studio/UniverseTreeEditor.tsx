/**
 * The Universe screen tree editor — one component, used by the screener and by a strategy's
 * Universe slot, speaking the tree the API actually compiles (`universe_query_v1` where).
 *
 * It used to be a "chips" editor capped at one level of nesting, which meant anything the
 * chips could not hold — `not`, a division, a group inside a group — was lost on the way in
 * or out. The recursion is the change: a group renders its leaves (via the existing chip
 * bar) and then its child groups, to any depth.
 *
 * Editing stays exact by construction: leaves map to rows in `astRows`, and a node the row
 * editor cannot express is carried verbatim (`readOnly` + `raw`) instead of being rewritten.
 * Ids exist only for React keys — the caller strips them (`stripIds`) before saving or
 * serialising, so a spec, a saved screen and a URL never see them.
 */

import { nextFilterId } from "../../lib/irFilters";
import {
  emptyGroup,
  isGroupNode,
  withIds,
  type UiGroup,
  type UiNode,
} from "../../lib/screenAst";
import { groupItemsFromRows, isLeafNode, leafRowsFrom } from "../../lib/astRows";
import type { ScreenField } from "../../types";
import { cn } from "../../lib/utils";
import { FilterChipBar } from "./FilterChipBar";
import { ReorderButtons } from "./ReorderButtons";

export interface UniverseTreeEditorProps {
  /** A group (wrap a bare comparison with `asGroup` first). */
  node: UiGroup;
  fields: ScreenField[];
  /** Receives the edited node; `null` means the node should be removed. */
  onChange: (next: UiNode | null) => void;
  onFocusField?: (field: ScreenField | null) => void;
  /** Position among siblings, for reordering. */
  index?: number;
  siblingCount?: number;
  onMove?: (from: number, to: number) => void;
  depth?: number;
  isRoot?: boolean;
}

/** A tree whose root is a bare comparison or a `not` still needs a place to hang groups. */
export function asGroup(node: UiNode): UiGroup {
  if (isGroupNode(node)) return node;
  return { id: node.id, type: "all", items: [node] };
}

export function UniverseTreeEditor({
  node,
  fields,
  onChange,
  onFocusField,
  index = 0,
  siblingCount = 1,
  onMove,
  depth = 0,
  isRoot = false,
}: UniverseTreeEditorProps) {
  const logic: "all" | "any" = node.type === "any" ? "any" : "all";
  const rest = node.items.filter((child) => !isLeafNode(child));
  const rows = leafRowsFrom(node.items);
  const isPrimary = isRoot && logic === "all" && (!node.name || node.name === "membership");
  /**
   * The top level *is* the AND, so a root whose logic is ALL gets no chrome at all — no box,
   * no toggle, no name field. Its children are simply the screen. The wrapper carried no
   * meaning: a universe narrows (AND), and a union belongs one level down as a nested `any`
   * (e.g. `any(exchange=NYSE, exchange=NASDAQ)`), so there is no reason to *author* a top-level
   * OR. A root that already is `any` (loaded from a spec) still renders as a real box, so
   * nothing is hidden or silently turned into an AND. The node itself is untouched, so saving
   * writes back exactly what was loaded.
   */
  const flattenRoot = isRoot && logic === "all";

  const patch = (next: Partial<UiGroup>) => onChange({ ...node, ...next });
  const replaceItems = (items: UiNode[]) => patch({ items });
  const removeAt = (id: string) => replaceItems(node.items.filter((child) => child.id !== id));
  const addGroup = () =>
    replaceItems([...node.items, withIds(emptyGroup(logic === "all" ? "any" : "all"), nextFilterId)]);
  const toggleLogic = () => patch({ type: logic === "all" ? "any" : "all" });
  const move = (from: number, to: number) => {
    if (to < 0 || to >= node.items.length) return;
    const items = [...node.items];
    const [moved] = items.splice(from, 1);
    if (moved) items.splice(to, 0, moved);
    replaceItems(items);
  };

  return (
    <div
      className={cn(
        !flattenRoot && "rounded-md border bg-surface-raised/50",
        !flattenRoot && (logic === "all" ? "border-sky-500/40" : "border-amber-500/40"),
        depth > 0 && !flattenRoot && "mt-1",
      )}
    >
      <div
        className={cn(
          "flex items-center justify-between gap-2 border-b border-line/60 px-2 py-1",
          flattenRoot && "hidden",
        )}
      >
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={toggleLogic}
            className={cn(
              "rounded px-1.5 py-0.5 text-[9.5px] font-bold uppercase tracking-wide",
              logic === "all" ? "bg-sky-500/20 text-sky-300" : "bg-amber-500/20 text-amber-300",
            )}
            title="Toggle ALL (AND) vs ANY (OR)"
          >
            {logic === "all" ? "ALL" : "ANY"}
          </button>
          <input
            type="text"
            value={node.name ?? (isPrimary ? "membership" : "")}
            onChange={(e) => patch({ name: e.target.value || undefined })}
            placeholder={isPrimary ? "membership" : "name (e.g. code_33)"}
            className="w-28 rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[10px] text-ink"
          />
          {node.items.length === 0 && (
            <span className="text-[10px] italic text-ink-faint">— no conditions yet</span>
          )}
        </div>
        <div className="flex items-center gap-1">
          {onMove && siblingCount > 1 ? (
            <ReorderButtons
              canUp={index > 0}
              canDown={index < siblingCount - 1}
              onUp={() => onMove(index, index - 1)}
              onDown={() => onMove(index, index + 1)}
            />
          ) : null}
          {!isPrimary && (
            <button
              type="button"
              onClick={() => onChange(null)}
              className="rounded border border-line px-1.5 py-0.5 text-[10px] text-danger hover:bg-danger/10"
              title="Remove group"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      <div className={cn("pb-1.5", !flattenRoot && "px-2")}>
        <FilterChipBar
          filterRows={rows}
          fields={fields}
          onFilterRowsChange={(next) => replaceItems(groupItemsFromRows(next, rest))}
          onFocusField={onFocusField}
        />

        {rest.length > 0 && (
          <div className={cn("mt-1 space-y-1", !flattenRoot && "border-l border-line/70 pl-2")}>
            {rest.map((child, i) => (
              <NestedNode
                key={child.id}
                node={child}
                fields={fields}
                onFocusField={onFocusField}
                index={i}
                siblingCount={rest.length}
                depth={depth + 1}
                onChange={(next) => {
                  if (next === null) removeAt(child.id);
                  else replaceItems(node.items.map((c) => (c.id === child.id ? next : c)));
                }}
                onMove={(from, to) => {
                  // reorder within the non-leaf run, mapped back onto the full item list
                  const leafCount = node.items.length - rest.length;
                  move(leafCount + from, leafCount + to);
                }}
              />
            ))}
          </div>
        )}

        <button
          type="button"
          onClick={addGroup}
          className="mt-1.5 inline-flex items-center gap-1 rounded-md border border-dashed border-violet-400/60 bg-violet-500/5 px-2.5 py-1 text-[11px] font-semibold text-violet-300 hover:bg-violet-500/10"
        >
          + Add Group
        </button>
      </div>
    </div>
  );
}

/**
 * A child that is a group renders as a group; a child wrapped in `not` keeps its negation
 * (shown as a NOT box, so `not(all(...))` is never silently rewritten as something else).
 */
function NestedNode({
  node,
  onChange,
  ...rest
}: Omit<UniverseTreeEditorProps, "node" | "onChange"> & {
  node: UiNode;
  onChange: (next: UiNode | null) => void;
}) {
  if (node.type === "not") {
    if (!isGroupNode(node.item)) {
      // a `not` over a comparison is a leaf row; it should not reach here
      return null;
    }
    return (
      <NotBox
        onRemove={() => onChange(node.item)}
        onDelete={() => onChange(null)}
      >
        <UniverseTreeEditor
          node={asGroup(node.item)}
          onChange={(next) => onChange(next === null ? null : { ...node, id: node.id, item: next })}
          {...rest}
        />
      </NotBox>
    );
  }
  return <UniverseTreeEditor node={asGroup(node)} onChange={onChange} {...rest} />;
}

function NotBox({
  children,
  onRemove,
  onDelete,
}: {
  children: React.ReactNode;
  onRemove: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="rounded-md border border-rose-500/40 bg-rose-500/5">
      <div className="flex items-center justify-between gap-2 border-b border-rose-500/30 px-2 py-0.5">
        <span className="text-[9.5px] font-bold uppercase tracking-wide text-rose-300">
          NOT
        </span>
        <span className="flex items-center gap-1">
          <button
            type="button"
            onClick={onRemove}
            className="rounded border border-line px-1.5 text-[9.5px] text-ink-dim hover:bg-surface"
            title="Keep the group, drop the NOT"
          >
            unwrap
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="rounded border border-line px-1.5 text-[9.5px] text-danger hover:bg-danger/10"
            title="Remove"
          >
            ✕
          </button>
        </span>
      </div>
      <div className="p-1">{children}</div>
    </div>
  );
}
