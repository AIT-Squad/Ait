from __future__ import annotations

from ait.chunk_parser import parse_text
from ait.format_validator import PRD_FORMAT_VIOLATION, validate_prd_chunk


def _chunk(text: str):
    return parse_text(text, "prd/demo").chunks[0]


def test_chinese_four_sections_pass():
    chunk = _chunk(
        """<!-- @id:prd-demo-feature -->
## Demo

### 概述

A

### 业务规则

B

### 验收标准

C

### 边界与非目标

D
"""
    )

    assert validate_prd_chunk(chunk) == []


def test_english_sections_violation():
    chunk = _chunk(
        """<!-- @id:prd-demo-feature -->
## Demo

### Goal

A

### Approach

B

### Acceptance

C

### Non-Goals

D
"""
    )

    violations = validate_prd_chunk(chunk)

    assert any(v.code == PRD_FORMAT_VIOLATION for v in violations)
    assert all(v.fixable for v in violations if "must use Chinese" in v.message)
    assert any("### Goal" in (v.fix_hint or "") and "### 概述" in (v.fix_hint or "") for v in violations)


def test_missing_section_violation():
    chunk = _chunk(
        """<!-- @id:prd-demo-feature -->
## Demo

### 概述

A

### 业务规则

B

### 边界与非目标

D
"""
    )

    violations = validate_prd_chunk(chunk)

    assert len(violations) == 1
    assert violations[0].fixable is True
    assert "验收标准" in violations[0].message


def test_section_order_wrong():
    chunk = _chunk(
        """<!-- @id:prd-demo-feature -->
## Demo

### 概述

A

### 验收标准

C

### 业务规则

B

### 边界与非目标

D
"""
    )

    violations = validate_prd_chunk(chunk)

    assert any(v.code == PRD_FORMAT_VIOLATION and not v.fixable for v in violations)
