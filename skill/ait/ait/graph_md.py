"""graph_md.py — Generate a Mermaid subgraph Markdown file from the specgraph.

Each chunk id becomes a Mermaid node.  Chunks that live in the same .md file
are grouped inside a ``subgraph "file"`` block.  Edges are annotated with the
relation type (derives / decomposes / details / depends_on).

Output paths are fixed:
  baseline  →  <project-docs>/docs/graph.md
  version v →  <project-docs>/versions/<v>/graph.md
"""

from __future__ import annotations

import re
from pathlib import Path


_ESCAPE = str.maketrans({
    "[": "",
    "]": "",
    ":": "__",
    "-": "_",
    ".": "_",
    "/": "_",
    " ": "_",
})


def _node_id(chunk_id: str) -> str:
    """Return a Mermaid-safe node identifier for *chunk_id*."""
    return chunk_id.translate(_ESCAPE) or "node"


def generate_graph_md(root: Path, version: str | None = None) -> str:
    """Build the Mermaid Markdown string from specgraph data.

    *version* = None  →  baseline specgraph only.
    *version* = "vX.Y"  →  combined_view(baseline ∪ version).
    """
    import sys
    sys.path.insert(0, str(root.parent / "skill" / "ait"))  # dev convenience
    try:
        from .specgraph import combined_view, load_specgraph
        from .io_utils import to_posix_rel
    except ImportError:
        from ait.specgraph import combined_view, load_specgraph  # type: ignore

    if version is None:
        graph = load_specgraph(root, "baseline")
        # Build file→[chunk_id] map from specs
        by_file: dict[str, list[str]] = {}
        for spec in graph.specs.values():
            if spec.file:
                by_file.setdefault(spec.file, []).append(spec.chunk_id)
        # edges
        def _cid(uri: str) -> str:
            s = graph.specs.get(uri)
            return s.chunk_id if s else uri
        edges = [(_cid(e.src), e.rel, _cid(e.dst)) for e in graph.edges]
    else:
        view = combined_view(root, version)
        by_file = {}
        for cid, node in view.nodes.items():
            f = getattr(node, "file", None) or ""
            by_file.setdefault(f, []).append(cid)
        edges = [(e.src, e.rel, e.dst) for e in view.edges]

    if not by_file and not edges:
        return "## Spec Graph\n\n```mermaid\ngraph TD\n```\n"

    lines: list[str] = ["## Spec Graph\n", "```mermaid", "graph TD"]

    # subgraph per file
    for file_key in sorted(by_file):
        chunk_ids = sorted(set(by_file[file_key]))
        label = file_key if file_key else "(no file)"
        lines.append(f'  subgraph "{label}"')
        for cid in chunk_ids:
            nid = _node_id(cid)
            lines.append(f'    {nid}["{cid}"]')
        lines.append("  end")

    lines.append("")

    # edges (deduplicate)
    seen_edges: set[tuple[str, str, str]] = set()
    for src, rel, dst in edges:
        key = (src, rel, dst)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        lines.append(f"  {_node_id(src)} -->|{rel}| {_node_id(dst)}")

    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def write_graph_md(root: Path, version: str | None = None) -> dict:
    """Generate and atomically write graph.md to the fixed output path.

    Returns ``{path, nodes, edges}`` statistics.
    """
    try:
        from .io_utils import atomic_write_text
    except ImportError:
        from ait.io_utils import atomic_write_text  # type: ignore

    content = generate_graph_md(root, version)

    if version is None:
        out_path = root / "docs" / "graph.md"
    else:
        out_path = root / "versions" / version / "graph.md"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_path, content)

    # count nodes and edges from content
    node_count = content.count('["')
    edge_count = content.count("-->|")

    return {
        "path": str(out_path.relative_to(root)).replace("\\", "/"),
        "nodes": node_count,
        "edges": edge_count,
    }
