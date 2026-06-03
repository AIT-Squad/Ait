"""PRD manager — requirement lifecycle + draft persistence + commit.

Responsibilities (per project-docs/docs/prd/overview.md MVP scope):
    - create(title) → create req-NNN.yaml; auto-create current version if needed
    - save_draft(req_id, prd_text) → persist AI discussion outcome to req YAML
    - write_to_version(req_id, prd_file) → translate draft into a version markdown file
      and register every chunk in the version index (state=working)
    - show(prd_file_or_req_id, chunk_id=None)
    - commit(prd_file, message, req_id=None) → stage-all + commit chunks for this PRD
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .chunk_parser import ParsedFile, parse_file, parse_text
from .format_validator import (
    validate_chunk_id,
    validate_prd_chunk,
    violation_to_issue,
    violations_to_details,
)
from .index_manager import IndexManager
from .io_utils import atomic_write_text
from .schemas import PrdChunkSummary, RequirementMeta
from .validator import ValidationError, ValidationIssue, raise_if_e1, validate_parsed_file
from .version_manager import VersionManager
from .yaml_io import load_model, save_model

SUMMARY_MAX_LENGTH = 120

@dataclass
class CreateRequirementResult:
    req_id: str
    version: str

@dataclass
class WriteToVersionResult:
    version: str
    file: str
    chunk_ids: list[str]


@dataclass(frozen=True)
class CandidateDecision:
    new_id: str
    action: str
    overrides: str | None = None
    confidence: float | None = None
    reason: str | None = None


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

        # Parse the draft to derive PRD chunk summaries.
        parsed = parse_text(prd_text, file="prd/draft")
        req.prd_chunks = [
            PrdChunkSummary(id=c.id, heading=c.heading, level=c.level)
            for c in parsed.chunks
        ]
        self.save_requirement(req)
        if req.assigned_version:
            self._sync_candidates_to_version_index(req.assigned_version)
        return req

    def resolve_candidates(self, from_file: Path) -> dict:
        """Validate skill-produced PRD candidates and persist them in the version workspace."""
        version = self.versions.current()
        if not version:
            raise ValidationError([
                ValidationIssue(severity="E1", code="NO_VERSION", message="No active version")
            ])
        source_text = from_file.read_text(encoding="utf-8")
        data = yaml.safe_load(source_text) or {}
        candidates = self._parse_candidate_decisions(data)
        self._validate_candidate_decisions(candidates)
        target = self.candidates_path(version)
        atomic_write_text(target, source_text)
        self._sync_candidates_to_version_index(version)
        return {
            "version": version,
            "file": str(target.relative_to(self.root)).replace("\\", "/"),
            "count": len(candidates),
            "candidate_ids": [c.new_id for c in candidates],
        }

    def candidates_path(self, version: str) -> Path:
        return self.root / "versions" / version / ".candidates.yaml"

    def _parse_candidate_decisions(self, data: Any) -> list[CandidateDecision]:
        raw_items: list[tuple[str | None, dict]] = []
        if isinstance(data, list):
            raw_items = [(None, item) for item in data if isinstance(item, dict)]
        elif isinstance(data, dict):
            if isinstance(data.get("candidates"), list):
                raw_items.extend((None, item) for item in data["candidates"] if isinstance(item, dict))
            for key, action in (
                ("modify_candidates", "modify"),
                ("delete_candidates", "delete"),
                ("adds", "add"),
            ):
                values = data.get(key) or []
                if isinstance(values, list):
                    raw_items.extend((action, item) for item in values if isinstance(item, dict))
        else:
            raise ValidationError([
                ValidationIssue(
                    severity="E1",
                    code="CANDIDATES_SCHEMA_INVALID",
                    message="candidates YAML must be a mapping or list",
                )
            ])

        decisions: list[CandidateDecision] = []
        for default_action, item in raw_items:
            new_id = item.get("new_id") or item.get("id")
            action = item.get("action") or default_action or "add"
            if not new_id:
                raise ValidationError([
                    ValidationIssue(
                        severity="E1",
                        code="CANDIDATES_SCHEMA_INVALID",
                        message="candidate requires new_id",
                    )
                ])
            decisions.append(
                CandidateDecision(
                    new_id=str(new_id),
                    action=str(action),
                    overrides=(str(item["overrides"]) if item.get("overrides") else None),
                    confidence=(float(item["confidence"]) if item.get("confidence") is not None else None),
                    reason=(str(item["reason"]) if item.get("reason") is not None else None),
                )
            )
        return decisions

    def _validate_candidate_decisions(self, candidates: list[CandidateDecision]) -> None:
        baseline_ids = {c.id for c in self.indexes.load_baseline().chunks}
        issues: list[ValidationIssue] = []
        seen_overrides: dict[str, str] = {}
        for candidate in candidates:
            id_violations = validate_chunk_id(candidate.new_id)
            if id_violations or not candidate.new_id.startswith("prd-"):
                issues.append(
                    ValidationIssue(
                        severity="E1",
                        code="CHUNK_ID_FORMAT_VIOLATION",
                        message=f"candidate new_id '{candidate.new_id}' must match prd-{{domain}}-{{name}}",
                        chunk_id=candidate.new_id,
                    )
                )
            if candidate.new_id in baseline_ids:
                issues.append(
                    ValidationIssue(
                        severity="E1",
                        code="CHUNK_ID_COLLISION",
                        message=f"candidate new_id '{candidate.new_id}' already exists in baseline",
                        chunk_id=candidate.new_id,
                    )
                )
            if candidate.action not in {"add", "modify", "delete"}:
                issues.append(
                    ValidationIssue(
                        severity="E1",
                        code="CANDIDATES_SCHEMA_INVALID",
                        message=f"candidate action '{candidate.action}' is not supported",
                        chunk_id=candidate.new_id,
                    )
                )
                continue
            if candidate.action == "modify":
                if not candidate.overrides:
                    issues.append(
                        ValidationIssue(
                            severity="E1",
                            code="OVERRIDES_REQUIRED",
                            message=f"candidate '{candidate.new_id}' action=modify requires overrides",
                            chunk_id=candidate.new_id,
                        )
                    )
                    continue
                if candidate.overrides not in baseline_ids:
                    issues.append(
                        ValidationIssue(
                            severity="E1",
                            code="OVERRIDES_NOT_IN_BASELINE",
                            message=f"candidate '{candidate.new_id}' overrides missing baseline chunk '{candidate.overrides}'",
                            chunk_id=candidate.new_id,
                        )
                    )
                previous = seen_overrides.get(candidate.overrides)
                if previous:
                    issues.append(
                        ValidationIssue(
                            severity="E1",
                            code="DUPLICATE_OVERRIDES_TARGET",
                            message=f"baseline chunk '{candidate.overrides}' is modified by both '{previous}' and '{candidate.new_id}'",
                            chunk_id=candidate.new_id,
                        )
                    )
                else:
                    seen_overrides[candidate.overrides] = candidate.new_id
        if issues:
            raise ValidationError(issues)

    def _candidate_decisions_for_version(self, version: str) -> dict[str, CandidateDecision]:
        path = self.candidates_path(version)
        if not path.exists():
            return {}
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return {c.new_id: c for c in self._parse_candidate_decisions(data)}

    def _sync_candidates_to_version_index(self, version: str) -> None:
        decisions = self._candidate_decisions_for_version(version)
        if not decisions:
            return
        idx = self.indexes.load_version_index(version)
        changed = False
        for entry in idx.chunks:
            candidate = decisions.get(entry.id)
            if candidate is None or entry.state != "working":
                continue
            if candidate.action == "add":
                if entry.action != "add" or entry.overrides is not None:
                    entry.action = "add"
                    entry.overrides = None
                    changed = True
            elif candidate.action in {"modify", "delete"}:
                if entry.action != candidate.action or entry.overrides != candidate.overrides:
                    entry.action = candidate.action  # type: ignore[assignment]
                    entry.overrides = candidate.overrides
                    changed = True
        if changed:
            self.indexes.save_version_index(idx)

    def _baseline_chunk_hash(self, chunk_id: str) -> str | None:
        base_entry = self.indexes.query_baseline(chunk_id)
        base_path = self.root / "docs" / f"{base_entry.file}.md" if base_entry else None
        if not base_path or not base_path.exists():
            return None
        base_pf = parse_file(base_path, self.root / "docs")
        for bc in base_pf.chunks:
            if bc.id == chunk_id:
                from .hash_utils import chunk_hash

                return chunk_hash(bc.content)
        return None

    def write_to_version(
        self, req_id: str, prd_file: str | None = None
    ) -> WriteToVersionResult:
        """Materialize the prd_draft into a real markdown file inside the version workspace
        and register every chunk in the version index (state=working).

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
        # Redesign: refuse to overwrite a locked PRD (atomic-version model).
        try:
            self.versions.assert_prd_writable(req.assigned_version)
        except Exception as exc:
            raise ValidationError([
                ValidationIssue(severity="E1", code="LOCKED", message=str(exc))
            ])

        version = req.assigned_version
        file_rel = prd_file or f"prd/{slugify(req.title)}"

        parsed = parse_text(req.prd_draft, file=file_rel)
        issues = validate_parsed_file(
            parsed,
            baseline_ids={c.id for c in self.indexes.load_baseline().chunks},
        )
        raise_if_e1(issues)

        # Write the markdown file into versions/{v}/{prd/...}.md.
        self.versions.write_version_file(version, file_rel, req.prd_draft)

        # Register every parsed chunk in the version index.
        chunk_ids: list[str] = []
        baseline = self.indexes.load_baseline()
        baseline_ids = {c.id for c in baseline.chunks}
        candidate_decisions = self._candidate_decisions_for_version(version)
        for chunk in parsed.chunks:
            chunk_copy = chunk  # frozen dataclass; reuse
            candidate = candidate_decisions.get(chunk.id)
            if candidate is not None:
                action = candidate.action
                overrides = candidate.overrides if action in {"modify", "delete"} else None
                self.versions.add_chunk(
                    version,
                    chunk=chunk_copy,
                    action=action,  # type: ignore[arg-type]
                    overrides=overrides,
                    base_hash=self._baseline_chunk_hash(overrides) if overrides else None,
                    source_req=req_id,
                )
            elif chunk.id in baseline_ids:
                base_hash = self._baseline_chunk_hash(chunk.id)
                self.versions.add_chunk(
                    version,
                    chunk=chunk_copy,
                    action="modify",
                    overrides=chunk.id,
                    base_hash=base_hash,
                    source_req=req_id,
                )
            else:
                self.versions.add_chunk(
                    version,
                    chunk=chunk_copy,
                    action="add",
                    source_req=req_id,
                )
            chunk_ids.append(chunk.id)

        # Advance requirement status.
        req.status = "prd_confirmed"
        req.confirmed_at = datetime.now(timezone.utc)
        req.updated_at = req.confirmed_at
        self.save_requirement(req)

        from .specgraph import sync_specgraph

        sync_specgraph(self.root)

        # Generate the version state panel as soon as the version has its
        # initial PRD materialized, so `state.md` reflects progress from the
        # very first confirm. Best-effort: never block confirm on state errors.
        try:
            from .state import save_state

            save_state(self.root, version)
        except Exception:
            pass

        return WriteToVersionResult(version=version, file=file_rel, chunk_ids=chunk_ids)

    # ──────────────────────────────────────────────────
    # show / commit (operate on the PRD file or specific chunk)
    # ──────────────────────────────────────────────────

    def show(self, prd_file: str, chunk_id: str | None = None) -> dict:
        """Return PRD file or chunk info, looking in current version first then baseline."""
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
        if chunk_id:
            for chunk in parsed.chunks:
                if chunk.id == chunk_id:
                    return {
                        "source": source,
                        "version": version_name,
                        "chunk": {
                            "id": chunk.id,
                            "heading": chunk.heading,
                            "level": chunk.level,
                            "content": chunk.content,
                            "line_start": chunk.line_start,
                            "line_end": chunk.line_end,
                            "summary": chunk.summary,
                        },
                    }
            raise FileNotFoundError(f"Chunk {chunk_id} not found in {prd_file}")
        return {
            "source": source,
            "version": version_name,
            "file": prd_file,
            "chunks": [
                {"id": c.id, "heading": c.heading, "level": c.level, "summary": c.summary}
                for c in parsed.chunks
            ],
        }

    def commit(
        self, prd_file: str, message: str, req_id: str | None = None
    ) -> dict:
        """Stage-all chunks belonging to a PRD file then commit them.

        Looks up the version that owns this file; if multiple versions touch it,
        prefers the current (non-merged) one.
        """
        version = self.versions.current()
        if not version:
            raise ValidationError([
                ValidationIssue(severity="E1", code="NO_VERSION", message="No active version")
            ])
        idx = self.indexes.load_version_index(version)
        target_ids = [c.id for c in idx.chunks if c.file == prd_file]
        if not target_ids:
            raise ValidationError([
                ValidationIssue(
                    severity="E1",
                    code="NO_CHUNKS",
                    message=f"No chunks for PRD file {prd_file} in version {version}",
                )
            ])
        self._assert_modify_overrides_ready(idx.chunks, target_ids)
        self._assert_format_ready(version, prd_file, target_ids)
        self._assert_summary_ready(version, prd_file, target_ids)
        stage_result = self.versions.stage(version, target_ids)
        commit_result = self.versions.commit(version, message, req_id=req_id)
        # Redesign: committing the PRD locks it for this version.
        self.versions.lock_prd(version)
        # Refresh the version state panel so `state.md` reflects prd_locked
        # immediately. Best-effort: never block commit on state errors.
        # Symmetric to `impl_manager.lock` which also refreshes after locking.
        try:
            from .state import save_state

            save_state(self.root, version)
        except Exception:
            pass
        return {
            "version": version,
            "prd_file": prd_file,
            "staged": stage_result.staged,
            "commit_id": commit_result.commit_id,
            "changes": commit_result.changes,
            "prd_locked": True,
        }

    def _assert_summary_ready(self, version: str, prd_file: str, target_ids: list[str]) -> None:
        path = self.versions.versions_dir / version / f"{prd_file}.md"
        parsed = parse_file(path, self.versions.versions_dir / version)
        target_set = set(target_ids)
        missing: list[str] = []
        too_long: list[str] = []
        for chunk in parsed.chunks:
            if chunk.id not in target_set:
                continue
            if chunk.summary is None:
                missing.append(f"{chunk.id} ({chunk.heading or ''})".strip())
            elif len(chunk.summary) > SUMMARY_MAX_LENGTH:
                too_long.append(f"{chunk.id} ({len(chunk.summary)})")
        if missing:
            raise ValidationError([
                ValidationIssue(
                    severity="E1",
                    code="SUMMARY_REQUIRED",
                    message="summary required for chunks: " + ", ".join(missing),
                    file=prd_file,
                )
            ])
        if too_long:
            raise ValidationError([
                ValidationIssue(
                    severity="E1",
                    code="SUMMARY_TOO_LONG",
                    message="summary exceeds 120 characters: " + ", ".join(too_long),
                    file=prd_file,
                )
            ])

    def _assert_modify_overrides_ready(self, records, target_ids: list[str]) -> None:
        baseline_ids = {c.id for c in self.indexes.load_baseline().chunks}
        target_set = set(target_ids)
        issues: list[ValidationIssue] = []
        seen_overrides: dict[str, str] = {}
        for record in records:
            if record.id not in target_set or record.action not in {"modify", "delete"}:
                continue
            if not record.overrides:
                issues.append(
                    ValidationIssue(
                        severity="E1",
                        code="OVERRIDES_REQUIRED",
                        message=f"chunk '{record.id}' action={record.action} requires overrides",
                        chunk_id=record.id,
                        file=record.file,
                    )
                )
                continue
            if record.overrides not in baseline_ids:
                issues.append(
                    ValidationIssue(
                        severity="E1",
                        code="OVERRIDES_NOT_IN_BASELINE",
                        message=f"chunk '{record.id}' overrides missing baseline chunk '{record.overrides}'",
                        chunk_id=record.id,
                        file=record.file,
                    )
                )
            previous = seen_overrides.get(record.overrides)
            if previous:
                issues.append(
                    ValidationIssue(
                        severity="E1",
                        code="DUPLICATE_OVERRIDES_TARGET",
                        message=f"baseline chunk '{record.overrides}' is targeted by both '{previous}' and '{record.id}'",
                        chunk_id=record.id,
                        file=record.file,
                    )
                )
            else:
                seen_overrides[record.overrides] = record.id
        if issues:
            raise ValidationError(issues)

    def _assert_format_ready(self, version: str, prd_file: str, target_ids: list[str]) -> None:
        path = self.versions.versions_dir / version / f"{prd_file}.md"
        parsed = parse_file(path, self.versions.versions_dir / version)
        target_set = set(target_ids)
        violations = []
        for chunk in parsed.chunks:
            if chunk.id not in target_set:
                continue
            violations.extend(validate_chunk_id(chunk.id))
            if chunk.id.startswith("prd-"):
                violations.extend(validate_prd_chunk(chunk))
        if violations:
            raise ValidationError(
                [violation_to_issue(v) for v in violations],
                details={"violations": violations_to_details(violations)},
            )