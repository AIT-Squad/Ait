from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from ait.cli import main


@pytest.fixture
def cli_project(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "project-docs"
    for d in [
        "docs/prd",
        "docs/impl",
        "versions",
        ".meta/versions",
        ".meta/changes",
        ".meta/requirements",
    ]:
        (root / d).mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    return root


def _parse(out: str) -> dict:
    return json.loads(out.strip().splitlines()[-1])


def _run(runner: CliRunner, *args: str):
    return runner.invoke(main, [*args], catch_exceptions=False)


def _prd_chunk(chunk_id: str) -> str:
    return (
        f"<!-- @id:{chunk_id} -->\n## New Foo\n\n<!-- @summary: new foo -->\n\n"
        "### 概述\n\n内容\n\n"
        "### 业务规则\n\n规则\n\n"
        "### 验收标准\n\n验收\n\n"
        "### 边界与非目标\n\n边界\n"
    )


def _seed_baseline(root: Path, runner: CliRunner) -> None:
    (root / "docs" / "prd" / "global.md").write_text(_prd_chunk("prd-foo"), encoding="utf-8")
    assert _run(runner, "reindex").exit_code == 0


def test_save_draft_propagates_action_overrides(cli_project: Path, tmp_path: Path):
    runner = CliRunner()
    _seed_baseline(cli_project, runner)
    req_id = _parse(_run(runner, "prdv1", "create", "candidate-sync").output)["data"]["req_id"]
    source = tmp_path / "candidates.yaml"
    source.write_text(
        yaml.safe_dump(
            {
                "modify_candidates": [
                    {
                        "new_id": "prd-new-foo",
                        "overrides": "prd-foo",
                        "confidence": 0.94,
                        "reason": "same capability",
                    }
                ],
                "delete_candidates": [],
                "adds": [],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert _run(runner, "prdv1", "resolve-candidates", "--from-file", str(source)).exit_code == 0
    assert _run(runner, "prdv1", "save-draft", req_id, "--content", _prd_chunk("prd-new-foo")).exit_code == 0
    assert _run(runner, "prdv1", "confirm", req_id, "--file", "candidate-sync").exit_code == 0

    index = yaml.safe_load((cli_project / ".meta" / "chunks-index-v1.0.yaml").read_text(encoding="utf-8"))
    entry = next(chunk for chunk in index["chunks"] if chunk["id"] == "prd-new-foo")

    assert entry["action"] == "modify"
    assert entry["overrides"] == "prd-foo"
