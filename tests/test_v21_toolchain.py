"""v2.1 toolchain tests — new-model PRD command, init scaffold, taskless
confirm, and target_file uniqueness."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from ait.cli import main
from ait.init_manager import InitManager
from ait.new_model_manager import NewModelManager
from ait.new_model_validator import (
    validate_prd_fsd_tdd_graph,
    validate_target_file_uniqueness,
)
from ait.specgraph import combined_specgraph, load_specgraph
from ait.version_manager import VersionManager


def _payload(result):
    return json.loads(result.output.strip().splitlines()[-1])


def _new_project(tmp_path: Path) -> Path:
    root = tmp_path / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    return root


# ── Work 1: new-model PRD command (ait prdv2) ───────────────────────────────


def test_prdv2_create_and_link(tmp_path: Path, monkeypatch):
    root = _new_project(tmp_path)
    VersionManager(root).create("v9.0")
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    prd = runner.invoke(
        main,
        [
            "prdv2", "create", "[PRD]-shop",
            "--version", "v9.0",
            "--content", "<!-- @id:[PRD]-shop -->\n## Shop PRD\n",
        ],
        catch_exceptions=False,
    )
    assert prd.exit_code == 0, prd.output
    assert _payload(prd)["data"]["chunks"] == ["[PRD]-shop"]

    runner.invoke(
        main,
        [
            "fsd", "create", "[FSD]-shop",
            "--version", "v9.0",
            "--content", "<!-- @id:[FSD]-shop -->\n## Shop FSD\n",
        ],
        catch_exceptions=False,
    )
    link = runner.invoke(
        main,
        ["prdv2", "link", "[PRD]-shop", "[FSD]-shop", "--rel", "decomposes", "--version", "v9.0"],
        catch_exceptions=False,
    )
    assert link.exit_code == 0, link.output
    assert _payload(link)["data"]["rel"] == "decomposes"

    # create_prd must NOT require target_file (unlike create_tdd).
    assert NewModelManager(root).create_prd is not None


# ── Work 2: init --new-model scaffold ───────────────────────────────────────


def test_init_new_model_bootstrap(tmp_path: Path):
    root = _new_project(tmp_path)
    result = InitManager(root).run(new_model=True, project_name="demo")

    assert (root / "docs" / "prd" / "[PRD]-demo.md").exists()
    assert (root / "docs" / "fsd" / "[FSD]-demo.md").exists()
    assert (root / "docs" / "tdd" / "README.md").exists()
    assert result.chunks == 2

    graph = load_specgraph(root, "baseline")
    triples = {
        (graph.specs[e.src].chunk_id, e.rel, graph.specs[e.dst].chunk_id)
        for e in graph.edges
    }
    assert ("[PRD]-demo", "decomposes", "[FSD]-demo") in triples
    assert validate_prd_fsd_tdd_graph(graph) == []


def test_init_new_model_is_idempotent(tmp_path: Path):
    root = _new_project(tmp_path)
    InitManager(root).run(new_model=True, project_name="demo")
    (root / "docs" / "prd" / "[PRD]-demo.md").write_text(
        "<!-- @id:[PRD]-demo -->\n## Custom\n\nuser edits\n", encoding="utf-8"
    )
    InitManager(root).run(new_model=True, project_name="demo")
    # user content preserved (not overwritten).
    assert "user edits" in (root / "docs" / "prd" / "[PRD]-demo.md").read_text(encoding="utf-8")


# ── Work 4: target_file uniqueness ──────────────────────────────────────────


def test_target_file_uniqueness_pure():
    dup = validate_target_file_uniqueness(
        [
            ("[TDD]-a", "tdd/[TDD]-a", "app/x.py"),
            ("[TDD]-b", "tdd/[TDD]-b", "app/x.py"),
            ("[TDD]-c", "tdd/[TDD]-c", "app/y.py"),
        ]
    )
    assert [v.code for v in dup] == ["DUPLICATE_TARGET_FILE"]
    assert "[TDD]-a" in dup[0].message and "[TDD]-b" in dup[0].message

    assert validate_target_file_uniqueness(
        [
            ("[TDD]-a", "tdd/[TDD]-a", "app/x.py"),
            ("[TDD]-b", "tdd/[TDD]-b", "app/y.py"),
        ]
    ) == []


def test_target_file_uniqueness_via_collect(tmp_path: Path):
    root = _new_project(tmp_path)
    vm = VersionManager(root)
    vm.create("v9.0")
    mgr = NewModelManager(root)
    mgr.create_tdd(
        "v9.0", "[TDD]-alpha",
        "<!-- @id:[TDD]-alpha -->\n## Alpha\n\n```yaml\ntarget_file: app/shared.py\n```\n",
    )
    mgr.create_tdd(
        "v9.0", "[TDD]-beta",
        "<!-- @id:[TDD]-beta -->\n## Beta\n\n```yaml\ntarget_file: app/shared.py\n```\n",
    )
    graph = combined_specgraph(root, "v9.0")
    violations = validate_target_file_uniqueness(mgr.collect_tdd_target_files(graph))
    assert [v.code for v in violations] == ["DUPLICATE_TARGET_FILE"]


# ── Work 3: taskless version confirm ────────────────────────────────────────


def _git(root: Path, *args: str) -> None:
    try:
        subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    except FileNotFoundError:
        pytest.skip("git is not available")
    except subprocess.CalledProcessError as exc:
        pytest.fail(f"git {' '.join(args)} failed: {exc.stderr}")


def test_taskless_new_model_confirm(tmp_path: Path):
    root = tmp_path
    for d in ["docs", ".meta/versions", ".meta/changes", "versions"]:
        (root / d).mkdir(parents=True)
    vm = VersionManager(root)
    mgr = NewModelManager(root)
    vm.create("v1.0")

    mgr.create_prd("v1.0", "[PRD]-sys", "<!-- @id:[PRD]-sys -->\n## Sys PRD\n")
    mgr.create_fsd(
        "v1.0", "[FSD]-app",
        "<!-- @id:[FSD]-app -->\n## App FSD\n\n"
        "<!-- @id:[FSD]-app:svc -->\n## Service\n\n"
        "<!-- @id:[FSD]-app:store -->\n## Store\n",
    )
    mgr.create_tdd(
        "v1.0", "[TDD]-svc",
        "<!-- @id:[TDD]-svc -->\n## Service TDD\n\n```yaml\ntarget_file: app/svc.py\n```\n",
    )
    mgr.create_tdd(
        "v1.0", "[TDD]-store",
        "<!-- @id:[TDD]-store -->\n## Store TDD\n\n```yaml\ntarget_file: app/store.py\n```\n",
    )
    mgr.add_edge("v1.0", "[PRD]-sys", "[FSD]-app", "decomposes")
    mgr.add_edge("v1.0", "[FSD]-app:svc", "[TDD]-svc", "details")
    mgr.add_edge("v1.0", "[FSD]-app:store", "[TDD]-store", "details")
    mgr.add_edge("v1.0", "[FSD]-app:svc", "[FSD]-app:store", "depends_on")

    vm.stage("v1.0")
    vm.commit("v1.0", "commit new-model docs")

    _git(root, "init")
    _git(root, "config", "user.email", "ait@example.com")
    _git(root, "config", "user.name", "AIT Tests")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "before confirm")

    # Zero tasks must not block confirm.
    result = vm.confirm("v1.0")
    assert result["commit"]

    assert (root / "docs" / "fsd" / "[FSD]-app.md").exists()
    assert (root / "docs" / "tdd" / "[TDD]-svc.md").exists()
    assert not (root / "docs" / "prd" / "global.md").exists()

    baseline = load_specgraph(root, "baseline")
    rels = {
        (baseline.specs[e.src].chunk_id, e.rel, baseline.specs[e.dst].chunk_id)
        for e in baseline.edges
    }
    assert ("[PRD]-sys", "decomposes", "[FSD]-app") in rels
    assert ("[FSD]-app:svc", "details", "[TDD]-svc") in rels
    assert ("[FSD]-app:svc", "depends_on", "[FSD]-app:store") in rels
