"""Tests for ait.version_manager — stage/commit/status lifecycle."""

from __future__ import annotations

from pathlib import Path

import pytest

from ait.chunk_parser import Chunk
from ait.validation import ValidationError
from ait.version_manager import VersionManager, VersionManagerError


@pytest.fixture
def vm_root(tmp_path: Path) -> Path:
    """Bare project root with empty .meta/docs/versions skeletons."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "versions").mkdir()
    (tmp_path / ".meta" / "versions").mkdir(parents=True)
    (tmp_path / ".meta" / "changes").mkdir(parents=True)
    return tmp_path


def _make_chunk(id_: str, heading: str, file: str = "prd/test", level: int = 2) -> Chunk:
    content = f"<!-- @id:{id_} -->\n## {heading}\n\nbody"
    return Chunk(
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
    # v2.21: create no longer pre-builds legacy prd/impl subdirs; they appear
    # on demand when a file is written into them.
    assert not (vm_root / "versions" / "v1.1" / "prd").exists()
    assert not (vm_root / "versions" / "v1.1" / "impl").exists()
    assert vm.version_meta_path("v1.1").exists()
    assert vm.indexes.version_index_path("v1.1").exists()
    vm.write_version_file("v1.1", "prd/x", "<!-- @id:x -->\n## X\n")
    assert (vm_root / "versions" / "v1.1" / "prd").is_dir()


def test_create_rejects_duplicate(vm_root: Path):
    vm = VersionManager(vm_root)
    vm.create("v1.1")
    with pytest.raises(VersionManagerError):
        vm.create("v1.1")


def test_current_returns_latest_unmerged(vm_root: Path):
    vm = VersionManager(vm_root)
    assert vm.current() is None
    vm.create("v1.1")
    assert vm.current() == "v1.1"


def test_stage_all_working_blocks(vm_root: Path):
    vm = VersionManager(vm_root)
    vm.create("v1.1")
    vm.add_chunk("v1.1", chunk=_make_chunk("prd-test-a", "A"))
    vm.add_chunk("v1.1", chunk=_make_chunk("prd-test-b", "B"))

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
    vm.add_chunk("v1.1", chunk=_make_chunk("prd-test-a", "A"))
    vm.add_chunk("v1.1", chunk=_make_chunk("prd-test-b", "B"))

    result = vm.stage("v1.1", chunk_ids=["prd-test-a"])
    assert result.staged == ["prd-test-a"]
    status = vm.status("v1.1")
    assert status.staged == ["prd-test-a"]
    assert status.working == ["prd-test-b"]


def test_unstage_returns_block_to_working(vm_root: Path):
    vm = VersionManager(vm_root)
    vm.create("v1.1")
    vm.add_chunk("v1.1", chunk=_make_chunk("prd-test-a", "A"))
    vm.stage("v1.1")
    result = vm.unstage("v1.1", ["prd-test-a"])
    assert result.unstaged == ["prd-test-a"]
    assert vm.status("v1.1").working == ["prd-test-a"]


def test_commit_generates_chg_records(vm_root: Path):
    vm = VersionManager(vm_root)
    vm.create("v1.1")
    vm.add_chunk("v1.1", chunk=_make_chunk("prd-test-a", "A"))

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
    vm.add_chunk("v1.1", chunk=_make_chunk("prd-test-a", "A"))
    with pytest.raises(ValidationError) as exc:
        vm.commit("v1.1", "empty")
    assert exc.value.issues[0].code == "COMMIT_EMPTY"


def test_multiple_commits_increment_ids(vm_root: Path):
    vm = VersionManager(vm_root)
    vm.create("v1.1")
    vm.add_chunk("v1.1", chunk=_make_chunk("prd-a", "A"))
    vm.write_version_file("v1.1", "prd/test", "<!-- @id:prd-a -->\n## A\n\nbody\n")
    vm.stage("v1.1")
    first = vm.commit("v1.1", "first")
    assert first.commit_id == "c1"

    vm.add_chunk("v1.1", chunk=_make_chunk("prd-b", "B"))
    vm.write_version_file(
        "v1.1",
        "prd/test",
        "<!-- @id:prd-a -->\n## A\n\nbody\n\n<!-- @id:prd-b -->\n## B\n\nbody\n",
    )
    vm.stage("v1.1")
    second = vm.commit("v1.1", "second")
    assert second.commit_id == "c2"


def test_add_chunk_upserts_working_entry(vm_root: Path):
    """Re-adding the same chunk in working state must replace, not duplicate.

    Regression: prd confirm <req> --file <prd> twice used to grow the version
    chunks-index linearly (4 → 8 → 12 …). The fix is upsert semantics in
    VersionManager.add_chunk.
    """
    vm = VersionManager(vm_root)
    vm.create("v1.1")

    vm.add_chunk(
        "v1.1",
        chunk=_make_chunk("prd-up-a", "A v1"),
        action="add",
        source_req="req-001",
    )
    vm.add_chunk(
        "v1.1",
        chunk=_make_chunk("prd-up-b", "B v1"),
        action="add",
        source_req="req-001",
    )
    # Re-add the same ids with refreshed metadata (simulating a second prd confirm).
    vm.add_chunk(
        "v1.1",
        chunk=_make_chunk("prd-up-a", "A v2"),
        action="modify",
        overrides="prd-up-a",
        source_req="req-002",
    )
    vm.add_chunk(
        "v1.1",
        chunk=_make_chunk("prd-up-b", "B v2"),
        action="add",
        source_req="req-002",
    )

    idx = vm.indexes.load_version_index("v1.1")
    ids = [c.id for c in idx.chunks]
    assert ids == ["prd-up-a", "prd-up-b"], f"duplicate entries: {ids}"

    a = next(c for c in idx.chunks if c.id == "prd-up-a")
    assert a.heading == "A v2"
    assert a.action == "modify"
    assert a.overrides == "prd-up-a"
    assert a.source_req == "req-002"
    assert a.state == "working"

    b = next(c for c in idx.chunks if c.id == "prd-up-b")
    assert b.heading == "B v2"
    assert b.source_req == "req-002"


def test_add_chunk_refuses_to_overwrite_staged(vm_root: Path):
    vm = VersionManager(vm_root)
    vm.create("v1.1")
    vm.add_chunk("v1.1", chunk=_make_chunk("prd-lock-a", "A"))
    vm.stage("v1.1", chunk_ids=["prd-lock-a"])

    with pytest.raises(ValidationError) as exc:
        vm.add_chunk("v1.1", chunk=_make_chunk("prd-lock-a", "A again"))
    assert exc.value.issues[0].code == "CHUNK_LOCKED"
    # Index must remain unchanged.
    idx = vm.indexes.load_version_index("v1.1")
    assert len(idx.chunks) == 1
    assert idx.chunks[0].state == "staged"


def test_add_chunk_refuses_to_overwrite_committed(vm_root: Path):
    vm = VersionManager(vm_root)
    vm.create("v1.1")
    vm.add_chunk("v1.1", chunk=_make_chunk("prd-lock-c", "C"))
    vm.write_version_file(
        "v1.1", "prd/test", "<!-- @id:prd-lock-c -->\n## C\n\nbody\n"
    )
    vm.stage("v1.1")
    vm.commit("v1.1", "lock-c")

    with pytest.raises(ValidationError) as exc:
        vm.add_chunk("v1.1", chunk=_make_chunk("prd-lock-c", "C again"))
    assert exc.value.issues[0].code == "CHUNK_LOCKED"

# ── v2.97: change-ledger id allocation ─────────────────────────────────────
#
# Ids were picked by lexicographic sort of the filenames, so once the ledger
# crossed 999 the "last" name was chg-999, not chg-1000 — every later commit
# re-issued an id that already existed and overwrote the record. Allocation is
# numeric so a digit-count change cannot collide.

def _seed_ledger(root: Path, numbers: list[int]) -> None:
    changes = root / ".meta" / "changes"
    for n in numbers:
        (changes / f"chg-{n:03d}.yaml").write_text(f"id: chg-{n:03d}\n", encoding="utf-8")


def test_next_chg_id_starts_at_one_on_empty_ledger(vm_root: Path):
    assert VersionManager(vm_root)._next_chg_id() == "chg-001"


def test_next_chg_id_increments_within_three_digits(vm_root: Path):
    _seed_ledger(vm_root, list(range(1, 42)))
    assert VersionManager(vm_root)._next_chg_id() == "chg-042"


def test_next_chg_id_does_not_reissue_after_crossing_999(vm_root: Path):
    """chg-999 sorts after chg-1000 as text — the id must still be free."""
    _seed_ledger(vm_root, list(range(1, 1001)))
    assert VersionManager(vm_root)._next_chg_id() == "chg-1001"


def test_next_chg_id_keeps_climbing_past_the_boundary(vm_root: Path):
    _seed_ledger(vm_root, list(range(1, 1003)))
    assert VersionManager(vm_root)._next_chg_id() == "chg-1003"


def test_next_chg_id_never_returns_an_occupied_id(vm_root: Path):
    _seed_ledger(vm_root, list(range(1, 1001)))
    allocated = VersionManager(vm_root)._next_chg_id()
    assert not (vm_root / ".meta" / "changes" / f"{allocated}.yaml").exists()


def test_next_chg_id_ignores_unparsable_ledger_names(vm_root: Path):
    """A stray name must not drive the count into an occupied id."""
    _seed_ledger(vm_root, [1, 2, 3])
    (vm_root / ".meta" / "changes" / "chg-draft.yaml").write_text("x\n", encoding="utf-8")
    assert VersionManager(vm_root)._next_chg_id() == "chg-004"


# ── v3.2: implements gate, impl cascade and bare-id PRD routing retired ─────


def test_retired_legacy_members_are_gone():
    """Every one of these could only fire on `implements` edges or bare-id PRD
    records; neither can occur since v3.1, so the branches are removed."""
    from ait.version_manager import VersionManager

    for name in (
        "_assert_no_orphan_impl_refs",
        "_with_atomic_impl_deletes",
        "_changed_prd_ids",
        "_implements_of_exact_version",
        "_should_route_legacy_prd_to_global",
    ):
        assert not hasattr(VersionManager, name), f"{name} should be retired"
