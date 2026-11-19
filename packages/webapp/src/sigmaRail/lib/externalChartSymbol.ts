/** External chart symbol helpers — do not assume NASDAQ for every US equity. */

const KNOWN_PREFIX: Record<string, string> = {
  SPY: "AMEX",
  QQQ: "NASDAQ",
  IWM: "AMEX",
  DIA: "AMEX",
  GLD: "AMEX",
  SLV: "AMEX",
};

/** Map Sharadar / CH exchange codes → external chart exchange ids. */
const EXTERNAL_EXCHANGE_CODES: Record<string, string> = {
  NASDAQ: "NASDAQ",
  NYSE: "NYSE",
  NYSEMKT: "AMEX",
  AMEX: "AMEX",
  BATS: "BATS",
  ARCA: "AMEX",
  OTC: "OTC",
};

/**
 * Prefer bare ticker so the external provider can resolve the listing (NYSE vs NASDAQ).
 * If ``exchange`` is known (from CH), use ``EXCHANGE:TICKER``.
 */
export function toExternalChartSymbol(
  ticker: string,
  exchange?: string | null,
): string {
  const raw = ticker.trim().toUpperCase();
  if (!raw) return "SPY";
  if (raw.includes(":")) return raw;

  const fromKnown = KNOWN_PREFIX[raw];
  if (fromKnown) return `${fromKnown}:${raw}`;

  const ex = (exchange || "").trim().toUpperCase();
  const externalExchange = EXTERNAL_EXCHANGE_CODES[ex];
  if (externalExchange) return `${externalExchange}:${raw}`;

  // Bare ticker — the external chart provider resolves NYSE/NASDAQ better than a wrong NASDAQ: prefix.
  return raw;
}
