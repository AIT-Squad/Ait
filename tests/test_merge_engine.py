"""Tests for ait.merge_engine — pure block-level merge."""

from __future__ import annotations

from ait.block_parser import Block, ParsedFile, parse_text
from ait.merge_engine import VersionBlockOp, merge_file, merge_new_file


def _block(id_: str, heading: str, body: str = "Body text.", level: int = 2) -> Block:
    content = f"<!-- @id:{id_} -->\n{'#' * level} {heading}\n\n{body}"
    return Block(
        id=id_,
        heading=heading,
        level=level,
        content=content,
        line_start=1,
        line_end=4,
        file="test/file",
    )


def _base(*blocks: Block, header: str = "# Test\n") -> ParsedFile:
    return ParsedFile(file="test/file", file_header=header, blocks=list(blocks))


def test_modify_replaces_block():
    base = _base(_block("prd-a", "A"), _block("prd-b", "B"))
    new_b = _block("prd-b", "B (updated)", body="New body")
    op = VersionBlockOp(
        block_id="prd-b", action="modify", overrides="prd-b", new_block=new_b
    )
    merged = merge_file(base, [op])
    assert [b.id for b in merged.blocks] == ["prd-a", "prd-b"]
    assert "B (updated)" in merged.blocks[1].content
    assert "New body" in merged.new_content


def test_delete_removes_block():
    base = _base(_block("prd-a", "A"), _block("prd-b", "B"), _block("prd-c", "C"))
    op = VersionBlockOp(block_id="prd-b", action="delete", overrides="prd-b")
    merged = merge_file(base, [op])
    assert [b.id for b in merged.blocks] == ["prd-a", "prd-c"]


def test_add_at_tail():
    base = _base(_block("prd-a", "A"))
    new_b = _block("prd-b", "B")
    op = VersionBlockOp(
        block_id="prd-b", action="add", insert_after=None, new_block=new_b
    )
    merged = merge_file(base, [op])
    assert [b.id for b in merged.blocks] == ["prd-a", "prd-b"]


def test_add_after_specific():
    base = _base(_block("prd-a", "A"), _block("prd-c", "C"))
    new_b = _block("prd-b", "B")
    op = VersionBlockOp(
        block_id="prd-b", action="add", insert_after="prd-a", new_block=new_b
    )
    merged = merge_file(base, [op])
    assert [b.id for b in merged.blocks] == ["prd-a", "prd-b", "prd-c"]


def test_add_after_with_multiple():
    base = _base(_block("prd-a", "A"), _block("prd-z", "Z"))
    n1 = _block("prd-b", "B")
    n2 = _block("prd-c", "C")
    op1 = VersionBlockOp(
        block_id="prd-b", action="add", insert_after="prd-a", new_block=n1
    )
    op2 = VersionBlockOp(
        block_id="prd-c", action="add", insert_after="prd-a", new_block=n2
    )
    merged = merge_file(base, [op1, op2])
    assert [b.id for b in merged.blocks] == ["prd-a", "prd-b", "prd-c", "prd-z"]


def test_combined_add_modify_delete():
    base = _base(_block("prd-a", "A"), _block("prd-b", "B"), _block("prd-c", "C"))
    new_b = _block("prd-b", "B'", body="updated")
    new_d = _block("prd-d", "D")
    ops = [
        VersionBlockOp(
            block_id="prd-b", action="modify", overrides="prd-b", new_block=new_b
        ),
        VersionBlockOp(block_id="prd-c", action="delete", overrides="prd-c"),
        VersionBlockOp(
            block_id="prd-d", action="add", insert_after="prd-b", new_block=new_d
        ),
    ]
    merged = merge_file(base, ops)
    assert [b.id for b in merged.blocks] == ["prd-a", "prd-b", "prd-d"]
    assert "updated" in merged.blocks[1].content


def test_orphan_add_falls_back_to_previous_block():
    """If insert_after's target is deleted, orphan add still lands somewhere sane."""
    base = _base(_block("prd-a", "A"), _block("prd-b", "B"), _block("prd-c", "C"))
    new_x = _block("prd-x", "X")
    ops = [
        VersionBlockOp(block_id="prd-b", action="delete", overrides="prd-b"),
        VersionBlockOp(
            block_id="prd-x", action="add", insert_after="prd-b", new_block=new_x
        ),
    ]
    merged = merge_file(base, ops)
    # prd-x should land after the last kept block before prd-b (i.e. after prd-a).
    ids = [b.id for b in merged.blocks]
    assert "prd-x" in ids
    assert ids.index("prd-x") == ids.index("prd-a") + 1
    assert "prd-b" not in ids


def test_merge_result_reparses_to_same_blocks():
    """Self-referential: serialize → parse should round-trip the block IDs."""
    base = _base(_block("prd-a", "A"), _block("prd-c", "C"))
    new_b = _block("prd-b", "B", body="inserted")
    op = VersionBlockOp(
        block_id="prd-b", action="add", insert_after="prd-a", new_block=new_b
    )
    merged = merge_file(base, [op])

    reparsed = parse_text(merged.new_content, "test/file")
    assert [b.id for b in reparsed.blocks] == ["prd-a", "prd-b", "prd-c"]


def test_merge_new_file_only_accepts_add():
    new_a = _block("prd-a", "A")
    merged = merge_new_file("test/new", [
        VersionBlockOp(block_id="prd-a", action="add", new_block=new_a),
    ])
    assert [b.id for b in merged.blocks] == ["prd-a"]
    assert merged.file_header == ""
    assert merged.new_content.startswith("<!-- @id:prd-a -->")


def test_merge_new_file_rejects_non_add():
    import pytest

    with pytest.raises(ValueError):
        merge_new_file("x", [VersionBlockOp(block_id="x", action="modify", overrides="x")])
