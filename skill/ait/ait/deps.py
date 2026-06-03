"""Dependency queries backed by SpecGraph."""

from __future__ import annotations

from pathlib import Path

from .specgraph import combined_specgraph, resolve_chunk_uri
from .version_manager import VersionManager


def query_deps(project_root: Path, target: str, *, direction: str = "both") -> dict:
    version = VersionManager(project_root).current()
    graph = combined_specgraph(project_root, version)
    uri = resolve_chunk_uri(project_root, target, version, graph=graph)
    edges = graph.query(uri, direction=direction)
    return {
        "target": uri,
        "direction": direction,
        "edges": [edge.__dict__ for edge in edges],
    }