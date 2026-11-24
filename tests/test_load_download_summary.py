"""Unit tests for sigmarail-load download summary helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

import pandas as pd

from sigmarail.load import earliest_date_from_csv, format_download_earliest_date, main


def test_earliest_date_from_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "SHARADAR_DAILY_2026-06-01.csv"
    pd.DataFrame(
        {"date": ["2026-06-03", "2026-06-01", "2026-06-02"], "close": [1, 2, 3]}
    ).to_csv(csv_path, index=False)
    assert earliest_date_from_csv(csv_path, "date") == "2026-06-01"


def test_earliest_date_from_csv_empty_file(tmp_path: Path) -> None:
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("date,close\n", encoding="utf-8")
    assert earliest_date_from_csv(csv_path, "date") is None


def test_earliest_date_from_csv_no_date_field(tmp_path: Path) -> None:
    csv_path = tmp_path / "source_without_date.csv"
    csv_path.write_text("table,indicator\nx,y\n", encoding="utf-8")
    assert earliest_date_from_csv(csv_path, None) is None


def test_format_download_earliest_date() -> None:
    assert format_download_earliest_date("2026-01-01", has_date_field=True) == "2026-01-01"
    assert format_download_earliest_date(None, has_date_field=True) == "-"
    assert format_download_earliest_date(None, has_date_field=False) == "n/a"


def test_main_reports_download_failure_even_when_existing_csvs_load(monkeypatch) -> None:
    loader = MagicMock()
    loader.SHARADAR_TABLES = {"SEP": {"date_field": "lastupdated"}}
    loader.download_data.side_effect = RuntimeError("Sharadar unavailable")
    loader.load_csv_files.return_value = True
    monkeypatch.setattr(sys, "argv", ["sigmarail-load", "--download", "--tables", "SEP", "--no-splice"])

    with (
        patch("sigmarail.load.DataLoader", return_value=loader),
        patch("sigmarail.load.process_shared_args"),
        patch("sigmarail.load.optimize_tables", return_value=True),
        patch("sigmarail.load._print_event_summary"),
    ):
        assert main() == 1

    loader.load_csv_files.assert_called_once_with(tables=["sep"])
