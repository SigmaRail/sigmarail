import type { Time } from "lightweight-charts";

/** Map lightweight-charts Time → YYYY-MM-DD (UTC business day). */
export function lwcTimeToIsoDate(time: Time | undefined | null): string | null {
  if (time == null) return null;
  if (typeof time === "string") {
    const s = time.trim().slice(0, 10);
    return /^\d{4}-\d{2}-\d{2}$/.test(s) ? s : null;
  }
  if (typeof time === "number") {
    const d = new Date(time * 1000);
    if (Number.isNaN(d.getTime())) return null;
    return d.toISOString().slice(0, 10);
  }
  if (typeof time === "object" && "year" in time) {
    const y = Number(time.year);
    const m = Number(time.month);
    const day = Number(time.day);
    if (![y, m, day].every(Number.isFinite)) return null;
    return `${y}-${String(m).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
  }
  return null;
}
