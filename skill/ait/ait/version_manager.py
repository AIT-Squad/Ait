"""Version manager — three-stage commit lifecycle.

Per project-docs/docs/impl/version-manager.md:
    working → staged → committed → (merged via merge_engine, see Phase 3)

Public API (Phase 2 — Phase 3 adds `merge`):
    create / list_versions / current
    add_block / update_block (used by prd_manager / impl_manager)
    stage / unstage / commit / status
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from .block_parser import Block, parse_file, parse_text
from .hash_utils import block_hash
from .index_manager import IndexManager
from .io_utils import atomic_write_text
from .merge_engine import MergedFile, VersionBlockOp, merge_file, merge_new_file
from .schemas import (
    Action,
    ChangeRecord,
    ChangeType,
    CommitEntry,
    State,
    VersionBlockEntry,
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
    skipped: list[tuple[str, str]]  # (block_id, reason)


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
    block_id: str
    reason: str
    recorded_hash: str | None
    current_hash: str | None


@dataclass
class MergeResult:
    merged_blocks: list[str]
    conflicts: list[ConflictReport]
    skipped: list[VersionBlockEntry]
    status: str  # "completed" | "aborted"


class VersionManagerError(Exception):
    pass


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

    # ─────────────────────────────────────────────────────
    # Block-level mutations (called by prd/impl managers)
    # ─────────────────────────────────────────────────────

    def add_block(
        self,
        version: str,
        *,
        block: Block,
        action: Action = "add",
        overrides: str | None = None,
        insert_after: str | None = None,
        base_hash: str | None = None,
        source_req: str | None = None,
    ) -> VersionBlockEntry:
        """Register a new block record in the version index (state=working)."""
        idx = self.indexes.load_version_index(version)
        entry = VersionBlockEntry(
            id=block.id,
            file=block.file,
            heading=block.heading,
            level=block.level,
            action=action,
            state="working",
            overrides=overrides,
            insert_after=insert_after,
            base_hash=base_hash,
            source_req=source_req,
        )
        idx.blocks.append(entry)
        self.indexes.save_version_index(idx)
        return entry

    def remove_block(self, version: str, block_id: str) -> bool:
        """Remove all records of `block_id` from version index. Returns True if any removed."""
        idx = self.indexes.load_version_index(version)
        before = len(idx.blocks)
        idx.blocks = [b for b in idx.blocks if b.id != block_id]
        removed = len(idx.blocks) != before
        if removed:
            self.indexes.save_version_index(idx)
        return removed

    # ─────────────────────────────────────────────────────
    # stage / unstage / commit
    # ─────────────────────────────────────────────────────

    def stage(
        self, version: str, block_ids: list[str] | None = None
    ) -> StageResult:
        idx = self.indexes.load_version_index(version)
        staged: list[str] = []
        skipped: list[tuple[str, str]] = []

        for entry in idx.blocks:
            if block_ids is not None and entry.id not in block_ids:
                continue
            if entry.state == "working":
                entry.state = "staged"
                staged.append(entry.id)
            elif entry.state == "staged":
                skipped.append((entry.id, "already staged"))
            elif entry.state == "committed":
                skipped.append((entry.id, "already committed"))

        # IDs that were requested but not found.
        if block_ids:
            existing = {b.id for b in idx.blocks}
            for bid in block_ids:
                if bid not in existing:
                    skipped.append((bid, "not in version index"))

        if staged:
            self.indexes.save_version_index(idx)
        return StageResult(staged=staged, skipped=skipped)

    def unstage(self, version: str, block_ids: list[str]) -> UnstageResult:
        idx = self.indexes.load_version_index(version)
        unstaged: list[str] = []
        not_found: list[str] = []
        existing = {b.id for b in idx.blocks}
        for bid in block_ids:
            if bid not in existing:
                not_found.append(bid)
                continue
            for entry in idx.blocks:
                if entry.id == bid and entry.state == "staged":
                    entry.state = "working"
                    unstaged.append(bid)
                    break
        if unstaged:
            self.indexes.save_version_index(idx)
        return UnstageResult(unstaged=unstaged, not_found=not_found)

    def commit(
        self, version: str, message: str, req_id: str | None = None
    ) -> CommitResult:
        idx = self.indexes.load_version_index(version)
        staged_records = [b for b in idx.blocks if b.state == "staged"]
        if not staged_records:
            raise ValidationError(
                [
                    ValidationIssue(
                        severity="E1",
                        code="COMMIT_EMPTY",
                        message=f"No staged blocks in version {version}",
                    )
                ]
            )

        commit_id = f"c{len(idx.commits) + 1}"
        chg_ids: list[str] = []

        # Generate chg-N.yaml for each staged block.
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
                blocks=[b.id for b in staged_records],
                req_id=req_id,
            )
        )

        # Update version meta's changes list.
        meta = self.load_version_meta(version)
        meta.changes.extend(chg_ids)
        self.save_version_meta(meta)

        self.indexes.save_version_index(idx)
        return CommitResult(commit_id=commit_id, changes=chg_ids)

    def status(self, version: str) -> StatusReport:
        idx = self.indexes.load_version_index(version)
        working = [b.id for b in idx.blocks if b.state == "working"]
        staged = [b.id for b in idx.blocks if b.state == "staged"]
        committed = [b.id for b in idx.blocks if b.state == "committed"]
        by_action: dict[str, int] = {}
        for b in idx.blocks:
            by_action[b.action] = by_action.get(b.action, 0) + 1
        return StatusReport(
            version=version,
            working=working,
            staged=staged,
            committed=committed,
            by_action=by_action,
        )

    # ─────────────────────────────────────────────────────
    # merge — write committed blocks back into the baseline
    # ─────────────────────────────────────────────────────

    def merge(
        self,
        version: str,
        *,
        conflict_policy: ConflictPolicy = "abort",
        include_uncommitted: bool = False,
    ) -> MergeResult:
        """Apply all committed version blocks to baseline docs/."""
        idx = self.indexes.load_version_index(version)
        meta = self.load_version_meta(version)
        if meta.merged_at is not None:
            raise VersionManagerError(f"Version {version} is already merged")

        # Pick the relevant records: committed only by default.
        records = [b for b in idx.blocks if b.state == "committed"]
        if not records:
            raise ValidationError(
                [
                    ValidationIssue(
                        severity="E1",
                        code="MERGE_NO_COMMITTED",
                        message=f"Version {version} has no committed blocks",
                    )
                ]
            )

        non_committed = [b for b in idx.blocks if b.state != "committed"]
        if non_committed and not include_uncommitted:
            # E2: warn caller — surface via the result; CLI is the one that prompts.
            pass

        # Deduplicate: latest committed per id wins (largest commit_id).
        latest: dict[str, VersionBlockEntry] = {}
        for r in records:
            existing = latest.get(r.id)
            if existing is None or (r.commit_id or "") > (existing.commit_id or ""):
                latest[r.id] = r
        effective_records = list(latest.values())

        # Group by file. Delete records carry no file → use overrides for routing.
        by_file: dict[str, list[VersionBlockEntry]] = {}
        for r in effective_records:
            file_key = r.file
            if file_key is None and r.overrides:
                base_entry = self.indexes.query_baseline(r.overrides)
                if base_entry:
                    file_key = base_entry.file
            if file_key is None:
                continue
            by_file.setdefault(file_key, []).append(r)

        # Conflict detection: compare base_hash to current baseline-block hash.
        conflicts: list[ConflictReport] = []
        ok_records: list[VersionBlockEntry] = []
        skipped_records: list[VersionBlockEntry] = []
        baseline_hashes = self._snapshot_baseline_hashes()

        for r in effective_records:
            if r.action in ("modify", "delete") and r.base_hash:
                current = baseline_hashes.get(r.overrides or r.id)
                if current is None:
                    conflicts.append(
                        ConflictReport(
                            block_id=r.id,
                            reason="baseline_missing",
                            recorded_hash=r.base_hash,
                            current_hash=None,
                        )
                    )
                    continue
                if current != r.base_hash:
                    conflicts.append(
                        ConflictReport(
                            block_id=r.id,
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
                    merged_blocks=[],
                    conflicts=conflicts,
                    skipped=skipped_records,
                    status="aborted",
                )
            if conflict_policy == "use-baseline":
                conflicting_ids = {c.block_id for c in conflicts}
                ok_records = [r for r in effective_records if r.id not in conflicting_ids]
                skipped_records = [r for r in effective_records if r.id in conflicting_ids]
            elif conflict_policy == "use-version":
                ok_records = effective_records  # ignore conflicts, force overwrite

        # Apply per-file merges.
        for file_key, records_for_file in by_file.items():
            records_for_file = [r for r in records_for_file if r in ok_records]
            if not records_for_file:
                continue
            self._merge_one_file(version, file_key, records_for_file)

        # Persist baseline + links indices.
        self.indexes.rebuild_baseline()

        # Snapshot.
        self._create_snapshot(version)

        # Update version meta.
        meta.merged_at = datetime.now(timezone.utc)
        meta.snapshot = f"snapshots/{version}/"
        self.save_version_meta(meta)
        idx.status = "merged"
        self.indexes.save_version_index(idx)

        return MergeResult(
            merged_blocks=[r.id for r in ok_records],
            conflicts=conflicts,
            skipped=skipped_records,
            status="completed",
        )

    def _snapshot_baseline_hashes(self) -> dict[str, str]:
        """Return {block_id: hash} for every block currently in baseline."""
        hashes: dict[str, str] = {}
        baseline = self.indexes.build_baseline()
        # Build a quick file→ParsedFile cache.
        cache: dict[str, list[Block]] = {}
        for entry in baseline.blocks:
            if entry.file not in cache:
                path = self.root / "docs" / f"{entry.file}.md"
                if not path.exists():
                    cache[entry.file] = []
                    continue
                pf = parse_file(path, self.root / "docs")
                cache[entry.file] = list(pf.blocks)
            for b in cache[entry.file]:
                if b.id == entry.id:
                    hashes[entry.id] = block_hash(b.content)
                    break
        return hashes

    def _merge_one_file(
        self,
        version: str,
        file_key: str,
        records: list[VersionBlockEntry],
    ) -> None:
        """Stitch records into docs/{file_key}.md (creating it if necessary)."""
        baseline_path = self.root / "docs" / f"{file_key}.md"
        version_path = self.versions_dir / version / f"{file_key}.md"

        # Build VersionBlockOps from records, pulling new content from the version file.
        version_blocks_by_id: dict[str, Block] = {}
        if version_path.exists():
            pf = parse_file(version_path, self.versions_dir / version)
            version_blocks_by_id = {b.id: b for b in pf.blocks}

        ops: list[VersionBlockOp] = []
        for r in records:
            block_for_op: Block | None = None
            if r.action in ("add", "modify"):
                block_for_op = version_blocks_by_id.get(r.id)
                if block_for_op is None:
                    raise VersionManagerError(
                        f"Version file is missing block {r.id} required by record"
                    )
            ops.append(
                VersionBlockOp(
                    block_id=r.id,
                    action=r.action,
                    overrides=r.overrides,
                    insert_after=r.insert_after,
                    new_block=block_for_op,
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
        self, version: str, entry: VersionBlockEntry, message: str
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
                # Re-parse to extract just this block's content.
                pf = parse_file(version_path, self.versions_dir / version)
                for b in pf.blocks:
                    if b.id == entry.id:
                        new_content = b.content
                        break

        base_content: str | None = None
        if entry.action in ("modify", "delete") and entry.overrides:
            base_entry = self.indexes.query_baseline(entry.overrides)
            if base_entry:
                base_path = self.root / "docs" / f"{base_entry.file}.md"
                if base_path.exists():
                    pf = parse_file(base_path, self.root / "docs")
                    for b in pf.blocks:
                        if b.id == entry.overrides:
                            base_content = b.content
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

    def block_hash_in_version(
        self, version: str, file: str, block_id: str
    ) -> str | None:
        """Convenience: compute hash of a block currently sitting in a version file."""
        path = self.versions_dir / version / f"{file}.md"
        if not path.exists():
            return None
        pf = parse_file(path, self.versions_dir / version)
        for b in pf.blocks:
            if b.id == block_id:
                return block_hash(b.content)
        return None
