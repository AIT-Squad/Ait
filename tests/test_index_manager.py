"""Tests for ait.index_manager."""

from __future__ import annotations

from pathlib import Path

import pytest

from ait.index_manager import IndexManager
from ait.schemas import (
    VersionChunkEntry,
    VersionIndex,
)
from ait.specgraph import sync_specgraph

_PRD_FIXTURE = """# 图书管理

<!-- @id:prd-book-mgmt-overview -->
## 功能概述

图书管理系统提供图书维护、借阅和归还能力。

<!-- @id:prd-book-entry -->
## 图书录入

管理员可以录入图书的基本信息。

<!-- @id:prd-book-lifecycle -->
## 图书生命周期

图书状态包括在馆、借出和下架。
"""

_IMPL_FIXTURE = """# 图书管理 API 合同

<!-- @id:impl-api-overview -->
## API 概述

图书管理 API 提供图书操作接口。

<!-- @ref:prd/book-management#prd-book-mgmt-overview rel:implements -->

<!-- @id:impl-api-entry-post -->
## 创建图书接口

`POST /books` 创建图书。

<!-- @id:impl-data-book -->
## 图书数据模型

图书数据包含标识、名称和库存。

<!-- @id:impl-workflow-borrow-rollback -->
## 借阅回滚流程

借阅失败时恢复图书库存。
"""


@pytest.fixture
def demo_root(tmp_path: Path) -> Path:
    """Build a minimal legacy-format docs tree in-place (no external fixture project)."""
    dst = tmp_path / "demo"
    (dst / "docs" / "prd").mkdir(parents=True)
    (dst / "docs" / "impl").mkdir(parents=True)
    (dst / "docs" / "prd" / "book-management.md").write_text(_PRD_FIXTURE, encoding="utf-8")
    (dst / "docs" / "impl" / "api-contracts.md").write_text(_IMPL_FIXTURE, encoding="utf-8")
    return dst


def test_build_baseline_matches_demo(demo_root: Path):
    """Rebuilding baseline from the fixture tree should produce the expected block set."""
    mgr = IndexManager(demo_root)
    baseline = mgr.build_baseline()
    ids = {b.id for b in baseline.chunks}

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
