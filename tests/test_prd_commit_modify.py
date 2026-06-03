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


def _prd_chunk(chunk_id: str, heading: str = "测试", summary: str = "测试摘要") -> str:
    return (
        f"<!-- @id:{chunk_id} -->\n## {heading}\n\n<!-- @summary: {summary} -->\n\n"
        "### 概述\n\n内容\n\n"
        "### 业务规则\n\n规则\n\n"
        "### 验收标准\n\n验收\n\n"
        "### 边界与非目标\n\n边界\n"
    )


def _seed_baseline(root: Path, runner: CliRunner) -> None:
    (root / "docs" / "prd" / "global.md").write_text(
        _prd_chunk("prd-foo", "Foo", "foo baseline"),
        encoding="utf-8",
    )
    assert _run(runner, "reindex").exit_code == 0


def _prepare_version_prd(runner: CliRunner, chunk_ids: list[str]) -> str:
    req = _parse(_run(runner, "prd", "create", "modify-test").output)["data"]["req_id"]
    draft = "\n\n".join(_prd_chunk(chunk_id, chunk_id, f"{chunk_id} summary") for chunk_id in chunk_ids)
    assert _run(runner, "prd", "save-draft", req, "--content", draft).exit_code == 0
    assert _run(runner, "prd", "confirm", req, "--file", "prd/modify-test").exit_code == 0
    return req


def _rewrite_index(root: Path, version: str, mutator) -> None:
    path = root / ".meta" / f"chunks-index-{version}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    mutator(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_modify_overrides_must_exist(cli_project: Path):
    runner = CliRunner()
    _seed_baseline(cli_project, runner)
    req = _prepare_version_prd(runner, ["prd-new-one"])
    _rewrite_index(
        cli_project,
        "v1.0",
        lambda data: data["chunks"][0].update({"action": "modify", "overrides": "prd-not-exist"}),
    )

    res = _run(runner, "prd", "commit", "prd/modify-test", "-m", "msg", "--req-id", req)
    payload = _parse(res.output)

    assert res.exit_code == 1
    assert payload["code"] == "OVERRIDES_NOT_IN_BASELINE"


def test_modify_requires_overrides(cli_project: Path):
    runner = CliRunner()
    _seed_baseline(cli_project, runner)
    req = _prepare_version_prd(runner, ["prd-new-one"])
    _rewrite_index(
        cli_project,
        "v1.0",
        lambda data: data["chunks"][0].update({"action": "modify", "overrides": None}),
    )

    res = _run(runner, "prd", "commit", "prd/modify-test", "-m", "msg", "--req-id", req)
    payload = _parse(res.output)

    assert res.exit_code == 1
    assert payload["code"] == "OVERRIDES_REQUIRED"


def test_duplicate_overrides_target(cli_project: Path):
    runner = CliRunner()
    _seed_baseline(cli_project, runner)
    req = _prepare_version_prd(runner, ["prd-new-one", "prd-new-two"])

    def mutate(data: dict) -> None:
        for chunk in data["chunks"]:
            chunk.update({"action": "modify", "overrides": "prd-foo"})

    _rewrite_index(cli_project, "v1.0", mutate)

    res = _run(runner, "prd", "commit", "prd/modify-test", "-m", "msg", "--req-id", req)
    payload = _parse(res.output)

    assert res.exit_code == 1
    assert payload["code"] == "DUPLICATE_OVERRIDES_TARGET"


def test_delete_overrides_validated_too(cli_project: Path):
    runner = CliRunner()
    _seed_baseline(cli_project, runner)
    req = _prepare_version_prd(runner, ["prd-new-one"])
    _rewrite_index(
        cli_project,
        "v1.0",
        lambda data: data["chunks"][0].update({"action": "delete", "overrides": "prd-not-exist"}),
    )

    res = _run(runner, "prd", "commit", "prd/modify-test", "-m", "msg", "--req-id", req)
    payload = _parse(res.output)

    assert res.exit_code == 1
    assert payload["code"] == "OVERRIDES_NOT_IN_BASELINE"


def test_legitimate_modify_passes(cli_project: Path):
    runner = CliRunner()
    _seed_baseline(cli_project, runner)
    req = _prepare_version_prd(runner, ["prd-new-one"])
    _rewrite_index(
        cli_project,
        "v1.0",
        lambda data: data["chunks"][0].update({"action": "modify", "overrides": "prd-foo"}),
    )

    res = _run(runner, "prd", "commit", "prd/modify-test", "-m", "msg", "--req-id", req)
    payload = _parse(res.output)

    assert res.exit_code == 0
    assert payload["ok"] is True
    assert payload["data"]["commit_id"] == "c1"
