"""v2.2: new-model version lifecycle — meta auto-create (ensure), `version
commit`, and codegen baseline fallback."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from ait.cli import main
from ait.new_model_manager import NewModelManager
from ait.version_manager import VersionManager


def _git(root: Path, *args: str) -> None:
    try:
        subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        pytest.skip("git is not available")
    except subprocess.CalledProcessError as exc:
        pytest.fail(f"git {' '.join(args)} failed: {exc.stderr}")


def _new_project(tmp_path: Path) -> Path:
    root = tmp_path / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    return root


def test_new_model_ensure_creates_version_meta(tmp_path: Path):
    """Gap A: new-model create auto-creates the version meta (no pre-create)."""
    root = _new_project(tmp_path)
    vm = VersionManager(root)
    mgr = NewModelManager(root)

    assert not vm.version_meta_path("v1.0").exists()
    mgr.create_prd("v1.0", "[PRD]-sys", "<!-- @id:[PRD]-sys -->\n## Sys\n")
    assert vm.version_meta_path("v1.0").exists()
    # idempotent: second create on same version must not raise "already exists".
    mgr.create_fsd("v1.0", "[FSD]-sys", "<!-- @id:[FSD]-sys -->\n## Sys FSD\n")


def test_new_model_full_lifecycle(tmp_path: Path, monkeypatch):
    """Gaps A+B+C: create -> version commit -> confirm -> codegen on baseline."""
    root = _new_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    vm = VersionManager(root)
    mgr = NewModelManager(root)

    mgr.create_prd("v1.0", "[PRD]-sys", "<!-- @id:[PRD]-sys -->\n## Sys\n")
    mgr.create_fsd(
        "v1.0", "[FSD]-sys",
        "<!-- @id:[FSD]-sys -->\n## Sys FSD\n\n<!-- @id:[FSD]-sys:core -->\n## Core\n",
    )
    mgr.create_tdd(
        "v1.0", "[TDD]-core",
        "<!-- @id:[TDD]-core -->\n## Core TDD\n\n```yaml\ntarget_file: app/core.py\n```\n",
    )
    mgr.add_edge("v1.0", "[PRD]-sys", "[FSD]-sys", "decomposes")
    mgr.add_edge("v1.0", "[FSD]-sys:core", "[TDD]-core", "details")

    # Gap B: `version commit` locks all working chunks.
    res = runner.invoke(main, ["version", "commit", "v1.0", "-m", "lock"], catch_exceptions=False)
    assert res.exit_code == 0, res.output
    idx = vm.indexes.load_version_index("v1.0")
    assert {c.state for c in idx.chunks} == {"committed"}

    # confirm merges the taskless new-model version into baseline.
    _git(root, "init")
    _git(root, "config", "user.email", "a@b.c")
    _git(root, "config", "user.name", "x")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "base")
    result = vm.confirm("v1.0")
    assert result["commit"]
    assert (root / "docs" / "fsd" / "[FSD]-sys.md").exists()
    assert (root / "docs" / "tdd" / "[TDD]-core.md").exists()

    # Gap C: no active version (v1.0 merged) -> codegen resolves from baseline.
    cg = runner.invoke(main, ["codegen", "prepare", "[TDD]-core"], catch_exceptions=False)
    assert cg.exit_code == 0, cg.output
    data = json.loads(cg.output.strip().splitlines()[-1])["data"]
    assert data["target_file"] == "app/core.py"
    assert data["version"] == "baseline"
