"""AI context assembler — MVP L1+L2 only.

Per project-docs/docs/prd/overview.md (simplified):
    L1: target chunk content (mandatory, never trimmed)
    L2: chunks reachable via @ref (implements, see-also, etc.)
    L3/L4 are placeholders — interfaces present, content empty in MVP.

Scenarios:
    "prd-to-impl"  — generating impl from a PRD chunk
    "impl-edit"    — editing an impl chunk (rare in MVP; mainly for completeness)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .chunk_parser import parse_file
from .index_manager import IndexManager
from .version_manager import VersionManager

Scenario = Literal["prd-to-impl", "impl-edit"]


@dataclass
class ContextSlice:
    id: str
    file: str
    heading: str
    level: int
    content: str
    source: Literal["baseline", "version"]


@dataclass
class AssembledContext:
    scenario: Scenario
    target_id: str
    l1: ContextSlice
    l2: list[ContextSlice] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario,
            "target_id": self.target_id,
            "l1": _slice_dict(self.l1),
            "l2": [_slice_dict(s) for s in self.l2],
            "notes": list(self.notes),
        }


def _slice_dict(s: ContextSlice) -> dict:
    return {
        "id": s.id,
        "file": s.file,
        "heading": s.heading,
        "level": s.level,
        "content": s.content,
        "source": s.source,
    }


class ContextAssembler:
    def __init__(self, project_root: Path):
        self.root = project_root.resolve()
        self.indexes = IndexManager(self.root)
        self.versions = VersionManager(self.root)

    def assemble(
        self,
        target_id: str,
        scenario: Scenario,
        *,
        focus: bool = False,
        include_deps: bool = False,
    ) -> AssembledContext:
        l1 = self._locate_chunk(target_id)
        if l1 is None:
            raise FileNotFoundError(
                f"target chunk {target_id} not found in baseline or current version"
            )
        l2: list[ContextSlice] = []
        notes: list[str] = []

        if focus:
            notes.append("focus=true: only L1 target chunk returned")
            return AssembledContext(
                scenario=scenario, target_id=target_id, l1=l1, l2=l2, notes=notes
            )

        if include_deps:
            l2.extend(self._deps_related_to_chunk(target_id))
            notes.append("deps=true: L2 populated from SpecGraph dependencies")
        elif scenario == "prd-to-impl":
            l2.extend(self._impl_related_to_prd(target_id))
        elif scenario == "impl-edit":
            l2.extend(self._prd_related_to_impl(target_id))

        return AssembledContext(
            scenario=scenario, target_id=target_id, l1=l1, l2=l2, notes=notes
        )

    # ──────────────────────────────────────────────────
    # Lookup helpers
    # ──────────────────────────────────────────────────

    def _locate_chunk(self, chunk_id: str) -> ContextSlice | None:
        version = self.versions.current()
        if version:
            v_entry = self.indexes.query_version(version, chunk_id)
            if v_entry and v_entry.file:
                path = (
                    self.versions.versions_dir / version / f"{v_entry.file}.md"
                )
                slice_ = self._read_chunk_from(path, chunk_id, "version")
                if slice_:
                    return slice_
        base_entry = self.indexes.query_baseline(chunk_id)
        if base_entry:
            path = self.root / "docs" / f"{base_entry.file}.md"
            return self._read_chunk_from(path, chunk_id, "baseline")
        return None

    def _read_chunk_from(
        self, path: Path, chunk_id: str, source: Literal["baseline", "version"]
    ) -> ContextSlice | None:
        if not path.exists():
            return None
        base_dir = path.parents[1] if source == "version" else self.root / "docs"
        try:
            parsed = parse_file(path, base_dir)
        except Exception:
            return None
        for chunk in parsed.chunks:
            if chunk.id == chunk_id:
                return ContextSlice(
                    id=chunk.id,
                    file=chunk.file,
                    heading=chunk.heading,
                    level=chunk.level,
                    content=chunk.content,
                    source=source,
                )
        return None

    # ─────────────────────────────────────────────────────
    # Scenario-specific L2 lookups
    # ─────────────────────────────────────────────────────

    def _impl_related_to_prd(self, prd_id: str) -> list[ContextSlice]:
        """For PRD→impl: include existing impl chunks that implement this PRD as patterns."""
        from .specgraph import combined_specgraph, resolve_chunk_uri

        out: list[ContextSlice] = []
        version = self.versions.current()
        graph = combined_specgraph(self.root, version)
        prd_uri = resolve_chunk_uri(self.root, prd_id, version, graph=graph)
        seen: set[str] = set()
        for edge in graph.implementations(prd_uri):  # impl --implements--> prd (in edges)
            source_chunk_id = edge.src.split(":", 3)[-1]
            if source_chunk_id in seen:
                continue
            slice_ = self._locate_chunk(source_chunk_id)
            if slice_:
                out.append(slice_)
                seen.add(source_chunk_id)
        return out

    def _deps_related_to_chunk(self, chunk_id: str) -> list[ContextSlice]:
        """Include chunks connected by outgoing SpecGraph dependencies."""
        from .specgraph import combined_specgraph, resolve_chunk_uri

        version = self.versions.current()
        graph = combined_specgraph(self.root, version)
        uri = resolve_chunk_uri(self.root, chunk_id, version, graph=graph)
        out: list[ContextSlice] = []
        seen: set[str] = set()
        for edge in graph.dependencies(uri):
            target_chunk_id = edge.dst.split(":", 3)[-1]
            if target_chunk_id in seen:
                continue
            slice_ = self._locate_chunk(target_chunk_id)
            if slice_:
                out.append(slice_)
                seen.add(target_chunk_id)
        return out

    def _prd_related_to_impl(self, impl_id: str) -> list[ContextSlice]:
        """For impl-edit: include the PRD chunk(s) this impl implements."""
        out: list[ContextSlice] = []
        version = self.versions.current()
        # Search refs in version file first, then baseline files.
        candidates: list[Path] = []
        if version:
            entry = self.indexes.query_version(version, impl_id)
            if entry and entry.file:
                candidates.append(
                    self.versions.versions_dir / version / f"{entry.file}.md"
                )
        base_entry = self.indexes.query_baseline(impl_id)
        if base_entry:
            candidates.append(self.root / "docs" / f"{base_entry.file}.md")

        for path in candidates:
            if not path.exists():
                continue
            base_dir = (
                self.versions.versions_dir / version
                if version and path.is_relative_to(self.versions.versions_dir)
                else self.root / "docs"
            )
            parsed = parse_file(path, base_dir)
            for ref in parsed.refs:
                if ref.source_chunk_id != impl_id:
                    continue
                if ref.rel != "implements":
                    continue
                slice_ = self._locate_chunk(ref.target_chunk_id)
                if slice_:
                    out.append(slice_)
            if out:
                break
        return out
