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


def _baseline_chunk(chunk_id: str) -> str:
    return (
        f"<!-- @id:{chunk_id} -->\n## Baseline\n\n<!-- @summary: baseline -->\n\n"
        "### 概述\n\n内容\n\n"
        "### 业务规则\n\n规则\n\n"
        "### 验收标准\n\n验收\n\n"
        "### 边界与非目标\n\n边界\n"
    )


def _seed_baseline(root: Path, runner: CliRunner) -> None:
    (root / "docs" / "prd" / "global.md").write_text(_baseline_chunk("prd-foo"), encoding="utf-8")
    assert _run(runner, "reindex").exit_code == 0


def test_candidates_written_to_workspace(cli_project: Path, tmp_path: Path):
    runner = CliRunner()
    _seed_baseline(cli_project, runner)
    _parse(_run(runner, "prdv1", "create", "candidate-test").output)
    source = tmp_path / "candidates.yaml"
    candidate_data = {
        "modify_candidates": [
            {
                "new_id": "prd-new-foo",
                "overrides": "prd-foo",
                "confidence": 0.91,
                "reason": "same feature",
            }
        ],
        "delete_candidates": [],
        "adds": [
            {"new_id": "prd-new-bar", "reason": "new feature"},
        ],
    }
    source.write_text(yaml.safe_dump(candidate_data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    res = _run(runner, "prdv1", "resolve-candidates", "--from-file", str(source))
    payload = _parse(res.output)

    assert res.exit_code == 0
    assert payload["data"]["file"] == "versions/v1.0/.candidates.yaml"
    target = cli_project / "versions" / "v1.0" / ".candidates.yaml"
    assert yaml.safe_load(target.read_text(encoding="utf-8")) == candidate_data


def test_chunk_id_collision_baseline(cli_project: Path, tmp_path: Path):
    runner = CliRunner()
    _seed_baseline(cli_project, runner)
    _parse(_run(runner, "prdv1", "create", "candidate-test").output)
    source = tmp_path / "candidates.yaml"
    source.write_text(
        yaml.safe_dump(
            {
                "modify_candidates": [],
                "delete_candidates": [],
                "adds": [{"new_id": "prd-foo", "reason": "collision"}],
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    res = _run(runner, "prdv1", "resolve-candidates", "--from-file", str(source))
    payload = _parse(res.output)

    assert res.exit_code == 1
    assert payload["code"] == "CHUNK_ID_COLLISION"
