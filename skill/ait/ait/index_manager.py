"""Index manager — baseline / version / links indices.

Per project-docs/docs/prd/index-system.md:
    - Baseline index covers docs/ ; flat list with id/file/heading/level.
    - Version index covers versions/{vX.Y}/ ; same fields + action/state/commit_id/...
    - Links index aggregates @ref relations across all parsed files.
    - Indices are written atomically via yaml_io.save_model.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError

from .chunk_parser import ParsedFile, parse_file
from .io_utils import strip_md_ext, to_posix_rel
from .schemas import (
    BaselineChunkEntry,
    BaselineIndex,
    LinkEntry,
    LinksIndex,
    VersionChunkEntry,
    VersionIndex,
    VersionIndexStats,
)
from .yaml_io import load_model, save_model

class IndexSchemaViolation(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = "INDEX_SCHEMA_VIOLATION"

class IndexManager:
    """Read and write the three index files under .meta/."""

    BASELINE_FILE = "chunks-index.yaml"
    LINKS_FILE = "links-index.yaml"

    def __init__(self, project_root: Path):
        self.root = project_root.resolve()
        self.docs_dir = self.root / "docs"
        self.versions_dir = self.root / "versions"
        self.meta_dir = self.root / ".meta"

    # ─────────────────────────────────────────────────────
    # Path helpers
    # ─────────────────────────────────────────────────────

    def baseline_index_path(self) -> Path:
        return self.meta_dir / self.BASELINE_FILE

    def links_index_path(self) -> Path:
        return self.meta_dir / self.LINKS_FILE

    def version_dir(self, version: str) -> Path:
        return self.versions_dir / version

    def version_index_path(self, version: str) -> Path:
        return self.meta_dir / f"chunks-index-{version}.yaml"

    def find_baseline_file(self, file: str) -> Path | None:
        path = self.docs_dir / f"{file}.md"
        return path if path.exists() else None

    def find_version_file(self, version: str, file: str) -> Path | None:
        path = self.version_dir(version) / f"{file}.md"
        return path if path.exists() else None

    # ─────────────────────────────────────────────────────
    # Baseline + links
    # ─────────────────────────────────────────────────────

    def scan_dir(self, base_dir: Path) -> list[ParsedFile]:
        """Walk a directory and parse every .md file."""
        results: list[ParsedFile] = []
        if not base_dir.exists():
            return results
        for path in sorted(base_dir.rglob("*.md")):
            if path.is_file():
                results.append(parse_file(path, base_dir))
        return results

    def build_baseline(self) -> BaselineIndex:
        """Rescan docs/ and rebuild the baseline index in-memory."""
        previous_summary = {
            entry.id: entry.summary
            for entry in self.load_baseline().chunks
            if entry.summary is not None
        }
        parsed_files = self.scan_dir(self.docs_dir)
        entries: list[BaselineChunkEntry] = []
        for pf in parsed_files:
            for chunk in pf.chunks:
                entries.append(
                    BaselineChunkEntry(
                        id=chunk.id,
                        file=pf.file,
                        heading=chunk.heading,
                        level=chunk.level,
                        summary=chunk.summary or previous_summary.get(chunk.id),
                    )
                )
        return BaselineIndex(
            updated=datetime.now(timezone.utc),
            chunks=entries,
        )

    def build_links(self) -> LinksIndex:
        """Scan docs/ + all versions/ and aggregate all @ref links.

        Each link is recorded as `from: {file}#{chunk-id}`, `to: ...`, `rel: ...`.
        Baseline-only — versions' refs are merged in on `version merge`.
        """
        links: list[LinkEntry] = []
        for pf in self.scan_dir(self.docs_dir):
            for ref in pf.refs:
                links.append(
                    LinkEntry.model_validate(
                        {
                            "from": f"{pf.file}#{ref.source_chunk_id}",
                            "to": f"{ref.target_file}#{ref.target_chunk_id}",
                            "rel": ref.rel,
                        }
                    )
                )
        return LinksIndex(updated=datetime.now(timezone.utc), links=links)

    def rebuild_baseline(self) -> tuple[BaselineIndex, LinksIndex]:
        """Build + persist baseline chunks-index.

        NOTE (redesign): links-index is DEPRECATED — all relation queries now
        go through specgraph. We still return a LinksIndex object for backward
        compatibility with callers, but no longer write links-index.yaml to disk.
        """
        baseline = self.build_baseline()
        save_model(self.baseline_index_path(), baseline)
        # links-index.yaml intentionally not written (deprecated).
        return baseline, LinksIndex()

    def load_baseline(self) -> BaselineIndex:
        path = self.baseline_index_path()
        if not path.exists():
            return BaselineIndex()
        try:
            return load_model(path, BaselineIndex)
        except PydanticValidationError as exc:
            raise IndexSchemaViolation(f"{path}: {exc}") from exc

    def load_links(self) -> LinksIndex:
        path = self.links_index_path()
        if not path.exists():
            return LinksIndex()
        return load_model(path, LinksIndex)

    def query_baseline(self, chunk_id: str) -> BaselineChunkEntry | None:
        idx = self.load_baseline()
        for entry in idx.chunks:
            if entry.id == chunk_id:
                return entry
        return None

    # ─────────────────────────────────────────────────────
    # Version index
    # ─────────────────────────────────────────────────────

    def load_version_index(self, version: str) -> VersionIndex:
        path = self.version_index_path(version)
        if not path.exists():
            return VersionIndex(version_name=version)
        try:
            return load_model(path, VersionIndex)
        except PydanticValidationError as exc:
            raise IndexSchemaViolation(f"{path}: {exc}") from exc

    def save_version_index(self, idx: VersionIndex) -> None:
        idx.stats = self._compute_stats(idx)
        idx.stats.tasks_summary = self._compute_tasks_summary(idx.version_name)
        save_model(self.version_index_path(idx.version_name), idx)

    def _compute_tasks_summary(self, version: str) -> dict[str, int]:
        """Aggregate task status counts for a version.

        Defensive: any failure (missing tasks dir, import cycle, malformed
        YAML) yields empty summary so save_version_index never blows up.
        """
        summary = {"created": 0, "executing": 0, "done": 0, "failed": 0}
        try:
            from .task_manager import TaskManager

            tm = TaskManager(self.root)
            for t in tm.list_tasks(version):
                summary[t.status] = summary.get(t.status, 0) + 1
        except Exception:
            pass
        return summary

    def query_version(
        self, version: str, chunk_id: str
    ) -> VersionChunkEntry | None:
        """Return the latest record for `chunk_id` in the version index.

        Order: committed (newest commit_id) > staged > working.
        """
        idx = self.load_version_index(version)
        matches = [c for c in idx.chunks if c.id == chunk_id]
        if not matches:
            return None
        committed = [c for c in matches if c.state == "committed"]
        if committed:
            return max(committed, key=lambda c: c.commit_id or "")
        staged = [c for c in matches if c.state == "staged"]
        if staged:
            return staged[-1]
        working = [c for c in matches if c.state == "working"]
        return working[-1] if working else matches[-1]

    def all_version_records(
        self, version: str, chunk_id: str
    ) -> list[VersionChunkEntry]:
        idx = self.load_version_index(version)
        return [c for c in idx.chunks if c.id == chunk_id]

    @staticmethod
    def _compute_stats(idx: VersionIndex) -> VersionIndexStats:
        by_action: dict[str, int] = {}
        by_state: dict[str, int] = {}
        for c in idx.chunks:
            by_action[c.action] = by_action.get(c.action, 0) + 1
            by_state[c.state] = by_state.get(c.state, 0) + 1
        return VersionIndexStats(
            total_chunks=len(idx.chunks),
            by_action=by_action,
            by_state=by_state,
        )

    # ─────────────────────────────────────────────────────
    # Convenience: list known versions
    # ─────────────────────────────────────────────────────

    def list_versions(self) -> list[str]:
        if not self.versions_dir.exists():
            return []
        return sorted(p.name for p in self.versions_dir.iterdir() if p.is_dir())