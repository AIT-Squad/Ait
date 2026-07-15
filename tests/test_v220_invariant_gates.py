"""v2.20 六不变式门禁测试。

写时局部门禁（add_edge/create_tdd，拒绝＝零落盘可重试）＋ confirm 全局门禁
（INVARIANT_VIOLATION，落盘前拒绝、补齐规格后重试成功）＋ 校验器单元。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ait.new_model_manager import NewModelManager
from ait.new_model_validator import (
    check_edge_write,
    normalize_target_file,
    validate_invariants,
)
from ait.specgraph import CombinedView, ViewEdge, ViewNode, load_specgraph
from ait.validator import ValidationError
from ait.version_manager import VersionManager, VersionManagerError


# ── helpers ──────────────────────────────────────────────────────────────


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    VersionManager(root).create("v9.0")
    return root


def _set_phase(root: Path, version: str, phase: str) -> None:
    """P7 测试脚手架:直接置 phase 以构造本文件要测的图形态(相位门禁
    本身在 test_v222/v223/v224 专测;这里测的是边写/confirm 门禁)。"""
    vm = VersionManager(root)
    meta = vm.load_version_meta(version)
    meta.phase = phase  # type: ignore[assignment]
    vm.save_version_meta(meta)


def _node(chunk_id: str, type_: str, file: str) -> ViewNode:
    return ViewNode(
        chunk_id=chunk_id, type=type_, version="baseline",
        file=file, title=chunk_id, uri=f"spec:{type_}:baseline:{chunk_id}",
    )


def _view(nodes: list[ViewNode], edges: list[tuple[str, str, str]]) -> CombinedView:
    view = CombinedView()
    for n in nodes:
        view.nodes[n.chunk_id] = n
    view.edges = [ViewEdge(src=s, dst=d, rel=r, metadata={}) for s, d, r in edges]
    return view


FSD = "<!-- @id:[FSD]-app -->\n## App\n\n<!-- @id:[FSD]-app:feat -->\n## Feat\n"
TDD = "<!-- @id:[TDD]-app-feat -->\n## T\n\n```yaml\ntarget_file: app/feat.py\n```\n"
PRD = "<!-- @id:[PRD]-app -->\n## P\n"


# ── 写时局部门禁（真实命令路径）─────────────────────────────────────────


def test_add_edge_rejects_phantom_endpoint_then_retry(tmp_path: Path):
    root = _project(tmp_path)
    mgr = NewModelManager(root)
    _set_phase(root, "v9.0", "prd-confirm")
    mgr.create_fsd("v9.0", "[FSD]-app", FSD)

    with pytest.raises(ValidationError) as excinfo:
        mgr.add_edge("v9.0", "[FSD]-app:feat", "[TDD]-ghost", "details")
    assert "MISSING_ENDPOINT" in str(excinfo.value)
    assert load_specgraph(root, "v9.0").edges == [], "拒绝必须零落盘"

    _set_phase(root, "v9.0", "fsd-confirm")
    mgr.create_tdd("v9.0", "[TDD]-app-feat", TDD)
    mgr.add_edge("v9.0", "[FSD]-app:feat", "[TDD]-app-feat", "details")  # 重试成功


def test_add_edge_rejects_second_details_parent(tmp_path: Path):
    root = _project(tmp_path)
    mgr = NewModelManager(root)
    _set_phase(root, "v9.0", "prd-confirm")
    mgr.create_fsd("v9.0", "[FSD]-app", FSD)
    mgr.create_fsd(
        "v9.0", "[FSD]-other",
        "<!-- @id:[FSD]-other -->\n## O\n\n<!-- @id:[FSD]-other:x -->\n## X\n",
    )
    _set_phase(root, "v9.0", "fsd-confirm")
    mgr.create_tdd("v9.0", "[TDD]-app-feat", TDD)
    mgr.add_edge("v9.0", "[FSD]-app:feat", "[TDD]-app-feat", "details")

    with pytest.raises(ValidationError) as excinfo:
        mgr.add_edge("v9.0", "[FSD]-other:x", "[TDD]-app-feat", "details")
    assert "TDD_MULTI_PARENT" in str(excinfo.value)
    edges = load_specgraph(root, "v9.0").edges
    assert len([e for e in edges if e.rel == "details"]) == 1, "第二父不得落盘"


def test_add_edge_rejects_second_prd_fsd_link(tmp_path: Path):
    root = _project(tmp_path)
    mgr = NewModelManager(root)
    mgr.create_prd("v9.0", "[PRD]-app", PRD)
    _set_phase(root, "v9.0", "prd-confirm")
    mgr.create_fsd("v9.0", "[FSD]-app", FSD)
    mgr.create_fsd("v9.0", "[FSD]-second", "<!-- @id:[FSD]-second -->\n## S\n")
    mgr.add_edge("v9.0", "[PRD]-app", "[FSD]-app", "decomposes")

    with pytest.raises(ValidationError) as excinfo:
        mgr.add_edge("v9.0", "[PRD]-app", "[FSD]-second", "decomposes")
    assert "PRD_FSD_LINK_NOT_UNIQUE" in str(excinfo.value)


def test_add_edge_same_edge_is_idempotent(tmp_path: Path):
    root = _project(tmp_path)
    mgr = NewModelManager(root)
    _set_phase(root, "v9.0", "prd-confirm")
    mgr.create_fsd("v9.0", "[FSD]-app", FSD)
    _set_phase(root, "v9.0", "fsd-confirm")
    mgr.create_tdd("v9.0", "[TDD]-app-feat", TDD)
    mgr.add_edge("v9.0", "[FSD]-app:feat", "[TDD]-app-feat", "details")
    mgr.add_edge("v9.0", "[FSD]-app:feat", "[TDD]-app-feat", "details")  # 同边重放不拒


# ── confirm 全局门禁（真实命令路径＋拒后重试）────────────────────────────


def test_confirm_rejects_traceless_version_then_retry(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    vm = VersionManager(root)
    mgr = NewModelManager(root)
    monkeypatch.setattr(VersionManager, "_git_commit", lambda self, m: "cafe123")

    # 只有 FSD+TDD、无 PRD → 孤儿+断链
    _set_phase(root, "v9.0", "prd-confirm")
    mgr.create_fsd("v9.0", "[FSD]-app", FSD)
    _set_phase(root, "v9.0", "fsd-confirm")
    mgr.create_tdd("v9.0", "[TDD]-app-feat", TDD)
    mgr.add_edge("v9.0", "[FSD]-app:feat", "[TDD]-app-feat", "details")
    vm.stage("v9.0")
    vm.commit("v9.0", "lock")

    with pytest.raises(VersionManagerError) as excinfo:
        vm.confirm("v9.0", allow_dirty_git=True)
    assert excinfo.value.code == "INVARIANT_VIOLATION"
    assert "TRACE_BROKEN" in str(excinfo.value) or "ORPHAN_CHUNK" in str(excinfo.value)
    assert vm.load_version_meta("v9.0").merged_at is None, "门禁拒绝须零落盘"

    # 补齐 PRD 与 decomposes 边 → 重试成功（拒后可重试，无终态陷阱）
    _set_phase(root, "v9.0", "prd-creating")
    mgr.create_prd("v9.0", "[PRD]-app", PRD)
    mgr.add_edge("v9.0", "[PRD]-app", "[FSD]-app", "decomposes")
    vm.stage("v9.0")
    vm.commit("v9.0", "lock prd")
    result = vm.confirm("v9.0", allow_dirty_git=True)
    assert result["version"] == "v9.0"
    assert vm.load_version_meta("v9.0").merged_at is not None


# ── 校验器单元（六不变式各一反例 + vacuous + 环）──────────────────────────


def test_invariants_prd_link_not_unique():
    view = _view(
        [_node("[PRD]-a", "prd", "prd/[PRD]-a"),
         _node("[FSD]-x", "fsd", "fsd/[FSD]-x"),
         _node("[FSD]-y", "fsd", "fsd/[FSD]-y")],
        [("[PRD]-a", "[FSD]-x", "decomposes"), ("[PRD]-a", "[FSD]-y", "decomposes")],
    )
    codes = [v.code for v in validate_invariants(view, [])]
    assert "PRD_FSD_LINK_NOT_UNIQUE" in codes


def test_invariants_tdd_multi_parent_and_trace():
    view = _view(
        [_node("[PRD]-a", "prd", "prd/[PRD]-a"),
         _node("[FSD]-x", "fsd", "fsd/[FSD]-x"),
         _node("[FSD]-x:s", "fsd", "fsd/[FSD]-x"),
         _node("[FSD]-x:t", "fsd", "fsd/[FSD]-x"),
         _node("[TDD]-x-s", "tdd", "tdd/[TDD]-x-s")],
        [("[PRD]-a", "[FSD]-x", "decomposes"),
         ("[FSD]-x:s", "[TDD]-x-s", "details"),
         ("[FSD]-x:t", "[TDD]-x-s", "details")],
    )
    codes = [v.code for v in validate_invariants(view, [("[TDD]-x-s", "app/s.py")])]
    assert "TDD_MULTI_PARENT" in codes


def test_invariants_orphan_and_trace_broken():
    view = _view(
        [_node("[PRD]-a", "prd", "prd/[PRD]-a"),
         _node("[FSD]-x", "fsd", "fsd/[FSD]-x"),
         _node("[FSD]-lost", "fsd", "fsd/[FSD]-lost"),
         _node("[TDD]-lost-t", "tdd", "tdd/[TDD]-lost-t")],
        [("[PRD]-a", "[FSD]-x", "decomposes")],
    )
    codes = [v.code for v in validate_invariants(view, [("[TDD]-lost-t", "app/t.py")])]
    assert "ORPHAN_CHUNK" in codes and "TRACE_BROKEN" in codes


def test_invariants_duplicate_target_normalized_and_required():
    view = _view(
        [_node("[PRD]-a", "prd", "prd/[PRD]-a"),
         _node("[FSD]-x", "fsd", "fsd/[FSD]-x"),
         _node("[FSD]-x:s", "fsd", "fsd/[FSD]-x"),
         _node("[TDD]-p", "tdd", "tdd/[TDD]-p"),
         _node("[TDD]-q", "tdd", "tdd/[TDD]-q")],
        [("[PRD]-a", "[FSD]-x", "decomposes"),
         ("[FSD]-x:s", "[TDD]-p", "details"),
         ("[FSD]-x:s", "[TDD]-q", "details")],  # q 第二父由 MULTI_PARENT 报,此处只看 target
    )
    codes = [
        v.code
        for v in validate_invariants(
            view, [("[TDD]-p", "src/App.py"), ("[TDD]-q", "./src\\app.py")]
        )
    ]
    assert "DUPLICATE_TARGET_FILE" in codes
    codes2 = [v.code for v in validate_invariants(view, [("[TDD]-p", None)])]
    assert "TDD_TARGET_FILE_REQUIRED" in codes2


def test_invariants_spec_cycle_and_vacuous():
    view = _view(
        [_node("[PRD]-a", "prd", "prd/[PRD]-a"),
         _node("[FSD]-x", "fsd", "fsd/[FSD]-x"),
         _node("[FSD]-x:s", "fsd", "fsd/[FSD]-x"),
         _node("[FSD]-y", "fsd", "fsd/[FSD]-y"),
         _node("[FSD]-y:t", "fsd", "fsd/[FSD]-y")],
        [("[PRD]-a", "[FSD]-x", "decomposes"),
         ("[FSD]-x:s", "[FSD]-y", "decomposes"),
         ("[FSD]-y:t", "[FSD]-x", "decomposes")],  # 树关系成环 → 硬拦
    )
    codes = [v.code for v in validate_invariants(view, [])]
    assert "SPEC_CYCLE" in codes

    # depends_on 环:可诊断但不作门禁(现实互依 + 无删边命令,硬拦=终态陷阱)
    view2 = _view(
        [_node("[PRD]-a", "prd", "prd/[PRD]-a"),
         _node("[FSD]-x", "fsd", "fsd/[FSD]-x"),
         _node("[FSD]-x:s", "fsd", "fsd/[FSD]-x"),
         _node("[FSD]-x:t", "fsd", "fsd/[FSD]-x")],
        [("[PRD]-a", "[FSD]-x", "decomposes"),
         ("[FSD]-x:s", "[FSD]-x:t", "depends_on"),
         ("[FSD]-x:t", "[FSD]-x:s", "depends_on")],
    )
    codes2 = [v.code for v in validate_invariants(view2, [])]
    assert "SPEC_CYCLE" not in codes2
    assert view2.detect_cycle(rels={"depends_on"}) is not None  # 仍可诊断
    assert validate_invariants(CombinedView(), []) == []  # vacuous


def test_check_edge_write_and_normalize_unit():
    view = _view(
        [_node("[FSD]-x:s", "fsd", "fsd/[FSD]-x"), _node("[TDD]-t", "tdd", "tdd/[TDD]-t")],
        [],
    )
    assert [v.code for v in check_edge_write(view, "[FSD]-x:s", "[TDD]-ghost", "details")] == ["MISSING_ENDPOINT"]
    assert check_edge_write(view, "[FSD]-x:s", "[TDD]-t", "details") == []
    assert normalize_target_file("./src\\Sub/..\\App.PY") == "src/app.py"


def test_invariants_prd_requirement_split_exempt_from_rule_1():
    """PRD 需求项 split 不该被①要求 decompose FSD——只有 PRD 根受约束。
    回归 v2.46 dogfood 暴露的校验器缺陷:PRD chunk 化后 split 误触
    PRD_FSD_LINK_NOT_UNIQUE。"""
    view = _view(
        [_node("[PRD]-app", "prd", "prd/[PRD]-app"),
         _node("[PRD]-app:capture", "prd", "prd/[PRD]-app"),      # 需求项 split
         _node("[PRD]-app:complete", "prd", "prd/[PRD]-app"),     # 需求项 split
         _node("[FSD]-app", "fsd", "fsd/[FSD]-app"),
         _node("[FSD]-app:feat", "fsd", "fsd/[FSD]-app"),
         _node("[TDD]-app-feat", "tdd", "tdd/[TDD]-app-feat")],
        [("[PRD]-app", "[FSD]-app", "decomposes"),
         ("[FSD]-app:feat", "[TDD]-app-feat", "details")],
    )
    codes = [v.code for v in validate_invariants(view, [("[TDD]-app-feat", "app/feat.py")])]
    assert "PRD_FSD_LINK_NOT_UNIQUE" not in codes, f"PRD split 误触①: {codes}"


def test_invariants_prd_root_still_requires_one_fsd():
    """确认修复未削弱①对 PRD 根的约束:根 decompose 0 个 FSD 仍报违例。"""
    view = _view(
        [_node("[PRD]-app", "prd", "prd/[PRD]-app"),
         _node("[PRD]-app:capture", "prd", "prd/[PRD]-app")],
        [],  # 根无 decomposes 边
    )
    codes = [v.code for v in validate_invariants(view, [])]
    assert "PRD_FSD_LINK_NOT_UNIQUE" in codes, "PRD 根缺 FSD 应仍报违例"
