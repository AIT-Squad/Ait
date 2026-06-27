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


def _prd_chunk(chunk_id: str, heading: str, summary: str, body: str, *, no_impl: bool = False) -> str:
    marker = "<!-- @prd-no-impl -->\n\n" if no_impl else ""
    return (
        f"<!-- @id:{chunk_id} -->\n## {heading}\n\n<!-- @summary: {summary} -->\n\n"
        + marker
        + f"### 概述\n\n{body}\n\n"
        "### 业务规则\n\n规则\n\n"
        "### 验收标准\n\n验收\n\n"
        "### 边界与非目标\n\n边界\n"
    )


def test_end_to_end_happy_path(cli_project: Path):
    runner = CliRunner()
    root = cli_project

    # 1. /ait:prd <title>  → create requirement (+ auto version)
    res = _run(runner, root, "prdv1", "create", "推荐功能")
    data = _parse(res.output)["data"]
    req_id = data["req_id"]
    version = data["version"]
    assert version == "v1.0"

    # 2. save the AI-discussed PRD draft
    draft = (
        _prd_chunk("prd-recommend-overview", "概述", "推荐功能概述", "基于借阅历史推荐图书。")
        + "\n"
        + _prd_chunk("prd-recommend-rules", "业务规则", "推荐业务规则", "不推荐已借阅过的图书。", no_impl=True)
    )
    res = _run(
        runner,
        root,
        "prdv1",
        "save-draft",
        req_id,
        "--content",
        draft,
    )
    parsed = _parse(res.output)["data"]
    assert parsed["chunk_count"] == 2
    assert "prd-recommend-overview" in parsed["chunk_ids"]

    # 3. confirm → write to version workspace
    res = _run(
        runner,
        root,
        "prdv1",
        "confirm",
        req_id,
        "--file",
        "recommend",
    )
    parsed = _parse(res.output)["data"]
    assert parsed["version"] == version
    assert parsed["file"] == "prd/recommend"
    assert sorted(parsed["chunk_ids"]) == ["prd-recommend-overview", "prd-recommend-rules"]
    assert (root / "versions" / version / "prd" / "recommend.md").exists()

    # 4. /ait:prd commit
    res = _run(
        runner,
        root,
        "prdv1",
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
        "<!-- @id:impl-recommend-overview-api -->\n"
        "## 推荐接口\n\n<!-- @summary: 推荐接口实现 -->\n\nGET /api/v1/books/recommend\n"
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
    assert parsed["chunk_ids"] == ["impl-recommend-overview-api"]
    impl_file_path = root / "versions" / version / "impl" / "recommend.md"
    assert impl_file_path.exists()
    text = impl_file_path.read_text(encoding="utf-8")
    assert "@ref:prd/recommend#prd-recommend-overview rel:implements" in text

    # 6. /ait:impl commit
    res = _run(
        runner,
        root,
        "impl",
        "commit",
        "impl-recommend-overview-api",
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
    assert "prd-recommend-overview" in parsed["merged_chunks"]
    assert "prd-recommend-rules" in parsed["merged_chunks"]
    assert "impl-recommend-overview-api" in parsed["merged_chunks"]

    # Final assertions on baseline state
    # PRD baseline 单文件化：v1.6 起所有 PRD chunks 被收敛到 docs/prd/global.md。
    # 版本工作区仍可以使用 prd/recommend，但 baseline 只有 prd/global.md。
    baseline_prd = root / "docs" / "prd" / "global.md"
    baseline_impl = root / "docs" / "impl" / "recommend.md"
    assert baseline_prd.exists()
    assert baseline_impl.exists()
    prd_text = baseline_prd.read_text(encoding="utf-8")
    impl_text = baseline_impl.read_text(encoding="utf-8")
    assert "基于借阅历史推荐图书" in prd_text
    assert "GET /api/v1/books/recommend" in impl_text

    # Snapshot exists — 版本侧仍是 prd/recommend.md（快照是 docs/ 的拷贝）
    snapshot = root / ".meta" / "snapshots" / version / "docs" / "prd" / "global.md"
    assert snapshot.exists()

    # Baseline index updated
    baseline_index = root / ".meta" / "chunks-index.yaml"
    assert baseline_index.exists()
    assert "prd-recommend-overview" in baseline_index.read_text(encoding="utf-8")


def test_show_returns_block_after_merge(cli_project: Path):
    runner = CliRunner()
    root = cli_project

    _run(runner, root, "prdv1", "create", "test")
    data = _parse(_run(runner, root, "prdv1", "create", "test2").output)
    req_id = data["data"]["req_id"]

    _run(
        runner,
        root,
        "prdv1",
        "save-draft",
        req_id,
        "--content",
        "<!-- @id:prd-test-overview -->\n## 概述\n\nbody",
    )
    _run(runner, root, "prdv1", "confirm", req_id, "--file", "testing")

    res = _run(runner, root, "prdv1", "show", "prd/testing")
    parsed = _parse(res.output)["data"]
    assert parsed["source"] == "version"
    chunk_ids = [b["id"] for b in parsed["chunks"]]
    assert "prd-test-overview" in chunk_ids

    res = _run(runner, root, "prdv1", "show", "prd/testing", "prd-test-overview")
    parsed = _parse(res.output)["data"]
    assert parsed["chunk"]["heading"] == "概述"


def test_file_options_accept_names_not_paths(cli_project: Path):
    runner = CliRunner()
    root = cli_project

    data = _parse(_run(runner, root, "prdv1", "create", "path-check").output)
    req_id = data["data"]["req_id"]
    version = data["data"]["version"]

    _run(
        runner,
        root,
        "prdv1",
        "save-draft",
        req_id,
        "--content",
        _prd_chunk("prd-path-check", "Overview", "path check", "body"),
    )

    res = _run(runner, root, "prdv1", "confirm", req_id, "--file", "prd/path-check")
    payload = _parse(res.output)
    assert res.exit_code == 1
    assert payload["code"] == "INVALID_FILE_NAME"

    res = _run(runner, root, "prdv1", "confirm", req_id, "--file", "path-check")
    payload = _parse(res.output)["data"]
    assert payload["file"] == "prd/path-check"
    assert (root / "versions" / version / "prd" / "path-check.md").exists()
    assert not (root / "versions" / version / "path-check.md").exists()

    _run(runner, root, "prdv1", "commit", "prd/path-check", "-m", "msg", "--req-id", req_id)

    impl_content = (
        "<!-- @id:impl-path-check-version -->\n"
        "## Impl\n\n<!-- @summary: impl path check -->\n\nBody"
    )
    res = _run(
        runner,
        root,
        "impl",
        "create",
        "prd-path-check",
        "--content",
        impl_content,
        "--impl-file",
        "impl/version",
        "--req-id",
        req_id,
    )
    payload = _parse(res.output)
    assert res.exit_code == 1
    assert payload["code"] == "INVALID_FILE_NAME"

    res = _run(
        runner,
        root,
        "impl",
        "create",
        "prd-path-check",
        "--content",
        impl_content,
        "--impl-file",
        "version",
        "--prd-file",
        "prd/path-check",
        "--req-id",
        req_id,
    )
    payload = _parse(res.output)
    assert res.exit_code == 1
    assert payload["code"] == "INVALID_FILE_NAME"

    res = _run(
        runner,
        root,
        "impl",
        "create",
        "prd-path-check",
        "--content",
        impl_content,
        "--impl-file",
        "version",
        "--req-id",
        req_id,
    )
    payload = _parse(res.output)["data"]
    assert payload["file"] == "impl/version"
    assert (root / "versions" / version / "impl" / "version.md").exists()
    assert not (root / "versions" / version / "version.md").exists()


def test_context_command_returns_l1_only_when_no_links(cli_project: Path):
    runner = CliRunner()
    root = cli_project

    _run(runner, root, "prdv1", "create", "ctx-test")
    data = _parse(_run(runner, root, "prdv1", "create", "ctx-test-2").output)
    req_id = data["data"]["req_id"]

    _run(
        runner,
        root,
        "prdv1",
        "save-draft",
        req_id,
        "--content",
        _prd_chunk("prd-ctxtest-overview", "概述", "context 测试概述", "body"),
    )
    _run(runner, root, "prdv1", "confirm", req_id, "--file", "ctxtest")
    _run(runner, root, "prdv1", "commit", "prd/ctxtest", "-m", "msg", "--req-id", req_id)

    res = _run(runner, root, "context", "prd-ctxtest-overview")
    parsed = _parse(res.output)["data"]
    assert parsed["l1"]["id"] == "prd-ctxtest-overview"
    assert parsed["l2"] == []


def test_cli_returns_error_json_for_missing_block(cli_project: Path):
    runner = CliRunner()
    root = cli_project

    res = runner.invoke(
        main,
        ["prdv1", "show", "prd/nonexistent"],
        catch_exceptions=False,
    )
    payload = _parse(res.output)
    assert payload["ok"] is False
    assert payload["code"] == "NOT_FOUND"
    assert res.exit_code == 1
