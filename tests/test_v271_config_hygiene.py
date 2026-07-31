"""v2.71 配置分层与 docs 仓治理迁移的专项回归。

覆盖 G14 残留：机器字段归属、一次性迁移能力、验收门禁 fail-closed 与快照默认值。
断言外部可观察行为（两层文件内容、git ls-files、磁盘存在性、错误码），不断言私有实现。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from ait import config_store
from ait.cli import main
from ait.init_manager import InitManager, InitManagerError
from ait.version_manager import VersionManager, VersionManagerError

PRD = "<!-- @id:[PRD]-app -->\n## App PRD\n"
FSD = "<!-- @id:[FSD]-app -->\n## App FSD\n\n<!-- @id:[FSD]-app:feat -->\n## Feat\n"
TDD = "<!-- @id:[TDD]-app-feat -->\n## TDD\n\n```yaml\ntarget_file: app/feat.py\n```\n"


def _payload(result):
    return json.loads(result.output.strip().splitlines()[-1])


def _run(runner, *args):
    return _payload(runner.invoke(main, list(args), catch_exceptions=False))


def _meta(tmp_path: Path) -> Path:
    meta = tmp_path / ".meta"
    meta.mkdir(parents=True, exist_ok=True)
    return meta


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    return root


def _git(root: Path, *args: str):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def _init_docs_repo(root: Path) -> None:
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")


def _tracked(root: Path) -> list[str]:
    return [ln for ln in _git(root, "ls-files").stdout.splitlines() if ln.strip()]


def _shared(meta: Path) -> dict:
    return yaml.safe_load((meta / "config.yaml").read_text(encoding="utf-8"))


def _local(meta: Path) -> dict:
    return yaml.safe_load((meta / "config.local.yaml").read_text(encoding="utf-8"))


# ── 1. 分层合并 ────────────────────────────────────────────────

def test_local_layer_wins_and_missing_layers_yield_empty(tmp_path: Path):
    meta = _meta(tmp_path)
    # 两层皆无：返回空且不创建任何文件（读操作无副作用）。
    assert config_store.read_config(meta) == {}
    assert not (meta / "config.yaml").exists()
    assert not (meta / "config.local.yaml").exists()

    (meta / "config.yaml").write_text(
        "initialized: true\nskill_dir: /shared/skill\n", encoding="utf-8"
    )
    # 仅共享层存在。
    assert config_store.read_config(meta)["skill_dir"] == "/shared/skill"

    (meta / "config.local.yaml").write_text("skill_dir: /local/skill\n", encoding="utf-8")
    merged = config_store.read_config(meta)
    assert merged["skill_dir"] == "/local/skill", "本地层覆盖共享层同名键"
    assert merged["initialized"] is True, "共享层独有键仍可见"


# ── 2. fail-closed 读取 ────────────────────────────────────────

def test_corrupt_layer_raises_instead_of_returning_empty(tmp_path: Path):
    meta = _meta(tmp_path)
    (meta / "config.yaml").write_text("initialized: true\n  bad-indent: [\n", encoding="utf-8")
    with pytest.raises(config_store.ConfigError) as exc:
        config_store.read_config(meta)
    assert exc.value.code == "CONFIG_UNREADABLE"


def test_non_mapping_layer_raises(tmp_path: Path):
    meta = _meta(tmp_path)
    (meta / "config.yaml").write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(config_store.ConfigError) as exc:
        config_store.read_config(meta)
    assert exc.value.code == "CONFIG_UNREADABLE"


def test_empty_file_is_treated_as_empty_config(tmp_path: Path):
    meta = _meta(tmp_path)
    (meta / "config.yaml").write_text("", encoding="utf-8")
    assert config_store.read_config(meta) == {}, "空文件是合法的空配置，区别于损坏"


# ── 3. 归属写入 ────────────────────────────────────────────────

def test_write_routes_fields_to_owning_layer(tmp_path: Path):
    meta = _meta(tmp_path)
    config_store.write_config_fields(
        meta,
        {
            "initialized": True,
            "auto_snapshot_on_merge": False,
            "skill_dir": "/s",
            "acceptance_command": "pytest -q",
        },
    )
    shared, local = _shared(meta), _local(meta)
    assert set(shared) == {"initialized", "auto_snapshot_on_merge"}
    assert set(local) == {"skill_dir", "acceptance_command"}


def test_write_shared_only_does_not_create_local_layer(tmp_path: Path):
    meta = _meta(tmp_path)
    config_store.write_config_fields(meta, {"initialized": True})
    assert not (meta / "config.local.yaml").exists(), "无字段归属该层则不触碰该层"


def test_write_refuses_corrupt_target_layer(tmp_path: Path):
    meta = _meta(tmp_path)
    (meta / "config.yaml").write_text("bad: [\n", encoding="utf-8")
    with pytest.raises(config_store.ConfigError):
        config_store.write_config_fields(meta, {"initialized": True})
    # 原内容未被覆盖 —— 不允许"用写覆盖掉一个读不出来的层"。
    assert (meta / "config.yaml").read_text(encoding="utf-8") == "bad: [\n"


# ── 4. 遗留检出与搬迁 ──────────────────────────────────────────

def test_find_legacy_machine_fields(tmp_path: Path):
    meta = _meta(tmp_path)
    assert config_store.find_legacy_machine_fields(meta) == {}
    (meta / "config.yaml").write_text(
        "initialized: true\nskill_dir: /s\nacceptance_command: pytest\n", encoding="utf-8"
    )
    assert config_store.find_legacy_machine_fields(meta) == {
        "skill_dir": "/s",
        "acceptance_command": "pytest",
    }


def test_move_machine_fields_preserves_values_and_is_idempotent(tmp_path: Path):
    meta = _meta(tmp_path)
    (meta / "config.yaml").write_text(
        "initialized: true\nskill_dir: /s\ncli_path: /s/bin/ait\n"
        "acceptance_command: pytest -q\n",
        encoding="utf-8",
    )
    moved = config_store.move_machine_fields_to_local(meta)
    assert set(moved) == {"skill_dir", "cli_path", "acceptance_command"}

    shared, local = _shared(meta), _local(meta)
    assert set(shared) == {"initialized"}, "机器字段从共享层消失"
    assert local["skill_dir"] == "/s"
    assert local["cli_path"] == "/s/bin/ait"
    assert local["acceptance_command"] == "pytest -q", "取值逐字节保真"

    # 幂等：再次搬迁无事可做，两层内容不再变化。
    before = ((meta / "config.yaml").read_text(), (meta / "config.local.yaml").read_text())
    assert config_store.move_machine_fields_to_local(meta) == {}
    assert config_store.find_legacy_machine_fields(meta) == {}
    after = ((meta / "config.yaml").read_text(), (meta / "config.local.yaml").read_text())
    assert before == after


# ── 5. init 分层落地 ───────────────────────────────────────────

def test_init_writes_machine_fields_to_local_layer_only(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AIT_SKILL_DIR", str(tmp_path / "skill"))
    root = tmp_path / "project-docs"
    InitManager(root).run(new_model=True, project_name="demo")

    meta = root / ".meta"
    shared, local = _shared(meta), _local(meta)
    assert shared["initialized"] is True
    assert shared["auto_snapshot_on_merge"] is False
    for machine_field in ("skill_dir", "cli_path", "wrapper_path"):
        assert machine_field in local
        assert machine_field not in shared, f"{machine_field} 不得进共享层"

    ignore = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert f".meta/{config_store.LOCAL_CONFIG_NAME}" in ignore


def test_init_is_idempotent_across_both_layers(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AIT_SKILL_DIR", str(tmp_path / "skill"))
    root = tmp_path / "project-docs"
    InitManager(root).run(new_model=True, project_name="demo")
    meta = root / ".meta"
    before = (
        (meta / "config.yaml").read_text(encoding="utf-8"),
        (meta / "config.local.yaml").read_text(encoding="utf-8"),
        (root / ".gitignore").read_text(encoding="utf-8"),
    )
    InitManager(root).run(new_model=True, project_name="demo")
    after = (
        (meta / "config.yaml").read_text(encoding="utf-8"),
        (meta / "config.local.yaml").read_text(encoding="utf-8"),
        (root / ".gitignore").read_text(encoding="utf-8"),
    )
    assert before == after, "重跑 init 对两层与忽略规则均幂等"


# ── 6. 迁移预览与落地 ──────────────────────────────────────────

def _seed_tracked_hygiene_targets(root: Path) -> Path:
    _init_docs_repo(root)
    snap = root / ".meta" / "snapshots" / "v0.1"
    snap.mkdir(parents=True)
    (snap / "doc.md").write_text("snapshot\n", encoding="utf-8")
    ait_dir = root / ".ait"
    ait_dir.mkdir(parents=True)
    (ait_dir / "ait-cli").write_text("#!/bin/sh\n", encoding="utf-8")
    _git(root, "add", "-A", "-f")
    _git(root, "commit", "-q", "-m", "seed")
    return snap


def test_migration_preview_reports_without_changing_anything(tmp_path: Path):
    root = _project(tmp_path)
    _seed_tracked_hygiene_targets(root)
    (root / ".meta" / "config.yaml").write_text(
        "initialized: true\nskill_dir: /s\n", encoding="utf-8"
    )
    before = _tracked(root)

    report = InitManager(root).migrate_docs_repo_hygiene(dry_run=True)
    assert report.dry_run is True and report.applicable is True
    assert any(p.startswith(".meta/snapshots/") for p in report.removed_paths)
    assert "skill_dir" in report.moved_fields
    assert _tracked(root) == before, "预览不改动 Git 索引"
    assert "skill_dir" in _shared(root / ".meta"), "预览不改动配置"


def test_migration_apply_deindexes_but_keeps_files_on_disk(tmp_path: Path):
    root = _project(tmp_path)
    snap = _seed_tracked_hygiene_targets(root)
    files_before = {p for p in root.rglob("*") if ".git" not in p.parts and p.is_file()}

    report = InitManager(root).migrate_docs_repo_hygiene(dry_run=False)
    assert report.dry_run is False and report.applicable is True

    tracked = _tracked(root)
    assert not any(p.startswith(".meta/snapshots/") for p in tracked)
    assert not any(p.startswith(".ait/") for p in tracked)
    assert (snap / "doc.md").exists(), "git rm --cached 不删除磁盘文件"

    files_after = {p for p in root.rglob("*") if ".git" not in p.parts and p.is_file()}
    # 迁移会新建 .gitignore（忽略规则必须先就位），其余工作区文件保持不变。
    assert files_before <= files_after
    assert files_after - files_before <= {root / ".gitignore"}


def test_migration_relocates_legacy_shared_fields(tmp_path: Path):
    root = _project(tmp_path)
    _init_docs_repo(root)
    (root / ".meta" / "config.yaml").write_text(
        "initialized: true\nacceptance_command: pytest -q\n", encoding="utf-8"
    )
    report = InitManager(root).migrate_docs_repo_hygiene(dry_run=False)
    assert "acceptance_command" in report.moved_fields
    assert "acceptance_command" not in _shared(root / ".meta")
    assert _local(root / ".meta")["acceptance_command"] == "pytest -q"


# ── 7. 迁移失败不静默 ─────────────────────────────────────────

def test_git_rm_failure_raises_migration_failed(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    _seed_tracked_hygiene_targets(root)
    real_run = subprocess.run

    def fake_run(argv, *args, **kwargs):
        if isinstance(argv, list) and argv[:3] == ["git", "rm", "--cached"]:
            return subprocess.CompletedProcess(argv, 1, "", "fatal: simulated failure")
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(InitManagerError) as exc:
        InitManager(root).migrate_docs_repo_hygiene(dry_run=False)
    assert exc.value.code == "MIGRATION_FAILED"


# ── 8. 迁移边界 ───────────────────────────────────────────────

def test_non_git_docs_dir_reports_not_applicable(tmp_path: Path):
    root = _project(tmp_path)  # 未 git init
    report = InitManager(root).migrate_docs_repo_hygiene(dry_run=True)
    assert report.applicable is False
    assert report.removed_paths == [] and report.moved_fields == {}


def test_clean_repo_migration_is_empty_and_idempotent(tmp_path: Path):
    root = _project(tmp_path)
    _init_docs_repo(root)
    mgr = InitManager(root)
    first = mgr.migrate_docs_repo_hygiene(dry_run=False)
    second = mgr.migrate_docs_repo_hygiene(dry_run=False)
    assert first.removed_paths == [] and first.moved_fields == {}
    assert second.removed_paths == [] and second.moved_fields == {}
    assert first.applicable is True and second.applicable is True


# ── 8b. CLI 迁移入口 ─────────────────────────────────────────

def test_cli_migrate_previews_only(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    _seed_tracked_hygiene_targets(root)
    (root / ".meta" / "config.yaml").write_text(
        "initialized: true\nskill_dir: /s\n", encoding="utf-8"
    )
    before = _tracked(root)

    payload = _run(CliRunner(), "init", "--migrate")
    assert payload["ok"] is True
    assert payload["data"]["dry_run"] is True
    assert payload["data"]["applicable"] is True
    assert any(p.startswith(".meta/snapshots/") for p in payload["data"]["removed_paths"])
    assert payload["data"]["moved_fields"] == ["skill_dir"], "只输出键名，不输出机器取值"
    assert _tracked(root) == before, "预览不改动索引"


def test_cli_migrate_apply_deindexes(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    snap = _seed_tracked_hygiene_targets(root)

    payload = _run(CliRunner(), "init", "--migrate", "--apply")
    assert payload["ok"] is True and payload["data"]["dry_run"] is False
    tracked = _tracked(root)
    assert not any(p.startswith(".meta/snapshots/") for p in tracked)
    assert (snap / "doc.md").exists()


def test_cli_apply_without_migrate_is_usage_error(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    payload = _run(CliRunner(), "init", "--apply")
    assert payload["ok"] is False and payload["code"] == "USAGE_ERROR"


def test_cli_migrate_on_non_git_repo_reports_not_applicable(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    payload = _run(CliRunner(), "init", "--migrate")
    assert payload["ok"] is True, "不适用不伪装成失败"
    assert payload["data"]["applicable"] is False


# ── 9. 验收门禁 fail-closed ───────────────────────────────────

def test_corrupt_config_fails_acceptance_closed(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    (root / ".meta" / "config.yaml").write_text("acceptance_command: [\n", encoding="utf-8")
    with pytest.raises(VersionManagerError) as exc:
        VersionManager(root).run_acceptance()
    assert exc.value.code == "CONFIG_UNREADABLE", "损坏配置必须拒绝，而非静默跳过门禁"


def test_unconfigured_acceptance_still_skips(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    assert VersionManager(root).run_acceptance() == {
        "passed": True,
        "skipped": True,
        "command": None,
    }


def test_corrupt_config_surfaces_through_cli(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    (root / ".meta" / "config.yaml").write_text("acceptance_command: [\n", encoding="utf-8")
    payload = _run(CliRunner(), "acceptance", "run")
    assert payload["ok"] is False and payload["code"] == "CONFIG_UNREADABLE"


# ── 10. 验收命令归属与遗留拒绝 ────────────────────────────────

def test_set_acceptance_command_lands_in_local_layer(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    VersionManager(root).set_acceptance_command("pytest -q")
    assert _local(root / ".meta")["acceptance_command"] == "pytest -q"
    assert not (root / ".meta" / "config.yaml").exists() or (
        "acceptance_command" not in _shared(root / ".meta")
    )


def test_legacy_shared_acceptance_command_is_refused_not_executed(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    probe = tmp_path / "probe-executed"
    # 探针：若该命令被执行，标记文件就会出现。
    (root / ".meta" / "config.yaml").write_text(
        f"acceptance_command: touch {probe}\n", encoding="utf-8"
    )
    with pytest.raises(VersionManagerError) as exc:
        VersionManager(root).run_acceptance()
    assert exc.value.code == "LEGACY_ACCEPTANCE_CONFIG"
    assert not probe.exists(), "共享层残留命令绝不能被执行"


def test_unset_acceptance_command_clears_legacy_shared_copy(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    (root / ".meta" / "config.yaml").write_text(
        "initialized: true\nacceptance_command: pytest\n", encoding="utf-8"
    )
    VersionManager(root).set_acceptance_command(None)
    assert "acceptance_command" not in _shared(root / ".meta")


# ── 11. 快照默认值 ────────────────────────────────────────────

def _build_and_merge(runner, version: str) -> None:
    _run(runner, "version", "create", version)
    _run(runner, "prd", "create", "[PRD]-app", "--skip-context", "--content", PRD)
    _run(runner, "prd", "confirm")
    _run(runner, "fsd", "create", "[FSD]-app", "--parent", "[PRD]-app",
         "--skip-context", "--content", FSD)
    _run(runner, "fsd", "confirm")
    _run(runner, "tdd", "create", "[TDD]-app-feat", "--parent", "[FSD]-app:feat",
         "--skip-context", "--content", TDD)
    _run(runner, "tdd", "confirm")
    _run(runner, "version", "commit", version)
    _run(runner, "version", "confirm", version)
    _run(runner, "version", "merge", version)


def test_snapshot_absent_when_field_missing(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    _build_and_merge(CliRunner(), "v0.1")
    assert not (root / ".meta" / "snapshots" / "v0.1").exists(), (
        "字段缺失时默认关闭（v2.71 收口）"
    )


def test_snapshot_present_when_explicitly_enabled(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    (root / ".meta" / "config.yaml").write_text(
        "auto_snapshot_on_merge: true\n", encoding="utf-8"
    )
    _build_and_merge(CliRunner(), "v0.1")
    assert (root / ".meta" / "snapshots" / "v0.1").exists(), "显式开启的项目行为不变"
