"""target_file existence scan (new_model_validator + validate-new-model wiring).

Covers [TDD]-new_model_validator (validate_target_file_existence) and its
exposure via `specgraph validate-new-model`. The confirm-gate side lives in
tests/test_version_confirm.py ([TDD]-version_confirm_tests).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ait.cli import main
from ait.new_model_manager import NewModelManager
from ait.new_model_validator import TDD_TARGET_FILE_MISSING, validate_target_file_existence
from ait.specgraph import sync_specgraph


def _payload(result):
    return json.loads(result.output.strip().splitlines()[-1])


def _write(root: Path, relative: str, content: str) -> None:
    path = root / "docs" / f"{relative}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class _RecordingProbe:
    """Probe that answers from a fixed set and remembers what it was asked."""

    def __init__(self, present: set[str] | None = None):
        self.present = present or set()
        self.seen: list[str] = []

    def __call__(self, path: str) -> bool:
        self.seen.append(path)
        return path in self.present


ENTRIES = [
    ("[TDD]-alpha", "tdd/[TDD]-alpha", "src/alpha.py"),
    ("[TDD]-beta", "tdd/[TDD]-beta", "src/beta.py"),
]


# ── pure function ────────────────────────────────────────────────────────────

def test_every_missing_target_becomes_a_violation():
    out = validate_target_file_existence(ENTRIES, exists=lambda p: False)
    assert [v.code for v in out] == [TDD_TARGET_FILE_MISSING] * 2
    assert [v.chunk_id for v in out] == ["[TDD]-alpha", "[TDD]-beta"]
    assert [v.file for v in out] == ["tdd/[TDD]-alpha", "tdd/[TDD]-beta"]
    assert "src/alpha.py" in out[0].message
    assert "src/beta.py" in out[1].message


def test_no_violation_when_every_target_exists():
    assert validate_target_file_existence(ENTRIES, exists=lambda p: True) == []


def test_only_the_missing_one_is_reported():
    probe = _RecordingProbe(present={"src/alpha.py"})
    out = validate_target_file_existence(ENTRIES, exists=probe)
    assert len(out) == 1
    assert out[0].chunk_id == "[TDD]-beta"


@pytest.mark.parametrize("target", [None, ""])
def test_entries_without_target_file_are_skipped(target):
    """That gap is TDD_TARGET_FILE_REQUIRED's concern — not reported twice."""
    probe = _RecordingProbe()
    out = validate_target_file_existence([("[TDD]-x", "tdd/[TDD]-x", target)], exists=probe)
    assert out == []
    assert probe.seen == []  # never even probed


@pytest.mark.parametrize("enforcement", ["warn", "block"])
def test_enforcement_is_passed_through_verbatim(enforcement):
    out = validate_target_file_existence(
        ENTRIES, exists=lambda p: False, enforcement=enforcement
    )
    assert {v.enforcement for v in out} == {enforcement}


def test_enforcement_defaults_to_none():
    out = validate_target_file_existence(ENTRIES, exists=lambda p: False)
    assert {v.enforcement for v in out} == {None}


def test_probe_exception_propagates_rather_than_reading_as_present():
    def boom(path: str) -> bool:
        raise OSError("probe unavailable")

    with pytest.raises(OSError):
        validate_target_file_existence(ENTRIES, exists=boom)


def test_probe_is_the_only_external_dependency():
    """No disk IO of its own: paths are probed exactly as declared."""
    probe = _RecordingProbe()
    validate_target_file_existence(
        [("[TDD]-a", "tdd/[TDD]-a", "./Src\\Mixed.PY")], exists=probe
    )
    assert probe.seen == ["./Src\\Mixed.PY"]  # verbatim — not normalized/casefolded


# ── validate-new-model report field ──────────────────────────────────────────

def _project(root: Path, target_file: str) -> None:
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    _write(root, "prd/[PRD]-app", "<!-- @id:[PRD]-app -->\n## App\n")
    _write(root, "fsd/[FSD]-app", "<!-- @id:[FSD]-app -->\n## App design\n")
    _write(
        root, "tdd/[TDD]-app",
        f"<!-- @id:[TDD]-app -->\n## App TDD\n\n```yaml\ntarget_file: {target_file}\n```\n",
    )
    NewModelManager(root).indexes.rebuild_baseline()
    sync_specgraph(root)


def test_cli_reports_missing_target_file(tmp_path: Path, monkeypatch):
    root = tmp_path / "project-docs"
    _project(root, "src/gone.py")
    monkeypatch.chdir(tmp_path)

    data = _payload(CliRunner().invoke(main, ["specgraph", "validate-new-model"]))["data"]

    assert any(
        v["code"] == TDD_TARGET_FILE_MISSING and v["chunk_id"] == "[TDD]-app"
        for v in data["target_file_missing"]
    )


def test_cli_field_is_report_only(tmp_path: Path, monkeypatch):
    root = tmp_path / "project-docs"
    _project(root, "src/gone.py")
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["specgraph", "validate-new-model"])
    data = _payload(result)["data"]

    assert result.exit_code == 0
    assert data["passed"] is True
    assert all(v["code"] != TDD_TARGET_FILE_MISSING for v in data["violations"])


def test_cli_field_empty_when_target_exists(tmp_path: Path, monkeypatch):
    root = tmp_path / "project-docs"
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "here.py").write_text("", encoding="utf-8")
    _project(root, "src/here.py")
    monkeypatch.chdir(tmp_path)

    data = _payload(CliRunner().invoke(main, ["specgraph", "validate-new-model"]))["data"]
    assert data["target_file_missing"] == []
