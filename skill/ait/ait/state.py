"""Version state panel rendering for AIT."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .index_manager import IndexManager
from .io_utils import atomic_write_text
from .specgraph import combined_specgraph, sync_specgraph
from .version_manager import VersionManager, VersionManagerError


@dataclass
class StatePanel:
    version: str
    merged: bool
    title: str | None = None
    phase: str = "empty"
    prd_locked: bool = False
    impl_locked: bool = False
    working: list[str] = field(default_factory=list)
    staged: list[str] = field(default_factory=list)
    committed: list[str] = field(default_factory=list)
    by_action: dict[str, int] = field(default_factory=dict)
    prd_chunks: list[str] = field(default_factory=list)
    impl_chunks: list[str] = field(default_factory=list)
    impl_coverage: dict[str, list[str]] = field(default_factory=dict)
    tasks: list[dict] = field(default_factory=list)  # [{id,status,source_chunk}]

    def to_dict(self) -> dict:
        task_counts: dict[str, int] = {}
        for t in self.tasks:
            s = t.get("status", "created")
            task_counts[s] = task_counts.get(s, 0) + 1
        return {
            "version": self.version,
            "title": self.title,
            "phase": self.phase,
            "prd_locked": self.prd_locked,
            "impl_locked": self.impl_locked,
            "merged": self.merged,
            "working": self.working,
            "staged": self.staged,
            "committed": self.committed,
            "by_action": self.by_action,
            "prd_chunks": self.prd_chunks,
            "impl_chunks": self.impl_chunks,
            "impl_coverage": self.impl_coverage,
            "tasks": self.tasks,
            "counts": {
                "working": len(self.working),
                "staged": len(self.staged),
                "committed": len(self.committed),
                "prd": len(self.prd_chunks),
                "impl": len(self.impl_chunks),
                "covered_prd": len([v for v in self.impl_coverage.values() if v]),
                "tasks": task_counts,
            },
        }


def current_or_requested_version(project_root: Path, version: str | None) -> str:
    manager = VersionManager(project_root)
    if version:
        return version
    current = manager.current()
    if not current:
        raise VersionManagerError("No active version")
    return current


def load_version_state(project_root: Path, version: str | None = None) -> StatePanel:
    root = project_root.resolve()
    version_name = current_or_requested_version(root, version)
    indexes = IndexManager(root)
    manager = VersionManager(root)
    idx = indexes.load_version_index(version_name)
    meta = manager.load_version_meta(version_name)

    working = [entry.id for entry in idx.chunks if entry.state == "working"]
    staged = [entry.id for entry in idx.chunks if entry.state == "staged"]
    committed = [entry.id for entry in idx.chunks if entry.state == "committed"]
    by_action: dict[str, int] = {}
    prd_chunks: list[str] = []
    impl_chunks: list[str] = []
    for entry in idx.chunks:
        by_action[entry.action] = by_action.get(entry.action, 0) + 1
        if entry.id.startswith("prd-"):
            prd_chunks.append(entry.id)
        elif entry.id.startswith("impl-"):
            impl_chunks.append(entry.id)

    graph = combined_specgraph(root, version_name)
    if not graph.specs:
        sync_specgraph(root)
        graph = combined_specgraph(root, version_name)
    impl_coverage = compute_impl_coverage(graph, version_name, prd_chunks)
    tasks = _load_version_tasks(root, version_name)

    return StatePanel(
        version=version_name,
        title=meta.title,
        phase=meta.phase,
        prd_locked=meta.prd_locked,
        impl_locked=meta.impl_locked,
        merged=meta.merged_at is not None,
        working=working,
        staged=staged,
        committed=committed,
        by_action=by_action,
        prd_chunks=prd_chunks,
        impl_chunks=impl_chunks,
        impl_coverage=impl_coverage,
        tasks=tasks,
    )


def _load_version_tasks(project_root: Path, version: str) -> list[dict]:
    """Load task YAMLs from versions/{version}/tasks/ as lightweight dicts."""
    import yaml

    tasks_dir = project_root / "versions" / version / "tasks"
    if not tasks_dir.exists():
        return []
    out: list[dict] = []
    for path in sorted(tasks_dir.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        out.append({
            "id": raw.get("id", path.stem),
            "status": raw.get("status", "created"),
            "source_chunk": raw.get("source_chunk", ""),
            "title": raw.get("title", ""),
        })
    return out


def compute_impl_coverage(graph, version: str, prd_chunks: list[str]) -> dict[str, list[str]]:
    coverage: dict[str, list[str]] = {chunk_id: [] for chunk_id in prd_chunks}
    for edge in graph.edges:
        if edge.rel != "implements":
            continue
        dst_parts = edge.dst.split(":", 3)
        src_parts = edge.src.split(":", 3)
        if len(dst_parts) != 4 or len(src_parts) != 4:
            continue
        dst_version, dst_chunk = dst_parts[2], dst_parts[3]
        src_version, src_chunk = src_parts[2], src_parts[3]
        if dst_version == version and src_version == version and dst_chunk in coverage:
            coverage[dst_chunk].append(src_chunk)
    return coverage


def render_markdown(panel: StatePanel) -> str:
    """Render only the active version's execution progress and changed chunks."""
    lines = [
        f"# AIT State — {panel.version}",
        "",
        "## 当前执行阶段",
        "",
        f"- Phase: `{panel.phase}`",
        "",
        "## 当前版本 Chunk",
        "",
    ]
    for prefix, label in (("[PRD]-", "PRD"), ("[FSD]-", "FSD"), ("[TDD]-", "TDD")):
        lines += [f"### {label}", "", "| State | Count | Chunk IDs |", "|---|---:|---|"]
        for state_name, chunk_list in (
            ("working", panel.working),
            ("staged", panel.staged),
            ("committed", panel.committed),
        ):
            filtered = [c for c in chunk_list if c.startswith(prefix)]
            ids = ", ".join(f"`{c}`" for c in filtered) or "-"
            lines.append(f"| {state_name} | {len(filtered)} | {ids} |")
        lines.append("")

    lines.append("")
    return "\n".join(lines)


def save_state(project_root: Path, version: str | None = None) -> Path:
    panel = load_version_state(project_root, version)
    path = project_root / "versions" / panel.version / "state.md"
    atomic_write_text(path, render_markdown(panel))
    return path


def render_state(project_root: Path, version: str | None = None, *, fmt: str = "markdown") -> dict:
    panel = load_version_state(project_root, version)
    if fmt == "json":
        return panel.to_dict()
    return {"version": panel.version, "format": "markdown", "content": render_markdown(panel)}