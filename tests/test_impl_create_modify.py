from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from ait.cli import main


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


def _run(runner: CliRunner, *args: str):
    return runner.invoke(main, [*args], catch_exceptions=False)


def _parse(output: str) -> dict:
    return json.loads(output.strip().splitlines()[-1])


def _prd_chunk(chunk_id: str) -> str:
    return (
        f"<!-- @id:{chunk_id} -->\n## Recommend\n\n<!-- @summary: recommend -->\n\n"
        "### Overview\n\nbody\n\n"
        "### Business Rules\n\nrules\n\n"
        "### Acceptance Criteria\n\naccept\n\n"
        "### Boundaries and Non-Goals\n\nbounds\n"
    )


def _impl_chunk(chunk_id: str) -> str:
    return (
        f"<!-- @id:{chunk_id} -->\n## API\n\n<!-- @summary: api -->\n\n"
        "<!-- @ref:prd/global#prd-recommend-overview rel:implements -->\n\n"
        "GET /recommend\n"
    )


def _seed_baseline(root: Path, runner: CliRunner) -> None:
    (root / "docs" / "prd" / "global.md").write_text(
        _prd_chunk("prd-recommend-overview"),
        encoding="utf-8",
    )
    (root / "docs" / "impl" / "recommend.md").write_text(
        _impl_chunk("impl-recommend-overview-api"),
        encoding="utf-8",
    )
    assert _run(runner, "reindex").exit_code == 0


def test_impl_create_modify_writes_action_and_overrides(cli_project: Path):
    runner = CliRunner()
    _seed_baseline(cli_project, runner)
    assert _run(runner, "prd", "create", "modify impl", "--version", "v1.1").exit_code == 0

    new_impl = (
        "<!-- @id:impl-recommend-overview-api-v2 -->\n"
        "## API v2\n\n"
        "<!-- @summary: api v2 -->\n\n"
        "GET /recommend/v2\n"
    )
    res = _run(
        runner,
        "impl",
        "create",
        "prd-recommend-overview",
        "--content",
        new_impl,
        "--action",
        "modify",
        "--overrides",
        "impl-recommend-overview-api",
    )
    payload = _parse(res.output)

    assert res.exit_code == 0
    assert payload["data"]["chunk_ids"] == ["impl-recommend-overview-api-v2"]
    index = yaml.safe_load((cli_project / ".meta" / "chunks-index-v1.1.yaml").read_text(encoding="utf-8"))
    entry = next(c for c in index["chunks"] if c["id"] == "impl-recommend-overview-api-v2")
    assert entry["action"] == "modify"
    assert entry["overrides"] == "impl-recommend-overview-api"
    assert entry["base_hash"]


def test_impl_create_modify_requires_overrides(cli_project: Path):
    runner = CliRunner()
    _seed_baseline(cli_project, runner)
    assert _run(runner, "prd", "create", "modify impl", "--version", "v1.1").exit_code == 0

    res = _run(
        runner,
        "impl",
        "create",
        "prd-recommend-overview",
        "--content",
        "<!-- @id:impl-recommend-overview-api-v2 -->\n## API v2\n\n<!-- @summary: api v2 -->\n\nGET /v2\n",
        "--action",
        "modify",
    )
    payload = _parse(res.output)

    assert res.exit_code == 1
    assert payload["code"] == "OVERRIDES_REQUIRED"


def test_impl_create_add_rejects_overrides(cli_project: Path):
    runner = CliRunner()
    _seed_baseline(cli_project, runner)
    assert _run(runner, "prd", "create", "modify impl", "--version", "v1.1").exit_code == 0

    res = _run(
        runner,
        "impl",
        "create",
        "prd-recommend-overview",
        "--content",
        "<!-- @id:impl-recommend-overview-api-v2 -->\n## API v2\n\n<!-- @summary: api v2 -->\n\nGET /v2\n",
        "--overrides",
        "impl-recommend-overview-api",
    )
    payload = _parse(res.output)

    assert res.exit_code == 1
    assert payload["code"] == "OVERRIDES_NOT_ALLOWED"


def test_impl_create_modify_requires_baseline_override(cli_project: Path):
    runner = CliRunner()
    _seed_baseline(cli_project, runner)
    assert _run(runner, "prd", "create", "modify impl", "--version", "v1.1").exit_code == 0

    res = _run(
        runner,
        "impl",
        "create",
        "prd-recommend-overview",
        "--content",
        "<!-- @id:impl-recommend-overview-api-v2 -->\n## API v2\n\n<!-- @summary: api v2 -->\n\nGET /v2\n",
        "--action",
        "modify",
        "--overrides",
        "impl-missing",
    )
    payload = _parse(res.output)

    assert res.exit_code == 1
    assert payload["code"] == "OVERRIDES_NOT_IN_BASELINE"


def test_subskills_require_user_confirmation_before_persisting():
    discuss = Path("skill/ait/sub-skills/ait-discuss/SKILL.md").read_text(encoding="utf-8")
    impl = Path("skill/ait/sub-skills/ait-impl-discuss/SKILL.md").read_text(encoding="utf-8")

    assert "Wait for explicit user confirmation before calling" in discuss
    assert "Do not introduce a change plan concept" in discuss
    assert "baseline-summary --scope prd --format yaml" in discuss
    assert "inspect the old chunk content with `context <overrides>`" in discuss
    assert "A modify chunk is a full replacement chunk, not a patch" in discuss
    assert "merge does not backfill old content" in discuss
    assert "Before calling `impl inherit`" in impl
    assert "Before creating an impl modify" in impl
    assert "--action modify --overrides" in impl
