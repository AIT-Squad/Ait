"""Impact analysis backed by SpecGraph reverse dependencies."""

from __future__ import annotations

from pathlib import Path

from .specgraph import combined_specgraph, resolve_chunk_uri
from .version_manager import VersionManager


def analyze_impact(project_root: Path, target: str) -> dict:
    version = VersionManager(project_root).current()
    graph = combined_specgraph(project_root, version)
    uri = resolve_chunk_uri(project_root, target, version, graph=graph)
    impacted = graph.impacted(uri)
    return {
        "target": uri,
        "impacted": impacted,
        "count": len(impacted),
    }