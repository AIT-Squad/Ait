"""Validation for the PRD/FSD/TDD chunk graph model."""

from __future__ import annotations

from dataclasses import dataclass

from .specgraph import Edge, Spec, SpecGraph

ALLOWED_RELS = {"derives", "decomposes", "details", "depends_on"}
NEW_MODEL_TYPES = {"prd", "fsd", "tdd"}
NEW_MODEL_PREFIXES = ("[PRD]-", "[FSD]-", "[TDD]-")


@dataclass(frozen=True)
class NewModelViolation:
    code: str
    message: str
    chunk_id: str | None = None
    file: str | None = None
    rel: str | None = None
    src: str | None = None
    dst: str | None = None


def validate_prd_fsd_tdd_graph(graph: SpecGraph) -> list[NewModelViolation]:
    violations: list[NewModelViolation] = []
    child_kinds_by_parent: dict[str, set[str]] = {}

    for edge in graph.edges:
        src = graph.specs.get(edge.src)
        dst = graph.specs.get(edge.dst)
        if src is None or dst is None:
            if edge.rel in ALLOWED_RELS:
                violations.append(_violation(edge, "MISSING_ENDPOINT", "new-model edge endpoint is missing from specgraph"))
            continue
        if not (_is_new_model_spec(src) or _is_new_model_spec(dst)):
            continue

        if edge.rel not in ALLOWED_RELS:
            violations.append(
                _violation(
                    edge,
                    "UNSUPPORTED_RELATION",
                    "new-model graph relations must be one of: derives, decomposes, details, depends_on",
                    src,
                )
            )
            continue

        if edge.rel == "derives":
            violations.extend(_validate_derives(edge, src, dst))
        elif edge.rel == "decomposes":
            violations.extend(_validate_decomposes(edge, src, dst))
            if src.type == "fsd" and dst.type == "fsd" and _is_internal_split(src):
                child_kinds_by_parent.setdefault(_parent_chunk_id(src.chunk_id), set()).add("fsd")
        elif edge.rel == "details":
            violations.extend(_validate_details(edge, src, dst))
            if src.type == "fsd" and dst.type == "tdd" and _is_internal_split(src):
                child_kinds_by_parent.setdefault(_parent_chunk_id(src.chunk_id), set()).add("tdd")
        elif edge.rel == "depends_on":
            violations.extend(_validate_depends_on(edge, src, dst))

    for parent, child_kinds in sorted(child_kinds_by_parent.items()):
        if {"fsd", "tdd"}.issubset(child_kinds):
            parent_spec = _find_spec_by_chunk_id(graph, parent)
            violations.append(
                NewModelViolation(
                    code="FSD_MIXED_CHILDREN",
                    message="one FSD node must not mix child FSD decomposition and TDD detail children",
                    chunk_id=parent,
                    file=parent_spec.file if parent_spec else None,
                )
            )

    return violations


def violations_to_details(violations: list[NewModelViolation]) -> list[dict]:
    return [
        {
            "code": v.code,
            "message": v.message,
            "chunk_id": v.chunk_id,
            "file": v.file,
            "rel": v.rel,
            "src": v.src,
            "dst": v.dst,
        }
        for v in violations
    ]


def normalize_target_file(path: str) -> str:
    """Normalize a target_file path for artifact-identity comparison.

    Backslashes → posix, ``./`` stripped, ``..`` segments collapsed, casefold —
    so ``./src\\X.py`` and ``src/x.py`` denote the same artifact (audit R2-06).
    """
    parts: list[str] = []
    for seg in path.replace("\\", "/").split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
            continue
        parts.append(seg)
    return "/".join(parts).casefold()


def validate_target_file_uniqueness(
    entries: list[tuple[str, str | None, str | None]]
) -> list[NewModelViolation]:
    """Reject the case where two distinct TDD root chunks declare the same target_file.

    ``entries`` is a list of ``(chunk_id, file, target_file)`` tuples, one per TDD
    root chunk. Grouping uses :func:`normalize_target_file` so separator, ``./``
    and case variants of the same path collide. TDDs without a ``target_file``
    are ignored here (that is the separate ``TDD_TARGET_FILE_REQUIRED``
    concern). This is the hard guarantee behind "different people do not edit
    the same file".
    """
    by_target: dict[str, list[tuple[str, str | None]]] = {}
    for chunk_id, file, target_file in entries:
        if not target_file:
            continue
        by_target.setdefault(normalize_target_file(target_file), []).append((chunk_id, file))

    violations: list[NewModelViolation] = []
    for target_file, owners in sorted(by_target.items()):
        unique_owner_ids = sorted({chunk_id for chunk_id, _ in owners})
        if len(unique_owner_ids) > 1:
            violations.append(
                NewModelViolation(
                    code="DUPLICATE_TARGET_FILE",
                    message=(
                        f"target_file '{target_file}' is declared by multiple TDDs: "
                        + ", ".join(unique_owner_ids)
                    ),
                    chunk_id=unique_owner_ids[0],
                    file=sorted(owners)[0][1],
                )
            )
    return violations


# ── v2.20: six-invariant suite (write-time local gate + confirm global gate) ──


def check_edge_write(view, src: str, dst: str, rel: str) -> list[NewModelViolation]:
    """Write-time local gate for ``add_edge`` — runs BEFORE anything is persisted.

    Only rejects increments that can never be legal: phantom endpoints, a
    second details parent for a TDD, a second FSD for a PRD. Global
    completeness (orphans / broken traces / cycles) is legitimately violated
    while a graph is under construction and belongs to the confirm gate.
    """
    violations: list[NewModelViolation] = []
    if view.node(src) is None:
        violations.append(
            NewModelViolation(
                code="MISSING_ENDPOINT",
                message=f"edge src chunk does not exist: {src}",
                chunk_id=src, rel=rel, src=src, dst=dst,
            )
        )
    if view.node(dst) is None:
        violations.append(
            NewModelViolation(
                code="MISSING_ENDPOINT",
                message=f"edge dst chunk does not exist: {dst}",
                chunk_id=dst, rel=rel, src=src, dst=dst,
            )
        )
    if violations:
        return violations
    if rel == "details":
        other_parents = [e.src for e in view.edges_to(dst, "details") if e.src != src]
        if other_parents:
            violations.append(
                NewModelViolation(
                    code="TDD_MULTI_PARENT",
                    message=(
                        f"TDD {dst} already has a details parent: "
                        + ", ".join(sorted(other_parents))
                    ),
                    chunk_id=dst, rel=rel, src=src, dst=dst,
                )
            )
    if rel == "derives":
        src_node = view.node(src)
        if src_node is not None and src_node.type == "prd":
            other_fsds = [e.dst for e in view.edges_from(src, "derives") if e.dst != dst]
            if other_fsds:
                violations.append(
                    NewModelViolation(
                        code="PRD_FSD_LINK_NOT_UNIQUE",
                        message=(
                            f"PRD {src} already derives: "
                            + ", ".join(sorted(other_fsds))
                        ),
                        chunk_id=src, rel=rel, src=src, dst=dst,
                    )
                )
    if rel == "decomposes":
        src_node = view.node(src)
        if src_node is not None and src_node.type == "prd":
            violations.append(
                NewModelViolation(
                    code="INVALID_DECOMPOSES_TYPES",
                    message=f"PRD {src} does not decompose — PRD→FSD is a derives relation",
                    chunk_id=src, rel=rel, src=src, dst=dst,
                )
            )
    return violations


def validate_invariants(
    view, target_files: list[tuple[str, str | None]]
) -> list[NewModelViolation]:
    """Six-invariant global gate over the combined chunk_id view (confirm-time).

    ① PRD ↔ exactly one FSD · ② TDD has ≤1 details parent (0 → TRACE_BROKEN)
    · ③ artifact ↔ exactly one TDD (normalized) + target_file required
    · ⑤ no orphan chunks (unreachable from any PRD downward via edges +
    id-structural children) · ⑥ every TDD traces up to a PRD · plus SPEC_CYCLE
    per relation on the collapsed view. Incremental phantom endpoints (④) are
    stopped at write time; legacy dangling edges are covered by
    ``validate_prd_fsd_tdd_graph`` on the raw merged graph, because the view
    drops dangling edges by contract. Vacuous pass when the view holds no
    new-model nodes (legacy projects are unaffected).
    """
    new_nodes = {
        cid: node for cid, node in view.nodes.items() if _is_new_model_spec(node)
    }
    if not new_nodes:
        return []
    violations: list[NewModelViolation] = []
    prds = [n for n in new_nodes.values() if n.type == "prd"]
    tdds = [n for n in new_nodes.values() if n.type == "tdd"]

    # ① PRD ↔ exactly one FSD — only the PRD ROOT chunk (no colon) decomposes
    # an FSD. PRD colon splits are requirement items (content chunks), not
    # decomposition nodes; they are exempt (their structural membership under
    # the PRD root satisfies ⑤/⑥ via the id channel).
    for prd in prds:
        if ":" in prd.chunk_id:
            continue
        fsd_targets = sorted(e.dst for e in view.edges_from(prd.chunk_id, "derives"))
        if len(fsd_targets) != 1:
            violations.append(
                NewModelViolation(
                    code="PRD_FSD_LINK_NOT_UNIQUE",
                    message=(
                        f"PRD must decompose into exactly one FSD, got "
                        f"{len(fsd_targets)}: {', '.join(fsd_targets) or '(none)'}"
                    ),
                    chunk_id=prd.chunk_id, file=prd.file,
                )
            )

    # ② TDD upstream: more than one details parent
    for tdd in tdds:
        parents = sorted(e.src for e in view.edges_to(tdd.chunk_id, "details"))
        if len(parents) > 1:
            violations.append(
                NewModelViolation(
                    code="TDD_MULTI_PARENT",
                    message=f"TDD has multiple details parents: {', '.join(parents)}",
                    chunk_id=tdd.chunk_id, file=tdd.file,
                )
            )

    # ③ artifact ownership: target_file required + unique (normalized)
    for chunk_id, target in target_files:
        if not target:
            node = new_nodes.get(chunk_id)
            violations.append(
                NewModelViolation(
                    code="TDD_TARGET_FILE_REQUIRED",
                    message=f"TDD {chunk_id} does not declare a target_file",
                    chunk_id=chunk_id, file=node.file if node else None,
                )
            )
    violations.extend(
        validate_target_file_uniqueness(
            [
                (chunk_id, new_nodes[chunk_id].file if chunk_id in new_nodes else None, target)
                for chunk_id, target in target_files
            ]
        )
    )

    # structural children map (colon splits belong to their root without edges)
    children: dict[str, list[str]] = {}
    for cid in new_nodes:
        if ":" in cid:
            children.setdefault(cid.split(":", 1)[0], []).append(cid)

    # ⑤ orphans: BFS from all PRD roots downward (edges + structural channel)
    reachable: set[str] = set()
    queue = [p.chunk_id for p in prds]
    reachable.update(queue)
    while queue:
        current = queue.pop(0)
        neighbours = list(children.get(current, []))
        neighbours += [e.dst for e in view.edges_from(current, "derives")]
        neighbours += [e.dst for e in view.edges_from(current, "decomposes")]
        neighbours += [e.dst for e in view.edges_from(current, "details")]
        for n in neighbours:
            if n in reachable or n not in new_nodes:
                continue
            reachable.add(n)
            queue.append(n)
    for cid in sorted(new_nodes):
        if cid not in reachable:
            violations.append(
                NewModelViolation(
                    code="ORPHAN_CHUNK",
                    message=f"chunk is not reachable from any PRD: {cid}",
                    chunk_id=cid, file=new_nodes[cid].file,
                )
            )

    # ⑥ every TDD traces upward to a PRD
    for tdd in tdds:
        if not _traces_to_prd(view, new_nodes, tdd.chunk_id):
            violations.append(
                NewModelViolation(
                    code="TRACE_BROKEN",
                    message=(
                        f"TDD cannot be traced to a PRD via details/decomposes: "
                        f"{tdd.chunk_id}"
                    ),
                    chunk_id=tdd.chunk_id, file=tdd.file,
                )
            )

    # tree-relation cycle check on the synthetic downstream digraph:
    # decomposes/details edges ∪ the id-structural channel (root → colon
    # split). Edge-only detection misses cycles that close through structure
    # (the audit R2-01 crash graph `top:a→mid` + `mid:b→top` is exactly that
    # shape). depends_on cycles are NOT gated: lateral domain dependencies
    # are legitimately mutual (this project's own baseline has
    # version↔task↔indexing, exported from real imports), the six invariants
    # do not demand their acyclicity, and with no edge-removal command a hard
    # gate would be a terminal trap. They stay diagnosable via
    # view.detect_cycle.
    tree_edges: list[tuple[str, str]] = [
        (e.src, e.dst)
        for e in view.edges
        if e.rel in ("derives", "decomposes", "details")
    ]
    for root_id, split_ids in children.items():
        tree_edges.extend((root_id, split_id) for split_id in split_ids)
    cycle_nodes = _kahn_residual(tree_edges)
    if cycle_nodes:
        violations.append(
            NewModelViolation(
                code="SPEC_CYCLE",
                message=(
                    "decomposes/details tree (incl. structural channel) forms "
                    "a cycle: " + ", ".join(cycle_nodes)
                ),
            )
        )
    return violations


def _kahn_residual(edges: list[tuple[str, str]]) -> list[str]:
    """Nodes left with indegree > 0 after Kahn — i.e. on or feeding a cycle."""
    nodes: set[str] = set()
    for src, dst in edges:
        nodes.add(src)
        nodes.add(dst)
    indeg = {n: 0 for n in nodes}
    adj: dict[str, list[str]] = {n: [] for n in nodes}
    for src, dst in edges:
        adj[src].append(dst)
        indeg[dst] += 1
    queue = [n for n in nodes if indeg[n] == 0]
    visited = 0
    while queue:
        n = queue.pop()
        visited += 1
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
    if visited < len(nodes):
        return sorted(n for n in nodes if indeg[n] > 0)
    return []


def _traces_to_prd(view, new_nodes: dict, tdd_chunk_id: str) -> bool:
    seen: set[str] = set()
    stack = [tdd_chunk_id]
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        node = new_nodes.get(current)
        if node is not None and node.type == "prd":
            return True
        stack.extend(e.src for e in view.edges_to(current, "details"))
        stack.extend(e.src for e in view.edges_to(current, "decomposes"))
        stack.extend(e.src for e in view.edges_to(current, "derives"))
        if ":" in current:
            stack.append(current.split(":", 1)[0])
    return False


def _validate_derives(edge: Edge, src: Spec, dst: Spec) -> list[NewModelViolation]:
    """derives = PRD root → FSD root (problem-to-solution 派生, exactly 1:1).
    Only the PRD root chunk derives the FSD tree root; any other endpoint
    combination is INVALID_DERIVES."""
    if src.type == "prd" and dst.type == "fsd":
        if _is_root_chunk(src) and _is_root_chunk(dst):
            return []
        return [
            _violation(
                edge,
                "INVALID_DERIVES",
                "derives must connect the PRD root chunk to the root FSD root chunk",
                src,
            )
        ]
    return [
        _violation(
            edge,
            "INVALID_DERIVES",
            "derives is only legal from a PRD root to an FSD root",
            src,
        )
    ]


def _validate_decomposes(edge: Edge, src: Spec, dst: Spec) -> list[NewModelViolation]:
    """decomposes = FSD internal split → child FSD root (whole-to-part 拆分).
    PRD no longer decomposes (it derives); a PRD endpoint is INVALID_DECOMPOSES_TYPES."""
    if src.type == "prd" or dst.type == "prd":
        return [
            _violation(
                edge,
                "INVALID_DECOMPOSES_TYPES",
                "PRD does not decompose — PRD→FSD is a derives relation",
                src,
            )
        ]
    if src.type == "fsd" and dst.type == "fsd":
        if _is_internal_split(src) and _is_root_chunk(dst):
            return []
        return [
            _violation(
                edge,
                "INVALID_FSD_DECOMPOSES",
                "FSD decomposes must connect a parent internal split chunk to a child FSD root chunk",
                src,
            )
        ]
    return [
        _violation(
            edge,
            "INVALID_DECOMPOSES_TYPES",
            "decomposes is only valid for PRD/FSD to FSD relationships",
            src,
        )
    ]


def _validate_details(edge: Edge, src: Spec, dst: Spec) -> list[NewModelViolation]:
    if src.type == "fsd" and dst.type == "tdd" and _is_internal_split(src) and _is_root_chunk(dst):
        return []
    return [
        _violation(
            edge,
            "INVALID_DETAILS",
            "details must connect a parent FSD internal split chunk to a TDD root chunk",
            src,
        )
    ]


def _validate_depends_on(edge: Edge, src: Spec, dst: Spec) -> list[NewModelViolation]:
    if src.type != "fsd" or dst.type != "fsd":
        return [
            _violation(
                edge,
                "INVALID_DEPENDS_ON_TYPES",
                "depends_on is only valid between FSD internal split chunks",
                src,
            )
        ]
    if not _is_internal_split(src) or not _is_internal_split(dst):
        return [
            _violation(
                edge,
                "DEPENDS_ON_ROOT_CHUNK",
                "depends_on must not point directly at downstream root chunks",
                src,
            )
        ]
    if _parent_chunk_id(src.chunk_id) != _parent_chunk_id(dst.chunk_id):
        return [
            _violation(
                edge,
                "DEPENDS_ON_CROSS_LEVEL",
                "depends_on must connect sibling split chunks; lift the dependency to the parent split level",
                src,
            )
        ]
    return []


def _is_new_model_spec(spec: Spec) -> bool:
    return spec.type in NEW_MODEL_TYPES and spec.chunk_id.startswith(NEW_MODEL_PREFIXES)


def _is_root_chunk(spec: Spec) -> bool:
    if ":" in spec.chunk_id:
        return False
    return _file_stem(spec.file) == spec.chunk_id


def _is_internal_split(spec: Spec) -> bool:
    if spec.type != "fsd" or ":" not in spec.chunk_id:
        return False
    return _parent_chunk_id(spec.chunk_id) == _file_stem(spec.file)


def _parent_chunk_id(chunk_id: str) -> str:
    return chunk_id.split(":", 1)[0]


def _file_stem(file: str) -> str:
    return file.rsplit("/", 1)[-1]


def _find_spec_by_chunk_id(graph: SpecGraph, chunk_id: str) -> Spec | None:
    for spec in graph.specs.values():
        if spec.chunk_id == chunk_id:
            return spec
    return None


def _violation(
    edge: Edge,
    code: str,
    message: str,
    spec: Spec | None = None,
) -> NewModelViolation:
    return NewModelViolation(
        code=code,
        message=message,
        chunk_id=spec.chunk_id if spec else None,
        file=spec.file if spec else None,
        rel=edge.rel,
        src=edge.src,
        dst=edge.dst,
    )
