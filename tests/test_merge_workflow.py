"""End-to-end tests for VersionManager.merge — baseline write + snapshot + conflicts."""

from __future__ import annotations

from pathlib import Path

import pytest

from ait.block_parser import Block
from ait.hash_utils import block_hash
from ait.io_utils import atomic_write_text
from ait.validator import ValidationError
from ait.version_manager import VersionManager, VersionManagerError


@pytest.fixture
def project(tmp_path: Path) -> Path:
    for d in ["docs/prd", "docs/impl", ".meta/versions", ".meta/changes", "versions"]:
        (tmp_path / d).mkdir(parents=True)
    return tmp_path


def _make_block(id_: str, heading: str, file: str = "prd/test", level: int = 2) -> Block:
    content = f"<!-- @id:{id_} -->\n{'#' * level} {heading}\n\nbody"
    return Block(
        id=id_, heading=heading, level=level, content=content,
        line_start=1, line_end=4, file=file,
    )


def _seed_baseline(root: Path, file_rel: str, content: str) -> None:
    path = root / "docs" / f"{file_rel}.md"
    atomic_write_text(path, content)


def test_merge_creates_new_file_into_baseline(project: Path):
    vm = VersionManager(project)
    vm.create("v1.1")
    vm.add_block("v1.1", block=_make_block("prd-test-new", "New"))
    vm.write_version_file(
        "v1.1",
        "prd/new-feature",
        "<!-- @id:prd-test-new -->\n## New\n\nbody\n",
    )
    # Move the block's file pointer to the new file (not prd/test).
    idx = vm.indexes.load_version_index("v1.1")
    idx.blocks[0].file = "prd/new-feature"
    vm.indexes.save_version_index(idx)

    vm.stage("v1.1")
    vm.commit("v1.1", "add new feature")
    result = vm.merge("v1.1")

    assert result.status == "completed"
    assert result.merged_blocks == ["prd-test-new"]

    out = project / "docs" / "prd" / "new-feature.md"
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "<!-- @id:prd-test-new -->" in text
    assert "## New" in text


def test_merge_modify_existing_block(project: Path):
    # Seed baseline with one block.
    _seed_baseline(
        project,
        "prd/existing",
        "# Existing doc\n\n<!-- @id:prd-x -->\n## X\n\noriginal body\n",
    )
    vm = VersionManager(project)
    vm.indexes.rebuild_baseline()

    base_hash_recorded = block_hash(
        "<!-- @id:prd-x -->\n## X\n\noriginal body"
    )

    vm.create("v1.1")
    # Write the modified block into the version workspace.
    vm.write_version_file(
        "v1.1",
        "prd/existing",
        "<!-- @id:prd-x -->\n## X (updated)\n\nnew body\n",
    )
    vm.add_block(
        "v1.1",
        block=_make_block("prd-x", "X (updated)", file="prd/existing"),
        action="modify",
        overrides="prd-x",
        base_hash=base_hash_recorded,
    )
    vm.stage("v1.1")
    vm.commit("v1.1", "update x")
    result = vm.merge("v1.1")

    assert result.status == "completed"
    text = (project / "docs" / "prd" / "existing.md").read_text(encoding="utf-8")
    assert "X (updated)" in text
    assert "original body" not in text


def test_merge_conflict_abort_keeps_baseline(project: Path):
    _seed_baseline(
        project,
        "prd/existing",
        "# Existing\n\n<!-- @id:prd-x -->\n## X\n\noriginal\n",
    )
    vm = VersionManager(project)
    vm.indexes.rebuild_baseline()

    vm.create("v1.1")
    # Pretend version recorded an outdated base_hash (simulating someone else changed baseline).
    vm.write_version_file(
        "v1.1",
        "prd/existing",
        "<!-- @id:prd-x -->\n## X v2\n\nupdated\n",
    )
    vm.add_block(
        "v1.1",
        block=_make_block("prd-x", "X v2", file="prd/existing"),
        action="modify",
        overrides="prd-x",
        base_hash="deadbeef",  # wrong hash → conflict
    )
    vm.stage("v1.1")
    vm.commit("v1.1", "intended update")

    result = vm.merge("v1.1", conflict_policy="abort")
    assert result.status == "aborted"
    assert len(result.conflicts) == 1
    # Baseline untouched.
    text = (project / "docs" / "prd" / "existing.md").read_text(encoding="utf-8")
    assert "original" in text
    assert "X v2" not in text


def test_merge_conflict_use_version_overwrites(project: Path):
    _seed_baseline(
        project,
        "prd/existing",
        "# Existing\n\n<!-- @id:prd-x -->\n## X\n\noriginal\n",
    )
    vm = VersionManager(project)
    vm.indexes.rebuild_baseline()

    vm.create("v1.1")
    vm.write_version_file(
        "v1.1",
        "prd/existing",
        "<!-- @id:prd-x -->\n## X v2\n\nforced\n",
    )
    vm.add_block(
        "v1.1",
        block=_make_block("prd-x", "X v2", file="prd/existing"),
        action="modify",
        overrides="prd-x",
        base_hash="deadbeef",
    )
    vm.stage("v1.1")
    vm.commit("v1.1", "force update")

    result = vm.merge("v1.1", conflict_policy="use-version")
    assert result.status == "completed"
    text = (project / "docs" / "prd" / "existing.md").read_text(encoding="utf-8")
    assert "X v2" in text


def test_merge_creates_snapshot(project: Path):
    vm = VersionManager(project)
    vm.create("v1.1")
    vm.add_block(
        "v1.1", block=_make_block("prd-test-x", "X", file="prd/snap"),
    )
    vm.write_version_file(
        "v1.1", "prd/snap", "<!-- @id:prd-test-x -->\n## X\n\nbody\n"
    )
    vm.stage("v1.1")
    vm.commit("v1.1", "x")
    vm.merge("v1.1")

    snap_dir = project / ".meta" / "snapshots" / "v1.1" / "docs" / "prd"
    assert (snap_dir / "snap.md").exists()


def test_merge_updates_baseline_index(project: Path):
    vm = VersionManager(project)
    vm.create("v1.1")
    vm.add_block(
        "v1.1", block=_make_block("prd-test-y", "Y", file="prd/y"),
    )
    vm.write_version_file(
        "v1.1", "prd/y", "<!-- @id:prd-test-y -->\n## Y\n\nbody\n"
    )
    vm.stage("v1.1")
    vm.commit("v1.1", "y")
    vm.merge("v1.1")

    baseline = vm.indexes.load_baseline()
    ids = {b.id for b in baseline.blocks}
    assert "prd-test-y" in ids


def test_merge_already_merged_raises(project: Path):
    vm = VersionManager(project)
    vm.create("v1.1")
    vm.add_block(
        "v1.1", block=_make_block("prd-test-z", "Z", file="prd/z"),
    )
    vm.write_version_file(
        "v1.1", "prd/z", "<!-- @id:prd-test-z -->\n## Z\n\nbody\n"
    )
    vm.stage("v1.1")
    vm.commit("v1.1", "z")
    vm.merge("v1.1")

    with pytest.raises(VersionManagerError):
        vm.merge("v1.1")


def test_merge_no_committed_blocks_raises(project: Path):
    vm = VersionManager(project)
    vm.create("v1.1")
    vm.add_block(
        "v1.1", block=_make_block("prd-test-w", "W", file="prd/w"),
    )
    # Never staged/committed.
    with pytest.raises(ValidationError) as exc:
        vm.merge("v1.1")
    assert exc.value.issues[0].code == "MERGE_NO_COMMITTED"
