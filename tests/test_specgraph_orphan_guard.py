from __future__ import annotations

from pathlib import Path

import pytest

from ait.specgraph import Edge, Spec, SpecGraph, make_uri, specgraph_path
from ait.version_manager import VersionManager, VersionManagerError


def test_orphan_blocks_confirm(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "versions").mkdir()
    (tmp_path / ".meta" / "versions").mkdir(parents=True)
    (tmp_path / ".meta" / "changes").mkdir(parents=True)
    graph = SpecGraph()
    impl_uri = make_uri("impl-a", "baseline")
    missing_prd_uri = make_uri("prd-missing", "baseline")
    graph.add_spec(
        Spec(
            uri=impl_uri,
            title="Impl A",
            type="impl",
            version="baseline",
            chunk_id="impl-a",
            file="impl/a",
        )
    )
    graph.edges.append(Edge(src=impl_uri, dst=missing_prd_uri, rel="implements"))
    graph.save(specgraph_path(tmp_path, "baseline"))

    with pytest.raises(VersionManagerError) as exc:
        VersionManager(tmp_path)._assert_no_orphan_impl_refs()

    assert "orphan impl @refs" in str(exc.value)
    assert "impl-a->prd-missing" in str(exc.value)
