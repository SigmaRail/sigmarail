import type { WorkbenchTab } from "./types";

/**
 * Canonical path segments for each workbench tab.
 * User-facing names are used (not internal ids): compose -> /strategies, runs -> /backtests.
 */
export const TAB_PATHS: Record<WorkbenchTab, string> = {
  screens: "/screens",
  charts: "/charts",
  watchlists: "/watchlists",
  compose: "/strategies",
  runs: "/backtests",
  optimize: "/optimize",
  deploy: "/deploy",
  monitor: "/monitor",
  market: "/market",
};

const SEGMENT_TO_TAB: Record<string, WorkbenchTab> = {
  screens: "screens",
  charts: "charts",
  // Ticker workspace: /stock/NVDA/chart is the canonical charts URL (see stockFromPath).
  stock: "charts",
  watchlists: "watchlists",
  strategies: "compose",
  backtests: "runs",
  optimize: "optimize",
  deploy: "deploy",
  monitor: "monitor",
  market: "market",
};

/** Map a URL pathname back to the active workbench tab (defaults to screens). */
export function tabForPath(pathname: string): WorkbenchTab {
  const seg = pathname.split("/").filter(Boolean)[0] ?? "";
  return SEGMENT_TO_TAB[seg] ?? "screens";
}

export const BACKTEST_SECTIONS = ["overview", "trades", "attribution", "scrubber"] as const;
export type BacktestSection = (typeof BACKTEST_SECTIONS)[number];

/** Parse /backtests/:runId/:section into its parts (section defaults to overview). */
export function backtestRunFromPath(pathname: string): {
  runId: string | null;
  section: BacktestSection;
} {
  const segs = pathname.split("/").filter(Boolean);
  if (segs[0] !== "backtests" || !segs[1]) {
    return { runId: null, section: "overview" };
  }
  const raw = segs[2] ?? "overview";
  const section: BacktestSection = (BACKTEST_SECTIONS as readonly string[]).includes(raw)
    ? (raw as BacktestSection)
    : "overview";
  return { runId: segs[1], section };
}

/** Build a canonical backtest run URL. */
export function backtestRunPath(runId: string, section: BacktestSection = "overview"): string {
  return `/backtests/${runId}/${section}`;
}

/** Ticker workspace sections. `chart` is the default; add a name here to expose a new one. */
export const STOCK_SECTIONS = ["chart"] as const;
export type StockSection = (typeof STOCK_SECTIONS)[number];

/** Parse `/stock/:ticker/:section` — bare `/stock` returns a null ticker (section defaults to chart). */
export function stockFromPath(pathname: string): {
  ticker: string | null;
  section: StockSection;
} {
  const segs = pathname.split("/").filter(Boolean);
  if (segs[0] !== "stock" || !segs[1]) return { ticker: null, section: "chart" };
  let raw = segs[1];
  try {
    raw = decodeURIComponent(raw);
  } catch {
    // keep the raw segment when it is not valid percent-encoding
  }
  const requested = segs[2] ?? "chart";
  const section: StockSection = (STOCK_SECTIONS as readonly string[]).includes(requested)
    ? (requested as StockSection)
    : "chart";
  return { ticker: raw.trim().toUpperCase(), section };
}

/** Build a canonical ticker workspace URL: `/stock/NVDA/chart`. */
export function stockPath(ticker: string, section: StockSection = "chart"): string {
  return `/stock/${encodeURIComponent(ticker.trim().toUpperCase())}/${section}`;
}

/** Parse `/strategies/:irId` — bare `/strategies` returns null (untitled draft). */
export function strategyIrIdFromPath(pathname: string): string | null {
  const segs = pathname.split("/").filter(Boolean);
  if (segs[0] !== "strategies" || !segs[1]) return null;
  try {
    return decodeURIComponent(segs[1]);
  } catch {
    return segs[1];
  }
}

/** Build `/strategies` or `/strategies/:irId`. */
export function strategyPath(irId?: string | null): string {
  const id = (irId || "").trim();
  return id ? `/strategies/${encodeURIComponent(id)}` : "/strategies";
}
