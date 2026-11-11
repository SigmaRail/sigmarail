"""
Command-line interface for loading data into ClickHouse.
"""

import logging
import argparse
import os
import glob
import shutil
import zipfile
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional, Dict, Any, List, Sequence, Tuple, Union
import pandas as pd

from sigmarail.database import load_single_csv
from sigmarail.database import get_client, optimize_tables
from sigmarail.config import (
    app_config,
    create_shared_parser,
    get_data_config,
    get_database_config,
    get_project_root,
    get_sharadar_config,
    process_shared_args,
)
from sigmarail.sharadar_client import (
    TICKERS_QUERY_TABLE,
    download_table_with_pagination,
)
from sigmarail.splice_price_history import splice_downloaded_price_csvs

logger = logging.getLogger(__name__)


def parse_ticker_list(values: Optional[Sequence[str]]) -> List[str]:
    """Normalize CLI/API ticker args (comma-separated and/or repeated)."""
    if not values:
        return []
    out: List[str] = []
    seen: set[str] = set()
    for raw in values:
        for part in str(raw).split(","):
            ticker = part.strip().upper()
            if ticker and ticker not in seen:
                seen.add(ticker)
                out.append(ticker)
    return out


def _ticker_slug(tickers: Sequence[str]) -> str:
    items = [t.strip().upper() for t in tickers if t and str(t).strip()]
    if not items:
        return "tickers"
    if len(items) == 1:
        return items[0]
    if len(items) <= 3:
        return "_".join(items)
    return "_".join(items[:3]) + f"_x{len(items)}"


def earliest_date_from_csv(csv_path: Path, date_field: Optional[str]) -> Optional[str]:
    """
    Return the earliest value of *date_field* in a downloaded CSV.

    Used in the download summary so populate start-date can be validated against
    what was actually fetched in this run.
    """
    if not date_field or not csv_path.is_file():
        return None
    try:
        if csv_path.stat().st_size == 0:
            return None
        series = pd.read_csv(csv_path, usecols=[date_field], dtype=str)[date_field]
        if series.empty:
            return None
        return str(series.min())
    except (ValueError, KeyError, pd.errors.EmptyDataError) as exc:
        logger.debug("Could not read earliest date from %s: %s", csv_path, exc)
        return None


def format_download_earliest_date(
    earliest: Optional[str], *, has_date_field: bool
) -> str:
    if not has_date_field:
        return "n/a"
    return earliest if earliest else "-"


def get_incremental_download_params(table_name: str) -> Dict[str, Any]:
    """
    Get API parameters for incremental download based on last database update.

    Args:
        table_name: The table name (e.g., 'SEP', 'SF1')

    Returns:
        Dictionary of API parameters for incremental download
    """
    try:
        client = get_client()
        if not client:
            logger.warning(f"Could not get database client for {table_name}, will download all data")
            return {}

        # Get the latest date field timestamp from our database
        date_field = DataLoader.SHARADAR_TABLES[table_name]['date_field']

        # Source tables without a date field cannot use an incremental watermark.
        if not date_field:
            logger.info(f"No date field configured for {table_name}, will download all data")
            return {}

        query = (
            f"SELECT max({date_field}) FROM "
            f"{get_database_config().database}.{table_name.lower()} FINAL"
        )
        result = client.query(query)
        latest_db_update = result.result_rows[0][0] if result.result_rows and result.result_rows[0][0] else None

        if not latest_db_update:
            logger.info(f"No existing data found for {table_name}, will download all data")
            return {}

        # Add one day to avoid duplicate data
        start_date = (latest_db_update + timedelta(days=1)).strftime('%Y-%m-%d')
        logger.info(f"Found existing data for {table_name} up to {latest_db_update}, downloading from {start_date}")

        # Use the configured date field for incremental download
        if date_field:
            return {f"{date_field}.gte": start_date}

        return {}

    except Exception as e:
        logger.warning(f"Error getting incremental parameters for {table_name}: {e}, will download all data")
        return {}


class DataLoader:
    """A class to handle data loading operations for ClickHouse."""

    SHARADAR_TABLES = {
        'SEP': {'date_field': 'lastupdated'},
        'SF1': {'date_field': 'lastupdated'},
        'ACTIONS': {'date_field': 'date'},
        'TICKERS': {'date_field': 'lastupdated'},
        'DAILY': {'date_field': 'date'},
        'SF3': {'date_field': 'date'},
        'SF3A': {'date_field': 'date'},
        'SF3B': {'date_field': 'date'},
        'EVENTS': {'date_field': 'date'},
        'METRICS': {'date_field': 'lastupdated'},
        'SF2': {'date_field': 'date'},
        # lastupdated (not trade date): Sharadar rewrites historical prices after splits
        # and remounts series under successor tickers (e.g. BNY→BNY1 on 2026-05-21).
        # incremental-by-date misses those restatements (see VUG 2026-04-20).
        'SFP': {'date_field': 'lastupdated'},
        'SP500': {'date_field': 'date'},
    }

    def __init__(self):
        """Initialize the DataLoader."""
        self.client = get_client()
        if not self.client:
            raise RuntimeError(f"Failed to initialize ClickHouse client for mode '{app_config.mode}'")

        # Get configuration from typed config
        project_root = Path(get_project_root())
        data_cfg = get_data_config()
        relative_data_dir = data_cfg.root or "data"
        self.data_dir = project_root / relative_data_dir
        sharadar = get_sharadar_config()
        self.api_key = sharadar.api_key
        self.base_url = sharadar.base_url

        # Create the database separately, then initialize its schema with sigmarail-schema.

    def download_data(
        self,
        table_name: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        incremental: bool = True,
        *,
        years: Optional[str] = None,
        tickers: Optional[Sequence[str]] = None,
    ) -> Tuple[Optional[Path], int, Optional[str]]:
        """
        Coordinates the download and processing of a Sharadar table.

        Args:
            table_name: The table name to download
            start_date: Optional start date for download
            end_date: Optional end date for download
            incremental: Whether to use incremental download based on existing database data
            years: If set (5|10|full), use Sharadar bulk zip instead of paging
            tickers: Optional ticker filter(s) passed to Sharadar ``ticker=`` (paginated only)

        Returns:
            Tuple of (output_path, record_count, earliest_date_in_batch)
        """
        if not self.api_key:
            raise ValueError("API key not found in config.yaml under sharadar.api_key.")

        ticker_list = parse_ticker_list(tickers)
        if ticker_list and years:
            logger.warning(
                "Ignoring years=%s when tickers=%s; Sharadar bulk zip is full-table only",
                years,
                ",".join(ticker_list),
            )
            years = None

        # Bulk zip path (5y subscription / full refresh)
        if years:
            date_field = self.SHARADAR_TABLES[table_name]['date_field']
            self.data_dir.mkdir(parents=True, exist_ok=True)
            output_path = self.data_dir / f"SHARADAR_{table_name}_years{years}.csv"
            if table_name == 'TICKERS':
                record_count = self._download_tickers_sep_and_sfp(
                    output_path, {"years": years}
                )
            else:
                record_count = download_table_with_pagination(
                    code=table_name,
                    output_path=output_path,
                    api_key=self.api_key,
                    params={"years": years},
                    base_url=self.base_url,
                )
            earliest = earliest_date_from_csv(output_path, date_field)
            return output_path, record_count, earliest

        # If no dates provided and incremental is enabled, try to get incremental parameters
        if incremental and not start_date and not end_date:
            incremental_params = get_incremental_download_params(table_name)
            if incremental_params:
                logger.info(f"Using incremental download for {table_name}")
                params = incremental_params
                # Use today as end date for incremental download
                end_date = datetime.now().date().strftime('%Y-%m-%d')
            else:
                # Empty local table: pull 5y bulk (subscription floor) rather than one day.
                logger.info(
                    "No incremental watermark for %s; bulk years=5",
                    table_name,
                )
                return self.download_data(
                    table_name,
                    incremental=False,
                    years="5",
                    tickers=tickers,
                )
        else:
            # Use provided dates, optional bulk years, or fallback to yesterday
            if not start_date and not end_date and not years:
                if ticker_list:
                    params = {}
                else:
                    # Full non-incremental without dates → 5y bulk (retail subscription floor)
                    logger.info("Non-incremental with no dates for %s; bulk years=5", table_name)
                    return self.download_data(
                        table_name,
                        incremental=False,
                        years="5",
                        tickers=tickers,
                    )
            elif not start_date and not end_date:
                if ticker_list:
                    params = {}
                else:
                    start_date = end_date = (datetime.now().date() - timedelta(days=1)).strftime('%Y-%m-%d')
                    params = {}
            else:
                if not start_date:
                    start_date = end_date
                elif not end_date:
                    end_date = start_date
                params = {}

        date_field = self.SHARADAR_TABLES[table_name]['date_field']
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Add date filtering parameters if not already set by incremental download
        if not params and date_field and start_date and end_date:
            params[f"{date_field}.gte"] = start_date
            params[f"{date_field}.lte"] = end_date

        try:
            if ticker_list:
                output_path = self._scoped_ticker_output_path(
                    table_name, ticker_list, start_date, end_date
                )
                record_count = self._download_table_for_tickers(
                    table_name,
                    ticker_list,
                    output_path,
                    params,
                )
            else:
                # Define the final output path for the CSV
                if start_date == end_date:
                    output_path = self.data_dir / f"SHARADAR_{table_name}_{start_date}.csv"
                else:
                    output_path = (
                        self.data_dir
                        / f"SHARADAR_{table_name}_{start_date}_to_{end_date}.csv"
                    )
                # TICKERS: pull SEP + SFP only (price-table identity for mart routing).
                # Do not include SF1 — tickers ORDER BY (permaticker) would collide with SEP.
                if table_name == 'TICKERS':
                    record_count = self._download_tickers_sep_and_sfp(output_path, params)
                else:
                    record_count = download_table_with_pagination(
                        code=table_name,
                        output_path=output_path,
                        api_key=self.api_key,
                        params=params,
                        base_url=self.base_url,
                    )
            earliest = earliest_date_from_csv(output_path, date_field)
            return output_path, record_count, earliest
        except Exception as e:
            logger.error(f"Failed to download and process {table_name}: {e}")
            raise

    def _scoped_ticker_output_path(
        self,
        table_name: str,
        tickers: Sequence[str],
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> Path:
        slug = _ticker_slug(tickers)
        if start_date and end_date:
            if start_date == end_date:
                name = f"SHARADAR_{table_name}_{slug}_{start_date}.csv"
            else:
                name = f"SHARADAR_{table_name}_{slug}_{start_date}_to_{end_date}.csv"
        else:
            name = f"SHARADAR_{table_name}_{slug}.csv"
        return self.data_dir / name

    def _download_table_for_tickers(
        self,
        table_name: str,
        tickers: Sequence[str],
        output_path: Path,
        base_params: Optional[Dict[str, Any]],
    ) -> int:
        """Download one or more tickers via Sharadar ``ticker=`` and write one CSV."""
        if table_name == 'TICKERS':
            return self._download_tickers_sep_and_sfp(output_path, base_params, tickers=tickers)

        frames: List[pd.DataFrame] = []
        total = 0
        for ticker in tickers:
            part_path = output_path.with_name(
                f"{output_path.stem}.{ticker.lower()}{output_path.suffix}"
            )
            part_params = dict(base_params or {})
            part_params["ticker"] = ticker
            n = download_table_with_pagination(
                code=table_name,
                output_path=part_path,
                api_key=self.api_key,
                params=part_params,
                base_url=self.base_url,
            )
            total += n
            if part_path.is_file() and part_path.stat().st_size > 0:
                try:
                    frames.append(pd.read_csv(part_path))
                except pd.errors.EmptyDataError:
                    pass
            if part_path.exists():
                part_path.unlink(missing_ok=True)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if frames:
            pd.concat(frames, ignore_index=True).to_csv(output_path, index=False)
        else:
            pd.DataFrame().to_csv(output_path, index=False)
        logger.info(
            "Scoped download %s tickers=%s rows=%s -> %s",
            table_name,
            ",".join(tickers),
            total,
            output_path,
        )
        return total

    def _download_tickers_sep_and_sfp(
        self,
        output_path: Path,
        base_params: Optional[Dict[str, Any]] = None,
        *,
        tickers: Optional[Sequence[str]] = None,
    ) -> int:
        """Download Sharadar TICKERS for stocks(SEP) + funds(SFP), concat to one CSV."""
        frames: List[pd.DataFrame] = []
        total = 0
        scoped = parse_ticker_list(tickers)
        for legacy_table, query_table in TICKERS_QUERY_TABLE.items():
            targets = scoped or [None]
            for ticker in targets:
                suffix = f".{legacy_table.lower()}"
                if ticker:
                    suffix += f".{ticker.lower()}"
                part_path = output_path.with_name(f"{output_path.stem}{suffix}{output_path.suffix}")
                part_params = dict(base_params or {})
                part_params["table"] = query_table
                if ticker:
                    part_params["ticker"] = ticker
                n = download_table_with_pagination(
                    code="TICKERS",
                    output_path=part_path,
                    api_key=self.api_key,
                    params=part_params,
                    base_url=self.base_url,
                )
                total += n
                if part_path.is_file() and part_path.stat().st_size > 0:
                    try:
                        frames.append(pd.read_csv(part_path))
                    except pd.errors.EmptyDataError:
                        pass
                if part_path.exists():
                    part_path.unlink(missing_ok=True)
        if frames:
            pd.concat(frames, ignore_index=True).to_csv(output_path, index=False)
        else:
            output_path.touch()
        logger.info(
            "TICKERS stocks+funds (SEP+SFP) download complete: %s rows -> %s",
            total,
            output_path,
        )
        return total

    def load_csv_files(self, tables: Optional[List[str]] = None) -> bool:
        """
        Load CSV files into the database.

        Behavior:
        - If `tables` is None or empty, load all known SHARADAR tables found under the data directory.
        - If `tables` is provided, it acts as a filter of table names to load. The filter is
          case-insensitive (e.g., 'SF1' or 'sf1').

        Args:
            tables: Optional list of specific tables to load (case-insensitive). Examples:
                    ["sf1", "SEP", "daily"]. If omitted, all tables are considered.

        Returns:
            True if files were loaded successfully
        """
        try:
            # Import the new functions
            from sigmarail.database import adjust_clickhouse_settings_for_large_imports, reset_clickhouse_settings_after_import

            # Normalize requested table filters to lowercase for case-insensitive matching
            allowed_tables: Optional[set] = set(t.lower() for t in tables) if tables else None

            # Define file patterns and their corresponding table names
            # Support both regular CSV and gzipped CSV files
            file_patterns = {
                "SHARADAR_ACTIONS_*.csv*": "actions",
                "SHARADAR_DAILY_*.csv*": "daily",
                "SHARADAR_EVENTS_*.csv*": "events",
                "SHARADAR_METRICS_*.csv*": "metrics",
                "SHARADAR_SEP_*.csv*": "sep",
                "SHARADAR_SF1_*.csv*": "sf1",
                "SHARADAR_SF2_*.csv*": "sf2",
                "SHARADAR_SF3_*.csv*": "sf3",
                "SHARADAR_SF3A_*.csv*": "sf3a",
                "SHARADAR_SF3B_*.csv*": "sf3b",
                "SHARADAR_SFP_*.csv*": "sfp",
                "SHARADAR_SP500_*.csv*": "sp500",
                "SHARADAR_TICKERS_*.csv*": "tickers"
            }

            # Track overall progress
            total_files = 0
            loaded_files = 0
            failed_files = 0
            tables_with_many_partitions_detected = False

            # Tables that are likely to have many partitions due to date ranges
            tables_with_many_partitions = {
                'sep', 'sfp', 'metrics', 'daily', 'sf1', 'tickers'
            }

            # First pass: count total files and detect tables with many partitions
            for file_pattern, table_name_lower in file_patterns.items():
                if allowed_tables and table_name_lower not in allowed_tables:
                    continue

                matching_files = sorted(list(self.data_dir.glob(file_pattern)))
                total_files += len(matching_files)

                # Check if this table type is likely to have many partitions
                if table_name_lower in tables_with_many_partitions:
                    tables_with_many_partitions_detected = True

            logger.info(f"Found {total_files} total files to load")
            if tables_with_many_partitions_detected:
                logger.info("Tables with many partitions detected - will adjust ClickHouse settings for optimal performance")
                adjust_clickhouse_settings_for_large_imports()

            # Load each file pattern
            for file_pattern, table_name_lower in file_patterns.items():
                table_name = table_name_lower.upper() # Use uppercase for lookup, keep lower for DB
                if allowed_tables and table_name_lower not in allowed_tables:
                    continue

                # Find and sort matching files to process them in chronological order
                matching_files = sorted(list(self.data_dir.glob(file_pattern)))
                if not matching_files:
                    logger.warning(f"No files found matching pattern {file_pattern}")
                    continue

                logger.info(f"Processing {len(matching_files)} file(s) for {table_name_lower}...")

                for file_path in matching_files:
                    # Check if the file is empty or only has a header
                    try:
                        # Handle both regular CSV and gzipped CSV files
                        if file_path.suffix == '.gz':
                            # For gzipped files, we can't easily peek without decompressing
                            # Just check if the file has content
                            if file_path.stat().st_size == 0:
                                logger.warning(f"  - Skipping empty gzipped file: {file_path.name}")
                                continue
                        else:
                            # For regular CSV files, read the first row to check for content
                            df_peek = pd.read_csv(file_path, nrows=1)
                            if df_peek.empty:
                                logger.warning(f"  - Skipping empty file: {file_path.name}")
                                continue
                    except pd.errors.EmptyDataError:
                        logger.warning(f"  - Skipping empty file: {file_path.name}")
                        continue

                    rel_path = file_path.relative_to(self.data_dir)
                    file_size_mb = file_path.stat().st_size / (1024 * 1024)
                    logger.info(f"  - Loading {rel_path} ({file_size_mb:.1f}MB) into {table_name_lower}")

                    try:
                        logger.info(f"  - Starting database load for {rel_path}")
                        if not load_single_csv(str(rel_path), table_name_lower):
                            logger.error(f"Failed to load {rel_path}")
                            failed_files += 1
                            # Continue with other files but track the failure
                        else:
                            loaded_files += 1
                            logger.info(f"✅ Successfully loaded {rel_path}")
                    except Exception as e:
                        logger.error(f"Exception during load of {rel_path}: {e}")
                        logger.exception(f"Full traceback for {rel_path}:")
                        failed_files += 1

            # Reset ClickHouse settings if we adjusted them
            if tables_with_many_partitions_detected:
                logger.info("Resetting ClickHouse settings to default values...")
                reset_clickhouse_settings_after_import()

            # Summary
            logger.info(f"📊 Load Summary: {loaded_files}/{total_files} files loaded successfully")
            if failed_files > 0:
                logger.warning(f"⚠️  {failed_files} files failed to load")
                return False

            return True

        except Exception as e:
            logger.error(f"Error loading CSV files: {e}")
            return False

    def backup_csv_files(self) -> bool:
        """Create a backup of CSV files before loading them into ClickHouse.

        Returns:
            bool: True if backup was successful, False otherwise
        """
        try:
            # Create backup directory with timestamp
            timestamp = datetime.now().strftime('%Y%m%d')
            backup_dir = os.path.join(self.data_dir, 'backup', f'SHARADAR_{timestamp}')
            os.makedirs(backup_dir, exist_ok=True)

            # Copy all CSV files to backup directory
            csv_files = glob.glob(os.path.join(self.data_dir, '*.csv'))
            for csv_file in csv_files:
                filename = os.path.basename(csv_file)
                shutil.copy2(csv_file, os.path.join(backup_dir, filename))
                logger.info(f"Backed up {filename}")

            # Create zip file
            zip_path = os.path.join(self.data_dir, 'backup', f'SHARADAR_{timestamp}.zip')
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(backup_dir):
                    for file in files:
                        if file.endswith('.csv'):  # Only zip the CSV files
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, backup_dir)
                            zipf.write(file_path, arcname)

            logger.info(f"Created compressed backup at {zip_path}")

            # Remove original CSV files
            for csv_file in csv_files:
                os.remove(csv_file)
                logger.info(f"Removed original file: {os.path.basename(csv_file)}")

            # Remove the backup directory
            shutil.rmtree(backup_dir)
            logger.info(f"Removed backup directory: {backup_dir}")

            return True

        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            return False


# Actions that imply historical price restatement / metrics recalculation.
RECALC_PRICE_ACTIONS = (
    'split',
    'spinoff',
    'spinoffdividend',
    'adrratiosplit',
)


def _print_event_summary(lookback_days: int = 7) -> None:
    """
    Print summary of high-impact events (splits, spinoffs, sp500 changes) from the last N days.
    These events drive metrics recalculation. Appears in daily update log.
    """
    try:
        client = get_client()
        if not client:
            return
        cutoff = (date.today() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
        # Splits and spinoffs from actions
        # Use f-string for cutoff (safe: we control the value from date.today())
        split_result = client.query(
            f"SELECT count() FROM actions FINAL WHERE action = 'split' AND date >= '{cutoff}'"
        )
        split_count = split_result.result_rows[0][0] if split_result.result_rows else 0
        spinoff_result = client.query(
            f"""SELECT count() FROM actions FINAL
                WHERE action IN ('spinoff','spunofffrom','spinoffdividend') AND date >= '{cutoff}'"""
        )
        spinoff_count = spinoff_result.result_rows[0][0] if spinoff_result.result_rows else 0
        sp500_added_result = client.query(
            f"SELECT count() FROM sp500 FINAL WHERE action = 'added' AND date >= '{cutoff}'"
        )
        sp500_added = sp500_added_result.result_rows[0][0] if sp500_added_result.result_rows else 0
        sp500_removed_result = client.query(
            f"SELECT count() FROM sp500 FINAL WHERE action = 'removed' AND date >= '{cutoff}'"
        )
        sp500_removed = sp500_removed_result.result_rows[0][0] if sp500_removed_result.result_rows else 0
        action_list = ", ".join(f"'{a}'" for a in RECALC_PRICE_ACTIONS)
        ticker_result = client.query(
            f"""SELECT DISTINCT ticker FROM actions FINAL
                WHERE action IN ({action_list}) AND date >= '{cutoff}'
                ORDER BY ticker
                LIMIT 50"""
        )
        tickers = [row[0] for row in (ticker_result.result_rows or [])]
        print("\n" + "=" * 80)
        print("EVENTS SUMMARY (recalculation-impacting, last {} days)".format(lookback_days))
        print("=" * 80)
        print(f"Splits: {split_count:,}  |  Spinoffs: {spinoff_count:,}  |  S&P500 added: {sp500_added:,}  |  S&P500 removed: {sp500_removed:,}")
        if tickers:
            print(f"Price-recalc tickers (split/spinoff/ADR, up to 50): {', '.join(tickers)}")
        print("=" * 80 + "\n")
    except Exception as e:
        logger.warning(f"Could not print event summary: {e}")


def main() -> int:
    """Command-line entry point for loading data into ClickHouse.

    Returns:
        int: Exit code (0 for success, 1 for failure)
    """
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description='Load data into ClickHouse',
        parents=[create_shared_parser()]
    )
    # Add table and backup arguments
    parser.add_argument(
        '--tables',
        nargs='+',
        help=(
            'Optional filter: load only the listed tables (case-insensitive), '
            'e.g., actions daily sf1. If omitted, all supported tables are loaded.'
        )
    )
    parser.add_argument('--backup', action='store_true', help='Backup CSV files after loading (only available in prod mode)')
    # Add download options
    parser.add_argument('--download', action='store_true', help='Download data before loading')
    parser.add_argument('--no-incremental', action='store_true', help='Disable incremental download and download all data')
    parser.add_argument(
        '--years',
        choices=['5', '10', 'full'],
        help='Bulk zip history length (sharadar.com). Overrides date filters when set.',
    )
    parser.add_argument(
        '--no-splice',
        action='store_true',
        help='Skip scaling sep/sfp bars older than the download window before load',
    )

    parser.add_argument(
        '--tickers',
        nargs='+',
        metavar='TICKER',
        help=(
            'Optional ticker filter passed to Sharadar ticker= (paginated download only). '
            'Comma-separated or repeated, e.g. --tickers IESC or --tickers IESC,SFBS'
        ),
    )
    parser.add_argument('--start-date', help='Start date for data download/population (YYYY-MM-DD)')
    parser.add_argument('--end-date', help='End date for data download/population (YYYY-MM-DD)')
    args = parser.parse_args()

    # Handle shared args
    process_shared_args(args)

    try:
        # Check if backup is requested in test mode
        if args.backup and app_config.mode == 'test':
            logger.error("Backup operation is not allowed in test mode")
            return 1

        # Note: Database initialization should be done separately using sigmarail-schema --initialize-database

        # Create data loader instance
        loader = DataLoader()

        if args.tables:
            requested = {part.upper() for value in args.tables for part in value.split(',') if part.strip()}
            unknown = requested - set(loader.SHARADAR_TABLES)
            if unknown:
                logger.error("Unsupported SigmaRail source tables: %s", sorted(unknown))
                return 2
            args.tables = [
                part.strip().lower()
                for value in args.tables
                for part in value.split(',')
                if part.strip()
            ]

        # Determine date range for download/population
        start_date = args.start_date
        end_date = args.end_date

        # --- Auto-determine DOWNLOAD date range if --download is set and dates are missing ---
        if args.download and not start_date and not args.years:
            logger.info("Download start date not provided. Using incremental download based on existing database data...")
            # The incremental download logic is now handled in the download_data method
            # No need for the old auto-determination logic here

        # Download data if requested
        if args.download:
            # If no tables specified, use all SHARADAR tables
            tables_to_download = args.tables if args.tables else list(loader.SHARADAR_TABLES.keys())

            # Determine if we should use incremental download
            use_incremental = not args.no_incremental and not args.years
            if args.years:
                logger.info(
                    "Starting bulk years=%s download for tables: %s",
                    args.years,
                    ", ".join(tables_to_download),
                )
            elif use_incremental:
                logger.info(f"Starting incremental data download for tables: {', '.join(tables_to_download)}")
            else:
                logger.info(f"Starting full data download for tables: {', '.join(tables_to_download)} from {start_date} to {end_date}")

            successful_downloads = True
            download_summary: Dict[str, Dict[str, Any]] = {}  # records + earliest per table
            ticker_filter = parse_ticker_list(args.tickers)

            for table in tables_to_download:
                table_upper = table.upper()
                date_field = loader.SHARADAR_TABLES[table_upper]['date_field']
                try:
                    output_path, record_count, earliest_date = loader.download_data(
                        table_name=table_upper,
                        start_date=start_date,
                        end_date=end_date,
                        incremental=use_incremental,
                        years=args.years,
                        tickers=ticker_filter or None,
                    )
                    download_summary[table_upper] = {
                        "count": record_count,
                        "earliest": earliest_date,
                        "has_date_field": bool(date_field),
                    }
                except Exception as e:
                    logger.error(f"Failed to download {table}: {e}")
                    download_summary[table_upper] = {
                        "count": 0,
                        "earliest": None,
                        "has_date_field": bool(date_field),
                    }
                    successful_downloads = False

            # Print download summary
            print("\n" + "="*80)
            print("📊 DOWNLOAD SUMMARY")
            print("="*80)
            print(f"{'Table':<15} {'Records Downloaded':>20} {'Earliest Date':>15}")
            print("-"*80)
            total_records = 0
            for table, info in sorted(download_summary.items()):
                count = int(info["count"])
                earliest = format_download_earliest_date(
                    info.get("earliest"),
                    has_date_field=bool(info.get("has_date_field")),
                )
                print(f"{table:<15} {count:>20,} {earliest:>15}")
                total_records += count
            print("-"*80)
            print(f"{'TOTAL':<15} {total_records:>20,} {'':>15}")
            print("="*80 + "\n")

            if not successful_downloads:
                logger.warning("One or more downloads failed. Continuing with existing data...")
            else:
                logger.info("Data download completed.")

            # Scale older-than-window sep/sfp bars before inserting the restated window.
            if not args.no_splice:
                try:
                    splice_counts = splice_downloaded_price_csvs(
                        loader.client,
                        loader.data_dir,
                        tables=args.tables,
                    )
                    logger.info("Pre-load price splice: %s", splice_counts)
                except Exception as e:
                    logger.warning("Pre-load price splice failed (continuing with load): %s", e)

        # Load CSV files
        logger.info("Starting CSV file loading...")
        if not loader.load_csv_files(tables=args.tables):
            logger.error("Failed to load CSV files")
            return 1
        logger.info("CSV file loading completed.")

        # Backup files if requested
        if args.backup:
            logger.info("Starting backup process...")
            if not loader.backup_csv_files():
                logger.error("Failed to backup CSV files")
                return 1
            logger.info("Backup process completed.")

        # Optimize ReplacingMergeTree tables to ensure deduplication
        logger.info("Starting table optimization (deduplication)...")
        if not optimize_tables():
            logger.warning("Table optimization encountered issues, but load process completed")
        logger.info("Table optimization queued - merges will continue in background.")

        # Event summary: high-impact events that drive recalculations (last 7 days)
        _print_event_summary(lookback_days=7)

        logger.info("SigmaRail load process completed successfully!")
        return 0

    except Exception as e:
        logger.exception(f"An unexpected error occurred during the load process: {e}")
        return 1

if __name__ == '__main__':
    exit(main())
