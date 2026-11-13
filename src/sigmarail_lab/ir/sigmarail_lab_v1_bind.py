"""Bind Kind VeraLabV1 documents to ClickHouse runner inputs (Phase 2 / OOD plan §8.2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .lean_framework_json import FrameworkBundleV1
from .sigmarail_lab_v1_ch_parameters import validate_sigmarail_lab_v1_framework_bundle
from .sigmarail_lab_v1_json import VeraLabV1Document


class VeraLabV1ComposeError(RuntimeError):
    """Invalid framework Type for CH stack or bad Parameters (defense in depth)."""


@dataclass(frozen=True)
class BoundVeraLabV1:
    """Pure data needed to wire ClickHouseUniverseAlgorithm (store + framework kwargs + parameters)."""

    universe: UniverseLike
    framework: FrameworkBundleV1
    _alpha_kwargs: dict[str, Any]
    _portfolio_kwargs: dict[str, Any]
    _parameter_map: dict[str, str]
    _vera_base: Any = None

    def alpha_model_kwargs(self) -> dict[str, Any]:
        return dict(self._alpha_kwargs)

    def portfolio_model_kwargs(self) -> dict[str, Any]:
        return dict(self._portfolio_kwargs)

    def lean_set_parameter_map(self) -> dict[str, str]:
        return dict(self._parameter_map)


@dataclass
class _VeraBaseShim:
    """Shim to expose VeraBase data_sources and Evaluation to store / Initialize."""
    data_sources: list
    evaluation: Any = None

    def get(self, name: str):
        for spec in self.data_sources:
            if spec.name == name:
                return spec
        return None


@dataclass
class _RegimeShim:
    """CH regime loader alias for store.bind — source from DataSources only."""

    source: str | None = None


@dataclass
class _BoundLeanFrameworkShim:
    """Mimics LeanFrameworkSpec API used by main.py (three methods + regime)."""

    _bound: BoundVeraLabV1

    def lean_set_parameter_map(self) -> dict[str, str]:
        return self._bound.lean_set_parameter_map()

    def alpha_model_kwargs(self) -> dict[str, Any]:
        return self._bound.alpha_model_kwargs()

    def portfolio_model_kwargs(self) -> dict[str, Any]:
        return self._bound.portfolio_model_kwargs()

    @property
    def regime(self) -> _RegimeShim:
        # Prefer DataSources catalog; never default to mart ``daily``.
        vb = self._bound._vera_base
        if vb is not None and getattr(vb, "data_sources", None):
            for spec in vb.data_sources:
                name = getattr(spec, "name", None) or (
                    spec.get("name") if isinstance(spec, dict) else None
                )
                if name != "regime":
                    continue
                table = getattr(spec, "table", None) or (
                    spec.get("table") if isinstance(spec, dict) else None
                )
                if table:
                    return _RegimeShim(source=str(table))
        # AlgorithmParameters regime-source only if explicitly set (no silent daily)
        params = self._bound.lean_set_parameter_map()
        src = (params.get("regime-source") or "").strip()
        if src and src not in ("screener",):
            return _RegimeShim(source=src)
        return _RegimeShim(source=None)

    # Expose fields for clickhouse_runner_bundle compatibility
    @property
    def alpha(self):
        # Return a shim object with model_dump method
        bound = self._bound
        class _AlphaShim:
            def model_dump(self):
                return bound.alpha_model_kwargs()
        return _AlphaShim()

    @property
    def portfolio(self):
        bound = self._bound
        class _PortfolioShim:
            def model_dump(self):
                return bound.portfolio_model_kwargs()
        return _PortfolioShim()

    @property
    def exits(self):
        class _ExitsShim:
            def model_dump(self):
                # Graph mode doesn't use exits - return empty
                return {}
        return _ExitsShim()


class VeraLabV1BindingProxy:
    """Drop-in alongside VeraLab for Initialize: effective_universe + effective_lean_framework."""

    def __init__(self, bound: BoundVeraLabV1, policy_graph: Optional[dict] = None) -> None:
        self._bound = bound
        self._policy_graph = policy_graph

    def effective_universe(self) -> UniverseLike:
        return self._bound.universe

    def effective_lean_framework(self) -> _BoundLeanFrameworkShim:
        return _BoundLeanFrameworkShim(self._bound)

    def framework_bundle(self) -> FrameworkBundleV1:
        return self._bound.framework

    def is_graph_mode(self) -> bool:
        return self._policy_graph is not None

    @property
    def root(self) -> Optional[dict]:
        return self._policy_graph

    @property
    def vera_base(self):
        return self._bound._vera_base


def bind_sigmarail_lab_v1(doc: VeraLabV1Document) -> BoundVeraLabV1:
    fb = doc.framework
    try:
        validate_sigmarail_lab_v1_framework_bundle(fb)
    except ValueError as e:
        raise VeraLabV1ComposeError(str(e)) from e

    alpha_kw = dict(fb.alpha.parameters or {})
    pcm_kw = dict(fb.portfolio_construction.parameters or {})
    vera_base_shim = _VeraBaseShim(
        doc.vera_base.data_sources,
        evaluation=doc.vera_base.evaluation,
    )

    return BoundVeraLabV1(
        universe=doc.vera_base.universe,
        framework=fb,
        _alpha_kwargs=alpha_kw,
        _portfolio_kwargs=pcm_kw,
        _parameter_map=dict(doc.algorithm_parameters),
        _vera_base=vera_base_shim,
    )


def bind_sigmarail_lab_v1_with_graph(doc: VeraLabV1Document) -> tuple[BoundVeraLabV1, Optional[dict]]:
    """Bind and also extract PolicyGraph for graph mode."""
    fb = doc.framework
    try:
        validate_sigmarail_lab_v1_framework_bundle(fb)
    except ValueError as e:
        raise VeraLabV1ComposeError(str(e)) from e

    alpha_kw = dict(fb.alpha.parameters or {})
    pcm_kw = dict(fb.portfolio_construction.parameters or {})

    vera_base_shim = _VeraBaseShim(
        doc.vera_base.data_sources,
        evaluation=doc.vera_base.evaluation,
    )

    bound = BoundVeraLabV1(
        universe=doc.vera_base.universe,
        framework=fb,
        _alpha_kwargs=alpha_kw,
        _portfolio_kwargs=pcm_kw,
        _parameter_map=dict(doc.algorithm_parameters),
        _vera_base=vera_base_shim,
    )
    policy_graph = doc.vera_base.policy_graph
    return bound, policy_graph
