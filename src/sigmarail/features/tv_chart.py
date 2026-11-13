"""TradingView embed widget HTML for MCP (market data from TradingView; no Vera datafeed)."""

from __future__ import annotations

import json
import re
from typing import Any

# MCP Apps UI resource (``text/html;profile=mcp-app``). Bump suffix when HTML breaks compat.
TV_CHART_MCP_APP_URI = "ui://vera/tv-chart-v2.html"
# Legacy alias — hosts/chats that cached v1 still resolve the same shell.
TV_CHART_MCP_APP_URI_V1 = "ui://vera/tv-chart-v1.html"

# Common US listings when user passes bare ticker (extend as needed).
_EXCHANGE_PREFIX: dict[str, str] = {
    "SPY": "AMEX",
    "QQQ": "NASDAQ",
    "IWM": "AMEX",
    "DIA": "AMEX",
    "GLD": "AMEX",
    "SLV": "AMEX",
}


def normalize_tv_symbol(symbol: str, *, default_exchange: str = "NASDAQ") -> str:
    """Return TradingView symbol id, e.g. NASDAQ:NVDA."""
    raw = (symbol or "").strip().upper()
    if not raw:
        raise ValueError("symbol is required")
    if ":" in raw:
        return raw
    prefix = _EXCHANGE_PREFIX.get(raw, default_exchange)
    if re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", raw):
        return f"{prefix}:{raw}"
    raise ValueError(f"unrecognized ticker format: {symbol!r}")


def _validate_chart_params(
    symbol: str,
    *,
    interval: str,
    theme: str,
    height: int,
) -> tuple[str, str, str, int]:
    tv_symbol = normalize_tv_symbol(symbol)
    interval_key = (interval or "D").strip().upper()
    if interval_key not in ("1", "5", "15", "30", "60", "240", "D", "W", "M"):
        raise ValueError(
            "interval must be one of 1, 5, 15, 30, 60, 240, D, W, M (TradingView widget)"
        )
    theme_key = (theme or "dark").strip().lower()
    if theme_key not in ("dark", "light"):
        raise ValueError("theme must be 'dark' or 'light'")
    height_px = max(320, min(int(height), 900))
    return tv_symbol, interval_key, theme_key, height_px


def tv_widget_config(
    symbol: str,
    *,
    interval: str = "D",
    theme: str = "dark",
    studies: list[str] | None = None,
    hide_side_toolbar: bool = True,
) -> dict[str, Any]:
    """TradingView Advanced Chart widget JSON (passed to their embed script)."""
    tv_symbol, interval_key, theme_key, _ = _validate_chart_params(
        symbol, interval=interval, theme=theme, height=480
    )
    widget_config: dict[str, Any] = {
        "autosize": True,
        "symbol": tv_symbol,
        "interval": interval_key,
        "timezone": "America/New_York",
        "theme": theme_key,
        "style": "1",
        "locale": "en",
        "allow_symbol_change": True,
        "calendar": False,
        "hide_side_toolbar": hide_side_toolbar,
        "hide_top_toolbar": False,
        "hide_legend": False,
        "hide_volume": False,
        "support_host": "https://www.tradingview.com",
    }
    if studies:
        widget_config["studies"] = studies
    return widget_config


def tv_advanced_chart_embed_html(
    symbol: str,
    *,
    interval: str = "D",
    theme: str = "dark",
    height: int = 480,
    studies: list[str] | None = None,
    hide_side_toolbar: bool = True,
) -> str:
    """Self-contained HTML with TradingView Advanced Chart widget (their CDN + data)."""
    tv_symbol, interval_key, theme_key, height_px = _validate_chart_params(
        symbol, interval=interval, theme=theme, height=height
    )
    widget_config = tv_widget_config(
        symbol,
        interval=interval_key,
        theme=theme_key,
        studies=studies,
        hide_side_toolbar=hide_side_toolbar,
    )
    config_json = json.dumps(widget_config, separators=(",", ":"))
    # TradingView expects script body = JSON config (see widget docs).
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{tv_symbol} — TradingView</title>
  <style>
    html, body {{ margin: 0; padding: 0; background: {"#131722" if theme_key == "dark" else "#fff"}; }}
    .wrap {{ height: {height_px}px; width: 100%; }}
  </style>
</head>
<body>
  <div class="tradingview-widget-container wrap">
    <div class="tradingview-widget-container__widget" style="height:calc(100% - 32px);width:100%"></div>
    <div class="tradingview-widget-copyright">
      <a href="https://www.tradingview.com/symbols/{tv_symbol.replace(":", "-")}/" rel="noopener nofollow" target="_blank">
        <span class="blue-text">{tv_symbol} chart</span>
      </a>
      <span class="trademark"> by TradingView</span>
    </div>
    <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" async>
{config_json}
    </script>
  </div>
</body>
</html>
"""


def tv_mcp_app_resource_meta() -> dict[str, Any]:
    """``_meta`` for the MCP App HTML resource (CSP allowlist for TradingView CDN)."""
    return {
        "ui": {
            "csp": {
                "resourceDomains": [
                    "https://s3.tradingview.com",
                    "https://www.tradingview.com",
                    "https://cdn.jsdelivr.net",
                ],
                "connectDomains": ["https://www.tradingview.com"],
            }
        }
    }


def tv_mcp_app_html() -> str:
    """Static MCP App shell: mounts TV widget from host ``structuredContent``."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Vera — TradingView</title>
  <style>
    html, body { margin: 0; padding: 0; background: #131722; color: #d1d4dc; font: 13px/1.4 system-ui, sans-serif; }
    #status { padding: 8px 12px; }
    .wrap { height: min(70vh, 520px); width: 100%; }
    .err { color: #f23645; }
  </style>
</head>
<body>
  <div id="status">Waiting for chart data…</div>
  <div class="tradingview-widget-container wrap">
    <div class="tradingview-widget-container__widget" style="height:calc(100% - 32px);width:100%"></div>
    <div class="tradingview-widget-copyright" id="tv-copy"></div>
  </div>
  <script>
    (function () {
      const statusEl = document.getElementById("status");
      const copyEl = document.getElementById("tv-copy");
      let mounted = false;

      function setStatus(msg, isErr) {
        statusEl.textContent = msg;
        statusEl.className = isErr ? "err" : "";
      }

      function normalizePayload(raw) {
        if (!raw || typeof raw !== "object") return null;
        if (typeof raw.html === "string" && raw.html.length > 0) return raw;
        if (raw.widget_config) return raw;
        if (raw.structuredContent) return normalizePayload(raw.structuredContent);
        return null;
      }

      function mountChart(data) {
        const payload = normalizePayload(data);
        if (!payload) {
          setStatus("No html or widget_config in tool result", true);
          return;
        }
        if (payload.html) {
          document.open();
          document.write(payload.html);
          document.close();
          mounted = true;
          setStatus((payload.symbol || "Chart") + " · HTML embed");
          return;
        }
        const cfg = payload.widget_config;
        const sym = payload.symbol || cfg.symbol || "—";
        document.body.style.background = payload.theme === "light" ? "#fff" : "#131722";
        copyEl.innerHTML =
          '<a href="https://www.tradingview.com/symbols/' +
          String(sym).replace(":", "-") +
          '/" rel="noopener nofollow" target="_blank"><span class="blue-text">' +
          sym + " chart</span></a><span class=\"trademark\"> by TradingView</span>";
        const host = document.querySelector(".tradingview-widget-container");
        const old = host.querySelector("script[data-vera-tv]");
        if (old) old.remove();
        const script = document.createElement("script");
        script.type = "text/javascript";
        script.async = true;
        script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
        script.setAttribute("data-vera-tv", "1");
        script.appendChild(document.createTextNode(JSON.stringify(cfg)));
        host.appendChild(script);
        mounted = true;
        setStatus(sym + " · " + (payload.interval || cfg.interval || "D"));
      }

      function tryBoot() {
        const o = window.openai;
        if (!o) return false;
        const raw = o.toolOutput || o.structuredContent;
        if (raw) {
          mountChart(raw);
          return true;
        }
        return false;
      }

      window.addEventListener(
        "openai:set_globals",
        function (event) {
          const raw = event.detail && event.detail.globals
            ? (event.detail.globals.toolOutput || event.detail.globals.structuredContent)
            : null;
          if (raw) mountChart(raw);
        },
        { passive: true }
      );

      window.addEventListener(
        "message",
        function (event) {
          if (event.source !== window.parent) return;
          const msg = event.data;
          if (!msg || msg.jsonrpc !== "2.0") return;
          if (msg.method !== "ui/notifications/tool-result") return;
          const sc = msg.params && msg.params.structuredContent;
          if (sc) mountChart(sc);
        },
        { passive: true }
      );

      if (!tryBoot()) {
        var polls = 0;
        var timer = setInterval(function () {
          polls += 1;
          if (mounted || tryBoot()) {
            clearInterval(timer);
            return;
          }
          if (polls >= 40) {
            clearInterval(timer);
            if (!mounted) {
              setStatus(
                "No chart data from host (openai.toolOutput / tool-result). Check MCP App CSP.",
                true
              );
            }
          }
        }, 250);
      }
    })();
  </script>
</body>
</html>
"""


def tv_chart_structured_content(
    symbol: str,
    *,
    interval: str = "D",
    theme: str = "dark",
    height: int = 480,
    studies: list[str] | None = None,
) -> dict[str, Any]:
    """Payload for MCP App ``structuredContent`` (no full HTML blob)."""
    tv_symbol, interval_key, theme_key, height_px = _validate_chart_params(
        symbol, interval=interval, theme=theme, height=height
    )
    return {
        "symbol_input": symbol.strip(),
        "symbol": tv_symbol,
        "interval": interval_key,
        "theme": theme_key,
        "height": height_px,
        "data_source": "tradingview_widget",
        "widget_config": tv_widget_config(
            symbol,
            interval=interval_key,
            theme=theme_key,
            studies=studies,
        ),
    }


def tv_chart_embed_payload(
    symbol: str,
    *,
    interval: str = "D",
    theme: str = "dark",
    height: int = 480,
    studies: list[str] | None = None,
) -> dict[str, Any]:
    """MCP-friendly dict: metadata + html for browser preview; includes structured fields."""
    structured = tv_chart_structured_content(
        symbol,
        interval=interval,
        theme=theme,
        height=height,
        studies=studies,
    )
    html = tv_advanced_chart_embed_html(
        symbol,
        interval=structured["interval"],
        theme=structured["theme"],
        height=structured["height"],
        studies=studies,
    )
    return {
        **structured,
        "mcp_app_uri": TV_CHART_MCP_APP_URI,
        "attribution": "Chart by TradingView; market data from TradingView (not Vera ClickHouse).",
        "preview_note": (
            "Hosts with MCP Apps render ui://vera/tv-chart-v2.html in an iframe. "
            "Otherwise open html in a browser (requires s3.tradingview.com)."
        ),
        "html": html,
    }
