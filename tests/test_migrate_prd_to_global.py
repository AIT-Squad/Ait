"""Tests for scripts/migrate_prd_to_global.py.

覆盖 impl-prd-global-migrate-script：
- test_apply_migrates_prd_to_global  : apply=True 后磁盘单文件化、内容自反
- test_dry_run_does_not_touch_disk   : apply=False 时磁盘零变更
- test_specgraph_isomorphic          : 迁移前/后 PRD specgraph (src,rel,dst) 三元组集合完全相等

注意：fixture 全部建在 tmp_path/project-docs 内，绝不动真实 project-docs。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from ait.chunk_parser import parse_file
from ait.hash_utils import chunk_hash
from ait.index_manager import IndexManager
from ait.specgraph import SpecGraph, parse_uri, sync_specgraph


# ── load scripts/migrate_prd_to_global.py as a module ────────────────────────
_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "migrate_prd_to_global.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("migrate_prd_to_global", _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


migrate_module = _load_script_module()


# ── fixture helpers ──────────────────────────────────────────────────────────
def _bootstrap_mini_project(tmp_path: Path) -> Path:
    """构造 mini project-docs：3 个 PRD 文件，共 5 个 chunk，含跨文件 @ref。

    返回 root = tmp_path / 'project-docs'.
    """
    root = tmp_path / "project-docs"
    for d in [
        "docs/prd",
        "docs/impl",
        ".meta/versions",
        ".meta/changes",
        ".meta/requirements",
        "versions",
    ]:
        (root / d).mkdir(parents=True)

    # File A — 2 chunks (含 @summary marker，验证逐字保留)
    (root / "docs" / "prd" / "alpha.md").write_text(
        "# Alpha PRD\n\n"
        "<!-- @id:prd-alpha-overview -->\n"
        "## 概述\n\n"
        "<!-- @summary: alpha 概述 -->\n\n"
        "alpha overview body\n\n"
        "<!-- @id:prd-alpha-rules -->\n"
        "## 规则\n\n"
        "<!-- @summary: alpha 规则 -->\n\n"
        "<!-- @ref:prd/beta#prd-beta-core rel:related -->\n\n"
        "alpha rules body\n",
        encoding="utf-8",
    )

    # File B — 2 chunks (含 @prd-no-impl marker)
    (root / "docs" / "prd" / "beta.md").write_text(
        "# Beta PRD\n\n"
        "<!-- @id:prd-beta-core -->\n"
        "## 核心\n\n"
        "<!-- @summary: beta 核心 -->\n\n"
        "beta core body\n\n"
        "<!-- @id:prd-beta-notes -->\n"
        "## 备注\n\n"
        "<!-- @summary: beta 备注 -->\n\n"
        "<!-- @prd-no-impl -->\n\n"
        "beta notes body\n",
        encoding="utf-8",
    )

    # File C — 1 chunk
    (root / "docs" / "prd" / "gamma.md").write_text(
        "<!-- @id:prd-gamma-only -->\n"
        "## Gamma\n\n"
        "<!-- @summary: gamma 唯一 -->\n\n"
        "<!-- @ref:prd/alpha#prd-alpha-overview rel:related -->\n\n"
        "gamma body\n",
        encoding="utf-8",
    )

    # 一个 impl 文件，确保迁移不影响 impl
    (root / "docs" / "impl" / "untouched.md").write_text(
        "<!-- @id:impl-untouched -->\n"
        "## Untouched\n\n"
        "<!-- @summary: 不该被影响 -->\n\n"
        "<!-- @ref:prd/alpha#prd-alpha-overview rel:implements -->\n\n"
        "impl body\n",
        encoding="utf-8",
    )

    # 初始化 baseline 索引 + specgraph
    indexes = IndexManager(root)
    indexes.rebuild_baseline()
    sync_specgraph(root)

    return root


def _snapshot_prd_edges(root: Path) -> set[tuple[str, str, str]]:
    g = SpecGraph.load(root / ".meta" / "specgraph.yaml")
    triples: set[tuple[str, str, str]] = set()
    for e in g.edges:
        try:
            src_type, _, _ = parse_uri(e.src)
            dst_type, _, _ = parse_uri(e.dst)
        except ValueError:
            continue
        if src_type == "prd" or dst_type == "prd":
            triples.add((e.src, e.rel, e.dst))
    return triples


def _snapshot_chunk_hashes(root: Path) -> dict[str, str]:
    """对所有 PRD chunk 取 chunk_hash(content)，用于跨迁移自反性比对。"""
    docs = root / "docs"
    hashes: dict[str, str] = {}
    for md in sorted((docs / "prd").glob("*.md")):
        parsed = parse_file(md, docs)
        for c in parsed.chunks:
            hashes[c.id] = chunk_hash(c.content)
    return hashes


def _disk_mtime_snapshot(root: Path) -> dict[str, float]:
    """记录 root 下所有文件的 mtime 用于 dry-run 不变性断言。"""
    snap: dict[str, float] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            snap[str(p.relative_to(root))] = p.stat().st_mtime_ns / 1e9
    return snap


# ── tests ────────────────────────────────────────────────────────────────────
def test_apply_migrates_prd_to_global(tmp_path: Path):
    root = _bootstrap_mini_project(tmp_path)

    pre_hashes = _snapshot_chunk_hashes(root)
    assert len(pre_hashes) == 5

    report = migrate_module.migrate(root, apply=True)

    assert report["ok"] is True
    assert report.get("applied") is True
    assert report["prd_chunk_count"] == 5

    # global.md 存在且单一
    prd_dir = root / "docs" / "prd"
    md_files = sorted(p.name for p in prd_dir.glob("*.md"))
    assert md_files == ["global.md"]

    # 重解析：5 chunk、id 一致、hash 一致（自反性）
    parsed = parse_file(prd_dir / "global.md", root / "docs")
    assert len(parsed.chunks) == 5
    post_ids = {c.id for c in parsed.chunks}
    assert post_ids == set(pre_hashes.keys())
    for c in parsed.chunks:
        assert chunk_hash(c.content) == pre_hashes[c.id], f"hash drift on {c.id}"

    # impl 不受影响
    assert (root / "docs" / "impl" / "untouched.md").exists()

    # baseline chunks-index：所有 PRD chunk 的 file == prd/global
    baseline = IndexManager(root).load_baseline()
    prd_files = {e.file for e in baseline.chunks if e.id.startswith("prd-")}
    assert prd_files == {"prd/global"}


def test_dry_run_does_not_touch_disk(tmp_path: Path):
    root = _bootstrap_mini_project(tmp_path)

    before = _disk_mtime_snapshot(root)
    report = migrate_module.migrate(root, apply=False)
    after = _disk_mtime_snapshot(root)

    assert report["ok"] is True
    assert report.get("dry_run") is True
    assert report["prd_chunk_count"] == 5

    # 文件集合不变
    assert set(before.keys()) == set(after.keys()), (
        f"unexpected files diff: added={set(after) - set(before)} "
        f"removed={set(before) - set(after)}"
    )
    # mtime 不变
    for path, mtime in before.items():
        assert after[path] == pytest.approx(mtime), f"mtime drift on {path}"


def test_specgraph_isomorphic(tmp_path: Path):
    root = _bootstrap_mini_project(tmp_path)

    pre_edges = _snapshot_prd_edges(root)
    assert pre_edges, "fixture should produce at least one PRD-related edge"

    migrate_module.migrate(root, apply=True)

    post_edges = _snapshot_prd_edges(root)
    assert post_edges == pre_edges, (
        f"specgraph PRD edges drifted. added={post_edges - pre_edges} "
        f"removed={pre_edges - post_edges}"
    )
