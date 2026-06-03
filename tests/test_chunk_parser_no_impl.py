from __future__ import annotations

from ait.chunk_parser import parse_text


def test_marker_recognized():
    text = """<!-- @id:prd-no-code -->
## No Code Needed

<!-- @prd-no-impl -->

This requirement is documentation-only.
"""

    parsed = parse_text(text, "prd/no-code")

    assert len(parsed.chunks) == 1
    chunk = parsed.chunks[0]
    assert chunk.no_impl is True
    assert "@prd-no-impl" not in chunk.content
    assert "This requirement is documentation-only." in chunk.content
