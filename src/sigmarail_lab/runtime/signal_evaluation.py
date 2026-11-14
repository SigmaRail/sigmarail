"""Row-level evaluators re-exported from the generated LEAN-local runtime package.

The evaluator and expression dialect are authored in `packages/sigmarail-spec/`. The
`sigmarail_spec/` directory is generated into the backtest template because the LEAN runtime runs
the uploaded project tree without installing sibling packages. Tests fail if this copy drifts.

This module remains a compatibility re-export. New local code should import from `sigmarail_spec`;
the LEAN project uses the vendored `sigmarail_spec` namespace.
"""

from __future__ import annotations

from sigmarail_spec import (  # noqa: F401  (re-export for compatibility)
    evaluate_entry_triggers,
    evaluate_single_trigger,
    evaluate_slot_bool,
    evaluate_slot_number,
    evaluate_where_ast,
)

__all__ = [
    "evaluate_entry_triggers",
    "evaluate_single_trigger",
    "evaluate_slot_bool",
    "evaluate_slot_number",
    "evaluate_where_ast",
]
