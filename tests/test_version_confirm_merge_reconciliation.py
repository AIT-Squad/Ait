"""v2.61 G21: one persisted reconciliation plan for confirm and merge."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from ait.schemas import ReconciliationOperation, VersionChunkEntry
from ait.version_manager import VersionManager, VersionManagerError


def _manager_with_new_file_record(tmp_path: Path) -> VersionManager:
    root = tmp_path / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    manager = VersionManager(root)
    manager.create("v1.0")
    manager.write_version_file(
        "v1.0",
        "prd/new",
        "<!-- @id:prd-new -->\n## New\n\nfirst\n",
    )
    index = manager.indexes.load_version_index("v1.0")
    index.chunks.append(
        VersionChunkEntry(
            id="prd-new",
            file="prd/new",
            heading="New",
            level=2,
            action="modify",
            state="committed",
            overrides="prd-new",
        )
    )
    manager.indexes.save_version_index(index)
    return manager


def test_confirm_normalizes_missing_baseline_modify_and_persists_plan(tmp_path: Path):
    manager = _manager_with_new_file_record(tmp_path)

    report = manager.confirm_plan("v1.0")
    plan = manager.load_version_meta("v1.0").confirmed_plan

    assert report["plan_fingerprint"]
    assert plan is not None
    assert plan.operations[0].action == "add"
    assert plan.operations[0].target_id is None


def test_merge_rejects_input_changed_after_confirm_without_writing_baseline(tmp_path: Path):
    manager = _manager_with_new_file_record(tmp_path)
    manager.confirm_plan("v1.0")
    manager.write_version_file(
        "v1.0",
        "prd/new",
        "<!-- @id:prd-new -->\n## New\n\nchanged\n",
    )

    with pytest.raises(VersionManagerError) as excinfo:
        manager.merge_confirmed("v1.0")

    assert excinfo.value.code == "CONFIRMATION_STALE"
    assert not (manager.root / "docs" / "prd" / "new.md").exists()


def test_merge_rejects_tampered_persisted_plan(tmp_path: Path):
    manager = _manager_with_new_file_record(tmp_path)
    manager.confirm_plan("v1.0")
    meta = manager.load_version_meta("v1.0")
    assert meta.confirmed_plan is not None
    operation = meta.confirmed_plan.operations[0].model_copy(
        update={"new_content": "<!-- @id:prd-new -->\n## New\n\ntampered\n"}
    )
    meta.confirmed_plan = meta.confirmed_plan.model_copy(update={"operations": [operation]})
    manager.save_version_meta(meta)

    with pytest.raises(VersionManagerError) as excinfo:
        manager.merge_confirmed("v1.0")

    assert excinfo.value.code == "CONFIRMATION_STALE"
    assert not (manager.root / "docs" / "prd" / "new.md").exists()


def test_merge_rejects_specgraph_changed_after_confirm(tmp_path: Path):
    manager = _manager_with_new_file_record(tmp_path)
    manager.confirm_plan("v1.0")
    (manager.meta_dir / "specgraph-v1.0.yaml").write_text("version: 1\nedges: []\n", encoding="utf-8")

    with pytest.raises(VersionManagerError) as excinfo:
        manager.merge_confirmed("v1.0")

    assert excinfo.value.code == "CONFIRMATION_STALE"
    assert not (manager.root / "docs" / "prd" / "new.md").exists()


def test_reconciliation_plan_rejects_path_traversal():
    with pytest.raises(ValidationError):
        ReconciliationOperation(
            file="../outside",
            chunk_id="prd-new",
            action="add",
            new_content="<!-- @id:prd-new -->\n## New\n",
        )
