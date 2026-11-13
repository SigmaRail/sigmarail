"""Static validation of VeraLabV1 specs.

The table that feeds E200/E201 is *generated* by `vera_lab.ir.runtime_param_table`, which
lives in the VeraTradingLab tree because it introspects the Lean runtime. This module only
**reads** it. That direction is deliberate: VeraBase must never import `vera_lab`.

Static lint — reject invalid fields, operators, columns and expressions. Why this exists: ``save_spec`` only does ``json.loads`` + INSERT, so a spec carrying
unknown parameter names, unknown columns or malformed expression ASTs saves cleanly and
fails later (or silently succeeds, because framework models accept ``**_extra``).

This module does **not** re-implement validation. It reuses the existing ground truth and
applies it to *the whole spec document*, which nothing currently does — today those
validators only run on the ``VeraBase.Universe`` subtree during SQL compilation:

* ``sigmarail_spec``.parse_bool_expr`` / ``validate_bool_expr_depth``  — AST node types,
  operators, arity, extra fields, nesting (C-VERA-EXPR-V1)
* ``universe_v1_column_registry.get_universe_v1_col_sql_map``        — DB-backed columns

Codes
-----
``E100`` unknown expression node type / malformed AST      (error)
``E101`` expression exceeds max depth                      (error)
``E110`` unknown column referenced by an AST               (error in universe subtree,
                                                            warning under Framework.*)
``E200`` unknown framework model ``Type``                  (error)
``E201`` unknown framework parameter name                  (error — swallowed by **_extra)

Not yet implemented: detecting a parameter that *is* declared and read by code but has
no effect at runtime (e.g. ``min_regime_fraction`` when the regime always returns 1.0).
That is a semantic/coverage check, not a schema check, and it needs its own design.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Sequence

from pydantic import BaseModel, ValidationError

from sigmarail_spec import expr as spec_expr
from sigmarail.features.ir.universe_v1_column_registry import get_universe_v1_col_sql_map

__all__ = [
    "ARTIFACT_PATH",
    "LintIssue",
    "classes_by_type",
    "dialect_type_names",
    "expr_type_names",
    "lint_spec",
    "lint_spec_json",
    "render",
    "resolve_runtime_kwargs",
    "runtime_kwargs_from_artifact",
]

FRAMEWORK = "Framework"
UNIVERSE_SUBTREE_PREFIX = "VeraBase/Universe"

# `Framework.UniverseSelection.Parameters` is deliberately *not* consumed by
# VeraScreenerUniverseSelectionModel (its __init__ is `(self, store)`). The interpreter's
# `_params_with_universe_screen` forwards membership/named_groups to the Alpha, and the
# compiler lowers `screen` into the universe query. So these are live despite the class
# not declaring them — encoding this is the fix for the false positives an earlier,
# class-only checker emitted.
UNIVERSE_SLOT_FORWARDED = frozenset({"screen", "membership", "named_groups"})


@dataclass(frozen=True)
class LintIssue:
    severity: str  # "error" | "warning"
    code: str
    path: str
    message: str

    def __str__(self) -> str:  # pragma: no cover - formatting only
        return f"{self.severity.upper()} {self.code} {self.path}: {self.message}"


def _discriminators(model: Any) -> frozenset[str]:
    """Every ``type`` discriminator a union of AST nodes accepts (derived, not hardcoded)."""
    names: set[str] = set()
    args = getattr(model, "__args__", ()) or ()
    # Annotated[Union[...], Field(discriminator=...)] unwraps to (Union[...], FieldInfo)
    if args and hasattr(args[0], "__args__"):
        args = args[0].__args__
    for member in args:
        field = (getattr(member, "model_fields", {}) or {}).get("type")
        default = getattr(field, "default", None)
        if isinstance(default, str):
            names.add(default)
    return frozenset(names)


# One dialect, one home. The candidate-list machinery that used to live here existed only
# because VeraBase and VeraTradingLab declared colliding discriminators (`gte` as
# `left`/`right` here, as flat `column`/`value` there). That dialect now lives once, in
# `sigmarail_spec`, and the flat form is gone — it had no producer, no consumer and zero stored
# specs. A discriminator therefore resolves to exactly one class.
def _discriminators(model: Any) -> frozenset[str]:
    """Every ``type`` discriminator a union of AST nodes accepts."""
    names: set[str] = set()
    args = getattr(model, "__args__", ()) or ()
    if args and hasattr(args[0], "__args__"):
        args = args[0].__args__
    for member in args:
        field = (getattr(member, "model_fields", {}) or {}).get("type")
        default = getattr(field, "default", None)
        if isinstance(default, str):
            names.add(default)
    return frozenset(names)


def classes_by_type() -> dict[str, list[Any]]:
    """``{discriminator: [model]}`` for the canonical dialect.

    A list for backwards compatibility — it is always length 1 now.
    """
    table: dict[str, list[Any]] = {}
    modname = getattr(spec_expr, "__name__", "")
    for obj in vars(spec_expr).values():
        if (
            isinstance(obj, type)
            and issubclass(obj, BaseModel)
            and getattr(obj, "__module__", "") == modname
        ):
            field = (getattr(obj, "model_fields", {}) or {}).get("type")
            default = getattr(field, "default", None)
            if isinstance(default, str):
                table.setdefault(default, [obj])
    return table


def bool_type_names() -> frozenset[str]:
    """Discriminators for boolean expressions (``all``/``any``/``gte``/...)."""
    names: set[str] = set()
    for union in (spec_expr.BoolExprItem,):
        names |= _discriminators(union)
    return frozenset(names)


def operand_type_names() -> frozenset[str]:
    """Discriminators for operands (``col``/``lit``/``formula``).

    Needed as *sites* too: ``weight_expr``/``magnitude_expr`` legitimately hold a bare
    ``{"type": "col", ...}`` at the root.
    """
    return _discriminators(spec_expr.Operand)


def expr_type_names() -> frozenset[str]:
    """All ``type`` discriminators that mark a dict as an expression site."""
    return bool_type_names() | operand_type_names()


# Keys whose value is contractually an expression AST. Needed because type-based
# discovery is a whitelist and therefore blind to an *unknown* node type — which is
# precisely the case E100 must catch.
EXPR_KEYS = frozenset(
    {
        "where",
        "expr",
        "condition",
        "setup_where",
        "setup_expr",
        "eligibility_expr",
        "confidence_expr",
        "direction_expr",
        "magnitude_expr",
        "weight_expr",
        "risk_skip_time_stop_expr",
        "screen",
        "membership",
        "post_where",
    }
)




def _walk_expr_sites(
    node: Any, path: str, names: frozenset[str], key: str | None = None
) -> Iterator[tuple[str, dict]]:
    """Yield ``(path, expr_dict)`` for every expression site.

    Location-agnostic on purpose: a hardcoded path list would miss sites (gates[].where,
    setup_where, eligibility_expr, weight_expr, risk_skip_time_stop_expr, nested
    named_groups, ...). A dict is a site when its ``type`` is a known discriminator, **or**
    when it sits under a key contractually holding an AST — which is how an *unknown* node
    type becomes visible to E100. We do not descend into a matched expression.
    """
    if isinstance(node, dict):
        ntype = node.get("type")
        if isinstance(ntype, str) and (ntype in names or key in EXPR_KEYS):
            yield path, node
            return
        for k, value in node.items():
            yield from _walk_expr_sites(value, f"{path}/{k}", names, k)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _walk_expr_sites(value, f"{path}[{i}]", names, key)


def _columns_in(ast: Any) -> Iterator[str]:
    """Every ``col`` name inside a parsed AST, including nested formula args."""
    if isinstance(ast, spec_expr.ColRef):
        yield ast.name
        return
    if isinstance(ast, spec_expr.FormulaExpr):
        for arg in ast.args:
            yield from _columns_in(arg)
        return
    for value in ast.__dict__.values():
        if isinstance(value, list):
            for item in value:
                yield from _columns_in(item)
        elif hasattr(value, "__dict__"):
            yield from _columns_in(value)


def _lint_expression(
    path: str,
    raw: dict,
    bool_names: frozenset[str],
    columns: frozenset[str],
    *,
    column_severity: str,
    types: dict[str, list[Any]],
) -> list[LintIssue]:
    issues: list[LintIssue] = []
    type_name = raw.get("type")
    candidates = types.get(type_name) if isinstance(type_name, str) else None
    if not candidates:
        return [
            LintIssue("error", "E100", path, f"unknown expression node type: {type_name!r}")
        ]

    # The discriminator is shared across dialects, so a single matching candidate is
    # success. Only when every candidate rejects the node is it genuinely malformed.
    # Prefer the dialect whose declared fields the node actually uses. The same
    # discriminator has multiple shapes, and validating against the wrong one reports
    # fields that are not part of this node at all.
    ordered = sorted(
        candidates,
        key=lambda c: -len(set(getattr(c, "model_fields", {}) or {}) & set(raw)),
    )
    ast: Any = None
    best: list[dict] | None = None
    for cls in ordered:
        try:
            ast = cls.model_validate(raw)
            break
        except ValidationError as exc:
            errs = exc.errors()
            if best is None or len(errs) < len(best):
                best = errs
    if ast is None:
        for err in (best or [])[:5]:
            loc = "/".join(str(x) for x in err.get("loc", ()))
            issues.append(LintIssue("error", "E100", f"{path}/{loc}", err.get("msg", "invalid")))
        return issues

    if type_name in bool_names:
        try:
            spec_expr.validate_bool_expr_depth(ast)
        except ValueError as exc:  # depth limit exceeded
            issues.append(LintIssue("error", "E101", path, str(exc)))
            return issues
        except TypeError:
            pass  # this dialect is outside validate_bool_expr_depth's isinstance set

    for col in _columns_in(ast):
        bare = col.strip().strip("`")
        if bare.startswith("__"):
            continue  # runtime namespace (e.g. __position.price), not a column
        if bare not in columns and bare.split(".", 1)[-1] not in columns:
            issues.append(
                LintIssue(column_severity, "E110", path, f"unknown column: {col!r}")
            )
    return issues


def _lint_parameters(
    doc: dict, runtime_kwargs: dict[str, set[str] | None] | None
) -> list[LintIssue]:
    if runtime_kwargs is None:
        return []
    issues: list[LintIssue] = []
    fw = doc.get(FRAMEWORK) or {}
    for slot, spec in fw.items():
        if not isinstance(spec, dict):
            continue
        type_id = spec.get("Type") or spec.get("type")
        params = spec.get("Parameters") or {}
        if not type_id or not isinstance(params, dict):
            continue
        base = f"{FRAMEWORK}/{slot}"
        if type_id not in runtime_kwargs:
            issues.append(LintIssue("error", "E200", base, f"unknown model Type {type_id!r}"))
            continue
        allowed = runtime_kwargs[type_id]
        if allowed is None:
            # Known type (e.g. a Lean built-in) whose parameter names cannot be
            # introspected from here. Checking anyway would fabricate E201 errors.
            continue
        extra_allowed = UNIVERSE_SLOT_FORWARDED if slot == "UniverseSelection" else frozenset()
        for name in params:
            if name in allowed or name in extra_allowed:
                continue
            issues.append(
                LintIssue(
                    "error",
                    "E201",
                    f"{base}/Parameters/{name}",
                    f"{type_id} does not declare {name!r} — swallowed by **_extra",
                )
            )
    return issues


def _rule_action_vocabulary() -> dict[str, frozenset[str]] | None:
    """Action field sets from the committed runtime_param_table artifact."""
    try:
        payload = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    actions = payload.get("actions")
    if not isinstance(actions, dict):
        return None
    return {
        str(k): frozenset(v) for k, v in actions.items() if isinstance(v, list)
    }


def _lint_rules(
    doc: dict, actions: dict[str, frozenset[str]] | None = None
) -> list[LintIssue]:
    """Validate ``Framework/*/Parameters/rules`` action dicts against the artifact.

    The runtime Rule/ActionNode models are ``extra="forbid"`` — a key outside the
    action's declared fields fails validation *even when null* (compiler-emitted
    ``days``/``flag``/``fraction`` extras bit exactly this way).
    """
    if actions is None:
        actions = _rule_action_vocabulary()
    if not actions:
        return []
    issues: list[LintIssue] = []
    fw = doc.get(FRAMEWORK) or {}
    for slot, spec in fw.items():
        params = (spec or {}).get("Parameters") or {}
        rules = params.get("rules")
        if not isinstance(rules, list):
            continue
        base = f"{FRAMEWORK}/{slot}/Parameters/rules"
        for i, rule in enumerate(rules):
            if not isinstance(rule, dict):
                continue
            then = rule.get("then")
            if not isinstance(then, list) or not then:
                issues.append(
                    LintIssue("error", "E210", f"{base}[{i}]/then", "rule must have a non-empty 'then' list")
                )
                continue
            rname = rule.get("name") or f"#{i}"
            for j, action in enumerate(then):
                if not isinstance(action, dict):
                    continue
                atype = action.get("type")
                if atype not in actions:
                    issues.append(
                        LintIssue(
                            "error", "E211", f"{base}[{i}]({rname})/then[{j}]",
                            f"unknown action type {atype!r}",
                        )
                    )
                    continue
                for key in action:
                    if key not in actions[atype]:
                        issues.append(
                            LintIssue(
                                "error", "E212",
                                f"{base}[{i}]({rname})/then[{j}]/{key}",
                                f"{atype} does not declare {key!r} — extra key (even null) is rejected at runtime",
                            )
                        )
    return issues


def _declared_columns(doc: dict) -> set[str]:
    """Columns the spec defines for itself: ``select`` plus ``computed[].alias``.

    ``post_where`` legitimately references aliases declared in the same document
    (``screens_hit``, ``setup_pass``, ``w_conviction``, ...). Omitting them yields false
    errors on every valid spec — verified against the baseline.
    """
    uni = ((doc.get("VeraBase") or {}).get("Universe")) or {}
    names = {c for c in (uni.get("select") or []) if isinstance(c, str)}
    for item in uni.get("computed") or []:
        if isinstance(item, dict) and isinstance(item.get("alias"), str):
            names.add(item["alias"])
    return names


# Non-AST places that still name a column. The expression walker cannot see these: they
# are plain strings, not `{"type": "col"}` nodes, so `order_by`/`select`/`row_rank` were
# entirely unchecked.
def _lint_column_refs(
    doc: dict, physical: frozenset[str], referenceable: frozenset[str]
) -> list[LintIssue]:
    issues: list[LintIssue] = []

    def check(path: str, name: Any, severity: str, allowed: frozenset[str]) -> None:
        if not isinstance(name, str) or not name:
            return
        bare = name.strip().strip("`")
        if bare.startswith("__"):
            return
        if bare not in allowed and bare.split(".", 1)[-1] not in allowed:
            issues.append(LintIssue(severity, "E110", path, f"unknown column: {name!r}"))

    universe = ((doc.get("VeraBase") or {}).get("Universe")) or {}
    # `select[]` **is** the declaration, so validating it against the declared set is
    # vacuous — it must be checked against physical columns only.
    for i, name in enumerate(universe.get("select") or []):
        check(f"/VeraBase/Universe/select[{i}]", name, "error", physical)
    for i, item in enumerate(universe.get("order_by") or []):
        if isinstance(item, dict):
            check(
                f"/VeraBase/Universe/order_by[{i}]/field",
                item.get("field"),
                "error",
                referenceable,
            )

    alpha = (((doc.get("Framework") or {}).get("Alpha") or {}).get("Parameters")) or {}
    rank = alpha.get("row_rank") if isinstance(alpha, dict) else None
    if isinstance(rank, dict):
        for i, name in enumerate(rank.get("by") or []):
            check(
                f"/Framework/Alpha/Parameters/row_rank/by[{i}]", name, "warning", referenceable
            )
        minimum = rank.get("min")
        if isinstance(minimum, dict):
            for key in minimum:
                check(
                    f"/Framework/Alpha/Parameters/row_rank/min/{key}",
                    key,
                    "warning",
                    referenceable,
                )
    return issues


def lint_spec(
    doc: dict,
    *,
    runtime_kwargs: dict[str, set[str] | None] | None = None,
    column_map: dict[str, Any] | None = None,
    action_vocabulary: dict[str, frozenset[str]] | None = None,
) -> list[LintIssue]:
    """Lint a VeraLabV1 spec document. Returns a flat list of issues (may be empty).

    """
    types = classes_by_type()
    # Every discriminator is offered to the depth check; nodes outside
    # `validate_bool_expr_depth`'s isinstance set raise TypeError, which is swallowed.
    names = frozenset(types)
    bool_names = names
    column_map = get_universe_v1_col_sql_map() if column_map is None else column_map
    physical = frozenset(column_map)
    columns = physical | _declared_columns(doc)

    issues: list[LintIssue] = []
    issues += _lint_parameters(doc, runtime_kwargs)
    issues += _lint_rules(doc, action_vocabulary)
    issues += _lint_column_refs(doc, physical, columns)

    for path, raw in _walk_expr_sites(doc, "", names):
        # Columns under `Framework.*` are evaluated against a runtime row that carries
        # aliases the universe registry does not know (screens_hit, setup_pass,
        # w_conviction — verified absent), so an unknown name there is a warning, never
        # a false error.
        severity = "warning" if path.startswith("/Framework") else "error"
        found = _lint_expression(
            path, raw, bool_names, columns, column_severity=severity, types=types
        )
        # E100 stays an error even when no extra dialect is supplied. It was briefly
        # downgraded to a warning on the theory that an unrecognised node might belong to
        # the other dialect — but that made the gate *weaker in the Studio than in the
        # CLI*, since `vera_lab` is only importable in the latter. The one genuine case
        # (`regime.source`) is now accepted by this dialect directly, so an E100 here is a
        # real defect. If a future dialect node does trip it, the path names the node and
        # `SIGMARAIL_SPEC_LINT=warn` is the escape hatch.
        issues += found

    return issues


def lint_spec_json(
    spec_json: str,
    *,
    runtime_kwargs: dict[str, set[str] | None] | None = None,
    column_map: dict[str, Any] | None = None,
    action_vocabulary: dict[str, frozenset[str]] | None = None,
    client: Any = None,
) -> list[LintIssue]:
    """JSON-safe entry point. **Never raises.**

    Malformed JSON becomes an ``E000`` issue and a linter crash becomes ``LINT003``.
    Callers should prefer this over parsing themselves: one stored spec
    (``research-baseline-001``) has truncated JSON in ``algorithm_json``, and a linter
    that dies on it reports nothing about the other 216.

    Pass ``client`` (a ClickHouse client) to make column existence authoritative against
    the **live** database. Without it `E110` consults only the static, DDL-derived set —
    which is narrower than what the query will actually run against, so a column added to
    the live DB but not yet to `sql/schema/` would be wrongly reported as unknown. That is
    the wrong direction of error for a schema that gains columns.
    """
    import json

    if client is not None and column_map is None:
        # Invalidate both column caches first: they are process-lifetime (`lru_cache`), so
        # without this a long-lived Studio never sees a newly-added column.
        try:
            from sigmarail.features.ir.universe_v1_column_registry import (
                invalidate_universe_v1_column_registry,
                try_refresh_universe_v1_columns_from_client,
            )

            invalidate_universe_v1_column_registry()
            try_refresh_universe_v1_columns_from_client(client)
        except Exception:  # a refresh failure must not stop validation
            pass

    try:
        doc = json.loads(spec_json)
    except ValueError as exc:
        return [LintIssue("error", "E000", "-", f"algorithm_json is not valid JSON: {exc}")]
    if not isinstance(doc, dict):
        return [
            LintIssue("error", "E000", "-", f"spec must be a JSON object, got {type(doc).__name__}")
        ]
    try:
        return lint_spec(
            doc,
            runtime_kwargs=runtime_kwargs,
            column_map=column_map,
            action_vocabulary=action_vocabulary,
        )
    except Exception as exc:  # a linter crash must not cascade into the caller
        return [
            LintIssue("warning", "LINT003", "-", f"linter raised {type(exc).__name__}: {exc}")
        ]


# Committed artifact: the valid-Type / constructor-kwarg table, generated where vera_lab
# IS importable (the VeraTradingLab tree) and read where it is not (the Studio, the
# runner). Without it E200/E201 are skipped exactly where specs get saved.
ARTIFACT_PATH = Path(__file__).resolve().parents[1] / "data" / "runtime_param_table.json"


def runtime_kwargs_from_artifact(
    path: str | Path | None = None,
) -> dict[str, set[str] | None] | None:
    """Load the committed table. ``None`` when absent or unreadable."""
    target = Path(path) if path else ARTIFACT_PATH
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    types = payload.get("types")
    if not isinstance(types, dict):
        return None
    return {k: (set(v) if isinstance(v, list) else None) for k, v in types.items()}


def resolve_runtime_kwargs() -> dict[str, set[str] | None] | None:
    """The committed artifact, which is the authoritative table in this process.

    Live introspection needs `vera_lab`, which is only importable inside the VeraTradingLab
    tree — and this module deliberately does not depend on it any more (see the module note
    below). The artifact is generated *from* the live runtime and
    `vera_lab.ir.runtime_param_table --check` fails when the two drift, so reading it here
    is equivalent whenever the gate is green.
    """
    return runtime_kwargs_from_artifact()


def render(issues: list[LintIssue]) -> str:
    if not issues:
        return "OK — no issues"
    lines = [str(i) for i in issues]
    errors = sum(1 for i in issues if i.severity == "error")
    warns = len(issues) - errors
    lines.append(f"\n{errors} error(s), {warns} warning(s)")
    return "\n".join(lines)


def _load_from_clickhouse(ir_id: str) -> dict:
    """Fetch ``algorithm_json`` for a spec. Connection comes from env — never literals."""
    import json
    import os

    import clickhouse_connect

    missing = [
        k
        for k in ("CLICKHOUSE_HOST", "CLICKHOUSE_USER", "CLICKHOUSE_PASSWORD")
        if not os.environ.get(k)
    ]
    if missing:
        raise SystemExit(
            "CLICKHOUSE_HOST/CLICKHOUSE_USER/CLICKHOUSE_PASSWORD must be set to use --ir-id "
            f"(missing: {', '.join(missing)})"
        )
    client = clickhouse_connect.get_client(
        host=os.environ["CLICKHOUSE_HOST"],
        port=int(os.environ.get("CLICKHOUSE_PORT", "8123")),
        username=os.environ["CLICKHOUSE_USER"],
        password=os.environ["CLICKHOUSE_PASSWORD"],
        database=os.environ.get("CLICKHOUSE_DATABASE", "vera"),
    )
    rows = client.query(
        "SELECT algorithm_json FROM vera.strategy_algorithm_specs FINAL WHERE ir_id = "
        f"{{ir:String}}",
        parameters={"ir": ir_id},
    ).result_rows
    if not rows:
        raise SystemExit(f"no spec found for ir_id={ir_id!r}")
    return json.loads(rows[0][0])


def main(argv: list[str] | None = None) -> int:
    """CLI: lint a VeraLabV1 spec from a file or from ClickHouse.

    ``python -m sigmarail.features.ir.spec_lint spec.json``
    ``python -m sigmarail.features.ir.spec_lint --ir-id champion_vcp_reversal``

    Exit codes: 0 clean, 1 errors (or warnings with ``--strict-warnings``), 2 usage.
    """
    import argparse
    import json

    ap = argparse.ArgumentParser(prog="vera-spec-lint", description=main.__doc__)
    src = ap.add_mutually_exclusive_group(required=False)
    src.add_argument("spec_json", nargs="?", help="path to a spec JSON file")
    src.add_argument("--ir-id", help="load from vera.strategy_algorithm_specs")
    ap.add_argument("--strict-warnings", action="store_true")
    ap.add_argument("--no-runtime-params", action="store_true",
                    help="skip E200/E201")
    args = ap.parse_args(argv)

    if not args.ir_id and not args.spec_json:
        ap.error("provide spec_json or --ir-id")

    if args.ir_id:
        doc = _load_from_clickhouse(args.ir_id)
        label = args.ir_id
    else:
        with open(args.spec_json, encoding="utf-8") as fh:
            doc = json.load(fh)
        label = args.spec_json

    kwargs = None if args.no_runtime_params else runtime_kwargs_from_artifact()
    issues = lint_spec(doc, runtime_kwargs=kwargs)
    if kwargs is None and not args.no_runtime_params:
        issues.append(
            LintIssue(
                "warning",
                "LINT002",
                "-",
                "vera_lab not importable — E200/E201 and the VeraTradingLab AST dialect "
                "are unavailable (run from the VeraTradingLab tree to enable them)",
            )
        )

    print(f"# {label}")
    print(render(issues))
    has_error = any(i.severity == "error" for i in issues)
    has_warn = any(i.severity == "warning" for i in issues)
    if has_error:
        return 1
    return 1 if (args.strict_warnings and has_warn) else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
