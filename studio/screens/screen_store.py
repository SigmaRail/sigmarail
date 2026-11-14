"""ScreenRepository — saved universe_query_v1 screens (SQLite or ClickHouse).

Contract: C-SCREEN-PERSISTENCE (Phase A1).

Env / Django setting:
  SCREEN_STORE=sqlite|ch  (default: sqlite for tests/dev; set ch for production)
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from screens.lineage import universe_spec_hash


class ScreenNotFoundError(LookupError):
    """Raised when a screen_id does not exist (or is soft-deleted)."""


class ScreenNameConflictError(ValueError):
    """Raised when creating/renaming to a name that already exists."""


@dataclass(frozen=True)
class ScreenRecord:
    """Normalized screen DTO (id is always a string for API uniformity)."""

    id: str
    name: str
    spec: dict[str, Any]
    is_system: bool = False
    category: str = "Custom"
    description: str = ""
    created_at: str | None = None
    updated_at: str | None = None
    source_template_id: str = ""
    spec_content_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "spec": self.spec,
            "is_system": self.is_system,
            "category": self.category,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        # Preserve numeric id for SQLite clients that still parse as number when possible.
        if str(self.id).isdigit():
            out["id"] = int(self.id)
        if self.source_template_id:
            out["source_template_id"] = self.source_template_id
        if self.spec_content_hash:
            out["spec_content_hash"] = self.spec_content_hash
        return out


class ScreenRepository(Protocol):
    def list(self) -> list[ScreenRecord]: ...

    def get(self, screen_id: str) -> ScreenRecord: ...

    def create(
        self,
        *,
        name: str,
        spec: dict[str, Any],
        source_template_id: str = "",
    ) -> ScreenRecord: ...

    def update(
        self,
        screen_id: str,
        *,
        name: str | None = None,
        spec: dict[str, Any] | None = None,
        source_template_id: str | None = None,
    ) -> ScreenRecord: ...

    def delete(self, screen_id: str) -> None: ...


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _load_system_screens() -> list[ScreenRecord]:
    from screens.ir_preview import load_template
    from screens.adapter import preset_to_universe_spec

    system_definitions = [
        ("fair_value_discount_compounders", "Fair Value Discount Compounders", "Intrinsic Fair Value Discount • EPS CAGR ≥ 15% • 2Y Expected CAGR ≥ 20% • RS ≥ 60", "template"),
        ("garp_minervini_forecast_template", "GARP Minervini Forecast", "GARP + Minervini Trend • 2Y CAGR ≥ 15% • PEG ≤ 2.5 • RS ≥ 70", "template"),
        ("minervini_trend_template_5m", "Minervini Trend Template (5-Month / Strict)", "Chartmill Minervini Trend • 200 SMA rising ≥ 5 months • RS ≥ 70 • Price within 25% 52W high", "template"),
        ("minervini_trend_template_1m", "Minervini Trend Template (1-Month / Early)", "Chartmill Minervini Trend • 200 SMA rising ≥ 1 month • RS ≥ 60 • Stage 2 turnaround", "template"),
        ("minervini_momentum_leaders", "Minervini Momentum Leaders (RS 85+)", "Chartmill Trading Idea • Trend Template • Elite RS Rating ≥ 85 • Within 15% 52W high", "template"),
        ("minervini_fundamental_growth", "Minervini Fundamental Growth Champions", "Chartmill Trading Idea • Trend Template • Growth Rate ≥ 20% • RS ≥ 75", "template"),
        ("minervini_vcp_breakout", "Minervini VCP & Stage 2 Consolidation", "Chartmill Trading Idea • Volatility Contraction Pattern • Stage 2 Advancing • Setup Quality ≥ 70", "template"),
        ("minervini_high_tight_flag", "Minervini High Tight Flag / Power Play", "Chartmill Trading Idea • Run-up ≥ 70% off 52W low • Consolidating within 15% 52W high • RS ≥ 80", "template"),
        ("canslim_template", "CANSLIM Leader Filter", "CANSLIM Filter • High Growth & Institutional Accumulation", "template"),
        ("breakout_quality_setups", "Chartmill Breakout Setups", "Chartmill Breakout • Technical Rating ≥ 70 • Setup Quality ≥ 70 • Volume ≥ 300k", "template"),
        ("strong_growth_technical_setups", "Strong Growth Technical Setups", "Chartmill Growth + Tech • Growth Rate ≥ 15% • Setup Quality ≥ 70 • RS ≥ 70", "template"),
        ("kullamagi_breakout_momentum", "Kullamägi Momentum Breakout", "Kristjan Kullamägi Momentum • 1M Return ≥ 20% • Near 52W High • RS ≥ 80", "template"),
        ("weinstein_stage_2_breakout", "Weinstein Stage 2 Advancing", "Stan Weinstein Stage Analysis • Stage 2 Breakout • 30D Rising 200 SMA • RS ≥ 70", "template"),
        ("unusual_volume_breakouts", "Unusual Volume Breakouts", "Volume Surge ≥ 2x 50D Average • Within 15% 52W High • RS ≥ 65", "template"),
        ("swing_pullback_sma20", "Swing Trading - Pullback to 20-Day SMA", "Chartmill Swing Setup • Pullback to 20D SMA in Confirmed Uptrend • RS ≥ 70", "template"),
        ("near_52w_high_breakout", "Near 52-Week High Breakouts", "Chartmill Breakout • Within 5% of 52W High • RS ≥ 80 • Volume ≥ 250k", "template"),
        ("bull_flag_breakouts", "Bull Flag Continuation Breakouts", "Chartmill Bull Flag • Tight Flag Consolidation • RS ≥ 70 • Setup Quality ≥ 65", "template"),
        ("affordable_growth_compounders", "Affordable Growth Compounders (GARP)", "Chartmill Growth & Valuation • Growth Rate ≥ 15% • Forward PEG ≤ 2.2 • RS ≥ 65", "template"),
        ("volatility_squeeze_breakout", "Volatility Squeeze Breakout", "Chartmill Squeeze Setup • Bollinger Inside Keltner / Low ATR • RS ≥ 65", "template"),
        ("pocket_pivot_high_rs", "Pocket Pivot Signature", "Pocket Pivot Signature near 10D SMA in High RS Market Leaders • RS ≥ 75", "template"),
        ("high_trend_intensity_volume", "High Trend Intensity on Volume", "Chartmill Trend Intensity • 3M Return ≥ 25% • Rising 200 SMA • RS ≥ 75", "template"),
        ("piotroski_undervalued_compounders", "Piotroski Undervalued Compounders", "Piotroski Quality • 2Y CAGR ≥ 15% • Forward PEG ≤ 1.8 • Growth ≥ 10%", "template"),
        ("dividend_growth_compounders", "Quality Dividend Growth", "Chartmill Dividend Compounders • Forward EPS Growth • 2Y CAGR ≥ 10%", "template"),
        ("leaders", "Market Leaders", "High RS rating, top industry rank, strong technical momentum", "preset"),
        ("vcp_tight", "VCP Volatility Contraction", "Tight volatility consolidation near multi-week highs", "preset"),
        ("high_rs", "High Relative Strength", "Relative strength percentile ≥ 80 vs broad market", "preset"),
        ("inst_accumulating", "Institutional Accumulation", "Heavy institutional buying volume and positive accumulation/distribution", "preset"),
    ]

    out: list[ScreenRecord] = []
    for sid, label, desc, kind in system_definitions:
        try:
            if kind == "template":
                tpl = load_template(sid)
                spec = tpl.get("spec", tpl)
            else:
                spec = preset_to_universe_spec(sid)
            out.append(
                ScreenRecord(
                    id=sid,
                    name=label,
                    spec=spec,
                    is_system=True,
                    category="System",
                    description=desc,
                    source_template_id=sid,
                    spec_content_hash=universe_spec_hash(spec),
                )
            )
        except Exception:
            continue
    return out


class SqliteScreenRepository:
    """Django ORM SavedScreen backend (default / tests)."""

    def list(self) -> list[ScreenRecord]:
        from api.models import SavedScreen

        system_records = _load_system_screens()
        custom_records = [self._to_record(s) for s in SavedScreen.objects.all().order_by("-updated_at", "-created_at")]
        return system_records + custom_records

    def get(self, screen_id: str) -> ScreenRecord:
        for sys_rec in _load_system_screens():
            if sys_rec.id == screen_id:
                return sys_rec

        from api.models import SavedScreen

        try:
            pk = int(screen_id)
        except (TypeError, ValueError) as exc:
            raise ScreenNotFoundError(f"saved screen not found: {screen_id}") from exc
        try:
            return self._to_record(SavedScreen.objects.get(pk=pk))
        except SavedScreen.DoesNotExist as exc:
            raise ScreenNotFoundError(f"saved screen not found: {screen_id}") from exc

    def create(
        self,
        *,
        name: str,
        spec: dict[str, Any],
        source_template_id: str = "",
    ) -> ScreenRecord:
        from api.models import SavedScreen

        name = (name or "").strip()
        if not name:
            raise ValueError("name is required")
        if not isinstance(spec, dict):
            raise ValueError("spec must be an object")
        if SavedScreen.objects.filter(name=name).exists():
            raise ScreenNameConflictError(f"screen named {name!r} already exists")
        screen = SavedScreen.objects.create(name=name, spec=spec)
        return self._to_record(screen, source_template_id=source_template_id)

    def update(
        self,
        screen_id: str,
        *,
        name: str | None = None,
        spec: dict[str, Any] | None = None,
        source_template_id: str | None = None,
    ) -> ScreenRecord:
        from api.models import SavedScreen

        try:
            pk = int(screen_id)
            screen = SavedScreen.objects.get(pk=pk)
        except (TypeError, ValueError, SavedScreen.DoesNotExist) as exc:
            raise ScreenNotFoundError(f"saved screen not found: {screen_id}") from exc
        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("name must be non-empty")
            if SavedScreen.objects.filter(name=name).exclude(pk=pk).exists():
                raise ScreenNameConflictError(f"screen named {name!r} already exists")
            screen.name = name
        if spec is not None:
            if not isinstance(spec, dict):
                raise ValueError("spec must be an object")
            screen.spec = spec
        screen.save()
        return self._to_record(
            screen,
            source_template_id=source_template_id or "",
        )

    def delete(self, screen_id: str) -> None:
        for sys_rec in _load_system_screens():
            if sys_rec.id == str(screen_id):
                raise ValueError("cannot delete built-in system screen")

        from api.models import SavedScreen

        try:
            pk = int(screen_id)
            screen = SavedScreen.objects.get(pk=pk)
        except (TypeError, ValueError, SavedScreen.DoesNotExist) as exc:
            raise ScreenNotFoundError(f"saved screen not found: {screen_id}") from exc
        screen.delete()

    def _to_record(
        self,
        screen: Any,
        *,
        source_template_id: str = "",
    ) -> ScreenRecord:
        spec = screen.spec if isinstance(screen.spec, dict) else {}
        return ScreenRecord(
            id=str(screen.pk),
            name=screen.name,
            spec=spec,
            created_at=_iso(screen.created_at),
            updated_at=_iso(screen.updated_at),
            source_template_id=source_template_id,
            spec_content_hash=universe_spec_hash(spec) if spec else "",
        )


class ClickHouseScreenRepository:
    """ClickHouse strategy_screens backend (ReplacingMergeTree + soft-delete)."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    def _ch(self) -> Any:
        if self._client is not None:
            return self._client
        from screens.ch import get_ch_client

        return get_ch_client()

    def list(self) -> list[ScreenRecord]:
        client = self._ch()
        try:
            rows = client.query(
                "SELECT screen_id, name, spec_json, spec_content_hash,"
                "       source_template_id, created_at"
                " FROM strategy_screens FINAL"
                " WHERE deleted = 0"
                " ORDER BY name ASC"
                " LIMIT 500"
            )
        finally:
            if self._client is None:
                client.close()
        return [self._row_to_record(dict(zip(rows.column_names, r))) for r in rows.result_rows]

    def get(self, screen_id: str) -> ScreenRecord:
        screen_id = (screen_id or "").strip()
        if not screen_id:
            raise ScreenNotFoundError("saved screen not found: (empty id)")
        client = self._ch()
        try:
            rows = client.query(
                "SELECT screen_id, name, spec_json, spec_content_hash,"
                "       source_template_id, created_at"
                " FROM strategy_screens FINAL"
                " WHERE screen_id = %(sid)s AND deleted = 0"
                " LIMIT 1",
                parameters={"sid": screen_id},
            )
        finally:
            if self._client is None:
                client.close()
        if not rows.result_rows:
            raise ScreenNotFoundError(f"saved screen not found: {screen_id}")
        return self._row_to_record(dict(zip(rows.column_names, rows.result_rows[0])))

    def create(
        self,
        *,
        name: str,
        spec: dict[str, Any],
        source_template_id: str = "",
    ) -> ScreenRecord:
        name = (name or "").strip()
        if not name:
            raise ValueError("name is required")
        if not isinstance(spec, dict):
            raise ValueError("spec must be an object")
        if self._name_taken(name):
            raise ScreenNameConflictError(f"screen named {name!r} already exists")
        screen_id = str(uuid.uuid4())
        content_hash = universe_spec_hash(spec)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        client = self._ch()
        try:
            client.insert(
                "strategy_screens",
                [
                    [
                        screen_id,
                        name,
                        json.dumps(spec, separators=(",", ":"), sort_keys=True),
                        content_hash,
                        (source_template_id or "").strip(),
                        0,
                        now,
                    ]
                ],
                column_names=[
                    "screen_id",
                    "name",
                    "spec_json",
                    "spec_content_hash",
                    "source_template_id",
                    "deleted",
                    "created_at",
                ],
            )
        finally:
            if self._client is None:
                client.close()
        return ScreenRecord(
            id=screen_id,
            name=name,
            spec=spec,
            created_at=_iso(now.replace(tzinfo=timezone.utc)),
            updated_at=_iso(now.replace(tzinfo=timezone.utc)),
            source_template_id=(source_template_id or "").strip(),
            spec_content_hash=content_hash,
        )

    def update(
        self,
        screen_id: str,
        *,
        name: str | None = None,
        spec: dict[str, Any] | None = None,
        source_template_id: str | None = None,
    ) -> ScreenRecord:
        current = self.get(screen_id)
        new_name = current.name if name is None else name.strip()
        if not new_name:
            raise ValueError("name must be non-empty")
        if name is not None and new_name != current.name and self._name_taken(new_name, exclude_id=screen_id):
            raise ScreenNameConflictError(f"screen named {new_name!r} already exists")
        new_spec = current.spec if spec is None else spec
        if not isinstance(new_spec, dict):
            raise ValueError("spec must be an object")
        new_tpl = (
            current.source_template_id
            if source_template_id is None
            else source_template_id.strip()
        )
        content_hash = universe_spec_hash(new_spec)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        client = self._ch()
        try:
            client.insert(
                "strategy_screens",
                [
                    [
                        screen_id,
                        new_name,
                        json.dumps(new_spec, separators=(",", ":"), sort_keys=True),
                        content_hash,
                        new_tpl,
                        0,
                        now,
                    ]
                ],
                column_names=[
                    "screen_id",
                    "name",
                    "spec_json",
                    "spec_content_hash",
                    "source_template_id",
                    "deleted",
                    "created_at",
                ],
            )
        finally:
            if self._client is None:
                client.close()
        return ScreenRecord(
            id=screen_id,
            name=new_name,
            spec=new_spec,
            created_at=current.created_at,
            updated_at=_iso(now.replace(tzinfo=timezone.utc)),
            source_template_id=new_tpl,
            spec_content_hash=content_hash,
        )

    def delete(self, screen_id: str) -> None:
        current = self.get(screen_id)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        client = self._ch()
        try:
            client.insert(
                "strategy_screens",
                [
                    [
                        screen_id,
                        current.name,
                        json.dumps(current.spec, separators=(",", ":"), sort_keys=True),
                        current.spec_content_hash or universe_spec_hash(current.spec),
                        current.source_template_id,
                        1,
                        now,
                    ]
                ],
                column_names=[
                    "screen_id",
                    "name",
                    "spec_json",
                    "spec_content_hash",
                    "source_template_id",
                    "deleted",
                    "created_at",
                ],
            )
        finally:
            if self._client is None:
                client.close()

    def _name_taken(self, name: str, *, exclude_id: str | None = None) -> bool:
        client = self._ch()
        try:
            rows = client.query(
                "SELECT screen_id FROM strategy_screens FINAL"
                " WHERE deleted = 0 AND name = %(name)s"
                " LIMIT 5",
                parameters={"name": name},
            )
        finally:
            if self._client is None:
                client.close()
        for row in rows.result_rows:
            sid = str(row[0])
            if exclude_id is None or sid != exclude_id:
                return True
        return False

    def _row_to_record(self, row: dict[str, Any]) -> ScreenRecord:
        raw = row.get("spec_json") or "{}"
        try:
            spec = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            spec = {}
        if not isinstance(spec, dict):
            spec = {}
        created = row.get("created_at")
        created_iso = _iso(created) if isinstance(created, datetime) else (
            str(created) if created else None
        )
        return ScreenRecord(
            id=str(row["screen_id"]),
            name=str(row.get("name") or ""),
            spec=spec,
            created_at=created_iso,
            updated_at=created_iso,
            source_template_id=str(row.get("source_template_id") or ""),
            spec_content_hash=str(row.get("spec_content_hash") or ""),
        )


def screen_store_backend() -> str:
    """Resolve SCREEN_STORE from Django settings or env (sqlite|ch)."""
    try:
        from django.conf import settings

        raw = getattr(settings, "SCREEN_STORE", None)
    except Exception:
        raw = None
    if raw is None:
        raw = os.environ.get("SCREEN_STORE", "sqlite")
    backend = str(raw or "sqlite").strip().lower()
    if backend in ("clickhouse", "ch"):
        return "ch"
    return "sqlite"


def get_screen_repository(*, client: Any | None = None) -> ScreenRepository:
    if screen_store_backend() == "ch":
        return ClickHouseScreenRepository(client=client)
    return SqliteScreenRepository()


__all__ = [
    "ClickHouseScreenRepository",
    "ScreenNameConflictError",
    "ScreenNotFoundError",
    "ScreenRecord",
    "ScreenRepository",
    "SqliteScreenRepository",
    "get_screen_repository",
    "screen_store_backend",
]
