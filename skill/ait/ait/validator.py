"""Multi-level validation: E1 chunk / E2 warn / E3 info.

Per project-docs/docs/prd/block-system.md#prd-block-validation.
Validators emit ValidationIssue records; callers decide whether to raise or
just surface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .chunk_parser import Chunk, ParsedFile

Severity = Literal["E1", "E2", "E3"]

ID_FORMAT = re.compile(r"^(prd|impl)-[a-z0-9]+(-[a-z0-9]+)*$")

@dataclass(frozen=True)
class ValidationIssue:
    severity: Severity
    code: str
    message: str
    chunk_id: str | None = None
    file: str | None = None


class ValidationError(Exception):
    """Raised when an E1 issue blocks the operation."""

    def __init__(self, issues: list[ValidationIssue], details: dict | None = None):
        self.issues = issues
        self.details = details or {}
        msg = "; ".join(f"{i.code}: {i.message}" for i in issues)
        super().__init__(msg)


def validate_id_format(chunk_id: str) -> ValidationIssue | None:
    """ID must match {type}-{domain}-{name} with lowercase + hyphens."""
    if not ID_FORMAT.match(chunk_id):
        return ValidationIssue(
            severity="E1",
            code="ID_FORMAT",
            message=f"@id '{chunk_id}' violates naming rule {{type}}-{{domain}}-{{name}}",
            chunk_id=chunk_id,
        )
    return None

def validate_chunk_nonempty(chunk: Chunk) -> ValidationIssue | None:
    """A chunk must have at least a heading."""
    if not chunk.heading.strip() and chunk.level == 0:
        return ValidationIssue(
            severity="E3",
            code="CHUNK_NO_HEADING",
            message=f"Chunk '{chunk.id}' has no heading after the @id annotation",
            chunk_id=chunk.id,
            file=chunk.file,
        )
    return None

def validate_unique_ids(parsed: ParsedFile) -> list[ValidationIssue]:
    """Within one file, every @id must be unique (the global check happens elsewhere)."""
    seen: dict[str, int] = {}
    issues: list[ValidationIssue] = []
    for chunk in parsed.chunks:
        seen[chunk.id] = seen.get(chunk.id, 0) + 1
    for chunk_id, count in seen.items():
        if count > 1:
            issues.append(
                ValidationIssue(
                    severity="E1",
                    code="ID_DUPLICATE_IN_FILE",
                    message=f"@id '{chunk_id}' appears {count} times in {parsed.file}",
                    chunk_id=chunk_id,
                    file=parsed.file,
                )
            )
    return issues

def validate_baseline_id_unique(
    new_chunk_id: str, baseline_ids: set[str]
) -> ValidationIssue | None:
    """When adding a new chunk at the baseline level, its ID must not already exist."""
    if new_chunk_id in baseline_ids:
        return ValidationIssue(
            severity="E1",
            code="ID_CONFLICT_BASELINE",
            message=f"@id '{new_chunk_id}' already exists in baseline",
            chunk_id=new_chunk_id,
        )
    return None

def validate_ref_target(
    target_file: str,
    target_chunk_id: str,
    baseline_ids: set[str],
    version_ids: set[str],
) -> ValidationIssue | None:
    """Verify a @ref points at something known. E2 (warn) when missing."""
    if target_chunk_id not in baseline_ids and target_chunk_id not in version_ids:
        return ValidationIssue(
            severity="E2",
            code="REF_DANGLING",
            message=f"@ref target {target_file}#{target_chunk_id} not found",
            chunk_id=target_chunk_id,
        )
    return None

def validate_parsed_file(
    parsed: ParsedFile, baseline_ids: set[str] | None = None
) -> list[ValidationIssue]:
    """Run per-file checks: ID format, uniqueness, heading present."""
    baseline_ids = baseline_ids or set()
    issues: list[ValidationIssue] = []
    for chunk in parsed.chunks:
        if issue := validate_id_format(chunk.id):
            issues.append(issue)
        if issue := validate_chunk_nonempty(chunk):
            issues.append(issue)
    issues.extend(validate_unique_ids(parsed))
    return issues


def raise_if_e1(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    """Raise ValidationError if any E1 is present. Returns non-blocking issues for surfacing."""
    blocking = [i for i in issues if i.severity == "E1"]
    if blocking:
        raise ValidationError(blocking)
    return issues
