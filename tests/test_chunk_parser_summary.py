from __future__ import annotations

from ait.chunk_parser import parse_text
from ait.hash_utils import chunk_hash


def test_summary_extracted():
    with_summary = """<!-- @id:prd-summary-demo -->
## Demo

<!-- @summary: 一句话 -->

Body
"""
    without_summary = """<!-- @id:prd-summary-demo -->
## Demo

Body
"""

    parsed = parse_text(with_summary, "prd/demo")
    chunk = parsed.chunks[0]

    assert chunk.summary == "一句话"
    assert "@summary" not in chunk.content
    assert chunk_hash(chunk.content) == chunk_hash(parse_text(without_summary, "prd/demo").chunks[0].content)


def test_no_summary_remains_none():
    parsed = parse_text("<!-- @id:prd-summary-demo -->\n## Demo\n\nBody\n", "prd/demo")

    assert parsed.chunks[0].summary is None


def test_multiple_summary_take_last():
    parsed = parse_text(
        """<!-- @id:prd-summary-demo -->
## Demo

<!-- @summary: 第一版 -->

Body

<!-- @summary: 第二版 -->
""",
        "prd/demo",
    )

    chunk = parsed.chunks[0]
    assert chunk.summary == "第二版"
    assert "第一版" not in chunk.content
    assert "第二版" not in chunk.content
