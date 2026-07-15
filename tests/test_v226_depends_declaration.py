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
```yaml
depends_on: []
```

<!-- @id:[FSD]-app:store -->
## store
```yaml
depends_on: [feat]
```
"""


def _bootstrap(runner):
    # P7 收: explicit version create (no auto-open), then prd create + confirm
    # so the FSD layer is reachable (phase → prd-confirm).
    _run(runner, "version", "create", "v0.1")
    _run(runner, "prd", "create", "[PRD]-app", "--content", PRD)
    _run(runner, "prd", "confirm")


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
    # P7 收: iteration re-enters top-down from the PRD layer before touching FSD.
    _run(runner, "prd", "create", "[PRD]-app", "--action", "modify",
         "--overrides", "[PRD]-app", "--content", PRD)
    _run(runner, "prd", "confirm")
    p = _run(runner, "fsd", "create", "[FSD]-app",
             "--action", "modify", "--overrides", "[FSD]-app",
             "--content", FSD_DECLARED.replace("depends_on: [store]", "depends_on: []"))
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
    # P7 收: iteration re-enters top-down from the PRD layer before touching FSD.
    _run(runner, "prd", "create", "[PRD]-app", "--action", "modify",
         "--overrides", "[PRD]-app", "--content", PRD)
    _run(runner, "prd", "confirm")
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


# ── v2.31: 文档正文零关系声明 ──────────────────────────────────────


def test_declaration_stripped_from_persisted_doc(tmp_path: Path, monkeypatch):
    """depends_on 块建 specgraph 边后从持久 markdown 剥离;边仍在。"""
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _bootstrap(runner)
    _run(runner, "fsd", "create", "[FSD]-app", "--content", FSD_DECLARED)

    body = (root / "versions" / "v0.1" / "fsd" / "[FSD]-app.md").read_text(encoding="utf-8")
    assert "depends_on" not in body, "持久正文不得含 depends_on 块"
    assert "## store" in body and "## feat" in body, "非声明内容保留"

    view = combined_view(root, "v0.1")
    deps = [(e.src, e.dst) for e in view.edges_from("[FSD]-app:feat", "depends_on")]
    assert deps == [("[FSD]-app:feat", "[FSD]-app:store")], "specgraph 边仍在"


def test_strip_preserves_non_depends_yaml(tmp_path: Path, monkeypatch):
    """只剥离 depends_on 块,其它 yaml 块保留。"""
    from ait.new_model_manager import _strip_depends_on_blocks
    content = (
        "<!-- @id:[FSD]-x:a -->\n## a\n```yaml\ndepends_on: [b]\n```\n\n"
        "```yaml\nsome_other: keep_me\n```\n"
    )
    out = _strip_depends_on_blocks(content)
    assert "depends_on" not in out
    assert "some_other: keep_me" in out


# ── v2.32: preserve 语义 + :TEST 验收节点 ──────────────────────────


FSD_PROSE_ONLY = """<!-- @id:[FSD]-app -->
## App FSD (改了描述,没带 depends_on 块)

<!-- @id:[FSD]-app:feat -->
## feat 改后的描述

<!-- @id:[FSD]-app:store -->
## store 改后的描述
"""


def test_modify_without_block_preserves_edges(tmp_path: Path, monkeypatch):
    """v2.32 核心:重排 FSD 内容(不带 depends_on 块)不再 wipe 依赖边。"""
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _bootstrap(runner)
    _run(runner, "fsd", "create", "[FSD]-app", "--content", FSD_DECLARED)
    assert combined_view(root, "v0.1").edges_from("[FSD]-app:feat", "depends_on"), "前置:边已建"

    # 改描述、不带任何 depends_on 块
    p = _run(runner, "fsd", "create", "[FSD]-app",
             "--action", "modify", "--overrides", "[FSD]-app", "--content", FSD_PROSE_ONLY)
    assert p["ok"] is True
    deps = [e.dst for e in combined_view(root, "v0.1").edges_from("[FSD]-app:feat", "depends_on")]
    assert deps == ["[FSD]-app:store"], "无块 modify 必须保留现有边(preserve)"


def test_explicit_empty_clears_that_split_only(tmp_path: Path, monkeypatch):
    """显式 depends_on: [] 清空该 split;未提及的 split 不受影响。"""
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _bootstrap(runner)
    # feat→store, store→feat 两条
    two = FSD_DECLARED.replace("## store\n", "## store\n```yaml\ndepends_on: [feat]\n```\n")
    _run(runner, "fsd", "create", "[FSD]-app", "--content", two)
    v = combined_view(root, "v0.1")
    assert v.edges_from("[FSD]-app:feat", "depends_on") and v.edges_from("[FSD]-app:store", "depends_on")

    # 只清 feat(显式 []),不提 store
    clear_feat = two.replace("depends_on: [store]", "depends_on: []")
    _run(runner, "fsd", "create", "[FSD]-app",
         "--action", "modify", "--overrides", "[FSD]-app", "--content", clear_feat)
    v = combined_view(root, "v0.1")
    assert v.edges_from("[FSD]-app:feat", "depends_on") == [], "feat 被显式清空"
    assert [e.dst for e in v.edges_from("[FSD]-app:store", "depends_on")] == ["[FSD]-app:feat"], "store 边保留"


def test_fsd_with_test_chunk_passes_gate(tmp_path: Path, monkeypatch):
    """含 :TEST 验收节点的 FSD:可解析、过门禁(非孤儿、不误判)。"""
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _bootstrap(runner)
    fsd = (
        "<!-- @id:[FSD]-app -->\n## App FSD\n\n"
        "<!-- @id:[FSD]-app:feat -->\n## feat\n\n"
        "<!-- @id:[FSD]-app:TEST -->\n## TEST 集成验收\n所有部分合并的验收。\n"
    )
    p = _run(runner, "fsd", "create", "[FSD]-app", "--content", fsd)
    assert p["ok"] is True, p
    assert combined_view(root, "v0.1").node("[FSD]-app:TEST") is not None, ":TEST chunk 已入图"
    _run(runner, "fsd", "decompose", "[PRD]-app", "[FSD]-app")
    _run(runner, "version", "commit", "v0.1")
    m = _run(runner, "version", "merge", "v0.1")
    assert m["ok"] is True, f":TEST 节点应过六不变式门禁: {m}"
