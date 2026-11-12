/**
 * Relative presets for a from-to date window (the membership chart's range).
 *
 * A date is exact and reproducible where a drag is neither, and the data is daily bars — so a
 * window is chosen by picking dates, with presets for the common spans. Everything here is pure
 * date arithmetic on UTC days, so it is testable without a chart.
 */

export type RangePresetId = "1M" | "3M" | "6M" | "1Y" | "2Y" | "YTD" | "MAX";

export interface RangePreset {
  id: RangePresetId;
  label: string;
  /** Months back from the window's end; omitted for YTD / MAX. */
  months?: number;
}

export const RANGE_PRESETS: readonly RangePreset[] = [
  { id: "1M", label: "1M", months: 1 },
  { id: "3M", label: "3M", months: 3 },
  { id: "6M", label: "6M", months: 6 },
  { id: "1Y", label: "1Y", months: 12 },
  { id: "2Y", label: "2Y", months: 24 },
  { id: "YTD", label: "YTD" },
  { id: "MAX", label: "Max" },
];

const ISO = /^\d{4}-\d{2}-\d{2}$/;

/**
 * How far back `MAX` reaches when the data's own floor is unknown — deliberately bounded so a
 * "Max" click cannot ask ClickHouse for decades of membership. Pass `floor` when you know it.
 */
const MAX_YEARS = 30; // ~the platform's whole history; only used when the data floor is unknown

/**
 * `iso` minus `months`, clamped to the shorter month (2026-03-31 − 1M = 2026-02-28) so a
 * preset never rolls forward into the next month.
 */
export function subtractMonths(iso: string, months: number): string {
  if (!ISO.test(iso)) return iso;
  const [y, m, d] = iso.split("-").map(Number) as [number, number, number];
  const monthIndex = m - 1 - months;
  const year = y + Math.floor(monthIndex / 12);
  const month = ((monthIndex % 12) + 12) % 12;
  const lastDay = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  const day = Math.min(d, lastDay);
  return `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

/** Calendar days between two ISO dates (UTC), or null when either is not a date. */
export function daysBetween(from: string, to: string): number | null {
  if (!ISO.test(from) || !ISO.test(to)) return null;
  const ms = Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`);
  if (Number.isNaN(ms)) return null;
  return Math.round(ms / 86_400_000);
}

/**
 * Normalise a window: an inverted pair collapses to the end date. There is deliberately **no
 * width cap** — the range summary is one aggregate query and how much history to chart is the
 * caller's choice.
 */
export function clampWindow(from: string, to: string): { from: string; to: string } {
  const span = daysBetween(from, to);
  if (span === null) return { from, to };
  if (span < 0) return { from: to, to };
  return { from, to };
}

/** Inclusive from-to window for a preset, ending at `to` (the screen's latest date). */
export function presetWindow(
  id: RangePresetId,
  to: string,
  floor?: string | null,
): { from: string; to: string } | null {
  if (!ISO.test(to)) return null;
  const preset = RANGE_PRESETS.find((p) => p.id === id);
  if (!preset) return null;

  let from: string;
  if (preset.months) from = subtractMonths(to, preset.months);
  else if (id === "YTD") from = `${to.slice(0, 4)}-01-01`;
  else from = floor && ISO.test(floor) ? floor : subtractMonths(to, MAX_YEARS * 12);

  if (floor && ISO.test(floor) && from < floor) from = floor;
  return clampWindow(from, to);
}
