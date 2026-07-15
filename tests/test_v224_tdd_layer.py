"""v2.24→v2.51 tdd 层 + 四层命令面端到端合龙(P7 收:全链显式分层)。

tdd create --parent 创建即建 details 边;confirm/revert 成对;
version create→prd→confirm→fsd→confirm→tdd create --parent→confirm→codegen 全链走通。
"""

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


PRD = "<!-- @id:[PRD]-app -->\n## App PRD\n"
FSD = "<!-- @id:[FSD]-app -->\n## App FSD\n\n<!-- @id:[FSD]-app:feat -->\n## Feat split\n"
TDD = "<!-- @id:[TDD]-app-feat -->\n## TDD\n\n```yaml\ntarget_file: app/feat.py\n```\n"
TDD2 = "<!-- @id:[TDD]-app-other -->\n## TDD2\n\n```yaml\ntarget_file: app/other.py\n```\n"


def _run(runner, *args):
    r = runner.invoke(main, list(args), catch_exceptions=False)
    return _payload(r)


def _bootstrap_to_tdd_layer(runner, fsd_content=FSD):
    """P7 收:version create → prd create+confirm → fsd create+confirm(TDD 层可达)。"""
    _run(runner, "version", "create", "v0.1")
    _run(runner, "prd", "create", "[PRD]-app", "--content", PRD)
    _run(runner, "prd", "confirm")
    _run(runner, "fsd", "create", "[FSD]-app", "--content", fsd_content)
    _run(runner, "fsd", "confirm")


def test_tdd_create_requires_fsd_confirm_p7(tmp_path: Path, monkeypatch):
    """P7 收:FSD 未 confirm(phase=fsd-creating)时 tdd create 拒 FSD_NOT_CONFIRMED,零落盘。"""
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _run(runner, "version", "create", "v0.1")
    _run(runner, "prd", "create", "[PRD]-app", "--content", PRD)
    _run(runner, "prd", "confirm")
    _run(runner, "fsd", "create", "[FSD]-app", "--content", FSD)

    p = _run(runner, "tdd", "create", "[TDD]-app-feat", "--parent", "[FSD]-app:feat", "--content", TDD)
    assert p["ok"] is False and p["code"] == "FSD_NOT_CONFIRMED", p
    assert not (root / "versions" / "v0.1" / "tdd" / "[TDD]-app-feat.md").exists(), "拒绝须零落盘"

    # fsd confirm 后重试成功(拒绝非终态)
    _run(runner, "fsd", "confirm")
    p = _run(runner, "tdd", "create", "[TDD]-app-feat", "--parent", "[FSD]-app:feat", "--content", TDD)
    assert p["ok"] is True


def test_tdd_create_parent_builds_details_edge(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _bootstrap_to_tdd_layer(runner)

    p = _run(runner, "tdd", "create", "[TDD]-app-feat", "--parent", "[FSD]-app:feat", "--content", TDD)
    assert p["ok"] is True

    # details 边真的建了
    d = _run(runner, "deps", "[TDD]-app-feat", "--direction", "in")
    srcs = {e["src"] for e in d["data"]["edges"] if e["rel"] == "details"}
    assert "[FSD]-app:feat" in srcs, f"details 边缺失: {d['data']['edges']}"


def test_tdd_create_second_parent_rejected_zero_write(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _bootstrap_to_tdd_layer(runner, FSD + "\n<!-- @id:[FSD]-app:feat2 -->\n## Feat2\n")
    _run(runner, "tdd", "create", "[TDD]-app-feat", "--parent", "[FSD]-app:feat", "--content", TDD)

    # 同一 TDD 再挂第二个父 → TDD_MULTI_PARENT
    p = _run(runner, "tdd", "create", "[TDD]-app-feat",
             "--action", "modify", "--overrides", "[TDD]-app-feat",
             "--parent", "[FSD]-app:feat2", "--content", TDD)
    assert p["ok"] is False and "TDD_MULTI_PARENT" in (p.get("code") or "")


def test_tdd_create_phantom_parent_rejected_zero_write(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _bootstrap_to_tdd_layer(runner)

    p = _run(runner, "tdd", "create", "[TDD]-app-feat", "--parent", "[FSD]-ghost:x", "--content", TDD)
    assert p["ok"] is False and "MISSING_ENDPOINT" in (p.get("code") or "")
    assert not (root / "versions" / "v0.1" / "tdd" / "[TDD]-app-feat.md").exists(), "拒绝必须零落盘"


def test_tdd_confirm_freezes_and_revert_reworks(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _bootstrap_to_tdd_layer(runner)
    _run(runner, "tdd", "create", "[TDD]-app-feat", "--parent", "[FSD]-app:feat", "--content", TDD)
    assert VersionManager(root).load_version_meta("v0.1").phase == "tdd-creating"

    p = _run(runner, "tdd", "confirm")
    assert p["ok"] is True and p["data"]["phase"] == "tdd-confirm"
    assert "[TDD]-app-feat" in p["data"]["confirmed"]

    # 冻结是真的:P7 下先撞 FSD_NOT_CONFIRMED 相位门禁(phase=tdd-confirm 不在允许集)
    p = _run(runner, "tdd", "create", "[TDD]-app-feat",
             "--action", "modify", "--overrides", "[TDD]-app-feat", "--content", TDD)
    assert p["ok"] is False
    assert p["code"] == "FSD_NOT_CONFIRMED", p

    # revert 成对返工
    p = _run(runner, "tdd", "revert")
    assert p["ok"] is True and p["data"]["phase"] == "tdd-creating"
    assert "[TDD]-app-feat" in p["data"]["reverted"]


def test_tdd_confirm_requires_tdd_chunks(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    runner = CliRunner()
    _run(runner, "version", "create", "v3.0")
    # P7:fresh 版本 phase=empty,先撞 TDD_LAYER_NOT_OPEN 相位门禁
    p = _run(runner, "tdd", "confirm", "--version", "v3.0")
    assert p["ok"] is False and "TDD_LAYER_NOT_OPEN" in (p.get("code") or "") + p["error"]


def test_four_layer_pipeline_end_to_end(tmp_path: Path, monkeypatch):
    """version→prd→fsd→tdd(--parent)→codegen prepare 全层命令面合龙(P7 收)。"""
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()

    # 版本入口(P7:唯一开版本方式)
    _run(runner, "version", "create", "v0.1")
    # PRD 层
    _run(runner, "prd", "create", "[PRD]-app", "--content", PRD)
    _run(runner, "prd", "confirm")
    # FSD 层:decompose 建 PRD→FSD 边
    _run(runner, "fsd", "create", "[FSD]-app", "--content", FSD)
    _run(runner, "fsd", "decompose", "[PRD]-app", "[FSD]-app")
    _run(runner, "fsd", "confirm")
    # TDD 层:create --parent 建 FSD split→TDD details 边
    _run(runner, "tdd", "create", "[TDD]-app-feat", "--parent", "[FSD]-app:feat", "--content", TDD)
    _run(runner, "tdd", "confirm")

    # codegen prepare 沿 details→decomposes 上溯全链(P7:tdd-confirm 后才可达)
    cg = _run(runner, "codegen", "prepare", "[TDD]-app-feat")
    assert cg["ok"] is True
    assert cg["data"]["target_file"] == "app/feat.py"
    upstream_ids = {u["id"] for u in cg["data"]["upstream"]}
    assert "[FSD]-app:feat" in upstream_ids, f"上溯链缺父 split: {upstream_ids}"
    assert "[FSD]-app" in upstream_ids, f"上溯链缺 FSD 根: {upstream_ids}"
    assert "[PRD]-app" in upstream_ids, f"上溯链缺 PRD: {upstream_ids}"


def test_codegen_requires_tdd_confirm_p7(tmp_path: Path, monkeypatch):
    """P7:活动版本 phase 未到 tdd-confirm 时 codegen 拒 TDD_NOT_CONFIRMED。"""
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    runner = CliRunner()
    _bootstrap_to_tdd_layer(runner)
    _run(runner, "tdd", "create", "[TDD]-app-feat", "--parent", "[FSD]-app:feat", "--content", TDD)

    p = _run(runner, "codegen", "prepare", "[TDD]-app-feat")
    assert p["ok"] is False and p["code"] == "TDD_NOT_CONFIRMED", p

    _run(runner, "tdd", "confirm")
    p = _run(runner, "codegen", "prepare", "[TDD]-app-feat")
    assert p["ok"] is True
