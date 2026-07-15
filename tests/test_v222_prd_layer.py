"""v2.22→v2.51 prd 层流转:P7 收——显式 version create(无自动开版本) + confirm 冻结 / revert 成对返工。"""

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


def test_prd_create_requires_active_version_p7(tmp_path: Path, monkeypatch):
    """P7 rule#2:prd create 不再自动开版本——无活动版本报 NO_ACTIVE_VERSION;
    显式 version create 后成功且 phase 置起点。"""
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    r = runner.invoke(main, ["prd", "create", "[PRD]-app", "--content", PRD])
    p = _payload(r)
    assert p["ok"] is False and p["code"] == "NO_ACTIVE_VERSION", p

    runner.invoke(main, ["version", "create", "v0.1"], catch_exceptions=False)
    r = runner.invoke(main, ["prd", "create", "[PRD]-app", "--content", PRD], catch_exceptions=False)
    p = _payload(r)
    assert p["ok"] is True, p
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
    assert p["data"]["version"] == "v3.0", "прd create 落在当前活动版本"


def test_prd_create_after_merged_requires_new_version_p7(tmp_path: Path, monkeypatch):
    """P7:上一版 merged 后无活动版本——prd create 报 NO_ACTIVE_VERSION,
    须显式 version create 下一版(不再 auto-bump)。"""
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    vm = VersionManager(root)
    vm.create("v1.9")
    meta = vm.load_version_meta("v1.9")
    from datetime import datetime, timezone

    meta.merged_at = datetime.now(timezone.utc)  # 模拟已合入 → 无活动版本
    vm.save_version_meta(meta)

    r = runner.invoke(main, ["prd", "create", "[PRD]-app", "--content", PRD])
    p = _payload(r)
    assert p["ok"] is False and p["code"] == "NO_ACTIVE_VERSION", p

    # 显式开下一版(上一版已 merged → 守卫放行)后成功
    runner.invoke(main, ["version", "create", "v1.10"], catch_exceptions=False)
    r = runner.invoke(main, ["prd", "create", "[PRD]-app", "--content", PRD], catch_exceptions=False)
    assert _payload(r)["ok"] is True


def test_prd_confirm_freezes_and_revert_reworks(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["version", "create", "v0.1"], catch_exceptions=False)
    runner.invoke(main, ["prd", "create", "[PRD]-app", "--content", PRD], catch_exceptions=False)

    # confirm 冻结:chunk 锁定 + phase 推进
    r = runner.invoke(main, ["prd", "confirm"], catch_exceptions=False)
    p = _payload(r)
    assert p["ok"] is True and p["data"]["phase"] == "prd-confirm"
    assert p["data"]["confirmed"] == ["[PRD]-app"]
    vm = VersionManager(root)
    assert vm.load_version_meta("v0.1").phase == "prd-confirm"

    # 冻结是真的:再 modify 同 chunk → 拒(P7 下先撞 PRD_LAYER_CLOSED 门禁)
    r = runner.invoke(
        main,
        ["prd", "create", "[PRD]-app", "--action", "modify", "--overrides", "[PRD]-app", "--content", PRD],
        catch_exceptions=False,
    )
    p = _payload(r)
    assert p["ok"] is False
    assert p["code"] == "PRD_LAYER_CLOSED", p

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

    # P7:fresh 版本 phase=empty,先撞 PRD_LAYER_NOT_OPEN 相位门禁
    r = runner.invoke(main, ["prd", "confirm"], catch_exceptions=False)
    p = _payload(r)
    assert p["ok"] is False
    assert "PRD_LAYER_NOT_OPEN" in (p.get("code") or "") + p["error"]


def test_prd_revert_rejected_on_merged(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["version", "create", "v0.1"], catch_exceptions=False)
    runner.invoke(main, ["prd", "create", "[PRD]-app", "--content", PRD], catch_exceptions=False)
    vm = VersionManager(root)
    meta = vm.load_version_meta("v0.1")
    from datetime import datetime, timezone

    meta.merged_at = datetime.now(timezone.utc)
    vm.save_version_meta(meta)

    r = runner.invoke(main, ["prd", "revert", "--version", "v0.1"], catch_exceptions=False)
    assert _payload(r)["ok"] is False, "merged 版本不可层级返工"
