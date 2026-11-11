"""Direct sharadar.com REST client (not Nasdaq Data Link).

Canon: https://sharadar.com/llms.txt — base ``https://api.sharadar.com/v1.0``,
legacy table codes (SEP/SFP/SF1) still work on ``GET /data/{table}``.
"""

from __future__ import annotations

import io
import logging
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from sigmarail.config import SharadarConfig, get_sharadar_config, normalize_sharadar_base_url

logger = logging.getLogger(__name__)

DEFAULT_PAGE_LIMIT = 10_000

# Query filter values for dual TICKERS download (stocks + funds).
TICKERS_QUERY_TABLE = {
    "SEP": "stocks",
    "SFP": "funds",
}


def api_table_name(code: str) -> str:
    """Map internal loader codes to Sharadar /data/{table} path segments."""
    raw = (code or "").strip()
    if raw.upper().startswith("SHARADAR/"):
        raw = raw.split("/", 1)[1]
    return raw.upper()


def download_table_with_pagination(
    code: str,
    output_path: Path,
    api_key: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    base_url: Optional[str] = None,
    page_limit: int = DEFAULT_PAGE_LIMIT,
) -> int:
    """
    Download a Sharadar table via REST JSON + skip/limit pagination, or bulk zip.

    When ``params`` contains ``years`` (5|10|full), follow the 302 zip redirect
    instead of paging (llms.txt: do not page a full table with limit/skip).
    """
    if params is None:
        params = {}
    cfg_base = base_url
    if cfg_base is None:
        cfg_base = get_sharadar_config().base_url
    root = normalize_sharadar_base_url(cfg_base)
    table = api_table_name(code)
    url = f"{root}/data/{table}"

    years = params.get("years")
    if years is not None:
        return _download_bulk_zip(
            url=url,
            output_path=output_path,
            api_key=api_key,
            years=str(years),
            extra_params={k: v for k, v in params.items() if k != "years"},
        )

    query: Dict[str, Any] = dict(params)
    query["api_key"] = api_key
    query["format"] = query.get("format") or "json"
    query["limit"] = int(query.get("limit") or page_limit)

    all_frames: List[pd.DataFrame] = []
    skip = int(query.pop("skip", 0) or 0)
    page_num = 1

    while True:
        page_params = dict(query)
        page_params["skip"] = skip
        logger.info("Fetching page %s for %s (skip=%s)...", page_num, table, skip)
        response = requests.get(url, params=page_params, timeout=120)
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("data") or []
        if not rows:
            logger.info("No more data for %s. Download complete.", table)
            break
        all_frames.append(pd.DataFrame(rows))
        if len(rows) < int(page_params["limit"]):
            logger.info("Last page reached for %s.", table)
            break
        skip += len(rows)
        page_num += 1
        time.sleep(0.05)

    if not all_frames:
        logger.warning("No data was downloaded for %s with the given parameters.", table)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame().to_csv(output_path, index=False)
        return 0

    df = pd.concat(all_frames, ignore_index=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    logger.info("Successfully downloaded %s rows and saved to %s", len(df), output_path)
    return len(df)


def _download_bulk_zip(
    *,
    url: str,
    output_path: Path,
    api_key: str,
    years: str,
    extra_params: Dict[str, Any],
) -> int:
    params = dict(extra_params)
    params["api_key"] = api_key
    params["years"] = years
    logger.info("Bulk download %s years=%s ...", url, years)
    response = requests.get(url, params=params, timeout=600, allow_redirects=True)
    response.raise_for_status()
    content_type = (response.headers.get("Content-Type") or "").lower()
    raw = response.content
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if "zip" in content_type or raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not names:
                raise RuntimeError(f"Bulk zip for {url} contained no CSV")
            with zf.open(names[0]) as fh:
                df = pd.read_csv(fh)
    else:
        text = response.text
        if text.lstrip().startswith("{"):
            raise RuntimeError(
                f"Bulk years={years} did not return a zip (got JSON). "
                "Check subscription history entitlement."
            )
        df = pd.read_csv(io.StringIO(text))

    df.to_csv(output_path, index=False)
    logger.info("Bulk download saved %s rows to %s", len(df), output_path)
    return len(df)


def resolve_sharadar_auth(cfg: Optional[SharadarConfig] = None) -> SharadarConfig:
    return cfg or get_sharadar_config()
