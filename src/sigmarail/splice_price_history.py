"""Scale sep/sfp bars older than a 5y (or download) window after Sharadar restatements.

When the subscription only delivers ~5 years of restated prices, older ClickHouse
rows stay on the previous share basis. Before loading a new CSV batch, compare
close/closeadj on the oldest date in the batch (overlap) and INSERT scaled copies
of all prior bars (ReplacingMergeTree). Leave closeunadj unchanged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

PRICE_TABLES = frozenset({"sep", "sfp"})
_EPS = 1e-9


@dataclass(frozen=True)
class SpliceFactor:
    ticker: str
    splice_date: str
    px_factor: float
    tr_factor: float

    @property
    def needs_splice(self) -> bool:
        return abs(self.px_factor - 1.0) > 1e-6 or abs(self.tr_factor - 1.0) > 1e-6


def compute_splice_factor(
    *,
    ch_close: float,
    ch_closeadj: float,
    new_close: float,
    new_closeadj: float,
    ticker: str,
    splice_date: str,
) -> Optional[SpliceFactor]:
    """Build factors from one overlapping session. None if inputs invalid."""
    try:
        ch_c = float(ch_close)
        ch_a = float(ch_closeadj)
        new_c = float(new_close)
        new_a = float(new_closeadj)
    except (TypeError, ValueError):
        return None
    if ch_c <= _EPS or ch_a <= _EPS or new_c <= _EPS or new_a <= _EPS:
        return None
    return SpliceFactor(
        ticker=str(ticker).strip().upper(),
        splice_date=str(splice_date)[:10],
        px_factor=new_c / ch_c,
        tr_factor=new_a / ch_a,
    )


def factors_from_download_vs_ch(
    new_df: pd.DataFrame,
    ch_rows: Sequence[Tuple[Any, ...]],
) -> List[SpliceFactor]:
    """
    Match download rows to CH (ticker, date, close, closeadj) on the per-ticker
    oldest date present in *new_df*.
    """
    if new_df is None or new_df.empty:
        return []
    need = {"ticker", "date", "close", "closeadj"}
    if not need.issubset(set(new_df.columns)):
        logger.warning("splice: download CSV missing columns %s", need - set(new_df.columns))
        return []

    work = new_df.copy()
    work["ticker"] = work["ticker"].astype(str).str.strip().str.upper()
    work["date"] = work["date"].astype(str).str.slice(0, 10)
    # Oldest date per ticker in the download (= window edge for that name).
    idx = work.groupby("ticker", sort=False)["date"].idxmin()
    edge = work.loc[idx]

    ch_map: Dict[Tuple[str, str], Tuple[float, float]] = {}
    for row in ch_rows:
        if len(row) < 4:
            continue
        t = str(row[0]).strip().upper()
        d = str(row[1])[:10]
        try:
            ch_map[(t, d)] = (float(row[2]), float(row[3]))
        except (TypeError, ValueError):
            continue

    out: List[SpliceFactor] = []
    for _, r in edge.iterrows():
        key = (str(r["ticker"]), str(r["date"])[:10])
        if key not in ch_map:
            continue
        ch_c, ch_a = ch_map[key]
        fac = compute_splice_factor(
            ch_close=ch_c,
            ch_closeadj=ch_a,
            new_close=r["close"],
            new_closeadj=r["closeadj"],
            ticker=key[0],
            splice_date=key[1],
        )
        if fac is not None and fac.needs_splice:
            out.append(fac)
    return out


def _escape_str(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def build_splice_insert_sql(
    table: str,
    factors: Sequence[SpliceFactor],
) -> Optional[str]:
    """
    INSERT scaled older bars. closeunadj unchanged; lastupdated = now().

    OHLC *= px_factor; volume /= px_factor; closeadj *= tr_factor.
    """
    table = table.lower().strip()
    if table not in PRICE_TABLES or not factors:
        return None

    selects: List[str] = []
    for f in factors:
        if not f.needs_splice:
            continue
        selects.append(
            "SELECT "
            f"'{_escape_str(f.ticker)}' AS ticker, "
            f"toDate('{_escape_str(f.splice_date)}') AS splice_date, "
            f"{float(f.px_factor)} AS px_factor, "
            f"{float(f.tr_factor)} AS tr_factor"
        )
    if not selects:
        return None

    factors_sql = "\n    UNION ALL\n    ".join(selects)
    return f"""
INSERT INTO {table} (
    ticker, date, open, high, low, close, volume, closeadj, closeunadj, lastupdated
)
WITH factors AS (
    {factors_sql}
)
SELECT
    p.ticker,
    p.date,
    p.open * f.px_factor,
    p.high * f.px_factor,
    p.low * f.px_factor,
    p.close * f.px_factor,
    p.volume / f.px_factor,
    p.closeadj * f.tr_factor,
    p.closeunadj,
    now('America/New_York') AS lastupdated
FROM {table} AS p FINAL
INNER JOIN factors AS f ON f.ticker = p.ticker
WHERE p.date < f.splice_date
SETTINGS max_threads = 4
""".strip()


def fetch_ch_overlap_rows(
    client: Any,
    table: str,
    pairs: Iterable[Tuple[str, str]],
) -> List[Tuple[Any, ...]]:
    """SELECT ticker, date, close, closeadj for (ticker, date) pairs from CH."""
    table = table.lower().strip()
    if table not in PRICE_TABLES:
        return []
    pair_list = [(str(t).upper(), str(d)[:10]) for t, d in pairs]
    if not pair_list:
        return []
    # Chunk to keep query size bounded.
    out: List[Tuple[Any, ...]] = []
    chunk_size = 500
    for i in range(0, len(pair_list), chunk_size):
        chunk = pair_list[i : i + chunk_size]
        tuples = ", ".join(
            f"('{_escape_str(t)}', toDate('{_escape_str(d)}'))" for t, d in chunk
        )
        sql = f"""
SELECT ticker, date, close, closeadj
FROM {table} FINAL
WHERE (ticker, date) IN ({tuples})
"""
        result = client.query(sql)
        out.extend(list(result.result_rows or []))
    return out


def splice_older_bars_from_csv(
    client: Any,
    table: str,
    csv_path: Path,
    *,
    dry_run: bool = False,
) -> int:
    """
    Compare download CSV to CH on per-ticker min(date); INSERT scaled older bars.

    Returns number of tickers spliced (factors applied). Does not modify the CSV.
    """
    table = table.lower().strip()
    if table not in PRICE_TABLES:
        return 0
    path = Path(csv_path)
    if not path.is_file() or path.stat().st_size == 0:
        return 0

    try:
        new_df = pd.read_csv(path, usecols=["ticker", "date", "close", "closeadj"])
    except (ValueError, pd.errors.EmptyDataError) as exc:
        logger.warning("splice: could not read %s: %s", path, exc)
        return 0
    if new_df.empty:
        return 0

    work = new_df.copy()
    work["ticker"] = work["ticker"].astype(str).str.strip().str.upper()
    work["date"] = work["date"].astype(str).str.slice(0, 10)
    edge = work.loc[work.groupby("ticker", sort=False)["date"].idxmin()]
    pairs = [(r["ticker"], r["date"]) for _, r in edge.iterrows()]

    ch_rows = fetch_ch_overlap_rows(client, table, pairs)
    factors = factors_from_download_vs_ch(work, ch_rows)
    if not factors:
        logger.info("splice: no factor drift for %s from %s", table, path.name)
        return 0

    sql = build_splice_insert_sql(table, factors)
    if not sql:
        return 0

    logger.info(
        "splice: applying %s ticker factor(s) on %s older than overlap (e.g. %s @ %s px=%.6f tr=%.6f)",
        len(factors),
        table,
        factors[0].ticker,
        factors[0].splice_date,
        factors[0].px_factor,
        factors[0].tr_factor,
    )
    if dry_run:
        return len(factors)

    client.command(sql)
    return len(factors)


def splice_downloaded_price_csvs(
    client: Any,
    data_dir: Path,
    tables: Optional[Sequence[str]] = None,
    *,
    dry_run: bool = False,
) -> Dict[str, int]:
    """Run splice for SEP/SFP CSVs under data_dir matching SHARADAR_{TABLE}_*."""
    wanted = {t.lower() for t in tables} if tables else {"sep", "sfp"}
    wanted &= PRICE_TABLES
    counts: Dict[str, int] = {}
    for table in sorted(wanted):
        pattern = f"SHARADAR_{table.upper()}_*.csv*"
        files = sorted(Path(data_dir).glob(pattern))
        total = 0
        for fp in files:
            if fp.suffix == ".gz":
                continue  # rare; skip compressed for splice compare
            total += splice_older_bars_from_csv(client, table, fp, dry_run=dry_run)
        counts[table] = total
    return counts
