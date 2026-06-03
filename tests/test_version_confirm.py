"""Tests for PRD baseline 单文件化 (force-route to prd/global on confirm).

Covers impl-prd-global-merge-target-rewrite: in `_perform_merge_internal`,
all PRD records (file_key starting with `prd/` and not equal to `prd/global`)
must be routed into `docs/prd/global.md`. Impl records must be untouched.
"""

from __future__ import annotations

from pathlib import Path

from ait.chunk_parser import parse_file
from ait.schemas import VersionChunkEntry
from ait.specgraph import sync_specgraph
from ait.version_manager import VersionManager


def _init_project_with_global_prd(root: Path) -> VersionManager:
    """Bootstrap a mini project-docs whose baseline already uses prd/global.md."""
    (root / "docs" / "prd").mkdir(parents=True)
    (root / "docs" / "impl").mkdir(parents=True)
    (root / "versions").mkdir()
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    (root / "docs" / "prd" / "global.md").write_text(
        "<!-- @id:prd-existing -->\n## Existing\n\nold body\n",
        encoding="utf-8",
    )
    vm = VersionManager(root)
    vm.indexes.rebuild_baseline()
    sync_specgraph(root)
    vm.create("v1.1")
    return vm


def _parse_version_chunk(vm: VersionManager, version: str, file: str, text: str, chunk_id: str):
    path = vm.write_version_file(version, file, text)
    parsed = parse_file(path, vm.versions_dir / version)
    return next(c for c in parsed.chunks if c.id == chunk_id)


def _commit_records(vm: VersionManager, version: str, *records: VersionChunkEntry) -> None:
    idx = vm.indexes.load_version_index(version)
    idx.chunks.extend(records)
    vm.indexes.save_version_index(idx)
    sync_specgraph(vm.root)


def _committed(chunk, action: str, *, overrides: str | None = None) -> VersionChunkEntry:
    return VersionChunkEntry(
        id=chunk.id,
        file=chunk.file,
        heading=chunk.heading,
        level=chunk.level,
        action=action,
        state="committed",
        commit_id="c1",
        overrides=overrides,
    )


def test_prd_chunks_force_routed_to_global(tmp_path: Path):
    """版本侧多文件 PRD（add + modify）confirm 后必须全部落在 docs/prd/global.md。"""
    vm = _init_project_with_global_prd(tmp_path)

    # 版本工作区放在 prd/foo.md（人写时多文件友好），confirm 阶段应被收敛。
    # 同一份版本文件里同时承载 add 和 modify 两个 chunk。
    foo_text = (
        "<!-- @id:prd-new -->\n## New\n\nnew body\n\n"
        "<!-- @id:prd-existing -->\n## Existing\n\nupdated body\n"
    )
    foo_path = vm.write_version_file("v1.1", "prd/foo", foo_text)
    parsed = parse_file(foo_path, vm.versions_dir / "v1.1")
    new_chunk = next(c for c in parsed.chunks if c.id == "prd-new")
    modified = next(c for c in parsed.chunks if c.id == "prd-existing")

    _commit_records(
        vm,
        "v1.1",
        _committed(new_chunk, "add"),
        _committed(modified, "modify", overrides="prd-existing"),
    )

    result = vm.merge("v1.1", conflict_policy="use-version")

    assert result.status == "completed"

    # (a) docs/prd/global.md 含 2 个 chunk
    global_text = (tmp_path / "docs" / "prd" / "global.md").read_text(encoding="utf-8")
    assert "@id:prd-existing" in global_text
    assert "@id:prd-new" in global_text
    assert "updated body" in global_text
    assert "new body" in global_text

    # (b) docs/prd/foo.md 不存在 —— 路由强制收敛到 global
    assert not (tmp_path / "docs" / "prd" / "foo.md").exists()

    # (c) chunks-index 中所有 PRD chunk 的 file == "prd/global"
    baseline = vm.indexes.load_baseline()
    prd_files = {c.file for c in baseline.chunks if c.id.startswith("prd-")}
    assert prd_files == {"prd/global"}, f"unexpected PRD files: {prd_files}"


def test_impl_chunks_unaffected(tmp_path: Path):
    """impl/* 路由不受 PRD 单文件化影响，bar.md 应被正常创建。"""
    vm = _init_project_with_global_prd(tmp_path)

    impl = _parse_version_chunk(
        vm,
        "v1.1",
        "impl/bar",
        "<!-- @id:impl-bar -->\n## Bar\n\n"
        "<!-- @ref:prd/global#prd-existing rel:implements -->\n\nbar impl\n",
        "impl-bar",
    )
    _commit_records(vm, "v1.1", _committed(impl, "add"))

    result = vm.merge("v1.1", conflict_policy="use-version")
    assert result.status == "completed"

    # impl/bar.md 应该被正常创建（未被 PRD 路由收敛逻辑波及）
    impl_path = tmp_path / "docs" / "impl" / "bar.md"
    assert impl_path.exists(), "impl/bar.md must be created untouched by PRD routing"
    assert "@id:impl-bar" in impl_path.read_text(encoding="utf-8")

    # 没有把 impl 错误地塞进 prd/global.md
    global_text = (tmp_path / "docs" / "prd" / "global.md").read_text(encoding="utf-8")
    assert "@id:impl-bar" not in global_text


def test_delete_prd_chunk_routes_to_global(tmp_path: Path):
    """删除 baseline 已存在的 PRD chunk：从 prd/global.md 中移除，文件仍存在。"""
    vm = _init_project_with_global_prd(tmp_path)

    _commit_records(
        vm,
        "v1.1",
        VersionChunkEntry(
            id="prd-existing",
            file=None,
            heading=None,
            level=None,
            action="delete",
            state="committed",
            commit_id="c1",
            overrides="prd-existing",
        ),
    )

    result = vm.merge("v1.1", conflict_policy="use-version")
    assert result.status == "completed"

    global_path = tmp_path / "docs" / "prd" / "global.md"
    assert global_path.exists(), "prd/global.md must remain as the single PRD file"
    global_text = global_path.read_text(encoding="utf-8")
    assert "@id:prd-existing" not in global_text
