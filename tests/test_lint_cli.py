from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ait.cli import main
from ait.index_manager import IndexManager
from ait.specgraph import sync_specgraph
from ait.version_manager import VersionManager


def _parse(out: str) -> dict:
    return json.loads(out.strip().splitlines()[-1])


@pytest.fixture
def cli_project(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "project-docs"
    for d in [
        "docs/prd",
        "docs/impl",
        "versions",
        ".meta/versions",
        ".meta/changes",
        ".meta/requirements",
    ]:
        (root / d).mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    return root


def _clean_prd() -> str:
    return """<!-- @id:prd-demo-feature -->
## Demo

### 概述

A

### 业务规则

B

### 验收标准

C

### 边界与非目标

D
"""


def test_lint_baseline_clean(cli_project: Path):
    root = cli_project
    (root / "docs" / "prd" / "demo.md").write_text(_clean_prd(), encoding="utf-8")
    IndexManager(root).rebuild_baseline()
    sync_specgraph(root)

    res = CliRunner().invoke(main, ["lint", "--scope", "baseline"], catch_exceptions=False)
    payload = _parse(res.output)

    assert res.exit_code == 0
    assert payload == {"ok": True, "violations": [], "fixed_files": []}


def test_lint_fix_english_to_chinese(cli_project: Path):
    root = cli_project
    (root / "docs" / "prd" / "demo.md").write_text(
        """<!-- @id:prd-demo-feature -->
## Demo

### Goal

A

### Approach

B

### Acceptance

C

### Non-Goals

D
""",
        encoding="utf-8",
    )

    res = CliRunner().invoke(main, ["lint", "--scope", "baseline", "--fix"], catch_exceptions=False)
    payload = _parse(res.output)
    text = (root / "docs" / "prd" / "demo.md").read_text(encoding="utf-8")

    assert res.exit_code == 0
    assert payload["ok"] is True
    assert payload["violations"] == []
    assert "### 概述" in text
    assert "### Goal" not in text


def test_lint_fix_only_fixable(cli_project: Path):
    root = cli_project
    (root / "docs" / "prd" / "demo.md").write_text(
        """<!-- @id:prd-demo-feature -->
## Demo

### Goal

A

### Acceptance

C

### Approach

B

### Non-Goals

D
""",
        encoding="utf-8",
    )

    res = CliRunner().invoke(main, ["lint", "--scope", "baseline", "--fix"], catch_exceptions=False)
    payload = _parse(res.output)
    text = (root / "docs" / "prd" / "demo.md").read_text(encoding="utf-8")

    assert res.exit_code == 1
    assert payload["ok"] is False
    assert any(not v["fixable"] for v in payload["violations"])
    assert "### Goal" not in text
    assert "### 概述" in text
