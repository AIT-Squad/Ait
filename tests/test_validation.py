"""Tests for ait.validation."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from ait import validation
from ait.validation import ValidationError, ValidationIssue


def test_issue_positional_and_keyword_construction():
    positional = ValidationIssue("E1", "SOME_CODE", "some message")
    keyword = ValidationIssue(severity="E1", code="SOME_CODE", message="some message")
    assert positional == keyword
    assert positional.severity == "E1"
    assert positional.code == "SOME_CODE"
    assert positional.message == "some message"


def test_issue_locator_fields_default_to_none():
    issue = ValidationIssue("E2", "WARN", "warned")
    assert issue.chunk_id is None
    assert issue.file is None


def test_issue_locator_fields_can_be_supplied():
    issue = ValidationIssue("E3", "HINT", "hinted", chunk_id="some-chunk", file="fsd/[FSD]-ait")
    assert issue.chunk_id == "some-chunk"
    assert issue.file == "fsd/[FSD]-ait"


@pytest.mark.parametrize("field", ["severity", "code", "message", "chunk_id", "file"])
def test_issue_is_frozen(field):
    issue = ValidationIssue("E1", "CODE", "message")
    with pytest.raises(FrozenInstanceError):
        setattr(issue, field, "mutated")


def test_error_exposes_issues_as_given():
    issues = [ValidationIssue("E1", "A", "first")]
    err = ValidationError(issues)
    assert err.issues == issues


def test_error_details_none_normalizes_to_empty_dict():
    err = ValidationError([ValidationIssue("E1", "A", "first")])
    assert err.details == {}

    explicit_none = ValidationError([ValidationIssue("E1", "A", "first")], details=None)
    assert explicit_none.details == {}


def test_error_details_passed_through():
    details = {"version": "v2.93", "count": 2}
    err = ValidationError([ValidationIssue("E1", "A", "first")], details=details)
    assert err.details == details


def test_error_message_joins_code_and_message_with_semicolon():
    err = ValidationError(
        [
            ValidationIssue("E1", "A", "first"),
            ValidationIssue("E2", "B", "second"),
        ]
    )
    assert str(err) == "A: first; B: second"


def test_error_message_single_issue_has_no_separator():
    err = ValidationError([ValidationIssue("E1", "ONLY", "lonely")])
    assert str(err) == "ONLY: lonely"


def test_error_with_empty_issues_is_constructible():
    err = ValidationError([])
    assert err.issues == []
    assert err.details == {}
    assert str(err) == ""


def test_error_is_raisable_and_code_reachable():
    with pytest.raises(ValidationError) as excinfo:
        raise ValidationError([ValidationIssue("E1", "STABLE_CODE", "boom")])
    assert excinfo.value.issues[0].code == "STABLE_CODE"


def test_validation_module_has_no_project_internal_imports():
    """validation.py is imported by every layer; any relative import would cycle."""
    source = Path(validation.__file__).read_text(encoding="utf-8")
    assert "from ." not in source
