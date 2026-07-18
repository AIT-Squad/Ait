"""graph_md.py — Reingold-Tilford tree layout for the AIT spec-graph.

Parents are centred above their children.  Same-depth nodes share the same
y-coordinate.  Node shape encodes type: PRD=rect, FSD=rounded-rect,
TDD=pill.  Tree edges use solid elbow arrows; depends_on uses dashed lines.

Output paths:
  baseline  →  <project-docs>/docs/graph.html
  version v →  <project-docs>/versions/<v>/graph.html
"""
from __future__ import annotations

from collections import defaultdict, deque
from html import escape as he
from pathlib import Path

# ── Layout constants ──────────────────────────────────────────────────────────
NODE_W  = 160
NODE_H  = 36
H_GAP   = 32    # horizontal gap between sibling subtrees
V_GAP   = 70    # vertical gap between depth levels
MARGIN  = 40    # canvas margin

BG          = "#f6f6f6"
DOT_COL     = "#cccccc"
NODE_FILL   = "#ffffff"
BORDER_PRD  = "#333333"
BORDER_FSD  = "#222222"
BORDER_TDD  = "#555555"
EDGE_COL    = "#333333"
DEP_COL     = "#999999"

TREE_RELS = frozenset({"derives", "decomposes", "details"})


# ── Tree layout (Reingold-Tilford-lite) ───────────────────────────────────────

def _build_tree(edges):
    """Return (tree_children, tree_parents, dep_edges, all_nodes)."""
    ch: dict[str, list] = defaultdict(list)
    par: dict[str, str] = {}
    dep: list[tuple] = []
    nodes: set = set()
    for src, rel, dst in edges:
        nodes.add(src); nodes.add(dst)
        if rel in TREE_RELS:
            ch[src].append(dst)
            par[dst] = src
        elif rel == "depends_on":
            dep.append((src, dst))
    return dict(ch), par, dep, nodes


def _assign_x(node: str, ch: dict, x_slots: dict, slot_w: float, gap: float) -> float:
    """Recursively assign x (centre) for each node.  Returns subtree width."""
    kids = ch.get(node, [])
    if not kids:
        x_slots[node] = 0.0          # relative; absolute set later
        return slot_w

    widths = [_assign_x(k, ch, x_slots, slot_w, gap) for k in kids]
    total = sum(widths) + gap * (len(kids) - 1)

    # position each child relative to left edge of this subtree
    offset = 0.0
    for k, w in zip(kids, widths):
        x_slots[k] += offset          # shift child subtree right
        offset += w + gap

    # parent centred above children
    left  = x_slots[kids[0]]
    right = x_slots[kids[-1]]
    x_slots[node] = (left + right) / 2
    return total


def _layout(nodes: set, edges: list, ch: dict, par: dict) -> dict[str, tuple[float, float]]:
    """Return pos[cid] = (abs_x_centre, abs_y_centre)."""
    # BFS depth
    depth: dict[str, int] = {}
    roots = sorted(nodes - par.keys())
    q: deque = deque()
    for r in roots:
        depth[r] = 0; q.append(r)
    while q:
        n = q.popleft()
        for c in ch.get(n, []):
            if c not in depth:
                depth[c] = depth[n] + 1; q.append(c)
    for n in nodes:
        if n not in depth:
            if "[PRD]" in n:       depth[n] = 0
            elif "[TDD]" in n:     depth[n] = 3
            elif ":" in n:         depth[n] = 2
            else:                  depth[n] = 1

    slot_w = NODE_W + H_GAP
    x_slots: dict[str, float] = {n: 0.0 for n in nodes}

    # layout each root's subtree, then place side by side
    total_offset = 0.0
    for r in roots:
        w = _assign_x(r, ch, x_slots, slot_w, H_GAP)
        # shift all nodes in this subtree
        subtree = _subtree_nodes(r, ch)
        for n in subtree:
            x_slots[n] += total_offset
        total_offset += w + H_GAP * 2

    pos = {}
    for n in nodes:
        ax = MARGIN + x_slots[n] + NODE_W / 2
        ay = MARGIN + depth[n] * (NODE_H + V_GAP) + NODE_H / 2
        pos[n] = (ax, ay)
    return pos


def _subtree_nodes(root: str, ch: dict) -> set:
    visited, stack = set(), [root]
    while stack:
        n = stack.pop()
        if n in visited: continue
        visited.add(n); stack.extend(ch.get(n, []))
    return visited


# ── SVG rendering ─────────────────────────────────────────────────────────────

def _node_attrs(node_key: str) -> tuple[float, str, str]:
    """Return (rx, stroke_color, stroke_width) for the node rect."""
    if node_key.startswith("prd/") or node_key.startswith("[PRD]"):
        return 3.0, BORDER_PRD, "1.5"
    if node_key.startswith("tdd/") or node_key.startswith("[TDD]"):
        return NODE_H / 2, BORDER_TDD, "1.5"
    if node_key.startswith("fsd/") or node_key.startswith("[FSD]"):
        return 8.0, BORDER_FSD, "2"
    return 6.0, BORDER_PRD, "1.5"


def _dot_grid(W: int, H: int) -> str:
    lines = []
    step = 24
    for x in range(0, W + step, step):
        for y in range(0, H + step, step):
            lines.append(f'<circle cx="{x}" cy="{y}" r="1" fill="{DOT_COL}"/>')
    return "\n".join(lines)


def _arrowhead_marker() -> str:
    return (
        '<marker id="arr" markerWidth="8" markerHeight="6"'
        ' refX="7" refY="3" orient="auto">'
        f'<polygon points="0 0,8 3,0 6" fill="{EDGE_COL}"/></marker>'
        '<marker id="arrd" markerWidth="8" markerHeight="6"'
        ' refX="7" refY="3" orient="auto">'
        f'<polygon points="0 0,8 3,0 6" fill="{DEP_COL}"/></marker>'
    )


def _tree_edge_svg(p1, p2, rel: str) -> str:
    x1, y1 = p1[0], p1[1] + NODE_H / 2    # parent bottom-center
    x2, y2 = p2[0], p2[1] - NODE_H / 2    # child top-center
    mid = (y1 + y2) / 2
    if abs(x1 - x2) < 1:
        d = f"M{x1:.1f},{y1:.1f} L{x2:.1f},{y2:.1f}"
    else:
        d = (f"M{x1:.1f},{y1:.1f} L{x1:.1f},{mid:.1f}"
             f" L{x2:.1f},{mid:.1f} L{x2:.1f},{y2:.1f}")
    return (f'<path d="{d}" fill="none" stroke="{EDGE_COL}"'
            f' stroke-width="1.5" marker-end="url(#arr)">'
            f'<title>{rel}</title></path>')


def _dep_edge_svg(p1, p2, drop: float) -> str:
    x1, y1 = p1[0], p1[1] + NODE_H / 2
    x2, y2 = p2[0], p2[1] + NODE_H / 2
    d = (f"M{x1:.1f},{y1:.1f} L{x1:.1f},{drop:.1f}"
         f" L{x2:.1f},{drop:.1f} L{x2:.1f},{y2:.1f}")
    return (f'<path d="{d}" fill="none" stroke="{DEP_COL}"'
            f' stroke-width="1" stroke-dasharray="5,3"'
            f' marker-end="url(#arrd)"/>')


def _render_svg(pos: dict, edges: list, dep_edges: list, W: int, H: int) -> str:
    p = []
    p.append(f'<svg xmlns="http://www.w3.org/2000/svg"'
             f' width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
    p.append(f'<defs>{_arrowhead_marker()}</defs>')
    p.append(f'<rect width="{W}" height="{H}" fill="{BG}"/>')
    p.append(_dot_grid(W, H))

    # depends_on edges (behind nodes)
    depth_bottom: dict[float, float] = {}
    for cid, (_, cy) in pos.items():
        lvl_y = cy - NODE_H / 2
        depth_bottom[lvl_y] = max(depth_bottom.get(lvl_y, 0.0), cy + NODE_H / 2)

    seen_dep: set = set()
    for src, dst in dep_edges:
        if src not in pos or dst not in pos:
            continue
        key = (min(src, dst), max(src, dst))
        if key in seen_dep:
            continue
        seen_dep.add(key)
        lvl_y = pos[src][1] - NODE_H / 2
        drop = depth_bottom.get(lvl_y, pos[src][1] + NODE_H / 2) + 12
        p.append(_dep_edge_svg(pos[src], pos[dst], drop))

    # tree edges
    for src, rel, dst in edges:
        if rel in TREE_RELS and src in pos and dst in pos:
            p.append(_tree_edge_svg(pos[src], pos[dst], rel))

    # nodes
    for node_key, (cx, cy) in pos.items():
        nx, ny = cx - NODE_W / 2, cy - NODE_H / 2
        rx, stroke, sw = _node_attrs(node_key)
        display = node_key.split("/")[-1]   # strip prd/ fsd/ tdd/ prefix
        if len(display) > 22:
            display = "…" + display[-21:]
        p.append(f'<rect x="{nx:.1f}" y="{ny:.1f}" width="{NODE_W}" height="{NODE_H}"'
                 f' rx="{rx}" fill="{NODE_FILL}" stroke="{stroke}" stroke-width="{sw}"/>')
        p.append(f'<text x="{cx:.1f}" y="{cy + 5:.1f}" text-anchor="middle"'
                 f' font-family="ui-monospace,monospace" font-size="12"'
                 f' fill="#222222">{he(display)}</text>')

    p.append('</svg>')
    return "\n".join(p)


# ── File-level graph builder ──────────────────────────────────────────────────

def _file_level_graph(
    raw_edges: list[tuple],
    nodes_by_cid: dict[str, str],
) -> tuple[list[tuple], set[str]]:
    """Aggregate chunk-level edges to file-level.

    Skips same-file edges (intra-file decompositions show as chunk details,
    not as file-level relationships).  Deduplicates (file_A, rel, file_B).
    """
    chunk_to_file = {cid: fk for cid, fk in nodes_by_cid.items() if fk}
    seen: set = set()
    file_edges: list = []
    all_files: set = set(chunk_to_file.values())

    for src, rel, dst in raw_edges:
        sf = chunk_to_file.get(src)
        df = chunk_to_file.get(dst)
        if not sf or not df or sf == df:
            continue
        key = (sf, rel, df)
        if key not in seen:
            seen.add(key)
            file_edges.append((sf, rel, df))

    return file_edges, all_files




def generate_graph_html(root: Path, version: str | None = None) -> str:
    """Build a self-contained HTML+SVG spec-tree string (file-level nodes)."""
    try:
        from .specgraph import combined_view, load_specgraph
    except ImportError:
        from ait.specgraph import combined_view, load_specgraph  # type: ignore

    if version is None:
        graph = load_specgraph(root, "baseline")

        def _cid(uri: str) -> str:
            s = graph.specs.get(uri)
            return s.chunk_id if s else uri

        raw_edges = [(_cid(e.src), e.rel, _cid(e.dst)) for e in graph.edges]
        nodes_by_cid: dict[str, str] = {s.chunk_id: s.file or ""
                                         for s in graph.specs.values()}
    else:
        view = combined_view(root, version)
        raw_edges = [(e.src, e.rel, e.dst) for e in view.edges]
        nodes_by_cid = {cid: (getattr(n, "file", "") or "")
                        for cid, n in view.nodes.items()}

    if not raw_edges and not nodes_by_cid:
        return ("<!DOCTYPE html>\n<html><body style='background:#f6f6f6;"
                "font-family:monospace'><h2>Spec Graph</h2>"
                "<p>(empty)</p></body></html>\n")

    # aggregate to file-level
    file_edges, all_files = _file_level_graph(raw_edges, nodes_by_cid)

    ch, par, dep_edges, edge_nodes = _build_tree(file_edges)
    all_files |= edge_nodes
    pos = _layout(all_files, file_edges, ch, par)

    if pos:
        W = int(max(cx + NODE_W / 2 + MARGIN for cx, _ in pos.values()))
        H = int(max(cy + NODE_H / 2 + MARGIN + 20 for _, cy in pos.values()))
    else:
        W, H = 400, 200

    svg = _render_svg(pos, file_edges, dep_edges, W, H)
    title = f"Spec Graph — {version}" if version else "Spec Graph (baseline)"
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        f'<title>{he(title)}</title>\n'
        '<style>body{margin:0;background:#f6f6f6;overflow:auto}'
        'h2{font-family:ui-monospace,monospace;color:#444;padding:10px 16px;'
        'margin:0;font-size:13px;border-bottom:1px solid #ddd}</style>\n'
        '</head>\n<body>\n'
        f'<h2>{he(title)}</h2>\n'
        f'{svg}\n'
        '</body>\n</html>\n'
    )


def write_graph_html(root: Path, version: str | None = None) -> dict:
    """Generate and atomically write graph.html to the fixed output path."""
    try:
        from .io_utils import atomic_write_text
    except ImportError:
        from ait.io_utils import atomic_write_text  # type: ignore

    content = generate_graph_html(root, version)
    out_path = (root / "docs" / "graph.html" if version is None
                else root / "versions" / version / "graph.html")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_path, content)

    node_count = content.count('font-size="12"')
    edge_count = content.count('marker-end=')

    return {
        "path": str(out_path.relative_to(root)).replace("\\", "/"),
        "nodes": node_count,
        "edges": edge_count,
    }


# backward-compat aliases (CLI references these names)
generate_graph_md = generate_graph_html
write_graph_md = write_graph_html



