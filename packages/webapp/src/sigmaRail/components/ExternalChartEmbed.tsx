import { useEffect, useId, useRef } from "react";
import { toExternalChartSymbol } from "../lib/externalChartSymbol";

const EXTERNAL_CHART_SCRIPT_URL = "https://s3.tradingview.com/tv.js";

type ExternalChartWidget = {
  remove?: () => void;
};

type ExternalChartSdk = {
  widget: new (opts: Record<string, unknown>) => ExternalChartWidget;
};

declare global {
  interface Window {
    TradingView?: ExternalChartSdk;
  }
}

let scriptPromise: Promise<void> | null = null;

function loadExternalChartSdk(): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("no window"));
  if (window.TradingView) return Promise.resolve();
  if (scriptPromise) return scriptPromise;
  scriptPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>(
      `script[src="${EXTERNAL_CHART_SCRIPT_URL}"]`,
    );
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () =>
        reject(new Error("External chart script failed")),
      );
      if (window.TradingView) resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = EXTERNAL_CHART_SCRIPT_URL;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("External chart script failed"));
    document.head.appendChild(script);
  });
  return scriptPromise;
}

/** Full Advanced Chart — for list view detail pane. */
export function ExternalChartEmbed({
  symbol,
  exchange,
  className,
  compact,
  height,
}: {
  symbol: string | null;
  exchange?: string | null;
  className?: string;
  compact?: boolean;
  height?: number;
}) {
  const reactId = useId().replace(/:/g, "");
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetRef = useRef<ExternalChartWidget | null>(null);
  const minHeight = height ?? (compact ? 220 : 260);
  const chartSymbol = symbol ? toExternalChartSymbol(symbol, exchange) : null;

  useEffect(() => {
    if (!chartSymbol || !containerRef.current) return;
    const host = containerRef.current;
    const containerId = `chart_${reactId}_${chartSymbol.replace(/[^A-Za-z0-9]/g, "_")}`;
    let cancelled = false;

    host.innerHTML = "";
    const mount = document.createElement("div");
    mount.id = containerId;
    mount.style.width = "100%";
    mount.style.height = "100%";
    host.appendChild(mount);

    void loadExternalChartSdk()
      .then(() => {
        if (cancelled || !window.TradingView) return;
        widgetRef.current = new window.TradingView.widget({
          autosize: true,
          symbol: chartSymbol,
          interval: "D",
          timezone: "America/New_York",
          theme: "dark",
          style: "1",
          locale: "en",
          toolbar_bg: "#131722",
          enable_publishing: false,
          hide_side_toolbar: true,
          hide_top_toolbar: Boolean(compact),
          allow_symbol_change: !compact,
          withdateranges: !compact,
          container_id: containerId,
        });
      })
      .catch(() => {
        if (!cancelled && host.isConnected) {
          host.innerHTML =
            '<div class="flex h-full items-center justify-center text-xs text-ink-muted">External chart failed to load</div>';
        }
      });

    return () => {
      cancelled = true;
      try {
        widgetRef.current?.remove?.();
      } catch {
        /* ignore */
      }
      widgetRef.current = null;
      host.innerHTML = "";
    };
  }, [chartSymbol, reactId, compact]);

  if (!symbol) {
    return (
      <div
        className={
          className ??
          "flex h-full min-h-[220px] items-center justify-center border-t border-line bg-[#131722] text-xs text-ink-faint"
        }
        style={{ minHeight }}
      >
        Select a row to open the chart
      </div>
    );
  }

  return (
    <div
      className={
        className ??
        (compact
          ? "border-t border-line bg-[#131722]"
          : "min-h-[260px] flex-1 border-t border-line bg-[#131722]")
      }
      style={{ minHeight: compact ? minHeight : undefined }}
    >
      <div
        ref={containerRef}
        className="h-full w-full"
        style={{ minHeight }}
      />
    </div>
  );
}
