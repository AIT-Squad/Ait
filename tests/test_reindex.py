"""Tests for `ait reindex` CLI command and the underlying rebuild flow."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ait.cli import main


@pytest.fixture
def project_root(tmp_path: Path, monkeypatch) -> Path:
    docs_root = tmp_path / "project-docs"
    (docs_root / "docs" / "prd").mkdir(parents=True)
    (docs_root / "docs" / "impl").mkdir(parents=True)
    (docs_root / ".meta").mkdir()
    monkeypatch.chdir(tmp_path)
    return docs_root


def _run_reindex(runner: CliRunner, root: Path):
    result = runner.invoke(
        main, ["reindex"], catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["ok"] is True, payload
    return payload["data"]


def test_reindex_empty_docs(project_root: Path):
    """Empty docs/ → zero chunks, baseline index + specgraph written (links deprecated)."""
    runner = CliRunner()
    data = _run_reindex(runner, project_root)

    assert data["chunks"] == 0
    assert data["specs"] == 0
    assert data["baseline_index"] == ".meta/chunks-index.yaml"
    assert data["specgraph_index"] == ".meta/specgraph.yaml"
    assert (project_root / ".meta" / "chunks-index.yaml").exists()
    assert (project_root / ".meta" / "specgraph.yaml").exists()


def test_reindex_single_file_multiple_blocks(project_root: Path):
    """A single PRD file with N blocks should yield N baseline entries."""
    (project_root / "docs" / "prd" / "demo.md").write_text(
        "# Demo\n\n"
        "<!-- @id:prd-demo-overview -->\n## 概述\n\nfoo\n\n"
        "<!-- @id:prd-demo-rules -->\n## 规则\n\nbar\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    data = _run_reindex(runner, project_root)

    assert data["chunks"] == 2
    assert data["specs"] == 2


def test_reindex_picks_up_cross_file_refs(project_root: Path):
    """@ref across PRD and impl files should produce an implements edge in specgraph."""
    (project_root / "docs" / "prd" / "demo.md").write_text(
        "<!-- @id:prd-demo-feature -->\n## 功能\n\n描述\n",
        encoding="utf-8",
    )
    (project_root / "docs" / "impl" / "api.md").write_text(
        "<!-- @id:impl-api-demo -->\n## 接口\n\n"
        "<!-- @ref:prd/demo#prd-demo-feature rel:implements -->\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    data = _run_reindex(runner, project_root)

    assert data["chunks"] == 2
    assert data["edges"] == 1

    import yaml

    graph = yaml.safe_load(
        (project_root / ".meta" / "specgraph.yaml").read_text(encoding="utf-8")
    )
    edge = graph["edges"][0]
    assert edge["src"] == "spec:impl:baseline:impl-api-demo"
    assert edge["dst"] == "spec:prd:baseline:prd-demo-feature"
    assert edge["rel"] == "implements"


def test_reindex_supports_new_model_fsd_tdd_specs(project_root: Path):
    (project_root / "docs" / "fsd").mkdir()
    (project_root / "docs" / "tdd").mkdir()
    (project_root / "docs" / "fsd" / "[FSD]-book_management.md").write_text(
        "<!-- @id:[FSD]-book_management -->\n"
        "## Book Management\n\n"
        "<!-- @ref:tdd/[TDD]-book_model#[TDD]-book_model rel:details -->\n\n"
        "<!-- @id:[FSD]-book_management:book_model -->\n"
        "## Book Model\n\n",
        encoding="utf-8",
    )
    (project_root / "docs" / "tdd" / "[TDD]-book_model.md").write_text(
        "<!-- @id:[TDD]-book_model -->\n"
        "## Book Model TDD\n\n"
        "target_file: app/models/book.py\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    data = _run_reindex(runner, project_root)

    assert data["chunks"] == 3
    assert data["edges"] == 1

    import yaml

    graph = yaml.safe_load(
        (project_root / ".meta" / "specgraph.yaml").read_text(encoding="utf-8")
    )
    specs = {spec["chunk_id"]: spec for spec in graph["specs"]}
    assert specs["[FSD]-book_management"]["type"] == "fsd"
    assert specs["[FSD]-book_management:book_model"]["type"] == "fsd"
    assert specs["[TDD]-book_model"]["type"] == "tdd"
    assert graph["edges"][0]["rel"] == "details"


def test_reindex_is_idempotent(project_root: Path):
    """Running reindex twice should yield identical index contents."""
    (project_root / "docs" / "prd" / "a.md").write_text(
        "<!-- @id:prd-a-one -->\n## One\n\nx\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    _run_reindex(runner, project_root)
    first = (project_root / ".meta" / "chunks-index.yaml").read_text(encoding="utf-8")

    _run_reindex(runner, project_root)
    second = (project_root / ".meta" / "chunks-index.yaml").read_text(encoding="utf-8")

    import yaml

    a = yaml.safe_load(first)
    b = yaml.safe_load(second)
    assert a["chunks"] == b["chunks"]


def test_reindex_overwrites_stale_index(project_root: Path):
    """If a block is removed from docs/, reindex should drop it from the index."""
    prd = project_root / "docs" / "prd" / "demo.md"
    prd.write_text(
        "<!-- @id:prd-demo-a -->\n## A\n\nx\n\n"
        "<!-- @id:prd-demo-b -->\n## B\n\ny\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    data1 = _run_reindex(runner, project_root)
    assert data1["chunks"] == 2

    prd.write_text(
        "<!-- @id:prd-demo-a -->\n## A\n\nx\n",
        encoding="utf-8",
    )
    data2 = _run_reindex(runner, project_root)
    assert data2["chunks"] == 1
