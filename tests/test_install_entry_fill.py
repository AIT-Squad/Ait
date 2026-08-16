"""Tests for install.py filling the SKILL.md init entry path at install time (v2.91)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_INSTALL_PATH = Path(__file__).resolve().parent.parent / "install.py"


def _load_install_module():
    spec = importlib.util.spec_from_file_location("ait_install", _INSTALL_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


install_module = _load_install_module()

_PLACEHOLDER = "{{AIT_ENTRY}}"
_WRAPPER = "ait.cmd" if sys.platform == "win32" else "ait"

_SKILL_MD = (
    "- **入口命令**：唯一例外是 `init` 自身——首次用 skill 入口 "
    f"`{_PLACEHOLDER} init`；`init` 之后一律回到项目本地 wrapper。\n"
    f"| `/ait init` | `{_PLACEHOLDER} init`（首次；之后走项目本地 wrapper） |\n"
)


def _make_prefix(root: Path, name: str, text: str = _SKILL_MD) -> Path:
    prefix = root / name
    (prefix / "bin").mkdir(parents=True)
    (prefix / "SKILL.md").write_text(text, encoding="utf-8")
    return prefix


def test_fill_replaces_placeholder_with_wrapper_absolute_path(tmp_path: Path) -> None:
    prefix = _make_prefix(tmp_path, "skills-ait")

    install_module.fill_entry_path(prefix)

    filled = (prefix / "SKILL.md").read_text(encoding="utf-8")
    expected_entry = str(prefix / "bin" / _WRAPPER)
    assert _PLACEHOLDER not in filled
    assert filled.count(expected_entry) == 2
    assert Path(expected_entry).is_absolute()


def test_fill_follows_custom_prefix(tmp_path: Path) -> None:
    default_prefix = _make_prefix(tmp_path, "default")
    custom_prefix = _make_prefix(tmp_path, "custom-location")

    install_module.fill_entry_path(default_prefix)
    install_module.fill_entry_path(custom_prefix)

    default_text = (default_prefix / "SKILL.md").read_text(encoding="utf-8")
    custom_text = (custom_prefix / "SKILL.md").read_text(encoding="utf-8")
    assert str(custom_prefix / "bin" / _WRAPPER) in custom_text
    assert str(default_prefix / "bin" / _WRAPPER) not in custom_text
    assert default_text != custom_text


def test_fill_leaves_file_without_placeholder_untouched(tmp_path: Path) -> None:
    original = "- **入口命令**：已填充为 `/opt/ait/bin/ait init`，无占位符。\n"
    prefix = _make_prefix(tmp_path, "already-filled", text=original)

    install_module.fill_entry_path(prefix)
    install_module.fill_entry_path(prefix)

    assert (prefix / "SKILL.md").read_text(encoding="utf-8") == original
