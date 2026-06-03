"""Format validators for PRD/impl chunks and derived task names."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .chunk_parser import Chunk, Ref, parse_extract_blocks, parse_text

PRD_FORMAT_VIOLATION = "PRD_FORMAT_VIOLATION"
IMPL_FORMAT_VIOLATION = "IMPL_FORMAT_VIOLATION"
CHUNK_ID_FORMAT_VIOLATION = "CHUNK_ID_FORMAT_VIOLATION"
DERIVED_NAME_VIOLATION = "DERIVED_NAME_VIOLATION"

PRD_SECTIONS = ["概述", "业务规则", "验收标准", "边界与非目标"]
ENGLISH_SECTION_MAP = {
    "Goal": "概述",
    "Goals": "概述",
    "Non-Goals": "边界与非目标",
    "Non Goals": "边界与非目标",
    "Approach": "业务规则",
    "Acceptance": "验收标准",
    "Acceptance Criteria": "验收标准",
}

CHUNK_ID_RE = re.compile(r"^(prd|impl|task|global)-[a-z0-9-]+$")
TASK_ID_RE = re.compile(r"^T-[a-z0-9-]+-\d{2}$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
BACKTICK_FENCE_RE = re.compile(r"^\s*(```+)")
VERSION_RE = re.compile(r"^v\d+\.\d+$")


@dataclass(frozen=True)
class FormatViolation:
    chunk_id: str | None
    file: str | None
    line: int | None
    code: str
    message: str
    fixable: bool = False
    fix_hint: str | None = None


def validate_prd_chunk(chunk: Chunk) -> list[FormatViolation]:
    """Validate that a PRD chunk uses the required Chinese four-section shape."""
    headings = _chunk_headings(chunk)
    section_headings = [(line, text) for level, text, line in headings if level == 3]
    violations: list[FormatViolation] = []

    for line, text in section_headings:
        mapped = ENGLISH_SECTION_MAP.get(text)
        if mapped:
            violations.append(
                FormatViolation(
                    chunk_id=chunk.id,
                    file=chunk.file,
                    line=line,
                    code=PRD_FORMAT_VIOLATION,
                    message=f"PRD section '{text}' must use Chinese heading '{mapped}'",
                    fixable=True,
                    fix_hint=f"replace '### {text}' with '### {mapped}'",
                )
            )

    section_names = [text for _, text in section_headings]
    missing = [name for name in PRD_SECTIONS if name not in section_names]
    if missing:
        violations.append(
            FormatViolation(
                chunk_id=chunk.id,
                file=chunk.file,
                line=chunk.line_end,
                code=PRD_FORMAT_VIOLATION,
                message="PRD chunk missing required sections: " + ", ".join(missing),
                fixable=True,
                fix_hint="append missing sections in required order with _TODO_ placeholders",
            )
        )

    allowed = set(PRD_SECTIONS) | set(ENGLISH_SECTION_MAP)
    extras = [name for name in section_names if name not in allowed]
    if extras:
        violations.append(
            FormatViolation(
                chunk_id=chunk.id,
                file=chunk.file,
                line=next((line for line, text in section_headings if text in extras), chunk.line_start),
                code=PRD_FORMAT_VIOLATION,
                message="PRD chunk contains unsupported level-3 sections: " + ", ".join(extras),
                fixable=False,
                fix_hint="keep only ### 概述 / ### 业务规则 / ### 验收标准 / ### 边界与非目标",
            )
        )

    chinese_positions = [section_names.index(name) for name in PRD_SECTIONS if name in section_names]
    if len(chinese_positions) == len(PRD_SECTIONS) and chinese_positions != sorted(chinese_positions):
        violations.append(
            FormatViolation(
                chunk_id=chunk.id,
                file=chunk.file,
                line=section_headings[0][0] if section_headings else chunk.line_start,
                code=PRD_FORMAT_VIOLATION,
                message="PRD sections must appear in order: " + " / ".join(PRD_SECTIONS),
                fixable=False,
                fix_hint=None,
            )
        )

    return violations


def validate_impl_chunk(chunk: Chunk, *, full_text: str) -> list[FormatViolation]:
    """Validate that fenced code blocks inside an impl chunk are wrapped by @extract."""
    violations: list[FormatViolation] = []
    lines = _normalize(full_text).split("\n")
    try:
        extract_blocks = parse_extract_blocks(full_text, chunks=[chunk])
    except Exception as exc:
        return [
            FormatViolation(
                chunk_id=chunk.id,
                file=chunk.file,
                line=chunk.line_start,
                code=IMPL_FORMAT_VIOLATION,
                message=f"invalid @extract block: {exc}",
                fixable=False,
            )
        ]

    extract_ranges = [
        (block.line_start, block.line_end)
        for block in extract_blocks
        if block.source_chunk_id == chunk.id
    ]
    for start, end in _code_fence_ranges(lines, chunk.line_start, chunk.line_end):
        if not any(start >= ex_start and end <= ex_end for ex_start, ex_end in extract_ranges):
            violations.append(
                FormatViolation(
                    chunk_id=chunk.id,
                    file=chunk.file,
                    line=start,
                    code=IMPL_FORMAT_VIOLATION,
                    message="impl fenced code block must be wrapped by <!-- @extract:dynamic/{type}#{chunk} --> ... <!-- @extract-end -->",
                    fixable=False,
                    fix_hint="wrap this code block in an @extract block targeting dynamic ddl/schema/api",
                )
            )
    return violations


def validate_chunk_id(chunk_id: str) -> list[FormatViolation]:
    if CHUNK_ID_RE.match(chunk_id):
        return []
    return [
        FormatViolation(
            chunk_id=chunk_id,
            file=None,
            line=None,
            code=CHUNK_ID_FORMAT_VIOLATION,
            message=f"chunk id '{chunk_id}' must match ^(prd|impl|task|global)-[a-z0-9-]+$",
            fixable=False,
        )
    ]


def validate_derived_name(
    chunk: Chunk,
    baseline_ids: set[str],
    version_ids: set[str],
    refs: list[Ref] | None = None,
) -> list[FormatViolation]:
    """Validate impl id derivation and implements reference target existence."""
    if not chunk.id.startswith("impl-"):
        return []

    chunk_refs = refs
    if chunk_refs is None:
        parsed = parse_text(chunk.content, file=chunk.file)
        chunk_refs = parsed.refs
    implements_refs = [
        ref for ref in chunk_refs
        if ref.source_chunk_id == chunk.id and ref.rel == "implements"
    ]
    if not implements_refs:
        return [
            FormatViolation(
                chunk_id=chunk.id,
                file=chunk.file,
                line=chunk.line_start,
                code=DERIVED_NAME_VIOLATION,
                message=f"impl chunk {chunk.id} must have a rel:implements @ref to its PRD chunk",
                fixable=False,
            )
        ]

    violations: list[FormatViolation] = []
    all_ids = baseline_ids | version_ids
    for ref in implements_refs:
        if ref.target_chunk_id not in all_ids:
            violations.append(
                FormatViolation(
                    chunk_id=chunk.id,
                    file=chunk.file,
                    line=chunk.line_start,
                    code=DERIVED_NAME_VIOLATION,
                    message=f"impl {chunk.id} implements missing PRD chunk {ref.target_chunk_id}",
                    fixable=False,
                )
            )
            continue
        accepted_prefixes = _accepted_impl_prefixes(ref.target_chunk_id)
        if not any(chunk.id == prefix[:-1] or chunk.id.startswith(prefix) for prefix in accepted_prefixes):
            violations.append(
                FormatViolation(
                    chunk_id=chunk.id,
                    file=chunk.file,
                    line=chunk.line_start,
                    code=DERIVED_NAME_VIOLATION,
                    message=(
                        f"impl chunk {chunk.id} must start with one of "
                        + ", ".join(accepted_prefixes)
                    ),
                    fixable=False,
                )
            )
    return violations


def validate_task_id(task_id: str) -> list[FormatViolation]:
    if TASK_ID_RE.match(task_id):
        return []
    return [
        FormatViolation(
            chunk_id=task_id,
            file=None,
            line=None,
            code=DERIVED_NAME_VIOLATION,
            message=f"task id '{task_id}' must match ^T-[a-z0-9-]+-\\d{{2}}$",
            fixable=False,
        )
    ]


def violation_to_issue(violation: FormatViolation):
    from .validator import ValidationIssue

    return ValidationIssue(
        severity="E1",
        code=violation.code,
        message=violation.message,
        chunk_id=violation.chunk_id,
        file=violation.file,
    )


def violations_to_details(violations: list[FormatViolation]) -> list[dict]:
    return [
        {
            "chunk_id": v.chunk_id,
            "file": v.file,
            "line": v.line,
            "code": v.code,
            "message": v.message,
            "fixable": v.fixable,
            "fix_hint": v.fix_hint,
        }
        for v in violations
    ]


def scan_prd_text(text: str, file: str) -> list[FormatViolation]:
    parsed = parse_text(text, file=file)
    violations: list[FormatViolation] = []
    for chunk in parsed.chunks:
        violations.extend(validate_chunk_id(chunk.id))
        if chunk.id.startswith("prd-"):
            violations.extend(validate_prd_chunk(chunk))
    return violations


def scan_impl_text(
    text: str,
    file: str,
    *,
    baseline_ids: set[str],
    version_ids: set[str],
) -> list[FormatViolation]:
    parsed = parse_text(text, file=file)
    violations: list[FormatViolation] = []
    for chunk in parsed.chunks:
        violations.extend(validate_chunk_id(chunk.id))
        if chunk.id.startswith("impl-"):
            violations.extend(validate_impl_chunk(chunk, full_text=text))
            violations.extend(validate_derived_name(chunk, baseline_ids, version_ids, parsed.refs))
    return violations


def fix_prd_text(text: str) -> tuple[str, bool]:
    """Apply only mechanical PRD section fixes to markdown text."""
    normalized = _normalize(text)
    parsed = parse_text(normalized, file="fix")
    if not parsed.chunks:
        return text, False

    lines = normalized.split("\n")
    changed = False
    for chunk in reversed(parsed.chunks):
        present: list[str] = []
        for idx in range(chunk.line_start - 1, chunk.line_end):
            if idx < 0 or idx >= len(lines):
                continue
            match = HEADING_RE.match(lines[idx])
            if not match or len(match.group(1)) != 3:
                continue
            title = match.group(2).strip()
            mapped = ENGLISH_SECTION_MAP.get(title)
            if mapped:
                lines[idx] = f"### {mapped}"
                title = mapped
                changed = True
            if title in PRD_SECTIONS and title not in present:
                present.append(title)
        missing = [name for name in PRD_SECTIONS if name not in present]
        if missing:
            insert_at = chunk.line_end
            additions: list[str] = []
            for name in missing:
                additions.extend(["", f"### {name}", "", "_TODO_"])
            lines[insert_at:insert_at] = additions
            changed = True
    return "\n".join(lines), changed


def is_version_scope(scope: str) -> bool:
    return bool(VERSION_RE.match(scope))


def _chunk_headings(chunk: Chunk) -> list[tuple[int, str, int]]:
    headings: list[tuple[int, str, int]] = []
    for offset, line in enumerate(_normalize(chunk.content).split("\n")):
        match = HEADING_RE.match(line)
        if match:
            headings.append((len(match.group(1)), match.group(2).strip(), chunk.line_start + offset))
    return headings


def _code_fence_ranges(lines: list[str], line_start: int, line_end: int) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    open_at: int | None = None
    fence: str | None = None
    start_idx = max(line_start - 1, 0)
    end_idx = min(line_end, len(lines))
    for idx in range(start_idx, end_idx):
        match = BACKTICK_FENCE_RE.match(lines[idx])
        if not match:
            continue
        marker = match.group(1)[:3]
        if open_at is None:
            open_at = idx + 1
            fence = marker
        elif fence is not None and lines[idx].lstrip().startswith(fence):
            ranges.append((open_at, idx + 1))
            open_at = None
            fence = None
    if open_at is not None:
        ranges.append((open_at, line_end))
    return ranges


def _accepted_impl_prefixes(prd_chunk_id: str) -> list[str]:
    slug = _strip_prd_prefix(prd_chunk_id)
    parts = slug.split("-")
    prefixes = [f"impl-{slug}-"]
    for keep in range(len(parts) - 1, 1, -1):
        prefixes.append(f"impl-{'-'.join(parts[:keep])}-")
    return list(dict.fromkeys(prefixes))


def _strip_prd_prefix(chunk_id: str) -> str:
    return chunk_id[4:] if chunk_id.startswith("prd-") else chunk_id


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")
