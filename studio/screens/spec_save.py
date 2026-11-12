"""Guarded spec save: fork-on-edit when the target spec already has backtest runs.

Why this exists
---------------
``strategy_runs`` rows join to specs by ``ir_id`` alone (see
``screens/backtest.py``: ``LEFT JOIN strategy_algorithm_specs s FINAL ON
r.ir_id = s.ir_id``). Overwriting a spec in place therefore silently re-points
every prior run at content it never ran — the only trace is
``strategy_runs.ir_content_hash`` disagreeing with the spec's current hash.

Observed for real: ``v2_validation_sepa_minervini_recovery_surrogates`` had 5
runs spanning 2 spec revisions plus one unstamped run before this guard.

Enforcement lives here, **server-side**, so the REST view, the MCP tool and the
Studio UI cannot diverge — an agent cannot dodge the guard by calling the API
directly.

Contract (``SigmaRailStudio/AGENTS.md`` → *Spec reasoning + exploration
loop*): forks carry ``parent_ir_id`` + ``mutation_type`` + ``changelog_notes``.

Fork naming follows the shipped UI convention
(``ForkStrategyVersionModal.suggestNextVersion``): ``{base}-v{N}``, incrementing
from the highest existing sibling.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

__all__ = [
    "SpecGuardError",
    "count_runs",
    "hash_algorithm_json",
    "lint_spec_json",
    "next_fork_ir_id",
    "run_revision_stale",
    "save_spec_guarded",
    "spec_content_hash",
    "split_version",
]

# --- spec lint gate -------------------------------------------------------------------
# ``VERA_SPEC_LINT`` = ``off`` | ``warn`` | ``enforce``
#   off     — skip the linter entirely
#   warn    — run it, return findings, never block
#   enforce — refuse the save on any error-severity finding. **Default.**
#
# The default flipped from ``warn`` to ``enforce`` only after a precision audit of the
# whole corpus: every one of the 40 flagged specs was verified to carry a real defect, and
# none of the 176 clean ones was touched. Before that audit the linter had four separate
# false-positive classes (self-declared `computed` aliases, colliding AST dialects, an
# incomplete model-Type list, `select` validating against itself); enforcing then would
# have blocked valid configuration.
#
# An unknown value resolves to ``enforce`` too: a typo must never silently disable a gate.
# Use ``warn`` or ``off`` explicitly when you are deliberately iterating on a spec.
LINT_MODES = ("off", "warn", "enforce")


def _lint_mode() -> str:
    mode = (os.environ.get("VERA_SPEC_LINT") or "enforce").strip().lower()
    return mode if mode in LINT_MODES else "enforce"


def _apply_lint_gate(mode: str, findings: list[dict[str, str]], ir_id: str) -> None:
    """Raise when ``mode == 'enforce'`` and any finding is error-severity."""
    if mode != "enforce":
        return
    errors = [f for f in findings if f.get("severity") == "error"]
    if not errors:
        return
    detail = "; ".join(
        f"{f.get('code')} {f.get('path')}: {f.get('message')}" for f in errors[:6]
    )
    raise SpecGuardError(
        f"spec lint rejected {ir_id}: {len(errors)} error(s) — {detail}"
    )


def lint_spec_json(spec_json: str, client: Any | None = None) -> list[dict[str, str]]:
    """Lint a spec document. Never raises; returns serialisable findings.

    Reports *skipped* checks too, so an empty list is never mistaken for a clean bill of
    health — silently passing because a check never ran is the exact failure mode this
    gate exists to prevent.
    """
    try:
        from vera_query_core.ir import spec_lint
    except Exception as exc:  # pragma: no cover - depends on the host environment
        return [
            {
                "severity": "warning",
                "code": "LINT001",
                "path": "-",
                "message": f"spec linter unavailable: {exc}",
            }
        ]

    kwargs = None
    try:
        # `resolve_runtime_kwargs` prefers live introspection (fresher — only possible in
        # the VeraTradingLab tree) and falls back to the committed artifact, so this gate
        # checks E200/E201 in the Studio process too, where `vera_lab` is not importable.
        kwargs = spec_lint.resolve_runtime_kwargs()
        findings = spec_lint.lint_spec_json(
            spec_json,
            runtime_kwargs=kwargs,
            client=client,
        )
    except Exception as exc:  # a linter crash must not block a save
        return [
            {
                "severity": "warning",
                "code": "LINT003",
                "path": "-",
                "message": f"linter raised {type(exc).__name__}: {exc}",
            }
        ]

    out = [
        {
            "severity": i.severity,
            "code": i.code,
            "path": i.path,
            "message": i.message,
        }
        for i in findings
    ]
    if kwargs is None:
        out.append(
            {
                "severity": "warning",
                "code": "LINT002",
                "path": "-",
                "message": "no runtime parameter table available (neither live introspection "
                "nor the packaged data/runtime_param_table.json) — E200/E201 skipped",
            }
        )
    return out

#: Shipped convention — `ForkStrategyVersionModal.suggestNextVersion`.
_VERSION_RE = re.compile(r"^(?P<base>.+?)-v(?P<n>\d+)$")


class SpecGuardError(RuntimeError):
    """The run-history check could not be performed.

    Deliberately fail-closed: if we cannot prove the spec has no runs we must not
    overwrite it, because a wrong overwrite is unrecoverable while a refused save
    is not.
    """


def split_version(ir_id: str) -> tuple[str, int]:
    """``"x-v3"`` → ``("x", 3)``; an unversioned id → ``(id, 1)``."""
    match = _VERSION_RE.match((ir_id or "").strip())
    if match:
        return match.group("base"), int(match.group("n"))
    return (ir_id or "").strip(), 1


def count_runs(client: Any, ir_id: str) -> int:
    """Number of backtest runs recorded against ``ir_id``."""
    rows = client.query(
        "SELECT count() FROM strategy_runs FINAL WHERE ir_id = %(ir_id)s",
        parameters={"ir_id": ir_id},
    ).result_rows
    return int(rows[0][0]) if rows else 0


def hash_algorithm_json(algo_json: Any) -> str:
    """``sha256(algorithm_json)`` — the canonical ``ir_content_hash``.

    ``strategy_algorithm_specs`` stores **no** hash column; every reader derives
    it from ``algorithm_json``. ``screens/backtest_jobs.py`` and
    ``sigmarail_studio_mcp.backtest_runner.runner._ir_lineage_from_db`` do the same — route all
    callers through here so the three cannot drift apart.
    """
    if not algo_json:
        return ""
    return hashlib.sha256(str(algo_json).encode("utf-8")).hexdigest()


def spec_content_hash(client: Any, ir_id: str) -> tuple[bool, str]:
    """``(exists, ir_content_hash)`` for ``ir_id``."""
    rows = client.query(
        "SELECT algorithm_json FROM strategy_algorithm_specs FINAL"
        " WHERE ir_id = %(ir_id)s LIMIT 1",
        parameters={"ir_id": ir_id},
    ).result_rows
    if not rows:
        return False, ""
    return True, hash_algorithm_json(rows[0][0])


def next_fork_ir_id(client: Any, parent_ir_id: str) -> str:
    """``{base}-v{max sibling + 1}`` — forking ``x-v2`` yields ``x-v3``.

    A fork continues the family rather than nesting suffixes, so a lineage chain
    stays flat and readable in the spec library.
    """
    base, current = split_version(parent_ir_id)
    if not base:
        raise SpecGuardError("cannot derive a fork id from an empty ir_id")

    rows = client.query(
        "SELECT ir_id FROM strategy_algorithm_specs FINAL"
        " WHERE startsWith(ir_id, %(prefix)s)",
        parameters={"prefix": base},
    ).result_rows

    highest = max(1, current)
    for (sibling,) in rows:
        sibling_base, sibling_n = split_version(str(sibling))
        # Only `base` itself and `base-vN` belong to this family.
        if sibling_base == base:
            highest = max(highest, sibling_n)
    return f"{base}-v{highest + 1}"


def run_revision_stale(run_hash: str | None, spec_hash: str | None) -> bool:
    """True when a run came from a different revision than the spec's current one.

    Callers must pass already-trimmed hashes (``strategy_runs.ir_content_hash`` is
    ``FixedString(64)`` and NUL-padded — trim with
    ``trimRight(CAST(... AS Nullable(String)), '\\0')`` at the SQL layer, as
    ``screens/backtest.py`` does).
    """
    run_h = (run_hash or "").strip()
    spec_h = (spec_hash or "").strip()
    if not run_h or not spec_h:
        return False  # unstamped legacy run — unknown, not provably stale
    return run_h != spec_h


def save_spec_guarded(
    *,
    ir_id: str,
    title: str,
    spec_json: str,
    notes: str = "",
    pipeline_json: str | None = None,
    spec_schema_version: int | None = None,
    changelog_notes: str = "",
    author_agent: str = "user",
    force_fork: bool = False,
    client: Any | None = None,
) -> dict[str, Any]:
    """Save a spec, forking when the target already has backtest runs.

    ``force_fork=True`` forks even when the target has no runs (the explicit
    "Save as new version" path). Otherwise a spec with zero runs is updated in
    place and stamped ``mutation_type="patch"``.

    Returns the runner's payload plus ``forked``, ``parent_ir_id``,
    ``mutation_type``, ``changelog_notes`` and the effective ``ir_id`` — which
    differs from the input whenever a fork happened, so callers (especially the
    UI) must use the returned value.
    """
    from screens.ch import get_ch_client

    try:
        from sigmarail_studio_mcp.backtest_runner.runner import save_spec as _runner_save
    except ImportError as exc:  # runner package not on PYTHONPATH
        raise SpecGuardError(f"spec save unavailable: {exc}") from exc

    owned_client = client is None
    client = client if client is not None else get_ch_client()

    try:
        target = (ir_id or "").strip()
        if not target:
            raise SpecGuardError("ir_id is required")

        exists, current_hash = spec_content_hash(client, target)

        effective_id = target
        parent_ir_id = ""
        parent_content_hash = ""
        mutation_type = "init"
        forked = False
        runs = 0

        if exists:
            try:
                runs = count_runs(client, target)
            except Exception as exc:
                raise SpecGuardError(
                    f"cannot verify run history for {target!r}: {exc}"
                ) from exc

            if runs >= 1 or force_fork:
                forked = True
                parent_ir_id = target
                # `strategy_algorithm_specs.parent_content_hash` is FixedString(8) —
                # the short hash the fork UI displays, not the full sha256.
                parent_content_hash = current_hash[:8]
                mutation_type = "fork"
                effective_id = next_fork_ir_id(client, target)
                if not changelog_notes.strip():
                    changelog_notes = (
                        f"auto-fork: parent {target} had {runs} run(s)"
                        if runs >= 1
                        else f"fork of {target}"
                    )
            else:
                mutation_type = "patch"

        save_kwargs: dict[str, Any] = {
            "ir_id": effective_id,
            "title": title,
            "spec_json": spec_json,
            "notes": notes,
            "mutation_type": mutation_type,
            "changelog_notes": changelog_notes,
            "author_agent": author_agent,
        }
        if pipeline_json is not None:
            save_kwargs["pipeline_json"] = pipeline_json
        if spec_schema_version is not None:
            save_kwargs["spec_schema_version"] = spec_schema_version
        if parent_ir_id:
            save_kwargs["parent_ir_id"] = parent_ir_id
        if parent_content_hash:
            save_kwargs["parent_content_hash"] = parent_content_hash

        # --- spec-truth materialization (before lint so the linter sees the ----
        # stored form): when the risk slot is SwingProgressive without authored
        # rules, the generated ladder is injected into Parameters.rules — the
        # runtime would regenerate the identical table from the same knobs, so
        # this changes visibility only, never behavior. The seeded rules are
        # then mirrored into the pipeline doc's exit stage so the Studio Risk
        # card renders the exact decision table that will run.
        try:
            from screens.pcm_rules import materialize_pcm_rules, seed_pipeline_pcm_rules
            from screens.risk_rules import (
                materialize_swing_risk_rules,
                seed_pipeline_risk_rules,
            )

            spec_dict = json.loads(spec_json)
            changed_spec = materialize_swing_risk_rules(spec_dict)
            # PCM Phase 2: same contract — the generated allocation table +
            # size_expr materialize into Parameters so the stored spec carries
            # the decision surface that runs.
            changed_spec = materialize_pcm_rules(spec_dict) or changed_spec
            if changed_spec:
                spec_json = json.dumps(spec_dict, separators=(",", ":"), sort_keys=True)
                save_kwargs["spec_json"] = spec_json
            if pipeline_json is not None:
                doc_dict = json.loads(pipeline_json)
                seeded = seed_pipeline_risk_rules(spec_dict, doc_dict)
                seeded = seed_pipeline_pcm_rules(spec_dict, doc_dict) or seeded
                if seeded:
                    pipeline_json = json.dumps(
                        doc_dict, separators=(",", ":"), sort_keys=True
                    )
                    save_kwargs["pipeline_json"] = pipeline_json
        except Exception:
            # Materialization is best-effort — when the generator is not
            # importable the runtime regenerates the identical ladder
            # internally, so a save must never fail on this step.
            pass

        # --- lint gate — runs BEFORE the INSERT so `enforce` can actually block ------
        lint_mode = _lint_mode()
        lint_findings: list[dict[str, str]] = []
        if lint_mode != "off":
            lint_findings = lint_spec_json(spec_json, client)
            _apply_lint_gate(lint_mode, lint_findings, effective_id)

        out = _runner_save(**save_kwargs)

        result: dict[str, Any] = dict(out or {})
        result.update(
            {
                "ir_id": effective_id,
                "forked": forked,
                "parent_ir_id": parent_ir_id,
                "parent_content_hash": parent_content_hash,
                "mutation_type": mutation_type,
                "changelog_notes": changelog_notes,
                "runs_on_parent": runs,
                "lint_mode": lint_mode,
                "lint": lint_findings,
            }
        )
        if pipeline_json is not None:
            # Echo the stored form (post-materialization), not the request doc,
            # so callers see the seeded exit-stage rules immediately.
            try:
                result["pipeline_document"] = json.loads(pipeline_json)
            except Exception:
                pass
        return result
    finally:
        if owned_client:
            try:
                client.close()
            except Exception:
                pass
