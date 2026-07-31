"""tests/test_graph_md.py — v2.63 chunk-level graph-html with subgraph boxes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ait.cli import main
from ait.graph_md import (
    _build_chunk_graph,
    _layout,
    generate_graph_html,
    write_graph_html,
)
from ait.specgraph import Spec, SpecGraph, make_uri, specgraph_path
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
    mgr.create_prd(
        "v0.1", "[PRD]-demo", "<!-- @id:[PRD]-demo -->\n## Demo\n", skip_context=True
    )
    mgr.confirm_prd_layer("v0.1")
    mgr.create_fsd(
        "v0.1", "[FSD]-demo",
        "<!-- @id:[FSD]-demo -->\n## F\n\n<!-- @id:[FSD]-demo:core -->\n## core\n",
        parent_chunk_id="[PRD]-demo",
        skip_context=True,
    )
    mgr.confirm_fsd_layer("v0.1")
    mgr.create_tdd(
        "v0.1", "[TDD]-demo-core",
        "<!-- @id:[TDD]-demo-core -->\n## T\n```yaml\ntarget_file: src/core.py\n```\n",
        parent_chunk_id="[FSD]-demo:core",
        skip_context=True,
    )
    mgr.confirm_tdd_layer("v0.1")
    subprocess.run(["git", "init", "-q"], cwd=root, capture_output=True)
    subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=root, capture_output=True)
    subprocess.run(["git", "config", "user.name", "x"], cwd=root, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, capture_output=True)
    vm.confirm("v0.1", allow_dirty_git=True)


def _spec(chunk_id: str, file: str, type_: str = "fsd") -> Spec:
    return Spec(
        uri=make_uri(chunk_id, "baseline", file),
        title=chunk_id,
        type=type_,
        version="baseline",
        chunk_id=chunk_id,
        file=file,
        metadata={},
    )


def _save_baseline(root: Path, graph: SpecGraph) -> None:
    path = specgraph_path(root, "baseline")
    path.parent.mkdir(parents=True, exist_ok=True)
    graph.save(path)


# ── unit: empty specgraph ──────────────────────────────────────────────────


def test_generate_graph_html_empty_specgraph(tmp_path: Path):
    root = _project(tmp_path)
    content = generate_graph_html(root)
    assert "<!DOCTYPE html>" in content
    assert "(empty)" in content


# ── unit: chunk nodes + tree structure ─────────────────────────────────────


def test_generate_graph_html_has_chunk_nodes(tmp_path: Path):
    root = _project(tmp_path)
    _build_mini_project(root)
    content = generate_graph_html(root)
    assert "<!DOCTYPE html>" in content
    assert "[PRD]-demo" in content
    assert "[FSD]-demo" in content
    assert "[TDD]-demo-core" in content
    # internal split renders as a tree row inside its file box
    assert "└ :core" in content


def test_generate_graph_html_tree_relation_labels(tmp_path: Path):
    """Tree edges carry visible rel labels (not just hover titles)."""
    root = _project(tmp_path)
    _build_mini_project(root)
    content = generate_graph_html(root)
    assert "mermaid" not in content
    assert "-->" not in content
    # PRD→FSD derives and FSD-split→TDD details are cross-file → labelled
    assert ">derives</text>" in content
    assert ">details</text>" in content
    # The visible annotation identifies the chunk endpoints, so the edge is
    # not mistaken for a whole-file relation.
    assert "[FSD]-demo:core → [TDD]-demo-core" in content


def test_layout_spreads_tdd_boxes_horizontally_without_overlap():
    """A wide FSD→TDD fan-out spreads left-to-right in a single row."""
    fsd = _spec("[FSD]-demo:core", "fsd/[FSD]-demo")
    tdds = [
        _spec(f"[TDD]-demo-{index}", f"tdd/[TDD]-demo-{index}", "tdd")
        for index in range(7)
    ]
    nodes = {spec.chunk_id: spec.file for spec in [fsd, *tdds]}
    edges = [(fsd.chunk_id, "details", tdd.chunk_id) for tdd in tdds]
    chunks, cross_tree, _, files, _ = _build_chunk_graph(nodes, edges)
    box_pos, _ = _layout(files, chunks, cross_tree)

    tdd_positions = [box_pos[tdd.file] for tdd in tdds]
    # 平铺:全部 TDD 同一行、x 互不相同
    assert len({y for _, y, _, _ in tdd_positions}) == 1
    assert len({x for x, _, _, _ in tdd_positions}) == len(tdds)
    # 父 FSD 居中于其子 TDD 上方
    fsd_x, fsd_y, _, _ = box_pos[fsd.file]
    tdd_xs = sorted(x for x, _, _, _ in tdd_positions)
    assert tdd_xs[0] <= fsd_x <= tdd_xs[-1]
    assert fsd_y < tdd_positions[0][1]


def test_tree_edge_label_positions_are_unique(tmp_path: Path):
    """多条关系并存时,任何两个关系文本都不得落在完全相同的坐标上。"""
    import re as _re

    root = _project(tmp_path)
    _build_mini_project(root)
    content = generate_graph_html(root)
    positions = _re.findall(
        r'class="edge-chunks" x="([\d.-]+)" y="([\d.-]+)"', content
    )
    assert positions
    assert len(positions) == len(set(positions)), "关系文本坐标存在重叠"


def test_generate_graph_html_file_boxes(tmp_path: Path):
    """Every file becomes one coloured subgraph box titled with the file name."""
    root = _project(tmp_path)
    _build_mini_project(root)
    content = generate_graph_html(root)
    assert 'class="fbox"' in content
    assert "fsd/[FSD]-demo" in content
    assert "prd/[PRD]-demo" in content
    assert "tdd/[TDD]-demo-core" in content


def test_generate_graph_html_zoomable_viewport(tmp_path: Path):
    """No fixed canvas: viewport-sized SVG + wheel-zoom / drag-pan / fit."""
    root = _project(tmp_path)
    _build_mini_project(root)
    content = generate_graph_html(root)
    assert 'id="canvas"' in content
    assert 'width="100%"' in content
    assert '"wheel"' in content
    assert "getBBox" in content          # fit-to-view
    assert "mousedown" in content        # drag pan


def test_generate_graph_html_depends_on_dashed(tmp_path: Path):
    """Cross-file depends_on renders as a dashed edge with a hover title."""
    root = _project(tmp_path)
    g = SpecGraph()
    a = _spec("[FSD]-a", "fsd/[FSD]-a")
    b = _spec("[FSD]-b", "fsd/[FSD]-b")
    g.add_spec(a)
    g.add_spec(b)
    g.add_edge(a.uri, b.uri, "depends_on")
    _save_baseline(root, g)
    content = generate_graph_html(root)
    assert 'stroke-dasharray="5,3"' in content
    assert "depends_on: [FSD]-a → [FSD]-b" in content
    # depends_on must not become a tree edge
    assert ">depends_on</text>" not in content


def test_generate_graph_html_inbox_depends_note(tmp_path: Path):
    """Same-file depends_on shows as an in-row annotation (no edge leaves the box)."""
    root = _project(tmp_path)
    g = SpecGraph()
    a = _spec("[FSD]-a", "fsd/[FSD]-a")
    sp = _spec("[FSD]-a:feat", "fsd/[FSD]-a")
    st = _spec("[FSD]-a:store", "fsd/[FSD]-a")
    for s in (a, sp, st):
        g.add_spec(s)
    g.add_edge(sp.uri, st.uri, "depends_on")
    _save_baseline(root, g)
    content = generate_graph_html(root)
    assert "⇢ :store" in content          # annotated on the :feat row
    assert 'stroke-dasharray="5,3"' not in content   # same-file dep draws no edge


def test_generate_graph_html_decomposes_label(tmp_path: Path):
    """fsd decompose → cross-file decomposes edge with a visible label."""
    root = _project(tmp_path)
    vm = VersionManager(root)
    mgr = NewModelManager(root)
    vm.create("v0.1")
    mgr.create_prd(
        "v0.1", "[PRD]-demo", "<!-- @id:[PRD]-demo -->\n## Demo\n", skip_context=True
    )
    mgr.confirm_prd_layer("v0.1")
    mgr.create_fsd(
        "v0.1", "[FSD]-demo",
        "<!-- @id:[FSD]-demo -->\n## F\n\n<!-- @id:[FSD]-demo:core -->\n## core\n",
        parent_chunk_id="[PRD]-demo",
        skip_context=True,
    )
    mgr.decompose_fsd(
        "v0.1", "[FSD]-demo:core", "[FSD]-demo-sub",
        content="<!-- @id:[FSD]-demo-sub -->\n## Sub\n",
        skip_context=True,
    )
    content = generate_graph_html(root, "v0.1")
    assert "[FSD]-demo-sub" in content
    assert ">decomposes</text>" in content
    # the child FSD is its own file box
    assert "fsd/[FSD]-demo-sub" in content


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
    mgr.create_prd(
        "v0.1", "[PRD]-x", "<!-- @id:[PRD]-x -->\n## X\n", skip_context=True
    )
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
