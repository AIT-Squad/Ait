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
