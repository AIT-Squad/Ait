"""v2.61 G10: merged revert fails closed before either repository changes."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from ait.schemas import RevertAnchor
from ait.version_manager import VersionManager, VersionManagerError


def test_revert_rejects_unresolvable_anchor_before_any_reset(tmp_path: Path):
    root = tmp_path / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    manager = VersionManager(root)
    manager.create("v1.0")
    meta = manager.load_version_meta("v1.0")
    meta.merged_at = datetime.now(timezone.utc)
    meta.revert_anchor = RevertAnchor(docs_ref="refs/tags/ait/v1.0")
    manager.save_version_meta(meta)
    before = manager.version_meta_path("v1.0").read_bytes()

    with pytest.raises(VersionManagerError) as excinfo:
        manager.reset("v1.0", confirmed=True)

    assert excinfo.value.code == "REVERT_PRECHECK_FAILED"
    assert manager.version_meta_path("v1.0").read_bytes() == before
