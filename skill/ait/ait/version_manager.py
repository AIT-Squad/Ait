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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .chunk_parser import Chunk, parse_file, parse_text
from .hash_utils import chunk_hash
from .index_manager import IndexManager
from .io_utils import atomic_write_text
from .merge_engine import MergedFile, VersionChunkOp, merge_file, merge_new_file
from .schemas import (
    Action,
    ChangeRecord,
    ChangeType,
    CommitEntry,
    State,
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
        """Create a fresh version: directory skeleton + meta + empty index."""
        version_dir = self.versions_dir / version
        if version_dir.exists():
            raise VersionManagerError(f"Version {version} already exists")
        (version_dir / "prd").mkdir(parents=True)
        (version_dir / "impl").mkdir(parents=True)

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
        """Physically delete the version workspace and return to a blank state.

        The sole escape hatch for the atomic-version model. No snapshot kept.
        Merged versions cannot be reset.
        """
        import shutil

        meta_path = self.version_meta_path(version)
        if meta_path.exists():
            meta = self.load_version_meta(version)
            if meta.merged_at is not None:
                raise VersionManagerError(
                    f"version {version} is merged and cannot be reset"
                )
        if not confirmed:
            return {
                "ok": False,
                "code": "NEED_CONFIRM",
                "warning": f"将物理删除版本 {version} 的所有工作区内容，不可恢复。请加 --confirm",
            }
        # 1. version workspace (also covers versions/{version}/tasks/)
        shutil.rmtree(self.versions_dir / version, ignore_errors=True)
        # 2. indices + meta + specgraph (split file → clean delete)
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
        from .chunk_parser import parse_file, parse_extract_blocks, ExtractError

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

        # Deduplicate: latest committed per id wins (largest commit_id).
        latest: dict[str, VersionChunkEntry] = {}
        for r in records:
            existing = latest.get(r.id)
            if existing is None or (r.commit_id or "") > (existing.commit_id or ""):
                latest[r.id] = r
        effective_records = list(latest.values())

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

        # Group by file. Delete records carry no file → use overrides for routing.
        by_file: dict[str, list[VersionChunkEntry]] = {}
        for r in ok_records:
            file_key = r.file
            if file_key is None and r.overrides:
                base_entry = self.indexes.query_baseline(r.overrides)
                if base_entry:
                    file_key = base_entry.file
            if file_key is None:
                continue
            # PRD baseline 单文件化：所有 prd/* 路由强制收敛到 prd/global，
            # 版本工作区允许多文件，但 confirm 阶段统一落到 docs/prd/global.md。
            # impl/* 类目不受影响。
            if file_key.startswith("prd/") and file_key != "prd/global":
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

        # Snapshot.
        self._create_snapshot(version)

        # Update version meta.
        meta.merged_at = datetime.now(timezone.utc)
        meta.snapshot = f"snapshots/{version}/"
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

    def confirm(self, version: str, *, allow_dirty_git: bool = False) -> dict:
        """Atomic version confirm: precheck → merge → extract → specgraph → git.

        Two-phase with rollback: if anything in the merge/commit phase fails,
        docs/ is restored to its pre-merge state. Either fully succeeds (docs
        updated + git commit) or nothing changes.
        """
        meta = self.load_version_meta(version)
        if meta.merged_at is not None:
            raise VersionManagerError(f"Version {version} is already merged")

        # ── Phase 1: precheck guards (no file mutation) ──
        from .task_manager import TaskManager

        tm = TaskManager(self.root)
        tasks = tm.list_tasks(version)
        not_done = [t.id for t in tasks if t.status != "done"]
        if not_done:
            raise VersionManagerError(
                f"存在未完成 task，无法 confirm: {not_done}", code="TASK_NOT_DONE"
            )
        if not allow_dirty_git and not self._git_clean():
            raise VersionManagerError(
                "git 工作区不干净，请先提交或暂存改动（或加 --allow-dirty-git）",
                code="GIT_DIRTY",
            )

        # ── Phase 2: merge (mutates docs/, fully reversible) ──
        backup = self._backup_docs()
        try:
            merge_result = self.merge(version, conflict_policy="use-version")
            extracted = self._extract_dynamic_global(version)
            # Dynamic globals were written to docs/ AFTER merge's index rebuild;
            # re-index so the new global chunks land in baseline index+specgraph.
            if extracted:
                self.indexes.rebuild_baseline()
                from .specgraph import sync_specgraph

                sync_specgraph(self.root)
            self._merge_specgraph_to_baseline(version)
            self._assert_no_orphan_impl_refs()
            # ── Phase 3: git commit ──
            commit_msg = meta.title or f"AIT {version} merge"
            commit_hash = self._git_commit(commit_msg)
        except Exception as exc:  # noqa: BLE001 — rollback then re-raise as domain error
            self._restore_docs(backup)
            raise VersionManagerError(
                f"merge/commit 失败已回退: {exc}", code="MERGE_ROLLBACK"
            )

        # mark merged phase on meta (merge() already set merged_at)
        meta = self.load_version_meta(version)
        meta.phase = "merged"
        self.save_version_meta(meta)
        self._refresh_state(version)

        return {
            "version": version,
            "merged_chunks": merge_result.merged_chunks,
            "extracted_dynamic": extracted,
            "commit": commit_hash,
            "commit_msg": commit_msg,
        }

    def _backup_docs(self) -> dict[str, str]:
        """In-memory snapshot of every docs/ file (path → content)."""
        docs = self.root / "docs"
        snap: dict[str, str] = {}
        if docs.exists():
            for path in docs.rglob("*.md"):
                snap[str(path)] = path.read_text(encoding="utf-8")
        return snap

    def _restore_docs(self, backup: dict[str, str]) -> None:
        """Restore docs/ to a prior snapshot; remove files created after it."""
        docs = self.root / "docs"
        if docs.exists():
            for path in docs.rglob("*.md"):
                if str(path) not in backup:
                    path.unlink(missing_ok=True)
        for path_str, content in backup.items():
            p = Path(path_str)
            p.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(p, content)

    def _extract_dynamic_global(self, version: str) -> list[str]:
        """Extract @extract blocks from this version's impl into dynamic global.

        Each block routes to docs/global/{type}.md and upserts a chunk named
        block.target_chunk (same-chunk replace). Returns written chunk ids.
        """
        from .chunk_parser import parse_file, parse_extract_blocks

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
        from .specgraph import load_specgraph, specgraph_path

        base = load_specgraph(self.root, "baseline")
        vg = load_specgraph(self.root, version)
        for spec in vg.specs.values():
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

    def _with_atomic_impl_deletes(
        self, version: str, records: list[VersionChunkEntry]
    ) -> list[VersionChunkEntry]:
        changed_prd_ids = self._changed_prd_ids(records)
        if not changed_prd_ids:
            return records

        from .specgraph import load_specgraph

        baseline_graph = load_specgraph(self.root, "baseline")
        version_graph = load_specgraph(self.root, version)
        explicit_deletes = {r.id for r in records if r.action == "delete"}
        existing_ids = {r.id for r in records}
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

    def _git_commit(self, message: str) -> str | None:
        import subprocess

        try:
            subprocess.run(["git", "add", "-A"], cwd=self.root, check=True,
                           capture_output=True, text=True)
            subprocess.run(["git", "commit", "-m", message], cwd=self.root, check=True,
                           capture_output=True, text=True)
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=self.root,
                capture_output=True, text=True, check=True,
            )
            return result.stdout.strip()
        except Exception:
            # If git isn't available, the doc merge still stands; signal no commit.
            return None

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

        # PRD baseline 单文件化：版本工作区允许多文件 (versions/<v>/prd/*.md)，
        # 但 baseline 唯一文件是 prd/global.md。当合并目标是 prd/global 时，
        # 额外汇总版本侧 prd/ 目录下所有 .md，使每条 record.id 都能在工作区找到 chunk。
        if file_key == "prd/global":
            prd_version_dir = self.versions_dir / version / "prd"
            if prd_version_dir.is_dir():
                for md_path in sorted(prd_version_dir.glob("*.md")):
                    if md_path == version_path:
                        continue
                    pf = parse_file(md_path, self.versions_dir / version)
                    for c in pf.chunks:
                        version_chunks_by_id.setdefault(c.id, c)

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