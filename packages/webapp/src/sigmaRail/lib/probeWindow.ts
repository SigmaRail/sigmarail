/** Progressive probe windows: recent chunk first, extend earlier on demand. */

/** Initial / extend step (~1y calendar). Full backtest still via Load earlier. */
export const PROBE_CHUNK_DAYS = 365;

export function addCalendarDays(iso: string, days: number): string {
  const raw = (iso || "").trim().slice(0, 10);
  if (!raw) return "";
  const d = new Date(`${raw}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return "";
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** Start of the default probe window: max(backtestStart, asOf − chunkDays). */
export function latestChunkWindowStart(
  asOf: string,
  backtestStart?: string,
  chunkDays = PROBE_CHUNK_DAYS,
): string {
  const end = (asOf || "").trim().slice(0, 10);
  if (!end) return "";
  const chunkBack = addCalendarDays(end, -Math.abs(chunkDays));
  const floor = (backtestStart || "").trim().slice(0, 10);
  if (!floor) return chunkBack;
  return chunkBack > floor ? chunkBack : floor;
}

/** Step loadedStart one chunk earlier, clamped to backtestStart. */
export function extendWindowStart(
  currentStart: string,
  backtestStart: string,
  chunkDays = PROBE_CHUNK_DAYS,
): string {
  const cur = (currentStart || "").trim().slice(0, 10);
  const floor = (backtestStart || "").trim().slice(0, 10);
  if (!cur) return floor;
  const next = addCalendarDays(cur, -Math.abs(chunkDays));
  if (!floor) return next;
  return next > floor ? next : floor;
}
