const SECTOR_COLORS = {
  "Basic Materials": { hex: "#f59e0b", className: "bg-amber-500" },
  "Communication Services": { hex: "#f97316", className: "bg-orange-500" },
  "Consumer Cyclical": { hex: "#f43f5e", className: "bg-rose-500" },
  "Consumer Defensive": { hex: "#84cc16", className: "bg-lime-500" },
  Energy: { hex: "#ef4444", className: "bg-red-500" },
  "Financial Services": { hex: "#10b981", className: "bg-emerald-500" },
  Healthcare: { hex: "#0ea5e9", className: "bg-sky-500" },
  Industrials: { hex: "#8b5cf6", className: "bg-violet-500" },
  "Real Estate": { hex: "#ec4899", className: "bg-pink-500" },
  Technology: { hex: "#06b6d4", className: "bg-cyan-500" },
  Utilities: { hex: "#14b8a6", className: "bg-teal-500" },
  "Unknown / unclassified": { hex: "#64748b", className: "bg-slate-500" },
} as const;

const FALLBACK_COLORS = [
  { hex: "#3b82f6", className: "bg-blue-500" },
  { hex: "#a855f7", className: "bg-purple-500" },
  { hex: "#22c55e", className: "bg-green-500" },
  { hex: "#eab308", className: "bg-yellow-500" },
] as const;

function fallbackColor(sector: string) {
  let hash = 0;
  for (let i = 0; i < sector.length; i += 1) {
    hash = (hash * 31 + sector.charCodeAt(i)) | 0;
  }
  return FALLBACK_COLORS[Math.abs(hash) % FALLBACK_COLORS.length]!;
}

/** Stable palette so filtering, sorting, and time changes never recolor a sector. */
export function sectorColor(sector: string): { hex: string; className: string } {
  return SECTOR_COLORS[sector as keyof typeof SECTOR_COLORS] ?? fallbackColor(sector);
}

const SECTOR_ORDER = Object.keys(SECTOR_COLORS);

export function compareSectorNames(a: string, b: string): number {
  const ai = SECTOR_ORDER.indexOf(a);
  const bi = SECTOR_ORDER.indexOf(b);
  if (ai >= 0 && bi >= 0) return ai - bi;
  if (ai >= 0) return -1;
  if (bi >= 0) return 1;
  return a.localeCompare(b);
}
