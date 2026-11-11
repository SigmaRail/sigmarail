"""
Command to populate ClickHouse metrics tables (daily_metrics, weekly_metrics, etc.)
"""
import argparse
import logging
import os
import re
import time
import yaml
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import pandas as pd

if __name__ == '__main__' and __package__ is None:
    project_src = Path(__file__).resolve().parents[1]
    if str(project_src) not in sys.path:
        sys.path.insert(0, str(project_src))

from sigmarail.database import get_client, load_schema

from sigmarail.config import (
    create_shared_parser,
    process_shared_args,
    app_config,
    get_database_config,
    get_project_root,
)
from sigmarail.transform_sql import (
    TransformSpec,
    chunk_insert_sql,
    discover_legacy_transform_files,
    discover_transform_specs,
    parse_header_config,
    parse_transform,
    register_all_transform_views,
    transform_catalog,
    view_name_for,
)

logger = logging.getLogger(__name__)


def _metric_sql_sort_key(path: Path) -> Tuple[int, str]:
    """Sort transform files by numeric prefix (98 before 100), then filename."""
    match = re.match(r'^(\d+)-', path.name)
    order = int(match.group(1)) if match else 999999
    return (order, path.name)


# Filename overrides are retained for legacy transforms without COMMENT config.
# View transforms declare on_hold in their COMMENT JSON.
DEPRECATED_POPULATE_SQL_FILES = frozenset({
})
ON_HOLD_POPULATE_SQL_FILES = frozenset({
})


def _split_metrics_args(metrics: Optional[List[str]]) -> Optional[List[str]]:
    """Expand CLI --metrics tokens; accept comma-separated lists in one arg."""
    if metrics is None:
        return None
    expanded: List[str] = []
    for token in metrics:
        for part in str(token).split(","):
            name = part.strip()
            if name:
                expanded.append(name)
    return expanded


def _rewrite_metric_sql_database_qualifier(sql_content: str) -> str:
    """Rewrite the SigmaRail database qualifier for isolated test databases."""
    if app_config.mode != "test":
        return sql_content
    db = get_database_config().database
    if not db or db == "sigmarail":
        return sql_content
    return sql_content.replace("sigmarail.", f"{db}.")

class DataPopulator:
    """A class to populate metrics tables in ClickHouse."""

    # Sharadar source tables are owned by sigmarail-load, not by transforms.
    BASE_DATA_TABLES = {
        'tickers', 'sep', 'sfp', 'metrics', 'daily', 'sf1', 'actions',
        'events', 'sf2', 'sf3', 'sf3a', 'sf3b', 'sp500',
    }

    # Marts whose rows must track vendor price rewrites (sep/sfp lastupdated).
    PRICE_PIPELINE_TARGETS = frozenset({
        'daily_metrics',
        'daily_metrics_derived',
        'daily_price_sequence',
        'weekly_metrics',
        'weekly_metrics_derived',
        'relative_strength_base',
        'relative_strength_ranks',
        'relative_strength',
        'broad_market_breadth',
        'broad_market_breadth_weekly',
        'market_trend_template',
        'enhanced_bear_market_signals',
        'market_regime_signals',
        'market_regime_signals_daily',
        'industry_group_strength',
        'minervini_trend_template',
        'daily_fundamentals',
        'screener_fundamentals_daily',
        'screener_price_tech_daily',
        'stage_analysis',
        'technical_ratings',
        'accumulation_distribution_rating',
        'screener_ratings',
        'screener_ratings_daily',
        'ownership_signals_daily',
        'screener_stage_weekly_daily',
        'screener_ownership_daily',
    })

    # Corporate actions that imply historical price restatement (matches recalculation_events_view).
    RECALC_PRICE_ACTIONS = (
        'split',
        'spinoff',
        'spinoffdividend',
        'adrratiosplit',
    )
    # Cap auto lookback so one split does not force a full 1998→today universe refresh.
    AUTO_RECALC_MAX_LOOKBACK_DAYS = 730
    AUTO_RECALC_EVENT_LOOKBACK_DAYS = 14

    def __init__(self):
        """Initialize the DataPopulator."""
        self.client = get_client()
        if not self.client:
            raise RuntimeError(f"Failed to get ClickHouse client for mode '{app_config.mode}'")

        # Define chunk size mappings
        self.chunk_size_mappings = {
            '0m': None,    # Complete timeframe (no chunking)
            '1w': 7,       # 1 week
            '1m': 30,      # 1 month
            '3m': 90,      # 3 months
            '6m': 180,     # 6 months
            '12m': 365     # 12 months
        }

    @staticmethod
    def _is_darwin() -> bool:
        return sys.platform == 'darwin'

    def _populate_query_settings(self, sql_or_spec=None) -> Dict:
        """Conservative per-query limits to avoid macOS SIGILL crashes under memory pressure.

        Override via env: SIGMARAIL_POPULATE_MAX_MEMORY_BYTES, SIGMARAIL_POPULATE_MAX_THREADS, etc.
        A transform can override selected limits through its view COMMENT config.
        """
        default_mem = '4000000000' if self._is_darwin() else '6000000000'
        default_threads = '4' if self._is_darwin() else '6'
        max_memory = int(os.environ.get('SIGMARAIL_POPULATE_MAX_MEMORY_BYTES', default_mem))
        max_memory_user = int(os.environ.get(
            'SIGMARAIL_POPULATE_MAX_MEMORY_USER_BYTES',
            str(min(int(max_memory * 1.1), 8_000_000_000)),
        ))
        max_threads = int(os.environ.get('SIGMARAIL_POPULATE_MAX_THREADS', default_threads))
        settings = {
            'max_memory_usage': max_memory,
            'max_memory_usage_for_user': max_memory_user,
            'max_bytes_before_external_group_by': 1_000_000_000,
            'max_bytes_before_external_sort': 1_000_000_000,
            'max_threads': max_threads,
            'max_block_size': 32768 if self._is_darwin() else 65536,
        }
        # macOS native 26.x SIGILL in LLVM JIT (clickhouse-*.ips: JITCompiler::compile via
        # compile_aggregate_expressions and/or compile_expressions). Same SQL/results.
        if self._is_darwin() and os.environ.get('SIGMARAIL_POPULATE_COMPILE_AGGREGATES', '0') != '1':
            settings['compile_aggregate_expressions'] = 0
            settings['compile_expressions'] = 0
            settings['compile_sort_description'] = 0
        if isinstance(sql_or_spec, TransformSpec):
            for setting_name in ('max_memory_usage', 'max_memory_usage_for_user'):
                memory_limit = sql_or_spec.config.get(setting_name)
                if memory_limit is not None:
                    memory_limit = int(memory_limit)
                    if memory_limit < 1:
                        raise ValueError(f'{setting_name} must be positive')
                    settings[setting_name] = memory_limit
            partition_limit = sql_or_spec.config.get('max_partitions_per_insert_block')
            if partition_limit is not None:
                partition_limit = int(partition_limit)
                if partition_limit < 1:
                    raise ValueError('max_partitions_per_insert_block must be positive')
                settings['max_partitions_per_insert_block'] = partition_limit
            final_partition_merge = sql_or_spec.config.get(
                'do_not_merge_across_partitions_select_final'
            )
            if final_partition_merge is not None:
                final_partition_merge = int(final_partition_merge)
                if final_partition_merge not in (0, 1):
                    raise ValueError(
                        'do_not_merge_across_partitions_select_final must be 0 or 1'
                    )
                settings['do_not_merge_across_partitions_select_final'] = (
                    final_partition_merge
                )
        return settings

    def _inter_chunk_sleep_seconds(self) -> float:
        default = '0' if self._is_darwin() else '3'
        return float(os.environ.get('SIGMARAIL_POPULATE_INTER_CHUNK_SLEEP_SEC', default))

    def _merge_wait_timeout_seconds(self) -> int:
        default = '300' if self._is_darwin() else '180'
        return int(os.environ.get('SIGMARAIL_POPULATE_MERGE_WAIT_SEC', default))

    def _refresh_client(self) -> None:
        """New HTTP session per chunk — avoids crashes seen reusing sessions on macOS."""
        try:
            self.client.close()
        except Exception:
            pass
        self.client = get_client()
        if not self.client:
            raise RuntimeError('Failed to refresh ClickHouse client')

    def _transform_target_table(self, sql_or_spec) -> Optional[str]:
        if isinstance(sql_or_spec, TransformSpec):
            return sql_or_spec.target
        config = self._parse_transform_config(sql_or_spec)
        if config:
            return config.get('target')
        return None

    def _chunk_sql_params(
        self,
        sql_or_spec,
        chunk_start: str,
        chunk_end: str,
        *,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            'chunk_start_date': chunk_start,
            'chunk_end_date': chunk_end,
        }
        if isinstance(sql_or_spec, TransformSpec):
            declares_force_refresh = (
                'force_refresh' in sql_or_spec.param_names
                if sql_or_spec.shape == 'view'
                else '{force_refresh' in sql_or_spec.body
            )
            if declares_force_refresh:
                params['force_refresh'] = 1 if force_refresh else 0
        elif '{force_refresh' in sql_or_spec:
            params['force_refresh'] = 1 if force_refresh else 0
        return params

    def _chunk_source_newer_than_target(
        self, target_table: str, chunk_start: str, chunk_end: str
    ) -> bool:
        """True when upstream source data is newer than target for this chunk.

        After a Sharadar split rewrite, trading days already exist in the mart but
        lastupdated on sep/sfp (or daily_metrics for downstream) is newer — do not skip.
        Market-regime daily rows also depend on breadth, so freshness is compared
        per date across daily_metrics, broad_market_breadth, and the target. A
        chunk-wide maximum can hide an old date needing refresh behind a newer
        target row on a different date.
        """
        if target_table not in self.PRICE_PIPELINE_TARGETS:
            return False
        try:
            if target_table == 'market_regime_signals_daily':
                result = self.client.query(
                    f"""
                    WITH
                    source_daily AS (
                        SELECT date, max(toUnixTimestamp(lastupdated)) AS daily_lu
                        FROM daily_metrics FINAL
                        WHERE date BETWEEN toDate('{chunk_start}') AND toDate('{chunk_end}')
                        GROUP BY date
                    ),
                    source_breadth AS (
                        SELECT date, max(toUnixTimestamp(last_populated)) AS breadth_lu
                        FROM broad_market_breadth FINAL
                        WHERE date BETWEEN toDate('{chunk_start}') AND toDate('{chunk_end}')
                        GROUP BY date
                    ),
                    target_rows AS (
                        SELECT date, max(toUnixTimestamp(lastupdated)) AS target_lu
                        FROM {target_table} FINAL
                        WHERE date BETWEEN toDate('{chunk_start}') AND toDate('{chunk_end}')
                        GROUP BY date
                    ),
                    per_date_freshness AS (
                        SELECT
                            d.date,
                            greatest(d.daily_lu, coalesce(b.breadth_lu, toUInt32(0))) AS source_lu,
                            coalesce(t.target_lu, toUInt32(0)) AS target_lu
                        FROM source_daily AS d
                        LEFT JOIN source_breadth AS b ON b.date = d.date
                        LEFT JOIN target_rows AS t ON t.date = d.date
                    )
                    SELECT countIf(source_lu > target_lu) > 0
                    FROM per_date_freshness
                    """
                )
                return bool(result.result_rows and result.result_rows[0][0])

            if target_table == 'daily_metrics':
                source_expr = f"""
                    SELECT max(lastupdated) AS source_lu FROM (
                        SELECT lastupdated FROM sep FINAL
                        WHERE date BETWEEN toDate('{chunk_start}') AND toDate('{chunk_end}')
                        UNION ALL
                        SELECT lastupdated FROM sfp FINAL
                        WHERE date BETWEEN toDate('{chunk_start}') AND toDate('{chunk_end}')
                    )
                """
                target_expr = f"""
                    SELECT max(lastupdated) FROM {target_table} FINAL
                    WHERE date BETWEEN toDate('{chunk_start}') AND toDate('{chunk_end}')
                """
            else:
                source_expr = f"""
                    SELECT max(lastupdated) AS source_lu FROM daily_metrics FINAL
                    WHERE date BETWEEN toDate('{chunk_start}') AND toDate('{chunk_end}')
                """
                target_expr = f"""
                    SELECT max(lastupdated) FROM {target_table} FINAL
                    WHERE date BETWEEN toDate('{chunk_start}') AND toDate('{chunk_end}')
                """
            result = self.client.query(
                f"""
                SELECT
                    ({source_expr}) AS source_lu,
                    ({target_expr}) AS target_lu
                """
            )
            if not result.result_rows:
                return False
            source_lu, target_lu = result.result_rows[0]
            if source_lu is None or target_lu is None:
                return False
            return source_lu > target_lu
        except Exception as e:
            logger.debug(f"    Chunk source-newer check skipped: {e}")
            return False

    def _chunk_dates_already_populated(
        self, target_table: str, chunk_start: str, chunk_end: str
    ) -> bool:
        """Skip chunks already filled (resume after SIGILL crash without --start-date).

        Does not skip when upstream lastupdated is newer than the target (split rewrites).
        """
        if os.environ.get('SIGMARAIL_POPULATE_FORCE_CHUNKS', '').strip().lower() in ('1', 'true', 'yes'):
            return False
        try:
            result = self.client.query(
                f"""
                SELECT
                    (SELECT count() FROM daily_price_sequence
                     WHERE date BETWEEN toDate('{chunk_start}') AND toDate('{chunk_end}')) AS expected_days,
                    (SELECT countDistinct(date) FROM {target_table}
                     WHERE date BETWEEN toDate('{chunk_start}') AND toDate('{chunk_end}')) AS populated_days
                """
            )
            if not result.result_rows:
                return False
            expected, populated = int(result.result_rows[0][0]), int(result.result_rows[0][1])
            if expected > 0 and populated >= expected:
                if self._chunk_source_newer_than_target(target_table, chunk_start, chunk_end):
                    logger.info(
                        f"    Chunk {chunk_start} to {chunk_end} has rows in {target_table} "
                        f"but upstream lastupdated is newer — not skipping"
                    )
                    return False
                return True
        except Exception as e:
            logger.debug(f"    Chunk resume check skipped: {e}")
        return False

    def get_recalculation_events(
        self, lookback_days: Optional[int] = None
    ) -> Dict[str, Any]:
        """Query recalculation_events_view for recent price-impacting corporate actions.

        Returns dict with keys: events (list), tickers (list), min_recalc_start (str|None),
        event_count (int).
        """
        days = lookback_days if lookback_days is not None else self.AUTO_RECALC_EVENT_LOOKBACK_DAYS
        empty: Dict[str, Any] = {
            'events': [],
            'tickers': [],
            'min_recalc_start': None,
            'event_count': 0,
        }
        try:
            cutoff = (datetime.now().date() - timedelta(days=days)).strftime('%Y-%m-%d')
            action_list = ", ".join(f"'{a}'" for a in self.RECALC_PRICE_ACTIONS)
            result = self.client.query(
                f"""
                SELECT
                    toString(date) AS event_date,
                    action,
                    ticker,
                    toString(recalculation_start_date) AS recalc_start
                FROM recalculation_events_view
                WHERE date >= toDate('{cutoff}')
                  AND action IN ({action_list})
                  AND source = 'actions'
                ORDER BY date DESC, ticker
                LIMIT 500
                """
            )
            rows = result.result_rows or []
            if not rows:
                return empty
            events = [
                {
                    'date': r[0],
                    'action': r[1],
                    'ticker': r[2],
                    'recalculation_start_date': r[3],
                }
                for r in rows
            ]
            tickers = sorted({e['ticker'] for e in events if e.get('ticker')})
            recalc_dates = [
                e['recalculation_start_date']
                for e in events
                if e.get('recalculation_start_date') and e['recalculation_start_date'] != '1970-01-01'
            ]
            min_recalc = min(recalc_dates) if recalc_dates else None
            return {
                'events': events,
                'tickers': tickers,
                'min_recalc_start': min_recalc,
                'event_count': len(events),
            }
        except Exception as e:
            logger.warning(f"Could not query recalculation_events_view: {e}")
            return empty

    def apply_auto_recalc_events(
        self,
        explicit_start: Optional[str],
        force_refresh: bool,
        enabled: bool = True,
    ) -> Tuple[Optional[str], bool]:
        """Widen start date and enable force_refresh when recent split/spinoff events exist.

        Caps lookback at AUTO_RECALC_MAX_LOOKBACK_DAYS. Does not override an explicit
        --start-date. Returns (effective_start_or_None, force_refresh).
        """
        if not enabled:
            return explicit_start, force_refresh
        if explicit_start:
            # Explicit range is authoritative; still allow caller force_refresh.
            return explicit_start, force_refresh

        info = self.get_recalculation_events()
        if info['event_count'] == 0:
            return explicit_start, force_refresh

        today = datetime.now().date()
        floor = (today - timedelta(days=self.AUTO_RECALC_MAX_LOOKBACK_DAYS)).strftime('%Y-%m-%d')
        min_recalc = info['min_recalc_start'] or floor
        # Cap: never go earlier than floor for auto daily runs.
        effective_start = max(min_recalc, floor)

        tickers_preview = ', '.join(info['tickers'][:20])
        if len(info['tickers']) > 20:
            tickers_preview += f", … (+{len(info['tickers']) - 20} more)"
        logger.info(
            "Auto-recalc: %s price-impacting event(s) in last %s days; "
            "tickers=[%s]; enabling force_refresh from %s (capped at %s-day lookback)",
            info['event_count'],
            self.AUTO_RECALC_EVENT_LOOKBACK_DAYS,
            tickers_preview,
            effective_start,
            self.AUTO_RECALC_MAX_LOOKBACK_DAYS,
        )
        print(
            f"🔁 Auto-recalc: {info['event_count']} event(s); "
            f"force-refresh from {effective_start} "
            f"(tickers: {tickers_preview})",
            flush=True,
        )
        return effective_start, True

    def _get_all_derived_tables(self) -> List[str]:
        """All derived tables written by transform SQL — parsed from transform targets.

        A hand-curated list drifts silently: new transforms never run in the test
        fixture populate (empty marts) and never drop under --rebuild. Parsing the
        target out of each transform keeps this complete by construction.
        """
        tables: set[str] = set()
        for spec in discover_transform_specs():
            if spec.target:
                tables.add(spec.target)
        for sql_file in discover_legacy_transform_files():
            for match in re.finditer(
                r'INSERT\s+INTO\s+(?:[A-Za-z_]\w*\.)?([A-Za-z_]\w*)',
                sql_file.read_text(),
            ):
                tables.add(match.group(1))
        # Never list base data tables even if a transform mentions them.
        return sorted(tables - self.BASE_DATA_TABLES)

    def _spec_matches_request(self, spec: TransformSpec, requested: str) -> bool:
        """Match --metrics by slug ('relative-strength') or target ('relative_strength')."""
        requested_normalized = requested.replace('-', '_')
        if spec.name.replace('-', '_') == requested_normalized:
            return True
        if spec.target and spec.target.replace('-', '_') == requested_normalized:
            return True
        if spec.view_name and spec.view_name == requested_normalized:
            return True
        return False

    def _spec_on_hold(self, spec: TransformSpec) -> bool:
        """Whether the transform is explicitly held in view config or legacy filenames."""
        if spec.config.get('on_hold'):
            return True
        if spec.path is not None:
            return spec.path.name in ON_HOLD_POPULATE_SQL_FILES
        return False

    def _spec_deprecated(self, spec: TransformSpec) -> bool:
        """Deprecated/on-hold per COMMENT config (view) or filename sets (legacy)."""
        if spec.deprecated or self._spec_on_hold(spec):
            return True
        if spec.path is not None:
            return spec.path.name in DEPRECATED_POPULATE_SQL_FILES
        return False

    def _get_transform_specs(self, requested_metrics: List[str] = None) -> List[TransformSpec]:
        """Populate's transform schedule — registered xform_* views from the DB.

        The database is the schedule: ordering (config.order), chunk_size,
        sources and deprecated flags come from the COMMENT JSON on registered
        views. File-derived specs are the fallback when the catalog is empty
        (e.g. unit tests without a client); legacy insert-shape files run when
        no registered view covers their target (dual-shape migration path).
        """
        try:
            specs = transform_catalog(self.client)
        except Exception as e:
            logger.warning(f"Transform catalog read failed; falling back to files: {e}")
            specs = []

        if specs:
            file_by_view = {
                local.view_name: local.path
                for local in discover_transform_specs()
                if local.view_name and local.path
            }
            for spec in specs:
                spec.path = file_by_view.get(spec.view_name)
        else:
            specs = discover_transform_specs()

        view_targets = {s.target for s in specs if s.target}
        for path in sorted(discover_legacy_transform_files(), key=_metric_sql_sort_key):
            try:
                legacy = parse_transform(path.read_text(), path=path)
            except Exception as e:
                logger.warning(f"Could not parse legacy transform {path.name}: {e}")
                continue
            if legacy.target in view_targets:
                continue
            specs.append(legacy)

        specs.sort(key=lambda s: (s.order, s.name))
        logger.debug(f"Transform schedule: {[(s.order, s.name) for s in specs]}")

        if not requested_metrics or 'all' in requested_metrics:
            kept = []
            for spec in specs:
                if self._spec_deprecated(spec):
                    logger.info("Skipping deprecated/on-hold transform: %s", spec.name)
                    continue
                kept.append(spec)
            return kept

        selected = [
            spec for spec in specs
            if any(self._spec_matches_request(spec, r) for r in requested_metrics)
        ]
        held = [spec for spec in selected if self._spec_on_hold(spec)]
        for spec in held:
            logger.info(
                "Skipping on-hold transform, including explicit request: %s",
                spec.name,
            )
        return [spec for spec in selected if not self._spec_on_hold(spec)]

    def _get_chunk_size_for_transform(self, sql_or_spec) -> Optional[int]:
        """Get chunk size (days) for a transform from its config chunk_size key."""
        if isinstance(sql_or_spec, TransformSpec):
            config = sql_or_spec.config
            label = sql_or_spec.view_name or sql_or_spec.name
        else:
            config = self._parse_transform_config(sql_or_spec)
            label = sql_or_spec.name
        if config and 'chunk_size' in config:
            chunk_size_str = str(config['chunk_size']).strip().lower()
            result = self.chunk_size_mappings.get(chunk_size_str)
            logger.debug(f"Chunk size from config for {label}: {chunk_size_str} -> {result}")
            return result
        return None

    def _determine_processing_chunks(self, start_date: str, end_date: str, chunk_size_days: int) -> List[Tuple[str, str]]:
        """Determine the processing chunks for a given date range and chunk size."""
        if chunk_size_days is None:
            # No chunking - process entire range
            return [(start_date, end_date)]

        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')

        chunks = []
        current_dt = start_dt

        while current_dt <= end_dt:
            chunk_end_dt = min(current_dt + timedelta(days=chunk_size_days - 1), end_dt)
            chunks.append((
                current_dt.strftime('%Y-%m-%d'),
                chunk_end_dt.strftime('%Y-%m-%d')
            ))
            current_dt = chunk_end_dt + timedelta(days=1)

        return chunks

    def _registration_failures_in_scope(
        self, reg_errors: List[tuple], requested_metrics: List[str]
    ) -> List[tuple]:
        """Failed view registrations that affect the requested schedule.

        A view missing from system.tables drops its transform from the
        catalog-built schedule entirely — `--metrics all` would leave the
        target stale while reporting success. Every unparseable file and any
        non-deprecated failure blocks `all`; explicit metrics only block on
        transforms they actually name (slug, target, or view name).
        Deprecated/on-hold transforms are skipped by the schedule anyway, so
        their registration failure does not block.
        """
        requested = requested_metrics or []
        run_all = not requested or 'all' in requested
        spec_by_view = {
            spec.view_name: spec for spec in discover_transform_specs() if spec.view_name
        }
        blocking: List[tuple] = []
        for name, err in reg_errors:
            spec = spec_by_view.get(name)
            if spec is not None and self._spec_deprecated(spec):
                continue
            if run_all:
                blocking.append((name, err))
                continue
            if spec is not None:
                if any(self._spec_matches_request(spec, r) for r in requested):
                    blocking.append((name, err))
            else:
                # Unparseable file — match on filename-derived names only.
                wanted = {Path(name).stem.replace('-', '_'), view_name_for(Path(name))}
                if any(r.replace('-', '_') in wanted for r in requested):
                    blocking.append((name, err))
        return blocking

    def _transform_label(self, sql_or_spec) -> str:
        if isinstance(sql_or_spec, TransformSpec):
            return sql_or_spec.view_name or sql_or_spec.name
        return sql_or_spec.name

    def _transform_run_sql(self, sql_or_spec, params: Dict[str, Any]) -> str:
        """Runnable SQL for a spec/chunk: small INSERT through the view, or legacy body."""
        if isinstance(sql_or_spec, TransformSpec):
            if sql_or_spec.shape == 'view':
                return chunk_insert_sql(sql_or_spec, params)
            return _rewrite_metric_sql_database_qualifier(sql_or_spec.body)
        return _rewrite_metric_sql_database_qualifier(Path(sql_or_spec).read_text())

    def _execute_transform_without_params(self, sql_or_spec) -> bool:
        """Execute a SQL transform that doesn't use parameters (like preprocessing files)."""
        label = self._transform_label(sql_or_spec)
        try:
            logger.debug(f"    Executing SQL: {label} (no parameters)")
            params = self._chunk_sql_params(sql_or_spec, '', '', force_refresh=True)
            sql_content = self._transform_run_sql(sql_or_spec, params)
            self.client.command(sql_content, settings=self._populate_query_settings(sql_or_spec))
            logger.info(f"    Successfully executed: {label}")
            return True
        except Exception as e:
            logger.error(f"    Failed to execute {label}: {e}")
            return False

    def _is_connection_reset_error(self, error: Exception) -> bool:
        """Check if the error is a connection reset error that can be recovered from."""
        error_str = str(error).lower()
        return ('connection reset' in error_str or
                'connection aborted' in error_str or
                'connectionreseterror' in error_str)

    def _is_server_down_error(self, error: Exception) -> bool:
        """ClickHouse process exited (crash/OOM/kill) — connection refused on localhost."""
        error_str = str(error).lower()
        return (
            'connection refused' in error_str
            or 'errno 61' in error_str
            or 'failed to establish a new connection' in error_str
        )

    def _is_memory_limit_error(self, error: Exception) -> bool:
        """Check if the error is a memory limit exceeded error."""
        error_str = str(error).lower()
        return ('memory limit exceeded' in error_str or
                'memory_limit_exceeded' in error_str or
                'code 241' in error_str or
                'overcommittracker' in error_str)

    def _release_memory(self) -> None:
        """Best-effort cache release between chunks (off by default on macOS — correlates with SIGILL)."""
        if self._is_darwin() and os.environ.get(
            'SIGMARAIL_POPULATE_ENABLE_MEMORY_COMMANDS', ''
        ).strip().lower() not in ('1', 'true', 'yes'):
            return
        if os.environ.get('SIGMARAIL_POPULATE_SKIP_MEMORY_COMMANDS', '').strip().lower() in ('1', 'true', 'yes'):
            return
        commands = [
            'SYSTEM DROP MARK CACHE',
            'SYSTEM DROP UNCOMPRESSED CACHE',
        ]
        if not self._is_darwin():
            commands.append('SYSTEM JEMALLOC PURGE')
        for command in commands:
            try:
                self.client.command(command)
            except Exception as e:
                logger.debug(f"    Memory cleanup skipped for {command}: {e}")
        logger.debug('    🧹 Memory cleanup pass finished')

    def _pause_between_chunks(self, merge_table: Optional[str] = None) -> None:
        """Let background merges drain before the next heavy INSERT SELECT."""
        sleep_sec = self._inter_chunk_sleep_seconds()
        if sleep_sec > 0:
            logger.info(f"    ⏳ Waiting {sleep_sec:g}s before next chunk...")
            time.sleep(sleep_sec)
        timeout = self._merge_wait_timeout_seconds()
        if timeout <= 0:
            return
        deadline = time.time() + timeout
        merge_filter = ""
        if merge_table:
            merge_filter = f" AND table = '{merge_table}'"
        while time.time() < deadline:
            try:
                result = self.client.query(
                    "SELECT count() FROM system.merges WHERE database = currentDatabase()"
                    + merge_filter
                )
                pending = int(result.result_rows[0][0]) if result.result_rows else 0
                if pending == 0:
                    return
                logger.info(f"    ⏳ {pending} merge(s) still running for {merge_table or 'database'}...")
                time.sleep(5)
            except Exception as e:
                logger.debug(f"    Merge wait stopped: {e}")
                return
        logger.warning(
            f"    ⚠️  Timed out after {timeout}s waiting for merges; continuing anyway"
        )

    def _get_smaller_chunk_size(self, current_chunk_size: int) -> Optional[int]:
        """Get the next smaller chunk size for error recovery."""
        # Extended hierarchy with much smaller chunks for extreme memory pressure
        chunk_hierarchy = [365, 180, 90, 30, 14, 7, 3, 1]  # 12m, 6m, 3m, 1m, 2w, 1w, 3d, 1d

        try:
            current_index = chunk_hierarchy.index(current_chunk_size)
            if current_index < len(chunk_hierarchy) - 1:
                return chunk_hierarchy[current_index + 1]
        except ValueError:
            # Current chunk size not in hierarchy, find the next smaller one
            for size in chunk_hierarchy:
                if size < current_chunk_size:
                    return size

        return None  # No smaller chunk size available (already at 1 day)

    def _execute_transform_for_chunk_with_recovery(
        self,
        sql_or_spec,
        chunk_start: str,
        chunk_end: str,
        original_chunk_size: int,
        merge_table: Optional[str] = None,
        force_refresh: bool = False,
    ) -> bool:
        """Execute a SQL transform for a specific chunk with error recovery.

        Strategy: On memory error, immediately reduce chunk size rather than retrying.
        """
        label = self._transform_label(sql_or_spec)
        params = self._chunk_sql_params(
            sql_or_spec, chunk_start, chunk_end, force_refresh=force_refresh
        )
        sql_content = self._transform_run_sql(sql_or_spec, params)
        # View shape renders params as view-invocation literals — no client-side
        # substitution. Legacy insert shape still uses server parameters.
        cmd_params = None if isinstance(sql_or_spec, TransformSpec) and sql_or_spec.shape == 'view' else params
        settings = self._populate_query_settings(sql_or_spec)

        try:
            if self._is_darwin():
                self._refresh_client()
            logger.debug(f"    Executing SQL: {label} for chunk {chunk_start} to {chunk_end}")
            self.client.command(sql_content, parameters=cmd_params, settings=settings)
            logger.info(f"    ✅ Successfully populated metric: {label} for chunk {chunk_start} to {chunk_end}.")
            self._pause_between_chunks(merge_table=merge_table)
            self._release_memory()
            return True

        except Exception as e:
            is_memory_error = self._is_memory_limit_error(e)
            is_connection_error = self._is_connection_reset_error(e)
            is_server_down = self._is_server_down_error(e)

            if is_server_down:
                logger.error(
                    f"    ❌ ClickHouse is not responding after chunk {chunk_start} to {chunk_end}. "
                    "The server process likely crashed (check ~/Library/Logs/DiagnosticReports/clickhouse-*.ips). "
                    "Restart with: Start ClickHouse with your local service manager."
                )
                return False

            if is_memory_error:
                # Memory error: immediately reduce chunk size instead of retrying
                logger.warning(f"    ⚠️  Memory limit exceeded for chunk {chunk_start} to {chunk_end}")

                # Aggressively clean up memory before retrying
                logger.info(f"    🧹 Forcing aggressive memory cleanup...")
                self._release_memory()
                time.sleep(3)  # Allow cleanup to complete

                smaller_chunk_size = self._get_smaller_chunk_size(original_chunk_size)

                if smaller_chunk_size:
                    # Can reduce further - do it immediately
                    logger.info(f"    🔄 Automatic chunk size reduction: {original_chunk_size} days → {smaller_chunk_size} days")
                    logger.info(f"    💡 Smaller chunks use less memory - retrying with {smaller_chunk_size}-day chunks")
                    return self._execute_transform_with_smaller_chunks(
                        sql_or_spec,
                        chunk_start,
                        chunk_end,
                        smaller_chunk_size,
                        force_refresh=force_refresh,
                    )
                else:
                    # Already at 1-day chunks - can't reduce further, must retry with delays
                    logger.warning(f"    ⚠️  Already at minimum chunk size (1 day). Will retry with delays...")
                    return self._retry_with_delays(sql_or_spec, chunk_start, chunk_end, sql_content, cmd_params, settings, e)

            elif is_connection_error:
                # Connection error: retry once after brief delay
                logger.warning(f"    ⚠️  Connection error for chunk {chunk_start} to {chunk_end}, retrying once...")
                time.sleep(5)
                try:
                    self.client.command(sql_content, parameters=cmd_params, settings=settings)
                    logger.info(f"    ✅ Successfully populated metric after retry: {label} for chunk {chunk_start} to {chunk_end}.")
                    return True
                except Exception as retry_error:
                    logger.error(f"    ❌ Connection failed after retry for chunk {chunk_start} to {chunk_end}: {retry_error}")
                    return False
            else:
                # Non-recoverable error
                logger.error(f"    ❌ Failed to execute {label} for chunk {chunk_start} to {chunk_end}: {e}")
                return False

    def _retry_with_delays(self, sql_or_spec, chunk_start: str, chunk_end: str, sql_content: str, params: dict, settings: dict, original_error: Exception) -> bool:
        """Retry with exponential backoff delays when at minimum chunk size (1 day).

        Only used when we can't reduce chunk size further and must wait for memory.
        """
        max_retries = 3
        base_delay = 30

        for attempt in range(max_retries):
            # Aggressively clean memory before each retry
            logger.info(f"    🧹 Aggressive memory cleanup before retry {attempt + 1}...")
            self._release_memory()

            delay = base_delay * (2 ** attempt)  # 30s, 60s, 120s
            logger.info(f"    Attempt {attempt + 2}/{max_retries + 1} after {delay}s delay to allow memory reclamation...")
            time.sleep(delay)

            try:
                self.client.command(sql_content, parameters=params, settings=settings)
                logger.info(f"    ✅ Successfully populated metric after retry: {self._transform_label(sql_or_spec)} for chunk {chunk_start} to {chunk_end}.")
                return True
            except Exception as e:
                if self._is_memory_limit_error(e):
                    if attempt < max_retries - 1:
                        logger.warning(f"    ⚠️  Still memory error on 1-day chunk (attempt {attempt + 2}/{max_retries + 1})")
                    else:
                        logger.error(f"    ❌ Memory limit exceeded after {max_retries + 1} attempts on 1-day chunk")
                        logger.error(f"    💡 Consider: 1) Increasing ClickHouse memory limits, 2) Optimizing the SQL query, or 3) Skipping this date")
                        logger.error(f"    Error details: {e}")
                        return False
                else:
                    logger.error(f"    ❌ Different error on retry: {e}")
                    return False

        return False

    def _execute_transform_with_smaller_chunks(
        self,
        sql_or_spec,
        chunk_start: str,
        chunk_end: str,
        smaller_chunk_size: int,
        force_refresh: bool = False,
    ) -> bool:
        """Execute a transform by breaking it into smaller chunks."""
        try:
            # Calculate smaller chunks
            smaller_chunks = self._determine_processing_chunks(chunk_start, chunk_end, smaller_chunk_size)
            logger.info(f"    Breaking chunk {chunk_start} to {chunk_end} into {len(smaller_chunks)} smaller chunks of {smaller_chunk_size} days")

            for small_chunk_start, small_chunk_end in smaller_chunks:
                logger.info(f"      Processing smaller chunk: {small_chunk_start} to {small_chunk_end}")
                if not self._execute_transform_for_chunk_with_recovery(
                    sql_or_spec,
                    small_chunk_start,
                    small_chunk_end,
                    smaller_chunk_size,
                    merge_table=self._transform_target_table(sql_or_spec),
                    force_refresh=force_refresh,
                ):
                    return False

            logger.info(f"    Successfully completed chunk {chunk_start} to {chunk_end} using smaller chunks")
            return True
        except Exception as e:
            logger.error(f"    Failed to execute {self._transform_label(sql_or_spec)} with smaller chunks for {chunk_start} to {chunk_end}: {e}")
            return False

    def _parse_transform_config(self, sql_or_spec) -> Optional[Dict]:
        """Transform config for a file or spec.

        View specs carry it in COMMENT JSON; legacy insert files carry it in the
        ``@transform-config`` comment block. Accepts a Path (unit tests patch
        this method) or a TransformSpec (returns its config verbatim).
        """
        if isinstance(sql_or_spec, TransformSpec):
            return sql_or_spec.config or None
        try:
            sql_content = sql_or_spec.read_text()
            try:
                parsed = parse_transform(sql_content, path=sql_or_spec)
                if parsed.config:
                    return parsed.config
            except ValueError:
                # Shared schema files may contain multiple managed views; callers
                # that need a specific transform should pass its TransformSpec.
                pass
            config = parse_header_config(sql_content)
            logger.debug(f"Parsed transform config from {sql_or_spec.name}: {config}")
            return config
        except Exception as e:
            logger.warning(f"Could not parse transform config from {sql_or_spec.name}: {e}")
            return None


    def _get_freshness_start_date_for_source(
        self,
        source_table: str,
        target_table: str,
        sf1_dimension: Optional[str] = None,
        source_timestamp_col: str = 'lastupdated',
        target_timestamp_col: str = 'lastupdated'
    ) -> Optional[str]:
        """Get freshness start date for a specific source/target pair.

        Finds the earliest date where source and target have different timestamp values.

        Args:
            source_table: Source table name (e.g., 'sep', 'sf1', 'daily_metrics')
            target_table: Target table name (e.g., 'daily_metrics', 'arq')
            sf1_dimension: Optional dimension for sf1 table (e.g., 'ARQ', 'MRQ')
            source_timestamp_col: Timestamp column name for source table (default: 'lastupdated', 'none' to skip)
            target_timestamp_col: Timestamp column name for target table (default: 'lastupdated', 'none' to skip)

        Returns:
            Earliest date that needs updating, or None if unavailable or up-to-date.
        """
        # Skip freshness check if timestamp columns are 'none'
        if str(target_timestamp_col).strip().lower() == 'none' or str(source_timestamp_col).strip().lower() == 'none':
            logger.debug(f"Skipping freshness check for {source_table} -> {target_table} (no timestamp columns)")
            return None

        # Static / dimension tables have no daily (date, lastupdated) grain
        non_temporal = frozenset({'tickers'})
        if source_table in non_temporal or target_table in non_temporal:
            logger.debug(f"Skipping freshness check for {source_table} -> {target_table} (non-temporal table)")
            return None

        try:
            # Limit freshness check to last 2 years to avoid expensive full table scans
            from datetime import date, timedelta
            two_years_ago = (date.today() - timedelta(days=730)).strftime('%Y-%m-%d')

            # Determine if table supports FINAL (ReplacingMergeTree) or not (MergeTree)
            # For now, try FINAL and catch errors
            final_clause = "FINAL"

            # Build source query based on table type
            if source_table in ['sep', 'sfp']:
                # Handle sep/sfp (can be checked individually or together)
                source_query = f"""
                    SELECT date, {source_timestamp_col} FROM {source_table} {final_clause}
                    WHERE date >= '{two_years_ago}'
                      AND {source_timestamp_col} >= toDateTime('1970-01-01 00:00:00')
                """
            elif source_table == 'sf1':
                # Handle sf1 with optional dimension
                dimension_filter = f"AND dimension = '{sf1_dimension}'" if sf1_dimension else ""
                source_query = f"""
                    SELECT calendardate as date, {source_timestamp_col} FROM sf1 {final_clause}
                    WHERE calendardate >= '{two_years_ago}'
                      AND {source_timestamp_col} >= toDateTime('1970-01-01 00:00:00')
                    {dimension_filter}
                """
            else:
                # Tables whose event date is not named `date` can provide an
                # explicit source_date_column in their transform metadata.
                source_date_col = 'date'
                source_query = f"""
                    SELECT {source_date_col} AS date, {source_timestamp_col} FROM {source_table} {final_clause}
                    WHERE {source_date_col} >= '{two_years_ago}'
                      AND {source_timestamp_col} >= toDateTime('1970-01-01 00:00:00')
                """

            # Build target query
            target_query = f"""
                SELECT date, max({target_timestamp_col}) as target_last_updated
                FROM {target_table} {final_clause}
                WHERE date >= '{two_years_ago}'
                  AND {target_timestamp_col} >= toDateTime('1970-01-01 00:00:00')
                GROUP BY date
            """

            # Simplified freshness check: find earliest date where source and target differ
            # This is more efficient than FULL OUTER JOIN - we just need the min date
            query = f"""
                WITH
                source_freshness AS (
                    SELECT
                        date,
                        max({source_timestamp_col}) as source_last_updated
                    FROM ({source_query}) s
                    GROUP BY date
                ),
                target_freshness AS (
                    {target_query}
                )
                SELECT toString(min(COALESCE(s.date, t.date)))
                FROM source_freshness s
                FULL OUTER JOIN target_freshness t ON s.date = t.date
                WHERE t.target_last_updated IS NULL  -- Missing date in target
                   OR s.source_last_updated > t.target_last_updated  -- Source is newer
            """

            result = self.client.query(query)
            if result.result_rows and result.result_rows[0][0]:
                date_str = result.result_rows[0][0]
                # ClickHouse returns '1970-01-01' (minimum Date) when min() is called on empty set
                # This means nothing needs updating, so return None
                if date_str == '1970-01-01':
                    return None
                return date_str
            return None
        except Exception as e:
            # If error is about FINAL not supported, retry without FINAL
            if 'ILLEGAL_FINAL' in str(e) or 'does not support FINAL' in str(e):
                try:
                    # Retry without FINAL
                    query_no_final = query.replace(' FINAL', '').replace(f' {final_clause}', '')
                    result = self.client.query(query_no_final)
                    if result.result_rows and result.result_rows[0][0]:
                        date_str = result.result_rows[0][0]
                        if date_str == '1970-01-01':
                            return None
                        return date_str
                    return None
                except Exception as e2:
                    logger.warning(f"Could not determine freshness start date for {source_table} -> {target_table} (even without FINAL): {e2}")
                    return None
            logger.warning(f"Could not determine freshness start date for {source_table} -> {target_table}: {e}")
            return None

    def _get_freshness_start_date_for_transform(self, sql_or_spec) -> Optional[str]:
        """Get freshness start date for a specific transform based on its config.

        Parses transform config and checks freshness for all source tables.
        Returns the earliest date across all sources that needs updating.
        """
        config = self._parse_transform_config(sql_or_spec)
        if not config:
            # No config found - fall back to default behavior
            return None

        sources = config.get('sources', [])
        target = config.get('target')
        sf1_dimension = config.get('sf1_dimension')
        source_timestamp_col = config.get('source_timestamp_column', 'lastupdated')
        target_timestamp_col = config.get('target_timestamp_column', 'lastupdated')

        if not sources or not target:
            logger.warning(f"Invalid transform config in {self._transform_label(sql_or_spec)}: missing sources or target")
            return None

        earliest_date = None

        # Handle sep/sfp together (they're often used together)
        if 'sep' in sources and 'sfp' in sources:
            if str(target_timestamp_col).strip().lower() == 'none':
                logger.debug(
                    f"Skipping sep/sfp freshness for {self._transform_label(sql_or_spec)} "
                    f"(target {target} has no timestamp column)"
                )
                sources = [s for s in sources if s not in ['sep', 'sfp']]
                if not sources:
                    return None
            else:
                # Check sep/sfp together with UNION ALL (matches SQL pattern)
                from datetime import date, timedelta
                two_years_ago = (date.today() - timedelta(days=730)).strftime('%Y-%m-%d')
                try:
                    query = f"""
                        WITH
                        source_date_freshness AS (
                            SELECT
                                date,
                                max({source_timestamp_col}) as source_last_updated
                            FROM (
                                SELECT date, {source_timestamp_col} FROM sep FINAL
                                WHERE date >= '{two_years_ago}'
                                  AND {source_timestamp_col} >= toDateTime('1970-01-01 00:00:00')
                                UNION ALL
                                SELECT date, {source_timestamp_col} FROM sfp FINAL
                                WHERE date >= '{two_years_ago}'
                                  AND {source_timestamp_col} >= toDateTime('1970-01-01 00:00:00')
                            ) s
                            GROUP BY date
                        ),
                        target_date_freshness AS (
                            SELECT
                                date,
                                max({target_timestamp_col}) as target_last_updated
                            FROM {target} FINAL
                            WHERE date >= '{two_years_ago}'
                              AND {target_timestamp_col} >= toDateTime('1970-01-01 00:00:00')
                            GROUP BY date
                        ),
                        dates_needing_update AS (
                            SELECT
                                COALESCE(s.date, t.date) as date
                            FROM source_date_freshness s
                            FULL OUTER JOIN target_date_freshness t ON s.date = t.date
                            WHERE t.target_last_updated IS NULL
                               OR s.source_last_updated > t.target_last_updated
                        )
                        SELECT toString(min(date))
                        FROM dates_needing_update
                    """
                    result = self.client.query(query)
                    if result.result_rows and result.result_rows[0][0]:
                        date_str = result.result_rows[0][0]
                        if date_str != '1970-01-01':
                            earliest_date = date_str
                except Exception as e:
                    logger.warning(f"Could not check sep/sfp freshness together: {e}")
                    earliest_date = None

                sources = [s for s in sources if s not in ['sep', 'sfp']]
                if not sources:
                    return earliest_date

        # Check remaining sources
        for source in sources:
            # For multi-source, use the same timestamp column for all sources
            # (most sources use 'lastupdated', but we allow override per source if needed)
            source_date = self._get_freshness_start_date_for_source(
                source, target,
                sf1_dimension if source == 'sf1' else None,
                source_timestamp_col,
                target_timestamp_col
            )
            if source_date and source_date != '1970-01-01':
                if earliest_date:
                    earliest_date = min(earliest_date, source_date)
                else:
                    earliest_date = source_date

        # Filter out 1970-01-01 (means nothing needs updating)
        if earliest_date == '1970-01-01':
            return None

        return earliest_date

    def _get_sep_incremental_start_date(self) -> Optional[str]:
        """Return earliest date where sep/sfp is out-of-sync with daily_metrics, or None if unavailable.

        This finds the earliest date that needs updating by comparing source freshness (sep/sfp)
        against target freshness (daily_metrics) per date.

        DEPRECATED: Use _get_freshness_start_date_for_transform() for transform-specific checks.
        Kept for backwards compatibility.
        """
        try:
            query = """
            WITH
            source_date_freshness AS (
                SELECT
                    date,
                    max(lastupdated) as source_last_updated
                FROM (
                    SELECT date, lastupdated FROM sep FINAL
                    WHERE lastupdated >= toDateTime('1970-01-01 00:00:00')
                    UNION ALL
                    SELECT date, lastupdated FROM sfp FINAL
                    WHERE lastupdated >= toDateTime('1970-01-01 00:00:00')
                ) s
                GROUP BY date
            ),
            target_date_freshness AS (
                SELECT
                    date,
                    max(lastupdated) as target_last_updated
                FROM daily_metrics FINAL
                WHERE lastupdated >= toDateTime('1970-01-01 00:00:00')
                GROUP BY date
            ),
            dates_needing_update AS (
                SELECT
                    COALESCE(s.date, t.date) as date
                FROM source_date_freshness s
                FULL OUTER JOIN target_date_freshness t ON s.date = t.date
                WHERE t.target_last_updated IS NULL  -- Missing date
                   OR s.source_last_updated > t.target_last_updated  -- Source is newer
            )
            SELECT toString(min(date))
            FROM dates_needing_update
            """
            result = self.client.query(query)
            if result.result_rows and result.result_rows[0][0]:
                date_str = result.result_rows[0][0]
                # ClickHouse returns '1970-01-01' (minimum Date) when min() is called on empty set
                # This means nothing needs updating, so return None
                if date_str == '1970-01-01':
                    return None
                return date_str
            return None
        except Exception as e:
            logger.warning(f"Could not determine incremental start date from freshness check: {e}")
            return None

    def _execute_transform_for_chunk(self, sql_or_spec, chunk_start: str, chunk_end: str, overall_start_date: str = None, overall_end_date: str = None) -> bool:
        """Execute a SQL transform for a specific chunk."""
        label = self._transform_label(sql_or_spec)
        try:
            logger.debug(f"    Executing SQL: {label} for chunk {chunk_start} to {chunk_end}")

            params = {
                'chunk_start_date': chunk_start,
                'chunk_end_date': chunk_end
            }
            # Add overall date range for freshness checks (if provided)
            if overall_start_date and overall_end_date:
                params['overall_start_date'] = overall_start_date
                params['overall_end_date'] = overall_end_date

            sql_content = self._transform_run_sql(sql_or_spec, params)
            cmd_params = None if isinstance(sql_or_spec, TransformSpec) and sql_or_spec.shape == 'view' else params
            settings = self._populate_query_settings(sql_or_spec)
            settings['max_execution_time'] = 1800
            self.client.command(sql_content, parameters=cmd_params, settings=settings)

            logger.info(f"    Successfully populated metric: {label} for chunk {chunk_start} to {chunk_end}.")
            return True
        except Exception as e:
            logger.error(f"    Failed to execute {label} for chunk {chunk_start} to {chunk_end}: {e}")
            return False

    def _fallback_start_date_when_freshness_unknown(self) -> str:
        """When a transform has no freshness boundary, avoid scanning from 1999."""
        from datetime import date, timedelta
        return (date.today() - timedelta(days=730)).strftime('%Y-%m-%d')

    def _resolve_transform_start_date(
        self,
        sql_or_spec,
        explicit_start: Optional[str],
        force_refresh: bool,
    ) -> str:
        if explicit_start:
            return explicit_start
        if force_refresh:
            return '1999-01-01'
        transform_start = self._get_freshness_start_date_for_transform(sql_or_spec)
        if transform_start:
            return transform_start
        return self._fallback_start_date_when_freshness_unknown()

    def populate_metrics(
        self,
        start_date: str = None,
        end_date: str = None,
        metrics_to_process: List[str] = None,
        force_refresh: bool = False,
        auto_recalc_events: bool = False,
    ) -> bool:
        """Populate metrics tables with the specified parameters."""
        try:
            from datetime import date
            if not end_date:
                end_date = date.today().strftime('%Y-%m-%d')

            # Schema loading installs xform_* definitions. The live ClickHouse
            # catalog, including each view's COMMENT metadata, is the populate
            # schedule; do not rebuild that schedule from source files here.
            sql_files = self._get_transform_specs(metrics_to_process)
            explicit_start = start_date
            explicit_start, force_refresh = self.apply_auto_recalc_events(
                explicit_start,
                force_refresh,
                enabled=auto_recalc_events,
            )

            if force_refresh and not explicit_start:
                logger.info("Force refresh enabled with no explicit start date; defaulting to 1999-01-01")
            elif explicit_start:
                logger.info(f"Using explicitly provided start_date {explicit_start} for all transforms")
            else:
                logger.info("Using per-transform freshness start dates (not a single global minimum)")

            print(f"📅 End date: {end_date}", flush=True)
            if explicit_start:
                print(f"📅 Start date (all transforms): {explicit_start}", flush=True)
            if force_refresh:
                print("🔄 Force refresh: enabled", flush=True)
            if not sql_files:
                logger.warning("No SQL files found to process")
                print("⚠️ No SQL files found to process", flush=True)
                return True

            logger.info(f"Found {len(sql_files)} transforms to process")
            print(f"📁 Found {len(sql_files)} transforms to process", flush=True)

            # Process each transform in schedule order
            for spec in sql_files:
                label = self._transform_label(spec)
                file_start = self._resolve_transform_start_date(spec, explicit_start, force_refresh)
                logger.info(f"Processing transform: {label} ({file_start} to {end_date})")
                print(f"🔄 Processing: {label} ({file_start} → {end_date})", flush=True)

                chunk_size_days = self._get_chunk_size_for_transform(spec)

                if chunk_size_days is None:
                    # No chunking - execute once for entire timeframe
                    logger.info(f"  Processing {label} for complete timeframe")
                    if not self._execute_transform_without_params(spec):
                        raise Exception(f"Failed to execute {label}")
                    print(f"✅ Completed: {label}", flush=True)
                else:
                    # Determine chunks and process each one
                    chunks = self._determine_processing_chunks(file_start, end_date, chunk_size_days)
                    logger.info(f"  Processing {label} in {len(chunks)} chunks of {chunk_size_days} days")
                    merge_table = self._transform_target_table(spec)

                    for idx, (chunk_start, chunk_end) in enumerate(chunks):
                        if (
                            not force_refresh
                            and merge_table
                            and self._chunk_dates_already_populated(
                                merge_table, chunk_start, chunk_end
                            )
                        ):
                            logger.info(
                                f"    ⏭️  Skipping chunk {chunk_start} to {chunk_end} "
                                f"({merge_table} already has trading days in range)"
                            )
                            continue
                        logger.info(f"    Processing chunk: {chunk_start} to {chunk_end}")
                        if not self._execute_transform_for_chunk_with_recovery(
                            spec,
                            chunk_start,
                            chunk_end,
                            chunk_size_days,
                            merge_table=merge_table,
                            force_refresh=force_refresh,
                        ):
                            raise Exception(f"Failed to execute {label} for chunk {chunk_start} to {chunk_end}")

                    print(f"✅ Completed: {label}", flush=True)

            self._warn_on_empty_targets(sql_files)

            logger.info("Metrics population process finished.")
            return True

        except Exception as e:
            logger.error(f"Error during metrics population: {e}")
            raise

    def _warn_on_empty_targets(self, sql_files: List[Path]) -> None:
        """Warn when a processed transform's target table has zero rows.

        A transform can log "Successfully populated" while writing nothing — the 2026-09-26
        fixture incident (37 derived tables empty because `tickers.table` held SEP/SFP) is the
        canonical case. This is a cheap post-hoc guard, not a per-chunk check: it only fires when
        a table is entirely empty after a full run.
        """
        seen: set = set()
        for sql_file in sql_files:
            target = self._transform_target_table(sql_file)
            if not target or target in seen:
                continue
            seen.add(target)
            try:
                n = int(self.client.query(f"SELECT count() FROM {target} FINAL").result_rows[0][0])
            except Exception:
                continue  # table may not exist (no-param transforms), or transient — not this guard's job
            if n == 0:
                logger.warning(f"Target table {target} has 0 rows after population — check the transform inputs.")
                print(f"⚠️  WARNING: {target} has 0 rows after population", flush=True)

    def rebuild_tables(self, tables_to_rebuild: List[str]) -> bool:
        """Rebuild specified tables by dropping and recreating them."""
        try:
            if not tables_to_rebuild:
                logger.warning("No tables specified for rebuild")
                return True

            # Safety check against base tables
            base_tables_to_rebuild = set(tables_to_rebuild) & self.BASE_DATA_TABLES
            if base_tables_to_rebuild:
                logger.error(f"Cannot rebuild base data tables: {base_tables_to_rebuild}")
                return False

            logger.info(f"Rebuilding tables: {tables_to_rebuild}")

            for table in tables_to_rebuild:
                logger.info(f"Dropping table: {table}")
                self.client.command(f"DROP TABLE IF EXISTS {table}")

            logger.info("Tables dropped successfully")
            return True

        except Exception as e:
            logger.error(f"Error during table rebuild: {e}")
            return False

def main():
    """Main function for the populate command."""
    parser = argparse.ArgumentParser(
        description='Populate ClickHouse metrics tables (daily_metrics, mrt, etc.)',
        parents=[create_shared_parser()]
    )
    parser.add_argument('--start-date', default=None, help='Start date for metrics calculation (YYYY-MM-DD, default: auto-detected based on updates)')
    parser.add_argument('--end-date', default=None, help='End date for metrics calculation (YYYY-MM-DD, default: auto-detected based on updates)')
    parser.add_argument('--metrics', nargs='*', help='Metric tables to process (space- or comma-separated, e.g. daily-metrics or daily-metrics,weekly-metrics). If flag is present without arguments, processes all metrics.')
    parser.add_argument('--rebuild', action='store_true', help='Drop the tables specified in --metrics before processing. If --metrics is not provided, all derived tables are dropped, and freshness checks are bypassed for the rebuild.')
    parser.add_argument('--force-refresh', action='store_true', help='(Optional) Ignore upstream freshness checks and process exactly the requested date range without requiring --rebuild.')
    parser.add_argument('--register-views', action='store_true', help='Register all xform_* transform views and exit (no population).')
    parser.add_argument(
        '--auto-recalc-events',
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            'When recent split/spinoff/ADR events exist in recalculation_events_view, '
            'auto-widen start date (capped) and enable full-universe force-refresh. '
            'Default: off. Use only for an intentional full-universe rematerialize.'
        ),
    )
    args = parser.parse_args()

    # Handle shared args
    process_shared_args(args)

    try:
        def _normalize_metric_name(name: str) -> str:
            return name.replace('-', '_') if name else name

        # Create data populator instance
        populator = DataPopulator()
        args.metrics = _split_metrics_args(args.metrics)
        if args.metrics is not None:
            args.metrics = [_normalize_metric_name(name) for name in args.metrics]
            allowed = set(populator._get_all_derived_tables())
            unknown = {name for name in args.metrics if name != 'all' and name not in allowed}
            if unknown:
                logger.error("Unknown SigmaRail core transform target(s): %s", sorted(unknown))
                print(
                    "❌ Unsupported transform target(s): " + ", ".join(sorted(unknown)),
                    flush=True,
                )
                return 2

        # Register transform views only — schema inspection / ad-hoc debugging.
        if args.register_views:
            registered, reg_errors = register_all_transform_views(populator.client)
            print(f"Registered {len(registered)} transform view(s)", flush=True)
            for name, err in reg_errors:
                print(f"  ⚠️ {name}: {err}", flush=True)
            return 1 if reg_errors else 0

        # Exit if --metrics is not specified at all and no other operations
        if args.metrics is None and not args.rebuild:
            logger.info("No --metrics specified, skipping metrics population.")
            return 0

        skip_schema = os.getenv("SIGMARAIL_SKIP_SCHEMA") == "1"

        # Load schema files only when needed (metrics processing or rebuild)
        if args.metrics is not None or args.rebuild:
            if skip_schema:
                logger.info("Skipping schema load due to SIGMARAIL_SKIP_SCHEMA=1")
            else:
                if not load_schema():
                    logger.error("Failed to load schema files")
                    print("❌ Schema loading failed", flush=True)
                    return 1
                logger.info("Schema files loaded successfully")
                print("✅ Schema loaded successfully", flush=True)

        # Handle rebuilding tables if requested
        if args.rebuild:
            tables_to_drop = []
            # If --metrics is provided (even if empty), it dictates what to drop
            if args.metrics is not None:
                if args.metrics and 'all' not in args.metrics:
                    tables_to_drop = [_normalize_metric_name(metric) for metric in args.metrics]
                else:  # --metrics (with no args)
                    logger.info("--metrics flag present with no tables; all derived tables will be dropped.")
                    tables_to_drop = populator._get_all_derived_tables()
            else: # --rebuild run by itself
                 logger.info("Only --rebuild specified; all derived tables will be dropped.")
                 tables_to_drop = populator._get_all_derived_tables()

            if not tables_to_drop:
                logger.warning("Rebuild requested, but no tables identified to drop.")
            else:
                logger.info(f"Rebuild requested. The following tables will be dropped: {tables_to_drop}")
                # Safety check against base tables
                base_tables_to_drop = set(tables_to_drop) & populator.BASE_DATA_TABLES
                if base_tables_to_drop:
                    logger.error(f"Cannot rebuild base data tables: {base_tables_to_drop}")
                    return 1

                # Drop the tables
                for table in tables_to_drop:
                    logger.info(f"Dropping table: {table}")
                    populator.client.command(f"DROP TABLE IF EXISTS {table}")

                logger.info("Tables dropped successfully")

                # Reload schema files to recreate the tables
                if skip_schema:
                    logger.info("Skipping schema reload after rebuild due to SIGMARAIL_SKIP_SCHEMA=1")
                else:
                    if not load_schema():
                        logger.error("Failed to reload schema files after rebuild")
                        return 1
                    logger.info("Schema files reloaded successfully after rebuild")

        # Determine which metrics to run. This runs if --metrics was specified at all.
        logger.debug(f"args.metrics = {args.metrics}")
        if args.metrics is not None:
            metrics_to_run = [_normalize_metric_name(metric) for metric in args.metrics] if args.metrics else ['all']
            logger.info(f"Running metric processing for: {metrics_to_run}")
            print(f"📊 Starting metrics population: {metrics_to_run}", flush=True)

            metrics_processed_range = populator.populate_metrics(
                start_date=args.start_date,
                end_date=args.end_date,
                metrics_to_process=metrics_to_run,
                force_refresh=(args.force_refresh or args.rebuild),
                auto_recalc_events=bool(args.auto_recalc_events),
            )

            if not metrics_processed_range:
                logger.error("Metrics population failed")
                print("❌ Metrics population failed", flush=True)
                return 1

            logger.info(f"Metrics population process reported completion for range {args.start_date} to {args.end_date}.")
            print("✅ Metrics population completed successfully", flush=True)

        logger.info("SigmaRail populate process finished.")
        print("✅ SigmaRail populate process finished successfully", flush=True)
        return 0

    except Exception as e:
        logger.error(f"An unexpected error occurred during the populate process: {e}")
        print(f"❌ SigmaRail populate process failed: {e}", flush=True)
        return 1

if __name__ == "__main__":
    exit(main())
