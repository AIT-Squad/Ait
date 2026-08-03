"""v2.74 G19: codegen prepare delivers the bundle via an ephemeral temp file.

v2.80: the delivered artifact is the rendered text (codegen_brief), not JSON;
this file also covers the renderer itself ([TDD]-codegen_delivery_tests).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from ait.cli import main
from ait.codegen_brief import EMPTY_MARK, SECTIONS, STATUS_TEXT, render
from ait.version_manager import VersionManager
from ait.new_model_manager import CodegenBundle, NewModelManager


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
    # v2.80: the file carries the rendered delivery text, not JSON
    assert bundle_path.suffix == ".md"
    assert "src/core.py" in raw
    for title, _reasons in SECTIONS:
        assert title in raw
    assert '\\"' not in raw  # a JSON payload would escape the spec's quotes


def _bundle(**overrides):
    """A CodegenBundle with only the fields a render test cares about."""
    fields = dict(
        version="v0.1",
        tdd_root="[TDD]-demo-core",
        target_file="src/core.py",
        source_file="tdd/[TDD]-demo-core",
        chunks=[{"id": "[TDD]-demo-core", "heading": "T", "file": "tdd/x", "content": "## T"}],
        upstream=[],
        dependencies=[],
        target_file_status="absent",
        target_file_content=None,
    )
    fields.update(overrides)
    return CodegenBundle(**fields)


def _item(chunk_id, reason, content="body"):
    return {
        "id": chunk_id,
        "heading": chunk_id,
        "file": "fsd/x",
        "type": "fsd",
        "content": content,
        "selection_reason": reason,
    }


def test_render_preserves_spec_verbatim():
    """The spec must survive byte-for-byte — no JSON escaping.

    Note the escape-check asymmetry: a spec may legitimately contain the two
    characters ``\\`` + ``n`` (it quotes code about newline handling), so
    "output has no \\n" would be self-contradictory. What JSON *adds* is a
    backslash before a bare quote and a second backslash before a literal one —
    those are the sequences with discriminating power.
    """
    spec = '- `normalize(text)`：`replace("\\r\\n","\\n").strip()`\n\n```yaml\nk: v\n```'
    out = render(_bundle(chunks=[{"id": "[TDD]-x", "heading": "x", "file": "tdd/x", "content": spec}]))
    assert spec in out          # strongest verbatim proof: JSON escaping would break this
    assert '\\"' not in out     # JSON would escape the bare quotes
    assert "\\\\r" not in out   # JSON would double the literal backslash


def test_render_section_order_and_reason_mapping():
    reasons = [
        "parent_split", "depends_on_contract", "fsd_ancestor",
        "test_covered_sibling", "test_implementation_tdd", "prd_root", "prd_requirement",
    ]
    out = render(_bundle(upstream=[_item("[FSD]-r-%s" % r, r) for r in reasons]))
    positions = [out.index("## %d. %s" % (i, t)) for i, (t, _) in enumerate(SECTIONS, 1)]
    assert positions == sorted(positions)
    # every reason's item lands inside the section that declares it
    for index, (_title, section_reasons) in enumerate(SECTIONS):
        if not section_reasons:
            continue
        start = positions[index]
        end = positions[index + 1] if index + 1 < len(positions) else len(out)
        for reason in section_reasons:
            assert out.index("[FSD]-r-%s" % reason) > start
            assert out.index("[FSD]-r-%s" % reason) < end


def test_render_empty_section_marked():
    out = render(_bundle())
    start = out.index("## 3. ")
    end = out.index("## 4. ")
    assert EMPTY_MARK in out[start:end]


@pytest.mark.parametrize("status", ["loaded", "absent", "unreadable"])
def test_render_target_file_status(status):
    content = "x = 1\n" if status == "loaded" else None
    out = render(_bundle(target_file_status=status, target_file_content=content))
    assert STATUS_TEXT[status] in out
    if status == "unreadable":
        assert "禁止生成" in out and "报错退出" in out
        assert STATUS_TEXT["absent"] not in out


def test_render_unknown_status_falls_back_to_unreadable():
    out = render(_bundle(target_file_status="weird"))
    assert STATUS_TEXT["unreadable"] in out


def test_render_is_deterministic():
    bundle = _bundle(upstream=[_item("[FSD]-a", "parent_split"), _item("[FSD]-b", "fsd_ancestor")])
    first, second = render(bundle), render(bundle)
    assert first == second
    assert hashlib.sha256(first.encode()).hexdigest() == hashlib.sha256(second.encode()).hexdigest()
