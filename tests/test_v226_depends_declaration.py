"""v2.26 依赖声明机制:split 内 yaml 声明 → 版本图对账 → 视图覆盖 → 合入对账。

link 全退(prd link 移除);fsd/tdd create 幽灵版本收口。
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from ait.cli import main
from ait.specgraph import combined_view, load_specgraph
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


PRD = "<!-- @id:[PRD]-app -->\n## App PRD\n"

FSD_DECLARED = """<!-- @id:[FSD]-app -->
## App FSD

<!-- @id:[FSD]-app:feat -->
## feat
```yaml
depends_on: [store]
```

<!-- @id:[FSD]-app:store -->
## store
"""

FSD_REDECLARED = """<!-- @id:[FSD]-app -->
## App FSD

<!-- @id:[FSD]-app:feat -->
## feat

<!-- @id:[FSD]-app:store -->
## store
```yaml
depends_on: [feat]
```
"""


def _bootstrap(runner):
    _run(runner, "prd", "create", "[PRD]-app", "--content", PRD)


def test_declaration_creates_edges(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _bootstrap(runner)

    p = _run(runner, "fsd", "create", "[FSD]-app", "--content", FSD_DECLARED)
    assert p["ok"] is True

    view = combined_view(root, "v0.1")
    deps = [(e.src, e.dst) for e in view.edges_from("[FSD]-app:feat", "depends_on")]
    assert deps == [("[FSD]-app:feat", "[FSD]-app:store")], "简写声明应生成同父依赖边"


def test_declaration_unknown_sibling_rejected_zero_write(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _bootstrap(runner)

    bad = FSD_DECLARED.replace("depends_on: [store]", "depends_on: [ghost]")
    p = _run(runner, "fsd", "create", "[FSD]-app", "--content", bad)
    assert p["ok"] is False and "DEPENDS_ON_UNKNOWN_SIBLING" in (p.get("code") or "")
    assert not (root / "versions" / "v0.1" / "fsd" / "[FSD]-app.md").exists(), "拒绝须零落盘"


def test_declaration_self_dep_rejected(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    runner = CliRunner()
    _bootstrap(runner)

    bad = FSD_DECLARED.replace("depends_on: [store]", "depends_on: [feat]")
    p = _run(runner, "fsd", "create", "[FSD]-app", "--content", bad)
    assert p["ok"] is False and "DEPENDS_ON_SELF" in (p.get("code") or "")


def test_declaration_cross_parent_rejected(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    runner = CliRunner()
    _bootstrap(runner)

    bad = FSD_DECLARED.replace("depends_on: [store]", 'depends_on: ["[FSD]-other:x"]')
    p = _run(runner, "fsd", "create", "[FSD]-app", "--content", bad)
    assert p["ok"] is False and "DEPENDS_ON_CROSS_LEVEL" in (p.get("code") or "")


def test_redeclare_reconciles_add_and_remove(tmp_path: Path, monkeypatch):
    """modify 改声明:旧边亡、新边生——文件是兄弟依赖边的所有权边界。"""
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _bootstrap(runner)
    _run(runner, "fsd", "create", "[FSD]-app", "--content", FSD_DECLARED)

    p = _run(runner, "fsd", "create", "[FSD]-app",
             "--action", "modify", "--overrides", "[FSD]-app",
             "--content", FSD_REDECLARED)
    assert p["ok"] is True

    view = combined_view(root, "v0.1")
    assert view.edges_from("[FSD]-app:feat", "depends_on") == [], "被删声明的边应消失"
    store_deps = [e.dst for e in view.edges_from("[FSD]-app:store", "depends_on")]
    assert store_deps == ["[FSD]-app:feat"], "新声明的边应生成"


def test_view_suppresses_baseline_scope_for_owned_root(tmp_path: Path, monkeypatch):
    """baseline 有旧依赖边,版本 modify 该文件删掉声明 → 视图立即不见(不还魂)。"""
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _bootstrap(runner)
    _run(runner, "fsd", "create", "[FSD]-app", "--content", FSD_DECLARED)
    _run(runner, "fsd", "decompose", "[PRD]-app", "[FSD]-app")
    # 简化直通:锁全部 chunk 后合入 baseline
    _run(runner, "version", "commit", "v0.1")
    # 补齐不变式(feat/store 是叶 split,需 TDD 才可追溯?不——不变式⑤⑥只约束
    # TDD 可追溯与孤儿;split 无 TDD 时是孤儿吗?structural 隶属算连接,ORPHAN
    # 走"从 PRD 沿边+结构下行可达",root 经 decomposes 可达,split 经结构可达 → 过)
    p = _run(runner, "version", "merge", "v0.1")
    assert p["ok"] is True, p

    base = load_specgraph(root)
    base_dep = [e for e in base.edges if e.rel == "depends_on"]
    assert len(base_dep) == 1, "合入后 baseline 应有 1 条依赖边"

    # 新版本 modify 同文件,删除声明
    _run(runner, "version", "create", "v0.2")
    p = _run(runner, "fsd", "create", "[FSD]-app",
             "--action", "modify", "--overrides", "[FSD]-app",
             "--content", FSD_DECLARED.replace("```yaml\ndepends_on: [store]\n```\n", ""))
    assert p["ok"] is True

    view = combined_view(root, "v0.2")
    assert view.edges_from("[FSD]-app:feat", "depends_on") == [], \
        "owned-scope 覆盖:baseline 旧边不得经并集还魂"


def test_merge_reconciles_baseline_edges(tmp_path: Path, monkeypatch):
    """删声明的版本 merge 后,baseline 对应边真正消失。"""
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _bootstrap(runner)
    _run(runner, "fsd", "create", "[FSD]-app", "--content", FSD_DECLARED)
    _run(runner, "fsd", "decompose", "[PRD]-app", "[FSD]-app")
    _run(runner, "version", "commit", "v0.1")
    assert _run(runner, "version", "merge", "v0.1")["ok"] is True

    _run(runner, "version", "create", "v0.2")
    _run(runner, "fsd", "create", "[FSD]-app",
         "--action", "modify", "--overrides", "[FSD]-app",
         "--content", FSD_REDECLARED)
    _run(runner, "version", "commit", "v0.2")
    p = _run(runner, "version", "merge", "v0.2")
    assert p["ok"] is True, p

    base = load_specgraph(root)

    def cid(uri):
        s = base.specs.get(uri)
        return s.chunk_id if s else uri

    deps = {(cid(e.src), cid(e.dst)) for e in base.edges if e.rel == "depends_on"}
    assert deps == {("[FSD]-app:store", "[FSD]-app:feat")}, \
        f"merge 对账:旧边删除、新边落地,得到 {deps}"


def test_prd_link_retired(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    r = CliRunner().invoke(main, ["prd", "link", "[PRD]-a", "[FSD]-b", "--rel", "decomposes"])
    assert r.exit_code != 0
    assert "no such command" in r.output.lower()


def test_fsd_tdd_create_ghost_version_rejected(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()

    p = _run(runner, "fsd", "create", "[FSD]-app", "--version", "v9.9typo",
             "--content", "<!-- @id:[FSD]-app -->\n## F\n")
    assert p["ok"] is False and "VERSION_NOT_FOUND" in (p.get("code") or "")
    assert not (root / ".meta" / "versions" / "v9.9typo.yaml").exists(), "不得静默建幽灵版本"

    p = _run(runner, "tdd", "create", "[TDD]-app-x", "--version", "v9.9typo",
             "--content", "<!-- @id:[TDD]-app-x -->\n## T\n```yaml\ntarget_file: a.py\n```\n")
    assert p["ok"] is False and "VERSION_NOT_FOUND" in (p.get("code") or "")
