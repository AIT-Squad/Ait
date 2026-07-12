"""v2.24 tdd 层 + 四层命令面端到端合龙。

tdd create --parent 创建即建 details 边;confirm/revert 成对;
prd→fsd decompose→tdd create --parent→codegen prepare 全链走通。
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


def test_tdd_create_parent_builds_details_edge(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _run(runner, "prd", "create", "[PRD]-app", "--content", PRD)
    _run(runner, "fsd", "create", "[FSD]-app", "--content", FSD)

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
    _run(runner, "prd", "create", "[PRD]-app", "--content", PRD)
    _run(runner, "fsd", "create", "[FSD]-app",
         "--content", FSD + "\n<!-- @id:[FSD]-app:feat2 -->\n## Feat2\n")
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
    _run(runner, "prd", "create", "[PRD]-app", "--content", PRD)
    _run(runner, "fsd", "create", "[FSD]-app", "--content", FSD)

    p = _run(runner, "tdd", "create", "[TDD]-app-feat", "--parent", "[FSD]-ghost:x", "--content", TDD)
    assert p["ok"] is False and "MISSING_ENDPOINT" in (p.get("code") or "")
    assert not (root / "versions" / "v0.1" / "tdd" / "[TDD]-app-feat.md").exists(), "拒绝必须零落盘"


def test_tdd_confirm_freezes_and_revert_reworks(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _run(runner, "prd", "create", "[PRD]-app", "--content", PRD)
    _run(runner, "prd", "confirm")
    _run(runner, "fsd", "create", "[FSD]-app", "--content", FSD)
    _run(runner, "fsd", "confirm")
    _run(runner, "tdd", "create", "[TDD]-app-feat", "--parent", "[FSD]-app:feat", "--content", TDD)
    assert VersionManager(root).load_version_meta("v0.1").phase == "tdd-creating"

    p = _run(runner, "tdd", "confirm")
    assert p["ok"] is True and p["data"]["phase"] == "tdd-confirm"
    assert "[TDD]-app-feat" in p["data"]["confirmed"]

    # 冻结是真的
    p = _run(runner, "tdd", "create", "[TDD]-app-feat",
             "--action", "modify", "--overrides", "[TDD]-app-feat", "--content", TDD)
    assert p["ok"] is False

    # revert 成对返工
    p = _run(runner, "tdd", "revert")
    assert p["ok"] is True and p["data"]["phase"] == "tdd-creating"
    assert "[TDD]-app-feat" in p["data"]["reverted"]


def test_tdd_confirm_requires_tdd_chunks(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    runner = CliRunner()
    _run(runner, "version", "create", "v3.0")
    p = _run(runner, "tdd", "confirm", "--version", "v3.0")
    assert p["ok"] is False and "NO_TDD_CHUNKS" in (p.get("code") or "") + p["error"]


def test_four_layer_pipeline_end_to_end(tmp_path: Path, monkeypatch):
    """prd → fsd → tdd(--parent) → codegen prepare 四层命令面合龙。"""
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()

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

    # codegen prepare 沿 details→decomposes 上溯全链
    cg = _run(runner, "codegen", "prepare", "[TDD]-app-feat")
    assert cg["ok"] is True
    assert cg["data"]["target_file"] == "app/feat.py"
    upstream_ids = {u["id"] for u in cg["data"]["upstream"]}
    assert "[FSD]-app:feat" in upstream_ids, f"上溯链缺父 split: {upstream_ids}"
    assert "[FSD]-app" in upstream_ids, f"上溯链缺 FSD 根: {upstream_ids}"
    assert "[PRD]-app" in upstream_ids, f"上溯链缺 PRD: {upstream_ids}"
