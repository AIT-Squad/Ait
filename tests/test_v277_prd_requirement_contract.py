"""v2.77 PRD 需求契约门禁:

PRD 需求 chunk(`[PRD]-<root>:<slug>`)必须携带用户故事与带编号条目的验收标准,
缺失则拒于落盘之前(PRD_REQUIREMENT_CONTRACT_VIOLATION);PRD 根 chunk 豁免。
历史不合规 chunk 不阻塞命令,但被 modify 重写时须补齐(修改即补齐);
validate-new-model 追加基线残留报告(报告不阻断)。
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from ait.cli import main
from ait.index_manager import IndexManager
from ait.new_model_validator import (
    PRD_REQUIREMENT_CONTRACT_VIOLATION,
    scan_baseline_prd_requirement_residue,
    scan_prd_requirement_contract,
)
from ait.specgraph import load_specgraph
from ait.version_manager import VersionManager


def _payload(result):
    return json.loads(result.output.strip().splitlines()[-1])


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project-docs"
    (root / "docs").mkdir(parents=True)
    (root / ".meta" / "versions").mkdir(parents=True)
    (root / ".meta" / "changes").mkdir(parents=True)
    return root


def _run(runner, *args):
    return _payload(runner.invoke(main, list(args), catch_exceptions=False))


def _set_phase(root: Path, version: str, phase: str) -> None:
    vm = VersionManager(root)
    meta = vm.load_version_meta(version)
    meta.phase = phase  # type: ignore[assignment]
    vm.save_version_meta(meta)


ROOT_BODY = (
    "<!-- @id:[PRD]-app -->\n## App PRD\n\n"
    "### 概述\n一句话讲清产品。\n\n"
    "### 范围\n**In scope**:A。**Out of scope**:B。\n\n"
    "### 目标与度量\n可量化指标。\n\n"
    "### 反向要求\n- 不做 C。\n"
)

COMPLIANT_REQ = (
    "<!-- @id:[PRD]-app:feat -->\n### 需求：某能力\n\n"
    "**用户故事:** 作为用户,我希望有某能力,以便达成某价值。\n\n"
    "#### 验收标准\n"
    "1. WHEN 条件 THEN 系统 SHALL 行为。\n"
    "2. IF 异常 THEN 系统 SHALL 拒绝。\n"
)

NO_STORY_REQ = (
    "<!-- @id:[PRD]-app:feat -->\n### 需求：某能力\n\n"
    "#### 验收标准\n1. WHEN 条件 THEN 系统 SHALL 行为。\n"
)

NO_ACCEPTANCE_REQ = (
    "<!-- @id:[PRD]-app:feat -->\n### 需求：某能力\n\n"
    "**用户故事:** 作为用户,我希望有某能力,以便达成某价值。\n\n"
    "系统必须以某方式实现之,不得走旁路。\n"
)

EMPTY_ACCEPTANCE_REQ = (
    "<!-- @id:[PRD]-app:feat -->\n### 需求：某能力\n\n"
    "**用户故事:** 作为用户,我希望有某能力,以便达成某价值。\n\n"
    "#### 验收标准\n待补充。\n"
)


# ── 纯函数:契约判定 ──────────────────────────────────────────────────────────
def test_compliant_requirement_passes():
    assert scan_prd_requirement_contract("[PRD]-app:feat", COMPLIANT_REQ) == []


def test_letter_suffixed_item_counts_as_numbered():
    body = COMPLIANT_REQ.replace("1. WHEN", "1a. WHEN")
    assert scan_prd_requirement_contract("[PRD]-app:feat", body) == []


def test_missing_user_story_rejected():
    out = scan_prd_requirement_contract("[PRD]-app:feat", NO_STORY_REQ)
    assert len(out) == 1
    assert out[0].code == PRD_REQUIREMENT_CONTRACT_VIOLATION
    assert "用户故事" in out[0].message
    assert out[0].chunk_id == "[PRD]-app:feat"


def test_missing_acceptance_section_rejected():
    out = scan_prd_requirement_contract("[PRD]-app:feat", NO_ACCEPTANCE_REQ)
    assert len(out) == 1
    assert "验收标准" in out[0].message


def test_empty_acceptance_section_rejected():
    """小节存在但无编号条目 —— 空壳不算满足契约。"""
    out = scan_prd_requirement_contract("[PRD]-app:feat", EMPTY_ACCEPTANCE_REQ)
    assert len(out) == 1
    assert "验收标准条目" in out[0].message


def test_both_missing_reported_in_one_violation():
    body = "<!-- @id:[PRD]-app:feat -->\n### 需求：某能力\n\n实现结论散文。\n"
    out = scan_prd_requirement_contract("[PRD]-app:feat", body)
    assert len(out) == 1
    assert "用户故事" in out[0].message and "验收标准" in out[0].message


# ── 纯函数:豁免范围 ──────────────────────────────────────────────────────────
def test_prd_root_chunk_exempt():
    assert scan_prd_requirement_contract("[PRD]-app", ROOT_BODY) == []


def test_same_body_as_requirement_chunk_is_rejected():
    """豁免依据是 id 结构(含冒号)而非正文内容。"""
    out = scan_prd_requirement_contract("[PRD]-app:overview", ROOT_BODY)
    assert len(out) == 1 and out[0].code == PRD_REQUIREMENT_CONTRACT_VIOLATION


def test_non_prd_chunks_exempt():
    for cid in ("[FSD]-app:feat", "[TDD]-app", "impl-app-x"):
        assert scan_prd_requirement_contract(cid, "任意正文") == []


# ── 写时门禁 ─────────────────────────────────────────────────────────────────
def test_prd_create_rejects_requirement_without_acceptance(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["version", "create", "v0.1"], catch_exceptions=False)

    bad = ROOT_BODY + "\n" + NO_ACCEPTANCE_REQ
    p = _run(runner, "prd", "create", "[PRD]-app", "--content", bad, "--skip-context")
    assert p["ok"] is False, p
    assert p["code"] == PRD_REQUIREMENT_CONTRACT_VIOLATION, p

    # 零落盘:markdown、索引、图、phase 均未变化
    assert not (root / "versions" / "v0.1" / "prd" / "[PRD]-app.md").exists()
    idx = IndexManager(root).load_version_index("v0.1")
    assert [c.id for c in idx.chunks] == []
    graph = load_specgraph(root, "baseline")
    assert all(not s.chunk_id.startswith("[PRD]-app") for s in graph.specs)
    assert VersionManager(root).load_version_meta("v0.1").phase in (None, "", "empty")


def test_retry_after_completing_contract_succeeds(tmp_path: Path, monkeypatch):
    """拒绝不留下阻碍重试的残留 —— 补齐后同一命令成功。"""
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["version", "create", "v0.1"], catch_exceptions=False)

    bad = ROOT_BODY + "\n" + NO_STORY_REQ
    assert _run(runner, "prd", "create", "[PRD]-app", "--content", bad, "--skip-context")["ok"] is False

    good = ROOT_BODY + "\n" + COMPLIANT_REQ
    p = _run(runner, "prd", "create", "[PRD]-app", "--content", good, "--skip-context")
    assert p["ok"] is True, p
    idx = IndexManager(root).load_version_index("v0.1")
    assert "[PRD]-app:feat" in [c.id for c in idx.chunks]


def test_root_only_and_compliant_requirement_not_false_flagged(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["version", "create", "v0.1"], catch_exceptions=False)

    p = _run(runner, "prd", "create", "[PRD]-app", "--content", ROOT_BODY, "--skip-context")
    assert p["ok"] is True, p

    p = _run(
        runner, "prd", "create", "[PRD]-app",
        "--content", ROOT_BODY + "\n" + COMPLIANT_REQ,
        "--action", "modify", "--skip-context",
    )
    assert p["ok"] is True, p


def test_fsd_and_tdd_layers_unaffected(tmp_path: Path, monkeypatch):
    """契约只作用于 kind == prd。"""
    root = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["version", "create", "v0.1"], catch_exceptions=False)
    _set_phase(root, "v0.1", "fsd-creating")

    fsd = "<!-- @id:[FSD]-app -->\n## App FSD\n\n<!-- @id:[FSD]-app:feat -->\n## feat\n无验收标准。\n"
    assert _run(runner, "fsd", "create", "[FSD]-app", "--content", fsd, "--skip-context")["ok"] is True

    _set_phase(root, "v0.1", "tdd-creating")
    tdd = "<!-- @id:[TDD]-app -->\n## App TDD\n\n```yaml\ntarget_file: app.py\n```\n无验收标准。\n"
    p = _run(
        runner, "tdd", "create", "[TDD]-app",
        "--parent", "[FSD]-app:feat", "--content", tdd, "--skip-context",
    )
    assert p["ok"] is True, p


# ── 历史残留:不阻塞 / 修改即补齐 / 报告 ──────────────────────────────────────
def _baseline_with_drift(tmp_path: Path) -> Path:
    root = _project(tmp_path)
    (root / "docs" / "prd").mkdir(parents=True)
    (root / "docs" / "prd" / "[PRD]-app.md").write_text(
        ROOT_BODY + "\n" + NO_ACCEPTANCE_REQ, encoding="utf-8"
    )
    return root


def test_untouched_legacy_drift_does_not_block(tmp_path: Path, monkeypatch):
    root = _baseline_with_drift(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["reindex"], catch_exceptions=False)
    runner.invoke(main, ["version", "create", "v0.2"], catch_exceptions=False)

    other = (
        "<!-- @id:[PRD]-other -->\n## Other PRD\n\n### 概述\n另一份 PRD。\n\n"
        + COMPLIANT_REQ.replace("[PRD]-app:feat", "[PRD]-other:feat")
    )
    p = _run(runner, "prd", "create", "[PRD]-other", "--content", other, "--skip-context")
    assert p["ok"] is True, p
    assert _run(runner, "prd", "confirm", "--version", "v0.2")["ok"] is True


def test_rewriting_legacy_drift_must_complete_contract(tmp_path: Path, monkeypatch):
    root = _baseline_with_drift(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["reindex"], catch_exceptions=False)
    runner.invoke(main, ["version", "create", "v0.2"], catch_exceptions=False)

    same = (root / "docs" / "prd" / "[PRD]-app.md").read_text(encoding="utf-8")
    p = _run(
        runner, "prd", "create", "[PRD]-app",
        "--content", same, "--action", "modify", "--skip-context",
    )
    assert p["ok"] is False and p["code"] == PRD_REQUIREMENT_CONTRACT_VIOLATION, p

    fixed = ROOT_BODY + "\n" + COMPLIANT_REQ
    p = _run(
        runner, "prd", "create", "[PRD]-app",
        "--content", fixed, "--action", "modify", "--skip-context",
    )
    assert p["ok"] is True, p


def test_baseline_residue_scan_only_covers_prd_files():
    contents = [
        ("prd/[PRD]-app", "[PRD]-app:feat", NO_ACCEPTANCE_REQ),
        ("prd/[PRD]-app", "[PRD]-app", ROOT_BODY),
        ("fsd/[FSD]-app", "[FSD]-app:feat", "无验收标准。"),
        ("tdd/[TDD]-app", "[TDD]-app", "无验收标准。"),
    ]
    out = scan_baseline_prd_requirement_residue(contents)
    assert len(out) == 1
    assert out[0].file == "prd/[PRD]-app"
    assert out[0].chunk_id == "[PRD]-app:feat"
    assert scan_baseline_prd_requirement_residue([]) == []


def test_validate_new_model_reports_residue_without_failing(tmp_path: Path, monkeypatch):
    root = _baseline_with_drift(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["reindex"], catch_exceptions=False)

    result = runner.invoke(main, ["specgraph", "validate-new-model"], catch_exceptions=False)
    assert result.exit_code == 0
    p = _payload(result)
    assert p["ok"] is True, p
    ids = [v.get("chunk_id") for v in p["data"]["prd_requirement_residue"]]
    assert "[PRD]-app:feat" in ids
    assert all(
        v["code"] != PRD_REQUIREMENT_CONTRACT_VIOLATION for v in p["data"]["violations"]
    ), "契约残留是报告项,不得混入 violations"


def test_validate_new_model_clean_baseline_has_empty_residue(tmp_path: Path, monkeypatch):
    root = _project(tmp_path)
    (root / "docs" / "prd").mkdir(parents=True)
    (root / "docs" / "prd" / "[PRD]-app.md").write_text(
        ROOT_BODY + "\n" + COMPLIANT_REQ, encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    runner.invoke(main, ["reindex"], catch_exceptions=False)

    p = _run(runner, "specgraph", "validate-new-model")
    assert p["data"]["prd_requirement_residue"] == []
