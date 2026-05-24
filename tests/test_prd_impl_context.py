"""Tests for prd_manager and impl_manager — workflow happy paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from ait.context_assembler import ContextAssembler
from ait.impl_manager import ImplManager
from ait.prd_manager import PrdManager
from ait.validator import ValidationError


@pytest.fixture
def project(tmp_path: Path) -> Path:
    for d in [
        "docs/prd",
        "docs/impl",
        ".meta/versions",
        ".meta/changes",
        ".meta/requirements",
        "versions",
    ]:
        (tmp_path / d).mkdir(parents=True)
    return tmp_path


def test_prd_create_auto_creates_version(project: Path):
    mgr = PrdManager(project)
    result = mgr.create("图书推荐")
    assert result.req_id == "req-001"
    assert result.version == "v1.0"
    assert (project / "versions" / "v1.0").is_dir()
    assert (project / ".meta" / "requirements" / "req-001.yaml").exists()


def test_prd_save_draft_parses_blocks(project: Path):
    mgr = PrdManager(project)
    result = mgr.create("test")
    draft = """# 测试需求

<!-- @id:prd-test-overview -->
## 概述

A test PRD.

<!-- @id:prd-test-rules -->
## 规则

Some rules.
"""
    req = mgr.save_draft(result.req_id, draft)
    assert req.status == "prd_draft"
    assert len(req.prd_blocks) == 2
    assert req.prd_blocks[0].id == "prd-test-overview"
    assert req.prd_blocks[1].heading == "规则"


def test_prd_write_to_version_registers_blocks(project: Path):
    mgr = PrdManager(project)
    res = mgr.create("recommend")
    draft = "<!-- @id:prd-recommend-overview -->\n## 概述\n\nA"
    mgr.save_draft(res.req_id, draft)

    write = mgr.write_to_version(res.req_id, prd_file="prd/recommend")
    assert write.version == "v1.0"
    assert write.block_ids == ["prd-recommend-overview"]

    idx = mgr.indexes.load_version_index("v1.0")
    assert len(idx.blocks) == 1
    assert idx.blocks[0].action == "add"
    assert idx.blocks[0].state == "working"
    assert idx.blocks[0].source_req == res.req_id


def test_prd_commit_stages_and_commits_file(project: Path):
    mgr = PrdManager(project)
    res = mgr.create("recommend")
    draft = (
        "<!-- @id:prd-recommend-overview -->\n## 概述\n\nA\n\n"
        "<!-- @id:prd-recommend-rules -->\n## 规则\n\nB"
    )
    mgr.save_draft(res.req_id, draft)
    mgr.write_to_version(res.req_id, prd_file="prd/recommend")

    commit = mgr.commit("prd/recommend", "first commit", req_id=res.req_id)
    assert commit["commit_id"] == "c1"
    assert set(commit["staged"]) == {"prd-recommend-overview", "prd-recommend-rules"}


def test_impl_create_auto_attaches_ref(project: Path):
    prd = PrdManager(project)
    res = prd.create("recommend")
    prd.save_draft(
        res.req_id,
        "<!-- @id:prd-recommend-overview -->\n## 概述\n\nbody",
    )
    prd.write_to_version(res.req_id, prd_file="prd/recommend")
    prd.commit("prd/recommend", "commit prd", req_id=res.req_id)

    impl = ImplManager(project)
    result = impl.create(
        "prd-recommend-overview",
        "<!-- @id:impl-api-recommend -->\n## 推荐接口\n\nGET /api/recommend",
        req_id=res.req_id,
    )
    assert result.block_ids == ["impl-api-recommend"]
    text = (project / "versions" / "v1.0" / "impl" / "api-contracts.md").read_text(
        encoding="utf-8"
    )
    assert "@ref:prd/recommend#prd-recommend-overview rel:implements" in text


def test_impl_commit_requires_prd_committed(project: Path):
    prd = PrdManager(project)
    res = prd.create("recommend")
    prd.save_draft(
        res.req_id,
        "<!-- @id:prd-recommend-overview -->\n## 概述\n\nbody",
    )
    prd.write_to_version(res.req_id, prd_file="prd/recommend")
    # NOT committing the PRD.

    impl = ImplManager(project)
    impl.create(
        "prd-recommend-overview",
        "<!-- @id:impl-api-recommend -->\n## 推荐接口\n\nGET /api/recommend",
        req_id=res.req_id,
    )
    with pytest.raises(ValidationError) as exc:
        impl.commit("impl-api-recommend", "msg", req_id=res.req_id)
    assert exc.value.issues[0].code == "PRD_NOT_COMMITTED"


def test_impl_commit_succeeds_after_prd_committed(project: Path):
    prd = PrdManager(project)
    res = prd.create("recommend")
    prd.save_draft(
        res.req_id,
        "<!-- @id:prd-recommend-overview -->\n## 概述\n\nbody",
    )
    prd.write_to_version(res.req_id, prd_file="prd/recommend")
    prd.commit("prd/recommend", "commit prd", req_id=res.req_id)

    impl = ImplManager(project)
    impl.create(
        "prd-recommend-overview",
        "<!-- @id:impl-api-recommend -->\n## 推荐接口\n\nGET /api/recommend",
        req_id=res.req_id,
    )
    result = impl.commit("impl-api-recommend", "commit impl", req_id=res.req_id)
    assert result["commit_id"] == "c2"  # PRD took c1


def test_context_assembler_prd_to_impl(project: Path):
    prd = PrdManager(project)
    res = prd.create("recommend")
    prd.save_draft(
        res.req_id,
        "<!-- @id:prd-recommend-overview -->\n## 概述\n\nA",
    )
    prd.write_to_version(res.req_id, prd_file="prd/recommend")
    prd.commit("prd/recommend", "msg", req_id=res.req_id)

    impl = ImplManager(project)
    impl.create(
        "prd-recommend-overview",
        "<!-- @id:impl-api-recommend -->\n## 推荐接口\n\nGET /api/recommend",
        req_id=res.req_id,
    )
    impl.commit("impl-api-recommend", "msg", req_id=res.req_id)
    # Merge so the links-index includes the link.
    prd.versions.merge("v1.0")

    asm = ContextAssembler(project)
    ctx = asm.assemble("prd-recommend-overview", scenario="prd-to-impl").to_dict()
    assert ctx["l1"]["id"] == "prd-recommend-overview"
    assert "@id:prd-recommend-overview" in ctx["l1"]["content"]
    impl_ids = [s["id"] for s in ctx["l2"]]
    assert "impl-api-recommend" in impl_ids


def test_context_assembler_impl_edit(project: Path):
    prd = PrdManager(project)
    res = prd.create("recommend")
    prd.save_draft(
        res.req_id,
        "<!-- @id:prd-recommend-overview -->\n## 概述\n\nA",
    )
    prd.write_to_version(res.req_id, prd_file="prd/recommend")
    prd.commit("prd/recommend", "msg", req_id=res.req_id)

    impl = ImplManager(project)
    impl.create(
        "prd-recommend-overview",
        "<!-- @id:impl-api-recommend -->\n## 推荐接口\n\nGET /api/recommend",
        req_id=res.req_id,
    )

    asm = ContextAssembler(project)
    ctx = asm.assemble("impl-api-recommend", scenario="impl-edit").to_dict()
    assert ctx["l1"]["id"] == "impl-api-recommend"
    l2_ids = [s["id"] for s in ctx["l2"]]
    assert "prd-recommend-overview" in l2_ids
