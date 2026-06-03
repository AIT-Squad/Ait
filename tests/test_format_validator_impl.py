from __future__ import annotations

from ait.chunk_parser import parse_text
from ait.format_validator import IMPL_FORMAT_VIOLATION, validate_impl_chunk


def _chunk(text: str):
    return parse_text(text, "impl/demo").chunks[0]


def test_naked_codeblock_violation():
    text = """<!-- @id:impl-prd-demo-feature-gate -->
## Gate

```python
print("hello")
```
"""
    chunk = _chunk(text)

    violations = validate_impl_chunk(chunk, full_text=text)

    assert len(violations) == 1
    assert violations[0].code == IMPL_FORMAT_VIOLATION


def test_extract_wrapped_codeblock_passes():
    text = """<!-- @id:impl-prd-demo-feature-gate -->
## Gate

<!-- @extract:dynamic/api#global-api-demo -->
```python
print("hello")
```
<!-- @extract-end -->
"""
    chunk = _chunk(text)

    assert validate_impl_chunk(chunk, full_text=text) == []
