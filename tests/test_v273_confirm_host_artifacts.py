"""v2.73 G25: version confirm commits the host artifact repo and binds code_result."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ait.version_manager import VersionManager


def _init_host_with_docs(tmp_path: Path) -> VersionManager:
    """host repo (git) ⊃ project-docs — so self.root.parent is the host git repo."""
    host = tmp_path / "host"
    root = host / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=host, capture_output=True)
    subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=host, capture_output=True)
    subprocess.run(["git", "config", "user.name", "x"], cwd=host, capture_output=True)
    # project-docs is an independent repo, gitignored by the host (v2.55 isolation)
    (host / ".gitignore").write_text("project-docs/\n", encoding="utf-8")
    (host / "seed.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=host, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=host, capture_output=True)
    return VersionManager(root)


def _host_head(vm: VersionManager) -> str:
    r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=vm.root.parent,
                       capture_output=True, text=True)
    return r.stdout.strip()


def test_commit_host_artifacts_commits_when_dirty(tmp_path: Path):
    vm = _init_host_with_docs(tmp_path)
    vm.create("v1.0")
    before = _host_head(vm)
    # make host dirty (an artifact change)
    (vm.root.parent / "seed.py").write_text("x = 2\n", encoding="utf-8")

    result = vm._commit_host_artifacts("v1.0")

    assert result["committed"] is True
    assert result["files"] >= 1
    after = _host_head(vm)
    assert after != before
    assert result["sha"] == after
    # commit message tagged with the version
    msg = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=vm.root.parent,
                         capture_output=True, text=True).stdout.strip()
    assert msg == "AIT v1.0 artifacts"


def test_commit_host_artifacts_noop_when_clean(tmp_path: Path):
    vm = _init_host_with_docs(tmp_path)
    vm.create("v1.0")
    head = _host_head(vm)

    result = vm._commit_host_artifacts("v1.0")

    assert result["committed"] is False
    assert result["files"] == 0
    assert result["sha"] == head          # clean → binds current HEAD, no new commit
    assert _host_head(vm) == head


def test_commit_host_artifacts_vacuous_when_non_git_host(tmp_path: Path):
    # project-docs whose parent is NOT a git repo
    root = tmp_path / "plain" / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    vm = VersionManager(root)
    vm.create("v1.0")

    result = vm._commit_host_artifacts("v1.0")

    assert result == {"committed": False, "sha": None, "files": 0}
