from __future__ import annotations

from pathlib import Path

import pytest

from ait.impl_manager import ImplManager
from ait.version_manager import VersionManager
from ait.validator import ValidationError
from ait.specgraph import sync_specgraph


def _init_project(root: Path) -> VersionManager:
    (root / "docs" / "prd").mkdir(parents=True)
    (root / "docs" / "impl").mkdir(parents=True)
    (root / "versions").mkdir()
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    vm = VersionManager(root)
    vm.indexes.rebuild_baseline()
    sync_specgraph(root)
    return vm


def _write_version_file(vm: VersionManager, version: str, file: str, text: str):
    path = vm.write_version_file(version, file, text)
    from ait.chunk_parser import parse_file

    return parse_file(path, vm.versions_dir / version)


def test_block_when_prd_uncovered(tmp_path: Path):
    vm = _init_project(tmp_path)
    vm.create("v1.1")
    parsed_prd = _write_version_file(
        vm,
        "v1.1",
        "prd/feature",
"<!-- @id:prd-a -->\n## A\n\n<!-- @summary: PRD A -->\n\nbody\n\n<!-- @id:prd-b -->\n## B\n\n<!-- @summary: PRD B -->\n\n<!-- @prd-no-impl -->\n\nbody\n",
    )
    prd = parsed_prd.chunks[0]
    prd_b = parsed_prd.chunks[1]
    impl = _write_version_file(
        vm,
        "v1.1",
        "impl/feature",
"<!-- @id:impl-b-other -->\n## Other\n\n<!-- @summary: Other impl -->\n\n<!-- @ref:prd/feature#prd-b rel:implements -->\n\nbody\n",
    ).chunks[0]
    vm.add_chunk("v1.1", chunk=prd, action="add")
    vm.add_chunk("v1.1", chunk=prd_b, action="add")
    vm.stage("v1.1", ["prd-a", "prd-b"])
    vm.commit("v1.1", "prd")
    vm.add_chunk("v1.1", chunk=impl, action="add")

    with pytest.raises(ValidationError) as exc:
        ImplManager(tmp_path).commit("impl-b-other", "impl")

    assert exc.value.issues[0].code == "IMPL_COVERAGE_INCOMPLETE"
    assert "prd-a" in exc.value.issues[0].message


def test_block_delete_with_orphan_impl(tmp_path: Path):
    vm = _init_project(tmp_path)
    (tmp_path / "docs" / "prd" / "feature.md").write_text(
"<!-- @id:prd-a -->\n## A\n\n<!-- @summary: PRD A -->\n\nbody\n",
        encoding="utf-8",
    )
    vm.indexes.rebuild_baseline()
    sync_specgraph(tmp_path)
    vm.create("v1.1")
    idx = vm.indexes.load_version_index("v1.1")
    from ait.schemas import VersionChunkEntry

    idx.chunks.append(
        VersionChunkEntry(
            id="prd-a",
            file=None,
            heading=None,
            level=None,
            action="delete",
            state="committed",
            overrides="prd-a",
        )
    )
    vm.indexes.save_version_index(idx)
    impl = _write_version_file(
        vm,
        "v1.1",
        "impl/feature",
"<!-- @id:impl-a-main -->\n## Impl A\n\n<!-- @summary: Impl A -->\n\n<!-- @ref:prd/feature#prd-a rel:implements -->\n",
    ).chunks[0]
    vm.add_chunk("v1.1", chunk=impl, action="add")

    with pytest.raises(ValidationError) as exc:
        ImplManager(tmp_path).commit("impl-a-main", "impl")

    assert exc.value.issues[0].code == "IMPL_ON_DELETED_PRD"
    assert "impl-a-main" in exc.value.issues[0].message


def test_pending_impl_counted(tmp_path: Path):
    vm = _init_project(tmp_path)
    vm.create("v1.1")
    prd = _write_version_file(
        vm,
        "v1.1",
        "prd/feature",
"<!-- @id:prd-a -->\n## A\n\n<!-- @summary: PRD A -->\n\nbody\n",
    ).chunks[0]
    impl = _write_version_file(
        vm,
        "v1.1",
        "impl/feature",
"<!-- @id:impl-a-main -->\n## Impl A\n\n<!-- @summary: Impl A -->\n\n<!-- @ref:prd/feature#prd-a rel:implements -->\n",
    ).chunks[0]
    vm.add_chunk("v1.1", chunk=prd, action="add")
    vm.stage("v1.1", ["prd-a"])
    vm.commit("v1.1", "prd")
    vm.add_chunk("v1.1", chunk=impl, action="add")

    result = ImplManager(tmp_path).commit("impl-a-main", "impl")

    assert result["impl_chunk_id"] == "impl-a-main"
    assert result["commit_id"] == "c2"
