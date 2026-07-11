"""Dependency queries on the combined chunk_id view."""

from __future__ import annotations

from pathlib import Path

from .specgraph import combined_view
from .version_manager import VersionManager


def query_deps(project_root: Path, target: str, *, direction: str = "both") -> dict:
    version = VersionManager(project_root).current()
    view = combined_view(project_root, version)
    if direction == "out":
        edges = view.edges_from(target)
    elif direction == "in":
        edges = view.edges_to(target)
    elif direction == "both":
        deduped: dict[tuple[str, str, str], object] = {}
        for edge in [*view.edges_from(target), *view.edges_to(target)]:
            deduped[(edge.src, edge.dst, edge.rel)] = edge
        edges = list(deduped.values())
    else:
        raise ValueError("direction must be one of: in, out, both")
    return {
        "target": target,
        "direction": direction,
        "edges": [edge.__dict__ for edge in edges],
    }
