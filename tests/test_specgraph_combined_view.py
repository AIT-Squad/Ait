"""v2.19 组合图视图（chunk_id 世界）单测。

覆盖 [TDD]-specgraph 组合视图契约：版本覆盖 baseline、边端点坍缩到 chunk_id
（消除 URI 二象性——被 modify 进版本的 chunk 保有 baseline 期全部关系）、
(src,dst,rel) 去重、悬空边丢弃、合并后才成环（audit R2-02）在视图上可检、
impacted 含 decomposes/details 正向下游与 depends_on 反向依赖方。
"""

from __future__ import annotations

from pathlib import Path

from ait.index_manager import IndexManager
from ait.schemas import VersionChunkEntry
from ait.specgraph import (
    Spec,
    SpecGraph,
    combined_view,
    load_specgraph,
    make_uri,
    specgraph_path,
)
from ait.version_manager import VersionManager


def _spec(chunk_id: str, version: str, file: str, type_: str = "fsd") -> Spec:
    return Spec(
        uri=make_uri(chunk_id, version, file),
        title=chunk_id,
        type=type_,
        version=version,
        chunk_id=chunk_id,
        file=file,
        metadata={},
    )


def _save(root: Path, graph: SpecGraph, version: str = "baseline") -> None:
    path = specgraph_path(root, version)
    path.parent.mkdir(parents=True, exist_ok=True)
    graph.save(path)


def _baseline_two_nodes(root: Path) -> None:
    g = SpecGraph()
    a = _spec("[FSD]-a", "baseline", "fsd/[FSD]-a")
    b = _spec("[TDD]-a-x", "baseline", "tdd/[TDD]-a-x", type_="tdd")
    g.add_spec(a)
    g.add_spec(b)
    g.add_edge(a.uri, b.uri, "details", metadata={"source": "new-model-cli"})
    _save(root, g)


def test_version_spec_overlays_baseline_node(tmp_path: Path):
    _baseline_two_nodes(tmp_path)
    vg = SpecGraph(version="v1.0")
    vg.add_spec(_spec("[TDD]-a-x", "v1.0", "tdd/[TDD]-a-x", type_="tdd"))
    _save(tmp_path, vg, "v1.0")

    view = combined_view(tmp_path, "v1.0")

    node = view.node("[TDD]-a-x")
    assert node is not None and node.version == "v1.0", "modify chunk 的内容来源应指向版本"
    assert view.node("[FSD]-a").version == "baseline"


def test_baseline_edges_visible_for_modified_chunk(tmp_path: Path):
    """v2.18 缺口回归（单元级）：details 边挂在 baseline URI，被 modify 的
    chunk 换进版本命名空间后，视图内按 chunk_id 仍能查到该边。"""
    _baseline_two_nodes(tmp_path)
    vg = SpecGraph(version="v1.0")
    vg.add_spec(_spec("[TDD]-a-x", "v1.0", "tdd/[TDD]-a-x", type_="tdd"))
    _save(tmp_path, vg, "v1.0")

    view = combined_view(tmp_path, "v1.0")

    incoming = view.edges_to("[TDD]-a-x", "details")
    assert [e.src for e in incoming] == ["[FSD]-a"]


def test_rename_modify_rebases_baseline_edges_in_both_directions(tmp_path: Path):
    """覆盖改名不应令 baseline 的关系仍指向被替代的旧 chunk。"""
    g = SpecGraph()
    old = _spec("[PRD]-old", "baseline", "prd/[PRD]-old", type_="prd")
    fsd = _spec("[FSD]-app", "baseline", "fsd/[FSD]-app")
    g.add_spec(old)
    g.add_spec(fsd)
    g.add_edge(old.uri, fsd.uri, "derives", metadata={"source": "new-model-cli"})
    _save(tmp_path, g)

    vg = SpecGraph(version="v1.0")
    renamed = _spec("[PRD]-new", "v1.0", "prd/[PRD]-new", type_="prd")
    vg.add_spec(renamed)
    _save(tmp_path, vg, "v1.0")
    indexes = IndexManager(tmp_path)
    index = indexes.load_version_index("v1.0")
    index.chunks.append(
        VersionChunkEntry(
            id="[PRD]-new",
            file="prd/[PRD]-new",
            heading="New",
            level=2,
            action="modify",
            state="working",
            overrides="[PRD]-old",
        )
    )
    indexes.save_version_index(index)

    view = combined_view(tmp_path, "v1.0")

    assert view.node("[PRD]-old") is None
    assert view.node("[PRD]-new").version == "v1.0"
    assert [edge.dst for edge in view.edges_from("[PRD]-new", "derives")] == ["[FSD]-app"]
    assert [edge.src for edge in view.edges_to("[FSD]-app", "derives")] == ["[PRD]-new"]


def test_rename_modify_promotion_keeps_rebased_baseline_edge(tmp_path: Path):
    """改名式 modify 合并后，baseline 图不能保留指向旧 chunk 的悬空关系。"""
    g = SpecGraph()
    old = _spec("[PRD]-old", "baseline", "prd/[PRD]-old", type_="prd")
    fsd = _spec("[FSD]-app", "baseline", "fsd/[FSD]-app")
    g.add_spec(old)
    g.add_spec(fsd)
    g.add_edge(old.uri, fsd.uri, "derives", metadata={"source": "new-model-cli"})
    _save(tmp_path, g)

    vg = SpecGraph(version="v1.0")
    renamed = _spec("[PRD]-new", "v1.0", "prd/[PRD]-new", type_="prd")
    vg.add_spec(renamed)
    _save(tmp_path, vg, "v1.0")
    indexes = IndexManager(tmp_path)
    index = indexes.load_version_index("v1.0")
    index.chunks.append(
        VersionChunkEntry(
            id="[PRD]-new",
            file="prd/[PRD]-new",
            heading="New",
            level=2,
            action="modify",
            state="working",
            overrides="[PRD]-old",
        )
    )
    indexes.save_version_index(index)

    VersionManager(tmp_path)._merge_specgraph_to_baseline("v1.0")
    merged = load_specgraph(tmp_path)

    assert all(spec.chunk_id != "[PRD]-old" for spec in merged.specs.values())
    assert [
        (edge.src, edge.dst, edge.rel) for edge in merged.edges
    ] == [(make_uri("[PRD]-new"), make_uri("[FSD]-app"), "derives")]


def test_edges_deduped_by_triple(tmp_path: Path):
    _baseline_two_nodes(tmp_path)
    vg = SpecGraph(version="v1.0")
    vg.add_spec(_spec("[FSD]-a", "v1.0", "fsd/[FSD]-a"))
    vg.add_spec(_spec("[TDD]-a-x", "v1.0", "tdd/[TDD]-a-x", type_="tdd"))
    # 同一逻辑边在版本图里再存一遍（版本 URI）
    vg.add_edge(
        make_uri("[FSD]-a", "v1.0", "fsd/[FSD]-a"),
        make_uri("[TDD]-a-x", "v1.0", "tdd/[TDD]-a-x"),
        "details",
        metadata={"source": "new-model-cli"},
    )
    _save(tmp_path, vg, "v1.0")

    view = combined_view(tmp_path, "v1.0")

    triples = [(e.src, e.dst, e.rel) for e in view.edges]
    assert triples.count(("[FSD]-a", "[TDD]-a-x", "details")) == 1


def test_dangling_edge_dropped(tmp_path: Path):
    g = SpecGraph()
    a = _spec("[FSD]-a", "baseline", "fsd/[FSD]-a")
    g.add_spec(a)
    g.add_edge(a.uri, make_uri("[FSD]-ghost", "baseline"), "depends_on")
    _save(tmp_path, g)

    view = combined_view(tmp_path)

    assert view.edges == []


def test_merge_only_cycle_detected_on_view(tmp_path: Path):
    """audit R2-02：baseline B→A depends_on ＋ 版本 A→B（各自命名空间下无环），
    坍缩到 chunk_id 后成环，视图上直接可检。"""
    g = SpecGraph()
    a = _spec("[FSD]-r:a", "baseline", "fsd/[FSD]-r")
    b = _spec("[FSD]-r:b", "baseline", "fsd/[FSD]-r")
    g.add_spec(a)
    g.add_spec(b)
    g.add_edge(b.uri, a.uri, "depends_on")
    _save(tmp_path, g)

    vg = SpecGraph(version="v1.0")
    va = _spec("[FSD]-r:a", "v1.0", "fsd/[FSD]-r")
    vg.add_spec(va)
    vg.add_edge(va.uri, make_uri("[FSD]-r:b", "baseline", "fsd/[FSD]-r"), "depends_on")
    _save(tmp_path, vg, "v1.0")

    view = combined_view(tmp_path, "v1.0")

    cycle = view.detect_cycle(rels={"depends_on"})
    assert cycle is not None
    assert set(cycle) == {"[FSD]-r:a", "[FSD]-r:b"}


def test_impacted_walks_tree_downstream_and_dependents(tmp_path: Path):
    """改 PRD → decomposes 子 FSD、根的冒号 split（无边的结构子）与 details 孙 TDD
    全部纳入；反向 depends_on 依赖方纳入。"""
    g = SpecGraph()
    prd = _spec("[PRD]-app", "baseline", "prd/[PRD]-app", type_="prd")
    fsd = _spec("[FSD]-app", "baseline", "fsd/[FSD]-app")
    split = _spec("[FSD]-app:feat", "baseline", "fsd/[FSD]-app")  # 结构子,无显式边
    tdd = _spec("[TDD]-app-x", "baseline", "tdd/[TDD]-app-x", type_="tdd")
    dep = _spec("[FSD]-other", "baseline", "fsd/[FSD]-other")
    for s in (prd, fsd, split, tdd, dep):
        g.add_spec(s)
    g.add_edge(prd.uri, fsd.uri, "decomposes")
    g.add_edge(split.uri, tdd.uri, "details")  # split 经 details 到 TDD
    g.add_edge(dep.uri, fsd.uri, "depends_on")  # dep 依赖 fsd → 改 fsd 波及 dep
    _save(tmp_path, g)

    view = combined_view(tmp_path)

    impacted = view.impacted("[PRD]-app")
    assert "[FSD]-app" in impacted, "decomposes 正向下游缺失"
    assert "[FSD]-app:feat" in impacted, "id 结构子（根→冒号 split 无边）缺失"
    assert "[TDD]-app-x" in impacted, "details 孙层缺失"
    assert "[FSD]-other" in impacted, "反向 depends_on 依赖方缺失"
    assert "[PRD]-app" not in impacted, "起点不应出现在影响集"
