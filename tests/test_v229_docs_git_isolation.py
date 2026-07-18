"""v2.55 docs/code 隔离仓测试。

project-docs 独立成 git 仓:
- init 后 project-docs/.git 存在
- 宿主 .gitignore 含 project-docs/
- docs .gitignore 含 versions/*/state.md
- 版本进行中 confirm 不因 docs 仓 dirty 失败(GIT_DIRTY 预检已去除)
- merge 后 meta.docs_commit 有值; meta.code_base 有值(宿主是 git 仓时)
- merge 后 docs 仓 git status 干净
- 全程幂等
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ait.init_manager import InitManager
from ait.new_model_manager import NewModelManager
from ait.version_manager import VersionManager


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    return root


def _git(path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=path,
        capture_output=True, text=True,
    )


def test_init_creates_docs_git_repo(tmp_path: Path):
    """init 在 project-docs 内建立独立 git 仓。"""
    root = _project(tmp_path)
    InitManager(root).run()
    assert (root / ".git").is_dir(), "project-docs/.git 须存在"


def test_init_adds_project_docs_to_host_gitignore(tmp_path: Path):
    """init 在宿主根 .gitignore 追加 project-docs/ 行。"""
    root = _project(tmp_path)
    InitManager(root).run()
    host_ignore = tmp_path / ".gitignore"
    assert host_ignore.exists(), "宿主 .gitignore 须存在"
    assert "project-docs/" in host_ignore.read_text(encoding="utf-8").splitlines()


def test_init_docs_gitignore_excludes_state_md(tmp_path: Path):
    """docs 仓 .gitignore 排除 versions/*/state.md(派生产物)。"""
    root = _project(tmp_path)
    InitManager(root).run()
    docs_ignore = root / ".gitignore"
    assert docs_ignore.exists(), "project-docs/.gitignore 须存在"
    assert "versions/*/state.md" in docs_ignore.read_text(encoding="utf-8").splitlines()


def test_init_docs_git_idempotent(tmp_path: Path):
    """重跑 init 幂等:不重复追加 gitignore 行。"""
    root = _project(tmp_path)
    mgr = InitManager(root)
    mgr.run()
    mgr.run()  # 第二次
    host_ignore = tmp_path / ".gitignore"
    lines = host_ignore.read_text(encoding="utf-8").splitlines()
    assert lines.count("project-docs/") == 1, "project-docs/ 不得重复追加"
    docs_ignore = root / ".gitignore"
    lines2 = docs_ignore.read_text(encoding="utf-8").splitlines()
    assert lines2.count("versions/*/state.md") == 1, "state.md 行不得重复"


def test_confirm_not_blocked_by_dirty_docs_repo(tmp_path: Path):
    """版本进行中 docs 仓 dirty 时 confirm 仍能通过(GIT_DIRTY 预检已去除)。"""
    root = _project(tmp_path)
    vm = VersionManager(root)
    mgr = NewModelManager(root)
    vm.create("v0.1")
    mgr.create_prd("v0.1", "[PRD]-app", "<!-- @id:[PRD]-app -->\n## App\n")
    mgr.confirm_prd_layer("v0.1")
    mgr.create_fsd(
        "v0.1", "[FSD]-app",
        "<!-- @id:[FSD]-app -->\n## F\n\n<!-- @id:[FSD]-app:core -->\n## core\n",
        parent_chunk_id="[PRD]-app",
    )
    mgr.confirm_fsd_layer("v0.1")
    mgr.create_tdd(
        "v0.1", "[TDD]-core",
        "<!-- @id:[TDD]-core -->\n## T\n```yaml\ntarget_file: src/core.py\n```\n",
        parent_chunk_id="[FSD]-app:core",
    )
    mgr.confirm_tdd_layer("v0.1")

    # docs 仓现在 dirty(version 工作区有未提交文件)
    # confirm(gate) 不得因此失败
    result = vm.gate("v0.1")
    assert result["passed"] is True, f"gate 不应因 dirty docs 失败: {result}"


def test_merge_records_docs_commit_and_code_base(tmp_path: Path):
    """merge 后 meta 记录 docs_commit + code_base。"""
    root = _project(tmp_path)
    vm = VersionManager(root)
    mgr = NewModelManager(root)

    # docs repo git init (initial commit so host git doesn't see it as broken submodule)
    _git(root, "init")
    _git(root, "config", "user.email", "a@b.c")
    _git(root, "config", "user.name", "x")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "base-docs")

    # host repo init with its own file — use explicit path, not -A, to avoid
    # "project-docs does not have a commit checked out" from nested repo
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "a@b.c")
    _git(tmp_path, "config", "user.name", "x")
    (tmp_path / "README.md").write_text("host")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-m", "init")

    vm.create("v0.1")
    mgr.create_prd("v0.1", "[PRD]-app", "<!-- @id:[PRD]-app -->\n## App\n")
    mgr.confirm_prd_layer("v0.1")
    mgr.create_fsd(
        "v0.1", "[FSD]-app",
        "<!-- @id:[FSD]-app -->\n## F\n\n<!-- @id:[FSD]-app:core -->\n## core\n",
        parent_chunk_id="[PRD]-app",
    )
    mgr.confirm_fsd_layer("v0.1")
    mgr.create_tdd(
        "v0.1", "[TDD]-core",
        "<!-- @id:[TDD]-core -->\n## T\n```yaml\ntarget_file: src/core.py\n```\n",
        parent_chunk_id="[FSD]-app:core",
    )
    mgr.confirm_tdd_layer("v0.1")

    # initial commit in docs repo
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "base")

    result = vm.confirm("v0.1", allow_dirty_git=True)
    meta = vm.load_version_meta("v0.1")

    assert meta.docs_commit is not None, "docs_commit 须有值"
    assert len(meta.docs_commit) >= 7, "docs_commit 须是 git sha"
    assert meta.code_base is not None, "宿主是 git 仓时 code_base 须有值"
    # docs repo clean after merge
    status = _git(root, "status", "--porcelain").stdout.strip()
    assert status == "", f"merge 后 docs 仓须干净,got: {status!r}"


def test_merge_code_base_none_when_host_not_git(tmp_path: Path):
    """宿主非 git 仓时 code_base=None,merge 仍成功。"""
    root = _project(tmp_path)
    vm = VersionManager(root)
    mgr = NewModelManager(root)

    _git(root, "init")
    _git(root, "config", "user.email", "a@b.c")
    _git(root, "config", "user.name", "x")

    vm.create("v0.1")
    mgr.create_prd("v0.1", "[PRD]-app", "<!-- @id:[PRD]-app -->\n## App\n")
    mgr.confirm_prd_layer("v0.1")
    mgr.create_fsd(
        "v0.1", "[FSD]-app",
        "<!-- @id:[FSD]-app -->\n## F\n\n<!-- @id:[FSD]-app:core -->\n## core\n",
        parent_chunk_id="[PRD]-app",
    )
    mgr.confirm_fsd_layer("v0.1")
    mgr.create_tdd(
        "v0.1", "[TDD]-core",
        "<!-- @id:[TDD]-core -->\n## T\n```yaml\ntarget_file: src/core.py\n```\n",
        parent_chunk_id="[FSD]-app:core",
    )
    mgr.confirm_tdd_layer("v0.1")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "base")

    result = vm.confirm("v0.1", allow_dirty_git=True)
    assert result["version"] == "v0.1"
    meta = vm.load_version_meta("v0.1")
    assert meta.code_base is None, "宿主非 git 仓时 code_base 须 None"
    assert meta.docs_commit is not None
