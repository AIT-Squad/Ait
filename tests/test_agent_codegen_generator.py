"""[TDD]-agent_codegen_generator — codegen 子 agent 定义文件的结构断言。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

AGENT_PATH = (
    Path(__file__).resolve().parent.parent
    / "skill"
    / "ait"
    / "agents"
    / "codegen-generator.md"
)


def _read() -> str:
    return AGENT_PATH.read_text(encoding="utf-8")


def _split() -> tuple[dict, str]:
    """拆 `---` 分隔的 frontmatter 与正文。"""
    text = _read()
    assert text.startswith("---\n"), "定义文件必须以 YAML frontmatter 开头"
    _, raw_front, body = text.split("---\n", 2)
    front = yaml.safe_load(raw_front)
    assert isinstance(front, dict), "frontmatter 必须解析为映射"
    return front, body


# ── 正常路径 ────────────────────────────────────────────────────────────────


def test_agent_definition_file_exists():
    assert AGENT_PATH.is_file(), f"缺少子 agent 定义文件: {AGENT_PATH}"


@pytest.mark.parametrize("field", ["name", "description", "tools", "model"])
def test_frontmatter_has_required_fields(field):
    front, _ = _split()
    assert field in front, f"frontmatter 缺字段 {field}"
    assert str(front[field]).strip(), f"frontmatter 字段 {field} 不得为空"


def test_name_is_codegen_generator():
    front, _ = _split()
    assert front["name"] == "codegen-generator"


def test_tools_whitelist_contains_read_and_edit():
    front, _ = _split()
    tools = front["tools"]
    names = tools if isinstance(tools, list) else [t.strip() for t in tools.split(",")]
    assert "Read" in names
    assert "Edit" in names


# ── 边界条件 ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("field", ["hooks:", "mcpServers:", "permissionMode:"])
def test_no_fields_ignored_by_plugin_distribution(field):
    """这三个字段在插件分发中会被忽略,行为不可依赖,不得出现。"""
    assert field not in _read(), f"定义文件不得使用 {field} 字段"


def test_body_mentions_sha256_verification_and_target_file():
    _, body = _split()
    assert "sha256" in body.lower(), "正文须要求校验 bundle 的 sha256"
    assert "target_file" in body, "正文须说明修改 bundle 指明的 target_file"
