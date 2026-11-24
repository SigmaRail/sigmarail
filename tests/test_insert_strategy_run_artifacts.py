import importlib.util
from pathlib import Path
import sys


SCRIPT = Path(__file__).parents[1] / "trading_lab" / "scripts" / "insert_strategy_run.py"
SPEC = importlib.util.spec_from_file_location("insert_strategy_run", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
_sys_path = sys.path[:]
try:
    SPEC.loader.exec_module(MODULE)
finally:
    # The CLI makes its generated TradingLab tree importable at startup. Keep
    # that runtime behavior from shadowing the installed Spec in pytest.
    sys.path[:] = _sys_path


def test_oversized_optional_day_snapshots_are_skipped_with_notice(tmp_path, capsys):
    snapshot = tmp_path / "backtest_day_snapshots.json"
    snapshot.write_text('{"snapshots": []}', encoding="utf-8")

    result = MODULE.read_optional_artifact(
        str(snapshot), artifact_type="backtest_day_snapshots", max_bytes=4
    )

    assert result == ""
    assert "Omitting optional backtest_day_snapshots artifact" in capsys.readouterr().err


def test_optional_artifacts_within_limit_are_read(tmp_path):
    snapshot = tmp_path / "backtest_day_snapshots.json"
    snapshot.write_text('{"snapshots": []}', encoding="utf-8")

    assert MODULE.read_optional_artifact(
        str(snapshot), artifact_type="backtest_day_snapshots", max_bytes=100
    ) == '{"snapshots": []}'
