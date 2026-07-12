from __future__ import annotations

import json
from pathlib import Path

import yaml
from click.testing import CliRunner

from ait.cli import main
from ait.specgraph import sync_specgraph
from ait.version_manager import VersionManager


def _payload(result):
    return json.loads(result.output.strip().splitlines()[-1])


def _run(runner: CliRunner, args: list[str]):
    result = runner.invoke(main, args, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    payload = _payload(result)
    assert payload["ok"] is True, payload
    return payload["data"]


def test_fsd_tdd_codegen_commands(tmp_path: Path, monkeypatch):
    root = tmp_path / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    VersionManager(root).create("v9.0")
    monkeypatch.chdir(tmp_path)

    fsd_content = """<!-- @id:[FSD]-book_management -->
## Book Management

<!-- @id:[FSD]-book_management:loan_service -->
## Loan Service

<!-- @id:[FSD]-book_management:persistence -->
## Persistence
"""
    storage_fsd_content = """<!-- @id:[FSD]-book_management-persistence -->
## Persistence FSD
"""
    tdd_content = """<!-- @id:[TDD]-book_management-loan_service -->
## Loan Service TDD

```yaml
target_file: app/services/loan_service.py
```
"""
    runner = CliRunner()

    fsd = _run(
        runner,
        [
            "fsd",
            "create",
            "[FSD]-book_management",
            "--version",
            "v9.0",
            "--content",
            fsd_content,
        ],
    )
    assert fsd["chunks"] == [
        "[FSD]-book_management",
        "[FSD]-book_management:loan_service",
        "[FSD]-book_management:persistence",
    ]

    _run(
        runner,
        [
            "fsd",
            "create",
            "[FSD]-book_management-persistence",
            "--version",
            "v9.0",
            "--content",
            storage_fsd_content,
        ],
    )

    tdd = _run(
        runner,
        [
            "tdd",
            "create",
            "[TDD]-book_management-loan_service",
            "--version",
            "v9.0",
            "--content",
            tdd_content,
        ],
    )
    assert tdd["chunks"] == ["[TDD]-book_management-loan_service"]

    # v2.23: fsd link 退役。details/depends_on 边用底层原语 add_edge 搭脚手架
    # (details 归 tdd 层原子建立;此处直接建图供 codegen 断言),decomposes 走 fsd decompose。
    from ait.new_model_manager import NewModelManager

    mgr = NewModelManager(root)
    edge = mgr.add_edge(
        "v9.0",
        "[FSD]-book_management:loan_service",
        "[TDD]-book_management-loan_service",
        "details",
    )
    assert edge.rel == "details"

    mgr.add_edge(
        "v9.0",
        "[FSD]-book_management:loan_service",
        "[FSD]-book_management:persistence",
        "depends_on",
    )
    _run(
        runner,
        [
            "fsd",
            "decompose",
            "[FSD]-book_management:persistence",
            "[FSD]-book_management-persistence",
            "--version",
            "v9.0",
        ],
    )

    graph = yaml.safe_load((root / ".meta" / "specgraph-v9.0.yaml").read_text(encoding="utf-8"))
    assert any(item["rel"] == "details" for item in graph["edges"])
    sync_specgraph(root)
    graph_after_sync = yaml.safe_load((root / ".meta" / "specgraph-v9.0.yaml").read_text(encoding="utf-8"))
    assert {item["rel"] for item in graph_after_sync["edges"]} == {"details", "depends_on", "decomposes"}

    bundle = _run(
        runner,
        [
            "codegen",
            "prepare",
            "[TDD]-book_management-loan_service",
            "--version",
            "v9.0",
        ],
    )
    assert bundle["target_file"] == "app/services/loan_service.py"
    assert bundle["tdd_root"] == "[TDD]-book_management-loan_service"
    assert [item["id"] for item in bundle["upstream"]] == [
        "[FSD]-book_management:loan_service",
        "[FSD]-book_management",
    ]
    assert [item["id"] for item in bundle["dependencies"]] == [
        "[FSD]-book_management:persistence",
        "[FSD]-book_management-persistence",
    ]


def test_tdd_create_requires_target_file(tmp_path: Path, monkeypatch):
    root = tmp_path / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    VersionManager(root).create("v9.0")
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "tdd",
            "create",
            "[TDD]-missing-target",
            "--version",
            "v9.0",
            "--content",
            "<!-- @id:[TDD]-missing-target -->\n## Missing\n",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 1
    payload = _payload(result)
    assert payload["ok"] is False
    assert payload["code"] == "TDD_TARGET_FILE_REQUIRED"
    assert "target_file" in payload["error"]


# ── v2.18: decomposes 环/自环下 prepare_codegen 上溯不爆栈（audit R2-01）──


def _init_new_model_project(tmp_path: Path, monkeypatch):
    root = tmp_path / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    VersionManager(root).create("v9.0")
    monkeypatch.chdir(tmp_path)
    from ait.new_model_manager import NewModelManager

    return NewModelManager(root)


def test_prepare_codegen_survives_self_loop_cycle(tmp_path: Path, monkeypatch):
    """split 反指自己的根（[FSD]-mod:leaf decomposes [FSD]-mod）→ 上溯短路不递归爆栈。"""
    mgr = _init_new_model_project(tmp_path, monkeypatch)
    mgr.create_fsd(
        "v9.0",
        "[FSD]-mod",
        "<!-- @id:[FSD]-mod -->\n## Mod\n\n<!-- @id:[FSD]-mod:leaf -->\n## Leaf\n",
    )
    mgr.create_tdd(
        "v9.0",
        "[TDD]-mod-leaf",
        "<!-- @id:[TDD]-mod-leaf -->\n## TDD\n\n```yaml\ntarget_file: app/mod/leaf.py\n```\n",
    )
    mgr.add_edge("v9.0", "[FSD]-mod:leaf", "[TDD]-mod-leaf", "details")
    mgr.add_edge("v9.0", "[FSD]-mod:leaf", "[FSD]-mod", "decomposes")

    bundle = mgr.prepare_codegen("v9.0", "[TDD]-mod-leaf")

    ids = [item["id"] for item in bundle.upstream]
    assert len(ids) == len(set(ids)), f"上溯链存在重复收集: {ids}"


def test_prepare_codegen_survives_mutual_cycle(tmp_path: Path, monkeypatch):
    """两根互指环（A:x decomposes B、B:y decomposes A）→ 上溯每节点至多一次、正常返回。"""
    mgr = _init_new_model_project(tmp_path, monkeypatch)
    mgr.create_fsd(
        "v9.0",
        "[FSD]-alpha",
        "<!-- @id:[FSD]-alpha -->\n## Alpha\n\n<!-- @id:[FSD]-alpha:x -->\n## X\n",
    )
    mgr.create_fsd(
        "v9.0",
        "[FSD]-beta",
        "<!-- @id:[FSD]-beta -->\n## Beta\n\n<!-- @id:[FSD]-beta:y -->\n## Y\n",
    )
    mgr.create_tdd(
        "v9.0",
        "[TDD]-alpha-x",
        "<!-- @id:[TDD]-alpha-x -->\n## TDD\n\n```yaml\ntarget_file: app/alpha/x.py\n```\n",
    )
    mgr.add_edge("v9.0", "[FSD]-alpha:x", "[TDD]-alpha-x", "details")
    mgr.add_edge("v9.0", "[FSD]-beta:y", "[FSD]-alpha", "decomposes")
    mgr.add_edge("v9.0", "[FSD]-alpha:x", "[FSD]-beta", "decomposes")

    bundle = mgr.prepare_codegen("v9.0", "[TDD]-alpha-x")

    ids = [item["id"] for item in bundle.upstream]
    assert len(ids) == len(set(ids)), f"上溯链存在重复收集: {ids}"
    assert "[FSD]-beta:y" in ids and "[FSD]-beta" in ids, "环上节点应各收集一次"


# ── v2.19: modify 进版本的 TDD,codegen 上下文完整(v2.18 发现的 URI 二象性缺口)──


def test_prepare_codegen_full_upstream_for_modified_tdd(tmp_path: Path, monkeypatch):
    """TDD 经 --action modify 进版本后,prepare_codegen(version) 仍取得完整上溯链,
    且 TDD 内容来源切到版本工作区。修复前 upstream/dependencies 均为空。"""
    root = tmp_path / "project-docs"
    (root / "docs" / "fsd").mkdir(parents=True)
    (root / "docs" / "tdd").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    (root / "docs" / "fsd" / "[FSD]-app.md").write_text(
        "<!-- @id:[FSD]-app -->\n## App\n\n<!-- @id:[FSD]-app:feat -->\n## Feat\n",
        encoding="utf-8",
    )
    (root / "docs" / "fsd" / "[FSD]-app-util.md").write_text(
        "<!-- @id:[FSD]-app-util -->\n## Util\n\n<!-- @id:[FSD]-app-util:helpers -->\n## Helpers\n",
        encoding="utf-8",
    )
    (root / "docs" / "tdd" / "[TDD]-app-feat.md").write_text(
        "<!-- @id:[TDD]-app-feat -->\n## TDD baseline\n\n```yaml\ntarget_file: app/feat.py\n```\n",
        encoding="utf-8",
    )
    vm = VersionManager(root)
    vm.indexes.rebuild_baseline()
    sync_specgraph(root)

    from ait.specgraph import load_specgraph, make_uri, specgraph_path

    g = load_specgraph(root)
    fsd_file = "fsd/[FSD]-app"
    g.add_edge(
        make_uri("[FSD]-app:feat", "baseline", fsd_file),
        make_uri("[TDD]-app-feat", "baseline", "tdd/[TDD]-app-feat"),
        "details",
        metadata={"source": "new-model-cli"},
    )
    g.add_edge(
        make_uri("[FSD]-app:feat", "baseline", fsd_file),
        make_uri("[FSD]-app-util:helpers", "baseline", "fsd/[FSD]-app-util"),
        "depends_on",
        metadata={"source": "new-model-cli"},
    )
    g.save(specgraph_path(root))
    vm.create("v9.0")
    monkeypatch.chdir(tmp_path)

    from ait.new_model_manager import NewModelManager

    mgr = NewModelManager(root)
    mgr.create_tdd(
        "v9.0",
        "[TDD]-app-feat",
        "<!-- @id:[TDD]-app-feat -->\n## TDD v2 modified\n\n```yaml\ntarget_file: app/feat.py\n```\n",
        action="modify",
        overrides="[TDD]-app-feat",
    )

    bundle = mgr.prepare_codegen("v9.0", "[TDD]-app-feat")

    ids = [u["id"] for u in bundle.upstream]
    assert ids and ids[0] == "[FSD]-app:feat", f"上溯链首项应为父 split,得到 {ids}"
    assert "[FSD]-app" in ids, f"上溯链应含 FSD 根,得到 {ids}"
    dep_ids = [u["id"] for u in bundle.dependencies]
    assert "[FSD]-app-util:helpers" in dep_ids, f"依赖上下文缺失,得到 {dep_ids}"
    assert "TDD v2 modified" in bundle.chunks[0]["content"], "TDD 内容来源应切到版本工作区"
