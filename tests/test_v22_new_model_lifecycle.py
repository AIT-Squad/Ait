"""v2.22→v2.51 new-model lifecycle over the P7 strict layered pipeline."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from ait.cli import main
from ait.new_model_manager import NewModelManager
from ait.validator import ValidationError
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


def test_new_model_create_requires_existing_version_p7(tmp_path: Path):
    """P7: no auto-create anywhere — create_prd on a missing version raises
    VERSION_NOT_FOUND; after an explicit `version create` it succeeds."""
    root = _new_project(tmp_path)
    vm = VersionManager(root)
    mgr = NewModelManager(root)

    assert not vm.version_meta_path("v1.0").exists()
    with pytest.raises(ValidationError) as exc:
        mgr.create_prd("v1.0", "[PRD]-sys", "<!-- @id:[PRD]-sys -->\n## Sys\n")
    assert exc.value.issues[0].code == "VERSION_NOT_FOUND"
    assert not vm.version_meta_path("v1.0").exists(), "拒绝须零落盘"

    vm.create("v1.0")
    mgr.create_prd("v1.0", "[PRD]-sys", "<!-- @id:[PRD]-sys -->\n## Sys\n")
    assert vm.version_meta_path("v1.0").exists()


def test_new_model_full_lifecycle(tmp_path: Path, monkeypatch):
    """Full P7 layered flow: version create -> prd -> confirm -> fsd -> confirm
    -> tdd -> confirm -> version commit -> vm.confirm (merge) -> baseline codegen."""
    root = _new_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    vm = VersionManager(root)
    mgr = NewModelManager(root)

    vm.create("v1.0")
    mgr.create_prd("v1.0", "[PRD]-sys", "<!-- @id:[PRD]-sys -->\n## Sys\n")
    mgr.confirm_prd_layer("v1.0")
    mgr.create_fsd(
        "v1.0", "[FSD]-sys",
        "<!-- @id:[FSD]-sys -->\n## Sys FSD\n\n<!-- @id:[FSD]-sys:core -->\n## Core\n",
    )
    mgr.add_edge("v1.0", "[PRD]-sys", "[FSD]-sys", "derives")
    mgr.confirm_fsd_layer("v1.0")
    mgr.create_tdd(
        "v1.0", "[TDD]-core",
        "<!-- @id:[TDD]-core -->\n## Core TDD\n\n```yaml\ntarget_file: app/core.py\n```\n",
        parent_chunk_id="[FSD]-sys:core",
    )
    mgr.confirm_tdd_layer("v1.0")

    # P7: the three layer-confirms already staged+committed every chunk —
    # `version commit` has nothing left (COMMIT_EMPTY), so assert state directly.
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

    # no active version (v1.0 merged) -> codegen resolves from baseline (not gated).
    cg = runner.invoke(main, ["codegen", "prepare", "[TDD]-core"], catch_exceptions=False)
    assert cg.exit_code == 0, cg.output
    data = json.loads(cg.output.strip().splitlines()[-1])["data"]
    assert data["target_file"] == "app/core.py"
    assert data["version"] == "baseline"


def test_codegen_climbs_to_domain_level_depends_on(tmp_path: Path):
    """v2.17: codegen surfaces depends_on declared at the domain-split level,
    not just the TDD's immediate parent module split. (P7: layered confirms.)"""
    root = _new_project(tmp_path)
    vm = VersionManager(root)
    mgr = NewModelManager(root)
    vm.create("v1.0")
    mgr.create_prd("v1.0", "[PRD]-sys", "<!-- @id:[PRD]-sys -->\n## Sys\n")
    mgr.confirm_prd_layer("v1.0")
    mgr.create_fsd(
        "v1.0", "[FSD]-app",
        "<!-- @id:[FSD]-app -->\n## App\n\n"
        "<!-- @id:[FSD]-app:svc -->\n## svc\n\n"
        "<!-- @id:[FSD]-app:store -->\n## store\n",
    )
    mgr.create_fsd(
        "v1.0", "[FSD]-app-svc",
        "<!-- @id:[FSD]-app-svc -->\n## svc FSD\n\n<!-- @id:[FSD]-app-svc:core -->\n## core\n",
    )
    mgr.create_fsd("v1.0", "[FSD]-app-store", "<!-- @id:[FSD]-app-store -->\n## store FSD\n")
    mgr.add_edge("v1.0", "[PRD]-sys", "[FSD]-app", "derives")
    mgr.add_edge("v1.0", "[FSD]-app:svc", "[FSD]-app-svc", "decomposes")
    mgr.add_edge("v1.0", "[FSD]-app:store", "[FSD]-app-store", "decomposes")
    # domain-level dependency: svc domain depends on store domain
    mgr.add_edge("v1.0", "[FSD]-app:svc", "[FSD]-app:store", "depends_on")
    mgr.confirm_fsd_layer("v1.0")
    mgr.create_tdd(
        "v1.0", "[TDD]-core",
        "<!-- @id:[TDD]-core -->\n## core TDD\n\n```yaml\ntarget_file: app/core.py\n```\n",
        parent_chunk_id="[FSD]-app-svc:core",
    )
    mgr.confirm_tdd_layer("v1.0")

    bundle = mgr.prepare_codegen("v1.0", "[TDD]-core")
    dep_ids = {d["id"] for d in bundle.dependencies}
    # codegen must climb from [TDD]-core's module split up to the [FSD]-app:svc
    # domain split and surface its depends_on target.
    assert "[FSD]-app:store" in dep_ids, dep_ids
