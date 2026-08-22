"""v2.92 G19: the codegen pointer's sha256/bytes must hold for the on-disk bytes.

Reading the bundle back in *binary* is the whole point: text mode silently
translates CRLF back to LF, which is exactly what hid the defect (Path.write_text
expanded LF to CRLF on Windows while the digest was taken over the pre-write
string, so the pointer could never match the file).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from click.testing import CliRunner

from ait.cli import main
from ait.new_model_manager import NewModelManager
from ait.version_manager import VersionManager


def _payload(result):
    return json.loads(result.output.strip().splitlines()[-1])


def _mini_merged_project(root: Path) -> None:
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


def test_pointer_digest_matches_on_disk_bytes(tmp_path: Path, monkeypatch):
    root = tmp_path / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    _mini_merged_project(root)
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    r = runner.invoke(main, ["codegen", "prepare", "[TDD]-demo-core"], catch_exceptions=False)
    data = _payload(r)["data"]

    raw = Path(data["bundle_path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == data["sha256"]
    assert len(raw) == data["bytes"]
    assert b"\r\n" not in raw
