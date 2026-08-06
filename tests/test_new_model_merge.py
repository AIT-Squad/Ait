from __future__ import annotations

from pathlib import Path

import pytest

from ait.chunk_parser import parse_file
from ait.new_model_manager import NewModelManager
from ait.specgraph import load_specgraph
from ait.validator import ValidationError
from ait.version_manager import VersionManager


def test_new_model_merge_preserves_file_containers_and_edges(tmp_path: Path):
    root = tmp_path
    (root / "docs").mkdir()
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    vm = VersionManager(root)
    vm.create("v9.0")
    mgr = NewModelManager(root)

    prd_path = vm.write_version_file(
        "v9.0",
        "prd/[PRD]-book_system",
        "<!-- @id:[PRD]-book_system -->\n## Book System\n",
    )
    prd = parse_file(prd_path, vm.versions_dir / "v9.0").chunks[0]
    vm.add_chunk("v9.0", chunk=prd, action="add")

    # P7 脚手架:PRD 经 write_version_file 直写(未走 create_prd),手动置 phase
    # 到 prd-confirm 以放行 FSD 层(本测试测的是 merge 保留文件容器与边)。
    _meta = vm.load_version_meta("v9.0")
    _meta.phase = "prd-confirm"  # type: ignore[assignment]
    vm.save_version_meta(_meta)

    mgr.create_fsd(
        "v9.0",
        "[FSD]-book_management",
        "<!-- @id:[FSD]-book_management -->\n## Book Management\n\n"
        "<!-- @id:[FSD]-book_management:book_model -->\n## Book Model\n",
        skip_context=True,
    )
    _meta = vm.load_version_meta("v9.0")
    _meta.phase = "fsd-confirm"  # type: ignore[assignment]
    vm.save_version_meta(_meta)
    mgr.create_tdd(
        "v9.0",
        "[TDD]-book_model",
        "<!-- @id:[TDD]-book_model -->\n## Book Model TDD\n\n"
        "```yaml\n"
        "target_file: app/models/book.py\n"
        "```\n",
        skip_context=True,
    )
    mgr._add_edge("v9.0", "[FSD]-book_management:book_model", "[TDD]-book_model", "details")

    vm.stage(
        "v9.0",
        [
            "[PRD]-book_system",
            "[FSD]-book_management",
            "[FSD]-book_management:book_model",
            "[TDD]-book_model",
        ],
    )
    vm.commit("v9.0", "commit new-model docs")

    result = vm.merge("v9.0", conflict_policy="use-version")

    assert result.status == "completed"
    assert (root / "docs" / "prd" / "[PRD]-book_system.md").exists()
    assert not (root / "docs" / "prd" / "global.md").exists()
    assert (root / "docs" / "fsd" / "[FSD]-book_management.md").exists()
    assert (root / "docs" / "tdd" / "[TDD]-book_model.md").exists()

    vm._merge_specgraph_to_baseline("v9.0")
    baseline_graph = load_specgraph(root, "baseline")
    edge_triples = {
        (
            baseline_graph.specs[edge.src].chunk_id,
            edge.rel,
            baseline_graph.specs[edge.dst].chunk_id,
        )
        for edge in baseline_graph.edges
    }
    assert ("[FSD]-book_management:book_model", "details", "[TDD]-book_model") in edge_triples


def test_create_rejects_action_add_for_chunk_already_in_baseline(tmp_path: Path):
    """回归测试(v2.87):create 若把已存在于baseline 的 chunk 也当 action=add 传入,
    须在写入前(零写入)就报 DUPLICATE_BASELINE_CHUNK,不能拖到下一版本 merge/confirm 才发现。"""
    root = tmp_path
    (root / "docs").mkdir()
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    vm = VersionManager(root)
    mgr = NewModelManager(root)

    # v1:正常建 [PRD]-app 并合入 baseline。
    vm.create("v1.0")
    mgr.create_prd(
        "v1.0",
        "[PRD]-app",
        "<!-- @id:[PRD]-app -->\n## App\n",
        skip_context=True,
    )
    vm.stage("v1.0", ["[PRD]-app"])
    vm.commit("v1.0", "seed baseline")
    vm.merge("v1.0", conflict_policy="use-version")

    # v2:content 里把已在 baseline 的 [PRD]-app 也当新增(action=add)一起传入。
    vm.create("v2.0")
    with pytest.raises(ValidationError) as exc:
        mgr.create_prd(
            "v2.0",
            "[PRD]-app2",
            "<!-- @id:[PRD]-app -->\n## App\n\n<!-- @id:[PRD]-app2 -->\n## App2\n",
            skip_context=True,
        )
    assert exc.value.issues[0].code == "DUPLICATE_BASELINE_CHUNK"
    assert exc.value.issues[0].chunk_id == "[PRD]-app"

    # 零写入:不应留下任何本次 create 产生的版本文件或索引记录。
    assert not (vm.versions_dir / "v2.0" / "prd" / "[PRD]-app2.md").exists()
    version_index = mgr.indexes.load_version_index("v2.0")
    assert version_index.chunks == []
