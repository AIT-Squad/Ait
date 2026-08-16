"""[TDD]-plugin_manifest — 插件清单 `.claude-plugin/plugin.json` 的结构断言。"""

from __future__ import annotations

import json
import re
from pathlib import Path

MANIFEST_PATH = (
    Path(__file__).resolve().parent.parent
    / "skill"
    / "ait"
    / ".claude-plugin"
    / "plugin.json"
)

_SEMVER = re.compile(
    r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)


def _load() -> dict:
    text = MANIFEST_PATH.read_text(encoding="utf-8")
    data = json.loads(text)
    assert isinstance(data, dict), "manifest 必须是单个 JSON 对象"
    return data


# ── 正常路径 ────────────────────────────────────────────────────────────


def test_manifest_exists_and_is_valid_json():
    assert MANIFEST_PATH.exists(), f"缺少插件清单：{MANIFEST_PATH}"
    _load()  # 语法错误在此抛 json.JSONDecodeError


def test_manifest_has_required_fields():
    data = _load()
    for field in ("name", "version", "description"):
        assert field in data, f"manifest 缺少必需字段 {field}"
        assert isinstance(data[field], str) and data[field].strip(), (
            f"字段 {field} 必须是非空字符串"
        )


def test_manifest_name_is_ait():
    assert _load()["name"] == "ait"


def test_manifest_version_is_semver():
    version = _load()["version"]
    assert _SEMVER.match(version), f"version 不是语义化版本形态：{version}"


# ── 边界条件 ────────────────────────────────────────────────────────────


def test_manifest_lives_under_claude_plugin_dir():
    assert MANIFEST_PATH.parent.name == ".claude-plugin"


def test_manifest_shares_distribution_root_with_skill_md():
    plugin_root = MANIFEST_PATH.parent.parent
    assert (plugin_root / "SKILL.md").exists(), (
        f"插件根 {plugin_root} 下应与 SKILL.md 同处一个分发根"
    )
