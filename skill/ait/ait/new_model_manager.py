"""Managers for v2 PRD/FSD/TDD-side document commands."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .chunk_parser import Chunk, parse_file, parse_text
from .index_manager import IndexManager
from .new_model_validator import check_edge_write, normalize_target_file
from .specgraph import combined_specgraph, combined_view, load_specgraph, resolve_chunk_uri, specgraph_path, sync_specgraph
from .validator import ValidationError, ValidationIssue
from .version_manager import VersionManager

TARGET_FILE_RE = re.compile(r"^\s*target_file:\s*(\S+)\s*$", re.MULTILINE)
NEW_MODEL_RELS = {"decomposes", "details", "depends_on"}


@dataclass(frozen=True)
class DocumentCreateResult:
    version: str
    file: str
    chunks: list[str]
    path: str


@dataclass(frozen=True)
class EdgeCreateResult:
    version: str
    src: str
    dst: str
    rel: str


@dataclass(frozen=True)
class CodegenBundle:
    version: str
    tdd_root: str
    target_file: str
    source_file: str
    chunks: list[dict]
    upstream: list[dict]
    dependencies: list[dict]


class NewModelManager:
    def __init__(self, project_root: Path):
        self.root = project_root.resolve()
        self.versions = VersionManager(self.root)
        self.indexes = IndexManager(self.root)

    def create_fsd(
        self,
        version: str,
        root_chunk_id: str,
        content: str,
        *,
        file: str | None = None,
        action: str = "add",
        overrides: str | None = None,
    ) -> DocumentCreateResult:
        # v2.26/v2.31: sibling depends_on is declared in a transient yaml block
        # inside split content — an input instruction, NOT persisted doc content.
        # Validate BEFORE any write, then STRIP the block so the document body
        # carries zero relation declarations (specgraph is the sole store).
        declared = self._parse_depends_on_declarations(root_chunk_id, content)
        # v2.32 preserve semantic: splits WITHOUT a depends_on block keep their
        # current edges (hydrated) — reformatting an FSD's prose no longer wipes
        # deps. Declared splits (incl. explicit `[]`) authoritatively override.
        prefix = f"{root_chunk_id}:"
        view_before = combined_view(self.root, version)
        hydrated: dict[str, list[str]] = {}
        for cid in view_before.nodes:
            if cid.startswith(prefix) and cid not in declared:
                deps = [e.dst for e in view_before.edges_from(cid, "depends_on")]
                if deps:
                    hydrated[cid] = deps
        clean_content = _strip_depends_on_blocks(content)
        result = self._create_document(
            version,
            root_chunk_id,
            clean_content,
            kind="fsd",
            file=file,
            action=action,
            overrides=overrides,
        )
        # Reconcile AFTER _create_document's sync_specgraph. final_deps carries
        # the file's FULL authoritative set (hydrated preserved + declared), so
        # combined_view/merge per-root scoping stays correct.
        final_deps = {**hydrated, **declared}
        self._reconcile_sibling_depends_on(version, root_chunk_id, final_deps)
        # FSD layer entry: advance the phase machine off the PRD layer.
        meta = self.versions.load_version_meta(version)
        if meta.phase == "prd-confirm":
            meta.phase = "fsd-creating"
            self.versions.save_version_meta(meta)
        return result

    def _parse_depends_on_declarations(
        self, root_chunk_id: str, content: str
    ) -> dict[str, list[str]]:
        """Validate and resolve each split's declared sibling dependencies.

        Shorthand names resolve against the same parent (``store`` →
        ``{root}:store``); full ids must stay same-parent. Rejection happens
        before any write.
        """
        parsed = parse_text(content, file=f"fsd/{root_chunk_id}")
        prefix = f"{root_chunk_id}:"
        split_ids = {c.id for c in parsed.chunks if c.id.startswith(prefix)}
        declared: dict[str, list[str]] = {}
        for chunk in parsed.chunks:
            if not chunk.id.startswith(prefix):
                continue
            names = _split_depends_on(chunk.content)
            if names is None:
                continue  # no block → not declared (preserved via hydrate)
            resolved: list[str] = []
            for name in names:
                dep = name if ":" in name else f"{root_chunk_id}:{name}"
                if ":" in name and _parent_chunk_id(dep) != root_chunk_id:
                    raise _validation_error(
                        "DEPENDS_ON_CROSS_LEVEL",
                        f"{chunk.id} declares cross-parent dependency {dep}",
                        chunk.id,
                    )
                if dep == chunk.id:
                    raise _validation_error(
                        "DEPENDS_ON_SELF",
                        f"{chunk.id} declares a dependency on itself",
                        chunk.id,
                    )
                if dep not in split_ids:
                    raise _validation_error(
                        "DEPENDS_ON_UNKNOWN_SIBLING",
                        f"{chunk.id} declares unknown sibling {dep}",
                        chunk.id,
                    )
                if dep not in resolved:
                    resolved.append(dep)
            declared[chunk.id] = resolved
        return declared

    def _reconcile_sibling_depends_on(
        self, version: str, root_chunk_id: str, declared: dict[str, list[str]]
    ) -> None:
        """Owned-scope reconcile: this file's sibling depends_on edges become a
        pure function of its declarations (same-parent rule makes every legal
        depends_on edge intra-file). Removes stale edges, adds declared ones.
        """
        graph = load_specgraph(self.root, version)
        prefix = f"{root_chunk_id}:"

        def _endpoint_chunk_id(uri: str) -> str:
            spec = graph.specs.get(uri)
            if spec is not None:
                return spec.chunk_id
            try:
                from .specgraph import parse_uri

                return parse_uri(uri)[2]
            except ValueError:
                return uri

        graph.edges = [
            e for e in graph.edges
            if not (e.rel == "depends_on" and _endpoint_chunk_id(e.src).startswith(prefix))
        ]
        uri_by_chunk = {spec.chunk_id: spec.uri for spec in graph.specs.values()}
        from .specgraph import make_uri

        for src, dsts in declared.items():
            src_uri = uri_by_chunk.get(src) or make_uri(src, version)
            for dst in dsts:
                dst_uri = uri_by_chunk.get(dst) or make_uri(dst, version)
                graph.add_edge(
                    src_uri, dst_uri, "depends_on",
                    metadata={"source": "fsd-declaration"},
                )
        graph.save(specgraph_path(self.root, version))

    def decompose_fsd(
        self,
        version: str,
        parent_chunk_id: str,
        child_root_chunk_id: str,
        *,
        content: str | None = None,
        file: str | None = None,
    ) -> EdgeCreateResult:
        """FSD "split-is-edge" entry — the retirement path of ``fsd link``.

        Parent-side gate is front-loaded (before any write) so a rejection
        leaves zero on disk; then the child FSD is written atomically (when
        ``content`` is given) and the decomposes edge is created through the
        full write-time gate. rel is always ``decomposes`` (details belongs to
        the tdd layer).
        """
        view = combined_view(self.root, version)
        self._precheck_decompose_parent(view, parent_chunk_id, child_root_chunk_id)
        if content is not None:
            self.create_fsd(version, child_root_chunk_id, content, file=file)
        edge = self.add_edge(version, parent_chunk_id, child_root_chunk_id, "decomposes")
        meta = self.versions.load_version_meta(version)
        if meta.phase == "prd-confirm":
            meta.phase = "fsd-creating"
            self.versions.save_version_meta(meta)
        return edge

    def _precheck_decompose_parent(self, view, parent_chunk_id: str, child_id: str) -> None:
        """Parent-side decompose gate, evaluable before the child exists."""
        parent = view.node(parent_chunk_id)
        if parent is None:
            raise _validation_error(
                "MISSING_ENDPOINT",
                f"decompose parent {parent_chunk_id} not in graph",
                parent_chunk_id,
            )
        if parent.type == "prd":
            others = [
                e.dst for e in view.edges_from(parent_chunk_id, "decomposes")
                if e.dst != child_id
            ]
            if others:
                raise _validation_error(
                    "PRD_FSD_LINK_NOT_UNIQUE",
                    f"PRD {parent_chunk_id} already decomposes to {others}",
                    parent_chunk_id,
                )

    def confirm_fsd_layer(self, version: str) -> dict:
        """Freeze the FSD layer: lock [FSD]- chunks, phase → fsd-confirm."""
        idx = self.indexes.load_version_index(version)
        fsd_ids = [c.id for c in idx.chunks if c.id.startswith("[FSD]-")]
        if not fsd_ids:
            raise _validation_error(
                "NO_FSD_CHUNKS", f"version {version} has no FSD chunks", version
            )
        working = [
            c.id for c in idx.chunks
            if c.id.startswith("[FSD]-") and c.state == "working"
        ]
        if working:
            self.versions.stage(version, working)
            self.versions.commit(version, "fsd layer confirm")
        meta = self.versions.load_version_meta(version)
        meta.phase = "fsd-confirm"
        self.versions.save_version_meta(meta)
        return {"version": version, "confirmed": working, "phase": "fsd-confirm"}

    def revert_fsd_layer(self, version: str) -> dict:
        """The pair of confirm_fsd_layer: unlock FSD chunks, phase → fsd-creating."""
        idx = self.indexes.load_version_index(version)
        fsd_ids = [
            c.id for c in idx.chunks
            if c.id.startswith("[FSD]-") and c.state in ("committed", "staged")
        ]
        result = self.versions.uncommit(version, fsd_ids)
        meta = self.versions.load_version_meta(version)
        meta.phase = "fsd-creating"
        self.versions.save_version_meta(meta)
        return {"version": version, "reverted": result["reverted"], "phase": "fsd-creating"}

    def create_tdd(
        self,
        version: str,
        root_chunk_id: str,
        content: str,
        *,
        file: str | None = None,
        action: str = "add",
        overrides: str | None = None,
        parent_chunk_id: str | None = None,
    ) -> DocumentCreateResult:
        if not _target_file(content):
            raise _validation_error("TDD_TARGET_FILE_REQUIRED", "TDD markdown must include target_file")
        # v2.20 write-time gate: one artifact ↔ one TDD (normalized paths).
        new_target = normalize_target_file(_target_file(content))
        for owner_id, _owner_file, owner_target in self.collect_tdd_target_files(
            combined_specgraph(self.root, version)
        ):
            if owner_id == root_chunk_id or not owner_target:
                continue  # modifying the same TDD keeps its own target
            if normalize_target_file(owner_target) == new_target:
                raise _validation_error(
                    "DUPLICATE_TARGET_FILE",
                    f"target_file already owned by {owner_id}: {owner_target}",
                    root_chunk_id,
                )
        # v2.24 "create-is-edge": parent-side details gate front-loaded so a
        # rejection leaves zero on disk.
        if parent_chunk_id is not None:
            view = combined_view(self.root, version)
            self._precheck_details_parent(view, parent_chunk_id, root_chunk_id)
        result = self._create_document(
            version,
            root_chunk_id,
            content,
            kind="tdd",
            file=file,
            action=action,
            overrides=overrides,
        )
        if parent_chunk_id is not None:
            self.add_edge(version, parent_chunk_id, root_chunk_id, "details")
        meta = self.versions.load_version_meta(version)
        if meta.phase == "fsd-confirm":
            meta.phase = "tdd-creating"
            self.versions.save_version_meta(meta)
        return result

    def _precheck_details_parent(self, view, parent_chunk_id: str, tdd_root: str) -> None:
        """Parent-side details gate, evaluable before the TDD is written."""
        parent = view.node(parent_chunk_id)
        if parent is None:
            raise _validation_error(
                "MISSING_ENDPOINT",
                f"details parent {parent_chunk_id} not in graph",
                parent_chunk_id,
            )
        others = [
            e.src for e in view.edges_to(tdd_root, "details")
            if e.src != parent_chunk_id
        ]
        if others:
            raise _validation_error(
                "TDD_MULTI_PARENT",
                f"TDD {tdd_root} already has details parent {others}",
                tdd_root,
            )

    def confirm_tdd_layer(self, version: str) -> dict:
        """Freeze the TDD layer: lock [TDD]- chunks, phase → tdd-confirm."""
        idx = self.indexes.load_version_index(version)
        tdd_ids = [c.id for c in idx.chunks if c.id.startswith("[TDD]-")]
        if not tdd_ids:
            raise _validation_error(
                "NO_TDD_CHUNKS", f"version {version} has no TDD chunks", version
            )
        working = [
            c.id for c in idx.chunks
            if c.id.startswith("[TDD]-") and c.state == "working"
        ]
        if working:
            self.versions.stage(version, working)
            self.versions.commit(version, "tdd layer confirm")
        meta = self.versions.load_version_meta(version)
        meta.phase = "tdd-confirm"
        self.versions.save_version_meta(meta)
        return {"version": version, "confirmed": working, "phase": "tdd-confirm"}

    def revert_tdd_layer(self, version: str) -> dict:
        """The pair of confirm_tdd_layer: unlock TDD chunks, phase → tdd-creating."""
        idx = self.indexes.load_version_index(version)
        tdd_ids = [
            c.id for c in idx.chunks
            if c.id.startswith("[TDD]-") and c.state in ("committed", "staged")
        ]
        result = self.versions.uncommit(version, tdd_ids)
        meta = self.versions.load_version_meta(version)
        meta.phase = "tdd-creating"
        self.versions.save_version_meta(meta)
        return {"version": version, "reverted": result["reverted"], "phase": "tdd-creating"}

    def create_prd(
        self,
        version: str,
        root_chunk_id: str,
        content: str,
        *,
        file: str | None = None,
        action: str = "add",
        overrides: str | None = None,
    ) -> DocumentCreateResult:
        result = self._create_document(
            version,
            root_chunk_id,
            content,
            kind="prd",
            file=file,
            action=action,
            overrides=overrides,
        )
        # create_prd is the flow entry: start the phase machine.
        meta = self.versions.load_version_meta(version)
        if meta.phase in (None, "", "empty"):
            meta.phase = "prd-creating"
            self.versions.save_version_meta(meta)
        return result

    def next_version_name(self) -> str:
        """Next v{major}.{minor} after the newest existing version (v0.1 if none).

        Used by CLI ``prd create`` to auto-open a version when none is active —
        the iteration-flow entry point.
        """
        best: tuple[int, int] | None = None
        for meta in self.versions.list_versions():
            match = re.fullmatch(r"v(\d+)\.(\d+)", meta.version)
            if not match:
                continue
            key = (int(match.group(1)), int(match.group(2)))
            if best is None or key > best:
                best = key
        if best is None:
            return "v0.1"
        return f"v{best[0]}.{best[1] + 1}"

    def confirm_prd_layer(self, version: str) -> dict:
        """Freeze the PRD layer: lock [PRD]- chunks, phase → prd-confirm."""
        idx = self.indexes.load_version_index(version)
        prd_ids = [c.id for c in idx.chunks if c.id.startswith("[PRD]-")]
        if not prd_ids:
            raise _validation_error(
                "NO_PRD_CHUNKS", f"version {version} has no PRD chunks", version
            )
        working = [
            c.id for c in idx.chunks
            if c.id.startswith("[PRD]-") and c.state == "working"
        ]
        if working:
            self.versions.stage(version, working)
            self.versions.commit(version, "prd layer confirm")
        meta = self.versions.load_version_meta(version)
        meta.phase = "prd-confirm"
        self.versions.save_version_meta(meta)
        return {"version": version, "confirmed": working, "phase": "prd-confirm"}

    def revert_prd_layer(self, version: str) -> dict:
        """The pair of confirm_prd_layer: unlock PRD chunks, phase → prd-creating."""
        idx = self.indexes.load_version_index(version)
        prd_ids = [
            c.id for c in idx.chunks
            if c.id.startswith("[PRD]-") and c.state in ("committed", "staged")
        ]
        result = self.versions.uncommit(version, prd_ids)
        meta = self.versions.load_version_meta(version)
        meta.phase = "prd-creating"
        self.versions.save_version_meta(meta)
        return {"version": version, "reverted": result["reverted"], "phase": "prd-creating"}

    def add_edge(self, version: str, src: str, dst: str, rel: str) -> EdgeCreateResult:
        if rel not in NEW_MODEL_RELS:
            raise _validation_error(
                "INVALID_NEW_MODEL_REL",
                "new-model relation must be one of: decomposes, details, depends_on",
                src,
            )
        # v2.20 write-time local gate: phantom endpoints / second details
        # parent / second PRD→FSD are never legal — reject before any write.
        # Global completeness (orphans/traces/cycles) belongs to confirm.
        view = combined_view(self.root, version)
        gate = check_edge_write(view, src, dst, rel)
        if gate:
            first = gate[0]
            raise _validation_error(first.code, first.message, first.chunk_id)
        combined = combined_specgraph(self.root, version)
        src_uri = resolve_chunk_uri(self.root, src, version, graph=combined)
        dst_uri = resolve_chunk_uri(self.root, dst, version, graph=combined)
        graph = load_specgraph(self.root, version)
        graph.add_edge(src_uri, dst_uri, rel, metadata={"source": "new-model-cli"})
        graph.save(specgraph_path(self.root, version))
        return EdgeCreateResult(version=version, src=src_uri, dst=dst_uri, rel=rel)

    def prepare_codegen(self, version: str | None, tdd_root_chunk_id: str) -> CodegenBundle:
        if version is None:
            entry = self.indexes.query_baseline(tdd_root_chunk_id)
            base_dir = self.root / "docs"
            source = "baseline"
        else:
            entry = self.indexes.query_version(version, tdd_root_chunk_id)
            base_dir = self.versions.versions_dir / version
            source = "version"
            if entry is None:
                entry = self.indexes.query_baseline(tdd_root_chunk_id)
                base_dir = self.root / "docs"
                source = "baseline"
        if entry is None or entry.file is None:
            raise _validation_error("TDD_NOT_FOUND", f"TDD root chunk {tdd_root_chunk_id} not found", tdd_root_chunk_id)

        path = base_dir / f"{entry.file}.md"
        parsed = parse_file(path, base_dir)
        root = next((chunk for chunk in parsed.chunks if chunk.id == tdd_root_chunk_id), None)
        if root is None:
            raise _validation_error("TDD_NOT_FOUND", f"TDD root chunk {tdd_root_chunk_id} not found", tdd_root_chunk_id)
        target_file = _target_file(root.content) or _target_file(path.read_text(encoding="utf-8"))
        if not target_file:
            raise _validation_error("TDD_TARGET_FILE_REQUIRED", "TDD markdown must include target_file", tdd_root_chunk_id)

        view = combined_view(self.root, version)
        upstream = self._collect_upstream_context(view, tdd_root_chunk_id)
        dependencies = self._collect_dependency_context(view, upstream)

        return CodegenBundle(
            version=version if source == "version" else "baseline",
            tdd_root=tdd_root_chunk_id,
            target_file=target_file,
            source_file=entry.file,
            chunks=[
                {
                    "id": chunk.id,
                    "heading": chunk.heading,
                    "file": chunk.file,
                    "content": chunk.content,
                }
                for chunk in parsed.chunks
            ],
            upstream=upstream,
            dependencies=dependencies,
        )

    def _collect_upstream_context(self, view, tdd_chunk_id: str) -> list[dict]:
        incoming_details = view.edges_to(tdd_chunk_id, "details")
        if not incoming_details:
            return []
        items: list[dict] = []
        seen: set[str] = set()

        parent_split = view.node(incoming_details[0].src)
        if parent_split is None:
            return []
        self._append_context_item(items, seen, parent_split)

        parent_root = view.node(_parent_chunk_id(parent_split.chunk_id))
        if parent_root is not None and parent_root.chunk_id not in seen:
            self._append_context_item(items, seen, parent_root)
            self._walk_upstream_roots(view, parent_root.chunk_id, items, seen)
        return items

    def _walk_upstream_roots(self, view, root_chunk_id: str, items: list[dict], seen: set[str]) -> None:
        for edge in view.edges_to(root_chunk_id, "decomposes"):
            src = view.node(edge.src)
            if src is None or src.chunk_id in seen:
                continue
            self._append_context_item(items, seen, src)
            if src.type == "fsd" and ":" in src.chunk_id:
                parent_root = view.node(_parent_chunk_id(src.chunk_id))
                if parent_root is not None and parent_root.chunk_id not in seen:
                    self._append_context_item(items, seen, parent_root)
                    self._walk_upstream_roots(view, parent_root.chunk_id, items, seen)

    def _collect_dependency_context(self, view, upstream: list[dict]) -> list[dict]:
        """Collect depends_on context from every FSD internal split in the upstream
        chain — not just the immediate parent module split.

        depends_on edges live at the domain-split level (e.g. ``[FSD]-ait:version``
        ↔ ``[FSD]-ait:doc_model``) because the model only allows same-parent
        siblings. A module split (``[FSD]-ait-version:version_manager``) therefore
        has no depends_on of its own; we must climb to the domain split — which is
        already part of the upstream chain — to surface real dependencies.
        """
        split_ids = [
            u["id"] for u in upstream
            if u.get("type") == "fsd" and ":" in u.get("id", "")
        ]
        items: list[dict] = []
        seen: set[str] = set()
        for split_id in split_ids:
            for edge in view.edges_from(split_id, "depends_on"):
                split = view.node(edge.dst)
                if split is None:
                    continue
                self._append_context_item(items, seen, split)
                for child_edge in view.edges_from(edge.dst):
                    if child_edge.rel not in {"decomposes", "details"}:
                        continue
                    child = view.node(child_edge.dst)
                    if child is not None:
                        self._append_context_item(items, seen, child)
        return items

    def _append_context_item(self, items: list[dict], seen: set[str], spec) -> None:
        if spec.chunk_id in seen:
            return
        seen.add(spec.chunk_id)
        item = self._context_item_for_spec(spec)
        if item is not None:
            items.append(item)

    def _context_item_for_spec(self, spec) -> dict | None:
        base_dir = self.versions.versions_dir / spec.version if spec.version != "baseline" else self.root / "docs"
        path = base_dir / f"{spec.file}.md"
        if not path.exists():
            return None
        parsed = parse_file(path, base_dir)
        chunk = next((c for c in parsed.chunks if c.id == spec.chunk_id), None)
        if chunk is None:
            return None
        return {
            "uri": spec.uri,
            "id": chunk.id,
            "type": spec.type,
            "version": spec.version,
            "file": chunk.file,
            "heading": chunk.heading,
            "content": chunk.content,
        }

    def _find_spec_by_chunk_id(self, graph, chunk_id: str, preferred_version: str | None = None):
        candidates = [spec for spec in graph.specs.values() if spec.chunk_id == chunk_id]
        if preferred_version:
            for spec in candidates:
                if spec.version == preferred_version:
                    return spec
        for spec in candidates:
            if spec.version == "baseline":
                return spec
        return sorted(candidates, key=lambda spec: spec.uri)[-1] if candidates else None

    def collect_tdd_target_files(self, graph) -> list[tuple[str, str | None, str | None]]:
        """Return ``(chunk_id, file, target_file)`` for each TDD root chunk in ``graph``.

        Only root chunks (file stem == chunk id) are considered; internal TDD
        detail chunks are skipped. When the same chunk id appears in both the
        active version and baseline, the version-side entry wins. ``target_file``
        is read from the TDD markdown body (markdown is the source of truth).
        """
        seen: dict[str, tuple[str, str | None, str | None]] = {}
        for spec in graph.specs.values():
            if spec.type != "tdd":
                continue
            if not spec.file or _file_stem(spec.file) != spec.chunk_id:
                continue  # root chunks only
            if spec.chunk_id in seen and spec.version == "baseline":
                continue  # keep the already-seen (version-side) entry
            seen[spec.chunk_id] = (
                spec.chunk_id,
                spec.file,
                self._read_target_file_for_spec(spec),
            )
        return list(seen.values())

    def _read_target_file_for_spec(self, spec) -> str | None:
        base_dir = (
            self.versions.versions_dir / spec.version
            if spec.version != "baseline"
            else self.root / "docs"
        )
        path = base_dir / f"{spec.file}.md"
        if not path.exists():
            return None
        return _target_file(path.read_text(encoding="utf-8"))

    def _create_document(
        self,
        version: str,
        root_chunk_id: str,
        content: str,
        *,
        kind: str,
        file: str | None,
        action: str,
        overrides: str | None,
    ) -> DocumentCreateResult:
        file = _validated_index_path(file, kind) if file else f"{kind}/{root_chunk_id}"
        parsed = parse_text(content, file=file)
        root = next((chunk for chunk in parsed.chunks if chunk.id == root_chunk_id), None)
        if root is None:
            raise _validation_error(
                "ROOT_CHUNK_REQUIRED",
                f"{kind.upper()} markdown must include root chunk {root_chunk_id}",
                root_chunk_id,
            )

        # v2.26 version-entry closure (R3-04 complete): only prd is the entry
        # layer — fsd/tdd require an existing version, no silent ghost create.
        if kind in ("fsd", "tdd"):
            if not self.versions.version_meta_path(version).exists():
                raise _validation_error(
                    "VERSION_NOT_FOUND",
                    f"version {version} does not exist — run `version create` or `prd create` first",
                    root_chunk_id,
                )
        else:
            self.versions.ensure(version)
        path = self.versions.write_version_file(version, file, content)
        final_parsed = parse_file(path, self.versions.versions_dir / version)
        chunk_ids: list[str] = []
        for chunk in final_parsed.chunks:
            self.versions.add_chunk(
                version,
                chunk=chunk,
                action=action,  # type: ignore[arg-type]
                overrides=overrides if chunk.id == root_chunk_id else None,
            )
            chunk_ids.append(chunk.id)
        sync_specgraph(self.root)
        return DocumentCreateResult(
            version=version,
            file=file,
            chunks=chunk_ids,
            path=str(path.relative_to(self.root)).replace("\\", "/"),
        )


def _validated_index_path(file: str, kind: str) -> str:
    """Sanitize a --file index path (audit R3-02): must stay inside its own
    kind directory, no escape segments, no .md suffix. Rejection = zero write.
    """
    norm = (file or "").strip().replace("\\", "/")
    segments = norm.split("/")
    bad = (
        not norm
        or norm.endswith(".md")
        or norm.startswith("/")
        or norm.startswith(".")
        or re.match(r"^[A-Za-z]:", norm) is not None
        or ".." in segments
        or "" in segments
    )
    if bad:
        raise _validation_error(
            "INVALID_FILE_NAME",
            f"--file only accepts a relative index path under {kind}/ (no .md): {file!r}",
        )
    if "/" not in norm:
        norm = f"{kind}/{norm}"
    if not norm.startswith(f"{kind}/"):
        raise _validation_error(
            "INVALID_FILE_NAME",
            f"--file must stay under {kind}/ (cross-kind rejected): {file!r}",
        )
    return norm


def _target_file(text: str) -> str | None:
    match = TARGET_FILE_RE.search(text)
    return match.group(1).strip() if match else None


_YAML_FENCE_RE = re.compile(r"```yaml\s*\n(.*?)```", re.DOTALL)
# Full-fence matcher (incl. delimiters + optional trailing blank line) for stripping.
_YAML_FENCE_FULL_RE = re.compile(r"```yaml\s*\n(?P<body>.*?)```[ \t]*\n?", re.DOTALL)


def _split_depends_on(chunk_content: str) -> list[str] | None:
    """Declared sibling dependencies from a split chunk's yaml fence block.

    v2.32 distinguishes "not declared" from "explicitly cleared":
      - no yaml block with a ``depends_on`` key → ``None`` (preserve existing)
      - ``depends_on: []`` / null → ``[]`` (explicit clear)
      - ``depends_on: [a, b]`` → ``["a", "b"]``
    """
    import yaml

    for block in _YAML_FENCE_RE.findall(chunk_content):
        try:
            loaded = yaml.safe_load(block)
        except Exception:
            continue
        if isinstance(loaded, dict) and "depends_on" in loaded:
            value = loaded["depends_on"]
            if isinstance(value, list):
                return [str(item) for item in value]
            return []
    return None


def _strip_depends_on_blocks(content: str) -> str:
    """Remove transient ``depends_on:`` yaml fence blocks from FSD markdown.

    The declaration is an input instruction consumed to build specgraph edges,
    never persisted doc content (a chunk↔chunk relation belongs only in
    specgraph). Non-depends_on yaml fences are left untouched.
    """
    import yaml

    def _drop(match: "re.Match[str]") -> str:
        try:
            loaded = yaml.safe_load(match.group("body"))
        except Exception:
            return match.group(0)
        if isinstance(loaded, dict) and "depends_on" in loaded:
            return ""
        return match.group(0)

    return _YAML_FENCE_FULL_RE.sub(_drop, content)


def _parent_chunk_id(chunk_id: str) -> str:
    return chunk_id.split(":", 1)[0]


def _file_stem(file: str) -> str:
    return file.rsplit("/", 1)[-1]


def _validation_error(code: str, message: str, chunk_id: str | None = None) -> ValidationError:
    return ValidationError(
        [
            ValidationIssue(
                severity="E1",
                code=code,
                message=message,
                chunk_id=chunk_id,
            )
        ]
    )
