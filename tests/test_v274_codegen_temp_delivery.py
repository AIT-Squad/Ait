"""v2.74 G19: codegen prepare delivers the bundle via an ephemeral temp file."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from click.testing import CliRunner

from ait.cli import main
from ait.version_manager import VersionManager
from ait.new_model_manager import NewModelManager


def _payload(result):
    return json.loads(result.output.strip().splitlines()[-1])


def _mini_merged_project(root: Path) -> None:
    import subprocess
    vm = VersionManager(root)
    mgr = NewModelManager(root)
    vm.create("v0.1")
    mgr.create_prd("v0.1", "[PRD]-demo", "<!-- @id:[PRD]-demo -->\n## Demo\n", skip_context=True)
    mgr.confirm_prd_layer("v0.1")
    mgr.create_fsd(
        "v0.1", "[FSD]-demo",
        "<!-- @id:[FSD]-demo -->\n## F\n\n<!-- @id:[FSD]-demo:core -->\n## core\n",
        parent_chunk_id="[PRD]-demo", skip_context=True,
    )
    mgr.confirm_fsd_layer("v0.1")
    mgr.create_tdd(
        "v0.1", "[TDD]-demo-core",
        "<!-- @id:[TDD]-demo-core -->\n## T\n```yaml\ntarget_file: src/core.py\n```\n",
        parent_chunk_id="[FSD]-demo:core", skip_context=True,
    )
    mgr.confirm_tdd_layer("v0.1")
    subprocess.run(["git", "init", "-q"], cwd=root, capture_output=True)
    subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=root, capture_output=True)
    subprocess.run(["git", "config", "user.name", "x"], cwd=root, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, capture_output=True)
    vm.confirm("v0.1", allow_dirty_git=True)


def test_codegen_prepare_writes_temp_file_pointer(tmp_path: Path, monkeypatch):
    root = tmp_path / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    _mini_merged_project(root)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    r = runner.invoke(main, ["codegen", "prepare", "[TDD]-demo-core"], catch_exceptions=False)
    data = _payload(r)["data"]

    # stdout is a compact pointer with target_file at top level
    assert data["target_file"] == "src/core.py"
    assert data["tdd_root"] == "[TDD]-demo-core"
    assert "upstream" not in data
    # the temp bundle lives outside any repo (system temp), never git-tracked
    bundle_path = Path(data["bundle_path"])
    assert bundle_path.exists()
    assert "project-docs" not in str(bundle_path)
    # hash covers the file content → truncation is detectable
    raw = bundle_path.read_text(encoding="utf-8")
    assert hashlib.sha256(raw.encode("utf-8")).hexdigest() == data["sha256"]
    assert data["bytes"] == len(raw.encode("utf-8"))
    # the file carries the full bundle
    bundle = json.loads(raw)
    assert bundle["target_file"] == "src/core.py"
    assert "upstream" in bundle and "dependencies" in bundle
