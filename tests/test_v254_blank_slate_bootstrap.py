"""v2.54 白板起步 bootstrap:空目录(无 project-docs)里 ait init 自建骨架,
让 P7 全流程从零可推进到 merge。init 是唯一白板入口(豁免根解析);
其余命令仍要求项目根已存在;重跑幂等。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from ait.cli import main


def _payload(result):
    return json.loads(result.output.strip().splitlines()[-1])


def _run(runner, *args, expect=True):
    res = runner.invoke(main, list(args), catch_exceptions=False)
    p = _payload(res)
    assert p["ok"] is expect, (args, p)
    return p


def test_init_on_blank_directory_builds_skeleton(tmp_path: Path, monkeypatch):
    """空目录(无 project-docs)运行 init → 自建骨架 + 空基线,不报 NOT_AT_PROJECT_ROOT。"""
    monkeypatch.chdir(tmp_path)
    assert not (tmp_path / "project-docs").exists(), "前置:真白板"
    runner = CliRunner()

    p = _run(runner, "init", "--new-model", "--name", "demo")
    pd = tmp_path / "project-docs"
    assert (pd / "docs").is_dir(), "docs/ 骨架"
    assert (pd / ".meta" / "versions").is_dir() and (pd / ".meta" / "changes").is_dir()
    assert (pd / ".meta" / "chunks-index.yaml").exists(), "空基线索引"
    assert (pd / ".meta" / "specgraph.yaml").exists(), "空关系图"


def test_non_init_command_still_requires_root_on_blank_dir(tmp_path: Path, monkeypatch):
    """P7 rule:只有 init 是白板入口——其余命令在空目录仍报 NOT_AT_PROJECT_ROOT。"""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    res = runner.invoke(main, ["version", "create", "v0.1"], catch_exceptions=False)
    assert res.exit_code == 1, res.output
    p = _payload(res)
    assert p["ok"] is False and p["code"] == "NOT_AT_PROJECT_ROOT", p


def test_init_is_idempotent_on_existing_project(tmp_path: Path, monkeypatch):
    """已初始化项目重跑 init 幂等,不破坏既有 baseline 文件。"""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    _run(runner, "init", "--new-model", "--name", "demo")
    prd = tmp_path / "project-docs" / "docs" / "prd" / "[PRD]-demo.md"
    before = prd.read_text(encoding="utf-8") if prd.exists() else None
    _run(runner, "init", "--new-model", "--name", "demo")
    after = prd.read_text(encoding="utf-8") if prd.exists() else None
    assert before == after, "重跑不覆盖既有内容"


def test_blank_slate_to_merge_end_to_end(tmp_path: Path, monkeypatch):
    """从真白板 init 一路走到 merge,全程无需手工建任何目录。"""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    _run(runner, "init", "--new-model", "--name", "demo")
    _run(runner, "version", "create", "v0.1")
    _run(runner, "prd", "create", "[PRD]-demo", "--action", "modify",
         "--overrides", "[PRD]-demo",
         "--content", "<!-- @id:[PRD]-demo -->\n## Demo\n\n<!-- @id:[PRD]-demo:feat -->\n## feat need\n")
    _run(runner, "prd", "confirm")
    _run(runner, "fsd", "create", "[FSD]-demo", "--parent", "[PRD]-demo",
         "--action", "modify", "--overrides", "[FSD]-demo",
         "--content", "<!-- @id:[FSD]-demo -->\n## F\n\n<!-- @id:[FSD]-demo:core -->\n## core\n")
    _run(runner, "fsd", "confirm")
    _run(runner, "tdd", "create", "[TDD]-demo-core", "--parent", "[FSD]-demo:core",
         "--content", "<!-- @id:[TDD]-demo-core -->\n## T\n```yaml\ntarget_file: src/core.py\n```\n")
    _run(runner, "tdd", "confirm")
    _run(runner, "codegen", "prepare", "[TDD]-demo-core")
    _run(runner, "version", "confirm", "v0.1")

    root = tmp_path / "project-docs"
    try:
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
        subprocess.run(["git", "-c", "user.email=a@b.c", "-c", "user.name=x",
                        "commit", "-qm", "base"], cwd=tmp_path, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("git unavailable")

    p = _run(runner, "version", "merge", "v0.1")
    assert p["data"]["git"] == "committed"
    assert (root / "docs" / "tdd" / "[TDD]-demo-core.md").exists(), "制品合入基线"
