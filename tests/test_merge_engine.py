"""Tests for ait.merge_engine — pure chunk-level merge."""

from __future__ import annotations

from ait.chunk_parser import Chunk, ParsedFile, parse_text
from ait.merge_engine import VersionChunkOp, merge_file, merge_new_file


def _chunk(id_: str, heading: str, body: str = "Body text.", level: int = 2) -> Chunk:
    content = f"<!-- @id:{id_} -->\n{'#' * level} {heading}\n\n{body}"
    return Chunk(
        id=id_,
        heading=heading,
        level=level,
        content=content,
        line_start=1,
        line_end=4,
        file="test/file",
    )


def _base(*chunks: Chunk, header: str = "# Test\n") -> ParsedFile:
    return ParsedFile(file="test/file", file_header=header, chunks=list(chunks))


def test_modify_replaces_block():
    base = _base(_chunk("prd-a", "A"), _chunk("prd-b", "B"))
    new_b = _chunk("prd-b", "B (updated)", body="New body")
    op = VersionChunkOp(
        chunk_id="prd-b", action="modify", overrides="prd-b", new_chunk=new_b
    )
    merged = merge_file(base, [op])
    assert [b.id for b in merged.chunks] == ["prd-a", "prd-b"]
    assert "B (updated)" in merged.chunks[1].content
    assert "New body" in merged.new_content


def test_modify_nonexistent_target_is_kept_as_add():
    """A `modify` whose target is absent from baseline must be appended, not
    silently dropped — regression for the root(modify)+new-split(modify) file."""
    base = _base(_chunk("[FSD]-x", "Root", body="old root"))
    new_root = _chunk("[FSD]-x", "Root", body="new root body")
    new_split = _chunk("[FSD]-x:s1", "Split 1", body="split body")
    ops = [
        VersionChunkOp(chunk_id="[FSD]-x", action="modify", overrides="[FSD]-x", new_chunk=new_root),
        VersionChunkOp(chunk_id="[FSD]-x:s1", action="modify", overrides=None, new_chunk=new_split),
    ]
    merged = merge_file(base, ops)
    assert [c.id for c in merged.chunks] == ["[FSD]-x", "[FSD]-x:s1"]
    assert "new root body" in merged.new_content
    assert "split body" in merged.new_content


def test_delete_removes_block():
    base = _base(_chunk("prd-a", "A"), _chunk("prd-b", "B"), _chunk("prd-c", "C"))
    op = VersionChunkOp(chunk_id="prd-b", action="delete", overrides="prd-b")
    merged = merge_file(base, [op])
    assert [b.id for b in merged.chunks] == ["prd-a", "prd-c"]


def test_add_at_tail():
    base = _base(_chunk("prd-a", "A"))
    new_b = _chunk("prd-b", "B")
    op = VersionChunkOp(
        chunk_id="prd-b", action="add", insert_after=None, new_chunk=new_b
    )
    merged = merge_file(base, [op])
    assert [b.id for b in merged.chunks] == ["prd-a", "prd-b"]


def test_add_after_specific():
    base = _base(_chunk("prd-a", "A"), _chunk("prd-c", "C"))
    new_b = _chunk("prd-b", "B")
    op = VersionChunkOp(
        chunk_id="prd-b", action="add", insert_after="prd-a", new_chunk=new_b
    )
    merged = merge_file(base, [op])
    assert [b.id for b in merged.chunks] == ["prd-a", "prd-b", "prd-c"]


def test_add_after_with_multiple():
    base = _base(_chunk("prd-a", "A"), _chunk("prd-z", "Z"))
    n1 = _chunk("prd-b", "B")
    n2 = _chunk("prd-c", "C")
    op1 = VersionChunkOp(
        chunk_id="prd-b", action="add", insert_after="prd-a", new_chunk=n1
    )
    op2 = VersionChunkOp(
        chunk_id="prd-c", action="add", insert_after="prd-a", new_chunk=n2
    )
    merged = merge_file(base, [op1, op2])
    assert [b.id for b in merged.chunks] == ["prd-a", "prd-b", "prd-c", "prd-z"]


def test_combined_add_modify_delete():
    base = _base(_chunk("prd-a", "A"), _chunk("prd-b", "B"), _chunk("prd-c", "C"))
    new_b = _chunk("prd-b", "B'", body="updated")
    new_d = _chunk("prd-d", "D")
    ops = [
        VersionChunkOp(
            chunk_id="prd-b", action="modify", overrides="prd-b", new_chunk=new_b
        ),
        VersionChunkOp(chunk_id="prd-c", action="delete", overrides="prd-c"),
        VersionChunkOp(
            chunk_id="prd-d", action="add", insert_after="prd-b", new_chunk=new_d
        ),
    ]
    merged = merge_file(base, ops)
    assert [b.id for b in merged.chunks] == ["prd-a", "prd-b", "prd-d"]
    assert "updated" in merged.chunks[1].content


def test_orphan_add_falls_back_to_previous_block():
    """If insert_after's target is deleted, orphan add still lands somewhere sane."""
    base = _base(_chunk("prd-a", "A"), _chunk("prd-b", "B"), _chunk("prd-c", "C"))
    new_x = _chunk("prd-x", "X")
    ops = [
        VersionChunkOp(chunk_id="prd-b", action="delete", overrides="prd-b"),
        VersionChunkOp(
            chunk_id="prd-x", action="add", insert_after="prd-b", new_chunk=new_x
        ),
    ]
    merged = merge_file(base, ops)
    # prd-x should land after the last kept block before prd-b (i.e. after prd-a).
    ids = [b.id for b in merged.chunks]
    assert "prd-x" in ids
    assert ids.index("prd-x") == ids.index("prd-a") + 1
    assert "prd-b" not in ids


def test_merge_result_reparses_to_same_blocks():
    """Self-referential: serialize → parse should round-trip the block IDs."""
    base = _base(_chunk("prd-a", "A"), _chunk("prd-c", "C"))
    new_b = _chunk("prd-b", "B", body="inserted")
    op = VersionChunkOp(
        chunk_id="prd-b", action="add", insert_after="prd-a", new_chunk=new_b
    )
    merged = merge_file(base, [op])

    reparsed = parse_text(merged.new_content, "test/file")
    assert [b.id for b in reparsed.chunks] == ["prd-a", "prd-b", "prd-c"]


def test_merge_new_file_only_accepts_add():
    new_a = _chunk("prd-a", "A")
    merged = merge_new_file("test/new", [
        VersionChunkOp(chunk_id="prd-a", action="add", new_chunk=new_a),
    ])
    assert [b.id for b in merged.chunks] == ["prd-a"]
    assert merged.file_header == ""
    assert merged.new_content.startswith("<!-- @id:prd-a -->")


def test_merge_new_file_rejects_non_add():
    import pytest

    with pytest.raises(ValueError):
        merge_new_file("x", [VersionChunkOp(chunk_id="x", action="modify", overrides="x")])
