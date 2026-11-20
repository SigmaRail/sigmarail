/** Classify a symbol's filled orders into pyramid adds vs scale-out tranches. */

export type CampaignFillKind =
  | "test"
  | "add"
  | "full"
  | "time_stop"
  | "t1"
  | "t2"
  | "t3"
  | "stop"
  | "trim";

export type CampaignFill = {
  date: string;
  side: "buy" | "sell";
  qty: number;
  price: number;
  label: string;
  kind: CampaignFillKind;
  openAfter: number;
};

export function tickerKey(raw: string): string {
  const tok = (raw || "").trim().split(/\s+/)[0] ?? "";
  return tok.toUpperCase();
}

function isFilled(status: unknown): boolean {
  if (status === 3 || status === 2) return true;
  const s = String(status ?? "").toLowerCase();
  return s === "filled" || s === "partiallyfilled" || s === "partially_filled";
}

function orderSymbol(row: Record<string, unknown>): string {
  const sym = row.symbolValue ?? row.Symbol ?? row.symbol;
  if (typeof sym === "string") return tickerKey(sym);
  if (sym && typeof sym === "object" && "value" in (sym as object)) {
    return tickerKey(String((sym as { value: unknown }).value ?? ""));
  }
  return "";
}

function orderDate(row: Record<string, unknown>): string | null {
  const t = row.time ?? row.lastFillTime ?? row.Time;
  if (typeof t === "number" && Number.isFinite(t) && t > 0) {
    const ms = t > 1e12 ? t : t * 1000;
    return new Date(ms).toISOString().slice(0, 10);
  }
  if (typeof t === "string" && t.length >= 8) {
    if (/^\d+(\.\d+)?$/.test(t)) {
      const n = Number(t);
      const ms = n > 1e12 ? n : n * 1000;
      return new Date(ms).toISOString().slice(0, 10);
    }
    return t.slice(0, 10);
  }
  return null;
}

function orderSideQty(
  row: Record<string, unknown>,
): { side: "buy" | "sell"; qty: number } | null {
  const fillQty = Number(row.fillQuantity ?? 0);
  const qtyRaw = Number(row.quantity ?? 0);
  const dir = String(row.direction ?? "").toLowerCase();
  const qty = Math.abs(fillQty) > 0 ? Math.abs(fillQty) : Math.abs(qtyRaw);
  if (!(qty > 0)) return null;
  if (dir === "buy" || dir === "0") return { side: "buy", qty };
  if (dir === "sell" || dir === "1") return { side: "sell", qty };
  if (fillQty < 0 || qtyRaw < 0) return { side: "sell", qty };
  return { side: "buy", qty };
}

function orderPrice(row: Record<string, unknown>): number {
  const px = Number(row.fillPrice ?? row.price ?? 0);
  return Number.isFinite(px) ? px : 0;
}

function sellKindFromFrac(frac: number): CampaignFillKind {
  if (frac >= 0.9) return "stop";
  if (frac >= 0.4 && frac <= 0.62) return "time_stop";
  if (frac >= 0.15 && frac < 0.28) return "t1";
  if (frac >= 0.28 && frac < 0.38) return "t2";
  if (frac >= 0.38 && frac < 0.45) return "t3";
  return "trim";
}

function buyLabel(kind: CampaignFillKind, qty: number): string {
  const n = Number.isInteger(qty) ? String(qty) : qty.toFixed(0);
  if (kind === "test") return `TEST +${n}`;
  if (kind === "add") return `ADD +${n}`;
  if (kind === "full") return `FULL +${n}`;
  return `BUY +${n}`;
}

function sellLabel(kind: CampaignFillKind, qty: number): string {
  const n = Number.isInteger(qty) ? String(qty) : qty.toFixed(0);
  if (kind === "time_stop") return `TIME-STOP -${n}`;
  if (kind === "t1") return `T1 -${n}`;
  if (kind === "t2") return `T2 -${n}`;
  if (kind === "t3") return `T3 -${n}`;
  if (kind === "stop") return `STOP -${n}`;
  return `TRIM -${n}`;
}

export function campaignFillsForSymbol(
  orders: unknown[],
  symbol: string,
): CampaignFill[] {
  const want = tickerKey(symbol);
  const parsed: Array<{
    date: string;
    side: "buy" | "sell";
    qty: number;
    price: number;
  }> = [];
  for (const raw of orders) {
    if (!raw || typeof raw !== "object") continue;
    const row = raw as Record<string, unknown>;
    if (!isFilled(row.status ?? row.Status)) continue;
    if (orderSymbol(row) !== want) continue;
    const date = orderDate(row);
    const sideQty = orderSideQty(row);
    const price = orderPrice(row);
    if (!date || !sideQty || !(price > 0)) continue;
    parsed.push({ date, side: sideQty.side, qty: sideQty.qty, price });
  }
  parsed.sort((a, b) => a.date.localeCompare(b.date));

  const out: CampaignFill[] = [];
  let openQty = 0;
  let buyIndex = 0;
  for (const fill of parsed) {
    if (fill.side === "buy") {
      const kind: CampaignFillKind =
        buyIndex === 0 ? "test" : buyIndex === 1 ? "add" : "full";
      buyIndex += 1;
      openQty += fill.qty;
      out.push({
        ...fill,
        kind,
        label: buyLabel(kind, fill.qty),
        openAfter: openQty,
      });
      continue;
    }
    const frac = openQty > 0 ? fill.qty / openQty : 1;
    const kind = sellKindFromFrac(frac);
    openQty = Math.max(0, openQty - fill.qty);
    if (openQty === 0) {
      buyIndex = 0;
    }
    out.push({
      ...fill,
      kind,
      label: sellLabel(kind, fill.qty),
      openAfter: openQty,
    });
  }
  return out;
}

export function campaignShareTotals(fills: CampaignFill[]): {
  bought: number;
  sold: number;
  remaining: number;
} {
  let bought = 0;
  let sold = 0;
  for (const f of fills) {
    if (f.side === "buy") bought += f.qty;
    else sold += f.qty;
  }
  return { bought, sold, remaining: Math.max(0, bought - sold) };
}

export type CampaignPerformance = {
  bought: number;
  sold: number;
  remaining: number;
  cashIn: number;
  cashOut: number;
  avgEntry: number;
  realizedPnl: number;
  unrealizedPnl: number;
  totalPnl: number;
  returnPct: number;
  firstDate: string | null;
  lastFillDate: string | null;
  markPrice: number | null;
};

export function campaignPerformance(
  fills: CampaignFill[],
  markPrice: number | null,
): CampaignPerformance | null {
  if (fills.length === 0) return null;
  const { bought, sold, remaining } = campaignShareTotals(fills);
  let cashIn = 0;
  let cashOut = 0;
  for (const f of fills) {
    const notional = f.qty * f.price;
    if (f.side === "buy") cashIn += notional;
    else cashOut += notional;
  }
  const avgEntry = bought > 0 ? cashIn / bought : 0;
  const mark = markPrice != null && markPrice > 0 ? markPrice : null;
  const realizedPnl = cashOut - avgEntry * sold;
  const unrealizedPnl = mark != null ? remaining * (mark - avgEntry) : 0;
  const totalPnl = realizedPnl + unrealizedPnl;
  const returnPct = cashIn > 0 ? totalPnl / cashIn : 0;
  return {
    bought,
    sold,
    remaining,
    cashIn,
    cashOut,
    avgEntry,
    realizedPnl,
    unrealizedPnl,
    totalPnl,
    returnPct,
    firstDate: fills[0]?.date ?? null,
    lastFillDate: fills[fills.length - 1]?.date ?? null,
    markPrice: mark,
  };
}

export type CampaignMarkPoint = {
  date: string;
  remaining: number;
  avgEntry: number;
  cashIn: number;
  totalPnl: number;
  returnPct: number;
};

/** Mark-to-market of the whole campaign at each bar close (fills dated that day or earlier). */
export function campaignMarkSeries(
  fills: CampaignFill[],
  bars: Array<{ date: string; close: number }>,
): CampaignMarkPoint[] {
  if (fills.length === 0 || bars.length === 0) return [];
  let fi = 0;
  let cashIn = 0;
  let cashOut = 0;
  let remaining = 0;
  let bought = 0;
  let lastFillDate: string | null = null;
  const out: CampaignMarkPoint[] = [];
  for (const bar of bars) {
    while (fi < fills.length && fills[fi]!.date <= bar.date) {
      const f = fills[fi]!;
      const notional = f.qty * f.price;
      if (f.side === "buy") {
        cashIn += notional;
        remaining += f.qty;
        bought += f.qty;
      } else {
        cashOut += notional;
        remaining = Math.max(0, remaining - f.qty);
      }
      lastFillDate = f.date;
      fi += 1;
    }
    if (bought === 0) continue;
    if (remaining === 0 && lastFillDate != null && lastFillDate < bar.date) {
      continue;
    }
    const totalPnl = cashOut + remaining * bar.close - cashIn;
    const returnPct = cashIn > 0 ? (totalPnl / cashIn) * 100 : 0;
    out.push({
      date: bar.date,
      remaining,
      avgEntry: cashIn / bought,
      cashIn,
      totalPnl,
      returnPct,
    });
  }
  return out;
}

export type HoldingSignRun = {
  startDate: string;
  endDate: string;
  positive: boolean;
};

export function campaignHoldingSignRuns(
  marks: CampaignMarkPoint[],
): HoldingSignRun[] {
  const runs: HoldingSignRun[] = [];
  for (const m of marks) {
    const positive = m.totalPnl >= 0;
    const last = runs[runs.length - 1];
    if (last && last.positive === positive) {
      last.endDate = m.date;
    } else {
      runs.push({ startDate: m.date, endDate: m.date, positive });
    }
  }
  return runs;
}

export const CAMPAIGN_FILL_COLORS: Record<CampaignFillKind, string> = {
  test: "#10b981",
  add: "#34d399",
  full: "#6ee7b7",
  time_stop: "#f59e0b",
  t1: "#f43f5e",
  t2: "#e11d48",
  t3: "#be123c",
  stop: "#881337",
  trim: "#fb7185",
};
