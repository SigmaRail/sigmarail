from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from sigmarail_lab.runtime.lean_framework_interpreter import (
    LeanFrameworkInterpreterError,
    apply_lean_framework_v1_algorithm_hints,
    wire_lean_framework_v1,
)
from sigmarail_lab.ir.lean_framework_json import LeanFrameworkV1Document
from sigmarail_lab.ir.lean_framework_presets import list_lean_framework_preset_ids
from sigmarail_lab.ir.lean_framework_resolve import (
    LeanFrameworkJsonResolutionError,
    resolve_lean_framework_v1_raw,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ir"


def test_rsi_parameters_reject_extra_keys() -> None:
    d = json.loads((FIXTURES / "lean_framework_v1_minimal.json").read_text(encoding="utf-8"))
    d["Framework"]["Alpha"]["Parameters"]["not_a_rsi_field"] = True
    with pytest.raises(ValidationError):
        LeanFrameworkV1Document.model_validate(d)


def test_rsi_period_must_be_positive_int() -> None:
    d = json.loads((FIXTURES / "lean_framework_v1_minimal.json").read_text(encoding="utf-8"))
    d["Framework"]["Alpha"]["Parameters"]["period"] = 0
    with pytest.raises(ValidationError):
        LeanFrameworkV1Document.model_validate(d)


def test_lean_framework_v1_fixture_validates() -> None:
    raw = (FIXTURES / "lean_framework_v1_minimal.json").read_text(encoding="utf-8")
    doc = LeanFrameworkV1Document.model_validate_json(raw)
    assert doc.kind == "LeanFrameworkV1"
    assert doc.framework.alpha.type == "RsiAlphaModel"


def test_lean_framework_v1_rejects_wrong_kind() -> None:
    d = json.loads((FIXTURES / "lean_framework_v1_minimal.json").read_text(encoding="utf-8"))
    d["Kind"] = "VeraLabV1"
    with pytest.raises(ValueError):
        LeanFrameworkV1Document.model_validate(d)


def test_resolve_lean_framework_missing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LEAN_FRAMEWORK_V1_PATH", raising=False)
    monkeypatch.delenv("LEAN_FRAMEWORK_V1_BASE64", raising=False)
    with pytest.raises(LeanFrameworkJsonResolutionError, match="LEAN_FRAMEWORK_V1"):
        resolve_lean_framework_v1_raw()


def test_resolve_lean_framework_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    p = tmp_path / "doc.json"
    p.write_text((FIXTURES / "lean_framework_v1_minimal.json").read_text(encoding="utf-8"))
    monkeypatch.setenv("LEAN_FRAMEWORK_V1_PATH", str(p))
    monkeypatch.delenv("LEAN_FRAMEWORK_V1_BASE64", raising=False)
    raw = resolve_lean_framework_v1_raw()
    assert "LeanFrameworkV1" in raw


def test_wire_lean_framework_with_stub_registry() -> None:
    raw = (FIXTURES / "lean_framework_v1_minimal.json").read_text(encoding="utf-8")
    doc = LeanFrameworkV1Document.model_validate_json(raw)

    built: list[tuple[str, dict]] = []

    def make_model(type_id: str):
        class M:
            def __init__(self, **kwargs):
                built.append((type_id, dict(kwargs)))

        M.__name__ = type_id
        return M

    types = [
        "ManualUniverseSelectionModel",
        "RsiAlphaModel",
        "EqualWeightingPortfolioConstructionModel",
        "ImmediateExecutionModel",
        "MaximumDrawdownPercentPerSecurity",
    ]
    registry = {t: make_model(t) for t in types}

    class MockAlgo:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        def set_universe_selection(self, m):
            self.calls.append(("universe", m))

        def set_alpha(self, m):
            self.calls.append(("alpha", m))

        def set_portfolio_construction(self, m):
            self.calls.append(("pcm", m))

        def set_execution(self, m):
            self.calls.append(("exec", m))

        def set_risk_management(self, m):
            self.calls.append(("risk", m))

        def set_cash(self, _x):
            pass

        def set_benchmark(self, _x):
            pass

    algo = MockAlgo()
    wire_lean_framework_v1(algo, doc, registry=registry, normalize=False)

    assert len(built) == 5
    assert built[0][0] == "ManualUniverseSelectionModel"
    assert built[0][1]["symbols"] == ["SPY", "QQQ"]
    assert built[1][1]["period"] == 14
    assert built[1][1]["resolution"] == "Daily"
    assert len(algo.calls) == 5


def test_wire_unknown_type_raises() -> None:
    raw = (FIXTURES / "lean_framework_v1_minimal.json").read_text(encoding="utf-8")
    d = json.loads(raw)
    d["Framework"]["Alpha"]["Type"] = "TotallyUnknownAlphaModel"
    doc = LeanFrameworkV1Document.model_validate(d)

    class MockAlgo:
        def set_universe_selection(self, m):
            pass

        def set_alpha(self, m):
            pass

        def set_portfolio_construction(self, m):
            pass

        def set_execution(self, m):
            pass

        def set_risk_management(self, m):
            pass

    def _stub(_tid: str):
        class M:
            def __init__(self, **kwargs):
                pass

        M.__name__ = _tid
        return M

    # Registry covers every slot except the unknown alpha type — fail at alpha.
    registry = {
        "ManualUniverseSelectionModel": _stub("ManualUniverseSelectionModel"),
        "EqualWeightingPortfolioConstructionModel": _stub("EqualWeightingPortfolioConstructionModel"),
        "ImmediateExecutionModel": _stub("ImmediateExecutionModel"),
        "MaximumDrawdownPercentPerSecurity": _stub("MaximumDrawdownPercentPerSecurity"),
    }

    with pytest.raises(LeanFrameworkInterpreterError, match="Unknown framework Type"):
        wire_lean_framework_v1(MockAlgo(), doc, registry=registry, normalize=False)


def test_preset_fixture_file_validates() -> None:
    raw = (FIXTURES / "lean_framework_v1_preset_only.json").read_text(encoding="utf-8")
    doc = LeanFrameworkV1Document.model_validate_json(raw)
    assert doc.framework.alpha.type == "RsiAlphaModel"


def test_list_lean_framework_preset_ids() -> None:
    assert "minimal_rsi_spy_qqq" in list_lean_framework_preset_ids()


def test_framework_preset_matches_minimal_fixture() -> None:
    raw = json.dumps(
        {
            "SchemaVersion": 2,
            "Kind": "LeanFrameworkV1",
            "FrameworkPreset": "minimal_rsi_spy_qqq",
        }
    )
    doc = LeanFrameworkV1Document.model_validate_json(raw)
    minimal = LeanFrameworkV1Document.model_validate_json(
        (FIXTURES / "lean_framework_v1_minimal.json").read_text(encoding="utf-8")
    )
    assert doc.framework.model_dump(by_alias=True) == minimal.framework.model_dump(by_alias=True)
    assert doc.framework_preset == "minimal_rsi_spy_qqq"


def test_framework_preset_xor_inline_framework() -> None:
    base = json.loads((FIXTURES / "lean_framework_v1_minimal.json").read_text(encoding="utf-8"))
    base["FrameworkPreset"] = "minimal_rsi_spy_qqq"
    with pytest.raises(ValueError, match="Framework or FrameworkPreset"):
        LeanFrameworkV1Document.model_validate(base)


def test_unknown_framework_preset() -> None:
    raw = json.dumps(
        {
            "SchemaVersion": 2,
            "Kind": "LeanFrameworkV1",
            "FrameworkPreset": "no_such_preset_xyz",
        }
    )
    with pytest.raises(ValueError, match="unknown LeanFrameworkV1 FrameworkPreset"):
        LeanFrameworkV1Document.model_validate_json(raw)


def test_wire_lean_framework_v1_with_preset_only_json() -> None:
    raw = json.dumps(
        {
            "SchemaVersion": 2,
            "Kind": "LeanFrameworkV1",
            "FrameworkPreset": "minimal_rsi_spy_qqq",
        }
    )
    doc = LeanFrameworkV1Document.model_validate_json(raw)

    built: list[tuple[str, dict]] = []

    def make_model(type_id: str):
        class M:
            def __init__(self, **kwargs):
                built.append((type_id, dict(kwargs)))

        M.__name__ = type_id
        return M

    types = [
        "ManualUniverseSelectionModel",
        "RsiAlphaModel",
        "EqualWeightingPortfolioConstructionModel",
        "ImmediateExecutionModel",
        "MaximumDrawdownPercentPerSecurity",
    ]
    registry = {t: make_model(t) for t in types}

    class MockAlgo:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        def set_universe_selection(self, m):
            self.calls.append(("universe", m))

        def set_alpha(self, m):
            self.calls.append(("alpha", m))

        def set_portfolio_construction(self, m):
            self.calls.append(("pcm", m))

        def set_execution(self, m):
            self.calls.append(("exec", m))

        def set_risk_management(self, m):
            self.calls.append(("risk", m))

    algo = MockAlgo()
    wire_lean_framework_v1(algo, doc, registry=registry, normalize=False)
    assert len(built) == 5
    assert built[0][0] == "ManualUniverseSelectionModel"


def test_apply_algorithm_hints() -> None:
    raw = (FIXTURES / "lean_framework_v1_minimal.json").read_text(encoding="utf-8")
    doc = LeanFrameworkV1Document.model_validate_json(raw)

    class A:
        def __init__(self):
            self.cash = None
            self.bench = None

        def set_cash(self, v):
            self.cash = v

        def set_benchmark(self, v):
            self.bench = v

    a = A()
    apply_lean_framework_v1_algorithm_hints(a, doc)
    assert a.cash == 100000.0
    assert a.bench == "SPY"


def test_lean_only_runner_sequence_former_main_lean_py(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    Specification for the old ``main_lean.py`` QC entry: env resolution, validation,
    date/cash setup, algorithm hints, then ``wire_lean_framework_v1`` (stubs, no LEAN container).
    """
    p = tmp_path / "doc.json"
    p.write_text((FIXTURES / "lean_framework_v1_minimal.json").read_text(encoding="utf-8"))
    monkeypatch.setenv("LEAN_FRAMEWORK_V1_PATH", str(p))
    monkeypatch.delenv("LEAN_FRAMEWORK_V1_BASE64", raising=False)

    raw = resolve_lean_framework_v1_raw()
    doc = LeanFrameworkV1Document.model_validate_json(raw)

    class _US:
        resolution = None

    built: list[tuple[str, dict]] = []

    def make_model(type_id: str):
        class M:
            def __init__(self, **kwargs):
                built.append((type_id, dict(kwargs)))

        M.__name__ = type_id
        return M

    types = [
        "ManualUniverseSelectionModel",
        "RsiAlphaModel",
        "EqualWeightingPortfolioConstructionModel",
        "ImmediateExecutionModel",
        "MaximumDrawdownPercentPerSecurity",
    ]
    registry = {t: make_model(t) for t in types}

    class MockAlgo:
        def __init__(self) -> None:
            self.slot_calls: list[tuple[str, object]] = []
            self.cash: int | float | None = None
            self.universe_settings = _US()
            self._dates: list[tuple[str, tuple[int, int, int]]] = []

        def get_parameter(self, key: str) -> str | None:
            if key == "start-date":
                return "2022-01-01"
            if key == "end-date":
                return "2022-12-31"
            if key == "initial-cash":
                return "100000"
            return None

        def set_start_date(self, y: int, m: int, d: int) -> None:
            self._dates.append(("start", (y, m, d)))

        def set_end_date(self, y: int, m: int, d: int) -> None:
            self._dates.append(("end", (y, m, d)))

        def set_cash(self, v: int | float) -> None:
            self.cash = v

        def set_benchmark(self, v: object) -> None:
            self.slot_calls.append(("benchmark_hint", v))

        def set_universe_selection(self, m: object) -> None:
            self.slot_calls.append(("universe", m))

        def set_alpha(self, m: object) -> None:
            self.slot_calls.append(("alpha", m))

        def set_portfolio_construction(self, m: object) -> None:
            self.slot_calls.append(("pcm", m))

        def set_execution(self, m: object) -> None:
            self.slot_calls.append(("exec", m))

        def set_risk_management(self, m: object) -> None:
            self.slot_calls.append(("risk", m))

    algo = MockAlgo()
    start_date = algo.get_parameter("start-date") or "2022-01-01"
    end_date = algo.get_parameter("end-date") or "2022-12-31"
    initial_cash = int(algo.get_parameter("initial-cash") or 100_000)
    s = [int(x) for x in start_date.split("-")]
    e = [int(x) for x in end_date.split("-")]
    algo.set_start_date(s[0], s[1], s[2])
    algo.set_end_date(e[0], e[1], e[2])
    algo.universe_settings.resolution = "Daily"

    apply_lean_framework_v1_algorithm_hints(algo, doc)
    algo.set_cash(initial_cash)
    wire_lean_framework_v1(algo, doc, registry=registry, normalize=False)

    assert algo._dates == [("start", (2022, 1, 1)), ("end", (2022, 12, 31))]
    assert algo.cash == 100_000
    assert any(t == "benchmark_hint" and v == "SPY" for t, v in algo.slot_calls)
    assert len(built) == 5
    assert built[0][0] == "ManualUniverseSelectionModel"
    framework_calls = [c for c in algo.slot_calls if c[0] != "benchmark_hint"]
    assert len(framework_calls) == 5


def test_expanded_lean_framework_models_normalization() -> None:
    from sigmarail_lab.runtime.lean_framework_interpreter import _normalize_parameters, default_stock_lean_wired_type_ids

    type_ids = default_stock_lean_wired_type_ids()
    assert "MacdAlphaModel" in type_ids
    assert "EmaCrossAlphaModel" in type_ids
    assert "TrailingStopRiskManagementModel" in type_ids
    assert "MaximumSectorExposureRiskManagementModel" in type_ids
    assert "VolumeWeightedAveragePriceExecutionModel" in type_ids
    assert "RiskParityPortfolioConstructionModel" in type_ids

    # Test parameter normalization
    norm_macd = _normalize_parameters(
        "MacdAlphaModel",
        {"fast_period": 10, "slow_period": 20, "signal_period": 5},
        symbol_cls=None,
        security_type_cls=None,
        market_cls=None,
        resolution_cls=None,
    )
    assert norm_macd["fastPeriod"] == 10
    assert norm_macd["slowPeriod"] == 20
    assert norm_macd["signalPeriod"] == 5

    norm_trail = _normalize_parameters(
        "TrailingStopRiskManagementModel",
        {"maximum_drawdown_percent": 0.05},
        symbol_cls=None,
        security_type_cls=None,
        market_cls=None,
        resolution_cls=None,
    )
    assert norm_trail["maximumDrawdownPercent"] == 0.05

    norm_sector = _normalize_parameters(
        "MaximumSectorExposureRiskManagementModel",
        {"maximum_sector_exposure": 0.25},
        symbol_cls=None,
        security_type_cls=None,
        market_cls=None,
        resolution_cls=None,
    )
    assert norm_sector["maximumSectorExposure"] == 0.25


def test_composite_framework_models_wiring() -> None:
    from sigmarail_lab.runtime.lean_framework_interpreter import (
        _build_framework_model_instance,
        default_stock_lean_wired_type_ids,
    )

    type_ids = default_stock_lean_wired_type_ids()
    assert "CompositeAlphaModel" in type_ids
    assert "CompositeRiskManagementModel" in type_ids
    assert "CompositeUniverseSelectionModel" in type_ids

    # Stub registry
    class SubAlpha:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class CompositeAlpha:
        def __init__(self, *models):
            self.models = list(models)

    lean_reg = {
        "SubAlpha": SubAlpha,
        "CompositeAlphaModel": CompositeAlpha,
    }

    params = {
        "models": [
            {"Type": "SubAlpha", "Parameters": {"period": 14}},
            {"Type": "SubAlpha", "Parameters": {"period": 28}},
        ]
    }

    instance = _build_framework_model_instance(
        "CompositeAlphaModel",
        params,
        store=None,
        store_builders={},
        lean_reg=lean_reg,
        normalize=False,
    )

    assert isinstance(instance, CompositeAlpha)
    assert len(instance.models) == 2
    assert instance.models[0].kwargs == {"period": 14}
    assert instance.models[1].kwargs == {"period": 28}


def test_vera_screener_alpha_and_pcm_holding_retention() -> None:
    from datetime import date, datetime, timedelta
    from sigmarail_lab.runtime.qc_sigmarail_screener_framework import (
        InsightDirection,
        Market,
        SecurityType,
        Symbol,
        VeraScreenerAlphaModel,
        VeraScreenerPortfolioConstructionModel,
    )

    class StubStore:
        def __init__(self, scores):
            self._scores = scores

        def get_universe(self, date_str):
            return self._scores.get(date_str, {})

        def get_spy_is_bull(self, date_str):
            return True

        def get_atrs(self, date_str):
            return {"AAPL": 0.02, "MSFT": 0.02, "NVDA": 0.03, "GOOGL": 0.02}

    class StubHolding:
        def __init__(self, invested=True, avg_px=100.0, qty=10, val=1000.0):
            self.Invested = invested
            self.AveragePrice = avg_px
            self.Quantity = qty
            self.HoldingsValue = val

    class StubPortfolio(dict):
        def __init__(self):
            super().__init__()
            self.Cash = 10000.0
            self.TotalPortfolioValue = 12000.0

    class StubSecurities(dict):
        def __contains__(self, k):
            return True

        def __getitem__(self, k):
            class S:
                Price = 100.0
            return S()

    class StubAlgorithm:
        def __init__(self):
            self.Time = datetime(2026, 1, 5, 9, 30)
            self.Portfolio = StubPortfolio()
            self.Securities = StubSecurities()
            self.logs = []

        def Debug(self, msg):
            self.logs.append(msg)

        def GetParameter(self, k):
            return None

    # Test 1: Alpha model rank hysteresis
    scores_day1 = {"AAPL": 95.0, "MSFT": 90.0, "NVDA": 85.0}
    scores_day2 = {"NVDA": 98.0, "GOOGL": 96.0, "AAPL": 88.0, "MSFT": 80.0}
    store = StubStore({"2026-01-04": scores_day1, "2026-01-05": scores_day2})

    alpha = VeraScreenerAlphaModel(store, max_positions=2, min_hold_days=3, hold_buffer_rank=5)
    algo = StubAlgorithm()

    # Day 1: AAPL and MSFT are top 2 -> Up insights
    insights_day1 = alpha.Update(algo, None)
    up_tickers_day1 = {i.Symbol.Value for i in insights_day1 if i.Direction == InsightDirection.Up}
    assert "AAPL" in up_tickers_day1
    assert "MSFT" in up_tickers_day1

    # Day 2: AAPL drops to #3, but is within hold_buffer_rank=5 and held < 3 days -> NOT exited!
    aapl_sym = Symbol.Create("AAPL", SecurityType.Equity, Market.USA)
    algo.Portfolio[aapl_sym] = StubHolding(invested=True, avg_px=100.0, qty=10, val=1000.0)
    algo.Time = datetime(2026, 1, 6, 9, 30)

    insights_day2 = alpha.Update(algo, None)
    flat_tickers_day2 = {i.Symbol.Value for i in insights_day2 if i.Direction == InsightDirection.Flat}
    assert "AAPL" not in flat_tickers_day2  # AAPL is protected by buffer rank!

    # Test 2: PCM does not liquidate invested positions when new candidates arrive
    pcm = VeraScreenerPortfolioConstructionModel(store, max_positions=5, max_weight=0.10)
    targets = pcm.CreateTargets(algo, insights_day2)

    # AAPL was invested, so PCM should NOT emit a target with 0 quantity for AAPL
    aapl_targets = [t for t in targets if t.Symbol.Value == "AAPL"]
    assert len(aapl_targets) == 0 or all(t.Quantity != 0 for t in aapl_targets)
