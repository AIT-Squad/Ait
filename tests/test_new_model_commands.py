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

    edge = _run(
        runner,
        [
            "fsd",
            "link",
            "[FSD]-book_management:loan_service",
            "[TDD]-book_management-loan_service",
            "--rel",
            "details",
            "--version",
            "v9.0",
        ],
    )
    assert edge["rel"] == "details"

    _run(
        runner,
        [
            "fsd",
            "link",
            "[FSD]-book_management:loan_service",
            "[FSD]-book_management:persistence",
            "--rel",
            "depends_on",
            "--version",
            "v9.0",
        ],
    )
    _run(
        runner,
        [
            "fsd",
            "link",
            "[FSD]-book_management:persistence",
            "[FSD]-book_management-persistence",
            "--rel",
            "decomposes",
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
    assert payload["code"] == "VALIDATION_FAILED"
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
