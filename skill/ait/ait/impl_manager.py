"""Impl manager — implementation chunk lifecycle.

Per ait-system.md /ait:impl commands:
    - create(prd_chunk_id, content, impl_file=None) → write impl markdown into the
      version workspace, auto-attach `@ref ... rel:implements` to the PRD chunk,
      and register every parsed impl chunk in the version index.
    - show(impl_chunk_id)
    - commit(impl_chunk_id, message, req_id=None) → stage + commit that chunk
      (validates that the related PRD chunk is already committed or in baseline).
    - lock(version=None) → mark impl as locked for the version (phase →
      impl_locked). Symmetric to prd_manager.commit's auto-lock, but exposed as
      an explicit step because impl is committed chunk-by-chunk and the user
      decides when all chunks are done.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .chunk_parser import Chunk, parse_file, parse_text
from .format_validator import (
    validate_chunk_id,
    validate_derived_name,
    validate_impl_chunk,
    violation_to_issue,
    violations_to_details,
)
from .index_manager import IndexManager
from .validator import ValidationError, ValidationIssue
from .version_manager import VersionManager

SUMMARY_MAX_LENGTH = 120

@dataclass
class ImplCreateResult:
    version: str
    file: str
    chunk_ids: list[str]

@dataclass
class ImplInheritResult:
    version: str
    prd_chunk_id: str
    inherited: list[str]
    skipped: list[str]
    file_writes: list[str]

# Default impl files per chunk-id prefix.
_IMPL_LAYER_FILES = {
    "impl-api-": "impl/api-contracts",
    "impl-data-": "impl/data-model",
    "impl-workflow-": "impl/workflow",
}

def _default_impl_file(impl_chunk_id: str) -> str:
    for prefix, file in _IMPL_LAYER_FILES.items():
        if impl_chunk_id.startswith(prefix):
            return file
    # Fallback: impl/{second-segment}
    parts = impl_chunk_id.split("-")
    if len(parts) >= 2 and parts[0] == "impl":
        return f"impl/{parts[1]}"
    return "impl/general"


class ImplManager:
    def __init__(self, project_root: Path):
        self.root = project_root.resolve()
        self.indexes = IndexManager(self.root)
        self.versions = VersionManager(self.root)

    def create(
        self,
        prd_chunk_id: str,
        impl_content: str,
        *,
        impl_file: str | None = None,
        req_id: str | None = None,
        prd_file: str | None = None,
    ) -> ImplCreateResult:
        """Add an impl chunk (or several) into the version workspace.

        `impl_content` should be valid markdown including at least one `<!-- @id:impl-... -->`
        annotation. If it does not already contain a `@ref` to the PRD chunk, one is auto-
        prepended after each top-level impl chunk.
        """
        version = self.versions.current()
        if not version:
            raise ValidationError([
                ValidationIssue(severity="E1", code="NO_VERSION", message="No active version")
            ])
        # Redesign: refuse to add impl when impl is already locked.
        try:
            self.versions.assert_impl_writable(version)
        except Exception as exc:
            raise ValidationError([
                ValidationIssue(severity="E1", code="LOCKED", message=str(exc))
            ])
        prd_resolved_file = prd_file or self._lookup_prd_file(prd_chunk_id, version)
        if prd_resolved_file is None:
            raise ValidationError([
                ValidationIssue(
                    severity="E1",
                    code="PRD_NOT_FOUND",
                    message=f"PRD chunk {prd_chunk_id} not found in baseline or version {version}",
                )
            ])

        # Parse content to discover impl chunks.
        target_file = impl_file or self._pick_impl_file(impl_content)
        parsed = parse_text(impl_content, file=target_file)
        if not parsed.chunks:
            raise ValidationError([
                ValidationIssue(
                    severity="E1",
                    code="IMPL_NO_CHUNKS",
                    message="impl content has no @id-annotated chunks",
                )
            ])

        # Inject @ref into any chunk that doesn't already reference the PRD.
        ref_line = f"<!-- @ref:{prd_resolved_file}#{prd_chunk_id} rel:implements -->"
        augmented = self._inject_refs(impl_content, parsed, prd_chunk_id, ref_line)

        # Append (or create) the version-side impl file.
        existing = self.versions.read_version_file(version, target_file)
        if existing.strip():
            merged_text = existing.rstrip() + "\n\n" + augmented.strip() + "\n"
        else:
            merged_text = augmented.strip() + "\n"
        self.versions.write_version_file(version, target_file, merged_text)

        # Re-parse (after write) so line numbers in the index reflect the saved file.
        final_path = self.versions.versions_dir / version / f"{target_file}.md"
        final_parsed = parse_file(final_path, self.versions.versions_dir / version)

        # Register only the newly added chunks (those that were in `parsed`).
        new_ids = {c.id for c in parsed.chunks}
        registered: list[str] = []
        for chunk in final_parsed.chunks:
            if chunk.id not in new_ids:
                continue
            self.versions.add_chunk(
                version,
                chunk=chunk,
                action="add",
                source_req=req_id,
            )
            registered.append(chunk.id)

        from .specgraph import sync_specgraph

        sync_specgraph(self.root)
        return ImplCreateResult(
            version=version, file=target_file, chunk_ids=registered
        )

    def show(self, impl_chunk_id: str) -> dict:
        version = self.versions.current()
        if version:
            entry = self.indexes.query_version(version, impl_chunk_id)
            if entry and entry.file:
                path = self.versions.versions_dir / version / f"{entry.file}.md"
                if path.exists():
                    parsed = parse_file(path, self.versions.versions_dir / version)
                    for chunk in parsed.chunks:
                        if chunk.id == impl_chunk_id:
                            return {
                                "source": "version",
                                "version": version,
                                "chunk": _chunk_dict(chunk),
                            }

        baseline_entry = self.indexes.query_baseline(impl_chunk_id)
        if baseline_entry:
            path = self.root / "docs" / f"{baseline_entry.file}.md"
            parsed = parse_file(path, self.root / "docs")
            for chunk in parsed.chunks:
                if chunk.id == impl_chunk_id:
                    return {
                        "source": "baseline",
                        "version": None,
                        "chunk": _chunk_dict(chunk),
                    }
        raise FileNotFoundError(f"impl chunk {impl_chunk_id} not found")

    def commit(
        self, impl_chunk_id: str, message: str, req_id: str | None = None
    ) -> dict:
        version = self.versions.current()
        if not version:
            raise ValidationError([
                ValidationIssue(severity="E1", code="NO_VERSION", message="No active version")
            ])
        entry = self.indexes.query_version(version, impl_chunk_id)
        if entry is None:
            raise ValidationError([
                ValidationIssue(
                    severity="E1",
                    code="CHUNK_NOT_IN_VERSION",
                    message=f"impl chunk {impl_chunk_id} not in version {version}",
                )
            ])
        self._assert_format_ready(version, impl_chunk_id, entry.file)
        self._assert_summary_ready(version, impl_chunk_id, entry.file)

        # Verify any related PRD chunk(s) are committed or baseline-present.
        if entry.file:
            path = self.versions.versions_dir / version / f"{entry.file}.md"
            if path.exists():
                parsed = parse_file(path, self.versions.versions_dir / version)
                refs = [r for r in parsed.refs if r.source_chunk_id == impl_chunk_id]
                for ref in refs:
                    if ref.rel != "implements":
                        continue
                    if not self._prd_chunk_ready(ref.target_chunk_id, version):
                        raise ValidationError([
                            ValidationIssue(
                                severity="E1",
                                code="PRD_NOT_COMMITTED",
                                message=f"impl {impl_chunk_id} depends on PRD {ref.target_chunk_id} which is not committed",
                            )
                        ])

        self._assert_impl_coverage_after(version, pending_impl_id=impl_chunk_id)

        stage_result = self.versions.stage(version, [impl_chunk_id])
        commit_result = self.versions.commit(version, message, req_id=req_id)
        # Redesign: pre-merge validation (cycle + intra-version duplicates).
        # Run after commit so specgraph reflects this chunk; surface issues to caller.
        issues = self.versions.pre_merge_check(version)
        # Surface a hint so the user knows the next step. Unlike PRD (which is
        # committed file-at-a-time and locked atomically), impl is committed
        # chunk-by-chunk; locking is therefore an explicit follow-up step.
        meta = self.versions.load_version_meta(version)
        return {
            "version": version,
            "impl_chunk_id": impl_chunk_id,
            "staged": stage_result.staged,
            "commit_id": commit_result.commit_id,
            "changes": commit_result.changes,
            "pre_merge_issues": issues,
            "impl_locked": meta.impl_locked,
            "hint": (
                None
                if meta.impl_locked
                else "run `ait impl lock` once all impl chunks are committed to advance phase to impl_locked"
            ),
        }

    def lock(self, version: str | None = None) -> dict:
        """Lock impl for the given (or current) version, advancing phase to
        ``impl_locked``. Symmetric counterpart to ``prd_manager.commit``'s
        auto-lock; exposed separately because impl chunks are committed one at
        a time and the user decides when all are in.

        Idempotent: re-locking is a no-op (matches ``VersionManager.lock_impl``).
        """
        target = version or self.versions.current()
        if not target:
            raise ValidationError([
                ValidationIssue(
                    severity="E1", code="NO_VERSION", message="No active version"
                )
            ])
        # Guard: at least one impl chunk must be committed before locking, so
        # users don't lock an empty impl by accident.
        idx = self.indexes.load_version_index(target)
        committed_impl = [
            c for c in idx.chunks
            if c.state == "committed" and c.id.startswith("impl-")
        ]
        if not committed_impl:
            raise ValidationError([
                ValidationIssue(
                    severity="E1",
                    code="NO_IMPL_COMMITTED",
                    message=(
                        f"No committed impl chunks in {target}; commit at least "
                        "one impl chunk before locking"
                    ),
                )
            ])
        self.versions.lock_impl(target)
        meta = self.versions.load_version_meta(target)
        # Refresh the version state panel so `state.md` reflects the new
        # phase/impl_locked. Best-effort: never block lock on state errors.
        # Symmetric to `prd_manager.commit` which also refreshes after locking.
        try:
            from .state import save_state

            save_state(self.root, target)
        except Exception:
            pass
        return {
            "version": target,
            "impl_locked": True,
            "phase": meta.phase,
            "committed_impl_chunks": [c.id for c in committed_impl],
        }

    def inherit(self, prd_chunk_id: str) -> ImplInheritResult:
        """Copy baseline impl chunks for a PRD into the active version workspace."""
        version = self.versions.current()
        if not version:
            raise ValidationError([
                ValidationIssue(severity="E1", code="NO_VERSION", message="No active version")
            ])
        if self._lookup_prd_file(prd_chunk_id, version) is None:
            raise ValidationError([
                ValidationIssue(
                    severity="E1",
                    code="PRD_NOT_FOUND",
                    message=f"PRD chunk {prd_chunk_id} not found in baseline or version {version}",
                )
            ])

        from .specgraph import combined_specgraph

        graph = combined_specgraph(self.root, version)
        impl_ids = graph.implements_of(prd_chunk_id, version="baseline")
        inherited: list[str] = []
        skipped: list[str] = []
        file_writes: list[str] = []
        version_dir = self.versions.versions_dir / version
        existing_version_ids = {c.id for c in self.indexes.load_version_index(version).chunks}

        for impl_id in impl_ids:
            if impl_id in existing_version_ids:
                skipped.append(impl_id)
                continue
            base_entry = self.indexes.query_baseline(impl_id)
            if base_entry is None:
                skipped.append(impl_id)
                continue
            base_path = self.root / "docs" / f"{base_entry.file}.md"
            if not base_path.exists():
                skipped.append(impl_id)
                continue
            parsed = parse_file(base_path, self.root / "docs")
            chunk = next((c for c in parsed.chunks if c.id == impl_id), None)
            if chunk is None:
                skipped.append(impl_id)
                continue

            target_file = base_entry.file
            existing = self.versions.read_version_file(version, target_file)
            new_text = (
                existing.rstrip() + "\n\n" + chunk.content.strip() + "\n"
                if existing.strip()
                else chunk.content.strip() + "\n"
            )
            self.versions.write_version_file(version, target_file, new_text)
            target_path = version_dir / f"{target_file}.md"
            final_parsed = parse_file(target_path, version_dir)
            inherited_chunk = next(c for c in final_parsed.chunks if c.id == impl_id)
            self.versions.add_chunk(version, chunk=inherited_chunk, action="add", source_req=None)
            existing_version_ids.add(impl_id)
            inherited.append(impl_id)
            rel_path = str(target_path.relative_to(self.root)).replace("\\", "/")
            if rel_path not in file_writes:
                file_writes.append(rel_path)

        from .specgraph import sync_specgraph

        if inherited:
            sync_specgraph(self.root)
        return ImplInheritResult(
            version=version,
            prd_chunk_id=prd_chunk_id,
            inherited=inherited,
            skipped=skipped,
            file_writes=file_writes,
        )

    # ──────────────────────────────────────────────────
    # Internals
    # ──────────────────────────────────────────────────

    def _lookup_prd_file(self, prd_chunk_id: str, version: str) -> str | None:
        baseline_entry = self.indexes.query_baseline(prd_chunk_id)
        if baseline_entry:
            return baseline_entry.file
        version_entry = self.indexes.query_version(version, prd_chunk_id)
        if version_entry and version_entry.file:
            return version_entry.file
        return None

    def _assert_summary_ready(self, version: str, impl_chunk_id: str, file: str | None) -> None:
        if file is None:
            raise ValidationError([
                ValidationIssue(
                    severity="E1",
                    code="SUMMARY_REQUIRED",
                    message=f"summary required for chunk: {impl_chunk_id}",
                    chunk_id=impl_chunk_id,
                )
            ])
        path = self.versions.versions_dir / version / f"{file}.md"
        parsed = parse_file(path, self.versions.versions_dir / version)
        chunk = next((c for c in parsed.chunks if c.id == impl_chunk_id), None)
        if chunk is None or chunk.summary is None:
            heading = f" ({chunk.heading})" if chunk and chunk.heading else ""
            raise ValidationError([
                ValidationIssue(
                    severity="E1",
                    code="SUMMARY_REQUIRED",
                    message=f"summary required for chunk: {impl_chunk_id}{heading}",
                    chunk_id=impl_chunk_id,
                    file=file,
                )
            ])
        if len(chunk.summary) > SUMMARY_MAX_LENGTH:
            raise ValidationError([
                ValidationIssue(
                    severity="E1",
                    code="SUMMARY_TOO_LONG",
                    message=f"summary exceeds 120 characters for chunk: {impl_chunk_id} ({len(chunk.summary)})",
                    chunk_id=impl_chunk_id,
                    file=file,
                )
            ])

    def _assert_format_ready(self, version: str, impl_chunk_id: str, file: str | None) -> None:
        if file is None:
            raise ValidationError([
                ValidationIssue(
                    severity="E1",
                    code="IMPL_FORMAT_VIOLATION",
                    message=f"format validation requires file for chunk: {impl_chunk_id}",
                    chunk_id=impl_chunk_id,
                )
            ])
        path = self.versions.versions_dir / version / f"{file}.md"
        text = path.read_text(encoding="utf-8")
        parsed = parse_file(path, self.versions.versions_dir / version)
        chunk = next((c for c in parsed.chunks if c.id == impl_chunk_id), None)
        if chunk is None:
            return
        baseline_ids = {c.id for c in self.indexes.load_baseline().chunks}
        version_ids = {c.id for c in self.indexes.load_version_index(version).chunks}
        violations = []
        violations.extend(validate_chunk_id(chunk.id))
        violations.extend(validate_impl_chunk(chunk, full_text=text))
        violations.extend(validate_derived_name(chunk, baseline_ids, version_ids, parsed.refs))
        if violations:
            raise ValidationError(
                [violation_to_issue(v) for v in violations],
                details={"violations": violations_to_details(violations)},
            )

    def _pick_impl_file(self, content: str) -> str:
        """Pick a default impl file path based on the first impl-* chunk id found."""
        import re

        m = re.search(r"<!--\s*@id:(impl-[a-z0-9-]+)\s*-->", content)
        if m:
            return _default_impl_file(m.group(1))
        return "impl/general"

    def _inject_refs(
        self, content: str, parsed, prd_chunk_id: str, ref_line: str
    ) -> str:
        """Ensure each impl chunk contains the implements @ref pointing at prd_chunk_id."""
        lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        inserts: list[tuple[int, str]] = []
        for chunk in parsed.chunks:
            already = any(
                r.source_chunk_id == chunk.id
                and r.target_chunk_id == prd_chunk_id
                and r.rel == "implements"
                for r in parsed.refs
            )
            if already:
                continue
            start = max(chunk.line_start - 1, 0)
            end = min(chunk.line_end, len(lines))
            insert_at = start + 1
            for idx in range(start + 1, end):
                if lines[idx].lstrip().startswith("#"):
                    insert_at = idx + 1
                    break
            inserts.append((insert_at, f"\n{ref_line}"))
        if not inserts:
            return content
        for insert_at, text in sorted(inserts, reverse=True):
            lines.insert(insert_at, text)
        return "\n".join(lines)

    def _prd_chunk_ready(self, prd_chunk_id: str, version: str) -> bool:
        """PRD chunk must be in baseline OR committed in the current version."""
        if self.indexes.query_baseline(prd_chunk_id) is not None:
            return True
        entry = self.indexes.query_version(version, prd_chunk_id)
        return entry is not None and entry.state == "committed"

    def _assert_impl_coverage_after(self, version: str, pending_impl_id: str) -> None:
        idx = self.indexes.load_version_index(version)
        changed_prds = [
            c for c in idx.chunks
            if c.id.startswith("prd-") and c.action in ("add", "modify")
        ]
        deleted_prd_ids = {
            c.id for c in idx.chunks
            if c.id.startswith("prd-") and c.action == "delete"
        }
        if not changed_prds and not deleted_prd_ids:
            return

        version_dir = self.versions.versions_dir / version
        impl_refs: dict[str, set[str]] = {}
        impl_to_deleted: dict[str, set[str]] = {}
        pending_targets = self._implements_targets_for_impl(version, pending_impl_id)

        for path in sorted(version_dir.rglob("*.md")) if version_dir.exists() else []:
            parsed = parse_file(path, version_dir)
            for ref in parsed.refs:
                if ref.rel != "implements":
                    continue
                impl_refs.setdefault(ref.target_chunk_id, set()).add(ref.source_chunk_id)
                if ref.target_chunk_id in deleted_prd_ids:
                    impl_to_deleted.setdefault(ref.source_chunk_id, set()).add(ref.target_chunk_id)

        for target in pending_targets:
            impl_refs.setdefault(target, set()).add(pending_impl_id)

        if impl_to_deleted:
            violations = [
                f"{impl_id}->{','.join(sorted(targets))}"
                for impl_id, targets in sorted(impl_to_deleted.items())
            ]
            raise ValidationError([
                ValidationIssue(
                    severity="E1",
                    code="IMPL_ON_DELETED_PRD",
                    message="impl refs point to deleted PRD chunks: " + "; ".join(violations),
                )
            ])

        uncovered: list[str] = []
        for prd in changed_prds:
            if impl_refs.get(prd.id):
                continue
            if self._prd_no_impl(prd.id, version):
                continue
            uncovered.append(f"{prd.id} ({prd.heading or ''})".strip())

        if uncovered:
            raise ValidationError([
                ValidationIssue(
                    severity="E1",
                    code="IMPL_COVERAGE_INCOMPLETE",
                    message="PRD chunks lack implements coverage: " + ", ".join(uncovered),
                )
            ])

    def _implements_targets_for_impl(self, version: str, impl_chunk_id: str) -> set[str]:
        entry = self.indexes.query_version(version, impl_chunk_id)
        if entry is None or not entry.file:
            return set()
        path = self.versions.versions_dir / version / f"{entry.file}.md"
        if not path.exists():
            return set()
        parsed = parse_file(path, self.versions.versions_dir / version)
        return {
            r.target_chunk_id
            for r in parsed.refs
            if r.source_chunk_id == impl_chunk_id and r.rel == "implements"
        }

    def _prd_no_impl(self, prd_chunk_id: str, version: str) -> bool:
        entry = self.indexes.query_version(version, prd_chunk_id)
        candidates: list[tuple[Path, Path]] = []
        if entry and entry.file:
            candidates.append((
                self.versions.versions_dir / version / f"{entry.file}.md",
                self.versions.versions_dir / version,
            ))
        base_entry = self.indexes.query_baseline(prd_chunk_id)
        if base_entry:
            candidates.append((self.root / "docs" / f"{base_entry.file}.md", self.root / "docs"))
        for path, base_dir in candidates:
            if not path.exists():
                continue
            parsed = parse_file(path, base_dir)
            chunk = next((c for c in parsed.chunks if c.id == prd_chunk_id), None)
            if chunk and chunk.no_impl:
                return True
        return False

def _chunk_dict(chunk) -> dict:
    return {
        "id": chunk.id,
        "heading": chunk.heading,
        "level": chunk.level,
        "content": chunk.content,
        "line_start": chunk.line_start,
        "line_end": chunk.line_end,
        "summary": chunk.summary,
    }