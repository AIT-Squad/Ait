"""v2.27 合入与 JSON 契约加固。

R1-06 git commit 三分语义;R1-07/08 override 冲突前置拦截;
R3-02 --file 路径清洗;R3-05 click 参数错误 JSON 化。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from click.testing import CliRunner

from ait.chunk_parser import parse_text
from ait.cli import main
from ait.schemas import VersionChunkEntry
from ait.version_manager import VersionManager, VersionManagerError


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


def _set_phase(root: Path, version: str, phase: str) -> None:
    """P7 脚手架:置 phase,以到达本文件要测的层(相位门禁本身在
    test_v222/223/224 专测;这里测 --file 清洗 / git 三分 / 回滚)。"""
    vm = VersionManager(root)
    meta = vm.load_version_meta(version)
    meta.phase = phase  # type: ignore[assignment]
    vm.save_version_meta(meta)


# ── R1-06: _git_commit 三分 ──────────────────────────────────────────


def test_git_commit_returns_none_outside_repo(tmp_path: Path):
    root = _project(tmp_path)
    assert VersionManager(root)._git_commit("msg") is None, "非 repo 容忍为 None"


def test_git_commit_noop_returns_head_and_real_commit_advances(tmp_path: Path):
    root = _project(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    (root / "seed.txt").write_text("seed", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=root, check=True)
    head0 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                           capture_output=True, text=True).stdout.strip()

    vm = VersionManager(root)
    assert vm._git_commit("noop") == head0, "nothing-to-commit → 返回当前 HEAD"

    (root / "new.txt").write_text("x", encoding="utf-8")
    head1 = vm._git_commit("real")
    assert head1 and head1 != head0, "真实提交推进 HEAD"


def test_confirm_reports_git_unavailable(tmp_path: Path, monkeypatch):
    """非 git 环境 merge 成功但显式标注 git:unavailable,不再伪装 commit。"""
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _run(runner, "version", "create", "v0.1")
    _run(runner, "prd", "create", "[PRD]-app", "--content", "<!-- @id:[PRD]-app -->\n## P\n")
    _run(runner, "prd", "confirm")
    _run(runner, "fsd", "create", "[FSD]-app", "--content", "<!-- @id:[FSD]-app -->\n## F\n")
    _run(runner, "fsd", "decompose", "[PRD]-app", "[FSD]-app")
    _run(runner, "version", "commit", "v0.1")

    p = _run(runner, "version", "merge", "v0.1")
    assert p["ok"] is True
    assert p["data"]["commit"] is None and p["data"]["git"] == "unavailable"


def test_git_commit_failure_rolls_back(tmp_path: Path, monkeypatch):
    """git commit 真实失败 → MERGE_ROLLBACK,merged 标记不残留(R1-06 假成功杜绝)。"""
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _run(runner, "version", "create", "v0.1")
    _run(runner, "prd", "create", "[PRD]-app", "--content", "<!-- @id:[PRD]-app -->\n## P\n")
    _run(runner, "prd", "confirm")
    _run(runner, "fsd", "create", "[FSD]-app", "--content", "<!-- @id:[FSD]-app -->\n## F\n")
    _run(runner, "fsd", "decompose", "[PRD]-app", "[FSD]-app")
    _run(runner, "version", "commit", "v0.1")

    def boom(self, message):
        raise VersionManagerError("git commit 失败: simulated", code="GIT_COMMIT_FAILED")

    monkeypatch.setattr(VersionManager, "_git_commit", boom)
    p = _run(runner, "version", "merge", "v0.1")
    assert p["ok"] is False and p["code"] == "MERGE_ROLLBACK"
    assert VersionManager(root).load_version_meta("v0.1").merged_at is None, "回滚后无 merged 残留"


# ── R1-07/08: override 冲突前置拦截 ──────────────────────────────────


def _committed(chunk_id: str, action: str, overrides: str | None = None) -> VersionChunkEntry:
    return VersionChunkEntry(
        id=chunk_id, file=f"fsd/{chunk_id}", heading=chunk_id, level=2,
        action=action, state="committed", commit_id="c1", overrides=overrides,
    )


def _baseline_with(root: Path, *chunk_ids: str) -> None:
    for cid in chunk_ids:
        (root / "docs" / "fsd").mkdir(parents=True, exist_ok=True)
        (root / "docs" / "fsd" / f"{cid}.md").write_text(
            f"<!-- @id:{cid} -->\n## {cid}\n", encoding="utf-8")
    VersionManager(root).indexes.rebuild_baseline()


def test_modify_rename_collision_intercepted(tmp_path: Path):
    root = _project(tmp_path)
    _baseline_with(root, "[FSD]-a", "[FSD]-b")
    vm = VersionManager(root)
    vm.create("v9.0")
    idx = vm.indexes.load_version_index("v9.0")
    idx.chunks.append(_committed("[FSD]-b", "modify", overrides="[FSD]-a"))  # 改名撞已存在 [FSD]-b
    vm.indexes.save_version_index(idx)

    report = vm.gate("v9.0")
    codes = {v["code"] for v in report["violations"]}
    assert "MODIFY_RENAME_COLLISION" in codes

    try:
        vm.confirm("v9.0", allow_dirty_git=True)
        raise AssertionError("confirm 应被拦截")
    except VersionManagerError as exc:
        assert exc.code == "MODIFY_RENAME_COLLISION"


def test_duplicate_override_target_intercepted(tmp_path: Path):
    root = _project(tmp_path)
    _baseline_with(root, "[FSD]-a")
    vm = VersionManager(root)
    vm.create("v9.0")
    idx = vm.indexes.load_version_index("v9.0")
    idx.chunks.append(_committed("[FSD]-x", "modify", overrides="[FSD]-a"))
    idx.chunks.append(_committed("[FSD]-y", "modify", overrides="[FSD]-a"))  # 撞同一目标
    vm.indexes.save_version_index(idx)

    report = vm.gate("v9.0")
    codes = {v["code"] for v in report["violations"]}
    assert "DUPLICATE_OVERRIDES_TARGET" in codes


# ── R3-02: --file 清洗 ───────────────────────────────────────────────


def test_file_escape_rejected_zero_write(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _run(runner, "version", "create", "v9.0")
    _set_phase(root, "v9.0", "prd-confirm")  # 到 FSD 层以测 --file 清洗

    for bad in ("../../ESCAPED", "fsd/../../x", "abs.md", "/etc/x", "C:/evil"):
        p = _run(runner, "fsd", "create", "[FSD]-app", "--version", "v9.0",
                 "--file", bad, "--content", "<!-- @id:[FSD]-app -->\n## F\n")
        assert p["ok"] is False and p["code"] == "INVALID_FILE_NAME", f"{bad}: {p}"
    escaped = list(tmp_path.rglob("ESCAPED*"))
    assert not escaped, "禁止逃逸落盘"


def test_file_cross_kind_rejected_and_shortname_ok(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = _project(tmp_path)
    runner = CliRunner()
    _run(runner, "version", "create", "v9.0")

    _set_phase(root, "v9.0", "fsd-confirm")  # 到 TDD 层以测跨 kind --file 拒
    p = _run(runner, "tdd", "create", "[TDD]-x", "--version", "v9.0",
             "--file", "fsd/x",
             "--content", "<!-- @id:[TDD]-x -->\n## T\n```yaml\ntarget_file: a.py\n```\n")
    assert p["ok"] is False and p["code"] == "INVALID_FILE_NAME", "跨 kind 拒"

    _set_phase(root, "v9.0", "prd-confirm")  # 回 FSD 层以测简名补前缀
    p = _run(runner, "fsd", "create", "[FSD]-app", "--version", "v9.0",
             "--file", "custom_name", "--content", "<!-- @id:[FSD]-app -->\n## F\n")
    assert p["ok"] is True
    assert (root / "versions" / "v9.0" / "fsd" / "custom_name.md").exists(), "简名补 kind 前缀"


# ── R3-05: USAGE_ERROR JSON 化 ───────────────────────────────────────


def test_usage_errors_emit_json(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    runner = CliRunner()

    r = runner.invoke(main, ["nonexistent-command"])
    p = _payload(r)
    assert p["ok"] is False and p["code"] == "USAGE_ERROR" and r.exit_code == 2

    r = runner.invoke(main, ["fsd", "decompose"])  # 缺位置参数
    p = _payload(r)
    assert p["ok"] is False and p["code"] == "USAGE_ERROR"

    r = runner.invoke(main, ["fsd", "create", "[FSD]-x", "--action", "zap", "--content", "x"])
    p = _payload(r)
    assert p["ok"] is False and p["code"] == "USAGE_ERROR"


def test_help_still_prints_text(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _project(tmp_path)
    r = CliRunner().invoke(main, ["--help"])
    assert r.exit_code == 0
    assert "Usage" in r.output and "version" in r.output
