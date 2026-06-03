from __future__ import annotations

from pathlib import Path

import pytest

from ait.schemas import TaskYaml
from ait.task_manager import TaskManager, TaskManagerError


def test_task_id_format_blocks(tmp_path: Path):
    root = tmp_path / "project-docs"
    (root / "versions" / "v1.1" / "tasks").mkdir(parents=True)
    mgr = TaskManager(root)
    task = TaskYaml(
        id="T-foo-3",
        title="bad task",
        source_chunk="prd-foo",
        status="created",
    )

    with pytest.raises(TaskManagerError) as exc:
        mgr.save_task("v1.1", task)

    assert exc.value.code == "DERIVED_NAME_VIOLATION"
    assert not (root / "versions" / "v1.1" / "tasks" / "T-foo-3.yaml").exists()
