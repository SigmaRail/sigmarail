"""Generate and verify `runtime_param_table.json` — the valid-Type / kwarg artifact.

**Why this lives here and not in VeraBase.** The table is derived by introspecting
`sigmarail_lab.runtime` class signatures and `lean_framework_interpreter._default_vera_store_builders()`.
That introspection needs this tree on `PYTHONPATH`. It used to live in
`vera_query_core.ir.spec_lint`, which made the database layer import the Lean runtime — the
one genuine cross-domain edge in VeraBase, and the wrong direction. Generating here and
*reading* there makes the dependency strictly one-way: VeraTradingLab → VeraBase, never back.

The artifact itself still lives in VeraBase (`vera_query_core/data/runtime_param_table.json`)
because VeraBase is what reads it — the Studio and the backtest runner have no access to this
tree, and a stale artifact makes `E200`/`E201` lie.
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import pathlib
import sys

_MISSING = object()

DEFAULT_ARTIFACT = (
    pathlib.Path(__file__).resolve().parents[4]
    / "VeraBase" / "src" / "vera_query_core" / "data" / "runtime_param_table.json"
)

REGENERATE = "python -m sigmarail_lab.ir.runtime_param_table --export"


def artifact_path(path: str | pathlib.Path | None = None) -> pathlib.Path:
    """Resolve the artifact: explicit argument, then $SIGMARAIL_PARAM_TABLE, then the sibling tree."""
    if path:
        return pathlib.Path(path)
    env = os.environ.get("SIGMARAIL_PARAM_TABLE")
    return pathlib.Path(env) if env else DEFAULT_ARTIFACT


def runtime_param_table() -> dict[str, set[str] | None]:
    """Valid model Types mapped to their explicit constructor kwargs.

    A value of ``None`` means *known Type, parameter names not introspectable* — the Lean
    built-ins such as ``ManualUniverseSelectionModel``. ``E201`` is skipped for those rather
    than fabricating errors. Unlike the old VeraBase implementation this does not return
    ``None`` on failure: here `sigmarail_lab` must be importable, so a failure is a real error.
    """
    import importlib
    import pkgutil

    import sigmarail_lab.runtime as rt
    from sigmarail_lab.ir import lean_framework_parameters as lfp
    from sigmarail_lab.runtime import lean_framework_interpreter as lfi

    table: dict[str, set[str] | None] = {}

    # Importing every runtime module executes the QuantConnect stub, which rewrites
    # sys.path[:] and drops site-packages (no `finally`). Snapshot and restore, or every
    # later import — including `yaml` via the column registry — fails.
    saved_path = list(sys.path)
    try:
        for mod_info in pkgutil.iter_modules(rt.__path__):
            try:
                mod = importlib.import_module(f"sigmarail_lab.runtime.{mod_info.name}")
            except Exception:
                continue
            for name, obj in vars(mod).items():
                if name in table or not inspect.isclass(obj):
                    continue
                if not getattr(obj, "__module__", "").startswith("sigmarail_lab.runtime"):
                    continue
                try:
                    sig = inspect.signature(obj)
                except (TypeError, ValueError):
                    continue
                table[name] = {
                    p for p in sig.parameters
                    if p not in ("self", "_extra", "kwargs", "args")
                }

        # Authoritative valid-Type list. Scanning runtime classes alone missed every Lean
        # built-in, which produced 243 false E200 errors across the stored corpus.
        try:
            for type_id in lfi._default_vera_store_builders():
                table.setdefault(type_id, None)
        except Exception:
            pass
        for fn_name in ("all_default_wirable_type_ids", "default_stock_lean_wired_type_ids"):
            try:
                for type_id in getattr(lfi, fn_name)():
                    table.setdefault(type_id, None)
            except Exception:
                pass

        # `{TypeId}Params` models carry the declared contract for Lean built-ins, so the
        # Type id is valid even though its constructor cannot be introspected.
        for attr in vars(lfp):
            if attr.endswith("Params") and inspect.isclass(getattr(lfp, attr)):
                table.setdefault(attr[: -len("Params")], None)
    finally:
        sys.path[:] = saved_path
    return table


def payload(table: dict[str, set[str] | None] | None = None) -> dict:
    from sigmarail_lab.ir.risk_ladder import generate_swing_risk_ladder
    from sigmarail_lab.ir.rules import action_vocabulary, ACTION_TERMINAL

    table = runtime_param_table() if table is None else table
    # The canonical generated ladder at ctor defaults — so the "rules=None"
    # decision table is inspectable by spec tooling (lint, Studio preview)
    # without importing sigmarail_lab at query time.
    default_rules = generate_swing_risk_ladder()
    return {
        "_generated_from": (
            "sigmarail_lab.runtime constructor signatures + "
            "lean_framework_interpreter._default_vera_store_builders()"
        ),
        "_regenerate": REGENERATE,
        "types": {k: (sorted(v) if v is not None else None) for k, v in sorted(table.items())},
        "actions": {k: sorted(v) for k, v in sorted(action_vocabulary().items())},
        "_terminal": {k: ACTION_TERMINAL.get(k, False) for k in sorted(ACTION_TERMINAL)},
        "default_exit_rules": default_rules,
    }


def export(path: str | pathlib.Path | None = None) -> pathlib.Path:
    out = artifact_path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload(), indent=1) + "\n", encoding="utf-8")
    return out


def _load(path: str | pathlib.Path | None) -> dict:
    try:
        data = json.loads(artifact_path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    out: dict = {}
    for key in ("types", "actions", "_terminal", "default_exit_rules"):
        value = data.get(key)
        if key == "types":
            if not isinstance(value, dict):
                return None
            out[key] = {k: (set(v) if isinstance(v, list) else None) for k, v in value.items()}
        elif key == "actions":
            if not isinstance(value, dict):
                return None
            out[key] = {k: sorted(v) if isinstance(v, list) else [] for k, v in value.items()}
        elif key == "_terminal":
            if not isinstance(value, dict):
                return None
            out[key] = {k: bool(v) for k, v in value.items()}
        elif key == "default_exit_rules":
            if not isinstance(value, list):
                return None
            out[key] = value
    return out


def check(path: str | pathlib.Path | None = None) -> list[str]:
    """Diff the committed artifact against the live runtime. Empty means current."""
    live_types = runtime_param_table()
    committed = _load(path)
    if committed is None:
        return [f"{artifact_path(path)} is missing or unreadable — regenerate with `{REGENERATE}`"]

    from sigmarail_lab.ir.rules import ACTION_TERMINAL, action_vocabulary

    live_actions = action_vocabulary()
    live_terminal = dict(ACTION_TERMINAL)
    committed_types = committed.get("types", {})
    committed_actions = committed.get("actions", {})
    committed_terminal = committed.get("_terminal", {})

    diffs: list[str] = []
    for type_id in sorted(set(live_types) | set(committed_types)):
        a, b = live_types.get(type_id, _MISSING), committed_types.get(type_id, _MISSING)
        if a is _MISSING:
            diffs.append(f"{type_id}: in the artifact but not the runtime — regenerate")
            continue
        if b is _MISSING:
            diffs.append(f"{type_id}: in the runtime but not the artifact — regenerate")
            continue
        if a is None or b is None:
            if a is not b:
                diffs.append(f"{type_id}: checkability differs ({a} vs {b})")
            continue
        if set(a) != set(b):
            diffs.append(
                f"{type_id}: runtime-only={sorted(set(a) - set(b))} "
                f"artifact-only={sorted(set(b) - set(a))} — regenerate"
            )

    for action_id in sorted(set(live_actions) | set(committed_actions)):
        a = live_actions.get(action_id, _MISSING)
        b = committed_actions.get(action_id, _MISSING)
        if a is _MISSING:
            diffs.append(f"action:{action_id}: in the artifact but not the runtime — regenerate")
            continue
        if b is _MISSING:
            diffs.append(f"action:{action_id}: in the runtime but not the artifact — regenerate")
            continue
        if sorted(a) != sorted(b):
            diffs.append(
                f"action:{action_id}: runtime fields={sorted(a)} "
                f"artifact fields={sorted(b)} — regenerate"
            )

    for action_id in sorted(set(live_terminal) | set(committed_terminal)):
        a = live_terminal.get(action_id, _MISSING)
        b = committed_terminal.get(action_id, _MISSING)
        if a is _MISSING or b is _MISSING or a != b:
            diffs.append(
                f"terminal:{action_id}: runtime={a} artifact={b} — regenerate"
            )

    # The generated default ladder is part of the contract surface: drift between
    # the runtime generator and the artifact means the stored-spec view of
    # "which rules will run" has gone stale.
    try:
        from sigmarail_lab.ir.risk_ladder import generate_swing_risk_ladder

        live_rules = generate_swing_risk_ladder()
        committed_rules = committed.get("default_exit_rules")
        if committed_rules != live_rules:
            diffs.append(
                "default_exit_rules: artifact differs from the runtime generator "
                "— regenerate"
            )
    except Exception as exc:
        diffs.append(f"default_exit_rules: could not generate ({exc})")

    return diffs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--export", nargs="?", const="", metavar="PATH",
                    help="write the table (default: the VeraBase artifact)")
    ap.add_argument("--check", nargs="?", const="", metavar="PATH",
                    help="diff the artifact against the runtime; exit 1 when stale")
    args = ap.parse_args(argv)

    if args.export is not None:
        out = export(args.export or None)
        print(f"wrote {out}")
        return 0
    if args.check is not None:
        diffs = check(args.check or None)
        if diffs:
            print("runtime parameter table is STALE — regenerate with "
                  f"`{REGENERATE}`:")
            for d in diffs:
                print(f"  {d}")
            return 1
        print(f"runtime parameter table is current ({len(runtime_param_table())} types)")
        return 0
    ap.error("provide --export or --check")


if __name__ == "__main__":
    raise SystemExit(main())
