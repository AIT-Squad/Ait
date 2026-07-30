"""v2.65 关系出生边界收口(G4+G13):

- G4:prd/fsd/tdd create 正文含 @ref/@extract 或(非 fsd 层)depends_on/derives
  声明块 → 拒于落盘前(MARKDOWN_CONTAINS_RELATION);sync_specgraph 对新模型
  chunk(帶 [PRD]-/[FSD]-/[TDD]- 前缀)不再从 @ref 造边(legacy 裸 id chunk 不变);
  validate-new-model 追加基线残留一次性排查(报告不阻断)。
- G13:NewModelManager.add_edge 改名为 _add_edge,不再是公开建边入口。
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from ait.cli import main
from ait.index_manager import IndexManager
from ait.new_model_manager import NewModelManager
from ait.new_model_validator import scan_baseline_relation_residue, scan_content_relations
from ait.specgraph import sync_specgraph
from ait.version_manager import VersionManager


def _payload(result):
    return json.loads(result.output.strip().splitlines()[-1])


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    return root


def _run(runner, *args):
    return _payload(runner.invoke(main, list(args), catch_exceptions=False))


def _set_phase(root: Path, version: str, phase: str) -> None:
    vm = VersionManager(root)
    meta = vm.load_version_meta(version)
    meta.phase = phase  # type: ignore[assignment]
    vm.save_version_meta(meta)


PRD = "<!-- @id:[PRD]-app -->\n## App PRD\n"


# ── G4: content gate ─────────────────────────────────────────────────────────
def test_prd_create_rejects_ref_annotation(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["version", "create", "v0.1"], catch_exceptions=False)

    bad = "<!-- @id:[PRD]-app -->\n## App PRD\n\n<!-- @ref:prd/other#x rel:related -->\n"
    p = _run(runner, "prd", "create", "[PRD]-app", "--content", bad)
    assert p["ok"] is False and p["code"] == "MARKDOWN_CONTAINS_RELATION", p
    assert not (root / "versions" / "v0.1" / "prd" / "[PRD]-app.md").exists(), "零残留"


def test_tdd_create_rejects_extract_annotation(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["version", "create", "v0.1"], catch_exceptions=False)
    _set_phase(root, "v0.1", "tdd-creating")

    bad = (
        "<!-- @id:[TDD]-app -->\n## App TDD\n\n"
        "```yaml\ntarget_file: app.py\n```\n\n"
        "<!-- @extract:impl/detail#x -->\nbody\n<!-- @extract:end -->\n"
    )
    p = _run(runner, "tdd", "create", "[TDD]-app", "--content", bad)
    assert p["ok"] is False and p["code"] == "MARKDOWN_CONTAINS_RELATION", p


def test_prd_create_rejects_depends_on_block(tmp_path: Path, monkeypatch):
    """depends_on/derives 声明块只在 fsd 层合法,prd/tdd 层残留即拒。"""
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["version", "create", "v0.1"], catch_exceptions=False)

    bad = "<!-- @id:[PRD]-app -->\n## App PRD\n\n```yaml\ndepends_on: [x]\n```\n"
    p = _run(runner, "prd", "create", "[PRD]-app", "--content", bad)
    assert p["ok"] is False and p["code"] == "MARKDOWN_CONTAINS_RELATION", p


def test_fsd_create_legit_depends_on_not_rejected(tmp_path: Path, monkeypatch):
    """fsd split 内合法的 depends_on 声明块经既有剥离机制处理,不触发内容闸(回归)。"""
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["version", "create", "v0.1"], catch_exceptions=False)
    _set_phase(root, "v0.1", "fsd-creating")

    fsd = (
        "<!-- @id:[FSD]-app -->\n## App FSD\n\n"
        "<!-- @id:[FSD]-app:feat -->\n## feat\n```yaml\ndepends_on: [store]\n```\n\n"
        "<!-- @id:[FSD]-app:store -->\n## store\n"
    )
    p = _run(runner, "fsd", "create", "[FSD]-app", "--content", fsd)
    assert p["ok"] is True, p
    text = (root / "versions" / "v0.1" / "fsd" / "[FSD]-app.md").read_text(encoding="utf-8")
    assert "depends_on" not in text, "声明块须从正文剥离"


def test_fsd_create_still_rejects_ref_annotation(tmp_path: Path, monkeypatch):
    """fsd 层的内容闸仍检测 @ref/@extract 残留(只是 depends_on/derives 不检测)。"""
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["version", "create", "v0.1"], catch_exceptions=False)
    _set_phase(root, "v0.1", "fsd-creating")

    fsd = (
        "<!-- @id:[FSD]-app -->\n## App FSD\n\n"
        "<!-- @ref:fsd/other#x rel:decomposes -->\n"
    )
    p = _run(runner, "fsd", "create", "[FSD]-app", "--content", fsd)
    assert p["ok"] is False and p["code"] == "MARKDOWN_CONTAINS_RELATION", p


# ── G4: scan_content_relations / scan_baseline_relation_residue 纯函数单测 ──
def test_scan_content_relations_detects_ref():
    v = scan_content_relations("<!-- @ref:a#b rel:related -->", kind="prd")
    assert len(v) == 1 and v[0].code == "MARKDOWN_CONTAINS_RELATION"


def test_scan_content_relations_detects_extract():
    v = scan_content_relations("<!-- @extract:cat/type#x -->\nbody\n<!-- @extract:end -->", kind="tdd")
    assert len(v) == 1 and v[0].code == "MARKDOWN_CONTAINS_RELATION"


def test_scan_content_relations_depends_on_only_flagged_outside_fsd():
    content = "```yaml\ndepends_on: [x]\n```"
    assert scan_content_relations(content, kind="prd")
    assert scan_content_relations(content, kind="tdd")
    assert scan_content_relations(content, kind="fsd") == []


def test_scan_content_relations_clean_body_returns_empty():
    assert scan_content_relations("## Title\n\nplain body, no relations here.\n", kind="prd") == []


def test_scan_baseline_relation_residue_aggregates_and_is_pure():
    contents = [
        ("prd/[PRD]-app", "[PRD]-app", "## App\n\n<!-- @ref:a#b rel:related -->"),
        ("fsd/[FSD]-app", "[FSD]-app", "## App FSD\n\nclean body"),
    ]
    out = scan_baseline_relation_residue(contents)
    assert len(out) == 1
    assert out[0].chunk_id == "[PRD]-app"
    assert out[0].file == "prd/[PRD]-app"
    # pure function: no disk access performed regardless of whether the given
    # paths exist on disk.
    assert scan_baseline_relation_residue([]) == []


# ── G4: sync_specgraph 新模型 chunk @ref 造边退役(chunk_id 前缀判定,非目录) ──
def test_sync_specgraph_skips_new_model_ref(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    (root / "docs" / "fsd").mkdir(parents=True)
    (root / "docs" / "tdd").mkdir(parents=True)
    (root / "docs" / "fsd" / "[FSD]-app.md").write_text(
        "<!-- @id:[FSD]-app -->\n## App FSD\n\n"
        "<!-- @ref:tdd/[TDD]-app#[TDD]-app rel:details -->\n",
        encoding="utf-8",
    )
    (root / "docs" / "tdd" / "[TDD]-app.md").write_text(
        "<!-- @id:[TDD]-app -->\n## App TDD\n\n```yaml\ntarget_file: app.py\n```\n",
        encoding="utf-8",
    )
    IndexManager(root).rebuild_baseline()
    graph = sync_specgraph(root)
    assert graph.edges == [], "新模型 chunk 的 @ref 残留不应造边"


def test_sync_specgraph_keeps_legacy_ref(tmp_path: Path, monkeypatch):
    """docs/prd/ 与新模型共用目录,legacy 裸 id chunk 的 @ref 造边行为不受影响(回归)。"""
    root = _project(tmp_path)
    (root / "docs" / "prd").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "impl").mkdir(parents=True)
    (root / "docs" / "prd" / "global.md").write_text(
        "<!-- @id:prd-alpha -->\n## Alpha\nbody\n\n"
        "<!-- @id:prd-beta -->\n## Beta\n\n<!-- @ref:prd/global#prd-alpha rel:related -->\n",
        encoding="utf-8",
    )
    IndexManager(root).rebuild_baseline()
    graph = sync_specgraph(root)
    rels = {(e.rel) for e in graph.edges}
    assert "related" in rels, "legacy @ref 造边行为不变"


# ── G13: add_edge 私有化 ──────────────────────────────────────────────────────
def test_add_edge_renamed_private(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    VersionManager(root).create("v0.1")
    mgr = NewModelManager(root)

    assert not hasattr(mgr, "add_edge"), "add_edge 不再是公开方法"
    assert callable(mgr._add_edge)


# ── G4: validate-new-model 基线残留排查(报告不阻断) ──────────────────────────
def test_validate_new_model_reports_relation_residue(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    (root / "docs" / "prd").mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    (root / "docs" / "prd" / "[PRD]-app.md").write_text(
        "<!-- @id:[PRD]-app -->\n## App PRD\n\n<!-- @ref:prd/other#x rel:related -->\n",
        encoding="utf-8",
    )
    p = _payload(runner.invoke(main, ["specgraph", "validate-new-model"], catch_exceptions=False))
    assert p["ok"] is True, "残留排查只报告,不影响 ok/退出码"
    residue = p["relation_residue"]
    assert len(residue) == 1
    assert residue[0]["chunk_id"] == "[PRD]-app"


def test_validate_new_model_empty_residue_when_clean(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    (root / "docs" / "prd").mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    (root / "docs" / "prd" / "[PRD]-app.md").write_text(
        "<!-- @id:[PRD]-app -->\n## App PRD\n\nclean body\n", encoding="utf-8"
    )
    p = _payload(runner.invoke(main, ["specgraph", "validate-new-model"], catch_exceptions=False))
    assert p["ok"] is True
    assert p["relation_residue"] == []

