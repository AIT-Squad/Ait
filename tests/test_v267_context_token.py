from __future__ import annotations

import json
from pathlib import Path

import pytest

from click.testing import CliRunner

from ait.cli import main
from ait.schemas import DiscussionUsage
from ait.validator import ValidationError
from ait.version_manager import VersionManager


PRD = "<!-- @id:[PRD]-app -->\n## App\n"
FSD = "<!-- @id:[FSD]-app -->\n## App\n\n<!-- @id:[FSD]-app:core -->\n## Core\n"
TDD = "<!-- @id:[TDD]-app-core -->\n## Core\n```yaml\ntarget_file: app/core.py\n```\n"


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    return root


def _payload(result):
    assert result.output, result.exception
    return json.loads(result.output.strip().splitlines()[-1])


def _run(runner: CliRunner, *args: str):
    result = runner.invoke(main, list(args), catch_exceptions=False)
    return _payload(result)


def _token(runner: CliRunner, *args: str) -> str:
    payload = _run(runner, *args)
    assert payload["ok"] is True, payload
    return payload["data"]["context_token"]


def test_context_token_is_stable_and_gates_prd_write(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    assert _run(runner, "version", "create", "v0.1")["ok"] is True

    token = _token(runner, "prd", "create", "[PRD]-app")
    assert token == _token(runner, "prd", "create", "[PRD]-app")

    missing = _run(runner, "prd", "create", "[PRD]-app", "--content", PRD)
    assert missing["code"] == "CONTEXT_TOKEN_REQUIRED"
    assert not (root / "versions" / "v0.1" / "prd" / "[PRD]-app.md").exists()

    stale = _run(
        runner,
        "prd",
        "create",
        "[PRD]-app",
        "--content",
        PRD,
        "--action",
        "modify",
        "--overrides",
        "[PRD]-app",
        "--context-token",
        token,
    )
    assert stale["code"] == "CONTEXT_TOKEN_STALE"
    assert not (root / "versions" / "v0.1" / "prd" / "[PRD]-app.md").exists()

    created = _run(
        runner,
        "prd",
        "create",
        "[PRD]-app",
        "--content",
        PRD,
        "--context-token",
        token,
    )
    assert created["ok"] is True
    index_text = (root / ".meta" / "chunks-index-v0.1.yaml").read_text(encoding="utf-8")
    assert "discussion_usage" in index_text and token not in index_text


def test_context_token_covers_fsd_tdd_and_content_decompose(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    runner = CliRunner()
    _run(runner, "version", "create", "v0.1")
    _run(runner, "prd", "create", "[PRD]-app", "--content", PRD, "--skip-context")
    _run(runner, "prd", "confirm")

    fsd_token = _token(runner, "fsd", "create", "[FSD]-app")
    fsd = _run(runner, "fsd", "create", "[FSD]-app", "--content", FSD, "--context-token", fsd_token)
    assert fsd["ok"] is True

    child = "<!-- @id:[FSD]-app-child -->\n## Child\n"
    decompose_token = _token(runner, "fsd", "decompose", "[FSD]-app:core", "[FSD]-app-child")
    decompose = _run(
        runner,
        "fsd",
        "decompose",
        "[FSD]-app:core",
        "[FSD]-app-child",
        "--content",
        child,
        "--context-token",
        decompose_token,
    )
    assert decompose["ok"] is True and decompose["data"]["rel"] == "decomposes"

    _run(runner, "fsd", "confirm")
    tdd_token = _token(runner, "tdd", "create", "[TDD]-app-core", "--parent", "[FSD]-app:core")
    tdd = _run(
        runner,
        "tdd",
        "create",
        "[TDD]-app-core",
        "--parent",
        "[FSD]-app:core",
        "--content",
        TDD,
        "--context-token",
        tdd_token,
    )
    assert tdd["ok"] is True


def test_skip_is_audited_and_schema_rejects_invalid_receipts(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _run(runner, "version", "create", "v0.1")
    created = _run(runner, "prd", "create", "[PRD]-app", "--content", PRD, "--skip-context")
    assert created["ok"] is True
    _run(runner, "prd", "confirm")

    index = VersionManager(root).indexes.load_version_index("v0.1")
    assert index.chunks[0].discussion_usage == DiscussionUsage(mode="skipped")
    change_path = root / ".meta" / "changes" / "chg-001.yaml"
    assert "discussion_usage:\n  mode: skipped" in change_path.read_text(encoding="utf-8")

    with pytest.raises(Exception):
        DiscussionUsage(mode="receipt", receipt_digest="sha256:not-a-digest")
    with pytest.raises(Exception):
        DiscussionUsage(mode="skipped", receipt_digest="sha256:" + "0" * 64)


def test_context_skip_conflict_and_direct_api_are_rejected(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _run(runner, "version", "create", "v0.1")
    token = _token(runner, "prd", "create", "[PRD]-app")
    conflict = _run(
        runner,
        "prd",
        "create",
        "[PRD]-app",
        "--content",
        PRD,
        "--context-token",
        token,
        "--skip-context",
    )
    assert conflict["code"] == "CONTEXT_TOKEN_CONFLICT"

    from ait.new_model_manager import NewModelManager

    with pytest.raises(ValidationError) as error:
        NewModelManager(root).create_prd("v0.1", "[PRD]-app", PRD)
    assert error.value.issues[0].code == "CONTEXT_TOKEN_REQUIRED"
