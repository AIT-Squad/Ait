from __future__ import annotations

from pathlib import Path

from ait.chunk_parser import parse_file
from ait.new_model_manager import NewModelManager
from ait.specgraph import load_specgraph
from ait.version_manager import VersionManager


def test_new_model_merge_preserves_file_containers_and_edges(tmp_path: Path):
    root = tmp_path
    (root / "docs").mkdir()
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    vm = VersionManager(root)
    vm.create("v9.0")
    mgr = NewModelManager(root)

    prd_path = vm.write_version_file(
        "v9.0",
        "prd/[PRD]-book_system",
        "<!-- @id:[PRD]-book_system -->\n## Book System\n",
    )
    prd = parse_file(prd_path, vm.versions_dir / "v9.0").chunks[0]
    vm.add_chunk("v9.0", chunk=prd, action="add")

    mgr.create_fsd(
        "v9.0",
        "[FSD]-book_management",
        "<!-- @id:[FSD]-book_management -->\n## Book Management\n\n"
        "<!-- @id:[FSD]-book_management:book_model -->\n## Book Model\n",
    )
    mgr.create_tdd(
        "v9.0",
        "[TDD]-book_model",
        "<!-- @id:[TDD]-book_model -->\n## Book Model TDD\n\n"
        "```yaml\n"
        "target_file: app/models/book.py\n"
        "```\n",
    )
    mgr.add_edge("v9.0", "[FSD]-book_management:book_model", "[TDD]-book_model", "details")

    vm.stage(
        "v9.0",
        [
            "[PRD]-book_system",
            "[FSD]-book_management",
            "[FSD]-book_management:book_model",
            "[TDD]-book_model",
        ],
    )
    vm.commit("v9.0", "commit new-model docs")

    result = vm.merge("v9.0", conflict_policy="use-version")

    assert result.status == "completed"
    assert (root / "docs" / "prd" / "[PRD]-book_system.md").exists()
    assert not (root / "docs" / "prd" / "global.md").exists()
    assert (root / "docs" / "fsd" / "[FSD]-book_management.md").exists()
    assert (root / "docs" / "tdd" / "[TDD]-book_model.md").exists()

    vm._merge_specgraph_to_baseline("v9.0")
    baseline_graph = load_specgraph(root, "baseline")
    edge_triples = {
        (
            baseline_graph.specs[edge.src].chunk_id,
            edge.rel,
            baseline_graph.specs[edge.dst].chunk_id,
        )
        for edge in baseline_graph.edges
    }
    assert ("[FSD]-book_management:book_model", "details", "[TDD]-book_model") in edge_triples
