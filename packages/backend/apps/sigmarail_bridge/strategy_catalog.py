"""Authenticated, package-backed catalogs used by the strategy editor."""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from sigmarail_spec.strategy import (
    PipelineDocument,
    PortfolioDocument,
    compile_pipeline,
    compile_portfolio,
    decompile_pipeline,
    decompile_portfolio,
    generate_default_init_stop,
    generate_swing_risk_ladder,
    get_preset,
    list_factors,
    list_presets,
)
from sigmarail_spec.strategy.position_bindings import POSITION_BINDINGS

from .views import _workspace_for_request


def _materialize_generated_risk_rules(spec: dict[str, Any]) -> None:
    """Bake SigmaRail Spec's canonical default risk rules into the compiled spec."""
    framework = spec.get("Framework")
    risk = framework.get("RiskManagement") if isinstance(framework, dict) else None
    if not isinstance(risk, dict) or risk.get("Type") != "SwingProgressiveRiskManagementModel":
        return
    params = risk.get("Parameters")
    if not isinstance(params, dict):
        params = {}
        risk["Parameters"] = params
    if not params.get("rules"):
        params["rules"] = generate_swing_risk_ladder(**params)
    if params.get("init_stop") is None:
        params["init_stop"] = generate_default_init_stop(
            use_atr_stops=bool(params.get("use_atr_stops", True)),
            atr_stop_multiplier=float(params.get("atr_stop_multiplier", 2.0)),
            max_stop_loss_pct=float(params.get("max_stop_loss_pct", 0.05)),
        )


class StrategyFactorsView(APIView):
    def get(self, request: Request) -> Response:
        _, error = _workspace_for_request(request)
        if error:
            return error
        return Response({"factors": list_factors()})


class StrategyPositionFieldsView(APIView):
    def get(self, request: Request) -> Response:
        _, error = _workspace_for_request(request)
        if error:
            return error
        fields: list[dict[str, Any]] = [dict(binding) for binding in POSITION_BINDINGS]
        return Response({"fields": fields, "count": len(fields)})


class StrategyPresetsView(APIView):
    """List the built-in strategy presets from the installed SigmaRail Spec."""

    def get(self, request: Request) -> Response:
        _, error = _workspace_for_request(request)
        if error:
            return error
        return Response({"presets": list_presets()})


class StrategyPresetView(APIView):
    """Return one built-in preset as its editable pipeline document."""

    def get(self, request: Request, preset_id: str) -> Response:
        _, error = _workspace_for_request(request)
        if error:
            return error
        try:
            document = get_preset(preset_id)
        except (KeyError, ValueError):
            return Response({"detail": "Strategy preset not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(document.model_dump(mode="json"))


class StrategyPipelineCompileView(APIView):
    def post(self, request: Request) -> Response:
        _, error = _workspace_for_request(request)
        if error:
            return error
        body = request.data if isinstance(request.data, dict) else {}
        try:
            spec = compile_pipeline(PipelineDocument.model_validate(body))
            _materialize_generated_risk_rules(spec)
            return Response(spec)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class StrategyPipelineDecompileView(APIView):
    def post(self, request: Request) -> Response:
        _, error = _workspace_for_request(request)
        if error:
            return error
        body = request.data if isinstance(request.data, dict) else {}
        try:
            return Response(decompile_pipeline(body).model_dump(mode="json"))
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class StrategyPipelineValidateView(APIView):
    def post(self, request: Request) -> Response:
        _, error = _workspace_for_request(request)
        if error:
            return error
        body = request.data if isinstance(request.data, dict) else {}
        try:
            compile_pipeline(PipelineDocument.model_validate(body))
            return Response({"valid": True})
        except Exception as exc:
            return Response({"valid": False, "error": str(exc)})


class StrategyPortfolioCompileView(APIView):
    def post(self, request: Request) -> Response:
        _, error = _workspace_for_request(request)
        if error:
            return error
        body = request.data if isinstance(request.data, dict) else {}
        try:
            return Response(compile_portfolio(PortfolioDocument.model_validate(body)))
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class StrategyPortfolioDecompileView(APIView):
    def post(self, request: Request) -> Response:
        _, error = _workspace_for_request(request)
        if error:
            return error
        body = request.data if isinstance(request.data, dict) else {}
        try:
            return Response(decompile_portfolio(body).model_dump(mode="json"))
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
