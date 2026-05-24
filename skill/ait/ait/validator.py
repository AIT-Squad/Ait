"""Multi-level validation: E1 block / E2 warn / E3 info.

Per project-docs/docs/prd/block-system.md#prd-block-validation.
Validators emit ValidationIssue records; callers decide whether to raise or
just surface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .block_parser import Block, ParsedFile

Severity = Literal["E1", "E2", "E3"]

ID_FORMAT = re.compile(r"^(prd|impl)-[a-z0-9]+(-[a-z0-9]+)*$")


@dataclass(frozen=True)
class ValidationIssue:
    severity: Severity
    code: str
    message: str
    block_id: str | None = None
    file: str | None = None


class ValidationError(Exception):
    """Raised when an E1 issue blocks the operation."""

    def __init__(self, issues: list[ValidationIssue]):
        self.issues = issues
        msg = "; ".join(f"{i.code}: {i.message}" for i in issues)
        super().__init__(msg)


def validate_id_format(block_id: str) -> ValidationIssue | None:
    """ID must match {type}-{domain}-{name} with lowercase + hyphens."""
    if not ID_FORMAT.match(block_id):
        return ValidationIssue(
            severity="E1",
            code="ID_FORMAT",
            message=f"@id '{block_id}' violates naming rule {{type}}-{{domain}}-{{name}}",
            block_id=block_id,
        )
    return None


def validate_block_nonempty(block: Block) -> ValidationIssue | None:
    """A block must have at least a heading."""
    if not block.heading.strip() and block.level == 0:
        return ValidationIssue(
            severity="E3",
            code="BLOCK_NO_HEADING",
            message=f"Block '{block.id}' has no heading after the @id annotation",
            block_id=block.id,
            file=block.file,
        )
    return None


def validate_unique_ids(parsed: ParsedFile) -> list[ValidationIssue]:
    """Within one file, every @id must be unique (the global check happens elsewhere)."""
    seen: dict[str, int] = {}
    issues: list[ValidationIssue] = []
    for block in parsed.blocks:
        seen[block.id] = seen.get(block.id, 0) + 1
    for block_id, count in seen.items():
        if count > 1:
            issues.append(
                ValidationIssue(
                    severity="E1",
                    code="ID_DUPLICATE_IN_FILE",
                    message=f"@id '{block_id}' appears {count} times in {parsed.file}",
                    block_id=block_id,
                    file=parsed.file,
                )
            )
    return issues


def validate_baseline_id_unique(
    new_block_id: str, baseline_ids: set[str]
) -> ValidationIssue | None:
    """When adding a new block at the baseline level, its ID must not already exist."""
    if new_block_id in baseline_ids:
        return ValidationIssue(
            severity="E1",
            code="ID_CONFLICT_BASELINE",
            message=f"@id '{new_block_id}' already exists in baseline",
            block_id=new_block_id,
        )
    return None


def validate_ref_target(
    target_file: str,
    target_block_id: str,
    baseline_ids: set[str],
    version_ids: set[str],
) -> ValidationIssue | None:
    """Verify a @ref points at something known. E2 (warn) when missing."""
    if target_block_id not in baseline_ids and target_block_id not in version_ids:
        return ValidationIssue(
            severity="E2",
            code="REF_DANGLING",
            message=f"@ref target {target_file}#{target_block_id} not found",
            block_id=target_block_id,
        )
    return None


def validate_parsed_file(
    parsed: ParsedFile, baseline_ids: set[str] | None = None
) -> list[ValidationIssue]:
    """Run per-file checks: ID format, uniqueness, heading present."""
    baseline_ids = baseline_ids or set()
    issues: list[ValidationIssue] = []
    for block in parsed.blocks:
        if issue := validate_id_format(block.id):
            issues.append(issue)
        if issue := validate_block_nonempty(block):
            issues.append(issue)
    issues.extend(validate_unique_ids(parsed))
    return issues


def raise_if_e1(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    """Raise ValidationError if any E1 is present. Returns non-blocking issues for surfacing."""
    blocking = [i for i in issues if i.severity == "E1"]
    if blocking:
        raise ValidationError(blocking)
    return issues
