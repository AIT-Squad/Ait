"""Tests for install.py update venv refresh behavior."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

_INSTALL_PATH = Path(__file__).resolve().parent.parent / "install.py"


def _load_install_module():
    spec = importlib.util.spec_from_file_location("ait_install", _INSTALL_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


install_module = _load_install_module()


def _make_source(root: Path) -> Path:
    source = root / "source"
    (source / "bin").mkdir(parents=True)
    (source / "ait").mkdir()
    (source / ".venv").mkdir()
    (source / "SKILL.md").write_text("# New skill\n", encoding="utf-8")
    (source / "bin" / "ait").write_text("new wrapper\n", encoding="utf-8")
    (source / "ait" / "__init__.py").write_text("__version__ = 'new'\n", encoding="utf-8")
    (source / ".venv" / "should-not-copy.txt").write_text("ignored\n", encoding="utf-8")
    return source


def _make_dest(root: Path) -> Path:
    dest = root / "dest"
    (dest / "bin").mkdir(parents=True)
    (dest / "ait").mkdir()
    (dest / ".venv").mkdir()
    (dest / "SKILL.md").write_text("# Old skill\n", encoding="utf-8")
    (dest / "bin" / "ait").write_text("old wrapper\n", encoding="utf-8")
    (dest / "ait" / "__init__.py").write_text("__version__ = 'old'\n", encoding="utf-8")
    (dest / "ait" / "stale.py").write_text("stale\n", encoding="utf-8")
    (dest / ".venv" / "marker.txt").write_text("keep\n", encoding="utf-8")
    return dest


def test_update_copies_files_and_refreshes_venv_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _make_source(tmp_path)
    dest = _make_dest(tmp_path)
    refreshed: list[Path] = []

    monkeypatch.setattr(install_module, "refresh_venv", lambda target: refreshed.append(target))

    install_module.do_update(source, dest)

    assert refreshed == [dest]
    assert (dest / "SKILL.md").read_text(encoding="utf-8") == "# New skill\n"
    assert (dest / "bin" / "ait").read_text(encoding="utf-8") == "new wrapper\n"
    assert (dest / "ait" / "__init__.py").read_text(encoding="utf-8") == "__version__ = 'new'\n"
    assert not (dest / "ait" / "stale.py").exists()
    assert (dest / ".venv" / "marker.txt").read_text(encoding="utf-8") == "keep\n"
    assert not (dest / ".venv" / "should-not-copy.txt").exists()


def test_update_skip_venv_copies_files_without_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _make_source(tmp_path)
    dest = _make_dest(tmp_path)

    def fail_refresh(_target: Path) -> None:
        raise AssertionError("refresh_venv should not be called")

    monkeypatch.setattr(install_module, "refresh_venv", fail_refresh)

    install_module.do_update(source, dest, skip_venv=True)

    assert (dest / "SKILL.md").read_text(encoding="utf-8") == "# New skill\n"
    assert (dest / "bin" / "ait").read_text(encoding="utf-8") == "new wrapper\n"
    assert (dest / ".venv" / "marker.txt").read_text(encoding="utf-8") == "keep\n"


def test_refresh_venv_reinstalls_copied_skill_with_existing_venv_python(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "dest"
    (dest / ".venv" / "Scripts").mkdir(parents=True)
    (dest / ".venv" / "bin").mkdir(parents=True)
    (dest / ".venv" / "Scripts" / "python.exe").write_text("", encoding="utf-8")
    (dest / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
    expected_python = install_module.find_venv_python(dest)
    calls: list[dict[str, object]] = []

    def fake_run(cmd: list[str], **kwargs: object):
        calls.append({"cmd": cmd, "kwargs": kwargs})
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(install_module.subprocess, "run", fake_run)

    install_module.refresh_venv(dest)

    assert expected_python is not None
    assert calls == [
        {
            "cmd": [
                str(expected_python),
                "-m",
                "pip",
                "install",
                "--quiet",
                "--disable-pip-version-check",
                "--upgrade",
                str(dest),
            ],
            "kwargs": {"capture_output": True, "text": True, "check": False},
        }
    ]


def test_skip_venv_parser_option_belongs_only_to_update() -> None:
    parser = install_module.build_parser()

    args = parser.parse_args(["update", "--skip-venv"])
    assert args.action == "update"
    assert args.skip_venv is True

    with pytest.raises(SystemExit):
        parser.parse_args(["install", "--skip-venv"])
