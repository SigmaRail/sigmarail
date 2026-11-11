"""
ClickHouse database operations and command-line interface.

This module provides both the unified database interface and CLI commands for ClickHouse operations.
"""

import logging
import os
import pwd
import re
import json
import shutil
import subprocess
import time
import argparse
from typing import Dict, Any, Optional, List, Tuple, Union
from pathlib import Path
import clickhouse_connect
from sigmarail.config import (
    app_config,
    create_shared_parser,
    get_database_config,
    get_data_config,
    get_schema_files,
    get_schema_dir,
    get_project_root,
    load_config,
    process_shared_args,
)
from sigmarail.config import DatabaseConfig

logger = logging.getLogger(__name__)


def _schema_sql_sort_key(path: Path) -> Tuple[int, str]:
    """Sort schema files by numeric prefix (89 before 102), then filename."""
    match = re.match(r"^(\d+)-", path.name)
    order = int(match.group(1)) if match else 999999
    return (order, path.name)


def _sql_statement_head(statement: str) -> str:
    """Return a statement after any leading SQL comments and whitespace."""
    remaining = statement.lstrip()
    while True:
        if remaining.startswith("--"):
            _, newline, remaining = remaining.partition("\n")
            if not newline:
                return ""
            remaining = remaining.lstrip()
            continue
        if remaining.startswith("/*"):
            end = remaining.find("*/", 2)
            if end < 0:
                return remaining
            remaining = remaining[end + 2 :].lstrip()
            continue
        return remaining


# Singleton client instance
_client_instance: Optional[clickhouse_connect.driver.Client] = None


def _passwd_home() -> Path:
    """Real user home (not IDE sandbox HOME)."""
    try:
        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    except Exception:
        return Path.home()


def resolve_clickhouse_client_executable() -> str:
    """
  Path to native ``clickhouse-client`` for subprocess INFILE / SQL file loads.

  Prefers ``CLICKHOUSE_CLIENT`` / ``SIGMARAIL_CLICKHOUSE_CLIENT``, then
  ``<passwd-home>/.clickhouse/versions/*/clickhouse``, then ``PATH``.
  """
    for key in ("CLICKHOUSE_CLIENT", "SIGMARAIL_CLICKHOUSE_CLIENT"):
        override = os.environ.get(key, "").strip()
        if override and os.path.isfile(override) and os.access(override, os.X_OK):
            return override

    versions_dir = _passwd_home() / ".clickhouse" / "versions"
    default_version_file = _passwd_home() / ".clickhouse" / "default"
    if default_version_file.is_file():
        version = default_version_file.read_text(encoding="utf-8").strip()
        if version:
            pinned = versions_dir / version / "clickhouse"
            if pinned.is_file() and os.access(pinned, os.X_OK):
                return str(pinned)

    if versions_dir.is_dir():
        candidates = sorted(
            (p / "clickhouse" for p in versions_dir.iterdir() if p.is_dir()),
            key=lambda p: p.parent.name,
            reverse=True,
        )
        for candidate in candidates:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)

    on_path = shutil.which("clickhouse-client")
    if on_path:
        return on_path

    raise FileNotFoundError(
        "clickhouse-client not found. Install native ClickHouse under "
        f"{versions_dir} (see SigmaRail/README.md) or set "
        "CLICKHOUSE_CLIENT to the clickhouse binary path."
    )


def _validate_test_mode_safety() -> None:
    """
    Ensure test mode never connects to production database.

    Raises:
        RuntimeError: If test mode is attempting to use production credentials or ports
    """
    if app_config.mode != 'test':
        return

    db_config = get_database_config()

    if db_config.database == db_config.production_database:
        raise RuntimeError(
            "Safety violation: SigmaRail test mode is configured for the production database. "
            "Set the test database to sigmarail_test before connecting."
        )

    # Database identity is the hard boundary between test and production.
    if db_config.database == db_config.production_database:
        raise RuntimeError(
            "SigmaRail test mode cannot use the configured production database. "
            "Set database.database to sigmarail_test in config-test.yaml."
        )

    # Block production native port in test mode
    if db_config.port == 9000 and db_config.host in ('localhost', '127.0.0.1'):
        raise RuntimeError(
            "🚨 SAFETY VIOLATION: Test mode attempting to connect to production port!\n"
            f"   Current: {db_config.host}:{db_config.port} (PRODUCTION)\n"
            "   Expected: localhost:9001 (Docker test container)\n"
            "   Check config-test.yaml and ensure it uses port 9001, not 9000.\n"
            "   This prevents accidental modifications to production data."
        )

    # Block production HTTP port in test mode
    if db_config.http_port == 8123 and db_config.host in ('localhost', '127.0.0.1'):
        raise RuntimeError(
            "🚨 SAFETY VIOLATION: Test mode attempting to connect to production HTTP port!\n"
            f"   Current: {db_config.host}:{db_config.http_port} (PRODUCTION)\n"
            "   Expected: localhost:8134 (Docker test container)\n"
            "   Check config-test.yaml and ensure it uses HTTP port 8134, not 8123.\n"
            "   This prevents accidental modifications to production data."
        )

    logger.info(
        f"✅ Test mode safety check passed: {db_config.user}@{db_config.host}:{db_config.port}"
    )


def clear_caches() -> bool:
    """Clear ClickHouse caches to free memory."""
    client = get_client()
    if not client:
        logger.error("Failed to get ClickHouse client")
        return False

    print("🧹 Clearing ClickHouse caches...")

    cache_commands = [
        ("SYSTEM DROP MARK CACHE", "Mark cache"),
        ("SYSTEM DROP UNCOMPRESSED CACHE", "Uncompressed cache"),
        ("SYSTEM DROP COMPILED EXPRESSION CACHE", "Compiled expression cache"),
        ("SYSTEM DROP QUERY CACHE", "Query cache"),
    ]

    success_count = 0
    for command, description in cache_commands:
        try:
            client.command(command)
            print(f"  ✅ Cleared {description}")
            logger.info(f"Cleared {description}")
            success_count += 1
        except Exception as e:
            # Some caches might not exist or be supported in all versions
            print(f"  ⚠️  Could not clear {description}: {e}")
            logger.warning(f"Could not clear {description}: {e}")

    print(f"\n💾 Cleared {success_count}/{len(cache_commands)} caches")
    logger.info(f"Cache clearing complete: {success_count}/{len(cache_commands)} caches cleared")

    return success_count > 0


def optimize_tables(
    tables: Optional[List[str]] = None,
    dup_check_recent_days: Optional[int] = None,
) -> bool:
    """Optimize ReplacingMergeTree tables by optimizing each partition individually.

    This approach is faster than optimizing the entire table because partitions
    can be queued and processed in parallel.

    Args:
        tables: Optional list of table names to optimize. If None, optimizes all
                ReplacingMergeTree tables. Names are case-insensitive.
        dup_check_recent_days: If None, skip duplicate reporting (default; avoids
                heavy full-table scans). If set (e.g. 30), run a light duplicate
                check only on recent data (date >= today() - N) to bound memory.

    Returns:
        bool: True if optimization was successful
    """
    client = get_client()
    if not client:
        logger.error("Failed to get ClickHouse client")
        return False

    # Get all ReplacingMergeTree tables, filtered by provided table list if specified
    try:
        query = f"""
        SELECT name
        FROM system.tables
        WHERE database = '{get_database_config().database}'
        AND engine LIKE '%ReplacingMergeTree%'
        ORDER BY name
        """
        result = client.query(query)
        all_table_names = [row[0] for row in result.result_rows]

        # Filter by provided table list if specified
        if tables:
            tables_lower = [t.lower() for t in tables]
            table_names = [t for t in all_table_names if t.lower() in tables_lower]
            if not table_names:
                logger.warning(f"No matching ReplacingMergeTree tables found for: {tables}")
                return True
        else:
            table_names = all_table_names

        logger.info(f"Found {len(table_names)} ReplacingMergeTree table(s) to optimize: {table_names}")
    except Exception as e:
        logger.warning(f"Could not get ReplacingMergeTree tables: {e}")
        return False

    if not table_names:
        logger.warning("No ReplacingMergeTree tables found to optimize")
        return True

    logger.info(f"Starting partition-level optimization for {len(table_names)} table(s)...")

    total_tables_processed = 0
    total_partitions_queued = 0
    total_tables = len(table_names)
    total_tables_skipped = 0  # tables with no active partitions (not failures)

    for table_name in table_names:
        logger.info(f"Processing table: {table_name}")

        # Check if table exists
        try:
            client.query(f"SELECT 1 FROM {table_name} LIMIT 1")
        except Exception as e:
            logger.warning(f"  Table {table_name} does not exist or is not accessible: {e}")
            continue

        # Get all partitions for this table
        try:
            partitions_query = """
            SELECT DISTINCT partition
            FROM system.parts
            WHERE database = '{database}'
            AND table = '{table}'
            AND active = 1
            ORDER BY partition
            """.format(database=get_database_config().database, table=table_name)

            partitions_result = client.query(partitions_query)
            partitions = [row[0] for row in partitions_result.result_rows]

            if not partitions:
                logger.info(f"  No active partitions found for {table_name}")
                total_tables_skipped += 1
                continue

            logger.info(f"  Found {len(partitions)} partition(s) for {table_name}")

            # Optimize each partition individually
            partition_success_count = 0
            for partition in partitions:
                try:
                    # Skip empty partition tuples (unpartitioned tables)
                    if partition == "tuple()" or str(partition).strip() == "tuple()" or not partition:
                        logger.info(f"    Skipping empty partition (table is unpartitioned), using table-level optimization")
                        break

                    # Use PARTITION syntax to optimize individual partitions
                    # This queues merges faster than optimizing the entire table
                    client.command(f"OPTIMIZE TABLE {table_name} PARTITION '{partition}'")
                    partition_success_count += 1
                    total_partitions_queued += 1
                except Exception as e:
                    # If partition optimization fails, fall back to table-level
                    if "INVALID_PARTITION_VALUE" in str(e) or "Wrong number of fields" in str(e):
                        logger.info(f"    Partition syntax not supported, falling back to table-level optimization")
                        break
                    logger.warning(f"    Failed to queue optimization for partition {partition}: {e}")
                    # Continue with other partitions

            # If we have partitions but none were queued, or if we encountered empty partition tuple,
            # fall back to table-level optimization
            if partition_success_count == 0 and partitions:
                # Check if it's an unpartitioned table (empty tuple)
                if any(p == "tuple()" or str(p).strip() == "tuple()" or not p for p in partitions):
                    try:
                        logger.info(f"  Using table-level optimization for unpartitioned table {table_name}...")
                        client.command(f"OPTIMIZE TABLE {table_name}")
                        total_tables_processed += 1
                        logger.info(f"  ✅ Queued table-level optimization for {table_name}")
                    except Exception as e2:
                        logger.error(f"  ❌ Table-level optimization also failed for {table_name}: {e2}")
                else:
                    logger.warning(f"  ⚠️  Failed to queue any partitions for {table_name}")
            elif partition_success_count > 0:
                total_tables_processed += 1
                logger.info(f"  ✅ Queued optimization for {partition_success_count}/{len(partitions)} partition(s) in {table_name}")
            else:
                logger.warning(f"  ⚠️  No partitions found for {table_name}")

        except Exception as e:
            logger.error(f"  ❌ Failed to get partitions for table {table_name}: {e}")
            # Try fallback to table-level optimization if partition query fails
            try:
                logger.info(f"  Falling back to table-level optimization for {table_name}...")
                client.command(f"OPTIMIZE TABLE {table_name}")
                total_tables_processed += 1
                logger.info(f"  ✅ Queued table-level optimization for {table_name}")
            except Exception as e2:
                logger.error(f"  ❌ Table-level optimization also failed for {table_name}: {e2}")

    logger.info(f"Optimization complete: {total_tables_processed}/{total_tables} table(s) processed, {total_tables_skipped} skipped (empty), {total_partitions_queued} partition(s) queued")

    # Optional: light duplicate check on recent data only (bounded memory). Skip if dup_check_recent_days is None.
    if dup_check_recent_days is not None and dup_check_recent_days >= 0:
        try:
            def _table_has_columns(tbl: str, cols: List[str]) -> bool:
                try:
                    placeholders = ",".join([f"'{c}'" for c in cols])
                    q = f"""
                    SELECT count()
                    FROM system.columns
                    WHERE database = '{get_database_config().database}' AND table = '{tbl}' AND name IN ({placeholders})
                    """
                    r = client.query(q)
                    return r.result_rows and r.result_rows[0][0] == len(cols)
                except Exception:
                    return False

            def _report_duplication_recent(tbl: str, recent_days: int) -> None:
                try:
                    # Only check tables with a date column so we can scope to recent data (bounded memory)
                    if _table_has_columns(tbl, ['ticker', 'date']):
                        key_expr = "(ticker, date)"
                        group_cols = "ticker, date"
                        where_clause = f"WHERE date >= today() - {recent_days}"
                    elif _table_has_columns(tbl, ['date']):
                        key_expr = "(date)"
                        group_cols = "date"
                        where_clause = f"WHERE date >= today() - {recent_days}"
                    elif _table_has_columns(tbl, ['ticker']):
                        # No date column: skip full-table dup-check to avoid memory spike
                        logger.info(f"[dup-check] {tbl}: skipped (no date column for bounded check)")
                        return
                    else:
                        logger.info(f"[dup-check] {tbl}: skipped (no recognizable key columns)")
                        return

                    q = f"""
                    WITH g AS (
                        SELECT {group_cols}, count() AS cnt
                        FROM {tbl} {where_clause}
                        GROUP BY {group_cols}
                    )
                    SELECT
                        (SELECT count() FROM {tbl} {where_clause})                AS total_rows,
                        (SELECT count(DISTINCT {key_expr}) FROM {tbl} {where_clause}) AS unique_keys,
                        (SELECT countIf(cnt > 1) FROM g)                           AS duplicate_key_groups
                    """
                    res = client.query(q)
                    if not res.result_rows:
                        logger.info(f"[dup-check] {tbl}: no rows (recent {recent_days}d)")
                        return
                    total_rows, unique_keys, duplicate_groups = res.result_rows[0]
                    logger.info(
                        f"[dup-check] {tbl}: recent_{recent_days}d rows={total_rows}, "
                        f"unique_keys={unique_keys}, duplicate_key_groups={duplicate_groups}"
                    )
                    print(
                        f"[dup-check] {tbl}: recent_{recent_days}d rows={total_rows}, "
                        f"unique_keys={unique_keys}, duplicate_key_groups={duplicate_groups}"
                    )
                except Exception as e:
                    logger.warning(f"[dup-check] {tbl}: failed to compute duplication status: {e}")

            logger.info(f"Running light dup-check (last {dup_check_recent_days} days only)...")
            for tbl in table_names:
                _report_duplication_recent(tbl, dup_check_recent_days)
        except Exception as e:
            logger.debug(f"Duplication status reporting skipped due to error: {e}")

    return total_tables_processed == (total_tables - total_tables_skipped)


def get_client(db_config: Optional[DatabaseConfig] = None) -> clickhouse_connect.driver.Client:
    """Get a configured ClickHouse client instance.

    Args:
        db_config: Optional DatabaseConfig. If None, uses get_database_config().

    Returns:
        Configured ClickHouse client instance.
    """
    # Safety check: ensure test mode never connects to production
    _validate_test_mode_safety()

    if db_config is None:
        db_config = get_database_config()
    database_name = db_config.database
    # Test mode: connect to `default` first — clickhouse_connect cannot open a session on a missing database.
    if app_config.mode == "test":
        try:
            temp_client = clickhouse_connect.get_client(
                host=db_config.host,
                port=db_config.http_port,
                username=db_config.user,
                password=db_config.password,
                database="default",
                connect_timeout=db_config.connect_timeout,
                send_receive_timeout=db_config.send_receive_timeout or 3600,
            )
            temp_client.command(f"CREATE DATABASE IF NOT EXISTS {database_name}")
            temp_client.close()
        except Exception as e:
            logger.warning("Could not ensure database exists: %s", e)
    return clickhouse_connect.get_client(
        host=db_config.host,
        port=db_config.http_port,
        username=db_config.user,
        password=db_config.password,
        database=database_name,
        connect_timeout=db_config.connect_timeout,
        send_receive_timeout=db_config.send_receive_timeout or 3600,
    )

def adjust_clickhouse_settings_for_large_imports() -> bool:
    """
    Temporarily adjust ClickHouse settings to handle large imports with many partitions.

    Returns:
        bool: True if settings were adjusted successfully
    """
    try:
        # Settings to adjust for large imports
        settings = {
            'max_partitions_per_insert_block': '1000',  # Allow more partitions per insert
            'max_insert_block_size': '1000000',  # Larger insert blocks
            'max_memory_usage': '20000000000',  # 20GB memory limit
            'max_bytes_before_external_group_by': '10000000000',  # 10GB before external sort
            'max_bytes_before_external_sort': '10000000000',  # 10GB before external sort
        }
        db_config = get_database_config()
        # Apply each setting
        client_bin = resolve_clickhouse_client_executable()
        for setting_name, setting_value in settings.items():
            cmd = [
                client_bin,
                "--host", db_config.host,
                "--port", str(db_config.port),
                "--user", db_config.user,
                "--password", db_config.password,
                "--database", db_config.database,
                "--query", f"SET {setting_name} = {setting_value}"
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30)

            if result.returncode != 0:
                logger.warning(f"Failed to set {setting_name} = {setting_value}: {result.stderr}")
                # Continue with other settings even if one fails
            else:
                logger.debug(f"Successfully set {setting_name} = {setting_value}")

        logger.info("Adjusted ClickHouse settings for large imports")
        return True

    except Exception as e:
        logger.warning(f"Failed to adjust ClickHouse settings for large imports: {e}")
        return False

def reset_clickhouse_settings_after_import() -> bool:
    """
    Reset ClickHouse settings to default values after large imports.

    Returns:
        bool: True if settings were reset successfully
    """
    try:
        # Reset to more conservative default settings
        settings = {
            'max_partitions_per_insert_block': '100',  # Back to default
            'max_insert_block_size': '100000',  # Back to default
            'max_memory_usage': '10000000000',  # 10GB memory limit
            'max_bytes_before_external_group_by': '1000000000',  # 1GB before external sort
            'max_bytes_before_external_sort': '1000000000',  # 1GB before external sort
        }
        db_config = get_database_config()
        client_bin = resolve_clickhouse_client_executable()
        # Apply each setting
        for setting_name, setting_value in settings.items():
            cmd = [
                client_bin,
                "--host", db_config.host,
                "--port", str(db_config.port),
                "--user", db_config.user,
                "--password", db_config.password,
                "--database", db_config.database,
                "--query", f"SET {setting_name} = {setting_value}"
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=30)

            if result.returncode != 0:
                logger.warning(f"Failed to reset {setting_name} = {setting_value}: {result.stderr}")
                # Continue with other settings even if one fails
            else:
                logger.debug(f"Successfully reset {setting_name} = {setting_value}")

        logger.info("Reset ClickHouse settings to default values")
        return True

    except Exception as e:
        logger.warning(f"Failed to reset ClickHouse settings: {e}")
        return False

def estimate_file_size_mb(file_path: str) -> float:
    """
    Estimate the size of a file in megabytes.

    Args:
        file_path: Path to the file

    Returns:
        float: File size in megabytes
    """
    try:
        size_bytes = os.path.getsize(file_path)
        return size_bytes / (1024 * 1024)  # Convert to MB
    except Exception:
        return 0.0

def count_csv_rows(file_path: str) -> int:
    """
    Count the number of rows in a CSV file (excluding header) using wc -l for efficiency.

    Args:
        file_path: Path to the CSV file

    Returns:
        int: Number of rows in the CSV file
    """
    try:
        # Use wc -l for fast line counting
        result = subprocess.run(['wc', '-l', file_path], capture_output=True, text=True, check=True)
        line_count = int(result.stdout.strip().split()[0])
        # Subtract 1 for header row
        return max(0, line_count - 1)
    except Exception as e:
        logger.warning(f"Could not count rows in {file_path}: {e}")
        return 0

def _clickhouse_docker_container_for_infile() -> str:
    """When set, CSV INFILE runs via ``docker exec`` so paths resolve on the server (user_files)."""
    return os.environ.get("SIGMARAIL_TEST_CLICKHOUSE_CONTAINER", "").strip()


def _infile_path_for_csv_load(host_absolute_path: str) -> str:
    """Path string passed to ``INFILE``.

    Remote ``clickhouse-client`` resolves relative INFILE paths on the **host** cwd, not on the
    server, so basename-only mode is wrong for Docker port-forwarding. With
    ``SIGMARAIL_TEST_CLICKHOUSE_CONTAINER`` set, ``load_single_csv`` runs the client inside that
    container and passes an absolute path under ``user_files`` (the test compose image sets
  ``working_dir`` to ``/opt/sigmarail``, so a bare basename would incorrectly resolve under
  ``/opt/sigmarail``).

    Override directory with ``SIGMARAIL_TEST_CLICKHOUSE_USER_FILES`` if your mount differs.

    Local ClickHouse on the same machine as the CSV files uses the host absolute path.
    """
    if app_config.mode != "test":
        return host_absolute_path
    if _clickhouse_docker_container_for_infile():
        base = os.environ.get(
            "SIGMARAIL_TEST_CLICKHOUSE_USER_FILES", "/var/lib/clickhouse/user_files"
        ).rstrip("/")
        return f"{base}/{os.path.basename(os.path.normpath(host_absolute_path))}"
    return host_absolute_path


def _clickhouse_client_argv_for_infile(db_config: DatabaseConfig) -> List[str]:
    """Native client argv for ``INSERT ... FROM INFILE`` (optionally wrapped in ``docker exec``)."""
    container = _clickhouse_docker_container_for_infile()
    if container:
        return [
            "docker",
            "exec",
            container,
            "clickhouse-client",
            "--host",
            "127.0.0.1",
            "--port",
            "9000",
            "--user",
            db_config.user,
            "--password",
            db_config.password,
            "--database",
            db_config.database,
        ]
    return [
        resolve_clickhouse_client_executable(),
        "--host",
        db_config.host,
        "--port",
        str(db_config.port),
        "--user",
        db_config.user,
        "--password",
        db_config.password,
        "--database",
        db_config.database,
    ]


def _resolve_csv_full_path(file_path: str) -> str:
    """Resolve CSV path under the SigmaRail working data root."""
    if os.path.isabs(file_path):
        return file_path
    data_cfg = get_data_config()
    data_root = Path(data_cfg.root or "data").expanduser()
    if not data_root.is_absolute():
        data_root = get_project_root() / data_root
    return str(data_root / file_path.lstrip("/\\"))


def load_single_csv(file_path: str, table_name: str) -> bool:
    """Load a single CSV file into the specified table.

    Args:
        file_path: Basename or path relative to configured data root (e.g. data/prod)
        table_name: Name of the table to load into

    Returns:
        bool: True if file was loaded successfully
    """
    try:
        logger.info(f"Starting load_single_csv for {file_path} into {table_name}")
        full_path = _resolve_csv_full_path(file_path)
        logger.info(f"Full path: {full_path}")
        db_config = get_database_config()
        logger.info(f"Database config: host={db_config.host}, port={db_config.port}, database={db_config.database}")

        # Check if file exists
        if not os.path.exists(full_path):
            logger.error(f"File does not exist: {full_path}")
            return False

        # Check if this file is likely to have many partitions by counting rows
        # Files with many rows are more likely to span many dates/partitions
        logger.info(f"Counting rows in {full_path}...")
        row_count = count_csv_rows(full_path)
        logger.info(f"File has {row_count:,} rows")

        # Tables with lastupdated columns typically span many years and create many partitions
        tables_with_many_partitions = {
            'sep', 'sfp', 'metrics', 'daily', 'sf1', 'tickers'
        }

        is_likely_many_partitions = (
            row_count > 100000 or  # Files with > 100k rows likely have many partitions
            table_name.lower() in tables_with_many_partitions  # Tables with lastupdated columns
        )

        if is_likely_many_partitions:
            logger.info(f"Large file detected ({row_count:,} rows), adjusting ClickHouse settings...")

        # Use clickhouse-client command line tool for CSV loading
        # Use absolute path for INFILE since ClickHouse needs to access the file directly
        absolute_path = os.path.abspath(full_path)
        infile_path = _infile_path_for_csv_load(absolute_path)
        via = _clickhouse_docker_container_for_infile() or "host"
        logger.info(
            "Absolute path: %s (INFILE path: %s; client via %s)",
            absolute_path,
            infile_path,
            f"docker exec {via}" if via != "host" else "host",
        )

        # Tables that need synthetic lastupdated column (not in source CSV)
        tables_needing_lastupdated = {'actions', 'sp500'}
        needs_lastupdated = table_name.lower() in tables_needing_lastupdated

        # Build the query with settings if needed
        if is_likely_many_partitions:
            if needs_lastupdated:
                # For tables needing lastupdated, use SELECT to add the synthetic column
                if table_name.lower() == 'actions':
                    query = """
                    SET max_partitions_per_insert_block = 1000;
                    SET max_insert_block_size = 1000000;
                    SET max_memory_usage = 20000000000;
                    SET max_bytes_before_external_group_by = 10000000000;
                    SET max_bytes_before_external_sort = 10000000000;
                    INSERT INTO actions (date, action, ticker, name, value, contraticker, contraname) FROM INFILE '{file_path}' FORMAT CSVWithNames;
                    """.format(file_path=infile_path)
                elif table_name.lower() == 'sp500':
                    query = """
                    SET max_partitions_per_insert_block = 1000;
                    SET max_insert_block_size = 1000000;
                    SET max_memory_usage = 20000000000;
                    SET max_bytes_before_external_group_by = 10000000000;
                    SET max_bytes_before_external_sort = 10000000000;
                    INSERT INTO sp500 (date, action, ticker, name, contraticker, contraname, note) FROM INFILE '{file_path}' FORMAT CSVWithNames;
                    """.format(file_path=infile_path)
            else:
                query = """
                SET max_partitions_per_insert_block = 1000;
                SET max_insert_block_size = 1000000;
                SET max_memory_usage = 20000000000;
                SET max_bytes_before_external_group_by = 10000000000;
                SET max_bytes_before_external_sort = 10000000000;
                INSERT INTO {table_name} FROM INFILE '{file_path}' FORMAT CSVWithNames;
                """.format(table_name=table_name, file_path=infile_path)
        else:
            if needs_lastupdated:
                # For tables needing lastupdated, use SELECT to add the synthetic column
                if table_name.lower() == 'actions':
                    query = f"INSERT INTO actions (date, action, ticker, name, value, contraticker, contraname) FROM INFILE '{infile_path}' FORMAT CSVWithNames"
                elif table_name.lower() == 'sp500':
                    query = f"INSERT INTO sp500 (date, action, ticker, name, contraticker, contraname, note) FROM INFILE '{infile_path}' FORMAT CSVWithNames"
            else:
                query = f"INSERT INTO {table_name} FROM INFILE '{infile_path}' FORMAT CSVWithNames"

        logger.info(f"Query: {query}")

        db_config = get_database_config()
        cmd = _clickhouse_client_argv_for_infile(db_config) + [
            "--multiquery",
            "--query",
            query,
        ]
        logger.info(
            "Invoking native client for INFILE (docker container=%s)",
            _clickhouse_docker_container_for_infile() or "(none, host client)",
        )

        # Increase timeout for files with many partitions
        timeout = 1800 if is_likely_many_partitions else 300  # 30 minutes for many partitions, 5 minutes for others
        logger.info(f"Loading with {timeout}s timeout...")

        logger.info(f"Executing clickhouse-client command...")
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)

        logger.info(f"Command completed with return code: {result.returncode}")
        if result.stdout:
            logger.info(f"Command stdout: {result.stdout[:500]}...")  # Log first 500 chars
        if result.stderr:
            logger.error(f"Command stderr: {result.stderr}")

        if result.returncode != 0:
            logger.error(f"Failed to load CSV file: {result.stderr}")
            return False

        logger.info(f"Successfully loaded {file_path}")
        return True

    except subprocess.TimeoutExpired as e:
        logger.error(f"Timeout loading CSV file {file_path}: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to load CSV file {file_path}: {e}")
        logger.exception(f"Full traceback for {file_path}:")
        return False

from sigmarail.sql_script import split_sql_statements as _split_sql_statements

def _execute_sql_file_http(
    sql_file: Path,
    params: Optional[Dict[str, Any]] = None,
    description: str = "SQL File",
) -> bool:
    """Execute a SQL file's statements over HTTP in their original file order."""
    try:
        text = sql_file.read_text()
        if params:
            for key, value in params.items():
                text = text.replace(f"{{{key}:String}}", str(value))
                text = text.replace(f"{{{key}:Date}}", str(value))
        client = get_client()
        for stmt in _split_sql_statements(text):
            client.command(stmt)
        logger.info(f"Successfully executed {description} (HTTP)")
        return True
    except Exception as e:
        logger.error(f"Failed to execute {description} via HTTP: {e}")
        print(f"❌ FAILED to execute {description} (HTTP)")
        print(f"Error: {e}")
        return False


def execute_sql_file(sql_file: Path, params: Optional[Dict[str, Any]] = None, description: str = "SQL File") -> bool:
    """
    Execute a SQL file using clickhouse-client.

    Args:
        sql_file: Path to the SQL file
        params: Dictionary of parameters for the query
        description: Description for logging purposes

    Returns:
        bool: True if execution was successful
    """
    if app_config.mode == "test":
        ok = _execute_sql_file_http(sql_file, params=params, description=description)
        return bool(ok)

    try:
        # Safety check: ensure test mode never connects to production
        _validate_test_mode_safety()

        db_config = get_database_config()
        cmd = [
            resolve_clickhouse_client_executable(),
            "--host", db_config.host,
            "--port", str(db_config.port),
            "--user", db_config.user,
            "--password", db_config.password,
            "--database", db_config.database,
            "--multiquery",
            "--stacktrace",
        ]

        if params:
            for key, value in params.items():
                cmd.append(f"--param_{key}={value}")

        text = Path(sql_file).read_text(encoding="utf-8")
        queries_file = str(sql_file)
        tmp_path = None
        cmd.append("--queries-file")
        cmd.append(queries_file)

        logger.debug(f"Executing {description} from {sql_file}")
        # Capture output to log errors properly
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=300)  # 5 minute timeout
        finally:
            if tmp_path:
                Path(tmp_path).unlink(missing_ok=True)

        if result.returncode != 0:
            logger.error(f"Failed to execute {description}")
            logger.error(f"Error output: {result.stderr[:1000]}")  # Log first 1000 chars of error
            print(f"❌ FAILED to execute {description}")
            print(f"Error: {result.stderr[:500]}")  # Show first 500 chars to user
            return False

        logger.info(f"Successfully executed {description}")
        return True

    except subprocess.TimeoutExpired as e:
        logger.error(f"Timeout executing {description} from {sql_file}: {e}")
        return False
    except Exception as e:
        logger.exception(f"An unexpected error occurred during {description} execution: {e}")
        return False

def _quote_ch_identifier(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"


def _quote_ch_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _normalize_ch_type(value: str) -> str:
    """Ignore formatting whitespace in ClickHouse type strings, preserving quoted labels."""
    normalized: List[str] = []
    quote: Optional[str] = None
    escaped = False
    for char in value.strip():
        if quote:
            normalized.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in ("'", '"', "`"):
            quote = char
            normalized.append(char)
        elif not char.isspace():
            normalized.append(char)
    return "".join(normalized)


def _schema_reconciliation_statements(
    expected_tables: List[Dict[str, Any]],
    actual_rows: List[Tuple[str, str, str, str]],
    drop_extra_columns: bool = False,
) -> Tuple[List[str], List[str]]:
    """Return safe ALTER statements and blocking schema drift diagnostics."""
    actual = {(table, name): {"type": typ, "comment": comment or ""}
              for table, name, typ, comment in actual_rows}
    statements: List[str] = []
    issues: List[str] = []
    for table in expected_tables:
        table_name = table["name"]
        expected = {column["name"]: column for column in table["columns"]}
        current = {name: values for (tbl, name), values in actual.items() if tbl == table_name}
        for name, column in expected.items():
            found = current.get(name)
            if found is None:
                statements.append(
                    f"ALTER TABLE {_quote_ch_identifier(table_name)} ADD COLUMN IF NOT EXISTS "
                    f"{_quote_ch_identifier(name)} {column['type']} COMMENT {_quote_ch_string(column.get('comment', ''))}"
                )
            elif _normalize_ch_type(found["type"]) != _normalize_ch_type(column["type"]):
                issues.append(f"{table_name}.{name}: type is {found['type']}, expected {column['type']}; explicit migration required")
            elif found["comment"] != column.get("comment", ""):
                statements.append(
                    f"ALTER TABLE {_quote_ch_identifier(table_name)} COMMENT COLUMN "
                    f"{_quote_ch_identifier(name)} {_quote_ch_string(column.get('comment', ''))}"
                )
        extras = sorted(set(current) - set(expected))
        if extras and not drop_extra_columns:
            issues.append(
                f"{table_name}: undeclared columns {', '.join(extras)}; "
                "review deletion with --drop-extra-columns, then apply with --apply"
            )
        elif extras:
            for name in extras:
                statements.append(
                    f"ALTER TABLE {_quote_ch_identifier(table_name)} DROP COLUMN IF EXISTS {_quote_ch_identifier(name)}"
                )
    return statements, issues


def _print_schema_plan(
    database: str,
    create_statements: List[str],
    other_statements: List[str],
    alter_statements: List[str],
    issues: List[str],
    drops: List[Tuple[str, str]],
    views: List[Tuple[str, str]],
    apply: bool,
) -> None:
    """Print a compact, reproducible schema plan."""
    label = "Applying" if apply else "Preview (read-only)"
    print(f"SigmaRail schema {label} for database {database}")
    print(f"  Create missing tables: {len(create_statements)}")
    for statement in create_statements:
        head = _sql_statement_head(statement).strip().splitlines()[0]
        print(f"    + {head[:180]}")
    print(f"  Other SQL statements: {len(other_statements)}")
    print(f"  Column changes: {len(alter_statements)}")
    for statement in alter_statements:
        print(f"    ~ {statement}")
    print(f"  Refresh views: drop {len(drops)}, create {len(views)}")
    if issues:
        print("  Blockers:")
        for issue in issues:
            print(f"    ! {issue}")
    elif not apply:
        print("  Plan is ready. Re-run with --apply to execute it.")
    if not apply and any("DROP COLUMN" in statement for statement in alter_statements):
        print("  Column deletion is planned; re-run with --apply --drop-extra-columns to execute it.")


def _schema_object_name(statement: str, kind: str) -> Optional[str]:
    match = re.match(
        rf"(?is)^{kind}\s+(?:IF\s+(?:NOT\s+)?EXISTS\s+)?`?([A-Za-z_][\w]*)`?\b",
        _sql_statement_head(statement).strip(),
    )
    return match.group(1) if match else None


def load_schema(drop_extra_columns: bool = False, apply: bool = True) -> bool:
    """Plan or apply creation, reconciliation, and refresh of the core schema.

    The packaged SQL remains the source of truth. Core tables are described by
    the generated lineage manifest; extension data belongs in separate tables.
    Internal callers apply by default. The ``sigmarail-schema`` CLI opts into apply
    explicitly; its normal mode is a read-only plan.
    """
    try:
        db_config = get_database_config()
        _validate_test_mode_safety()
        schema_dir = get_schema_dir()
        if not schema_dir.is_dir():
            logger.error("Schema directory not found: %s", schema_dir)
            return False
        sql_files = get_schema_files()
        if not sql_files:
            logger.error("No SQL statements found in %s", schema_dir)
            return False

        tables: List[str] = []
        drops: List[Tuple[str, str]] = []
        views: List[Tuple[str, str]] = []
        other: List[str] = []
        for sql_file in sql_files:
            for statement in _split_sql_statements(sql_file.read_text(encoding="utf-8")):
                head = _sql_statement_head(statement).strip()
                table_name = _schema_object_name(head, r"CREATE\s+TABLE")
                view_name = _schema_object_name(head, r"CREATE\s+VIEW")
                drop_name = _schema_object_name(head, r"DROP\s+VIEW")
                if table_name:
                    tables.append(statement)
                elif view_name:
                    views.append((view_name, statement))
                elif drop_name:
                    drops.append((drop_name, statement))
                elif head:
                    other.append(statement)

        client = get_client()
        if not client:
            logger.error("Failed to get ClickHouse client")
            return False
        contract_path = Path(__file__).resolve().parent / "spec" / "lineage-manifest.json"
        expected_tables = json.loads(contract_path.read_text(encoding="utf-8"))["tables"]
        names = [table["name"] for table in expected_tables]
        escaped_names = ",".join(_quote_ch_string(name) for name in names)
        existing_result = client.query(
            "SELECT name FROM system.tables "
            f"WHERE database = {_quote_ch_string(db_config.database)} AND name IN ({escaped_names})"
        )
        existing_tables = {row[0] for row in existing_result.result_rows}
        create_statements = [
            statement for statement in tables
            if _schema_object_name(statement, r"CREATE\s+TABLE") not in existing_tables
        ]

        # Applying creates all tables before inspecting columns so freshly
        # created tables already match their source DDL. Preview never executes
        # any SQL statement.
        if apply:
            logger.info("Creating SigmaRail tables in %s", db_config.database)
            for statement in tables + other:
                client.command(statement)
            existing_tables = set(names)

        result = client.query(
            "SELECT table, name, type, comment FROM system.columns "
            f"WHERE database = {_quote_ch_string(db_config.database)} AND table IN ({escaped_names})"
        )
        expected_present = [table for table in expected_tables if table["name"] in existing_tables]
        alter_statements, issues = _schema_reconciliation_statements(
            expected_present, list(result.result_rows), drop_extra_columns=drop_extra_columns
        )
        _print_schema_plan(
            db_config.database, create_statements, other, alter_statements,
            issues, drops, views, apply,
        )
        if issues:
            for issue in issues:
                logger.error("SigmaRail schema drift: %s", issue)
            return not apply

        if not apply:
            return True

        # Drop in reverse dependency order, independent of where DROP statements
        # appeared in the source files; recreate in declared manifest order.
        drops_by_name: Dict[str, List[str]] = {}
        for name, statement in drops:
            drops_by_name.setdefault(name, []).append(statement)
        consumed_drops = set()
        for view_name, _ in reversed(views):
            for statement in drops_by_name.get(view_name, []):
                client.command(statement)
                consumed_drops.add(id(statement))
        # Preserve executable SQL even for a DROP VIEW that has no matching
        # CREATE VIEW in this release's manifest.
        for _, statement in drops:
            if id(statement) not in consumed_drops:
                client.command(statement)
        for statement in alter_statements:
            client.command(statement)
        for _, statement in views:
            client.command(statement)

        logger.info("SigmaRail schema loaded and reconciled successfully")
        return True
    except Exception as e:
        logger.error("Failed to load schema: %s", e)
        print(f"❌ CRITICAL ERROR loading schema: {e}")
        return False


def load_bootstrap_data() -> bool:
    """Explicitly load idempotent reference/bootstrap INSERTs from sql/bootstrap.

    This is separate from schema creation and is never called by populate or
    load_schema. Run it after base source tables such as ``tickers`` are loaded.
    """
    project_root = get_project_root()
    bootstrap_dir = project_root / "sql" / "bootstrap"
    if not bootstrap_dir.is_dir():
        logger.error("Bootstrap data directory not found: %s", bootstrap_dir)
        return False

    sql_files = sorted(bootstrap_dir.glob("*.sql"), key=_schema_sql_sort_key)
    if not sql_files:
        logger.error("No bootstrap data files found in %s", bootstrap_dir)
        return False

    invalid_statements: List[Tuple[Path, str]] = []
    for sql_file in sql_files:
        for statement in _split_sql_statements(sql_file.read_text(encoding="utf-8")):
            head = _sql_statement_head(statement)
            if head.strip() and not re.match(r"(?is)^INSERT\s+INTO\b", head):
                invalid_statements.append((sql_file, head))
    if invalid_statements:
        details = "; ".join(
            f"{path.name}: {head.strip().splitlines()[0][:120]}"
            for path, head in invalid_statements[:10]
        )
        logger.error("Bootstrap directory contains non-INSERT SQL: %s", details)
        print(f"❌ Bootstrap load blocked; only INSERT statements are allowed: {details}")
        return False

    for sql_file in sql_files:
        if not execute_sql_file(sql_file, description=f"Bootstrap data {sql_file.name}"):
            return False
    return True

def initialize_database(auto_load_schema: bool = False) -> bool:
    """Initialize the database with schema if needed.

    Args:
        auto_load_schema: If True, automatically load schema

    Returns:
        bool: True if initialization was successful
    """
    try:
        db_config = get_database_config()
        logger.info(f"Initializing ClickHouse client for {app_config.mode} mode: {db_config.host}:{db_config.port}")

        # Get client (database creation is handled by get_client)
        client = get_client()
        if not client:
            logger.error(f"Failed to initialize client in mode '{app_config.mode}'!")
            return False

        # If auto_load_schema is enabled, load the schema
        if auto_load_schema:
            logger.info("Auto-loading schema...")
            if not load_schema():
                logger.error("Failed to auto-load schema")
                return False
            logger.info("Schema auto-loaded successfully")

        return True

    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return False

# Command-line interface functions below
def initialize_database_command() -> bool:
    """
    Initialize the database with schema.

    Returns:
        bool: True if initialization was successful
    """
    # Safety check: Only allow database initialization in test mode
    if app_config.mode != 'test':
        logger.error(f"DATABASE INITIALIZATION BLOCKED: This operation is only allowed in test mode, not '{app_config.mode}'")
        logger.error("Use test mode if you need to initialize a database")
        print(f"❌ BLOCKED: Database initialization only allowed in test mode, not '{app_config.mode}'")
        return False

    try:
        logger.info(f"Initializing database for mode: {app_config.mode}")
        print(f"🚀 Initializing database for mode: {app_config.mode}")

        # Database creation is handled automatically by get_client()
        print("📊 Database will be created automatically if needed...")

        # Then load the schema
        print("📋 Loading schema files...")
        if not load_schema():
            logger.error("Failed to load schema")
            print("❌ FAILED to load schema")
            return False

        logger.info("Database initialization completed successfully")
        print("✅ Database initialization completed successfully")
        return True

    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        print(f"❌ CRITICAL ERROR initializing database: {e}")
        import traceback
        print(f"Stack trace:\n{traceback.format_exc()}")
        return False

def drop_and_recreate_database() -> bool:
    """
    Drop and recreate the database.

    Returns:
        bool: True if operation was successful
    """
    # Safety check: Only allow dropping database in test mode
    if app_config.mode != 'test':
        logger.error(f"DROP AND RECREATE OPERATION BLOCKED: This operation is only allowed in test mode, not '{app_config.mode}'")
        logger.error("Use test mode if you need to drop and recreate a database")
        print(f"❌ BLOCKED: Database drop/recreate only allowed in test mode, not '{app_config.mode}'")
        return False

    try:
        logger.info(f"Dropping and recreating database for mode: {app_config.mode}")
        db_config = get_database_config()
        # Create a temporary client connected to default database
        temp_client = clickhouse_connect.get_client(
            host=db_config.host,
            port=db_config.http_port,
            username=db_config.user,
            password=db_config.password,
            database='default',
        )
        database_name = db_config.database
        # Drop the database if it exists
        temp_client.command(f"DROP DATABASE IF EXISTS {database_name}")
        logger.info(f"Dropped existing database: {database_name}")

        # Create the database
        temp_client.command(f"CREATE DATABASE {database_name}")
        logger.info(f"Created fresh database: {database_name}")

        # Close the temp client
        temp_client.close()

        # Reset the singleton client so it will reconnect to the fresh database
        global _client_instance
        if _client_instance:
            _client_instance.close()
            _client_instance = None

        return True

    except Exception as e:
        logger.error(f"Failed to drop/recreate database: {e}")
        return False

def verify_database_connection() -> bool:
    """
    Verify database connection and basic functionality.

    Returns:
        bool: True if connection is successful
    """
    try:
        client = get_client()
        result = client.query("SELECT 1 as test")
        if result.result_rows and result.result_rows[0][0] == 1:
            logger.info("Database connection verified successfully")
            return True
        else:
            logger.error("Database connection test failed")
            return False
    except Exception as e:
        logger.error(f"Failed to verify database connection: {e}")
        return False

def main() -> int:
    """Command-line entry point for database operations.

    Returns:
        int: Exit code (0 for success, 1 for failure)
    """
    # Set up argument parser
    parser = argparse.ArgumentParser(
        description='Database operations for ClickHouse',
        parents=[create_shared_parser()]
    )

    # Add database operation arguments
    parser.add_argument(
        '--initialize-database',
        action='store_true',
        help='Initialize the database by creating missing schema tables and views'
    )
    parser.add_argument(
        '--load-bootstrap-data',
        action='store_true',
        help='Explicitly load idempotent reference data from sql/bootstrap (run after source data load)'
    )
    parser.add_argument(
        '--drop-and-recreate',
        action='store_true',
        help='Drop and recreate the database (WARNING: This will delete all data!)'
    )
    parser.add_argument(
        '--verify-connection',
        action='store_true',
        help='Verify database connection'
    )
    parser.add_argument(
        '--optimize',
        action='store_true',
        help='Optimize ReplacingMergeTree tables (use --tables to specify which tables)'
    )
    parser.add_argument(
        '--tables',
        nargs='+',
        help='Optional list of specific tables to optimize (only used with --optimize). '
             'If omitted, all ReplacingMergeTree tables are optimized. '
             'Example: --optimize --tables sep sfp metrics'
    )
    parser.add_argument(
        '--dup-check',
        nargs='?',
        type=int,
        default=None,
        const=30,
        metavar='DAYS',
        help='Optional: after optimize, run a light duplicate check on recent data only (bounded memory). '
             'Use with --optimize. If DAYS is omitted, 30 is used. If --dup-check is not given, no dup-check runs. '
             'Example: --optimize --dup-check 7'
    )
    parser.add_argument(
        '--clear-caches',
        action='store_true',
        help='Clear ClickHouse caches to free memory (useful when encountering memory errors)'
    )

    args = parser.parse_args()

    # Handle shared args
    process_shared_args(args)

    try:
        # Check if any operation was specified
        if not any([args.initialize_database, args.load_bootstrap_data, args.drop_and_recreate, args.verify_connection, args.optimize, args.clear_caches]):
            logger.error("No operation specified. Use --help for available options.")
            return 1

        # Perform requested operations
        success = True

        if args.drop_and_recreate:
            if app_config.mode == 'prod':
                logger.error("Drop and recreate operation is not allowed in production mode")
                return 1
            success = success and drop_and_recreate_database()

        if args.initialize_database:
            success = success and initialize_database_command()

        if args.load_bootstrap_data:
            success = success and load_bootstrap_data()

        if args.verify_connection:
            success = success and verify_database_connection()

        if args.clear_caches:
            success = success and clear_caches()

        if args.optimize:
            success = success and optimize_tables(
                tables=args.tables,
                dup_check_recent_days=args.dup_check,
            )

        if success:
            logger.info("Database operations completed successfully!")
            return 0
        else:
            logger.error("One or more database operations failed")
            return 1

    except Exception as e:
        logger.exception(f"An unexpected error occurred during database operations: {e}")
        return 1


# Define what should be exported from this module
__all__ = [
    'get_client', 'initialize_database', 'load_schema', 'load_bootstrap_data',
    'load_single_csv', 'execute_sql_file',
]


if __name__ == '__main__':
    exit(main())
