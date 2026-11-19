import type { OrderDirection, UniverseQueryV1 } from "../types";

/** Ensure `field` appears in `select` (append if missing). */
export function ensureSelectHas(
  spec: UniverseQueryV1,
  field: string,
): UniverseQueryV1 {
  const select = Array.isArray(spec.select) ? [...spec.select] : [];
  if (!select.includes(field)) {
    select.push(field);
  }
  return { ...spec, select };
}

export function applySortToSpec(
  spec: UniverseQueryV1,
  field: string,
  direction: OrderDirection,
): UniverseQueryV1 {
  const withSelect = ensureSelectHas(spec, field);
  return {
    ...withSelect,
    order_by: [{ field, direction }],
  };
}

export function applyLimitToSpec(
  spec: UniverseQueryV1,
  limitPerDay: number,
): UniverseQueryV1 {
  const clamped = Math.min(500, Math.max(1, Math.round(limitPerDay)));
  return { ...spec, limit_per_day: clamped };
}

export function primaryOrderBy(
  spec: UniverseQueryV1 | null | undefined,
): { field: string; direction: OrderDirection } | null {
  const first = spec?.order_by?.[0];
  if (!first?.field) return null;
  const direction =
    first.direction === "asc" || first.direction === "ASC" ? "asc" : "desc";
  return { field: first.field, direction };
}
