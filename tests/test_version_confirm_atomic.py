from __future__ import annotations

from pathlib import Path

from ait.chunk_parser import parse_file
from ait.schemas import VersionChunkEntry
from ait.specgraph import sync_specgraph
from ait.version_manager import VersionManager


def _init_project(root: Path) -> VersionManager:
    (root / "docs" / "prd").mkdir(parents=True)
    (root / "docs" / "impl").mkdir(parents=True)
    (root / "versions").mkdir()
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    # PRD baseline 单文件化：v1.6 起 baseline PRD 唯一文件为 docs/prd/global.md。
    (root / "docs" / "prd" / "global.md").write_text(
        "<!-- @id:prd-a -->\n## A old\n\nold\n",
        encoding="utf-8",
    )
    (root / "docs" / "impl" / "feature.md").write_text(
        "<!-- @id:impl-old-1 -->\n## Old 1\n\n<!-- @ref:prd/global#prd-a rel:implements -->\n\nold 1\n\n"
        "<!-- @id:impl-old-2 -->\n## Old 2\n\n<!-- @ref:prd/global#prd-a rel:implements -->\n\nold 2\n",
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


def _commit_records(vm: VersionManager, *records: VersionChunkEntry) -> None:
    idx = vm.indexes.load_version_index("v1.1")
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


def test_modify_prd_replaces_impl_set(tmp_path: Path):
    vm = _init_project(tmp_path)
    prd = _parse_version_chunk(vm, "v1.1", "prd/global", "<!-- @id:prd-a -->\n## A new\n\nnew\n", "prd-a")
    impl = _parse_version_chunk(
        vm,
        "v1.1",
        "impl/feature-new",
        "<!-- @id:impl-new -->\n## New\n\n<!-- @ref:prd/global#prd-a rel:implements -->\n\nnew impl\n",
        "impl-new",
    )
    _commit_records(vm, _committed(prd, "modify", overrides="prd-a"), _committed(impl, "add"))

    result = vm.merge("v1.1", conflict_policy="use-version")

    assert result.status == "completed"
    old_text = (tmp_path / "docs" / "impl" / "feature.md").read_text(encoding="utf-8")
    new_text = (tmp_path / "docs" / "impl" / "feature-new.md").read_text(encoding="utf-8")
    assert "impl-old-1" not in old_text
    assert "impl-old-2" not in old_text
    assert "impl-new" in new_text


def test_modify_prd_keeps_impl_when_inherited(tmp_path: Path):
    vm = _init_project(tmp_path)
    prd = _parse_version_chunk(vm, "v1.1", "prd/global", "<!-- @id:prd-a -->\n## A new\n\nnew\n", "prd-a")
    inherited = _parse_version_chunk(
        vm,
        "v1.1",
        "impl/feature",
        "<!-- @id:impl-old-1 -->\n## Old 1\n\n<!-- @ref:prd/global#prd-a rel:implements -->\n\nold 1\n",
        "impl-old-1",
    )
    _commit_records(vm, _committed(prd, "modify", overrides="prd-a"), _committed(inherited, "add"))

    vm.merge("v1.1", conflict_policy="use-version")

    text = (tmp_path / "docs" / "impl" / "feature.md").read_text(encoding="utf-8")
    assert "impl-old-1" in text
    assert "impl-old-2" not in text


def test_delete_prd_removes_all_impls(tmp_path: Path):
    vm = _init_project(tmp_path)
    _commit_records(
        vm,
        VersionChunkEntry(
            id="prd-a",
            file=None,
            heading=None,
            level=None,
            action="delete",
            state="committed",
            commit_id="c1",
            overrides="prd-a",
        ),
    )

    vm.merge("v1.1", conflict_policy="use-version")

    prd_text = (tmp_path / "docs" / "prd" / "global.md").read_text(encoding="utf-8")
    impl_text = (tmp_path / "docs" / "impl" / "feature.md").read_text(encoding="utf-8")
    assert "prd-a" not in prd_text
    assert "impl-old-1" not in impl_text
    assert "impl-old-2" not in impl_text


def test_no_impl_marker_skips_coverage(tmp_path: Path):
    vm = _init_project(tmp_path)
    prd = _parse_version_chunk(
        vm,
        "v1.1",
        "prd/no-code",
        "<!-- @id:prd-no-code -->\n## No Code\n\n<!-- @prd-no-impl -->\n\nDocs only.\n",
        "prd-no-code",
    )
    vm.add_chunk("v1.1", chunk=prd, action="add")
    vm.stage("v1.1", ["prd-no-code"])
    vm.commit("v1.1", "prd no impl")

    assert vm.status("v1.1").committed == ["prd-no-code"]
