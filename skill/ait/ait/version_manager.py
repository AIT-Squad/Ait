"""Version manager — three-stage commit lifecycle.

Per project-docs/docs/impl/version-manager.md:
    working → staged → committed → (merged via merge_engine, see Phase 3)

Public API (Phase 2 — Phase 3 adds `merge`):
    create / list_versions / current
    add_chunk / update_chunk (used by prd_manager / impl_manager)
    stage / unstage / commit / status
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, replace as _dc_replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml

from .chunk_parser import Chunk, ParsedFile, parse_file
from .hash_utils import chunk_hash
from .index_manager import IndexManager
from .io_utils import atomic_write_text
from . import config_store
from .merge_engine import (
    VersionChunkOp,
    execute_plan,
    merge_file,
    merge_new_file,
    plan_reconciliation,
    reconciliation_input_fingerprint,
)
from .schemas import (
    Action,
    ChangeRecord,
    ChangeType,
    CommitEntry,
    DiscussionUsage,
    HistoricalAnchorRepair,
    ReconciliationOperation,
    ReconciliationPlan,
    RecoveryJournal,
    RevertAnchor,
    VersionChunkEntry,
    VersionDependencies,
    VersionIndex,
    VersionMeta,
)
from .validator import ValidationError, ValidationIssue
from .yaml_io import save_model

ConflictPolicy = Literal["abort", "use-version", "use-baseline"]


@dataclass
class StageResult:
    staged: list[str]
    skipped: list[tuple[str, str]]  # (chunk_id, reason)

@dataclass
class UnstageResult:
    unstaged: list[str]
    not_found: list[str]

@dataclass
class CommitResult:
    commit_id: str
    changes: list[str]  # chg ids

@dataclass
class StatusReport:
    version: str
    working: list[str]
    staged: list[str]
    committed: list[str]
    by_action: dict[str, int]

@dataclass
class ConflictReport:
    chunk_id: str
    reason: str
    recorded_hash: str | None
    current_hash: str | None

@dataclass
class MergeResult:
    merged_chunks: list[str]
    conflicts: list[ConflictReport]
    skipped: list[VersionChunkEntry]
    status: str  # "completed" | "aborted"


class VersionManagerError(Exception):
    def __init__(self, message: str, code: str = "VERSION_ERROR") -> None:
        super().__init__(message)
        self.code = code


class VersionManager:
    def __init__(self, project_root: Path):
        self.root = project_root.resolve()
        self.indexes = IndexManager(self.root)
        self.meta_dir = self.root / ".meta"
        self.versions_dir = self.root / "versions"
        self.changes_dir = self.meta_dir / "changes"
        self.version_meta_dir = self.meta_dir / "versions"

    # ─────────────────────────────────────────────────────
    # Version lifecycle
    # ─────────────────────────────────────────────────────

    def version_meta_path(self, version: str) -> Path:
        return self.version_meta_dir / f"{version}.yaml"

    def load_version_meta(self, version: str) -> VersionMeta:
        path = self.version_meta_path(version)
        if not path.exists():
            raise VersionManagerError(f"Version {version} has no metadata file")
        from .yaml_io import load_model

        return load_model(path, VersionMeta)

    def save_version_meta(self, meta: VersionMeta) -> None:
        save_model(self.version_meta_path(meta.version), meta)

    def create(self, version: str, based_on: str | None = None) -> VersionMeta:
        """Create a fresh version: meta + empty index (explicit entry point).

        Workspace subdirectories are NOT pre-built — ``atomic_write_text``
        creates them on demand, so no legacy ``prd/``/``impl/`` skeleton.
        Erroring on an existing version is the entry-level kill for ghost
        versions (audit R3-04): a typo'd ``--version`` can no longer silently
        materialise.
        """
        # P7 rule #1: one open version at a time — the previous version must be
        # merged (or reverted) before a new one can be created.
        active = self.current()
        if active is not None:
            raise VersionManagerError(
                f"active version {active} must be merged or reverted before creating {version}",
                code="ACTIVE_VERSION_EXISTS",
            )
        version_dir = self.versions_dir / version
        if version_dir.exists() or self.version_meta_path(version).exists():
            raise VersionManagerError(f"Version {version} already exists")

        meta = VersionMeta(
            version=version,
            created_at=datetime.now(timezone.utc),
            dependencies=VersionDependencies(based_on=based_on),
        )
        self.save_version_meta(meta)

        # Initialize empty version index.
        idx = VersionIndex(version_name=version, status="developing")
        self.indexes.save_version_index(idx)
        self._refresh_state(version)
        return meta

    def ensure(self, version: str, based_on: str | None = None) -> VersionMeta:
        """Idempotently ensure a version's meta + index exist.

        Unlike :meth:`create`, this tolerates a pre-existing version directory
        (e.g. created by ``write_version_file`` on the new-model fsd/tdd path) and
        is a no-op when the meta file already exists. Closes the gap where
        new-model documents could be written into a version with no metadata file
        and therefore could never be confirmed. No legacy subdirectory skeleton
        is pre-built.
        """
        if self.version_meta_path(version).exists():
            return self.load_version_meta(version)
        meta = VersionMeta(
            version=version,
            created_at=datetime.now(timezone.utc),
            dependencies=VersionDependencies(based_on=based_on),
        )
        self.save_version_meta(meta)
        idx = VersionIndex(version_name=version, status="developing")
        self.indexes.save_version_index(idx)
        self._refresh_state(version)
        return meta

    def list_versions(self) -> list[VersionMeta]:
        if not self.version_meta_dir.exists():
            return []
        metas: list[VersionMeta] = []
        for path in sorted(self.version_meta_dir.glob("*.yaml")):
            from .yaml_io import load_model

            metas.append(load_model(path, VersionMeta))
        return metas

    def current(self) -> str | None:
        """Return the newest version that hasn't been merged yet."""
        unmerged = [m for m in self.list_versions() if m.merged_at is None]
        if not unmerged:
            return None
        return max(unmerged, key=lambda m: m.created_at).version

    # ──────────────────────────────────────────────────
    # Chunk-level mutations (called by prd/impl managers)
    # ──────────────────────────────────────────────────

    def add_chunk(
        self,
        version: str,
        *,
        chunk: Chunk,
        action: Action = "add",
        overrides: str | None = None,
        insert_after: str | None = None,
        base_hash: str | None = None,
        source_req: str | None = None,
        discussion_usage: DiscussionUsage | None = None,
    ) -> VersionChunkEntry:
        """Register / refresh a chunk record in the version index.

        Upsert semantics (fix duplicate-append bug observed in v1.6 PRD re-confirm):
          - If an existing entry with the same id is in state ``working``: replace it
            in-place (preserving list order). All mutable fields are refreshed from
            the new chunk + arguments. ``commit_id`` is reset to None.
          - If an existing entry is in state ``staged`` or ``committed``: refuse to
            overwrite (these represent locked progress). Caller must explicitly
            unstage or open a new version.
          - Otherwise: append a new entry at the tail.
        """
        idx = self.indexes.load_version_index(version)

        previous_summary = next(
            (c.summary for c in reversed(idx.chunks) if c.id == chunk.id and c.summary is not None),
            None,
        )
        parsed_summary = chunk.summary if chunk.summary is not None and len(chunk.summary) <= 120 else None
        baseline_summary = None
        base_entry = self.indexes.query_baseline(overrides or chunk.id)
        if base_entry is not None:
            baseline_summary = base_entry.summary

        # Locate any pre-existing record with the same id.
        existing_pos: int | None = None
        for i, c in enumerate(idx.chunks):
            if c.id == chunk.id:
                if c.state in ("staged", "committed"):
                    raise ValidationError([
                        ValidationIssue(
                            severity="E1",
                            code="CHUNK_LOCKED",
                            message=(
                                f"Cannot re-add chunk '{chunk.id}' in version '{version}': "
                                f"existing record is in state '{c.state}' (already locked). "
                                f"Unstage it first or start a new version."
                            ),
                        )
                    ])
                existing_pos = i
                break

        entry = VersionChunkEntry(
            id=chunk.id,
            file=chunk.file,
            heading=chunk.heading,
            level=chunk.level,
            action=action,
            state="working",
            overrides=overrides,
            insert_after=insert_after,
            base_hash=base_hash,
            source_req=source_req,
            discussion_usage=discussion_usage,
            summary=parsed_summary or previous_summary or baseline_summary,
        )
        if existing_pos is not None:
            idx.chunks[existing_pos] = entry
        else:
            idx.chunks.append(entry)
        self.indexes.save_version_index(idx)
        return entry

    def remove_chunk(self, version: str, chunk_id: str) -> bool:
        """Remove all records of `chunk_id` from version index. Returns True if any removed."""
        idx = self.indexes.load_version_index(version)
        before = len(idx.chunks)
        idx.chunks = [c for c in idx.chunks if c.id != chunk_id]
        removed = len(idx.chunks) != before
        if removed:
            self.indexes.save_version_index(idx)
        return removed

    # ─────────────────────────────────────────────────────
    # stage / unstage / commit
    # ─────────────────────────────────────────────────────

    def stage(
        self, version: str, chunk_ids: list[str] | None = None
    ) -> StageResult:
        idx = self.indexes.load_version_index(version)
        staged: list[str] = []
        skipped: list[tuple[str, str]] = []

        for entry in idx.chunks:
            if chunk_ids is not None and entry.id not in chunk_ids:
                continue
            if entry.state == "working":
                entry.state = "staged"
                staged.append(entry.id)
            elif entry.state == "staged":
                skipped.append((entry.id, "already staged"))
            elif entry.state == "committed":
                skipped.append((entry.id, "already committed"))

        # IDs that were requested but not found.
        if chunk_ids:
            existing = {c.id for c in idx.chunks}
            for cid in chunk_ids:
                if cid not in existing:
                    skipped.append((cid, "not in version index"))

        if staged:
            self.indexes.save_version_index(idx)
        return StageResult(staged=staged, skipped=skipped)

    def unstage(self, version: str, chunk_ids: list[str]) -> UnstageResult:
        idx = self.indexes.load_version_index(version)
        unstaged: list[str] = []
        not_found: list[str] = []
        existing = {c.id for c in idx.chunks}
        for cid in chunk_ids:
            if cid not in existing:
                not_found.append(cid)
                continue
            for entry in idx.chunks:
                if entry.id == cid and entry.state == "staged":
                    entry.state = "working"
                    unstaged.append(cid)
                    break
        if unstaged:
            self.indexes.save_version_index(idx)
        return UnstageResult(unstaged=unstaged, not_found=not_found)

    def uncommit(self, version: str, chunk_ids: list[str]) -> dict:
        """Layer-rework primitive: committed/staged → working.

        The pair of a layer confirm's freeze (v2.22: prd revert; later fsd/tdd
        revert). Refused for merged versions — the merged baseline is the only
        terminal state.
        """
        meta = self.load_version_meta(version)
        if meta.merged_at is not None:
            raise VersionManagerError(f"Version {version} is already merged")
        idx = self.indexes.load_version_index(version)
        reverted: list[str] = []
        wanted = set(chunk_ids)
        for entry in idx.chunks:
            if entry.id in wanted:
                wanted.discard(entry.id)
                if entry.state in ("committed", "staged"):
                    entry.state = "working"
                    entry.commit_id = None
                    reverted.append(entry.id)
        if reverted:
            self.indexes.save_version_index(idx)
            self._refresh_state(version)
        return {"reverted": reverted, "not_found": sorted(wanted)}

    def commit(
        self, version: str, message: str, req_id: str | None = None
    ) -> CommitResult:
        idx = self.indexes.load_version_index(version)
        staged_records = [c for c in idx.chunks if c.state == "staged"]
        if not staged_records:
            raise ValidationError(
                [
                    ValidationIssue(
                        severity="E1",
                        code="COMMIT_EMPTY",
                        message=f"No staged chunks in version {version}",
                    )
                ]
            )

        commit_id = f"c{len(idx.commits) + 1}"
        chg_ids: list[str] = []

        # Generate chg-N.yaml for each staged chunk.
        for entry in staged_records:
            chg = self._build_change_record(version, entry, message)
            chg_ids.append(chg.id)
            save_model(self.changes_dir / f"{chg.id}.yaml", chg)
            entry.state = "committed"
            entry.commit_id = commit_id

        idx.commits.append(
            CommitEntry(
                id=commit_id,
                timestamp=datetime.now(timezone.utc),
                message=message,
                chunks=[c.id for c in staged_records],
                req_id=req_id,
            )
        )

        # Update version meta's changes list.
        meta = self.load_version_meta(version)
        meta.changes.extend(chg_ids)
        self.save_version_meta(meta)

        self.indexes.save_version_index(idx)

        from .specgraph import sync_specgraph

        sync_specgraph(self.root)
        self._refresh_state(version)
        return CommitResult(commit_id=commit_id, changes=chg_ids)

    def status(self, version: str) -> StatusReport:
        idx = self.indexes.load_version_index(version)
        working = [c.id for c in idx.chunks if c.state == "working"]
        staged = [c.id for c in idx.chunks if c.state == "staged"]
        committed = [c.id for c in idx.chunks if c.state == "committed"]
        by_action: dict[str, int] = {}
        for c in idx.chunks:
            by_action[c.action] = by_action.get(c.action, 0) + 1
        return StatusReport(
            version=version,
            working=working,
            staged=staged,
            committed=committed,
            by_action=by_action,
        )

    # ─────────────────────────────────────────────────────
    # Redesign: lock state + version reset (atomicity)
    # ─────────────────────────────────────────────────────

    def lock_prd(self, version: str) -> None:
        """Mark PRD as locked (phase → prd_locked). Idempotent."""
        meta = self.load_version_meta(version)
        meta.prd_locked = True
        if meta.phase == "empty":
            meta.phase = "prd_locked"
        self.save_version_meta(meta)

    def lock_impl(self, version: str) -> None:
        """Mark impl as locked (phase → impl_locked). Idempotent."""
        meta = self.load_version_meta(version)
        meta.impl_locked = True
        if meta.phase in ("empty", "prd_locked"):
            meta.phase = "impl_locked"
        self.save_version_meta(meta)

    def assert_prd_writable(self, version: str) -> None:
        meta = self.load_version_meta(version)
        if meta.prd_locked:
            raise VersionManagerError(
                f"PRD is locked in {version}; use `ait version reset {version}` to restart"
            )

    def assert_impl_writable(self, version: str) -> None:
        meta = self.load_version_meta(version)
        if meta.impl_locked:
            raise VersionManagerError(
                f"impl is locked in {version}; use `ait version reset {version}` to restart"
            )

    def set_title(self, version: str, title: str) -> None:
        meta = self.load_version_meta(version)
        meta.title = title
        self.save_version_meta(meta)

    def reset(self, version: str, *, confirmed: bool) -> dict:
        """Roll back to a specific version's merged state, or wipe an unmerged workspace.

        Merged version: git reset --hard to docs_commit, then delete all version
        artefacts that were created after this version (including any open version).
        Unmerged version: physically delete workspace (original behaviour).
        """
        import shutil
        import subprocess

        meta_path = self.version_meta_path(version)
        meta = self.load_version_meta(version) if meta_path.exists() else None

        if meta is not None and meta.merged_at is not None:
            # Anchor resolution (v2.72): the persistent tag (revert_anchor.docs_ref)
            # is a GC-safety OPTIMISATION; the commit SHA (docs_commit / code_result)
            # is the source of truth. Prefer the tag when it resolves, else fall back
            # to the SHA. Only when NEITHER resolves is the anchor unverifiable — a
            # dangling/never-created tag alone no longer blocks a revert.
            anchor = meta.revert_anchor
            if anchor is None and not meta.docs_commit:
                anchor = self._repair_historical_anchor(meta)

            def object_exists(repo: Path, ref: str | None) -> bool:
                if not ref:
                    return False
                result = subprocess.run(
                    ["git", "cat-file", "-e", f"{ref}^{{commit}}"],
                    cwd=repo, capture_output=True, text=True,
                )
                return result.returncode == 0

            def _first_resolvable(repo: Path, *refs: str | None) -> str | None:
                for ref in refs:
                    if object_exists(repo, ref):
                        return ref
                return None

            anchor_docs_ref = anchor.docs_ref if anchor is not None else None
            anchor_code_ref = anchor.code_result if anchor is not None else None
            recorded_docs = anchor_docs_ref or meta.docs_commit
            code_candidate = anchor_code_ref or meta.code_result
            if not recorded_docs:
                raise VersionManagerError(
                    f"version {version} has no verifiable docs revert anchor",
                    code="REVERT_ANCHOR_INVALID",
                )

            docs_head = self._git_head(self.root)
            docs_target = _first_resolvable(self.root, anchor_docs_ref, meta.docs_commit)
            if docs_head is None or docs_target is None:
                raise VersionManagerError(
                    f"docs revert anchor is unavailable: {recorded_docs}",
                    code="REVERT_PRECHECK_FAILED",
                )
            host_head = self._git_head(self.root.parent)
            code_target = (
                _first_resolvable(self.root.parent, anchor_code_ref, meta.code_result)
                if code_candidate else None
            )
            if code_candidate and (host_head is None or code_target is None):
                raise VersionManagerError(
                    f"host revert anchor is unavailable: {code_candidate}",
                    code="REVERT_PRECHECK_FAILED",
                )

            later_versions = [
                item.version for item in self.list_versions()
                if item.merged_at is not None
                and item.version != version
                and item.merged_at > meta.merged_at
            ]
            active = self.current()
            to_clean = list(dict.fromkeys(later_versions + ([active] if active and active != version else [])))
            if not confirmed:
                return {
                    "ok": False,
                    "code": "NEED_CONFIRM",
                    "warning": (
                        f"将把 project-docs git 回滚到 {version} 的最终锚点 "
                        f"({docs_target})，其后版本 {later_versions} 及活动版本 {active!r} 将被删除。"
                        "不可恢复。请加 --confirm"
                    ),
                }

            journal = RecoveryJournal(
                docs_head=docs_head,
                host_head=host_head,
                docs_target=docs_target,
                host_target=code_target,
                later_versions=to_clean,
                phase="applying",
            )
            meta.recovery_journal = journal
            self.save_version_meta(meta)
            docs_switched = False
            host_switched = False
            try:
                docs_result = subprocess.run(
                    ["git", "reset", "--hard", docs_target],
                    cwd=self.root, capture_output=True, text=True,
                )
                if docs_result.returncode != 0:
                    raise VersionManagerError(
                        f"docs git reset failed: {(docs_result.stderr or docs_result.stdout).strip()}",
                        code="REVERT_FAILED",
                    )
                docs_switched = True
                if code_target:
                    host_result = subprocess.run(
                        ["git", "reset", "--hard", code_target],
                        cwd=self.root.parent, capture_output=True, text=True,
                    )
                    if host_result.returncode != 0:
                        raise VersionManagerError(
                            f"host git reset failed: {(host_result.stderr or host_result.stdout).strip()}",
                            code="HOST_RESET_FAILED",
                        )
                    host_switched = True

                for item in to_clean:
                    workspace = self.versions_dir / item
                    if workspace.exists():
                        shutil.rmtree(workspace, ignore_errors=False)
                    (self.meta_dir / f"chunks-index-{item}.yaml").unlink(missing_ok=True)
                    (self.meta_dir / f"specgraph-{item}.yaml").unlink(missing_ok=True)
                    (self.version_meta_dir / f"{item}.yaml").unlink(missing_ok=True)
                clean_result = subprocess.run(
                    ["git", "clean", "-fd", "versions/"],
                    cwd=self.root, capture_output=True, text=True,
                )
                if clean_result.returncode != 0:
                    raise VersionManagerError(
                        f"docs workspace clean failed: {(clean_result.stderr or clean_result.stdout).strip()}",
                        code="REVERT_RECOVERY_PENDING",
                    )
            except Exception as exc:  # noqa: BLE001
                compensation_errors: list[str] = []
                if host_switched and host_head:
                    result = subprocess.run(
                        ["git", "reset", "--hard", host_head],
                        cwd=self.root.parent, capture_output=True, text=True,
                    )
                    if result.returncode != 0:
                        compensation_errors.append("host")
                if docs_switched:
                    result = subprocess.run(
                        ["git", "reset", "--hard", docs_head],
                        cwd=self.root, capture_output=True, text=True,
                    )
                    if result.returncode != 0:
                        compensation_errors.append("docs")
                try:
                    restored = self.load_version_meta(version)
                    restored.recovery_journal = journal.model_copy(
                        update={"phase": "recovery_pending", "diagnostic": str(exc)}
                    )
                    self.save_version_meta(restored)
                except Exception:
                    compensation_errors.append("journal")
                if compensation_errors:
                    raise VersionManagerError(
                        f"revert recovery pending after {exc}: {', '.join(compensation_errors)}",
                        code="REVERT_RECOVERY_PENDING",
                    ) from exc
                if isinstance(exc, VersionManagerError):
                    raise
                raise VersionManagerError(f"revert failed and was compensated: {exc}", code="REVERT_FAILED") from exc

            return {
                "ok": True,
                "reverted_to": version,
                "git_reset": docs_target,
                "host_reset": code_target,
                "invalidated": sorted(later_versions),
                "dropped_active": active,
            }

        # ── Unmerged-version path (original behaviour) ────────────────────────
        if not confirmed:
            return {
                "ok": False,
                "code": "NEED_CONFIRM",
                "warning": f"将物理删除版本 {version} 的所有工作区内容，不可恢复。请加 --confirm",
            }
        shutil.rmtree(self.versions_dir / version, ignore_errors=True)
        (self.meta_dir / f"chunks-index-{version}.yaml").unlink(missing_ok=True)
        (self.meta_dir / f"specgraph-{version}.yaml").unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)
        return {"ok": True, "version": version, "reset": True}

    def pre_merge_check(self, version: str) -> list[str]:
        """Dry-run merge the version specgraph into baseline; detect issues.

        Returns a list of human-readable issue strings (empty = OK). Checks:
          1. dependency cycle (after merge)
          2. intra-version duplicates (same @id / same @extract target)
        """
        from .specgraph import combined_specgraph

        issues: list[str] = []
        merged = combined_specgraph(self.root, version)
        cyc = merged.detect_cycle()
        if cyc:
            issues.append("dependency cycle: " + ", ".join(c.split(":")[-1] for c in cyc))
        issues += self._detect_intra_version_dup(version)
        return issues

    def _detect_intra_version_dup(self, version: str) -> list[str]:
        from .chunk_parser import ExtractError, parse_extract_blocks, parse_file

        issues: list[str] = []
        version_dir = self.versions_dir / version
        if not version_dir.exists():
            return issues
        seen_ids: dict[str, int] = {}
        seen_targets: dict[str, int] = {}
        for path in sorted(version_dir.rglob("*.md")):
            parsed = parse_file(path, version_dir)
            for chunk in parsed.chunks:
                seen_ids[chunk.id] = seen_ids.get(chunk.id, 0) + 1
            try:
                for blk in parse_extract_blocks(path.read_text(encoding="utf-8"), chunks=parsed.chunks):
                    seen_targets[blk.target_chunk] = seen_targets.get(blk.target_chunk, 0) + 1
            except ExtractError as exc:
                issues.append(f"malformed @extract in {path.name}: {exc}")
        issues += [f"duplicate @id: {cid}" for cid, n in seen_ids.items() if n > 1]
        issues += [
            f"@extract target conflict: {t}" for t, n in seen_targets.items() if n > 1
        ]
        return issues

    # ─────────────────────────────────────────────────────
    # Confirmed reconciliation planning (v2.61)
    # ─────────────────────────────────────────────────────

    def _reconciliation_inputs(
        self, version: str
    ) -> tuple[list[VersionChunkEntry], list[ReconciliationOperation], dict[str, ParsedFile]]:
        """Collect every explicit input needed to plan or validate a merge."""
        idx = self.indexes.load_version_index(version)
        records = self._latest_by_chunk_id(
            [record for record in idx.chunks if record.state == "committed"]
        )
        if not records:
            raise VersionManagerError(
                f"Version {version} has no committed chunks", code="MERGE_NO_COMMITTED"
            )
        self._assert_no_duplicate_adds(records)
        self._assert_no_override_conflicts(records)
        records = self._with_atomic_impl_deletes(version, records)

        version_root = self.versions_dir / version
        source_chunks: dict[str, Chunk] = {}
        if version_root.exists():
            for source_path in sorted(version_root.rglob("*.md")):
                parsed = parse_file(source_path, version_root)
                for chunk in parsed.chunks:
                    source_chunks.setdefault(chunk.id, chunk)

        operations: list[ReconciliationOperation] = []
        baseline_files: dict[str, ParsedFile] = {}
        for record in records:
            base_entry = (
                self.indexes.query_baseline(record.overrides or record.id)
                if record.action in ("modify", "delete")
                else None
            )
            target_file = base_entry.file if base_entry is not None else record.file
            if target_file is None:
                raise VersionManagerError(
                    f"Cannot determine merge target for chunk {record.id}",
                    code="MERGE_TARGET_MISSING",
                )
            if self._should_route_legacy_prd_to_global(target_file, [record]):
                target_file = "prd/global"
            baseline_path = self.root / "docs" / f"{target_file}.md"
            if baseline_path.exists() and target_file not in baseline_files:
                baseline_files[target_file] = parse_file(baseline_path, self.root / "docs")

            new_content: str | None = None
            if record.action in ("add", "modify"):
                source = source_chunks.get(record.id)
                if source is None:
                    raise VersionManagerError(
                        f"Version file is missing chunk {record.id} required by record",
                        code="MERGE_SOURCE_MISSING",
                    )
                new_content = source.content
            operations.append(
                ReconciliationOperation(
                    file=target_file,
                    chunk_id=record.id,
                    action=record.action,
                    target_id=record.overrides or record.id,
                    insert_after=record.insert_after,
                    base_hash=record.base_hash,
                    new_content=new_content,
                )
            )
        return records, operations, baseline_files

    def _select_reconciliation_records(
        self,
        records: list[VersionChunkEntry],
        conflict_policy: ConflictPolicy,
    ) -> list[VersionChunkEntry]:
        """Apply the existing optimistic conflict rule before a plan is frozen."""
        baseline_hashes = self._snapshot_baseline_hashes()
        conflicts: list[ConflictReport] = []
        for record in records:
            if record.action not in ("modify", "delete") or not record.base_hash:
                continue
            current = baseline_hashes.get(record.overrides or record.id)
            if current is None:
                conflicts.append(ConflictReport(record.id, "baseline_missing", record.base_hash, None))
            elif current != record.base_hash:
                conflicts.append(ConflictReport(record.id, "hash_mismatch", record.base_hash, current))
        if conflicts and conflict_policy == "abort":
            details = ", ".join(f"{item.chunk_id}:{item.reason}" for item in conflicts)
            raise VersionManagerError(f"merge conflict: {details}", code="MERGE_CONFLICT")
        if conflict_policy == "use-baseline":
            conflicting = {item.chunk_id for item in conflicts}
            return [record for record in records if record.id not in conflicting]
        return records

    def _reconciliation_specgraph_inputs(self, version: str) -> dict[str, str]:
        """Return exact graph files whose content is promoted by a merge."""
        from .specgraph import specgraph_path

        paths = {
            "baseline": specgraph_path(self.root, "baseline"),
            "version": specgraph_path(self.root, version),
        }
        return {
            name: path.read_text(encoding="utf-8") if path.exists() else ""
            for name, path in paths.items()
        }

    def confirm_plan(
        self,
        version: str,
        *,
        conflict_policy: ConflictPolicy = "use-version",
    ) -> dict:
        """Run gates once and persist the sole plan that a later merge may execute."""
        meta = self.load_version_meta(version)
        if meta.merged_at is not None:
            raise VersionManagerError(f"Version {version} is already merged")
        records, all_operations, baseline_files = self._reconciliation_inputs(version)
        selected = self._select_reconciliation_records(records, conflict_policy)
        selected_ids = {record.id for record in selected}
        selected_operations = [
            operation for operation in all_operations if operation.chunk_id in selected_ids
        ]
        fingerprint = reconciliation_input_fingerprint(
            baseline_files,
            all_operations,
            conflict_policy,
            specgraph_inputs=self._reconciliation_specgraph_inputs(version),
        )
        plan = plan_reconciliation(
            baseline_files,
            selected_operations,
            conflict_policy=conflict_policy,
            input_fingerprint=fingerprint,
        )
        meta.confirmed_plan = plan
        meta.recovery_journal = None
        self.save_version_meta(meta)
        return {
            "version": version,
            "passed": True,
            "plan_fingerprint": plan.input_fingerprint,
            "planned_operations": len(plan.operations),
            "conflict_policy": plan.conflict_policy,
        }

    def _docs_plan_path(self, file_key: str) -> Path:
        """Resolve a plan file key while enforcing containment in ``docs/``."""
        docs_root = (self.root / "docs").resolve()
        path = (docs_root / f"{file_key}.md").resolve()
        if path != docs_root and docs_root not in path.parents:
            raise VersionManagerError(
                f"reconciliation plan target escapes docs/: {file_key}",
                code="MERGE_PLAN_INVALID",
            )
        return path

    def _apply_confirmed_plan(self, plan: ReconciliationPlan) -> list[str]:
        baseline_files: dict[str, ParsedFile] = {}
        for operation in plan.operations:
            path = self._docs_plan_path(operation.file)
            if path.exists() and operation.file not in baseline_files:
                baseline_files[operation.file] = parse_file(path, self.root / "docs")
        merged_files = execute_plan(plan, baseline_files)
        for merged in merged_files:
            path = self._docs_plan_path(merged.file)
            atomic_write_text(path, merged.new_content)
        return [operation.chunk_id for operation in plan.operations]

    def merge_confirmed(self, version: str) -> dict:
        """Atomically execute a still-valid plan persisted by :meth:`confirm_plan`."""
        meta = self.load_version_meta(version)
        plan = meta.confirmed_plan
        if plan is None:
            # Preserve the actionable invariant diagnosis that legacy `version
            # merge` callers received before plans were introduced.
            self._assert_new_model_invariants(version)
            raise VersionManagerError(
                f"Version {version} has no confirmed reconciliation plan",
                code="CONFIRMATION_REQUIRED",
            )
        records, all_operations, baseline_files = self._reconciliation_inputs(version)
        selected = self._select_reconciliation_records(records, plan.conflict_policy)
        selected_ids = {record.id for record in selected}
        selected_operations = [
            operation for operation in all_operations if operation.chunk_id in selected_ids
        ]
        fingerprint = reconciliation_input_fingerprint(
            baseline_files,
            all_operations,
            plan.conflict_policy,
            specgraph_inputs=self._reconciliation_specgraph_inputs(version),
        )
        expected_plan = plan_reconciliation(
            baseline_files,
            selected_operations,
            conflict_policy=plan.conflict_policy,
            input_fingerprint=fingerprint,
        )
        if plan != expected_plan:
            raise VersionManagerError(
                f"Version {version} changed after confirm; run version confirm again",
                code="CONFIRMATION_STALE",
            )

        backup = self._backup_state(version)
        try:
            merged_chunks = self._apply_confirmed_plan(plan)
            self.indexes.rebuild_baseline()
            from .specgraph import sync_specgraph

            sync_specgraph(self.root)
            # v2.71: default False (was True). schemas and init already default
            # to False; the merge read points defaulting to True meant projects
            # that never set the field kept producing snapshot trees that have
            # no reader — `meta.snapshot` is written but never read, and rollback
            # relies on docs_commit + the persistent revert tag, not on these
            # copies. Projects that explicitly set True are unaffected.
            auto_snapshot = self._read_config().get("auto_snapshot_on_merge", False)
            if auto_snapshot:
                self._create_snapshot(version)
            self._merge_specgraph_to_baseline(version)
            self._assert_no_orphan_impl_refs()

            meta = self.load_version_meta(version)
            meta.merged_at = datetime.now(timezone.utc)
            meta.snapshot = f"snapshots/{version}/" if auto_snapshot else None
            meta.phase = "merged"
            self.save_version_meta(meta)
            idx = self.indexes.load_version_index(version)
            idx.status = "merged"
            self.indexes.save_version_index(idx)
            commit_msg = meta.title or f"AIT {version} merge"
            merge_commit = self._git_commit(commit_msg)

            meta = self.load_version_meta(version)
            if merge_commit:
                meta.docs_commit = merge_commit
            host_head = self._git_head(self.root.parent)
            if host_head is not None:
                meta.code_base = host_head
                meta.code_result = meta.code_result or host_head
            anchor_ref = f"refs/tags/ait/{version}"
            meta.revert_anchor = RevertAnchor(
                docs_ref=anchor_ref,
                code_result=meta.code_result,
            )
            self.save_version_meta(meta)
            self._refresh_state(version)
            binding_commit = self._git_commit(f"AIT {version} meta: record bindings")
            tag_created = False
            if binding_commit is not None:
                tag_created = self._create_git_tag(anchor_ref, binding_commit)
        except Exception as exc:  # noqa: BLE001
            self._restore_state(backup)
            raise VersionManagerError(
                f"merge/commit failed and was rolled back: {exc}", code="MERGE_ROLLBACK"
            ) from exc
        return {
            "version": version,
            "merged_chunks": merged_chunks,
            "commit": binding_commit,
            "git": "committed" if binding_commit else "unavailable",
            "tag_created": tag_created,
            "plan_fingerprint": plan.input_fingerprint,
        }

    def backfill_revert_tags(self) -> dict:
        """Re-create missing persistent revert tags from each version's docs_commit.

        A merged version whose ``revert_anchor.docs_ref`` names a tag that was
        never persisted (dangling anchor) is repaired by pointing that tag at the
        durable ``docs_commit`` SHA. Idempotent: already-present tags are skipped.
        """
        probe = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=self.root, capture_output=True, text=True,
        )
        if probe.returncode != 0:
            return {"backfilled": [], "skipped": [], "git": "unavailable"}

        backfilled: list[str] = []
        skipped: list[dict] = []
        for meta in self.list_versions():
            if meta.merged_at is None:
                continue
            anchor = meta.revert_anchor
            if anchor is None or not anchor.docs_ref:
                skipped.append({"version": meta.version, "reason": "no_anchor"})
                continue
            exists = subprocess.run(
                ["git", "cat-file", "-e", f"{anchor.docs_ref}^{{commit}}"],
                cwd=self.root, capture_output=True, text=True,
            )
            if exists.returncode == 0:
                skipped.append({"version": meta.version, "reason": "tag_present"})
                continue
            if not meta.docs_commit:
                skipped.append({"version": meta.version, "reason": "no_docs_commit"})
                continue
            if self._create_git_tag(anchor.docs_ref, meta.docs_commit):
                backfilled.append(meta.version)
            else:
                skipped.append({"version": meta.version, "reason": "tag_failed"})
        return {"backfilled": backfilled, "skipped": skipped, "git": "committed"}

    def _repair_historical_anchor(self, meta: VersionMeta) -> RevertAnchor | None:
        """Recover an old binding only when Git history proves one unique target."""
        path = f".meta/versions/{meta.version}.yaml"
        history = subprocess.run(
            ["git", "log", "--format=%H", "--all", "--", path],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        if history.returncode != 0:
            return None

        candidates: list[tuple[str, str | None]] = []
        for commit in history.stdout.splitlines():
            shown = subprocess.run(
                ["git", "show", f"{commit}:{path}"],
                cwd=self.root,
                capture_output=True,
                text=True,
            )
            if shown.returncode != 0:
                continue
            data = yaml.safe_load(shown.stdout) or {}
            if not isinstance(data, dict):
                continue
            docs_commit = data.get("docs_commit")
            if isinstance(docs_commit, str) and docs_commit:
                candidates.append((commit, data.get("code_result")))

        unique = {(commit, code_result) for commit, code_result in candidates}
        if len(unique) != 1:
            return None
        binding_commit, code_result = unique.pop()
        ref = f"refs/tags/ait/{meta.version}"
        self._create_git_tag(ref, binding_commit)
        anchor = RevertAnchor(docs_ref=ref, code_result=code_result)
        meta.revert_anchor = anchor
        meta.historical_anchor_repairs.append(
            HistoricalAnchorRepair(
                version=meta.version,
                source=f"git-history:{binding_commit}",
                docs_ref=ref,
            )
        )
        self.save_version_meta(meta)
        return anchor

    def _git_head(self, repo: Path) -> str | None:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
        )
        return result.stdout.strip() if result.returncode == 0 else None

    def _create_git_tag(self, ref: str, commit: str) -> bool:
        """Create the external rollback anchor and verify it landed.

        The tag is a GC-safety optimisation over docs_commit (the source of
        truth), so a failure here is non-fatal — return False instead of raising
        so a merge is never rolled back over a missing optimisation. The post
        `cat-file` check guards against a tag that silently failed to persist.
        """
        probe = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=self.root, capture_output=True, text=True,
        )
        if probe.returncode != 0:
            return False
        tag = ref.removeprefix("refs/tags/")
        result = subprocess.run(
            ["git", "tag", "-f", tag, commit], cwd=self.root, capture_output=True, text=True
        )
        if result.returncode != 0:
            return False
        verify = subprocess.run(
            ["git", "cat-file", "-e", f"{ref}^{{commit}}"],
            cwd=self.root, capture_output=True, text=True,
        )
        return verify.returncode == 0

    # ─────────────────────────────────────────────────────
    # merge — write committed chunks back into the baseline
    # ─────────────────────────────────────────────────────

    def merge(
        self,
        version: str,
        *,
        conflict_policy: ConflictPolicy = "abort",
        include_uncommitted: bool = False,
    ) -> MergeResult:
        """Apply all committed version chunks to baseline docs/."""
        idx = self.indexes.load_version_index(version)
        meta = self.load_version_meta(version)
        if meta.merged_at is not None:
            raise VersionManagerError(f"Version {version} is already merged")

        # Pick the relevant records: committed only by default.
        records = [c for c in idx.chunks if c.state == "committed"]
        if not records:
            raise ValidationError(
                [
                    ValidationIssue(
                        severity="E1",
                        code="MERGE_NO_COMMITTED",
                        message=f"Version {version} has no committed chunks",
                    )
                ]
            )

        non_committed = [c for c in idx.chunks if c.state != "committed"]
        if non_committed and not include_uncommitted:
            # E2: warn caller — surface via the result; CLI is the one that prompts.
            pass

        # Deduplicate: later committed records in the version index win.
        effective_records = self._latest_by_chunk_id(records)
        self._assert_no_duplicate_adds(effective_records)

        # Conflict detection: compare base_hash to current baseline-chunk hash.
        conflicts: list[ConflictReport] = []
        ok_records: list[VersionChunkEntry] = []
        skipped_records: list[VersionChunkEntry] = []
        baseline_hashes = self._snapshot_baseline_hashes()

        for r in effective_records:
            if r.action in ("modify", "delete") and r.base_hash:
                current = baseline_hashes.get(r.overrides or r.id)
                if current is None:
                    conflicts.append(
                        ConflictReport(
                            chunk_id=r.id,
                            reason="baseline_missing",
                            recorded_hash=r.base_hash,
                            current_hash=None,
                        )
                    )
                    continue
                if current != r.base_hash:
                    conflicts.append(
                        ConflictReport(
                            chunk_id=r.id,
                            reason="hash_mismatch",
                            recorded_hash=r.base_hash,
                            current_hash=current,
                        )
                    )
                    continue
            ok_records.append(r)

        if conflicts:
            if conflict_policy == "abort":
                return MergeResult(
                    merged_chunks=[],
                    conflicts=conflicts,
                    skipped=skipped_records,
                    status="aborted",
                )
            if conflict_policy == "use-baseline":
                conflicting_ids = {c.chunk_id for c in conflicts}
                ok_records = [r for r in effective_records if r.id not in conflicting_ids]
                skipped_records = [r for r in effective_records if r.id in conflicting_ids]
            elif conflict_policy == "use-version":
                ok_records = effective_records  # ignore conflicts, force overwrite

        ok_records = self._with_atomic_impl_deletes(version, ok_records)

        # Group by merge target file. Modify/delete records route through the
        # baseline chunk they override; their version-side draft may live in a
        # different version file.
        by_file: dict[str, list[VersionChunkEntry]] = {}
        for r in ok_records:
            file_key = r.file
            if r.action in ("modify", "delete"):
                base_entry = self.indexes.query_baseline(r.overrides or r.id)
                if base_entry:
                    file_key = base_entry.file
            if file_key is None:
                continue
            # PRD baseline 单文件化：所有 prd/* 路由强制收敛到 prd/global，
            # 版本工作区允许多文件，但 confirm 阶段统一落到 docs/prd/global.md。
            # impl/* 类目不受影响。
            if self._should_route_legacy_prd_to_global(file_key, [r]):
                file_key = "prd/global"
            by_file.setdefault(file_key, []).append(r)

        # Apply per-file merges.
        for file_key, records_for_file in by_file.items():
            records_for_file = [r for r in records_for_file if r in ok_records]
            if not records_for_file:
                continue
            self._merge_one_file(version, file_key, records_for_file)

        # Persist baseline + links indices.
        self.indexes.rebuild_baseline()

        from .specgraph import sync_specgraph

        sync_specgraph(self.root)

        # Snapshot. v2.71: default False — see the confirm-path read point above.
        auto_snapshot = self._read_config().get("auto_snapshot_on_merge", False)
        if auto_snapshot:
            self._create_snapshot(version)

        # Update version meta.
        meta.merged_at = datetime.now(timezone.utc)
        meta.snapshot = f"snapshots/{version}/" if auto_snapshot else None
        meta.phase = "merged"
        self.save_version_meta(meta)
        idx.status = "merged"
        self.indexes.save_version_index(idx)
        self._refresh_state(version)

        return MergeResult(
            merged_chunks=[r.id for r in ok_records],
            conflicts=conflicts,
            skipped=skipped_records,
            status="completed",
        )

    # ─────────────────────────────────────────────────────
    # Redesign: version confirm — guard → merge → git commit (atomic)
    # ─────────────────────────────────────────────────────

    def confirm(
        self,
        version: str,
        *,
        allow_dirty_git: bool = False,
        conflict_policy: ConflictPolicy = "use-version",
    ) -> dict:
        """Backward-compatible atomic shortcut: persist a plan, then execute it."""
        backup = self._backup_state(version)
        try:
            report = self.gate(
                version,
                conflict_policy=conflict_policy,
                check_host=not allow_dirty_git,
            )
            if not report["passed"]:
                violation = report["violations"][0]
                precondition_codes = {
                    "DUPLICATE_BASELINE_CHUNK",
                    "DUPLICATE_OVERRIDES_TARGET",
                    "MODIFY_RENAME_COLLISION",
                }
                domain_code = (
                    violation["code"]
                    if violation["code"] in precondition_codes
                    else "INVARIANT_VIOLATION"
                )
                raise VersionManagerError(
                    violation["message"]
                    if domain_code in precondition_codes
                    else f"{violation['code']}: {violation['message']}",
                    code=domain_code,
                )
            return self.merge_confirmed(version)
        except Exception:
            self._restore_state(backup)
            raise

    def gate(
        self,
        version: str,
        *,
        conflict_policy: ConflictPolicy = "use-version",
        check_host: bool = True,
    ) -> dict:
        """Run confirm gates and persist the canonical reconciliation plan."""
        meta = self.load_version_meta(version)
        if meta.merged_at is not None:
            raise VersionManagerError(f"Version {version} is already merged")

        violations: list[dict] = []
        from .task_manager import TaskManager

        tasks = TaskManager(self.root).list_tasks(version)
        for task in tasks:
            if task.status != "done":
                violations.append(
                    {"code": "TASK_NOT_DONE", "message": f"task not done: {task.id}", "chunk_id": task.id}
                )
        idx = self.indexes.load_version_index(version)
        records = [c for c in idx.chunks if c.state == "committed"]
        effective = self._latest_by_chunk_id(records)
        for check in (self._assert_no_duplicate_adds, self._assert_no_override_conflicts):
            try:
                check(effective)
            except VersionManagerError as exc:
                violations.append(
                    {"code": getattr(exc, "code", "DUPLICATE_BASELINE_CHUNK"), "message": str(exc), "chunk_id": None}
                )
        new_model_violations = self._collect_new_model_violations(version)
        violations.extend(
            {
                "code": v.code,
                "message": v.message,
                "chunk_id": v.chunk_id,
            }
            for v in new_model_violations
            if getattr(v, "enforcement", None) != "warn"
        )
        warnings: list[dict] = [
            {
                "code": v.code,
                "message": v.message,
                "chunk_id": v.chunk_id,
            }
            for v in new_model_violations
            if getattr(v, "enforcement", None) == "warn"
        ]
        acceptance = self.run_acceptance()
        if not acceptance["passed"]:
            violations.append(
                {"code": "ACCEPTANCE_FAILED", "message": "artifact acceptance failed", "chunk_id": None}
            )

        if violations:
            return {
                "version": version,
                "passed": False,
                "violations": violations,
                "warnings": warnings,
                "acceptance": acceptance,
            }

        # Gate passed — AIT commits the host artifact repo and binds code_result
        # (G25). Symmetric with revert's two-repo rollback: the docs version now
        # points at an AIT-authored host commit capturing this version's code.
        if check_host:
            artifacts = self._commit_host_artifacts(version)
            if artifacts["sha"] is not None:
                meta = self.load_version_meta(version)
                meta.code_result = artifacts["sha"]
                self.save_version_meta(meta)
        else:
            artifacts = {"committed": False, "sha": None, "files": 0}

        plan_report = self.confirm_plan(version, conflict_policy=conflict_policy)
        return {
            "version": version,
            "passed": True,
            "violations": [],
            "warnings": warnings,
            "acceptance": acceptance,
            "code_result": artifacts["sha"],
            "artifacts": artifacts,
            **plan_report,
        }

    def _commit_host_artifacts(self, version: str) -> dict:
        """Commit the host artifact repo at confirm; return the binding SHA (G25).

        Captures the full host working-tree state as this version's artifact
        commit so ``code_result`` is an AIT-authored commit — symmetric with
        revert's two-repo rollback. Non-git host → vacuous (sha=None). Clean
        host → no new commit, sha = current HEAD.
        """
        import subprocess
        host = self.root.parent
        probe = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=host, capture_output=True, text=True,
        )
        if probe.returncode != 0:
            return {"committed": False, "sha": None, "files": 0}

        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=host, capture_output=True, text=True,
        )
        dirty = [ln for ln in status.stdout.splitlines() if ln.strip()]
        committed = False
        if dirty:
            add = subprocess.run(["git", "add", "-A"], cwd=host, capture_output=True, text=True)
            if add.returncode != 0:
                raise VersionManagerError(
                    f"host git add failed: {(add.stderr or add.stdout).strip()}",
                    code="HOST_COMMIT_FAILED",
                )
            commit = subprocess.run(
                ["git", "commit", "-m", f"AIT {version} artifacts"],
                cwd=host, capture_output=True, text=True,
            )
            if commit.returncode != 0:
                out = (commit.stdout or "") + (commit.stderr or "")
                if "nothing to commit" not in out:
                    raise VersionManagerError(
                        f"host git commit failed: {out.strip()[-300:]}",
                        code="HOST_COMMIT_FAILED",
                    )
            else:
                committed = True

        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=host, capture_output=True, text=True,
        )
        sha = head.stdout.strip() if head.returncode == 0 else None
        return {"committed": committed, "sha": sha, "files": len(dirty)}

    def _assert_new_model_invariants(self, version: str) -> None:
        """Six-invariant confirm gate on baseline∪version (audit-family closer).

        Delegates to :meth:`_collect_new_model_violations` (shared with the
        repeatable :meth:`gate`). Rejection happens before any disk mutation —
        fix the specs and retry. Vacuous when the project has no new-model
        chunks.
        """
        violations = self._collect_new_model_violations(version)
        if violations:
            summary = "; ".join(
                f"{v.code}({v.chunk_id or v.rel or '-'})" for v in violations[:10]
            )
            more = f" …+{len(violations) - 10}" if len(violations) > 10 else ""
            raise VersionManagerError(
                f"新模型不变式违例，confirm 被拒（修复后可重试）: {summary}{more}",
                code="INVARIANT_VIOLATION",
            )

    def _collect_new_model_violations(self, version: str):
        """Shared collection kernel for gate() and _assert_new_model_invariants().

        Shape + legacy dangling edges are checked on the raw merged graph
        (the combined view drops dangling edges by contract); the six
        invariants run on the collapsed chunk_id view.
        """
        from .new_model_validator import (
            validate_invariants,
            validate_prd_fsd_tdd_graph,
        )
        from .specgraph import combined_specgraph, combined_view

        raw = combined_specgraph(self.root, version)
        violations = validate_prd_fsd_tdd_graph(raw)
        view = combined_view(self.root, version)
        targets = self._collect_new_model_target_files(view)

        scopes = config_store.read_config(self.root / ".meta").get("artifact_scopes", {})
        suffixes = frozenset(s["parent_suffix"] for s in scopes.values())
        exempt = frozenset(
            cid for s in scopes.values() for cid in s.get("exempt_test_splits", [])
        )
        for v in validate_invariants(
            view, targets, test_scope_suffixes=suffixes, test_scope_exempt=exempt,
        ):
            if v.code == "TEST_SPLIT_UNCOVERED" and v.chunk_id:
                matched = next(
                    (s for s in scopes.values() if v.chunk_id.endswith(s["parent_suffix"])),
                    None,
                )
                if matched is not None:
                    v = _dc_replace(v, enforcement=matched.get("enforcement", "warn"))
            violations.append(v)
        if scopes:
            violations += self._scope_coverage_violations(scopes, targets)
        return violations

    def _scope_coverage_violations(
        self, scopes: dict, targets: list[tuple[str, str | None]]
    ) -> list:
        """v2.83: read-only host `git ls-files` enumeration per configured
        scope prefix, diffed against declared TDD target_files. Non-git host
        or any git failure → vacuous (must never report false UNCOVERED_ARTIFACT
        because enumeration was unavailable)."""
        from .new_model_validator import NewModelViolation

        declared = {
            self._normalize_target_file(target) for _cid, target in targets if target
        }
        out: list[NewModelViolation] = []
        host_root = self.root.parent
        for prefix, scope in scopes.items():
            try:
                result = subprocess.run(
                    ["git", "ls-files", prefix], cwd=host_root,
                    capture_output=True, text=True, timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if result.returncode != 0:
                continue
            for line in result.stdout.splitlines():
                path = line.strip()
                if path and self._normalize_target_file(path) not in declared:
                    out.append(
                        NewModelViolation(
                            code="UNCOVERED_ARTIFACT",
                            message=f"{path} in scope '{prefix}' has no owning TDD",
                            chunk_id=None,
                            enforcement=scope.get("enforcement", "warn"),
                        )
                    )
        return out

    @staticmethod
    def _normalize_target_file(target: str) -> str:
        from .new_model_validator import normalize_target_file

        return normalize_target_file(target)

    def _collect_new_model_target_files(self, view) -> list[tuple[str, str | None]]:
        """(chunk_id, target_file|None) for every new-model TDD node in the view."""
        import re

        pattern = re.compile(r"^\s*target_file:\s*(\S+)\s*$", re.MULTILINE)
        entries: list[tuple[str, str | None]] = []
        for node in view.nodes.values():
            if node.type != "tdd" or not node.chunk_id.startswith("[TDD]-"):
                continue
            base_dir = (
                self.versions_dir / node.version
                if node.version != "baseline"
                else self.root / "docs"
            )
            path = base_dir / f"{node.file}.md"
            if not path.exists():
                entries.append((node.chunk_id, None))
                continue
            match = pattern.search(path.read_text(encoding="utf-8"))
            entries.append((node.chunk_id, match.group(1) if match else None))
        return entries

    def _backup_state(self, version: str) -> dict:
        """Byte-level in-memory snapshot of confirm-mutable state.

        Covers docs/*.md plus the .meta files the merge phase writes, so a
        failed confirm rolls back completely — no stray "merged" markers
        (audit R1-01) and no line-ending rewrites on restore.
        """
        docs = self.root / "docs"
        doc_files: dict[str, bytes] = {}
        if docs.exists():
            for path in docs.rglob("*.md"):
                doc_files[str(path)] = path.read_bytes()
        meta_files: dict[str, bytes | None] = {}
        for p in self._confirm_meta_paths(version):
            meta_files[str(p)] = p.read_bytes() if p.exists() else None
        snapshot_dir = self.meta_dir / "snapshots" / version
        return {
            "docs": doc_files,
            "meta": meta_files,
            "snapshot_existed": snapshot_dir.exists(),
            "version": version,
        }

    def _confirm_meta_paths(self, version: str) -> list[Path]:
        """The .meta files confirm's merge phase writes to."""
        return [
            self.meta_dir / "chunks-index.yaml",
            self.meta_dir / "specgraph.yaml",
            self.version_meta_path(version),
            self.meta_dir / f"chunks-index-{version}.yaml",
        ]

    @staticmethod
    def _write_bytes_atomic(path: Path, data: bytes) -> None:
        """Byte-faithful atomic write (tmp + replace); no newline translation."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp-restore")
        tmp.write_bytes(data)
        tmp.replace(path)

    def _restore_state(self, backup: dict) -> None:
        """Restore docs/ and .meta byte-for-byte; remove files created after snapshot."""
        docs = self.root / "docs"
        if docs.exists():
            for path in docs.rglob("*.md"):
                if str(path) not in backup["docs"]:
                    path.unlink(missing_ok=True)
        for path_str, data in backup["docs"].items():
            self._write_bytes_atomic(Path(path_str), data)
        for path_str, data in backup["meta"].items():
            p = Path(path_str)
            if data is None:
                p.unlink(missing_ok=True)
            else:
                self._write_bytes_atomic(p, data)
        if not backup["snapshot_existed"]:
            snapshot_dir = self.meta_dir / "snapshots" / backup["version"]
            if snapshot_dir.exists():
                shutil.rmtree(snapshot_dir)

    def _extract_dynamic_global(self, version: str) -> list[str]:
        """Extract @extract blocks from this version's impl into dynamic global.

        Each block routes to docs/global/{type}.md and upserts a chunk named
        block.target_chunk (same-chunk replace). Returns written chunk ids.
        """
        from .chunk_parser import parse_extract_blocks, parse_file

        version_dir = self.versions_dir / version
        if not version_dir.exists():
            return []
        written: list[str] = []
        for path in sorted((version_dir / "impl").rglob("*.md")) if (version_dir / "impl").exists() else []:
            text = path.read_text(encoding="utf-8")
            parsed = parse_file(path, version_dir)
            for blk in parse_extract_blocks(text, chunks=parsed.chunks):
                gtype = blk.target_type  # ddl | schema | api
                target_file = self.root / "docs" / "global" / f"{gtype}.md"
                self._upsert_global_chunk(target_file, blk.target_chunk, blk.content, gtype)
                written.append(blk.target_chunk)
        return written

    def _upsert_global_chunk(
        self, target_file: Path, chunk_id: str, body: str, gtype: str
    ) -> None:
        """Insert-or-replace a dynamic global chunk in target_file."""
        from .chunk_parser import parse_file

        heading_map = {"ddl": "数据库 DDL", "schema": "数据结构 Schema", "api": "API 契约"}
        block = f"<!-- @id:{chunk_id} -->\n## {chunk_id}\n\n{body}\n"
        if not target_file.exists():
            header = f"<!-- @id:global-{gtype} -->\n## {heading_map.get(gtype, gtype)}\n\n"
            target_file.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(target_file, header + block)
            return
        parsed = parse_file(target_file, self.root / "docs")
        existing = next((c for c in parsed.chunks if c.id == chunk_id), None)
        text = target_file.read_text(encoding="utf-8")
        if existing is not None:
            # replace the existing chunk content verbatim
            new_text = text.replace(existing.content, block.rstrip("\n"), 1)
        else:
            new_text = text.rstrip("\n") + "\n\n" + block
        atomic_write_text(target_file, new_text)

    def _merge_specgraph_to_baseline(self, version: str) -> None:
        """Promote version specgraph nodes/edges into baseline graph file."""
        from .specgraph import Edge, load_specgraph, specgraph_path

        base = load_specgraph(self.root, "baseline")
        vg = load_specgraph(self.root, version)

        # v2.26 declaration reconcile: an FSD root touched in this version owns
        # its sibling depends_on scope — replace baseline's scope wholesale so
        # removed declarations actually disappear (same rule as combined_view).
        def _chunk_of(graph, uri: str) -> str:
            spec = graph.specs.get(uri)
            if spec is not None:
                return spec.chunk_id
            from .specgraph import parse_uri

            try:
                return parse_uri(uri)[2]
            except ValueError:
                return uri

        # A rename-style modify replaces the old baseline identity. Rebase all
        # inherited relations to the version spec before promotion; otherwise
        # the merged graph would retain a dangling endpoint for the old id.
        version_specs_by_id = {spec.chunk_id: spec for spec in vg.specs.values()}
        replacements = {
            entry.overrides: entry.id
            for entry in self.indexes.load_version_index(version).chunks
            if (
                entry.action == "modify"
                and entry.overrides
                and entry.overrides != entry.id
                and entry.id in version_specs_by_id
            )
        }
        if replacements:
            replacement_uris = {
                old_id: version_specs_by_id[new_id].uri
                for old_id, new_id in replacements.items()
            }
            base.edges = [
                Edge(
                    src=replacement_uris.get(_chunk_of(base, edge.src), edge.src),
                    dst=replacement_uris.get(_chunk_of(base, edge.dst), edge.dst),
                    rel=edge.rel,
                    weight=edge.weight,
                    metadata=dict(edge.metadata),
                )
                for edge in base.edges
            ]
            for uri, spec in list(base.specs.items()):
                if spec.chunk_id in replacements:
                    del base.specs[uri]

        owned_roots = {
            spec.chunk_id for spec in vg.specs.values()
            if spec.type == "fsd" and ":" not in spec.chunk_id
        }
        if owned_roots:
            base.edges = [
                e for e in base.edges
                if not (
                    e.rel == "depends_on"
                    and ":" in _chunk_of(base, e.src)
                    and _chunk_of(base, e.src).split(":", 1)[0] in owned_roots
                )
            ]

        for spec in vg.specs.values():
            # v2.64: promotion must not leak version-workspace-only lifecycle
            # fields (state/action/commit_id) into the baseline metadata —
            # they're meaningless once a chunk is part of baseline and would
            # otherwise force every next `sync` to strip them back out.
            promoted_metadata = {
                k: v for k, v in spec.metadata.items()
                if k not in ("state", "action", "commit_id")
            }
            if promoted_metadata != spec.metadata:
                from .specgraph import Spec as _Spec

                spec = _Spec(
                    uri=spec.uri,
                    title=spec.title,
                    type=spec.type,
                    version=spec.version,
                    chunk_id=spec.chunk_id,
                    file=spec.file,
                    metadata=promoted_metadata,
                )
            base.add_spec(spec)
        for edge in vg.edges:
            base.add_edge(edge.src, edge.dst, edge.rel, weight=edge.weight,
                          metadata=dict(edge.metadata))
        base.merge_into_baseline(version)
        base.save(specgraph_path(self.root, "baseline"))

    def _assert_no_orphan_impl_refs(self) -> None:
        from .specgraph import load_specgraph, parse_uri

        graph = load_specgraph(self.root, "baseline")
        missing: list[tuple[str, str]] = []
        for edge in graph.edges:
            if edge.rel != "implements":
                continue
            src = graph.specs.get(edge.src)
            if src is None or src.type != "impl":
                continue
            dst = graph.specs.get(edge.dst)
            if dst is None:
                try:
                    missing_id = parse_uri(edge.dst)[2]
                except ValueError:
                    missing_id = edge.dst
                missing.append((src.chunk_id, missing_id))
        if missing:
            detail = ", ".join(f"{impl}->{prd}" for impl, prd in missing)
            raise VersionManagerError(f"orphan impl @refs after merge: {detail}")

    @staticmethod
    def _latest_by_chunk_id(records: list[VersionChunkEntry]) -> list[VersionChunkEntry]:
        """Return the last committed record for each chunk id."""
        latest: dict[str, VersionChunkEntry] = {}
        for record in records:
            latest.pop(record.id, None)
            latest[record.id] = record
        return list(latest.values())

    def _assert_no_duplicate_adds(self, records: list[VersionChunkEntry]) -> None:
        """Reject add records that would append an already-existing baseline chunk."""
        baseline_by_id = {entry.id: entry for entry in self.indexes.load_baseline().chunks}
        issues: list[ValidationIssue] = []
        for record in records:
            if record.action != "add" or record.id not in baseline_by_id:
                continue
            baseline_entry = baseline_by_id[record.id]
            issues.append(
                ValidationIssue(
                    severity="E1",
                    code="DUPLICATE_BASELINE_CHUNK",
                    message=(
                        f"chunk '{record.id}' is action=add but already exists in "
                        f"baseline file '{baseline_entry.file}'. Use action=modify "
                        "with overrides, or skip inherited/no-op chunks."
                    ),
                    chunk_id=record.id,
                    file=record.file or baseline_entry.file,
                )
            )
        if issues:
            raise ValidationError(issues)

    def _assert_no_override_conflicts(self, records: list[VersionChunkEntry]) -> None:
        """Merge-precheck for override collisions (audit R1-07/R1-08).

        - modify-rename: id != overrides while id already exists in baseline —
          the merge would emit a duplicate ``@id`` (MODIFY_RENAME_COLLISION).
        - two effective records targeting the same override — later silently
          overwrites earlier (DUPLICATE_OVERRIDES_TARGET).
        """
        baseline_ids = {entry.id for entry in self.indexes.load_baseline().chunks}
        owners: dict[str, str] = {}
        for record in records:
            if record.action not in ("modify", "delete"):
                continue
            target = record.overrides or record.id
            if (
                record.action == "modify"
                and record.overrides
                and record.id != record.overrides
                and record.id in baseline_ids
            ):
                raise VersionManagerError(
                    f"modify 改名撞已存在 baseline id: '{record.id}'(overrides "
                    f"'{record.overrides}') —— 合并会产生重复 @id",
                    code="MODIFY_RENAME_COLLISION",
                )
            if target in owners and owners[target] != record.id:
                raise VersionManagerError(
                    f"两条记录撞同一 override 目标 '{target}': "
                    f"'{owners[target]}' 与 '{record.id}' —— 后者会静默覆盖前者",
                    code="DUPLICATE_OVERRIDES_TARGET",
                )
            owners[target] = record.id

    def _with_atomic_impl_deletes(
        self, version: str, records: list[VersionChunkEntry]
    ) -> list[VersionChunkEntry]:
        changed_prd_ids = self._changed_prd_ids(records)
        if not changed_prd_ids:
            return records

        from .specgraph import load_specgraph

        baseline_graph = load_specgraph(self.root, "baseline")
        version_graph = load_specgraph(self.root, version)
        explicit_deletes = {
            r.overrides or r.id for r in records if r.action == "delete"
        }
        existing_ids = {r.id for r in records}
        existing_ids.update(
            r.overrides
            for r in records
            if r.action in ("modify", "delete") and r.overrides is not None
        )
        synthetic: list[VersionChunkEntry] = []

        for prd_id in changed_prd_ids:
            baseline_impl_ids = set(baseline_graph.implements_of(prd_id, version="baseline"))
            version_impl_ids = self._implements_of_exact_version(version_graph, prd_id, version)
            for impl_id in sorted(baseline_impl_ids - version_impl_ids):
                if impl_id in explicit_deletes or impl_id in existing_ids:
                    continue
                base_entry = self.indexes.query_baseline(impl_id)
                if base_entry is None:
                    continue
                synthetic.append(
                    VersionChunkEntry(
                        id=impl_id,
                        file=base_entry.file,
                        heading=None,
                        level=None,
                        action="delete",
                        state="committed",
                        overrides=impl_id,
                        base_hash=None,
                        summary=base_entry.summary,
                    )
                )
                existing_ids.add(impl_id)
        return records + synthetic

    @staticmethod
    def _changed_prd_ids(records: list[VersionChunkEntry]) -> set[str]:
        return {
            r.id for r in records
            if r.id.startswith("prd-") and r.action in ("add", "modify", "delete")
        }

    @staticmethod
    def _should_route_legacy_prd_to_global(file_key: str, records: list[VersionChunkEntry]) -> bool:
        if not file_key.startswith("prd/") or file_key == "prd/global":
            return False
        return all(record.id.startswith("prd-") for record in records)

    @staticmethod
    def _implements_of_exact_version(graph, prd_chunk_id: str, version: str) -> set[str]:
        result: set[str] = set()
        for edge in graph.edges:
            if edge.rel != "implements":
                continue
            src = graph.specs.get(edge.src)
            dst = graph.specs.get(edge.dst)
            if src is None or dst is None:
                continue
            if src.version == version and dst.chunk_id == prd_chunk_id:
                result.add(src.chunk_id)
        return result

    def _git_clean(self) -> bool:
        import subprocess

        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.root, capture_output=True, text=True, check=True,
            )
            return result.stdout.strip() == ""
        except Exception:
            # No git / not a repo → treat as clean (don't block on git absence).
            return True

    # ── Artifact acceptance gate (v2.25) ───────────────────────────────

    def _config_path(self) -> Path:
        return self.meta_dir / config_store.SHARED_CONFIG_NAME

    def _read_config(self) -> dict:
        """Return the merged layered config.

        v2.71: no local try/except swallowing. The previous implementation
        caught every exception and returned ``{}``, which made "config is
        corrupt" indistinguishable from "nothing configured" — and since
        ``run_acceptance`` treats a missing command as *skipped*, a corrupt
        config silently disabled the acceptance gate. Corruption now surfaces
        as ``CONFIG_UNREADABLE`` so confirm/merge fail closed. A missing or
        empty file still yields ``{}``, so genuinely unconfigured projects keep
        skipping acceptance as before. The foundation-level error is re-raised
        as a domain error carrying the *same* code, so the CLI's existing
        handler reports it without rewriting the code.
        """
        try:
            return config_store.read_config(self.meta_dir)
        except config_store.ConfigError as exc:
            raise VersionManagerError(str(exc), code=exc.code) from exc

    def _legacy_machine_fields(self) -> dict:
        """Machine fields still in the shared layer (same error translation)."""
        try:
            return config_store.find_legacy_machine_fields(self.meta_dir)
        except config_store.ConfigError as exc:
            raise VersionManagerError(str(exc), code=exc.code) from exc

    def set_acceptance_command(self, command: str | None) -> dict:
        """Persist ``acceptance_command`` into the machine-local config layer.

        v2.71: routed via config_store instead of writing the shared
        ``config.yaml``. The value is machine-specific *and* gets executed, so
        it must not ride along in the shared docs history to other machines.
        """
        if command:
            config_store.write_config_fields(
                self.meta_dir, {"acceptance_command": command}
            )
        else:
            # Unset clears both layers, which also cleans up a pre-v2.71 copy.
            config_store.write_config_fields(
                self.meta_dir, delete=["acceptance_command"]
            )
        return {"acceptance_command": self._read_config().get("acceptance_command")}

    def run_acceptance(self) -> dict:
        """Run the project's configured acceptance command; gate merge on it.

        Reads ``acceptance_command`` from the layered config. Absent/empty →
        skipped (vacuous pass — legacy and non-test projects unaffected).
        Otherwise runs it at the project root (parent of project-docs, where
        tests/artifacts live) and passes iff exit code is 0.

        v2.71: a command still sitting in the *shared* layer is refused rather
        than executed, so a config that travels with the repo can never drive
        command execution on this machine without the user migrating first.
        """
        legacy = self._legacy_machine_fields()
        if "acceptance_command" in legacy:
            raise VersionManagerError(
                "acceptance_command is still stored in the shared config layer; "
                "run `init --migrate --apply` to relocate it before running "
                "acceptance",
                code="LEGACY_ACCEPTANCE_CONFIG",
            )
        command = (self._read_config().get("acceptance_command") or "").strip()
        if not command:
            return {"passed": True, "skipped": True, "command": None}
        import subprocess

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.root.parent,
                capture_output=True,
                text=True,
                timeout=600,
            )
            output = (result.stdout or "") + (result.stderr or "")
            return {
                "passed": result.returncode == 0,
                "skipped": False,
                "command": command,
                "exit_code": result.returncode,
                "output_tail": output[-2000:],
            }
        except Exception as exc:  # noqa: BLE001 — timeout / spawn failure → fail closed
            return {
                "passed": False,
                "skipped": False,
                "command": command,
                "exit_code": None,
                "output_tail": f"acceptance run failed: {exc}",
            }

    def _git_commit(self, message: str) -> str | None:
        """Three-way git-commit semantics (audit R1-06 closer).

        - Not a git repo / git unavailable → None (tolerated; confirm reports
          ``git: "unavailable"`` — test fixtures and git-less environments).
        - Repo, but nothing to commit → no-op, return current HEAD.
        - Repo, and add/commit genuinely fails → raise ``GIT_COMMIT_FAILED``
          so confirm's rollback machinery restores state (no fake success).
        """
        import subprocess

        try:
            probe = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=self.root, capture_output=True, text=True,
            )
        except Exception:
            return None  # git binary unavailable
        if probe.returncode != 0:
            return None  # not a repo

        def _head() -> str:
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=self.root,
                capture_output=True, text=True, check=True,
            )
            return head.stdout.strip()

        add = subprocess.run(["git", "add", "-A"], cwd=self.root,
                             capture_output=True, text=True)
        if add.returncode != 0:
            raise VersionManagerError(
                f"git add 失败: {(add.stderr or add.stdout).strip()}",
                code="GIT_COMMIT_FAILED",
            )
        commit = subprocess.run(["git", "commit", "-m", message], cwd=self.root,
                                capture_output=True, text=True)
        if commit.returncode != 0:
            output = (commit.stdout or "") + (commit.stderr or "")
            if "nothing to commit" in output or "nothing added to commit" in output:
                return _head()
            raise VersionManagerError(
                f"git commit 失败: {output.strip()[-500:]}",
                code="GIT_COMMIT_FAILED",
            )
        return _head()

    def _snapshot_baseline_hashes(self) -> dict[str, str]:
        """Return {chunk_id: hash} for every chunk currently in baseline."""
        hashes: dict[str, str] = {}
        baseline = self.indexes.build_baseline()
        # Build a quick file→ParsedFile cache.
        cache: dict[str, list[Chunk]] = {}
        for entry in baseline.chunks:
            if entry.file not in cache:
                path = self.root / "docs" / f"{entry.file}.md"
                if not path.exists():
                    cache[entry.file] = []
                    continue
                pf = parse_file(path, self.root / "docs")
                cache[entry.file] = list(pf.chunks)
            for c in cache[entry.file]:
                if c.id == entry.id:
                    hashes[entry.id] = chunk_hash(c.content)
                    break
        return hashes

    def _merge_one_file(
        self,
        version: str,
        file_key: str,
        records: list[VersionChunkEntry],
    ) -> None:
        """Stitch records into docs/{file_key}.md (creating it if necessary)."""
        baseline_path = self.root / "docs" / f"{file_key}.md"
        version_path = self.versions_dir / version / f"{file_key}.md"

        # Build VersionChunkOps from records, pulling new content from the version file.
        version_chunks_by_id: dict[str, Chunk] = {}
        if version_path.exists():
            pf = parse_file(version_path, self.versions_dir / version)
            version_chunks_by_id = {c.id: c for c in pf.chunks}

        needed_ids = {
            r.id for r in records if r.action in ("add", "modify")
        } - set(version_chunks_by_id)
        if needed_ids:
            version_root = self.versions_dir / version
            for md_path in sorted(version_root.rglob("*.md")):
                if md_path == version_path:
                    continue
                pf = parse_file(md_path, version_root)
                for c in pf.chunks:
                    if c.id in needed_ids:
                        version_chunks_by_id.setdefault(c.id, c)
                        needed_ids.discard(c.id)
                if not needed_ids:
                    break

        ops: list[VersionChunkOp] = []
        for r in records:
            chunk_for_op: Chunk | None = None
            if r.action in ("add", "modify"):
                chunk_for_op = version_chunks_by_id.get(r.id)
                if chunk_for_op is None:
                    raise VersionManagerError(
                        f"Version file is missing chunk {r.id} required by record"
                    )
            ops.append(
                VersionChunkOp(
                    chunk_id=r.id,
                    action=r.action,
                    overrides=r.overrides,
                    insert_after=r.insert_after,
                    new_chunk=chunk_for_op,
                    base_hash=r.base_hash,
                )
            )

        if baseline_path.exists():
            base_parsed = parse_file(baseline_path, self.root / "docs")
            merged = merge_file(base_parsed, ops)
        else:
            merged = merge_new_file(file_key, ops)

        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(baseline_path, merged.new_content)

    def _create_snapshot(self, version: str) -> Path:
        snapshot_root = self.meta_dir / "snapshots" / version
        if snapshot_root.exists():
            shutil.rmtree(snapshot_root)
        snapshot_root.mkdir(parents=True)
        docs_src = self.root / "docs"
        if docs_src.exists():
            shutil.copytree(docs_src, snapshot_root / "docs")
        return snapshot_root

    # ─────────────────────────────────────────────────────
    # Internals
    # ─────────────────────────────────────────────────────

    def _refresh_state(self, version: str) -> None:
        try:
            from .state import save_state

            save_state(self.root, version)
        except Exception:
            pass

    def _next_chg_id(self) -> str:
        self.changes_dir.mkdir(parents=True, exist_ok=True)
        existing = sorted(self.changes_dir.glob("chg-*.yaml"))
        if not existing:
            return "chg-001"
        last = existing[-1].stem  # chg-NNN
        try:
            n = int(last.split("-")[1]) + 1
        except (IndexError, ValueError):
            n = len(existing) + 1
        return f"chg-{n:03d}"

    def _build_change_record(
        self, version: str, entry: VersionChunkEntry, message: str
    ) -> ChangeRecord:
        ctype: ChangeType = {
            "add": "ADD",
            "modify": "MODIFY",
            "delete": "DELETE",
        }[entry.action]

        new_content: str | None = None
        if entry.action in ("add", "modify") and entry.file:
            version_path = (
                self.versions_dir / version / f"{entry.file}.md"
            )
            if version_path.exists():
                # Re-parse to extract just this chunk's content.
                pf = parse_file(version_path, self.versions_dir / version)
                for c in pf.chunks:
                    if c.id == entry.id:
                        new_content = c.content
                        break

        base_content: str | None = None
        if entry.action in ("modify", "delete") and entry.overrides:
            base_entry = self.indexes.query_baseline(entry.overrides)
            if base_entry:
                base_path = self.root / "docs" / f"{base_entry.file}.md"
                if base_path.exists():
                    pf = parse_file(base_path, self.root / "docs")
                    for c in pf.chunks:
                        if c.id == entry.overrides:
                            base_content = c.content
                            break

        target_file = entry.file or (
            self.indexes.query_baseline(entry.overrides).file
            if entry.overrides and self.indexes.query_baseline(entry.overrides)
            else "unknown"
        )
        target = f"{target_file}#{entry.id}"

        return ChangeRecord(
            id=self._next_chg_id(),
            version=version,
            type=ctype,
            target=target,
            author="system",
            date=datetime.now(timezone.utc),
            message=message,
            base_hash=entry.base_hash,
            discussion_usage=entry.discussion_usage,
            base_content=base_content,
            new_content=new_content,
        )

    # ─────────────────────────────────────────────────────
    # Helpers for writing version files (used by prd/impl managers)
    # ─────────────────────────────────────────────────────

    def write_version_file(
        self, version: str, file: str, content: str
    ) -> Path:
        """Write or overwrite a version-scoped markdown file atomically.

        `file` is the index-form path (no .md), e.g. "prd/book-recommend".
        """
        path = self.versions_dir / version / f"{file}.md"
        atomic_write_text(path, content)
        return path

    def read_version_file(self, version: str, file: str) -> str:
        path = self.versions_dir / version / f"{file}.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def chunk_hash_in_version(
        self, version: str, file: str, chunk_id: str
    ) -> str | None:
        """Convenience: compute hash of a chunk currently sitting in a version file."""
        path = self.versions_dir / version / f"{file}.md"
        if not path.exists():
            return None
        pf = parse_file(path, self.versions_dir / version)
        for c in pf.chunks:
            if c.id == chunk_id:
                return chunk_hash(c.content)
        return None
