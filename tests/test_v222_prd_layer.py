"""v2.22 prd 层流转:create 自动开版本(阶段机起点) + confirm 冻结 / revert 成对返工。"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from ait.cli import main
from ait.version_manager import VersionManager


def _payload(result):
    return json.loads(result.output.strip().splitlines()[-1])


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    return root


PRD = "<!-- @id:[PRD]-app -->\n## P\n"


def test_prd_create_auto_opens_version_and_starts_phase(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    r = runner.invoke(main, ["prd", "create", "[PRD]-app", "--content", PRD], catch_exceptions=False)
    p = _payload(r)
    assert p["ok"] is True
    assert p["data"]["auto_created_version"] == "v0.1", "空库应自动开 v0.1"
    meta = VersionManager(root).load_version_meta("v0.1")
    assert meta.phase == "prd-creating", "阶段机起点"


def test_prd_create_reuses_active_version(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["version", "create", "v3.0"], catch_exceptions=False)

    r = runner.invoke(main, ["prd", "create", "[PRD]-app", "--content", PRD], catch_exceptions=False)
    p = _payload(r)
    assert p["ok"] is True
    assert p["data"]["version"] == "v3.0"
    assert p["data"]["auto_created_version"] is None, "有活动版本不得另开"


def test_prd_create_auto_bumps_after_merged(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    vm = VersionManager(root)
    vm.create("v1.9")
    meta = vm.load_version_meta("v1.9")
    from datetime import datetime, timezone

    meta.merged_at = datetime.now(timezone.utc)  # 模拟已合入 → 无活动版本
    vm.save_version_meta(meta)

    r = runner.invoke(main, ["prd", "create", "[PRD]-app", "--content", PRD], catch_exceptions=False)
    p = _payload(r)
    assert p["ok"] is True
    assert p["data"]["auto_created_version"] == "v1.10", "minor 递增(非字典序)"


def test_prd_confirm_freezes_and_revert_reworks(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["prd", "create", "[PRD]-app", "--content", PRD], catch_exceptions=False)

    # confirm 冻结:chunk 锁定 + phase 推进
    r = runner.invoke(main, ["prd", "confirm"], catch_exceptions=False)
    p = _payload(r)
    assert p["ok"] is True and p["data"]["phase"] == "prd-confirm"
    assert p["data"]["confirmed"] == ["[PRD]-app"]
    vm = VersionManager(root)
    assert vm.load_version_meta("v0.1").phase == "prd-confirm"

    # 冻结是真的:再 modify 同 chunk → CHUNK_LOCKED
    r = runner.invoke(
        main,
        ["prd", "create", "[PRD]-app", "--action", "modify", "--overrides", "[PRD]-app", "--content", PRD],
        catch_exceptions=False,
    )
    assert _payload(r)["ok"] is False

    # revert 成对返工:解锁 + phase 回退
    r = runner.invoke(main, ["prd", "revert"], catch_exceptions=False)
    p = _payload(r)
    assert p["ok"] is True and p["data"]["phase"] == "prd-creating"
    assert p["data"]["reverted"] == ["[PRD]-app"]

    # 返工后可继续修改(无终态陷阱)
    r = runner.invoke(
        main,
        ["prd", "create", "[PRD]-app", "--action", "modify", "--overrides", "[PRD]-app",
         "--content", "<!-- @id:[PRD]-app -->\n## P v2\n"],
        catch_exceptions=False,
    )
    assert _payload(r)["ok"] is True


def test_prd_confirm_requires_prd_chunks(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["version", "create", "v3.0"], catch_exceptions=False)

    r = runner.invoke(main, ["prd", "confirm"], catch_exceptions=False)
    p = _payload(r)
    assert p["ok"] is False
    assert "NO_PRD_CHUNKS" in (p.get("code") or "") + p["error"]


def test_prd_revert_rejected_on_merged(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["prd", "create", "[PRD]-app", "--content", PRD], catch_exceptions=False)
    vm = VersionManager(root)
    meta = vm.load_version_meta("v0.1")
    from datetime import datetime, timezone

    meta.merged_at = datetime.now(timezone.utc)
    vm.save_version_meta(meta)

    r = runner.invoke(main, ["prd", "revert", "--version", "v0.1"], catch_exceptions=False)
    assert _payload(r)["ok"] is False, "merged 版本不可层级返工"
