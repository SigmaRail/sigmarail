"""Compatibility import path for the canonical SigmaRail Spec compiler."""

from sigmarail_spec.strategy.compiler import (
    compile_pipeline,
    compile_pipeline_prefix,
    compile_portfolio,
)

__all__ = ["compile_pipeline", "compile_pipeline_prefix", "compile_portfolio"]
