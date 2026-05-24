"""Tests for project root resolution (PRD prd-project-docs-only-*).

Covers:
- resolve_project_root() unit tests for all 3 error codes + happy path
- non-goal assertions (AIT_ROOT env var has no effect)
- end-to-end CLI JSON error contract
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ait.cli import main
from ait.root import (
    DOCS_DIR_NAME,
    CwdInsideProjectDocs,
    NotAtProjectRoot,
    ProjectDocsMalformed,
    ProjectRoot,
    resolve_project_root,
)


def _make_valid_project(parent: Path) -> Path:
    """Create a minimal valid project-docs/ layout under parent. Returns project-docs/ path."""
    docs_root = parent / DOCS_DIR_NAME
    (docs_root / "docs").mkdir(parents=True)
    (docs_root / ".meta").mkdir()
    (docs_root / "versions").mkdir()
    return docs_root


# ── resolve_project_root() unit tests ──────────────────────────────────────


def test_valid_root_returns_resolved(tmp_path: Path, monkeypatch) -> None:
    docs_root = _make_valid_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = resolve_project_root()

    assert isinstance(result, ProjectRoot)
    assert result.root == docs_root.resolve()
    assert result.docs == (docs_root / "docs").resolve()
    assert result.meta == (docs_root / ".meta").resolve()
    assert result.cwd == tmp_path.resolve()


def test_missing_project_docs_raises_not_at_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(NotAtProjectRoot) as exc_info:
        resolve_project_root()

    assert exc_info.value.code == "NOT_AT_PROJECT_ROOT"
    assert exc_info.value.data["cwd"] == str(tmp_path.resolve())
    assert exc_info.value.data["expected_path"] == str((tmp_path / DOCS_DIR_NAME).resolve())


def test_missing_docs_subdir_raises_malformed(tmp_path: Path, monkeypatch) -> None:
    docs_root = tmp_path / DOCS_DIR_NAME
    docs_root.mkdir()
    (docs_root / ".meta").mkdir()  # only .meta/, no docs/
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ProjectDocsMalformed) as exc_info:
        resolve_project_root()

    assert exc_info.value.code == "PROJECT_DOCS_MALFORMED"
    assert "docs" in exc_info.value.data["missing"]
    assert ".meta" not in exc_info.value.data["missing"]


def test_missing_meta_subdir_raises_malformed(tmp_path: Path, monkeypatch) -> None:
    docs_root = tmp_path / DOCS_DIR_NAME
    docs_root.mkdir()
    (docs_root / "docs").mkdir()  # only docs/, no .meta/
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ProjectDocsMalformed) as exc_info:
        resolve_project_root()

    assert exc_info.value.code == "PROJECT_DOCS_MALFORMED"
    assert ".meta" in exc_info.value.data["missing"]
    assert "docs" not in exc_info.value.data["missing"]


def test_cwd_is_project_docs_raises_inside(tmp_path: Path, monkeypatch) -> None:
    docs_root = _make_valid_project(tmp_path)
    monkeypatch.chdir(docs_root)

    with pytest.raises(CwdInsideProjectDocs) as exc_info:
        resolve_project_root()

    assert exc_info.value.code == "CWD_INSIDE_PROJECT_DOCS"


def test_cwd_descendant_of_project_docs_raises_inside(tmp_path: Path, monkeypatch) -> None:
    docs_root = _make_valid_project(tmp_path)
    monkeypatch.chdir(docs_root / "docs")

    with pytest.raises(CwdInsideProjectDocs) as exc_info:
        resolve_project_root()

    assert exc_info.value.code == "CWD_INSIDE_PROJECT_DOCS"


def test_ait_root_env_has_no_effect(tmp_path: Path, monkeypatch) -> None:
    """non-goal R4: AIT_ROOT must NOT be honored as an override."""
    _make_valid_project(tmp_path)
    monkeypatch.setenv("AIT_ROOT", str(tmp_path / "elsewhere"))
    monkeypatch.chdir(tmp_path)

    result = resolve_project_root()

    # Resolution must come from CWD/project-docs, not from AIT_ROOT.
    assert result.root == (tmp_path / DOCS_DIR_NAME).resolve()


# ── End-to-end CLI integration ─────────────────────────────────────────────


def test_cli_emits_json_error_on_invalid_root(tmp_path: Path, monkeypatch) -> None:
    """From a dir without project-docs/, CLI subcommand exits 1 with JSON error."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(main, ["reindex"], catch_exceptions=False)

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["ok"] is False
    assert payload["code"] == "NOT_AT_PROJECT_ROOT"
