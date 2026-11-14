/**
 * A strategy document's filter slot (Universe hygiene tree, Alpha measure filters) edited by
 * the shared `UniverseTreeEditor`.
 *
 * The document stores `FilterTree[]` — a model that can express `not(eq(...))` as `neq` and
 * nothing else negated — while the editor speaks the API's where-AST. This adapter is the one
 * place those two meet, so every strategy slot gets the screener's editing power (any nesting
 * depth, `not`, arithmetic) without each card reimplementing the bridge:
 *
 *   document FilterTree[]  --filterTreesToIr-->  tree  --UniverseTreeEditor-->  tree
 *                          <--screenTreesForWhere--        (only when exact)
 *
 * A change the document cannot hold is refused and shown, never silently reduced.
 */

import { useEffect, useRef, useState } from "react";
import { filterTreesToIr, screenTreesForWhere } from "../../lib/filterTreeChips";
import {
  emptyGroup,
  stripIds,
  whereToAst,
  withIds,
  type UiGroup,
  type UiNode,
} from "../../lib/screenAst";
import { nextFilterId } from "../../lib/irFilters";
import type { ScreenField } from "../../types";
import type { FilterTree } from "../strategy/StrategyDocument";
import { UniverseTreeEditor, asGroup } from "./UniverseTreeEditor";

export interface FilterTreeSlotEditorProps {
  /** The document slot's trees; a stage may have none yet. */
  filters?: FilterTree[];
  fields: ScreenField[];
  onChange: (next: FilterTree[]) => void;
}

function treeFromFilters(filters: FilterTree[] | undefined): UiGroup {
  return asGroup(
    withIds(whereToAst(filterTreesToIr(filters)) ?? emptyGroup("all", "membership"), nextFilterId),
  );
}

export function FilterTreeSlotEditor({ filters, fields, onChange }: FilterTreeSlotEditorProps) {
  const key = JSON.stringify(filters ?? []);
  const appliedRef = useRef(key);
  const [root, setRoot] = useState<UiGroup>(() => treeFromFilters(filters));
  const [refusal, setRefusal] = useState<string | null>(null);

  // Re-sync when the document changes elsewhere; our own commits echo back, so the applied
  // content is remembered and an echo must not rebuild the tree (fresh ids would remount
  // every input and steal focus mid-typing).
  useEffect(() => {
    if (key === appliedRef.current) return;
    appliedRef.current = key;
    setRoot(treeFromFilters(filters));
  }, [key]);

  const handleChange = (node: UiNode | null) => {
    const next = asGroup(node ?? withIds(emptyGroup("all", "membership"), nextFilterId));
    const trees = screenTreesForWhere(stripIds(next));
    if (trees === null) {
      setRefusal(
        "Not stored: the strategy document holds `not` only as `≠`, so this condition cannot be saved yet. Nothing was changed.",
      );
      return;
    }
    setRefusal(null);
    setRoot(next);
    appliedRef.current = JSON.stringify(trees);
    onChange(trees);
  };

  return (
    <div className="space-y-2">
      {refusal && (
        <div className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[10.5px] text-amber-200">
          {refusal}
        </div>
      )}
      <UniverseTreeEditor node={root} fields={fields} onChange={handleChange} isRoot />
    </div>
  );
}
