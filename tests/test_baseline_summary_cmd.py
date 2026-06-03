from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ait.cli import main
from ait.schemas import BaselineChunkEntry, BaselineIndex
from ait.yaml_io import save_model


@pytest.fixture
def cli_project(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "project-docs"
    for d in ["docs/prd", "docs/impl", "versions", ".meta/versions", ".meta/changes"]:
        (root / d).mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    return root


def _parse(out: str) -> dict:
    return json.loads(out.strip().splitlines()[-1])


def test_scope_prd(cli_project: Path):
    save_model(
        cli_project / ".meta" / "chunks-index.yaml",
        BaselineIndex(
            chunks=[
                BaselineChunkEntry(id="prd-a", file="prd/a", heading="A", level=2, summary="PRD A"),
                BaselineChunkEntry(id="impl-a", file="impl/a", heading="A impl", level=2, summary="Impl A"),
            ]
        ),
    )
    res = CliRunner().invoke(main, ["baseline-summary", "--scope", "prd", "--format", "json"], catch_exceptions=False)
    payload = _parse(res.output)

    assert res.exit_code == 0
    assert payload["ok"] is True
    assert [item["id"] for item in payload["data"]] == ["prd-a"]
    assert set(payload["data"][0]) == {"id", "heading", "summary"}


def test_token_budget(cli_project: Path):
    save_model(
        cli_project / ".meta" / "chunks-index.yaml",
        BaselineIndex(
            chunks=[
                BaselineChunkEntry(
                    id=f"prd-{i}",
                    file=f"prd/{i}",
                    heading=f"Heading {i}",
                    level=2,
                    summary="s" * 80,
                )
                for i in range(30)
            ]
        ),
    )
    res = CliRunner().invoke(main, ["baseline-summary", "--format", "yaml"], catch_exceptions=False)

    assert res.exit_code == 0
    assert len(res.output.encode("utf-8")) <= 5 * 1024


def test_index_schema_violation_for_overlong_summary(cli_project: Path):
    (cli_project / ".meta" / "chunks-index.yaml").write_text(
        """version: 1
scope: global
updated: null
chunks:
- id: prd-a
  file: prd/a
  heading: A
  level: 2
  summary: """ + "x" * 121 + "\n",
        encoding="utf-8",
    )

    res = CliRunner().invoke(main, ["baseline-summary", "--format", "json"], catch_exceptions=False)
    payload = _parse(res.output)

    assert res.exit_code == 1
    assert payload["ok"] is False
    assert payload["code"] == "INDEX_SCHEMA_VIOLATION"