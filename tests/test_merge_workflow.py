"""End-to-end tests for VersionManager.merge — baseline write + snapshot + conflicts."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ait.chunk_parser import Chunk
from ait.hash_utils import chunk_hash
from ait.io_utils import atomic_write_text
from ait.schemas import VersionChunkEntry
from ait.validator import ValidationError
from ait.version_manager import VersionManager, VersionManagerError


@pytest.fixture
def project(tmp_path: Path) -> Path:
    for d in ["docs/prd", "docs/impl", ".meta/versions", ".meta/changes", "versions"]:
        (tmp_path / d).mkdir(parents=True)
    return tmp_path


def _make_chunk(id_: str, heading: str, file: str = "impl/test", level: int = 2) -> Chunk:
    content = f"<!-- @id:{id_} -->\n{'#' * level} {heading}\n\nbody"
    return Chunk(
        id=id_, heading=heading, level=level, content=content,
        line_start=1, line_end=4, file=file,
    )


def _seed_baseline(root: Path, file_rel: str, content: str) -> None:
    path = root / "docs" / f"{file_rel}.md"
    atomic_write_text(path, content)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        pytest.skip("git is not available")
    except subprocess.CalledProcessError as exc:
        pytest.fail(f"git {' '.join(args)} failed: {exc.stderr}")


def test_merge_creates_new_file_into_baseline(project: Path):
    # NOTE: 用 impl 路径承载"新建 baseline 文件"语义；PRD 类目在 v1.6 起被收敛到
    # docs/prd/global.md，不再以"任意新建多文件"作为合并目标。
    vm = VersionManager(project)
    vm.create("v1.1")
    vm.add_chunk("v1.1", chunk=_make_chunk("impl-test-new", "New"))
    vm.write_version_file(
        "v1.1",
        "impl/new-feature",
        "<!-- @id:impl-test-new -->\n## New\n\nbody\n",
    )
    # Move the block's file pointer to the new file (not impl/test).
    idx = vm.indexes.load_version_index("v1.1")
    idx.chunks[0].file = "impl/new-feature"
    vm.indexes.save_version_index(idx)

    vm.stage("v1.1")
    vm.commit("v1.1", "add new feature")
    result = vm.merge("v1.1")

    assert result.status == "completed"
    assert result.merged_chunks == ["impl-test-new"]

    out = project / "docs" / "impl" / "new-feature.md"
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "<!-- @id:impl-test-new -->" in text
    assert "## New" in text


def test_merge_modify_existing_block(project: Path):
    # NOTE: 用 impl 路径承载通用 "modify existing" 语义。
    # Seed baseline with one block.
    _seed_baseline(
        project,
        "impl/existing",
        "# Existing doc\n\n<!-- @id:impl-x -->\n## X\n\noriginal body\n",
    )
    vm = VersionManager(project)
    vm.indexes.rebuild_baseline()

    base_hash_recorded = chunk_hash(
        "<!-- @id:impl-x -->\n## X\n\noriginal body"
    )

    vm.create("v1.1")
    # Write the modified block into the version workspace.
    vm.write_version_file(
        "v1.1",
        "impl/existing",
        "<!-- @id:impl-x -->\n## X (updated)\n\nnew body\n",
    )
    vm.add_chunk(
        "v1.1",
        chunk=_make_chunk("impl-x", "X (updated)", file="impl/existing"),
        action="modify",
        overrides="impl-x",
        base_hash=base_hash_recorded,
    )
    vm.stage("v1.1")
    vm.commit("v1.1", "update x")
    result = vm.merge("v1.1")

    assert result.status == "completed"
    text = (project / "docs" / "impl" / "existing.md").read_text(encoding="utf-8")
    assert "X (updated)" in text
    assert "original body" not in text


def test_merge_rejects_add_when_chunk_exists_in_baseline(project: Path):
    _seed_baseline(
        project,
        "impl/existing",
        "# Existing doc\n\n<!-- @id:impl-x -->\n## X\n\noriginal body\n",
    )
    vm = VersionManager(project)
    vm.indexes.rebuild_baseline()

    vm.create("v1.1")
    vm.write_version_file(
        "v1.1",
        "impl/existing",
        "<!-- @id:impl-x -->\n## X duplicate\n\nnew body\n",
    )
    vm.add_chunk(
        "v1.1",
        chunk=_make_chunk("impl-x", "X duplicate", file="impl/existing"),
        action="add",
    )
    vm.stage("v1.1")
    vm.commit("v1.1", "bad duplicate add")

    with pytest.raises(ValidationError) as exc:
        vm.merge("v1.1")

    assert exc.value.issues[0].code == "DUPLICATE_BASELINE_CHUNK"
    text = (project / "docs" / "impl" / "existing.md").read_text(encoding="utf-8")
    assert text.count("<!-- @id:impl-x -->") == 1
    assert "original body" in text
    assert "new body" not in text


def test_merge_latest_record_uses_index_order_not_commit_id_text(project: Path):
    _seed_baseline(
        project,
        "impl/existing",
        "# Existing doc\n\n<!-- @id:impl-x -->\n## X\n\noriginal body\n",
    )
    vm = VersionManager(project)
    vm.indexes.rebuild_baseline()

    vm.create("v1.1")
    vm.write_version_file(
        "v1.1",
        "impl/existing",
        "<!-- @id:impl-x -->\n## X updated\n\nnew body\n",
    )
    idx = vm.indexes.load_version_index("v1.1")
    idx.chunks.extend(
        [
            VersionChunkEntry(
                id="impl-x",
                file="impl/existing",
                heading="X duplicate",
                level=2,
                action="add",
                state="committed",
                commit_id="c9",
            ),
            VersionChunkEntry(
                id="impl-x",
                file="impl/existing",
                heading="X updated",
                level=2,
                action="modify",
                state="committed",
                commit_id="c10",
                overrides="impl-x",
                base_hash=chunk_hash(
                    "<!-- @id:impl-x -->\n## X\n\noriginal body\n"
                ),
            ),
        ]
    )
    vm.indexes.save_version_index(idx)

    result = vm.merge("v1.1")

    assert result.status == "completed"
    text = (project / "docs" / "impl" / "existing.md").read_text(encoding="utf-8")
    assert text.count("<!-- @id:impl-x -->") == 1
    assert "X updated" in text
    assert "new body" in text


def test_modify_record_routes_to_overridden_baseline_file(project: Path):
    _seed_baseline(
        project,
        "impl/existing",
        "# Existing doc\n\n<!-- @id:impl-x -->\n## X\n\noriginal body\n",
    )
    vm = VersionManager(project)
    vm.indexes.rebuild_baseline()

    vm.create("v1.1")
    vm.write_version_file(
        "v1.1",
        "impl/update-bundle",
        "<!-- @id:impl-x -->\n## X updated\n\nnew body\n",
    )
    idx = vm.indexes.load_version_index("v1.1")
    idx.chunks.append(
        VersionChunkEntry(
            id="impl-x",
            file="impl/update-bundle",
            heading="X updated",
            level=2,
            action="modify",
            state="committed",
            commit_id="c1",
            overrides="impl-x",
            base_hash=chunk_hash("<!-- @id:impl-x -->\n## X\n\noriginal body\n"),
        )
    )
    vm.indexes.save_version_index(idx)

    result = vm.merge("v1.1")

    assert result.status == "completed"
    text = (project / "docs" / "impl" / "existing.md").read_text(encoding="utf-8")
    assert "X updated" in text
    assert "new body" in text
    assert not (project / "docs" / "impl" / "update-bundle.md").exists()


def test_confirm_surfaces_duplicate_add_before_merge_rollback(project: Path):
    _seed_baseline(
        project,
        "impl/existing",
        "# Existing doc\n\n<!-- @id:impl-x -->\n## X\n\noriginal body\n",
    )
    vm = VersionManager(project)
    vm.indexes.rebuild_baseline()

    vm.create("v1.1")
    vm.write_version_file(
        "v1.1",
        "impl/existing",
        "<!-- @id:impl-x -->\n## X duplicate\n\nnew body\n",
    )
    vm.add_chunk(
        "v1.1",
        chunk=_make_chunk("impl-x", "X duplicate", file="impl/existing"),
        action="add",
    )
    vm.stage("v1.1")
    vm.commit("v1.1", "bad duplicate add")

    with pytest.raises(ValidationError) as exc:
        vm.confirm("v1.1")

    assert exc.value.issues[0].code == "DUPLICATE_BASELINE_CHUNK"
    text = (project / "docs" / "impl" / "existing.md").read_text(encoding="utf-8")
    assert text.count("<!-- @id:impl-x -->") == 1
    assert "original body" in text
    assert "new body" not in text


def test_confirm_commits_final_merged_state_without_dirty_tail(project: Path):
    _seed_baseline(
        project,
        "impl/existing",
        "# Existing doc\n\n<!-- @id:impl-x -->\n## X\n\noriginal body\n",
    )
    vm = VersionManager(project)
    vm.indexes.rebuild_baseline()

    vm.create("v1.1")
    vm.write_version_file(
        "v1.1",
        "impl/new-feature",
        "<!-- @id:impl-y -->\n## Y\n\nnew body\n",
    )
    vm.add_chunk(
        "v1.1",
        chunk=_make_chunk("impl-y", "Y", file="impl/new-feature"),
        action="add",
    )
    vm.stage("v1.1")
    vm.commit("v1.1", "add y")

    _git(project, "init")
    _git(project, "config", "user.email", "ait@example.com")
    _git(project, "config", "user.name", "AIT Tests")
    _git(project, "add", "-A")
    _git(project, "commit", "-m", "before confirm")

    result = vm.confirm("v1.1")

    assert result["commit"]
    assert _git(project, "status", "--porcelain").stdout.strip() == ""
    assert "phase: merged" in (project / ".meta" / "versions" / "v1.1.yaml").read_text(
        encoding="utf-8"
    )
    assert "- Phase: `merged`" in (
        project / "versions" / "v1.1" / "state.md"
    ).read_text(encoding="utf-8")


def test_merge_conflict_abort_keeps_baseline(project: Path):
    # NOTE: 用 impl 路径承载通用 "conflict abort" 语义。
    _seed_baseline(
        project,
        "impl/existing",
        "# Existing\n\n<!-- @id:impl-x -->\n## X\n\noriginal\n",
    )
    vm = VersionManager(project)
    vm.indexes.rebuild_baseline()

    vm.create("v1.1")
    # Pretend version recorded an outdated base_hash (simulating someone else changed baseline).
    vm.write_version_file(
        "v1.1",
        "impl/existing",
        "<!-- @id:impl-x -->\n## X v2\n\nupdated\n",
    )
    vm.add_chunk(
        "v1.1",
        chunk=_make_chunk("impl-x", "X v2", file="impl/existing"),
        action="modify",
        overrides="impl-x",
        base_hash="deadbeef",  # wrong hash → conflict
    )
    vm.stage("v1.1")
    vm.commit("v1.1", "intended update")

    result = vm.merge("v1.1", conflict_policy="abort")
    assert result.status == "aborted"
    assert len(result.conflicts) == 1
    # Baseline untouched.
    text = (project / "docs" / "impl" / "existing.md").read_text(encoding="utf-8")
    assert "original" in text
    assert "X v2" not in text


def test_merge_conflict_use_version_overwrites(project: Path):
    # NOTE: 用 impl 路径承载通用 "conflict use-version" 语义。
    _seed_baseline(
        project,
        "impl/existing",
        "# Existing\n\n<!-- @id:impl-x -->\n## X\n\noriginal\n",
    )
    vm = VersionManager(project)
    vm.indexes.rebuild_baseline()

    vm.create("v1.1")
    vm.write_version_file(
        "v1.1",
        "impl/existing",
        "<!-- @id:impl-x -->\n## X v2\n\nforced\n",
    )
    vm.add_chunk(
        "v1.1",
        chunk=_make_chunk("impl-x", "X v2", file="impl/existing"),
        action="modify",
        overrides="impl-x",
        base_hash="deadbeef",
    )
    vm.stage("v1.1")
    vm.commit("v1.1", "force update")

    result = vm.merge("v1.1", conflict_policy="use-version")
    assert result.status == "completed"
    text = (project / "docs" / "impl" / "existing.md").read_text(encoding="utf-8")
    assert "X v2" in text


def test_merge_creates_snapshot(project: Path):
    # NOTE: 用 impl 路径承载通用 "snapshot 落盘" 语义。
    vm = VersionManager(project)
    vm.create("v1.1")
    vm.add_chunk(
        "v1.1", chunk=_make_chunk("impl-test-x", "X", file="impl/snap"),
    )
    vm.write_version_file(
        "v1.1", "impl/snap", "<!-- @id:impl-test-x -->\n## X\n\nbody\n"
    )
    vm.stage("v1.1")
    vm.commit("v1.1", "x")
    vm.merge("v1.1")

    snap_dir = project / ".meta" / "snapshots" / "v1.1" / "docs" / "impl"
    assert (snap_dir / "snap.md").exists()


def test_merge_updates_baseline_index(project: Path):
    # NOTE: 用 impl 路径承载通用 "baseline index 更新" 语义。
    vm = VersionManager(project)
    vm.create("v1.1")
    vm.add_chunk(
        "v1.1", chunk=_make_chunk("impl-test-y", "Y", file="impl/y"),
    )
    vm.write_version_file(
        "v1.1", "impl/y", "<!-- @id:impl-test-y -->\n## Y\n\nbody\n"
    )
    vm.stage("v1.1")
    vm.commit("v1.1", "y")
    vm.merge("v1.1")

    baseline = vm.indexes.load_baseline()
    ids = {b.id for b in baseline.chunks}
    assert "impl-test-y" in ids


def test_merge_already_merged_raises(project: Path):
    # NOTE: 用 impl 路径承载通用 "重复 merge 报错" 语义。
    vm = VersionManager(project)
    vm.create("v1.1")
    vm.add_chunk(
        "v1.1", chunk=_make_chunk("impl-test-z", "Z", file="impl/z"),
    )
    vm.write_version_file(
        "v1.1", "impl/z", "<!-- @id:impl-test-z -->\n## Z\n\nbody\n"
    )
    vm.stage("v1.1")
    vm.commit("v1.1", "z")
    vm.merge("v1.1")

    with pytest.raises(VersionManagerError):
        vm.merge("v1.1")


def test_merge_no_committed_blocks_raises(project: Path):
    # NOTE: 用 impl 路径承载通用 "无 committed 报错" 语义。
    vm = VersionManager(project)
    vm.create("v1.1")
    vm.add_chunk(
        "v1.1", chunk=_make_chunk("impl-test-w", "W", file="impl/w"),
    )
    # Never staged/committed.
    with pytest.raises(ValidationError) as exc:
        vm.merge("v1.1")
    assert exc.value.issues[0].code == "MERGE_NO_COMMITTED"
