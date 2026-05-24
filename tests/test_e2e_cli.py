"""End-to-end CLI tests covering the full 7-command workflow.

Uses click's CliRunner to exercise the same code paths a Skill / IDE would,
asserting JSON output contracts and final on-disk state.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ait.cli import main


@pytest.fixture
def cli_project(tmp_path: Path, monkeypatch) -> Path:
    docs_root = tmp_path / "project-docs"
    for d in [
        "docs/prd",
        "docs/impl",
        "versions",
        ".meta/versions",
        ".meta/changes",
        ".meta/requirements",
    ]:
        (docs_root / d).mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    return docs_root


def _run(runner: CliRunner, project: Path, *args: str, input_: str | None = None):
    result = runner.invoke(
        main,
        [*args],
        input=input_,
        catch_exceptions=False,
    )
    assert result.exit_code in (0, 1), result.output
    return result


def _parse(out: str) -> dict:
    return json.loads(out.strip().splitlines()[-1])


def test_end_to_end_happy_path(cli_project: Path):
    runner = CliRunner()
    root = cli_project

    # 1. /ait:prd <title>  → create requirement (+ auto version)
    res = _run(runner, root, "prd", "create", "推荐功能")
    data = _parse(res.output)["data"]
    req_id = data["req_id"]
    version = data["version"]
    assert version == "v1.0"

    # 2. save the AI-discussed PRD draft
    draft = (
        "<!-- @id:prd-recommend-overview -->\n## 概述\n\n基于借阅历史推荐图书。\n\n"
        "<!-- @id:prd-recommend-rules -->\n## 业务规则\n\n不推荐已借阅过的图书。\n"
    )
    res = _run(
        runner,
        root,
        "prd",
        "save-draft",
        req_id,
        "--content",
        draft,
    )
    parsed = _parse(res.output)["data"]
    assert parsed["block_count"] == 2
    assert "prd-recommend-overview" in parsed["block_ids"]

    # 3. confirm → write to version workspace
    res = _run(
        runner,
        root,
        "prd",
        "confirm",
        req_id,
        "--file",
        "prd/recommend",
    )
    parsed = _parse(res.output)["data"]
    assert parsed["version"] == version
    assert parsed["file"] == "prd/recommend"
    assert sorted(parsed["block_ids"]) == ["prd-recommend-overview", "prd-recommend-rules"]
    assert (root / "versions" / version / "prd" / "recommend.md").exists()

    # 4. /ait:prd commit
    res = _run(
        runner,
        root,
        "prd",
        "commit",
        "prd/recommend",
        "-m",
        "首版推荐 PRD",
        "--req-id",
        req_id,
    )
    parsed = _parse(res.output)["data"]
    assert parsed["commit_id"] == "c1"
    assert len(parsed["changes"]) == 2  # two chg-NNN.yaml files

    # 5. /ait:impl <prd-block-id> — generate impl
    impl_content = (
        "<!-- @id:impl-api-recommend -->\n"
        "## 推荐接口\n\nGET /api/v1/books/recommend\n"
    )
    res = _run(
        runner,
        root,
        "impl",
        "create",
        "prd-recommend-overview",
        "--content",
        impl_content,
        "--req-id",
        req_id,
    )
    parsed = _parse(res.output)["data"]
    assert parsed["block_ids"] == ["impl-api-recommend"]
    impl_file_path = root / "versions" / version / "impl" / "api-contracts.md"
    assert impl_file_path.exists()
    text = impl_file_path.read_text(encoding="utf-8")
    assert "@ref:prd/recommend#prd-recommend-overview rel:implements" in text

    # 6. /ait:impl commit
    res = _run(
        runner,
        root,
        "impl",
        "commit",
        "impl-api-recommend",
        "-m",
        "推荐 API",
        "--req-id",
        req_id,
    )
    parsed = _parse(res.output)["data"]
    assert parsed["commit_id"] == "c2"

    # 7. /ait:version merge
    res = _run(runner, root, "version", "merge", version)
    parsed = _parse(res.output)["data"]
    assert parsed["status"] == "completed"
    assert "prd-recommend-overview" in parsed["merged_blocks"]
    assert "prd-recommend-rules" in parsed["merged_blocks"]
    assert "impl-api-recommend" in parsed["merged_blocks"]

    # Final assertions on baseline state
    baseline_prd = root / "docs" / "prd" / "recommend.md"
    baseline_impl = root / "docs" / "impl" / "api-contracts.md"
    assert baseline_prd.exists()
    assert baseline_impl.exists()
    prd_text = baseline_prd.read_text(encoding="utf-8")
    impl_text = baseline_impl.read_text(encoding="utf-8")
    assert "基于借阅历史推荐图书" in prd_text
    assert "GET /api/v1/books/recommend" in impl_text

    # Snapshot exists
    snapshot = root / ".meta" / "snapshots" / version / "docs" / "prd" / "recommend.md"
    assert snapshot.exists()

    # Baseline index updated
    baseline_index = root / ".meta" / "blocks-index.yaml"
    assert baseline_index.exists()
    assert "prd-recommend-overview" in baseline_index.read_text(encoding="utf-8")


def test_show_returns_block_after_merge(cli_project: Path):
    runner = CliRunner()
    root = cli_project

    _run(runner, root, "prd", "create", "test")
    data = _parse(_run(runner, root, "prd", "create", "test2").output)
    req_id = data["data"]["req_id"]

    _run(
        runner,
        root,
        "prd",
        "save-draft",
        req_id,
        "--content",
        "<!-- @id:prd-test-overview -->\n## 概述\n\nbody",
    )
    _run(runner, root, "prd", "confirm", req_id, "--file", "prd/testing")

    res = _run(runner, root, "prd", "show", "prd/testing")
    parsed = _parse(res.output)["data"]
    assert parsed["source"] == "version"
    block_ids = [b["id"] for b in parsed["blocks"]]
    assert "prd-test-overview" in block_ids

    res = _run(runner, root, "prd", "show", "prd/testing", "prd-test-overview")
    parsed = _parse(res.output)["data"]
    assert parsed["block"]["heading"] == "概述"


def test_context_command_returns_l1_only_when_no_links(cli_project: Path):
    runner = CliRunner()
    root = cli_project

    _run(runner, root, "prd", "create", "ctx-test")
    data = _parse(_run(runner, root, "prd", "create", "ctx-test-2").output)
    req_id = data["data"]["req_id"]

    _run(
        runner,
        root,
        "prd",
        "save-draft",
        req_id,
        "--content",
        "<!-- @id:prd-ctxtest-overview -->\n## 概述\n\nbody",
    )
    _run(runner, root, "prd", "confirm", req_id, "--file", "prd/ctxtest")
    _run(runner, root, "prd", "commit", "prd/ctxtest", "-m", "msg", "--req-id", req_id)

    res = _run(runner, root, "context", "prd-ctxtest-overview")
    parsed = _parse(res.output)["data"]
    assert parsed["l1"]["id"] == "prd-ctxtest-overview"
    assert parsed["l2"] == []


def test_cli_returns_error_json_for_missing_block(cli_project: Path):
    runner = CliRunner()
    root = cli_project

    res = runner.invoke(
        main,
        ["prd", "show", "prd/nonexistent"],
        catch_exceptions=False,
    )
    payload = _parse(res.output)
    assert payload["ok"] is False
    assert payload["code"] == "NOT_FOUND"
    assert res.exit_code == 1
