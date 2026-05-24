"""AI context assembler — MVP L1+L2 only.

Per project-docs/docs/prd/overview.md (simplified):
    L1: target block content (mandatory, never trimmed)
    L2: blocks reachable via @ref (implements, see-also, etc.)
    L3/L4 are placeholders — interfaces present, content empty in MVP.

Scenarios:
    "prd-to-impl"  — generating impl from a PRD block
    "impl-edit"    — editing an impl block (rare in MVP; mainly for completeness)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .block_parser import parse_file
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

    def assemble(self, target_id: str, scenario: Scenario) -> AssembledContext:
        l1 = self._locate_block(target_id)
        if l1 is None:
            raise FileNotFoundError(
                f"target block {target_id} not found in baseline or current version"
            )
        l2: list[ContextSlice] = []

        if scenario == "prd-to-impl":
            l2.extend(self._impl_related_to_prd(target_id))
        elif scenario == "impl-edit":
            l2.extend(self._prd_related_to_impl(target_id))

        return AssembledContext(
            scenario=scenario, target_id=target_id, l1=l1, l2=l2
        )

    # ─────────────────────────────────────────────────────
    # Lookup helpers
    # ─────────────────────────────────────────────────────

    def _locate_block(self, block_id: str) -> ContextSlice | None:
        version = self.versions.current()
        if version:
            v_entry = self.indexes.query_version(version, block_id)
            if v_entry and v_entry.file:
                path = (
                    self.versions.versions_dir / version / f"{v_entry.file}.md"
                )
                slice_ = self._read_block_from(path, block_id, "version")
                if slice_:
                    return slice_
        base_entry = self.indexes.query_baseline(block_id)
        if base_entry:
            path = self.root / "docs" / f"{base_entry.file}.md"
            return self._read_block_from(path, block_id, "baseline")
        return None

    def _read_block_from(
        self, path: Path, block_id: str, source: Literal["baseline", "version"]
    ) -> ContextSlice | None:
        if not path.exists():
            return None
        base_dir = path.parents[1] if source == "version" else self.root / "docs"
        try:
            parsed = parse_file(path, base_dir)
        except Exception:
            return None
        for block in parsed.blocks:
            if block.id == block_id:
                return ContextSlice(
                    id=block.id,
                    file=block.file,
                    heading=block.heading,
                    level=block.level,
                    content=block.content,
                    source=source,
                )
        return None

    # ─────────────────────────────────────────────────────
    # Scenario-specific L2 lookups
    # ─────────────────────────────────────────────────────

    def _impl_related_to_prd(self, prd_id: str) -> list[ContextSlice]:
        """For PRD→impl: include existing impl blocks that implement this PRD as patterns."""
        out: list[ContextSlice] = []
        links = self.indexes.load_links()
        for link in links.links:
            if not link.to.endswith(f"#{prd_id}"):
                continue
            if link.rel != "implements":
                continue
            source_block_id = link.from_.split("#", 1)[1]
            slice_ = self._locate_block(source_block_id)
            if slice_:
                out.append(slice_)
        return out

    def _prd_related_to_impl(self, impl_id: str) -> list[ContextSlice]:
        """For impl-edit: include the PRD block(s) this impl implements."""
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
                if ref.source_block_id != impl_id:
                    continue
                if ref.rel != "implements":
                    continue
                slice_ = self._locate_block(ref.target_block_id)
                if slice_:
                    out.append(slice_)
            if out:
                break
        return out
