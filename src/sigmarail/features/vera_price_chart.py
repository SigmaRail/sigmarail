"""Vera ClickHouse OHLCV charts for MCP / visualizer (Chart.js on jsdelivr CDN)."""

from __future__ import annotations

import json
import re
from typing import Any

SIGMARAIL_PRICE_CHART_MCP_APP_URI = "ui://vera/price-chart-v1.html"

_MAX_LOOKBACK = 504
_MIN_LOOKBACK = 20


def normalize_ticker(ticker: str) -> str:
    raw = (ticker or "").strip().upper()
    if not raw:
        raise ValueError("ticker is required")
    if ":" in raw:
        raw = raw.split(":", 1)[1]
    if not re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", raw):
        raise ValueError(f"unrecognized ticker format: {ticker!r}")
    return raw


def compute_rsi14(closes: list[float | None], *, period: int = 14) -> list[float | None]:
    """Wilder RSI; None until ``period`` bars exist."""
    n = len(closes)
    out: list[float | None] = [None] * n
    if n <= period:
        return out

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, period + 1):
        delta = (closes[i] or 0.0) - (closes[i - 1] or 0.0)
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        out[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        out[period] = 100.0 - (100.0 / (1.0 + rs))

    for i in range(period + 1, n):
        delta = (closes[i] or 0.0) - (closes[i - 1] or 0.0)
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            out[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100.0 - (100.0 / (1.0 + rs))
    return out


def query_l7_ohlcv(
    client: Any,
    ticker: str,
    *,
    lookback_days: int = 252,
) -> list[dict[str, Any]]:
    """Load daily OHLCV + SMA columns from ``screener_price_tech_daily``."""
    sym = normalize_ticker(ticker)
    lookback = max(_MIN_LOOKBACK, min(int(lookback_days), _MAX_LOOKBACK))

    result = client.query(
        """
        SELECT
            date,
            open,
            high,
            low,
            close AS close,
            sma50d,
            sma200d
        FROM screener_price_tech_daily FINAL
        WHERE ticker = %(ticker)s
          AND date >= (
              SELECT max(date) - toIntervalDay(%(lookback)s)
              FROM screener_price_tech_daily
              WHERE ticker = %(ticker)s
          )
        ORDER BY date ASC
        LIMIT %(limit)s
        """,
        parameters={"ticker": sym, "lookback": lookback, "limit": lookback + 10},
    )
    rows: list[dict[str, Any]] = []
    for row in result.result_rows:
        rec = dict(zip(result.column_names, row))
        d = rec.get("date")
        rows.append(
            {
                "date": d.isoformat() if hasattr(d, "isoformat") else str(d),
                "open": rec.get("open"),
                "high": rec.get("high"),
                "low": rec.get("low"),
                "close": rec.get("close"),
                "sma50": rec.get("sma50d"),
                "sma200": rec.get("sma200d"),
            }
        )
    if not rows:
        raise ValueError(f"no screener_price_tech_daily rows for ticker {sym!r} in lookback window")
    return rows


def _series_points(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in rows:
        v = r.get(key)
        if v is None:
            continue
        out.append({"x": r["date"], "y": float(v)})
    return out


def _chartjs_payload(
    ticker: str,
    rows: list[dict[str, Any]],
    *,
    show_rsi: bool = True,
    theme: str = "dark",
) -> dict[str, Any]:
    dates: list[str] = []
    closes: list[float] = []
    sma50: list[float | None] = []
    sma200: list[float | None] = []
    for r in rows:
        c = r.get("close")
        if c is None:
            continue
        dates.append(r["date"])
        closes.append(float(c))
        sma50.append(float(r["sma50"]) if r.get("sma50") is not None else None)
        sma200.append(float(r["sma200"]) if r.get("sma200") is not None else None)
    if not dates:
        raise ValueError("no close prices in range")

    rsi_all = compute_rsi14(closes)
    rsi_vals = [float(v) if v is not None else None for v in rsi_all]

    return {
        "ticker": normalize_ticker(ticker),
        "dates": dates,
        "closes": closes,
        "sma50": sma50,
        "sma200": sma200,
        "rsi": rsi_vals,
        "showRsi": show_rsi,
        "theme": theme,
    }


def chartjs_price_chart_html(
    ticker: str,
    rows: list[dict[str, Any]],
    *,
    theme: str = "dark",
    height: int = 520,
    show_rsi: bool = True,
) -> str:
    """Self-contained HTML: close line + SMA50/200 + RSI (Chart.js core only)."""
    theme_key = (theme or "dark").strip().lower()
    if theme_key not in ("dark", "light"):
        raise ValueError("theme must be 'dark' or 'light'")
    height = max(360, min(int(height), 900))
    payload = _chartjs_payload(ticker, rows, show_rsi=show_rsi, theme=theme_key)
    data_json = json.dumps(payload, separators=(",", ":"))
    bg = "#131722" if theme_key == "dark" else "#ffffff"
    fg = "#d1d4dc" if theme_key == "dark" else "#131722"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{payload["ticker"]} — Vera screener_price_tech_daily</title>
  <style>
    html, body {{ margin: 0; padding: 8px; background: {bg}; color: {fg}; font: 13px system-ui, sans-serif; }}
    .wrap {{ height: {height}px; display: flex; flex-direction: column; gap: 8px; }}
    #price {{ flex: 3 1 0; min-height: 200px; }}
    #rsi {{ flex: 1 1 0; min-height: 80px; }}
    .cap {{ opacity: 0.7; font-size: 11px; }}
  </style>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
</head>
<body>
  <div class="cap">Vera ClickHouse · screener_price_tech_daily · Chart.js</div>
  <div class="wrap">
    <canvas id="price"></canvas>
    <canvas id="rsi"></canvas>
  </div>
  <script>
    const DATA = {data_json};
    const dark = DATA.theme === "dark";
    Chart.defaults.color = dark ? "#d1d4dc" : "#131722";
    Chart.defaults.borderColor = dark ? "#2a2e39" : "#e0e0e0";

    function lineData(values) {{
      return DATA.dates.map((d, i) => (values[i] == null ? null : {{ x: d, y: values[i] }}));
    }}

    new Chart(document.getElementById("price"), {{
      type: "line",
      data: {{
        datasets: [
          {{ label: DATA.ticker + " close", data: lineData(DATA.closes), borderColor: "#3b82f6", pointRadius: 0, borderWidth: 1.5 }},
          {{ label: "SMA50", data: lineData(DATA.sma50), borderColor: "#f59e0b", pointRadius: 0, borderWidth: 1.2 }},
          {{ label: "SMA200", data: lineData(DATA.sma200), borderColor: "#8b5cf6", pointRadius: 0, borderWidth: 1.2 }},
        ],
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        parsing: false,
        plugins: {{ legend: {{ position: "top" }} }},
        scales: {{ x: {{ type: "category" }}, y: {{ position: "right" }} }},
      }},
    }});

    if (DATA.showRsi) {{
      new Chart(document.getElementById("rsi"), {{
        type: "line",
        data: {{ datasets: [{{ label: "RSI14", data: lineData(DATA.rsi), borderColor: "#22c55e", pointRadius: 0, borderWidth: 1.2 }}] }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          parsing: false,
          plugins: {{ legend: {{ display: false }} }},
          scales: {{ x: {{ display: false }}, y: {{ min: 0, max: 100 }} }},
        }},
      }});
    }} else {{
      document.getElementById("rsi").style.display = "none";
    }}
  </script>
</body>
</html>
"""


def vera_price_mcp_app_resource_meta() -> dict[str, Any]:
    return {
        "ui": {
            "csp": {
                "resourceDomains": ["https://cdn.jsdelivr.net"],
                "connectDomains": [],
            }
        }
    }


def vera_price_mcp_app_html() -> str:
    """MCP App shell: applies ``structuredContent.html`` from vera_price_chart_embed."""
    return """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8" />
<style>html,body{margin:0;background:#131722;color:#d1d4dc;font:13px system-ui,sans-serif}#status{padding:8px 12px}.err{color:#f23645}</style>
</head><body><div id="status">Waiting for Vera chart…</div>
<script>
(function(){
  var mounted=false, statusEl=document.getElementById("status");
  function setStatus(m,e){statusEl.textContent=m;statusEl.className=e?"err":"";}
  function norm(raw){
    if(!raw||typeof raw!=="object")return null;
    if(typeof raw.html==="string"&&raw.html.length)return raw;
    if(raw.structuredContent)return norm(raw.structuredContent);
    return null;
  }
  function apply(raw){
    var p=norm(raw);
    if(!p){setStatus("No html in tool result",true);return;}
    if(p.html){document.open();document.write(p.html);document.close();mounted=true;setStatus((p.ticker||"Chart")+" · "+(p.bar_count||"?")+" bars");return;}
    setStatus("Missing html field",true);
  }
  function boot(){var o=window.openai;if(!o)return false;var r=o.toolOutput||o.structuredContent;if(r){apply(r);return true;}return false;}
  window.addEventListener("openai:set_globals",function(e){
    var r=e.detail&&e.detail.globals?(e.detail.globals.toolOutput||e.detail.globals.structuredContent):null;
    if(r)apply(r);
  },{passive:true});
  window.addEventListener("message",function(e){
    if(e.source!==window.parent)return;
    var m=e.data;if(!m||m.jsonrpc!=="2.0"||m.method!=="ui/notifications/tool-result")return;
    if(m.params&&m.params.structuredContent)apply(m.params.structuredContent);
  },{passive:true});
  if(!boot()){var n=0,t=setInterval(function(){n++;if(mounted||boot())clearInterval(t);else if(n>=40){clearInterval(t);if(!mounted)setStatus("No toolOutput from host",true);}},250);}
})();
</script></body></html>"""


def vera_price_chart_embed_payload(
    client: Any,
    ticker: str,
    *,
    lookback_days: int = 252,
    theme: str = "dark",
    height: int = 520,
    show_rsi: bool = True,
) -> dict[str, Any]:
    """MCP payload: bars from ClickHouse + Chart.js HTML for browser / visualizer."""
    sym = normalize_ticker(ticker)
    rows = query_l7_ohlcv(client, sym, lookback_days=lookback_days)
    html = chartjs_price_chart_html(
        sym, rows, theme=theme, height=height, show_rsi=show_rsi
    )
    date_from = rows[0]["date"]
    date_to = rows[-1]["date"]
    return {
        "ticker": sym,
        "lookback_days": lookback_days,
        "date_from": date_from,
        "date_to": date_to,
        "bar_count": len(rows),
        "data_source": "vera_clickhouse_screener_price_tech_daily",
        "attribution": "OHLCV and SMA from Vera ClickHouse screener_price_tech_daily; RSI14 computed in vera_price_chart.",
        "mcp_app_uri": SIGMARAIL_PRICE_CHART_MCP_APP_URI,
        "visualizer_note": (
            "MCP App: ui://vera/price-chart-v1.html. Chart.js on cdn.jsdelivr.net only (no candlestick plugin)."
        ),
        "chart_series": {
            "candles": [
                {
                    "date": r["date"],
                    "open": r.get("open"),
                    "high": r.get("high"),
                    "low": r.get("low"),
                    "close": r.get("close"),
                }
                for r in rows
            ],
            "sma50": [r.get("sma50") for r in rows],
            "sma200": [r.get("sma200") for r in rows],
        },
        "html": html,
    }
