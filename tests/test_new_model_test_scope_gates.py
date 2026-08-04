"""v2.83 artifact_scopes governance gates ([TDD]-new_model_manager_test_scope_gates_tests).

Covers the write-time bidirectional TDD_SCOPE_PARENT_MISMATCH gate, the
TARGET_FILE_SCOPE_ESCAPE path-escape gate, the `:TEST` acceptance-split
coverage gate (TEST_SPLIT_UNCOVERED), and the host-artifact coverage
reconciliation (UNCOVERED_ARTIFACT) in ``VersionManager.gate()``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from ait.new_model_manager import NewModelManager
from ait.specgraph import load_specgraph
from ait.validator import ValidationError
from ait.version_manager import VersionManager

PRD = (
    "<!-- @id:[PRD]-app -->\n## App\n\n"
    "<!-- @id:[PRD]-app:feat -->\n## Feat\n\n"
    "**用户故事:** 作为用户，我需要 feat 能力。\n\n"
    "#### 验收标准\n\n1. WHEN x THEN y\n"
)
FSD = (
    "<!-- @id:[FSD]-app -->\n## App\n\n"
    "<!-- @id:[FSD]-app:feat -->\n## Feat\n\n"
    "<!-- @id:[FSD]-app:TEST -->\n## Tests\n"
)


def _set_scopes(root: Path, enforcement: str, exempt: list[str] | None = None) -> None:
    (root / ".meta" / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "artifact_scopes": {
                    "tests/": {
                        "parent_suffix": ":TEST",
                        "enforcement": enforcement,
                        "exempt_test_splits": exempt or [],
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def _project(tmp_path: Path, *, host_git: bool = False) -> Path:
    """project-docs skeleton, optionally under a git-initialised host dir."""
    base = (tmp_path / "host") if host_git else tmp_path
    root = base / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    if host_git:
        subprocess.run(["git", "init", "-q"], cwd=base, capture_output=True)
        subprocess.run(["git", "config", "user.email", "a@b.c"], cwd=base, capture_output=True)
        subprocess.run(["git", "config", "user.name", "x"], cwd=base, capture_output=True)
        (base / ".gitignore").write_text("project-docs/\n", encoding="utf-8")
    VersionManager(root).create("v9.0")
    return root


def _set_phase(root: Path, version: str, phase: str) -> None:
    vm = VersionManager(root)
    meta = vm.load_version_meta(version)
    meta.phase = phase  # type: ignore[assignment]
    vm.save_version_meta(meta)


def _to_tdd_creating(root: Path, version: str = "v9.0") -> NewModelManager:
    """PRD → FSD, both confirmed, phase left at fsd-confirm (tdd create allowed)."""
    mgr = NewModelManager(root)
    _set_phase(root, version, "prd-creating")
    mgr.create_prd(version, "[PRD]-app", PRD, skip_context=True)
    mgr.confirm_prd_layer(version)
    mgr.create_fsd(version, "[FSD]-app", FSD, skip_context=True)
    mgr._add_edge(version, "[PRD]-app", "[FSD]-app", "derives")
    mgr.confirm_fsd_layer(version)
    return mgr


# ── write-time bidirectional scope gate ─────────────────────────────────


def test_scope_mismatch_rejected_when_target_in_scope_but_parent_not_test(tmp_path: Path):
    root = _project(tmp_path)
    _set_scopes(root, "block")
    mgr = _to_tdd_creating(root)

    with pytest.raises(ValidationError) as excinfo:
        mgr.create_tdd(
            "v9.0", "[TDD]-app-feat-tests",
            "<!-- @id:[TDD]-app-feat-tests -->\n## T\n\n```yaml\ntarget_file: tests/test_x.py\n```\n",
            parent_chunk_id="[FSD]-app:feat",
            skip_context=True,
        )
    assert "TEST_SCOPE_PARENT_MISMATCH" in str(excinfo.value)
    edges = load_specgraph(root, "v9.0").edges
    assert not any(e.dst.endswith("[TDD]-app-feat-tests") for e in edges), "拒绝必须零落盘"


def test_scope_mismatch_rejected_when_parent_is_test_but_target_not_in_scope(tmp_path: Path):
    root = _project(tmp_path)
    _set_scopes(root, "block")
    mgr = _to_tdd_creating(root)

    with pytest.raises(ValidationError) as excinfo:
        mgr.create_tdd(
            "v9.0", "[TDD]-app-tests",
            "<!-- @id:[TDD]-app-tests -->\n## T\n\n```yaml\ntarget_file: skill/ait/ait/x.py\n```\n",
            parent_chunk_id="[FSD]-app:TEST",
            skip_context=True,
        )
    assert "TEST_SCOPE_PARENT_MISMATCH" in str(excinfo.value)
    edges = load_specgraph(root, "v9.0").edges
    assert not any(e.dst.endswith("[TDD]-app-tests") for e in edges)


def test_scope_compliant_combination_succeeds(tmp_path: Path):
    root = _project(tmp_path)
    _set_scopes(root, "block")
    mgr = _to_tdd_creating(root)

    mgr.create_tdd(
        "v9.0", "[TDD]-app-tests",
        "<!-- @id:[TDD]-app-tests -->\n## T\n\n```yaml\ntarget_file: tests/test_app.py\n```\n",
        parent_chunk_id="[FSD]-app:TEST",
        skip_context=True,
    )
    mgr._add_edge("v9.0", "[FSD]-app:TEST", "[TDD]-app-tests", "details")
    assert any(e.rel == "details" for e in load_specgraph(root, "v9.0").edges)


def test_target_file_scope_escape_rejected(tmp_path: Path):
    root = _project(tmp_path)
    _set_scopes(root, "block")
    mgr = _to_tdd_creating(root)

    with pytest.raises(ValidationError) as excinfo:
        mgr.create_tdd(
            "v9.0", "[TDD]-app-tests",
            "<!-- @id:[TDD]-app-tests -->\n## T\n\n"
            "```yaml\ntarget_file: tests/../../etc/passwd\n```\n",
            parent_chunk_id="[FSD]-app:TEST",
            skip_context=True,
        )
    assert "TARGET_FILE_SCOPE_ESCAPE" in str(excinfo.value)
    edges = load_specgraph(root, "v9.0").edges
    assert not any(e.dst.endswith("[TDD]-app-tests") for e in edges)


def test_no_scopes_configured_gate_is_vacuous(tmp_path: Path):
    root = _project(tmp_path)  # no _set_scopes call: artifact_scopes unset
    mgr = _to_tdd_creating(root)

    mgr.create_tdd(
        "v9.0", "[TDD]-app-tests",
        "<!-- @id:[TDD]-app-tests -->\n## T\n\n```yaml\ntarget_file: tests/test_app.py\n```\n",
        parent_chunk_id="[FSD]-app:feat",
        skip_context=True,
    )  # would violate the bidirectional rule if scopes were configured


# ── `:TEST` acceptance-split coverage (confirm-time) ────────────────────


def _confirm_ready(root: Path) -> NewModelManager:
    """FSD confirmed, no TDD created yet — the `:TEST` split has zero details
    children, ready to exercise the coverage gate directly against gate()."""
    return _to_tdd_creating(root)


def test_uncovered_test_split_blocks_when_enforcement_block(tmp_path: Path):
    root = _project(tmp_path)
    _set_scopes(root, "block")
    _confirm_ready(root)
    _set_phase(root, "v9.0", "tdd-confirm")

    result = VersionManager(root).gate("v9.0", check_host=False)

    assert result["passed"] is False
    assert any(v["code"] == "TEST_SPLIT_UNCOVERED" for v in result["violations"])


def test_uncovered_test_split_warns_when_enforcement_warn(tmp_path: Path):
    root = _project(tmp_path)
    _set_scopes(root, "warn")
    _confirm_ready(root)
    _set_phase(root, "v9.0", "tdd-confirm")

    result = VersionManager(root).gate("v9.0", check_host=False)

    codes_in_violations = [v["code"] for v in result["violations"]]
    codes_in_warnings = [w["code"] for w in result["warnings"]]
    assert "TEST_SPLIT_UNCOVERED" not in codes_in_violations
    assert "TEST_SPLIT_UNCOVERED" in codes_in_warnings


def test_uncovered_test_split_exempt_suppresses_violation(tmp_path: Path):
    root = _project(tmp_path)
    _set_scopes(root, "block", exempt=["[FSD]-app:TEST"])
    _confirm_ready(root)
    _set_phase(root, "v9.0", "tdd-confirm")

    result = VersionManager(root).gate("v9.0", check_host=False)

    all_codes = [v["code"] for v in result["violations"]] + [w["code"] for w in result["warnings"]]
    assert "TEST_SPLIT_UNCOVERED" not in all_codes


# ── host artifact coverage reconciliation (confirm-time) ────────────────


def test_uncovered_host_artifact_blocks_when_enforcement_block(tmp_path: Path):
    root = _project(tmp_path, host_git=True)
    _set_scopes(root, "block")
    mgr = _to_tdd_creating(root)
    mgr.create_tdd(
        "v9.0", "[TDD]-app-tests",
        "<!-- @id:[TDD]-app-tests -->\n## T\n\n```yaml\ntarget_file: tests/test_app.py\n```\n",
        parent_chunk_id="[FSD]-app:TEST",
        skip_context=True,
    )
    mgr._add_edge("v9.0", "[FSD]-app:TEST", "[TDD]-app-tests", "details")
    _set_phase(root, "v9.0", "tdd-confirm")

    host = root.parent
    (host / "tests").mkdir()
    (host / "tests" / "test_app.py").write_text("def test_x(): pass\n", encoding="utf-8")
    (host / "tests" / "test_untracked.py").write_text("def test_y(): pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=host, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "add tests"], cwd=host, capture_output=True)

    result = VersionManager(root).gate("v9.0", check_host=False)

    assert result["passed"] is False
    uncovered = [v for v in result["violations"] if v["code"] == "UNCOVERED_ARTIFACT"]
    assert len(uncovered) == 1
    assert "test_untracked.py" in uncovered[0]["message"]


def test_all_host_artifacts_covered_no_violation(tmp_path: Path):
    root = _project(tmp_path, host_git=True)
    _set_scopes(root, "block")
    mgr = _to_tdd_creating(root)
    mgr.create_tdd(
        "v9.0", "[TDD]-app-tests",
        "<!-- @id:[TDD]-app-tests -->\n## T\n\n```yaml\ntarget_file: tests/test_app.py\n```\n",
        parent_chunk_id="[FSD]-app:TEST",
        skip_context=True,
    )
    mgr._add_edge("v9.0", "[FSD]-app:TEST", "[TDD]-app-tests", "details")
    _set_phase(root, "v9.0", "tdd-confirm")

    host = root.parent
    (host / "tests").mkdir()
    (host / "tests" / "test_app.py").write_text("def test_x(): pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=host, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "add tests"], cwd=host, capture_output=True)

    result = VersionManager(root).gate("v9.0", check_host=False)

    codes = [v["code"] for v in result["violations"]]
    assert "UNCOVERED_ARTIFACT" not in codes


def test_non_git_host_scope_coverage_is_vacuous(tmp_path: Path):
    root = _project(tmp_path, host_git=False)  # host.parent is NOT a git repo
    _set_scopes(root, "block")
    mgr = _to_tdd_creating(root)
    mgr.create_tdd(
        "v9.0", "[TDD]-app-tests",
        "<!-- @id:[TDD]-app-tests -->\n## T\n\n```yaml\ntarget_file: tests/test_app.py\n```\n",
        parent_chunk_id="[FSD]-app:TEST",
        skip_context=True,
    )
    mgr._add_edge("v9.0", "[FSD]-app:TEST", "[TDD]-app-tests", "details")
    _set_phase(root, "v9.0", "tdd-confirm")

    result = VersionManager(root).gate("v9.0", check_host=False)

    codes = [v["code"] for v in result["violations"]]
    assert "UNCOVERED_ARTIFACT" not in codes
