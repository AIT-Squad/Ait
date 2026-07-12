"""v2.21 version 命令四件套 + 无 impl 预建目录。

create(显式开版本/拒重复/不预建 impl) · confirm(纯门禁,可重复跑零落盘) ·
merge(原子合入,门禁前置) · revert(未合入版本清空)。走 CLI 真实路径。
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from ait.cli import main
from ait.new_model_manager import NewModelManager
from ait.version_manager import VersionManager


def _payload(result):
    return json.loads(result.output.strip().splitlines()[-1])


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    return root


FSD = "<!-- @id:[FSD]-app -->\n## App\n\n<!-- @id:[FSD]-app:feat -->\n## Feat\n"
TDD = "<!-- @id:[TDD]-app-feat -->\n## T\n\n```yaml\ntarget_file: app/feat.py\n```\n"
PRD = "<!-- @id:[PRD]-app -->\n## P\n"


def _build_valid_version(root: Path, runner: CliRunner, version: str) -> None:
    """A minimally invariant-compliant new-model version via CLI."""
    def run(*args):
        r = runner.invoke(main, list(args), catch_exceptions=False)
        assert r.exit_code == 0, r.output
        assert _payload(r)["ok"] is True, r.output
        return _payload(r)["data"]

    run("prd", "create", "[PRD]-app", "--version", version, "--content", PRD)
    run("fsd", "create", "[FSD]-app", "--version", version, "--content", FSD)
    run("tdd", "create", "[TDD]-app-feat", "--version", version, "--content", TDD)
    run("fsd", "decompose", "[PRD]-app", "[FSD]-app", "--version", version)
    # details 边由 tdd 层原子建立(v2.24);此处用底层原语搭脚手架
    NewModelManager(root).add_edge(version, "[FSD]-app:feat", "[TDD]-app-feat", "details")


def test_version_create_explicit_and_no_impl_dir(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    r = runner.invoke(main, ["version", "create", "v9.0"], catch_exceptions=False)
    assert _payload(r)["ok"] is True
    assert (root / ".meta" / "versions" / "v9.0.yaml").exists()
    # v2.21: 不再预建 legacy impl/ 目录
    assert not (root / "versions" / "v9.0" / "impl").exists()
    assert not (root / "versions" / "v9.0" / "prd").exists()


def test_version_create_rejects_ghost_duplicate(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["version", "create", "v9.0"], catch_exceptions=False)
    r = runner.invoke(main, ["version", "create", "v9.0"], catch_exceptions=False)
    assert _payload(r)["ok"] is False


def test_confirm_is_pure_gate_repeatable_zero_write(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    # 只建 FSD+TDD,缺 PRD → 门禁应报违例
    runner.invoke(main, ["fsd", "create", "[FSD]-app", "--version", "v9.0", "--content", FSD], catch_exceptions=False)
    runner.invoke(main, ["tdd", "create", "[TDD]-app-feat", "--version", "v9.0", "--content", TDD], catch_exceptions=False)
    NewModelManager(root).add_edge("v9.0", "[FSD]-app:feat", "[TDD]-app-feat", "details")
    runner.invoke(main, ["version", "commit", "v9.0"], catch_exceptions=False)

    before = (root / ".meta" / "chunks-index.yaml").read_bytes() if (root / ".meta" / "chunks-index.yaml").exists() else None
    r1 = runner.invoke(main, ["version", "confirm", "v9.0"], catch_exceptions=False)
    p1 = _payload(r1)
    assert p1["ok"] is False and p1["code"] == "INVARIANT_VIOLATION"
    # 纯门禁:未合入,可重复跑,基线零落盘
    assert VersionManager(root).load_version_meta("v9.0").merged_at is None
    r2 = runner.invoke(main, ["version", "confirm", "v9.0"], catch_exceptions=False)
    assert _payload(r2)["ok"] is False  # 可重复跑,结论一致
    after = (root / ".meta" / "chunks-index.yaml").read_bytes() if (root / ".meta" / "chunks-index.yaml").exists() else None
    assert before == after, "纯门禁不得改动基线索引"


def test_confirm_passes_then_merge_commits(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(VersionManager, "_git_commit", lambda self, m: "cafe123")
    runner = CliRunner()
    _build_valid_version(root, runner, "v9.0")
    runner.invoke(main, ["version", "commit", "v9.0"], catch_exceptions=False)

    # confirm(纯门禁)通过
    r = runner.invoke(main, ["version", "confirm", "v9.0"], catch_exceptions=False)
    assert _payload(r)["ok"] is True and _payload(r)["data"]["passed"] is True
    assert VersionManager(root).load_version_meta("v9.0").merged_at is None, "confirm 不合入"

    # merge 原子合入
    r = runner.invoke(main, ["version", "merge", "v9.0", "--allow-dirty-git"], catch_exceptions=False)
    assert _payload(r)["ok"] is True
    assert VersionManager(root).load_version_meta("v9.0").merged_at is not None


def test_merge_blocked_by_gate_before_any_write(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(VersionManager, "_git_commit", lambda self, m: "cafe123")
    runner = CliRunner()
    # 缺 PRD → 门禁前置应拦 merge
    runner.invoke(main, ["fsd", "create", "[FSD]-app", "--version", "v9.0", "--content", FSD], catch_exceptions=False)
    runner.invoke(main, ["tdd", "create", "[TDD]-app-feat", "--version", "v9.0", "--content", TDD], catch_exceptions=False)
    NewModelManager(root).add_edge("v9.0", "[FSD]-app:feat", "[TDD]-app-feat", "details")
    runner.invoke(main, ["version", "commit", "v9.0"], catch_exceptions=False)

    r = runner.invoke(main, ["version", "merge", "v9.0", "--allow-dirty-git"], catch_exceptions=False)
    p = _payload(r)
    assert p["ok"] is False and p["code"] == "INVARIANT_VIOLATION"
    assert VersionManager(root).load_version_meta("v9.0").merged_at is None, "门禁拦截须零落盘"


def test_version_revert_wipes_unmerged(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["version", "create", "v9.0"], catch_exceptions=False)
    runner.invoke(main, ["fsd", "create", "[FSD]-app", "--version", "v9.0", "--content", FSD], catch_exceptions=False)

    r = runner.invoke(main, ["version", "revert", "v9.0", "--confirm"], catch_exceptions=False)
    assert _payload(r)["ok"] is True
    assert not (root / ".meta" / "versions" / "v9.0.yaml").exists()
    assert not (root / "versions" / "v9.0").exists()
