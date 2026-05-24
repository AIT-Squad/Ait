"""Tests for ait.version_manager — stage/commit/status lifecycle."""

from __future__ import annotations

from pathlib import Path

import pytest

from ait.block_parser import Block
from ait.validator import ValidationError
from ait.version_manager import VersionManager


@pytest.fixture
def vm_root(tmp_path: Path) -> Path:
    """Bare project root with empty .meta/docs/versions skeletons."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "versions").mkdir()
    (tmp_path / ".meta" / "versions").mkdir(parents=True)
    (tmp_path / ".meta" / "changes").mkdir(parents=True)
    return tmp_path


def _make_block(id_: str, heading: str, file: str = "prd/test", level: int = 2) -> Block:
    content = f"<!-- @id:{id_} -->\n## {heading}\n\nbody"
    return Block(
        id=id_,
        heading=heading,
        level=level,
        content=content,
        line_start=1,
        line_end=4,
        file=file,
    )


def test_create_version(vm_root: Path):
    vm = VersionManager(vm_root)
    meta = vm.create("v1.1")
    assert meta.version == "v1.1"
    assert (vm_root / "versions" / "v1.1" / "prd").is_dir()
    assert (vm_root / "versions" / "v1.1" / "impl").is_dir()
    assert vm.version_meta_path("v1.1").exists()
    assert vm.indexes.version_index_path("v1.1").exists()


def test_current_returns_latest_unmerged(vm_root: Path):
    vm = VersionManager(vm_root)
    assert vm.current() is None
    vm.create("v1.1")
    assert vm.current() == "v1.1"


def test_stage_all_working_blocks(vm_root: Path):
    vm = VersionManager(vm_root)
    vm.create("v1.1")
    vm.add_block("v1.1", block=_make_block("prd-test-a", "A"))
    vm.add_block("v1.1", block=_make_block("prd-test-b", "B"))

    # Write the actual file content so commit can find new_content later.
    vm.write_version_file(
        "v1.1",
        "prd/test",
        "<!-- @id:prd-test-a -->\n## A\n\nbody\n\n<!-- @id:prd-test-b -->\n## B\n\nbody\n",
    )

    result = vm.stage("v1.1")
    assert set(result.staged) == {"prd-test-a", "prd-test-b"}
    status = vm.status("v1.1")
    assert set(status.staged) == {"prd-test-a", "prd-test-b"}
    assert status.working == []


def test_stage_specific_blocks(vm_root: Path):
    vm = VersionManager(vm_root)
    vm.create("v1.1")
    vm.add_block("v1.1", block=_make_block("prd-test-a", "A"))
    vm.add_block("v1.1", block=_make_block("prd-test-b", "B"))

    result = vm.stage("v1.1", block_ids=["prd-test-a"])
    assert result.staged == ["prd-test-a"]
    status = vm.status("v1.1")
    assert status.staged == ["prd-test-a"]
    assert status.working == ["prd-test-b"]


def test_unstage_returns_block_to_working(vm_root: Path):
    vm = VersionManager(vm_root)
    vm.create("v1.1")
    vm.add_block("v1.1", block=_make_block("prd-test-a", "A"))
    vm.stage("v1.1")
    result = vm.unstage("v1.1", ["prd-test-a"])
    assert result.unstaged == ["prd-test-a"]
    assert vm.status("v1.1").working == ["prd-test-a"]


def test_commit_generates_chg_records(vm_root: Path):
    vm = VersionManager(vm_root)
    vm.create("v1.1")
    vm.add_block("v1.1", block=_make_block("prd-test-a", "A"))

    vm.write_version_file(
        "v1.1",
        "prd/test",
        "<!-- @id:prd-test-a -->\n## A\n\nbody\n",
    )
    vm.stage("v1.1")

    result = vm.commit("v1.1", "first commit")
    assert result.commit_id == "c1"
    assert len(result.changes) == 1

    chg_path = vm_root / ".meta" / "changes" / f"{result.changes[0]}.yaml"
    assert chg_path.exists()

    text = chg_path.read_text(encoding="utf-8")
    assert "type: ADD" in text
    assert "prd-test-a" in text

    # Version meta should record the chg id.
    meta = vm.load_version_meta("v1.1")
    assert result.changes[0] in meta.changes


def test_commit_without_staged_raises_e1(vm_root: Path):
    vm = VersionManager(vm_root)
    vm.create("v1.1")
    vm.add_block("v1.1", block=_make_block("prd-test-a", "A"))
    with pytest.raises(ValidationError) as exc:
        vm.commit("v1.1", "empty")
    assert exc.value.issues[0].code == "COMMIT_EMPTY"


def test_multiple_commits_increment_ids(vm_root: Path):
    vm = VersionManager(vm_root)
    vm.create("v1.1")
    vm.add_block("v1.1", block=_make_block("prd-a", "A"))
    vm.write_version_file("v1.1", "prd/test", "<!-- @id:prd-a -->\n## A\n\nbody\n")
    vm.stage("v1.1")
    first = vm.commit("v1.1", "first")
    assert first.commit_id == "c1"

    vm.add_block("v1.1", block=_make_block("prd-b", "B"))
    vm.write_version_file(
        "v1.1",
        "prd/test",
        "<!-- @id:prd-a -->\n## A\n\nbody\n\n<!-- @id:prd-b -->\n## B\n\nbody\n",
    )
    vm.stage("v1.1")
    second = vm.commit("v1.1", "second")
    assert second.commit_id == "c2"
