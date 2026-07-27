"""graph_md.py — chunk-level spec-tree with per-file subgraph boxes.

v2.63 renderer:
- Nodes are chunks, not file aggregates.  Every file becomes a coloured
  subgraph box that holds its chunks as a tree-indented list (root chunk
  first, ``:split`` chunks below it) — one box == one FSD file.
- Cross-file tree edges (derives/decomposes/details) draw with a visible rel
  label; cross-file depends_on edges are dashed curves (hover for detail).
- Two-pass "subgraph" layout: the file forest is laid out first
  (Reingold-Tilford-lite), then each box stacks its own chunks.
- No fixed canvas: the SVG fills the viewport and supports wheel-zoom,
  drag-pan and an initial fit-to-view.

Output paths:
  baseline  →  <project-docs>/docs/graph.html
  version v →  <project-docs>/versions/<v>/graph.html
"""
from __future__ import annotations

from collections import defaultdict, deque
from html import escape as he
from pathlib import Path

# ── Layout constants ──────────────────────────────────────────────────────────
BOX_W   = 230   # subgraph box width
TITLE_H = 26    # box title-bar height
ROW_H   = 26    # chunk row height inside a box
BOX_PAD = 8     # box bottom padding
INDENT  = 14    # per-depth indent of split rows
H_GAP   = 70    # horizontal gap between sibling boxes
V_GAP   = 80    # vertical gap between depth levels
MARGIN  = 40    # canvas margin

BG       = "#f6f6f6"
ROW_FILL = "#ffffff"
ROW_LINE = "#d4d4d4"
EDGE_COL = "#44607a"
DEP_COL  = "#999999"
TEXT_COL = "#222222"
REL_COL  = "#667788"

# box palette per dominant chunk type: (fill, stroke, title-colour)
PALETTE = {
    "prd":  ("#f2f2f2", "#666666", "#e2e2e2"),
    "fsd":  ("#eaf2fc", "#4a90d9", "#d6e6f8"),
    "tdd":  ("#ecf7ef", "#52a871", "#d9efe1"),
    "impl": ("#f3eef9", "#8e6bbf", "#e8ddf5"),
    "misc": ("#fbf6e9", "#c9a227", "#f4ead0"),
}

TREE_RELS = frozenset({"derives", "decomposes", "details"})

MAX_LABEL = 32


# ── Chunk graph building ──────────────────────────────────────────────────────

def _chunk_type(cid: str) -> str:
    if cid.startswith("[PRD]"):
        return "prd"
    if cid.startswith("[FSD]"):
        return "fsd"
    if cid.startswith("[TDD]"):
        return "tdd"
    if cid.startswith("[IMPL]"):
        return "impl"
    return "misc"


def _build_chunk_graph(
    nodes_by_cid: dict[str, str],
    raw_edges: list[tuple[str, str, str]],
) -> tuple[dict[str, str], list[tuple], list[tuple], dict[str, list[str]], dict[str, list[str]]]:
    """Return (chunks cid→file, cross_tree, cross_dep, files file→[cids], dep_map).

    Same-file tree edges are not drawn: the box already expresses containment.
    All depends_on targets are collected in dep_map (src → [dst]) so in-box
    rows can annotate them; cross-file depends_on additionally draws a dashed
    edge.
    """
    chunks: dict[str, str] = {}
    for cid, f in nodes_by_cid.items():
        chunks[cid] = f or cid
    for src, _rel, dst in raw_edges:
        chunks.setdefault(src, src)
        chunks.setdefault(dst, dst)

    cross_tree: list[tuple] = []
    cross_dep: list[tuple] = []
    dep_map: dict[str, list[str]] = defaultdict(list)
    seen_tree: set = set()
    seen_dep: set = set()
    for src, rel, dst in raw_edges:
        if rel in TREE_RELS:
            if chunks[src] == chunks[dst]:
                continue
            key = (src, rel, dst)
            if key not in seen_tree:
                seen_tree.add(key)
                cross_tree.append((src, rel, dst))
        elif rel == "depends_on":
            key = (src, dst)
            if key in seen_dep:
                continue
            seen_dep.add(key)
            dep_map[src].append(dst)
            if chunks[src] != chunks[dst]:
                cross_dep.append((src, dst))

    files: dict[str, list[str]] = defaultdict(list)
    for cid, f in chunks.items():
        files[f].append(cid)
    return chunks, cross_tree, cross_dep, dict(files), {
        k: sorted(v) for k, v in dep_map.items()
    }


# ── Box-internal ordering (root first, splits as a tree) ─────────────────────

def _file_rows(cids: list[str]) -> list[tuple[str, int]]:
    """Order a file's chunks as (cid, depth) rows: roots, then split subtree."""
    cid_set = set(cids)
    children: dict[str, list[str]] = defaultdict(list)
    roots: list[str] = []
    for cid in cids:
        if ":" not in cid:
            roots.append(cid)
        else:
            parent = cid.rsplit(":", 1)[0]
            children[parent].append(cid)

    rows: list[tuple[str, int]] = []

    def _emit(cid: str, depth: int) -> None:
        rows.append((cid, depth))
        for kid in sorted(children.get(cid, [])):
            _emit(kid, depth + 1)

    for r in sorted(roots):
        _emit(r, 0)
    # orphan splits whose parent lives outside this file (defensive)
    for cid in sorted(c for c in cids if c not in {r for r, _ in rows}):
        if cid in cid_set:
            _emit(cid, max(1, cid.count(":")))
    return rows


# ── File-forest layout (subgraph pass) ────────────────────────────────────────

def _file_tree_edges(
    cross_tree: list[tuple],
    chunks: dict[str, str],
) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Project chunk tree edges onto file-level parent/children maps."""
    ch: dict[str, list[str]] = defaultdict(list)
    par: dict[str, str] = {}
    seen: set = set()
    for src, _rel, dst in cross_tree:
        fs, fd = chunks[src], chunks[dst]
        if fs == fd or (fs, fd) in seen:
            continue
        seen.add((fs, fd))
        # The renderer keeps every chunk-level edge, but file layout is a
        # forest. A file with several incoming chunk relations therefore uses
        # its first stable parent for placement only; retaining it under every
        # parent makes `_assign_x` visit the same TDD subtree repeatedly and
        # causes the wide/overlapping TDD layout seen in large graphs.
        if fd in par:
            continue
        par[fd] = fs
        ch[fs].append(fd)
    for f in ch:
        ch[f].sort()
    return dict(ch), par


def _assign_x(node: str, ch: dict, x_slots: dict, slot_w: float, gap: float) -> float:
    kids = ch.get(node, [])
    if not kids:
        x_slots.setdefault(node, 0.0)
        return slot_w
    widths = [_assign_x(k, ch, x_slots, slot_w, gap) for k in kids]
    total = sum(widths) + gap * (len(kids) - 1)
    cursor = 0.0
    for k, w in zip(kids, widths):
        # Align the child's subtree LEFT EDGE to the cursor. Shifting by
        # ``offset - root_x`` misplaces subtrees whose recursive layout no
        # longer starts at 0 (coordinates go negative and siblings collide).
        subtree = _subtree_nodes(k, ch)
        left = min(x_slots.get(n, 0.0) for n in subtree)
        shift = cursor - left
        for n in subtree:
            x_slots[n] = x_slots.get(n, 0.0) + shift
        cursor += w + gap
    x_slots[node] = (x_slots[kids[0]] + x_slots[kids[-1]]) / 2
    return total


def _subtree_nodes(root: str, ch: dict) -> set:
    visited, stack = set(), [root]
    while stack:
        n = stack.pop()
        if n in visited:
            continue
        visited.add(n)
        stack.extend(ch.get(n, []))
    return visited


def _layout(
    files: dict[str, list[str]],
    chunks: dict[str, str],
    cross_tree: list[tuple],
) -> tuple[dict[str, tuple], dict[str, dict[str, tuple]]]:
    """Tidy-tree layout: leaves spread left-to-right, parents centred above.

    Every file box gets its own horizontal slot so sibling TDD boxes never
    share coordinates and each FSD sits directly over its TDD children —
    keeping FSD→TDD connectors independent of one another instead of stacked
    on shared vertical lines. Combined with zoom/pan, a wide graph stays
    readable: the user pans sideways rather than decoding a wrapped grid.
    """
    rows_by_file = {f: _file_rows(cids) for f, cids in files.items()}
    box_h = {f: TITLE_H + len(rows_by_file[f]) * ROW_H + BOX_PAD for f in files}
    children, parents = _file_tree_edges(cross_tree, chunks)

    depth: dict[str, int] = {}
    roots = sorted(set(files) - set(parents))
    queue: deque[str] = deque(roots)
    for root in roots:
        depth[root] = 0
    while queue:
        parent = queue.popleft()
        for child in children.get(parent, []):
            if child not in depth:
                depth[child] = depth[parent] + 1
                queue.append(child)
    for f, cids in files.items():
        if f not in depth:
            types = {_chunk_type(cid) for cid in cids}
            depth[f] = 0 if "prd" in types else 3 if "tdd" in types else 1

    slot_w = BOX_W + H_GAP
    x_slots: dict[str, float] = {}
    total_offset = 0.0
    laid_out: set[str] = set()
    for root in roots:
        width = _assign_x(root, children, x_slots, slot_w, H_GAP)
        for node in _subtree_nodes(root, children):
            x_slots[node] = x_slots.get(node, 0.0) + total_offset
        laid_out |= _subtree_nodes(root, children)
        total_offset += width + H_GAP
    for f in sorted(files):
        if f not in laid_out:
            x_slots[f] = total_offset
            total_offset += slot_w

    # Normalize so the leftmost box starts at the margin.
    min_x = min(x_slots.values()) if x_slots else 0.0
    if min_x < 0:
        x_slots = {f: x - min_x for f, x in x_slots.items()}

    max_h: dict[int, int] = defaultdict(int)
    for f, d in depth.items():
        max_h[d] = max(max_h[d], box_h[f])
    # The gap below each level doubles as a routing bus: it must be tall
    # enough for one labelled lane per outgoing tree edge of the busiest
    # file on that level, so FSD files with many TDD children get their
    # own per-edge lanes instead of overlapping text.
    bus_out: dict[str, int] = defaultdict(int)
    for src, _rel, _dst in cross_tree:
        bus_out[chunks[src]] += 1
    gap_below: dict[int, int] = defaultdict(lambda: V_GAP)
    for f, n in bus_out.items():
        gap_below[depth[f]] = max(gap_below[depth[f]], 24 + n * 16)
    y_at: dict[int, float] = {}
    acc = float(MARGIN)
    for d in sorted(max_h):
        y_at[d] = acc
        acc += max_h[d] + gap_below[d]

    box_pos: dict[str, tuple] = {}
    row_pos: dict[str, dict[str, tuple]] = {}
    for f in files:
        bx = MARGIN + x_slots[f]
        by = y_at[depth[f]]
        box_pos[f] = (bx, by, BOX_W, box_h[f])
        row_pos[f] = {
            cid: (bx + BOX_W / 2, by + TITLE_H + i * ROW_H + ROW_H / 2)
            for i, (cid, _depth) in enumerate(rows_by_file[f])
        }

    return box_pos, row_pos


def _subtree_all(roots: list[str], ch: dict) -> set:
    out: set = set()
    for r in roots:
        out |= _subtree_nodes(r, ch)
    return out


# ── SVG rendering ─────────────────────────────────────────────────────────────

def _clip(text: str, limit: int = MAX_LABEL) -> str:
    return text if len(text) <= limit else "…" + text[-(limit - 1):]


def _markers() -> str:
    return (
        f'<marker id="arr" markerWidth="8" markerHeight="6" refX="7" refY="3"'
        f' orient="auto"><polygon points="0 0,8 3,0 6" fill="{EDGE_COL}"/></marker>'
        f'<marker id="arrd" markerWidth="8" markerHeight="6" refX="7" refY="3"'
        f' orient="auto"><polygon points="0 0,8 3,0 6" fill="{DEP_COL}"/></marker>'
    )


def _edge_chunk_label(cid: str) -> str:
    """Keep a visible edge annotation tied to chunk IDs rather than files."""
    if ":" in cid:
        root, split = cid.rsplit(":", 1)
        return f"{_clip(root, 22)}:{split}"
    return _clip(cid, 26)


def _tree_edge_svg(
    exit_x: float,
    src_boundary: float,
    bus_y: float,
    entry_x: float,
    dst_boundary: float,
    rel: str,
    src: str,
    dst: str,
    going_down: bool,
    label_shift: float = 0,
) -> str:
    """Orthogonal bus-routed edge: out of the source box boundary, across a
    dedicated lane in the inter-row gap, into the target box boundary.

    The horizontal segment lives in the gap between rows (never inside any
    box), so sibling boxes can never look connected to each other.
    """
    d = (
        f"M{exit_x:.1f},{src_boundary:.1f} L{exit_x:.1f},{bus_y:.1f} "
        f"L{entry_x:.1f},{bus_y:.1f} L{entry_x:.1f},{dst_boundary:.1f}"
    )
    chunk_label = f"{_edge_chunk_label(src)} → {_edge_chunk_label(dst)}"
    title = f"{rel}: {src} → {dst}"
    label_y = bus_y - 4 + label_shift if going_down else bus_y + 14 + label_shift
    halo = f'paint-order="stroke" stroke="{BG}" stroke-width="3"'
    return (
        f'<g class="tree-edge" data-src="{he(src)}" data-dst="{he(dst)}" data-rel="{he(rel)}">'
        f'<path d="{d}" fill="none" stroke="{EDGE_COL}" stroke-width="1.5"'
        f' marker-end="url(#arr)"><title>{he(title)}</title></path>'
        f'<text class="edge-rel" x="{entry_x - 6:.1f}" y="{label_y:.1f}"'
        f' text-anchor="end" font-family="ui-monospace,monospace" font-size="10"'
        f' font-weight="bold" fill="{REL_COL}" {halo}>{he(rel)}</text>'
        f'<text class="edge-chunks" x="{entry_x + 6:.1f}" y="{label_y:.1f}"'
        f' text-anchor="start" font-family="ui-monospace,monospace" font-size="9"'
        f' fill="{REL_COL}" {halo}>{he(chunk_label)}</text></g>'
    )


def _dep_edge_svg(sx, sy, dx, dy, src: str, dst: str) -> str:
    d = (f"M{sx:.1f},{sy:.1f} C{sx - 34:.1f},{sy:.1f} "
         f"{dx - 34:.1f},{dy:.1f} {dx:.1f},{dy:.1f}")
    return (
        f'<path d="{d}" fill="none" stroke="{DEP_COL}" stroke-width="1"'
        f' stroke-dasharray="5,3" marker-end="url(#arrd)">'
        f'<title>depends_on: {he(src)} → {he(dst)}</title></path>'
    )


def _dep_note(cid: str, dep_map: dict[str, list[str]]) -> str:
    """Short in-row annotation of a chunk's depends_on targets."""
    dsts = dep_map.get(cid)
    if not dsts:
        return ""
    names = [":" + d.rsplit(":", 1)[1] if ":" in d else _clip(d, 14) for d in dsts]
    note = "⇢ " + ",".join(names[:2])
    if len(dsts) > 2:
        note += f" +{len(dsts) - 2}"
    return _clip(note, 26)


def _box_svg(
    f: str,
    pos: tuple,
    rows: list[tuple[str, int]],
    rpos: dict[str, tuple],
    dep_map: dict[str, list[str]],
) -> str:
    bx, by, bw, bh = pos
    types = {_chunk_type(c) for c, _ in rows}
    tkey = "fsd" if "fsd" in types else "prd" if "prd" in types else \
           "tdd" if "tdd" in types else "impl" if "impl" in types else "misc"
    fill, stroke, title_bg = PALETTE[tkey]
    parts = [
        f'<rect class="fbox" x="{bx:.1f}" y="{by:.1f}" width="{bw}" height="{bh}"'
        f' rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>',
        f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw}" height="{TITLE_H}" rx="10"'
        f' fill="{title_bg}" stroke="none"/>',
        f'<line x1="{bx:.1f}" y1="{by + TITLE_H:.1f}" x2="{bx + bw:.1f}"'
        f' y2="{by + TITLE_H:.1f}" stroke="{stroke}" stroke-width="1"/>',
        f'<text x="{bx + 10:.1f}" y="{by + 17:.1f}" font-family="ui-monospace,monospace"'
        f' font-size="11" font-weight="bold" fill="{TEXT_COL}">{he(_clip(f))}</text>',
    ]
    for cid, depth in rows:
        cx, cy = rpos[cid]
        rx = bx + 8
        rw = bw - 16
        display = _clip(cid) if depth == 0 else "└ " * 1 + ":" + cid.rsplit(":", 1)[1]
        row = (
            f'<rect x="{rx:.1f}" y="{cy - ROW_H / 2 + 2:.1f}" width="{rw}"'
            f' height="{ROW_H - 5}" rx="4" fill="{ROW_FILL}" stroke="{ROW_LINE}"'
            f' stroke-width="1"/>'
            f'<text x="{rx + 6 + depth * INDENT:.1f}" y="{cy + 4:.1f}"'
            f' font-family="ui-monospace,monospace" font-size="11"'
            f' fill="{TEXT_COL}">{he(_clip(display))}</text>'
        )
        note = _dep_note(cid, dep_map)
        if note:
            row += (
                f'<text x="{rx + rw - 5:.1f}" y="{cy + 3:.1f}" text-anchor="end"'
                f' font-family="ui-monospace,monospace" font-size="9"'
                f' fill="{DEP_COL}">{he(note)}</text>'
            )
        parts.append(row)
    return "\n".join(parts)


def _render_svg(
    files: dict[str, list[str]],
    chunks: dict[str, str],
    cross_tree: list[tuple],
    cross_dep: list[tuple],
    dep_map: dict[str, list[str]],
    box_pos: dict[str, tuple],
    row_pos: dict[str, dict[str, tuple]],
) -> str:
    def _rp(cid: str) -> tuple:
        return row_pos[chunks[cid]][cid]

    # no viewBox: user units stay 1:1 with CSS px so zoom/pan math is exact
    p = [
        f'<svg id="svg" xmlns="http://www.w3.org/2000/svg"'
        f' width="100%" height="100%"'
        f' style="display:block;cursor:grab">',
        f'<defs>{_markers()}</defs>',
        '<g id="canvas">',
    ]

    # depends_on behind everything
    for src, dst in cross_dep:
        sx, sy = _rp(src)
        dx, dy = _rp(dst)
        src_box_x = box_pos[chunks[src]][0]
        dst_box_x = box_pos[chunks[dst]][0]
        p.append(_dep_edge_svg(src_box_x, sy, dst_box_x, dy, src, dst))

    # Bus-routed chunk-to-chunk tree edges: each edge gets an exit lane at
    # the source box, its own horizontal lane in the inter-row gap, and an
    # entry lane at the target box. Labels sit on the lane itself.
    rows_by_file = {f: _file_rows(cids) for f, cids in files.items()}
    row_index = {
        f: {cid: i for i, (cid, _d) in enumerate(rows)}
        for f, rows in rows_by_file.items()
    }
    entry_count: dict[str, int] = defaultdict(int)
    bus_count: dict[str, int] = defaultdict(int)
    used_label_pos: set[tuple[float, float]] = set()
    for src, rel, dst in cross_tree:
        src_file, dst_file = chunks[src], chunks[dst]
        sbx, sby, sbw, sbh = box_pos[src_file]
        dbx, dby, dbw, _dbh = box_pos[dst_file]
        ri = row_index[src_file].get(src, 0)
        exit_x = sbx + min(12 + ri * 10, sbw - 12)
        ei = entry_count[dst_file]
        entry_count[dst_file] += 1
        entry_x = dbx + min(12 + ei * 12, dbw - 12)
        bi = bus_count[src_file]
        bus_count[src_file] += 1
        going_down = dby >= sby + sbh
        if going_down:
            src_boundary, dst_boundary = sby + sbh, dby
            bus_y = src_boundary + 12 + bi * 16
        else:
            src_boundary, dst_boundary = sby, dby + _dbh
            bus_y = src_boundary - 12 - bi * 16
        label_y = bus_y - 4 if going_down else bus_y + 14
        shift = 0.0
        while (entry_x, label_y + shift) in used_label_pos:
            shift += 12.0
        used_label_pos.add((entry_x, label_y + shift))
        p.append(
            _tree_edge_svg(
                exit_x, src_boundary, bus_y, entry_x, dst_boundary,
                rel, src, dst, going_down, label_shift=shift,
            )
        )

    # subgraph boxes on top
    rows_by_file = {f: _file_rows(cids) for f, cids in files.items()}
    for f in sorted(files, key=lambda f: (box_pos[f][1], box_pos[f][0])):
        p.append(_box_svg(f, box_pos[f], rows_by_file[f], row_pos[f], dep_map))

    p.append('</g></svg>')
    return "\n".join(p)


# ── HTML shell (viewport + zoom/pan) ──────────────────────────────────────────

def _html_shell(title: str, svg: str) -> str:
    legend = (
        '<span class="sw" style="background:#eaf2fc;border-color:#4a90d9"></span>FSD'
        ' <span class="sw" style="background:#f2f2f2;border-color:#666"></span>PRD'
        ' <span class="sw" style="background:#ecf7ef;border-color:#52a871"></span>TDD'
        ' <span class="ln"></span> derives / decomposes / details'
        ' <span class="ln dash"></span> depends_on'
        ' &nbsp;·&nbsp; 滚轮缩放 / 拖拽平移 / 双击复位'
    )
    return (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        f'<title>{he(title)}</title>\n'
        '<style>'
        'html,body{margin:0;height:100%;overflow:hidden;background:' + BG + '}'
        'body{display:flex;flex-direction:column}'
        'h2{font-family:ui-monospace,monospace;color:#444;padding:8px 14px;'
        'margin:0;font-size:13px;border-bottom:1px solid #ddd;flex:0 0 auto}'
        '#view{flex:1 1 auto;min-height:0}'
        '#view svg{width:100%;height:100%;background:' + BG + '}'
        '#tools{position:fixed;top:8px;right:12px;display:flex;gap:6px;z-index:2}'
        '#tools button{font-family:ui-monospace,monospace;font-size:12px;'
        'padding:2px 9px;border:1px solid #bbb;border-radius:5px;background:#fff;'
        'cursor:pointer;color:#333}'
        '#legend{position:fixed;left:12px;bottom:10px;z-index:2;'
        'font-family:ui-monospace,monospace;font-size:11px;color:#556;'
        'background:rgba(255,255,255,.88);border:1px solid #ddd;border-radius:6px;'
        'padding:4px 10px}'
        '#legend .sw{display:inline-block;width:10px;height:10px;border:1.5px solid;'
        'border-radius:3px;margin:0 3px 0 8px;vertical-align:-1px}'
        '#legend .ln{display:inline-block;width:22px;border-top:2px solid ' + EDGE_COL + ';'
        'margin:0 4px 0 10px;vertical-align:3px}'
        '#legend .ln.dash{border-top:1.5px dashed ' + DEP_COL + '}'
        '</style>\n</head>\n<body>\n'
        f'<h2>{he(title)}</h2>\n'
        '<div id="tools"><button id="zin">+</button><button id="zout">−</button>'
        '<button id="zfit">fit</button></div>\n'
        '<div id="view">\n'
        f'{svg}\n'
        '</div>\n'
        f'<div id="legend">{legend}</div>\n'
        '<script>\n'
        'const svg=document.getElementById("svg"),g=document.getElementById("canvas");\n'
        'let tx=0,ty=0,k=1;\n'
        'function apply(){g.setAttribute("transform",`translate(${tx} ${ty}) scale(${k})`);}\n'
        'function toView(e){const pt=new DOMPoint(e.clientX,e.clientY);'
        'return pt.matrixTransform(svg.getScreenCTM().inverse());}\n'
        'function zoomAt(f,cx,cy){const nk=Math.min(8,Math.max(0.05,k*f));const r=nk/k;'
        'tx=cx-(cx-tx)*r;ty=cy-(cy-ty)*r;k=nk;apply();}\n'
        'function fit(){const b=g.getBBox();if(!b.width||!b.height)return;'
        'const vw=svg.clientWidth,vh=svg.clientHeight;'
        'k=Math.min(vw/(b.width+80),vh/(b.height+80),1);'
        'tx=(vw-b.width*k)/2-b.x*k;ty=(vh-b.height*k)/2-b.y*k;apply();}\n'
        'svg.addEventListener("wheel",e=>{e.preventDefault();'
        'const p=toView(e);zoomAt(e.deltaY<0?1.15:1/1.15,p.x,p.y);},{passive:false});\n'
        'let drag=null;\n'
        'svg.addEventListener("mousedown",e=>{drag={x:e.clientX,y:e.clientY,tx,ty};'
        'svg.style.cursor="grabbing";});\n'
        'window.addEventListener("mousemove",e=>{if(!drag)return;'
        'tx=drag.tx+(e.clientX-drag.x);ty=drag.ty+(e.clientY-drag.y);apply();});\n'
        'window.addEventListener("mouseup",()=>{drag=null;svg.style.cursor="grab";});\n'
        'svg.addEventListener("dblclick",fit);\n'
        'document.getElementById("zin").onclick=()=>{'
        'zoomAt(1.25,svg.clientWidth/2,svg.clientHeight/2);};\n'
        'document.getElementById("zout").onclick=()=>{'
        'zoomAt(1/1.25,svg.clientWidth/2,svg.clientHeight/2);};\n'
        'document.getElementById("zfit").onclick=fit;\n'
        'fit();\n'
        '</script>\n'
        '</body>\n</html>\n'
    )


# ── PRD-chunk scoping (unchanged semantics) ──────────────────────────────────

def _scope_graph_to_prd(
    nodes_by_cid: dict[str, str],
    edges: list[tuple[str, str, str]],
    prd_chunk: str,
) -> tuple[dict[str, str], list[tuple[str, str, str]]]:
    """Scope to prd_chunk's derives/decomposes/details subtree (+ id struct children)."""
    if prd_chunk not in nodes_by_cid:
        raise ValueError(f"PRD chunk not found: {prd_chunk}")
    if not prd_chunk.startswith("[PRD]-"):
        raise ValueError(f"Chunk is not a PRD: {prd_chunk}")

    children: dict[str, list] = defaultdict(list)
    for src, rel, dst in edges:
        if rel in TREE_RELS:
            children[src].append(dst)
            if rel == "derives":
                children[dst].append(src)

    all_ids = set(nodes_by_cid.keys())

    def _struct_children(cid: str) -> list:
        prefix = cid + ":"
        return [i for i in all_ids
                if i.startswith(prefix) and ":" not in i[len(prefix):]]

    scoped: set = set()
    queue: deque = deque([prd_chunk])
    while queue:
        cid = queue.popleft()
        if cid in scoped:
            continue
        scoped.add(cid)
        queue.extend(children.get(cid, []))
        queue.extend(_struct_children(cid))

    scoped_nodes = {cid: nodes_by_cid[cid] for cid in scoped if cid in nodes_by_cid}
    scoped_edges = [(s, r, d) for s, r, d in edges if s in scoped and d in scoped]
    return scoped_nodes, scoped_edges


# ── Entry points ──────────────────────────────────────────────────────────────

def _empty_html() -> str:
    return ("<!DOCTYPE html>\n<html><body style='background:#f6f6f6;"
            "font-family:monospace'><h2>Spec Graph</h2>"
            "<p>(empty)</p></body></html>\n")


def generate_graph_html(root: Path, version: str | None = None, prd_chunk: str | None = None) -> str:
    """Build a self-contained, zoomable HTML+SVG chunk-level spec-tree.

    prd_chunk=None  → whole graph, grouped into per-file subgraph boxes.
    prd_chunk=<id>  → scope to that PRD chunk's subtree first.
    """
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

        def _cid_v(uri: str) -> str:
            parts = uri.split(":", 3)
            return parts[3] if len(parts) == 4 else uri

        raw_edges = [(_cid_v(e.src), e.rel, _cid_v(e.dst)) for e in view.edges]
        nodes_by_cid = {cid: (getattr(n, "file", "") or "")
                        for cid, n in view.nodes.items()}

    if prd_chunk is not None:
        nodes_by_cid, raw_edges = _scope_graph_to_prd(nodes_by_cid, raw_edges, prd_chunk)

    chunks, cross_tree, cross_dep, files, dep_map = _build_chunk_graph(nodes_by_cid, raw_edges)
    if not chunks:
        return _empty_html()

    box_pos, row_pos = _layout(files, chunks, cross_tree)
    svg = _render_svg(files, chunks, cross_tree, cross_dep, dep_map, box_pos, row_pos)
    scope = f" — {prd_chunk}" if prd_chunk else ""
    title = f"Spec Graph — {version}{scope}" if version else f"Spec Graph (baseline){scope}"
    return _html_shell(title, svg)


def write_graph_html(root: Path, version: str | None = None, prd_chunk: str | None = None) -> dict:
    """Generate and atomically write graph.html to the fixed output path."""
    try:
        from .io_utils import atomic_write_text
    except ImportError:
        from ait.io_utils import atomic_write_text  # type: ignore

    content = generate_graph_html(root, version, prd_chunk)
    out_path = (root / "docs" / "graph.html" if version is None
                else root / "versions" / version / "graph.html")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_path, content)

    node_count = content.count('font-size="11"')
    edge_count = content.count("marker-end=") - 2   # exclude the two <marker> defs

    return {
        "path": str(out_path.relative_to(root)).replace("\\", "/"),
        "nodes": node_count,
        "edges": max(0, edge_count),
    }


# backward-compat aliases (CLI references these names)
generate_graph_md = generate_graph_html
write_graph_md = write_graph_html
