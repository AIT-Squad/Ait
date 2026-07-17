"""v2.53 讨论背景组装(迭代连续性原则的工具化)。

create 无内容=返回该层讨论背景(mode=discussion-context),零写入、phase 不动;
现状(经关联检索)+修改方向(上层已落地改动)→讨论出新 chunk。
发现式(fsd create/tdd create 无 parent:锚=version 上层改动)与
锚定式(tdd --parent / decompose child 缺失:锚=命名父块)两种形态;
空 baseline=空背景(初始=现状为空的迭代,零分支);init 建空 baseline 文件。
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from ait.cli import main
from ait.init_manager import InitManager
from ait.version_manager import VersionManager


def _payload(result):
    return json.loads(result.output.strip().splitlines()[-1])


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    return root


def _run(runner, *args):
    return _payload(runner.invoke(main, list(args), catch_exceptions=False))


PRD = "<!-- @id:[PRD]-app -->\n## App\n\n<!-- @id:[PRD]-app:cap -->\n## cap need\n"
FSD = ("<!-- @id:[FSD]-app -->\n## F\n\n<!-- @id:[FSD]-app:core -->\n## core\n\n"
       "<!-- @id:[FSD]-app:util -->\n## util\n```yaml\ndepends_on: [core]\n```\n")


def test_prd_context_empty_baseline_then_populated(tmp_path: Path, monkeypatch):
    """空 baseline → 空背景(初始=现状为空的迭代);有现状后返回 PRD 全文。"""
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _run(runner, "version", "create", "v0.1")

    p = _run(runner, "prd", "create", "[PRD]-app")
    assert p["ok"] is True and p["data"]["mode"] == "discussion-context"
    assert p["data"]["related"] == [] and p["data"]["target"]["exists"] is False
    assert not (root / "versions" / "v0.1" / "prd" / "[PRD]-app.md").exists(), "背景模式零写入"

    _run(runner, "prd", "create", "[PRD]-app", "--content", PRD)
    p = _run(runner, "prd", "create", "[PRD]-app")
    ids = [x["id"] for x in p["data"]["related"]]
    assert "[PRD]-app" in ids and "[PRD]-app:cap" in ids
    assert p["data"]["target"]["exists"] is True and "App" in p["data"]["target"]["content"]


def test_fsd_discovery_context_anchored_on_prd_changes(tmp_path: Path, monkeypatch):
    """发现式:anchors=本版本 PRD 改动 chunk 全文(修改方向的载体)。"""
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    runner = CliRunner()
    _run(runner, "version", "create", "v0.1")
    _run(runner, "prd", "create", "[PRD]-app", "--content", PRD)
    _run(runner, "prd", "confirm")

    p = _run(runner, "fsd", "create", "[FSD]-app")
    d = p["data"]
    assert d["mode"] == "discussion-context" and d["layer"] == "fsd"
    anchors = {a["id"]: a for a in d["anchors"]}
    assert "[PRD]-app:cap" in anchors and anchors["[PRD]-app:cap"]["action"] == "add"
    assert "cap need" in anchors["[PRD]-app:cap"]["content"], "锚点须带全文"


def test_decompose_anchored_context_when_child_missing(tmp_path: Path, monkeypatch):
    """锚定式:decompose 无 content 且 child 不存在 → parent 邻域背景
    (原 MISSING_ENDPOINT 错误路径);child 存在无 content 仍 link-only。"""
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _run(runner, "version", "create", "v0.1")
    _run(runner, "prd", "create", "[PRD]-app", "--content", PRD)
    _run(runner, "prd", "confirm")
    _run(runner, "fsd", "create", "[FSD]-app", "--parent", "[PRD]-app", "--content", FSD)

    p = _run(runner, "fsd", "decompose", "[FSD]-app:core", "[FSD]-app-core")
    d = p["data"]
    assert d["mode"] == "discussion-context"
    assert d["anchor"]["id"] == "[FSD]-app:core"
    linked = {(x["id"], x["rel"], x["direction"]) for x in d["linked"]}
    assert ("[FSD]-app:util", "depends_on", "in") in linked, "依赖方(入边)须进背景"
    up = [x["id"] for x in d["upstream"]]
    assert up == ["[FSD]-app", "[PRD]-app"], f"上溯链经 derives 到 PRD: {up}"
    assert not (root / "versions" / "v0.1" / "fsd" / "[FSD]-app-core.md").exists(), "零写入"

    # child 存在 + 无 content → 保持 link-only 语义
    _run(runner, "fsd", "create", "[FSD]-app-core", "--content",
         "<!-- @id:[FSD]-app-core -->\n## core module\n")
    p = _run(runner, "fsd", "decompose", "[FSD]-app:core", "[FSD]-app-core")
    assert p["data"].get("rel") == "decomposes", "child 已存在时仍是建边语义"


def test_tdd_anchored_and_discovery_context(tmp_path: Path, monkeypatch):
    """tdd create --parent=锚定式;无 parent=发现式(FSD 改动锚)。"""
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    runner = CliRunner()
    _run(runner, "version", "create", "v0.1")
    _run(runner, "prd", "create", "[PRD]-app", "--content", PRD)
    _run(runner, "prd", "confirm")
    _run(runner, "fsd", "create", "[FSD]-app", "--parent", "[PRD]-app", "--content", FSD)
    _run(runner, "fsd", "confirm")

    p = _run(runner, "tdd", "create", "[TDD]-app-core", "--parent", "[FSD]-app:core")
    d = p["data"]
    assert d["anchor"]["id"] == "[FSD]-app:core"
    assert [x["id"] for x in d["upstream"]] == ["[FSD]-app", "[PRD]-app"]

    p = _run(runner, "tdd", "create", "[TDD]-app-core")
    anchors = {a["id"] for a in p["data"]["anchors"]}
    assert "[FSD]-app:core" in anchors and "[FSD]-app" in anchors, "发现式锚=FSD 改动"


def test_context_mode_still_phase_gated(tmp_path: Path, monkeypatch):
    """背景模式过同层相位门禁:PRD 未 confirm 时 fsd 背景也拒(P7 一致)。"""
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    runner = CliRunner()
    _run(runner, "version", "create", "v0.1")
    _run(runner, "prd", "create", "[PRD]-app", "--content", PRD)

    p = _run(runner, "fsd", "create", "[FSD]-app")  # 无 content,phase=prd-creating
    assert p["ok"] is False and p["code"] == "PRD_NOT_CONFIRMED", p


def test_init_creates_empty_baseline_stores(tmp_path: Path):
    """init(legacy 模式)保证空 baseline 文件落盘——初始/迭代零分支地基。"""
    root = _project(tmp_path)
    InitManager(root).run()
    assert (root / ".meta" / "chunks-index.yaml").exists(), "空基线索引须落盘"
    assert (root / ".meta" / "specgraph.yaml").exists(), "空关系图须落盘"
