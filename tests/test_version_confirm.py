"""Tests for PRD baseline 单文件化 (force-route to prd/global on confirm).

Covers impl-prd-global-merge-target-rewrite: in `_perform_merge_internal`,
all PRD records (file_key starting with `prd/` and not equal to `prd/global`)
must be routed into `docs/prd/global.md`. Impl records must be untouched.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ait.chunk_parser import parse_file
from ait.new_model_manager import NewModelManager
from ait.schemas import VersionChunkEntry
from ait.specgraph import sync_specgraph
from ait.version_manager import VersionManager


def _init_project_with_global_prd(root: Path) -> VersionManager:
    """Bootstrap a mini project-docs whose baseline already uses prd/global.md."""
    (root / "docs" / "prd").mkdir(parents=True)
    (root / "docs" / "impl").mkdir(parents=True)
    (root / "versions").mkdir()
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    (root / "docs" / "prd" / "global.md").write_text(
        "<!-- @id:prd-existing -->\n## Existing\n\nold body\n",
        encoding="utf-8",
    )
    vm = VersionManager(root)
    vm.indexes.rebuild_baseline()
    sync_specgraph(root)
    vm.create("v1.1")
    return vm


def _parse_version_chunk(vm: VersionManager, version: str, file: str, text: str, chunk_id: str):
    path = vm.write_version_file(version, file, text)
    parsed = parse_file(path, vm.versions_dir / version)
    return next(c for c in parsed.chunks if c.id == chunk_id)


def _commit_records(vm: VersionManager, version: str, *records: VersionChunkEntry) -> None:
    idx = vm.indexes.load_version_index(version)
    idx.chunks.extend(records)
    vm.indexes.save_version_index(idx)
    sync_specgraph(vm.root)


def _committed(chunk, action: str, *, overrides: str | None = None) -> VersionChunkEntry:
    return VersionChunkEntry(
        id=chunk.id,
        file=chunk.file,
        heading=chunk.heading,
        level=chunk.level,
        action=action,
        state="committed",
        commit_id="c1",
        overrides=overrides,
    )


def test_prd_chunks_force_routed_to_global(tmp_path: Path):
    """版本侧多文件 PRD（add + modify）confirm 后必须全部落在 docs/prd/global.md。"""
    vm = _init_project_with_global_prd(tmp_path)

    # 版本工作区放在 prd/foo.md（人写时多文件友好），confirm 阶段应被收敛。
    # 同一份版本文件里同时承载 add 和 modify 两个 chunk。
    foo_text = (
        "<!-- @id:prd-new -->\n## New\n\nnew body\n\n"
        "<!-- @id:prd-existing -->\n## Existing\n\nupdated body\n"
    )
    foo_path = vm.write_version_file("v1.1", "prd/foo", foo_text)
    parsed = parse_file(foo_path, vm.versions_dir / "v1.1")
    new_chunk = next(c for c in parsed.chunks if c.id == "prd-new")
    modified = next(c for c in parsed.chunks if c.id == "prd-existing")

    _commit_records(
        vm,
        "v1.1",
        _committed(new_chunk, "add"),
        _committed(modified, "modify", overrides="prd-existing"),
    )

    result = vm.merge("v1.1", conflict_policy="use-version")

    assert result.status == "completed"

    # (a) docs/prd/global.md 含 2 个 chunk
    global_text = (tmp_path / "docs" / "prd" / "global.md").read_text(encoding="utf-8")
    assert "@id:prd-existing" in global_text
    assert "@id:prd-new" in global_text
    assert "updated body" in global_text
    assert "new body" in global_text

    # (b) docs/prd/foo.md 不存在 —— 路由强制收敛到 global
    assert not (tmp_path / "docs" / "prd" / "foo.md").exists()

    # (c) chunks-index 中所有 PRD chunk 的 file == "prd/global"
    baseline = vm.indexes.load_baseline()
    prd_files = {c.file for c in baseline.chunks if c.id.startswith("prd-")}
    assert prd_files == {"prd/global"}, f"unexpected PRD files: {prd_files}"


def test_impl_chunks_unaffected(tmp_path: Path):
    """impl/* 路由不受 PRD 单文件化影响，bar.md 应被正常创建。"""
    vm = _init_project_with_global_prd(tmp_path)

    impl = _parse_version_chunk(
        vm,
        "v1.1",
        "impl/bar",
        "<!-- @id:impl-bar -->\n## Bar\n\n"
        "<!-- @ref:prd/global#prd-existing rel:implements -->\n\nbar impl\n",
        "impl-bar",
    )
    _commit_records(vm, "v1.1", _committed(impl, "add"))

    result = vm.merge("v1.1", conflict_policy="use-version")
    assert result.status == "completed"

    # impl/bar.md 应该被正常创建（未被 PRD 路由收敛逻辑波及）
    impl_path = tmp_path / "docs" / "impl" / "bar.md"
    assert impl_path.exists(), "impl/bar.md must be created untouched by PRD routing"
    assert "@id:impl-bar" in impl_path.read_text(encoding="utf-8")

    # 没有把 impl 错误地塞进 prd/global.md
    global_text = (tmp_path / "docs" / "prd" / "global.md").read_text(encoding="utf-8")
    assert "@id:impl-bar" not in global_text


def test_delete_prd_chunk_routes_to_global(tmp_path: Path):
    """删除 baseline 已存在的 PRD chunk：从 prd/global.md 中移除，文件仍存在。"""
    vm = _init_project_with_global_prd(tmp_path)

    _commit_records(
        vm,
        "v1.1",
        VersionChunkEntry(
            id="prd-existing",
            file=None,
            heading=None,
            level=None,
            action="delete",
            state="committed",
            commit_id="c1",
            overrides="prd-existing",
        ),
    )

    result = vm.merge("v1.1", conflict_policy="use-version")
    assert result.status == "completed"

    global_path = tmp_path / "docs" / "prd" / "global.md"
    assert global_path.exists(), "prd/global.md must remain as the single PRD file"
    global_text = global_path.read_text(encoding="utf-8")
    assert "@id:prd-existing" not in global_text


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
