"""[TDD]-cli: `ait --version` reflects the project's current document version.

Covers the v2.86 requirement "cli_version_reflects_docs" — the eager
`--version` option must print the numeric-max recorded `vMAJOR.MINOR` label
(comparing (major, minor) as integers, not lexicographically — "v2.10" must
not be treated as smaller than "v2.9"), and fall back to "unversioned" with
exit code 0 when there is no project root or no recorded version.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from click.testing import CliRunner

from ait.cli import main
from ait.schemas import VersionMeta
from ait.version_manager import VersionManager
from ait.yaml_io import save_model


def _project_root(tmp_path: Path) -> Path:
    root = tmp_path / "project-docs"
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    return root


def _write_version_meta(root: Path, version: str) -> None:
    meta = VersionMeta(version=version, created_at=datetime.now(timezone.utc))
    save_model(root / ".meta" / "versions" / f"{version}.yaml", meta)


def test_latest_version_label_compares_numerically(tmp_path: Path):
    root = _project_root(tmp_path)
    for v in ("v2.2", "v2.9", "v2.10"):
        _write_version_meta(root, v)
    assert VersionManager(root).latest_version_label() == "v2.10"


def test_latest_version_label_none_when_no_versions(tmp_path: Path):
    root = _project_root(tmp_path)
    assert VersionManager(root).latest_version_label() is None


def test_cli_version_prints_numeric_max_label(tmp_path: Path, monkeypatch):
    root = _project_root(tmp_path)
    for v in ("v2.9", "v2.10"):
        _write_version_meta(root, v)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["--version"], catch_exceptions=False)
    assert result.exit_code == 0
    assert result.output.strip() == "ait, version v2.10"


def test_cli_version_unversioned_when_no_versions_recorded(tmp_path: Path, monkeypatch):
    _project_root(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["--version"], catch_exceptions=False)
    assert result.exit_code == 0
    assert result.output.strip() == "ait, version unversioned"


def test_cli_version_unversioned_outside_project_root(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["--version"], catch_exceptions=False)
    assert result.exit_code == 0
    assert result.output.strip() == "ait, version unversioned"


def test_cli_help_contract_unaffected(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(main, ["--help"], catch_exceptions=False)
    assert result.exit_code == 0
    assert "--version" in result.output
