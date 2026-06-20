"""Tests for ait.chunk_parser."""

from __future__ import annotations

from pathlib import Path

from ait.chunk_parser import parse_file, parse_text

FIXTURE_ROOT = Path(__file__).parent.parent / "project-demo"


def test_parse_book_management_prd():
    """The demo PRD should yield 14 chunks (per chunks-index.yaml)."""
    path = FIXTURE_ROOT / "docs/prd/book-management.md"
    base = FIXTURE_ROOT / "docs"
    pf = parse_file(path, base)

    assert pf.file == "prd/book-management"
    assert len(pf.chunks) == 14
    chunk_ids = [b.id for b in pf.chunks]
    assert "prd-book-mgmt-overview" in chunk_ids
    assert "prd-book-lifecycle" in chunk_ids

    # First block must include its @id annotation in content.
    first = pf.chunks[0]
    assert first.id == "prd-book-mgmt-overview"
    assert first.heading == "功能概述"
    assert first.level == 2
    assert first.content.startswith("<!-- @id:prd-book-mgmt-overview -->")


def test_parse_api_contracts_impl_with_refs():
    """impl/api-contracts.md should yield 9 blocks and 5 implements refs."""
    path = FIXTURE_ROOT / "docs/impl/api-contracts.md"
    base = FIXTURE_ROOT / "docs"
    pf = parse_file(path, base)

    assert pf.file == "impl/api-contracts"
    assert len(pf.chunks) == 9

    implements = [r for r in pf.refs if r.rel == "implements"]
    assert len(implements) == 5
    # All implements should point at prd/book-management.
    assert all(r.target_file == "prd/book-management" for r in implements)


def test_code_fence_masks_fake_ids():
    text = """# Doc

Some intro.

```markdown
<!-- @id:fake-block -->
## Fake

This is inside a code fence.
```

<!-- @id:real-block -->
## Real

Body.
"""
    pf = parse_text(text, "test/doc")
    chunk_ids = [b.id for b in pf.chunks]
    assert chunk_ids == ["real-block"]


def test_nested_subblocks_are_flat():
    text = """<!-- @id:parent-x -->
## Parent X

Parent body.

<!-- @id:parent-x-child -->
### Child

Child body.
"""
    pf = parse_text(text, "test/nested")
    assert [b.id for b in pf.chunks] == ["parent-x", "parent-x-child"]
    parent = pf.chunks[0]
    child = pf.chunks[1]
    # Parent block ends before child @id; doesn't include child content.
    assert "Child body." not in parent.content
    assert child.level == 3


def test_file_with_no_id_is_pure_header():
    text = "# Just a title\n\nNo blocks here.\n"
    pf = parse_text(text, "test/header-only")
    assert pf.chunks == []
    assert "Just a title" in pf.file_header


def test_ref_in_file_header_is_ignored():
    text = """<!-- @ref:foo#bar rel:see-also -->

<!-- @id:body -->
## Body
"""
    pf = parse_text(text, "test/hdrref")
    assert pf.refs == []


def test_crlf_normalized():
    text = "<!-- @id:a -->\r\n## A\r\n\r\nBody\r\n"
    pf = parse_text(text, "test/crlf")
    assert len(pf.chunks) == 1
    assert "\r" not in pf.chunks[0].content


def test_multiple_refs_in_same_block_attributed_correctly():
    text = """<!-- @id:impl-x -->
## Impl X

<!-- @ref:prd/feat#prd-a rel:implements -->

Body.

<!-- @ref:prd/feat#prd-b rel:see-also -->
"""
    pf = parse_text(text, "test/multi-ref")
    assert len(pf.refs) == 2
    assert all(r.source_chunk_id == "impl-x" for r in pf.refs)
    rels = {r.rel for r in pf.refs}
    assert rels == {"implements", "see-also"}


def test_new_model_chunk_ids_and_refs_parse():
    text = """<!-- @id:[FSD]-book_management -->
## Book Management

<!-- @ref:fsd/[FSD]-book_management-book_catalog#[FSD]-book_management:book_catalog rel:depends_on -->

<!-- @id:[FSD]-book_management:book_catalog -->
## Book Catalog

Catalog split.

<!-- @id:[TDD]-loan_workflow-loan_service -->
## Loan Service
"""
    pf = parse_text(text, "fsd/[FSD]-book_management")

    assert [chunk.id for chunk in pf.chunks] == [
        "[FSD]-book_management",
        "[FSD]-book_management:book_catalog",
        "[TDD]-loan_workflow-loan_service",
    ]
    assert len(pf.refs) == 1
    ref = pf.refs[0]
    assert ref.source_chunk_id == "[FSD]-book_management"
    assert ref.target_file == "fsd/[FSD]-book_management-book_catalog"
    assert ref.target_chunk_id == "[FSD]-book_management:book_catalog"
    assert ref.rel == "depends_on"
