from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from ait.cli import main
from ait.new_model_validator import validate_prd_fsd_tdd_graph
from ait.specgraph import Edge, Spec, SpecGraph, make_uri


def _spec(chunk_id: str, file: str, title: str = "") -> Spec:
    uri = make_uri(chunk_id, "baseline", file)
    return Spec(
        uri=uri,
        title=title or chunk_id,
        type=uri.split(":", 3)[1],
        version="baseline",
        chunk_id=chunk_id,
        file=file,
    )


def _add_spec(graph: SpecGraph, chunk_id: str, file: str) -> str:
    spec = _spec(chunk_id, file)
    graph.add_spec(spec)
    return spec.uri


def test_new_model_validator_accepts_valid_graph():
    graph = SpecGraph()
    prd = _add_spec(graph, "[PRD]-book_system", "prd/[PRD]-book_system")
    root_fsd = _add_spec(graph, "[FSD]-book_management", "fsd/[FSD]-book_management")
    catalog_split = _add_spec(graph, "[FSD]-book_management:book_catalog", "fsd/[FSD]-book_management")
    storage_split = _add_spec(graph, "[FSD]-book_management:persistence", "fsd/[FSD]-book_management")
    catalog_fsd = _add_spec(graph, "[FSD]-book_management-book_catalog", "fsd/[FSD]-book_management-book_catalog")
    storage_fsd = _add_spec(graph, "[FSD]-book_management-persistence", "fsd/[FSD]-book_management-persistence")

    graph.add_edge(prd, root_fsd, "decomposes")
    graph.add_edge(catalog_split, catalog_fsd, "decomposes")
    graph.add_edge(storage_split, storage_fsd, "decomposes")
    graph.add_edge(catalog_split, storage_split, "depends_on")

    assert validate_prd_fsd_tdd_graph(graph) == []


def test_new_model_validator_rejects_cross_level_dependency():
    graph = SpecGraph()
    a = _add_spec(graph, "[FSD]-book_management:book_catalog", "fsd/[FSD]-book_management")
    b = _add_spec(graph, "[FSD]-loan_workflow:loan_service", "fsd/[FSD]-loan_workflow")

    graph.add_edge(a, b, "depends_on")

    violations = validate_prd_fsd_tdd_graph(graph)

    assert [v.code for v in violations] == ["DEPENDS_ON_CROSS_LEVEL"]
    assert "lift the dependency" in violations[0].message


def test_new_model_validator_rejects_mixed_fsd_children():
    graph = SpecGraph()
    catalog_split = _add_spec(graph, "[FSD]-book_management:book_catalog", "fsd/[FSD]-book_management")
    loan_split = _add_spec(graph, "[FSD]-book_management:loan_service", "fsd/[FSD]-book_management")
    catalog_fsd = _add_spec(graph, "[FSD]-book_management-book_catalog", "fsd/[FSD]-book_management-book_catalog")
    loan_tdd = _add_spec(graph, "[TDD]-book_management-loan_service", "tdd/[TDD]-book_management-loan_service")

    graph.add_edge(catalog_split, catalog_fsd, "decomposes")
    graph.add_edge(loan_split, loan_tdd, "details")

    violations = validate_prd_fsd_tdd_graph(graph)

    assert any(v.code == "FSD_MIXED_CHILDREN" for v in violations)


def test_specgraph_validate_new_model_cli(tmp_path: Path, monkeypatch):
    project_docs_root = tmp_path / "project-docs"
    (project_docs_root / ".meta").mkdir(parents=True)
    monkeypatch.chdir(project_docs_root.parent)
    (project_docs_root / "docs" / "prd").mkdir(parents=True)
    (project_docs_root / "docs" / "fsd").mkdir(parents=True)
    (project_docs_root / "docs" / "prd" / "[PRD]-book_system.md").write_text(
        "<!-- @id:[PRD]-book_system -->\n"
        "## Book System\n\n"
        "<!-- @ref:fsd/[FSD]-book_management#[FSD]-book_management rel:decomposes -->\n",
        encoding="utf-8",
    )
    (project_docs_root / "docs" / "fsd" / "[FSD]-book_management.md").write_text(
        "<!-- @id:[FSD]-book_management -->\n"
        "## Book Management\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    reindex = runner.invoke(main, ["reindex"], catch_exceptions=False)
    assert reindex.exit_code == 0, reindex.output

    result = runner.invoke(main, ["specgraph", "validate-new-model"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert payload["violations"] == []
