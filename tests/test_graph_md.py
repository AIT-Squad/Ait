"""tests/test_graph_md.py — v2.56 Mermaid spec-graph generation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ait.cli import main
from ait.graph_md import _node_id, generate_graph_md, write_graph_md
from ait.specgraph import SpecGraph, specgraph_path
from ait.version_manager import VersionManager
from ait.new_model_manager import NewModelManager
from ait.io_utils import atomic_write_text
import yaml


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    return root


# ── unit: node id escaping ─────────────────────────────────────────────────


def test_node_id_escapes_special_chars():
    assert "[" not in _node_id("[PRD]-ait")
    assert "]" not in _node_id("[PRD]-ait")
    assert ":" not in _node_id("[FSD]-ait:version")
    # produces a valid identifier (no mermaid-special chars)
    assert _node_id("[FSD]-ait:version") == "FSD_ait__version"


def test_node_id_plain_name():
    assert _node_id("PRD_ait") == "PRD_ait"


# ── unit: empty specgraph ──────────────────────────────────────────────────


def test_generate_graph_md_empty_specgraph(tmp_path: Path):
    root = _project(tmp_path)
    # no specgraph.yaml → empty graph
    content = generate_graph_md(root)
    assert "graph TD" in content
    assert "```mermaid" in content


# ── integration: baseline graph with real pipeline ─────────────────────────


def _build_mini_project(root: Path) -> None:
    """Create a minimal PRD→FSD→TDD project and merge it so baseline has data."""
    import subprocess
    vm = VersionManager(root)
    mgr = NewModelManager(root)
    vm.create("v0.1")
    mgr.create_prd("v0.1", "[PRD]-demo", "<!-- @id:[PRD]-demo -->\n## Demo\n")
    mgr.confirm_prd_layer("v0.1")
    mgr.create_fsd(
        "v0.1", "[FSD]-demo",
        "<!-- @id:[FSD]-demo -->\n## F\n\n<!-- @id:[FSD]-demo:core -->\n## core\n",
        parent_chunk_id="[PRD]-demo",
    )
    mgr.confirm_fsd_layer("v0.1")
    mgr.create_tdd(
        "v0.1", "[TDD]-demo-core",
        "<!-- @id:[TDD]-demo-core -->\n## T\n```yaml\ntarget_file: src/core.py\n```\n",
        parent_chunk_id="[FSD]-demo:core",
    )
    mgr.confirm_tdd_layer("v0.1")
    # git init so merge can commit
    subprocess.run(["git", "init", "-q"], cwd=root, capture_output=True)
    subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=root, capture_output=True)
    subprocess.run(["git", "config", "user.name", "x"], cwd=root, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, capture_output=True)
    vm.confirm("v0.1", allow_dirty_git=True)


def test_generate_graph_md_baseline_has_subgraphs(tmp_path: Path):
    root = _project(tmp_path)
    _build_mini_project(root)
    content = generate_graph_md(root)
    assert "subgraph" in content
    assert "[PRD]-demo" in content
    assert "[FSD]-demo" in content
    assert "[TDD]-demo-core" in content
    # edges
    assert "derives" in content or "decomposes" in content or "details" in content


def test_write_graph_md_creates_file_at_correct_path(tmp_path: Path):
    root = _project(tmp_path)
    _build_mini_project(root)
    result = write_graph_md(root)
    out = root / "docs" / "graph.md"
    assert out.exists(), f"baseline graph.md not created at {out}"
    assert result["path"] == "docs/graph.md"
    assert result["nodes"] > 0
    assert result["edges"] >= 0


def test_write_graph_md_version_path(tmp_path: Path, monkeypatch):
    """version graph goes to versions/<v>/graph.md."""
    root = _project(tmp_path)
    vm = VersionManager(root)
    mgr = NewModelManager(root)
    vm.create("v0.1")
    mgr.create_prd("v0.1", "[PRD]-x", "<!-- @id:[PRD]-x -->\n## X\n")
    monkeypatch.setattr(VersionManager, "_git_commit", lambda self, m: "cafe123")
    mgr.confirm_prd_layer("v0.1")
    result = write_graph_md(root, "v0.1")
    out = root / "versions" / "v0.1" / "graph.md"
    assert out.exists(), f"version graph.md not at {out}"
    assert result["path"] == "versions/v0.1/graph.md"


def test_write_graph_md_idempotent(tmp_path: Path):
    root = _project(tmp_path)
    _build_mini_project(root)
    write_graph_md(root)
    write_graph_md(root)  # second call overwrites, no error
    out = root / "docs" / "graph.md"
    assert out.exists()


# ── CLI integration ────────────────────────────────────────────────────────


def test_cli_graph_md_baseline(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _build_mini_project(root)
    runner = CliRunner()
    r = runner.invoke(main, ["specgraph", "graph-md"], catch_exceptions=False)
    p = json.loads(r.output.strip().splitlines()[-1])
    assert p["ok"] is True
    assert p["data"]["path"] == "docs/graph.md"
    assert (root / "docs" / "graph.md").exists()
