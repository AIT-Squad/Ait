"""真实 baseline `docs/prd/global.md` 的解析回归保护。

实现 impl-prd-global-parser-compat-check #2 (T-prd-global-single-file-03)。

迁移脚本 (scripts/migrate_prd_to_global.py --apply) 还没跑之前，本测试守卫
让其自然 skip；迁移之后将作为持续保护：
  - parse_file 解析出的 chunk 数 ≥ 52（v1.6 基线 52，未来增不退）
  - 所有 chunk 的 @id 唯一
  - 所有 @ref 的 dst 要么在本文件内，要么在 docs/impl/*.md 中能找到
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ait.chunk_parser import parse_file
from ait.index_manager import IndexManager


# 真实仓库 baseline 路径（仓库根 / project-docs / ...）
_REPO_ROOT = Path(__file__).resolve().parent.parent
_REAL_DOCS = _REPO_ROOT / "project-docs" / "docs"
_REAL_GLOBAL_MD = _REAL_DOCS / "prd" / "global.md"


_pytestmark_requires_global = pytest.mark.skipif(
    not _REAL_GLOBAL_MD.exists(),
    reason=(
        "真实 baseline docs/prd/global.md 尚未生成 —— 请先跑 "
        "scripts/migrate_prd_to_global.py --apply 完成 PRD 单文件化迁移。"
    ),
)


@_pytestmark_requires_global
def test_large_single_file_parses_full():
    parsed = parse_file(_REAL_GLOBAL_MD, _REAL_DOCS)

    # (1) chunk 数 ≥ 52
    assert len(parsed.chunks) >= 52, (
        f"global.md should have at least 52 chunks (v1.6 baseline); got {len(parsed.chunks)}"
    )

    # (2) 所有 @id 唯一
    ids = [c.id for c in parsed.chunks]
    assert len(ids) == len(set(ids)), (
        f"duplicate @id in global.md: {[i for i in ids if ids.count(i) > 1]}"
    )

    # (3) 所有 @ref 的 dst 要么是本文件内 chunk，要么在 baseline chunks-index 中找得到
    own_ids = set(ids)
    indexes = IndexManager(_REPO_ROOT / "project-docs")
    baseline_ids = {c.id for c in indexes.load_baseline().chunks}

    dangling: list[tuple[str, str]] = []
    for ref in parsed.refs:
        if ref.target_chunk_id in own_ids:
            continue
        if ref.target_chunk_id in baseline_ids:
            continue
        dangling.append((ref.source_chunk_id, ref.target_chunk_id))

    assert not dangling, f"dangling @ref targets in global.md: {dangling}"
