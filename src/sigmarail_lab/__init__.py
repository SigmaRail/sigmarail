"""Python package for the VeraLab algorithm JSON contract (Pydantic models, resolver, SQL)."""

from sigmarail_lab.ir.models import VeraLab
from sigmarail_lab.ir.resolver import ResolvedVeraLab, resolve_sigmarail_lab

__all__ = ["VeraLab", "ResolvedVeraLab", "resolve_sigmarail_lab"]
