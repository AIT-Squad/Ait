"""confirm-gate reconciliations in `VersionManager.gate()`.

v3.2: the PRD-to-prd/global force-routing tests this file was created for are
gone with the routing branch itself (legacy bare-id PRD records can no longer
occur). What remains are the two gates added since: target_file existence
(v2.96) and derives-claim consistency (v2.98).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ait.new_model_manager import NewModelManager
from ait.version_manager import VersionManager


# ── v2.96: target_file existence reconciliation in gate() ──────────────────
#
# The mirror of invariant ③: coverage asks whether an artifact has an owner,
# this asks whether the artifact an owner claims still exists. Enforcement
# defaults to "warn" so landing the gate cannot make an existing version
# un-confirmable (invariant_governance AC#10/#12).

_TF_PRD = "<!-- @id:[PRD]-app -->\n## App\n"
_TF_FSD = (
    "<!-- @id:[FSD]-app -->\n## App design\n\n"
    "<!-- @id:[FSD]-app:feat -->\n## Feat\n"
)


def _tf_set_enforcement(root: Path, enforcement: str | None) -> None:
    """Write config.yaml; None omits the key entirely (the default path)."""
    config: dict = {}
    if enforcement is not None:
        config["target_file_existence"] = {"enforcement": enforcement}
    (root / ".meta" / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")


def _tf_set_phase(root: Path, version: str, phase: str) -> None:
    vm = VersionManager(root)
    meta = vm.load_version_meta(version)
    meta.phase = phase  # type: ignore[assignment]
    vm.save_version_meta(meta)


def _tf_ready(tmp_path: Path, target_file: str) -> Path:
    """PRD→FSD→TDD all confirmed, with the TDD declaring `target_file`.

    No artifact_scopes are configured, so the scope gates stay vacuous and only
    the existence reconciliation is under test.
    """
    root = tmp_path / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    VersionManager(root).create("v9.0")

    mgr = NewModelManager(root)
    _tf_set_phase(root, "v9.0", "prd-creating")
    mgr.create_prd("v9.0", "[PRD]-app", _TF_PRD, skip_context=True)
    mgr.confirm_prd_layer("v9.0")
    mgr.create_fsd("v9.0", "[FSD]-app", _TF_FSD, skip_context=True)
    mgr._add_edge("v9.0", "[PRD]-app", "[FSD]-app", "derives")
    mgr.confirm_fsd_layer("v9.0")
    mgr.create_tdd(
        "v9.0", "[TDD]-app",
        f"<!-- @id:[TDD]-app -->\n## App TDD\n\n```yaml\ntarget_file: {target_file}\n```\n",
        parent_chunk_id="[FSD]-app:feat", skip_context=True,
    )
    mgr.confirm_tdd_layer("v9.0")
    _tf_set_phase(root, "v9.0", "tdd-confirm")
    return root


def test_missing_target_file_blocks_when_enforcement_block(tmp_path: Path):
    root = _tf_ready(tmp_path, "src/gone.py")
    _tf_set_enforcement(root, "block")

    result = VersionManager(root).gate("v9.0", check_host=False)

    assert result["passed"] is False
    assert any(
        v["code"] == "TDD_TARGET_FILE_MISSING" and "src/gone.py" in v["message"]
        for v in result["violations"]
    )


def test_missing_target_file_only_warns_when_enforcement_warn(tmp_path: Path):
    root = _tf_ready(tmp_path, "src/gone.py")
    _tf_set_enforcement(root, "warn")

    result = VersionManager(root).gate("v9.0", check_host=False)

    assert "TDD_TARGET_FILE_MISSING" not in [v["code"] for v in result["violations"]]
    assert "TDD_TARGET_FILE_MISSING" in [w["code"] for w in result["warnings"]]


def test_missing_target_file_defaults_to_warn_when_unconfigured(tmp_path: Path):
    """Landing the gate must not make an existing version un-confirmable."""
    root = _tf_ready(tmp_path, "src/gone.py")
    _tf_set_enforcement(root, None)

    result = VersionManager(root).gate("v9.0", check_host=False)

    assert "TDD_TARGET_FILE_MISSING" not in [v["code"] for v in result["violations"]]
    assert "TDD_TARGET_FILE_MISSING" in [w["code"] for w in result["warnings"]]


def test_no_violation_when_target_file_exists(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "here.py").write_text("", encoding="utf-8")
    root = _tf_ready(tmp_path, "src/here.py")
    _tf_set_enforcement(root, "block")

    result = VersionManager(root).gate("v9.0", check_host=False)

    all_codes = [v["code"] for v in result["violations"]] + [
        w["code"] for w in result["warnings"]
    ]
    assert "TDD_TARGET_FILE_MISSING" not in all_codes


def test_reconciliation_never_creates_the_missing_artifact(tmp_path: Path):
    root = _tf_ready(tmp_path, "src/gone.py")
    _tf_set_enforcement(root, "block")

    VersionManager(root).gate("v9.0", check_host=False)

    assert not (tmp_path / "src" / "gone.py").exists()
    assert not (tmp_path / "src").exists()


# ── v2.98: derives-claim consistency reconciliation in gate() ──────────────
#
# FSD prose says "承接 [PRD]-ait:X"; the edge only exists if someone declared
# it. Report-only did not converge — v2.96 closed one residue and opened one,
# v2.97 closed that and opened two. Enforcement defaults to "warn" so the gate
# can land while a backlog of residue is still being worked off.

_DR_PRD = (
    "<!-- @id:[PRD]-app -->\n## App\n\n"
    "<!-- @id:[PRD]-app:feat -->\n## Feat requirement\n\n"
    "**用户故事:** 作为用户,我希望有 feat,以便完成任务。\n\n"
    "#### 验收标准\n1. WHEN 用 THEN 可用。\n"
)


def _dr_set_enforcement(root: Path, enforcement: str | None) -> None:
    config: dict = {}
    if enforcement is not None:
        config["derives_residue"] = {"enforcement": enforcement}
    (root / ".meta" / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")


def _dr_ready(tmp_path: Path, *, claim: bool, with_edge: bool) -> Path:
    """FSD split whose prose optionally claims [PRD]-app:feat, edge optional."""
    root = tmp_path / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    VersionManager(root).create("v9.0")

    body = "承接 [PRD]-app:feat 的能力契约" if claim else "无任何需求提及"
    fsd = (
        "<!-- @id:[FSD]-app -->\n## App design\n\n"
        f"<!-- @id:[FSD]-app:feat -->\n## Feat\n\n{body}\n"
    )
    if with_edge:
        fsd += '\n```yaml\nderives:\n  - "[PRD]-app:feat"\n```\n'

    mgr = NewModelManager(root)
    _tf_set_phase(root, "v9.0", "prd-creating")
    mgr.create_prd("v9.0", "[PRD]-app", _DR_PRD, skip_context=True)
    mgr.confirm_prd_layer("v9.0")
    mgr.create_fsd("v9.0", "[FSD]-app", fsd, skip_context=True)
    mgr._add_edge("v9.0", "[PRD]-app", "[FSD]-app", "derives")
    mgr.confirm_fsd_layer("v9.0")
    mgr.create_tdd(
        "v9.0", "[TDD]-app",
        "<!-- @id:[TDD]-app -->\n## App TDD\n\n```yaml\ntarget_file: src/app.py\n```\n",
        parent_chunk_id="[FSD]-app:feat", skip_context=True,
    )
    mgr.confirm_tdd_layer("v9.0")
    _tf_set_phase(root, "v9.0", "tdd-confirm")
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "app.py").write_text("", encoding="utf-8")
    return root


def test_derives_claim_without_edge_blocks_when_enforcement_block(tmp_path: Path):
    root = _dr_ready(tmp_path, claim=True, with_edge=False)
    _dr_set_enforcement(root, "block")

    result = VersionManager(root).gate("v9.0", check_host=False)

    assert result["passed"] is False
    assert any(
        v["code"] == "DERIVES_RESIDUE" and "[PRD]-app:feat" in v["message"]
        for v in result["violations"]
    )


def test_derives_claim_without_edge_only_warns_when_enforcement_warn(tmp_path: Path):
    root = _dr_ready(tmp_path, claim=True, with_edge=False)
    _dr_set_enforcement(root, "warn")

    result = VersionManager(root).gate("v9.0", check_host=False)

    assert "DERIVES_RESIDUE" not in [v["code"] for v in result["violations"]]
    assert "DERIVES_RESIDUE" in [w["code"] for w in result["warnings"]]


def test_derives_reconciliation_defaults_to_warn_when_unconfigured(tmp_path: Path):
    root = _dr_ready(tmp_path, claim=True, with_edge=False)
    _dr_set_enforcement(root, None)

    result = VersionManager(root).gate("v9.0", check_host=False)

    assert "DERIVES_RESIDUE" not in [v["code"] for v in result["violations"]]
    assert "DERIVES_RESIDUE" in [w["code"] for w in result["warnings"]]


def test_no_derives_violation_when_the_edge_exists(tmp_path: Path):
    root = _dr_ready(tmp_path, claim=True, with_edge=True)
    _dr_set_enforcement(root, "block")

    result = VersionManager(root).gate("v9.0", check_host=False)

    all_codes = [v["code"] for v in result["violations"]] + [
        w["code"] for w in result["warnings"]
    ]
    assert "DERIVES_RESIDUE" not in all_codes


def test_no_derives_violation_when_prose_claims_nothing(tmp_path: Path):
    root = _dr_ready(tmp_path, claim=False, with_edge=False)
    _dr_set_enforcement(root, "block")

    result = VersionManager(root).gate("v9.0", check_host=False)

    all_codes = [v["code"] for v in result["violations"]] + [
        w["code"] for w in result["warnings"]
    ]
    assert "DERIVES_RESIDUE" not in all_codes


def test_gate_skips_acceptance_nodes_when_scopes_configured(tmp_path: Path):
    """v2.99: gate passes artifact_scopes' parent_suffix set into the scan."""
    root = _dr_ready(tmp_path, claim=True, with_edge=False)
    (root / ".meta" / "config.yaml").write_text(yaml.safe_dump({
        "derives_residue": {"enforcement": "block"},
        "artifact_scopes": {"tests/": {"parent_suffix": ":feat", "enforcement": "warn"}},
    }), encoding="utf-8")

    result = VersionManager(root).gate("v9.0", check_host=False)

    all_codes = [v["code"] for v in result["violations"]] + [
        w["code"] for w in result["warnings"]
    ]
    assert "DERIVES_RESIDUE" not in all_codes


def test_gate_judges_the_split_when_no_scopes_configured(tmp_path: Path):
    root = _dr_ready(tmp_path, claim=True, with_edge=False)
    _dr_set_enforcement(root, "block")

    result = VersionManager(root).gate("v9.0", check_host=False)

    assert any(v["code"] == "DERIVES_RESIDUE" for v in result["violations"])
