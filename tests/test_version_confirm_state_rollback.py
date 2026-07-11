"""v2.18 confirm 原子性（audit R1-01）：confirm 中途失败必须全量回滚 docs + .meta。

修复前：merge() 在 confirm 早段就把 merged_at/phase/baseline 索引/specgraph 落盘，
后续任一步（specgraph 基线合并 / git commit）异常时只回滚 docs/ → .meta 残留
merged 态且无 CLI 恢复路径。修复后 `_backup_state/_restore_state` 覆盖
docs/*.md + baseline chunks-index.yaml + specgraph.yaml + versions/{v}.yaml +
chunks-index-{v}.yaml，并清除本次新建的 snapshots/{v}/。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ait.chunk_parser import parse_file
from ait.schemas import VersionChunkEntry
from ait.specgraph import sync_specgraph
from ait.version_manager import VersionManager, VersionManagerError


def _init_project(root: Path) -> VersionManager:
    (root / "docs" / "prd").mkdir(parents=True)
    (root / "docs" / "impl").mkdir(parents=True)
    (root / "versions").mkdir()
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    (root / "docs" / "prd" / "global.md").write_text(
        "<!-- @id:prd-a -->\n## A\n\nbody\n",
        encoding="utf-8",
    )
    vm = VersionManager(root)
    vm.indexes.rebuild_baseline()
    sync_specgraph(root)
    vm.create("v1.1")
    return vm


def _seed_committed_add(vm: VersionManager) -> None:
    path = vm.write_version_file(
        "v1.1", "prd/global", "<!-- @id:prd-b -->\n## B\n\nnew\n"
    )
    parsed = parse_file(path, vm.versions_dir / "v1.1")
    chunk = next(c for c in parsed.chunks if c.id == "prd-b")
    idx = vm.indexes.load_version_index("v1.1")
    idx.chunks.append(
        VersionChunkEntry(
            id=chunk.id,
            file=chunk.file,
            heading=chunk.heading,
            level=chunk.level,
            action="add",
            state="committed",
            commit_id="c1",
        )
    )
    vm.indexes.save_version_index(idx)
    sync_specgraph(vm.root)


def _meta_fingerprint(vm: VersionManager, version: str) -> dict[str, bytes | None]:
    return {
        str(p): (p.read_bytes() if p.exists() else None)
        for p in vm._confirm_meta_paths(version)
    }


def _docs_fingerprint(vm: VersionManager) -> dict[str, bytes]:
    return {str(p): p.read_bytes() for p in (vm.root / "docs").rglob("*.md")}


def _assert_fully_rolled_back(vm, version, meta_before, docs_before):
    meta = vm.load_version_meta(version)
    assert meta.merged_at is None, "merged_at 残留 —— .meta 未回滚"
    assert meta.phase != "merged"
    idx = vm.indexes.load_version_index(version)
    assert idx.status != "merged"
    assert _meta_fingerprint(vm, version) == meta_before, ".meta 关键文件与 confirm 前不一致"
    assert _docs_fingerprint(vm) == docs_before, "docs/ 与 confirm 前不一致"
    assert not (vm.meta_dir / "snapshots" / version).exists(), "本次新建快照目录未清除"


def test_specgraph_merge_failure_rolls_back_all_state(tmp_path: Path, monkeypatch):
    vm = _init_project(tmp_path)
    _seed_committed_add(vm)
    meta_before = _meta_fingerprint(vm, "v1.1")
    docs_before = _docs_fingerprint(vm)

    def boom(self, version):
        raise RuntimeError("specgraph merge exploded")

    monkeypatch.setattr(VersionManager, "_merge_specgraph_to_baseline", boom)
    with pytest.raises(VersionManagerError) as excinfo:
        vm.confirm("v1.1", allow_dirty_git=True)
    assert excinfo.value.code == "MERGE_ROLLBACK"
    _assert_fully_rolled_back(vm, "v1.1", meta_before, docs_before)


def test_git_commit_failure_rolls_back_all_state(tmp_path: Path, monkeypatch):
    vm = _init_project(tmp_path)
    _seed_committed_add(vm)
    meta_before = _meta_fingerprint(vm, "v1.1")
    docs_before = _docs_fingerprint(vm)

    def boom(self, message):
        raise RuntimeError("git is down")

    monkeypatch.setattr(VersionManager, "_git_commit", boom)
    with pytest.raises(VersionManagerError) as excinfo:
        vm.confirm("v1.1", allow_dirty_git=True)
    assert excinfo.value.code == "MERGE_ROLLBACK"
    _assert_fully_rolled_back(vm, "v1.1", meta_before, docs_before)


def test_confirm_retry_succeeds_after_rollback(tmp_path: Path, monkeypatch):
    vm = _init_project(tmp_path)
    _seed_committed_add(vm)

    calls = {"n": 0}

    def fail_once(self, version):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient failure")

    monkeypatch.setattr(VersionManager, "_merge_specgraph_to_baseline", fail_once)
    monkeypatch.setattr(VersionManager, "_git_commit", lambda self, message: "cafe123")

    with pytest.raises(VersionManagerError):
        vm.confirm("v1.1", allow_dirty_git=True)

    result = vm.confirm("v1.1", allow_dirty_git=True)
    assert result["version"] == "v1.1"
    meta = vm.load_version_meta("v1.1")
    assert meta.merged_at is not None
    assert meta.phase == "merged"
    baseline_text = (vm.root / "docs" / "prd" / "global.md").read_text(encoding="utf-8")
    assert "@id:prd-b" in baseline_text
