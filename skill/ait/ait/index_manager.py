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

from .block_parser import ParsedFile, parse_file
from .io_utils import strip_md_ext, to_posix_rel
from .schemas import (
    BaselineBlockEntry,
    BaselineIndex,
    LinkEntry,
    LinksIndex,
    VersionBlockEntry,
    VersionIndex,
    VersionIndexStats,
)
from .yaml_io import load_model, save_model


class IndexManager:
    """Read and write the three index files under .meta/."""

    BASELINE_FILE = "blocks-index.yaml"
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
        return self.meta_dir / f"blocks-index-{version}.yaml"

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
        parsed_files = self.scan_dir(self.docs_dir)
        entries: list[BaselineBlockEntry] = []
        for pf in parsed_files:
            for block in pf.blocks:
                entries.append(
                    BaselineBlockEntry(
                        id=block.id,
                        file=pf.file,
                        heading=block.heading,
                        level=block.level,
                    )
                )
        return BaselineIndex(
            updated=datetime.now(timezone.utc),
            blocks=entries,
        )

    def build_links(self) -> LinksIndex:
        """Scan docs/ + all versions/ and aggregate all @ref links.

        Each link is recorded as `from: {file}#{block-id}`, `to: ...`, `rel: ...`.
        Baseline-only — versions' refs are merged in on `version merge`.
        """
        links: list[LinkEntry] = []
        for pf in self.scan_dir(self.docs_dir):
            for ref in pf.refs:
                links.append(
                    LinkEntry.model_validate(
                        {
                            "from": f"{pf.file}#{ref.source_block_id}",
                            "to": f"{ref.target_file}#{ref.target_block_id}",
                            "rel": ref.rel,
                        }
                    )
                )
        return LinksIndex(updated=datetime.now(timezone.utc), links=links)

    def rebuild_baseline(self) -> tuple[BaselineIndex, LinksIndex]:
        """Build + persist baseline blocks-index and links-index."""
        baseline = self.build_baseline()
        links = self.build_links()
        save_model(self.baseline_index_path(), baseline)
        save_model(self.links_index_path(), links)
        return baseline, links

    def load_baseline(self) -> BaselineIndex:
        path = self.baseline_index_path()
        if not path.exists():
            return BaselineIndex()
        return load_model(path, BaselineIndex)

    def load_links(self) -> LinksIndex:
        path = self.links_index_path()
        if not path.exists():
            return LinksIndex()
        return load_model(path, LinksIndex)

    def query_baseline(self, block_id: str) -> BaselineBlockEntry | None:
        idx = self.load_baseline()
        for entry in idx.blocks:
            if entry.id == block_id:
                return entry
        return None

    # ─────────────────────────────────────────────────────
    # Version index
    # ─────────────────────────────────────────────────────

    def load_version_index(self, version: str) -> VersionIndex:
        path = self.version_index_path(version)
        if not path.exists():
            return VersionIndex(version_name=version)
        return load_model(path, VersionIndex)

    def save_version_index(self, idx: VersionIndex) -> None:
        idx.stats = self._compute_stats(idx)
        save_model(self.version_index_path(idx.version_name), idx)

    def query_version(
        self, version: str, block_id: str
    ) -> VersionBlockEntry | None:
        """Return the latest record for `block_id` in the version index.

        Order: committed (newest commit_id) > staged > working.
        """
        idx = self.load_version_index(version)
        matches = [b for b in idx.blocks if b.id == block_id]
        if not matches:
            return None
        committed = [b for b in matches if b.state == "committed"]
        if committed:
            return max(committed, key=lambda b: b.commit_id or "")
        staged = [b for b in matches if b.state == "staged"]
        if staged:
            return staged[-1]
        working = [b for b in matches if b.state == "working"]
        return working[-1] if working else matches[-1]

    def all_version_records(
        self, version: str, block_id: str
    ) -> list[VersionBlockEntry]:
        idx = self.load_version_index(version)
        return [b for b in idx.blocks if b.id == block_id]

    @staticmethod
    def _compute_stats(idx: VersionIndex) -> VersionIndexStats:
        by_action: dict[str, int] = {}
        by_state: dict[str, int] = {}
        for b in idx.blocks:
            by_action[b.action] = by_action.get(b.action, 0) + 1
            by_state[b.state] = by_state.get(b.state, 0) + 1
        return VersionIndexStats(
            total_blocks=len(idx.blocks),
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
