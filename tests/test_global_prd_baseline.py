"""回归保护：单文件 baseline (docs/prd/global.md) 下 chunk 索引 / specgraph /
context / deps / impact 都正常工作。

实现 impl-prd-global-parser-compat-check (T-prd-global-single-file-03)。

不改产品代码：本文件构造手工 fixture，验证整套已有读侧逻辑在单文件 baseline
下的等价性 —— 同一组 @ref 关系，单文件 vs 多文件作 oracle 对比，结果应同构。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ait.context_assembler import ContextAssembler
from ait.deps import query_deps
from ait.impact import analyze_impact
from ait.index_manager import IndexManager
from ait.specgraph import SpecGraph, parse_uri, sync_specgraph


# ── fixtures ─────────────────────────────────────────────────────────────────
def _bootstrap_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    for d in [
        "docs/prd",
        "docs/impl",
        ".meta/versions",
        ".meta/changes",
        ".meta/requirements",
        "versions",
    ]:
        (root / d).mkdir(parents=True)
    return root


def _build_single_file_project(tmp_path: Path) -> Path:
    """单文件 baseline：3 个 PRD chunk + 跨 chunk @ref 集中在 docs/prd/global.md。"""
    root = _bootstrap_root(tmp_path, "single")
    (root / "docs" / "prd" / "global.md").write_text(
        "# Baseline PRD（merged baseline, edit by chunk only）\n\n"
        "<!-- @id:prd-alpha -->\n"
        "## Alpha\n\n"
        "<!-- @summary: alpha 概述 -->\n\n"
        "alpha body\n\n"
        "<!-- @id:prd-beta -->\n"
        "## Beta\n\n"
        "<!-- @summary: beta 内容 -->\n\n"
        "<!-- @ref:prd/global#prd-alpha rel:related -->\n\n"
        "beta body referencing alpha\n\n"
        "<!-- @id:prd-gamma -->\n"
        "## Gamma\n\n"
        "<!-- @summary: gamma 内容 -->\n\n"
        "<!-- @ref:prd/global#prd-alpha rel:related -->\n\n"
        "<!-- @ref:prd/global#prd-beta rel:related -->\n\n"
        "gamma body referencing alpha+beta\n",
        encoding="utf-8",
    )
    # 一个 impl 文件，覆盖 1 个 PRD chunk，验证 cross-file @ref 仍正常
    (root / "docs" / "impl" / "alpha.md").write_text(
        "<!-- @id:impl-alpha -->\n"
        "## Alpha impl\n\n"
        "<!-- @summary: alpha 实现 -->\n\n"
        "<!-- @ref:prd/global#prd-alpha rel:implements -->\n\n"
        "impl body\n",
        encoding="utf-8",
    )
    IndexManager(root).rebuild_baseline()
    sync_specgraph(root)
    return root


def _build_multi_file_oracle(tmp_path: Path) -> Path:
    """同一组 @ref 关系的多文件等价构造（oracle）。

    chunk id 与 ref 关系完全一致，只是物理上分散在 prd/alpha.md, prd/beta.md,
    prd/gamma.md。impl 文件不变。
    """
    root = _bootstrap_root(tmp_path, "multi")
    (root / "docs" / "prd" / "alpha.md").write_text(
        "<!-- @id:prd-alpha -->\n"
        "## Alpha\n\n"
        "<!-- @summary: alpha 概述 -->\n\n"
        "alpha body\n",
        encoding="utf-8",
    )
    (root / "docs" / "prd" / "beta.md").write_text(
        "<!-- @id:prd-beta -->\n"
        "## Beta\n\n"
        "<!-- @summary: beta 内容 -->\n\n"
        "<!-- @ref:prd/alpha#prd-alpha rel:related -->\n\n"
        "beta body referencing alpha\n",
        encoding="utf-8",
    )
    (root / "docs" / "prd" / "gamma.md").write_text(
        "<!-- @id:prd-gamma -->\n"
        "## Gamma\n\n"
        "<!-- @summary: gamma 内容 -->\n\n"
        "<!-- @ref:prd/alpha#prd-alpha rel:related -->\n\n"
        "<!-- @ref:prd/beta#prd-beta rel:related -->\n\n"
        "gamma body referencing alpha+beta\n",
        encoding="utf-8",
    )
    (root / "docs" / "impl" / "alpha.md").write_text(
        "<!-- @id:impl-alpha -->\n"
        "## Alpha impl\n\n"
        "<!-- @summary: alpha 实现 -->\n\n"
        "<!-- @ref:prd/alpha#prd-alpha rel:implements -->\n\n"
        "impl body\n",
        encoding="utf-8",
    )
    IndexManager(root).rebuild_baseline()
    sync_specgraph(root)
    return root


# ── helpers ──────────────────────────────────────────────────────────────────
def _edges_by_chunk_ids(root: Path) -> set[tuple[str, str, str]]:
    """specgraph 的边按 chunk_id（去掉 type/version 维度）三元组化，方便跨布局比对。"""
    g = SpecGraph.load(root / ".meta" / "specgraph.yaml")
    triples: set[tuple[str, str, str]] = set()
    for e in g.edges:
        try:
            _, _, src_id = parse_uri(e.src)
            _, _, dst_id = parse_uri(e.dst)
        except ValueError:
            continue
        triples.add((src_id, e.rel, dst_id))
    return triples


# ── tests ────────────────────────────────────────────────────────────────────
def test_single_file_chunks_index_layout(tmp_path: Path):
    """chunks-index：3 个 PRD chunk 的 file == prd/global、id 对应 @id、顺序与文件物理顺序一致。"""
    root = _build_single_file_project(tmp_path)
    baseline = IndexManager(root).load_baseline()
    prd_entries = [c for c in baseline.chunks if c.id.startswith("prd-")]

    assert len(prd_entries) == 3
    assert [e.id for e in prd_entries] == ["prd-alpha", "prd-beta", "prd-gamma"]
    assert {e.file for e in prd_entries} == {"prd/global"}


def test_single_file_specgraph_edges_match_handwritten_refs(tmp_path: Path):
    """specgraph 三元组（chunk_id 维度）== 手工写入的 @ref 关系集合。"""
    root = _build_single_file_project(tmp_path)
    triples = _edges_by_chunk_ids(root)

    expected = {
        ("prd-beta", "related", "prd-alpha"),
        ("prd-gamma", "related", "prd-alpha"),
        ("prd-gamma", "related", "prd-beta"),
        ("impl-alpha", "implements", "prd-alpha"),
    }
    assert triples == expected


@pytest.mark.parametrize("chunk_id", ["prd-alpha", "prd-beta", "prd-gamma"])
def test_context_l1_non_empty_for_each_chunk(tmp_path: Path, chunk_id: str):
    """ait context <chunk_id> 对每个 PRD chunk 都能命中 L1（content 非空）。"""
    root = _build_single_file_project(tmp_path)
    asm = ContextAssembler(root)
    result = asm.assemble(chunk_id, scenario="prd-to-impl").to_dict()

    assert result["l1"]["id"] == chunk_id
    assert result["l1"]["content"], "L1 content must not be empty"


def test_context_prd_to_impl_l2_contains_impl(tmp_path: Path):
    """prd-to-impl 场景下，prd-alpha 的 L2 应包含实现它的 impl-alpha
    （证明 cross-file @ref 在单文件 baseline 下仍被正确解析为 implements 边）。
    """
    root = _build_single_file_project(tmp_path)
    asm = ContextAssembler(root)
    result = asm.assemble("prd-alpha", scenario="prd-to-impl").to_dict()

    l2_ids = [s["id"] for s in result["l2"]]
    assert "impl-alpha" in l2_ids, f"expected impl-alpha in L2, got {l2_ids}"


def test_deps_and_impact_isomorphic_to_multi_file_oracle(tmp_path: Path):
    """同一组 @ref 关系下，单文件 vs 多文件构造的 deps / impact 输出完全等价
    （以 chunk_id 维度比对，不比 URI 字符串差异）。
    """
    single_root = _build_single_file_project(tmp_path)
    multi_root = _build_multi_file_oracle(tmp_path)

    # specgraph chunk-id 三元组在两种布局下完全相等
    assert _edges_by_chunk_ids(single_root) == _edges_by_chunk_ids(multi_root)

    # deps（出+入双向）的 chunk_id 邻居集合相等
    for cid in ["prd-alpha", "prd-beta", "prd-gamma"]:
        single_deps = query_deps(single_root, cid, direction="both")
        multi_deps = query_deps(multi_root, cid, direction="both")
        single_neighbors = {
            tuple(sorted([parse_uri(e["src"])[2], parse_uri(e["dst"])[2]])) + (e["rel"],)
            for e in single_deps["edges"]
        }
        multi_neighbors = {
            tuple(sorted([parse_uri(e["src"])[2], parse_uri(e["dst"])[2]])) + (e["rel"],)
            for e in multi_deps["edges"]
        }
        assert single_neighbors == multi_neighbors, f"deps mismatch on {cid}"

    # impact 受影响的 chunk_id 集合相等
    for cid in ["prd-alpha", "prd-beta", "prd-gamma"]:
        single_impacted = analyze_impact(single_root, cid)["impacted"]
        multi_impacted = analyze_impact(multi_root, cid)["impacted"]
        single_ids = {parse_uri(u)[2] for u in single_impacted}
        multi_ids = {parse_uri(u)[2] for u in multi_impacted}
        assert single_ids == multi_ids, f"impact mismatch on {cid}"
