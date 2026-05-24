"""PRD manager — requirement lifecycle + draft persistence + commit.

Responsibilities (per project-docs/docs/prd/overview.md MVP scope):
    - create(title) → create req-NNN.yaml; auto-create current version if needed
    - save_draft(req_id, prd_text) → persist AI discussion outcome to req YAML
    - write_to_version(req_id, prd_file) → translate draft into a version markdown file
      and register every block in the version index (state=working)
    - show(prd_file_or_req_id, block_id=None)
    - commit(prd_file, message, req_id=None) → stage-all + commit blocks for this PRD
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .block_parser import ParsedFile, parse_file, parse_text
from .index_manager import IndexManager
from .schemas import PrdBlockSummary, RequirementMeta
from .validator import ValidationError, ValidationIssue, raise_if_e1, validate_parsed_file
from .version_manager import VersionManager
from .yaml_io import load_model, save_model


@dataclass
class CreateRequirementResult:
    req_id: str
    version: str


@dataclass
class WriteToVersionResult:
    version: str
    file: str
    block_ids: list[str]


def slugify(title: str) -> str:
    """Compact, lowercase slug for filenames."""
    cleaned = re.sub(r"[^a-z0-9一-鿿]+", "-", title.lower())
    return cleaned.strip("-") or "untitled"


class PrdManager:
    def __init__(self, project_root: Path):
        self.root = project_root.resolve()
        self.indexes = IndexManager(self.root)
        self.versions = VersionManager(self.root)
        self.req_dir = self.root / ".meta" / "requirements"

    # ─────────────────────────────────────────────────────
    # requirements/req-NNN.yaml
    # ─────────────────────────────────────────────────────

    def req_path(self, req_id: str) -> Path:
        return self.req_dir / f"{req_id}.yaml"

    def _next_req_id(self) -> str:
        self.req_dir.mkdir(parents=True, exist_ok=True)
        existing = sorted(self.req_dir.glob("req-*.yaml"))
        if not existing:
            return "req-001"
        last = existing[-1].stem
        try:
            n = int(last.split("-")[1]) + 1
        except (IndexError, ValueError):
            n = len(existing) + 1
        return f"req-{n:03d}"

    def load_requirement(self, req_id: str) -> RequirementMeta:
        path = self.req_path(req_id)
        if not path.exists():
            raise FileNotFoundError(f"Requirement {req_id} not found")
        return load_model(path, RequirementMeta)

    def save_requirement(self, req: RequirementMeta) -> None:
        save_model(self.req_path(req.id), req)

    # ─────────────────────────────────────────────────────
    # Lifecycle commands
    # ─────────────────────────────────────────────────────

    def create(
        self,
        title: str,
        *,
        author: str = "system",
        version: str | None = None,
    ) -> CreateRequirementResult:
        """Create a new requirement; auto-create version if none is current."""
        if version is None:
            version = self.versions.current() or self._auto_create_version()
        else:
            if not (self.root / "versions" / version).exists():
                self.versions.create(version)

        req_id = self._next_req_id()
        now = datetime.now(timezone.utc)
        req = RequirementMeta(
            id=req_id,
            title=title,
            status="draft",
            created_at=now,
            updated_at=now,
            author=author,
            assigned_version=version,
        )
        self.save_requirement(req)
        return CreateRequirementResult(req_id=req_id, version=version)

    def _auto_create_version(self) -> str:
        """Pick the next available version slot (vMAJOR.MINOR)."""
        existing = self.versions.list_versions()
        if not existing:
            new_version = "v1.0"
        else:
            # Bump minor of the highest version, even if merged (creating a fresh slot).
            latest = max(existing, key=lambda m: m.version)
            major, minor = latest.version.lstrip("v").split(".")
            new_version = f"v{major}.{int(minor) + 1}"
        self.versions.create(new_version)
        return new_version

    def save_draft(self, req_id: str, prd_text: str) -> RequirementMeta:
        """Save AI-discussed PRD markdown into the requirement's prd_draft field."""
        req = self.load_requirement(req_id)
        req.prd_draft = prd_text
        req.updated_at = datetime.now(timezone.utc)
        if req.status == "draft":
            req.status = "prd_draft"

        # Parse the draft to derive PRD block summaries.
        parsed = parse_text(prd_text, file="prd/draft")
        req.prd_blocks = [
            PrdBlockSummary(id=b.id, heading=b.heading, level=b.level)
            for b in parsed.blocks
        ]
        self.save_requirement(req)
        return req

    def write_to_version(
        self, req_id: str, prd_file: str | None = None
    ) -> WriteToVersionResult:
        """Materialize the prd_draft into a real markdown file inside the version workspace
        and register every block in the version index (state=working).

        `prd_file` is the file path under `prd/` (no .md). Defaults to a slug of the title.
        """
        req = self.load_requirement(req_id)
        if not req.prd_draft:
            raise ValidationError([
                ValidationIssue(
                    severity="E1",
                    code="DRAFT_EMPTY",
                    message=f"Requirement {req_id} has no PRD draft",
                )
            ])
        if req.assigned_version is None:
            raise ValidationError([
                ValidationIssue(
                    severity="E1",
                    code="VERSION_MISSING",
                    message=f"Requirement {req_id} has no assigned version",
                )
            ])

        version = req.assigned_version
        file_rel = prd_file or f"prd/{slugify(req.title)}"

        parsed = parse_text(req.prd_draft, file=file_rel)
        issues = validate_parsed_file(
            parsed,
            baseline_ids={b.id for b in self.indexes.load_baseline().blocks},
        )
        raise_if_e1(issues)

        # Write the markdown file into versions/{v}/{prd/...}.md.
        self.versions.write_version_file(version, file_rel, req.prd_draft)

        # Register every parsed block in the version index.
        block_ids: list[str] = []
        baseline = self.indexes.load_baseline()
        baseline_ids = {b.id for b in baseline.blocks}
        for block in parsed.blocks:
            block_copy = block  # frozen dataclass; reuse
            if block.id in baseline_ids:
                base_entry = self.indexes.query_baseline(block.id)
                base_path = (
                    self.root / "docs" / f"{base_entry.file}.md"
                    if base_entry
                    else None
                )
                base_hash: str | None = None
                if base_path and base_path.exists():
                    base_pf = parse_file(base_path, self.root / "docs")
                    for bb in base_pf.blocks:
                        if bb.id == block.id:
                            from .hash_utils import block_hash

                            base_hash = block_hash(bb.content)
                            break
                self.versions.add_block(
                    version,
                    block=block_copy,
                    action="modify",
                    overrides=block.id,
                    base_hash=base_hash,
                    source_req=req_id,
                )
            else:
                self.versions.add_block(
                    version,
                    block=block_copy,
                    action="add",
                    source_req=req_id,
                )
            block_ids.append(block.id)

        # Advance requirement status.
        req.status = "prd_confirmed"
        req.confirmed_at = datetime.now(timezone.utc)
        req.updated_at = req.confirmed_at
        self.save_requirement(req)

        return WriteToVersionResult(version=version, file=file_rel, block_ids=block_ids)

    # ─────────────────────────────────────────────────────
    # show / commit (operate on the PRD file or specific block)
    # ─────────────────────────────────────────────────────

    def show(self, prd_file: str, block_id: str | None = None) -> dict:
        """Return PRD file or block info, looking in current version first then baseline."""
        baseline_path = self.root / "docs" / f"{prd_file}.md"
        version_paths: list[tuple[str, Path]] = []
        for meta in self.versions.list_versions():
            p = self.root / "versions" / meta.version / f"{prd_file}.md"
            if p.exists():
                version_paths.append((meta.version, p))

        # Prefer the freshest unmerged version.
        chosen_path: Path | None = None
        source = "missing"
        version_name: str | None = None
        for v, p in version_paths:
            chosen_path = p
            source = "version"
            version_name = v
            break
        if chosen_path is None and baseline_path.exists():
            chosen_path = baseline_path
            source = "baseline"
        if chosen_path is None:
            raise FileNotFoundError(f"PRD file {prd_file} not found")

        base_dir = self.root / "versions" / version_name if source == "version" else self.root / "docs"
        parsed = parse_file(chosen_path, base_dir)
        if block_id:
            for block in parsed.blocks:
                if block.id == block_id:
                    return {
                        "source": source,
                        "version": version_name,
                        "block": {
                            "id": block.id,
                            "heading": block.heading,
                            "level": block.level,
                            "content": block.content,
                            "line_start": block.line_start,
                            "line_end": block.line_end,
                        },
                    }
            raise FileNotFoundError(f"Block {block_id} not found in {prd_file}")
        return {
            "source": source,
            "version": version_name,
            "file": prd_file,
            "blocks": [
                {"id": b.id, "heading": b.heading, "level": b.level}
                for b in parsed.blocks
            ],
        }

    def commit(
        self, prd_file: str, message: str, req_id: str | None = None
    ) -> dict:
        """Stage-all blocks belonging to a PRD file then commit them.

        Looks up the version that owns this file; if multiple versions touch it,
        prefers the current (non-merged) one.
        """
        version = self.versions.current()
        if not version:
            raise ValidationError([
                ValidationIssue(severity="E1", code="NO_VERSION", message="No active version")
            ])
        idx = self.indexes.load_version_index(version)
        target_ids = [b.id for b in idx.blocks if b.file == prd_file]
        if not target_ids:
            raise ValidationError([
                ValidationIssue(
                    severity="E1",
                    code="NO_BLOCKS",
                    message=f"No blocks for PRD file {prd_file} in version {version}",
                )
            ])
        stage_result = self.versions.stage(version, target_ids)
        commit_result = self.versions.commit(version, message, req_id=req_id)
        return {
            "version": version,
            "prd_file": prd_file,
            "staged": stage_result.staged,
            "commit_id": commit_result.commit_id,
            "changes": commit_result.changes,
        }
