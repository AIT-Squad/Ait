from __future__ import annotations

from ait.chunk_parser import parse_text
from ait.format_validator import (
    CHUNK_ID_FORMAT_VIOLATION,
    DERIVED_NAME_VIOLATION,
    validate_chunk_id,
    validate_derived_name,
    validate_task_id,
)


def test_chunk_id_uppercase_violation():
    violations = validate_chunk_id("Prd-Foo")

    assert len(violations) == 1
    assert violations[0].code == CHUNK_ID_FORMAT_VIOLATION


def test_derived_impl_name_violation():
    text = """<!-- @id:impl-foo-x -->
## Impl

<!-- @ref:prd/foo#prd-foo rel:implements -->
"""
    parsed = parse_text(text, "impl/foo")

    violations = validate_derived_name(parsed.chunks[0], set(), set(), parsed.refs)

    assert any(v.code == DERIVED_NAME_VIOLATION for v in violations)


def test_derived_task_id():
    bad = validate_task_id("T-foo-3")
    good = validate_task_id("T-foo-03")

    assert len(bad) == 1
    assert bad[0].code == DERIVED_NAME_VIOLATION
    assert good == []
