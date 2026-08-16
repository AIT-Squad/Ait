"""v2.90 安装位置解析:_mark_initialized 的 skill_dir 三级优先级链。

AIT_SKILL_DIR(显式覆盖) > CLAUDE_PLUGIN_ROOT(插件形态) > ~/.claude/skills/ait(Skill 形态兜底)。
取首个非空值。全部用 monkeypatch 管理环境变量,不依赖真实安装。
"""

from __future__ import annotations

import os
from pathlib import Path

from ait.init_manager import InitManager


def _wrapper_basename() -> str:
    return "ait.cmd" if os.name == "nt" else "ait"


def _mgr(tmp_path: Path) -> InitManager:
    root = tmp_path / "project-docs"
    (root / ".meta").mkdir(parents=True)
    return InitManager(root)


def test_plugin_root_used_when_only_env(tmp_path: Path, monkeypatch):
    """仅设 CLAUDE_PLUGIN_ROOT 时 skill_dir 取之。"""
    monkeypatch.delenv("AIT_SKILL_DIR", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path / "plugin-cache" / "ait"))

    skill_dir, cli_path = _mgr(tmp_path)._mark_initialized()

    assert skill_dir == str(tmp_path / "plugin-cache" / "ait")
    assert cli_path == str(Path(skill_dir) / "bin" / _wrapper_basename())


def test_ait_skill_dir_wins_over_plugin_root(tmp_path: Path, monkeypatch):
    """两者都设时 AIT_SKILL_DIR 优先(显式覆盖最高)。"""
    monkeypatch.setenv("AIT_SKILL_DIR", str(tmp_path / "explicit" / "ait"))
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path / "plugin-cache" / "ait"))

    skill_dir, cli_path = _mgr(tmp_path)._mark_initialized()

    assert skill_dir == str(tmp_path / "explicit" / "ait")
    assert cli_path == str(Path(skill_dir) / "bin" / _wrapper_basename())


def test_falls_back_to_home_skill_dir(tmp_path: Path, monkeypatch):
    """两者皆无时回落到 ~/.claude/skills/ait。"""
    monkeypatch.delenv("AIT_SKILL_DIR", raising=False)
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)

    skill_dir, cli_path = _mgr(tmp_path)._mark_initialized()

    assert skill_dir == str(Path.home() / ".claude" / "skills" / "ait")
    assert cli_path == str(Path(skill_dir) / "bin" / _wrapper_basename())
