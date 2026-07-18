"""tests/test_graph_md.py — v2.57 HTML spec-tree generation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ait.cli import main
from ait.graph_md import generate_graph_html, write_graph_html
from ait.specgraph import SpecGraph, specgraph_path
from ait.version_manager import VersionManager
from ait.new_model_manager import NewModelManager
import subprocess


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    return root


# ── integration helpers ────────────────────────────────────────────────────


def _build_mini_project(root: Path) -> None:
    """Create a minimal PRD→FSD→TDD project and merge it so baseline has data."""
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
    subprocess.run(["git", "init", "-q"], cwd=root, capture_output=True)
    subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=root, capture_output=True)
    subprocess.run(["git", "config", "user.name", "x"], cwd=root, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, capture_output=True)
    vm.confirm("v0.1", allow_dirty_git=True)


# ── unit: empty specgraph ──────────────────────────────────────────────────


def test_generate_graph_html_empty_specgraph(tmp_path: Path):
    root = _project(tmp_path)
    content = generate_graph_html(root)
    assert "<!DOCTYPE html>" in content
    assert "(empty)" in content


# ── unit: HTML tree structure ──────────────────────────────────────────────


def test_generate_graph_html_has_tree_nodes(tmp_path: Path):
    root = _project(tmp_path)
    _build_mini_project(root)
    content = generate_graph_html(root)
    assert "<!DOCTYPE html>" in content
    assert "[PRD]-demo" in content
    assert "[FSD]-demo" in content
    assert "[TDD]-demo-core" in content


def test_generate_graph_html_tree_relations(tmp_path: Path):
    root = _project(tmp_path)
    _build_mini_project(root)
    content = generate_graph_html(root)
    # tree edges appear as rel-tag spans, not Mermaid arrows
    assert "mermaid" not in content
    assert "-->" not in content
    # derives/decomposes/details appear as inline relation labels
    assert any(r in content for r in ("derives", "decomposes", "details"))


def test_generate_graph_html_depends_on_as_chips(tmp_path: Path):
    """depends_on edges must appear as dep-chip spans, not tree edges."""
    root = _project(tmp_path)
    _build_mini_project(root)
    content = generate_graph_html(root)
    # no depends_on tree arrows; chips only if any deps exist
    assert "dep-chip" in content or "depends_on" not in content


# ── integration: file paths ───────────────────────────────────────────────


def test_write_graph_html_baseline_path(tmp_path: Path):
    root = _project(tmp_path)
    _build_mini_project(root)
    result = write_graph_html(root)
    out = root / "docs" / "graph.html"
    assert out.exists(), f"baseline graph.html not created at {out}"
    assert result["path"] == "docs/graph.html"
    assert result["nodes"] > 0


def test_write_graph_html_version_path(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    vm = VersionManager(root)
    mgr = NewModelManager(root)
    vm.create("v0.1")
    mgr.create_prd("v0.1", "[PRD]-x", "<!-- @id:[PRD]-x -->\n## X\n")
    monkeypatch.setattr(VersionManager, "_git_commit", lambda self, m: "cafe123")
    mgr.confirm_prd_layer("v0.1")
    result = write_graph_html(root, "v0.1")
    out = root / "versions" / "v0.1" / "graph.html"
    assert out.exists(), f"version graph.html not at {out}"
    assert result["path"] == "versions/v0.1/graph.html"


def test_write_graph_html_idempotent(tmp_path: Path):
    root = _project(tmp_path)
    _build_mini_project(root)
    write_graph_html(root)
    write_graph_html(root)  # second call overwrites cleanly
    assert (root / "docs" / "graph.html").exists()


# ── CLI integration ───────────────────────────────────────────────────────


def test_cli_graph_html_baseline(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _build_mini_project(root)
    runner = CliRunner()
    r = runner.invoke(main, ["specgraph", "graph-html"], catch_exceptions=False)
    p = json.loads(r.output.strip().splitlines()[-1])
    assert p["ok"] is True
    assert p["data"]["path"] == "docs/graph.html"
    assert (root / "docs" / "graph.html").exists()
