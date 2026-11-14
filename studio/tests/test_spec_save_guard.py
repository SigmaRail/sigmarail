"""A+C: guarded spec save forks when the target already has backtest runs.

Motivated by measured drift: ``v2_validation_sepa_minervini_recovery_surrogates``
had runs spanning multiple spec revisions plus an unstamped one, because the
compose save path overwrote the spec in place. See ``screens/spec_save.py``.

These are pure unit tests — the ClickHouse client and the runner's ``save_spec``
are both replaced, so no database is required.

NOTE: ``strategy_algorithm_specs`` has **no ``ir_content_hash`` column**; the hash
is derived from ``algorithm_json``. The fakes below therefore answer the
``algorithm_json`` query that the real database accepts — an earlier version of
this file faked the wrong query and let a live 502 through.
"""
from __future__ import annotations

import hashlib

import pytest

from screens import spec_save

OLD_JSON = '{"Kind":"VeraLabV1","x":1}'
NEW_JSON = '{"Kind":"VeraLabV1","x":2}'


def _hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@pytest.fixture(autouse=True)
def _no_real_clickhouse(monkeypatch):
    """Safety net: no test here may touch the real database.

    An earlier version of this file forgot to stub the runner's ``save_spec`` and
    attempted a live insert. Fail loudly instead.
    """
    import screens.ch

    def _boom():
        raise AssertionError("test attempted a real ClickHouse connection")

    monkeypatch.setattr(screens.ch, "get_ch_client", _boom)
    monkeypatch.setattr(screens.ch, "get_client", _boom, raising=False)


class _Result:
    def __init__(self, rows):
        self.result_rows = rows


class FakeClient:
    """Answers exactly the queries the guard makes against the real schema."""

    def __init__(
        self,
        *,
        algorithm_json: str | None = None,
        runs: int = 0,
        siblings: list[str] | None = None,
        runs_error: bool = False,
    ) -> None:
        self.algorithm_json = algorithm_json
        self.runs = runs
        self.siblings = list(siblings or [])
        self.runs_error = runs_error
        self.closed = False
        self.queries: list[str] = []

    def query(self, sql, parameters=None):  # noqa: ANN001, ANN201
        s = " ".join(str(sql).split())
        self.queries.append(s)
        if "count() FROM strategy_runs" in s:
            if self.runs_error:
                raise RuntimeError("clickhouse unavailable")
            return _Result([(self.runs,)])
        if "startsWith(ir_id" in s:
            return _Result([(x,) for x in self.siblings])
        if "algorithm_json FROM strategy_algorithm_specs" in s:
            if self.algorithm_json is None:
                return _Result([])
            return _Result([(self.algorithm_json,)])
        raise AssertionError(f"unexpected query: {s[:90]}")

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def saved(monkeypatch):
    """Capture the kwargs the guard hands to the runner's save_spec."""
    calls: list[dict] = []

    def fake_save(**kw):  # noqa: ANN003, ANN202
        calls.append(kw)
        return {"ir_id": kw["ir_id"], "ir_content_hash": _hash(NEW_JSON), "inserted": True}

    import sigmarail_studio_mcp.backtest_runner.runner as runner

    monkeypatch.setattr(runner, "save_spec", fake_save)
    return calls


def _save(client: FakeClient, **overrides):
    kwargs = dict(
        ir_id="strat-x",
        title="Strat X",
        spec_json=NEW_JSON,
        client=client,
    )
    kwargs.update(overrides)
    return spec_save.save_spec_guarded(**kwargs)


# --- hash convention --------------------------------------------------------

def test_spec_content_hash_derives_from_algorithm_json():
    """Locks the convention shared with backtest_jobs / runner."""
    exists, h = spec_save.spec_content_hash(FakeClient(algorithm_json=OLD_JSON), "strat-x")
    assert exists is True
    assert h == _hash(OLD_JSON)


def test_spec_content_hash_reports_absence():
    exists, h = spec_save.spec_content_hash(FakeClient(algorithm_json=None), "strat-x")
    assert exists is False
    assert h == ""


def test_guard_never_queries_an_ir_content_hash_column(saved):
    """`strategy_algorithm_specs.ir_content_hash` does not exist — selecting it 502s."""
    client = FakeClient(algorithm_json=OLD_JSON, runs=2)
    _save(client)
    for q in client.queries:
        assert "ir_content_hash" not in q, f"query would fail on the real schema: {q}"


def test_parent_content_hash_is_short_enough_for_the_column(saved):
    """`parent_content_hash` is FixedString(8) — a full sha256 would fail the insert."""
    out = _save(FakeClient(algorithm_json=OLD_JSON, runs=1))
    assert out["parent_content_hash"] == _hash(OLD_JSON)[:8]
    assert len(out["parent_content_hash"]) <= 8
    assert saved[0]["parent_content_hash"] == _hash(OLD_JSON)[:8]


# --- naming -----------------------------------------------------------------

def test_split_version():
    assert spec_save.split_version("strat-x-v3") == ("strat-x", 3)
    assert spec_save.split_version("strat-x") == ("strat-x", 1)
    assert spec_save.split_version("") == ("", 1)


def test_next_fork_ir_id_increments_from_highest_sibling():
    client = FakeClient(siblings=["strat-x", "strat-x-v2", "strat-y-v9"])
    # v2 is already taken, so the next free slot is v3 — and `strat-y-v9` must
    # not leak into `strat-x`'s family.
    assert spec_save.next_fork_ir_id(client, "strat-x") == "strat-x-v3"
    assert spec_save.next_fork_ir_id(client, "strat-x-v2") == "strat-x-v3"


def test_next_fork_ir_id_first_fork_is_v2():
    assert spec_save.next_fork_ir_id(FakeClient(siblings=["strat-x"]), "strat-x") == "strat-x-v2"


def test_next_fork_ir_id_rejects_empty_parent():
    with pytest.raises(spec_save.SpecGuardError):
        spec_save.next_fork_ir_id(FakeClient(), "")


# --- guard behaviour --------------------------------------------------------

def test_new_spec_is_init_and_not_forked(saved):
    out = _save(FakeClient(algorithm_json=None))
    assert out["forked"] is False
    assert out["mutation_type"] == "init"
    assert out["ir_id"] == "strat-x"
    assert "parent_ir_id" not in saved[0]


def test_edit_with_no_runs_patches_in_place(saved):
    out = _save(FakeClient(algorithm_json=OLD_JSON, runs=0))
    assert out["forked"] is False
    assert out["mutation_type"] == "patch"
    assert out["ir_id"] == "strat-x"
    assert "parent_ir_id" not in saved[0]


def test_edit_with_runs_auto_forks(saved):
    out = _save(FakeClient(algorithm_json=OLD_JSON, runs=2))
    assert out["forked"] is True
    assert out["mutation_type"] == "fork"
    assert out["ir_id"] == "strat-x-v2"
    assert out["parent_ir_id"] == "strat-x"
    # parent_content_hash is the PARENT's derived hash, truncated to the
    # FixedString(8) the column stores — not the new content's full hash.
    assert out["parent_content_hash"] == _hash(OLD_JSON)[:8]
    assert out["runs_on_parent"] == 2
    # The original id is never written to.
    assert saved[0]["ir_id"] == "strat-x-v2"
    assert saved[0]["parent_ir_id"] == "strat-x"


def test_auto_fork_records_a_changelog(saved):
    out = _save(FakeClient(algorithm_json=OLD_JSON, runs=3))
    assert out["changelog_notes"] == "auto-fork: parent strat-x had 3 run(s)"
    assert saved[0]["changelog_notes"]


def test_explicit_changelog_is_preserved(saved):
    out = _save(
        FakeClient(algorithm_json=OLD_JSON, runs=1),
        changelog_notes="tightened stop to 1.5x ATR",
    )
    assert out["changelog_notes"] == "tightened stop to 1.5x ATR"


def test_force_fork_forks_even_with_no_runs(saved):
    out = _save(FakeClient(algorithm_json=OLD_JSON, runs=0), force_fork=True)
    assert out["forked"] is True
    assert out["mutation_type"] == "fork"
    assert out["ir_id"] == "strat-x-v2"


def test_author_agent_is_forwarded(saved):
    _save(FakeClient(algorithm_json=None), author_agent="agent-7")
    assert saved[0]["author_agent"] == "agent-7"


def test_run_count_failure_fails_closed(monkeypatch):
    """If run history can't be verified we must NOT overwrite."""
    calls: list[dict] = []
    import sigmarail_studio_mcp.backtest_runner.runner as runner

    monkeypatch.setattr(runner, "save_spec", lambda **kw: calls.append(kw))
    client = FakeClient(algorithm_json=OLD_JSON, runs_error=True)
    with pytest.raises(spec_save.SpecGuardError):
        _save(client)
    assert calls == [], "guard must not write when the run count is unknown"


def test_caller_supplied_client_is_not_closed(saved):
    client = FakeClient(algorithm_json=None)
    _save(client)
    assert client.closed is False


# --- C: revision staleness --------------------------------------------------

def test_run_revision_stale():
    assert spec_save.run_revision_stale("a" * 8, "b" * 8) is True
    assert spec_save.run_revision_stale("a" * 8, "a" * 8) is False
    # Unstamped legacy run — unknown, not provably stale.
    assert spec_save.run_revision_stale(None, "a" * 8) is False
    assert spec_save.run_revision_stale("a" * 8, None) is False
    assert spec_save.run_revision_stale("", "") is False
