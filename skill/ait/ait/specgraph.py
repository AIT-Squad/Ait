"""SpecGraph — normalized graph index for PRD/impl chunks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml

from .chunk_parser import parse_file
from .index_manager import IndexManager
from .io_utils import atomic_write_text

SpecType = Literal["prd", "impl", "fsd", "tdd", "global", "other"]


@dataclass
class Spec:
    uri: str
    title: str
    type: SpecType
    version: str
    chunk_id: str
    file: str
    metadata: dict = field(default_factory=dict)


@dataclass
class Edge:
    src: str
    dst: str
    rel: str
    weight: float = 1.0
    metadata: dict = field(default_factory=dict)


@dataclass
class SpecGraph:
    version: int = 1
    updated: str | None = None
    specs: dict[str, Spec] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "SpecGraph":
        if not path.exists():
            return cls()
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        graph = cls(version=raw.get("version", 1), updated=raw.get("updated"))
        for item in raw.get("specs", []):
            spec = Spec(
                uri=item["uri"],
                title=item.get("title", ""),
                type=item.get("type", "other"),
                version=item.get("version", "baseline"),
                chunk_id=item["chunk_id"],
                file=item.get("file", ""),
                metadata=item.get("metadata") or {},
            )
            graph.specs[spec.uri] = spec
        for item in raw.get("edges", []):
            graph.edges.append(
                Edge(
                    src=item["src"],
                    dst=item["dst"],
                    rel=item.get("rel", "related"),
                    weight=float(item.get("weight", 1.0)),
                    metadata=item.get("metadata") or {},
                )
            )
        return graph

    def save(self, path: Path) -> None:
        self.updated = datetime.now(timezone.utc).isoformat()
        raw = {
            "version": self.version,
            "updated": self.updated,
            "specs": [
                {
                    "uri": spec.uri,
                    "title": spec.title,
                    "type": spec.type,
                    "version": spec.version,
                    "chunk_id": spec.chunk_id,
                    "file": spec.file,
                    "metadata": spec.metadata,
                }
                for spec in sorted(self.specs.values(), key=lambda s: s.uri)
            ],
            "edges": [
                {
                    "src": edge.src,
                    "dst": edge.dst,
                    "rel": edge.rel,
                    "weight": edge.weight,
                    "metadata": edge.metadata,
                }
                for edge in self.edges
            ],
        }
        text = yaml.safe_dump(raw, allow_unicode=True, sort_keys=False, width=120)
        atomic_write_text(path, text)

    def add_spec(self, spec: Spec) -> None:
        self.specs[spec.uri] = spec

    def add_edge(
        self,
        src: str,
        dst: str,
        rel: str,
        *,
        weight: float = 1.0,
        metadata: dict | None = None,
    ) -> None:
        for edge in self.edges:
            if edge.src == src and edge.dst == dst and edge.rel == rel:
                edge.weight = weight
                edge.metadata.update(metadata or {})
                return
        self.edges.append(
            Edge(src=src, dst=dst, rel=rel, weight=weight, metadata=metadata or {})
        )

    def query(self, uri: str, *, direction: str = "out", rel: str | None = None) -> list[Edge]:
        edges = self.edges
        if rel is not None:
            edges = [edge for edge in edges if edge.rel == rel]
        if direction == "out":
            return [edge for edge in edges if edge.src == uri]
        if direction == "in":
            return [edge for edge in edges if edge.dst == uri]
        if direction == "both":
            return [edge for edge in edges if edge.src == uri or edge.dst == uri]
        raise ValueError("direction must be one of: in, out, both")

    def dependencies(self, uri: str) -> list[Edge]:
        return [edge for edge in self.query(uri, direction="out") if edge.rel in {"depends_on", "implements"}]

    def implementations(self, uri: str) -> list[Edge]:
        return [edge for edge in self.query(uri, direction="in", rel="implements")]

    def impacted(self, uri: str) -> list[str]:
        reverse = [edge for edge in self.edges if edge.rel in {"depends_on", "implements"}]
        seen: set[str] = set()
        queue = [uri]
        while queue:
            current = queue.pop(0)
            for edge in reverse:
                if edge.dst != current or edge.src in seen:
                    continue
                seen.add(edge.src)
                queue.append(edge.src)
        return sorted(seen)

    def detect_cycle(self, *, rels: set[str] | None = None) -> list[str] | None:
        """Detect a dependency cycle via Kahn topological sort.

        Considers only edges whose rel is in `rels` (default: depends_on /
        depends-on). Returns the list of URIs that form the residual cycle, or
        None if the graph is acyclic.
        """
        rels = rels or {"depends_on", "depends-on"}
        nodes = set(self.specs.keys())
        # Include endpoints that may not be registered as specs (defensive).
        dep_edges = [e for e in self.edges if e.rel in rels]
        for e in dep_edges:
            nodes.add(e.src)
            nodes.add(e.dst)
        indeg = {n: 0 for n in nodes}
        adj: dict[str, list[str]] = {n: [] for n in nodes}
        for e in dep_edges:
            adj[e.src].append(e.dst)
            indeg[e.dst] += 1
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
            # Residual nodes (indeg > 0) participate in or feed the cycle.
            return sorted(n for n in nodes if indeg[n] > 0)
        return None

    def implements_of(self, prd_chunk_id: str, version: str) -> list[str]:
        """chunk ids of impl specs that `implements` the given PRD chunk.

        Restricted to the given version (or baseline). Used by task build.
        """
        result: list[str] = []
        for edge in self.edges:
            if edge.rel != "implements":
                continue
            dst = self.specs.get(edge.dst)
            src = self.specs.get(edge.src)
            if dst is None or src is None:
                continue
            if dst.chunk_id == prd_chunk_id and src.version in (version, "baseline"):
                result.append(src.chunk_id)
        return sorted(set(result))

    def dry_run_merge(self, other: "SpecGraph") -> "SpecGraph":
        """Return a new graph = self + other (no mutation, no disk write).

        Used by impl-confirm pre-merge validation: merge the version graph into
        baseline in memory, then run detect_cycle on the result.
        """
        merged = SpecGraph(version=self.version)
        merged.specs = dict(self.specs)
        merged.edges = list(self.edges)
        for spec in other.specs.values():
            merged.specs[spec.uri] = spec
        for edge in other.edges:
            merged.add_edge(
                edge.src, edge.dst, edge.rel, weight=edge.weight, metadata=dict(edge.metadata)
            )
        return merged

    def merge_into_baseline(self, version: str) -> None:
        """Rewrite this graph's version-`version` nodes/edges as baseline.

        Used at version-confirm: a version's specs are promoted to baseline
        (URI version segment rewritten to `baseline`), replacing same-chunk
        baseline specs.
        """
        remap: dict[str, str] = {}
        promoted: dict[str, Spec] = {}
        for uri, spec in self.specs.items():
            if spec.version == version:
                new_uri = make_uri(spec.chunk_id, "baseline")
                remap[uri] = new_uri
                promoted[new_uri] = Spec(
                    uri=new_uri, title=spec.title, type=spec.type,
                    version="baseline", chunk_id=spec.chunk_id, file=spec.file,
                    metadata={**spec.metadata, "source": "baseline"},
                )
        # Drop old version specs, apply promoted (replacing same-uri baseline).
        for uri in list(self.specs.keys()):
            if self.specs[uri].version == version:
                del self.specs[uri]
        self.specs.update(promoted)
        # Remap edges that referenced the version specs; drop dangling ones.
        new_edges: list[Edge] = []
        seen: set[tuple[str, str, str]] = set()
        for e in self.edges:
            s = remap.get(e.src, e.src)
            d = remap.get(e.dst, e.dst)
            key = (s, d, e.rel)
            if key in seen:
                continue
            seen.add(key)
            new_edges.append(Edge(src=s, dst=d, rel=e.rel, weight=e.weight, metadata=dict(e.metadata)))
        self.edges = new_edges

    def export_dot(self) -> str:
        lines = ["digraph SpecGraph {"]
        for uri, spec in sorted(self.specs.items()):
            label = f"{spec.chunk_id}\\n{spec.version}"
            lines.append(f'  "{uri}" [label="{label}"];')
        for edge in self.edges:
            lines.append(f'  "{edge.src}" -> "{edge.dst}" [label="{edge.rel}"];')
        lines.append("}")
        return "\n".join(lines) + "\n"


# ── Combined view: chunk_id world across baseline ∪ version ─────────────


@dataclass
class ViewNode:
    """A chunk in the combined view; version/file/uri come from the winning source."""

    chunk_id: str
    type: str
    version: str
    file: str
    title: str
    uri: str


@dataclass
class ViewEdge:
    """An edge with endpoints collapsed to chunk_id."""

    src: str
    dst: str
    rel: str
    metadata: dict = field(default_factory=dict)


class CombinedView:
    """baseline ∪ version collapsed to chunk_id identity.

    Nodes: baseline specs overlaid by version specs (same chunk_id → the
    version spec wins, so a chunk being modified reads from the version
    workspace while keeping every relation it had in baseline — this removes
    the URI duality that blinded codegen/deps/impact to in-flight chunks).
    Edges: endpoints collapsed URI→chunk_id, deduped by (src, dst, rel);
    edges with an endpoint that has no node are dropped (write-side integrity
    belongs to the validators). Read-time only — storage format unchanged.
    """

    def __init__(self) -> None:
        self.nodes: dict[str, ViewNode] = {}
        self.edges: list[ViewEdge] = []

    def node(self, chunk_id: str) -> ViewNode | None:
        return self.nodes.get(chunk_id)

    def edges_from(self, chunk_id: str, rel: str | None = None) -> list[ViewEdge]:
        return [
            e for e in self.edges
            if e.src == chunk_id and (rel is None or e.rel == rel)
        ]

    def edges_to(self, chunk_id: str, rel: str | None = None) -> list[ViewEdge]:
        return [
            e for e in self.edges
            if e.dst == chunk_id and (rel is None or e.rel == rel)
        ]

    def impacted(self, chunk_id: str) -> list[str]:
        """Transitive impact closure in discovery order (start excluded).

        Forward decomposes/details edges + id-structural children (a colon
        split ``X:*`` belongs to its root ``X`` with no explicit edge) —
        spec-tree downstream: change a PRD → its FSD tree → their TDDs —
        plus reverse depends_on/implements (dependents of the changed chunk).
        """
        forward = {"decomposes", "details"}
        reverse = {"depends_on", "implements"}
        children: dict[str, list[str]] = {}
        for cid in self.nodes:
            if ":" in cid:
                children.setdefault(cid.split(":", 1)[0], []).append(cid)
        seen: set[str] = {chunk_id}
        order: list[str] = []
        queue = [chunk_id]
        while queue:
            current = queue.pop(0)
            neighbours: list[str] = list(children.get(current, []))
            for edge in self.edges:
                if edge.rel in forward and edge.src == current:
                    neighbours.append(edge.dst)
                elif edge.rel in reverse and edge.dst == current:
                    neighbours.append(edge.src)
            for neighbour in neighbours:
                if neighbour in seen:
                    continue
                seen.add(neighbour)
                order.append(neighbour)
                queue.append(neighbour)
        return order

    def detect_cycle(self, *, rels: set[str]) -> list[str] | None:
        """Kahn residual on the collapsed chunk_id edges (rels explicit).

        Because endpoints are collapsed to chunk_id, a cycle that would only
        appear after merging a version into baseline (audit R2-02) is visible
        here before the merge. Self-loops (X→X) are reported too.
        """
        dep_edges = [e for e in self.edges if e.rel in rels]
        nodes = set(self.nodes)
        for e in dep_edges:
            nodes.add(e.src)
            nodes.add(e.dst)
        indeg = {n: 0 for n in nodes}
        adj: dict[str, list[str]] = {n: [] for n in nodes}
        for e in dep_edges:
            adj[e.src].append(e.dst)
            indeg[e.dst] += 1
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
        return None


def spec_type(
    chunk_id: str,
    file: str | None = None,
    metadata: dict | None = None,
) -> SpecType:
    doc_type = (metadata or {}).get("doc_type") or (metadata or {}).get("type")
    if isinstance(doc_type, str) and doc_type.lower() in {"prd", "impl", "fsd", "tdd", "global"}:
        return doc_type.lower()  # type: ignore[return-value]
    if file:
        first_segment = file.split("/", 1)[0].lower()
        if first_segment in {"prd", "impl", "fsd", "tdd", "global"}:
            return first_segment  # type: ignore[return-value]
    if chunk_id.startswith("prd-"):
        return "prd"
    if chunk_id.startswith("impl-"):
        return "impl"
    if chunk_id.startswith("global-"):
        return "global"
    if chunk_id.startswith("[PRD]-"):
        return "prd"
    if chunk_id.startswith("[FSD]-"):
        return "fsd"
    if chunk_id.startswith("[TDD]-"):
        return "tdd"
    return "other"


def make_uri(
    chunk_id: str,
    version: str = "baseline",
    file: str | None = None,
    metadata: dict | None = None,
) -> str:
    return f"spec:{spec_type(chunk_id, file, metadata)}:{version}:{chunk_id}"


def parse_uri(uri: str) -> tuple[str, str, str]:
    parts = uri.split(":", 3)
    if len(parts) != 4 or parts[0] != "spec":
        raise ValueError(f"Invalid spec URI: {uri}")
    return parts[1], parts[2], parts[3]


def specgraph_path(project_root: Path, version: str = "baseline") -> Path:
    """Path to a specgraph file.

    - baseline → .meta/specgraph.yaml (global graph)
    - vX.Y     → .meta/specgraph-{version}.yaml (per-version graph)
    """
    if version == "baseline":
        return project_root / ".meta" / "specgraph.yaml"
    return project_root / ".meta" / f"specgraph-{version}.yaml"


def load_specgraph(project_root: Path, version: str = "baseline") -> SpecGraph:
    return SpecGraph.load(specgraph_path(project_root, version))


def _global_category(chunk_id: str, file: str) -> str | None:
    """static vs dynamic for global-* chunks; None for non-global."""
    if spec_type(chunk_id, file) != "global":
        return None
    stem = (file or "").rsplit("/", 1)[-1]
    if stem in {"ddl", "schema", "api"} or any(
        chunk_id.startswith(f"global-{k}") for k in ("ddl", "schema", "api")
    ):
        return "dynamic"
    return "static"


def sync_specgraph(project_root: Path) -> SpecGraph:
    """Rebuild specgraph as split files: one baseline graph + one per version.

    - .meta/specgraph.yaml          : baseline chunks (docs/) + their @ref edges
    - .meta/specgraph-{version}.yaml : that version's chunks + edges (to version
      or baseline targets)

    Does NOT read or write links-index — edges come straight from chunk @refs.
    Returns the baseline graph (for backward-compat with callers).
    """
    root = project_root.resolve()
    indexes = IndexManager(root)
    previous_base = load_specgraph(root, "baseline")

    # ── Baseline graph ──
    base = SpecGraph()
    base_known: dict[str, str] = {}  # chunk_id -> baseline uri
    for entry in indexes.load_baseline().chunks:
        uri = make_uri(entry.id, "baseline", entry.file, entry.metadata)
        meta: dict = {"source": "baseline", **entry.metadata}
        cat = _global_category(entry.id, entry.file)
        if cat:
            meta["category"] = cat
        base.add_spec(
            Spec(uri=uri, title=entry.heading, type=spec_type(entry.id, entry.file, entry.metadata),
                 version="baseline", chunk_id=entry.id, file=entry.file, metadata=meta)
        )
        base_known[entry.id] = uri
    # Baseline edges from docs/ @refs
    for pf in indexes.scan_dir(indexes.docs_dir):
        for ref in pf.refs:
            src = base_known.get(ref.source_chunk_id)
            dst = base_known.get(ref.target_chunk_id)
            if src and dst:
                base.add_edge(src, dst, ref.rel, metadata={"source": "baseline-ref"})
    _preserve_explicit_edges(previous_base, base)
    base.save(specgraph_path(root, "baseline"))

    # ── Per-version graphs ──
    for version in indexes.list_versions():
        vmeta = indexes.load_version_index(version)
        if vmeta.status == "merged":
            continue  # merged versions live in baseline now
        previous_vg = load_specgraph(root, version)
        vg = SpecGraph()
        v_known: dict[str, str] = {}
        for entry in vmeta.chunks:
            uri = make_uri(entry.id, version, entry.file or "", entry.metadata)
            meta = {"source": "version", "state": entry.state,
                    "action": entry.action, "commit_id": entry.commit_id, **entry.metadata}
            cat = _global_category(entry.id, entry.file or "")
            if cat:
                meta["category"] = cat
            vg.add_spec(
                Spec(uri=uri, title=entry.heading or "", type=spec_type(entry.id, entry.file or "", entry.metadata),
                     version=version, chunk_id=entry.id, file=entry.file or "", metadata=meta)
            )
            v_known[entry.id] = uri
        # Version edges from version markdown @refs (target may be version or baseline)
        version_dir = root / "versions" / version
        if version_dir.exists():
            for path in sorted(version_dir.rglob("*.md")):
                parsed = parse_file(path, version_dir)
                for ref in parsed.refs:
                    src = v_known.get(ref.source_chunk_id)
                    dst = v_known.get(ref.target_chunk_id) or base_known.get(ref.target_chunk_id)
                    if src and dst:
                        vg.add_edge(src, dst, ref.rel, metadata={"source": "version-ref"})
        _preserve_explicit_edges(previous_vg, vg)
        vg.save(specgraph_path(root, version))

    return base


def _preserve_explicit_edges(previous: SpecGraph, current: SpecGraph) -> None:
    """Carry explicit graph edges across scan-based sync."""
    for edge in previous.edges:
        if edge.metadata.get("source") not in {"manual", "new-model-cli"}:
            continue
        current.add_edge(edge.src, edge.dst, edge.rel, weight=edge.weight, metadata=dict(edge.metadata))


def combined_specgraph(project_root: Path, version: str | None = None) -> SpecGraph:
    """Load baseline + (optional) one version graph merged in-memory for queries.

    Used by deps/impact/context/task-build which need cross-version visibility.
    """
    base = load_specgraph(project_root, "baseline")
    if version is None:
        return base
    vg = load_specgraph(project_root, version)
    return base.dry_run_merge(vg)


def combined_view(project_root: Path, version: str | None = None) -> CombinedView:
    """Read-time collapse of baseline (+ optional version) to the chunk_id world.

    Nodes are baseline specs overlaid by version specs; edges are collapsed to
    chunk_id endpoints and deduped. No data migration — storage stays URI-keyed.
    """
    graphs = [load_specgraph(project_root, "baseline")]
    if (
        version
        and version != "baseline"
        and specgraph_path(project_root, version).exists()
    ):
        graphs.append(load_specgraph(project_root, version))

    view = CombinedView()
    uri_to_chunk: dict[str, str] = {}
    for graph in graphs:
        for spec in graph.specs.values():
            uri_to_chunk[spec.uri] = spec.chunk_id
            existing = view.nodes.get(spec.chunk_id)
            # version-side spec wins over baseline regardless of load order
            if (
                existing is not None
                and existing.version != "baseline"
                and spec.version == "baseline"
            ):
                continue
            view.nodes[spec.chunk_id] = ViewNode(
                chunk_id=spec.chunk_id,
                type=spec.type,
                version=spec.version,
                file=spec.file,
                title=spec.title,
                uri=spec.uri,
            )

    def _endpoint(uri: str) -> str | None:
        if uri in uri_to_chunk:
            return uri_to_chunk[uri]
        try:
            return parse_uri(uri)[2]
        except ValueError:
            return None

    seen_edges: set[tuple[str, str, str]] = set()
    for graph in graphs:
        for edge in graph.edges:
            src = _endpoint(edge.src)
            dst = _endpoint(edge.dst)
            if src is None or dst is None:
                continue
            if src not in view.nodes or dst not in view.nodes:
                continue  # dangling edge — write-side validators own this
            key = (src, dst, edge.rel)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            view.edges.append(
                ViewEdge(src=src, dst=dst, rel=edge.rel, metadata=dict(edge.metadata))
            )
    return view


def add_edge(project_root: Path, src: str, dst: str, rel: str) -> SpecGraph:
    graph = load_specgraph(project_root)
    graph.add_edge(src, dst, rel, metadata={"source": "manual"})
    graph.save(specgraph_path(project_root))
    return graph


def resolve_chunk_uri(
    project_root: Path,
    chunk_id_or_uri: str,
    version: str | None = None,
    *,
    graph: "SpecGraph | None" = None,
) -> str:
    if chunk_id_or_uri.startswith("spec:"):
        return chunk_id_or_uri
    if graph is None:
        graph = combined_specgraph(project_root, version)
    candidates = [spec.uri for spec in graph.specs.values() if spec.chunk_id == chunk_id_or_uri]
    if version:
        for uri in candidates:
            if f":{version}:" in uri:
                return uri
    non_baseline = [uri for uri in candidates if ":baseline:" not in uri]
    if non_baseline:
        return sorted(non_baseline)[-1]
    if candidates:
        return sorted(candidates)[-1]
    return make_uri(chunk_id_or_uri, version or "baseline")


def _preferred_uri(known_by_chunk: dict[str, list[str]], chunk_id: str, version: str) -> str | None:
    candidates = known_by_chunk.get(chunk_id, [])
    for uri in candidates:
        if f":{version}:" in uri:
            return uri
    for uri in candidates:
        if ":baseline:" in uri:
            return uri
    return sorted(candidates)[-1] if candidates else None
