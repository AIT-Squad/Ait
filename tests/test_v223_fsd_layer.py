"""v2.23→v2.51 fsd 层流转:P7 收——decompose 拆分即建边 + confirm/revert 成对(prd confirm 前置)。"""

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


def _bootstrap_prd(runner):
    """P7 收:显式 version create → prd create → prd confirm(FSD 层可达)。"""
    runner.invoke(main, ["version", "create", "v0.1"], catch_exceptions=False)
    runner.invoke(main, ["prd", "create", "[PRD]-app",
                         "--content", "<!-- @id:[PRD]-app -->\n## App PRD\n"],
                  catch_exceptions=False)
    runner.invoke(main, ["prd", "confirm"], catch_exceptions=False)


FSD_ROOT = "<!-- @id:[FSD]-app -->\n## App FSD root\n"
FSD_CHILD = "<!-- @id:[FSD]-app-svc -->\n## Svc module\n"


def test_link_command_retired(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    r = CliRunner().invoke(main, ["fsd", "link", "[FSD]-a", "[FSD]-b", "--rel", "decomposes"])
    assert r.exit_code != 0, "fsd link 应已退役(no such command)"
    assert "No such command" in r.output or "no such command" in r.output.lower()


def test_fsd_create_requires_prd_confirm_p7(tmp_path: Path, monkeypatch):
    """P7 收:PRD 未 confirm(phase=prd-creating)时 fsd create 拒 PRD_NOT_CONFIRMED,零落盘。"""
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["version", "create", "v0.1"], catch_exceptions=False)
    runner.invoke(main, ["prd", "create", "[PRD]-app",
                         "--content", "<!-- @id:[PRD]-app -->\n## App PRD\n"],
                  catch_exceptions=False)

    r = runner.invoke(main, ["fsd", "create", "[FSD]-app", "--content", FSD_ROOT])
    p = _payload(r)
    assert p["ok"] is False and p["code"] == "PRD_NOT_CONFIRMED", p
    assert not (root / "versions" / "v0.1" / "fsd" / "[FSD]-app.md").exists(), "拒绝须零落盘"

    # prd confirm 后重试成功(拒绝非终态)
    runner.invoke(main, ["prd", "confirm"], catch_exceptions=False)
    r = runner.invoke(main, ["fsd", "create", "[FSD]-app", "--content", FSD_ROOT], catch_exceptions=False)
    assert _payload(r)["ok"] is True


def test_decompose_atomic_write_child_and_edge(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _bootstrap_prd(runner)
    # 一级 FSD:PRD derives FSD 根(create --parent 建 derives 边)
    r = runner.invoke(main, ["fsd", "create", "[FSD]-app", "--parent", "[PRD]-app", "--content", FSD_ROOT], catch_exceptions=False)
    assert _payload(r)["ok"] is True, "PRD→FSD 建 derives 边"

    # decompose 原子写子 FSD + 建边(child 不预先存在)
    r = runner.invoke(
        main,
        ["fsd", "decompose", "[FSD]-app", "[FSD]-app-svc", "--content", FSD_CHILD],
        catch_exceptions=False,
    )
    p = _payload(r)
    assert p["ok"] is True and p["data"]["rel"] == "decomposes"

    # 边真的建了:deps 查得到
    r = runner.invoke(main, ["deps", "[FSD]-app", "--direction", "out"], catch_exceptions=False)
    dsts = {e["dst"] for e in _payload(r)["data"]["edges"] if e["rel"] == "decomposes"}
    assert "[FSD]-app-svc" in dsts
    # 子 FSD 文件真的写了
    assert (root / "versions" / "v0.1" / "fsd" / "[FSD]-app-svc.md").exists()


def test_decompose_prd_rejected_zero_write(tmp_path: Path, monkeypatch):
    """v2.52: PRD 不再 decompose(改用 derives via `fsd create --parent`)。
    对 PRD 调 `fsd decompose` 当场被 INVALID_DECOMPOSES_TYPES 拒,零落盘。"""
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _bootstrap_prd(runner)
    runner.invoke(main, ["fsd", "create", "[FSD]-app", "--parent", "[PRD]-app", "--content", FSD_ROOT], catch_exceptions=False)

    # PRD 派生一个 FSD 后,试图让 PRD decompose 另一个 FSD → 父侧门禁拒,零落盘
    r = runner.invoke(
        main,
        ["fsd", "decompose", "[PRD]-app", "[FSD]-other", "--content", "<!-- @id:[FSD]-other -->\n## O\n"],
        catch_exceptions=False,
    )
    p = _payload(r)
    assert p["ok"] is False and "INVALID_DECOMPOSES_TYPES" in (p.get("code") or "")
    assert not (root / "versions" / "v0.1" / "fsd" / "[FSD]-other.md").exists(), "拒绝必须零落盘"


def test_decompose_phantom_parent_rejected(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    runner = CliRunner()
    _bootstrap_prd(runner)
    r = runner.invoke(
        main,
        ["fsd", "decompose", "[FSD]-ghost", "[FSD]-x", "--content", "<!-- @id:[FSD]-x -->\n## X\n"],
        catch_exceptions=False,
    )
    p = _payload(r)
    assert p["ok"] is False and "MISSING_ENDPOINT" in (p.get("code") or "")


def test_fsd_confirm_freezes_and_revert_reworks(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _bootstrap_prd(runner)
    runner.invoke(main, ["fsd", "create", "[FSD]-app", "--content", FSD_ROOT], catch_exceptions=False)
    vm = VersionManager(root)
    assert vm.load_version_meta("v0.1").phase == "fsd-creating", "create_fsd 应把 phase 推进到 fsd-creating"

    r = runner.invoke(main, ["fsd", "confirm"], catch_exceptions=False)
    p = _payload(r)
    assert p["ok"] is True and p["data"]["phase"] == "fsd-confirm"
    assert "[FSD]-app" in p["data"]["confirmed"]

    # 冻结是真的:P7 下先撞 PRD_NOT_CONFIRMED 相位门禁(phase=fsd-confirm 不在允许集)
    r = runner.invoke(
        main,
        ["fsd", "create", "[FSD]-app", "--action", "modify", "--overrides", "[FSD]-app", "--content", FSD_ROOT],
        catch_exceptions=False,
    )
    p = _payload(r)
    assert p["ok"] is False
    assert p["code"] == "PRD_NOT_CONFIRMED", p

    # revert 成对返工
    r = runner.invoke(main, ["fsd", "revert"], catch_exceptions=False)
    p = _payload(r)
    assert p["ok"] is True and p["data"]["phase"] == "fsd-creating"
    assert "[FSD]-app" in p["data"]["reverted"]

    # 返工后可继续改(无终态陷阱)
    r = runner.invoke(
        main,
        ["fsd", "create", "[FSD]-app", "--action", "modify", "--overrides", "[FSD]-app",
         "--content", "<!-- @id:[FSD]-app -->\n## App FSD v2\n"],
        catch_exceptions=False,
    )
    assert _payload(r)["ok"] is True


def test_fsd_confirm_requires_fsd_chunks(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["version", "create", "v3.0"], catch_exceptions=False)
    # P7:fresh 版本 phase=empty,先撞 FSD_LAYER_NOT_OPEN 相位门禁
    r = runner.invoke(main, ["fsd", "confirm", "--version", "v3.0"], catch_exceptions=False)
    p = _payload(r)
    assert p["ok"] is False and "FSD_LAYER_NOT_OPEN" in (p.get("code") or "") + p["error"]


# ── v2.52: PRD→FSD 关系拆分(decomposes → derives)回归 ──────────────────


def test_fsd_create_parent_builds_derives_edge(tmp_path: Path, monkeypatch):
    """回归:`fsd create --parent [PRD]-x` 是 PRD→FSD derives 边的出生地。"""
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _bootstrap_prd(runner)

    p = _payload(runner.invoke(main, ["fsd", "create", "[FSD]-app", "--parent", "[PRD]-app", "--content", FSD_ROOT], catch_exceptions=False))
    assert p["ok"] is True

    # derives 边真的建了:deps 查得到,且 rel=="derives"(非 decomposes)
    d = _payload(runner.invoke(main, ["deps", "[PRD]-app", "--direction", "out"], catch_exceptions=False))
    triples = {(e["src"], e["dst"], e["rel"]) for e in d["data"]["edges"]}
    assert ("[PRD]-app", "[FSD]-app", "derives") in triples, f"应生成 derives 边: {triples}"
    assert not any(r == "decomposes" for _, _, r in triples), "PRD 不再 decomposes"


def test_fsd_create_second_parent_derives_rejected_zero_write(tmp_path: Path, monkeypatch):
    """回归:PRD 已 derives 一个 FSD,再 `create --parent` 第二个 → PRD_FSD_LINK_NOT_UNIQUE,零落盘。"""
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _bootstrap_prd(runner)
    runner.invoke(main, ["fsd", "create", "[FSD]-app", "--parent", "[PRD]-app", "--content", FSD_ROOT], catch_exceptions=False)

    p = _payload(runner.invoke(
        main,
        ["fsd", "create", "[FSD]-other", "--parent", "[PRD]-app", "--content", "<!-- @id:[FSD]-other -->\n## O\n"],
        catch_exceptions=False,
    ))
    assert p["ok"] is False and "PRD_FSD_LINK_NOT_UNIQUE" in (p.get("code") or "")
    assert not (root / "versions" / "v0.1" / "fsd" / "[FSD]-other.md").exists(), "拒绝必须零落盘"


def test_fsd_decompose_prd_parent_type_rejected_zero_write(tmp_path: Path, monkeypatch):
    """回归:`fsd decompose [PRD]-x [FSD]-y` → INVALID_DECOMPOSES_TYPES(PRD 只 derives),零落盘。"""
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _bootstrap_prd(runner)
    runner.invoke(main, ["fsd", "create", "[FSD]-app", "--parent", "[PRD]-app", "--content", FSD_ROOT], catch_exceptions=False)

    p = _payload(runner.invoke(
        main,
        ["fsd", "decompose", "[PRD]-app", "[FSD]-y", "--content", "<!-- @id:[FSD]-y -->\n## Y\n"],
        catch_exceptions=False,
    ))
    assert p["ok"] is False and "INVALID_DECOMPOSES_TYPES" in (p.get("code") or "")
    assert not (root / "versions" / "v0.1" / "fsd" / "[FSD]-y.md").exists(), "拒绝必须零落盘"
