"""Spec lint gate on the guarded save path.

The gate wraps `VeraBase`'s `spec_lint` at the single server-side choke point that the
REST view, the MCP tool and the Studio UI all funnel through, so an agent cannot dodge it
by calling the API directly.

Default is `enforce`. It became so only after the 2026-10-02 precision audit, which
verified every flagged spec as a genuine defect. These tests pin the default so it cannot
silently become blocking *without* that evidence, nor silently stop blocking.
"""

from __future__ import annotations

import json

import pytest

from screens import spec_save


# --- mode selection -------------------------------------------------------------------

def test_lint_mode_defaults_to_enforce(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default is enforcing. Flipped only after a corpus precision audit
    (2026-10-02-spec-lint-gate): 40 flagged specs all genuine, 0 false positives."""
    monkeypatch.delenv("VERA_SPEC_LINT", raising=False)
    assert spec_save._lint_mode() == "enforce"


@pytest.mark.parametrize("value", ["off", "warn", "enforce", "ENFORCE", " enforce "])
def test_lint_mode_accepts_known_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("VERA_SPEC_LINT", value)
    assert spec_save._lint_mode() == value.strip().lower()


@pytest.mark.parametrize("value", ["", "yes", "true", "block"])
def test_lint_mode_rejects_unknown_values_to_enforce(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """A typo'd mode must never silently disable the gate."""
    monkeypatch.setenv("VERA_SPEC_LINT", value)
    assert spec_save._lint_mode() == "enforce"


# --- the gate decision ----------------------------------------------------------------

def test_gate_passes_when_mode_is_warn() -> None:
    findings = [{"severity": "error", "code": "E201", "path": "/x", "message": "boom"}]
    spec_save._apply_lint_gate("warn", findings, "some-spec")  # must not raise


def test_gate_passes_when_mode_is_off() -> None:
    findings = [{"severity": "error", "code": "E201", "path": "/x", "message": "boom"}]
    spec_save._apply_lint_gate("off", findings, "some-spec")


def test_gate_raises_in_enforce_on_error() -> None:
    findings = [{"severity": "error", "code": "E201", "path": "/x", "message": "boom"}]
    with pytest.raises(spec_save.SpecGuardError) as exc:
        spec_save._apply_lint_gate("enforce", findings, "some-spec")
    assert "some-spec" in str(exc.value)
    assert "E201" in str(exc.value)


def test_gate_allows_warnings_in_enforce() -> None:
    """Warnings must never block — `Framework.*` columns are warnings by design."""
    findings = [{"severity": "warning", "code": "E110", "path": "/x", "message": "hmm"}]
    spec_save._apply_lint_gate("enforce", findings, "some-spec")


def test_gate_allows_empty_findings_in_enforce() -> None:
    spec_save._apply_lint_gate("enforce", [], "some-spec")


# --- lint_spec_json -------------------------------------------------------------------

def test_lint_spec_json_flags_invalid_json() -> None:
    findings = spec_save.lint_spec_json("{not json")
    assert [f for f in findings if f["code"] == "E000" and f["severity"] == "error"]


def test_lint_spec_json_flags_unknown_node_type() -> None:
    doc = {"Framework": {"Alpha": {"Type": "VeraPyramidAlphaModel",
                                   "Parameters": {"setup_where": {"type": "frobnicate"}}}}}
    findings = spec_save.lint_spec_json(json.dumps(doc))
    assert [f for f in findings if f["code"] == "E100" and f["severity"] == "error"]


def test_lint_spec_json_never_raises_and_is_serialisable() -> None:
    for payload in ("{}", "[]", "null", "not json at all", json.dumps({"Framework": {}})):
        findings = spec_save.lint_spec_json(payload)
        assert isinstance(findings, list)
        json.dumps(findings)  # must survive a JSON round trip into the MCP payload


def test_lint_spec_json_reports_skipped_parameter_check() -> None:
    """An empty result must be distinguishable from 'the check never ran'."""
    findings = spec_save.lint_spec_json(json.dumps({"Framework": {}}))
    if any(f["code"] == "LINT002" for f in findings):
        assert all(f["severity"] == "warning" for f in findings if f["code"] == "LINT002")
    else:  # vera_lab importable in this environment -> check actually ran
        assert not any(f["code"] == "LINT002" for f in findings)


# --- integration: the gate must block BEFORE the write --------------------------------

BAD_SPEC = json.dumps(
    {
        "Framework": {
            "Alpha": {
                "Type": "VeraPyramidAlphaModel",
                "Parameters": {"setup_where": {"type": "frobnicate"}},
            }
        }
    }
)


def _patch_runner(monkeypatch: pytest.MonkeyPatch) -> list:
    """Capture runner.save_spec calls and make the target look brand new."""
    runner = pytest.importorskip("sigmarail_studio_mcp.backtest_runner.runner")
    calls: list = []
    monkeypatch.setattr(runner, "save_spec", lambda **kw: calls.append(kw) or {"inserted": True})
    monkeypatch.setattr(spec_save, "spec_content_hash", lambda client, ir: (False, ""))
    return calls


def test_enforce_blocks_save_before_the_insert(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERA_SPEC_LINT", "enforce")
    calls = _patch_runner(monkeypatch)
    with pytest.raises(spec_save.SpecGuardError):
        spec_save.save_spec_guarded(
            ir_id="brand-new-spec", title="t", spec_json=BAD_SPEC, client=object()
        )
    assert calls == [], "enforce must prevent the write, not report after it"


def test_warn_still_saves_and_reports_findings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERA_SPEC_LINT", "warn")
    calls = _patch_runner(monkeypatch)
    result = spec_save.save_spec_guarded(
        ir_id="brand-new-spec", title="t", spec_json=BAD_SPEC, client=object()
    )
    assert len(calls) == 1, "warn must not block the write"
    assert result["lint_mode"] == "warn"
    assert any(f["severity"] == "error" for f in result["lint"])


def test_off_skips_the_linter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VERA_SPEC_LINT", "off")
    calls = _patch_runner(monkeypatch)
    result = spec_save.save_spec_guarded(
        ir_id="brand-new-spec", title="t", spec_json=BAD_SPEC, client=object()
    )
    assert len(calls) == 1
    assert result["lint"] == []
