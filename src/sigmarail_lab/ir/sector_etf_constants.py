"""ETF map and universe constants for the sector ETF allocation model.

Separated from qc_sector_etf.py so they can be imported outside the LEAN container
(e.g. in sector_etf_ir.py for spec building).
"""

from __future__ import annotations

DEFAULT_ETF_MAP: dict[str, dict[str, str | None]] = {
    "Technology": {
        "base": "XLK",
        "2x":   "ROM",
        "3x":   "TECL",
        "inverse": "REW",
    },
    "Healthcare": {
        "base": "XLV",
        "2x":   "CURE",
        "3x":   "CURE",
        "inverse": "LABD",
    },
    "Financial Services": {
        "base": "XLF",
        "2x":   "UYG",
        "3x":   "FAS",
        "inverse": "SKF",
    },
    "Consumer Cyclical": {
        "base": "XLY",
        "2x":   "UCC",
        "3x":   None,
        "inverse": None,
    },
    "Consumer Defensive": {
        "base": "XLP",
        "2x":   "UGE",
        "3x":   None,
        "inverse": None,
    },
    "Energy": {
        "base": "XLE",
        "2x":   "ERX",
        "3x":   None,
        "inverse": "DRIP",
    },
    "Industrials": {
        "base": "XLI",
        "2x":   None,
        "3x":   None,
        "inverse": None,
    },
    "Basic Materials": {
        "base": "XLB",
        "2x":   None,
        "3x":   None,
        "inverse": "SMN",
    },
    "Utilities": {
        "base": "XLU",
        "2x":   None,
        "3x":   None,
        "inverse": "SDP",
    },
    "Real Estate": {
        "base": "XLRE",
        "2x":   "URE",
        "3x":   None,
        "inverse": "DRV",
    },
    "Communication Services": {
        "base": "XLC",
        "2x":   None,
        "3x":   None,
        "inverse": None,
    },
}

DEFAULT_ETF_UNIVERSE: list[str] = sorted({
    sym
    for entry in DEFAULT_ETF_MAP.values()
    for sym in entry.values()
    if sym is not None
})
