from __future__ import annotations

import json
from pathlib import Path

import pytest
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


def _prd_body(summary: str = "") -> str:
    return (
        "<!-- @id:prd-summary-demo -->\n## Demo\n\n"
        + summary
        + "### 概述\n\nBody\n\n"
        "### 业务规则\n\nRule\n\n"
        "### 验收标准\n\nAcceptance\n\n"
        "### 边界与非目标\n\nBoundary\n"
    )


def _prepare_prd(runner: CliRunner, draft: str) -> str:
    req = _parse(_run(runner, "prdv1", "create", "summary").output)["data"]["req_id"]
    assert _run(runner, "prdv1", "save-draft", req, "--content", draft).exit_code == 0
    assert _run(runner, "prdv1", "confirm", req, "--file", "summary").exit_code == 0
    return req


def test_commit_blocks_when_summary_missing(cli_project: Path):
    runner = CliRunner()
    req = _prepare_prd(
        runner,
        _prd_body(),
    )

    res = _run(runner, "prdv1", "commit", "prd/summary", "-m", "msg", "--req-id", req)
    payload = _parse(res.output)

    assert res.exit_code == 1
    assert payload["ok"] is False
    assert payload["code"] == "SUMMARY_REQUIRED"
    assert "prd-summary-demo" in payload["error"]


def test_commit_blocks_when_summary_too_long(cli_project: Path):
    runner = CliRunner()
    req = _prepare_prd(
        runner,
        _prd_body("<!-- @summary: " + "长" * 121 + " -->\n\n"),
    )

    res = _run(runner, "prdv1", "commit", "prd/summary", "-m", "msg", "--req-id", req)
    payload = _parse(res.output)

    assert res.exit_code == 1
    assert payload["ok"] is False
    assert payload["code"] == "SUMMARY_TOO_LONG"
    assert "prd-summary-demo" in payload["error"]
