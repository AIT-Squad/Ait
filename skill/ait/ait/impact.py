"""Impact analysis on the combined chunk_id view.

Forward decomposes/details (spec-tree downstream) + reverse
depends_on/implements (dependents) — the traversal that powers the
iteration flow "沿既有 chunk 关联逐层向下改".
"""

from __future__ import annotations

from pathlib import Path

from .specgraph import combined_view
from .version_manager import VersionManager


def analyze_impact(project_root: Path, target: str) -> dict:
    version = VersionManager(project_root).current()
    view = combined_view(project_root, version)
    if view.node(target) is None:
        return {"target": target, "impacted": [], "count": 0, "found": False}
    impacted = view.impacted(target)
    return {
        "target": target,
        "impacted": impacted,
        "count": len(impacted),
        "found": True,
    }
