"""ScreenRepository unit tests (SQLite + mocked ClickHouse)."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from screens.screen_store import (
    ClickHouseScreenRepository,
    ScreenNameConflictError,
    ScreenNotFoundError,
    SqliteScreenRepository,
    get_screen_repository,
    screen_store_backend,
)


def _sample_spec() -> dict:
    return {
        "version": 1,
        "from": "daily_screener",
        "select": ["ticker", "close", "overall_score"],
        "where": {
            "type": "all",
            "items": [
                {
                    "type": "gt",
                    "left": {"type": "col", "name": "close"},
                    "right": {"type": "lit", "value": 10},
                }
            ],
        },
        "order_by": [{"field": "overall_score", "direction": "desc"}],
        "limit_per_day": 20,
    }


@pytest.mark.django_db
def test_sqlite_repo_crud() -> None:
    repo = SqliteScreenRepository()
    created = repo.create(name="a1-leaders", spec=_sample_spec())
    assert created.id
    assert created.spec_content_hash
    listed = repo.list()
    assert any(s.id == created.id for s in listed)
    got = repo.get(str(created.id))
    assert got.name == "a1-leaders"
    updated = repo.update(str(created.id), name="a1-leaders-v2")
    assert updated.name == "a1-leaders-v2"
    repo.delete(str(created.id))
    with pytest.raises(ScreenNotFoundError):
        repo.get(str(created.id))


@pytest.mark.django_db
def test_sqlite_repo_name_conflict() -> None:
    repo = SqliteScreenRepository()
    repo.create(name="dup-screen", spec=_sample_spec())
    with pytest.raises(ScreenNameConflictError):
        repo.create(name="dup-screen", spec=_sample_spec())


def test_clickhouse_repo_create_list_get() -> None:
    client = MagicMock()
    # name_taken query
    empty = MagicMock()
    empty.result_rows = []
    # list/get after insert
    list_result = MagicMock()
    list_result.column_names = [
        "screen_id",
        "name",
        "spec_json",
        "spec_content_hash",
        "source_template_id",
        "created_at",
    ]
    sid = "11111111-2222-3333-4444-555555555555"
    list_result.result_rows = [
        (
            sid,
            "ch-screen",
            json.dumps(_sample_spec()),
            "a" * 64,
            "",
            datetime(2026, 8, 27, 12, 0, 0),
        )
    ]
    client.query.side_effect = [empty, list_result, list_result]

    repo = ClickHouseScreenRepository(client=client)
    created = repo.create(name="ch-screen", spec=_sample_spec())
    assert created.name == "ch-screen"
    assert client.insert.called
    assert created.id
    listed = repo.list()
    assert listed[0].id == sid
    got = repo.get(sid)
    assert got.name == "ch-screen"


def test_clickhouse_repo_soft_delete() -> None:
    client = MagicMock()
    get_result = MagicMock()
    get_result.column_names = [
        "screen_id",
        "name",
        "spec_json",
        "spec_content_hash",
        "source_template_id",
        "created_at",
    ]
    sid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    get_result.result_rows = [
        (
            sid,
            "to-delete",
            json.dumps(_sample_spec()),
            "b" * 64,
            "",
            datetime(2026, 8, 27, 12, 0, 0),
        )
    ]
    client.query.return_value = get_result
    repo = ClickHouseScreenRepository(client=client)
    repo.delete(sid)
    args = client.insert.call_args
    assert args[0][0] == "strategy_screens"
    row = args[0][1][0]
    assert row[5] == 1  # deleted flag


def test_screen_store_backend_default(settings) -> None:
    settings.SCREEN_STORE = "sqlite"
    assert screen_store_backend() == "sqlite"
    assert isinstance(get_screen_repository(), SqliteScreenRepository)
    settings.SCREEN_STORE = "ch"
    assert screen_store_backend() == "ch"
    assert isinstance(get_screen_repository(), ClickHouseScreenRepository)
    settings.SCREEN_STORE = "sqlite"
