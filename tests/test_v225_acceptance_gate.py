"""v2.25 制品验收门禁:config 声明命令,confirm/merge 前跑,红则拒;未配跳过。"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from click.testing import CliRunner

from ait.cli import main
from ait.new_model_manager import NewModelManager
from ait.version_manager import VersionManager


def _payload(result):
    return json.loads(result.output.strip().splitlines()[-1])


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    return root


PRD = "<!-- @id:[PRD]-app -->\n## App PRD\n"
FSD = "<!-- @id:[FSD]-app -->\n## App FSD\n\n<!-- @id:[FSD]-app:feat -->\n## Feat\n"
TDD = "<!-- @id:[TDD]-app-feat -->\n## TDD\n\n```yaml\ntarget_file: app/feat.py\n```\n"


def _run(runner, *args):
    return _payload(runner.invoke(main, list(args), catch_exceptions=False))


def _build_valid_version(runner):
    """A six-invariant-compliant new-model version via the pipeline (P7: explicit version create)."""
    _run(runner, "version", "create", "v0.1")
    _run(runner, "prd", "create", "[PRD]-app", "--content", PRD)
    _run(runner, "prd", "confirm")
    _run(runner, "fsd", "create", "[FSD]-app", "--content", FSD)
    _run(runner, "fsd", "decompose", "[PRD]-app", "[FSD]-app")
    _run(runner, "fsd", "confirm")
    _run(runner, "tdd", "create", "[TDD]-app-feat", "--parent", "[FSD]-app:feat", "--content", TDD)
    _run(runner, "tdd", "confirm")
    _run(runner, "version", "commit", "v0.1")


def test_acceptance_unconfigured_is_skipped(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    res = VersionManager(root).run_acceptance()
    assert res == {"passed": True, "skipped": True, "command": None}


def test_acceptance_set_persists_and_keeps_other_keys(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    (root / ".meta" / "config.yaml").write_text("initialized: true\nskill_dir: skill/ait\n", encoding="utf-8")
    runner = CliRunner()
    p = _run(runner, "acceptance", "set", "exit 0")
    assert p["ok"] is True and p["data"]["acceptance_command"] == "exit 0"
    cfg = yaml.safe_load((root / ".meta" / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["acceptance_command"] == "exit 0"
    assert cfg["initialized"] is True and cfg["skill_dir"] == "skill/ait", "其余键保留"


def test_acceptance_green_command_passes(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    vm = VersionManager(root)
    vm.set_acceptance_command("exit 0")
    res = vm.run_acceptance()
    assert res["passed"] is True and res["skipped"] is False and res["exit_code"] == 0


def test_acceptance_red_command_fails(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    vm = VersionManager(root)
    vm.set_acceptance_command("exit 1")
    res = vm.run_acceptance()
    assert res["passed"] is False and res["exit_code"] == 1


def test_gate_reports_acceptance_failure(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _build_valid_version(runner)
    VersionManager(root).set_acceptance_command("exit 3")

    p = _run(runner, "version", "confirm", "v0.1")  # gate
    assert p["ok"] is False  # gate failed → non-ok, report in details
    report = p["details"]
    assert report["passed"] is False
    codes = {v["code"] for v in report["violations"]}
    assert "ACCEPTANCE_FAILED" in codes
    assert report["acceptance"]["passed"] is False


def test_merge_blocked_by_red_acceptance_zero_write(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _build_valid_version(runner)
    VersionManager(root).set_acceptance_command("exit 1")
    before = (root / ".meta" / "chunks-index.yaml").read_bytes() if (root / ".meta" / "chunks-index.yaml").exists() else None

    p = _run(runner, "version", "merge", "v0.1")
    assert p["ok"] is False and "ACCEPTANCE_FAILED" in (p.get("code") or "")
    # 零落盘:版本未 merged
    assert VersionManager(root).load_version_meta("v0.1").merged_at is None
    after = (root / ".meta" / "chunks-index.yaml").read_bytes() if (root / ".meta" / "chunks-index.yaml").exists() else None
    assert before == after, "验收拒绝必须零落盘"


def test_merge_passes_with_green_acceptance(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _build_valid_version(runner)
    VersionManager(root).set_acceptance_command("exit 0")

    p = _run(runner, "version", "merge", "v0.1")
    assert p["ok"] is True
    assert VersionManager(root).load_version_meta("v0.1").merged_at is not None
