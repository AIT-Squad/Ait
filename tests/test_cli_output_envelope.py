"""CLI output envelope: validate-new-model & lint emit the standard ok() shape.

Covers [TDD]-cli output contract — every stdout payload is wrapped as
``{"ok": true, "data": {...}}`` and ok() terminates the process by itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ait.cli import main
from ait.index_manager import IndexManager
from ait.specgraph import sync_specgraph


def _payload(result):
    return json.loads(result.output.strip().splitlines()[-1])


def _blank_project(tmp_path: Path) -> Path:
    root = tmp_path / "project-docs"
    for sub in ("docs/prd", "docs/fsd", "docs/tdd", ".meta/versions", ".meta/changes"):
        (root / sub).mkdir(parents=True)
    IndexManager(root).rebuild_baseline()
    sync_specgraph(root)
    return root


def test_validate_new_model_uses_ok_envelope(tmp_path: Path, monkeypatch):
    root = _blank_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(main, ["specgraph", "validate-new-model"], catch_exceptions=False)
    # standard envelope: {"ok": true, "data": {...}}, exit 0 (report, not failure)
    assert r.exit_code == 0
    p = _payload(r)
    assert p["ok"] is True
    assert "data" in p
    assert p["data"]["passed"] is True
    assert p["data"]["violations"] == []
    # no flat top-level violations key (envelope, not flat)
    assert "violations" not in p


def test_lint_uses_ok_envelope(tmp_path: Path, monkeypatch):
    root = _blank_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(main, ["lint", "--scope", "baseline"], catch_exceptions=False)
    assert r.exit_code == 0
    p = _payload(r)
    assert p["ok"] is True
    assert p["data"]["passed"] is True
    assert "violations" not in p          # lives under data, not flat
    assert "violations" in p["data"]


def test_ok_terminates_process(capsys):
    """ok() must exit(0) by itself — a call site relying on fall-through must
    never emit a second line."""
    from ait.cli import ok

    with pytest.raises(SystemExit) as exc:
        ok({"x": 1})
        # unreachable: proves ok() itself stops execution, not the test
        click_echo_marker = "should never run"
        raise AssertionError(click_echo_marker)
    assert exc.value.code == 0

    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    assert json.loads(out[0]) == {"ok": True, "data": {"x": 1}}
