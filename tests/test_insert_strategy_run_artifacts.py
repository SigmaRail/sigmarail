import importlib.util
from pathlib import Path
import sys


SCRIPT = Path(__file__).parents[1] / "trading_lab" / "scripts" / "insert_strategy_run.py"
SPEC = importlib.util.spec_from_file_location("insert_strategy_run", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
_sys_path = sys.path[:]
_module_prefixes = ("sigmarail_lab", "sigmarail_spec")
_modules = {
    name: module
    for name, module in sys.modules.items()
    if any(name == prefix or name.startswith(f"{prefix}.") for prefix in _module_prefixes)
}
try:
    SPEC.loader.exec_module(MODULE)
finally:
    # The CLI makes its generated TradingLab tree importable at startup. Keep
    # its import path and module cache from shadowing installed packages in pytest.
    sys.path[:] = _sys_path
    for name in list(sys.modules):
        if any(name == prefix or name.startswith(f"{prefix}.") for prefix in _module_prefixes):
            sys.modules.pop(name, None)
    sys.modules.update(_modules)


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
