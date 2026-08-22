"""Domain validation records and error type.

Severity is three-level: E1 blocking / E2 warning / E3 info.

This module is pure data with no project-internal imports, so any layer can
import it without creating a cycle. It defines no validation rules of its own:
graph validation belongs to new_model_validator, and rendering/JSON wrapping
belongs to the cli layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["E1", "E2", "E3"]


@dataclass(frozen=True)
class ValidationIssue:
    """A single validation record."""

    severity: Severity
    code: str
    message: str
    chunk_id: str | None = None
    file: str | None = None


class ValidationError(Exception):
    """Raised when validation issues block the operation.

    Carries the issue list so the CLI can pass through a stable error code
    via ``.issues[0].code``.
    """

    def __init__(self, issues: list[ValidationIssue], details: dict | None = None):
        self.issues = issues
        self.details = details or {}
        msg = "; ".join(f"{i.code}: {i.message}" for i in issues)
        super().__init__(msg)
