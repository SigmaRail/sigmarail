import { toTvSymbol } from "../lib/tvSymbol";

/**
 * Compact TradingView Mini Symbol Overview via iframe (reliable for many
 * simultaneous grid cards; avoids script-tag races).
 */
export function TradingViewMiniEmbed({
  symbol,
  exchange,
  height = 180,
  dateRange = "12M",
  className,
}: {
  symbol: string | null;
  exchange?: string | null;
  height?: number;
  /** TV mini widget range: 1D | 1M | 3M | 12M | 60M | ALL */
  dateRange?: string;
  className?: string;
}) {
  if (!symbol) {
    return (
      <div
        className={
          className ??
          "flex items-center justify-center bg-[#131722] text-[10px] text-ink-faint"
        }
        style={{ height }}
      >
        —
      </div>
    );
  }

  const tvSymbol = toTvSymbol(symbol, exchange);
  const config = {
    symbol: tvSymbol,
    width: "100%",
    height,
    locale: "en",
    dateRange,
    colorTheme: "dark",
    isTransparent: true,
    autosize: false,
    chartOnly: false,
    noTimeScale: false,
  };
  const src = `https://s.tradingview.com/embed-widget/mini-symbol-overview/?locale=en#${encodeURIComponent(
    JSON.stringify(config),
  )}`;

  return (
    <div
      className={
        className ?? "overflow-hidden bg-[#131722]"
      }
      style={{ height, width: "100%" }}
    >
      <iframe
        title={`TV ${tvSymbol}`}
        src={src}
        style={{
          width: "100%",
          height: "100%",
          border: 0,
          margin: 0,
          padding: 0,
          display: "block",
        }}
        loading="lazy"
        referrerPolicy="no-referrer-when-downgrade"
      />
    </div>
  );
}
