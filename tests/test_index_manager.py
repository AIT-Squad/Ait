"""Tests for ait.index_manager."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ait.index_manager import IndexManager
from ait.schemas import (
    VersionChunkEntry,
    VersionIndex,
)
from ait.specgraph import sync_specgraph

DEMO_ROOT = Path(__file__).parent.parent / "project-demo"


@pytest.fixture
def demo_root(tmp_path: Path) -> Path:
    """Copy project-demo into a tmp directory so tests don't mutate the source."""
    dst = tmp_path / "demo"
    shutil.copytree(DEMO_ROOT, dst)
    return dst


def test_build_baseline_matches_demo(demo_root: Path):
    """Rebuilding baseline from demo files should produce the same block set."""
    mgr = IndexManager(demo_root)
    baseline = mgr.build_baseline()
    ids = {b.id for b in baseline.chunks}

    # The demo's hand-maintained chunks-index.yaml lists these chunks.
    must_have = {
        "prd-book-mgmt-overview",
        "prd-book-entry",
        "prd-book-lifecycle",
        "impl-api-overview",
        "impl-api-entry-post",
        "impl-data-book",
        "impl-workflow-borrow-rollback",
    }
    missing = must_have - ids
    assert not missing, f"Missing expected ids: {missing}"


def test_rebuild_baseline_writes_files(demo_root: Path):
    mgr = IndexManager(demo_root)
    baseline, links = mgr.rebuild_baseline()
    assert mgr.baseline_index_path().exists()
    assert baseline.chunks, "baseline must not be empty"
    assert links.links == []

    graph = sync_specgraph(demo_root)
    assert any(edge.rel == "implements" for edge in graph.edges)


def test_query_baseline(demo_root: Path):
    mgr = IndexManager(demo_root)
    mgr.rebuild_baseline()
    entry = mgr.query_baseline("prd-book-entry")
    assert entry is not None
    assert entry.file == "prd/book-management"
    assert entry.heading == "图书录入"
    assert entry.level == 2

    assert mgr.query_baseline("nonexistent-block") is None


def test_load_baseline_returns_empty_when_missing(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / ".meta").mkdir()
    mgr = IndexManager(tmp_path)
    baseline = mgr.load_baseline()
    assert baseline.chunks == []


def test_version_index_save_and_load(tmp_path: Path):
    (tmp_path / ".meta").mkdir()
    (tmp_path / "versions" / "v1.1").mkdir(parents=True)
    mgr = IndexManager(tmp_path)
    idx = VersionIndex(
        version_name="v1.1",
        chunks=[
            VersionChunkEntry(
                id="prd-test-x",
                file="prd/test",
                heading="X",
                level=2,
                action="add",
                state="working",
            )
        ],
    )
    mgr.save_version_index(idx)

    loaded = mgr.load_version_index("v1.1")
    assert len(loaded.chunks) == 1
    assert loaded.chunks[0].id == "prd-test-x"
    assert loaded.stats.total_chunks == 1
    assert loaded.stats.by_action == {"add": 1}
    assert loaded.stats.by_state == {"working": 1}


def test_query_version_picks_latest_committed(tmp_path: Path):
    (tmp_path / ".meta").mkdir()
    (tmp_path / "versions" / "v1.1").mkdir(parents=True)
    mgr = IndexManager(tmp_path)
    idx = VersionIndex(
        version_name="v1.1",
        chunks=[
            VersionChunkEntry(
                id="prd-x",
                file="prd/x",
                heading="X",
                level=2,
                action="add",
                state="committed",
                commit_id="c1",
            ),
            VersionChunkEntry(
                id="prd-x",
                file="prd/x",
                heading="X v2",
                level=2,
                action="modify",
                state="working",
                amends="c1/prd-x",
            ),
        ],
    )
    mgr.save_version_index(idx)
    # query_version prefers committed first when both committed and working records exist.
    entry = mgr.query_version("v1.1", "prd-x")
    assert entry is not None
    assert entry.state == "committed"
    assert entry.commit_id == "c1"

    # All records should be visible via all_version_records.
    records = mgr.all_version_records("v1.1", "prd-x")
    assert len(records) == 2
