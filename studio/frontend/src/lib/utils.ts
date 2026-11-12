import type { PreviewResponse, RankDelta, RankedRow, TurnoverResponse } from "../types";

export function priorDateInRange(
  datesDesc: string[],
  asOf: string,
): string | null {
  const idx = datesDesc.indexOf(asOf);
  if (idx < 0 || idx + 1 >= datesDesc.length) return null;
  return datesDesc[idx + 1] ?? null;
}

export function computeTurnover(
  current: PreviewResponse,
  prior: PreviewResponse | null,
  priorAsOf: string | null,
): TurnoverResponse {
  const currSet = new Set(current.rows.map((r) => r.ticker.toUpperCase()));
  const priorSet = new Set(
    (prior?.rows ?? []).map((r) => r.ticker.toUpperCase()),
  );
  const added = [...currSet].filter((t) => !priorSet.has(t)).sort();
  const removed = [...priorSet].filter((t) => !currSet.has(t)).sort();
  let retained = 0;
  for (const t of currSet) {
    if (priorSet.has(t)) retained += 1;
  }
  return {
    as_of: current.as_of,
    prior: priorAsOf,
    added,
    removed,
    retained_count: retained,
  };
}

export function enrichRows(
  current: PreviewResponse,
  prior: PreviewResponse | null,
  turnover: TurnoverResponse | null,
): RankedRow[] {
  const priorRank = new Map<string, number>();
  (prior?.rows ?? []).forEach((row, i) => {
    priorRank.set(row.ticker.toUpperCase(), i + 1);
  });
  const added = new Set((turnover?.added ?? []).map((t) => t.toUpperCase()));
  const removed = new Set(
    (turnover?.removed ?? []).map((t) => t.toUpperCase()),
  );

  const ranked: RankedRow[] = current.rows.map((row, i) => {
    const ticker = row.ticker.toUpperCase();
    const rank = i + 1;
    const prev = priorRank.get(ticker) ?? null;
    let delta: RankDelta = null;
    let deltaRank: number | null = null;
    if (added.has(ticker) || prev == null) {
      delta = "new";
    } else {
      deltaRank = prev - rank;
      if (deltaRank > 0) delta = "up";
      else if (deltaRank < 0) delta = "down";
      else delta = "same";
    }
    return {
      ...row,
      ticker,
      rank,
      priorRank: prev,
      delta,
      deltaRank,
    };
  });

  // Surface dropped names at bottom for visibility when prior exists
  if (prior && removed.size > 0) {
    prior.rows.forEach((row, i) => {
      const ticker = row.ticker.toUpperCase();
      if (!removed.has(ticker)) return;
      ranked.push({
        ...row,
        ticker,
        rank: -(i + 1),
        priorRank: i + 1,
        delta: "dropped",
        deltaRank: null,
      });
    });
  }

  return ranked;
}

export function formatNum(value: unknown, digits = 1): string {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value.toFixed(digits);
  }
  if (typeof value === "string" && value.trim() !== "") {
    const n = Number(value);
    if (Number.isFinite(n)) return n.toFixed(digits);
  }
  return "—";
}

/** Compact volume for AvgVol50 / similar (e.g. 689920 → 690k). */
export function formatVol(value: unknown): string {
  let n: number | null = null;
  if (typeof value === "number" && Number.isFinite(value)) n = value;
  else if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) n = parsed;
  }
  if (n == null) return "—";
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `${Math.round(n / 1_000)}k`;
  return String(Math.round(n));
}

export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/** Move ``from`` index to ``to`` (no-op if out of range). */
export function moveIndex<T>(items: T[], from: number, to: number): T[] {
  if (
    from === to ||
    from < 0 ||
    to < 0 ||
    from >= items.length ||
    to >= items.length
  ) {
    return items;
  }
  const next = [...items];
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item!);
  return next;
}

/** Swap two indices (no-op if out of range). */
export function swapIndex<T>(items: T[], a: number, b: number): T[] {
  if (
    a === b ||
    a < 0 ||
    b < 0 ||
    a >= items.length ||
    b >= items.length
  ) {
    return items;
  }
  const next = [...items];
  const tmp = next[a]!;
  next[a] = next[b]!;
  next[b] = tmp;
  return next;
}
