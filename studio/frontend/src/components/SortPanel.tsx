import {
  applyLimitToSpec,
  applySortToSpec,
  primaryOrderBy,
} from "../lib/screenSpec";
import type {
  OrderDirection,
  ScreenField,
  ScreenSource,
  UniverseQueryV1,
} from "../types";

const FALLBACK_SORT_FIELDS = [
  "rs_rating",
  "overall_score",
  "minervini_score",
  "oneil_score",
  "close",
];

export function SortPanel({
  source,
  spec,
  fields,
  onSpecChange,
}: {
  source: ScreenSource;
  spec: UniverseQueryV1 | null;
  fields: ScreenField[];
  onSpecChange: (next: UniverseQueryV1) => void;
}) {
  const editable = source === "ir" && spec != null;
  const order = primaryOrderBy(spec);
  const field = order?.field ?? spec?.select?.[0] ?? "rs_rating";
  const direction: OrderDirection = order?.direction ?? "desc";
  const limit = spec?.limit_per_day ?? 50;

  const fieldOptions = buildFieldOptions(spec, fields);

  const onFieldChange = (nextField: string) => {
    if (!spec) return;
    onSpecChange(applySortToSpec(spec, nextField, direction));
  };

  const onDirectionChange = (nextDir: OrderDirection) => {
    if (!spec) return;
    onSpecChange(applySortToSpec(spec, field, nextDir));
  };

  const onLimitChange = (raw: string) => {
    if (!spec) return;
    const n = Number(raw);
    if (!Number.isFinite(n)) return;
    onSpecChange(applyLimitToSpec(spec, n));
  };

  return (
    <div className="shrink-0 border-b border-line">
      <div className="border-b border-line px-3 py-2">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
          Sort &amp; limit
        </div>
        <div className="text-[11px] text-ink-muted">
          {editable
            ? "Saved with IR · order_by + limit_per_day"
            : "Load an IR template to edit sort"}
        </div>
      </div>

      <div className="space-y-2 p-2">
        {!editable ? (
          <p className="px-1 py-1 text-[11px] text-ink-muted">
            Load an IR template to edit sort.
          </p>
        ) : (
          <>
            <label className="block">
              <span className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
                Sort field
              </span>
              <select
                className="w-full rounded border border-line bg-surface-sunk px-2 py-1 font-mono text-[11px] text-ink"
                value={field}
                onChange={(e) => onFieldChange(e.target.value)}
              >
                {fieldOptions.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
                Direction
              </span>
              <select
                className="w-full rounded border border-line bg-surface-sunk px-2 py-1 font-mono text-[11px] text-ink"
                value={direction}
                onChange={(e) =>
                  onDirectionChange(e.target.value as OrderDirection)
                }
              >
                <option value="desc">DESC</option>
                <option value="asc">ASC</option>
              </select>
            </label>

            <label className="block">
              <span className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
                Limit per day
              </span>
              <input
                type="number"
                min={1}
                max={500}
                className="w-full rounded border border-line bg-surface-sunk px-2 py-1 font-mono text-[11px] text-ink"
                value={limit}
                onChange={(e) => onLimitChange(e.target.value)}
              />
            </label>
          </>
        )}
      </div>
    </div>
  );
}

function buildFieldOptions(
  spec: UniverseQueryV1 | null,
  fields: ScreenField[],
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  const push = (name: string) => {
    if (!name || seen.has(name)) return;
    seen.add(name);
    out.push(name);
  };
  for (const s of spec?.select ?? []) push(s);
  for (const f of fields) push(f.name);
  for (const f of FALLBACK_SORT_FIELDS) push(f);
  return out;
}
