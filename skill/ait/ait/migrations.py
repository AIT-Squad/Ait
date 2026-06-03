"""One-time data migration: `block` → `chunk` (v1.1 → v1.2).

Per project-docs/versions/v1.2/data-model.md §4 (impl-data-chunk-rename).

Public API:
    migrate_block_to_chunk(meta_dir, dry_run=False) -> MigrationReport

Behaviour:
    - Walks `meta_dir` recursively for `*.yaml`.
    - Recursively renames the following keys (in-place, depth-first):
        blocks         → chunks
        prd_blocks     → prd_chunks
        impl_blocks    → impl_chunks
        merged_blocks  → merged_chunks
        total_blocks   → total_chunks
    - Skips walking into `ChangeRecord.{base_content,new_content}` (markdown text).
    - Renames index files:
        blocks-index.yaml         → chunks-index.yaml
        blocks-index-{vX.Y}.yaml  → chunks-index-{vX.Y}.yaml
    - Idempotent: marker file `.meta/.migrated-chunk-v1` short-circuits re-runs.
    - Atomic per yaml: tempfile + os.replace.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

FIELD_MAP = {
    "blocks": "chunks",
    "prd_blocks": "prd_chunks",
    "impl_blocks": "impl_chunks",
    "merged_blocks": "merged_chunks",
    "total_blocks": "total_chunks",
}

MARKER_NAME = ".migrated-chunk-v1"

# Field paths whose string values are markdown content; do NOT walk into them.
SKIP_TEXT_FIELDS = {"base_content", "new_content"}


class MigrationError(RuntimeError):
    pass


@dataclass
class MigrationReport:
    """Outcome of `migrate_block_to_chunk`. Idempotent re-runs return all-empty + skipped_reason."""

    yaml_files_rewritten: list[Path] = field(default_factory=list)
    files_renamed: list[tuple[Path, Path]] = field(default_factory=list)
    fields_renamed_count: int = 0
    skipped_reason: str | None = None
    errors: list[str] = field(default_factory=list)


def _rename_keys(node: Any, counter: list[int]) -> Any:
    """Recursively rename FIELD_MAP keys in-place. counter[0] tracks total renames."""
    if isinstance(node, dict):
        new_dict: dict[str, Any] = {}
        for key, value in node.items():
            new_key = FIELD_MAP.get(key, key)
            if new_key != key:
                counter[0] += 1
            if key in SKIP_TEXT_FIELDS:
                # Don't recurse into raw markdown text.
                new_dict[new_key] = value
            else:
                new_dict[new_key] = _rename_keys(value, counter)
        return new_dict
    if isinstance(node, list):
        return [_rename_keys(item, counter) for item in node]
    return node


def _atomic_write(path: Path, text: str) -> None:
    """Write `text` atomically: tempfile + fsync + os.replace, same dir."""
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".migrate-", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


def _rewrite_yaml_file(path: Path, dry_run: bool) -> tuple[bool, int]:
    """Rewrite one yaml file. Returns (changed, fields_renamed)."""
    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise MigrationError(f"YAML parse error in {path}: {exc}") from exc

    if data is None:
        return (False, 0)

    counter = [0]
    new_data = _rename_keys(data, counter)
    if counter[0] == 0:
        return (False, 0)

    if not dry_run:
        new_text = yaml.safe_dump(
            new_data,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=120,
        )
        _atomic_write(path, new_text)
    return (True, counter[0])


def _rename_index_files(meta_dir: Path, dry_run: bool) -> list[tuple[Path, Path]]:
    """Rename baseline + version index files. Returns list of (old, new)."""
    renames: list[tuple[Path, Path]] = []

    baseline_old = meta_dir / "blocks-index.yaml"
    if baseline_old.exists():
        baseline_new = meta_dir / "chunks-index.yaml"
        renames.append((baseline_old, baseline_new))

    for old in meta_dir.glob("blocks-index-*.yaml"):
        new_name = old.name.replace("blocks-index-", "chunks-index-", 1)
        renames.append((old, meta_dir / new_name))

    if not dry_run:
        for old, new in renames:
            os.replace(old, new)
    return renames


def migrate_block_to_chunk(meta_dir: Path, dry_run: bool = False) -> MigrationReport:
    """One-shot migration from `block` to `chunk` data model.

    Args:
        meta_dir: project's `.meta/` directory (e.g. `project-docs/.meta`).
        dry_run: when True, scan + report but write nothing.

    Returns:
        MigrationReport (always; check `skipped_reason` for already-migrated).

    Raises:
        MigrationError: on yaml parse failure or post-migration validation failure.
    """
    meta_dir = meta_dir.resolve()
    if not meta_dir.exists():
        raise MigrationError(f"meta dir does not exist: {meta_dir}")

    marker = meta_dir / MARKER_NAME
    if marker.exists():
        return MigrationReport(skipped_reason="already migrated")

    report = MigrationReport()

    # Step 1+2: rewrite yaml files (depth-first key rename).
    yaml_paths = sorted(meta_dir.rglob("*.yaml"))
    for path in yaml_paths:
        try:
            changed, n = _rewrite_yaml_file(path, dry_run=dry_run)
            if changed:
                report.yaml_files_rewritten.append(path)
                report.fields_renamed_count += n
        except MigrationError as exc:
            report.errors.append(str(exc))

    if report.errors:
        raise MigrationError("; ".join(report.errors))

    # Step 3: rename index files.
    report.files_renamed = _rename_index_files(meta_dir, dry_run=dry_run)

    # Step 4: validate by deserializing rewritten yaml against NEW schemas (sanity-only).
    if not dry_run:
        _validate_or_raise(meta_dir)

    # Step 5: write marker.
    if not dry_run:
        marker.write_text(
            f"migrated_at: {datetime.now(timezone.utc).isoformat()}\n",
            encoding="utf-8",
        )

    return report


def _validate_or_raise(meta_dir: Path) -> None:
    """Try loading new yaml with new pydantic schemas. Raise on failure."""
    from .schemas import BaselineIndex, RequirementMeta, VersionIndex
    from .yaml_io import load_model

    baseline_path = meta_dir / "chunks-index.yaml"
    if baseline_path.exists():
        try:
            load_model(baseline_path, BaselineIndex)
        except Exception as exc:
            raise MigrationError(
                f"post-migration validation failed for {baseline_path}: {exc}"
            ) from exc

    for vpath in meta_dir.glob("chunks-index-*.yaml"):
        try:
            load_model(vpath, VersionIndex)
        except Exception as exc:
            raise MigrationError(
                f"post-migration validation failed for {vpath}: {exc}"
            ) from exc

    req_dir = meta_dir / "requirements"
    if req_dir.exists():
        for rpath in req_dir.glob("req-*.yaml"):
            try:
                load_model(rpath, RequirementMeta)
            except Exception as exc:
                raise MigrationError(
                    f"post-migration validation failed for {rpath}: {exc}"
                ) from exc
