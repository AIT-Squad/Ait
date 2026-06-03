from __future__ import annotations

from pathlib import Path

from ait.impl_manager import ImplManager
from ait.specgraph import sync_specgraph
from ait.version_manager import VersionManager


def _init_project(root: Path) -> VersionManager:
    (root / "docs" / "prd").mkdir(parents=True)
    (root / "docs" / "impl").mkdir(parents=True)
    (root / "versions").mkdir()
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    (root / "docs" / "prd" / "feature.md").write_text(
        "<!-- @id:prd-a -->\n## A\n\nbody\n",
        encoding="utf-8",
    )
    (root / "docs" / "impl" / "feature.md").write_text(
        "<!-- @id:impl-a-1 -->\n## Impl 1\n\n<!-- @ref:prd/feature#prd-a rel:implements -->\n\nbody 1\n\n"
        "<!-- @id:impl-a-2 -->\n## Impl 2\n\n<!-- @ref:prd/feature#prd-a rel:implements -->\n\nbody 2\n",
        encoding="utf-8",
    )
    vm = VersionManager(root)
    vm.indexes.rebuild_baseline()
    sync_specgraph(root)
    vm.create("v1.1")
    return vm


def test_inherit_clones_baseline_impls(tmp_path: Path):
    vm = _init_project(tmp_path)

    result = ImplManager(tmp_path).inherit("prd-a")

    assert result.version == "v1.1"
    assert result.inherited == ["impl-a-1", "impl-a-2"]
    assert result.skipped == []
    target = tmp_path / "versions" / "v1.1" / "impl" / "feature.md"
    text = target.read_text(encoding="utf-8")
    assert "<!-- @id:impl-a-1 -->" in text
    assert "<!-- @id:impl-a-2 -->" in text
    assert "@ref:prd/feature#prd-a rel:implements" in text
    idx_ids = [c.id for c in vm.indexes.load_version_index("v1.1").chunks]
    assert idx_ids == ["impl-a-1", "impl-a-2"]


def test_inherit_idempotent(tmp_path: Path):
    _init_project(tmp_path)
    mgr = ImplManager(tmp_path)

    first = mgr.inherit("prd-a")
    second = mgr.inherit("prd-a")

    assert first.inherited == ["impl-a-1", "impl-a-2"]
    assert second.inherited == []
    assert second.skipped == ["impl-a-1", "impl-a-2"]
