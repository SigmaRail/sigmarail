/** TradingView symbol helpers — do not assume NASDAQ for every US equity. */

const KNOWN_PREFIX: Record<string, string> = {
  SPY: "AMEX",
  QQQ: "NASDAQ",
  IWM: "AMEX",
  DIA: "AMEX",
  GLD: "AMEX",
  SLV: "AMEX",
};

/** Map Sharadar / CH exchange codes → TradingView exchange ids. */
const EXCHANGE_TO_TV: Record<string, string> = {
  NASDAQ: "NASDAQ",
  NYSE: "NYSE",
  NYSEMKT: "AMEX",
  AMEX: "AMEX",
  BATS: "BATS",
  ARCA: "AMEX",
  OTC: "OTC",
};

/**
 * Prefer bare ticker so TV can resolve the listing (NYSE vs NASDAQ).
 * If ``exchange`` is known (from CH), use ``EXCHANGE:TICKER``.
 */
export function toTvSymbol(
  ticker: string,
  exchange?: string | null,
): string {
  const raw = ticker.trim().toUpperCase();
  if (!raw) return "SPY";
  if (raw.includes(":")) return raw;

  const fromKnown = KNOWN_PREFIX[raw];
  if (fromKnown) return `${fromKnown}:${raw}`;

  const ex = (exchange || "").trim().toUpperCase();
  const tvEx = EXCHANGE_TO_TV[ex];
  if (tvEx) return `${tvEx}:${raw}`;

  // Bare ticker — TradingView resolves NYSE/NASDAQ better than a wrong NASDAQ: prefix.
  return raw;
}
