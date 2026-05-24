"""Impl manager — implementation block lifecycle.

Per ait-system.md /ait:impl commands:
    - create(prd_block_id, content, impl_file=None) → write impl markdown into the
      version workspace, auto-attach `@ref ... rel:implements` to the PRD block,
      and register every parsed impl block in the version index.
    - show(impl_block_id)
    - commit(impl_block_id, message, req_id=None) → stage + commit that block
      (validates that the related PRD block is already committed or in baseline).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .block_parser import parse_file, parse_text
from .index_manager import IndexManager
from .validator import ValidationError, ValidationIssue
from .version_manager import VersionManager


@dataclass
class ImplCreateResult:
    version: str
    file: str
    block_ids: list[str]


# Default impl files per block-id prefix.
_IMPL_LAYER_FILES = {
    "impl-api-": "impl/api-contracts",
    "impl-data-": "impl/data-model",
    "impl-workflow-": "impl/workflow",
}


def _default_impl_file(impl_block_id: str) -> str:
    for prefix, file in _IMPL_LAYER_FILES.items():
        if impl_block_id.startswith(prefix):
            return file
    # Fallback: impl/{second-segment}
    parts = impl_block_id.split("-")
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
        prd_block_id: str,
        impl_content: str,
        *,
        impl_file: str | None = None,
        req_id: str | None = None,
        prd_file: str | None = None,
    ) -> ImplCreateResult:
        """Add an impl block (or several) into the version workspace.

        `impl_content` should be valid markdown including at least one `<!-- @id:impl-... -->`
        annotation. If it does not already contain a `@ref` to the PRD block, one is auto-
        prepended after each top-level impl block.
        """
        version = self.versions.current()
        if not version:
            raise ValidationError([
                ValidationIssue(severity="E1", code="NO_VERSION", message="No active version")
            ])

        # Locate the PRD block to verify it exists (in baseline or current version).
        prd_resolved_file = prd_file or self._lookup_prd_file(prd_block_id, version)
        if prd_resolved_file is None:
            raise ValidationError([
                ValidationIssue(
                    severity="E1",
                    code="PRD_NOT_FOUND",
                    message=f"PRD block {prd_block_id} not found in baseline or version {version}",
                )
            ])

        # Parse content to discover impl blocks.
        target_file = impl_file or self._pick_impl_file(impl_content)
        parsed = parse_text(impl_content, file=target_file)
        if not parsed.blocks:
            raise ValidationError([
                ValidationIssue(
                    severity="E1",
                    code="IMPL_NO_BLOCKS",
                    message="impl content has no @id-annotated blocks",
                )
            ])

        # Inject @ref into any block that doesn't already reference the PRD.
        ref_line = f"<!-- @ref:{prd_resolved_file}#{prd_block_id} rel:implements -->"
        augmented = self._inject_refs(impl_content, parsed, prd_block_id, ref_line)

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

        # Register only the newly added blocks (those that were in `parsed`).
        new_ids = {b.id for b in parsed.blocks}
        registered: list[str] = []
        for block in final_parsed.blocks:
            if block.id not in new_ids:
                continue
            self.versions.add_block(
                version,
                block=block,
                action="add",
                source_req=req_id,
            )
            registered.append(block.id)

        return ImplCreateResult(
            version=version, file=target_file, block_ids=registered
        )

    def show(self, impl_block_id: str) -> dict:
        version = self.versions.current()
        if version:
            entry = self.indexes.query_version(version, impl_block_id)
            if entry and entry.file:
                path = self.versions.versions_dir / version / f"{entry.file}.md"
                if path.exists():
                    parsed = parse_file(path, self.versions.versions_dir / version)
                    for block in parsed.blocks:
                        if block.id == impl_block_id:
                            return {
                                "source": "version",
                                "version": version,
                                "block": _block_dict(block),
                            }

        baseline_entry = self.indexes.query_baseline(impl_block_id)
        if baseline_entry:
            path = self.root / "docs" / f"{baseline_entry.file}.md"
            parsed = parse_file(path, self.root / "docs")
            for block in parsed.blocks:
                if block.id == impl_block_id:
                    return {
                        "source": "baseline",
                        "version": None,
                        "block": _block_dict(block),
                    }
        raise FileNotFoundError(f"impl block {impl_block_id} not found")

    def commit(
        self, impl_block_id: str, message: str, req_id: str | None = None
    ) -> dict:
        version = self.versions.current()
        if not version:
            raise ValidationError([
                ValidationIssue(severity="E1", code="NO_VERSION", message="No active version")
            ])
        entry = self.indexes.query_version(version, impl_block_id)
        if entry is None:
            raise ValidationError([
                ValidationIssue(
                    severity="E1",
                    code="BLOCK_NOT_IN_VERSION",
                    message=f"impl block {impl_block_id} not in version {version}",
                )
            ])

        # Verify any related PRD block(s) are committed or baseline-present.
        if entry.file:
            path = self.versions.versions_dir / version / f"{entry.file}.md"
            if path.exists():
                parsed = parse_file(path, self.versions.versions_dir / version)
                refs = [r for r in parsed.refs if r.source_block_id == impl_block_id]
                for ref in refs:
                    if ref.rel != "implements":
                        continue
                    if not self._prd_block_ready(ref.target_block_id, version):
                        raise ValidationError([
                            ValidationIssue(
                                severity="E1",
                                code="PRD_NOT_COMMITTED",
                                message=f"impl {impl_block_id} depends on PRD {ref.target_block_id} which is not committed",
                            )
                        ])

        stage_result = self.versions.stage(version, [impl_block_id])
        commit_result = self.versions.commit(version, message, req_id=req_id)
        return {
            "version": version,
            "impl_block_id": impl_block_id,
            "staged": stage_result.staged,
            "commit_id": commit_result.commit_id,
            "changes": commit_result.changes,
        }

    # ─────────────────────────────────────────────────────
    # Internals
    # ─────────────────────────────────────────────────────

    def _lookup_prd_file(self, prd_block_id: str, version: str) -> str | None:
        baseline_entry = self.indexes.query_baseline(prd_block_id)
        if baseline_entry:
            return baseline_entry.file
        version_entry = self.indexes.query_version(version, prd_block_id)
        if version_entry and version_entry.file:
            return version_entry.file
        return None

    def _pick_impl_file(self, content: str) -> str:
        """Pick a default impl file path based on the first impl-* block id found."""
        import re

        m = re.search(r"<!--\s*@id:(impl-[a-z0-9-]+)\s*-->", content)
        if m:
            return _default_impl_file(m.group(1))
        return "impl/general"

    def _inject_refs(
        self, content: str, parsed, prd_block_id: str, ref_line: str
    ) -> str:
        """Ensure each impl block contains the implements @ref pointing at prd_block_id."""
        out = content
        for block in parsed.blocks:
            already = any(
                r.source_block_id == block.id
                and r.target_block_id == prd_block_id
                and r.rel == "implements"
                for r in parsed.refs
            )
            if already:
                continue
            # Insert ref_line right after the first heading line in this block.
            block_text = block.content
            replacement = block_text + "\n\n" + ref_line
            out = out.replace(block_text, replacement, 1)
        return out

    def _prd_block_ready(self, prd_block_id: str, version: str) -> bool:
        """PRD block must be in baseline OR committed in the current version."""
        if self.indexes.query_baseline(prd_block_id) is not None:
            return True
        entry = self.indexes.query_version(version, prd_block_id)
        return entry is not None and entry.state == "committed"


def _block_dict(block) -> dict:
    return {
        "id": block.id,
        "heading": block.heading,
        "level": block.level,
        "content": block.content,
        "line_start": block.line_start,
        "line_end": block.line_end,
    }
