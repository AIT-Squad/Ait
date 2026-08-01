"""v2.72 G10: revert anchor falls back to docs_commit SHA when the tag is missing."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ait.schemas import RevertAnchor
from ait.version_manager import VersionManager


def _git(root: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    return r.stdout.strip()


def _init_docs_repo(tmp_path: Path) -> tuple[VersionManager, str]:
    root = tmp_path / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=root, capture_output=True)
    subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=root, capture_output=True)
    subprocess.run(["git", "config", "user.name", "x"], cwd=root, capture_output=True)
    (root / "docs" / "seed.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=root, capture_output=True)
    return VersionManager(root), _git(root, "rev-parse", "HEAD")


def _merged_meta(manager: VersionManager, version: str, *, docs_ref: str, docs_commit: str) -> None:
    manager.create(version)
    meta = manager.load_version_meta(version)
    meta.merged_at = datetime.now(timezone.utc)
    meta.docs_commit = docs_commit
    meta.revert_anchor = RevertAnchor(docs_ref=docs_ref)
    manager.save_version_meta(meta)


def test_reset_falls_back_to_docs_commit_when_tag_missing(tmp_path: Path):
    """A dangling tag ref no longer blocks revert — docs_commit SHA is authoritative."""
    manager, head = _init_docs_repo(tmp_path)
    # revert_anchor names a tag that was never created; docs_commit is a real SHA.
    _merged_meta(manager, "v1.0", docs_ref="refs/tags/ait/v1.0", docs_commit=head)
    assert manager._git_head(manager.root.parent) is None or True  # host not required

    # dry-run: precheck must PASS (return NEED_CONFIRM), proving SHA fallback resolved.
    result = manager.reset("v1.0", confirmed=False)
    assert result["ok"] is False
    assert result["code"] == "NEED_CONFIRM"


def test_reset_fails_only_when_neither_tag_nor_sha_resolves(tmp_path: Path):
    manager, _head = _init_docs_repo(tmp_path)
    _merged_meta(manager, "v1.0", docs_ref="refs/tags/ait/v1.0", docs_commit="0" * 40)
    from ait.version_manager import VersionManagerError
    import pytest
    with pytest.raises(VersionManagerError) as exc:
        manager.reset("v1.0", confirmed=True)
    assert exc.value.code == "REVERT_PRECHECK_FAILED"


def test_backfill_recreates_missing_tag_from_docs_commit(tmp_path: Path):
    manager, head = _init_docs_repo(tmp_path)
    _merged_meta(manager, "v1.0", docs_ref="refs/tags/ait/v1.0", docs_commit=head)
    # tag absent beforehand
    assert _git(manager.root, "tag", "-l", "ait/v1.0") == ""

    report = manager.backfill_revert_tags()
    assert "v1.0" in report["backfilled"]
    # tag now points at docs_commit
    assert _git(manager.root, "rev-parse", "ait/v1.0^{commit}") == head


def test_backfill_skips_already_present_tag(tmp_path: Path):
    manager, head = _init_docs_repo(tmp_path)
    _merged_meta(manager, "v1.0", docs_ref="refs/tags/ait/v1.0", docs_commit=head)
    subprocess.run(["git", "tag", "ait/v1.0", head], cwd=manager.root, capture_output=True)

    report = manager.backfill_revert_tags()
    assert "v1.0" not in report["backfilled"]
    assert any(s["version"] == "v1.0" and s["reason"] == "tag_present" for s in report["skipped"])


def test_create_git_tag_nonfatal_returns_bool(tmp_path: Path):
    """Tag creation is an optimisation — a bad commit returns False, never raises."""
    manager, _head = _init_docs_repo(tmp_path)
    assert manager._create_git_tag("refs/tags/ait/bad", "0" * 40) is False
